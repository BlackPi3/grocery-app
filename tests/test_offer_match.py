"""Which offers are for what a person buys, and what they save (offers step 1b).

The owner, 2026-10-23: single offers for a person's regular groceries, for
the coming week, labelled "your product" (the same brand) or "like yours"
(the same kind), with a saving only like for like. Made-up products, offers
and a fake judge: no model is called.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from grocery_app import offer_match, offers
from tests.conftest import DATABASE_URL as URL
from tests.test_offers import NOW, TODAY, FakeSite, raw_offer
from tests.test_offers import history as offer_history  # noqa: F401 - a fixture

QUARK = {"name": "Magerquark", "brand": "Muster", "details": [],
         "size": {"count": 1, "value": 500, "unit": "g"}}


def offer(id_, per=1.58, unit="kg", amount=0.5, brand="Muster", product="Magerquark"):
    return {"id": id_, "chain": "Musterdiscount", "brand": brand, "product": product,
            "description": "500-g-Becher", "category": "Quark", "price": round(per * amount, 2),
            "pack": {"amount": amount, "unit": unit, "count": 1.0},
            "per_unit": {"amount": per, "per": unit}}


def bought(*prices, per="kg"):
    """Purchases of one product at these shelf prices per unit, oldest first."""
    return [{"date": f"2026-10-{d + 1:02d}", "gross": p / 2, "net_paid": p / 2,
             "discount": 0.0, "qty": 1, "unit_price": {"amount": p, "per": per}}
            for d, p in enumerate(prices)]


class FakeJudge:
    """Says what it was told to for each (product, offer), and records the calls."""

    def __init__(self, said=None, extra=()):
        self.said, self.extra, self.calls = said or {}, list(extra), []

    def __call__(self, system, prompt, schema):
        self.calls.append(prompt)
        verdicts = [{"product": p, "offer": o, "verdict": v} for (p, o), v in self.said.items()
                    if f"Product {p}:" in prompt and f"offer {o}:" in prompt]
        return {"verdicts": verdicts + self.extra}


# --- the judge -----------------------------------------------------------------------

def test_the_judge_reads_the_product_and_its_offers_and_answers_each():
    judge = FakeJudge({("p-1", "a"): "same_product", ("p-1", "b"): "same_kind"},
                      extra=[{"product": "p-1", "offer": "c", "verdict": "probably"}])
    said = offer_match.judge({"p-1": QUARK},
                             {"p-1": [offer("a"), offer("b"), offer("c"), offer("d")]}, judge)
    assert said == {("p-1", "a"): "same_product", ("p-1", "b"): "same_kind"}, \
        "an odd verdict or none is no verdict: asked again, never a no it did not give"
    prompt = judge.calls[0]
    assert "Product p-1: Magerquark | brand Muster | 500 g" in prompt
    assert "offer a: Magerquark | brand Muster | 500-g-Becher | flyer section Quark" in prompt


def test_the_judge_asks_in_batches_and_not_at_all_for_nothing():
    judge = FakeJudge()
    products = {f"p-{i}": QUARK for i in range(10)}
    offer_match.judge(products, {pid: [offer("a")] for pid in products}, judge, batch=4)
    assert len(judge.calls) == 3
    offer_match.judge(products, {"p-1": []}, judge)
    assert len(judge.calls) == 3


def test_the_shortlist_puts_offers_named_by_the_word_first_and_caps_them():
    found = [offer("x", product="Milchschokolade"), offer("y", product="H-Milch"),
             offer("z", product="Frische Milch")]
    assert [o["id"] for o in offer_match.shortlist("Milch", found)] == ["y", "z", "x"]
    assert len(offer_match.shortlist("Milch", found * 30, most=40)) == 40


# --- like for like --------------------------------------------------------------------

def test_the_usual_price_is_the_median_of_the_last_five_in_the_newest_unit():
    assert offer_match.usual_unit_price(bought(9, 1.6, 1.7, 1.8, 1.6, 1.9)) == {
        "amount": 1.7, "per": "kg"}, "the 9 is older than the last five"
    mixed = bought(3.0, 3.0) + bought(1.2, per="l")
    mixed[-1]["date"] = "2026-10-30"
    assert offer_match.usual_unit_price(mixed) == {"amount": 1.2, "per": "l"}
    assert offer_match.usual_unit_price([]) is None


def test_a_pack_is_similar_within_a_factor_of_two():
    assert offer_match.similar_size(QUARK["size"], {"amount": 0.25, "unit": "kg"})
    assert offer_match.similar_size(QUARK["size"], {"amount": 1.0, "unit": "kg"})
    assert not offer_match.similar_size(QUARK["size"], {"amount": 2.0, "unit": "kg"})
    assert not offer_match.similar_size(QUARK["size"], {"amount": 0.2, "unit": "kg"})
    assert offer_match.similar_size(QUARK["size"], {"amount": 0.5, "unit": "kg", "count": 2})
    assert not offer_match.similar_size(QUARK["size"], {"amount": 0.5, "unit": "kg",
                                                        "count": 6}), "a six-pack"
    assert offer_match.similar_size(None, {"amount": 5.0, "unit": "kg"}), "unknown: per unit"
    assert offer_match.similar_size(QUARK["size"], {"amount": 1.0, "unit": "l"})


def test_an_offer_for_your_product_says_what_it_saves():
    found = offer_match.match(QUARK, bought(1.7, 1.7, 1.7), offer("a", per=1.36),
                              "same_product")
    assert found == {"label": "your product", "offer": offer("a", per=1.36),
                     "usual_per_unit": {"amount": 1.7, "per": "kg"},
                     "saving": {"per_unit": 0.34, "share": 0.2}}


def test_another_brand_is_like_yours_at_a_like_size_only():
    rows = bought(1.7, 1.7, 1.7)
    assert offer_match.match(QUARK, rows, offer("b", per=1.2, brand="Andere"),
                             "same_kind")["label"] == "like yours"
    assert offer_match.match(QUARK, rows, offer("c", per=1.2, amount=5.0),
                             "same_kind") is None, "a 5 kg tub is not like a 500 g cup"
    assert offer_match.match(QUARK, rows, offer("c", per=1.2, amount=5.0),
                             "same_product") is not None, "your own, in any size"


def test_no_offer_that_costs_more_than_you_pay_and_none_that_is_not_it():
    rows = bought(1.2, 1.2, 1.2)
    assert offer_match.match(QUARK, rows, offer("a", per=1.58), "same_product") is None
    assert offer_match.match(QUARK, rows, offer("a", per=1.2), "same_product") is None
    assert offer_match.match(QUARK, rows, offer("a", per=0.5), "no") is None
    assert offer_match.match(QUARK, rows, offer("a", per=0.5), "unjudged") is None


def test_an_offer_with_a_pack_but_no_unit_price_is_compared_by_its_pack():
    no_unit = {**offer("a", per=1.98), "per_unit": None}  # 0.99 for 500 g
    assert offer_match.match(QUARK, bought(1.58, 1.58), no_unit, "same_product") is None
    cheaper = {**offer("a", per=1.2), "per_unit": None}
    assert offer_match.match(QUARK, bought(1.58), cheaper, "same_product")["saving"] == {
        "per_unit": 0.38, "share": 0.24}
    raw = {"id": 1, "advertisers": [{"name": "X"}], "price": 0.99, "volume": 0.5,
           "quantity": 1.0, "unit": {"shortName": "kg"},
           "validityDates": [{"from": "2026-10-25T23:00:00Z", "to": "2026-10-31T22:59:00Z"}]}
    assert offers.read_offer(raw)["per_unit"] == {"amount": 1.98, "per": "kg"}


def test_under_a_cent_less_is_no_saving():
    assert offer_match.match(QUARK, bought(1.7), offer("a", per=1.699), "same_product") is None


def test_with_nothing_like_for_like_to_compare_no_saving_is_claimed():
    eggs = {"name": "Eier", "brand": None, "details": [], "size": None}
    per_box = bought(2.0, 2.0, 2.0, per="item")  # a box with no size: not per piece
    found = offer_match.match(eggs, per_box, offer("e", per=0.25, unit="Stk", amount=10),
                              "same_kind")
    assert found["saving"] is None and found["usual_per_unit"] is None
    by_litre = offer_match.match(QUARK, bought(1.7, per="l"), offer("a", per=1.0),
                                 "same_product")
    assert by_litre["saving"] is None, "a kilo is not a litre"


# --- on the server (PostgreSQL) --------------------------------------------------------

db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")

MILK = dict(unit={"shortName": "l"}, volume=1.0, quantity=1.0)


@pytest.fixture
def shoppers(offer_history):  # noqa: F811 - the imported fixture
    """The owner buys milk at 12345 and Sara bananas at 54321 (`tests.test_offers`)."""
    return offer_history


def milk_offer(id_, per, **extra):
    return raw_offer(id_, price=per, referencePrice=per, oldPrice=None,
                     product={"name": "H-Milch"}, **{**MILK, **extra})


def _fetched(repository, results):
    from grocery_app.api.offers import fetch_due

    fetch_due(repository, offers.Marktguru(FakeSite(results)), now=NOW, pause=0)


@db
def test_each_offer_is_judged_once_per_product(shoppers, session):
    from grocery_app.api.offers import judge_due
    from grocery_app.db.models import OfferVerdict

    repository, _ = shoppers
    _fetched(repository, [milk_offer(1, 0.79), milk_offer(2, 0.89)])
    judge = FakeJudge({("p-0001", "1"): "same_kind", ("p-0001", "2"): "no",
                       ("p-0002", "1"): "no", ("p-0002", "2"): "no"})
    assert judge_due(repository, judge, TODAY) == 4, "two offers for milk, two for bananas"
    assert judge_due(repository, judge, TODAY) == 0
    assert len(judge.calls) == 1, "nothing judged twice"
    assert {(v.product_id, v.source_id, v.verdict) for v in session.query(OfferVerdict)} == {
        ("p-0001", "1", "same_kind"), ("p-0001", "2", "no"),
        ("p-0002", "1", "no"), ("p-0002", "2", "no")}
    assert "Bananen" in judge.calls[0] and "Milch" in judge.calls[0]


@db
def test_a_pair_left_unanswered_is_asked_again_but_not_forever(shoppers, session):
    from collections import Counter

    from grocery_app.api.offers import judge_due

    repository, _ = shoppers
    _fetched(repository, [milk_offer(1, 0.79)])
    asked: Counter = Counter()
    silent = FakeJudge()
    assert [judge_due(repository, silent, TODAY, asked) for _ in range(4)] == [0, 0, 0, 0]
    assert len(silent.calls) == offer_match.MOST_ASKS, "then left until the server restarts"

    class Down(FakeJudge):
        def __call__(self, *a):
            raise RuntimeError("busy")

    for _ in range(4):
        with pytest.raises(RuntimeError):
            judge_due(repository, Down(), TODAY, Counter())
    answering = FakeJudge({("p-0001", "1"): "no", ("p-0002", "1"): "no"})
    assert judge_due(repository, answering, TODAY, Counter()) == 2, \
        "a failed call costs its pairs nothing"


@db
def test_a_product_has_at_most_forty_offers_judged_a_week(shoppers, session):
    from grocery_app.api.offers import judge_due

    repository, _ = shoppers
    _fetched(repository, [milk_offer(i, 0.5 + i / 1000) for i in range(60)])
    every = {(p, str(i)): "no" for p in ("p-0001", "p-0002") for i in range(60)}
    assert judge_due(repository, FakeJudge(every), TODAY) == 2 * offer_match.MOST_CANDIDATES
    assert judge_due(repository, FakeJudge(every), TODAY) == 0, "not the next forty an hour on"


@db
def test_only_offers_found_by_the_products_own_word_are_judged_for_it(shoppers, session):
    from grocery_app.api.offers import judge_due, keep

    repository, _ = shoppers
    keep(session, "12345", "Joghurt", [offers.read_offer(milk_offer(5, 0.5))], NOW)
    session.commit()
    judge = FakeJudge()
    assert judge_due(repository, judge, TODAY) == 0 and not judge.calls, \
        "a yoghurt search's offer is not the milk's, though it is near the same shop"


@db
def test_an_offer_long_after_the_coming_week_is_not_judged_yet(shoppers):
    from grocery_app.api.offers import judge_due

    repository, _ = shoppers
    _fetched(repository, [milk_offer(3, 0.79, validityDates=[
        {"from": "2026-11-15T23:00:00Z", "to": "2026-11-21T22:59:00Z"}])])
    judge = FakeJudge({("p-0001", "3"): "no", ("p-0002", "3"): "no"})
    assert judge_due(repository, judge, TODAY) == 0 and not judge.calls
    assert judge_due(repository, judge, TODAY + timedelta(days=20)) == 2


@db
def test_a_person_sees_their_own_offers_and_no_one_elses(shoppers):
    from fastapi.testclient import TestClient

    from grocery_app.api.app import create_app
    from grocery_app.api.offers import judge_due

    repository, sara = shoppers
    _fetched(repository, [milk_offer(1, 0.79), milk_offer(2, 1.29), milk_offer(4, 0.69)])
    judge_due(repository, FakeJudge({("p-0001", "1"): "same_product",
                                     ("p-0001", "2"): "same_kind",
                                     ("p-0002", "4"): "same_kind"}), TODAY)
    client = TestClient(create_app(repository, token="owner-secret"))

    mine = client.get("/v1/offers", headers={"Authorization": "Bearer owner-secret"}).json()
    assert [(o["product"], o["offer"]["id"], o["label"]) for o in mine["offers"]] == [
        ("Milch 1,5%", "1", "your product")], \
        "the dearer one is no offer, and Sara's bananas are not the owner's"
    assert mine["offers"][0]["usual_per_unit"] == {"amount": 1.0, "per": "l"}
    assert mine["offers"][0]["saving"] == {"per_unit": 0.21, "share": 0.21}

    hers = client.get("/v1/offers", headers={"Authorization": f"Bearer {sara['password']}"})
    assert [(o["product"], o["offer"]["id"]) for o in hers.json()["offers"]] == [
        ("Bananen", "4")]


# --- the Home tile (the page's own code, in Node) -----------------------------------------

def test_the_tile_shows_this_weeks_offers_only_and_when():
    """A kept copy of the page may be days old: an offer that ended is not
    shown. One that has not started says from when, a running one until when."""
    from grocery_app.api.app import REVIEW_PAGE
    from tests.test_api import run_page_function

    page = REVIEW_PAGE.read_text(encoding="utf-8")
    assert "const OFFERS_SHOWN = 8;" in page
    out = run_page_function(page, "offersCard offerDays", """
        const OFFERS_SHOWN = 8;
        const day = iso => new Date(iso + "T00:00:00Z");
        globalThis.turningCard = (key, items, fill) => items.map(m => offerDays(m.offer));
        const at = d => new Date(Date.now() + d * 864e5).toISOString().slice(0, 10);
        const m = (from, to) => ({ offer: { valid_from: at(from), valid_to: at(to) } });
        const shown = offersCard({ offers: [m(-8, -2), m(-2, 1), m(3, 8)] });
        console.log(shown.length);
        console.log(shown[0].startsWith("until "), shown[1].startsWith("from "));
        console.log(offersCard({ offers: Array.from({ length: 12 }, () => m(0, 3)) }).length);
        console.log(offersCard({ offers: [] }), offersCard(null));
    """)
    assert out == ["2", "true true", "8", "null null"]


# --- the word a flyer lists it under -----------------------------------------------------

class FakeNamer:
    """Gives the words it was told to for the products it is asked about."""

    def __init__(self, said=None):
        self.said, self.calls = said or {}, []

    def __call__(self, system, prompt, schema):
        self.calls.append(prompt)
        return {"words": [{"product": p, "word": w} for p, w in self.said.items()
                          if f"Product {p}:" in prompt]}


def test_a_product_is_given_the_word_a_flyer_lists_it_under():
    products = {"p-1": {"name": "Bio H-Alpenmilch 1,5% Fett", "brand": "Muster"},
                "p-2": {"name": "salted pickled cucumbers", "brand": None},
                "p-3": {"name": "Rätselware", "brand": None}}
    namer = FakeNamer({"p-1": " H-Milch ", "p-2": "Gewürzgurken", "p-3": "Milch½",
                       "p-9": "Brot"})
    [(asked, said)] = list(offer_match.flyer_words(products, namer))
    assert asked == {"p-1", "p-2", "p-3"}
    assert said == {"p-1": "H-Milch", "p-2": "Gewürzgurken"}, \
        "a size is not a search word, nor a product not asked about"
    assert "brand Muster" in namer.calls[0]


def test_words_are_asked_in_batches_and_not_at_all_for_nothing():
    namer = FakeNamer()
    products = {f"p-{i}": {"name": "Milch"} for i in range(45)}
    assert len(list(offer_match.flyer_words(products, namer))) == 3
    assert list(offer_match.flyer_words({}, namer)) == [] and len(namer.calls) == 3


@db
def test_a_regular_is_named_once_and_searched_by_its_flyer_word(shoppers, session):
    from collections import Counter

    from grocery_app.api.offers import word_due
    from grocery_app.db.models import OfferSearch, Product

    repository, _ = shoppers
    asked: Counter = Counter()
    namer = FakeNamer({"p-0001": "H-Milch"})
    assert word_due(repository, namer, TODAY, asked) == 1
    milk = session.get(Product, "p-0001")
    assert (milk.offer_word, milk.offer_word_by) == ("H-Milch", offer_match.WORDS_VERSION)
    assert "Product p-0002" in namer.calls[0], "Sara's bananas too"
    word_due(repository, namer, TODAY, asked)
    word_due(repository, namer, TODAY, asked)
    assert len(namer.calls) == offer_match.MOST_ASKS, "bananas left unnamed are not asked forever"
    assert all("p-0001" not in call for call in namer.calls[1:]), "a word is asked once"

    _fetched(repository, [milk_offer(1, 0.79)])
    session.expire_all()
    assert {s.word for s in session.query(OfferSearch)} == {"H-Milch", "Bananen"}, \
        "the flyer word, and the name for a product with none"


@db
def test_a_failed_naming_call_names_nothing(shoppers, session):
    from grocery_app.api.offers import word_due
    from grocery_app.db.models import Product

    repository, _ = shoppers

    class Down(FakeNamer):
        def __call__(self, *a):
            raise RuntimeError("busy")

    with pytest.raises(RuntimeError):
        word_due(repository, Down(), TODAY)
    assert session.get(Product, "p-0001").offer_word is None


@db
def test_an_offer_kept_with_the_no_brand_mark_is_served_with_no_brand(shoppers, session):
    from grocery_app.api.offers import candidates
    from grocery_app.db.models import Offer

    repository, _ = shoppers
    _fetched(repository, [milk_offer(1, 0.79)])
    row = session.query(Offer).filter_by(postcode="12345").one()
    row.record = {**row.record, "brand": "thisisnobrand123"}  # as kept before the fix
    session.commit()
    [found] = candidates(session, ["12345"], "Milch", TODAY)
    assert found["brand"] is None
