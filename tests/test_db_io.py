"""Rows to and from the file shapes, without a database: the conversions are
pure, so a broken round trip shows up here before the PostgreSQL tests run."""

import pytest

from grocery_app.db.io import (
    line_from_dict,
    product_from_dict,
    product_to_dict,
    receipt_from_dict,
    receipt_to_dict,
    resolution_from_dict,
    resolution_to_dict,
    store_slug,
)
from tests.conftest import PRODUCTS, RECEIPTS, RESOLUTION


@pytest.mark.parametrize("receipt", RECEIPTS, ids=lambda r: r["source_image"])
def test_a_receipt_round_trips(receipt):
    assert receipt_to_dict(receipt_from_dict(receipt)) == receipt


def test_optional_header_fields_round_trip_when_present():
    receipt = dict(RECEIPTS[0], store_location="Musterstraße 1", tax_buckets={"7%": 0.2},
                   printed_savings=0.5, is_duplicate=True)
    assert receipt_to_dict(receipt_from_dict(receipt)) == receipt


@pytest.mark.parametrize("product_id", sorted(PRODUCTS["products"]))
def test_a_product_round_trips(product_id):
    d = PRODUCTS["products"][product_id]
    assert product_to_dict(product_from_dict(product_id, d)) == d


def test_enrichment_fields_round_trip_only_when_present():
    d = dict(PRODUCTS["products"]["p-0001"], nutrition={"nutriscore": "a", "nova": 1})
    assert product_to_dict(product_from_dict("p-0001", d)) == d


@pytest.mark.parametrize("entry", RESOLUTION["entries"], ids=lambda e: e["raw_name"])
def test_a_resolution_round_trips(entry):
    assert resolution_to_dict(resolution_from_dict(entry)) == entry


def test_a_family_resolution_round_trips():
    entry = {"store": "Musterladen", "raw_name": "MU Chia", "line_type": "product",
             "product_id": None, "confirmed_by": "test", "confirmed_at": "2026-01-01",
             "source": "test", "product_ids": ["p-0002", "p-0003"],
             "status": "ambiguous_on_receipt"}
    assert resolution_to_dict(resolution_from_dict(entry)) == entry


def test_an_unknown_field_is_refused_not_dropped():
    with pytest.raises(ValueError, match="surprise"):
        receipt_from_dict(dict(RECEIPTS[0], surprise=1))
    with pytest.raises(ValueError, match="surprise"):
        line_from_dict(0, dict(RECEIPTS[0]["lines"][0], surprise=1))
    with pytest.raises(ValueError, match="surprise"):
        product_from_dict("p-0001", dict(PRODUCTS["products"]["p-0001"], surprise=1))


def test_a_line_without_a_net_amount_is_refused():
    line = {k: v for k, v in RECEIPTS[0]["lines"][0].items() if k != "net"}
    with pytest.raises(ValueError, match="net"):
        line_from_dict(0, line)


def test_store_slug_matches_the_directory_names():
    assert store_slug("GLOBUS") == "globus"
    assert store_slug("ALDI SÜD") == "aldi-sued"
    assert store_slug("Musterladen") == "musterladen"
