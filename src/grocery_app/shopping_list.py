"""The shopping list: what a person needs now, and what is running out.

The owner, 2026-10-23: a drafted list of what they need now or will need
soon, big enough that offers add up across it, which the person shortens and
adds to. This module drafts it from the purchase history and nothing else.

A line on the list is an item (Walnüsse, Eier, H-Milch), with the product
they usually take as a hint: what a person writes on a shopping list, the
brand kept in mind (owner, 2026-10-24). The item is the product's `item` word
in purchases.json, given by a model; a product not named yet counts under its
category (Nüsse & Kerne) until it is. On the owner's history 241 of 322
products were bought only once, while 94% of a week's buys were of a kind
bought before: people take a different cheese, the one on offer, but they buy
cheese.

Two numbers per kind, each with one job:

- **chance**: how likely the kind is bought in the coming week, from how often
  it was bought lately. Each buying day counts half as much as one
  `HALF_LIFE_DAYS` newer (owner: "people can change"), over every day the
  person has been shopping. A kind goes on the list when its chance is at
  least `LIST_CHANCE`, so the list's length follows from one number. On the
  owner's history the chance was honest: of kinds given 40-50%, 46% were
  bought (`evaluate_list`).
- **runs_out**: when the last buy is used up, for urgency. A buy lasts until
  the next one, so what was bought on one day was used over the days to the
  next buy; amounts are counted in usual buys (a kind's typical line), so two
  tubs last twice as long as one. Recent gaps count more. The day sorts the
  list: `now` (out, or by tomorrow), `this_week`, `later`.

Ordering by run-out alone did no better than the chance at picking the week's
kinds (backtest, 2026-10-23), which is why the chance decides what is on the
list and the run-out only how urgent it is.

The list knows nothing of the cupboard. It guesses from receipts, and the
person removes what they don't need now and adds what they do. A habit that
stops fades from the list as its chance falls; a missed receipt reads the
same way.

The person's edits (`with_edits`) are kept apart from the draft:

- **A removal is a snooze.** It means only "not now": they still have some,
  or their habit changed, and the app can't tell which (owner, 2026-10-23).
  So the first removal hides the kind for half of what one usual buy lasts
  (eggs every 6 days: 3 days), and each further removal without a buy for
  twice as long as the one before (6, 12, 24): someone who still had some
  loses a few days, and a changed habit is out of sight in a few taps
  (owner, 2026-10-24).
- **An addition** keeps a kind on the list, as needed now, until it is
  bought.
- **A buy ends both.** A receipt with the kind on or after the edit's day
  starts it afresh, and the next removal is a first one again.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from grocery_app import categories
from grocery_app.insights import _product_rows, _quantity

# Bought on this many days or more before a kind is judged: one day is
# something tried, not a habit.
MIN_DAYS = 2
# A buying day this many days older weighs half as much.
HALF_LIFE_DAYS = 28
# On the list from this chance of being bought in the coming week.
LIST_CHANCE = 0.25
WEEK = 7
# Runs out by this many days after the list's day: needed now.
NOW_DAYS = 1
# The usual product is the most frequent among the kind's last few lines.
USUAL_LOOKBACK = 5
# A first removal hides a kind for this share of what one usual buy lasts;
# each further one without a buy, twice as long as the one before.
SNOOZE_SHARE = 0.5
MIN_SNOOZE_DAYS = 1
EDITS = ("add", "remove")


def item_key(p: dict[str, Any]) -> str:
    """Which line of the list a purchase counts for: its item word, any
    case, else its category key."""
    return (p.get("item") or "").casefold() or p["category"]


def _item_name(group: list[dict[str, Any]], key: str) -> str:
    """An item's name as last written, else its category's label."""
    latest = max(group, key=lambda p: p["date"]) if group else {}
    if latest.get("item"):
        return latest["item"]
    path = latest.get("category_path") or []
    if path:
        return path[-1]
    return categories.label(key) if key in categories.CATEGORIES else key


def _weight(age_days: int) -> float:
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def chance(days: list[date], first: date, as_of: date) -> float:
    """The chance of at least one buy in the week from `as_of`: the recent
    buying days over the recent days shopped, as a rate per day."""
    shopped = sum(_weight((as_of - first).days - i) for i in range((as_of - first).days))
    if not shopped:
        return 0.0
    rate = sum(_weight((as_of - d).days) for d in days) / shopped
    return 1 - math.exp(-WEEK * rate)


def _weighted_median(values: list[float], weights: list[float]) -> float:
    pairs = sorted(zip(values, weights, strict=True))
    half = sum(weights) / 2
    seen = 0.0
    for value, weight in pairs:
        seen += weight
        if seen >= half:
            return value
    return pairs[-1][0]


def _day_amounts(group: list[dict[str, Any]]) -> list[tuple[date, float]]:
    """Each buying day of a kind and how much was bought, in usual buys: a
    line's amount over the kind's median line in the same unit (kg, l, piece,
    item), so units never mix."""
    amounts = [(_quantity(p), p) for p in group]
    by_unit: dict[str, list[float]] = defaultdict(list)
    for (amount, unit), _ in amounts:
        by_unit[unit].append(amount)
    usual = {unit: statistics.median(v) for unit, v in by_unit.items()}
    days: dict[date, float] = defaultdict(float)
    for (amount, unit), p in amounts:
        days[date.fromisoformat(p["date"])] += amount / usual[unit] if usual[unit] else 1.0
    return sorted(days.items())


def runs_out(days: list[tuple[date, float]]) -> tuple[date, float]:
    """The day the last buy is used up, and the days one usual buy lasts."""
    lastings = [(b - a).days / amount
                for (a, amount), (b, _) in zip(days, days[1:], strict=False)]
    weights = [_weight((days[-1][0] - b).days) for (b, _) in days[1:]]
    per_buy = _weighted_median(lastings, weights)
    last_day, last_amount = days[-1]
    return last_day + timedelta(days=round(per_buy * last_amount)), per_buy


def _usual_product(group: list[dict[str, Any]]) -> dict[str, Any] | None:
    recent = [p for p in sorted(group, key=lambda p: p["date"]) if p.get("product_id")]
    recent = recent[-USUAL_LOOKBACK:]
    if not recent:
        return None
    counts = Counter(p["product_id"] for p in recent)
    # Most lines first; of two equal, the one bought last.
    last_seen = {p["product_id"]: i for i, p in enumerate(recent)}
    pid = max(counts, key=lambda k: (counts[k], last_seen[k]))
    last = recent[last_seen[pid]]
    return {"product_id": pid, "product": last.get("product") or last.get("raw_name"),
            "brand": last.get("brand")}


def kind(group: list[dict[str, Any]], first: date, as_of: date) -> dict[str, Any] | None:
    """One kind's chance this week and when it runs out, or None when it was
    bought on too few days to judge."""
    days = _day_amounts(group)
    if len(days) < MIN_DAYS:
        return None
    out_day, per_buy = runs_out(days)
    days_left = (out_day - as_of).days
    key = item_key(group[0])
    return {
        "kind": key,
        "name": _item_name(group, key),
        "usual": _usual_product(group),
        "products": len({p["product_id"] for p in group if p.get("product_id")}),
        "days_bought": len(days),
        "last_bought": days[-1][0].isoformat(),
        "chance": round(chance([d for d, _ in days], first, as_of), 2),
        "days_per_buy": round(per_buy, 1),
        "runs_out": out_day.isoformat(),
        "days_left": days_left,
        "when": "now" if days_left <= NOW_DAYS else "this_week" if days_left <= WEEK else "later",
    }


_ORDER = {"now": 0, "this_week": 1, "later": 2}


def kinds(rows: list[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    """Every kind bought on `MIN_DAYS` or more, before `as_of`: a list for a
    past day sees only what was known then. `rows` come from `list_rows`."""
    before = [p for p in rows if p.get("category") and date.fromisoformat(p["date"]) < as_of]
    if not before:
        return []
    first = min(date.fromisoformat(p["date"]) for p in before)
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in before:
        by_kind[item_key(p)].append(p)
    return [line for group in by_kind.values() if (line := kind(group, first, as_of))]


def shopping_list(rows: list[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    """The kinds likely bought in the week from `as_of`, most urgent first."""
    out = [k for k in kinds(rows, as_of) if k["chance"] >= LIST_CHANCE]
    out.sort(key=lambda r: (_ORDER[r["when"]], r["days_left"], r["name"]))
    return out


def snooze_days(days_per_buy: float, times: int) -> int:
    """How long the `times`-th removal since the last buy hides a kind."""
    return max(MIN_SNOOZE_DAYS, round(days_per_buy * SNOOZE_SHARE * 2 ** (times - 1)))


def _added_line(kind_key: str, group: list[dict[str, Any]],
                judged: dict[str, Any] | None) -> dict[str, Any]:
    """An added kind, needed now. One bought on too few days to judge, or
    never, has no chance or run-out: only what it is and the usual product."""
    if judged is not None:
        return {**judged, "when": "now", "added": True}
    return {"kind": kind_key, "name": _item_name(group, kind_key),
            "usual": _usual_product(group),
            "products": len({p["product_id"] for p in group if p.get("product_id")}),
            "days_bought": len({p["date"] for p in group}),
            "last_bought": max(p["date"] for p in group) if group else None,
            "chance": None, "days_per_buy": None, "runs_out": None, "days_left": None,
            "when": "now", "added": True}


def with_edits(rows: list[dict[str, Any]], edits: list[dict[str, Any]],
               today: date) -> dict[str, Any]:
    """Today's list with the person's edits: what they added first, in the
    order added, then the draft without what is snoozed; and what is snoozed,
    until when. `edits` are `{"kind", "edit", "day"}`, oldest first. Today's
    receipts count: the draft is the one for the morning after."""
    as_of = today + timedelta(days=1)
    judged = {k["kind"]: k for k in kinds(rows, as_of)}
    drafted = shopping_list(rows, as_of)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in rows:
        if p.get("category") and date.fromisoformat(p["date"]) < as_of:
            groups[item_key(p)].append(p)
    last = {k: max(date.fromisoformat(p["date"]) for p in g) for k, g in groups.items()}

    since: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in edits:
        if e["edit"] in EDITS and (e["kind"] not in last or e["day"] > last[e["kind"]]):
            since[e["kind"]].append(e)
    added = sorted((k for k, own in since.items() if own[-1]["edit"] == "add"),
                   key=lambda k: since[k][-1]["day"])
    snoozed = []
    for line in drafted:
        own = since.get(line["kind"], [])
        if not own or own[-1]["edit"] != "remove":
            continue
        removals = [e["day"] for e in own if e["edit"] == "remove"]
        until = removals[-1] + timedelta(days=snooze_days(line["days_per_buy"], len(removals)))
        if today < until:
            snoozed.append({"kind": line["kind"], "name": line["name"],
                            "until": until.isoformat(), "times": len(removals)})
    hidden = {s["kind"] for s in snoozed} | set(added)
    return {
        "as_of": today.isoformat(),
        "lines": [_added_line(k, groups.get(k, []), judged.get(k)) for k in added]
                 + [{**line, "added": False} for line in drafted if line["kind"] not in hidden],
        "snoozed": snoozed,
    }


def known(rows: list[dict[str, Any]]) -> set[str]:
    """Every line key these purchases can make: what an edit may name."""
    return {item_key(p) for p in rows if p.get("category")}


def list_rows(purchases: dict[str, Any]) -> list[dict[str, Any]]:
    """The lines a list is drafted from: dated groceries the shopper bought for
    themselves, as for the insights (`insights.build_insights`). Household and
    toiletries stay: toilet paper belongs on a shopping list."""
    return [p for p in _product_rows(purchases.get("purchases", []))
            if p.get("date") and categories.is_grocery(p.get("category"))
            and not p.get("not_counted")]
