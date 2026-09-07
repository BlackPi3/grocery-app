"""Convert hand-transcribed receipt text files into held-out ground-truth JSON.

Input:  data/holdout/raw/*.txt   (typed by hand while reading the paper receipt)
Output: data/holdout/*.json      (same field names as data/gold/, minus the
                                  fields a human cannot transcribe)

The text format is one receipt per file. Type only what the receipt prints —
the converter derives unit prices, nets, and totals:

    IMG_5311.jpeg
    Lidl | Sulzbachtalstrasse 86-90, 66125 Dudweiler
    2026-06-26 | 11:49 | EUR

    Minze geschnitten     | 1              | 0.89
    Snack Gurken          | 0.99 * 2       | 1.98
    Romatomaten           | 1              | 1.19 | -0.20
    BioBabyWassermelone   | 2.434kg * 2.49 | 6.06
    PFAND                 | 1              | 0.25
    SAVINGS 2.40
    TAX 7% 30.15
    TAX 19% 3.26
    TOTAL 33.41

Product lines are `name | qty | price` with two optional trailing fields, in
any order: a discount (starts with `-`) and a tax class as printed (`A`, `B`,
`1`, `2`, or a rate like `7%`).
The price is always the printed line total, not the per-unit price.

Quantity is a count (`1`, `3`), a bare weight (`0.208kg`) when the receipt shows
no unit price, or a full weight expression (`2.434kg * 2.49`,
where `*`, `x` and `@` are interchangeable and a trailing `/kg` is optional)
for anything sold loose. A fixed-price pack is a count of 1 — its size belongs
in the name (`Radieschen 250g | 1 | 0.89`).

A line named PFAND is a deposit charge. A negative price — or a name containing
LEERGUT or RETOURE — is an empties return, recorded as a bare negative net. An optional SAVINGS line records a receipt-level savings recap
(Lidl's "Preisvorteil gesamt"); it is stored but never added to the total, since
the item prices already reflect it. Blank lines and lines starting with # are ignored.

Arithmetic is checked, not assumed: a transcription typo in the answer key
mis-grades the parser forever, so conversion fails loudly rather than writing a
file that does not add up.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOLERANCE = 0.011  # one cent, plus room for float representation
WEIGHT_TOLERANCE = 0.02  # receipts round weight x unit price to the cent
WEIGHT_QTY = re.compile(
    r"^([\d.,]+)\s*(kg|g)\s*[@*x]\s*([\d.,]+)\s*(?:(?:EUR)?\s*/\s*(?:kg|g))?$",
    re.IGNORECASE,
)
BARE_WEIGHT = re.compile(r"^([\d.,]+)\s*(kg|g)$", re.IGNORECASE)
COUNT_QTY = re.compile(r"^([\d.,]+)\s*[@*x]\s*([\d.,]+)$", re.IGNORECASE)
TAX_CLASS = re.compile(r"^(\d{1,2}\s*%|[A-Z]|\d)$", re.IGNORECASE)  # 7%, A, or Globus's 1/2


class TranscriptionError(Exception):
    """A receipt file that cannot be trusted as ground truth."""


def _money(value: str, field: str, line_no: int) -> float:
    cleaned = value.replace("€", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        raise TranscriptionError(f"line {line_no}: {field} {value!r} is not a number")


def _parse_quantity(value: str, line_no: int) -> dict:
    """Return either a plain count or the weight fields the gold schema uses."""
    cleaned = value.replace("€", "").strip()
    if match := WEIGHT_QTY.match(cleaned):
        amount, unit, unit_price = match.groups()
        weight_kg = _money(amount, "weight", line_no)
        if unit.lower() == "g":
            weight_kg /= 1000
        return {
            "qty": 1,
            "sold_by_weight": True,
            "weight_kg": round(weight_kg, 4),
            "unit_price": _money(unit_price, "unit price", line_no),
            "unit_price_basis": "kg",
        }

    if match := BARE_WEIGHT.match(cleaned):
        # A weight with no unit price beside it. Record the weight and leave
        # unit_price absent rather than dividing it out — a derived number the
        # receipt never printed does not belong in ground truth.
        amount, unit = match.groups()
        weight_kg = _money(amount, "weight", line_no)
        if unit.lower() == "g":
            weight_kg /= 1000
        return {"qty": 1, "sold_by_weight": True, "weight_kg": round(weight_kg, 4)}

    if match := COUNT_QTY.match(cleaned):
        first, second = (_money(g, "quantity", line_no) for g in match.groups())
        # Receipts print "<unit price> * <count>". Accept the reverse too, by
        # reading whichever side is a whole number as the count.
        if second.is_integer():
            unit_gross, count = first, second
        elif first.is_integer():
            unit_gross, count = second, first
        else:
            raise TranscriptionError(
                f"line {line_no}: in {value!r} neither side is a whole number, "
                f"so which one is the item count is ambiguous"
            )
        return {"qty": int(count), "unit_gross": round(unit_gross, 2)}

    count = _money(value, "qty", line_no)
    if count <= 0:
        raise TranscriptionError(f"line {line_no}: qty {value!r} must be positive")
    return {"qty": int(count) if count.is_integer() else count}


def _parse_optional_fields(extras: list[str], line_no: int) -> tuple[float, str | None]:
    discount, tax_class = 0.0, None
    for extra in extras:
        if not extra:
            continue
        if TAX_CLASS.match(extra.replace(" ", "")):
            tax_class = extra.replace(" ", "").upper()
        elif extra.lstrip().startswith("-"):
            discount = _money(extra, "discount", line_no)
        else:
            raise TranscriptionError(
                f"line {line_no}: cannot tell whether {extra!r} is a discount "
                f"(write it as -0.20) or a tax class (write it as 7% or A)"
            )
    return discount, tax_class


def _parse_product(fields: list[str], line_no: int) -> dict:
    if len(fields) < 3:
        raise TranscriptionError(
            f"line {line_no}: expected at least 'name | qty | price', found {len(fields)} field(s)"
        )
    if len(fields) > 5:
        raise TranscriptionError(f"line {line_no}: found {len(fields)} fields, expected at most 5")

    raw_name, qty_text, price_text, *extras = fields
    if not raw_name:
        raise TranscriptionError(f"line {line_no}: missing item name")

    quantity = _parse_quantity(qty_text, line_no)
    gross = _money(price_text, "price", line_no)
    discount, tax_class = _parse_optional_fields(extras, line_no)

    if quantity.get("sold_by_weight") and "unit_price" in quantity:
        expected = quantity["weight_kg"] * quantity["unit_price"]
        if abs(expected - gross) > WEIGHT_TOLERANCE:
            raise TranscriptionError(
                f"line {line_no}: {quantity['weight_kg']}kg x {quantity['unit_price']:.2f} "
                f"= {expected:.2f}, but the price reads {gross:.2f} "
                f"— re-check {raw_name!r} against the photo"
            )

    if (unit_gross := quantity.get("unit_gross")) is not None:
        expected = unit_gross * quantity["qty"]
        if abs(expected - gross) > TOLERANCE:
            raise TranscriptionError(
                f"line {line_no}: {quantity['qty']} x {unit_gross:.2f} = {expected:.2f}, "
                f"but the line total reads {gross:.2f} "
                f"— re-check {raw_name!r} against the photo"
            )

    upper = raw_name.upper()
    # Empties returns are named differently per chain — "Pfand Return" at Lidl,
    # "Retoure Leergut" at Globus — so a negative price is the reliable signal.
    if gross < 0 or "LEERGUT" in upper or "RETOURE" in upper:
        # Gold records these as a bare negative net, with no gross or discount
        # columns. Match that shape exactly so both sets stay comparable.
        return {
            "type": "deposit_return",
            "raw_name": raw_name,
            **quantity,
            "net": round(gross + discount, 2),
            "tax_class": tax_class,
        }

    line = {
        "type": "deposit" if upper.startswith("PFAND") else "product",
        "raw_name": raw_name,
        **quantity,
        "gross": round(gross, 2),
        "discount": round(discount, 2),
        "net": round(gross + discount, 2),
        "tax_class": tax_class,
    }
    if line["qty"] != 1 and not quantity.get("sold_by_weight") and "unit_gross" not in line:
        line["unit_gross"] = round(gross / line["qty"], 2)
    return line


def parse_receipt(text: str) -> dict:
    lines = [
        (n, stripped)
        for n, raw in enumerate(text.splitlines(), start=1)
        if (stripped := raw.strip()) and not stripped.startswith("#")
    ]
    if len(lines) < 4:
        raise TranscriptionError(
            "expected an image name, a store line, a date line, and at least one item"
        )

    (_, source_image), (store_no, store_line), (header_no, header_line) = lines[:3]

    store_parts = [p.strip() for p in store_line.split("|")]
    if len(store_parts) != 2:
        raise TranscriptionError(f"line {store_no}: expected 'STORE | LOCATION'")
    store, store_location = store_parts

    header_parts = [p.strip() for p in header_line.split("|")]
    if len(header_parts) != 3:
        raise TranscriptionError(f"line {header_no}: expected 'DATE | TIME | CURRENCY'")
    date, time, currency = header_parts

    product_lines: list[dict] = []
    printed_total: float | None = None
    printed_savings: float | None = None
    tax_buckets: dict[str, float] = {}

    for line_no, line in lines[3:]:
        if line.upper().startswith("TAX "):
            # Receipt-level VAT summary, e.g. "TAX 19% 5.98". Some receipts print
            # only this and no per-line class — the buckets are then the only
            # honest VAT signal available.
            parts = line.split()
            if len(parts) != 3:
                raise TranscriptionError(f"line {line_no}: expected 'TAX <rate> <amount>'")
            tax_buckets[parts[1].replace(" ", "").upper()] = _money(parts[2], "tax bucket", line_no)
            continue
        if line.upper().startswith("SAVINGS"):
            # A receipt-level savings recap (Lidl "Preisvorteil"). Already
            # reflected in the item prices, so it is recorded but never summed.
            printed_savings = abs(_money(line.split(None, 1)[1], "savings", line_no))
            continue
        if line.upper().startswith("TOTAL"):
            remainder = line.split(None, 1)
            if len(remainder) != 2:
                raise TranscriptionError(f"line {line_no}: expected 'TOTAL <amount>'")
            printed_total = _money(remainder[1], "total", line_no)
            continue
        product_lines.append(_parse_product([f.strip() for f in line.split("|")], line_no))

    if not product_lines:
        raise TranscriptionError("no item lines found")
    if printed_total is None:
        raise TranscriptionError(
            "no 'TOTAL <amount>' line found — copy the amount the receipt says you paid"
        )

    if tax_buckets:
        bucket_sum = round(sum(tax_buckets.values()), 2)
        if abs(bucket_sum - printed_total) > TOLERANCE:
            raise TranscriptionError(
                f"tax buckets sum to {bucket_sum:.2f} but the receipt says "
                f"{printed_total:.2f} — re-check the VAT summary"
            )

    computed = round(sum(line["net"] for line in product_lines), 2)
    if abs(computed - printed_total) > TOLERANCE:
        raise TranscriptionError(
            f"item lines sum to {computed:.2f} but the receipt says {printed_total:.2f} "
            f"(off by {computed - printed_total:+.2f}) — an item is missing, "
            f"duplicated, or mistyped"
        )

    return {
        "source_image": source_image,
        "store": store,
        "store_location": store_location,
        "date": date,
        "time": time,
        "currency": currency,
        "lines": product_lines,
        "printed_total": round(printed_total, 2),
        **({"tax_buckets": tax_buckets} if tax_buckets else {}),
        **({"printed_savings": round(printed_savings, 2)} if printed_savings is not None else {}),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert transcriptions into held-out ground truth")
    ap.add_argument("--raw-dir", default="data/holdout/raw")
    ap.add_argument("--output-dir", default="data/holdout")
    args = ap.parse_args()

    raw_dir = Path(args.raw_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sources = sorted(raw_dir.glob("*.txt"))
    if not sources:
        print(f"No .txt files in {raw_dir}", file=sys.stderr)
        return 1

    written = failures = 0
    for source in sources:
        try:
            receipt = parse_receipt(source.read_text(encoding="utf-8"))
        except TranscriptionError as exc:
            print(f"FAIL {source.name}: {exc}", file=sys.stderr)
            failures += 1
            continue

        destination = output_dir / f"{source.stem}.json"
        destination.write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        written += 1
        print(
            f"  ok  {source.name} -> {destination.name}  "
            f"({len(receipt['lines'])} lines, {receipt['printed_total']:.2f})"
        )

    print(f"\n{written} receipt(s) written, {failures} rejected")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
