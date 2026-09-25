"""Running the matcher over a stored receipt, and saving what it decides.

Catalog growth step 5b. After a photo is read, every product line the memory
cannot place goes to `matcher.propose`, and its verdict is acted on here:

- `accept` or `family`: the answer is **saved to the memory**, as the
  matcher's (`confirmed_by = "matcher"`), so the next receipt needs no model
  call. A chosen shop listing the catalog does not hold becomes a product
  first (`matcher.new_product`), with its listing and the price seen.
- `ask`: the line becomes a **question**, with everything the matcher saw,
  for the shopper to answer (5c lists them).

The matcher's answers are not final: a shopper's answer overrules one and the
mistake is counted (`memory.learn`, `corrections`). Names a till prints for
anything (`normalizer.NEVER_REMEMBERED`) are left alone: nothing about one
line of them says anything about the next, so they wait for the shopper.

The line matcher is an argument with no default, like the extractor: a model
call is not something a test may trigger by forgetting a parameter.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from grocery_app import matcher as matching
from grocery_app.db.io import load_normalizer_inputs, product_from_dict, receipt_to_dict
from grocery_app.db.models import Product, Question, Receipt, Resolution, StoreListing
from grocery_app.normalizer import never_remembered, normalize_receipt
from grocery_app.resolver import store_key

# (receipt line, store, the normalizer's inputs plus `index`) -> a proposal.
LineMatcher = Callable[[dict[str, Any], str | None, dict[str, Any]], dict[str, Any]]


def line_matcher(decider: matching.Decider,
                 shops: dict[str, matching.ShopSource]) -> LineMatcher:
    """`matcher.propose`, bound to a decider and the shops to search."""
    def match(line: dict[str, Any], store: str | None,
              inputs: dict[str, Any]) -> dict[str, Any]:
        return matching.propose(line, store, inputs["products"], inputs["resolution"],
                                inputs["shelf_prices"], inputs["index"], shops, decider)
    return match


def article_index(session: Session) -> dict[str, str]:
    """Shop article number or barcode -> our product, as `evaluate_matching`
    builds it from the files."""
    index = {listing.article_number: listing.product_id
             for listing in session.scalars(select(StoreListing))}
    for product in session.scalars(select(Product)):
        for ean in product.eans or []:
            index.setdefault(ean, product.id)
    return index


def _next_product_id(session: Session) -> str:
    numbers = [int(pid.split("-")[1]) for pid in session.scalars(select(Product.id))
               if pid.startswith("p-") and pid.split("-")[1].isdigit()]
    return f"p-{max(numbers, default=0) + 1:04d}"


def _product_for(session: Session, candidate: dict[str, Any], store: str,
                 inputs: dict[str, Any]) -> str:
    """Our product for a chosen candidate, made from its shop listing if new."""
    if candidate.get("product_id"):
        return candidate["product_id"]
    article = candidate.get("article")
    if article and article in inputs["index"]:
        return inputs["index"][article]
    product_id = _next_product_id(session)
    made = matching.new_product(candidate, "matcher")
    session.add(product_from_dict(product_id, made))
    if article:
        session.add(StoreListing(
            store=store, article_number=article, product_id=product_id,
            url=candidate.get("url"),
            prices=[{"date": date.today().isoformat(), "price": price}
                    for price in candidate.get("prices") or []][:1]))
        inputs["index"][article] = product_id
    session.flush()
    inputs["products"][product_id] = made
    return product_id


def match_receipt(session: Session, receipt_id: int, match: LineMatcher) -> dict[str, int]:
    """Match every line of one receipt the memory cannot place. The caller commits.

    A printed name is matched once per receipt: the second `Bitter-Getränk`
    finds the first one's answer in the memory. A line that already has a
    question is not asked about twice.
    """
    receipt = session.get(Receipt, receipt_id)
    counts = {"accepted": 0, "families": 0, "questions": 0, "products": 0}
    if receipt is None or not receipt.store:
        return counts

    inputs = load_normalizer_inputs(session)
    inputs["index"] = article_index(session)
    asked = {q.position for q in session.scalars(
        select(Question).where(Question.receipt_id == receipt_id))}
    doc = receipt_to_dict(receipt)

    for position, line in enumerate(doc["lines"]):
        # Read again each time: an answer saved for an earlier line of this
        # receipt may already place this one.
        record = normalize_receipt({**doc, "lines": [line]}, inputs["resolution"],
                                   inputs["products"])[0]
        if record["resolution"] != "none" or line.get("type", "product") != "product" \
                or never_remembered(receipt.store, line["raw_name"]) or position in asked:
            continue

        proposal = match(line, receipt.store, inputs)
        verdict = proposal["verdict"]
        if verdict == "ask":
            session.add(Question(receipt_id=receipt_id, position=position,
                                 raw_name=line["raw_name"], proposal=proposal))
            counts["questions"] += 1
            continue

        chosen = [proposal["pick"]] if verdict == "accept" else proposal["versions"]
        before = len(inputs["products"])
        ids = [_product_for(session, c, receipt.store, inputs) for c in chosen]
        counts["products"] += len(inputs["products"]) - before
        family = len(ids) > 1
        session.add(Resolution(
            store=receipt.store, raw_name=line["raw_name"], line_type="product",
            product_id=None if family else ids[0], product_ids=ids if family else [],
            status="ambiguous_on_receipt" if family else None,
            confirmed_by="matcher", confirmed_at=date.today(),
            source=f"matcher {matching.PROMPT_VERSION}"))
        inputs["resolution"][(store_key(receipt.store), line["raw_name"])] = ids
        counts["families" if family else "accepted"] += 1
    session.flush()
    return counts
