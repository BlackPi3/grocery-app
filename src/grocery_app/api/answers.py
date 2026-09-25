"""The shopper's answers from a sheet, given to the server as the phone would.

`data/receipts/product_truth.json` holds Parham's answer for every line of the
22 fresh receipts (`evaluate_matching` scores the matcher against it). Once a
batch has been scored, its answers are what the memory should learn from
(`catalog-growth.md`: scored before it learns, then its answers are added).

Each answer goes through the same repository calls as `PUT .../resolution`,
so 5a's rules decide what the memory learns. Only answers that name a real
product are given:

- one catalog id -> that product;
- a shop article that is among the line's question candidates -> that
  candidate, so a shop listing becomes a product decided by the shopper.

An answer that is only words (`lemon, premium, 1`) is not turned into a
product here: a description is not a product name, and inventing one would
put words in the shopper's mouth. Those lines stay questions. A line
something else already placed is left alone: the answer key is not a reason
to overrule an answer that is not known to be wrong.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from grocery_app.api.repository import PostgresRepository
from grocery_app.db.models import Receipt


def apply_answers(repo: PostgresRepository, truth_doc: dict[str, Any],
                  confirmed_by: str, basis: str) -> dict[str, list[str]]:
    """Give every usable answer in `truth_doc`; say what happened to each line."""
    with repo.session_factory() as session:
        receipt_ids = {r.source_image: r.id for r in session.scalars(select(Receipt))}
    open_questions = {(q["receipt_id"], q["position"]): q
                      for q in repo.questions()["questions"]}

    done: dict[str, list[str]] = {"answered": [], "placed_already": [], "words_only": [],
                                  "not_offered": [], "family": [], "no_receipt": []}
    for line in truth_doc["lines"]:
        label = f"{line['source_image']}#{line['position']} {line['raw_name']}"
        receipt_id = receipt_ids.get(line["source_image"])
        if receipt_id is None:
            done["no_receipt"].append(label)
            continue
        question = open_questions.get((receipt_id, line["position"]))
        if question is None or question["raw_name"] != line["raw_name"]:
            done["placed_already"].append(label)
            continue

        ids = line.get("catalog_ids") or []
        article = str(line["article"]) if line.get("article") else None
        if len(ids) == 1:
            product_id = ids[0]
        elif len(ids) > 1 and not article:
            # The shopper knows the family, not the version: nothing to pin.
            done["family"].append(label)
            continue
        elif article:
            number = next((c["number"] for c in question["candidates"]
                           if c.get("article") == article), None)
            if number is None:
                done["not_offered"].append(label)
                continue
            product_id = repo.product_for_answer(receipt_id, line["position"], number, None)
        else:
            done["words_only"].append(label)
            continue
        repo.set_line_resolution(receipt_id, line["position"], product_id, confirmed_by, basis)
        done["answered"].append(label)
    return done
