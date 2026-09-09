"""Invariants of the product / resolution contract.

These two files are the join every downstream consumer depends on, and they are
edited by hand as matches are confirmed. A dangling product_id or a duplicated
id would surface as a silently unresolved item rather than an error, so the
cheapest place to catch it is here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def products():
    return json.loads((DATA / "products.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def resolution():
    return json.loads((DATA / "resolution.json").read_text(encoding="utf-8"))


def test_product_ids_are_opaque_and_unique(products):
    ids = list(products["products"])
    assert ids == sorted(set(ids))
    for product_id in ids:
        assert re.fullmatch(r"p-\d{4}", product_id), product_id


def test_next_id_is_ahead_of_every_existing_id(products):
    highest = max(int(pid.split("-")[1]) for pid in products["products"])
    assert products["meta"]["next_id"] > highest


def test_every_product_keeps_a_readable_label_and_a_size_shape(products):
    for product_id, product in products["products"].items():
        assert product["label"], product_id
        size = product["size"]
        assert set(size) == {"count", "value", "unit"}
        assert isinstance(product["eans"], list)


def test_every_resolved_entry_points_at_a_real_product(products, resolution):
    known = set(products["products"])
    for entry in resolution["entries"]:
        if entry["product_id"] is not None:
            assert entry["product_id"] in known, entry["raw_name"]


def test_non_product_lines_are_distinguished_from_unresolved_ones(resolution):
    """A deposit return is not an unresolved product, and conflating the two
    would quietly understate every coverage figure we report."""
    non_products = [e for e in resolution["entries"] if e["line_type"] != "product"]
    assert non_products, "expected at least the Leergut lines"
    for entry in non_products:
        assert entry["product_id"] is None


def test_a_name_never_resolves_to_two_products_within_one_store(resolution):
    seen: dict[tuple[str, str], str] = {}
    for entry in resolution["entries"]:
        key = (entry["store"], entry["raw_name"])
        assert key not in seen or seen[key] == entry["product_id"], key
        seen[key] = entry["product_id"]


def test_confirmed_entries_record_who_confirmed_them(resolution):
    """Provenance is the thing that keeps verified work distinguishable from a
    matcher's guess. Losing it once already caused a real misreading here."""
    for entry in resolution["entries"]:
        if entry["product_id"]:
            assert entry["confirmed_by"], entry["raw_name"]
            assert entry["source"], entry["raw_name"]
