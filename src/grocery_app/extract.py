"""Extract structured receipt data from a photo with a vision model.

The pipeline step this project was missing: photo -> JSON in the same shape as
`data/gold/`. One API call per image, constrained to a JSON schema so the output
is always parseable, with the extraction rules learned from hand-transcribing
the held-out set (`docs/receipt-quirks.md`) written into the prompt.

Every result is cached under `<out>/<model>/<prompt version>/<image>.json` with
a sidecar `.meta.json` recording token usage and cost. Re-running only bills for
images whose model or prompt version changed, so the evaluation harness can be
run freely between prompt iterations.

Honesty rules baked in: the model is told to transcribe literally, never to
repair text, never to guess a tax class the receipt does not print, and to drop
lines the receipt itself reversed. Whether it obeys is what `eval` measures.
"""

from __future__ import annotations

import base64
import io
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from PIL import Image, ImageOps

# Measured on the held-out set: Sonnet 5 made 1 error in 180 lines to Opus 5's 6,
# at half the cost. Opus tends to "repair" what it reads (brand names corrected
# into dictionary words, suffixes dropped), which is wrong for transcription.
# See docs/designs/receipt-ingestion-pipeline.md.
DEFAULT_MODEL = "claude-sonnet-5"
PROMPT_VERSION = "v1"

# Server-side refusal fallbacks are only accepted on these models; Sonnet and
# Haiku reject the parameter with a 400.
FALLBACK_MODELS = {"claude-opus-5", "claude-fable-5", "claude-fable-5-1"}

# Opus 5 / Sonnet 5 accept up to 2576 px on the long edge; anything larger is
# downscaled server-side anyway, so sending more only costs upload time.
MAX_LONG_EDGE = 2576
JPEG_QUALITY = 90

# USD per million tokens, for the per-run cost line. Cache reads/writes are
# priced relative to input. Update alongside the model table when it changes.
PRICES_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-opus-5": {"input": 5.0, "output": 25.0, "cache_write": 6.25, "cache_read": 0.5},
    "claude-sonnet-5": {"input": 2.0, "output": 10.0, "cache_write": 2.5, "cache_read": 0.2},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0, "cache_write": 1.25, "cache_read": 0.1},
}

SYSTEM_PROMPT = """\
You transcribe photographed German grocery receipts into structured JSON. The
output is graded field-by-field against a human transcription of the same paper,
so fidelity to what is printed matters more than readability.

Rules, in priority order:

1. Transcribe item names literally. Keep truncations (`BioBabyWasserme`), odd
   capitalisation, abbreviations, and lowercase starts exactly as printed. Some
   printers render umlauts as `?` (`SAATENBR?TCHEN`) — keep the `?`; do not
   restore the umlaut. Never expand, correct, or normalise a name.

2. Include only what was actually bought. Some receipts print an item that was
   scanned and then immediately reversed (a "Storno"/"Sofortstorno" line, or a
   matching negative line directly after it). Leave both the item and its
   reversal out. The receipt's own printed total excludes them, and your line
   nets must sum to that total.

3. One entry per printed item line, in printed order. Do not merge repeated
   items into one line with a higher quantity unless the receipt itself prints
   them as one line with a count.

4. Quantities and weights:
   - A line printed as `<unit price> x <count>` (e.g. `0,99 x 2`) has that
     count as `qty`, the unit price as `unit_gross`, and the printed line total
     as `gross`.
   - A line sold by weight (e.g. `0,472 kg x 2,99 EUR/kg`) has `qty` 1,
     `sold_by_weight` true, `weight_kg`, `unit_price`, `unit_price_basis` "kg".
     If the receipt prints a weight but no unit price, set `unit_price` null.
   - Otherwise `qty` is 1 and the size in the name stays in the name.

5. Prices: `gross` is the printed line amount. If a discount line is attached
   to the item (e.g. "Preisvorteil", "Rabatt", a personal discount), put it in
   `discount` as a negative number; otherwise `discount` is 0. `net` is
   `gross + discount`. A receipt-level savings recap ("Preisvorteil gesamt",
   "Sie sparen") is NOT a line — report it in `printed_savings`.

6. Deposits: a "Pfand" charge is its own line with `type` "deposit". Returned
   empties ("Leergut", "Retoure", "Pfand-Rückgabe", any negative Pfand) are
   `type` "deposit_return" with a negative `net`.

7. Tax class: copy exactly what the line prints — a letter (`A`, `B`) or a rate
   (`7%`, `19%`). If the line prints nothing, set `tax_class` null. Never infer
   it from the VAT summary or from what kind of product it is.

8. Header and totals:
   - `store`: the chain name as printed at the top (e.g. `Lidl`, `ALDI SÜD`).
   - `store_location`: the address line(s) as printed, joined with ", ".
   - `date` as YYYY-MM-DD, `time` as HH:MM (24h), `currency` "EUR".
   - `printed_total`: the amount actually paid ("Summe", "zu zahlen", "Total").
   - `tax_buckets`: the VAT summary as a list of {rate, amount} with the gross
     amount per rate (e.g. [{"rate": "7%", "amount": 21.43}]). If the receipt
     prints net and VAT separately, add them. Omit rates not printed. Null if
     there is no summary.

Numbers use a decimal point, never a comma, and carry two decimals. Ignore
everything that is not an item line, the header, or the totals: cashier names,
loyalty programme text, payment method, footer messages.
"""

LINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["product", "deposit", "deposit_return"]},
        "raw_name": {"type": "string"},
        "qty": {"type": "number"},
        "sold_by_weight": {"type": "boolean"},
        "weight_kg": {"type": ["number", "null"]},
        "unit_price": {"type": ["number", "null"]},
        "unit_price_basis": {"type": ["string", "null"]},
        "unit_gross": {"type": ["number", "null"]},
        "gross": {"type": "number"},
        "discount": {"type": "number"},
        "net": {"type": "number"},
        "tax_class": {"type": ["string", "null"]},
    },
    "required": [
        "type", "raw_name", "qty", "sold_by_weight", "weight_kg", "unit_price",
        "unit_price_basis", "unit_gross", "gross", "discount", "net", "tax_class",
    ],
    "additionalProperties": False,
}

RECEIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "store": {"type": "string"},
        "store_location": {"type": "string"},
        "date": {"type": "string"},
        "time": {"type": "string"},
        "currency": {"type": "string"},
        "lines": {"type": "array", "items": LINE_SCHEMA},
        "printed_total": {"type": "number"},
        "printed_savings": {"type": ["number", "null"]},
        "tax_buckets": {
            "type": ["array", "null"],
            "items": {
                "type": "object",
                "properties": {"rate": {"type": "string"}, "amount": {"type": "number"}},
                "required": ["rate", "amount"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "store", "store_location", "date", "time", "currency", "lines",
        "printed_total", "printed_savings", "tax_buckets",
    ],
    "additionalProperties": False,
}


class ExtractionError(Exception):
    """The model call completed but did not yield a usable receipt."""


@dataclass(frozen=True)
class Extraction:
    receipt: dict[str, Any]
    meta: dict[str, Any]


def prepare_image(path: str | Path, max_long_edge: int = MAX_LONG_EDGE) -> bytes:
    """Load a photo, apply its EXIF rotation, downscale, re-encode as JPEG.

    Phones store the sensor image plus an orientation tag; without applying the
    tag a portrait receipt arrives sideways. Downscaling to the model's maximum
    input size keeps uploads small without losing anything the model would see.
    """
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
        long_edge = max(image.size)
        if long_edge > max_long_edge:
            scale = max_long_edge / long_edge
            image = image.resize(
                (round(image.width * scale), round(image.height * scale)),
                Image.Resampling.LANCZOS,
            )
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buffer.getvalue()


def _tidy_line(line: dict[str, Any]) -> dict[str, Any]:
    """Drop the schema's nullable placeholders so the shape matches gold."""
    tidy: dict[str, Any] = {"type": line["type"], "raw_name": line["raw_name"]}
    qty = line["qty"]
    tidy["qty"] = int(qty) if float(qty).is_integer() else qty
    if line.get("sold_by_weight"):
        tidy["sold_by_weight"] = True
        if line.get("weight_kg") is not None:
            tidy["weight_kg"] = line["weight_kg"]
        if line.get("unit_price") is not None:
            tidy["unit_price"] = line["unit_price"]
            tidy["unit_price_basis"] = line.get("unit_price_basis") or "kg"
    elif line.get("unit_gross") is not None and tidy["qty"] != 1:
        tidy["unit_gross"] = line["unit_gross"]

    if line["type"] == "deposit_return":
        tidy["net"] = round(line["net"], 2)
    else:
        tidy["gross"] = round(line["gross"], 2)
        tidy["discount"] = round(line.get("discount") or 0.0, 2)
        tidy["net"] = round(line["net"], 2)
    tidy["tax_class"] = line.get("tax_class")
    return tidy


def parse_model_output(text: str, source_image: str) -> dict[str, Any]:
    """Turn the model's JSON text into a receipt in the gold shape."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"model output is not valid JSON: {exc}") from exc

    receipt: dict[str, Any] = {
        "source_image": source_image,
        "store": raw["store"],
        "store_location": raw["store_location"],
        "date": raw["date"],
        "time": raw["time"],
        "currency": raw["currency"],
        "lines": [_tidy_line(line) for line in raw["lines"]],
        "printed_total": round(raw["printed_total"], 2),
    }
    if raw.get("tax_buckets"):
        receipt["tax_buckets"] = {
            bucket["rate"]: round(bucket["amount"], 2) for bucket in raw["tax_buckets"]
        }
    if raw.get("printed_savings") is not None:
        receipt["printed_savings"] = round(raw["printed_savings"], 2)

    computed = round(sum(line["net"] for line in receipt["lines"]), 2)
    receipt["computed_total"] = computed
    receipt["reconciled"] = abs(computed - receipt["printed_total"]) < 0.011
    return receipt


def estimate_cost(model: str, usage: dict[str, int]) -> float | None:
    prices = PRICES_PER_MTOK.get(model)
    if prices is None:
        return None
    return round(
        usage.get("input_tokens", 0) * prices["input"] / 1e6
        + usage.get("output_tokens", 0) * prices["output"] / 1e6
        + usage.get("cache_creation_input_tokens", 0) * prices["cache_write"] / 1e6
        + usage.get("cache_read_input_tokens", 0) * prices["cache_read"] / 1e6,
        5,
    )


def build_request(model: str, image_bytes: bytes) -> dict[str, Any]:
    """The full request for one receipt photo, as keyword arguments."""
    request: dict[str, Any] = {
        "model": model,
        "max_tokens": 16000,
        "system": [
            {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
        ],
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64.standard_b64encode(image_bytes).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": "Transcribe this receipt."},
                ],
            }
        ],
        "output_config": {"format": {"type": "json_schema", "schema": RECEIPT_SCHEMA}},
    }
    if model in FALLBACK_MODELS:
        request["betas"] = ["server-side-fallback-2026-07-01"]
        request["fallbacks"] = "default"
    return request


def extract_receipt(
    image_path: str | Path,
    client: anthropic.Anthropic,
    model: str = DEFAULT_MODEL,
) -> Extraction:
    """One photo -> one receipt, via a single structured-output model call."""
    image_path = Path(image_path)
    image_bytes = prepare_image(image_path)
    started = time.monotonic()

    response = client.beta.messages.create(**build_request(model, image_bytes))
    elapsed = round(time.monotonic() - started, 1)

    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        raise ExtractionError(
            f"model declined the request ({getattr(details, 'category', None)}): "
            f"{getattr(details, 'explanation', '')}"
        )
    if response.stop_reason == "max_tokens":
        raise ExtractionError("model output was cut off at max_tokens")

    text = next((block.text for block in response.content if block.type == "text"), None)
    if text is None:
        raise ExtractionError(f"no text block in response (stop_reason={response.stop_reason})")

    receipt = parse_model_output(text, image_path.name)
    usage = response.usage.to_dict() if hasattr(response.usage, "to_dict") else dict(response.usage)
    usage = {k: v for k, v in usage.items() if isinstance(v, int)}
    meta = {
        "source_image": image_path.name,
        "model": response.model,
        "requested_model": model,
        "prompt_version": PROMPT_VERSION,
        "request_id": getattr(response, "_request_id", None),
        "stop_reason": response.stop_reason,
        "usage": usage,
        "cost_usd": estimate_cost(model, usage),
        "seconds": elapsed,
        "image_bytes_sent": len(image_bytes),
    }
    return Extraction(receipt=receipt, meta=meta)


def output_dir(base: str | Path, model: str, prompt_version: str = PROMPT_VERSION) -> Path:
    return Path(base) / model / prompt_version


def extract_directory(
    images_dir: str | Path,
    out_base: str | Path,
    model: str = DEFAULT_MODEL,
    force: bool = False,
    limit: int | None = None,
    client: anthropic.Anthropic | None = None,
    log=print,
) -> dict[str, Any]:
    """Extract every image in a directory, skipping ones already cached."""
    images = sorted(
        p for p in Path(images_dir).iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    if limit:
        images = images[:limit]
    target = output_dir(out_base, model)
    target.mkdir(parents=True, exist_ok=True)

    summary = {"extracted": 0, "cached": 0, "failed": 0, "cost_usd": 0.0, "out_dir": str(target)}
    for image in images:
        destination = target / f"{image.stem}.json"
        meta_path = target / f"{image.stem}.meta.json"
        if destination.exists() and not force:
            summary["cached"] += 1
            log(f"  cached  {image.name}")
            continue

        if client is None:
            client = anthropic.Anthropic()
        try:
            result = extract_receipt(image, client, model=model)
        except (ExtractionError, anthropic.APIError) as exc:
            summary["failed"] += 1
            log(f"  FAILED  {image.name}: {exc}")
            meta_path.write_text(
                json.dumps({"source_image": image.name, "error": str(exc), "model": model,
                            "prompt_version": PROMPT_VERSION}, indent=2) + "\n",
                encoding="utf-8",
            )
            continue

        destination.write_text(
            json.dumps(result.receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        meta_path.write_text(json.dumps(result.meta, indent=2) + "\n", encoding="utf-8")
        summary["extracted"] += 1
        summary["cost_usd"] += result.meta["cost_usd"] or 0.0
        flag = "" if result.receipt["reconciled"] else "  (does not reconcile)"
        log(
            f"  ok      {image.name}  {len(result.receipt['lines'])} lines, "
            f"{result.receipt['printed_total']:.2f}, ${result.meta['cost_usd']:.3f}, "
            f"{result.meta['seconds']}s{flag}"
        )

    summary["cost_usd"] = round(summary["cost_usd"], 4)
    return summary
