"""Accounts: the owner and users, on made-up receipts.

Parham, 2026-10-11: a designer uses the app with her own receipts. Each
person sees only their own receipts and numbers; the catalog and the memory
are shared; a user's answers teach the memory "with a grain of salt": they
replace a machine's guess, never the owner's answer, and the owner's answer
replaces theirs.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from grocery_app import memory
from grocery_app.api.app import create_app
from grocery_app.api.images import DiskImageStore
from grocery_app.api.repository import NotFound, PostgresRepository
from grocery_app.db.io import receipt_from_dict
from grocery_app.db.models import LineResolution, Product, Resolution
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL as URL
from tests.test_upload import RECEIPT, FakeExtractor, todays

OWNER = {"Authorization": "Bearer owner-secret"}


def photo(colour: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 60), colour).save(buffer, format="JPEG")
    return buffer.getvalue()


# --- the memory's rule, alone --------------------------------------------------

def test_a_user_never_changes_what_the_owner_told_the_memory():
    owners = {"product_id": "p-1", "product_ids": [], "confirmed_by": "shopper"}
    assert memory.learn(owners, "p-2", "user") is None
    assert memory.disagrees(owners, "p-2") == "p-1"
    assert memory.disagrees(owners, "p-1") is None


def test_a_user_replaces_a_guess_and_the_owner_replaces_a_user():
    guess = {"product_id": "p-1", "product_ids": [], "confirmed_by": "identify"}
    assert memory.learn(guess, "p-2", "user") == {"product_id": "p-2", "product_ids": []}
    hers = {"product_id": "p-2", "product_ids": [], "confirmed_by": "user:Sara"}
    assert memory.learn(hers, "p-3", "owner") == {"product_id": "p-3", "product_ids": []}, \
        "replaced, not made a family: her word weighs less than his"
    assert memory.learn(hers, "p-3", "user") == {"product_id": None,
                                                 "product_ids": ["p-2", "p-3"]}, \
        "two users who differ: the till prints one name for two products"
    assert memory.disagrees(hers, "p-3") is None, "only the owner's word is disagreed with"


def test_who_wrote_an_entry():
    assert [memory.author_kind(a) for a in ("matcher", "identify", "user:Sara", "shopper",
                                            None)] == \
        ["machine", "machine", "user", "owner", "owner"]


# --- on the server --------------------------------------------------------------

pytestmark_db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")


@pytest.fixture
def two_people(engine, session, tmp_path):
    for pid, name in (("p-0001", "Butter"), ("p-0002", "Margarine"), ("p-0003", "Quark"),
                      ("p-0004", "Skyr")):
        session.add(Product(id=pid, name=name, brand="Muster"))
    session.commit()
    repository = PostgresRepository(make_session_factory(engine))
    sara = repository.create_user("Sara")
    client = TestClient(create_app(repository, DiskImageStore(tmp_path),
                                   FakeExtractor(todays(RECEIPT)), token="owner-secret"))
    return client, repository, {"Authorization": f"Bearer {sara['password']}"}


@pytestmark_db
def test_each_person_sees_only_their_own(two_people):
    client, repository, sara = two_people
    mine = client.post("/v1/receipts", headers=OWNER,
                       files={"file": ("a.jpg", photo("red"), "image/jpeg")}).json()
    # The same paper, minute and total: another person's shopping, never a duplicate.
    hers = client.post("/v1/receipts", headers=sara,
                       files={"file": ("b.jpg", photo("blue"), "image/jpeg")}).json()
    mine = client.get(f"/v1/jobs/{mine['job_id']}", headers=OWNER).json()
    hers = client.get(f"/v1/jobs/{hers['job_id']}", headers=sara).json()
    assert not hers["already_added"] and hers["receipt_id"] != mine["receipt_id"]
    # A spot check on each receipt, as the matcher would leave one.
    from grocery_app.db.models import Check, Resolution
    session = repository.session_factory()
    session.add(Resolution(store="Musterladen", raw_name="MU Butter", line_type="product",
                           product_id="p-0001", confirmed_by="identify"))
    session.add(Product(id="p-0009", name="Süßrahmbutter", brand="Muster",
                        details=["mild gesäuert"]))
    session.query(Resolution).filter_by(raw_name="MU Butter").update({"product_id": "p-0009"})
    for receipt_id in (mine["receipt_id"], hers["receipt_id"]):
        session.add(Check(receipt_id=receipt_id, position=0, raw_name="MU Butter",
                          app_product_id="p-0009"))
    session.commit()
    session.close()

    seen = {}
    for headers, own, other in ((OWNER, mine, hers), (sara, hers, mine)):
        assert [r["receipt_id"] for r in client.get("/v1/receipts", headers=headers).json()] \
            == [own["receipt_id"]]
        assert client.get(f"/v1/jobs/{other['job_id']}", headers=headers).status_code == 404
        theirs = other["receipt_id"]
        assert client.get(f"/v1/receipts/{theirs}", headers=headers).status_code == 404
        assert client.put(f"/v1/receipts/{theirs}/lines/0/resolution", headers=headers,
                          json={"product_id": "p-0001"}).status_code == 404
        assert client.put(f"/v1/receipts/{theirs}/lines/0/counted", headers=headers,
                          json={"counted": False}).status_code == 404
        assert client.patch(f"/v1/receipts/{theirs}", headers=headers,
                            json={"store": "Anderswo"}).status_code == 404
        assert client.delete(f"/v1/receipts/{theirs}", headers=headers).status_code == 404
        seen[own["job_id"]] = {p["source_image"] for p in
                               client.get("/v1/purchases", headers=headers).json()["purchases"]}
        assert len(seen[own["job_id"]]) == 1
        assert client.get("/v1/insights", headers=headers).json()["coverage"]["receipts"] == 1
        for question in client.get("/v1/questions", headers=headers).json()["questions"]:
            assert question["receipt_id"] == own["receipt_id"]
        assert [c["receipt_id"] for c in
                client.get("/v1/checks", headers=headers).json()["checks"]] == [own["receipt_id"]]
        assert [j["job_id"] for j in client.get("/v1/jobs", headers=headers).json()["jobs"]] \
            in ([], [own["job_id"]])

    assert seen[mine["job_id"]].isdisjoint(seen[hers["job_id"]])
    assert client.get("/v1/me", headers=sara).json() == \
        {"role": "user", "name": "Sara", "demo": False, "contact": None}
    assert client.get("/v1/me", headers=OWNER).json() == \
        {"role": "owner", "name": None, "demo": False, "contact": None}
    for path in ("/v1/costs", "/v1/users", "/v1/sureness"):
        assert client.get(path, headers=sara).status_code == 403, path
    assert client.post("/v1/users", headers=sara, json={"name": "Eve"}).status_code == 403
    assert client.get("/v1/receipts",
                      headers={"Authorization": "Bearer guessed"}).status_code == 401


@pytestmark_db
def test_the_owner_adds_a_user_and_sees_the_password_once(two_people, session):
    client, _, _ = two_people
    made = client.post("/v1/users", headers=OWNER, json={"name": "Lea"})
    assert made.status_code == 201
    password = made.json()["password"]
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {password}"}).json() == \
        {"role": "user", "name": "Lea", "demo": False, "contact": None}
    assert [u["name"] for u in client.get("/v1/users", headers=OWNER).json()] == ["Sara", "Lea"]
    assert client.post("/v1/users", headers=OWNER, json={"name": "lea"}).status_code == 422
    from grocery_app.db.models import User
    assert password not in {u.token_sha256 for u in session.query(User)}, "only its hash is kept"


@pytestmark_db
def test_the_owner_sees_how_each_person_uses_the_app(two_people, session):
    """The People card: receipts, last sign-in and photo, and this month's cost,
    each person's own and nobody else's (owner, 2026-10-15)."""
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from grocery_app.db.models import Job, ModelCall

    client, owner, sara = two_people
    lea = owner.create_user("Lea", "lea@example.com")
    hers = client.post("/v1/receipts", headers=sara,
                       files={"file": ("b.jpg", photo("blue"), "image/jpeg")}).json()
    client.post("/v1/receipts", headers=OWNER,
                files={"file": ("a.jpg", photo("red"), "image/jpeg")})
    owner.start_sign_in({"id": lea["id"], "name": "Lea"}, "lea@example.com")
    now = datetime.now(UTC)
    job = session.get(Job, uuid.UUID(hers["job_id"]))
    owners_job = session.query(Job).filter(Job.user_id.is_(None)).one()
    session.add_all([
        ModelCall(purpose="finding", job_id=job.id, model="m", cost_usd=Decimal("0.25"), at=now),
        # Last month's, and the owner's own: neither is her cost this month.
        ModelCall(purpose="reading", job_id=job.id, model="m", cost_usd=Decimal("1.00"),
                  at=now.replace(day=1) - timedelta(days=1)),
        ModelCall(purpose="reading", job_id=owners_job.id, model="m",
                  cost_usd=Decimal("2.00"), at=now),
    ])
    session.commit()

    people = {u["name"]: u for u in client.get("/v1/users", headers=OWNER).json()}
    assert people["Sara"]["receipts"] == 1
    assert people["Sara"]["last_upload"] is not None
    assert people["Sara"]["last_sign_in"] is None, "she uses a password"
    assert people["Sara"]["month_cost_usd"] == 0.25
    assert people["Lea"] == {"id": lea["id"], "name": "Lea", "email": "lea@example.com",
                             "receipts": 0, "last_sign_in": people["Lea"]["last_sign_in"],
                             "last_upload": None, "month_cost_usd": 0.0}
    assert people["Lea"]["last_sign_in"] is not None


def add_receipt(session, source_image, raw_names, user_id=None):
    receipt = receipt_from_dict({
        "source_image": source_image, "transcribed_by": "llm", "store": "Musterladen",
        "date": "2026-03-01", "currency": "EUR", "printed_total": 1.0 * len(raw_names),
        "lines": [{"type": "product", "raw_name": name, "qty": 1, "gross": 1.0,
                   "discount": 0.0, "net": 1.0, "tax_class": "A"} for name in raw_names]})
    # Uploaded the day it was printed: not an old receipt (`cards.too_old_to_ask`).
    receipt.created_at = datetime(2026, 3, 1, 12, tzinfo=UTC)
    receipt.user_id = user_id
    session.add(receipt)
    session.commit()
    return receipt.id


def line(view, position=0):
    found = view["lines"][position]
    return found["product_id"], found["said_by"]


@pytestmark_db
def test_her_answers_weigh_less_than_the_owners(two_people, session):
    _, owner, _ = two_people
    sara = owner.as_user({"id": owner.users()[0]["id"], "name": "Sara"})
    mine = add_receipt(session, "IMG_1.jpeg", ["MU Butter", "MU Quark"])
    hers = add_receipt(session, "IMG_2.jpeg", ["MU Butter", "MU Quark"], sara.user_id)

    # The owner says what `MU Butter` is; she says it was something else.
    owner.set_line_resolution(mine, 0, "p-0001")
    view = sara.set_line_resolution(hers, 0, "p-0002", confirmed_by="shopper")
    assert line(view) == ("p-0002", "you"), "her answer holds for her own line"
    remembered = session.query(Resolution).filter_by(raw_name="MU Butter").one()
    assert (remembered.product_id, remembered.confirmed_by) == ("p-0001", "shopper"), \
        "the owner's word stands in the memory"
    answer = session.query(LineResolution).filter_by(receipt_id=hers, position=0).one()
    assert answer.confirmed_by == "user:Sara", "stamped as hers, whatever the request said"
    assert answer.disagrees_with == "p-0001", "kept for the owner to look at"

    # A name nobody had answered: hers teaches the memory, as a guess would.
    sara.set_line_resolution(hers, 1, "p-0003")
    assert line(owner.receipt(mine), 1) == ("p-0003", "app"), \
        "placed from her answer, so it can still be spot-checked"
    # The owner's answer replaces hers.
    owner.set_line_resolution(mine, 1, "p-0004")
    session.expire_all()
    remembered = session.query(Resolution).filter_by(raw_name="MU Quark").one()
    assert (remembered.product_id, remembered.product_ids, remembered.confirmed_by) == \
        ("p-0004", [], "shopper")

    assert sara.receipt(mine) is None
    with pytest.raises(NotFound):
        sara.set_line_resolution(mine, 0, "p-0002")


# --- the developer's inbox -------------------------------------------------------
# 2026-10-11: new kinds of upload reach development by themselves.

@pytestmark_db
def test_uploads_worth_a_look_reach_the_developer_once(two_people):
    from tests.test_upload import A_PDF

    client, _, sara = two_people
    client.post("/v1/receipts", headers=OWNER,
                files={"file": ("a.jpg", photo("red"), "image/jpeg")})       # ordinary
    pdf = client.post("/v1/receipts", headers=OWNER,
                      files={"file": ("order.pdf", A_PDF, "application/pdf")}).json()
    hers = client.post("/v1/receipts", headers=sara,
                       files={"file": ("b.jpg", photo("blue"), "image/jpeg")}).json()

    assert client.post("/v1/inbox", headers=sara).status_code == 403
    items = client.post("/v1/inbox", headers=OWNER).json()
    assert {(i["job_id"], i["kind"], i["user"]) for i in items} == {(pdf["job_id"], "pdf", None)}, \
        "hers is not shared: it never reaches the developer"
    assert client.get(f"/v1/inbox/{hers['job_id']}/file", headers=OWNER).status_code == 404

    # Owner, 2026-10-15: "we need consent". One tap on her receipt shares it.
    her_receipt = client.get(f"/v1/jobs/{hers['job_id']}", headers=sara).json()["receipt_id"]
    assert client.put(f"/v1/receipts/{her_receipt}/shared", headers=OWNER,
                      json={"shared": True}).status_code == 404, "only she can share hers"
    assert client.put(f"/v1/receipts/{her_receipt}/shared", headers=sara,
                      json={"shared": True}).status_code == 204
    assert [r["shared"] for r in client.get("/v1/receipts", headers=sara).json()] == [True]
    (her_item,) = client.post("/v1/inbox", headers=OWNER).json()
    assert (her_item["job_id"], her_item["user"]) == (hers["job_id"], "Sara")
    assert her_item["read"][0]["lines"][0]["raw_name"] == "MU Butter", \
        "what was read comes along, to set against the file"
    assert client.post("/v1/inbox", headers=OWNER).json() == [], "each arrives once"
    assert client.get(f"/v1/inbox/{hers['job_id']}/file", headers=OWNER).status_code == 200
    assert client.get("/v1/inbox/withdrawn", headers=OWNER).json() == []

    # Taken back: the file is closed, and the laptop is told to delete its copy.
    client.put(f"/v1/receipts/{her_receipt}/shared", headers=sara, json={"shared": False})
    assert client.get(f"/v1/inbox/{hers['job_id']}/file", headers=OWNER).status_code == 404
    assert client.get("/v1/inbox/withdrawn", headers=OWNER).json() == [hers["job_id"]]
    assert client.get("/v1/inbox/withdrawn", headers=sara).status_code == 403

    got = client.get(f"/v1/inbox/{pdf['job_id']}/file", headers=OWNER)
    assert got.content == A_PDF and got.headers["content-type"] == "application/pdf"
    assert client.get(f"/v1/inbox/{pdf['job_id']}/file", headers=sara).status_code == 403


@pytestmark_db
def test_an_upload_that_could_not_be_read_is_shared_by_its_job(two_people):
    client, _, sara = two_people
    hers = client.post("/v1/receipts", headers=sara,
                       files={"file": ("b.jpg", photo("blue"), "image/jpeg")}).json()
    assert client.put(f"/v1/jobs/{hers['job_id']}/shared", headers=OWNER,
                      json={"shared": True}).status_code == 404, "not the owner's to share"
    assert client.put("/v1/jobs/not-a-uuid/shared", headers=sara,
                      json={"shared": True}).status_code == 404
    assert client.put(f"/v1/jobs/{hers['job_id']}/shared", headers=sara,
                      json={"shared": True}).status_code == 204
    assert client.get(f"/v1/jobs/{hers['job_id']}", headers=sara).json()["shared"] is True


# --- deleting means deleting (owner, 2026-10-15) ---------------------------------

def stored(tmp_path, data):
    from grocery_app.api.images import sha256_of
    return (tmp_path / sha256_of(data)).exists()


@pytestmark_db
def test_removing_a_receipt_deletes_its_photo(two_people, tmp_path):
    client, _, _ = two_people
    red = photo("red")
    job = client.post("/v1/receipts", headers=OWNER,
                      files={"file": ("a.jpg", red, "image/jpeg")}).json()
    receipt_id = client.get(f"/v1/jobs/{job['job_id']}", headers=OWNER).json()["receipt_id"]
    assert stored(tmp_path, red)

    assert client.delete(f"/v1/receipts/{receipt_id}", headers=OWNER).status_code == 204
    assert not stored(tmp_path, red), "the photo goes with the receipt"

    again = client.post("/v1/receipts", headers=OWNER,
                        files={"file": ("a.jpg", red, "image/jpeg")}).json()
    assert client.get(f"/v1/jobs/{again['job_id']}", headers=OWNER).json()["receipt_id"], \
        "sent again, it is read again"
    assert stored(tmp_path, red)


@pytestmark_db
def test_a_person_deletes_their_account_and_everything_theirs(two_people, session, tmp_path):
    client, owner, sara = two_people
    mine, hers = photo("red"), photo("blue")
    client.post("/v1/receipts", headers=OWNER, files={"file": ("a.jpg", mine, "image/jpeg")})
    client.post("/v1/receipts", headers=sara, files={"file": ("b.jpg", hers, "image/jpeg")})
    sara_repo = owner.as_user({"id": owner.users()[0]["id"], "name": "Sara"})
    her_receipt = add_receipt(session, "IMG_9.jpeg", ["MU Skyr"], sara_repo.user_id)
    sara_repo.set_line_resolution(her_receipt, 0, "p-0004")  # teaches the shared memory

    assert client.delete("/v1/me", headers=OWNER).status_code == 403, "the owner's is the server"
    assert client.delete("/v1/me", headers=sara).status_code == 204

    assert client.get("/v1/receipts", headers=sara).status_code == 401, "her password is gone"
    assert [u["name"] for u in client.get("/v1/users", headers=OWNER).json()] == []
    assert not stored(tmp_path, hers) and stored(tmp_path, mine)
    session.expire_all()
    from grocery_app.db.models import Job, Receipt
    assert session.query(Receipt).filter(Receipt.user_id.is_not(None)).count() == 0
    assert session.query(Job).filter(Job.user_id.is_not(None)).count() == 0
    remembered = session.query(Resolution).filter_by(raw_name="MU Skyr").one()
    assert (remembered.product_id, remembered.confirmed_by) == ("p-0004", "user:removed"), \
        "what she taught about the name stays, without her name"
    assert len(client.get("/v1/receipts", headers=OWNER).json()) == 1, "the owner's untouched"


@pytestmark_db
def test_a_photo_no_receipt_came_from_is_deleted_after_30_days(two_people, session, tmp_path):
    from datetime import UTC, datetime, timedelta

    from grocery_app.api.app import forget_old_photos
    from grocery_app.api.images import DiskImageStore, sha256_of
    from grocery_app.db.models import Job

    client, owner, _ = two_people
    store = DiskImageStore(tmp_path)
    read = photo("red")
    client.post("/v1/receipts", headers=OWNER, files={"file": ("a.jpg", read, "image/jpeg")})
    for colour, days in (("blue", 31), ("green", 5)):  # never made a receipt
        data = photo(colour)
        store.put(sha256_of(data), data)
        session.add(Job(image_sha256=sha256_of(data), status="failed",
                        created_at=datetime.now(UTC) - timedelta(days=days)))
    session.query(Job).filter(Job.image_sha256 == sha256_of(read)).update(
        {"created_at": datetime.now(UTC) - timedelta(days=90)})
    session.commit()

    assert forget_old_photos(owner, store) == 1
    assert not stored(tmp_path, photo("blue")), "a month old and no receipt: deleted"
    assert stored(tmp_path, photo("green")), "kept for the developer to learn from"
    assert stored(tmp_path, read), "a receipt's photo stays as long as the receipt"


@pytestmark_db
def test_the_privacy_page_is_open_and_names_who_runs_the_server(two_people, monkeypatch):
    client, _, _ = two_people
    monkeypatch.setenv("GROCERY_OWNER_NAME", "Erika <Muster>")
    monkeypatch.setenv("GROCERY_OWNER_EMAIL", "erika@example.com")
    page = client.get("/privacy")  # no password: one reads it before signing in
    assert page.status_code == 200
    assert "Erika &lt;Muster&gt;" in page.text, "escaped, never markup"
    assert 'href="mailto:erika@example.com"' in page.text
    assert "{{" not in page.text

    monkeypatch.delenv("GROCERY_OWNER_NAME")
    monkeypatch.delenv("GROCERY_OWNER_EMAIL")
    assert "The person who runs this server" in client.get("/privacy").text
