"""Keeping the weekly offers near the shops people visit (`grocery_app.offers`).

What is searched comes from the people using the app, and nothing about
them leaves the server: for each person, the postcodes of the shops on their
receipts (`offers.shopping_postcodes`) and the names of the products they
buy regularly (`insights.regulars`, groceries only), searched as words. Each
pair is looked up at most once a day (`offer_searches`), whoever needs it,
so two people who shop at the same place cost one search.

Every offer found is kept with when it was first and last seen. The first
sighting before an offer starts is what tells, after a couple of weeks, on
which weekday each chain publishes (`offers.rhythm`, `GET /v1/offers/rhythm`).

After each pass, a model judges which of the offers a product's word found
are that product or its kind (`offer_match.judge`), once per product and
offer, and a person's offers for the coming week are worked out from those
verdicts when asked (`offers_for`, `GET /v1/offers`).
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from grocery_app import categories, offer_match, offers
from grocery_app.db.models import Offer, OfferSearch, OfferVerdict, Product, Receipt, User
from grocery_app.insights import _product_rows, regulars

log = logging.getLogger(__name__)

# A shop or a habit older than this is not where or what someone shops now.
RECENT = timedelta(days=90)
# A search is made again once this old: the chains publish once a week, but
# on different days, and a daily look is what finds each one's day.
SEARCH_AGAIN_AFTER = timedelta(hours=20)
FETCH_EVERY_SECONDS = 3600
PAUSE_BETWEEN_SEARCHES_S = 1.0
# This many failed searches in a row and the source is taken to be down
# until the next pass; a single failure only skips its own search.
GIVE_UP_AFTER = 3
# Offers that ended this long ago are of no use to the tile, but are kept
# that long for the rhythm.
KEEP_ENDED = timedelta(days=60)
# "The coming week": offers running on any day from today to this many after.
WEEK_AHEAD = timedelta(days=7)


def shopping(session: Session, person: Any, today: date) -> dict[str, Any]:
    """Where and what one person shops now: `postcodes` (`offers.shopping_postcodes`)
    and `regulars`, product id -> {"product", "word", "rows"}: their regular
    groceries in the last `RECENT`, each with the catalog's product, its
    search word (the flyer's word when one was given, else the name) and
    their purchases of it. `person` is a repository as that
    person sees it (`PostgresRepository.as_user`)."""
    since = today - RECENT
    mine = (Receipt.user_id.is_(None) if person.user_id is None
            else Receipt.user_id == person.user_id)
    postcodes = offers.shopping_postcodes(session.scalars(
        select(Receipt.store_location).where(mine, Receipt.date >= since)))
    if not postcodes:
        return {"postcodes": [], "regulars": {}}
    rows = [r for r in _product_rows(person.purchases()["purchases"])
            if r.get("date") and date.fromisoformat(r["date"]) >= since
            and r.get("category") in categories.CATEGORIES
            and categories.is_grocery(r["category"])]
    ids = [r["product_id"] for r in regulars(rows, today)]
    found = {}
    for product in session.scalars(select(Product).where(Product.id.in_(ids))) if ids else []:
        if word := product.offer_word or offers.search_word(product.name):
            found[product.id] = {
                "product": {"name": product.name, "brand": product.brand,
                            "details": list(product.details or []), "size": product.size},
                "word": word, "rows": [r for r in rows if r["product_id"] == product.id]}
    return {"postcodes": postcodes, "regulars": found}


def everyone(repository: Any, session: Session) -> list[Any]:
    """A repository per person: the owner, then each user."""
    return [repository.as_user(None)] + [
        repository.as_user({"id": u.id, "name": u.name})
        for u in session.scalars(select(User).order_by(User.id))]


def wanted_searches(session: Session, people: list[Any], today: date) -> set[tuple[str, str]]:
    """Every (postcode, word) the people in `people` need: each person's
    shop postcodes with each of their regular groceries' names."""
    wanted: set[tuple[str, str]] = set()
    for person in people:
        mine = shopping(session, person, today)
        wanted |= {(postcode, regular["word"]) for postcode in mine["postcodes"]
                   for regular in mine["regulars"].values()}
    return wanted


def due(session: Session, wanted: set[tuple[str, str]], now: datetime) -> list[tuple[str, str]]:
    """The searches in `wanted` not made in the last `SEARCH_AGAIN_AFTER`.
    A search nobody wants any more is forgotten: once a person's account is
    gone, or they stop buying a thing, nothing kept points at them."""
    recent = set()
    for search in session.scalars(select(OfferSearch)):
        if (search.postcode, search.word) not in wanted:
            session.delete(search)
        elif search.searched_at > now - SEARCH_AGAIN_AFTER:
            recent.add((search.postcode, search.word))
    session.flush()
    return sorted(wanted - recent)


def keep(session: Session, postcode: str, word: str, found: list[dict[str, Any]],
         now: datetime) -> int:
    """Save one search's offers and that it was made; how many were new.
    The caller commits."""
    known = {o.source_id: o for o in session.scalars(
        select(Offer).where(Offer.postcode == postcode,
                            Offer.source_id.in_([f["id"] for f in found])))} if found else {}
    new = 0
    for record in found:
        row = known.get(record["id"])
        if row is None:
            row = Offer(source=record["source"], source_id=record["id"], postcode=postcode,
                        first_seen_at=now)
            session.add(row)
            known[record["id"]] = row
            new += 1
        row.chain = record["chain"]
        row.valid_from = date.fromisoformat(record["valid_from"])
        row.valid_to = date.fromisoformat(record["valid_to"])
        row.record = record
        row.last_seen_at = now
        if word not in (row.words or []):
            row.words = [*(row.words or []), word]
    search = session.scalar(select(OfferSearch).where(OfferSearch.postcode == postcode,
                                                      OfferSearch.word == word))
    if search is None:
        search = OfferSearch(postcode=postcode, word=word)
        session.add(search)
    search.searched_at, search.found = now, len(found)
    session.flush()
    return new


def fetch_due(repository: Any, source: offers.Marktguru, now: datetime | None = None,
              pause: float | None = None) -> dict[str, int]:
    """One pass: work out what everyone needs, search what is due, keep what
    is found. A failed search is skipped and stays due; `GIVE_UP_AFTER` in a
    row end the pass."""
    now = now or datetime.now(UTC)
    pause = PAUSE_BETWEEN_SEARCHES_S if pause is None else pause
    today = now.astimezone(offers.GERMANY).date()
    with repository.session_factory() as session:
        todo = due(session, wanted_searches(session, everyone(repository, session), today), now)
        session.commit()
    done = failed = in_a_row = new = 0
    try:
        for postcode, word in todo:
            if pause and done + failed:
                time.sleep(pause)
            try:
                found = source.search(word, postcode)
            except offers.OffersUnavailable as exc:
                failed, in_a_row = failed + 1, in_a_row + 1
                log.warning("offers: %s", exc)
                if in_a_row >= GIVE_UP_AFTER:
                    log.warning("offers: %d failed in a row, trying again next pass", in_a_row)
                    break
                continue
            in_a_row = 0
            with repository.session_factory() as session:
                new += keep(session, postcode, word, found, now)
                session.commit()
            done += 1
    finally:
        with repository.session_factory() as session:
            session.query(Offer).filter(Offer.valid_to < today - KEEP_ENDED).delete()
            session.commit()
    return {"due": len(todo), "searched": done, "failed": failed, "new_offers": new}


def candidates(session: Session, postcodes: list[str], word: str,
               today: date) -> list[dict[str, Any]]:
    """The offers `word` found near any of `postcodes` that run on a day of
    the coming week, each once."""
    rows = session.scalars(select(Offer).where(
        Offer.postcode.in_(postcodes), Offer.words.any(word),
        Offer.valid_to >= today, Offer.valid_from <= today + WEEK_AHEAD).order_by(Offer.id))
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        # An offer kept before `offers.brand_of` may still carry the no-brand mark.
        seen.setdefault(row.source_id, {**row.record,
                                        "brand": offers.brand_of(row.record.get("brand"))})
    return list(seen.values())


def _verdicts(session: Session, product_ids: list[str]) -> dict[tuple[str, str], str]:
    return {(v.product_id, v.source_id): v.verdict for v in session.scalars(
        select(OfferVerdict).where(OfferVerdict.product_id.in_(product_ids)))
    } if product_ids else {}


def judge_due(repository: Any, decider: Any, today: date,
              asked: Counter | None = None) -> int:
    """Have the model judge the offers of the coming week that a person's
    regular product's word found and that have no verdict for that product
    yet; how many verdicts were made. Each (product, offer) is judged once,
    whoever buys the product, and at most `offer_match.MOST_CANDIDATES` of a
    product's offers are judged for one week. Each batch is kept as soon as
    it is answered. `asked` counts, across passes, the answers that left a
    pair out: one left out `MOST_ASKS` times is not asked again. A call that
    failed counts for nothing; its pairs are asked again next pass."""
    asked = Counter() if asked is None else asked
    with repository.session_factory() as session:
        products: dict[str, dict[str, Any]] = {}
        words: dict[str, str] = {}
        todo: dict[str, dict[str, dict[str, Any]]] = {}
        for person in everyone(repository, session):
            mine = shopping(session, person, today)
            for pid, regular in mine["regulars"].items():
                products[pid], words[pid] = regular["product"], regular["word"]
                for offer in candidates(session, mine["postcodes"], regular["word"], today):
                    todo.setdefault(pid, {})[offer["id"]] = offer
        judged = _verdicts(session, list(todo))
        unjudged = {}
        for pid, found in todo.items():
            room = offer_match.MOST_CANDIDATES - sum((pid, oid) in judged for oid in found)
            waiting = [o for oid, o in found.items() if (pid, oid) not in judged
                       and asked[(pid, oid)] < offer_match.MOST_ASKS]
            if room > 0 and waiting:
                unjudged[pid] = offer_match.shortlist(words[pid], waiting, most=room)
    made = 0
    for put, said in offer_match.judge_batches(products, unjudged, decider):
        for pair in put - said.keys():
            asked[pair] += 1
        with repository.session_factory() as session:
            for (pid, offer_id), verdict in said.items():
                session.add(OfferVerdict(product_id=pid, source=offers.SOURCE,
                                         source_id=offer_id, verdict=verdict,
                                         judged_by=offer_match.JUDGE_VERSION))
            session.commit()
        made += len(said)
    return made


def word_due(repository: Any, decider: Any, today: date,
             asked: Counter | None = None) -> int:
    """Have the model give each regular product with no flyer word yet its
    word (`offer_match.flyer_words`); how many were given. Each batch is
    kept as soon as it is answered. `asked` counts, across passes, the
    answers that gave a product none: one left `offer_match.MOST_ASKS` times
    is searched by its name until the server starts anew."""
    asked = Counter() if asked is None else asked
    with repository.session_factory() as session:
        people = everyone(repository, session)
        ids = {pid for person in people for pid in shopping(session, person, today)["regulars"]}
        products = {p.id: {"name": p.name, "brand": p.brand, "details": list(p.details or []),
                           "size": p.size}
                    for p in session.scalars(select(Product).where(
                        Product.id.in_(ids), Product.offer_word.is_(None)))
                    if asked[p.id] < offer_match.MOST_ASKS} if ids else {}
    made = 0
    for put, said in offer_match.flyer_words(products, decider):
        for pid in put - said.keys():
            asked[pid] += 1
        with repository.session_factory() as session:
            for product in session.scalars(select(Product).where(Product.id.in_(said))):
                product.offer_word = said[product.id]
                product.offer_word_by = offer_match.WORDS_VERSION
            session.commit()
        made += len(said)
    return made


def offers_for(person: Any, today: date) -> list[dict[str, Any]]:
    """One person's offers for the coming week: for each regular grocery,
    the judged offers near their shops that are that product or its kind and
    cheaper than they usually pay (`offer_match.match`). Their own product
    first, then the biggest saving."""
    with person.session_factory() as session:
        mine = shopping(session, person, today)
        verdicts = _verdicts(session, list(mine["regulars"]))
        out = []
        for pid, regular in mine["regulars"].items():
            for offer in candidates(session, mine["postcodes"], regular["word"], today):
                found = offer_match.match(regular["product"], regular["rows"], offer,
                                          verdicts.get((pid, offer["id"]), "unjudged"))
                if found:
                    out.append({"product_id": pid, "product": regular["product"]["name"],
                                "brand": regular["product"]["brand"], **found})
    out.sort(key=lambda m: (m["label"] != offer_match.LABELS["same_product"],
                            -((m["saving"] or {}).get("share") or 0.0),
                            m["product"], m["offer"]["chain"], m["offer"]["id"]))
    return out


def keep_fetching(repository: Any, source: offers.Marktguru, judge: Any = None,
                  every: float = FETCH_EVERY_SECONDS) -> None:
    """The server's offers thread: a pass, a pause, for as long as it runs.
    Each pass searches only what is a day old, so an hourly pass costs a
    database read when nothing is due, and a server that slept all night
    catches up when it wakes. With a `judge`, new offers are judged after."""
    from grocery_app import spend

    asked: Counter = Counter()
    unnamed: Counter = Counter()
    while True:
        if judge is not None:
            try:  # without a word a product is searched by its name
                with spend.tagged("other"):
                    today = datetime.now(UTC).astimezone(offers.GERMANY).date()
                    if named := word_due(repository, judge, today, unnamed):
                        log.info("offers: %d search words", named)
            except Exception:
                log.exception("naming products for the offers failed")
        try:
            if (result := fetch_due(repository, source))["searched"]:
                log.info("offers: %s", result)
            if judge is not None:
                with spend.tagged("other"):
                    today = datetime.now(UTC).astimezone(offers.GERMANY).date()
                    if judged := judge_due(repository, judge, today, asked):
                        log.info("offers: %d verdicts", judged)
        except Exception:  # an offer is never worth the server
            log.exception("fetching offers failed")
        time.sleep(every)


def rhythm(session: Session) -> list[dict[str, Any]]:
    """`offers.rhythm` over every offer kept, each once however many
    postcodes it was seen near, at its first sighting anywhere."""
    first = (select(Offer.chain, Offer.valid_from, func.min(Offer.first_seen_at))
             .group_by(Offer.source, Offer.source_id, Offer.chain, Offer.valid_from))
    return offers.rhythm({"chain": chain, "valid_from": valid_from, "first_seen": seen}
                         for chain, valid_from, seen in session.execute(first))
