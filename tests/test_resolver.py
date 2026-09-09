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
