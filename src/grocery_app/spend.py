"""What each model call cost, written down where the call is made.

Parham, 2026-10-11: "we need to incorporate a way to see how much it costs
to process receipts. not just reading but finding items. as we go on, this
search will become lesser and lesser." So every Gemini call, whatever made
it, goes through `record` (from `gemini.generate`), and a server writes each
one to the `model_calls` table. A receipt's cost is then the sum of the calls
made for its job; a month's, the sum of the calls made in it.

What a call was *for* and *which job* it served are not known where the call
is made, so the code that does know says so around it (`tagged`): the job
runner names the job, the reader says `reading`, placing the lines says
`finding`, the picture thread says `pictures`. A call nobody tagged is
`other`, still counted.

Prices are list prices, in dollars, as the provider bills. The first 5,000
searches a month are free on Gemini 3 (`FREE_SEARCHES_PER_MONTH`); that is not
subtracted per call, because which searches fall inside it is only known at
the month's end. Without a sink installed (tests, a laptop without a
database) nothing is written; a sink that fails never fails the call.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

log = logging.getLogger(__name__)

# USD per million tokens; thinking is billed as output. Introductory rates
# until 2026-12-31, doubling on 2027-01-01 (third-party price pages,
# 2026-10-03; not checked against Google's own page). Read in the EU since
# 2026-10-15, about 10% over the global endpoint's 0.75 / 3.75 (third-party
# price pages, the same day).
GEMINI_PRICES_PER_MTOK: dict[str, dict[str, float]] = {
    "gemini-3.8-flash": {"input": 0.825, "output": 4.125},
}
# Grounding with Google Search on Gemini 3: per search query the model runs,
# not per request (third-party pricing guides, 2026-10-11; Google's own page
# was not found).
SEARCH_PRICE_USD = 0.014
FREE_SEARCHES_PER_MONTH = 5000

PURPOSES = ("reading", "finding", "pictures", "other")

# A day's model calls past this, in dollars, is unusual (Parham, 2026-10-12:
# guests and a second user are in, "we don't want to bleed money without
# knowing"). October's first twelve days cost $0.91 in all; a dollar in one
# day is about ten normal days. Each further dollar is said again.
ALERT_EVERY_USD = 1.0
ALERT_MARK = "SPEND_ALERT"  # what the log-based alert in Cloud Monitoring matches

_purpose: ContextVar[str | None] = ContextVar("spend_purpose", default=None)
_job: ContextVar[str | None] = ContextVar("spend_job", default=None)
_sink: Callable[[dict[str, Any]], None] | None = None


def install(sink: Callable[[dict[str, Any]], None] | None) -> None:
    """Where calls are written from now on; None stops writing."""
    global _sink
    _sink = sink


@contextmanager
def tagged(purpose: str | None = None, job_id: str | None = None) -> Iterator[None]:
    """Calls made inside are for `purpose` and, when given, for `job_id`."""
    tokens = []
    if purpose is not None:
        tokens.append((_purpose, _purpose.set(purpose)))
    if job_id is not None:
        tokens.append((_job, _job.set(str(job_id))))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def gemini_cost(model: str, usage: dict[str, Any], searches: int = 0) -> float | None:
    """A call's list price: its tokens, and the searches it ran. None for a
    model with no known price."""
    prices = GEMINI_PRICES_PER_MTOK.get(model)
    if prices is None:
        return None
    output = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
    return round(usage.get("promptTokenCount", 0) * prices["input"] / 1e6
                 + output * prices["output"] / 1e6 + searches * SEARCH_PRICE_USD, 5)


def call_record(model: str, data: dict[str, Any]) -> dict[str, Any]:
    """One Gemini answer as a row: what it was for, what it used, its price."""
    usage = data.get("usageMetadata") or {}
    grounding = (data.get("candidates") or [{}])[0].get("groundingMetadata") or {}
    searches = len(grounding.get("webSearchQueries") or [])
    return {
        "purpose": _purpose.get() or "other",
        "job_id": _job.get(),
        "model": model,
        "input_tokens": usage.get("promptTokenCount", 0),
        "output_tokens": usage.get("candidatesTokenCount", 0)
                         + usage.get("thoughtsTokenCount", 0),
        "searches": searches,
        "cost_usd": gemini_cost(model, usage, searches),
    }


def record(model: str, data: dict[str, Any]) -> None:
    """Write down one answered call, if anything is listening."""
    if _sink is None:
        return
    try:
        _sink(call_record(model, data))
    except Exception:  # noqa: BLE001 - a lost cost row is never worth a failed call
        log.exception("could not record a model call's cost")


def database_sink(session_factory: Any) -> Callable[[dict[str, Any]], None]:
    """Each call as a `model_calls` row, in a session of its own: the caller's
    may be mid-transaction or rolled back, and the money was spent anyway.

    A call that takes the day's spend past another `GROCERY_SPEND_ALERT_USD`
    (default `ALERT_EVERY_USD`) also logs `SPEND_ALERT`, which Cloud
    Monitoring turns into an email (scripts/setup-alerts.sh)."""
    from datetime import UTC, datetime
    from decimal import Decimal

    from sqlalchemy import func, select

    from grocery_app.db.models import ModelCall

    every = float(os.environ.get("GROCERY_SPEND_ALERT_USD", ALERT_EVERY_USD))

    def write(row: dict[str, Any]) -> None:
        cost = row["cost_usd"]
        with session_factory() as session:
            session.add(ModelCall(**{**row, "cost_usd": None if cost is None
                                     else Decimal(str(cost))}))
            session.commit()
            if not cost:
                return
            midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            today = float(session.scalar(select(func.coalesce(func.sum(ModelCall.cost_usd), 0))
                                         .where(ModelCall.at >= midnight)))
        if int(today // every) > int((today - cost) // every):
            log.error("%s: model calls cost $%.2f today (UTC), past the $%.2f mark; "
                      "last call: %s, %s", ALERT_MARK, today, today // every * every,
                      row["purpose"], row["model"])

    return write
