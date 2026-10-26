"""How far apart trips could be: what a person's own buying says.

The owner, 2026-10-26: plan the shopping so that one trip a week or every two
weeks, to the shop that saves the most, covers what is needed, instead of a
trip every other day. Which spacing works "depends on my needs. we need to
see what we can come up with". This reads it from the receipts, before any
plan is built.

For each spacing (`SPACINGS`), the last `weeks` weeks are cut into stretches
of that many days, the newest ending on the last receipt, each covered by one
trip on its first day. What the person bought in a stretch stands for what
that trip would have to bring home: what was bought is the best record there
is of what was needed. It measures the needs, not the habit of shopping
every other day.

Per spacing:

- **trips a month**, beside the shopping days a month they actually had;
- **lines a trip**: the median and the most;
- **won't keep**: lines whose product keeps fewer days (`keeps_days`, from
  the day bought, unopened; `grocery_app.storage`) than the days from the
  trip to the day it was actually bought: bread for Saturday bought on
  Monday. Split by where it is kept. A line with no `keeps_days` is counted
  apart, as not known;
- **fridge and freezer**: the most lines kept there that one trip brings
  home, beside the most the person ever brought home in one day (their
  fridge has held at least that much).

Limits: lines are counted, not volume (a tub and a cucumber are one each); a
product's `keeps_days` is a model's answer, for the unopened pack; a missed
receipt reads as a stretch with less in it.
"""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import date, timedelta
from typing import Any

SPACINGS = (3, 7, 10, 14)
WEEKS = 8
MONTH = 30


def _day(p: dict[str, Any]) -> date:
    return date.fromisoformat(p["date"])


def stretches(end: date, days: int, spacing: int) -> list[tuple[date, date]]:
    """Every whole stretch of `spacing` days in the `days` days up to `end`,
    oldest first, the newest ending on `end`."""
    return [(end - timedelta(days=spacing * (i + 1) - 1), end - timedelta(days=spacing * i))
            for i in reversed(range(days // spacing))]


def most_in_a_day(rows: list[dict[str, Any]], storage: str) -> int:
    """The most lines kept in `storage` the person brought home on one day."""
    per_day = Counter(p["date"] for p in rows if p.get("storage") == storage)
    return max(per_day.values(), default=0)


def spacing_report(rows: list[dict[str, Any]], end: date, days: int,
                   spacing: int) -> dict[str, Any]:
    """What trips every `spacing` days would have had to cover (see above)."""
    trips = stretches(end, days, spacing)
    lines, fridge, freezer = [], [], []
    wont_keep: Counter[str] = Counter()
    unknown = counted = 0
    for start, stop in trips:
        brought = [p for p in rows if start <= _day(p) <= stop]
        lines.append(len(brought))
        fridge.append(sum(p.get("storage") == "fridge" for p in brought))
        freezer.append(sum(p.get("storage") == "freezer" for p in brought))
        for p in brought:
            counted += 1
            keeps = p.get("keeps_days")
            if keeps is None:
                unknown += 1
            elif keeps < (_day(p) - start).days:
                wont_keep[p.get("storage") or "unknown"] += 1
    return {
        "spacing": spacing,
        "trips": len(trips),
        "trips_a_month": round(MONTH / spacing, 1),
        "lines_a_trip": statistics.median(lines) if lines else 0,
        "most_lines": max(lines, default=0),
        "wont_keep": round(sum(wont_keep.values()) / counted, 3) if counted else 0.0,
        "wont_keep_by_storage": dict(sorted(wont_keep.items())),
        "keeps_unknown": round(unknown / counted, 3) if counted else 0.0,
        "most_fridge": max(fridge, default=0),
        "most_freezer": max(freezer, default=0),
    }


def backtest(rows: list[dict[str, Any]], weeks: int = WEEKS,
             spacings: tuple[int, ...] = SPACINGS) -> dict[str, Any]:
    """Each spacing over the last `weeks` weeks of `rows` (`shopping_list.list_rows`)."""
    rows = [p for p in rows if p.get("date")]
    if not rows:
        return {"weeks": 0, "spacings": []}
    end = max(_day(p) for p in rows)
    days = weeks * 7
    start = end - timedelta(days=days - 1)
    shopped = {p["date"] for p in rows if _day(p) >= start}
    return {
        "weeks": weeks, "from": start.isoformat(), "to": end.isoformat(),
        "shopping_days_a_month": round(len(shopped) * MONTH / days, 1),
        "fridge_room": most_in_a_day(rows, "fridge"),
        "freezer_room": most_in_a_day(rows, "freezer"),
        "spacings": [spacing_report(rows, end, days, s) for s in spacings],
    }


def format_report(report: dict[str, Any]) -> str:
    if not report["weeks"] or not report["spacings"]:
        return "No purchases: nothing to test."
    out = [f"Trips every N days, {report['from']} to {report['to']} ({report['weeks']} weeks)",
           f"You shopped on {report['shopping_days_a_month']} days a month. Most brought "
           f"home in one day: {report['fridge_room']} fridge lines, "
           f"{report['freezer_room']} freezer lines.",
           "",
           f"{'every':>6}{'trips/mo':>10}{'lines/trip':>12}{'most':>6}{'no keep':>12}"
           f"{'not known':>11}{'fridge':>8}{'freezer':>9}"]
    for s in report["spacings"]:
        out.append(f"{s['spacing']:>4} d{s['trips_a_month']:>10}{s['lines_a_trip']:>12g}"
                   f"{s['most_lines']:>6}{s['wont_keep']:>12.0%}{s['keeps_unknown']:>11.0%}"
                   f"{s['most_fridge']:>8}{s['most_freezer']:>9}")
    out += ["", "no keep: bought at the trip, it would be past its days before the day "
                "it was actually bought. fridge, freezer: the most lines one trip brings home."]
    for s in report["spacings"]:
        if s["wont_keep_by_storage"]:
            parts = ", ".join(f"{k} {v}" for k, v in s["wont_keep_by_storage"].items())
            out.append(f"  every {s['spacing']} d, won't keep by where kept: {parts}")
    return "\n".join(out)
