"""Finding, keeping and refreshing every product's picture, in the background.

A picture is part of the product (Parham, 2026-10-10): every product gets one
soon after it is found, the app keeps its own copy of the photo (named by its
sha256, like receipt photos, in `data/pictures`), and looks again after
`REFRESH_AFTER` in case the shop shows a new pack. Products on open spot
checks go first.

The lookup (`grocery_app.pictures`) reads web pages, so it runs on a thread
of its own and never inside a request or a receipt job: a product appears
straight away and its picture within a pass or two. A product with no
picture anywhere is looked up again only when its picture is due anyway.
"""

from __future__ import annotations

import io
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from grocery_app import pictures, spend
from grocery_app.api.images import DiskImageStore, ImageStore, looks_like_an_image, sha256_of
from grocery_app.db.io import product_to_dict
from grocery_app.db.models import Check, LineResolution, Product, StoreListing
from grocery_app.resolver import fold

log = logging.getLogger(__name__)

PictureFinder = Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any] | None]
PASS_EVERY_SECONDS = 30
# "3 or 6 months" (Parham, 2026-10-10): six, so each shop is asked half as often.
REFRESH_AFTER = timedelta(days=182)
# How long a spot check waits for its picture before it shows without one: a
# web search takes half a minute and a pass comes every 30 s, so ten minutes
# means the lookup is not coming.
CHECK_WAITS_UP_TO = timedelta(minutes=10)
PICTURE_PATH = "/pictures/{file}"
DEFAULT_ROOT = "data/pictures"
ENV_VAR = "GROCERY_PICTURES"


@dataclass
class Pictures:
    """What the server needs to give products pictures: where to find one,
    how to fetch its bytes, and where to keep them."""

    find: PictureFinder
    download: Callable[[str], bytes]
    store: ImageStore


def shown(picture: dict[str, Any] | None) -> dict[str, Any] | None:
    """A product's picture as the API shows it: our own copy's address."""
    if not picture or not picture.get("file"):
        return None
    return {"url": PICTURE_PATH.format(file=picture["file"]), "from": picture.get("from"),
            "page": picture.get("page")}


def media_type(data: bytes) -> str:
    try:
        kind = Image.open(io.BytesIO(data)).format or ""
    except OSError:
        kind = ""
    return Image.MIME.get(kind, "application/octet-stream")


def products_wanting_pictures(session: Session, now: datetime | None = None) -> list[str]:
    """Products whose picture is due: never looked up, looked up longer than
    `REFRESH_AFTER` ago, or found before the app kept copies. Those on open
    spot checks first, then those a shop or a barcode gives a picture for in
    a second; a web search takes half a minute, so those come last."""
    now = now or datetime.now(UTC)
    answered = select(LineResolution.id).where(
        and_(LineResolution.receipt_id == Check.receipt_id,
             LineResolution.position == Check.position))
    on_checks = set(session.scalars(select(Check.app_product_id).where(~answered.exists())))
    listed = set(session.scalars(select(StoreListing.product_id)))
    due = session.execute(select(Product.id, Product.eans).where(or_(
        Product.picture_checked_at.is_(None),
        Product.picture_checked_at < now - REFRESH_AFTER,
        and_(Product.picture.is_not(None), Product.picture["file"].astext.is_(None)),
    )).order_by(Product.id)).all()
    return [product_id for product_id, eans in sorted(due, key=lambda row: (
        row[0] not in on_checks, row[0] not in listed and not row[1]))]


def fill_pictures(session_factory: sessionmaker[Session], service: Pictures,
                  limit: int = 20, now: datetime | None = None) -> int:
    """Look up pictures for up to `limit` due products; returns how many.

    A photo found is fetched and kept. When a look finds nothing, or the
    photo cannot be fetched, a picture the product already has stays: an old
    pack beats no pack.
    """
    with session_factory() as session:
        product_ids = products_wanting_pictures(session, now)[:limit]
        for product_id in product_ids:
            product = session.get(Product, product_id)
            listings = [{"store": listing.store, "article_number": listing.article_number,
                         "url": listing.url}
                        for listing in session.scalars(select(StoreListing).where(
                            StoreListing.product_id == product_id).order_by(StoreListing.id))]
            found = service.find(product_to_dict(product), listings)
            if found:
                try:
                    data = service.download(found["url"])
                except (OSError, ValueError):
                    data = b""
                if looks_like_an_image(data):
                    digest = sha256_of(data)
                    service.store.put(digest, data)
                    product.picture = {"file": digest, "from": found["from"],
                                       "page": found.get("page"), "source": found["url"]}
            if product.picture and not product.picture.get("file"):
                product.picture = None  # found before copies were kept, and not again
            product.picture_checked_at = now or datetime.now(UTC)
            session.commit()
        return len(product_ids)


def keep_filling(session_factory: sessionmaker[Session], service: Pictures,
                 every: float = PASS_EVERY_SECONDS) -> None:
    """The server's picture thread: a pass, a pause, for as long as it runs."""
    while True:
        try:
            with spend.tagged("pictures"):
                fill_pictures(session_factory, service)
        except Exception:  # noqa: BLE001 - a picture is never worth the server
            log.exception("looking up pictures failed")
        time.sleep(every)


def limited(search: Callable[[str], list[str]], most: int) -> Callable[[str], list[str]]:
    """`search`, until it has run `most` times; then nothing is searched.
    Each search is paid for, so a fault cannot spend without limit."""
    count = 0

    def run(text: str) -> list[str]:
        nonlocal count
        if count >= most:
            return []
        count += 1
        return search(text)

    return run


def default_pictures(products_dir: str | Path = "data/products",
                     model: str | None = None) -> Pictures:
    """The real thing: shop pages, Open Food Facts and (with Gemini set up) a
    web search over the network, ALDI SÜD's crawl from `products_dir` (read
    once), copies kept under `GROCERY_PICTURES` (else `data/pictures`). At
    most `GROCERY_MAX_PICTURE_SEARCHES` searches (300 unless set) per run."""
    from grocery_app import gemini

    aldi_path = Path(products_dir) / "aldi-sued" / "crawl.json"
    aldi = json.loads(aldi_path.read_text(encoding="utf-8")) if aldi_path.exists() else {}

    def crawled(store: str, article: str) -> dict[str, Any] | None:
        return aldi.get(article) if "aldi" in fold(store) else None

    search = (limited(pictures.gemini_search(model),
                      int(os.environ.get("GROCERY_MAX_PICTURE_SEARCHES", "300")))
              if model and gemini.configured() else None)
    find = partial(pictures.find_picture, fetch_page=pictures.fetch_page, crawled=crawled,
                   fetch_off=pictures.fetch_off, search=search)
    return Pictures(find=find, download=pictures.fetch_bytes,
                    store=DiskImageStore(os.environ.get(ENV_VAR, DEFAULT_ROOT)))
