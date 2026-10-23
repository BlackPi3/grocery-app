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
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from grocery_app import categories, offers
from grocery_app.db.models import Offer, OfferSearch, Product, Receipt, User
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


def wanted_searches(session: Session, people: list[Any], today: date) -> set[tuple[str, str]]:
    """Every (postcode, word) the people in `people` need: each person's
    shop postcodes with each of their regular groceries' names.

    `people` holds a repository per person (`PostgresRepository.as_user`):
    their purchases are read the way their own pages read them."""
    since = today - RECENT
    wanted: set[tuple[str, str]] = set()
    for person in people:
        mine = (Receipt.user_id.is_(None) if person.user_id is None
                else Receipt.user_id == person.user_id)
        locations = session.scalars(select(Receipt.store_location)
                                    .where(mine, Receipt.date >= since))
        postcodes = offers.shopping_postcodes(locations)
        if not postcodes:
            continue
        rows = [r for r in _product_rows(person.purchases()["purchases"])
                if r.get("date") and date.fromisoformat(r["date"]) >= since
                and r.get("category") in categories.CATEGORIES
                and categories.is_grocery(r["category"])]
        ids = [r["product_id"] for r in regulars(rows, today)]
        names = dict(session.execute(select(Product.id, Product.name)
                                     .where(Product.id.in_(ids))).all()) if ids else {}
        words = {w for w in map(offers.search_word, names.values()) if w}
        wanted |= {(postcode, word) for postcode in postcodes for word in words}
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
    search = session.scalar(select(OfferSearch).where(OfferSearch.postcode == postcode,
                                                      OfferSearch.word == word))
    if search is None:
        search = OfferSearch(postcode=postcode, word=word)
        session.add(search)
    search.searched_at, search.found = now, len(found)
    session.flush()
    return new


def fetch_due(repository: Any, source: offers.Marktguru, now: datetime | None = None,
              pause: float = PAUSE_BETWEEN_SEARCHES_S) -> dict[str, int]:
    """One pass: work out what everyone needs, search what is due, keep what
    is found. A failed search is skipped and stays due; `GIVE_UP_AFTER` in a
    row end the pass."""
    now = now or datetime.now(UTC)
    today = now.astimezone(offers.GERMANY).date()
    with repository.session_factory() as session:
        people = [repository.as_user(None)] + [
            repository.as_user({"id": u.id, "name": u.name})
            for u in session.scalars(select(User).order_by(User.id))]
        todo = due(session, wanted_searches(session, people, today), now)
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


def keep_fetching(repository: Any, source: offers.Marktguru,
                  every: float = FETCH_EVERY_SECONDS) -> None:
    """The server's offers thread: a pass, a pause, for as long as it runs.
    Each pass searches only what is a day old, so an hourly pass costs a
    database read when nothing is due, and a server that slept all night
    catches up when it wakes."""
    while True:
        try:
            if (result := fetch_due(repository, source))["searched"]:
                log.info("offers: %s", result)
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
