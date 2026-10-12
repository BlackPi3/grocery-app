"""Pictures of products: a photo of the pack is part of what a product is.

Parham, 2026-10-08: days after the shop, "Was it this one?" over a product
name rings no bell, and he pasted the name into a browser to find out. A
photo of the pack settles it. 2026-10-10: every product gets one when it is
found, the app keeps its own copy, and looks again after six months in case
the pack changed.

Where a picture comes from, in order (his rule: general for every user, not
built around his shops):

1. The shop the product is listed at: its product page names the pack's
   photo in its schema.org data (`@type: Product`, `image`). That holds for
   GLOBUS and for most web shops. ALDI SÜD turns away a program asking for a
   page, so ALDI's photo comes from the crawl of its product API instead
   (`image_url` in its `crawl.json`).
2. Open Food Facts, by the product's barcode.
3. A web search for the product, for one with a brand but neither of the
   above, whose name was read from a receipt line (`SEARCHED_KINDS`: what
   `identify` found on the web, or what the shopper described). The first
   catalog's English names ("Plant-based drink") and the coarse,
   category-level products would match no German page, or one variant
   passed off as the product, so they are not searched. Only pages the search returned
   are read, never an address a model wrote, and a page's photo is taken only
   when the product it describes has our product's brand and most of its
   name (`same_product`).

A product with none of these gets no picture. A line known only as a kind of
thing (`Sandkuchen`) has no listing, no barcode and no brand, so it never
gets a stock photo that would claim more than the app knows.

A search that could not be made (it failed, or the run's budget is spent)
is not a search that found nothing: `find_picture` raises `LookupFailed`, and
the product is looked up again rather than marked as having no picture for
six months. 2026-10-12: three of the demo's 18 branded products were left
without a picture that way, each after two timed-out tries.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from grocery_app.resolver import fold

log = logging.getLogger(__name__)

PICTURE_FROM_OFF = "Open Food Facts"
PICTURE_FROM_SEARCH = "web search"
SEARCHED_KINDS = {"identify", "shopper"}  # `provenance.attributes`
OFF_PRODUCT_URL = ("https://world.openfoodfacts.org/api/v2/product/{ean}.json"
                   "?fields=image_front_url")
OFF_PAGE_URL = "https://world.openfoodfacts.org/product/{ean}"
USER_AGENT = "grocery-app/0.1 (https://github.com/BlackPi3/grocery-app)"


class LookupFailed(Exception):
    """A web search for a product's picture could not be made: nothing was
    learnt, so the product is not marked as looked up."""


def product_on_page(html: str) -> dict[str, str | None] | None:
    """The product a page describes in its schema.org data: `name`, `brand`
    and the photo `image`, or None when it describes none with a photo."""
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
                image = next((i for i in image if isinstance(i, (str, dict))), None)
            if isinstance(image, dict):
                image = image.get("url") or image.get("contentUrl")
            if not (isinstance(image, str) and image.startswith("http")):
                continue
            brand = item.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")
            return {"name": item.get("name") if isinstance(item.get("name"), str) else None,
                    "brand": brand if isinstance(brand, str) else None, "image": image}
    return None


def picture_on_page(html: str) -> str | None:
    """The product photo a page names in its schema.org Product data, or None."""
    found = product_on_page(html)
    return found["image"] if found else None


def _words(text: str | None) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", fold(text or "")) if w]


def same_product(product: dict[str, Any], page: dict[str, str | None]) -> bool:
    """Whether a page found by a search describes our product: its brand in
    full and at least half the words of its name (of three letters or more).
    A page for the brand's other products, or a shop's category page, fails."""
    on_page = "".join(_words(f"{page.get('brand') or ''} {page.get('name') or ''}"))
    brand = "".join(_words(product.get("brand")))
    if not brand or brand not in on_page:
        return False
    name = [w for w in _words(product.get("name")) if len(w) >= 3]
    return not name or sum(w in on_page for w in name) * 2 >= len(name)


def searchable(product: dict[str, Any], listings: list[dict[str, Any]]) -> bool:
    """Whether a web search is the way to this product's picture (see above)."""
    return (not listings and not product.get("eans") and bool(product.get("brand"))
            and (product.get("provenance") or {}).get("attributes") in SEARCHED_KINDS)


def search_text(product: dict[str, Any]) -> str:
    """What a person would type to find the product."""
    size = product.get("size") or {}
    amount = (f"{size['value']:g} {size['unit']}"
              if size.get("value") and size.get("unit") and size["unit"] != "piece" else "")
    named = set(_words(f"{product.get('brand') or ''} {product.get('name') or ''}"))
    details = [d for d in product.get("details") or [] if not set(_words(d)) <= named]
    return " ".join(part for part in [product.get("brand"), product.get("name"),
                                      *details, amount] if part)


def find_picture(product: dict[str, Any], listings: list[dict[str, Any]], *,
                 fetch_page: Callable[[str], str],
                 crawled: Callable[[str, str], dict[str, Any] | None],
                 fetch_off: Callable[[str], str | None],
                 search: Callable[[str], list[str]] | None = None) -> dict[str, Any] | None:
    """`{"url", "from", "page"}` for one product, or None.

    `listings` are the product's shop listings (`store`, `article_number`,
    `url`), the shop it was first found at first. `crawled(store, article)`
    is a crawled record of that shop's, if the app has one; `fetch_page`
    reads a page, `fetch_off` gives Open Food Facts' photo for a barcode,
    `search` the addresses of the pages a web search returned for a text.
    Each may raise; a shop, a barcode or a page that fails is passed over,
    but a search that fails raises `LookupFailed`: whether the web has a
    picture is then unknown, not no.
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
    if search is None or not searchable(product, listings):
        return None
    text = search_text(product)
    try:
        pages = search(text)
    except LookupFailed:
        raise
    except (OSError, ValueError) as error:
        raise LookupFailed(f"searching {text!r} failed: {error}") from error
    for page_url in pages:
        try:
            found = product_on_page(fetch_page(page_url))
        except (OSError, ValueError) as error:
            log.info("picture search %r: %s unreadable (%s)", text, page_url, error)
            continue
        if found and same_product(product, found):
            site = urllib.parse.urlsplit(page_url).hostname or PICTURE_FROM_SEARCH
            return {"url": found["image"], "from": site.removeprefix("www."), "page": page_url}
        log.info("picture search %r: %s %s", text, page_url,
                 f"is another product ({found['brand']} {found['name']})" if found
                 else "names no product with a photo")
    log.info("picture search %r: no page of %d shows the product", text, len(pages))
    return None


# --- the network, for the server ------------------------------------------------

def _open(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=20)


def fetch_page(url: str) -> str:
    with _open(url) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_bytes(url: str, limit: int = 8 * 1024 * 1024) -> bytes:
    with _open(url) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"picture over {limit} bytes: {url}")
    return data


def fetch_off(ean: str) -> str | None:
    try:
        with _open(OFF_PRODUCT_URL.format(ean=ean)) as response:
            doc = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return (doc.get("product") or {}).get("image_front_url")


# A search with Google takes 10 to 60 s and sometimes more. 2026-10-12, the
# demo seed's build: with 60 s, 6 of 18 searches timed out on the first try
# and 3 on the second too (no picture for Weihenstephan, Kerrygold, Kokett).
SEARCH_TIMEOUT_S = 180
SEARCH_PROMPT = ("Find the product page of exactly this product, in an online shop or on "
                 "the maker's own site, preferably German: {text}")


def gemini_search(model: str) -> Callable[[str], list[str]]:
    """A web search through Gemini's Google Search tool: the addresses of the
    pages it returned (followed through Google's redirects), never one the
    model wrote in its answer."""
    from grocery_app import gemini

    def search(text: str) -> list[str]:
        try:
            data = gemini.generate(model, {
                "contents": [{"parts": [{"text": SEARCH_PROMPT.format(text=text)}]}],
                "tools": [{"google_search": {}}]}, timeout_s=SEARCH_TIMEOUT_S)
        except gemini.GeminiError as error:
            raise OSError(str(error)) from error
        grounding = (data.get("candidates") or [{}])[0].get("groundingMetadata") or {}
        pages = []
        for chunk in grounding.get("groundingChunks") or []:
            uri = (chunk.get("web") or {}).get("uri")
            if not uri:
                continue
            # Google's redirect expires; the page it leads to is kept instead.
            try:
                with _open(uri) as response:
                    pages.append(response.geturl())
            except (OSError, ValueError):
                continue
        return pages

    return search
