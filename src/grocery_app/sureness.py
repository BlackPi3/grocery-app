"""How sure the app is of each line, and how much a person had to help.

The owner's call, 2026-10-12: count every product line by level, so the
numbers say how much the app needs its users. The levels are read from what
a line already records (`normalizer.normalize_line`: `resolution` and
`said_by`) and nothing else; no new field is written for them.

- **answered**: a person said what the line is (`said_by` is `you`: their
  answer for the line, or a memory entry the owner decided), or said it was
  none of what the app offered. Counted apart from the four levels.
- **1 sure** (`exact`, `produce`): the app placed the line on one product,
  from its memory of the printed name or the produce vocabulary. Spot checks
  ask about these anyway; their yes rate says how good the app is.
- **2 unclear print** (`price`): the printed name stands for several products
  and the price paid picked one. The receipt was unclear; the app found the
  product anyway.
- **3 category only** (`family` with a category): the printed name stands
  for several products and nothing picked one. The app knows the kind of
  thing (and the brand), not which one: still fine for the insights.
- **4 needs an answer** (`none`, or a `family` whose members share no
  category): nothing the history can use. Only a person can say.

What the fields cannot say, and is not guessed: whether an exact or a
nothing-placed line had unclear print. Unclear print is told apart only where
the line records it: a family and a price reading are the receipt's doing
(one printed name, several products). Inside level 4, two things are counted
because the data says them: `print_says_nothing`, a name the till prints for
anything (`normalizer.NEVER_REMEMBERED`, the receipt's fault), and
`category_guessed`, a line whose photo reading guessed a category
(`line_guesses`) that nothing placed. The guess is not used by the history,
so the line stays at level 4.

A line the shopper left out of their numbers is not counted at all.
"""

from __future__ import annotations

from typing import Any

from grocery_app.normalizer import never_remembered

LEVELS = ("sure", "unclear_print", "category_only", "needs_answer")
COUNTS = ("lines", "answered", *LEVELS, "print_says_nothing", "category_guessed")


def level(record: dict[str, Any], answered: bool = False) -> str | None:
    """`answered`, one of `LEVELS`, or None for a line not counted.

    `record` is a line as the normalizer reads it. `answered` is whether a
    person answered this line, "none of these" too: such an answer leaves
    `said_by` empty, so the caller says it from the line's answer."""
    if record.get("type", "product") != "product" or record.get("not_counted"):
        return None
    if answered or record.get("said_by") == "you":
        return "answered"
    how = record.get("resolution")
    if how in ("exact", "produce"):
        return "sure"
    if how == "price":
        return "unclear_print"
    if how == "family" and record.get("category"):
        return "category_only"
    return "needs_answer"


def empty() -> dict[str, int]:
    return dict.fromkeys(COUNTS, 0)


def add(counts: dict[str, int], record: dict[str, Any], answered: bool = False,
        category_guessed: bool = False) -> str | None:
    """Count one line into `counts`; returns its level."""
    found = level(record, answered)
    if found is None:
        return None
    counts["lines"] += 1
    counts[found] += 1
    if found == "needs_answer":
        if never_remembered(record.get("store"), record.get("raw_name") or ""):
            counts["print_says_nothing"] += 1
        if category_guessed:
            counts["category_guessed"] += 1
    return found
