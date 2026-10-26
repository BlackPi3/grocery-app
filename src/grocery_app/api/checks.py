"""Spot checks: finding the mistakes the app does not know it made.

A question is a line the app knows it cannot place. A wrong answer it is
sure of never becomes one, so it would sit in the history unnoticed. The
only way to find those is to ask about lines the app thinks it got right,
chosen at random, and count how often the shopper corrects them: on real
shopping, not only on the answer sheet it was tuned on.

`pick_checks` chooses, per receipt, `SPOT_CHECKS_PER_RECEIPT` lines whose
`said_by` is `app` (the matcher's or identify's memory entries, or a
reading by rule), different printed names, where the product says more than
the paper (`says_more_than_print`) beyond how the line was sold. A line the
shopper has answered is `you`, so it is never one. A receipt is picked for
once. The seed is the receipt id, so the choice is random across receipts and
the same on a re-run.

Far fewer since 2026-10-26 (owner: "what's the point of random check at this
moment? it has proved the app is finding things alright. make far less
frequent. not necessarily per receipt"; 100 of 103 answered right): one
check a week per person at most (`CHECK_EVERY`), only on groceries (an
Action glass carafe was asked about), never on an old receipt
(`cards.too_old_to_ask`). An open check is shown for `CHECK_EVERY` after it
was picked; one left unanswered longer is let go, so the checks picked two
a receipt before that do not come back as a pile.

The shopper answers a check as any line: `PUT .../lines/{position}/resolution`
with the product the app said (right) or another one (corrected).
"""

from __future__ import annotations

import random
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from grocery_app import categories
from grocery_app.api.cards import too_old_to_ask
from grocery_app.db.io import load_normalizer_inputs, receipt_to_dict
from grocery_app.db.models import Check, Receipt
from grocery_app.normalizer import SOLD_AS_WORDS, normalize_receipt, printed_size
from grocery_app.resolver import fold

# One line when a receipt is picked from (it was two, Parham's call of
# 2026-09-30: about ten seconds per receipt).
SPOT_CHECKS_PER_RECEIPT = 1
# At most one pick a week per person, and a check is shown for that long.
CHECK_EVERY = timedelta(days=7)


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
    Authentic) is the same word. The category is not counted, and neither is
    a word for how the line was sold (`SOLD_AS_WORDS`): that is the purchase,
    not the product.

    Only such a line is worth a spot check (Parham, 2026-10-08): the receipt
    says `Sandkuchen`, the app says Sandkuchen, and a person cannot tell what
    is being asked. Nor when the receipt says `Bananen` and the app says
    Bananen, lose (2026-10-12).
    """
    printed = _words(raw_name)
    claimed = _words(" ".join([product.get("name") or "", product.get("brand") or "",
                               *(product.get("details") or [])]))
    for word in claimed:
        if word in SOLD_AS_WORDS:
            continue
        if not any(word == p or (len(p) >= 3 and word.startswith(p)) for p in printed):
            return True
    size = _amount(product.get("size"))
    return size is not None and size != _amount(printed_size(raw_name))


def picked_lately(session: Session, user_id: int | None,
                  now: datetime | None = None) -> bool:
    """Whether this person (None: the owner) had a check picked in the last
    `CHECK_EVERY`."""
    since = (now or datetime.now(UTC)) - CHECK_EVERY
    whose = Receipt.user_id.is_(None) if user_id is None else Receipt.user_id == user_id
    return session.scalars(select(Check.id).join(Receipt, Receipt.id == Check.receipt_id)
                           .where(whose, Check.created_at >= since)).first() is not None


def pick_checks(session: Session, receipt_id: int,
                n: int = SPOT_CHECKS_PER_RECEIPT) -> int:
    """Choose this receipt's spot checks, if it has none yet, it is not old,
    and its person had none picked in the last `CHECK_EVERY`. The caller
    commits."""
    receipt = session.get(Receipt, receipt_id)
    if receipt is None or session.scalars(
            select(Check).where(Check.receipt_id == receipt_id)).first() is not None:
        return 0
    if too_old_to_ask(receipt.date, receipt.created_at) \
            or picked_lately(session, receipt.user_id):
        return 0
    inputs = load_normalizer_inputs(session)
    doc = receipt_to_dict(receipt)
    records = normalize_receipt(doc, inputs["resolution"], inputs["products"],
                                inputs["line_resolutions"], inputs["shelf_prices"],
                                inputs["authors"])
    by_name: dict[str, int] = {}
    for position, record in enumerate(records):
        product = inputs["products"].get(record["product_id"], {})
        if (record["type"] == "product" and record["said_by"] == "app"
                and record["product_id"] and categories.is_grocery(product.get("category"))
                and says_more_than_print(record["raw_name"], product)):
            by_name.setdefault(record["raw_name"], position)
    chosen = sorted(random.Random(receipt_id).sample(sorted(by_name.values()),
                                                     min(n, len(by_name))))
    for position in chosen:
        session.add(Check(receipt_id=receipt_id, position=position,
                          raw_name=records[position]["raw_name"],
                          app_product_id=records[position]["product_id"]))
    session.flush()
    return len(chosen)
