"""Tests for the extraction module that need no API access."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from grocery_app.extract import (
    ExtractionError,
    build_request,
    estimate_cost,
    parse_model_output,
    prepare_image,
)


def test_fallbacks_only_sent_to_models_that_accept_them():
    opus = build_request("claude-opus-5", b"img")
    sonnet = build_request("claude-sonnet-5", b"img")
    assert opus["fallbacks"] == "default" and "betas" in opus
    assert "fallbacks" not in sonnet and "betas" not in sonnet


def test_request_constrains_output_to_the_receipt_schema():
    request = build_request("claude-opus-5", b"img")
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert request["messages"][0]["content"][0]["type"] == "image"


def test_prepare_image_applies_exif_rotation_and_downscales(tmp_path):
    # A landscape 4000x3000 image tagged "rotate 90" must come out portrait,
    # and no longer than the model's maximum edge.
    path = tmp_path / "receipt.jpg"
    image = Image.new("RGB", (4000, 3000), "white")
    exif = image.getexif()
    exif[0x0112] = 6  # orientation: rotate 90 CW
    image.save(path, format="JPEG", exif=exif.tobytes())

    out = Image.open(io.BytesIO(prepare_image(path, max_long_edge=2576)))
    assert out.height > out.width, "EXIF rotation was not applied"
    assert max(out.size) == 2576


def test_parse_model_output_matches_gold_shape():
    text = json.dumps({
        "store": "Lidl", "store_location": "Dudweiler", "date": "2026-06-26",
        "time": "11:49", "currency": "EUR", "printed_total": 3.23,
        "printed_savings": None,
        "tax_buckets": [{"rate": "A", "amount": 2.98}, {"rate": "B", "amount": 0.25}],
        "lines": [
            {"type": "product", "raw_name": "Snack Gurken", "qty": 2.0,
             "sold_by_weight": False, "weight_kg": None, "unit_price": None,
             "unit_price_basis": None, "unit_gross": 0.99, "gross": 1.98,
             "discount": 0.0, "net": 1.98, "tax_class": "A"},
            {"type": "product", "raw_name": "Tomaten", "qty": 1,
             "sold_by_weight": True, "weight_kg": 0.472, "unit_price": 2.12,
             "unit_price_basis": "kg", "unit_gross": None, "gross": 1.0,
             "discount": 0.0, "net": 1.0, "tax_class": "A"},
            {"type": "deposit_return", "raw_name": "Leergut", "qty": 1,
             "sold_by_weight": False, "weight_kg": None, "unit_price": None,
             "unit_price_basis": None, "unit_gross": None, "gross": -0.25,
             "discount": 0.0, "net": 0.25, "tax_class": "B"},
        ],
    })
    receipt = parse_model_output(text, "IMG_1.jpeg")

    assert receipt["source_image"] == "IMG_1.jpeg"
    assert receipt["tax_buckets"] == {"A": 2.98, "B": 0.25}
    count_line, weight_line, return_line = receipt["lines"]
    assert count_line["qty"] == 2 and count_line["unit_gross"] == 0.99
    assert "weight_kg" not in count_line, "nullable placeholders must be dropped"
    assert weight_line["sold_by_weight"] and weight_line["unit_price_basis"] == "kg"
    assert "gross" not in return_line, "returns carry a bare net, like gold"
    assert receipt["computed_total"] == 3.23 and receipt["reconciled"] is True


def test_parse_model_output_rejects_non_json():
    with pytest.raises(ExtractionError):
        parse_model_output("not json", "IMG_1.jpeg")


def test_estimate_cost_uses_model_prices():
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    assert estimate_cost("claude-opus-5", usage) == 5.0
    assert estimate_cost("claude-sonnet-5", usage) == 2.0
    assert estimate_cost("unknown-model", usage) is None
