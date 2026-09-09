"""Migrate the first-attempt catalog into the product / listing / resolution split.

Input:  data/catalog.json        53 product entries, attributes partly model-proposed
        data/gold/*.json         9 receipts whose product_id choices Parham verified

Output: data/products.json               what a product is, independent of any store
        data/resolution.json             which receipt text means which product
        data/store_listings/globus.json  what one store sells it as (starts empty)

Why three files. The old shape carried two different kinds of truth in one place:
what the receipt says, and which product that is. The first is fixed by the photo
and belongs to one receipt; the second is a judgement about a *name* and holds
across every receipt it ever appears on. Splitting them means each is corrected
once, in one place, and each file answers a single question.

Two things this migration is careful about:

  - Product ids are opaque (`p-0001`). An id that encodes brand or size becomes a
    lie the first time either changes, and then you must choose between a wrong
    key and a rename that breaks every reference. The old slugs are kept as
    `label` because `4104060000065` is miserable to read, but they are no longer
    the key.

  - Provenance is recorded per fact, not per file. Parham verified which product
    each receipt line is; the *attributes* of those products (brand, size) were
    largely proposed by the original prompt and 35 of 53 still carry open
    questions. Collapsing those into one undifferentiated "catalog" is what made
    this data ambiguous in the first place.

Run:  .venv/bin/python scripts/migrate_product_store.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CATALOG = Path("data/catalog.json")
GOLD_DIR = Path("data/gold")
PRODUCTS_OUT = Path("data/products.json")
RESOLUTION_OUT = Path("data/resolution.json")
LISTINGS_OUT = Path("data/store_listings/globus.json")

SCHEMA = 1

# Fields consumed explicitly below; anything else on a catalog entry is preserved
# under "extra" rather than dropped, because it was hand-checked and cheap to keep.
_MAPPED = {
    "product_id", "brand", "product_line", "variant", "product",
    "net_quantity", "unit", "is_organic", "category", "is_own_brand",
    "needs_review",
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_size(entry: dict[str, Any]) -> dict[str, Any]:
    """Size as count x value unit, so a multipack can be expressed at all.

    `count` stays 1 here: the old catalog has no multipack information, and the
    GLOBUS listing is what will fill it in (it prints "3er (3x 1,000 Stück)").
    Inventing a count now would be guessing dressed as data.
    """
    return {"count": 1, "value": entry.get("net_quantity"), "unit": entry.get("unit")}


def build_products(catalog: dict[str, dict[str, Any]]) -> tuple[dict, dict[str, str]]:
    """Return (products file, old slug -> new opaque id)."""
    products: dict[str, Any] = {}
    slug_to_id: dict[str, str] = {}

    for number, (slug, entry) in enumerate(sorted(catalog.items()), start=1):
        product_id = f"p-{number:04d}"
        slug_to_id[slug] = product_id

        open_questions = entry.get("needs_review") or []
        extra = {k: v for k, v in entry.items() if k not in _MAPPED}

        products[product_id] = {
            "label": slug,
            "name": entry.get("product"),
            "brand": entry.get("brand"),
            "product_line": entry.get("product_line"),
            "variant": entry.get("variant"),
            "size": build_size(entry),
            "category": entry.get("category"),
            "is_organic": entry.get("is_organic"),
            "is_own_brand": entry.get("is_own_brand"),
            # Barcodes are a list: a relaunch adds one rather than forking the
            # product, so price history stays continuous across it.
            "eans": [],
            "open_questions": open_questions,
            "provenance": {
                "attributes": "model-proposed",
                "source": "data/catalog.json",
            },
        }
        if extra:
            products[product_id]["extra"] = extra

    return {
        "meta": {
            "schema": SCHEMA,
            "next_id": len(products) + 1,
            "note": "product_id is opaque and permanent; `label` is the old slug, "
                    "kept for readability only. Attributes are model-proposed "
                    "unless provenance says otherwise; see open_questions.",
        },
        "products": products,
    }, slug_to_id


def build_resolution(gold_dir: Path, slug_to_id: dict[str, str]) -> tuple[dict, list[str]]:
    """One entry per (store, raw_name), carrying who decided it and how."""
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    conflicts: list[str] = []

    for path in sorted(gold_dir.glob("*.json")):
        receipt = load(path)
        store = receipt.get("store")
        for line in receipt.get("lines", []):
            raw_name = line.get("raw_name")
            if not raw_name:
                continue
            key = (store, raw_name)
            slug = line.get("product_id")
            product_id = slug_to_id.get(slug) if slug else None

            entry = {
                "store": store,
                "raw_name": raw_name,
                # Distinguishes "not a product" (deposit, bag) from "unresolved".
                # Without this every coverage figure silently understates itself.
                "line_type": line.get("type", "product"),
                "product_id": product_id,
                "confirmed_by": "parham" if product_id else None,
                "confirmed_at": None,  # predates provenance tracking; not invented here
                "source": "data/gold",
            }
            if slug and not product_id:
                conflicts.append(f"{raw_name}: product_id {slug!r} is not in the catalog")

            existing = entries.get(key)
            if existing and existing["product_id"] != entry["product_id"]:
                conflicts.append(
                    f"{raw_name}: mapped to both {existing['product_id']} and {product_id}"
                )
            entries[key] = entry

    return {
        "meta": {
            "schema": SCHEMA,
            "note": "confirmed_at is null for entries migrated from data/gold: "
                    "Parham verified them against the photos, but the date was "
                    "not recorded at the time and is not invented here.",
        },
        "entries": [entries[k] for k in sorted(entries)],
    }, conflicts


def build_listings() -> dict:
    """GLOBUS listings start empty on purpose.

    A listing links a product to the store's own article number and price
    history. Nothing may be written here until a match is confirmed -- the 9,700
    fetched products in data/catalog/ are a raw cache, not confirmed listings,
    and copying them here would turn this file into a mirror of someone else's
    database.
    """
    return {
        "meta": {
            "schema": SCHEMA,
            "store": "GLOBUS",
            "note": "Populated as matches are confirmed. `prices` is the shelf "
                    "price observed at fetch time, which is a different series "
                    "from what was paid (that lives in purchases.json). Shelf "
                    "history cannot be backfilled: the shop publishes today only.",
        },
        "listings": {},
    }


def main() -> int:
    catalog = load(CATALOG)
    products, slug_to_id = build_products(catalog)
    resolution, conflicts = build_resolution(GOLD_DIR, slug_to_id)

    write(PRODUCTS_OUT, products)
    write(RESOLUTION_OUT, resolution)
    listings_existed = LISTINGS_OUT.exists()
    if not listings_existed:
        write(LISTINGS_OUT, build_listings())

    resolved = sum(1 for e in resolution["entries"] if e["product_id"])
    non_product = sum(1 for e in resolution["entries"] if e["line_type"] != "product")
    unresolved = len(resolution["entries"]) - resolved - non_product
    flagged = sum(1 for p in products["products"].values() if p["open_questions"])

    print(f"{PRODUCTS_OUT}:   {len(products['products'])} products, "
          f"{flagged} with open questions about their attributes")
    print(f"{RESOLUTION_OUT}: {len(resolution['entries'])} entries "
          f"({resolved} resolved, {non_product} not a product, {unresolved} unresolved)")
    print(f"{LISTINGS_OUT}: {'kept' if LISTINGS_OUT.exists() else 'created'}, "
          f"filled as matches are confirmed")

    for problem in conflicts:
        print(f"  CONFLICT: {problem}")
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
