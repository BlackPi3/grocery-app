"""How well the shopping list foresees what a person buys.

A backtest on a purchase history: on each of the last `weeks` weeks, the list
is drafted from what was bought before that day only, then set against the
kinds actually bought in the seven days from it.

- **bought**: of the kinds on the list, the share bought that week. Low means
  a list full of things they don't need.
- **caught**: of the kinds bought that week, the share the list had. Low means
  a list that misses most of the shopping.
- **chance, checked**: kinds grouped by the chance the list gave them, and the
  share of each group actually bought. An honest chance has about 30% bought
  among kinds given 30%.
- **urgency, checked**: kinds grouped by `when`, and the share bought within
  `NOW_CHECK_DAYS` days. `now` should be bought sooner than `later`.

The baseline is the rule the list replaces, applied to kinds: due when the
median gap between buying days has passed since the last buy
(`insights.repurchase`), stopped when three gaps and a week overdue.

A missed receipt looks like a week the person bought nothing, so these numbers
are a floor for a history with gaps in it.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from grocery_app.shopping_list import LIST_CHANCE, MIN_DAYS, WEEK, kinds

NOW_CHECK_DAYS = 3
# Other cut-offs, to show what a longer or shorter list would cost.
CHANCES = (0.15, 0.2, 0.25, 0.3, 0.4)


def gap_rule(rows: list[dict[str, Any]], as_of: date) -> set[str]:
    """The baseline: kinds whose median gap ends within the week."""
    days: dict[str, set[date]] = defaultdict(set)
    for p in rows:
        d = date.fromisoformat(p["date"])
        if p.get("category") and d < as_of:
            days[p["category"]].add(d)
    due = set()
    for k, ds in days.items():
        ds = sorted(ds)
        if len(ds) < max(MIN_DAYS, 3):
            continue
        gap = statistics.median((b - a).days for a, b in zip(ds, ds[1:], strict=False))
        if (as_of - ds[-1]).days > 3 * gap + WEEK:
            continue
        if ds[-1] + timedelta(days=gap) < as_of + timedelta(days=WEEK):
            due.add(k)
    return due


def _bought(rows: list[dict[str, Any]], start: date, days: int) -> set[str]:
    end = start + timedelta(days=days)
    return {p["category"] for p in rows
            if p.get("category") and start <= date.fromisoformat(p["date"]) < end}


_WHEN = ("now", "this_week", "later")


def _share(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def backtest(rows: list[dict[str, Any]], weeks: int = 8) -> dict[str, Any]:
    dated = [date.fromisoformat(p["date"]) for p in rows if p.get("category")]
    if not dated:
        return {"weeks": 0}
    # The last week ends on the last day with a receipt.
    start = max(dated) - timedelta(days=WEEK * weeks - 1)
    methods = {f"chance >= {c:.0%}": [0, 0] for c in CHANCES}
    methods["gap rule"] = [0, 0]
    calibration = defaultdict(lambda: [0, 0])
    urgency = defaultdict(lambda: [0, 0])
    bought_total = 0
    for w in range(weeks):
        day = start + timedelta(days=WEEK * w)
        bought = _bought(rows, day, WEEK)
        soon = _bought(rows, day, NOW_CHECK_DAYS)
        bought_total += len(bought)
        drafted = kinds(rows, day)
        for c in CHANCES:
            listed = {k["kind"] for k in drafted if k["chance"] >= c}
            methods[f"chance >= {c:.0%}"][0] += len(listed)
            methods[f"chance >= {c:.0%}"][1] += len(listed & bought)
        due = gap_rule(rows, day)
        methods["gap rule"][0] += len(due)
        methods["gap rule"][1] += len(due & bought)
        for k in drafted:
            group = calibration[min(int(k["chance"] * 10), 9)]
            group[0] += 1
            group[1] += k["kind"] in bought
            if k["chance"] >= LIST_CHANCE:
                urgency[k["when"]][0] += 1
                urgency[k["when"]][1] += k["kind"] in soon
    return {
        "weeks": weeks,
        "from": start.isoformat(),
        "list_chance": LIST_CHANCE,
        "kinds_bought_per_week": round(bought_total / weeks, 1),
        "methods": {m: {"per_week": round(listed / weeks, 1),
                        "bought": _share(hit, listed),
                        "caught": _share(hit, bought_total)}
                    for m, (listed, hit) in methods.items()},
        "calibration": [{"chance": f"{g / 10:.1f}-{(g + 1) / 10:.1f}", "kinds": n,
                         "bought": _share(hit, n)}
                        for g, (n, hit) in sorted(calibration.items())],
        "urgency": {w: {"kinds": n, "bought_within_days": NOW_CHECK_DAYS,
                        "bought": _share(hit, n)}
                    for w, (n, hit) in sorted(urgency.items(), key=lambda x: _WHEN.index(x[0]))},
    }


def format_report(result: dict[str, Any]) -> str:
    if not result.get("weeks"):
        return "No dated lines with a kind: nothing to test."

    def pct(x: float | None) -> str:
        return "-" if x is None else f"{x:.0%}"

    out = [f"{result['weeks']} weeks from {result['from']}; "
           f"{result['kinds_bought_per_week']} kinds bought a week; "
           f"the list is chance >= {result['list_chance']:.0%}",
           "",
           f"{'method':14} {'on list':>8} {'bought':>7} {'caught':>7}"]
    for m, r in result["methods"].items():
        out.append(f"{m:14} {r['per_week']:>8} {pct(r['bought']):>7} {pct(r['caught']):>7}")
    out += ["", f"{'chance given':14} {'kinds':>8} {'bought':>7}"]
    for r in result["calibration"]:
        out.append(f"{r['chance']:14} {r['kinds']:>8} {pct(r['bought']):>7}")
    soon = f"bought in {NOW_CHECK_DAYS} days"
    out += ["", f"{'on the list':14} {'kinds':>8} {soon:>18}"]
    for w, r in result["urgency"].items():
        out.append(f"{w:14} {r['kinds']:>8} {pct(r['bought']):>18}")
    return "\n".join(out)
