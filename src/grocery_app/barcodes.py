"""Barcodes for packaged products that have none, found in Open Food Facts by name.

A barcode is what ties one product to the same product at another shop: a
GLOBUS page names it, an ALDI SÜD listing does not, and a product read from a
receipt line has none. Open Food Facts (ODbL, community-edited) can be
searched by brand and name for one.

Parham, 2026-10-13: only an exact match is written down. A hit is exact when
its brand is ours, its name says nothing ours does not, its size is ours, and
it is sold in Germany. Anything less is a near miss, reported and not
written: a wrong barcode would quietly compare the wrong product across
shops, which is worse than no barcode. He may move to taking the best near
miss (marked as a guess) after seeing how many there are, so the report keeps
them.

A product whose size is unknown can never match exactly: the receipt names a
family (`Goldbären`), and its sizes have different barcodes.

The search is cached per query, so a re-run asks Open Food Facts nothing new.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from grocery_app.resolver import fold, parse_size

SEARCH_URL = "https://search.openfoodfacts.org/search"
FIELDS = "code,product_name,product_name_de,brands_tags,quantity,countries_tags"
COUNTRY = "en:germany"  # every shop the app reads is in Germany
DEFAULT_CACHE_DIR = "data/products/off-search"
USER_AGENT = "grocery-app/0.1 (https://github.com/BlackPi3/grocery-app)"
REQUEST_DELAY_S = 1.0
FROM = "Open Food Facts search"

EXACT = "exact"
OTHER = "other product"  # a different brand or name: not a near miss either
_MULTIPACK = re.compile(r"\d\s*[x×]\s*\d", re.IGNORECASE)
_SIZE_WORD = re.compile(r"^\d+([.,]\d+)?(kg|g|ml|l|er|stk)?$")


# --- searching -----------------------------------------------------------------

def brand_tag(brand: str) -> str:
    """Open Food Facts' form of a brand: `Dr. Oetker` -> `dr-oetker`."""
    return re.sub(r"[^a-z0-9]+", "-", fold(brand)).strip("-")


def query(product: dict[str, Any]) -> str:
    """The search: the product's words, limited to its brand and to Germany.
    Only the words go in: a bracket or a hyphen (`Butter (Irish)`,
    `Bitter-Getränk`) is query syntax to the search and empties the result."""
    words = " ".join(re.findall(r"\w+", " ".join([product["name"],
                                                   *(product.get("details") or [])])))
    return f'{words} brands:"{brand_tag(product["brand"])}" countries_tags:"{COUNTRY}"'


def search(text: str, cache_dir: str | Path = DEFAULT_CACHE_DIR) -> list[dict[str, Any]]:
    """The hits for a query, from the cache when it was asked before."""
    path = Path(cache_dir) / (hashlib.sha1(text.encode()).hexdigest()[:16] + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["hits"]
    url = SEARCH_URL + "?" + urllib.parse.urlencode(
        {"q": text, "page_size": 20, "fields": FIELDS})
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=45) as response:
        hits = json.loads(response.read().decode("utf-8")).get("hits") or []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"q": text, "hits": hits,
                                "fetched_at": datetime.now(UTC).isoformat(timespec="seconds")},
                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    time.sleep(REQUEST_DELAY_S)
    return hits


# --- judging (pure) ------------------------------------------------------------

def _words(text: str | None) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", fold(text or ""))
            if len(w) >= 3 and not _SIZE_WORD.match(w)}


def hit_name(hit: dict[str, Any]) -> str:
    return hit.get("product_name_de") or hit.get("product_name") or ""


def judge(product: dict[str, Any], hit: dict[str, Any]) -> str:
    """`exact`, `other product`, or why a hit for this product falls short."""
    if brand_tag(product["brand"]) not in (hit.get("brands_tags") or []):
        return OTHER
    brand = _words(product["brand"])
    ours = _words(" ".join([product["name"], *(product.get("details") or [])])) - brand
    theirs = _words(hit_name(hit)) - brand
    if not theirs or not theirs <= ours:
        return OTHER
    if COUNTRY not in (hit.get("countries_tags") or []):
        return "not sold in Germany"
    size = product.get("size") or {}
    if not size.get("value") or not size.get("unit"):
        return "our size unknown"
    quantity = hit.get("quantity") or ""
    if _MULTIPACK.search(quantity):
        return "a multipack"
    found = parse_size(quantity)
    if not found:
        return "their size unknown"
    if found[1] != size["unit"] or round(found[0], 1) != round(float(size["value"]), 1):
        return f"size {quantity}"
    return EXACT


def find(product: dict[str, Any], hits: list[dict[str, Any]],
         taken: dict[str, str]) -> dict[str, Any]:
    """What the hits say about one product's barcode.

    `found`: exactly one barcode matches, and no other product has it.
    `taken`: the one match is another product's barcode (a double to merge).
    `several`: more than one barcode matches; which one is not known.
    `near`: the best hit that falls short, and why (what a guess would take).
    `none`: nothing of this brand and name.
    """
    judged = [(hit, judge(product, hit)) for hit in hits if hit.get("code")]
    exact = list(dict.fromkeys(hit["code"] for hit, verdict in judged if verdict == EXACT))
    if len(exact) == 1:
        hit = next(hit for hit, verdict in judged if hit["code"] == exact[0])
        if exact[0] in taken:
            return {"outcome": "taken", "ean": exact[0], "other": taken[exact[0]]}
        return {"outcome": "found", "ean": exact[0], "name": hit_name(hit),
                "quantity": hit.get("quantity")}
    if exact:
        return {"outcome": "several", "eans": exact}
    near = [(hit, verdict) for hit, verdict in judged if verdict != OTHER]
    if near:
        hit, why = near[0]
        return {"outcome": "near", "ean": hit["code"], "name": hit_name(hit),
                "quantity": hit.get("quantity"), "why": why}
    return {"outcome": "none"}


def wanted(product: dict[str, Any]) -> bool:
    """A packaged product without a barcode: it has a brand. Loose produce and
    a kind of thing (`Sandkuchen`) have no brand and no barcode to find."""
    return not product.get("eans") and bool(product.get("brand"))


def find_all(products: dict[str, dict[str, Any]],
             search: Callable[[str], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """One report row per product that wants a barcode, in id order."""
    taken = {ean: pid for pid, p in products.items() for ean in p.get("eans") or []}
    rows = []
    for pid in sorted(products):
        product = products[pid]
        if not wanted(product):
            continue
        said = find(product, search(query(product)), taken)
        if said["outcome"] == "found":
            taken[said["ean"]] = pid  # two of ours on one barcode would be a double
        rows.append({"product_id": pid, "brand": product["brand"], "name": product["name"],
                     "size": product.get("size"), **said})
    return rows
