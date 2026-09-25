"""What the memory learns from a shopper's answer (catalog growth, step 5).

The memory is `resolution`: (store, printed name) -> a product, or a family of
products when the till prints one name for several of them. A shopper's answer
is about one line. What it teaches about the *name* depends on what the memory
already held, and `learn` is that rule, written once:

    held                      answer X    afterwards
    nothing                   X           X
    X                         X           unchanged
    a machine's answer Y      X           X, and the machine's mistake is logged
    a person's answer Y       X           the family {Y, X}
    a family holding X        X           unchanged
    a family without X        X           the family and X

The fourth row is the one to read. Two people-answers that differ do not mean
one of them was wrong: they mean the till prints one name for two products
(`JT Tortilla Wraps`, Classic one week and Mehrkorn the next). The receipt
cannot say which, so the name becomes a family, and each answer stays true
for its own line only (decided 2026-09-25). A machine's answer is a guess, so
the person replaces it.

A name on `normalizer.NEVER_REMEMBERED` teaches nothing; the caller checks.
"""

from __future__ import annotations

from typing import Any

# Who wrote a memory entry, when it was not a person.
MACHINE_AUTHORS = frozenset({"matcher"})
# Readings the normalizer makes without any entry saying so.
MACHINE_READINGS = frozenset({"produce", "price"})


def learn(entry: dict[str, Any] | None, answer: str) -> dict[str, Any] | None:
    """The entry the memory should hold after this answer, or None for no change.

    `entry` has `product_id`, `product_ids` and `confirmed_by`; the result has
    the first two. The caller stamps who confirmed it and when.
    """
    if entry is None:
        return {"product_id": answer, "product_ids": []}
    family = list(entry.get("product_ids") or [])
    if family:
        return None if answer in family else {"product_id": None,
                                              "product_ids": family + [answer]}
    held = entry.get("product_id")
    if held is None or held == answer:
        return None if held == answer else {"product_id": answer, "product_ids": []}
    if entry.get("confirmed_by") in MACHINE_AUTHORS:
        return {"product_id": answer, "product_ids": []}
    return {"product_id": None, "product_ids": [held, answer]}


def machine_answer(record: dict[str, Any], entry: dict[str, Any] | None) -> str | None:
    """The product a machine had given this line, before the shopper answered.

    Either the normalizer placed it without a remembered entry (the produce
    vocabulary, a price narrowing a family) or the entry it used was written by
    the matcher. A person's entry, or no answer at all, is not a machine's.
    """
    product_id = record.get("product_id")
    if not product_id:
        return None
    if record.get("resolution") in MACHINE_READINGS:
        return product_id
    if record.get("resolution") == "exact" and entry and \
            entry.get("confirmed_by") in MACHINE_AUTHORS:
        return product_id
    return None
