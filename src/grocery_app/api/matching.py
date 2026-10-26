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
  one with the same name, brand and details, else a new one in that format
  (`docs/designs/what-a-line-is.md`). Only when it cannot tell does the line
  become a **question**, with everything the matcher and identify saw, for
  the shopper to answer (5c lists them). So does a line whose brand no shop
  has been seen with and is one letter from a brand this shop sells
  (`identify.misread_brand`): it is asked with that brand's products as the
  cards (`brand_question`), never saved as a new brand.

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
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from grocery_app import identify as identifying
from grocery_app import matcher as matching
from grocery_app.db.io import load_normalizer_inputs, product_from_dict, receipt_to_dict
from grocery_app.db.models import (
    Job,
    LineResolution,
    Product,
    Question,
    Receipt,
    Resolution,
    StoreListing,
    UncountedLine,
)
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


def _fold(text: str | None) -> str:
    return (text or "").strip().casefold()


def same_product_key(name: str | None, brand: str | None,
                     details: list[str] | None = None) -> tuple[Any, ...]:
    """What makes two level-1 products the same: name, brand and details,
    letter case and outer spaces aside. The details in any order: a list read
    `Citrat, Granulat` one day and `Granulat, Citrat` the next is one product."""
    return (_fold(name), _fold(brand), tuple(sorted({_fold(d) for d in details or []})))


def identified_product(session: Session, identity: identifying.Identity,
                       inputs: dict[str, Any], decided_by: str = "identify") -> str:
    """The level-1 product for what identify said a line is.

    An existing product with the same name, brand and details (letter case
    and order aside) is that product; otherwise a new one is made from the identity and
    nothing else. No size: it belongs to the purchase, not the product. Organic
    only when the name says Bio; otherwise unknown, not false."""
    wanted = same_product_key(identity.name, identity.brand, identity.details)
    for product_id, product in inputs["products"].items():
        if same_product_key(product.get("name"), product.get("brand"),
                            product.get("details")) == wanted:
            return product_id

    from grocery_app.categorize import CATEGORY_UNKNOWN
    from grocery_app.resolver import brand_questions

    product_id = next_product_id(session)
    made = {
        "label": identity.name, "name": identity.name, "brand": identity.brand,
        "details": list(identity.details),
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


def placed_at(session: Session, inputs: dict[str, Any]) -> dict[str, set[str]]:
    """Shop -> the products seen there: placed on a line in the memory or by
    a person's answer (anyone's receipts), or listed by the shop. A product
    no line points at any more (its lines corrected) is not seen."""
    placed: dict[str, set[str]] = {}
    for (store, _), ids in inputs["resolution"].items():
        placed.setdefault(store, set()).update(ids)
    stores = {r["source_image"]: store_key(r.get("store")) for r in inputs["receipts"]}
    for (image, _), said in inputs["line_resolutions"].items():
        if said.get("product_id") and image in stores:
            placed.setdefault(stores[image], set()).add(said["product_id"])
    for listing in session.scalars(select(StoreListing)):
        placed.setdefault(store_key(listing.store), set()).add(listing.product_id)
    return placed


def brands_seen(placed: dict[str, set[str]],
                products: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    """Shop -> the brands of the products seen there (`placed_at`)."""
    return {store: {brand for pid in ids if (brand := (products.get(pid) or {}).get("brand"))}
            for store, ids in placed.items()}


def brand_question(proposal: dict[str, Any], identity: identifying.Identity,
                   near: list[str], store_products: set[str],
                   inputs: dict[str, Any]) -> dict[str, Any]:
    """The question for a line whose brand reads one letter from a brand this
    shop sells (`identify.misread_brand`): is it that brand's product?

    The cards: this shop's products of the near brand, the one with the
    name identify read first (the pick); when the shop has no such product,
    the reading with the near brand, as a choice. Then the reading as it
    stands, so a brand that really is new is one Yes away too. The matcher's
    candidates follow.
    """
    keys = {identifying.brand_key(b) for b in near}
    name = _fold(identity.name)
    ours = sorted((pid for pid in store_products
                   if identifying.brand_key((inputs["products"].get(pid) or {}).get("brand"))
                   in keys),
                  key=lambda pid: (_fold(inputs["products"][pid].get("name")) != name, pid))
    candidates = [asdict(matching.catalog_candidate(pid, inputs["products"],
                                                    inputs["shelf_prices"]))
                  for pid in ours]
    same_name = [c for c in candidates if _fold(c["name"]) == name]
    candidates += [c for c in proposal.get("candidates") or []
                   if not c.get("product_id") or c["product_id"] not in ours]
    said = " ".join([identity.name, *identity.details])
    choices = ([] if same_name else [f"{said}, {brand}" for brand in near]) \
        + [f"{said}, {identity.brand}"]
    read = ", ".join(f"`{b}`" for b in near)
    asked = replace(identity, can_tell=False, choices=choices,
                    reason=f"read the brand `{identity.brand}`, which no shop has been seen "
                           f"with; {read}, one letter from it, is sold here, so it may be "
                           f"misread: {identity.reason}")
    return {**proposal, "candidates": candidates,
            "pick": same_name[0] if same_name else proposal.get("pick"),
            "misread_brand": {"read": identity.brand, "near": near},
            "identity": asked.as_dict()}


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
    the same name and brand (and no details) already is that product: typing
    `Kashk` twice is one Kashk.
    """
    from grocery_app.categorize import CATEGORY_UNKNOWN
    from grocery_app.resolver import brand_questions

    wanted = same_product_key(name, brand)
    for product in session.scalars(select(Product)):
        if same_product_key(product.name, product.brand, product.details) == wanted:
            return product.id
    product_id = next_product_id(session)
    session.add(product_from_dict(product_id, {
        "label": name, "name": name, "brand": brand, "details": [],
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
    The words are a hint (Parham, 2026-10-03): identify searches them with
    the printed line, reads what the pages show with the price and the rest
    of the receipt, and gives the level-1 product (`Salzgurken`, Pamir): an
    existing one with that name, brand and details, or a new one decided by
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


def answered_since(session: Session, receipt_id: int, position: int) -> bool:
    """Whether a line has an answer or a question now, read fresh: a receipt
    is matched line by line for minutes, and the shopper may answer meanwhile."""
    return any(session.scalar(select(model.id).where(model.receipt_id == receipt_id,
                                                     model.position == position).limit(1))
               is not None for model in (LineResolution, Question))


def match_receipt(session: Session, receipt_id: int, match: LineMatcher,
                  identify: LineIdentifier | None = None,
                  checkpoint: Callable[[], None] | None = None) -> dict[str, int]:
    """Match every line of one receipt the memory cannot place. The caller commits.

    A printed name is matched once per receipt: the second `Bitter-Getränk`
    finds the first one's answer in the memory. A line that already has a
    question is not asked about twice. `checkpoint`, when given, runs after
    each line that was matched (a job passes `session.commit`, so the phone
    sees lines placed one by one, and a failure later keeps them).
    """
    receipt = session.get(Receipt, receipt_id)
    counts = {"accepted": 0, "families": 0, "identified": 0, "questions": 0, "products": 0,
              "unsearched": 0}
    if receipt is None or not receipt.store:
        return counts

    inputs = load_normalizer_inputs(session)
    inputs["index"] = article_index(session)
    # A line the shopper answered, "none of these" too, is theirs: never matched.
    asked = {q.position for q in session.scalars(
        select(Question).where(Question.receipt_id == receipt_id))} | set(session.scalars(
            select(LineResolution.position).where(LineResolution.receipt_id == receipt_id)))
    doc = receipt_to_dict(receipt)
    shop = store_key(receipt.store)
    placed = placed_at(session, inputs)
    seen = brands_seen(placed, inputs["products"])

    for position, line in enumerate(doc["lines"]):
        # Read again each time: an answer saved for an earlier line of this
        # receipt may already place this one.
        record = normalize_receipt({**doc, "lines": [line]}, inputs["resolution"],
                                   inputs["products"])[0]
        if record["resolution"] != "none" or line.get("type", "product") != "product" \
                or never_remembered(receipt.store, line["raw_name"]) or position in asked:
            continue
        if answered_since(session, receipt_id, position):
            # Answered or asked while the lines before were read: theirs.
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
            near = (identifying.misread_brand(identity.brand, shop, seen)
                    if identity.can_tell else [])
            if near:
                # One letter from a brand sold here, and seen nowhere: asked,
                # with that brand's products as the cards, never saved as new.
                proposal = brand_question(proposal, identity, near, placed.get(shop, set()),
                                          inputs)
            elif identity.can_tell:
                before = len(inputs["products"])
                product_id = identified_product(session, identity, inputs)
                counts["products"] += len(inputs["products"]) - before
                session.add(Resolution(
                    store=receipt.store, raw_name=line["raw_name"], line_type="product",
                    product_id=product_id, product_ids=[],
                    confirmed_by="identify", confirmed_at=date.today(),
                    source=f"identify {identifying.PROMPT_VERSION}"))
                inputs["resolution"][(shop, line["raw_name"])] = [product_id]
                placed.setdefault(shop, set()).add(product_id)
                if identity.brand:
                    seen.setdefault(shop, set()).add(identity.brand)
                counts["identified"] += 1
                if checkpoint:
                    checkpoint()
                continue
            else:
                proposal = {**proposal, "identity": identity.as_dict()}
        if verdict == "ask":
            session.add(Question(receipt_id=receipt_id, position=position,
                                 raw_name=line["raw_name"], proposal=proposal))
            counts["questions"] += 1
            if checkpoint:
                checkpoint()
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
        inputs["resolution"][(shop, line["raw_name"])] = ids
        placed.setdefault(shop, set()).update(ids)
        seen.setdefault(shop, set()).update(
            b for pid in ids if (b := (inputs["products"].get(pid) or {}).get("brand")))
        counts["families" if family else "accepted"] += 1
        if checkpoint:
            checkpoint()
    session.flush()
    return counts


def reread_product(session: Session, product_id: str,
                   identify: LineIdentifier) -> dict[str, Any]:
    """Read a line the app made a product from again, with the current prompt,
    and fill in the details an older reading dropped. The caller commits.

    2026-10-08: identify v7 read a supplement line's range and strength and
    left both out of the product. Its id stays, so every line and answer placed on
    it stays; the name and the details change, and only when the
    new reading is the same product: the same brand in the same category (a
    name alone is too strict, the reader words `Magnesium Granulat` and
    `Magnesium 400` either way). Anything else is left as it was and said,
    never swapped silently. Only products identify made:
    a shop's listing or a shopper's answer is not this step's to rewrite.
    """
    product = session.get(Product, product_id)
    said = {"product_id": product_id, "changed": False}
    if product is None or (product.provenance or {}).get("attributes") != "identify":
        return {**said, "why": "not a product identify made"}
    entry = session.scalars(select(Resolution).where(Resolution.product_id == product_id)
                            .order_by(Resolution.id)).first()
    if entry is None:
        return {**said, "why": "no line in the memory points at it"}
    for receipt in session.scalars(select(Receipt).order_by(Receipt.id)):
        if store_key(receipt.store) != store_key(entry.store):
            continue
        doc = receipt_to_dict(receipt)
        positions = [i for i, line in enumerate(doc["lines"]) if line["raw_name"] == entry.raw_name]
        if positions:
            break
    else:
        return {**said, "why": f"no receipt prints `{entry.raw_name}`"}
    identity = identify(positions[0], doc, {}, load_normalizer_inputs(session))
    said |= {"raw_name": entry.raw_name,
             "before": {"name": product.name, "details": list(product.details or [])}}
    if not identity.can_tell:
        return {**said, "why": f"the new reading cannot tell: {identity.reason}"}
    if (_fold(identity.brand), _fold(identity.category)) != (_fold(product.brand),
                                                             _fold(product.category)):
        return {**said, "why": f"the new reading is another product: {identity.name}, "
                               f"{identity.brand}, {identity.category}"}
    # Fills in, never empties: a detail only the old reading had stays, after
    # the new ones. One the new reading says anywhere is not kept twice.
    said_now = " ".join([identity.name, *identity.details]).casefold()
    after = {"name": identity.name or product.name,
             "details": [*identity.details,
                         *(d for d in product.details or [] if d.casefold() not in said_now)]}
    if after == said["before"]:
        return {**said, "after": after, "why": "nothing to add"}
    product.name, product.details = after["name"], after["details"]
    if product.label == said["before"]["name"]:
        product.label = product.name  # identify sets the label to the name
    product.provenance = {**(product.provenance or {}),
                          "source": f"identify {identifying.PROMPT_VERSION}"}
    return {**said, "after": after, "changed": True, "why": "filled in"}


def sort_products(session: Session, decider: Any,
                  aldi_shelves: dict[str, str] | None = None,
                  skip: set[str] | frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """Give every product with no category one, where the shop's shelf and a
    model reading the name agree (`categorize.sort`). The caller commits.

    Parham, 2026-10-09: products made from a shop page before the shelf
    tables existed, and products from answers, were never sorted, and 195 EUR
    of the month view sat under "Not sorted yet". `aldi_shelves` is the ALDI
    crawl's article number -> category path: an ALDI URL carries no shelf, so
    the shelf is looked up and recorded on the product (`provenance.shelf`).
    A product whose shelf and name disagree keeps no category and is reported.
    Products in `skip` are left as they are.
    """
    from grocery_app import categories, categorize

    listings = {listing.product_id: {"url": listing.url}
                for listing in session.scalars(select(StoreListing)) if listing.url}
    unsorted = [p for p in session.scalars(select(Product).order_by(Product.id))
                if p.category not in categories.CATEGORIES and p.id not in skip]
    for product in unsorted:
        provenance = product.provenance or {}
        url = provenance.get("source") or ""
        article = url.rsplit("-", 1)[-1] if "aldi-sued.de/produkt/" in url else ""
        if article and not provenance.get("shelf") and (aldi_shelves or {}).get(article):
            product.provenance = {**provenance, "shelf": f"aldi:{aldi_shelves[article]}"}
    as_dicts = {p.id: {"name": p.name, "brand": p.brand, "details": list(p.details or []),
                       "provenance": p.provenance or {}} for p in unsorted}
    named = categorize.read_names(as_dicts, decider)
    report = []
    for product in unsorted:
        shelf = categorize.shop_shelf(product.id, as_dicts[product.id], listings)
        hint = categorize.shelf_meaning(*shelf) if shelf else None
        key, how = categorize.sort(hint, named.get(product.id))
        report.append({"product_id": product.id, "name": product.name, "brand": product.brand,
                       "shelf": ":".join(shelf) if shelf else None, "shelf_says": hint,
                       "name_says": named.get(product.id), "category": key, "how": how})
        if key:
            product.category = key
            product.open_questions = [q for q in product.open_questions or []
                                      if q != categorize.CATEGORY_UNKNOWN]
            product.provenance = {**(product.provenance or {}), "category_from": how}
    return report


# How often the server looks for products with no category.
SORT_EVERY_SECONDS = 60


def sort_new_products(session_factory: Any, decider: Any,
                      tried: set[str]) -> list[dict[str, Any]]:
    """One pass of the server's sorting: every product with no category, but
    those already `tried`, sorted by `sort_products`, and saved.

    The owner, 2026-10-14: a found product showed no category, and a family
    of two such products read "2 candidates". A product made from a shop
    page with no shelf, or from an answer, waited for `db categorize`, a step
    run by hand. Now it is sorted within a minute of being made. One that
    stays unsorted (its shelf and name disagree) is added to `tried`, so the
    model is not asked again until the server's next start."""
    with session_factory() as session:
        report = sort_products(session, decider, skip=tried)
        session.commit()
    tried.update(row["product_id"] for row in report if not row["category"])
    return report


def keep_sorting(session_factory: Any, decider: Any,
                 every: float = SORT_EVERY_SECONDS) -> None:
    """The server's sorting thread: a pass, a pause, for as long as it runs."""
    import logging
    import time

    from grocery_app import spend

    tried: set[str] = set()
    while True:
        try:
            with spend.tagged("finding"):
                sort_new_products(session_factory, decider, tried)
        except Exception:  # noqa: BLE001 - a category is never worth the server
            logging.getLogger(__name__).exception("sorting products failed")
        time.sleep(every)


# How often the server looks for lines a failed search left waiting, and how
# many receipts one pass reads again (each line a reading and a search).
REREAD_EVERY_SECONDS = 300
REREAD_PER_PASS = 5
# A receipt is read again at most this often, each try after the wait since
# the one before: at once, an hour later, a day later; then never by itself.
# Kept on the receipt, so a server that stops and starts pays once.
REREAD_WAITS = (timedelta(0), timedelta(hours=1), timedelta(days=1))
REREAD_TRIES = len(REREAD_WAITS)
# The first pass waits as resuming jobs do: a deploy runs the old server
# for up to ten seconds beside the new one.
REREAD_FIRST_AFTER_SECONDS = 30


def waiting_receipts(session: Session, now: datetime | None = None) -> list[int]:
    """Receipts, oldest first, with a product line nothing placed, asked,
    answered or left out by the shopper: its search failed
    (`identify.unsearched`), or matching stopped part way. Not a receipt from
    a file still being read, nor one tried `REREAD_TRIES` times or whose
    wait (`REREAD_WAITS`) has not passed since its last try.

    The owner, 2026-10-26: 175 lines of old receipts uploaded at once stayed
    grey, with nothing to tap and no question; "the next run reads it again"
    had no next run but the CLI's `--retry-unsearched`.
    """
    from grocery_app.api.jobs import UNFINISHED

    now = now or datetime.now(UTC)
    inputs = load_normalizer_inputs(session)
    taken = {tuple(row) for model in (Question, LineResolution, UncountedLine)
             for row in session.execute(select(model.receipt_id, model.position))}
    # A file with several purchases names only its first receipt on its job;
    # the rest are found by the file and placed by the same job.
    unfinished = session.execute(select(Job.receipt_id, Job.image_sha256, Job.user_id)
                                 .where(Job.status.in_(UNFINISHED))).all()
    waiting = []
    for receipt in session.scalars(select(Receipt).where(Receipt.store.is_not(None))
                                   .order_by(Receipt.id)):
        if any(receipt.id == r or (receipt.image_sha256 == sha and receipt.user_id == u)
               for r, sha, u in unfinished):
            continue
        tries = receipt.reread_tries or 0
        if tries >= REREAD_TRIES or (
                receipt.reread_at and now - receipt.reread_at < REREAD_WAITS[tries]):
            continue
        doc = receipt_to_dict(receipt)
        for position, line in enumerate(doc["lines"]):
            if line.get("type", "product") != "product" or (receipt.id, position) in taken \
                    or never_remembered(receipt.store, line["raw_name"]):
                continue
            record = normalize_receipt({**doc, "lines": [line]}, inputs["resolution"],
                                       inputs["products"])[0]
            if record["resolution"] == "none":
                waiting.append(receipt.id)
                break
    return waiting


def reread_waiting(session_factory: Any, match: LineMatcher, identify: LineIdentifier,
                   now: datetime | None = None) -> list[int]:
    """One pass: the first `REREAD_PER_PASS` waiting receipts, each try
    counted on the receipt before it is made, matched again as a new
    upload's are. Says which."""
    import logging

    from grocery_app import spend

    now = now or datetime.now(UTC)
    with session_factory() as session:
        due = waiting_receipts(session, now)[:REREAD_PER_PASS]
        for receipt in session.scalars(select(Receipt).where(Receipt.id.in_(due))):
            receipt.reread_tries = (receipt.reread_tries or 0) + 1
            receipt.reread_at = now
        session.commit()
    for receipt_id in due:
        try:
            with session_factory() as session, spend.tagged("finding"):
                match_receipt(session, receipt_id, match, identify, checkpoint=session.commit)
                session.commit()
        except Exception:  # noqa: BLE001 - one receipt never stops the others
            logging.getLogger(__name__).exception("reading receipt %s again failed", receipt_id)
    return due


def keep_rereading(session_factory: Any, match: LineMatcher, identify: LineIdentifier,
                   every: float = REREAD_EVERY_SECONDS,
                   first_after: float = REREAD_FIRST_AFTER_SECONDS) -> None:
    """The server's thread for waiting lines: a pass, a pause, while it runs."""
    import logging
    import time

    time.sleep(first_after)
    while True:
        try:
            reread_waiting(session_factory, match, identify)
        except Exception:  # noqa: BLE001 - a waiting line is never worth the server
            logging.getLogger(__name__).exception("reading waiting lines again failed")
        time.sleep(every)


def find_barcodes(session: Session, search: Any) -> list[dict[str, Any]]:
    """Give every packaged product without a barcode the one Open Food Facts
    matches exactly (`barcodes.find`), and say where it came from
    (`provenance.barcode_from`). The report also holds what was not written
    and why. The caller commits.
    """
    from grocery_app import barcodes

    products = {p.id: p for p in session.scalars(select(Product))}
    as_dicts = {p.id: {"name": p.name, "brand": p.brand, "details": list(p.details or []),
                       "size": p.size, "eans": list(p.eans or [])}
                for p in products.values()}
    report = barcodes.find_all(as_dicts, search)
    found_on = datetime.now(UTC).date().isoformat()
    for row in report:
        if row["outcome"] == "found":
            product = products[row["product_id"]]
            product.eans = [row["ean"]]
            product.provenance = {**(product.provenance or {}), "barcode_from": {
                "source": barcodes.FROM, "name": row["name"], "quantity": row["quantity"],
                "found_on": found_on}}
    return report


def drop_unsearched_questions(session: Session) -> set[int]:
    """Delete the open questions no web search narrowed down, and say which
    receipts they were on. The caller commits, then matches those receipts.

    2026-10-09: 25 questions from before search was a step were held back
    from the shopper for being unsearched, and their lines stayed unplaced.
    Matching their receipts again gives each line what a new line gets: the
    shops' products, then a search and a reading, and only then a question. An
    answered question is the shopper's and is never touched.
    """
    receipt_ids = set()
    for question in session.scalars(select(Question).where(Question.answered_at.is_(None))):
        if not ((question.proposal or {}).get("identity") or {}).get("searched"):
            receipt_ids.add(question.receipt_id)
            session.delete(question)
    session.flush()
    return receipt_ids
