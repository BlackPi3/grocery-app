"""The supermarkets near the shops a person uses (`grocery_app.nearby`,
`grocery_app.api.nearby`). Made-up shops and points; no test asks the map."""

from __future__ import annotations

import json
import urllib.parse
from datetime import UTC, date, datetime, timedelta

import pytest

from grocery_app import nearby
from tests.conftest import DATABASE_URL as URL

# --- where a shop is ---------------------------------------------------------------


@pytest.mark.parametrize(("printed", "street", "postcode"), [
    ("Markthalle Musterstadt, Musterstr. 12 - 12345 Mstd.-Nord", "Musterstr. 12", "12345"),
    ("Musterladen GmbH & Co.KG, Markthalle, Musterstr. 12 - 12345 Mstd.", "Musterstr. 12",
     "12345"),
    ("Beispielweg 1 A, 54321 Beispieldorf", "Beispielweg 1 A", "54321"),
    ("Musterladen - Hauptstraße  86-90, 12345 Musterstadt", "Hauptstraße 86-90", "12345"),
    ("Rastplatz, Am Musterkreuz 3b, 12345 Musterstadt", "Am Musterkreuz 3b", "12345"),
    ("Bundesautobahn A9 Ost, 12345 Rastdorf", None, "12345"),
])
def test_a_printed_address_is_its_street_and_postcode(printed, street, postcode):
    assert nearby.address_of(printed) == {"street": street, "postcode": postcode}


def test_no_postcode_is_no_address():
    assert nearby.address_of("Musterstadt-Nord") is None
    assert nearby.address_of("Tel. 06812 345678") is None
    assert nearby.address_of(None) is None


def test_one_shop_however_its_receipts_space_or_case_it():
    a = nearby.address_of("Musterstr.  12, 12345 Musterstadt")
    b = nearby.address_of("Markthalle, MUSTERSTR. 12 - 12345 Mstd.")
    assert nearby.place_key(a) == nearby.place_key(b) == "12345 musterstr. 12"


def test_the_shops_someone_uses_are_where_they_go_again():
    here, there, once = ("Musterstr. 12, 12345 Musterstadt", "Beispielweg 1, 54321 Beispieldorf",
                         "Einmalweg 9, 99999 Fernstadt")
    assert nearby.shopping_places([here, there, here, there, there, once, None]) == [
        {"street": "Beispielweg 1", "postcode": "54321"},
        {"street": "Musterstr. 12", "postcode": "12345"}], "most visits first, no one-off"
    assert nearby.shopping_places([once]) == [
        {"street": "Einmalweg 9", "postcode": "99999"}], "the only shop still counts"
    assert nearby.shopping_places([here] * 2 + [there] * 2 + [once] * 2, most=2) == [
        {"street": "Musterstr. 12", "postcode": "12345"},
        {"street": "Beispielweg 1", "postcode": "54321"}]


# --- what is around it ----------------------------------------------------------------

def test_distance_is_as_the_crow_flies():
    assert nearby.distance_m(50.0, 8.0, 50.0, 8.0) == 0
    assert 111_000 < nearby.distance_m(50.0, 8.0, 51.0, 8.0) < 111_400, "a degree of latitude"


def element(id_, lat, lon, kind="node", **tags):
    place = {"lat": lat, "lon": lon} if kind == "node" else {"center": {"lat": lat, "lon": lon}}
    return {"type": kind, "id": id_, **place, "tags": tags}


def test_a_supermarket_is_read_with_its_chain_and_distance():
    store = nearby.read_store(element(7, 50.009, 8.0, kind="way", brand="Musterdiscount",
                                      name="Musterdiscount", **{"addr:street": "Musterstr.",
                                      "addr:housenumber": "5", "addr:postcode": "12345",
                                      "addr:city": "Musterstadt"}), 50.0, 8.0)
    assert store == {"osm_id": "way/7", "chain": "Musterdiscount", "name": "Musterdiscount",
                     "address": "Musterstr. 5, 12345 Musterstadt", "lat": 50.009, "lon": 8.0,
                     "distance_m": 1001}


def test_an_independent_shop_has_no_chain_and_a_nameless_one_is_no_use():
    assert nearby.read_store(element(1, 50.0, 8.0, name="Frischmarkt Muster"), 50.0, 8.0)[
        "chain"] is None
    assert nearby.read_store(element(2, 50.0, 8.0), 50.0, 8.0) is None
    assert nearby.read_store({"type": "node", "id": 3, "tags": {"name": "X"}}, 50.0, 8.0) is None


class FakeFetch:
    def __init__(self, *answers):
        self.answers, self.asked = list(answers), []

    def __call__(self, url, headers):
        self.asked.append(url)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, bytes) else json.dumps(answer).encode()


def test_a_shop_is_placed_by_its_street_and_postcode_only():
    fetch = FakeFetch([{"lat": "50.1", "lon": "8.2", "display_name": "Musterstr. 12"}])
    point = nearby.OpenStreetMap(fetch).locate({"street": "Musterstr. 12", "postcode": "12345"})
    assert point == (50.1, 8.2)
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(fetch.asked[0]).query)
    assert {k: v[0] for k, v in query.items()} == {
        "street": "Musterstr. 12", "postalcode": "12345", "countrycodes": "de",
        "format": "jsonv2", "limit": "1"}, "nothing else is sent"


def test_a_shop_without_a_street_is_placed_by_its_postcode():
    fetch = FakeFetch([{"lat": "50.1", "lon": "8.2"}])
    nearby.OpenStreetMap(fetch).locate({"street": None, "postcode": "12345"})
    assert "street" not in urllib.parse.parse_qs(urllib.parse.urlsplit(fetch.asked[0]).query)


def test_an_unknown_place_is_none_and_a_broken_answer_is_unavailable():
    maps = nearby.OpenStreetMap(FakeFetch([], b"<html>", OSError("down"), {"no": "list"}))
    address = {"street": "Musterstr. 12", "postcode": "12345"}
    assert maps.locate(address) is None
    for _ in range(3):
        with pytest.raises(nearby.MapUnavailable):
            maps.locate(address)


def test_the_supermarkets_around_a_point_are_nearest_first():
    fetch = FakeFetch({"elements": [element(1, 50.02, 8.0, brand="Mustermarkt", name="M"),
                                    element(2, 50.005, 8.0, name="Frischmarkt Muster"),
                                    element(3, 50.0, 8.0)]})
    stores = nearby.OpenStreetMap(fetch).around(50.0, 8.0)
    assert [s["osm_id"] for s in stores] == ["node/2", "node/1"], "a nameless one left out"
    assert "around:3000,50.0,8.0" in urllib.parse.unquote(fetch.asked[0])
    with pytest.raises(nearby.MapUnavailable):
        nearby.OpenStreetMap(FakeFetch({"remark": "timeout"})).around(50.0, 8.0)


def test_each_chain_is_its_branch_nearest_any_shop():
    stores = [
        {"osm_id": "node/1", "chain": "Musterdiscount", "name": "Musterdiscount",
         "distance_m": 2100},
        {"osm_id": "node/2", "chain": "MUSTERDISCOUNT", "name": "Musterdiscount",
         "distance_m": 900},
        {"osm_id": "node/3", "chain": None, "name": "Frischmarkt A", "distance_m": 400},
        {"osm_id": "node/4", "chain": None, "name": "Frischmarkt B", "distance_m": 1500},
    ]
    assert [s["osm_id"] for s in nearby.chains_near(stores)] == ["node/3", "node/2", "node/4"]


# --- kept by the server ------------------------------------------------------------------

db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")
TODAY = date(2026, 10, 23)
NOW = datetime(2026, 10, 23, 9, tzinfo=UTC)
HERE = "Musterladen, Musterstr. 12 - 12345 Musterstadt"
THERE = "Beispielweg 1, 54321 Beispieldorf"


class FakeMap:
    """Every address is at (50, 8) plus its postcode's last digit; around
    each, one Musterdiscount 500 m off and an independent shop."""

    def __init__(self, unknown=(), down=False):
        self.unknown, self.down = set(unknown), down
        self.located, self.looked = [], []

    def locate(self, address):
        if self.down:
            raise nearby.MapUnavailable("down")
        self.located.append(address["postcode"])
        if address["postcode"] in self.unknown:
            return None
        return 50.0 + int(address["postcode"][-1]), 8.0

    def around(self, lat, lon):
        if self.down:
            raise nearby.MapUnavailable("down")
        self.looked.append(lat)
        return [{"osm_id": f"node/{int(lat)}1", "chain": "Musterdiscount",
                 "name": "Musterdiscount", "address": None, "lat": lat, "lon": lon,
                 "distance_m": 500 + int(lat)},
                {"osm_id": f"node/{int(lat)}2", "chain": None, "name": f"Frischmarkt {int(lat)}",
                 "address": None, "lat": lat, "lon": lon, "distance_m": 100}]


def _receipt(image, day, location, user_id=None):
    from grocery_app.db.io import receipt_from_dict

    receipt = receipt_from_dict({
        "source_image": image, "store": "Musterladen", "store_location": location,
        "date": (TODAY - timedelta(days=day)).isoformat(), "currency": "EUR",
        "lines": [{"type": "product", "raw_name": "MU Milch 1,5%", "qty": 1, "gross": 1.0,
                   "discount": 0.0, "net": 1.0, "tax_class": "A"}]})
    receipt.user_id = user_id
    return receipt


@pytest.fixture
def shoppers(engine, session):
    """The owner shops at HERE; Sara at HERE and THERE; both long ago at an
    old shop."""
    from grocery_app.api.repository import PostgresRepository
    from grocery_app.db.session import make_session_factory

    repository = PostgresRepository(make_session_factory(engine))
    sara = repository.create_user("Sara")
    for day in (3, 10):
        session.add(_receipt(f"o{day}.jpeg", day, HERE))
        session.add(_receipt(f"s{day}.jpeg", day, THERE, sara["id"]))
        session.add(_receipt(f"t{day}.jpeg", day + 1, HERE, sara["id"]))
        session.add(_receipt(f"old{day}.jpeg", day + 200, "Alt 1, 99999 Altstadt"))
    session.commit()
    return repository, sara


@db
def test_each_shop_is_looked_up_once_whoever_shops_there(shoppers, session):
    from grocery_app.api.nearby import look_up_due
    from grocery_app.db.models import NearbyStore, ShopPlace

    repository, _ = shoppers
    maps = FakeMap()
    assert look_up_due(repository, maps, now=NOW, pause=0) == {
        "due": 2, "asked": 4, "failed": 0, "stores": 4}
    assert sorted(maps.located) == ["12345", "54321"], "one look at HERE for both, no old shop"
    assert look_up_due(repository, maps, now=NOW + timedelta(days=1), pause=0)["due"] == 0
    session.expire_all()
    assert {p.key for p in session.query(ShopPlace)} == {"12345 musterstr. 12",
                                                         "54321 beispielweg 1"}
    assert session.query(NearbyStore).count() == 4


@db
def test_the_surroundings_are_looked_up_again_after_a_month_not_the_address(shoppers, session):
    from grocery_app.api.nearby import look_up_due

    repository, _ = shoppers
    maps = FakeMap()
    look_up_due(repository, maps, now=NOW, pause=0)
    later = look_up_due(repository, maps, now=NOW + timedelta(days=31), pause=0)
    assert later == {"due": 2, "asked": 2, "failed": 0, "stores": 4}
    assert len(maps.located) == 2 and len(maps.looked) == 4


@db
def test_a_shop_the_map_does_not_know_is_asked_again_after_a_month(shoppers, session):
    from grocery_app.api.nearby import look_up_due

    repository, _ = shoppers
    maps = FakeMap(unknown={"54321"})
    assert look_up_due(repository, maps, now=NOW, pause=0)["stores"] == 2
    assert look_up_due(repository, maps, now=NOW + timedelta(days=2), pause=0)["due"] == 0
    look_up_due(repository, maps, now=NOW + timedelta(days=31), pause=0)
    assert maps.located.count("54321") == 2


@db
def test_a_map_that_is_down_leaves_everything_due(shoppers, session):
    from grocery_app.api.nearby import look_up_due
    from grocery_app.db.models import ShopPlace

    repository, _ = shoppers
    assert look_up_due(repository, FakeMap(down=True), now=NOW, pause=0) == {
        "due": 2, "asked": 0, "failed": 2, "stores": 0}
    session.expire_all()
    assert session.query(ShopPlace).count() == 0
    assert look_up_due(repository, FakeMap(), now=NOW, pause=0)["due"] == 2


@db
def test_a_shop_nobody_uses_any_more_is_forgotten(shoppers, session):
    """Once Sara's account is gone, nothing kept points at THERE."""
    from grocery_app.api.nearby import look_up_due
    from grocery_app.db.models import NearbyStore, ShopPlace

    repository, sara = shoppers
    look_up_due(repository, FakeMap(), now=NOW, pause=0)
    repository.as_user({"id": sara["id"], "name": "Sara"}).remove_account()
    look_up_due(repository, FakeMap(), now=NOW + timedelta(hours=1), pause=0)
    session.expire_all()
    assert [p.key for p in session.query(ShopPlace)] == ["12345 musterstr. 12"]
    assert session.query(NearbyStore).count() == 2, "its stores went with it"


@db
def test_a_person_gets_the_chains_near_their_own_shops(shoppers, session):
    from fastapi.testclient import TestClient

    from grocery_app.api.app import create_app
    from grocery_app.api.nearby import look_up_due

    repository, sara = shoppers
    client = TestClient(create_app(repository, token="owner-secret"))
    before = client.get("/v1/stores/nearby", headers={"Authorization": "Bearer owner-secret"})
    assert before.json() == {"shops": [{"street": "Musterstr. 12", "postcode": "12345",
                                        "found": None}], "stores": []}, "not looked up yet"

    look_up_due(repository, FakeMap(), now=NOW, pause=0)
    mine = client.get("/v1/stores/nearby", headers={"Authorization": "Bearer owner-secret"})
    assert mine.json()["stores"] == [
        {"osm_id": "node/552", "chain": None, "name": "Frischmarkt 55", "address": None,
         "distance_m": 100, "near": "Musterstr. 12"},
        {"osm_id": "node/551", "chain": "Musterdiscount", "name": "Musterdiscount",
         "address": None, "distance_m": 555, "near": "Musterstr. 12"}], "only near HERE"
    hers = client.get("/v1/stores/nearby", headers={"Authorization": f"Bearer {sara['password']}"})
    assert [s["osm_id"] for s in hers.json()["stores"]] == ["node/512", "node/552", "node/511"], \
        "one Musterdiscount, the nearer of her two shops'"


def test_the_privacy_page_names_openstreetmap_and_what_is_sent_in_both_languages():
    from importlib.resources import files

    page = files("grocery_app.api").joinpath("privacy.html").read_text()
    assert page.count("OpenStreetMap") >= 2, "named in German and in English"
    assert "Straße und Postleitzahl" in page and "street and postcode" in page
