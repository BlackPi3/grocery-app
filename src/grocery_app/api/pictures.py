"""Finding pictures for the products on open spot checks, in the background.

The lookup (`grocery_app.pictures`) reads web pages, so it runs on a thread
of its own and never inside a request or a receipt job: a check appears
straight away and its picture within a pass or two. Each product is looked
up once (`picture_checked_at`), found or not.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, sessionmaker

from grocery_app import pictures
from grocery_app.db.io import product_to_dict
from grocery_app.db.models import Check, LineResolution, Product, StoreListing
from grocery_app.resolver import fold

log = logging.getLogger(__name__)

PictureFinder = Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any] | None]
PASS_EVERY_SECONDS = 30


def products_wanting_pictures(session: Session) -> list[str]:
    """Products on open spot checks the app has not looked up yet."""
    answered = select(LineResolution.id).where(
        and_(LineResolution.receipt_id == Check.receipt_id,
             LineResolution.position == Check.position))
    return list(session.scalars(
        select(Check.app_product_id).join(Product, Product.id == Check.app_product_id)
        .where(~answered.exists(), Product.picture_checked_at.is_(None))
        .distinct()))


def fill_pictures(session_factory: sessionmaker[Session], find: PictureFinder,
                  limit: int = 20) -> int:
    """Look up pictures for up to `limit` products; returns how many were looked up."""
    with session_factory() as session:
        product_ids = products_wanting_pictures(session)[:limit]
        for product_id in product_ids:
            product = session.get(Product, product_id)
            listings = [{"store": listing.store, "article_number": listing.article_number,
                         "url": listing.url}
                        for listing in session.scalars(select(StoreListing).where(
                            StoreListing.product_id == product_id).order_by(StoreListing.id))]
            product.picture = find(product_to_dict(product), listings)
            product.picture_checked_at = datetime.now(UTC)
            session.commit()
        return len(product_ids)


def keep_filling(session_factory: sessionmaker[Session], find: PictureFinder,
                 every: float = PASS_EVERY_SECONDS) -> None:
    """The server's picture thread: a pass, a pause, for as long as it runs."""
    while True:
        try:
            fill_pictures(session_factory, find)
        except Exception:  # noqa: BLE001 - a picture is never worth the server
            log.exception("looking up pictures failed")
        time.sleep(every)


def default_finder(products_dir: str | Path = "data/products") -> PictureFinder:
    """The real lookup: shop pages and Open Food Facts over the network, and
    ALDI SÜD's crawl from `products_dir` (read once)."""
    aldi_path = Path(products_dir) / "aldi-sued" / "crawl.json"
    aldi = json.loads(aldi_path.read_text(encoding="utf-8")) if aldi_path.exists() else {}

    def crawled(store: str, article: str) -> dict[str, Any] | None:
        return aldi.get(article) if "aldi" in fold(store) else None

    return partial(pictures.find_picture, fetch_page=pictures.fetch_page, crawled=crawled,
                   fetch_off=pictures.fetch_off)
