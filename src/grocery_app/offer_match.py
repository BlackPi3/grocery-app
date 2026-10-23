"""Which of the week's offers are for something a person buys, and what it saves.

The owner, 2026-10-23, step 1 of the offers: single offers for what a person
buys regularly, for the coming week. The offers come from `grocery_app.offers`.
This module decides, for one regular product and the offers its name found,
which are that product and what each would save.

**A search word is not a match.** `Milch` finds milk, and also cheese, milk
chocolate and Milch-Schnitte. A model reads the product and the offers and
gives each offer one verdict (`judge`):

- `same_product`: that product, by that brand (any size). Labelled "your product".
- `same_kind`: the same kind of thing from another brand, which the shopper
  could buy instead: Magerquark for Magerquark, not Sahnequark, not a quark
  dessert. Labelled "like yours", and only at a pack size within a factor of
  two of theirs, when both sizes are known (`similar_size`).
- `no`: anything else.

Which labels the Home tile shows is the owner's call (2026-10-23: the exact
product only, or the same kind too); both are worked out here and labelled.

**A saving is only claimed like for like:** the offer's price per kg, litre
or piece against what the person usually paid per the same unit (`usual_unit_price`:
the median of their last five shelf prices, before discounts). An offer dearer
than that is no offer for them and is dropped; one with nothing to compare
against is kept with no saving, and says so.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Iterator
from typing import Any

from grocery_app.insights import shelf_unit_price

VERDICTS = ("same_product", "same_kind", "no")
LABELS = {"same_product": "your product", "same_kind": "like yours"}
JUDGE_VERSION = "offers-v1"
# Offers judged per product for one coming week: a search can find hundreds,
# and past the best-named forty they are cheese for milk. Shown no more, the
# rest are never matched; that is the price of a cent a week.
MOST_CANDIDATES = 40
# A pair the judge was asked about this many times without an answer is not
# asked again until the server starts anew.
MOST_ASKS = 2

JUDGE_SYSTEM = (
    "You compare a shopper's grocery products with offers from supermarket flyers. "
    "For each product, give every offer listed under it one verdict:\n"
    "- same_product: the same product by the same brand (any pack size).\n"
    "- same_kind: the same kind of product from another brand, which the shopper could "
    "buy instead without noticing a different thing: same type, same form, same main "
    "variety (Magerquark for Magerquark; Vollmilch for Vollmilch). Not a flavoured, "
    "sweetened, processed, plant-based or diet version unless the product is one, not a "
    "product that only shares a word (Milchschokolade is not milk), not a multipack of "
    "something else.\n"
    "- no: anything else, and whenever unsure.\n"
    "Judge only from the words given. Answer every offer id listed.")

JUDGE_SCHEMA = {"type": "object", "properties": {"verdicts": {"type": "array", "items": {
    "type": "object", "properties": {
        "product": {"type": "string"}, "offer": {"type": "string"},
        "verdict": {"type": "string", "enum": list(VERDICTS)}},
    "required": ["product", "offer", "verdict"]}}}, "required": ["verdicts"]}


def _describe_product(product: dict[str, Any]) -> str:
    parts = [product.get("name") or "?"]
    if product.get("brand"):
        parts.append(f"brand {product['brand']}")
    if product.get("details"):
        parts.append(", ".join(product["details"]))
    size = product.get("size") or {}
    if size.get("value") and size.get("unit"):
        parts.append(f"{size['value']:g} {size['unit']}")
    return " | ".join(parts)


def _describe_offer(offer: dict[str, Any]) -> str:
    parts = [offer.get("product") or "?"]
    if offer.get("brand"):
        parts.append(f"brand {offer['brand']}")
    if offer.get("description"):
        parts.append(offer["description"])
    if offer.get("category"):
        parts.append(f"flyer section {offer['category']}")
    return " | ".join(parts)


def judge_batches(products: dict[str, dict[str, Any]],
                  candidates: dict[str, list[dict[str, Any]]], decider: Any,
                  batch: int = 8) -> Iterator[tuple[set, dict[tuple[str, str], str]]]:
    """One model call per `batch` products, each yielding the (product id,
    offer id) pairs it asked about and the verdicts for those it answered, so
    a caller can keep each batch before the next is asked. Only what the model said:
    a pair it left out, named wrongly or gave a verdict it may not stays
    unjudged, to be asked again, never a `no` it did not give. (A cut-off
    answer would otherwise turn a whole week's offers into `no`.)"""
    ids = sorted(pid for pid in candidates if candidates[pid] and pid in products)
    for start in range(0, len(ids), batch):
        lines, asked = [], set()
        for pid in ids[start:start + batch]:
            lines.append(f"Product {pid}: {_describe_product(products[pid])}")
            for o in candidates[pid]:
                lines.append(f"  - offer {o['id']}: {_describe_offer(o)}")
                asked.add((pid, o["id"]))
        answer = decider(JUDGE_SYSTEM, "\n".join(lines), JUDGE_SCHEMA)
        verdicts = answer.get("verdicts") if isinstance(answer, dict) else None
        said: dict[tuple[str, str], str] = {}
        for v in verdicts if isinstance(verdicts, list) else []:
            if not isinstance(v, dict):
                continue
            pair = (str(v.get("product")), str(v.get("offer")))
            if pair in asked and v.get("verdict") in VERDICTS:
                said.setdefault(pair, v["verdict"])
        yield asked, said


def judge(products: dict[str, dict[str, Any]], candidates: dict[str, list[dict[str, Any]]],
          decider: Any, batch: int = 8) -> dict[tuple[str, str], str]:
    """Every batch of `judge_batches` in one dict."""
    out: dict[tuple[str, str], str] = {}
    for _, said in judge_batches(products, candidates, decider, batch):
        out |= said
    return out


def shortlist(word: str, offers: list[dict[str, Any]],
              most: int = MOST_CANDIDATES) -> list[dict[str, Any]]:
    """The offers worth showing the judge for `word`, at most `most`: those
    whose product name has the word as a word of its own first (`H-Milch`,
    not `Milchschokolade`). Only the prompt's length is decided here; the
    judge decides what matches."""
    whole = re.compile(rf"(?<!\w){re.escape(word)}(?!\w)", re.IGNORECASE)
    ranked = sorted(offers, key=lambda o: (not whole.search(o.get("product") or ""),
                                           o.get("price") or 0.0, o["id"]))
    return ranked[:most]


# --- what it saves --------------------------------------------------------------------

# The offers source's units, and the receipt's, onto one name each. A
# receipt's `item` (a line with no known size) is not a piece: a box of six
# eggs is one item and six pieces, so it compares with nothing.
_UNIT = {"kg": "kg", "l": "l", "stk": "piece", "piece": "piece"}
_BASE = {"g": ("kg", 0.001), "kg": ("kg", 1.0), "ml": ("l", 0.001), "l": ("l", 1.0),
         "piece": ("piece", 1.0), "stk": ("piece", 1.0)}


def _unit(name: str | None) -> str | None:
    return _UNIT.get((name or "").casefold())


def usual_unit_price(rows: list[dict[str, Any]], last: int = 5) -> dict[str, Any] | None:
    """What the person usually paid for a product per unit: the median shelf
    price per unit of their last `last` purchases in the newest purchase's unit."""
    prices = [(r["date"], *found) for r in rows if (found := shelf_unit_price(r))]
    if not prices:
        return None
    prices.sort()
    unit = prices[-1][2]
    same = [amount for _, amount, u in prices if u == unit][-last:]
    return {"amount": round(statistics.median(same), 2), "per": _unit(unit) or unit}


def _amount(value: float | None, unit: str | None, count: float | None = 1) -> tuple | None:
    base = _BASE.get((unit or "").casefold())
    if not value or not base:
        return None
    return value * base[1] * (count or 1), base[0]


def similar_size(size: dict[str, Any] | None, pack: dict[str, Any] | None) -> bool:
    """Is the offer's pack within a factor of two of the product's size? True
    when either is unknown or they are in different units: then the price per
    unit is the comparison."""
    size, pack = size or {}, pack or {}
    mine = _amount(size.get("value"), size.get("unit"), size.get("count"))
    theirs = _amount(pack.get("amount"), pack.get("unit"), pack.get("count"))
    if not mine or not theirs or mine[1] != theirs[1]:
        return True
    return 0.5 <= theirs[0] / mine[0] <= 2.0


def _offer_per_unit(offer: dict[str, Any]) -> dict[str, Any]:
    """The offer's price per unit, or its price over its pack when it has none."""
    if (offer.get("per_unit") or {}).get("amount"):
        return offer["per_unit"]
    pack = offer.get("pack") or {}
    if pack.get("amount") and pack.get("unit") and offer.get("price"):
        return {"amount": offer["price"] / (pack["amount"] * (pack.get("count") or 1)),
                "per": pack["unit"]}
    return {}


def match(product: dict[str, Any], rows: list[dict[str, Any]], offer: dict[str, Any],
          verdict: str) -> dict[str, Any] | None:
    """The offer as one for this person, or None when it is not one: not the
    product or its kind, another kind's pack size far from theirs, or no
    cheaper than what they usually pay."""
    if verdict not in LABELS:
        return None
    if verdict == "same_kind" and not similar_size(product.get("size"), offer.get("pack")):
        return None
    usual = usual_unit_price(rows)
    per_unit = _offer_per_unit(offer)
    comparable = (usual is not None and per_unit.get("amount")
                  and _unit(per_unit.get("per")) == usual["per"])
    saving = None
    if comparable:
        less = round(usual["amount"] - per_unit["amount"], 2)
        if less <= 0:  # dearer, the same, or under a cent less: no saving
            return None
        saving = {"per_unit": less, "share": round(less / usual["amount"], 2)}
    return {"label": LABELS[verdict], "offer": offer,
            "usual_per_unit": usual if comparable else None, "saving": saving}
