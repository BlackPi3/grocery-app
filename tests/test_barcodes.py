"""Barcodes from Open Food Facts by name: exact matches only, on made-up hits
shaped like the search's."""

from __future__ import annotations

from grocery_app.barcodes import find, find_all, judge, query

DE = ["en:germany"]
WAFFLES = {"name": "Waffeln Kakao", "brand": "Musterback", "details": [],
           "size": {"count": 1, "value": 250, "unit": "g"}, "eans": []}


def hit(code="4000000000017", name="Waffeln Kakao", brands=("musterback",),
        quantity="250 g", countries=DE):
    return {"code": code, "product_name_de": name, "brands_tags": list(brands),
            "quantity": quantity, "countries_tags": countries}


def test_brand_name_size_and_country_all_matching_is_exact():
    assert judge(WAFFLES, hit()) == "exact"
    assert judge(WAFFLES, hit(name="Kakao Waffeln", quantity="0,25 kg")) == "exact"


def test_a_word_in_their_name_that_ours_lacks_is_another_product():
    """Our `Goldbären` is not their `Saure Goldbären`: a flavour we never said."""
    assert judge(WAFFLES, hit(name="Waffeln Kakao Vanille")) == "other product"
    assert judge(WAFFLES, hit(brands=["anderback"])) == "other product"


def test_an_unknown_or_different_size_is_a_near_miss_and_says_why():
    family = {**WAFFLES, "size": {"count": 1, "value": None, "unit": None}}
    assert judge(family, hit()) == "our size unknown"
    assert judge(WAFFLES, hit(quantity="500 g")) == "size 500 g"
    assert judge(WAFFLES, hit(quantity="2 x 250 g")) == "a multipack"
    assert judge(WAFFLES, hit(countries=["en:norway"])) == "not sold in Germany"


def test_only_one_exact_barcode_is_found_and_a_near_miss_is_never_found():
    found = find(WAFFLES, [hit(code="1", name="Waffeln Vanille"), hit(code="2")], {})
    assert (found["outcome"], found["ean"]) == ("found", "2")

    near = find(WAFFLES, [hit(code="3", quantity="500 g")], {})
    assert (near["outcome"], near["ean"], near["why"]) == ("near", "3", "size 500 g")

    assert find(WAFFLES, [hit(code="4"), hit(code="5")], {}) == {
        "outcome": "several", "eans": ["4", "5"]}
    assert find(WAFFLES, [hit(name="Kekse")], {}) == {"outcome": "none"}


def test_a_barcode_another_product_has_is_a_double_not_a_second_owner():
    products = {"p-0001": {**WAFFLES, "eans": ["9"]}, "p-0002": WAFFLES,
                "p-0003": {**WAFFLES}}
    rows = {r["product_id"]: r for r in find_all(products, lambda q: [hit(code="9")])}
    assert set(rows) == {"p-0002", "p-0003"}, "a product with a barcode is not searched"
    assert (rows["p-0002"]["outcome"], rows["p-0002"]["other"]) == ("taken", "p-0001")

    rows = find_all({"p-0002": WAFFLES, "p-0003": {**WAFFLES}}, lambda q: [hit(code="8")])
    assert [r["outcome"] for r in rows] == ["found", "taken"]


def test_loose_produce_is_not_searched_and_the_query_carries_no_syntax():
    asked = []
    find_all({"p-0001": {"name": "Bananen", "brand": None, "eans": []}},
             lambda q: asked.append(q) or [])
    assert asked == []
    said = query({"name": "Bitter-Getränk (Lemon)", "brand": "Dr. Muster", "details": []})
    assert said == 'Bitter Getränk Lemon brands:"dr-muster" countries_tags:"en:germany"'


def test_only_a_found_barcode_is_written_with_where_it_came_from(session):
    from grocery_app.api.matching import find_barcodes
    from grocery_app.db.models import Product

    session.add_all([
        Product(id="p-0001", name="Waffeln Kakao", brand="Musterback",
                size={"count": 1, "value": 250, "unit": "g"}, provenance={"source": "x"}),
        Product(id="p-0002", name="Waffeln Kakao", brand="Musterback",
                size={"count": 1, "value": None, "unit": None}),
    ])
    session.flush()
    report = find_barcodes(session, lambda q: [hit(code="4000000000017")])
    assert [r["outcome"] for r in report] == ["found", "near"]
    exact, family = session.get(Product, "p-0001"), session.get(Product, "p-0002")
    assert exact.eans == ["4000000000017"]
    assert exact.provenance["source"] == "x", "what was there is kept"
    assert exact.provenance["barcode_from"]["source"] == "Open Food Facts search"
    assert family.eans == [] and "barcode_from" not in (family.provenance or {})
