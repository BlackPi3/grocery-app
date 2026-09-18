"""The normalizer's join, on made-up data only: nothing here comes from a receipt."""

import json

from grocery_app.normalizer import load_receipts, load_resolution, normalize_line

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


def test_a_pinpoint_narrows_a_family_and_is_labelled_as_the_shoppers():
    from grocery_app.normalizer import normalize_receipt

    receipt = dict(RECEIPT, lines=[LINE, LINE])
    answers = {("fake.jpeg", 1): {"source_image": "fake.jpeg", "line_index": 1,
                                  "raw_name": "Dove Dusche", "product_id": "p-2"}}
    first, second = normalize_receipt(receipt, {("globus", "Dove Dusche"): ["p-1", "p-2"]},
                                      PRODUCTS, answers)
    assert first["resolution"] == "family" and first["product_id"] is None
    assert second["resolution"] == "user" and second["product_id"] == "p-2"
    assert second["variant"] == "Fruchtig Leicht" and second["candidate_ids"] == []
    assert second["unit_price"] == {"amount": 8.96, "per": "l"}


def test_a_pinpoint_is_refused_when_the_line_or_family_no_longer_matches():
    from grocery_app.normalizer import normalize_receipt

    receipt = dict(RECEIPT, lines=[LINE])
    family = {("globus", "Dove Dusche"): ["p-1", "p-2"]}
    # The line was re-transcribed under another name: the note is stale.
    stale = {("fake.jpeg", 0): {"raw_name": "Dove Deo", "product_id": "p-2"}}
    assert normalize_receipt(receipt, family, PRODUCTS, stale)[0]["resolution"] == "family"
    # The answer points outside the family the name resolves to.
    outside = {("fake.jpeg", 0): {"raw_name": "Dove Dusche", "product_id": "p-9"}}
    assert normalize_receipt(receipt, family, PRODUCTS, outside)[0]["resolution"] == "family"


def test_missing_line_resolutions_file_means_no_answers(tmp_path):
    from grocery_app.normalizer import load_line_resolutions

    assert load_line_resolutions(None) == {}
    assert load_line_resolutions(tmp_path / "absent.json") == {}


def test_the_paid_amount_narrows_a_family_when_exactly_one_price_fits():
    from grocery_app.normalizer import load_shelf_prices, priced_like

    seeds = {("globus", "Chiasamen"): ["p-1", "p-2"]}
    line = {"type": "product", "raw_name": "Chiasamen", "qty": 1, "gross": 3.99, "net": 3.59}
    shelf = {"p-1": {3.99}, "p-2": {2.49}}
    record = normalize_line(line, RECEIPT, seeds, PRODUCTS, shelf_prices=shelf)
    assert record["resolution"] == "price" and record["product_id"] == "p-1"
    assert record["resolved"] is True and record["candidate_ids"] == []
    # Two pots of the small pack: compare per item, not the line total.
    two = dict(line, qty=2, gross=4.98)
    assert priced_like(two, ["p-1", "p-2"], shelf) == "p-2"
    # Same price on both shelves says nothing.
    assert priced_like(line, ["p-1", "p-2"], {"p-1": {3.99}, "p-2": {3.99}}) is None
    assert priced_like(line, ["p-1", "p-2"], {}) is None
    assert load_shelf_prices(None) == {}


def test_shelf_prices_are_collected_across_listing_files(tmp_path):
    import json

    from grocery_app.normalizer import load_shelf_prices

    (tmp_path / "globus").mkdir()
    (tmp_path / "globus" / "listings.json").write_text(json.dumps({"listings": {
        "111": {"product_id": "p-1", "prices": [{"date": "2026-01-01", "price": 3.99}]},
        "222": {"product_id": "p-1", "prices": [{"date": "2026-02-01", "price": 4.29}]},
        "333": {"product_id": "p-2", "prices": []}}}), encoding="utf-8")
    assert load_shelf_prices(tmp_path) == {"p-1": {3.99, 4.29}}


def test_a_tax_class_means_different_rates_at_different_stores():
    from grocery_app.normalizer import tax_rate

    assert tax_rate("Lidl", "A") == 0.07 and tax_rate("Kaufland", "A") == 0.19
    assert tax_rate("GLOBUS", "2") == 0.07 and tax_rate("Globus", "1") == 0.19
    assert tax_rate("ALDI SÜD", "b") == 0.19
    # Unknown store, unknown class, or nothing printed: no guess.
    assert tax_rate("Some Shop", "A") is None
    assert tax_rate("Lidl", "C") is None
    assert tax_rate("Lidl", None) is None


def test_purchase_rows_carry_the_rate_beside_the_printed_class():
    line = dict(LINE, tax_class="1")
    record = normalize_line(line, RECEIPT, {}, PRODUCTS)
    assert record["tax_class"] == "1" and record["tax_rate"] == 0.19


def test_meta_sidecars_are_not_mistaken_for_receipts(tmp_path):
    """`purchases` must accept an extraction directory, where every IMG_x.json has
    an IMG_x.meta.json sidecar beside it."""
    receipt = {"source_image": "IMG_1.jpeg", "store": "GLOBUS", "date": "2026-07-14", "lines": []}
    (tmp_path / "IMG_1.json").write_text(json.dumps(receipt), encoding="utf-8")
    (tmp_path / "IMG_1.meta.json").write_text(
        json.dumps({"source_image": "IMG_1.jpeg", "cost_usd": 0.03}), encoding="utf-8"
    )
    assert load_receipts(tmp_path) == [receipt]
