"""Normalizer: parsed receipts -> purchases.json (the central contract).

The normalizer joins each parsed receipt line against:
  - resolution.json  ((store, raw receipt string) -> product_id)
  - products.json    (product_id                  -> structured product attributes)

Resolution is store-scoped because the same printed abbreviation can mean
different things in different chains, while still allowing two chains to point
at one product when they genuinely sell the same thing.

and derives fields the receipt never printed (notably price-per-unit), producing
one flat, enriched list of purchase records that every downstream consumer reads.

Design notes:
  - Resolution is done from (store, raw_name) via resolution.json, exactly as it
    would be for real parser output. Any product_id still present in a receipt
    file is used only as a cross-check.
  - Unknown items are flagged (resolved=False), never silently dropped or guessed.
  - Duplicate receipt photos (same transaction) are excluded to avoid double-counting.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# --- loading -----------------------------------------------------------------

def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_gold_receipts(gold_dir: str | Path) -> list[dict[str, Any]]:
    """Load every gold receipt, sorted by date then source image for stable output."""
    receipts = [load_json(p) for p in sorted(Path(gold_dir).glob("*.json"))]
    return sorted(receipts, key=lambda r: (r.get("date", ""), r.get("source_image", "")))


# --- unit-price derivation ---------------------------------------------------

# Convert a product size into a base amount for price-per-unit.
# Weight -> per kg, volume -> per litre, countable -> per piece.
_TO_KG = {"kg": 1.0, "g": 0.001}
_TO_L = {"l": 1.0, "ml": 0.001}


def compute_unit_price(net_paid: float, qty: int, line: dict[str, Any],
                       entry: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return {'amount', 'per', 'currency'} for the effective paid unit price, or None.

    'Effective' means based on what was actually paid (net of discount), so it is
    directly comparable across stores and over time.
    """
    # Weighed produce: the line itself carries the purchased weight in kg.
    if line.get("sold_by_weight") and line.get("weight_kg"):
        return {"amount": round(net_paid / line["weight_kg"], 2), "per": "kg"}

    if not entry:
        return None

    size = entry.get("size") or {}
    net_quantity = size.get("value")
    unit = size.get("unit")
    if not net_quantity or not unit:
        return None

    # count covers multipacks: 6 x 0.33 l is six units, not one.
    total = qty * (size.get("count") or 1) * net_quantity
    if unit in _TO_KG:
        kg = total * _TO_KG[unit]
        return {"amount": round(net_paid / kg, 2), "per": "kg"} if kg else None
    if unit in _TO_L:
        litres = total * _TO_L[unit]
        return {"amount": round(net_paid / litres, 2), "per": "l"} if litres else None
    if unit == "piece":
        return {"amount": round(net_paid / total, 2), "per": "piece"} if total else None
    return None


# --- core join ---------------------------------------------------------------

def normalize_line(line: dict[str, Any], receipt: dict[str, Any],
                   resolution: dict[tuple[str, str], str],
                   products: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Turn one parsed receipt line into an enriched purchase record."""
    raw_name = line["raw_name"]
    product_id = resolution.get((receipt.get("store"), raw_name))
    entry = products.get(product_id) if product_id else None
    net_paid = line.get("net", 0.0)
    qty = line.get("qty", 1)

    record: dict[str, Any] = {
        "date": receipt.get("date"),
        "store": receipt.get("store"),
        "source_image": receipt.get("source_image"),
        "type": line.get("type", "product"),
        "raw_name": raw_name,
        "product_id": product_id,
        "resolved": entry is not None,
        "qty": qty,
        "gross": line.get("gross"),
        "discount": line.get("discount", 0.0),
        "net_paid": net_paid,
        "tax_class": line.get("tax_class"),
    }

    if entry:
        record.update({
            "brand": entry.get("brand"),
            "product_line": entry.get("product_line"),
            "variant": entry.get("variant"),
            # The readable name travels with the opaque id, so purchases.json
            # stays legible to a human reading it.
            "product": entry.get("name"),
            "category": entry.get("category"),
            "is_own_brand": entry.get("is_own_brand"),
            "is_organic": entry.get("is_organic"),
        })
        record["unit_price"] = compute_unit_price(net_paid, qty, line, entry)
    else:
        # Unresolved: keep the money, be honest about the missing identity.
        record["unit_price"] = compute_unit_price(net_paid, qty, line, None)

    return record


def normalize_receipt(receipt: dict[str, Any], resolution: dict[tuple[str, str], str],
                      products: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        normalize_line(line, receipt, resolution, products)
        for line in receipt.get("lines", [])
    ]


def load_resolution(path: str | Path) -> dict[tuple[str, str], str]:
    """Flatten resolution.json into a (store, raw_name) -> product_id lookup.

    Entries whose line_type is not "product" (deposit returns, bags) carry no
    product_id by design: they are not unresolved, they are not products.
    """
    data = load_json(path)
    return {
        (entry["store"], entry["raw_name"]): entry["product_id"]
        for entry in data["entries"]
        if entry.get("product_id")
    }


def load_products(path: str | Path) -> dict[str, dict[str, Any]]:
    return load_json(path)["products"]


def build_purchases(receipts_dir: str | Path, products_path: str | Path,
                    resolution_path: str | Path) -> dict[str, Any]:
    """Build the purchases.json contract from verified receipts + reference data."""
    products = load_products(products_path)
    resolution = load_resolution(resolution_path)
    receipts = load_gold_receipts(receipts_dir)

    purchases: list[dict[str, Any]] = []
    used_receipts = 0
    for receipt in receipts:
        # Skip any receipt flagged as a duplicate photo of another transaction.
        if receipt.get("is_duplicate"):
            continue
        used_receipts += 1
        purchases.extend(normalize_receipt(receipt, resolution, products))

    product_lines = [p for p in purchases if p["type"] == "product"]
    unresolved = sorted({p["raw_name"] for p in product_lines if not p["resolved"]})
    dates = sorted({r["date"] for r in receipts if not r.get("is_duplicate")})

    return {
        "contract_version": 1,
        "meta": {
            "receipts": used_receipts,
            "date_range": [dates[0], dates[-1]] if dates else [],
            "product_lines": len(product_lines),
            "total_net_paid": round(sum(p["net_paid"] for p in product_lines), 2),
            "unresolved_items": unresolved,
        },
        "purchases": purchases,
    }


def save_json(data: Any, output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
