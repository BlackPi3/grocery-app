"""Insights over purchases.json: the questions a bank or a store app cannot answer.

Everything here reads the purchases contract and nothing else, so it works on
any purchases.json regardless of how the lines were resolved. Every number
carries its coverage: how many lines and how much money it is based on, and
what was left out. Unresolved lines have money but no identity, so they count
towards spend and never towards a product-level insight.

Prices are what was paid, per unit, after discounts: `unit_price` when the
normalizer could compute one (per kg, per l, per piece), else the paid amount
per item. A personal inflation index has to follow what the person pays.

The four insights promised in CLAUDE.md, in the order they are computed:

1. repurchase cadence and predicted needs,
2. price over time per product (a price watch),
3. a personal basket index (Laspeyres: last month's basket at this month's prices),
4. own-brand vs brand share of spend,

plus the same-item comparison across stores, which is honest about having no
data until a product resolves at two stores.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from grocery_app.resolver import store_key

CONTRACT_VERSION = 1

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


def _paid_unit_price(p: dict[str, Any]) -> tuple[float, str] | None:
    """What was paid per unit, and the unit: (6.08, "kg"), (1.44, "piece"), (0.76, "item")."""
    unit = p.get("unit_price") or {}
    if unit.get("amount"):
        return float(unit["amount"]), unit.get("per") or "item"
    qty = p.get("qty") or 1
    net = p.get("net_paid")
    if net is None or net <= 0:
        return None
    return round(net / qty, 2), "item"


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


# --- 2. price over time ------------------------------------------------------

def _observations(group: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str] | None:
    """One paid unit price per date for a product, or None when the unit differs."""
    by_date: dict[str, list[float]] = defaultdict(list)
    units = set()
    for p in group:
        priced = _paid_unit_price(p)
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
    """Every product seen on at least two dates, with the price it was bought at each time."""
    labels = _store_labels(rows)
    out = []
    for pid, group in _by_product(rows).items():
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
            "per": unit,
            "first": obs[0],
            "last": obs[-1],
            "change_pct": pct,
            "observations": obs,
        })
    out.sort(key=lambda r: -abs(r["change_pct"] or 0))
    return out


# --- 3. personal basket index -----------------------------------------------

def _month_prices(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    """month -> product_id -> {"price": mean paid unit price, "quantity": units bought}.

    Quantity is spend divided by unit price, so it is in the unit the price is
    in: pieces for packs, kilograms for loose goods. That keeps price x quantity
    equal to money for every kind of line.
    """
    acc: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: {"prices": [], "spend": []}))
    for p in rows:
        if not p.get("product_id") or not p.get("date"):
            continue
        priced = _paid_unit_price(p)
        if priced is None:
            continue
        month = p["date"][:7]
        acc[month][p["product_id"]]["prices"].append(priced[0])
        acc[month][p["product_id"]]["spend"].append(p.get("net_paid") or 0.0)
    out: dict[str, dict[str, dict[str, float]]] = {}
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
        overlap = sorted(set(months[prev]) & set(months[cur]))
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
            "product_ids": overlap,
        })
        series.append(entry)
    return {
        "base_month": order[0] if order else None,
        "base": 100.0,
        "series": series,
        "method": "Laspeyres, month over month, chained; quantities from the earlier month; "
                  "prices are paid unit prices after discounts",
    }


# --- 4. own-brand vs brand ---------------------------------------------------

def _split(rows: list[dict[str, Any]]) -> dict[str, float]:
    s = {"own_brand": 0.0, "brand": 0.0, "unknown": 0.0, "unresolved": 0.0}
    for p in rows:
        paid = p.get("net_paid") or 0.0
        if not p.get("product_id"):
            s["unresolved"] += paid
        elif p.get("is_own_brand") is True:
            s["own_brand"] += paid
        elif p.get("is_own_brand") is False:
            s["brand"] += paid
        else:
            s["unknown"] += paid
    known = s["own_brand"] + s["brand"]
    out = {k: round(v, 2) for k, v in s.items()}
    out["own_brand_share_of_known"] = round(s["own_brand"] / known, 3) if known else None
    return out


def own_brand(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Spend split into own-brand, brand, unknown (resolved, status not recorded) and unresolved.

    `unknown_brands` lists the brands behind the unknown money, largest first,
    so the gap can be closed by marking products rather than by guessing here.
    """
    labels = _store_labels(rows)
    by_store: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in rows:
        by_store[_store(p, labels)].append(p)
    unknown: dict[str, float] = defaultdict(float)
    for p in rows:
        if p.get("product_id") and p.get("is_own_brand") is None:
            unknown[p.get("brand") or "(no brand recorded)"] += p.get("net_paid") or 0.0
    return {
        "overall": _split(rows),
        "by_store": {store: _split(group) for store, group in sorted(by_store.items())},
        "unknown_brands": [{"brand": b, "spend": round(v, 2)}
                           for b, v in sorted(unknown.items(), key=lambda kv: -kv[1])],
    }


# --- 5. same item across stores ---------------------------------------------

def cross_store(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Products resolved at more than one store, with the latest paid unit price at each."""
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
            priced = _paid_unit_price(g[-1])
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


# --- coverage and assembly ---------------------------------------------------

def coverage(purchases: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
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
        "spend": round(spend, 2),
        "resolved_spend": round(resolved_spend, 2),
        "resolved_share_of_spend": round(resolved_spend / spend, 3) if spend else None,
        "by_store": dict(sorted(per_store.items())),
        "note": "product-level insights use resolved lines only; spend figures use every line",
    }


def build_insights(purchases: dict[str, Any], as_of: date | None = None) -> dict[str, Any]:
    """The insights contract, from a purchases.json document."""
    rows = _product_rows(purchases.get("purchases", []))
    dates = sorted(p["date"] for p in rows if p.get("date"))
    if as_of is None:
        as_of = _parse(dates[-1]) if dates else date.today()
    return {
        "contract_version": CONTRACT_VERSION,
        "as_of": as_of.isoformat(),
        "coverage": coverage(purchases, rows),
        "repurchase": repurchase(rows, as_of),
        "price_changes": price_changes(rows),
        "basket_index": basket_index(rows),
        "own_brand": own_brand(rows),
        "cross_store": cross_store(rows),
    }


def load_purchases(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
