"""The trip plan: which one shop the next trip goes to.

The owner, 2026-10-26: "the objective here is optimizing cost given the
constraints", and "cost isn't just money. it's money + time + commute", so a
plan that sends the person from shop to shop defeats the purpose. Agreed: a
trip goes to one shop, from the shops on the person's receipts, chosen to
cover the biggest share of the list at the lowest price; a small top-up at a
shop they use is fine. No price is put on time or travel and nothing is asked
about how they travel ("choose safely, observe, adapt"): their receipts say
whether they followed the plan, and the next plan follows that.

- **The base** (`base_shop`) is the shop on most of their receipts: they are
  near there (owner, 2026-10-26), and it is where a top-up happens.
- **A shop's price for a kind** (`price_book`) is what the person paid for it
  there per kg, litre, piece or item: the median of their last `LOOKBACK`
  lines of that kind at that shop, before the plan's day. A kind is a line of
  the list (`shopping_list.item_key`), so the price is that of what they take
  of it there: the shop's own brand at one, a name brand at the other. Paid,
  not shelf: a discount they always get there is money they don't spend.
  Units never mix: a kind bought by the kilo at one shop and by the piece at
  the other has no price to compare.
- **A shop is a candidate** when it prices more than `MIN_COVER` of the list's
  lines (the base always is), as agreed for step 4: "a chain gets a total
  only when most of the list is priced". What it does not price is topped up
  at the base, at the base's price.
- **The cheapest candidate goes**, compared like for like: every candidate's
  total is over the same lines, those every candidate can price (itself or
  by the top-up). An even total goes to the base.

Shops are chains as the receipt prints them (`resolver.store_key`): two
branches of one chain are one shop, which is how chains price.

Where prices come from is the price book's job alone: the lines it is given
(the person's own; anyone's, once the server passes everyone's lines there).
A shop prices only what someone bought there, so a shop the person uses for
a few things prices little of the list and is not a candidate: the safe side.
This week's offers and ALDI SÜD's website prices come in once each is matched
to a kind like for like (step 4 b).
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date
from typing import Any

from grocery_app.insights import _quantity, _store_labels
from grocery_app.resolver import store_key
from grocery_app.shopping_list import item_key, shopping_list

# A kind's price at a shop is the median of its last this many lines there.
LOOKBACK = 5
# A shop is a candidate when it prices more than this share of the list.
MIN_COVER = 0.5

Book = dict[str, dict[str, dict[str, float]]]


def shop(p: dict[str, Any]) -> str:
    return store_key(p.get("store"))


def _before(rows: list[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    return [p for p in rows if p.get("category") and shop(p)
            and date.fromisoformat(p["date"]) < as_of]


def base_shop(rows: list[dict[str, Any]], as_of: date) -> str | None:
    """The shop on most receipts before `as_of`; of two even, the one shopped
    at last."""
    receipts: dict[str, set[tuple[str, str]]] = defaultdict(set)
    last: dict[str, str] = {}
    for p in _before(rows, as_of):
        s = shop(p)
        receipts[s].add((p["date"], p.get("source_image") or ""))
        last[s] = max(last.get(s, ""), p["date"])
    return max(receipts, key=lambda s: (len(receipts[s]), last[s], s), default=None)


def paid_unit_price(p: dict[str, Any]) -> tuple[float, str] | None:
    """What the line cost per unit, after its printed discount: (1.09, "l")."""
    amount, unit = _quantity(p)
    net = p.get("net_paid") or 0.0
    if net <= 0 or not amount:
        return None
    return net / amount, unit


def price_book(rows: list[dict[str, Any]], as_of: date) -> Book:
    """Each shop's price per unit for each kind bought there before `as_of`:
    shop -> kind -> unit -> price."""
    seen: dict[tuple[str, str, str], list[tuple[str, float]]] = defaultdict(list)
    for p in _before(rows, as_of):
        priced = paid_unit_price(p)
        if priced:
            seen[(shop(p), item_key(p), priced[1])].append((p["date"], priced[0]))
    book: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for (s, kind, unit), prices in seen.items():
        recent = [price for _, price in sorted(prices)[-LOOKBACK:]]
        book[s][kind][unit] = round(statistics.median(recent), 2)
    return {s: dict(kinds) for s, kinds in book.items()}


def usual_amounts(rows: list[dict[str, Any]], as_of: date) -> dict[str, tuple[float, str]]:
    """How much one usual buy of each kind is, in its most common unit: the
    median line, at any shop."""
    amounts: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for p in _before(rows, as_of):
        if paid_unit_price(p):
            amounts[item_key(p)].append(_quantity(p))
    out = {}
    for kind, seen in amounts.items():
        unit = Counter(u for _, u in seen).most_common(1)[0][0]
        out[kind] = (statistics.median(a for a, u in seen if u == unit), unit)
    return out


def line_of(p: dict[str, Any]) -> dict[str, Any] | None:
    """A bought line as a line to plan: its kind, how much, in which unit."""
    amount, unit = _quantity(p)
    return {"kind": item_key(p), "amount": amount, "unit": unit} if amount else None


def line_cost(book: Book, s: str | None, line: dict[str, Any]) -> float | None:
    """What `line` costs at shop `s`, or None when `s` has no price for its
    kind in its unit."""
    price = book.get(s or "", {}).get(line["kind"], {}).get(line["unit"])
    return None if price is None else price * line["amount"]


def plan_trip(lines: list[dict[str, Any]], book: Book, base: str | None
              ) -> dict[str, Any] | None:
    """The one shop for a trip that buys `lines` (`{"kind", "amount", "unit"}`),
    and how every shop in `book` did; None with no lines or no base."""
    if not lines or base is None:
        return None
    shops = sorted(set(book) | {base})
    priced = {s: [line_cost(book, s, line) for line in lines] for s in shops}
    at_base = priced[base]

    def cost(s: str, i: int) -> float | None:
        own = priced[s][i]
        return own if own is not None else at_base[i]

    covers = {s: sum(c is not None for c in priced[s]) for s in shops}
    candidates = [s for s in shops if s == base or covers[s] > MIN_COVER * len(lines)]
    common = [i for i in range(len(lines))
              if all(cost(s, i) is not None for s in candidates)]
    totals = {s: round(sum(cost(s, i) for i in common), 2) for s in candidates}
    chosen = min(candidates, key=lambda s: (totals[s], s != base, s))
    return {
        "shop": chosen,
        "base": base,
        "lines": len(lines),
        "compared": len(common),
        "saves": round(totals[base] - totals[chosen], 2),
        "top_up": [] if chosen == base else [
            line["kind"] for line, own, b in zip(lines, priced[chosen], at_base, strict=True)
            if own is None and b is not None],
        "shops": [{"shop": s, "priced": covers[s], "cover": round(covers[s] / len(lines), 2),
                   "candidate": s in candidates, "total": totals.get(s)} for s in shops],
    }


def named(trip: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """A plan with each shop as its receipts spell it most (`ALDI SÜD`)."""
    labels = _store_labels(rows)
    return {**trip, "shop": labels[trip["shop"]], "base": labels[trip["base"]],
            "shops": [{**s, "shop": labels[s["shop"]]} for s in trip["shops"]]}


def next_trip(rows: list[dict[str, Any]], as_of: date) -> dict[str, Any] | None:
    """The plan for a trip on `as_of` that buys the list drafted for that day,
    each line one usual buy; prices and the base from what came before.
    `rows` come from `shopping_list.list_rows`."""
    usual = usual_amounts(rows, as_of)
    lines = [{"kind": k["kind"], "amount": usual[k["kind"]][0], "unit": usual[k["kind"]][1]}
             for k in shopping_list(rows, as_of) if k["kind"] in usual]
    return plan_trip(lines, price_book(rows, as_of), base_shop(rows, as_of))
