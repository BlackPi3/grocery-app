"""Fetch the GLOBUS product catalog from the retailer's own category listings.

The catalog is sourced from the store rather than derived from receipts, so every
entry is a real product with a real barcode, brand and price instead of a model's
guess at what a receipt abbreviation meant. Resolution then becomes retrieval
("which of these real products is this line?") rather than generation.

Why listing pages and not product pages: one listing request returns 24 products
with everything needed (EAN, name, brand, price, pack size, deposit), so the
whole catalog costs ~3k requests instead of ~73k.

Layering, deliberately:
  fetch_page     the only function that touches the network; caches raw HTML
  parse_listing  pure HTML -> products, so the parser is testable from a fixture
  crawl_category paginates until a page yields no new article numbers

Products are keyed by the article number in their URL. Slugs and category paths
drift (the published sitemap is two years stale and its URLs redirect), the
article number does not. For most products that number is the EAN; bakery and
counter goods carry a short in-house number instead, so `ean` is set only when
the number is barcode-shaped.

Politeness: one request per second, sequential, stop on any non-200. Only paths
that robots.txt permits are fetched.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup

BASE_URL = "https://produkte.globus.de"

# A crawler that hides what it is is a crawler you cannot be held to. Identify it.
USER_AGENT = (
    "grocery-app/0.1 (personal receipt-normalization project; "
    "contact: parhamzolfaqari@gmail.com)"
)

REQUEST_DELAY_S = 1.0
MAX_PAGES = 100  # guard against a listing that serves the same page forever

DEFAULT_CACHE_DIR = "data/catalog_cache/globus"
DEFAULT_OUTPUT = "data/catalog/globus.json"

# The three starter branches, as level-2 categories. Level-2 pages already list
# products aggregated across their leaves, so the ~124 leaf categories below them
# never need to be walked.
STARTER_CATEGORIES = [
    "milchprodukte-eier/eier",
    "milchprodukte-eier/kaese",
    "milchprodukte-eier/kaesetheke",
    "milchprodukte-eier/laktosefrei",
    "milchprodukte-eier/margarine-butter-fette",
    "milchprodukte-eier/milch-molkereiprodukte",
    "milchprodukte-eier/milchersatz",
    "brot-backwaren-fruehstueck/aufstriche",
    "brot-backwaren-fruehstueck/backzutaten",
    "brot-backwaren-fruehstueck/brot-backwaren",
    "brot-backwaren-fruehstueck/kaffee",
    "brot-backwaren-fruehstueck/kakao",
    "brot-backwaren-fruehstueck/meisterbaeckerei",
    "brot-backwaren-fruehstueck/muesli",
    "brot-backwaren-fruehstueck/tee",
    "obst-gemuese/frische-kraeuter-gewuerze",
    "obst-gemuese/frisches-gemuese",
    "obst-gemuese/frisches-obst",
    "obst-gemuese/trockenobst-nuesse-kerne",
]


def log(message: str) -> None:
    print(message, flush=True)


# --- fetching ----------------------------------------------------------------

def category_url(category: str, page: int = 1) -> str:
    """Listing URL for a category page.

    Note `?limit=N` is not supported by this shop: it silently renders zero
    product cards. Only `?p=N` paginates.
    """
    url = f"{BASE_URL}/{category.strip('/')}/"
    return url if page == 1 else f"{url}?p={page}"


def cache_path(cache_dir: str | Path, category: str, page: int) -> Path:
    return Path(cache_dir) / category.strip("/") / f"p{page}.html"


def fetch_page(category: str, page: int, cache_dir: str | Path,
               force: bool = False) -> tuple[str, bool]:
    """Return (html, from_cache) for one listing page.

    Raw HTML is cached so the parser can be reworked without re-hitting their
    servers, mirroring how extraction caches per image.
    """
    path = cache_path(cache_dir, category, page)
    if path.exists() and not force:
        return path.read_text(encoding="utf-8"), True

    request = urllib.request.Request(category_url(category, page),
                                     headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} for {category} page {page}")
        html = response.read().decode("utf-8", errors="replace")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    time.sleep(REQUEST_DELAY_S)
    return html, False


# --- parsing (pure) ----------------------------------------------------------

# Barcode lengths (EAN-8, UPC-A, EAN-13, GTIN-14). Anything else in the article
# slot is one of GLOBUS's own short article numbers, used for counter and bakery
# goods that never carry a printed barcode.
_BARCODE_LENGTHS = {8, 12, 13, 14}


def _article_number_from_href(href: str) -> str | None:
    """Product URLs are shaped /<category>/<article number>/<slug>."""
    parts = [p for p in href.split("?")[0].rstrip("/").split("/") if p]
    if len(parts) < 2:
        return None
    candidate = parts[-2]
    return candidate if candidate.isdigit() else None


def _text(node: Any) -> str | None:
    if node is None:
        return None
    value = " ".join(node.get_text(" ", strip=True).split())
    return value or None


def parse_listing(html: str) -> list[dict[str, Any]]:
    """Parse one listing page into product records. No network, no disk, no clock."""
    soup = BeautifulSoup(html, "html.parser")
    products: list[dict[str, Any]] = []

    for card in soup.select("div[data-product-information]"):
        link = card.select_one("a.product-name[href]")
        href = link["href"] if link else None
        article_number = _article_number_from_href(href) if href else None
        if not article_number:
            # No identifier means no stable identity; skip rather than invent a key.
            continue

        name = _text(link)
        if not name:
            try:
                name = json.loads(card["data-product-information"]).get("name")
            except (ValueError, KeyError):
                name = None

        manufacturer = card.select_one(".product-manufacturer")
        brand = (manufacturer.get("title") or _text(manufacturer)) if manufacturer else None

        price_node = card.select_one(".js-unit-price[data-value]")
        price = None
        if price_node:
            try:
                price = float(price_node["data-value"])
            except ValueError:
                price = None

        # Two .price-unit-content blocks per card; the informative one is the
        # last with actual text ("0,5 kg (3,58 € / 1 kg)  zzgl. Pfand 0.15 €").
        pack_size = None
        deposit_text = None
        for block in card.select(".price-unit-content"):
            value = _text(block)
            if not value:
                continue
            if "Pfand" in value:
                head, _, tail = value.partition("zzgl. Pfand")
                pack_size = head.strip() or pack_size
                deposit_text = f"zzgl. Pfand{tail}".strip()
            else:
                pack_size = value

        products.append({
            "article_number": article_number,
            # Bakery and counter goods carry a short in-house number, not a barcode.
            "ean": article_number if len(article_number) in _BARCODE_LENGTHS else None,
            "name": name,
            "brand": brand,
            "price": price,
            "pack_size": pack_size,
            "deposit": deposit_text,
            "url": href,
        })

    return products


# --- crawling ----------------------------------------------------------------

def crawl_category(category: str, cache_dir: str | Path, force: bool = False,
                   max_pages: int = MAX_PAGES) -> list[dict[str, Any]]:
    """Page through a category until it stops yielding products we have not seen.

    Termination is on *new article numbers*, not on card count: a shop that serves
    the last page forever still returns 24 cards every time.
    """
    seen: dict[str, dict[str, Any]] = {}
    for page in range(1, max_pages + 1):
        try:
            html, from_cache = fetch_page(category, page, cache_dir, force=force)
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as exc:
            log(f"    page {page}: stopped ({exc})")
            break

        products = parse_listing(html)
        fresh = [p for p in products if p["article_number"] not in seen]
        for product in fresh:
            product["category"] = category
            seen[product["article_number"]] = product

        log(f"    page {page}: {len(products)} cards, {len(fresh)} new"
            f"{' (cached)' if from_cache else ''}")
        if not fresh:
            break

    return list(seen.values())


def crawl(categories: Iterable[str], cache_dir: str | Path = DEFAULT_CACHE_DIR,
          output: str | Path = DEFAULT_OUTPUT, force: bool = False) -> dict[str, Any]:
    """Crawl categories and merge them into an article-number-keyed catalog file.

    Existing entries are preserved, so categories can be added a few at a time.
    """
    output = Path(output)
    catalog: dict[str, Any] = {}
    if output.exists():
        catalog = json.loads(output.read_text(encoding="utf-8"))

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    before = len(catalog)

    for category in categories:
        log(f"  {category}")
        for product in crawl_category(category, cache_dir, force=force):
            # Prices are observed, not permanent: record when we saw them, or
            # comparing a shop price to a months-old receipt is unfalsifiable.
            product["fetched_at"] = fetched_at
            catalog[product["article_number"]] = product

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True),
                      encoding="utf-8")

    return {
        "output": str(output),
        "products": len(catalog),
        "added": len(catalog) - before,
        "with_price": sum(1 for p in catalog.values() if p.get("price") is not None),
        "with_brand": sum(1 for p in catalog.values() if p.get("brand")),
        "with_ean": sum(1 for p in catalog.values() if p.get("ean")),
    }
