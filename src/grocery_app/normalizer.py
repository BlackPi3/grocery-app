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
    would be for real parser output. Receipt files carry no product_id: a
    receipt says what was printed, never which catalog entry it means.
  - Unknown items are flagged (resolution="none"), never silently dropped or
    guessed. A name the receipt prints for several products it cannot tell
    apart resolves to all of them (resolution="family") and to nothing narrower.
  - Duplicate receipt photos (same transaction) are excluded to avoid double-counting.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from grocery_app.resolver import store_key


# --- loading -----------------------------------------------------------------

def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_receipts(truth_dir: str | Path) -> list[dict[str, Any]]:
    """Load every verified receipt, sorted by date then source image for stable output."""
    receipts = [load_json(p) for p in sorted(Path(truth_dir).glob("*.json"))]
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
                   resolution: dict[tuple[str, str], list[str]],
                   products: dict[str, dict[str, Any]],
                   pinpoint: dict[str, Any] | None = None,
                   shelf_prices: dict[str, set[float]] | None = None) -> dict[str, Any]:
    """Turn one parsed receipt line into an enriched purchase record.

    `pinpoint` is the shopper's own answer for this line, when there is one:
    it narrows a family to one product, and is labelled as coming from them.
    `shelf_prices` (product_id -> prices ever seen on the shelf) lets the paid
    amount narrow a family when exactly one candidate has been sold at it.
    """
    raw_name = line["raw_name"]
    ids = resolution.get((store_key(receipt.get("store")), raw_name), [])
    candidates = [products[i] for i in ids if i in products]
    net_paid = line.get("net", 0.0)
    qty = line.get("qty", 1)

    if pinpoint and pinpoint["product_id"] in ids and pinpoint["product_id"] in products:
        # The receipt could not tell, the shopper could. It must stay inside the
        # family the name resolves to; an answer outside it is a stale note.
        ids = [pinpoint["product_id"]]
        candidates = [products[ids[0]]]
        product_id, how = ids[0], "user"
    elif len(candidates) == 1:
        product_id, how = ids[0], "exact"
    elif (by_price := priced_like(line, ids, shelf_prices)) is not None:
        # The name is ambiguous but the amount is not: 3.99 is the 0,5 kg
        # chia seeds, the 0,2 kg pack has only ever been seen at 2.49.
        ids = [by_price]
        candidates = [products[by_price]]
        product_id, how = by_price, "price"
    elif candidates:
        product_id, how = None, "family"
    else:
        product_id, how = None, "none"

    record: dict[str, Any] = {
        "date": receipt.get("date"),
        "store": receipt.get("store"),
        "source_image": receipt.get("source_image"),
        "type": line.get("type", "product"),
        "raw_name": raw_name,
        "product_id": product_id,
        # `resolved` keeps meaning "product_id is set"; `resolution` says how we
        # got there. "family" is the honest middle: known brand and range,
        # unknown variant, because the till printed one name for all of them.
        "resolved": product_id is not None,
        "resolution": how,
        "candidate_ids": ids if how == "family" else [],
        "qty": qty,
        "gross": line.get("gross"),
        "discount": line.get("discount", 0.0),
        "net_paid": net_paid,
        "tax_class": line.get("tax_class"),
    }

    if candidates:
        record.update(shared_attributes(candidates))
        # Unit price needs a pack size, and only an exact match has one we can
        # trust: a family may span 0,5 kg and 0,2 kg of the same seeds.
        record["unit_price"] = compute_unit_price(
            net_paid, qty, line, candidates[0] if how != "family" else None)
    else:
        # Unresolved: keep the money, be honest about the missing identity.
        record["unit_price"] = compute_unit_price(net_paid, qty, line, None)

    return record


def priced_like(line: dict[str, Any], ids: list[str],
                shelf_prices: dict[str, set[float]] | None) -> str | None:
    """The one candidate whose shelf price matches what this line paid, or None.

    Compares the per-item gross (before discount, which is what the shelf
    shows) against every price ever recorded for each candidate. Two or more
    matches is no answer: same-priced variants stay a family.
    """
    if len(ids) < 2 or not shelf_prices or not line.get("gross"):
        return None
    per_item = round(line["gross"] / (line.get("qty") or 1), 2)
    matches = [i for i in ids
               if any(abs(p - per_item) < 0.005 for p in shelf_prices.get(i, ()))]
    return matches[0] if len(matches) == 1 else None


_SHARED = ("brand", "product_line", "variant", "category", "is_own_brand", "is_organic")


def shared_attributes(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Attributes every candidate agrees on; the rest stay None.

    For an exact match this is simply the product. For a family it is what can
    be said without guessing: `Dove Dusche` has a brand and a category, but no
    variant, because the receipt never printed one.
    """
    shared: dict[str, Any] = {}
    for key in _SHARED:
        values = {json.dumps(c.get(key), sort_keys=True) for c in candidates}
        shared[key] = candidates[0].get(key) if len(values) == 1 else None
    # The readable name travels with the opaque id, so purchases.json stays
    # legible to a human reading it.
    names = {c.get("name") for c in candidates}
    shared["product"] = (candidates[0].get("name") if len(names) == 1
                         else f"{len(candidates)} candidates")
    return shared


def normalize_receipt(receipt: dict[str, Any], resolution: dict[tuple[str, str], list[str]],
                      products: dict[str, dict[str, Any]],
                      line_resolutions: dict[tuple[str, int], dict[str, Any]] | None = None,
                      shelf_prices: dict[str, set[float]] | None = None,
                      ) -> list[dict[str, Any]]:
    image = receipt.get("source_image")
    records = []
    for index, line in enumerate(receipt.get("lines", [])):
        pinpoint = (line_resolutions or {}).get((image, index))
        # A pinpoint is bound to the line's text as well as its position, so a
        # re-transcribed receipt cannot silently move it onto another product.
        if pinpoint and pinpoint.get("raw_name") != line.get("raw_name"):
            pinpoint = None
        records.append(normalize_line(line, receipt, resolution, products,
                                      pinpoint, shelf_prices))
    return records


def load_resolution(path: str | Path) -> dict[tuple[str, str], list[str]]:
    """Flatten resolution.json into a (store, raw_name) -> [product_id, ...] lookup.

    One id is an exact resolution. Several ids are a family: the receipt prints
    one name for products it cannot tell apart (`Dove Dusche` for every 250 ml
    variant), so the name resolves to all of them and nothing narrower.

    Entries whose line_type is not "product" (deposit returns, bags) carry no
    product_id by design: they are not unresolved, they are not products.
    """
    data = load_json(path)
    lookup: dict[tuple[str, str], list[str]] = {}
    for entry in data["entries"]:
        ids = entry.get("product_ids") or (
            [entry["product_id"]] if entry.get("product_id") else [])
        if ids:
            lookup[(store_key(entry["store"]), entry["raw_name"])] = ids
    return lookup


def load_products(path: str | Path) -> dict[str, dict[str, Any]]:
    return load_json(path)["products"]


def load_line_resolutions(path: str | Path | None) -> dict[tuple[str, int], dict[str, Any]]:
    """(source_image, line_index) -> the shopper's answer for that one line.

    This is what the receipt could not say and the shopper could ("it was the
    Kräuter one"). It lives apart from the receipts, which record only what the
    photo shows, and apart from resolution.json, which is keyed by name and so
    cannot hold a per-line fact. A missing file simply means no answers yet.
    """
    if not path or not Path(path).exists():
        return {}
    return {
        (entry["source_image"], entry["line_index"]): entry
        for entry in load_json(path)["entries"]
    }


def load_shelf_prices(products_dir: str | Path | None) -> dict[str, set[float]]:
    """product_id -> every shelf price recorded for it, across all stores' listings.

    Reads `<products_dir>/<store>/listings.json` for every store. Shelf prices
    are a separate series from what was paid; here they serve only to tell
    family members apart. A missing directory means no prices.
    """
    prices: dict[str, set[float]] = {}
    if not products_dir or not Path(products_dir).is_dir():
        return prices
    for path in sorted(Path(products_dir).glob("*/listings.json")):
        for listing in load_json(path).get("listings", {}).values():
            for observed in listing.get("prices", []):
                prices.setdefault(listing["product_id"], set()).add(float(observed["price"]))
    return prices


def build_purchases(receipts_dir: str | Path, products_path: str | Path,
                    resolution_path: str | Path,
                    line_resolutions_path: str | Path | None = None,
                    products_dir: str | Path | None = None) -> dict[str, Any]:
    """Build the purchases.json contract from verified receipts + reference data."""
    products = load_products(products_path)
    resolution = load_resolution(resolution_path)
    line_resolutions = load_line_resolutions(line_resolutions_path)
    shelf_prices = load_shelf_prices(products_dir)
    receipts = load_receipts(receipts_dir)

    purchases: list[dict[str, Any]] = []
    used_receipts = 0
    for receipt in receipts:
        # Skip any receipt flagged as a duplicate photo of another transaction.
        if receipt.get("is_duplicate"):
            continue
        used_receipts += 1
        purchases.extend(normalize_receipt(receipt, resolution, products,
                                           line_resolutions, shelf_prices))

    product_lines = [p for p in purchases if p["type"] == "product"]
    unresolved = sorted({p["raw_name"] for p in product_lines if p["resolution"] == "none"})
    # A family is not unresolved: brand and category are known, the variant is
    # not. It is listed separately so neither number lies.
    ambiguous = sorted({p["raw_name"] for p in product_lines if p["resolution"] == "family"})
    dates = sorted({r["date"] for r in receipts if not r.get("is_duplicate")})

    return {
        "contract_version": 2,
        "meta": {
            "receipts": used_receipts,
            "date_range": [dates[0], dates[-1]] if dates else [],
            "product_lines": len(product_lines),
            "total_net_paid": round(sum(p["net_paid"] for p in product_lines), 2),
            "unresolved_items": unresolved,
            "ambiguous_items": ambiguous,
        },
        "purchases": purchases,
    }


def save_json(data: Any, output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
