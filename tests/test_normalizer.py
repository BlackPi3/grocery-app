"""The normalizer's join, on made-up data only: nothing here comes from a receipt."""

from grocery_app.normalizer import load_resolution, normalize_line

PRODUCTS = {
    "p-1": {"name": "Dusche Sweet Treat", "brand": "Dove", "product_line": None,
            "variant": "Sweet Treat", "category": "Body care", "is_own_brand": False,
            "is_organic": False, "size": {"count": 1, "value": 250.0, "unit": "ml"}},
    "p-2": {"name": "Dusche Fruchtig Leicht", "brand": "Dove", "product_line": None,
            "variant": "Fruchtig Leicht", "category": "Body care", "is_own_brand": False,
            "is_organic": False, "size": {"count": 1, "value": 250.0, "unit": "ml"}},
}
RECEIPT = {"store": "GLOBUS", "date": "2026-01-01", "source_image": "fake.jpeg"}
LINE = {"type": "product", "raw_name": "Dove Dusche", "qty": 1, "gross": 2.49, "net": 2.24}


def test_family_keeps_what_the_candidates_agree_on_and_nothing_else():
    record = normalize_line(LINE, RECEIPT, {("globus", "Dove Dusche"): ["p-1", "p-2"]}, PRODUCTS)
    assert record["resolution"] == "family"
    assert record["product_id"] is None and record["resolved"] is False
    assert record["candidate_ids"] == ["p-1", "p-2"]
    assert record["brand"] == "Dove" and record["is_own_brand"] is False
    assert record["variant"] is None
    assert record["product"] == "2 candidates"
    # Pack sizes may differ across a family, so no unit price is derived.
    assert record["unit_price"] is None


def test_single_candidate_is_an_exact_resolution():
    record = normalize_line(LINE, RECEIPT, {("globus", "Dove Dusche"): ["p-1"]}, PRODUCTS)
    assert record["resolution"] == "exact" and record["product_id"] == "p-1"
    assert record["resolved"] is True and record["candidate_ids"] == []
    assert record["variant"] == "Sweet Treat"
    assert record["unit_price"] == {"amount": 8.96, "per": "l"}


def test_unknown_name_is_none_not_family():
    record = normalize_line(LINE, RECEIPT, {}, PRODUCTS)
    assert record["resolution"] == "none" and record["candidate_ids"] == []
    assert "brand" not in record


def test_load_resolution_reads_both_shapes(tmp_path):
    path = tmp_path / "resolution.json"
    path.write_text('{"entries": ['
                    '{"store": "GLOBUS", "raw_name": "A", "product_id": "p-1"},'
                    '{"store": "GLOBUS", "raw_name": "B", "product_id": null,'
                    ' "product_ids": ["p-1", "p-2"]},'
                    '{"store": "GLOBUS", "raw_name": "Leergut", "product_id": null}]}',
                    encoding="utf-8")
    assert load_resolution(path) == {("globus", "A"): ["p-1"], ("globus", "B"): ["p-1", "p-2"]}
