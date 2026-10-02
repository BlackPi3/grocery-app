"""Running the matcher over a stored receipt, and saving what it decides.

Catalog growth step 5b. After a photo is read, every product line the memory
cannot place goes to `matcher.propose`, and its verdict is acted on here:

- `accept` or `family`: the answer is **saved to the memory**, as the
  matcher's (`confirmed_by = "matcher"`), so the next receipt needs no model
  call. A chosen shop listing the catalog does not hold becomes a product
  first (`matcher.new_product`), with its listing and the price seen.
- `ask`: with an identifier, `identify` reads the line first (price, VAT,
  the rest of the receipt, the shop's similar products). When it can tell
  what the line is, that is **saved to the memory** as identify's answer
  (`confirmed_by = "identify"`), pointing at a level-1 product: an existing
  one with the same name, brand and variant, else a new one in that format
  (`docs/designs/what-a-line-is.md`). Only when it cannot tell does the line
  become a **question**, with everything the matcher and identify saw, for
  the shopper to answer (5c lists them).

The matcher's answers are not final: a shopper's answer overrules one and the
mistake is counted (`memory.learn`, `corrections`). Names a till prints for
anything (`normalizer.NEVER_REMEMBERED`) are left alone: nothing about one
line of them says anything about the next, so they wait for the shopper.

The line matcher is an argument with no default, like the extractor: a model
call is not something a test may trigger by forgetting a parameter. The
identifier too; without one, a line the matcher cannot settle is a question,
as before.

Until the catalog is rewritten in the level-1 format, a new level-1 product
can be the same thing as an older product named another way (`Magerquark,
Jeden Tag` beside `Magerquark (low-fat quark)`). That rewrite merges them;
the history points at product ids, so nothing is lost meanwhile (decided
with Parham 2026-09-30, option A).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from grocery_app import identify as identifying
from grocery_app import matcher as matching
from grocery_app.db.io import load_normalizer_inputs, product_from_dict, receipt_to_dict
from grocery_app.db.models import Product, Question, Receipt, Resolution, StoreListing
from grocery_app.normalizer import never_remembered, normalize_receipt
from grocery_app.resolver import store_key

# (receipt line, store, the normalizer's inputs plus `index`) -> a proposal.
LineMatcher = Callable[[dict[str, Any], str | None, dict[str, Any]], dict[str, Any]]
# (position, the receipt as a dict, the matcher's proposal, the normalizer's
# inputs, and optionally the shopper's description) -> what the line is, or
# that it cannot tell.
LineIdentifier = Callable[..., identifying.Identity]


def line_matcher(decider: matching.Decider,
                 shops: dict[str, matching.ShopSource]) -> LineMatcher:
    """`matcher.propose`, bound to a decider and the shops to search."""
    def match(line: dict[str, Any], store: str | None,
              inputs: dict[str, Any]) -> dict[str, Any]:
        return matching.propose(line, store, inputs["products"], inputs["resolution"],
                                inputs["shelf_prices"], inputs["index"], shops, decider)
    return match


def line_identifier(decider: matching.Decider,
                    searcher: matching.Decider | None = None) -> LineIdentifier:
    """`identify.read_line`, bound to a reader and a searcher, with the
    evidence it is scored with: what was paid and the VAT rate, the other
    printed names on the receipt, the shop's similar products the matcher
    gathered, and the abbreviations the memory has learned at this store.
    With a searcher, every line that is not a café line is searched before it
    is read, and a question carries what the search narrowed it to."""
    def read(position: int, receipt: dict[str, Any], proposal: dict[str, Any],
             inputs: dict[str, Any], description: str | None = None) -> identifying.Identity:
        line = receipt["lines"][position]
        store = receipt.get("store")
        learned = identifying.abbreviations(inputs["resolution"], inputs["products"])
        others = [other["raw_name"] for other in receipt["lines"]
                  if other.get("type", "product") == "product"]
        paid = identifying.paid(line, identifying.line_vat_rates(receipt)[position])
        return identifying.read_line(line["raw_name"], store, decider, searcher,
                                     proposal.get("candidates") or None, others, paid,
                                     learned.get(store_key(store)), description,
                                     receipt.get("store_location"))
    return read


def same_product_key(name: str | None, brand: str | None,
                     variant: str | None = None) -> tuple[str, ...]:
    """What makes two level-1 products the same: name, brand and variant,
    letter case and outer spaces aside."""
    return tuple((v or "").strip().casefold() for v in (name, brand, variant))


def identified_product(session: Session, identity: identifying.Identity,
                       inputs: dict[str, Any], decided_by: str = "identify") -> str:
    """The level-1 product for what identify said a line is.

    An existing product with the same name, brand and variant (letter case
    aside) is that product; otherwise a new one is made from the identity and
    nothing else. No size: it belongs to the purchase, not the product. Organic
    only when the name says Bio; otherwise unknown, not false."""
    wanted = same_product_key(identity.name, identity.brand, identity.variant)
    for product_id, product in inputs["products"].items():
        if same_product_key(product.get("name"), product.get("brand"),
                            product.get("variant")) == wanted:
            return product_id

    from grocery_app.categorize import CATEGORY_UNKNOWN
    from grocery_app.resolver import brand_questions

    product_id = next_product_id(session)
    made = {
        "label": identity.name, "name": identity.name, "brand": identity.brand,
        "product_line": None, "variant": identity.variant,
        "size": {"count": 1, "value": None, "unit": None}, "category": identity.category,
        "is_organic": True if "bio" in identity.name.casefold().split() else None,
        "eans": [],
        "open_questions": brand_questions(identity.brand)
        + ([] if identity.category else [CATEGORY_UNKNOWN]),
        "provenance": {"attributes": "identify",
                       "source": f"identify {identifying.PROMPT_VERSION}",
                       "decided_by": decided_by},
    }
    session.add(product_from_dict(product_id, made))
    session.flush()
    inputs["products"][product_id] = made
    return product_id


def article_index(session: Session) -> dict[str, str]:
    """Shop article number or barcode -> our product, as `evaluate_matching`
    builds it from the files."""
    index = {listing.article_number: listing.product_id
             for listing in session.scalars(select(StoreListing))}
    for product in session.scalars(select(Product)):
        for ean in product.eans or []:
            index.setdefault(ean, product.id)
    return index


def next_product_id(session: Session) -> str:
    numbers = [int(pid.split("-")[1]) for pid in session.scalars(select(Product.id))
               if pid.startswith("p-") and pid.split("-")[1].isdigit()]
    return f"p-{max(numbers, default=0) + 1:04d}"


def product_for(session: Session, candidate: dict[str, Any], store: str,
                inputs: dict[str, Any], decided_by: str = "matcher") -> str:
    """Our product for a chosen candidate, made from its shop listing if new.

    `inputs` needs `index` and `products`, and both are kept up to date, so a
    listing chosen twice becomes one product.
    """
    if candidate.get("product_id"):
        return candidate["product_id"]
    article = candidate.get("article")
    if article and article in inputs["index"]:
        return inputs["index"][article]
    product_id = next_product_id(session)
    made = matching.new_product(candidate, decided_by)
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


def shopper_product(session: Session, name: str, brand: str | None) -> str:
    """"None of these, it's …": a product in the shopper's words, as far as they go.

    Kashk from a shop no catalog lists. Nothing else is known, and nothing is
    guessed: size, category and barcode stay empty, and `open_questions` says
    so. A barcode scanned at home later can fill in the rest. A product with
    the same name and brand (and no variant) already is that product: typing
    `Kashk` twice is one Kashk.
    """
    from grocery_app.categorize import CATEGORY_UNKNOWN
    from grocery_app.resolver import brand_questions

    wanted = same_product_key(name, brand)
    for product in session.scalars(select(Product)):
        if same_product_key(product.name, product.brand, product.variant) == wanted:
            return product.id
    product_id = next_product_id(session)
    session.add(product_from_dict(product_id, {
        "label": name, "name": name, "brand": brand, "product_line": None, "variant": None,
        "size": {"count": 1, "value": None, "unit": None}, "category": None,
        "is_organic": None, "eans": [],
        "open_questions": brand_questions(brand) + [CATEGORY_UNKNOWN],
        "provenance": {"attributes": "shopper", "source": None, "decided_by": "shopper"},
    }))
    session.flush()
    return product_id


def described_product(session: Session, receipt_id: int, position: int, description: str,
                      identify: LineIdentifier | None) -> str:
    """The product a shopper's description of a line means, in our format.

    The shopper says what it was in their own words, in any language and as
    loosely as they like ("salted pickled cucumbers, the Pamir ones").
    identify reads the words with the printed line, the price and the rest of
    the receipt, and gives the level-1 product (`Salzgurken`, Pamir): an
    existing one with that name, brand and variant, or a new one decided by
    the shopper. The meaning is the shopper's; only the wording is ours, so
    a change of format is a re-run, never a question back (Parham,
    2026-10-01). The words themselves are kept on the line's answer.

    When identify cannot read the words, or there is no identifier, the
    product is the words as written (`shopper_product`): an answer is never
    lost for want of a format.
    """
    if identify is not None:
        receipt = session.get(Receipt, receipt_id)
        doc = receipt_to_dict(receipt)
        inputs = load_normalizer_inputs(session)
        question = session.scalars(select(Question).where(
            Question.receipt_id == receipt_id, Question.position == position)).first()
        proposal = question.proposal if question is not None else {"candidates": []}
        identity = identify(position, doc, proposal, inputs, description=description)
        if identity.can_tell:
            return identified_product(session, identity, inputs, decided_by="shopper")
    return shopper_product(session, description, None)


def match_receipt(session: Session, receipt_id: int, match: LineMatcher,
                  identify: LineIdentifier | None = None) -> dict[str, int]:
    """Match every line of one receipt the memory cannot place. The caller commits.

    A printed name is matched once per receipt: the second `Bitter-Getränk`
    finds the first one's answer in the memory. A line that already has a
    question is not asked about twice.
    """
    receipt = session.get(Receipt, receipt_id)
    counts = {"accepted": 0, "families": 0, "identified": 0, "questions": 0, "products": 0,
              "unsearched": 0}
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
        if verdict == "ask" and identify is not None:
            identity = identify(position, doc, proposal, inputs)
            if identity.unsearched:
                # No search happened: neither saved nor asked; the next run
                # reads it again.
                counts["unsearched"] += 1
                continue
            if identity.can_tell:
                before = len(inputs["products"])
                product_id = identified_product(session, identity, inputs)
                counts["products"] += len(inputs["products"]) - before
                session.add(Resolution(
                    store=receipt.store, raw_name=line["raw_name"], line_type="product",
                    product_id=product_id, product_ids=[],
                    confirmed_by="identify", confirmed_at=date.today(),
                    source=f"identify {identifying.PROMPT_VERSION}"))
                inputs["resolution"][(store_key(receipt.store), line["raw_name"])] = \
                    [product_id]
                counts["identified"] += 1
                continue
            proposal = {**proposal, "identity": identity.as_dict()}
        if verdict == "ask":
            session.add(Question(receipt_id=receipt_id, position=position,
                                 raw_name=line["raw_name"], proposal=proposal))
            counts["questions"] += 1
            continue

        chosen = [proposal["pick"]] if verdict == "accept" else proposal["versions"]
        before = len(inputs["products"])
        ids = [product_for(session, c, receipt.store, inputs) for c in chosen]
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
