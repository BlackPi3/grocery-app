"""The nearby-supermarkets lookup, checked against its rule, on made-up data.

Written from the rule alone, before reading the code (owner, 2026-10-25):

1. The server finds the supermarkets near the shops on each person's receipts
   through OpenStreetMap: Nominatim places an address, Overpass lists the
   supermarkets around a point. Only a shop's street and postcode as printed
   are sent, then that shop's point and a radius. Never a person's name,
   email, id, receipt contents or product names. Only
   nominatim.openstreetmap.org and overpass-api.de are asked.
2. A shop is looked up once for everyone, and `shop_places` /
   `nearby_stores` hold no user.
3. Only a person's own recent shops count: receipts of the last 90 days, a
   shop seen at least twice (or the only one). `GET /v1/stores/nearby` shows
   each person only the chains near their own shops; no sign-in is 401.
4. When no receipt names a shop any more (its only shopper deleted their
   account), the next pass deletes the shop and the stores around it.
5. A map that is down or answers garbage crashes nothing; the shop stays due
   and is asked again next pass; three failures in a row end the pass.
6. The privacy page names OpenStreetMap and what is sent, in German and English.

Every map here is a fake: nothing leaves the machine.
"""

from __future__ import annotations

import http.client
import json
import re
import socket
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from grocery_app import nearby
from grocery_app.api import nearby as nearby_api
from grocery_app.api.app import create_app
from grocery_app.api.images import DiskImageStore
from grocery_app.api.repository import PostgresRepository
from grocery_app.db.io import receipt_from_dict
from grocery_app.db.models import NearbyStore, ShopPlace
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL as URL
from tests.test_upload import FakeExtractor

needs_db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")

OWNER = {"Authorization": "Bearer owner-secret"}
USER_IDS: list[str] = []
TODAY = date.today()


def days_ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


# A shop: its name, the address as printed, its point, the chain the fake map
# lists near it, and that store's own street.
SHOPS = {
    "A": ("Musterladen", "Musterweg 17, 12345 Musterstadt", (50.1, 8.1),
          "Alphamarkt", "Alphastraße"),
    "B": ("Beispielmarkt", "Beispielallee 3, 54321 Beispielstadt", (51.2, 9.2),
          "Betamarkt", "Betaweg"),
    "C": ("Gemeinladen", "Teilerweg 5, 11111 Teilstadt", (52.3, 10.3),
          "Gammamarkt", "Gammagasse"),
    "D": ("Einmalladen", "Einmalweg 4, 22222 Einmalstadt", (53.4, 11.4),
          "Deltamarkt", "Deltaring"),
    "E": ("Altladen", "Altgasse 2, 33333 Altstadt", (49.5, 7.5),
          "Epsilonmarkt", "Epsilonpfad"),
    "F": ("Fernladen", "Fernweg 6, 44444 Fernstadt", (48.6, 6.6),
          "Fimarkt", "Fiweg"),
    "G": ("Zweitladen", "Zweitweg 7, 55555 Zweitstadt", (47.7, 12.7),
          "Zetamarkt", "Zetaallee"),
}
POSTCODE = {k: re.search(r"\b(\d{5})\b", s[1]).group(1) for k, s in SHOPS.items()}
STREET = {k: s[1].split(",")[0] for k, s in SHOPS.items()}
CITY = {k: s[1].rsplit(" ", 1)[1] for k, s in SHOPS.items()}

# What each person shops at, and when.
#   owner: A twice, C twice (shared with Sara), D once (not counted: not the
#          only one), E twice but 120 days ago (not counted).
#   Sara:  B twice, C twice, G twice.
#   Lea:   F once, her only shop (counted).
#   Old:   E twice, 120 days ago; nothing recent (sees nothing).
VISITS = {
    "owner": [("A", 5), ("A", 12), ("C", 6), ("C", 20), ("D", 8), ("E", 120), ("E", 130)],
    "sara": [("B", 3), ("B", 10), ("C", 4), ("C", 11), ("G", 7), ("G", 14)],
    "lea": [("F", 9)],
    "old": [("E", 121), ("E", 131)],
}
SEEN_BY = {"owner": {"A", "C"}, "sara": {"B", "C", "G"}, "lea": {"F"}, "old": set()}
COUNTED = set().union(*SEEN_BY.values())

RAW_LINES = ["GEHEIMKAESE NATUR", "ZAUBERSAFT ROT"]
# No secret may be a string a timestamp could hold: "6.0" was found inside
# "11:18:06.025" on 26 Oct. Seconds stop at 59, so "65.62" never is one.
PRICES = ["37.19", "28.43"]


def add_receipt(session, shop_key, user_id, day, n):
    store, location, *_ = SHOPS[shop_key]
    receipt = receipt_from_dict({
        "source_image": f"nearby-{shop_key}-{user_id}-{day}-{n}.jpeg",
        "transcribed_by": "llm",
        "store": store, "store_location": location, "date": day, "time": "10:00",
        "currency": "EUR", "printed_total": 65.62,
        "lines": [{"type": "product", "raw_name": raw, "qty": 1, "gross": float(price),
                   "discount": 0.0, "net": float(price), "tax_class": "A"}
                  for raw, price in zip(RAW_LINES, PRICES, strict=True)]})
    receipt.user_id = user_id
    session.add(receipt)


@pytest.fixture
def people(engine, session):
    repository = PostgresRepository(make_session_factory(engine))
    sara = repository.create_user("Sara Probe", "sara.probe@example.com")
    lea = repository.create_user("Lea Probe", "lea.probe@example.com")
    old = repository.create_user("Otto Probe", "otto.probe@example.com")
    ids = {"owner": None, "sara": sara["id"], "lea": lea["id"], "old": old["id"]}
    for who, visits in VISITS.items():
        for n, (shop, ago) in enumerate(visits):
            add_receipt(session, shop, ids[who], days_ago(ago), n)
    session.commit()
    personal = ["Sara", "Lea", "Otto", "Probe", "example.com", "owner-secret",
                sara["password"], lea["password"], old["password"],
                *RAW_LINES, "GEHEIM", "ZAUBER", *PRICES, "65.62"]
    # User ids are small numbers, found inside any timestamp or coordinate:
    # they are checked as whole values (`no_user_id_in`), not as substrings.
    USER_IDS[:] = [str(i) for i in ids.values() if i is not None]
    auth = {"owner": OWNER,
            **{w: {"Authorization": f"Bearer {u['password']}"}
               for w, u in (("sara", sara), ("lea", lea), ("old", old))}}
    return repository, auth, personal


# --- a fake OpenStreetMap -------------------------------------------------------

class Stop(BaseException):
    """Ends a test's nearby thread: not an Exception, so not caught as one."""


def _locate_ok(url, shop_key):
    if shop_key is None:
        return b"[]"
    lat, lon = SHOPS[shop_key][2]
    return json.dumps([{"lat": f"{lat:.7f}", "lon": f"{lon:.7f}",
                        "display_name": "somewhere"}]).encode()


def _around_ok(url, shop_key):
    if shop_key is None:
        return json.dumps({"elements": []}).encode()
    _, _, (lat, lon), chain, street = SHOPS[shop_key]
    return json.dumps({"elements": [{
        "type": "node", "id": 9000 + ord(shop_key), "lat": lat + 0.002, "lon": lon + 0.002,
        "tags": {"shop": "supermarket", "brand": chain, "name": f"{chain} Filiale",
                 "addr:street": street, "addr:housenumber": "1"}}]}).encode()


class FakeMap:
    """Records every (url, headers). `locate(url, shop, n)` / `around(url, shop, n)`
    answer the n-th call of their kind; by default both answer well."""

    def __init__(self, locate=None, around=None):
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.locate = locate or (lambda url, shop, n: _locate_ok(url, shop))
        self.around = around or (lambda url, shop, n: _around_ok(url, shop))
        self.stop = False

    def __call__(self, url, headers):
        if self.stop:
            raise Stop()
        self.calls.append((url, dict(headers)))
        host = urllib.parse.urlsplit(url).netloc
        text = urllib.parse.unquote_plus(url)
        if host == "nominatim.openstreetmap.org":
            shop = next((k for k, p in POSTCODE.items() if p in text), None)
            return self.locate(url, shop, len(self.locates()))
        if host == "overpass-api.de":
            numbers = [float(x) for x in re.findall(r"-?\d+\.\d+", text)]
            shop = next((k for k, s in SHOPS.items()
                         if any(abs(x - s[2][0]) < 1e-3 for x in numbers)
                         and any(abs(x - s[2][1]) < 1e-3 for x in numbers)), None)
            return self.around(url, shop, len(self.arounds()))
        raise OSError(f"unknown host {host}")

    def locates(self):
        return [(u, h) for u, h in self.calls
                if urllib.parse.urlsplit(u).netloc == "nominatim.openstreetmap.org"]

    def arounds(self):
        return [(u, h) for u, h in self.calls
                if urllib.parse.urlsplit(u).netloc == "overpass-api.de"]

    def located(self):
        """The shops asked of Nominatim, one entry per ask."""
        out = []
        for url, _ in self.locates():
            text = urllib.parse.unquote_plus(url)
            out.append(next((k for k, p in POSTCODE.items() if p in text), None))
        return out


def run(repository, fake):
    return nearby_api.look_up_due(repository, nearby.OpenStreetMap(fake), pause=0)


def client_for(repository, tmp_path):
    return TestClient(create_app(repository, DiskImageStore(tmp_path), FakeExtractor(),
                                 token="owner-secret"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any attempt to open a connection is recorded and refused."""
    tried: list[object] = []

    def refuse(*args, **kwargs):
        tried.append(args)
        raise OSError("no network in tests")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    return tried


# --- 1: what is sent, and to whom ----------------------------------------------

@needs_db
def test_only_the_two_map_hosts_are_asked_and_nothing_about_a_person(people):
    repository, _, personal = people
    fake = FakeMap()
    run(repository, fake)
    assert fake.locates() and fake.arounds(), "something was looked up"
    for url, headers in fake.calls:
        host = urllib.parse.urlsplit(url).netloc
        assert host in ("nominatim.openstreetmap.org", "overpass-api.de"), url
        assert urllib.parse.urlsplit(url).scheme == "https", url
        sent = urllib.parse.unquote_plus(url) + json.dumps(headers, ensure_ascii=False)
        for secret in personal:
            assert secret not in sent, f"{secret!r} sent in {url}"
        for key, value in urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query):
            assert "user" not in key.lower(), (key, value)
    assert len({json.dumps(h, sort_keys=True) for _, h in fake.calls}) == 1, \
        "every request carries the same headers: none can carry a person"


@needs_db
def test_nominatim_gets_the_street_and_postcode_and_nothing_else(people):
    """Not the shop's name, not its city, not a date: street and postcode."""
    repository, _, _ = people
    fake = FakeMap()
    run(repository, fake)
    rest = set()
    for url, _ in fake.locates():
        text = urllib.parse.unquote_plus(url)
        shop = next(k for k, p in POSTCODE.items() if p in text)
        assert STREET[shop] in text or STREET[shop].replace(" ", "+") in url, url
        for k, (store, *_rest) in SHOPS.items():
            assert store not in text, f"the shop's name went out: {url}"
            assert CITY[k] not in text, f"a city went out: {url}"
        params = urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query)
        rest.add(json.dumps(sorted(
            (key, value.replace(STREET[shop], "").replace(POSTCODE[shop], ""))
            for key, value in params)))
    assert len(rest) == 1, f"beyond street and postcode, every ask is the same: {rest}"


@needs_db
def test_overpass_gets_a_point_and_a_radius_and_no_address(people):
    repository, _, _ = people
    fake = FakeMap()
    run(repository, fake)
    rest = set()
    for url, _ in fake.arounds():
        text = urllib.parse.unquote_plus(url)
        for k in SHOPS:
            assert STREET[k] not in text and POSTCODE[k] not in text, url
            assert SHOPS[k][0] not in text and CITY[k] not in text, url
        rest.add(re.sub(r"-?\d+(?:\.\d+)?", "#", text))
    assert len(rest) == 1, f"beyond numbers, every ask is the same: {rest}"


# --- 2: one lookup for everyone, kept without a person ---------------------------

@needs_db
def test_a_shared_shop_is_looked_up_once(people):
    repository, _, _ = people
    fake = FakeMap()
    run(repository, fake)
    located = fake.located()
    assert located.count("C") == 1, located
    assert len(located) == len(set(located)), f"no shop is placed twice: {located}"
    assert len(fake.arounds()) == len(set(located)), "one area ask per placed shop"


@needs_db
def test_a_second_pass_asks_nothing_again(people):
    repository, _, _ = people
    run(repository, FakeMap())
    again = FakeMap()
    run(repository, again)
    assert not again.calls, again.calls


@needs_db
def test_the_kept_tables_hold_no_person(people, engine, session):
    repository, _, personal = people
    run(repository, FakeMap())
    for table in ("shop_places", "nearby_stores"):
        columns = {c["name"] for c in inspect(engine).get_columns(table)}
        assert not any("user" in c or "receipt" in c or "email" in c for c in columns), \
            (table, columns)
        assert all(fk["referred_table"] not in ("users", "receipts")
                   for fk in inspect(engine).get_foreign_keys(table)), table
    session.expire_all()
    places = session.query(ShopPlace).all()
    stores = session.query(NearbyStore).all()
    assert places and stores
    assert len({p.postcode for p in places}) == len(places), "one row per shop"
    for row in [*places, *stores]:
        text = json.dumps({c.key: str(getattr(row, c.key)) for c in row.__table__.columns},
                          ensure_ascii=False)
        for secret in personal:
            assert secret not in text, (secret, text)
        assert not any(getattr(row, c.key) == int(i) for c in row.__table__.columns
                       if c.key not in ("id", "place_id") for i in USER_IDS
                       if isinstance(getattr(row, c.key), int)), text
        for store, *_ in SHOPS.values():
            assert store not in text, f"the shop name is receipt text: {text}"


# --- 3: each person sees only their own shops -------------------------------------

def chains_in(text):
    return {s[3] for s in SHOPS.values() if s[3] in text}


@needs_db
@pytest.mark.parametrize("who", sorted(SEEN_BY))
def test_each_person_sees_only_the_chains_near_their_own_recent_shops(people, tmp_path,
                                                                     who):
    repository, auth, _ = people
    run(repository, FakeMap())
    answer = client_for(repository, tmp_path).get("/v1/stores/nearby", headers=auth[who])
    assert answer.status_code == 200, answer.text
    assert chains_in(answer.text) == {SHOPS[k][3] for k in SEEN_BY[who]}, answer.text
    for k in set(SHOPS) - SEEN_BY[who]:
        for leak in (STREET[k], POSTCODE[k], CITY[k], SHOPS[k][0], SHOPS[k][4]):
            assert leak not in answer.text, f"{leak!r} of shop {k} shown to {who}"


@needs_db
def test_the_lookup_covers_every_counted_shop(people):
    """The answer test above would pass if a shop were never looked up and
    every person saw nothing; this one would not."""
    repository, _, _ = people
    fake = FakeMap()
    run(repository, fake)
    assert COUNTED <= set(fake.located()), fake.located()


@needs_db
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer guessed"},
                                     {"Authorization": "owner-secret"}])
def test_no_sign_in_is_401(people, tmp_path, headers):
    repository, _, _ = people
    run(repository, FakeMap())
    answer = client_for(repository, tmp_path).get("/v1/stores/nearby", headers=headers)
    assert answer.status_code == 401
    assert not chains_in(answer.text)


# --- 4: a shop nobody names any more is forgotten ---------------------------------

@needs_db
def test_a_deleted_account_takes_its_only_shops_with_it(people, tmp_path, session):
    repository, auth, _ = people
    run(repository, FakeMap())
    session.expire_all()
    before = {p.postcode for p in session.query(ShopPlace)}
    assert {POSTCODE["B"], POSTCODE["G"], POSTCODE["C"]} <= before
    client = client_for(repository, tmp_path)
    assert client.delete("/v1/me", headers=auth["sara"]).status_code == 204
    fake = FakeMap()
    run(repository, fake)
    session.expire_all()
    after = {p.postcode for p in session.query(ShopPlace)}
    assert POSTCODE["B"] not in after and POSTCODE["G"] not in after, after
    assert POSTCODE["C"] in after and POSTCODE["A"] in after, "the owner's shops stay"
    chains = {s.chain for s in session.query(NearbyStore)}
    assert "Betamarkt" not in chains and "Zetamarkt" not in chains, chains
    assert "Gammamarkt" in chains and "Alphamarkt" in chains, chains
    assert not {"B", "G"} & set(fake.located()), "and they are not looked up again"
    mine = client.get("/v1/stores/nearby", headers=OWNER)
    assert chains_in(mine.text) == {"Alphamarkt", "Gammamarkt"}


# --- 5: a map that is down or answers garbage --------------------------------------

def raises(error):
    def answer(url, shop, n):
        raise error
    return answer


def gives(body):
    return lambda url, shop, n: body


HOSTILE = {
    "refused": raises(OSError("connection refused")),
    "timeout": raises(TimeoutError("slow")),
    "value error": raises(ValueError("odd")),
    "garbage": gives(b"\x00not json{{"),
    "html": gives(b"<html>Too Many Requests</html>"),
    "null": gives(b"null"),
    "a number": gives(b"42"),
    "an object": gives(b'{"error": "x"}'),
    "list of numbers": gives(b"[1, 2]"),
    "list of empties": gives(b"[{}]"),
    "bad lat": gives(b'[{"lat": "north", "lon": "8.1"}]'),
    "null lat": gives(b'[{"lat": null, "lon": null}]'),
    # The connection dropped mid-answer: `http.client` says so with an
    # HTTPException, which is not an OSError.
    "cut short": raises(http.client.IncompleteRead(b'[{"lat": "5')),
    # Valid JSON too deep to decode: RecursionError, not a ValueError.
    "too deep": gives(b"[" * 200_000 + b"]" * 200_000),
}

AROUND_HOSTILE = {
    **{k: v for k, v in HOSTILE.items() if k in ("refused", "timeout", "garbage", "html",
                                                 "null", "a number", "list of numbers",
                                                 "cut short", "too deep")},
    # What Overpass answers, with a 200, when the question runs out of time:
    # no elements, and a remark saying why. It is not "no supermarkets here".
    "timed out": gives(json.dumps({
        "version": 0.6, "elements": [],
        "remark": 'runtime error: Query timed out in "query" at line 1 after 91 seconds.',
    }).encode()),
    "elements not a list": gives(b'{"elements": "x"}'),
    "elements of numbers": gives(b'{"elements": [1, 2]}'),
}


def assert_all_found_by_a_good_map(repository, tmp_path, auth):
    run(repository, FakeMap())
    client = client_for(repository, tmp_path)
    for who, shops in SEEN_BY.items():
        answer = client.get("/v1/stores/nearby", headers=auth[who])
        assert answer.status_code == 200
        assert chains_in(answer.text) == {SHOPS[k][3] for k in shops}, (who, answer.text)


@needs_db
@pytest.mark.parametrize("kind", sorted(HOSTILE))
def test_a_bad_nominatim_answer_crashes_nothing_and_the_shop_stays_due(people, tmp_path,
                                                                      kind):
    repository, auth, _ = people
    run(repository, FakeMap(locate=HOSTILE[kind]))  # must not raise
    answer = client_for(repository, tmp_path).get("/v1/stores/nearby", headers=OWNER)
    assert answer.status_code == 200, answer.text
    assert_all_found_by_a_good_map(repository, tmp_path, auth)


@needs_db
@pytest.mark.parametrize("kind", sorted(AROUND_HOSTILE))
def test_a_bad_overpass_answer_crashes_nothing_and_the_shop_stays_due(people, tmp_path,
                                                                     kind):
    repository, auth, _ = people
    run(repository, FakeMap(around=AROUND_HOSTILE[kind]))  # must not raise
    answer = client_for(repository, tmp_path).get("/v1/stores/nearby", headers=OWNER)
    assert answer.status_code == 200, answer.text
    again = FakeMap()
    run(repository, again)
    assert again.arounds(), "the area is asked again next pass"
    assert_all_found_by_a_good_map(repository, tmp_path, auth)


@needs_db
def test_three_failures_in_a_row_end_the_pass(people):
    repository, _, _ = people
    assert len(COUNTED) > 3, "enough shops due to tell"
    fake = FakeMap(locate=HOSTILE["refused"])
    run(repository, fake)
    assert len(fake.locates()) == 3, fake.located()


@needs_db
def test_three_failures_in_a_row_end_the_pass_when_overpass_fails(people):
    repository, _, _ = people
    fake = FakeMap(around=HOSTILE["refused"])
    run(repository, fake)
    assert len(fake.arounds()) == 3, fake.calls


@needs_db
def test_failures_not_in_a_row_do_not_end_the_pass(people):
    """Two failures, a success, two failures: every due shop is still tried."""
    repository, _, _ = people

    def locate(url, shop, n):  # n counts this call
        if n in (3,):
            return _locate_ok(url, shop)
        raise OSError("down")

    fake = FakeMap(locate=locate)
    run(repository, fake)
    assert len(fake.locates()) == len(COUNTED), fake.located()


@needs_db
def test_the_nearby_thread_survives_a_map_that_keeps_failing(people, monkeypatch):
    repository, _, _ = people
    monkeypatch.setattr(nearby_api, "PAUSE_BETWEEN_ASKS_S", 0)
    fake = FakeMap(locate=HOSTILE["garbage"])
    thread = threading.Thread(target=nearby_api.keep_looking,
                              args=(repository, nearby.OpenStreetMap(fake)),
                              kwargs={"every": 0.05}, daemon=True)
    try:
        thread.start()
        deadline = time.monotonic() + 10
        while len(fake.locates()) < 6 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert thread.is_alive(), "the thread died on a failed pass"
        assert len(fake.locates()) >= 6, "and kept trying on later passes"
    finally:
        fake.stop = True
        thread.join(timeout=5)


@needs_db
def test_a_server_without_a_map_never_reaches_the_network(people, tmp_path, no_network):
    repository, _, _ = people
    with client_for(repository, tmp_path) as client:
        assert client.get("/v1/stores/nearby", headers=OWNER).status_code == 200
        time.sleep(0.3)
    assert not no_network


# --- 6: the privacy page --------------------------------------------------------

@needs_db
def test_the_privacy_page_names_openstreetmap_and_what_is_sent_in_both_languages(
        people, tmp_path):
    repository, _, _ = people
    page = client_for(repository, tmp_path).get("/privacy").text
    assert page.count("OpenStreetMap") >= 2, "named in German and in English"
    lower = page.lower()
    assert "straße" in lower and "postleitzahl" in lower, "German: street and postcode"
    assert "street" in lower and "postcode" in lower, "English: street and postcode"
