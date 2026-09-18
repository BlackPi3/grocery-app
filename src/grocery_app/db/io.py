"""Rows to and from the file shapes in docs/data-layout.md.

Three jobs, all built on the same conversions:

- `load_normalizer_inputs` reads the tables into exactly the dicts
  `normalizer.assemble_purchases` takes, so the server joins nothing itself;
- `import_data` loads the files under data/ into the tables, idempotently;
- `export_data` writes the tables back out in the same layout, so the CLI,
  eval and tests keep their inputs.

Money is Decimal in the rows and float in the dicts, as in the files. A key
the tables have no column for is an error, not a silent drop: the files are
the developer's data and losing part of it on the way in would be a lie.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from grocery_app.db.models import (
    LineResolution,
    Product,
    Receipt,
    ReceiptLine,
    Resolution,
    StoreListing,
)
from grocery_app.normalizer import load_json, receipt_files, save_json
from grocery_app.resolver import store_key

# --- scalar conversions ------------------------------------------------------


def _money(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _date(value: str | None) -> date | None:
    return None if not value else date.fromisoformat(value)


def _iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _check_keys(what: str, d: dict[str, Any], known: tuple[str, ...]) -> None:
    unknown = sorted(set(d) - set(known))
    if unknown:
        raise ValueError(f"{what}: no column for {unknown}; add one before importing")


def store_slug(store: str) -> str:
    """The directory name a store's listings live under: 'ALDI SÜD' -> 'aldi-sued'."""
    slug = store.casefold()
    for umlaut, ascii_ in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        slug = slug.replace(umlaut, ascii_)
    return "-".join(slug.split())


# --- receipts ----------------------------------------------------------------

RECEIPT_FIELDS = ("source_image", "transcribed_by", "store", "store_location", "date", "time",
                  "currency", "printed_total", "printed_savings", "tax_buckets",
                  "is_duplicate", "lines")
LINE_FIELDS = ("type", "raw_name", "qty", "unit_gross", "gross", "discount", "net", "tax_class",
               "sold_by_weight", "weight_kg", "unit_price", "unit_price_basis")


def line_from_dict(position: int, d: dict[str, Any]) -> ReceiptLine:
    _check_keys(f"line {position} {d.get('raw_name')!r}", d, LINE_FIELDS)
    if "net" not in d:
        raise ValueError(f"line {position} {d.get('raw_name')!r} has no net amount")
    return ReceiptLine(
        position=position, type=d.get("type", "product"), raw_name=d["raw_name"],
        qty=int(d.get("qty", 1)), unit_gross=_decimal(d.get("unit_gross")),
        gross=_decimal(d.get("gross")), discount=_decimal(d.get("discount")),
        net=_decimal(d["net"]), tax_class=d.get("tax_class"),
        sold_by_weight=d.get("sold_by_weight"), weight_kg=_decimal(d.get("weight_kg")),
        unit_price=_decimal(d.get("unit_price")), unit_price_basis=d.get("unit_price_basis"),
    )


def line_to_dict(line: ReceiptLine) -> dict[str, Any]:
    d: dict[str, Any] = {"type": line.type, "raw_name": line.raw_name, "qty": line.qty}
    if line.unit_gross is not None:
        d["unit_gross"] = _money(line.unit_gross)
    if line.gross is not None:
        d["gross"] = _money(line.gross)
    if line.discount is not None:
        d["discount"] = _money(line.discount)
    d["net"] = _money(line.net)
    d["tax_class"] = line.tax_class
    if line.sold_by_weight is not None:
        d["sold_by_weight"] = line.sold_by_weight
    if line.weight_kg is not None:
        d["weight_kg"] = _money(line.weight_kg)
    if line.unit_price is not None:
        d["unit_price"] = _money(line.unit_price)
    if line.unit_price_basis is not None:
        d["unit_price_basis"] = line.unit_price_basis
    return d


def receipt_from_dict(d: dict[str, Any]) -> Receipt:
    _check_keys(f"receipt {d.get('source_image')!r}", d, RECEIPT_FIELDS)
    return Receipt(
        source_image=d["source_image"], transcribed_by=d.get("transcribed_by", "hand"),
        store=d.get("store"), store_location=d.get("store_location"),
        date=_date(d.get("date")), time=d.get("time"), currency=d.get("currency"),
        printed_total=_decimal(d.get("printed_total")),
        printed_savings=_decimal(d.get("printed_savings")), tax_buckets=d.get("tax_buckets"),
        is_duplicate=bool(d.get("is_duplicate", False)),
        lines=[line_from_dict(i, line) for i, line in enumerate(d.get("lines", []))],
    )


def receipt_to_dict(receipt: Receipt) -> dict[str, Any]:
    """The truth schema. Optional header fields appear only when they hold a value."""
    d: dict[str, Any] = {"source_image": receipt.source_image,
                         "transcribed_by": receipt.transcribed_by, "store": receipt.store}
    for field in ("store_location",):
        if getattr(receipt, field) is not None:
            d[field] = getattr(receipt, field)
    d["date"] = _iso(receipt.date)
    for field in ("time", "currency"):
        if getattr(receipt, field) is not None:
            d[field] = getattr(receipt, field)
    if receipt.printed_total is not None:
        d["printed_total"] = _money(receipt.printed_total)
    if receipt.printed_savings is not None:
        d["printed_savings"] = _money(receipt.printed_savings)
    if receipt.tax_buckets is not None:
        d["tax_buckets"] = receipt.tax_buckets
    if receipt.is_duplicate:
        d["is_duplicate"] = True
    d["lines"] = [line_to_dict(line) for line in sorted(receipt.lines, key=lambda x: x.position)]
    return d


# --- products, resolutions, listings, line answers ----------------------------

PRODUCT_FIELDS = ("label", "name", "brand", "product_line", "variant", "size", "category",
                  "is_organic", "is_own_brand", "eans", "open_questions", "provenance",
                  "nutrition", "enrichment", "extra")
PRODUCT_ALWAYS = PRODUCT_FIELDS[:12]


def product_from_dict(product_id: str, d: dict[str, Any]) -> Product:
    _check_keys(f"product {product_id}", d, PRODUCT_FIELDS)
    values = {field: d.get(field) for field in PRODUCT_FIELDS}
    values["eans"] = list(values["eans"] or [])
    values["open_questions"] = list(values["open_questions"] or [])
    return Product(id=product_id, **values)


def product_to_dict(product: Product) -> dict[str, Any]:
    d = {field: getattr(product, field) for field in PRODUCT_ALWAYS}
    for field in PRODUCT_FIELDS[12:]:
        if getattr(product, field) is not None:
            d[field] = getattr(product, field)
    return d


RESOLUTION_FIELDS = ("store", "raw_name", "line_type", "product_id", "product_ids", "status",
                     "confirmed_by", "confirmed_at", "source")


def resolution_from_dict(d: dict[str, Any]) -> Resolution:
    _check_keys(f"resolution {d.get('store')!r} {d.get('raw_name')!r}", d, RESOLUTION_FIELDS)
    return Resolution(
        store=d["store"], raw_name=d["raw_name"], line_type=d.get("line_type", "product"),
        product_id=d.get("product_id"), product_ids=list(d.get("product_ids") or []),
        status=d.get("status"), confirmed_by=d.get("confirmed_by"),
        confirmed_at=_date(d.get("confirmed_at")), source=d.get("source"),
    )


def resolution_to_dict(r: Resolution) -> dict[str, Any]:
    d: dict[str, Any] = {"store": r.store, "raw_name": r.raw_name, "line_type": r.line_type,
                         "product_id": r.product_id, "confirmed_by": r.confirmed_by,
                         "confirmed_at": _iso(r.confirmed_at), "source": r.source}
    if r.product_ids:
        d["product_ids"] = list(r.product_ids)
    if r.status is not None:
        d["status"] = r.status
    return d


LISTING_FIELDS = ("product_id", "url", "prices")


def listing_from_dict(store: str, article_number: str, d: dict[str, Any]) -> StoreListing:
    _check_keys(f"listing {store} {article_number}", d, LISTING_FIELDS)
    return StoreListing(store=store, article_number=article_number, product_id=d["product_id"],
                        url=d.get("url"), prices=list(d.get("prices") or []))


def listing_to_dict(listing: StoreListing) -> dict[str, Any]:
    return {"product_id": listing.product_id, "url": listing.url,
            "prices": list(listing.prices or [])}


LINE_RESOLUTION_FIELDS = ("source_image", "line_index", "raw_name", "product_id",
                          "confirmed_by", "confirmed_at", "basis")


def line_resolution_to_dict(lr: LineResolution, source_image: str) -> dict[str, Any]:
    return {"source_image": source_image, "line_index": lr.position, "raw_name": lr.raw_name,
            "product_id": lr.product_id, "confirmed_by": lr.confirmed_by,
            "confirmed_at": _iso(lr.confirmed_at), "basis": lr.basis}


# --- reading for the normalizer ----------------------------------------------


def load_normalizer_inputs(session: Session) -> dict[str, Any]:
    """Keyword arguments for `normalizer.assemble_purchases`, from the tables.

    The lookups are built the same way the file loaders build them
    (`load_resolution`, `load_line_resolutions`, `load_shelf_prices`).
    """
    receipts = [receipt_to_dict(r) for r in
                session.scalars(select(Receipt).options(selectinload(Receipt.lines)))]
    products = {p.id: product_to_dict(p) for p in session.scalars(select(Product))}

    resolution: dict[tuple[str, str], list[str]] = {}
    for r in session.scalars(select(Resolution)):
        ids = list(r.product_ids or []) or ([r.product_id] if r.product_id else [])
        if ids:
            resolution[(store_key(r.store), r.raw_name)] = ids

    line_resolutions = {
        (source_image, lr.position): line_resolution_to_dict(lr, source_image)
        for lr, source_image in session.execute(
            select(LineResolution, Receipt.source_image).join(Receipt))
    }

    shelf_prices: dict[str, set[float]] = {}
    for listing in session.scalars(select(StoreListing)):
        for observed in listing.prices or []:
            shelf_prices.setdefault(listing.product_id, set()).add(float(observed["price"]))

    return {"receipts": receipts, "products": products, "resolution": resolution,
            "line_resolutions": line_resolutions, "shelf_prices": shelf_prices}


# --- import ------------------------------------------------------------------


def _copy(target: Any, source: Any, fields: tuple[str, ...]) -> None:
    for field in fields:
        setattr(target, field, getattr(source, field))


def import_data(session: Session, receipts_dir: str | Path, products_path: str | Path,
                resolution_path: str | Path, line_resolutions_path: str | Path | None = None,
                products_dir: str | Path | None = None) -> dict[str, Any]:
    """Load the files into the tables. Running it twice changes nothing.

    Rows are matched by their natural keys (`source_image`, `p-xxxx`,
    (store, raw_name, line_type), (store, article_number), (receipt, position))
    and updated in place; a receipt's lines are replaced, and its line
    answers survive because they hang off the receipt, not the line.
    The caller commits.
    """
    summary: dict[str, Any] = {kind: {"added": 0, "updated": 0} for kind in
                               ("products", "receipts", "resolutions", "listings",
                                "line_resolutions")}
    summary["line_resolutions_skipped"] = []

    for product_id, d in load_json(products_path)["products"].items():
        new = product_from_dict(product_id, d)
        existing = session.get(Product, product_id)
        if existing:
            _copy(existing, new, PRODUCT_FIELDS)
            summary["products"]["updated"] += 1
        else:
            session.add(new)
            summary["products"]["added"] += 1
    session.flush()

    header = tuple(f for f in RECEIPT_FIELDS if f != "lines")
    for path in receipt_files(receipts_dir):
        new = receipt_from_dict(load_json(path))
        existing = session.scalar(select(Receipt).where(Receipt.source_image == new.source_image))
        if existing:
            _copy(existing, new, header)
            existing.lines = []
            session.flush()  # the old positions must be gone before the new ones land
            existing.lines = list(new.lines)
            summary["receipts"]["updated"] += 1
        else:
            session.add(new)
            summary["receipts"]["added"] += 1
    session.flush()

    for d in load_json(resolution_path)["entries"]:
        new = resolution_from_dict(d)
        existing = session.scalar(select(Resolution).where(
            Resolution.store == new.store, Resolution.raw_name == new.raw_name,
            Resolution.line_type == new.line_type))
        if existing:
            _copy(existing, new, RESOLUTION_FIELDS)
            summary["resolutions"]["updated"] += 1
        else:
            session.add(new)
            summary["resolutions"]["added"] += 1

    if products_dir and Path(products_dir).is_dir():
        for path in sorted(Path(products_dir).glob("*/listings.json")):
            doc = load_json(path)
            store = doc.get("meta", {}).get("store") or path.parent.name
            for article_number, d in doc.get("listings", {}).items():
                new = listing_from_dict(store, article_number, d)
                existing = session.scalar(select(StoreListing).where(
                    StoreListing.store == store, StoreListing.article_number == article_number))
                if existing:
                    _copy(existing, new, LISTING_FIELDS)
                    summary["listings"]["updated"] += 1
                else:
                    session.add(new)
                    summary["listings"]["added"] += 1

    if line_resolutions_path and Path(line_resolutions_path).exists():
        for d in load_json(line_resolutions_path)["entries"]:
            _check_keys(f"line resolution {d.get('source_image')!r}", d, LINE_RESOLUTION_FIELDS)
            receipt = session.scalar(select(Receipt).where(
                Receipt.source_image == d["source_image"]))
            if receipt is None:
                summary["line_resolutions_skipped"].append(d["source_image"])
                continue
            existing = session.scalar(select(LineResolution).where(
                LineResolution.receipt_id == receipt.id,
                LineResolution.position == d["line_index"]))
            new = LineResolution(receipt_id=receipt.id, position=d["line_index"],
                                 raw_name=d["raw_name"], product_id=d["product_id"],
                                 confirmed_by=d.get("confirmed_by"),
                                 confirmed_at=_date(d.get("confirmed_at")), basis=d.get("basis"))
            if existing:
                _copy(existing, new, ("raw_name", "product_id", "confirmed_by", "confirmed_at",
                                      "basis"))
                summary["line_resolutions"]["updated"] += 1
            else:
                session.add(new)
                summary["line_resolutions"]["added"] += 1
    session.flush()
    return summary


# --- export ------------------------------------------------------------------


def export_data(session: Session, out_dir: str | Path) -> dict[str, int]:
    """Write the tables out in the data/ layout. Content round-trips; formatting
    and entry order are the exporter's, not the original files'."""
    out = Path(out_dir)
    truth = out / "receipts" / "truth"
    counts = {"receipts": 0, "products": 0, "resolutions": 0, "listings": 0,
              "line_resolutions": 0}

    receipts = session.scalars(select(Receipt).options(selectinload(Receipt.lines))).all()
    for receipt in receipts:
        save_json(receipt_to_dict(receipt), truth / f"{Path(receipt.source_image).stem}.json")
        counts["receipts"] += 1

    products = {p.id: product_to_dict(p) for p in
                session.scalars(select(Product).order_by(Product.id))}
    numbers = [int(pid.split("-")[-1]) for pid in products if pid.split("-")[-1].isdigit()]
    save_json({"meta": {"schema": 1, "next_id": (max(numbers) + 1) if numbers else 1},
               "products": products}, out / "products" / "products.json")
    counts["products"] = len(products)

    entries = [resolution_to_dict(r) for r in session.scalars(
        select(Resolution).order_by(Resolution.store, Resolution.raw_name, Resolution.line_type))]
    save_json({"meta": {"schema": 1}, "entries": entries}, out / "products" / "resolution.json")
    counts["resolutions"] = len(entries)

    by_store: dict[str, dict[str, Any]] = {}
    for listing in session.scalars(select(StoreListing).order_by(
            StoreListing.store, StoreListing.article_number)):
        by_store.setdefault(listing.store, {})[listing.article_number] = listing_to_dict(listing)
        counts["listings"] += 1
    for store, listings in by_store.items():
        save_json({"meta": {"schema": 1, "store": store}, "listings": listings},
                  out / "products" / store_slug(store) / "listings.json")

    answers = [line_resolution_to_dict(lr, source_image) for lr, source_image in
               session.execute(select(LineResolution, Receipt.source_image).join(Receipt)
                               .order_by(Receipt.source_image, LineResolution.position))]
    save_json({"meta": {"schema": 1}, "entries": answers},
              out / "receipts" / "line_resolutions.json")
    counts["line_resolutions"] = len(answers)
    return counts
