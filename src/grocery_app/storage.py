"""Where a product is kept and how long it keeps: what limits buying ahead.

The owner, 2026-10-25: the app plans a person's shopping, and a trip buys
what will be needed before the next one, long-life things further ahead.
Two things stop that: food that goes off, and room, in the fridge above all
("perishables are the real bottleneck; also things that must be in the
fridge, because that depends on the person's fridge size"). So each product
has two facts, each with one job:

- **storage**: where it is kept at home until it is opened: `fridge`,
  `freezer`, or `cupboard` (anything not cooled: a shelf, a cellar, a
  balcony).
- **keeps_days**: how many days it keeps from the day it is bought,
  unopened and kept there.

They belong to the product, not to its category or item (owner,
2026-10-25): tinned Thunfisch and fresh Lachs share a category, frozen
Minipizzen and chilled Pizzateig another. A model gives both, once per
product, from what the product is (name, brand, details, size), never from
anything about the person (`api.offers.storage_due`). A product it gave
nothing usable has neither, and nothing guesses one in its place.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from grocery_app.offer_match import _describe_product, ask

VERSION = "storage-v1"

PLACES = ("fridge", "freezer", "cupboard")
# A tin keeps for years and toilet paper for ever; past ten years the number
# says nothing more, and an answer above it is not a number of days.
MOST_DAYS = 3650

SYSTEM = (
    "For each product a household in Germany buys at the supermarket, say where it is "
    "kept at home until it is opened, and how many days it keeps from the day it is "
    "bought, unopened and kept there. storage: 'fridge' (it must be chilled), 'freezer' "
    "(frozen food), or 'cupboard' (it needs no cooling: a shelf, a cellar, a balcony). "
    "keeps_days: a whole number of days, as the pack's best-before usually allows "
    "(fresh milk about 7, bread 3, tinned food about 700; toilet paper or cleaning "
    "products, which do not go off, 3650). Judge from the product as described. Answer "
    "every product id listed.")

SCHEMA = {"type": "object", "properties": {"products": {"type": "array", "items": {
    "type": "object", "properties": {
        "product": {"type": "string"},
        "storage": {"type": "string", "enum": list(PLACES)},
        "keeps_days": {"type": "integer"}},
    "required": ["product", "storage", "keeps_days"]}}}, "required": ["products"]}


def _days(value: Any) -> int | None:
    """A whole number of days from 1 to `MOST_DAYS`, else None. A bool is
    not a number here, nor is 7.5."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if value != int(value) or not 1 <= value <= MOST_DAYS:
        return None
    return int(value)


def answers(products: dict[str, dict[str, Any]], decider: Any,
            batch: int = 20) -> Iterator[tuple[set[str], dict[str, tuple[str, int]]]]:
    """One model call per `batch` products, each yielding the products it
    asked about and, for those it answered usably, `(storage, keeps_days)`.
    A place not in `PLACES`, a number of days out of range, or a failed call
    is no answer: the product is left without either."""
    ids = sorted(products)
    for start in range(0, len(ids), batch):
        asked = ids[start:start + batch]
        answer = ask(decider, SYSTEM, "\n".join(
            f"Product {pid}: {_describe_product(products[pid])}" for pid in asked), SCHEMA)
        found = answer.get("products") if isinstance(answer, dict) else None
        said: dict[str, tuple[str, int]] = {}
        for a in found if isinstance(found, list) else []:
            if not isinstance(a, dict) or str(a.get("product")) not in asked:
                continue
            days = _days(a.get("keeps_days"))
            if a.get("storage") in PLACES and days is not None:
                said.setdefault(str(a["product"]), (a["storage"], days))
        yield set(asked), said
