"""What each chain sells, kept in the database from its downloads.

A download (`crawl.json`) is compared with what we hold, and only what changed
is written, so the tables grow with changes and not with downloads
(`docs/designs/products-and-resolutions.md`):

- a new product gets a row;
- a changed price gets a dated entry, and a price is never overwritten;
- a changed name, brand, pack size or the like is updated;
- a product the download no longer holds is marked gone, and unmarked if it
  comes back. A row is never deleted;
- an unchanged product writes nothing but the day it was last seen.

A product is marked gone only when the caller says the download was complete,
so a failed page does not make a shelf look discontinued.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from grocery_app import traps
from grocery_app.db.models import ChainPrice, ChainProduct
from grocery_app.resolver import store_key

# Columns every chain's download has; anything else stays in `extra`.
SHARED = ("ean", "name", "brand", "pack_size", "category", "url")
NOT_EXTRA = (*SHARED, "article_number", "price", "fetched_at")
CHUNK = 1000
# More of a chain than this vanishing at once looks like a broken download, not
# a change of range. Not measured: no two complete downloads of GLOBUS exist yet.
MOST_GONE_AT_ONCE = 0.2


class OlderDownload(ValueError):
    """A download older than what we hold would move "last seen" backwards."""


def seen_on_of(listings: Iterable[dict[str, Any]]) -> date | None:
    """The day a download was finished: its newest row's `fetched_at`."""
    days = [str(row["fetched_at"])[:10] for row in listings if row.get("fetched_at")]
    return date.fromisoformat(max(days)) if days else None


def _price(row: dict[str, Any]) -> Decimal | None:
    value = row.get("price")
    return None if value is None else Decimal(str(value)).quantize(Decimal("0.01"))


def _fields(row: dict[str, Any]) -> dict[str, Any]:
    return {**{key: row.get(key) for key in SHARED},
            "extra": {k: v for k, v in row.items() if k not in NOT_EXTRA}}


def _chunks(rows: list[Any]) -> Iterable[list[Any]]:
    return (rows[i:i + CHUNK] for i in range(0, len(rows), CHUNK))


def load_download(session: Session, chain: str, listings: dict[str, dict[str, Any]],
                  seen_on: date, complete: bool = False) -> dict[str, int]:
    """Bring one chain's rows up to date with a download. The caller commits.

    `listings` is article number -> row, as a `crawl.json` holds them.
    """
    chain = store_key(chain)
    held = {r.article_number: r for r in session.execute(select(
        ChainProduct.id, ChainProduct.article_number, ChainProduct.last_seen,
        ChainProduct.gone_since, ChainProduct.extra,
        *[getattr(ChainProduct, key) for key in SHARED]).where(ChainProduct.chain == chain))}
    if held and seen_on < max(r.last_seen for r in held.values()):
        raise OlderDownload(f"{chain}: {seen_on} is older than what is held")
    latest = dict(session.execute(
        select(ChainPrice.chain_product_id, ChainPrice.price)
        .join(ChainProduct, ChainProduct.id == ChainPrice.chain_product_id)
        .where(ChainProduct.chain == chain)
        .distinct(ChainPrice.chain_product_id)
        .order_by(ChainPrice.chain_product_id, ChainPrice.seen_on.desc())).all())

    counts = {"new": 0, "prices": 0, "changed": 0, "gone": 0, "back": 0, "unchanged": 0}
    new_rows: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    prices: list[dict[str, Any]] = []
    seen_ids: list[int] = []
    back: list[int] = []

    for article, row in listings.items():
        if not row.get("name"):
            counts["skipped"] = counts.get("skipped", 0) + 1
            continue
        was = held.get(article)
        if was is None:
            new_rows.append({"chain": chain, "article_number": article, "first_seen": seen_on,
                             "last_seen": seen_on, **_fields(row)})
            continue
        seen_ids.append(was.id)
        fields = _fields(row)
        different = any(getattr(was, key) != value for key, value in fields.items())
        if different:
            changed.append({"row_id": was.id, **fields})
            counts["changed"] += 1
        if was.gone_since is not None:
            back.append(was.id)
            counts["back"] += 1
        price = _price(row)
        moved = price is not None and latest.get(was.id) != price
        if moved:
            prices.append({"chain_product_id": was.id, "seen_on": seen_on, "price": price})
            counts["prices"] += 1
        if not different and not moved and was.gone_since is None:
            counts["unchanged"] += 1

    for chunk in _chunks(new_rows):
        made = session.execute(insert(ChainProduct).returning(
            ChainProduct.id, ChainProduct.article_number), chunk).all()
        for product_id, article in made:
            price = _price(listings[article])
            if price is not None:
                prices.append({"chain_product_id": product_id, "seen_on": seen_on,
                               "price": price})
    counts["new"] = len(new_rows)

    if changed:
        session.connection().execute(
            update(ChainProduct).where(ChainProduct.id == bindparam("row_id")).values(
                **{key: bindparam(key) for key in (*SHARED, "extra")}), changed)
    for chunk in _chunks(prices):
        statement = pg_insert(ChainPrice).values(chunk)
        session.execute(statement.on_conflict_do_update(
            index_elements=["chain_product_id", "seen_on"],
            set_={"price": statement.excluded.price}))
    for chunk in _chunks(seen_ids):
        session.execute(update(ChainProduct).where(ChainProduct.id.in_(chunk))
                        .values(last_seen=seen_on))
    for chunk in _chunks(back):
        session.execute(update(ChainProduct).where(ChainProduct.id.in_(chunk))
                        .values(gone_since=None))

    if complete:
        named = {article for article, row in listings.items() if row.get("name")}
        missing = [r.id for article, r in held.items()
                   if article not in named and r.gone_since is None]
        standing = sum(1 for r in held.values() if r.gone_since is None)
        if standing and len(missing) / standing > MOST_GONE_AT_ONCE:
            # Marks nothing: a broken download must not end a whole range.
            traps.fire("chain-download-shrank", chain=chain, missing=len(missing),
                       held=standing)
            counts["refused_gone"] = len(missing)
        else:
            for chunk in _chunks(missing):
                session.execute(update(ChainProduct).where(ChainProduct.id.in_(chunk))
                                .values(gone_since=seen_on))
            counts["gone"] = len(missing)
    session.flush()
    return counts
