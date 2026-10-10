"""Spot checks: finding the mistakes the app does not know it made.

A question is a line the app knows it cannot place. A wrong answer it is
sure of never becomes one, so it would sit in the history unnoticed. The
only way to find those is to ask about lines the app thinks it got right,
chosen at random, and count how often the shopper corrects them: on real
shopping, not only on the answer sheet it was tuned on.

`pick_checks` chooses, per receipt, `SPOT_CHECKS_PER_RECEIPT` lines whose
`said_by` is `app` (the matcher's or identify's memory entries, or a
reading by rule), different printed names, where the product says more than
the paper (`says_more_than_print`). A line the shopper has answered is `you`,
so it is never one. A receipt is picked for once. The seed is the receipt id, so the
choice is random across receipts and the same on a re-run.

The shopper answers a check as any line: `PUT .../lines/{position}/resolution`
with the product the app said (right) or another one (corrected).
"""

from __future__ import annotations

import random
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from grocery_app.db.io import load_normalizer_inputs, receipt_to_dict
from grocery_app.db.models import Check, Receipt
from grocery_app.normalizer import normalize_receipt, printed_size
from grocery_app.resolver import fold

# Parham's call, 2026-09-30: about ten seconds per receipt, and after twenty
# receipts forty checked lines.
SPOT_CHECKS_PER_RECEIPT = 2


_TO_BASE = {"kg": ("g", 1000), "l": ("ml", 1000)}


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", fold(text)) if w and not w.isdigit()]


def _amount(size: dict[str, Any] | None) -> tuple[float, float, str] | None:
    if not size or not size.get("value") or not size.get("unit"):
        return None
    unit, factor = _TO_BASE.get(size["unit"].lower(), (size["unit"].lower(), 1))
    return (size.get("count") or 1, round(size["value"] * factor, 3), unit)


def says_more_than_print(raw_name: str, product: dict[str, Any]) -> bool:
    """Whether the product claims something the printed line does not say: a
    word of its name, brand or details that is not on the paper, or a size
    the paper does not print. A word cut short on the paper (`Authent` for
    Authentic) is the same word. The category is not counted.

    Only such a line is worth a spot check (Parham, 2026-10-08): the receipt
    says `Sandkuchen`, the app says Sandkuchen, and a person cannot tell what
    is being asked.
    """
    printed = _words(raw_name)
    claimed = _words(" ".join([product.get("name") or "", product.get("brand") or "",
                               *(product.get("details") or [])]))
    for word in claimed:
        if not any(word == p or (len(p) >= 3 and word.startswith(p)) for p in printed):
            return True
    size = _amount(product.get("size"))
    return size is not None and size != _amount(printed_size(raw_name))


def pick_checks(session: Session, receipt_id: int,
                n: int = SPOT_CHECKS_PER_RECEIPT) -> int:
    """Choose this receipt's spot checks, if it has none yet. The caller commits."""
    receipt = session.get(Receipt, receipt_id)
    if receipt is None or session.scalars(
            select(Check).where(Check.receipt_id == receipt_id)).first() is not None:
        return 0
    inputs = load_normalizer_inputs(session)
    doc = receipt_to_dict(receipt)
    records = normalize_receipt(doc, inputs["resolution"], inputs["products"],
                                inputs["line_resolutions"], inputs["shelf_prices"],
                                inputs["authors"])
    by_name: dict[str, int] = {}
    for position, record in enumerate(records):
        if (record["type"] == "product" and record["said_by"] == "app"
                and record["product_id"]
                and says_more_than_print(record["raw_name"],
                                         inputs["products"].get(record["product_id"], {}))):
            by_name.setdefault(record["raw_name"], position)
    chosen = sorted(random.Random(receipt_id).sample(sorted(by_name.values()),
                                                     min(n, len(by_name))))
    for position in chosen:
        session.add(Check(receipt_id=receipt_id, position=position,
                          raw_name=records[position]["raw_name"],
                          app_product_id=records[position]["product_id"]))
    session.flush()
    return len(chosen)
