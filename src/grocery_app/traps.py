"""Traps: checks on real data that tell the owner when a rule breaks.

A trap writes one line to the server's log, and Cloud Monitoring turns any
such line into an email (`scripts/setup-alerts.sh`). Logs are not for receipt
text, so a trap says where to look (ids, counts) and never what was bought.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

MARK = "GROCERY_TRAP"  # what the log-based alert in Cloud Monitoring matches


def fire(name: str, **where: int | str | None) -> None:
    """Notify the owner that the rule `name` broke, and where."""
    place = " ".join(f"{key}={value}" for key, value in where.items())
    log.error("%s %s %s", MARK, name, place)
