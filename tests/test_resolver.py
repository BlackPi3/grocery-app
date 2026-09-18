"""Tests for the proposal ranker. No network, no catalog file needed."""

from __future__ import annotations

from grocery_app.resolver import (
    expand_abbreviations,
    own_brand_status,
    parse_size,
    rank,
    score,
    tokens,
)

CATALOG = [
    {"article_number": "1", "name": "Cheddar, gerieben", "brand": "Jeden Tag",
     "pack_size": "0,2 kg", "price": 2.19},
    {"article_number": "2", "name": "Pinienkerne", "brand": "Jeden Tag",
     "pack_size": "0,1 kg", "price": 1.89},
    {"article_number": "3", "name": "Baguette mit Pfefferkruste",
     "brand": "GLOBUS Meisterbäckerei", "pack_size": None, "price": 1.59},
    {"article_number": "4", "name": "Erdbeeren", "brand": None,
     "pack_size": "0,5 kg", "price": 1.11},
]


def test_umlauts_fold_so_a_till_placeholder_still_matches():
    # Tills print '?' where they cannot render an umlaut, and slugs spell it out.
    assert tokens("Saatenbrötchen") == tokens("Saatenbroetchen")


def test_brand_abbreviations_expand():
    assert "jeden tag" in expand_abbreviations("JT Milch 1,5% ESL").lower()


def test_sizes_normalise_to_a_common_unit():
    assert parse_size("Kerrygold 250g") == (250.0, "g")
    assert parse_size("0,5 kg (3,58 € / 1 kg)") == (500.0, "g")
    assert parse_size("Alpro 1L") == (1000.0, "ml")
    assert parse_size("no size here") is None


def test_name_and_brand_together_outrank_brand_alone():
    ranked = rank("JT Cheddar gerieben", 2.19, CATALOG)
    assert ranked[0]["product"]["article_number"] == "1"


def test_price_alone_never_produces_a_candidate():
    """The failure that motivated this ranker: 'Chips Salt & Vinegar' matched
    'Erdbeeren' because both cost 1.11."""
    assert rank("Chips Salt & Vinegar", 1.11, CATALOG) == []


def test_a_size_disagreement_counts_against_a_candidate():
    with_match, _ = score("Cheddar gerieben 200g", None, CATALOG[0])
    with_clash, evidence = score("Cheddar gerieben 500g", None, CATALOG[0])
    assert with_clash < with_match
    assert "size-mismatch" in evidence


def test_price_is_only_a_hint_and_cannot_carry_a_match():
    _, evidence = score("Baguette Pfefferkr.", 1.59, CATALOG[2])
    assert any(e.startswith("name:") for e in evidence)
    # Price contributes, but the match stands on the name.
    without_price, _ = score("Baguette Pfefferkr.", None, CATALOG[2])
    assert without_price > 0


def test_umlaut_placeholders_are_filled_in():
    """Tills print '?' where they cannot render an umlaut. Search cannot match
    'SAATENBR?TCHEN', but finds 'Saatenbrötchen' immediately."""
    from grocery_app.resolver import umlaut_variants

    variants = umlaut_variants("SAATENBR?TCHEN 3+1")
    assert "SAATENBRÖTCHEN 3+1" in variants
    assert all("?" not in v for v in variants)


def test_names_without_a_placeholder_need_no_variants():
    from grocery_app.resolver import umlaut_variants

    assert umlaut_variants("Kerrygold Butter") == []


def test_variant_count_stays_bounded():
    from grocery_app.resolver import MAX_UMLAUT_VARIANTS, umlaut_variants

    assert len(umlaut_variants("J?ch?nt?ch?r")) <= MAX_UMLAUT_VARIANTS


def test_store_names_compare_case_insensitively():
    """One receipt prints GLOBUS and another Globus; they are one chain."""
    from grocery_app.resolver import store_key

    assert store_key("GLOBUS") == store_key("Globus") == "globus"


def test_brand_expansion_is_offered_as_a_separate_query():
    from grocery_app.resolver import queries_for

    queries = queries_for("JT Magerquark 250g")
    assert queries[0] == "JT Magerquark 250g"
    assert any("jeden tag" in q.lower() for q in queries)


def test_multi_quantity_lines_compare_per_item(tmp_path):
    """`gross` is the line total: two quark pots at 0.69 print as 1.38, and
    comparing that against a shelf price is meaningless."""
    import json

    from grocery_app.resolver import unresolved_lines

    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "r.json").write_text(json.dumps({
        "store": "Globus",
        "lines": [{"type": "product", "raw_name": "JT Magerquark 250g",
                   "qty": 2, "gross": 1.38}],
    }), encoding="utf-8")
    resolution = tmp_path / "resolution.json"
    resolution.write_text(json.dumps({"entries": []}), encoding="utf-8")

    assert unresolved_lines(receipts, resolution, "Globus") == {"JT Magerquark 250g": 0.69}


def test_blank_and_no_are_different_answers():
    """Blank means 'not looked at yet'; 'n' means 'I checked and none fits'.
    Collapsing them loses the signal that a different source is needed."""
    from grocery_app.resolver import decision_of

    assert decision_of({"decision": "y"}) == "y"
    assert decision_of({"decision": "N"}) == "n"
    assert decision_of({"decision": "?"}) == "?"
    assert decision_of({"decision": ""}) is None
    assert decision_of({"decision": "   "}) is None


def test_unrecognised_marks_are_ignored_rather_than_guessed():
    from grocery_app.resolver import decision_of

    assert decision_of({"decision": "maybe later"}) is None


def test_unrecognised_decisions_are_reported_not_dropped():
    """A reviewer's note in the decision cell must never be read as blank.
    Silently dropping them cost a whole review pass."""
    from grocery_app.resolver import unclear_rows

    rows = [{"decision": "y", "raw_name": "a"},
            {"decision": "", "raw_name": "b"},
            {"decision": "couldn't find it", "raw_name": "c"}]
    assert [r["raw_name"] for r in unclear_rows(rows)] == ["c"]


def test_accepted_rows_naming_different_products_form_a_family():
    """Three listings of the same eggs merge into one product; 'Dusche Sweet
    Treat' and 'Dusche Fruchtig Leicht' are different products and must not."""
    from grocery_app.resolver import ambiguous_names

    same = [{"decision": "y", "raw_name": "eggs", "catalog_name": "Bio Eier", "pack_size": "10"},
            {"decision": "y", "raw_name": "eggs", "catalog_name": "Bio Eier", "pack_size": "10"}]
    assert ambiguous_names(same) == {}

    different = [{"decision": "y", "raw_name": "dove", "catalog_name": "Dusche A", "pack_size": ""},
                 {"decision": "y", "raw_name": "dove", "catalog_name": "Dusche B", "pack_size": ""}]
    assert "dove" in ambiguous_names(different)


def test_same_product_in_two_sizes_is_ambiguous():
    """`Bio Chia Samen` at 0,5 kg and 0,2 kg are two products, and the receipt
    prints the same text for both."""
    from grocery_app.resolver import ambiguous_names

    rows = [{"decision": "y", "raw_name": "chia", "catalog_name": "Bio Chia Samen",
             "pack_size": "0,5 kg"},
            {"decision": "y", "raw_name": "chia", "catalog_name": "Bio Chia Samen",
             "pack_size": "0,2 kg"}]
    assert "chia" in ambiguous_names(rows)


def test_a_family_is_not_a_no_match():
    """It carries `y`s. Recording it as 'no match in catalog' would bury a real
    decision and stop the name ever being asked about again."""
    from grocery_app.resolver import accepted_rows, ambiguous_names, marked_names

    rows = [{"decision": "y", "raw_name": "dove", "catalog_name": "Dusche A", "pack_size": ""},
            {"decision": "y", "raw_name": "dove", "catalog_name": "Dusche B", "pack_size": ""},
            {"decision": "n", "raw_name": "dove", "catalog_name": "Dusche C", "pack_size": ""}]
    assert "dove" in ambiguous_names(rows)
    assert "dove" in marked_names(rows, "n")
    # The guard is that it also has a y, so it must never be written as no-match.
    assert "dove" in accepted_rows(rows)


def test_confirm_writes_a_family_as_several_products_under_one_name(tmp_path):
    """Two `y`s on different products do not merge and are not held back: each
    earns its own id, and the name resolves to both."""
    import json

    from grocery_app.resolver import confirm

    reviewed = tmp_path / "reviewed.csv"
    reviewed.write_text(
        "decision,raw_name,receipt_price,rank,score,evidence,"
        "catalog_name,brand,pack_size,catalog_price,article_number,url\n"
        "y,Dove Dusche,2.49,1,7.0,search#1,Dusche A,Dove,\"0,25 l\",2.29,8720181848834,https://x/a\n"
        "y,Dove Dusche,2.49,2,6.7,search#2,Dusche B,Dove,\"0,25 l\",2.29,8720181923883,https://x/b\n"
        "y,Eier,2.99,1,7.0,search#1,Bio Eier,Alnatura,10 Stk,2.99,4104420000001,https://x/e\n"
        "y,Eier,2.99,2,6.9,search#2,Bio Eier,Alnatura,10 Stk,2.99,4104420000002,https://x/e2\n",
        encoding="utf-8")
    products = tmp_path / "products.json"
    products.write_text(json.dumps({"meta": {"next_id": 1}, "products": {}}), encoding="utf-8")
    resolution = tmp_path / "resolution.json"
    resolution.write_text(json.dumps({"entries": []}), encoding="utf-8")
    listings = tmp_path / "listings.json"
    listings.write_text(json.dumps({"listings": {}}), encoding="utf-8")

    summary = confirm(reviewed, products, resolution, listings, "GLOBUS", "2026-01-01")

    assert summary["families"] == {"Dove Dusche": 2}
    assert summary["products"] == 3 and summary["entries"] == 2
    entries = {e["raw_name"]: e for e in json.loads(resolution.read_text())["entries"]}
    dove, eggs = entries["Dove Dusche"], entries["Eier"]
    assert dove["product_id"] is None and dove["status"] == "ambiguous_on_receipt"
    assert len(dove["product_ids"]) == 2
    assert eggs["product_id"] and "product_ids" not in eggs
    stored = json.loads(products.read_text())["products"]
    assert {stored[i]["name"] for i in dove["product_ids"]} == {"Dusche A", "Dusche B"}
    assert stored[eggs["product_id"]]["eans"] == ["4104420000001", "4104420000002"]
    written = json.loads(listings.read_text())["listings"]
    articles = ("8720181848834", "8720181923883")
    assert {written[a]["product_id"] for a in articles} == set(dove["product_ids"])


def test_confirm_fills_a_missing_shelf_price_from_the_product_page(tmp_path):
    """The search page showed no price for the 0,2 kg seeds; without one, the
    paid amount could never tell the two packs apart."""
    import json

    from grocery_app.resolver import confirm

    reviewed = tmp_path / "reviewed.csv"
    reviewed.write_text(
        "decision,raw_name,receipt_price,rank,score,evidence,"
        "catalog_name,brand,pack_size,catalog_price,article_number,url\n"
        "y,Chia,3.99,1,5.5,search#1,Bio Chia Samen,Alnatura,\"0,5 kg\",3.99,4104420249967,https://x/big\n"
        "y,Chia,3.99,2,4.7,search#2,Bio Chia Samen,Alnatura,\"0,2 kg\",,4104420244092,https://x/small\n",
        encoding="utf-8")
    for name, doc in (("products.json", {"meta": {"next_id": 1}, "products": {}}),
                      ("resolution.json", {"entries": []}), ("listings.json", {"listings": {}})):
        (tmp_path / name).write_text(json.dumps(doc), encoding="utf-8")

    asked = []
    def lookup(url):
        asked.append(url)
        return 2.49

    confirm(reviewed, tmp_path / "products.json", tmp_path / "resolution.json",
            tmp_path / "listings.json", "GLOBUS", "2026-01-01", price_lookup=lookup)

    assert asked == ["https://x/small"]
    listings = json.loads((tmp_path / "listings.json").read_text())["listings"]
    assert listings["4104420244092"]["prices"] == [{"date": "2026-01-01", "price": 2.49}]
    assert listings["4104420249967"]["prices"] == [{"date": "2026-01-01", "price": 3.99}]


def test_one_article_in_two_families_is_one_product(tmp_path):
    """The same Bridgerton bottle was accepted under `Dove Dusche` and under
    `Dove Dusche 225ml`. It must not be minted twice."""
    import json

    from grocery_app.resolver import confirm

    reviewed = tmp_path / "reviewed.csv"
    reviewed.write_text(
        "decision,raw_name,receipt_price,rank,score,evidence,"
        "catalog_name,brand,pack_size,catalog_price,article_number,url\n"
        "y,Dove Dusche,2.49,1,7.0,search#1,Dusche A,Dove,\"0,25 l\",2.29,8720181848834,https://x/a\n"
        "y,Dove Dusche,2.49,2,5.2,search#7,Bridgerton,Dove,\"0,23 l\",2.79,8720181871375,https://x/b\n"
        "y,Dove Dusche 225ml,2.49,1,5.0,search#2,Bridgerton,Dove,\"0,23 l\",2.79,8720181871375,https://x/b\n"
        "y,Dove Dusche 225ml,2.49,2,4.7,search#3,Pflege Oel,Dove,\"0,23 l\",,8720181460029,https://x/c\n",
        encoding="utf-8")
    for name, doc in (("products.json", {"meta": {"next_id": 1}, "products": {}}),
                      ("resolution.json", {"entries": []}), ("listings.json", {"listings": {}})):
        (tmp_path / name).write_text(json.dumps(doc), encoding="utf-8")

    summary = confirm(reviewed, tmp_path / "products.json", tmp_path / "resolution.json",
                      tmp_path / "listings.json", "GLOBUS", "2026-01-01")

    products = json.loads((tmp_path / "products.json").read_text())["products"]
    assert len(products) == 3 and summary["products"] == 3
    entries = {e["raw_name"]: e["product_ids"]
               for e in json.loads((tmp_path / "resolution.json").read_text())["entries"]}
    shared = set(entries["Dove Dusche"]) & set(entries["Dove Dusche 225ml"])
    assert len(shared) == 1 and products[shared.pop()]["name"] == "Bridgerton"


def test_generic_tokens_do_not_carry_a_match():
    """`Bananen Bio` must not match a bio apple juice on the word `bio` alone,
    and `300g` is a size, scored by parse_size, not a name."""
    assert tokens("Bananen Bio 300g lose") == {"bananen"}
    juice = {"article_number": "9", "name": "Bio-Apfelschorle 330 ml", "brand": "BIO",
             "pack_size": "0,33 l", "price": 0.75}
    assert rank("Bananen Bio", 0.97, [juice]) == []


def test_own_brand_is_decided_per_store_from_the_brand():
    assert own_brand_status("GLOBUS", "Jeden Tag") is True
    assert own_brand_status("Globus", "GLOBUS Meisterbäckerei") is True, "a store line counts"
    assert own_brand_status("GLOBUS", "OHO") is True
    assert own_brand_status("GLOBUS", "Manner") is False
    assert own_brand_status("GLOBUS", None) is None, "no brand, no answer"
    assert own_brand_status("Musterladen", "Jeden Tag") is None, "no list for this store yet"
