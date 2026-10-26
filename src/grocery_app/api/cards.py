"""Which cards a question shows, in what order (Parham, 2026-10-12).

A question is asked with yes/no cards, one product at a time, never with a
blank to type in. The order is his rule of 2026-10-04: the product that
costs what was paid comes first. Then the model's pick, then what a web
search narrowed the line to, then the rest by how near their price is.

At most `MOST_CARDS`: a No on every card leaves the line not placed, and a
long run of Noes is the shopper's time spent on products the app was never
close to.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

MOST_CARDS = 5
# A receipt dated more than this many days before it was uploaded is old:
# nothing on it is asked, neither a question nor a spot check (owner,
# 2026-10-26: "a receipt older than 7 days don't bother"; a person does not
# remember what a line was weeks ago). Its open lines wait for a newer
# receipt with the same printed line at the same shop: that one is asked,
# and the answer, kept for the shop and the printed line, places both.
OLD_AFTER_DAYS = 7


def too_old_to_ask(printed: date | None, uploaded: datetime | None) -> bool:
    """Whether a receipt printed on `printed` and uploaded at `uploaded` is
    old (`OLD_AFTER_DAYS`), by the day in Germany. One with no printed date
    is not."""
    if printed is None or uploaded is None:
        return False
    from grocery_app.offers import GERMANY

    return (uploaded.astimezone(GERMANY).date() - printed).days > OLD_AFTER_DAYS


def nearest_price(prices: list[float] | None, paid: float | None) -> float | None:
    """The shelf price of a candidate nearest to what was paid; its only one
    when nothing was paid to compare with."""
    if not prices:
        return None
    if paid is None:
        return prices[0]
    return min(prices, key=lambda p: abs(p - paid))


def card_order(candidates: list[dict[str, Any]], choices: list[str],
               pick: int | None, paid: float | None) -> list[dict[str, Any]]:
    """The cards to show: `{"candidate": n}` (1-based, as the question numbers
    them) or `{"choice": text}`, first card first."""
    ranked = []
    for number, candidate in enumerate(candidates, 1):
        price = nearest_price(candidate.get("prices"), paid)
        gap = abs(price - paid) if price is not None and paid is not None else None
        if gap is not None and gap < 0.005:
            rank = 0
        elif number == pick:
            rank = 1
        else:
            rank = 3
        ranked.append((rank, gap if gap is not None else float("inf"), number,
                       {"candidate": number}))
    ranked += [(2, 0.0, n, {"choice": text}) for n, text in enumerate(choices)]
    ranked.sort(key=lambda r: r[:3])
    return [card for *_, card in ranked[:MOST_CARDS]]
