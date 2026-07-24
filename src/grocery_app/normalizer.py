"""Normalizer: parsed gold receipts -> purchases.json (the central contract).

The normalizer joins each parsed receipt line against:
  - resolution_map.json  (raw receipt string  -> product_id)
  - catalog.json         (product_id          -> structured product attributes)

and derives fields the receipt never printed (notably price-per-unit), producing
one flat, enriched list of purchase records that every downstream consumer reads.

Design notes:
  - Resolution is done from the *raw_name* via the resolution map, exactly as it
    would be for real parser output. The product_id already present in the gold
    files is used only as a cross-check.
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

# Convert a catalog (net_quantity, unit) into a base amount for price-per-unit.
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

    net_quantity = entry.get("net_quantity")
    unit = entry.get("unit")
    if not net_quantity or not unit:
        return None

    total = qty * net_quantity  # total amount purchased on this line
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
                   resolution_map: dict[str, str],
                   catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Turn one parsed receipt line into an enriched purchase record."""
    raw_name = line["raw_name"]
    product_id = resolution_map.get(raw_name)
    entry = catalog.get(product_id) if product_id else None
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
            "product": entry.get("product"),
            "category": entry.get("category"),
            "is_own_brand": entry.get("is_own_brand"),
            "is_organic": entry.get("is_organic"),
        })
        record["unit_price"] = compute_unit_price(net_paid, qty, line, entry)
    else:
        # Unresolved: keep the money, be honest about the missing identity.
        record["unit_price"] = compute_unit_price(net_paid, qty, line, None)

    return record


def normalize_receipt(receipt: dict[str, Any], resolution_map: dict[str, str],
                      catalog: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        normalize_line(line, receipt, resolution_map, catalog)
        for line in receipt.get("lines", [])
    ]


def build_purchases(gold_dir: str | Path, catalog_path: str | Path,
                    resolution_map_path: str | Path) -> dict[str, Any]:
    """Build the purchases.json contract from the gold receipts + reference data."""
    catalog = load_json(catalog_path)
    resolution_map = load_json(resolution_map_path)
    receipts = load_gold_receipts(gold_dir)

    purchases: list[dict[str, Any]] = []
    used_receipts = 0
    for receipt in receipts:
        # Skip any receipt flagged as a duplicate photo of another transaction.
        if receipt.get("is_duplicate"):
            continue
        used_receipts += 1
        purchases.extend(normalize_receipt(receipt, resolution_map, catalog))

    products = [p for p in purchases if p["type"] == "product"]
    unresolved = sorted({p["raw_name"] for p in products if not p["resolved"]})
    dates = sorted({r["date"] for r in receipts if not r.get("is_duplicate")})

    return {
        "contract_version": 1,
        "meta": {
            "receipts": used_receipts,
            "date_range": [dates[0], dates[-1]] if dates else [],
            "product_lines": len(products),
            "total_net_paid": round(sum(p["net_paid"] for p in products), 2),
            "unresolved_items": unresolved,
        },
        "purchases": purchases,
    }


def save_json(data: Any, output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
