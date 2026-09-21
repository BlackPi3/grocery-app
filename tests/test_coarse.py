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
    # a packaged good whose brand nobody read
    {"store": "Musterladen", "raw_name": "Knusperzeug Salz", "route": "search",
     "brand": "", "product": "Kartoffelchips gesalzen", "ean": "",
     "options": "", "your_note": ""},
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
    assert summary["products"] == 4, "cola, keks, riegel, chips — other routes write nothing"


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
    assert again["skipped_known"] == 5
    assert len(read(resolution)["entries"]) == 5, "re-running writes no duplicates"


# --- propose -----------------------------------------------------------------

from grocery_app.coarse import brand_in, expand, propose, without  # noqa: E402

PURCHASES = {
    "purchases": [
        {"type": "product", "store": "Musterladen", "raw_name": "Musterbrause 1,25l",
         "resolved": False, "net_paid": 0.99},
        {"type": "product", "store": "Woanders", "raw_name": "KBio Joghurt gr Art 1kg",
         "resolved": False, "net_paid": 2.19},
        {"type": "product", "store": "Musterladen", "raw_name": "Rein WSP Basis 71",
         "resolved": False, "net_paid": 3.79},
        {"type": "product", "store": "Musterladen", "raw_name": "Schon da",
         "resolved": True, "net_paid": 1.00},
    ],
}
CATALOG = {"products": {"p-0001": {"name": "Cola", "brand": "Muster-Brause"},
                        "p-0002": {"name": "Weichspüler", "brand": "Rein"}}}


def rows_by_name(previous=None):
    return {r["raw_name"]: r for r in propose(PURCHASES, CATALOG, previous)}


def test_a_brand_printed_on_the_line_is_read_not_guessed():
    rows = rows_by_name()
    assert rows["Rein WSP Basis 71"]["brand"] == "Rein"
    assert rows["Rein WSP Basis 71"]["product"] == "Weichspüler Basis", \
        "the brand is not repeated inside its own product name"


def test_punctuation_does_not_hide_a_brand():
    # The till prints "Musterbrause"; the catalog holds "Muster-Brause".
    assert rows_by_name()["Musterbrause 1,25l"]["brand"] == "Muster-Brause"


def test_an_own_brand_prefix_becomes_the_brand_and_leaves_the_name():
    brand, name = expand("KBio Joghurt gr Art 1kg")
    assert brand == "K-Bio"
    assert name == "Joghurt griechischer Art", "multi-word abbreviation, quantity dropped"


def test_expansion_keeps_the_case_the_till_printed():
    _, name = expand("HP Skyr Drink 330")
    assert name == "High Protein Skyr Drink", "not 'high protein skyr drink'"


def test_an_unknown_token_is_kept_exactly_as_printed():
    _, name = expand("Knurpsel Spezial 500g")
    assert name == "Knurpsel Spezial", "nothing is invented for a word we do not know"


def test_the_longest_matching_brand_wins():
    # A line carrying both must not resolve to the shorter one.
    assert brand_in("BIO BIO Heumilch 1L", ["BIO", "BIO BIO"]) == "BIO BIO"
    assert brand_in("BB Heumil 1L", ["BIO", "BIO BIO"]) == "", \
        "BB is an own-brand prefix, handled by expand, not a brand printed on the line"


def test_without_leaves_the_name_alone_when_it_is_only_the_brand():
    assert without("Rein", "Rein") == "Rein", "an empty product name helps nobody"


def test_a_resolved_line_is_never_proposed():
    assert "Schon da" not in rows_by_name()


def test_an_ean_is_never_proposed():
    assert all(r["ean"] == "" for r in propose(PURCHASES, CATALOG)), \
        "a barcode is the fine-grained identity; it arrives by scan, not by guess"


def test_a_naming_a_reviewer_edited_survives_while_the_proposal_does():
    before = [dict(r, product="Weichspüler Aprilfrisch", your_note="checked the box")
              for r in propose(PURCHASES, CATALOG)]
    kept = rows_by_name(before)["Rein WSP Basis 71"]
    assert kept["product"] == "Weichspüler Basis", \
        "the edit was made against a proposal this row no longer carries"
    assert kept["your_note"] == "", "and the note that went with it goes too"


def test_what_kind_of_line_it_is_survives_a_changed_proposal():
    before = [dict(r, route="nonproduct") for r in propose(PURCHASES, CATALOG)]
    moved = [dict(r, product="Something else", brand="Someone else") for r in before]
    assert rows_by_name(moved)["Rein WSP Basis 71"]["route"] == "nonproduct", \
        "a bag is a bag however the name was expanded"
    assert rows_by_name(moved)["Rein WSP Basis 71"]["product"] == "Weichspüler Basis", \
        "the naming itself does not survive: that is what the reviewer agreed to"


def test_a_packaged_good_with_no_brand_says_the_brand_is_unknown(catalog):
    reviewed, products, resolution = catalog
    confirm(reviewed, products, resolution)

    chips = next(p for p in read(products)["products"].values()
                 if p["name"] == "Kartoffelchips gesalzen")
    assert chips["brand"] is None
    assert "brand unknown" in chips["open_questions"], \
        "a box has a brand printed on it; a null means nobody read it, not that none exists"


def test_a_flagged_guess_is_not_also_reported_as_simply_unknown(catalog):
    reviewed, products, resolution = catalog
    confirm(reviewed, products, resolution)

    riegel = next(p for p in read(products)["products"].values() if p["name"] == "Schokoriegel")
    assert riegel["open_questions"] == ["brand uncertain: Vielleicht", "variant unknown"], \
        "naming the guess says more than `brand unknown`, so it should not say both"
