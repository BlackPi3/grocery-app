"""Invariants of the product store: products.json and resolution.json.

These two files are the join every downstream consumer depends on, and they
are written by `confirm` as matches are banked. A dangling product_id or a
duplicated id would surface as a silently unresolved item rather than an
error, so the checks live here, as data, where both the tests and a person
can run them against any pair of files.
"""

from __future__ import annotations

import re
from typing import Any

PRODUCT_ID = re.compile(r"p-\d{4}")
SIZE_SHAPE = {"count", "value", "unit"}


def problems(products_doc: dict[str, Any], resolution_doc: dict[str, Any]) -> list[str]:
    """Every way the two files disagree with the contract, in words. Empty is good."""
    found: list[str] = []
    products = products_doc["products"]

    ids = list(products)
    if ids != sorted(set(ids)):
        found.append("product ids are not unique and sorted")
    for product_id in ids:
        if not PRODUCT_ID.fullmatch(product_id):
            found.append(f"{product_id}: id is not opaque (expected p-NNNN)")

    highest = max((int(pid.split("-")[1]) for pid in ids if PRODUCT_ID.fullmatch(pid)), default=0)
    if products_doc["meta"]["next_id"] <= highest:
        found.append(f"next_id {products_doc['meta']['next_id']} is not ahead of {highest}")

    for product_id, product in products.items():
        if not product.get("label"):
            found.append(f"{product_id}: no readable label")
        if set(product.get("size") or {}) != SIZE_SHAPE:
            found.append(f"{product_id}: size is not {{count, value, unit}}")
        if not isinstance(product.get("eans"), list):
            found.append(f"{product_id}: eans is not a list")

        # A null brand is two different answers and the record has to say which.
        # Loose produce has no barcode, so no lookup, no scan and no shopper
        # will ever supply a brand: silence there is the final answer. Anything
        # else in a packet has a brand printed on it, and a null means nobody
        # read it — a gap, which belongs in open_questions. Left to a writer to
        # remember, twenty packaged products ended up claiming to be cucumbers.
        if not product.get("brand") and not (product.get("category") or "").startswith("Produce") \
                and not any(q.startswith("brand ") for q in product.get("open_questions") or []):
            found.append(f"{product_id}: no brand, not produce, and no 'brand unknown' question")

    seen: dict[tuple[str, str], Any] = {}
    for entry in resolution_doc["entries"]:
        name = f"{entry['store']} / {entry['raw_name']}"
        single, several = entry.get("product_id"), entry.get("product_ids") or []

        for product_id in ([single] if single else []) + several:
            if product_id not in products:
                found.append(f"{name}: points at unknown product {product_id}")
        # A family is several ids or none; never one id in both places.
        if several and (single is not None or len(several) < 2):
            found.append(f"{name}: a family needs product_id null and 2+ product_ids")

        # A deposit return is not an unresolved product, and conflating the
        # two would quietly understate every coverage figure we report.
        if entry["line_type"] != "product" and (single or several):
            found.append(f"{name}: non-product line carries a product id")

        key = (entry["store"], entry["raw_name"])
        if key in seen:
            found.append(f"{name}: resolved more than once")
        seen[key] = single

        # Provenance keeps verified work distinguishable from a matcher's
        # guess. Losing it once already caused a real misreading.
        if (single or several) and not (entry.get("confirmed_by") and entry.get("source")):
            found.append(f"{name}: resolved without confirmed_by and source")

    return found
