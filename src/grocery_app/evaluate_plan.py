"""What the trip plan would have saved: a backtest on a purchase history.

The last `weeks` weeks are cut into trips every `spacing` days, as in
`evaluate_trips`, the newest ending on the last receipt. On each trip's day
the plan knows only what came before: the base, the prices, the drafted
list. What the person bought in the trip's stretch stands for what the trip
had to bring home, and each of those lines is costed twice from the same
price book, like for like:

- **as bought**: at the shop where it was actually bought;
- **as planned**: at the trip's shop, else topped up at the base.

A line counts only where both are priced; the saving is the difference, so a
line bought at the plan's shop saves nothing, whatever it cost that day.

Three ways to pick the trip's shop:

- **base**: always the shop on most receipts, the plan's safe default;
- **plan**: the engine on the list drafted that day (`trip_plan.next_trip`),
  what the app would really have proposed;
- **hindsight**: the engine on what was actually bought, the most a better
  list could add.

Per way: trips sent somewhere other than the base, the share of lines
compared, the saving over the weeks and a week, and **followed**: the share
of lines already bought at the shop it picked, which is how far the plan is
from the person's habit (they never saw it).

Limits: a shop prices only what the person bought there, so the saving is on
what they already buy at more than one shop; a missed receipt reads as a
stretch with less in it; nothing is said about whether the lines would keep
until needed (`evaluate_trips` does that).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from grocery_app.evaluate_trips import stretches
from grocery_app.insights import _store_labels
from grocery_app.trip_plan import (
    base_shop,
    line_cost,
    line_of,
    next_trip,
    paid_unit_price,
    plan_trip,
    price_book,
    shop,
)

WEEKS = 8
SPACING = 7
METHODS = ("base", "plan", "hindsight")


def _share(a: float, b: float) -> float | None:
    return round(a / b, 3) if b else None


def backtest(rows: list[dict[str, Any]], weeks: int = WEEKS,
             spacing: int = SPACING) -> dict[str, Any]:
    """Each way of picking a trip's shop over the last `weeks` weeks of `rows`
    (`shopping_list.list_rows`), with trips every `spacing` days."""
    rows = [p for p in rows if p.get("date") and p.get("category") and shop(p)]
    if not rows:
        return {"weeks": 0, "trips": []}
    end = max(date.fromisoformat(p["date"]) for p in rows)
    totals = {m: {"away": 0, "lines": 0, "compared": 0, "as_bought": 0.0,
                  "as_planned": 0.0, "followed": 0} for m in METHODS}
    labels = _store_labels(rows)
    trips, paid, lines = [], 0.0, 0
    for start, stop in stretches(end, weeks * 7, spacing):
        base = base_shop(rows, start)
        bought = [p for p in rows if start <= date.fromisoformat(p["date"]) <= stop
                  and paid_unit_price(p)]
        if base is None or not bought:
            continue
        book = price_book(rows, start)
        needs = [line_of(p) for p in bought]
        drafted = next_trip(rows, start)
        picked = {"base": base,
                  "plan": drafted["shop"] if drafted else base,
                  "hindsight": plan_trip(needs, book, base)["shop"]}
        paid += sum(p["net_paid"] for p in bought)
        lines += len(bought)
        trip = {"day": start.isoformat(), "base": labels[base], "lines": len(bought),
                **{m: labels[picked[m]] for m in METHODS if m != "base"}}
        for m, s in picked.items():
            t = totals[m]
            t["away"] += s != base
            t["lines"] += len(bought)
            saved = 0.0
            for p, need in zip(bought, needs, strict=True):
                t["followed"] += shop(p) == s
                as_bought = line_cost(book, shop(p), need)
                as_planned = line_cost(book, s, need)
                if as_planned is None:
                    as_planned = line_cost(book, base, need)
                if as_bought is None or as_planned is None:
                    continue
                t["compared"] += 1
                t["as_bought"] += as_bought
                t["as_planned"] += as_planned
                saved += as_bought - as_planned
            trip[f"saved_{m}"] = round(saved, 2)
        trips.append(trip)
    if not trips:
        return {"weeks": 0, "trips": []}
    return {
        "weeks": weeks, "spacing": spacing,
        "from": (end - timedelta(days=weeks * 7 - 1)).isoformat(), "to": end.isoformat(),
        "lines": lines, "paid": round(paid, 2),
        "methods": {m: {"away": t["away"],
                        "compared": _share(t["compared"], t["lines"]),
                        "as_bought": round(t["as_bought"], 2),
                        "as_planned": round(t["as_planned"], 2),
                        "saved": round(t["as_bought"] - t["as_planned"], 2),
                        "saved_a_week": round((t["as_bought"] - t["as_planned"]) / weeks, 2),
                        "saved_share": _share(t["as_bought"] - t["as_planned"], t["as_bought"]),
                        "followed": _share(t["followed"], t["lines"])}
                    for m, t in totals.items()},
        "trips": trips,
    }


def format_report(report: dict[str, Any]) -> str:
    if not report["weeks"]:
        return "No purchases with a shop and a price: nothing to test."

    def pct(x: float | None) -> str:
        return "-" if x is None else f"{x:.0%}"

    out = [f"A trip every {report['spacing']} days, {report['from']} to {report['to']} "
           f"({len(report['trips'])} trips, {report['lines']} lines, "
           f"{report['paid']:.2f} EUR paid)",
           "",
           f"{'shop picked by':16}{'away':>6}{'compared':>10}{'saved':>9}{'a week':>8}"
           f"{'share':>7}{'followed':>10}"]
    for m, r in report["methods"].items():
        out.append(f"{m:16}{r['away']:>6}{pct(r['compared']):>10}{r['saved']:>9.2f}"
                   f"{r['saved_a_week']:>8.2f}{pct(r['saved_share']):>7}"
                   f"{pct(r['followed']):>10}")
    out += ["",
            "away: trips sent to a shop other than the base. compared: lines priced both "
            "where bought and where planned. saved: EUR, as bought minus as planned "
            "(below 0: dearer). followed: lines already bought at the picked shop.",
            "",
            f"{'trip':12}{'base':16}{'plan':16}{'saved':>7}  {'hindsight':16}{'saved':>7}"]
    for t in report["trips"]:
        out.append(f"{t['day']:12}{t['base'][:15]:16}{t['plan'][:15]:16}"
                   f"{t['saved_plan']:>7.2f}  {t['hindsight'][:15]:16}"
                   f"{t['saved_hindsight']:>7.2f}")
    return "\n".join(out)
