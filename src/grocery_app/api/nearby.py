"""Keeping the supermarkets near the shops people use (`grocery_app.nearby`).

What is looked up comes from the people using the app, and nothing about
them leaves the server: for each person, the addresses of the shops on their
receipts (`nearby.shopping_places`). Each shop is placed on the map once and
its surroundings looked up again only after `LOOK_AGAIN_AFTER`, whoever
shops there, so two people at the same GLOBUS cost one look. A shop nobody's
receipts name any more is forgotten with what was found around it.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from grocery_app import nearby
from grocery_app.api.offers import RECENT, everyone
from grocery_app.db.models import NearbyStore, Receipt, ShopPlace
from grocery_app.offers import GERMANY

log = logging.getLogger(__name__)

# Supermarkets open and close rarely; a month is soon enough to notice.
LOOK_AGAIN_AFTER = timedelta(days=30)
LOOK_EVERY_SECONDS = 6 * 3600
# The map's rule: at most one request a second.
PAUSE_BETWEEN_ASKS_S = 1.1
# This many failed asks in a row and the map is taken to be down until the
# next pass; a single failure only skips its own shop.
GIVE_UP_AFTER = 3


def places_for(session: Session, person: Any, today: date) -> list[dict[str, Any]]:
    """The shops one person uses now, by their receipts of the last `RECENT`."""
    mine = (Receipt.user_id.is_(None) if person.user_id is None
            else Receipt.user_id == person.user_id)
    return nearby.shopping_places(session.scalars(
        select(Receipt.store_location).where(mine, Receipt.date >= today - RECENT)))


def forget_unused(repository: Any, session: Session, today: date) -> dict[str, dict[str, Any]]:
    """Delete every shop place nobody uses now, with the stores found around
    it; the shops everyone uses, by key. Run at each pass and when an account
    is deleted, so a deleted person's shops go then, not at the next pass
    (the server may be asleep for days). The caller commits."""
    wanted = {nearby.place_key(a): a for person in everyone(repository, session)
              for a in places_for(session, person, today)}
    for place in session.scalars(select(ShopPlace)):
        if place.key not in wanted:
            session.delete(place)
    session.flush()
    return wanted


def _needs(place: ShopPlace | None, now: datetime) -> tuple[bool, bool]:
    """Whether a shop is to be placed on the map, and whether its
    surroundings are to be looked up: a new shop both; one the map did not
    know, placed again once `LOOK_AGAIN_AFTER` old; a placed one's
    supermarkets once they are that old."""
    stale = now - LOOK_AGAIN_AFTER
    if place is None:
        return True, True
    if place.lat is None:
        return place.located_at <= stale, place.located_at <= stale
    return False, place.stores_at is None or place.stores_at <= stale


def look_up_due(repository: Any, maps: nearby.OpenStreetMap, now: datetime | None = None,
                pause: float | None = None) -> dict[str, int]:
    """One pass: the shops everyone uses, each placed on the map and its
    supermarkets kept, where that is new or `LOOK_AGAIN_AFTER` old. A failed
    ask is skipped and stays due; `GIVE_UP_AFTER` in a row end the pass."""
    now = now or datetime.now(UTC)
    pause = PAUSE_BETWEEN_ASKS_S if pause is None else pause
    today = now.astimezone(GERMANY).date()
    with repository.session_factory() as session:
        wanted = forget_unused(repository, session, today)
        known = {p.key: p for p in session.scalars(select(ShopPlace))}
        todo = sorted(k for k in wanted if any(_needs(known.get(k), now)))
        session.commit()
    asked = failed = in_a_row = found = 0

    def ask(question, *args):
        nonlocal asked
        if pause and asked + failed:
            time.sleep(pause)
        answer = question(*args)
        asked += 1
        return answer

    for key in todo:
        try:
            with repository.session_factory() as session:
                place = session.scalar(select(ShopPlace).where(ShopPlace.key == key))
                locate, around = _needs(place, now)
                if locate:
                    point = ask(maps.locate, wanted[key])
                    if place is None:
                        place = ShopPlace(key=key, postcode=wanted[key]["postcode"])
                        session.add(place)
                    place.street = wanted[key]["street"]
                    place.lat, place.lon = point or (None, None)
                    place.located_at = now
                if around and place.lat is not None:
                    stores = ask(maps.around, place.lat, place.lon)
                    place.stores.clear()
                    session.flush()  # the old rows go before the new, same ids
                    place.stores.extend(NearbyStore(**s) for s in stores)
                    place.stores_at = now
                    found += len(stores)
                session.commit()
            in_a_row = 0
        except nearby.MapUnavailable as exc:
            failed, in_a_row = failed + 1, in_a_row + 1
            log.warning("nearby: %s", exc)
            if in_a_row >= GIVE_UP_AFTER:
                log.warning("nearby: %d failed in a row, trying again next pass", in_a_row)
                break
    return {"due": len(todo), "asked": asked, "failed": failed, "stores": found}


def stores_near(person: Any, today: date) -> dict[str, Any]:
    """One person's shops, and for each chain its branch nearest any of them
    (`nearby.chains_near`). A shop not yet placed on the map, or one the map
    does not know, says so."""
    with person.session_factory() as session:
        shops, stores = [], []
        for address in places_for(session, person, today):
            place = session.scalar(select(ShopPlace).where(
                ShopPlace.key == nearby.place_key(address)))
            shops.append({"street": address["street"], "postcode": address["postcode"],
                          "found": None if place is None else place.lat is not None})
            for store in place.stores if place is not None else []:
                stores.append({"osm_id": store.osm_id, "chain": store.chain,
                               "name": store.name, "address": store.address,
                               "distance_m": store.distance_m,
                               "near": address["street"] or address["postcode"]})
    return {"shops": shops, "stores": nearby.chains_near(stores)}


def keep_looking(repository: Any, maps: nearby.OpenStreetMap,
                 every: float = LOOK_EVERY_SECONDS) -> None:
    """The server's nearby thread: a pass, a pause, for as long as it runs.
    A pass with nothing due costs a database read."""
    while True:
        try:
            if (result := look_up_due(repository, maps))["asked"]:
                log.info("nearby: %s", result)
        except Exception:  # a map is never worth the server
            log.exception("looking up nearby stores failed")
        time.sleep(every)
