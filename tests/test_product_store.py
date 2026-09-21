"""The product-store invariants, exercised on made-up files.

The real products.json and resolution.json are private and gitignored, so the
checks are tested here on fixtures that break each rule in turn. The last test
runs the same checks on the real files when they are present, so a bad bank of
matches still fails locally, and simply skips on a clean clone.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from grocery_app.product_store import problems

PRODUCTS = {
    "meta": {"next_id": 3},
    "products": {
        "p-0001": {"label": "Bio Eier", "name": "Bio Eier", "brand": "Alnatura",
                   "size": {"count": 1, "value": 10.0, "unit": "piece"}, "eans": ["4104420000001"]},
        "p-0002": {"label": "Dusche Sweet Treat", "name": "Dusche Sweet Treat", "brand": "Dove",
                   "size": {"count": 1, "value": 250.0, "unit": "ml"}, "eans": []},
    },
}
RESOLUTION = {
    "entries": [
        {"store": "GLOBUS", "raw_name": "ALN Bio Eier", "line_type": "product",
         "product_id": "p-0001", "confirmed_by": "reviewer", "source": "reviewed.csv"},
        {"store": "GLOBUS", "raw_name": "Dove Dusche", "line_type": "product",
         "product_id": None, "product_ids": ["p-0001", "p-0002"],
         "status": "ambiguous_on_receipt", "confirmed_by": "reviewer", "source": "reviewed.csv"},
        {"store": "GLOBUS", "raw_name": "Leergut", "line_type": "deposit_return",
         "product_id": None, "confirmed_by": None, "source": "receipts"},
    ]
}


def broken(products=None, resolution=None):
    """Fresh copies of the fixtures, with the caller's edits applied."""
    p, r = copy.deepcopy(PRODUCTS), copy.deepcopy(RESOLUTION)
    if products:
        products(p)
    if resolution:
        resolution(r)
    return problems(p, r)


def test_a_consistent_store_has_no_problems():
    assert problems(PRODUCTS, RESOLUTION) == []


def test_product_ids_must_be_opaque():
    def rename(p):
        p["products"]["kerrygold-butter"] = p["products"].pop("p-0002")
    assert any("not opaque" in m for m in broken(products=rename))


def test_next_id_must_stay_ahead_of_existing_ids():
    def stale(p):
        p["meta"]["next_id"] = 2
    assert any("next_id" in m for m in broken(products=stale))


def test_every_product_keeps_a_label_and_a_size_shape():
    def strip(p):
        p["products"]["p-0002"]["label"] = ""
        p["products"]["p-0002"]["size"] = {"value": 250.0}
    messages = broken(products=strip)
    assert any("label" in m for m in messages) and any("size" in m for m in messages)


def test_a_resolution_must_point_at_a_real_product():
    def dangling(r):
        r["entries"][0]["product_id"] = "p-0099"
    assert any("unknown product p-0099" in m for m in broken(resolution=dangling))


def test_a_family_is_several_ids_and_never_one_in_both_places():
    def both(r):
        r["entries"][1]["product_id"] = "p-0001"
    def lonely(r):
        r["entries"][1]["product_ids"] = ["p-0001"]
    assert any("family" in m for m in broken(resolution=both))
    assert any("family" in m for m in broken(resolution=lonely))


def test_non_product_lines_carry_no_product():
    def mislabelled(r):
        r["entries"][2]["product_id"] = "p-0001"
    assert any("non-product line" in m for m in broken(resolution=mislabelled))


def test_a_name_resolves_once_per_store():
    def twice(r):
        r["entries"].append(dict(r["entries"][0], product_id="p-0002"))
    assert any("more than once" in m for m in broken(resolution=twice))


def test_resolved_entries_record_who_confirmed_them():
    def anonymous(r):
        r["entries"][0]["confirmed_by"] = None
    assert any("confirmed_by" in m for m in broken(resolution=anonymous))


REAL = Path(__file__).resolve().parents[1] / "data" / "products"


@pytest.mark.skipif(not (REAL / "products.json").exists(), reason="private data not present")
def test_the_real_store_if_present_is_consistent():
    products = json.loads((REAL / "products.json").read_text(encoding="utf-8"))
    resolution = json.loads((REAL / "resolution.json").read_text(encoding="utf-8"))
    assert problems(products, resolution) == []


# --- types: a branded product hangs off a brandless one ----------------------


def add_type(p, **overrides):
    """A brandless type plus a branded product pointing at it."""
    p["products"]["p-0003"] = {"label": "Kartoffelchips", "name": "Kartoffelchips gesalzen",
                               "brand": None, "size": PRODUCTS["products"]["p-0001"]["size"],
                               "eans": [], **overrides}
    p["products"]["p-0002"]["parent_id"] = "p-0003"
    p["meta"]["next_id"] = 4


def test_a_type_and_its_brand_are_consistent():
    assert broken(products=add_type) == []


def test_a_parent_must_exist():
    def dangle(p):
        p["products"]["p-0002"]["parent_id"] = "p-0099"
    assert any("parent p-0099 does not exist" in m for m in broken(products=dangle))


def test_a_product_cannot_be_its_own_type():
    def loop(p):
        p["products"]["p-0002"]["parent_id"] = "p-0002"
    assert any("is its own parent" in m for m in broken(products=loop))


def test_a_type_must_be_brandless():
    # The whole point of a type is that it is the thing, not one maker's version
    # of it; a branded parent would make "own-brand vs brand" meaningless.
    def branded_parent(p):
        add_type(p, brand="Knusperhaus")
    assert any("has a brand, so it is not a type" in m for m in broken(products=branded_parent))


def test_a_type_may_not_have_a_type_of_its_own():
    # One level only: a chain makes "roll this up" ambiguous, and can cycle.
    def chain(p):
        add_type(p)
        p["products"]["p-0003"]["parent_id"] = "p-0001"
    assert any("has a parent of its own" in m for m in broken(products=chain))
