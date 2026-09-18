"""Open Food Facts enrichment, on made-up records shaped like the API's."""

from __future__ import annotations

import json

from grocery_app.openfoodfacts import attributes_from, enrich

FOUND = {"status": 1, "code": "4000000000001", "fetched_at": "2026-01-01T00:00:00Z",
         "product": {"product_name": "Chia seeds", "product_name_de": "Chiasamen",
                     "brands": "Alnatura", "quantity": "500 g",
                     "categories_tags": ["en:plant-based-foods", "en:seeds", "en:chia"],
                     "labels_tags": ["en:organic", "en:eu-organic"],
                     "nutriscore_grade": "a", "nova_group": 1,
                     "allergens_tags": []}}
MISSING = {"status": 0, "code": "4000000000002", "fetched_at": "2026-01-01T00:00:00Z"}


def test_a_found_record_is_read_into_project_terms():
    got = attributes_from(FOUND)
    assert got["name"] == "Chiasamen" and got["brand"] == "Alnatura"
    assert got["category"] == "chia"
    assert got["categories"] == ["plant based foods", "seeds", "chia"]
    assert got["is_organic"] is True and got["nutriscore"] == "a" and got["nova"] == 1


def test_free_text_tags_do_not_pass_for_a_category():
    """Contributors can type anything into categories; only taxonomy entries
    (lowercase, hyphenated) count, and the deepest one wins."""
    typed = json.loads(json.dumps(FOUND))
    typed["product"]["categories_tags"] = ["en:meats", "en:chicken", "en:Hühnchen",
                                           "en:Snacks sucres"]
    assert attributes_from(typed)["category"] == "chicken"
    typed["product"]["categories_tags"] = ["en:Waffeln"]
    assert attributes_from(typed)["category"] is None


def test_no_organic_label_means_unknown_not_false():
    unlabelled = json.loads(json.dumps(FOUND))
    unlabelled["product"]["labels_tags"] = []
    assert attributes_from(unlabelled)["is_organic"] is None
    assert attributes_from(MISSING) is None


def test_enrich_fills_only_nulls_and_records_what_it_filled(tmp_path):
    products = tmp_path / "products.json"
    products.write_text(json.dumps({"meta": {"next_id": 4}, "products": {
        "p-0001": {"name": "Bio Chia Samen", "category": None, "is_organic": None,
                   "eans": ["4000000000001"]},
        "p-0002": {"name": "Confirmed Butter", "category": "Dairy", "is_organic": False,
                   "eans": ["4000000000001"]},
        "p-0003": {"name": "Unknown", "category": None, "is_organic": None,
                   "eans": ["4000000000002"]},
        "p-0004": {"name": "No barcode", "category": None, "is_organic": None, "eans": []},
    }}), encoding="utf-8")

    def fake_fetch(ean, cache_dir, force=False):
        return (FOUND if ean == "4000000000001" else MISSING), False

    summary = enrich(products, tmp_path / "off", fetch=fake_fetch)
    stored = json.loads(products.read_text())["products"]

    assert summary == {"with_ean": 3, "found": 2, "filled": 2, "cached": 0}
    assert stored["p-0001"]["category"] == "chia" and stored["p-0001"]["is_organic"] is True
    assert stored["p-0001"]["enrichment"]["filled"] == ["category", "is_organic"]
    assert stored["p-0001"]["nutrition"] == {"nutriscore": "a", "nova": 1}
    # A person's values stand, even when Open Food Facts disagrees.
    assert stored["p-0002"]["category"] == "Dairy" and stored["p-0002"]["is_organic"] is False
    assert stored["p-0002"]["enrichment"]["filled"] == []
    # Not found and no barcode: untouched.
    assert "enrichment" not in stored["p-0003"] and "enrichment" not in stored["p-0004"]
