"""Tests for the proposal ranker. No network, no catalog file needed."""

from __future__ import annotations

from grocery_app.resolver import (
    expand_abbreviations,
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


def test_accepted_rows_naming_different_products_are_held_back():
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


def test_a_name_held_back_for_disambiguation_is_not_a_no_match():
    """It carries a `y`. Recording it as 'no match in catalog' would bury a real
    decision and stop the name ever being asked about again."""
    from grocery_app.resolver import accepted_rows, ambiguous_names, marked_names

    rows = [{"decision": "y", "raw_name": "dove", "catalog_name": "Dusche A", "pack_size": ""},
            {"decision": "y", "raw_name": "dove", "catalog_name": "Dusche B", "pack_size": ""},
            {"decision": "n", "raw_name": "dove", "catalog_name": "Dusche C", "pack_size": ""}]
    assert "dove" in ambiguous_names(rows)
    assert "dove" in marked_names(rows, "n")
    # The guard is that it also has a y, so it must never be written as no-match.
    assert "dove" in accepted_rows(rows)
