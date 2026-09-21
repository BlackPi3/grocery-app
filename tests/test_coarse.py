"""Coarse resolution writes what is known and refuses to invent the rest."""

import csv
import json

import pytest

from grocery_app.coarse import confirm

ROWS = [
    # same product, two tills, two spellings of the name
    {"store": "Musterladen", "raw_name": "Muster Cola 1.25L", "route": "search",
     "brand": "Musterbrause", "product": "Cola Classic", "ean": "", "options": "", "your_note": ""},
    {"store": "Woanders", "raw_name": "Muster Cola 1,25l", "route": "search",
     "brand": "Musterbrause", "product": "Cola Classic", "ean": "", "options": "", "your_note": ""},
    # a confirmed barcode
    {"store": "Musterladen", "raw_name": "Muster Keks 200g", "route": "known",
     "brand": "Kekshaus", "product": "Butterkeks", "ean": "1234567890123",
     "options": "", "your_note": ""},
    # the reviewer flagged their own brand guess
    {"store": "Musterladen", "raw_name": "Unklar Riegel", "route": "search",
     "brand": "Vielleicht?", "product": "Schokoriegel", "ean": "", "options": "", "your_note": ""},
    # routes that must not become products
    {"store": "Tante Emma", "raw_name": "Diverse Waren", "route": "ask",
     "brand": "", "product": "category line", "ean": "", "options": "", "your_note": ""},
    {"store": "Musterladen", "raw_name": "Tragetasche", "route": "nonproduct",
     "brand": "", "product": "carrier bag", "ean": "", "options": "", "your_note": ""},
]


@pytest.fixture
def catalog(tmp_path):
    reviewed = tmp_path / "coarse.csv"
    with reviewed.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROWS[0]))
        writer.writeheader()
        writer.writerows(ROWS)
    products = tmp_path / "products.json"
    resolution = tmp_path / "resolution.json"
    products.write_text(json.dumps({"meta": {"next_id": 1}, "products": {}}), encoding="utf-8")
    resolution.write_text(json.dumps({"meta": {"schema": 1}, "entries": []}), encoding="utf-8")
    return reviewed, products, resolution


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_one_product_serves_every_store_that_prints_a_name_for_it(catalog):
    reviewed, products, resolution = catalog
    summary = confirm(reviewed, products, resolution)

    entries = read(resolution)["entries"]
    cola = [e["product_id"] for e in entries if "Cola" in e["raw_name"]]
    assert len(cola) == 2 and cola[0] == cola[1], "two tills, two spellings, one product"
    assert summary["products"] == 3, "cola, keks, riegel — the other routes write nothing"


def test_an_unknown_variant_is_null_and_asked_about_never_guessed(catalog):
    reviewed, products, resolution = catalog
    confirm(reviewed, products, resolution)

    cola = next(p for p in read(products)["products"].values() if p["name"] == "Cola Classic")
    assert cola["variant"] is None
    assert cola["eans"] == [], "an invented barcode could never be told from a real one"
    assert "variant unknown" in cola["open_questions"], "the queue for asking later"


def test_a_confirmed_ean_is_kept_and_stops_the_variant_question(catalog):
    reviewed, products, resolution = catalog
    summary = confirm(reviewed, products, resolution)

    keks = next(p for p in read(products)["products"].values() if p["name"] == "Butterkeks")
    assert keks["eans"] == ["1234567890123"]
    assert "variant unknown" not in keks["open_questions"]
    assert summary["with_ean"] == 1


def test_a_flagged_guess_becomes_a_question_not_a_brand(catalog):
    reviewed, products, resolution = catalog
    confirm(reviewed, products, resolution)

    riegel = next(p for p in read(products)["products"].values() if p["name"] == "Schokoriegel")
    assert riegel["brand"] is None, "a trailing ? is doubt about the brand, not a brand"
    assert riegel["open_questions"] == ["brand uncertain: Vielleicht", "variant unknown"]


def test_routes_that_name_no_product_write_nothing(catalog):
    reviewed, products, resolution = catalog
    summary = confirm(reviewed, products, resolution)

    names = {e["raw_name"] for e in read(resolution)["entries"]}
    assert "Diverse Waren" not in names, "only the shopper can say"
    assert "Tragetasche" not in names, "a bag is not a grocery"
    assert summary["by_route"]["ask"] == 1 and summary["by_route"]["nonproduct"] == 1


def test_an_answer_already_given_is_never_overwritten(catalog):
    reviewed, products, resolution = catalog
    confirm(reviewed, products, resolution)
    again = confirm(reviewed, products, resolution)

    assert again["products"] == 0 and again["entries"] == 0
    assert again["skipped_known"] == 4
    assert len(read(resolution)["entries"]) == 4, "re-running writes no duplicates"
