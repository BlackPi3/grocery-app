"""Coarse resolution: name the thing at the level the evidence supports.

Most receipt lines are not produce and not in any catalogue we hold, but they
are not mysteries either. `Chipsfrisch SalVin` is funny-frisch Chipsfrisch;
what it does not say is the flavour. `HP Skyr Drink 330` is a Milsani High
Protein Skyr Drink; what it does not say is whether it was strawberry.

The temptation is to guess the missing half, and that is the one thing this
module refuses to do. A guessed flavour is indistinguishable from a confirmed
one the moment it is written, so it can never be cleaned up; a null says
"unknown" honestly and costs nothing. Three of the four insights this project
is built on — cadence, own-brand share, personal inflation — work perfectly
well at brand-and-product-line, provided the coarse product does not straddle
a price gap. Only same-item-across-stores needs the barcode, and that arrives
when someone scans one.

So a coarse product carries what is known, leaves the rest null, and says so
in `open_questions`, which doubles as the work queue for whatever asks the
shopper later. It never carries an invented EAN: the barcode *is* the
fine-grained identity, and a made-up one would be a lie the catalog cannot
detect afterwards.

Splitting later is cheap, which is what makes all of this safe. A purchase
stores no product id — `purchases.json` is derived on every read from
`(store, raw_name) -> product_id` — so when the finer answer arrives, one
resolution entry is repointed and the whole history re-derives. No migration,
no backfill.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

from grocery_app.resolver import fold, store_key

# The routes a reviewed row can carry. Only the first two name a product.
WRITES = ("search", "known")
SKIPS = {
    "produce": "handled by the produce vocabulary",
    "ask": "only the shopper can say",
    "dropped": "not remembered; deliberately unresolved",
    "nonproduct": "packaging, not a grocery",
    "outofscope": "not groceries",
}

FIELDS = ("store", "raw_name", "route", "brand", "product", "ean", "options", "your_note")


def _label(name: str, brand: str | None) -> str:
    import re
    text = f"{brand} {name}" if brand else name
    return re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")


def read_rows(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def confirm(reviewed_path: str | Path, products_path: str | Path,
            resolution_path: str | Path) -> dict[str, Any]:
    """Write reviewed coarse rows into the catalog, guessing nothing.

    One product per (brand, name) across every store: two tills printing
    `Coca-Cola 1.25L` and `Coca Cola 1,25l` resolve to the same id, which is
    the whole reason a shared catalog is worth having. A row whose
    `(store, raw_name)` is already resolved is left alone — an answer given
    once is never overwritten by a later guess.
    """
    products_doc = json.loads(Path(products_path).read_text(encoding="utf-8"))
    resolution_doc = json.loads(Path(resolution_path).read_text(encoding="utf-8"))

    by_key = {(p.get("brand"), p["name"]): pid for pid, p in products_doc["products"].items()}
    known = {(store_key(e["store"]), e["raw_name"]) for e in resolution_doc["entries"]}
    summary: dict[str, Any] = {"products": 0, "entries": 0, "skipped_known": 0,
                               "with_ean": 0, "by_route": {}}

    for row in read_rows(reviewed_path):
        route = (row.get("route") or "").strip()
        summary["by_route"][route] = summary["by_route"].get(route, 0) + 1
        if route not in WRITES:
            continue

        name = (row.get("product") or "").strip()
        if not name:
            continue
        brand = (row.get("brand") or "").strip()
        ean = (row.get("ean") or "").strip()

        questions = []
        # A trailing `?` is the reviewer saying "this is my guess", which is a
        # fact about the brand, not a brand. It goes to the queue, not the field.
        if brand.endswith("?"):
            questions.append(f"brand uncertain: {brand.rstrip('?')}")
            brand = ""
        if not ean:
            questions.append("variant unknown")

        if (store_key(row["store"]), row["raw_name"]) in known:
            summary["skipped_known"] += 1
            continue

        key = (brand or None, name)
        product_id = by_key.get(key)
        if product_id is None:
            product_id = f"p-{products_doc['meta']['next_id']:04d}"
            products_doc["meta"]["next_id"] += 1
            products_doc["products"][product_id] = {
                "label": _label(name, brand or None),
                "name": name,
                "brand": brand or None,
                "product_line": None,
                # Left null on purpose: see the module docstring.
                "variant": None,
                "size": {"count": 1, "value": None, "unit": None},
                "category": None,
                "is_organic": None,
                "is_own_brand": None,
                "eans": [ean] if ean else [],
                "open_questions": questions,
                "provenance": {"attributes": "coarse-resolution",
                               "source": str(reviewed_path)},
            }
            by_key[key] = product_id
            summary["products"] += 1
            if ean:
                summary["with_ean"] += 1

        resolution_doc["entries"].append({
            "store": row["store"],
            "raw_name": row["raw_name"],
            "line_type": "product",
            "product_id": product_id,
            "confirmed_by": "coarse-resolution",
            "confirmed_at": date.today().isoformat(),
            "source": str(reviewed_path),
        })
        known.add((store_key(row["store"]), row["raw_name"]))
        summary["entries"] += 1

    Path(products_path).write_text(
        json.dumps(products_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(resolution_path).write_text(
        json.dumps(resolution_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
