"""Insights over purchases.json: the questions a bank or a store app cannot answer.

Everything here reads the purchases contract and nothing else, so it works on
any purchases.json regardless of how the lines were resolved. Every number
carries its coverage: how many lines and how much money it is based on, and
what was left out. Unresolved lines have money but no identity, so they count
towards spend and never towards a product-level insight.

Prices are shelf prices, per unit, before printed discounts (the owner,
2026-10-14: "a price change is the shelf price moving"): an offer, a shop card
or a staff discount printed on the receipt is not the price moving, and what
discounts saved is told on its own. The unit is the one `unit_price` is in
(per kg, per l, per piece), else per item. Spend is what was paid.

The four insights promised in CLAUDE.md, in the order they are computed:

1. repurchase cadence and predicted needs,
2. price over time per product (a price watch),
3. a personal basket index (Laspeyres: last month's basket at this month's prices),
4. budget-brand vs name-brand share of spend,

plus the same-item comparison across stores, which is honest about having no
data until a product resolves at two stores, and the month view (`months`):
what the money went on, by kind of thing, and against the same days of the
month before (`compare_month`), and what printed discounts saved (`discounts`).

Only groceries count. A café breakfast, flowers or a birthday card stays in the
history, but a basket index or a budget-brand share that included them would
answer a question nobody asked. `categories.is_grocery` is the one place that
says what is not a grocery; coverage reports what was left out and how much
money it was, so the exclusion is visible rather than silent.

The month view is the exception: it counts everything the shopper bought,
groceries or not, because its question is "what did I spend it on last month?"
(Parham, 2026-10-09) and a café breakfast is part of that answer. What
discounts saved counts the same lines: a café breakfast's discount was money
saved too.

Only the shopper's own shopping counts towards spend and habits. A line they
marked `not_counted` (a wine bought for a friend) leaves spend, cadence, the
basket and the budget-brand share, and stays in the price watch and the
cross-store comparison: who it was for does not change what the shop charged.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from grocery_app import categories
from grocery_app.resolver import store_key

CONTRACT_VERSION = 10

# A basket index over fewer products than this says more about one item than
# about the basket; it is reported as unavailable with the reason.
MIN_BASKET_PRODUCTS = 3


# --- helpers -----------------------------------------------------------------

def _product_rows(purchases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in purchases if p.get("type") == "product"]


def _by_product(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in rows:
        if p.get("product_id"):
            groups[p["product_id"]].append(p)
    return groups


def _shelf(p: dict[str, Any]) -> float:
    """What the shelf asked for the line, before printed discounts."""
    if p.get("gross") is not None:
        return p["gross"]
    return (p.get("net_paid") or 0.0) - (p.get("discount") or 0.0)


def _quantity(p: dict[str, Any]) -> tuple[float, str]:
    """How much the line bought, in the unit its price is in: (0.65, "kg"),
    (2, "item"). Paid money over paid unit price, so a kilo is a kilo
    whatever the discount was."""
    unit = p.get("unit_price") or {}
    net = p.get("net_paid") or 0.0
    if unit.get("amount") and net > 0:
        return net / unit["amount"], unit.get("per") or "item"
    return p.get("qty") or 1, "item"


def shelf_unit_price(p: dict[str, Any]) -> tuple[float, str] | None:
    """The shelf price per unit, and the unit: (6.08, "kg"), (1.44, "piece"),
    (0.76, "item"). A discount printed on the line does not lower it."""
    shelf = _shelf(p)
    quantity, unit = _quantity(p)
    if shelf <= 0 or not quantity:
        return None
    return round(shelf / quantity, 2), unit


def _form(p: dict[str, Any]) -> str | None:
    """How the line was sold: `loose`, `pack`, or None (`normalizer.sold_as`)."""
    return (p.get("sold_as") or {}).get("form")


def _by_product_and_form(rows: list[dict[str, Any]]
                         ) -> dict[tuple[str, str | None], list[dict[str, Any]]]:
    """Like with like: loose tomatoes are compared with loose tomatoes and the
    650 g pack with packs, so a change of form never reads as inflation
    (Parham, 2026-10-01). The product stays one; only the comparison splits."""
    groups: dict[tuple[str, str | None], list[dict[str, Any]]] = defaultdict(list)
    for p in rows:
        if p.get("product_id"):
            groups[(p["product_id"], _form(p))].append(p)
    return groups


def _name(rows: list[dict[str, Any]]) -> str:
    return rows[-1].get("product") or rows[-1].get("raw_name") or "?"


def _store_labels(rows: list[dict[str, Any]]) -> dict[str, str]:
    """One display name per store, whatever the receipts spelled.

    The truth set has `GLOBUS` and `Globus`, `ALDI SÜD` and `Aldi Süd`. They are
    one store each; the most common spelling is the label, the case-folded
    form the key everything groups on.
    """
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for p in rows:
        store = p.get("store") or ""
        counts[store_key(store)][store] += 1
    return {key: max(spellings.items(), key=lambda kv: (kv[1], kv[0]))[0]
            for key, spellings in counts.items()}


def _store(p: dict[str, Any], labels: dict[str, str]) -> str:
    return labels.get(store_key(p.get("store")), p.get("store") or "")


def _parse(d: str) -> date:
    return date.fromisoformat(d)


# --- 1. repurchase cadence ---------------------------------------------------

def repurchase(rows: list[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    """Products bought on at least two dates: how often, and when next.

    The typical interval is the median gap between trips that included the
    product. `expected_next` adds it to the last purchase; `status` compares
    that with `as_of` (the last receipt date by default, never the wall clock,
    so a history that ends in August is not 'overdue' when read in December).
    """
    labels = _store_labels(rows)
    out = []
    for pid, group in _by_product(rows).items():
        dates = sorted({_parse(p["date"]) for p in group if p.get("date")})
        if len(dates) < 2:
            continue
        gaps = [(b - a).days for a, b in zip(dates, dates[1:], strict=False)]
        typical = int(round(statistics.median(gaps)))
        expected = dates[-1] + timedelta(days=typical)
        out.append({
            "product_id": pid,
            "product": _name(group),
            "brand": group[-1].get("brand"),
            "store": _store(group[-1], labels),
            "trips": len(dates),
            "units": sum(p.get("qty") or 1 for p in group),
            "typical_interval_days": typical,
            # A median of one gap is that gap. Two trips say "bought again",
            # not "every N days"; the reader decides how much to trust it.
            "gaps_observed": len(gaps),
            "last_bought": dates[-1].isoformat(),
            "expected_next": expected.isoformat(),
            "status": "due" if expected <= as_of else "upcoming",
            "days_overdue": max((as_of - expected).days, 0),
        })
    out.sort(key=lambda r: (r["status"] != "due", -r["days_overdue"], r["expected_next"]))
    return out


# Bought on this many days or more is a regular (the owner, 2026-10-14: "7× in
# 6 weeks"); two days say "bought again", not a habit.
REGULAR_TRIPS = 3


def regulars(rows: list[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    """What the shopper buys again and again, for Home's rotating tile: every
    product bought on at least `REGULAR_TRIPS` days, how many, and over how
    long (`days`: from its first purchase to `as_of`, the last receipt, so a
    product that stopped reads over the time since too). Most days first;
    of two equal, the one bought over the shorter time."""
    out = []
    for pid, group in _by_product(rows).items():
        dates = sorted({_parse(p["date"]) for p in group if p.get("date")})
        if len(dates) < REGULAR_TRIPS:
            continue
        out.append({
            "product_id": pid,
            "product": _name(group),
            "brand": group[-1].get("brand"),
            "trips": len(dates),
            "first_bought": dates[0].isoformat(),
            "last_bought": dates[-1].isoformat(),
            "days": (max(as_of, dates[-1]) - dates[0]).days + 1,
        })
    out.sort(key=lambda r: (-r["trips"], r["days"], r["product"]))
    return out


# --- 2. price over time ------------------------------------------------------

def _observations(group: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str] | None:
    """One shelf unit price per date for a product, or None when the unit differs."""
    by_date: dict[str, list[float]] = defaultdict(list)
    units = set()
    for p in group:
        priced = shelf_unit_price(p)
        if priced is None or not p.get("date"):
            continue
        amount, unit = priced
        by_date[p["date"]].append(amount)
        units.add(unit)
    if len(units) != 1 or len(by_date) < 2:
        return None
    obs = [{"date": d, "price": round(statistics.mean(v), 2)} for d, v in sorted(by_date.items())]
    return obs, units.pop()


def price_changes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every product seen on at least two dates in the same form (loose, a pack,
    or unknown) at the same shop, with the price it was bought at each time.

    One shop at a time: loose tomatoes at 0,99 €/kg in one shop and 2,69 €/kg
    in another three months later read as +172% (Parham, 2026-10-12), a
    difference between shops shown as a price going up. Shops are compared
    in `cross_store`."""
    labels = _store_labels(rows)
    by_shop: dict[tuple[str, str | None, str], list[dict[str, Any]]] = defaultdict(list)
    for (pid, form), group in _by_product_and_form(rows).items():
        for p in group:
            by_shop[(pid, form, store_key(p.get("store")))].append(p)
    out = []
    for (pid, form, _), group in by_shop.items():
        found = _observations(group)
        if found is None:
            continue
        obs, unit = found
        first, last = obs[0]["price"], obs[-1]["price"]
        pct = round((last - first) / first * 100, 1) if first else None
        out.append({
            "product_id": pid,
            "product": _name(group),
            "brand": group[-1].get("brand"),
            "store": _store(group[-1], labels),
            "sold_as": form,
            "per": unit,
            "first": obs[0],
            "last": obs[-1],
            "change_pct": pct,
            "observations": obs,
            "move": price_move(obs),
        })
    out.sort(key=lambda r: -abs(r["change_pct"] or 0))
    return out


# Two shelf prices this close are one price: a cent of rounding, or a few
# cents on a weighed item, is not the price moving.
SAME_PRICE = 0.03
# A move smaller than this is not told (the owner, 2026-10-14: "only real
# changes"), nor one on fewer buys than MOVE_BUYS.
MOVE_AT_LEAST = 0.10
MOVE_BUYS = 3


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= SAME_PRICE * max(a, b)


def price_move(obs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """How a product's shelf price moved over its dates, and when (the owner,
    2026-10-14: each move says when and how; no fixed window, the date of
    the change is the window). The dates are read as runs of one price:

    - `stayed`: the price only went one way (in one step or several, `steps`
      dates) and the last price was paid at least twice;
    - `latest`: the same, but the last price is only the last date so far;
    - `offer`: one date off the price before and after, then back (probably an
      offer not printed as a discount: not a change);
    - `keeps_changing`: up and down;
    - None: the price held (within `SAME_PRICE`).

    `before` and `after` are the first and the last price; `since` is the
    first change (for `keeps_changing`, the first date).
    """
    runs: list[list[Any]] = []  # [price, index of its first date, dates]
    for i, o in enumerate(obs):
        if runs and _same(o["price"], runs[-1][0]):
            runs[-1][2] += 1
        else:
            runs.append([o["price"], i, 1])
    if len(runs) < 2:
        return None
    before, after = runs[0][0], runs[-1][0]
    if len(runs) == 3 and runs[1][2] == 1 and _same(before, after):
        return {"kind": "offer", "since": obs[runs[1][1]]["date"], "steps": [],
                "before": before, "after": runs[1][0], "change_pct": None}
    rises = [b[0] > a[0] for a, b in zip(runs, runs[1:], strict=False)]
    if all(rises) or not any(rises):
        kind = "stayed" if runs[-1][2] >= 2 else "latest"
        steps = [obs[run[1]]["date"] for run in runs[1:]]
    else:
        kind, steps = "keeps_changing", []
    pct = round((after - before) / before * 100, 1) if before else None
    return {"kind": kind, "since": steps[0] if steps else obs[0]["date"], "steps": steps,
            "before": before, "after": after, "change_pct": pct}


def price_moves(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The real moves among `price_changes`, for Home's rotating price tile:
    bought at least `MOVE_BUYS` times, a move that is not an offer, at least
    `MOVE_AT_LEAST` either way. Newest move first."""
    out = []
    for change in changes:
        move = change.get("move")
        if (len(change["observations"]) >= MOVE_BUYS and move and move["kind"] != "offer"
                and move["change_pct"] is not None
                and abs(move["change_pct"]) >= MOVE_AT_LEAST * 100):
            out.append({k: change[k] for k in
                        ("product_id", "product", "brand", "store", "sold_as", "per")} | move)
    out.sort(key=lambda m: (m["since"], abs(m["change_pct"])), reverse=True)
    return out


# --- 3. personal basket index -----------------------------------------------

Key = tuple[str, str | None, str]  # product, form, unit of the price


def _month_prices(rows: list[dict[str, Any]]) -> dict[str, dict[Key, dict[str, float]]]:
    """month -> (product, form, unit) -> {"price": mean shelf unit price, "quantity": units}.

    Keyed on the form as well as the product, so the basket compares like
    with like; and on the unit, so a price per kilo is never averaged with a
    price per item.

    Quantity is spend divided by unit price, so it is in the unit the price is
    in: pieces for packs, kilograms for loose goods. That keeps price x quantity
    equal to money for every kind of line.
    """
    acc: dict[str, dict[Key, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: {"prices": [], "spend": []}))
    for p in rows:
        if not p.get("product_id") or not p.get("date"):
            continue
        priced = shelf_unit_price(p)
        if priced is None:
            continue
        month = p["date"][:7]
        key = (p["product_id"], _form(p), priced[1])
        acc[month][key]["prices"].append(priced[0])
        acc[month][key]["spend"].append(_shelf(p))
    out: dict[str, dict[Key, dict[str, float]]] = {}
    for month, products in acc.items():
        out[month] = {}
        for pid, v in products.items():
            price = statistics.mean(v["prices"])
            quantity = sum(v["spend"]) / price if price else 0.0
            out[month][pid] = {"price": price, "quantity": quantity}
    return out


def basket_index(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Personal inflation: the previous month's basket priced at this month's prices.

    A Laspeyres index month over month, over the products bought in both
    months. Base quantities come from the earlier month, so the answer to
    "what would last month's shopping cost at this month's prices" is exactly
    the ratio reported. Months are chained so the series reads from the first.
    """
    months = _month_prices(rows)
    order = sorted(months)
    series: list[dict[str, Any]] = []
    level = 100.0
    for prev, cur in zip(order, order[1:], strict=False):
        overlap = sorted(set(months[prev]) & set(months[cur]),
                         key=lambda k: (k[0], k[1] or "", k[2]))
        entry: dict[str, Any] = {"month": cur, "versus": prev, "products": len(overlap)}
        if len(overlap) < MIN_BASKET_PRODUCTS:
            entry.update({"index": None, "month_over_month_pct": None,
                          "reason": f"only {len(overlap)} products bought in both months "
                                    f"(need {MIN_BASKET_PRODUCTS})"})
            series.append(entry)
            continue
        base_cost = sum(months[prev][pid]["quantity"] * months[prev][pid]["price"]
                        for pid in overlap)
        cur_cost = sum(months[prev][pid]["quantity"] * months[cur][pid]["price"]
                       for pid in overlap)
        ratio = cur_cost / base_cost if base_cost else 1.0
        level = round(level * ratio, 1)
        entry.update({
            "index": level,
            "month_over_month_pct": round((ratio - 1) * 100, 1),
            "basket_cost_at_previous_prices": round(base_cost, 2),
            "basket_cost_at_current_prices": round(cur_cost, 2),
            # What was compared: each product in the form and unit it was
            # priced in both months.
            "compared": [{"product_id": pid, "sold_as": form, "per": per}
                         for pid, form, per in overlap],
        })
        series.append(entry)
    return {
        "base_month": order[0] if order else None,
        "base": 100.0,
        "series": series,
        "method": "Laspeyres, month over month, chained; quantities from the earlier month; "
                  "prices are shelf unit prices, before printed discounts",
    }


# --- 4. budget brand vs name brand -------------------------------------------

def _unbranded(p: dict[str, Any]) -> bool:
    """Whether this line is a thing that has no brand to find, ever.

    Loose produce carries no barcode, no packet and no label, so no lookup, no
    scan and no shopper will ever name a brand for it. Asking whether a cucumber
    is a shop's own label is not an open question but a malformed one, and money
    spent on it does not belong in the same bucket as a label nobody has read
    yet. This reads `category` only at its coarsest level — which section of
    the shop the thing comes from — and never at the leaf.
    """
    return not p.get("brand") and categories.is_produce(p.get("category"))


def _split(rows: list[dict[str, Any]]) -> dict[str, float]:
    s = {"budget": 0.0, "name_brand": 0.0, "unbranded": 0.0, "unknown": 0.0, "unresolved": 0.0}
    for p in rows:
        paid = p.get("net_paid") or 0.0
        if not p.get("product_id"):
            s["unresolved"] += paid
        elif p.get("is_budget_brand") is True:
            s["budget"] += paid
        elif p.get("is_budget_brand") is False:
            s["name_brand"] += paid
        elif _unbranded(p):
            s["unbranded"] += paid
        else:
            s["unknown"] += paid
    known = s["budget"] + s["name_brand"]
    out = {k: round(v, 2) for k, v in s.items()}
    out["budget_share_of_known"] = round(s["budget"] / known, 3) if known else None
    return out


def budget_brand(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Spend split five ways: budget, name_brand, unbranded, unknown, unresolved.

    `unbranded` is money on things with no brand to find (loose produce), which
    is a final answer. `unknown` is a line whose brand exists but is not yet
    sourced — a gap that can be closed. Keeping them apart is what stops the
    insight reporting homework that can never be done.

    `unknown_brands` lists the brands behind the unknown money, largest first,
    so the gap is closed by sourcing a brand rather than by guessing here.
    """
    labels = _store_labels(rows)
    by_store: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in rows:
        by_store[_store(p, labels)].append(p)
    unknown: dict[str, float] = defaultdict(float)
    for p in rows:
        if p.get("product_id") and p.get("is_budget_brand") is None and not _unbranded(p):
            unknown[p.get("brand") or "(no brand recorded)"] += p.get("net_paid") or 0.0
    return {
        "overall": _split(rows),
        "by_store": {store: _split(group) for store, group in sorted(by_store.items())},
        "unknown_brands": [{"brand": b, "spend": round(v, 2)}
                           for b, v in sorted(unknown.items(), key=lambda kv: -kv[1])],
    }


# --- 5. same item across stores ---------------------------------------------

def cross_store(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Products resolved at more than one store, with the latest shelf unit price at each."""
    labels = _store_labels(rows)
    out = []
    for pid, group in _by_product(rows).items():
        stores = defaultdict(list)
        for p in group:
            stores[_store(p, labels)].append(p)
        if len(stores) < 2:
            continue
        latest = {}
        for store, g in stores.items():
            g = sorted(g, key=lambda p: p.get("date") or "")
            priced = shelf_unit_price(g[-1])
            latest[store] = {"date": g[-1].get("date"),
                             "price": priced[0] if priced else None,
                             "per": priced[1] if priced else None}
        out.append({"product_id": pid, "product": _name(group), "stores": latest})
    stores_with_products = {store_key(p.get("store")) for p in rows if p.get("product_id")}
    note = None
    if not out:
        note = (f"no product has resolved at two stores yet; resolved products come from "
                f"{len(stores_with_products)} store(s)")
    return {"products": out, "note": note}


# --- what discounts saved -------------------------------------------------------

def _saved(p: dict[str, Any]) -> float:
    """What a line's printed discount took off (`discount` is negative)."""
    return max(0.0, -(p.get("discount") or 0.0))


def discounts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """What printed discounts saved, per month (newest first) and per shop
    (the owner, 2026-10-14: "tell me how much I saved with the discount").

    Only a discount printed on a product line counts: an offer, a shop card or
    a staff discount. A returned bottle is not a saving and is not a product
    line; an offer that only lowers the shelf price is printed as the price,
    so the receipt cannot say it was one. `share` is the saving against the
    shelf price of everything bought that month, discounted or not.
    """
    labels = _store_labels(rows)
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_store: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in rows:
        if p.get("date"):
            by_month[p["date"][:7]].append(p)
        if _saved(p):
            by_store[_store(p, labels)].append(p)
    out = []
    for month in sorted(by_month, reverse=True):
        lines = by_month[month]
        saved = sum(_saved(p) for p in lines)
        shelf = sum(_shelf(p) for p in lines)
        out.append({"month": month, "saved": round(saved, 2), "shelf": round(shelf, 2),
                    "share": round(saved / shelf, 3) if shelf > 0 else None,
                    "lines": sum(1 for p in lines if _saved(p))})
    stores = [{"store": store, "saved": round(sum(_saved(p) for p in group), 2),
               "lines": len(group)} for store, group in by_store.items()]
    return {"saved": round(sum(_saved(p) for p in rows), 2),
            "lines": sum(1 for p in rows if _saved(p)),
            "months": out,
            "by_store": sorted(stores, key=lambda s: (-s["saved"], s["store"]))}


# --- the month view ------------------------------------------------------------

def _spend(rows: list[dict[str, Any]]) -> float:
    return round(sum(p.get("net_paid") or 0.0 for p in rows), 2)


def _items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per product (or per printed name, for a line nothing placed),
    most money first."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in rows:
        groups[p.get("product_id") or "raw:" + (p.get("raw_name") or "?")].append(p)
    items = [{"product_id": group[0].get("product_id"), "product": _name(group),
              "brand": group[-1].get("brand"), "lines": len(group), "spend": _spend(group)}
             for group in groups.values()]
    return sorted(items, key=lambda item: -item["spend"])


def months(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the money went on, month by month, newest first: spend per branch
    of the category tree (Obst & Gemüse, Getränke, ...) and the products in it.

    `rows` are every product line the shopper counts, groceries or not. A line
    with no category yet is its own group (`branch` null), so the total is all
    the money and nothing is quietly dropped (the page calls it "Not sorted
    yet"). Deposits are not product lines
    and are not in it.
    """
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in rows:
        if p.get("date"):
            by_month[p["date"][:7]].append(p)
    out = []
    for month in sorted(by_month, reverse=True):
        lines = by_month[month]
        by_branch: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for p in lines:
            key = p.get("category")
            by_branch[categories.BRANCHES[categories.branch_of(key)]
                      if key in categories.CATEGORIES else None].append(p)
        branches = [{"branch": branch, "lines": len(group), "spend": _spend(group),
                     "items": _items(group)} for branch, group in by_branch.items()]
        branches.sort(key=lambda b: (b["branch"] is None, -b["spend"]))
        out.append({"month": month,
                    "receipts": len({p.get("source_image") for p in lines}),
                    "lines": len(lines), "spend": _spend(lines), "branches": branches})
    return out


# --- a month against the one before ---------------------------------------------

def _month_end(year: int, month: int) -> date:
    following = date(year + month // 12, month % 12 + 1, 1)
    return following - timedelta(days=1)


def running_totals(rows: list[dict[str, Any]], month: str,
                   through_day: int | None = None) -> list[float]:
    """What had been spent by the end of each day of `month`, from the 1st to
    `through_day` (or the month's last day): the line the month draws."""
    year, number = int(month[:4]), int(month[5:7])
    end = _month_end(year, number)
    days = min(through_day, end.day) if through_day else end.day
    per_day = [0.0] * days
    for p in rows:
        if p.get("date", "")[:7] == month and (day := _parse(p["date"]).day) <= days:
            per_day[day - 1] += p.get("net_paid") or 0.0
    out, total = [], 0.0
    for amount in per_day:
        total += amount
        out.append(round(total, 2))
    return out


# How many months before make "your usual": recent enough to be today's habits.
USUAL_MONTHS = 6


def usual_by_day(rows: list[dict[str, Any]], month: str,
                 through_day: int | None = None) -> dict[str, Any] | None:
    """What the shopper usually spends by this day of a month: the mean of the
    months before `month` (up to `USUAL_MONTHS`), each cut at the same day
    (the 31st is a shorter month's last day), or whole when `through_day` is
    None. The owner, 2026-10-14: "am I going too fast, ok, or saving?"

    `running` is the usual month's line: for every day of `month`, the mean
    of what those months had spent by that day (a shorter month stays at its
    total after its last day).

    A month counts only when the history covers all of it: the month the
    history starts in is partial, and a month without a receipt was not
    tracked, not a month of spending nothing. None with fewer than two such
    months: one month is already "last month".
    """
    dates = sorted(_parse(p["date"]) for p in rows if p.get("date"))
    if not dates:
        return None
    year, number = int(month[:4]), int(month[5:7])
    counted: list[tuple[str, float]] = []
    lines_of: list[list[float]] = []
    start = date(year, number, 1)
    while len(counted) < USUAL_MONTHS:
        end = start - timedelta(days=1)
        start = end.replace(day=1)
        if start < dates[0]:
            break
        cut = end.replace(day=min(through_day, end.day)) if through_day else end
        lines = [p for p in rows if p.get("date") and start <= _parse(p["date"]) <= end]
        if lines:
            counted.append((start.strftime("%Y-%m"),
                            _spend([p for p in lines if _parse(p["date"]) <= cut])))
            lines_of.append(running_totals(lines, start.strftime("%Y-%m")))
    if len(counted) < 2:
        return None
    days = _month_end(year, number).day
    running = [round(statistics.mean(line[min(day, len(line)) - 1] for line in lines_of), 2)
               for day in range(1, days + 1)]
    return {"through_day": through_day, "months": [m for m, _ in counted],
            "spend": round(statistics.mean(v for _, v in counted), 2), "running": running}


# The parts a month's difference is split into, in the order they are told.
COMPARE_PARTS = ("new", "gone", "amounts", "prices", "discounts", "not_placed")


def compare_month(rows: list[dict[str, Any]], month: str,
                  through_day: int | None = None) -> dict[str, Any] | None:
    """`month` (days 1 to `through_day`, or all of it) against the same days
    of the month before, with the difference split so every euro lands in
    one part (the owner, 2026-10-14: like for like, one meaning):

    - `new`: things bought now and not then (all they cost now);
    - `gone`: things bought then and not now (minus all they cost then);
    - `amounts`: the same things, more or less of them, at the old shelf price;
    - `prices`: the same things, the shelf price now against then, on what was
      bought now;
    - `discounts`: the same things, printed discounts now against then
      (negative when they saved more);
    - `not_placed`: lines nothing placed on a product, now against then.

    A "same thing" is one product at one shop, sold the same way and priced in
    the same unit: the milk bought at another shop this month is a new thing,
    not a price change (the rule `price_changes` keeps). Prices are shelf
    prices, before printed discounts: a discount is not the price moving.

    None when the month before has no receipt in those days: against nothing
    tracked, a difference means nothing. A history that starts within those
    days is compared as it is.
    """
    year, number = int(month[:4]), int(month[5:7])
    end = _month_end(year, number)
    day = min(through_day, end.day) if through_day else end.day
    before = date(year, number, 1) - timedelta(days=1)
    then_end = before.replace(day=min(day, before.day)) if through_day else before
    now_from, now_end = date(year, number, 1), end.replace(day=day)
    then_from = before.replace(day=1)
    now = [p for p in rows if p.get("date") and now_from <= _parse(p["date"]) <= now_end]
    then = [p for p in rows if p.get("date") and then_from <= _parse(p["date"]) <= then_end]
    if not then:
        return None

    def things(lines: list[dict[str, Any]]) -> dict[tuple, list[dict[str, Any]]]:
        groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
        for p in lines:
            if p.get("product_id"):
                groups[(p["product_id"], _form(p), _quantity(p)[1],
                        store_key(p.get("store")))].append(p)
        return groups

    now_things, then_things = things(now), things(then)
    parts = dict.fromkeys(COMPARE_PARTS, 0.0)
    parts["not_placed"] = (_spend([p for p in now if not p.get("product_id")])
                           - _spend([p for p in then if not p.get("product_id")]))
    for key, lines in now_things.items():
        if key not in then_things:
            parts["new"] += _spend(lines)
    for key, lines in then_things.items():
        if key not in now_things:
            parts["gone"] -= _spend(lines)
            continue
        current = now_things[key]
        q_then = sum(_quantity(p)[0] for p in lines)
        q_now = sum(_quantity(p)[0] for p in current)
        shelf_then = sum(_shelf(p) for p in lines)
        shelf_now = sum(_shelf(p) for p in current)
        price_then = shelf_then / q_then if q_then else 0.0
        price_now = shelf_now / q_now if q_now else 0.0
        parts["prices"] += (price_now - price_then) * q_now
        parts["discounts"] += (sum(p.get("discount") or 0.0 for p in current)
                               - sum(p.get("discount") or 0.0 for p in lines))
    spend, versus_spend = _spend(now), _spend(then)
    difference = round(spend - versus_spend, 2)
    parts = {k: round(v, 2) for k, v in parts.items()}
    # What is left is the amounts, (q_now - q_then) x price_then for every
    # thing bought in both, so the parts add up to the difference to the cent.
    parts["amounts"] = round(difference - sum(v for k, v in parts.items() if k != "amounts"), 2)
    return {"through_day": day if through_day else None,
            "versus": before.strftime("%Y-%m"), "spend": spend,
            "versus_spend": versus_spend, "difference": difference, "parts": parts}


# --- coverage and assembly ---------------------------------------------------

def _not_grocery(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, float] = defaultdict(float)
    for p in rows:
        by_category[categories.label(p["category"])] += p.get("net_paid") or 0.0
    return {"lines": len(rows),
            "spend": round(sum(by_category.values(), 0.0), 2),
            "by_category": {c: round(v, 2) for c, v in
                            sorted(by_category.items(), key=lambda kv: -kv[1])}}


def coverage(purchases: dict[str, Any], rows: list[dict[str, Any]],
             left_out: list[dict[str, Any]],
             not_counted: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """What the insights rest on. `rows` are the grocery lines the shopper
    counts; `left_out` the lines known not to be groceries, and `not_counted`
    the grocery lines the shopper left out, each reported here and nowhere
    else."""
    not_counted = not_counted or []
    resolved = [p for p in rows if p.get("product_id")]
    spend = sum(p.get("net_paid") or 0.0 for p in rows)
    resolved_spend = sum(p.get("net_paid") or 0.0 for p in resolved)
    labels = _store_labels(rows)
    per_store: dict[str, dict[str, int]] = defaultdict(lambda: {"lines": 0, "resolved": 0})
    for p in rows:
        s = per_store[_store(p, labels)]
        s["lines"] += 1
        s["resolved"] += 1 if p.get("product_id") else 0
    meta = purchases.get("meta", {})
    return {
        "receipts": meta.get("receipts"),
        "date_range": meta.get("date_range"),
        "product_lines": len(rows),
        "resolved_lines": len(resolved),
        # How many different products the product-level insights could speak
        # about: "bought again" is read against it ("12 of 30 products").
        "products": len({p["product_id"] for p in resolved}),
        "spend": round(spend, 2),
        "resolved_spend": round(resolved_spend, 2),
        "resolved_share_of_spend": round(resolved_spend / spend, 3) if spend else None,
        "by_store": dict(sorted(per_store.items())),
        "not_grocery": _not_grocery(left_out),
        "not_counted": {"lines": len(not_counted),
                        "spend": round(sum(p.get("net_paid") or 0.0 for p in not_counted), 2)},
        "note": "groceries only: lines known not to be groceries are counted under "
                "not_grocery and left out of every insight; lines the shopper left out "
                "are counted under not_counted and kept only for prices; product-level "
                "insights use resolved lines only; spend figures use every counted "
                "grocery line",
    }


def build_insights(purchases: dict[str, Any], as_of: date | None = None,
                   today: date | None = None) -> dict[str, Any]:
    """The insights contract, from a purchases.json document.

    `today` (default: the server's date) is where this month stops: on the
    14th, a month's `compared` sets 1-14 of it against 1-14 of the month
    before. Every other month is compared whole."""
    lines = _product_rows(purchases.get("purchases", []))
    groceries = [p for p in lines if categories.is_grocery(p.get("category"))]
    left_out = [p for p in lines if not categories.is_grocery(p.get("category"))]
    # Prices are what the shop charged, whoever it was for; the rest is the
    # shopper's own shopping.
    rows = [p for p in groceries if not p.get("not_counted")]
    not_counted = [p for p in groceries if p.get("not_counted")]
    counted = [p for p in lines if not p.get("not_counted")]
    dates = sorted(p["date"] for p in lines if p.get("date"))
    if as_of is None:
        as_of = _parse(dates[-1]) if dates else date.today()
    return {
        "contract_version": CONTRACT_VERSION,
        "as_of": as_of.isoformat(),
        "coverage": coverage(purchases, rows, left_out, not_counted),
        "repurchase": repurchase(rows, as_of),
        "regulars": regulars(rows, as_of),
        "price_changes": (changes := price_changes(groceries)),
        "price_moves": price_moves(changes),
        "basket_index": basket_index(rows),
        "budget_brand": budget_brand(rows),
        "cross_store": cross_store(groceries),
        "months": _compared(months(counted), counted, today or date.today()),
        "discounts": discounts(counted),
    }


def _compared(out: list[dict[str, Any]], rows: list[dict[str, Any]],
              today: date) -> list[dict[str, Any]]:
    this_month = today.strftime("%Y-%m")
    for entry in out:
        day = today.day if entry["month"] == this_month else None
        entry["compared"] = compare_month(rows, entry["month"], day)
        entry["usual"] = usual_by_day(rows, entry["month"], day)
        # The lines a month's chart draws: this month to today, the month
        # before whole (when there is a comparison at all); the usual month's
        # is `usual.running`.
        entry["running"] = {
            "this": running_totals(rows, entry["month"], day),
            "before": running_totals(rows, entry["compared"]["versus"])
            if entry["compared"] else None}
    return out


def load_purchases(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
