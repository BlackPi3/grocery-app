"""Offer matching, checked against its rules, on made-up data (risk check, PR #177).

The rules, in words (owner, 2026-10-23):

1. Money: the judge is asked only about (product, offer) pairs with no verdict
   yet; a pair is judged at most once, whoever buys the product. Nothing is
   judged for offers outside the coming week (today to today+7), for products
   nobody has as a regular grocery, or for offers not found by that product's
   own search word. A pass is batched, never one call per offer. No app built
   without an explicit judge ever calls a model.
2. Only product names/brand/details/size and offer texts go to the model,
   nothing about a person.
3. `GET /v1/offers` returns only the asker's own offers; no token is 401.
4. A saving is claimed only like for like; an offer not cheaper than what the
   person usually pays is never shown; "your product" only for same_product,
   "like yours" only for same_kind within a factor of two in size; unjudged,
   "no" or malformed verdicts never match.
5. Stored verdicts hold no person, and go with their product.
6. A failing or hostile judge crashes nothing and stores no verdict it did not give.
7. The privacy page says what goes to Gemini for offers, in German and English.

Every judge and every source here is a fake: no model and no network is reached.
"""

from __future__ import annotations

import json
import re
import socket
import threading
import time
import urllib.request
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, inspect

from grocery_app import offer_match, offers
from grocery_app.api import offers as offers_api
from grocery_app.api.app import create_app
from grocery_app.api.repository import PostgresRepository
from grocery_app.db.io import product_from_dict, receipt_from_dict, resolution_from_dict
from grocery_app.db.models import OfferVerdict, Product
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL as URL
from tests.test_offers import FakeSite, raw_offer

needs_db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")

TODAY = date(2026, 10, 23)
NOW = datetime(2026, 10, 23, 9, tzinfo=UTC)
OWNER = {"Authorization": "Bearer owner-secret"}
VERDICTS = {"same_product", "same_kind", "no"}

OWNER_SHOP = ("Musterladen", "Musterweg 17, 12345 Musterstadt")
SARAS_SHOP = ("Beispielmarkt", "Beispielallee 3, 54321 Beispielstadt")


# --- pure: like for like and the labels ---------------------------------------------

QUARK = {"name": "Magerquark", "brand": "Muster", "details": [],
         "size": {"count": 1, "value": 500, "unit": "g"}}


def an_offer(id_="a", per=1.36, unit="kg", amount=0.5, count=1.0, brand="Muster",
             pack=True):
    return {"id": id_, "chain": "Musterdiscount", "brand": brand, "product": "Magerquark",
            "description": "Becher", "category": "Quark", "price": round(per * amount, 2),
            "pack": {"amount": amount, "unit": unit, "count": count} if pack else None,
            "per_unit": {"amount": per, "per": unit}}


def paid(*prices, per="kg"):
    return [{"date": f"2026-10-{d + 1:02d}", "gross": p / 2, "net_paid": p / 2,
             "discount": 0.0, "qty": 1, "unit_price": {"amount": p, "per": per}}
            for d, p in enumerate(prices)]


def test_your_product_only_when_the_judge_said_same_product():
    rows = paid(1.7, 1.7, 1.7)
    same_brand = an_offer(per=1.2, brand="Muster")
    assert offer_match.match(QUARK, rows, same_brand, "same_product")["label"] == "your product"
    kind = offer_match.match(QUARK, rows, same_brand, "same_kind")
    assert kind is not None and kind["label"] == "like yours", \
        "same brand, but the judge said same_kind: not 'your product'"


@pytest.mark.parametrize("verdict", ["no", "unjudged", "", None, "SAME_PRODUCT",
                                     "same_product ", "same product", "yes", "Same_Kind"])
def test_anything_but_a_clean_yes_verdict_never_matches(verdict):
    assert offer_match.match(QUARK, paid(1.7, 1.7, 1.7), an_offer(per=0.5), verdict) is None


@pytest.mark.parametrize("amount, shown", [
    (0.25, True), (1.0, True),        # exactly half and exactly double: within two
    (0.2, False), (1.1, False), (2.5, False)])
def test_like_yours_only_within_a_factor_of_two(amount, shown):
    found = offer_match.match(QUARK, paid(1.7, 1.7, 1.7),
                              an_offer(per=1.2, amount=amount, brand="Andere"), "same_kind")
    assert (found is not None) is shown


def test_like_yours_with_a_multipack_counts_the_whole_pack():
    found = offer_match.match(QUARK, paid(1.7, 1.7, 1.7),
                              an_offer(per=1.2, amount=0.5, count=4, brand="Andere"),
                              "same_kind")
    assert found is None, "4 x 500 g is four times a 500 g cup"


def test_like_yours_when_a_size_is_unknown_is_not_ruled_out_by_size():
    unsized = {**QUARK, "size": None}
    assert offer_match.match(unsized, paid(1.7, 1.7, 1.7),
                             an_offer(per=1.2, amount=5.0), "same_kind") is not None
    assert offer_match.match(QUARK, paid(1.7, 1.7, 1.7),
                             an_offer(per=1.2, pack=False), "same_kind") is not None


@pytest.mark.parametrize("per", [1.7, 1.71, 2.5])
def test_an_offer_not_cheaper_than_usual_is_never_shown(per):
    for verdict in ("same_product", "same_kind"):
        assert offer_match.match(QUARK, paid(1.7, 1.7, 1.7), an_offer(per=per), verdict) is None


def test_a_saving_shown_is_a_real_one():
    found = offer_match.match(QUARK, paid(1.7, 1.7, 1.7), an_offer(per=1.699),
                              "same_product")
    if found is not None and found["saving"] is not None:
        assert found["saving"]["per_unit"] > 0, "a saving of nothing is no saving"


def test_the_saving_is_against_the_usual_price_in_the_same_unit():
    found = offer_match.match(QUARK, paid(1.6, 1.8, 1.7), an_offer(per=1.36), "same_product")
    assert found["usual_per_unit"] == {"amount": 1.7, "per": "kg"}
    assert found["saving"]["per_unit"] == pytest.approx(0.34)


def test_a_dearer_offer_with_a_known_pack_but_no_unit_price_is_not_shown():
    """`read_offer` gives a pack but no per-unit price when the source sends no
    reference price: 0.99 for 500 g is 1.98 a kilo, dearer than the usual 1.58."""
    dearer = {**an_offer(per=1.98), "per_unit": None}
    assert dearer["price"] == 0.99 and dearer["pack"]["amount"] == 0.5
    assert offer_match.match(QUARK, paid(1.58, 1.58, 1.58), dearer, "same_product") is None


@pytest.mark.parametrize("paid_per, offer_per, offer_amount", [
    ("kg", "l", 1.36),         # a kilo is not a litre
    ("l", "kg", 1.36),
    ("kg", "100 g", 0.2),      # 0.20 per 100 g is 2.00 per kg: dearer, not a saving
    ("kg", "g", 0.002),
    ("item", "Stk", 0.25),     # a receipt line with no known size is not per piece
    ("item", "piece", 0.25),
    ("item", "item", 0.25),
])
def test_no_saving_is_claimed_across_units(paid_per, offer_per, offer_amount):
    found = offer_match.match(QUARK, paid(1.7, 1.7, 1.7, per=paid_per),
                              an_offer(per=offer_amount, unit=offer_per), "same_product")
    assert found is None or found["saving"] is None, found


# --- pure: the judge ----------------------------------------------------------------

class Judge:
    """Answers `say` for every pair it is asked about (or `answer` verbatim)."""

    def __init__(self, say="same_product", answer=None, raise_=None):
        self.say, self.answer, self.raise_ = say, answer, raise_
        self.calls: list[str] = []
        self.asked: list[tuple[str, str]] = []

    def __call__(self, system, prompt, schema):
        text = f"{system}\n{prompt}\n{json.dumps(schema, ensure_ascii=False, default=str)}"
        self.calls.append(text)
        current = None
        for line in prompt.splitlines():
            m = re.search(r"Product (\S+):", line)
            if m:
                current = m.group(1)
            for o in re.findall(r"offer (\S+):", line):
                self.asked.append((current, o))
        if self.raise_ is not None:
            raise self.raise_
        if self.answer is not None:
            return self.answer(self.asked) if callable(self.answer) else self.answer
        return {"verdicts": [{"product": p, "offer": o, "verdict": self.say}
                             for p, o in self.asked]}


HOSTILE = {
    "raises": dict(raise_=RuntimeError("model down")),
    "times out": dict(raise_=TimeoutError("slow")),
    "None": dict(answer=lambda asked: None),
    "a string": dict(answer=lambda asked: "same_product"),
    "a list": dict(answer=lambda asked: [1, 2, 3]),
    "verdicts not a list": dict(answer=lambda asked: {"verdicts": "same_product"}),
    "verdicts of numbers": dict(answer=lambda asked: {"verdicts": [1, None, "x"]}),
    "wrong ids": dict(answer=lambda asked: {"verdicts": [
        {"product": "p-ghost", "offer": o, "verdict": "same_product"} for _, o in asked] + [
        {"product": p, "offer": "nope", "verdict": "same_product"} for p, _ in asked]}),
    "odd verdicts": dict(answer=lambda asked: {"verdicts": [
        {"product": p, "offer": o, "verdict": "SAME_PRODUCT"} for p, o in asked]}),
    "huge": dict(answer=lambda asked: {"verdicts": [
        {"product": "p" * 10_000, "offer": str(i), "verdict": "x" * 1000}
        for i in range(20_000)]}),
}


@pytest.mark.parametrize("kind", sorted(HOSTILE))
def test_a_hostile_judge_never_yields_a_match(kind):
    products = {"p-1": QUARK, "p-2": {**QUARK, "name": "Skyr"}}
    candidates = {"p-1": [an_offer("a"), an_offer("b")], "p-2": [an_offer("c")]}
    try:
        said = offer_match.judge(products, candidates, Judge(**HOSTILE[kind]))
    except Exception:
        return  # said plainly; the caller must contain it (tested on the server below)
    assert set(said) <= {("p-1", "a"), ("p-1", "b"), ("p-2", "c")}
    assert all(v == "no" for v in said.values()), said


def test_a_verdict_for_an_offer_not_asked_about_for_that_product_is_ignored():
    products = {"p-1": QUARK, "p-2": {**QUARK, "name": "Skyr"}}
    candidates = {"p-1": [an_offer("a")], "p-2": [an_offer("c")]}
    crossed = Judge(answer=lambda asked: {"verdicts": [
        {"product": "p-1", "offer": "c", "verdict": "same_product"},
        {"product": "p-2", "offer": "a", "verdict": "same_product"}]})
    said = offer_match.judge(products, candidates, crossed, batch=8)
    assert said.get(("p-1", "c")) in (None, "no") and said.get(("p-2", "a")) in (None, "no")


def test_one_product_with_many_offers_is_one_call_not_one_per_offer():
    judge = Judge()
    offer_match.judge({"p-1": QUARK}, {"p-1": [an_offer(str(i)) for i in range(30)]}, judge)
    assert len(judge.calls) == 1


# --- on the server (PostgreSQL) ---------------------------------------------------------

PRODUCTS = {
    "p-milch": {"name": "Vollmilch 1L", "category": "milch",
                "size": {"count": 1, "value": 1.0, "unit": "l"}},
    "p-tulpe": {"name": "Tulpen", "category": "blumen", "size": None},
    "p-quark": {"name": "Magerquark 500 g", "category": "quark",
                "size": {"count": 1, "value": 500, "unit": "g"}},
}
RAW = {"p-milch": "MU VOLLMILCH H", "p-tulpe": "TULPEN BUND", "p-quark": "MU MAGERQUARK"}
OWNER_DAYS = ("2026-10-01", "2026-10-08", "2026-10-15")
SARA_DAYS = ("2026-10-02", "2026-10-09", "2026-10-16")


def utc_days(first, last):
    """Germany's days `first`..`last` as the source's UTC validity."""
    def edge(d, end):
        offset = 2 if d < date(2026, 10, 25) else 1
        moment = datetime(d.year, d.month, d.day, tzinfo=UTC) - timedelta(hours=offset)
        return (moment + timedelta(days=1, minutes=-1) if end else moment
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [{"from": edge(first, False), "to": edge(last, True)}]


def milk(id_, per, first=date(2026, 10, 26), last=date(2026, 10, 31), product="H-Vollmilch"):
    return offers.read_offer(raw_offer(id_, price=per, referencePrice=per, oldPrice=None,
                                       product={"name": product}, unit={"shortName": "l"},
                                       volume=1.0, quantity=1.0,
                                       validityDates=utc_days(first, last)))


# Which offers are kept, where, under which word.
KEPT = [
    ("12345", "Vollmilch", milk("m1", 0.99)),                       # owner's week, cheaper
    ("54321", "Vollmilch", milk("m2", 0.49)),                       # Sara's week, cheaper
    ("12345", "Vollmilch", milk("now", 0.95, date(2026, 10, 20), date(2026, 10, 24))),
    ("12345", "Vollmilch", milk("edge8", 0.90, date(2026, 10, 31), date(2026, 11, 6))),
    ("12345", "Vollmilch", milk("late", 0.80, date(2026, 11, 15), date(2026, 11, 21))),
    ("12345", "Vollmilch", milk("past", 0.70, date(2026, 10, 12), date(2026, 10, 17))),
    ("12345", "Joghurt", milk("y1", 0.30)),                         # another word's find
    ("12345", "Tulpen", milk("t1", 0.30, product="Tulpen")),        # not a grocery
    ("12345", "Magerquark", milk("q1", 0.30, product="Magerquark")),  # bought once
]
JUDGEABLE = {("p-milch", "m1"), ("p-milch", "m2"), ("p-milch", "now")}


def add_receipt(session, shop, user_id, day, pids, price):
    store, location = shop
    receipt = receipt_from_dict({
        "source_image": f"{store}-{user_id}-{day}.jpeg", "transcribed_by": "llm",
        "store": store, "store_location": location, "date": day, "time": "10:00",
        "currency": "EUR", "printed_total": round(price * len(pids), 2),
        "lines": [{"type": "product", "raw_name": RAW[p], "qty": 1, "gross": price,
                   "discount": 0.0, "net": price, "tax_class": "A"} for p in pids]})
    receipt.user_id = user_id
    session.add(receipt)


@pytest.fixture
def town(engine, session):
    """The owner buys milk (1.37) and tulips at 12345 on three days, quark once;
    Sara buys milk (0.61) at 54321 on three days. The offers in `KEPT` are kept."""
    for pid, p in PRODUCTS.items():
        session.add(product_from_dict(pid, {
            "label": pid, "name": p["name"], "brand": "Muster", "details": [],
            "size": p["size"], "category": p["category"], "is_organic": False, "eans": [],
            "open_questions": [], "provenance": {"attributes": "test", "source": "test"}}))
    session.flush()
    for store, _ in (OWNER_SHOP, SARAS_SHOP):
        for pid, raw in RAW.items():
            session.add(resolution_from_dict({
                "store": store, "raw_name": raw, "line_type": "product", "product_id": pid,
                "confirmed_by": "test", "confirmed_at": "2026-01-01", "source": "test"}))
    session.commit()
    repository = PostgresRepository(make_session_factory(engine))
    sara = repository.create_user("Sara", "sara@example.com")
    for day in OWNER_DAYS:
        add_receipt(session, OWNER_SHOP, None, day, ["p-milch", "p-tulpe"], 1.37)
    add_receipt(session, OWNER_SHOP, None, "2026-10-20", ["p-quark"], 1.37)
    for day in SARA_DAYS:
        add_receipt(session, SARAS_SHOP, sara["id"], day, ["p-milch"], 0.61)
    for postcode, word, record in KEPT:
        offers_api.keep(session, postcode, word, [record], NOW)
    session.commit()
    return repository, sara


def personal(sara):
    out = ["Sara", "sara@example.com", "owner-secret", sara["password"], "Musterweg",
           "Beispielallee", "Musterstadt", "Beispielstadt", "12345", "54321",
           *RAW.values(), *OWNER_DAYS, *SARA_DAYS, "1.37", "0.61"]
    if len(str(sara["id"])) > 3:
        out.append(str(sara["id"]))
    return out


@needs_db
def test_only_unjudged_pairs_in_the_week_for_regular_groceries_by_their_word(town, session):
    repository, _ = town
    judge = Judge()
    offers_api.judge_due(repository, judge, TODAY)
    asked = set(judge.asked)
    assert asked <= JUDGEABLE, f"judged what it must not: {asked - JUDGEABLE}"
    assert ("p-milch", "m1") in asked and ("p-milch", "m2") in asked, "something was judged"
    assert len(judge.asked) == len(asked), "a pair asked twice in one pass"


@needs_db
def test_an_offer_already_running_this_week_is_judged(town):
    repository, _ = town
    judge = Judge()
    offers_api.judge_due(repository, judge, TODAY)
    assert ("p-milch", "now") in set(judge.asked), "Tue-Sat this week is the coming week"


@needs_db
def test_a_pair_is_judged_once_ever_whoever_buys_it(town, session):
    repository, sara = town
    judge = Judge()
    offers_api.judge_due(repository, judge, TODAY)
    assert offers_api.judge_due(repository, judge, TODAY) == 0
    # A day later the offer starting on 31 Oct comes into the week: that one only.
    before = len(judge.asked)
    offers_api.judge_due(repository, judge, TODAY + timedelta(days=1))
    assert judge.asked[before:] == [("p-milch", "edge8")]
    assert len(judge.asked) == len(set(judge.asked)), "nothing asked twice"
    calls = len(judge.calls)
    # A third person starts buying milk at Sara's shop: nothing new to judge.
    lea = repository.create_user("Lea", "lea@example.com")
    for day in ("2026-10-03", "2026-10-10", "2026-10-17"):
        add_receipt(session, SARAS_SHOP, lea["id"], day, ["p-milch"], 0.66)
    session.commit()
    offers_api.judge_due(repository, judge, TODAY)
    assert len(judge.calls) == calls
    rows = [(v.product_id, v.source_id) for v in session.query(OfferVerdict)]
    assert len(rows) == len(set(rows)), "one verdict per pair"


NAMES = [f"Sorte{a}{b}" for a in "abcdefghij" for b in "xyz"]  # no digits: a search word


def _many_regulars(session, n, offers_each=5):
    for name in NAMES[:n]:
        pid = f"p-{name}"
        session.add(product_from_dict(pid, {
            "label": pid, "name": name, "brand": "Muster", "details": [],
            "size": {"count": 1, "value": 1.0, "unit": "l"}, "category": "milch",
            "is_organic": False, "eans": [], "open_questions": [],
            "provenance": {"attributes": "test", "source": "test"}}))
        session.flush()
        RAW[pid] = f"MU {name.upper()}"
        session.add(resolution_from_dict({
            "store": OWNER_SHOP[0], "raw_name": RAW[pid], "line_type": "product",
            "product_id": pid, "confirmed_by": "test", "confirmed_at": "2026-01-01",
            "source": "test"}))
    session.commit()
    for d in ("2026-10-02", "2026-10-09", "2026-10-16"):
        add_receipt(session, OWNER_SHOP, None, d, [f"p-{n}" for n in NAMES[:n]], 1.0)
    session.commit()
    for name in NAMES[:n]:
        assert offers.search_word(name) == name
        offers_api.keep(session, "12345", name,
                        [milk(f"{name}-{k}", 0.5, product=name) for k in range(offers_each)],
                        NOW)
    session.commit()


@pytest.fixture
def many(town, session):
    yield lambda n, offers_each=5: _many_regulars(session, n, offers_each)
    for name in NAMES:
        RAW.pop(f"p-{name}", None)


@needs_db
def test_many_regulars_are_judged_in_few_calls(town, many):
    repository, _ = town
    many(30)
    judge = Judge()
    offers_api.judge_due(repository, judge, TODAY)
    assert len(set(judge.asked)) >= 150, "every pair was asked"
    assert len(judge.calls) <= 10, f"{len(judge.calls)} calls for 31 products"


@needs_db
def test_a_batch_that_fails_does_not_get_the_others_judged_again(town, many, session):
    """Nine regulars and milk: two batches. The second call fails once; next
    pass a new offer has come for one product. No pair is paid for twice."""
    repository, _ = town
    many(9)

    class FailsSecondCallOnce(Judge):
        def __call__(self, system, prompt, schema):
            answer = super().__call__(system, prompt, schema)
            if len(self.calls) == 2:
                raise RuntimeError("model busy")
            return answer

    judge = FailsSecondCallOnce()
    try:
        offers_api.judge_due(repository, judge, TODAY)
    except Exception:  # noqa: BLE001 - the thread logs it
        pass
    answered = set(judge.asked)
    session.expire_all()
    kept = {(v.product_id, v.source_id) for v in session.query(OfferVerdict)}
    offers_api.keep(session, "12345", NAMES[0],
                    [milk(f"{NAMES[0]}-new", 0.5, product=NAMES[0])], NOW)
    session.commit()
    offers_api.judge_due(repository, judge, TODAY)
    twice = {p for p in judge.asked if judge.asked.count(p) > 1}
    assert kept and kept < answered, "the first batch was kept, the second was not"
    assert not twice & kept, f"{len(twice & kept)} answered pairs judged twice"
    assert twice == answered - kept, "only the failed call's pairs are asked again"


@needs_db
def test_nothing_about_a_person_reaches_the_judge(town):
    repository, sara = town
    judge = Judge()
    offers_api.judge_due(repository, judge, TODAY)
    assert judge.calls
    sent = "\n".join(judge.calls)
    for secret in personal(sara):
        assert secret not in sent, f"{secret!r} sent to the model"


@needs_db
def test_the_verdicts_table_holds_no_person(town, engine, session):
    repository, sara = town
    offers_api.judge_due(repository, Judge(), TODAY)
    columns = {c["name"] for c in inspect(engine).get_columns("offer_verdicts")}
    assert not any("user" in c or "postcode" in c for c in columns), columns
    assert all(fk["referred_table"] != "users"
               for fk in inspect(engine).get_foreign_keys("offer_verdicts"))
    for v in session.query(OfferVerdict):
        text = json.dumps([v.product_id, v.source, v.source_id, v.verdict, v.judged_by])
        for secret in personal(sara):
            assert secret not in text


def _solo_with_verdict(session):
    session.add(product_from_dict("p-solo", {
        "label": "solo", "name": "Solo", "brand": None, "details": [], "size": None,
        "category": "milch", "is_organic": False, "eans": [], "open_questions": [],
        "provenance": {"attributes": "test", "source": "test"}}))
    session.flush()
    session.add(OfferVerdict(product_id="p-solo", source="marktguru", source_id="m1",
                             verdict="no", judged_by="test", judged_at=NOW))
    session.commit()


@needs_db
def test_a_products_verdicts_go_with_it_in_sql(town, session):
    _solo_with_verdict(session)
    session.execute(delete(Product).where(Product.id == "p-solo"))
    session.commit()
    assert session.query(OfferVerdict).filter_by(product_id="p-solo").count() == 0


@needs_db
def test_a_products_verdicts_go_with_it_in_the_orm(town, session):
    _solo_with_verdict(session)
    session.delete(session.get(Product, "p-solo"))
    session.commit()
    assert session.query(OfferVerdict).filter_by(product_id="p-solo").count() == 0


# --- a hostile judge on the server ----------------------------------------------------

@needs_db
@pytest.mark.parametrize("kind", sorted(HOSTILE))
def test_a_hostile_judge_stores_nothing_it_did_not_say(town, session, kind):
    repository, _ = town
    try:
        offers_api.judge_due(repository, Judge(**HOSTILE[kind]), TODAY)
    except Exception:  # noqa: BLE001 - the thread must contain it; see below
        pass
    session.expire_all()
    rows = list(session.query(OfferVerdict))
    for v in rows:
        assert v.verdict in VERDICTS and (v.product_id, v.source_id) in JUDGEABLE
        assert v.verdict == "no", "a hostile judge said no yes"
    assert not rows, "a verdict the judge did not give was stored, so the pair is never asked again"
    good = Judge()
    offers_api.judge_due(repository, good, TODAY)
    assert {("p-milch", "m1"), ("p-milch", "m2")} <= set(good.asked)


@needs_db
def test_an_answer_that_names_only_some_pairs_leaves_the_rest_unjudged(town, session):
    """Unsure (rule 6 against the PR's 'missing counts as no'): a well-formed answer
    that skips a pair did not give a verdict for it."""
    repository, _ = town
    partial = Judge(answer=lambda asked: {"verdicts": [
        {"product": "p-milch", "offer": "m1", "verdict": "same_product"}]})
    offers_api.judge_due(repository, partial, TODAY)
    session.expire_all()
    stored = {(v.product_id, v.source_id): v.verdict for v in session.query(OfferVerdict)}
    assert stored.get(("p-milch", "m1")) == "same_product"
    assert ("p-milch", "m2") not in stored, stored


@needs_db
def test_a_crossed_or_doubled_verdict_is_not_stored_and_not_shown(town, session):
    repository, _ = town
    crossed = Judge(answer=lambda asked: {"verdicts": [
        {"product": "p-milch", "offer": "y1", "verdict": "same_product"},   # not its word
        {"product": "p-milch", "offer": "late", "verdict": "same_product"},  # not this week
        {"product": "p-tulpe", "offer": "t1", "verdict": "same_product"},   # not a grocery
        {"product": "p-milch", "offer": "m1", "verdict": "same_product"},
        {"product": "p-milch", "offer": "m1", "verdict": "no"},             # twice
    ]})
    try:
        offers_api.judge_due(repository, crossed, TODAY)
    except Exception:  # noqa: BLE001
        pass
    session.expire_all()
    rows = [(v.product_id, v.source_id) for v in session.query(OfferVerdict)]
    assert set(rows) <= JUDGEABLE, rows
    assert len(rows) == len(set(rows))
    shown = {o["offer"]["id"] for o in offers_api.offers_for(repository.as_user(None), TODAY)}
    assert not shown & {"y1", "late", "t1"}, shown


@needs_db
def test_the_offers_thread_survives_a_judge_that_keeps_failing(town, monkeypatch):
    repository, _ = town

    class Stop(BaseException):
        pass

    stop = threading.Event()

    class Failing(Judge):
        def __call__(self, system, prompt, schema):
            if stop.is_set():
                raise Stop()
            super().__call__(system, prompt, schema)
            raise RuntimeError("model down")

    judge = Failing()
    monkeypatch.setattr(offers_api, "PAUSE_BETWEEN_SEARCHES_S", 0)
    source = offers.Marktguru(FakeSite([raw_offer(1, product={"name": "H-Vollmilch"},
                                                  unit={"shortName": "l"}, volume=1.0)]))
    thread = threading.Thread(target=offers_api.keep_fetching,
                              args=(repository, source), kwargs={"judge": judge, "every": 0.05},
                              daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while len(judge.calls) < 3 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert thread.is_alive(), "the thread died on a failing judge"
        assert len(judge.calls) >= 3, "a failed judgement is asked again on a later pass"
    finally:
        stop.set()
        thread.join(timeout=5)


# --- what a person is shown ---------------------------------------------------------

def _judged(repository):
    offers_api.judge_due(repository, Judge(say="same_product"), TODAY)


@needs_db
def test_no_token_is_401(town):
    repository, _ = town
    client = TestClient(create_app(repository, token="owner-secret"))
    for headers in ({}, {"Authorization": "Bearer guessed"}, {"Authorization": "owner-secret"}):
        assert client.get("/v1/offers", headers=headers).status_code == 401, headers


@needs_db
def test_each_person_sees_their_own_regulars_at_their_own_shops_at_their_own_prices(town):
    repository, sara = town
    _judged(repository)
    client = TestClient(create_app(repository, token="owner-secret"))

    mine = client.get("/v1/offers", headers=OWNER)
    assert mine.status_code == 200
    ids = {o["offer"]["id"] for o in mine.json()["offers"]}
    assert "m1" in ids and ids <= {"m1", "now"}, ids
    for o in mine.json()["offers"]:
        assert o["usual_per_unit"] == {"amount": 1.37, "per": "l"}, "the owner's own price"
    for leak in ("54321", "Beispiel", "0.61", "Sara"):
        assert leak not in mine.text, leak

    hers = client.get("/v1/offers", headers={"Authorization": f"Bearer {sara['password']}"})
    assert hers.status_code == 200
    assert [o["offer"]["id"] for o in hers.json()["offers"]] == ["m2"], \
        "m1 is dearer than her 0.61 and not near her shop"
    assert hers.json()["offers"][0]["usual_per_unit"] == {"amount": 0.61, "per": "l"}
    for leak in ("12345", "Musterweg", "Musterstadt", "1.37", "Tulpen", "Magerquark"):
        assert leak not in hers.text, leak


@needs_db
def test_someone_with_no_receipts_sees_nothing(town):
    repository, _ = town
    _judged(repository)
    lea = repository.create_user("Lea", "lea@example.com")
    client = TestClient(create_app(repository, token="owner-secret"))
    answer = client.get("/v1/offers", headers={"Authorization": f"Bearer {lea['password']}"})
    assert answer.status_code == 200 and answer.json()["offers"] == []


@needs_db
def test_an_unjudged_or_no_offer_is_never_shown(town, session):
    repository, _ = town
    offers_api.judge_due(repository, Judge(say="no"), TODAY)
    assert offers_api.offers_for(repository.as_user(None), TODAY) == []
    session.query(OfferVerdict).delete()
    session.commit()
    assert offers_api.offers_for(repository.as_user(None), TODAY) == [], "nothing judged yet"


@needs_db
def test_an_offer_that_is_over_is_not_shown_though_judged(town, session):
    repository, _ = town
    _judged(repository)
    session.add(OfferVerdict(product_id="p-milch", source="marktguru", source_id="past",
                             verdict="same_product", judged_by="test", judged_at=NOW))
    session.commit()
    shown = {o["offer"]["id"] for o in offers_api.offers_for(repository.as_user(None), TODAY)}
    assert "past" not in shown


# --- 1: no judge given, no model --------------------------------------------------------

@pytest.fixture
def no_network(monkeypatch):
    tried: list[object] = []

    def refuse(*args, **kwargs):
        tried.append(args)
        raise OSError("no network in tests")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    return tried


@needs_db
def test_an_app_with_offers_but_no_judge_never_calls_a_model(town, session, monkeypatch,
                                                             no_network):
    repository, _ = town
    from grocery_app.db.models import OfferSearch

    session.query(OfferSearch).delete()  # so the thread has searches due
    session.commit()
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-never-used")
    monkeypatch.setenv("GEMINI_VERTEX_PROJECT", "fake-project")
    monkeypatch.setattr(offers_api, "PAUSE_BETWEEN_SEARCHES_S", 0)
    site = FakeSite([raw_offer(1, product={"name": "H-Vollmilch"})])
    with TestClient(create_app(repository, token="owner-secret",
                               offers=offers.Marktguru(site))) as client:
        deadline = time.monotonic() + 5
        while not [u for u, _ in site.asked if u != offers.HOME_URL] \
                and time.monotonic() < deadline:
            time.sleep(0.05)
        time.sleep(0.5)
        assert client.get("/v1/offers", headers=OWNER).status_code == 200
    assert [u for u, _ in site.asked if u != offers.HOME_URL], "the thread did run"
    assert not no_network, "something reached for the network"
    session.expire_all()
    assert session.query(OfferVerdict).count() == 0


# --- 7: the privacy page ---------------------------------------------------------------

def test_the_privacy_page_says_gemini_reads_offers_in_both_languages():
    from pathlib import Path

    import grocery_app.api as api

    page = (Path(api.__file__).parent / "privacy.html").read_text(encoding="utf-8")
    lowered = page.lower()
    assert lowered.count("gemini") >= 2
    assert "angebot" in lowered and "offer" in lowered
