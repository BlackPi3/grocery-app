"""Fetch the ALDI SÜD product catalog from the API behind aldi-sued.de.

The website blocks plain HTTP clients (403), but the JSON API it calls does
not, and it is far better than scraping: one request returns 30 products with
name, brand, pack size, price and unit price, already structured. The API has
no free-text search (every query parameter tried returns 400), so the catalog
is built by walking the category tree and paging through each leaf.

Prices are per store. Every request names a `servicePoint`; the default is the
Saarbrücken branch the receipts come from, so a listed price can be compared
with what was paid there. A crawl for another branch is a different cache.

Same layering as the GLOBUS fetcher:
  fetch_json       the only function that touches the network; caches raw JSON
  parse_products   pure JSON -> products, testable from a fixture
  leaf_categories  pure tree -> the categories worth crawling
  crawl_category   pages by offset until totalCount is reached

Products are keyed by ALDI's SKU (the number at the end of every product URL),
which is an in-house article number, not a barcode: `ean` stays None. Politeness:
one request per second, sequential, identify the crawler. robots.txt on both
ALDI hosts answers "Access Denied" to non-browser clients, so it could not be
consulted; the crawl is kept small and cached for that reason.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from grocery_app.catalog_globus import USER_AGENT, log

API_BASE = "https://api.aldi-sued.de"
SITE_BASE = "https://www.aldi-sued.de"

# Sulzbachtalstraße 157, 66125 Saarbrücken. Found via /v2/service-points.
DEFAULT_SERVICE_POINT = "BC08"

REQUEST_DELAY_S = 1.0
PAGE_SIZE = 30
MAX_PAGES = 100

DEFAULT_CACHE_DIR = "data/products/aldi-sued/cache"
DEFAULT_OUTPUT = "data/products/aldi-sued/crawl.json"


# --- fetching ----------------------------------------------------------------

def tree_url(service_point: str) -> str:
    return (f"{API_BASE}/v2/product-category-tree?serviceType=walk-in"
            f"&servicePoint={service_point}")


def listing_url(category_key: str, offset: int, service_point: str,
                limit: int = PAGE_SIZE) -> str:
    query = urllib.parse.urlencode({
        "currency": "EUR", "serviceType": "walk-in", "categoryKey": category_key,
        "limit": limit, "offset": offset, "sort": "relevance", "servicePoint": service_point,
    })
    return f"{API_BASE}/v3/product-search?{query}"


def fetch_json(url: str, path: Path, force: bool = False) -> tuple[dict[str, Any], bool]:
    """Return (document, from_cache). Raw responses are cached as fetched."""
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8")), True

    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} for {url}")
        text = response.read().decode("utf-8")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    time.sleep(REQUEST_DELAY_S)
    return json.loads(text), False


# --- parsing (pure) ----------------------------------------------------------

def leaf_categories(tree_doc: dict[str, Any]) -> dict[str, str]:
    """category key -> readable path, for every node without children.

    The tree repeats whole subtrees under several parents (promotional
    groupings), so keys are deduplicated; the first path seen is kept.
    """
    leaves: dict[str, str] = {}

    def walk(node: dict[str, Any], path: list[str]) -> None:
        name = node.get("name") or ""
        children = node.get("children") or []
        if not children:
            leaves.setdefault(node["key"], " / ".join(path + [name]))
        for child in children:
            walk(child, path + [name])

    for node in tree_doc.get("data") or []:
        walk(node, [])
    return leaves


def _euros(cents: Any) -> float | None:
    return round(cents / 100, 2) if isinstance(cents, (int, float)) else None


def parse_products(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Products in one listing response, in the shape the resolver ranks on."""
    products = []
    for item in doc.get("data") or []:
        sku = item.get("sku")
        if not sku:
            continue
        price = item.get("price") or {}
        products.append({
            "article_number": sku,
            "name": item.get("name"),
            "brand": item.get("brandName") or None,
            "pack_size": item.get("sellingSize"),
            "price": _euros(price.get("amountRelevant", price.get("amount"))),
            "unit_price": price.get("comparisonDisplay"),
            "deposit": _euros(price.get("bottleDeposit")) or None,
            "discontinued": bool(item.get("discontinued")),
            "url": f"{SITE_BASE}/produkt/{item.get('urlSlugText')}-{sku}",
            # An in-house number, not a barcode.
            "ean": None,
        })
    return products


def total_count(doc: dict[str, Any]) -> int | None:
    return ((doc.get("meta") or {}).get("pagination") or {}).get("totalCount")


# --- crawling ----------------------------------------------------------------

def crawl_category(category_key: str, cache_dir: str | Path, service_point: str,
                   force: bool = False, max_pages: int = MAX_PAGES) -> list[dict[str, Any]]:
    """Page by offset until the reported total is reached or a page adds nothing."""
    seen: dict[str, dict[str, Any]] = {}
    for page in range(max_pages):
        offset = page * PAGE_SIZE
        path = Path(cache_dir) / service_point / category_key / f"offset{offset}.json"
        try:
            doc, from_cache = fetch_json(listing_url(category_key, offset, service_point),
                                         path, force=force)
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as exc:
            log(f"    offset {offset}: stopped ({exc})")
            break

        products = parse_products(doc)
        fresh = [p for p in products if p["article_number"] not in seen]
        for product in fresh:
            seen[product["article_number"]] = product
        total = total_count(doc)
        log(f"    offset {offset}: {len(products)} items, {len(fresh)} new"
            f"{' (cached)' if from_cache else ''}")
        if not fresh or (total is not None and offset + PAGE_SIZE >= total):
            break
    return list(seen.values())


def crawl(categories: Iterable[str] | None = None, cache_dir: str | Path = DEFAULT_CACHE_DIR,
          output: str | Path = DEFAULT_OUTPUT, force: bool = False,
          service_point: str = DEFAULT_SERVICE_POINT) -> dict[str, Any]:
    """Crawl categories (all leaves by default) into an SKU-keyed catalog file.

    Existing entries are preserved, so categories can be added a few at a time.
    """
    output = Path(output)
    catalog: dict[str, Any] = {}
    if output.exists():
        catalog = json.loads(output.read_text(encoding="utf-8"))

    tree, _ = fetch_json(tree_url(service_point),
                         Path(cache_dir) / service_point / "category-tree.json", force=force)
    leaves = leaf_categories(tree)
    wanted = list(categories) if categories else list(leaves)

    fetched_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    before = len(catalog)
    for key in wanted:
        log(f"  {leaves.get(key, key)}")
        for product in crawl_category(key, cache_dir, service_point, force=force):
            # Prices are observed, not permanent: record when and where.
            product["fetched_at"] = fetched_at
            product["service_point"] = service_point
            product["category"] = leaves.get(key, key)
            catalog[product["article_number"]] = product

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True),
                      encoding="utf-8")
    return {
        "output": str(output),
        "categories": len(wanted),
        "products": len(catalog),
        "added": len(catalog) - before,
        "with_price": sum(1 for p in catalog.values() if p.get("price") is not None),
        "with_brand": sum(1 for p in catalog.values() if p.get("brand")),
    }
