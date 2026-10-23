"""The shops' weekly offers: reading one, what to search, and each chain's day.

The owner, 2026-10-23: show a user the offers for what they buy, refreshed
when each chain puts out its new ones. Everything here is made up: the
chains, the postcodes and the offers, in the shape the source answers.
No test reaches the network: the source is given a fake `fetch`.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from grocery_app import offers
from tests.conftest import DATABASE_URL as URL


def raw_offer(id_=1, chain="Musterdiscount", price=1.98, **extra):
    """A search result as the source sends it, cut to the fields read."""
    return {"id": id_, "advertisers": [{"name": chain}], "brand": {"name": "Muster"},
            "product": {"name": "Magerquark"}, "description": "  500-g-Becher ",
            "categories": [{"name": "Quark"}], "price": price, "oldPrice": 2.49,
            "volume": 0.5, "quantity": 1.0, "referencePrice": 3.96,
            "unit": {"shortName": "kg", "name": "Kilogramm"},
            # Monday 26 Oct to Saturday 31 Oct in Germany, as UTC.
            "validityDates": [{"from": "2026-10-25T23:00:00Z", "to": "2026-10-31T22:59:00Z"}],
            "requiresLoyalityMembership": True, **extra}


def test_an_offer_is_read_into_our_record():
    assert offers.read_offer(raw_offer()) == {
        "source": "marktguru", "id": "1", "chain": "Musterdiscount", "brand": "Muster",
        "product": "Magerquark", "description": "500-g-Becher", "category": "Quark",
        "price": 1.98, "price_before": 2.49,
        "pack": {"amount": 0.5, "unit": "kg", "count": 1.0},
        "per_unit": {"amount": 3.96, "per": "kg"},
        "valid_from": "2026-10-26", "valid_to": "2026-10-31", "loyalty_card": True,
    }


def test_an_offer_with_no_brand_has_none_not_the_sources_mark():
    loose = raw_offer(brand={"name": "thisisnobrand123"}, product={"name": "Möhren"})
    assert offers.read_offer(loose)["brand"] is None
    assert offers.brand_of("Gut & Günstig") == "Gut & Günstig"


def test_the_days_are_germanys_not_utcs():
    """Midnight in Germany is 22:00 or 23:00 UTC: the UTC date is the day before."""
    summer = raw_offer(validityDates=[{"from": "2026-07-05T22:00:00Z",
                                       "to": "2026-07-11T21:59:00Z"}])
    assert (offers.read_offer(summer)["valid_from"],
            offers.read_offer(summer)["valid_to"]) == ("2026-07-06", "2026-07-11")


def test_an_offer_with_no_chain_price_or_dates_is_no_use():
    assert offers.read_offer(raw_offer(advertisers=[])) is None
    assert offers.read_offer(raw_offer(price=None)) is None
    assert offers.read_offer(raw_offer(validityDates=[])) is None


def test_no_unit_means_no_pack_and_no_unit_price():
    record = offers.read_offer(raw_offer(unit=None))
    assert record["pack"] is None and record["per_unit"] is None
    assert record["price"] == 1.98


def test_the_postcode_is_the_one_before_the_town():
    assert offers.postcode_of("Musterweg 12, 12345 Musterstadt") == "12345"
    assert offers.postcode_of("Hausnummer 54321, 12345 Musterstadt") == "12345"
    assert offers.postcode_of("Musterweg 12, Musterstadt") is None
    assert offers.postcode_of("Musterweg 1, 12345 Musterstadt, Tel. 0621 98765") == "12345"
    assert offers.postcode_of("D-12345 Musterstadt") == "12345"
    assert offers.postcode_of(None) is None


def test_where_someone_shops_is_where_they_go_again():
    many = ["A 1, 11111 X", "B 2, 22222 Y", "A 1, 11111 X", "B 2, 22222 Y",
            "A 1, 11111 X", "C 3, 33333 Z", None]
    assert offers.shopping_postcodes(many) == ["11111", "22222"], "a one-off visit is not"
    assert offers.shopping_postcodes(["C 3, 33333 Z"]) == ["33333"], "but one is all there is"
    assert offers.shopping_postcodes([None, "no postcode"]) == []
    assert offers.shopping_postcodes(many * 2 + ["D, 44444 W"] * 9, most=1) == ["44444"]


def test_a_product_is_searched_by_its_words_not_its_sizes():
    assert offers.search_word("Saatenbrötchen 3er (3x 1,000 Stück)") == "Saatenbrötchen"
    assert offers.search_word("Milch 1,5%") == "Milch"
    assert offers.search_word("Magerquark (low-fat quark)") == "Magerquark"
    assert offers.search_word("Rispentomaten") == "Rispentomaten"
    assert offers.search_word("Skyr 450 g") == "Skyr"
    assert offers.search_word("Mineralwasser 6 x 1,5 l") == "Mineralwasser"
    assert offers.search_word("Vollmilch 1L") == "Vollmilch"
    assert offers.search_word("Gouda jung 400g Scheiben") == "Gouda jung Scheiben"
    assert offers.search_word("500 g") is None


HOME = b'<script>{"config":{"apiHostAddress":"api.example","apiKey":"K1","clientKey":"C1"}}'


class FakeSite:
    """The site's page and its search, answering from a list of offers."""

    def __init__(self, results, page=HOME, fail_searches=0):
        self.results, self.page, self.fail_searches = results, page, fail_searches
        self.asked: list[tuple[str, dict]] = []

    def __call__(self, url, headers):
        self.asked.append((url, headers))
        if url == offers.HOME_URL:
            return self.page
        if self.fail_searches:
            self.fail_searches -= 1
            raise OSError("busy")
        query = dict(p.split("=") for p in url.split("?", 1)[1].split("&"))
        start, limit = int(query["offset"]), int(query["limit"])
        return json.dumps({"totalResults": len(self.results),
                           "results": self.results[start:start + limit]}).encode()


def test_a_search_sends_the_sites_keys_and_reads_every_page():
    site = FakeSite([raw_offer(i) for i in range(150)])
    found = offers.Marktguru(site).search("Magerquark", "12345")
    assert [o["id"] for o in found] == [str(i) for i in range(150)]
    searches = [(u, h) for u, h in site.asked if u != offers.HOME_URL]
    assert len(searches) == 2, "two pages of 100"
    assert all(h == {"x-apikey": "K1", "x-clientkey": "C1"} for _, h in searches)
    assert all("q=Magerquark" in u and "zipCode=12345" in u for u, _ in searches)
    assert [u for u, _ in site.asked].count(offers.HOME_URL) == 1, "keys read once"


def test_a_failed_search_says_so_and_reads_the_keys_again():
    site = FakeSite([raw_offer()], fail_searches=1)
    source = offers.Marktguru(site)
    with pytest.raises(offers.OffersUnavailable):
        source.search("Milch", "12345")
    assert len(source.search("Milch", "12345")) == 1
    assert [u for u, _ in site.asked].count(offers.HOME_URL) == 2


def test_a_page_without_its_keys_is_unavailable_not_empty():
    with pytest.raises(offers.OffersUnavailable, match="keys"):
        offers.Marktguru(FakeSite([], page=b"<html>new site</html>")).search("Milch", "12345")


def berlin(day, hour=9):
    return datetime(2026, 10, day, hour, tzinfo=offers.GERMANY)


def test_each_chain_publishes_on_its_own_day():
    """Offers start on Monday 26 Oct. One chain's appear the Thursday before,
    the other's the Sunday before; an offer first seen once it had started
    says nothing about when it was published."""
    monday = date(2026, 10, 26)
    seen = ([{"chain": "Musterdiscount", "valid_from": monday, "first_seen": berlin(22)}] * 3
            + [{"chain": "Musterdiscount", "valid_from": monday, "first_seen": berlin(23)}]
            + [{"chain": "Mustermarkt", "valid_from": monday, "first_seen": berlin(25)}] * 2
            + [{"chain": "Spätmarkt", "valid_from": monday, "first_seen": berlin(27)}])
    assert offers.rhythm(seen) == [
        {"chain": "Musterdiscount", "offers": 4, "usual_day": "Thu", "days_ahead": 4,
         "by_day": {"Thu": 3, "Fri": 1}},
        {"chain": "Mustermarkt", "offers": 2, "usual_day": "Sun", "days_ahead": 1,
         "by_day": {"Sun": 2}},
    ]


def test_a_late_evening_sighting_is_that_days_in_germany():
    """22:30 UTC on Tuesday is half past midnight on Wednesday in Germany:
    the weekday is Germany's."""
    seen = [{"chain": "Musterdiscount", "valid_from": date(2026, 10, 26),
             "first_seen": datetime(2026, 10, 20, 22, 30, tzinfo=UTC)}]
    assert offers.rhythm(seen)[0]["usual_day"] == "Wed"


# --- the server keeping them (PostgreSQL) ----------------------------------------

db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")

TODAY = date(2026, 10, 23)
NOW = datetime(2026, 10, 23, 9, tzinfo=UTC)


def _receipt(image, day, location, lines, user_id=None):
    from grocery_app.db.io import receipt_from_dict

    receipt = receipt_from_dict({
        "source_image": image, "store": "Musterladen", "store_location": location,
        "date": (TODAY - timedelta(days=day)).isoformat(), "currency": "EUR",
        "lines": [{"type": "product", "raw_name": n, "qty": 1, "gross": 1.0,
                   "discount": 0.0, "net": 1.0, "tax_class": "A"} for n in lines]})
    receipt.user_id = user_id
    return receipt


@pytest.fixture
def history(engine, session):
    """The owner buys milk, flowers and something not yet sorted at 12345 on
    three days; Sara buys
    bananas at 54321 on three days, and milk once."""
    from grocery_app.api.repository import PostgresRepository
    from grocery_app.db.io import product_from_dict, resolution_from_dict
    from grocery_app.db.session import make_session_factory
    from tests.conftest import PRODUCTS, RESOLUTION

    for pid, product in PRODUCTS["products"].items():
        session.add(product_from_dict(pid, product))
    session.add(product_from_dict("p-0003", {**PRODUCTS["products"]["p-0002"],
                                             "label": "tulpen", "name": "Tulpen",
                                             "category": "blumen"}))
    session.add(product_from_dict("p-0004", {**PRODUCTS["products"]["p-0002"],
                                             "label": "raetsel", "name": "Rätselware",
                                             "category": None}))
    for entry in RESOLUTION["entries"]:
        session.add(resolution_from_dict(entry))
    session.add(resolution_from_dict({**RESOLUTION["entries"][1], "raw_name": "Raetsel",
                                      "product_id": "p-0004"}))
    session.add(resolution_from_dict({**RESOLUTION["entries"][1], "raw_name": "Tulpen",
                                      "product_id": "p-0003"}))
    session.flush()
    repository = PostgresRepository(make_session_factory(engine))
    session.commit()
    sara = repository.create_user("Sara")
    here, there = "Musterweg 1, 12345 Musterstadt", "Beispielweg 2, 54321 Beispieldorf"
    for day in (3, 10, 17):
        session.add(_receipt(f"o{day}.jpeg", day, here, ["MU Milch 1,5%", "Tulpen", "Raetsel"]))
        session.add(_receipt(f"s{day}.jpeg", day, there, ["Bananen"], sara["id"]))
    session.add(_receipt("s1.jpeg", 1, there, ["MU Milch 1,5%"], sara["id"]))
    # Long ago, somewhere else: not where the owner shops now.
    for day in (200, 210):
        session.add(_receipt(f"old{day}.jpeg", day, "Alt 1, 99999 Altstadt", ["Bananen"]))
    session.commit()
    return repository, sara


def _people(repository, sara):
    return [repository.as_user(None), repository.as_user({"id": sara["id"], "name": "Sara"})]


@db
def test_each_person_is_searched_for_what_they_buy_where_they_shop(history, session):
    from grocery_app.api.offers import wanted_searches

    repository, sara = history
    assert wanted_searches(session, _people(repository, sara), TODAY) == {
        ("12345", "Milch"), ("54321", "Bananen")}, \
        "no flowers (not groceries), nothing unsorted, no one-off milk, no old shop, " \
        "nobody's mixed"


@db
def test_a_search_is_made_once_a_day_and_its_offers_kept(history, session):
    from grocery_app.api.offers import fetch_due
    from grocery_app.db.models import Offer, OfferSearch

    repository, _ = history
    site = FakeSite([raw_offer(1), raw_offer(2, chain="Mustermarkt")])
    source = offers.Marktguru(site)
    first = fetch_due(repository, source, now=NOW, pause=0)
    assert first == {"due": 2, "searched": 2, "failed": 0, "new_offers": 4}, \
        "two offers near each postcode"
    assert fetch_due(repository, source, now=NOW + timedelta(hours=5), pause=0)["due"] == 0
    later = NOW + timedelta(hours=21)
    assert fetch_due(repository, source, now=later, pause=0) == {
        "due": 2, "searched": 2, "failed": 0, "new_offers": 0}

    session.expire_all()
    kept = session.query(Offer).filter_by(postcode="12345", source_id="1").one()
    assert (kept.first_seen_at, kept.last_seen_at) == (NOW, later)
    assert kept.chain == "Musterdiscount" and kept.valid_from == date(2026, 10, 26)
    assert kept.record == offers.read_offer(raw_offer(1))
    assert {(s.postcode, s.word, s.found) for s in session.query(OfferSearch)} == {
        ("12345", "Milch", 2), ("54321", "Bananen", 2)}


@db
def test_a_failed_search_is_skipped_and_stays_due(history, session):
    from grocery_app.api.offers import fetch_due
    from grocery_app.db.models import OfferSearch

    repository, _ = history

    class FailsSecond(FakeSite):
        def __call__(self, url, headers):
            if url != offers.HOME_URL and len(self.asked) > 1:
                raise OSError("down")
            return super().__call__(url, headers)

    result = fetch_due(repository, offers.Marktguru(FailsSecond([raw_offer()])),
                       now=NOW, pause=0)
    assert result == {"due": 2, "searched": 1, "failed": 1, "new_offers": 1}
    assert session.query(OfferSearch).count() == 1, "the failed one is due again"


@db
def test_a_source_that_is_down_is_given_up_on_for_the_pass(history, session):
    from grocery_app.api import offers as offers_api

    repository, _ = history
    site = FakeSite([raw_offer()], fail_searches=99)
    wanted = {("12345", f"Wort{i}") for i in range(10)}
    real = offers_api.wanted_searches
    offers_api.wanted_searches = lambda *a: wanted
    try:
        result = offers_api.fetch_due(repository, offers.Marktguru(site), now=NOW, pause=0)
    finally:
        offers_api.wanted_searches = real
    assert result == {"due": 10, "searched": 0, "failed": 3, "new_offers": 0}


@db
def test_a_search_nobody_needs_is_forgotten(history, session):
    """Once Sara's account is gone, nothing kept points at her shop and her
    bananas."""
    from grocery_app.api.offers import fetch_due
    from grocery_app.db.models import OfferSearch

    repository, sara = history
    source = offers.Marktguru(FakeSite([raw_offer()]))
    fetch_due(repository, source, now=NOW, pause=0)
    repository.as_user({"id": sara["id"], "name": "Sara"}).remove_account()
    fetch_due(repository, source, now=NOW + timedelta(hours=1), pause=0)
    session.expire_all()
    assert {(s.postcode, s.word) for s in session.query(OfferSearch)} == {("12345", "Milch")}


@db
def test_offers_long_over_are_let_go(history, session):
    from grocery_app.api.offers import fetch_due, keep
    from grocery_app.db.models import Offer

    repository, _ = history
    old = offers.read_offer(raw_offer(9, validityDates=[
        {"from": "2026-07-05T22:00:00Z", "to": "2026-07-11T21:59:00Z"}]))
    keep(session, "12345", "Milch", [old], NOW - timedelta(days=110))
    session.commit()
    fetch_due(repository, offers.Marktguru(FakeSite([])), now=NOW, pause=0)
    session.expire_all()
    assert session.query(Offer).filter_by(source_id="9").count() == 0


@db
def test_the_rhythm_counts_an_offer_once_however_many_postcodes(history, session):
    from fastapi.testclient import TestClient

    from grocery_app.api.app import create_app
    from grocery_app.api.offers import keep

    repository, sara = history
    record = offers.read_offer(raw_offer(1))
    keep(session, "12345", "Milch", [record], berlin(22))
    keep(session, "54321", "Milch", [record], berlin(23))
    session.commit()

    client = TestClient(create_app(repository, token="owner-secret"))
    assert client.get("/v1/offers/rhythm", headers={"Authorization": "Bearer owner-secret"}
                      ).json() == [{"chain": "Musterdiscount", "offers": 1, "usual_day": "Thu",
                                    "days_ahead": 4, "by_day": {"Thu": 1}}]
    sara_sees = client.get("/v1/offers/rhythm",
                           headers={"Authorization": f"Bearer {sara['password']}"})
    assert sara_sees.status_code == 403, "about the app: the owner's only"
