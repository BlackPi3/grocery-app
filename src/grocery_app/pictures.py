"""Pictures of products, so a spot check can be answered at a glance.

Parham, 2026-10-08: days after the shop, "Was it this one?" over a product
name rings no bell, and he pasted the name into a browser to find out. A
photo of the pack settles it.

Where a picture comes from, in order (his rule: general for every user, not
built around his shops):

1. The shop the product is listed at: its product page names the pack's
   photo in its schema.org data (`@type: Product`, `image`). That holds for
   GLOBUS and for most web shops. ALDI SÜD turns away a program asking for a
   page, so ALDI's photo comes from the crawl of its product API instead
   (`image_url` in its `crawl.json`).
2. Open Food Facts, by the product's barcode.

A product with neither gets no picture. A line known only as a kind of
thing (`Sandkuchen`) has no listing and no barcode, so it never gets a stock
photo that would claim more than the app knows.

The picture is the shop's own address, not a copy: the phone loads it from
the shop, as a browser would on the product page.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

PICTURE_FROM_OFF = "Open Food Facts"
OFF_PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{ean}.json?fields=image_front_small_url"
OFF_PAGE_URL = "https://world.openfoodfacts.org/product/{ean}"
USER_AGENT = "grocery-app/0.1 (https://github.com/BlackPi3/grocery-app)"


def picture_on_page(html: str) -> str | None:
    """The product photo a page names in its schema.org Product data, or None."""
    for block in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>",
                            html, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("@graph") or [data]
        else:
            items = []
        for item in items:
            if not isinstance(item, dict) or item.get("@type") != "Product":
                continue
            image = item.get("image")
            if isinstance(image, list):
                image = next((i for i in image if isinstance(i, str)), None)
            if isinstance(image, dict):
                image = image.get("url")
            if isinstance(image, str) and image.startswith("http"):
                return image
    return None


def find_picture(product: dict[str, Any], listings: list[dict[str, Any]], *,
                 fetch_page: Callable[[str], str],
                 crawled: Callable[[str, str], dict[str, Any] | None],
                 fetch_off: Callable[[str], str | None]) -> dict[str, Any] | None:
    """`{"url", "from", "page"}` for one product, or None.

    `listings` are the product's shop listings (`store`, `article_number`,
    `url`), the shop it was first found at first. `crawled(store, article)`
    is a crawled record of that shop's, if the app has one; `fetch_page`
    reads a page, `fetch_off` gives Open Food Facts' photo for a barcode.
    Each may raise; a source that fails is passed over.
    """
    for listing in listings:
        record = crawled(listing["store"], listing["article_number"]) or {}
        url = record.get("image_url")
        if not url and listing.get("url") and "aldi-sued.de" not in listing["url"]:
            try:
                url = picture_on_page(fetch_page(listing["url"]))
            except (OSError, ValueError):
                url = None
        if url:
            return {"url": url, "from": listing["store"], "page": listing.get("url")}
    for ean in product.get("eans") or []:
        try:
            url = fetch_off(ean)
        except (OSError, ValueError):
            url = None
        if url:
            return {"url": url, "from": PICTURE_FROM_OFF, "page": OFF_PAGE_URL.format(ean=ean)}
    return None


# --- the network, for the server ------------------------------------------------

def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def fetch_page(url: str) -> str:
    return _get(url).decode("utf-8", errors="replace")


def fetch_off(ean: str) -> str | None:
    try:
        doc = json.loads(_get(OFF_PRODUCT_URL.format(ean=ean)))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return (doc.get("product") or {}).get("image_front_small_url")
