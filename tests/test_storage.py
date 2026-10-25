"""Where a product is kept and how long it keeps (`grocery_app.storage`).

The owner, 2026-10-25: storage is the product's, not its category's; a model
says it once per product. Made-up products and a fake model: nothing is
called.
"""

from __future__ import annotations

from collections import Counter

import pytest

from grocery_app import offer_match, storage
from tests.conftest import DATABASE_URL as URL
from tests.test_offers import history as offer_history  # noqa: F401 - a fixture

db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")


class FakeModel:
    """Gives the answers it was told to for the products it is asked about."""

    def __init__(self, said=None):
        self.said, self.calls = said or {}, []

    def __call__(self, system, prompt, schema):
        self.calls.append(prompt)
        return {"products": [{"product": p, "storage": s, "keeps_days": d}
                             for p, (s, d) in self.said.items() if f"Product {p}:" in prompt]}


def test_each_product_is_told_where_it_is_kept_and_how_long_it_keeps():
    products = {"p-1": {"name": "Thunfisch in Öl", "brand": "Muster"},
                "p-2": {"name": "Lachsfilet", "brand": None},
                "p-3": {"name": "Minipizza Salami", "brand": None}}
    model = FakeModel({"p-1": ("cupboard", 700), "p-2": ("fridge", 4),
                       "p-3": ("freezer", 300), "p-9": ("fridge", 7)})
    [(asked, said)] = list(storage.answers(products, model))
    assert asked == {"p-1", "p-2", "p-3"}
    assert said == {"p-1": ("cupboard", 700), "p-2": ("fridge", 4), "p-3": ("freezer", 300)}, \
        "a product not asked about is ignored"
    assert "Product p-1: Thunfisch in Öl | brand Muster" in model.calls[0]


@pytest.mark.parametrize("place, days", [
    ("cellar", 30),          # not one of the three places
    ("fridge", 0),           # keeps no day at all
    ("fridge", -3),
    ("cupboard", 3651),      # past ten years is not a number of days
    ("fridge", 7.5),         # not a whole day
    ("fridge", True),        # a bool is not a number
    ("fridge", "7"),
    (None, 7),
])
def test_an_answer_out_of_bounds_is_no_answer(place, days):
    [(asked, said)] = list(storage.answers({"p-1": {"name": "Milch"}},
                                           FakeModel({"p-1": (place, days)})))
    assert asked == {"p-1"} and said == {}


def test_the_bounds_themselves_are_answers():
    model = FakeModel({"p-1": ("fridge", 1), "p-2": ("cupboard", 3650), "p-3": ("fridge", 7.0)})
    [(_, said)] = list(storage.answers({p: {"name": "x"} for p in ("p-1", "p-2", "p-3")}, model))
    assert said == {"p-1": ("fridge", 1), "p-2": ("cupboard", 3650), "p-3": ("fridge", 7)}


def test_a_broken_answer_answers_nothing():
    for broken in (None, [], {"products": "fridge"}, {"products": ["fridge", None]}):
        [(asked, said)] = list(storage.answers({"p-1": {"name": "Milch"}},
                                               lambda *a, broken=broken: broken))
        assert asked == {"p-1"} and said == {}


def test_a_failed_batch_does_not_hold_up_the_next():
    """Review of PR #207: a batch the model fails on is skipped, not the end
    of the pass, so the products after it are still answered."""
    calls = []

    def flaky(system, prompt, schema):
        calls.append(prompt)
        if len(calls) == 1:
            raise RuntimeError("no JSON")
        return {"products": [{"product": "p-24", "storage": "fridge", "keeps_days": 5}]}

    products = {f"p-{i:02}": {"name": "Milch"} for i in range(25)}
    got = list(storage.answers(products, flaky))
    assert [(len(asked), said) for asked, said in got] == [(20, {}), (5, {"p-24": ("fridge", 5)})]


def test_products_are_asked_twenty_to_a_call_and_not_at_all_for_none():
    model = FakeModel()
    products = {f"p-{i:02}": {"name": "Milch"} for i in range(45)}
    assert [len(a) for a, _ in storage.answers(products, model)] == [20, 20, 5]
    assert list(storage.answers({}, model)) == [] and len(model.calls) == 3


@db
def test_a_bought_grocery_is_asked_once_and_carries_its_answer(offer_history, session):  # noqa: F811
    """Only groceries someone bought are asked about (the owner's milk, Sara's
    bananas; not the tulips); an answer is kept and never asked again; a
    product given no usable answer is asked `MOST_ASKS` times at most; and
    the answer reaches the products the normalizer reads."""
    from grocery_app.api.offers import storage_due
    from grocery_app.db.io import load_normalizer_inputs
    from grocery_app.db.models import Product

    repository, _ = offer_history
    asked: Counter = Counter()
    model = FakeModel({"p-0001": ("fridge", 9)})
    assert storage_due(repository, model, asked) == 1
    assert "Product p-0002" in model.calls[0], "Sara's bananas too"
    assert "p-0003" not in model.calls[0], "tulips are not a grocery"
    milk = session.get(Product, "p-0001")
    assert (milk.storage, milk.keeps_days, milk.storage_by) == ("fridge", 9, storage.VERSION)

    storage_due(repository, model, asked)
    storage_due(repository, model, asked)
    assert len(model.calls) == offer_match.MOST_ASKS, \
        "bananas left unanswered are not asked forever"
    assert all("p-0001" not in call for call in model.calls[1:]), "an answer is asked once"

    session.expire_all()
    products = load_normalizer_inputs(session)["products"]
    assert (products["p-0001"]["storage"], products["p-0001"]["keeps_days"]) == ("fridge", 9)
    assert "storage" not in products["p-0002"] and "keeps_days" not in products["p-0002"]


@db
def test_a_failed_call_keeps_nothing_and_counts_as_asked(offer_history, session):  # noqa: F811
    from grocery_app.api.offers import storage_due
    from grocery_app.db.models import Product

    repository, _ = offer_history

    calls = []

    def down(system, prompt, schema):
        calls.append(prompt)
        raise RuntimeError("busy")

    asked: Counter = Counter()
    for _ in range(offer_match.MOST_ASKS + 2):
        assert storage_due(repository, down, asked) == 0
    assert session.get(Product, "p-0001").storage is None
    assert len(calls) == offer_match.MOST_ASKS, \
        "a call that keeps failing is not paid for every pass (risk check, PR #207)"
