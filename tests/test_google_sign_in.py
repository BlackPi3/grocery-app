"""Sign in with Google, on made-up addresses and a fake Google.

The owner's address is configuration (`GROCERY_OWNER_EMAIL`); since
2026-10-14 any other verified address is a user, made at its first sign-in
(who may sign in at all is Google's to say: its test users while in Testing).
A sign-in is a token kept as a hash, with an end date. No test reaches
Google: the verifier is passed in.
"""

from __future__ import annotations

import hashlib
import io
import time
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from grocery_app.api.app import create_app
from grocery_app.api.google_sign_in import (
    GoogleSignIn,
    GoogleUnavailable,
    NotSignedIn,
    configured,
)
from grocery_app.api.images import DiskImageStore
from grocery_app.api.repository import PostgresRepository
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL as URL
from tests.test_upload import FakeExtractor

CLIENT_ID = "1234-test.apps.googleusercontent.com"
OWNER = {"Authorization": "Bearer owner-secret"}


def claims(email: str | None, **changed) -> dict:
    return {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "email": email,
            "email_verified": True, "exp": time.time() + 3600, **changed}


class FakeGoogle:
    """Stands in for Google's signature check: a token is valid when it is one
    of the keys here, and says what its value says."""

    def __init__(self, tokens: dict[str, dict]) -> None:
        self.tokens = tokens

    def __call__(self, credential: str, client_id: str) -> dict:
        if credential not in self.tokens:
            raise ValueError("Could not verify token signature.")
        return self.tokens[credential]


def google(tokens: dict[str, dict], owner: str | None = "chef@example.com") -> GoogleSignIn:
    return GoogleSignIn(CLIENT_ID, owner, FakeGoogle(tokens))


# --- what a token must say ---------------------------------------------------------

def test_a_token_names_a_verified_address_for_this_app():
    sign_in = google({
        "good": claims("Chef@Example.com"),
        "other-app": claims("chef@example.com", aud="9999-other.apps.googleusercontent.com"),
        "not-google": claims("chef@example.com", iss="https://evil.example.com"),
        "stale": claims("chef@example.com", exp=time.time() - 1),
        "unverified": claims("chef@example.com", email_verified=False),
        "no-address": claims(None),
    })
    assert sign_in.email("good") == "chef@example.com", "kept in lower case"
    assert sign_in.is_owner("CHEF@example.com ")
    for token, why in (("forged", "valid"), ("other-app", "another app"),
                       ("not-google", "not made by Google"), ("stale", "expired"),
                       ("unverified", "not verified"), ("no-address", "no address")):
        with pytest.raises(NotSignedIn, match=why):
            sign_in.email(token)


def test_off_until_a_client_id_is_set():
    assert configured({}) is None
    assert configured({"GOOGLE_CLIENT_ID": " ", "GROCERY_OWNER_EMAIL": "a@b.de"}) is None
    on = configured({"GOOGLE_CLIENT_ID": CLIENT_ID, "GROCERY_OWNER_EMAIL": " Chef@Example.com"},
                    verify=FakeGoogle({}))
    assert (on.client_id, on.owner_email) == (CLIENT_ID, "chef@example.com")
    assert configured({"GOOGLE_CLIENT_ID": CLIENT_ID}, verify=FakeGoogle({})).owner_email is None


# --- on the server ----------------------------------------------------------------

pytestmark_db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")


def photo(colour: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 60), colour).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def server(engine, session, tmp_path):
    repository = PostgresRepository(make_session_factory(engine))
    tokens = {"chef": claims("chef@example.com"), "sara": claims("sara@example.com"),
              "stranger": claims("stranger@example.com"),
              "lea": claims("lea@example.com", given_name="Lea", name="Lea Muster"),
              "other-lea": claims("lea.b@example.com", given_name="Lea"),
              "sara-unverified": claims("sara@example.com", email_verified="false"),
              "sara-other-app": claims("sara@example.com", aud="9999-other")}

    def make(**options):
        return TestClient(create_app(repository, DiskImageStore(tmp_path), FakeExtractor(),
                                     **{"token": "owner-secret", "google": google(tokens),
                                        **options}))

    return make, repository, session


def bearer(signed_in: dict) -> dict:
    return {"Authorization": f"Bearer {signed_in['token']}"}


@pytestmark_db
def test_the_owner_signs_in_with_their_google_address(server):
    make, _, session = server
    client = make()
    assert client.get("/v1/auth/config").json() == {"google_client_id": CLIENT_ID}
    made = client.post("/v1/auth/google", json={"credential": "chef"})
    assert made.status_code == 200
    body = made.json()
    assert (body["role"], body["name"]) == ("owner", None)
    assert client.get("/v1/me", headers=bearer(body)).json()["role"] == "owner"
    assert client.get("/v1/costs", headers=bearer(body)).status_code == 200
    kept = session.execute(text("SELECT token_sha256, email FROM sign_ins")).all()
    assert len(kept) == 1 and kept[0].email == "chef@example.com"
    assert kept[0].token_sha256 == hashlib.sha256(body["token"].encode()).hexdigest(), \
        "only its hash is kept"


@pytestmark_db
def test_an_invited_person_signs_in_and_sees_only_their_receipts(server):
    make, _, _ = server
    client = make()
    added = client.post("/v1/users", headers=OWNER,
                        json={"name": "Sara", "email": " Sara@Example.com "})
    assert added.status_code == 201
    assert added.json()["email"] == "sara@example.com" and added.json()["password"]
    mine = client.post("/v1/receipts", headers=OWNER,
                       files={"file": ("a.jpg", photo("red"), "image/jpeg")}).json()

    hers = client.post("/v1/auth/google", json={"credential": "sara"}).json()
    assert (hers["role"], hers["name"]) == ("user", "Sara")
    assert client.get("/v1/me", headers=bearer(hers)).json() == \
        {"role": "user", "name": "Sara", "demo": False, "contact": None}
    assert client.get("/v1/receipts", headers=bearer(hers)).json() == []
    job = client.post("/v1/receipts", headers=bearer(hers),
                      files={"file": ("b.jpg", photo("blue"), "image/jpeg")}).json()
    receipt = client.get(f"/v1/jobs/{job['job_id']}", headers=bearer(hers)).json()["receipt_id"]
    owners = client.get(f"/v1/jobs/{mine['job_id']}", headers=OWNER).json()["receipt_id"]
    assert [r["receipt_id"] for r in client.get("/v1/receipts", headers=bearer(hers)).json()] \
        == [receipt]
    assert client.get(f"/v1/receipts/{owners}", headers=bearer(hers)).status_code == 404
    assert client.get("/v1/users", headers=bearer(hers)).status_code == 403
    assert [(u["name"], u["email"]) for u in client.get("/v1/users", headers=OWNER).json()] \
        == [("Sara", "sara@example.com")]


@pytestmark_db
def test_a_first_google_sign_in_makes_the_person_s_account(server):
    """The owner, 2026-10-14: no People card. Who may sign in is Google's to
    say (its test users while the consent screen is in Testing); a first
    sign-in makes the user, named as Google names them."""
    make, _, _ = server
    client = make()
    lea = client.post("/v1/auth/google", json={"credential": "lea"}).json()
    assert (lea["role"], lea["name"]) == ("user", "Lea")
    again = client.post("/v1/auth/google", json={"credential": "lea"}).json()
    assert again["name"] == "Lea", "the same account the next time"
    other = client.post("/v1/auth/google", json={"credential": "other-lea"}).json()
    assert other["name"] == "Lea (lea.b@example.com)", "a name taken gets the address beside it"
    nameless = client.post("/v1/auth/google", json={"credential": "stranger"}).json()
    assert nameless["name"] == "stranger", "no name on Google: the address's first part"
    assert client.get("/v1/receipts", headers=bearer(lea)).json() == [], "their own, empty"
    assert [(u["name"], u["email"]) for u in client.get("/v1/users", headers=OWNER).json()] == [
        ("Lea", "lea@example.com"), ("Lea (lea.b@example.com)", "lea.b@example.com"),
        ("stranger", "stranger@example.com")]


@pytestmark_db
def test_nobody_gets_in_unverified_or_forged(server):
    make, _, session = server
    client = make()
    for credential in ("sara-unverified", "sara-other-app", "forged"):
        assert client.post("/v1/auth/google",
                           json={"credential": credential}).status_code == 401, credential
    assert session.execute(text("SELECT count(*) FROM sign_ins")).scalar() == 0
    assert session.execute(text("SELECT count(*) FROM users")).scalar() == 0

def from_google(client: TestClient, credential: str, form_token: str = "csrf-1",
                cookie: str | None = "csrf-1") -> dict[str, str]:
    """What Google's redirect mode does: a form POST with the ID token and a
    CSRF token that must match the cookie Google's script set. Returns what
    the page receives after the "#"."""
    client.cookies.clear()
    if cookie is not None:
        client.cookies.set("g_csrf_token", cookie)
    answer = client.post("/v1/auth/google/redirect", follow_redirects=False,
                         data={"credential": credential, "g_csrf_token": form_token})
    assert answer.status_code == 303
    place, _, after = answer.headers["location"].partition("#")
    assert place == "/"
    key, _, value = after.partition("=")
    return {key: unquote(value)}


@pytestmark_db
def test_the_page_signs_in_through_google_s_redirect(server, caplog):
    """2026-10-13: on the owner's phone the pop-up never handed its answer
    back, so the page sends Google's answer to the server instead."""
    make, _, session = server
    client = make()
    client.post("/v1/users", headers=OWNER, json={"name": "Sara", "email": "sara@example.com"})
    chef = from_google(client, "chef")
    assert client.get("/v1/me", headers=bearer({"token": chef["google"]})).json()["role"] \
        == "owner"
    assert "not a valid Google sign-in" in from_google(client, "forged")["google-error"]
    for form_token, cookie in (("csrf-1", None), ("csrf-1", "csrf-2"), ("", "")):
        assert "could not be checked" in \
            from_google(client, "sara", form_token, cookie)["google-error"], "another site's form"
    assert session.execute(text("SELECT count(*) FROM sign_ins")).scalar() == 1
    refused = [r.getMessage() for r in caplog.records if "sign-in refused" in r.getMessage()]
    assert refused[0].startswith("Google sign-in refused: not a valid Google sign-in"), \
        "why is in the server's log"
    assert "Google sign-in refused: the CSRF cookie is missing" in refused


@pytestmark_db
def test_a_sign_in_ends(server):
    make, repository, session = server
    client = make()
    sara = client.post("/v1/users", headers=OWNER,
                       json={"name": "Sara", "email": "sara@example.com"}).json()
    lea = client.post("/v1/users", headers=OWNER,
                      json={"name": "Lea", "email": "lea@example.com"}).json()
    hers, chef, leas = (repository.start_sign_in(u, e) for u, e in (
        ({"id": sara["id"]}, "sara@example.com"), (None, "chef@example.com"),
        ({"id": lea["id"]}, "lea@example.com")))
    for signed_in in (hers, chef, leas):
        assert client.get("/v1/me", headers=bearer(signed_in)).status_code == 200

    # When its end date passes.
    session.execute(text("UPDATE sign_ins SET expires_at = now() - interval '1 second' "
                         "WHERE email = 'lea@example.com'"))
    session.commit()
    assert client.get("/v1/me", headers=bearer(leas)).status_code == 401
    # When the owner takes the address away; her password still works.
    assert client.patch(f"/v1/users/{sara['id']}", headers=OWNER,
                        json={"email": None}).json()["email"] is None
    assert client.get("/v1/me", headers=bearer(hers)).status_code == 401
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {sara['password']}"}) \
        .json()["name"] == "Sara"
    # When the owner's address changes, or Google sign-in is switched off.
    moved = make(google=GoogleSignIn(CLIENT_ID, "new-chef@example.com", FakeGoogle({})))
    assert moved.get("/v1/me", headers=bearer(chef)).status_code == 401
    assert make(google=None).get("/v1/me", headers=bearer(chef)).status_code == 401
    # When the person signs out.
    assert client.post("/v1/auth/sign-out", headers=bearer(chef)).status_code == 204
    assert client.get("/v1/me", headers=bearer(chef)).status_code == 401


@pytestmark_db
def test_a_removed_users_sign_in_ends_with_them(server):
    make, repository, session = server
    client = make()
    sara = client.post("/v1/users", headers=OWNER,
                       json={"name": "Sara", "email": "sara@example.com"}).json()
    hers = client.post("/v1/auth/google", json={"credential": "sara"}).json()
    assert client.get("/v1/me", headers=bearer(hers)).status_code == 200
    session.execute(text("DELETE FROM users WHERE id = :id"), {"id": sara["id"]})
    session.commit()
    assert client.get("/v1/me", headers=bearer(hers)).status_code == 401
    assert session.execute(text("SELECT count(*) FROM sign_ins")).scalar() == 0, \
        "the row goes with the user"


@pytestmark_db
def test_the_owner_invites_by_address(server):
    make, _, _ = server
    client = make()
    sara = client.post("/v1/users", headers=OWNER, json={"name": "Sara"}).json()
    assert sara["email"] is None, "a password only, as before"
    for email, why in (("SARA", "not an email"), ("chef@example.com", "owner's own")):
        refused = client.post("/v1/users", headers=OWNER, json={"name": "Eve", "email": email})
        assert refused.status_code == 422 and why in refused.json()["detail"], email
    assert client.patch(f"/v1/users/{sara['id']}", headers=OWNER,
                        json={"email": "Sara@example.com"}).json()["email"] == "sara@example.com"
    taken = client.post("/v1/users", headers=OWNER, json={"name": "Eve",
                                                          "email": "sara@example.com"})
    assert taken.status_code == 422 and "Sara already" in taken.json()["detail"]
    assert client.patch("/v1/users/999", headers=OWNER, json={"email": None}).status_code == 404
    hers = client.post("/v1/auth/google", json={"credential": "sara"}).json()
    assert client.patch(f"/v1/users/{sara['id']}", headers=bearer(hers),
                        json={"email": None}).status_code == 403


@pytestmark_db
def test_google_alone_locks_the_server(server):
    """Without GROCERY_TOKEN a server is open, as on the laptop; with Google
    sign-in on, it is not."""
    make, _, _ = server
    client = make(token=None)
    assert client.get("/v1/receipts").status_code == 401
    owner = client.post("/v1/auth/google", json={"credential": "chef"}).json()
    assert client.get("/v1/receipts", headers=bearer(owner)).status_code == 200


@pytestmark_db
def test_off_without_a_client_id_and_in_the_demo(server):
    make, _, _ = server
    for client in (make(google=None), make(google=None, token=None),
                   make(token=None, demo=True)):
        assert client.get("/v1/auth/config").json() == {"google_client_id": None}
        assert client.post("/v1/auth/google", json={"credential": "chef"}).status_code == 404


@pytestmark_db
def test_google_unreachable_is_a_503(server):
    make, _, _ = server

    def unreachable(credential, client_id):
        raise GoogleUnavailable("Google's keys could not be fetched")

    client = make(google=GoogleSignIn(CLIENT_ID, "chef@example.com", unreachable))
    assert client.post("/v1/auth/google", json={"credential": "chef"}).status_code == 503
