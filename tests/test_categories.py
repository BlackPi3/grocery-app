"""The category vocabulary: three levels, closed, and internally consistent.

The tables are hand-written and point at each other by key, so these tests are
mostly about the tables agreeing with themselves. The made-up tables exercise
each check; the shipped tables are asserted clean.
"""

from __future__ import annotations

import pytest

from grocery_app import categories

# Made-up tables, deliberately broken in one way each.
BRANCHES = {"kuehlregal": "Kühlregal", "verlassen": "Verlassen"}
SECTIONS = {
    "joghurt": ("Joghurt", "kuehlregal"),
    "kaputt": ("Kaputt", "gibtsnicht"),
    "leer": ("Leer", "kuehlregal"),
}
CATEGORIES = {
    "sahnejoghurt": ("Sahnejoghurt", "joghurt", ("sahnejoghurt", "rahmjoghurt")),
    "doppelt": ("Doppelt", "joghurt", ("griechisch", "griechisch")),
    "heimatlos": ("", "nirgendwo", ("rahmjoghurt",)),
}


def test_shipped_tables_are_consistent():
    assert categories.problems() == []


def test_shipped_tables_are_three_deep_and_non_trivial():
    assert categories.BRANCHES and categories.SECTIONS and categories.CATEGORIES
    # Every category reaches a branch without raising.
    for key in categories.CATEGORIES:
        branch, section, leaf = categories.path(key)
        assert branch and section and leaf


def test_a_section_pointing_at_no_branch_is_reported():
    found = categories.problems(BRANCHES, SECTIONS, CATEGORIES)
    assert "section kaputt: unknown branch gibtsnicht" in found


def test_a_category_pointing_at_no_section_is_reported():
    found = categories.problems(BRANCHES, SECTIONS, CATEGORIES)
    assert "category heimatlos: unknown section nirgendwo" in found


def test_a_category_without_a_label_is_reported():
    assert "category heimatlos: no label" in categories.problems(
        BRANCHES, SECTIONS, CATEGORIES)


def test_a_repeated_alias_within_one_category_is_reported():
    assert "category doppelt: duplicate aliases" in categories.problems(
        BRANCHES, SECTIONS, CATEGORIES)


def test_an_alias_claimed_by_two_categories_is_reported():
    # A proposal built on a shared alias is a coin toss, and a coin toss
    # written down is the failure the whole vocabulary exists to remove.
    found = categories.problems(BRANCHES, SECTIONS, CATEGORIES)
    assert "alias 'rahmjoghurt' claimed by heimatlos, sahnejoghurt" in found


def test_an_alias_repeated_inside_one_category_is_not_a_collision():
    # `doppelt` repeats `griechisch`, which is a typo in one category, not two
    # categories fighting over a word.
    found = categories.problems(BRANCHES, SECTIONS, CATEGORIES)
    assert not any(a.startswith("alias 'griechisch'") for a in found)


def test_an_empty_section_is_reported():
    assert "section leer: no categories" in categories.problems(
        BRANCHES, SECTIONS, CATEGORIES)


def test_an_empty_branch_is_reported():
    assert "branch verlassen: no sections" in categories.problems(
        BRANCHES, SECTIONS, CATEGORIES)


def test_path_reads_coarsest_first():
    assert categories.path("reibekaese") == (
        "Molkereiprodukte & Eier", "Käse", "Reibekäse")


@pytest.mark.parametrize("key", ["tomaten", "aepfel", "frische-kraeuter"])
def test_produce_sections_allow_a_null_brand(key):
    # A cucumber has no barcode, so no lookup, scan or shopper will ever supply
    # a brand: silence there is the final answer, not a gap.
    assert categories.is_produce(key)


@pytest.mark.parametrize("key", ["chips", "reibekaese", "kuechenrolle"])
def test_everything_else_does_not(key):
    assert not categories.is_produce(key)


def test_an_unknown_category_is_not_produce():
    # Absence must never be the thing that grants permission.
    assert not categories.is_produce("gibtsnicht")
    assert not categories.is_produce(None)


def test_obst_and_gemuese_are_separate_sections():
    # "Produce" cannot tell you how much fruit you bought, which is why it is
    # gone as a single value.
    assert categories.section_of("aepfel") == "obst"
    assert categories.section_of("tomaten") == "gemuese"
    assert categories.branch_of("aepfel") == categories.branch_of("tomaten")


def test_keys_are_ascii_so_a_second_language_is_a_second_label():
    for key in categories.CATEGORIES:
        assert key.isascii(), key
    for key in list(categories.SECTIONS) + list(categories.BRANCHES):
        assert key.isascii(), key
