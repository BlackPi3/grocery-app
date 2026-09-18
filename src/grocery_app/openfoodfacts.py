"""Enrich products that carry a barcode with what Open Food Facts knows about it.

A store listing says what a product is called and costs; it rarely says what
it *is*. products.json therefore has `category`, `is_organic` and the like as
null for most GLOBUS-sourced entries. Open Food Facts (ODbL, community-edited,
keyed by EAN) answers those from the barcode alone: a category taxonomy,
organic and other labels, Nutri-Score, NOVA group, ingredients.

Rules, so the enrichment never quietly outranks a person:
  - only attributes that are null get filled; a confirmed value is never
    overwritten, and what was filled is listed under `enrichment.filled`;
  - `is_organic` becomes True only on an explicit organic label; the absence
    of a label in a crowd-sourced record proves nothing, so it stays null;
  - every response is cached, including "not found", so re-runs cost nothing
    and their servers see each barcode once. `--force` re-asks.

Open Food Facts asks clients to identify themselves and to stay under about
100 product reads a minute; both are honoured here. Attribution: data from
Open Food Facts, https://openfoodfacts.org, licensed under the ODbL.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from grocery_app.catalog_globus import USER_AGENT, log

API_URL = "https://world.openfoodfacts.org/api/v2/product/{ean}"
FIELDS = ",".join([
    "product_name", "product_name_de", "brands", "quantity", "categories_tags",
    "labels_tags", "nutriscore_grade", "nova_group", "ingredients_text_de",
    "allergens_tags", "countries_tags",
])
# Their published limit is ~100 product reads a minute, but a 429 arrived
# after 16 at 0.7 s apart, so the pace is slower than the document implies.
REQUEST_DELAY_S = 2.0
RATE_LIMIT_WAIT_S = 60
DEFAULT_CACHE_DIR = "data/products/off"

# Fields on a product that enrichment may fill when they are null.
FILLABLE = ("category", "is_organic")


# --- fetching ----------------------------------------------------------------

def fetch_product(ean: str, cache_dir: str | Path = DEFAULT_CACHE_DIR,
                  force: bool = False) -> tuple[dict[str, Any], bool]:
    """Return (response document, from_cache). A miss is a document with status 0."""
    path = Path(cache_dir) / f"{ean}.json"
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8")), True

    request = urllib.request.Request(
        API_URL.format(ean=ean) + "?fields=" + FIELDS,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                doc = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                doc = {"status": 0, "code": ean}
                break
            if exc.code == 429 and attempt == 0:
                # Their limit, not ours to argue with: wait what they ask for
                # (a minute if unsaid) and try once more.
                wait = int(exc.headers.get("Retry-After") or RATE_LIMIT_WAIT_S)
                log(f"  rate limited by Open Food Facts; waiting {wait}s")
                time.sleep(wait)
                continue
            raise

    doc["fetched_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    time.sleep(REQUEST_DELAY_S)
    return doc, False


# --- reading (pure) ----------------------------------------------------------

_TAXONOMY_TAG = re.compile(r"^en:[a-z0-9]+(-[a-z0-9]+)*$")


def _readable(tag: str) -> str:
    """`en:gummy-bears` -> `gummy bears`."""
    return re.sub(r"^[a-z]{2}:", "", tag).replace("-", " ")


def attributes_from(doc: dict[str, Any]) -> dict[str, Any] | None:
    """What a found record says, in this project's terms. None when not found."""
    if doc.get("status") != 1:
        return None
    product = doc.get("product") or {}
    categories = [t for t in product.get("categories_tags") or [] if t.startswith("en:")]
    labels = product.get("labels_tags") or []
    # The deepest category is the most specific one, but a contributor's free
    # text (`en:Hühnchen`, `en:Snacks sucres`) sits at the end of the chain
    # with the same prefix as taxonomy entries. Taxonomy tags are lowercase
    # ASCII and hyphenated, so the deepest tag of that shape is taken.
    taxonomy = [t for t in categories if _TAXONOMY_TAG.match(t)]
    return {
        "name": product.get("product_name_de") or product.get("product_name") or None,
        "brand": product.get("brands") or None,
        "quantity": product.get("quantity") or None,
        # The whole chain is kept so a coarser grouping can be chosen later
        # without re-fetching.
        "category": _readable(taxonomy[-1]) if taxonomy else None,
        "categories": [_readable(t) for t in categories],
        "is_organic": True if "en:organic" in labels else None,
        "labels": [_readable(t) for t in labels],
        "nutriscore": product.get("nutriscore_grade") or None,
        "nova": product.get("nova_group") or None,
        "allergens": [_readable(t) for t in product.get("allergens_tags") or []],
    }


# --- applying ----------------------------------------------------------------

def enrich(products_path: str | Path, cache_dir: str | Path = DEFAULT_CACHE_DIR,
           force: bool = False,
           fetch: Callable[..., tuple[dict[str, Any], bool]] = fetch_product) -> dict[str, Any]:
    """Fill null attributes of every barcoded product from Open Food Facts."""
    doc = json.loads(Path(products_path).read_text(encoding="utf-8"))
    summary = {"with_ean": 0, "found": 0, "filled": 0, "cached": 0}

    for product_id, product in doc["products"].items():
        eans = product.get("eans") or []
        if not eans:
            continue
        summary["with_ean"] += 1

        found = None
        for ean in eans:
            response, from_cache = fetch(ean, cache_dir, force=force)
            summary["cached"] += from_cache
            found = attributes_from(response)
            if found:
                break
        if not found:
            log(f"  {product_id} {product.get('name')!s:40.40} not in Open Food Facts")
            continue
        summary["found"] += 1

        filled = [key for key in FILLABLE
                  if product.get(key) is None and found.get(key) is not None]
        for key in filled:
            product[key] = found[key]
        summary["filled"] += len(filled)

        # Facts a store listing never carries, kept apart from the attributes
        # a person may have confirmed.
        product["nutrition"] = {"nutriscore": found["nutriscore"], "nova": found["nova"]}
        product["enrichment"] = {
            "source": "open-food-facts", "ean": ean,
            "fetched_at": response.get("fetched_at"),
            "filled": filled,
            "categories": found["categories"], "labels": found["labels"],
            "allergens": found["allergens"],
            "off_name": found["name"], "off_brand": found["brand"],
            "off_quantity": found["quantity"],
        }
        log(f"  {product_id} {product.get('name')!s:40.40} "
            f"{found['category'] or '-':30.30} filled: {', '.join(filled) or 'nothing new'}")

    Path(products_path).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
    return summary
