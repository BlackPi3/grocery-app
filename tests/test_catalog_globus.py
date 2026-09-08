"""Tests for the GLOBUS catalog fetcher that need no network access.

The parser is pure, so it is exercised against a fixture trimmed from a real
listing page. That is the whole point of splitting fetch from parse: the parser
can be reworked and re-verified without touching their servers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from grocery_app.catalog_globus import (
    _article_number_from_href,
    category_url,
    parse_listing,
)

FIXTURE = Path(__file__).parent / "fixtures" / "globus_listing.html"


@pytest.fixture(scope="module")
def products():
    return parse_listing(FIXTURE.read_text(encoding="utf-8"))


def test_every_card_yields_the_fields_matching_needs(products):
    assert len(products) == 3
    for product in products:
        assert product["article_number"].isdigit()
        assert product["name"]
        assert product["brand"]
        assert isinstance(product["price"], float)


def test_fields_are_read_from_the_right_places(products):
    joghurt = next(p for p in products if p["article_number"] == "4104060000065")
    assert joghurt["name"] == "Bio Joghurt, Natur mild"
    assert joghurt["brand"] == "Andechser"
    # Price comes from the data-value attribute, not the localised "1,79 €" text.
    assert joghurt["price"] == 1.79
    assert joghurt["pack_size"] == "0,5 kg (3,58 € / 1 kg)"
    assert joghurt["deposit"] == "zzgl. Pfand 0.15 €"


def test_deposit_is_none_when_no_pfand_is_shown(products):
    pudding = next(p for p in products if p["article_number"] == "4012281322401")
    assert pudding["deposit"] is None
    assert pudding["pack_size"] == "0,04 kg (7,25 € / 1 kg)"


def test_article_number_is_taken_from_the_product_url():
    href = "https://produkte.globus.de/brot-backwaren-fruehstueck/meisterbaeckerei/brot-broetchen/2001609697033/saatenbroetchen-3er"
    assert _article_number_from_href(href) == "2001609697033"


def test_article_number_is_none_for_a_category_url():
    assert _article_number_from_href("https://produkte.globus.de/obst-gemuese/") is None


def test_short_in_house_numbers_are_kept_but_not_called_eans():
    """Bakery goods use a 6-digit house number. Dropping them would lose real
    products: 'Baguette mit Pfefferkruste' is one, and it is on a receipt."""
    href = "https://produkte.globus.de/brot-backwaren-fruehstueck/meisterbaeckerei/brot-broetchen/117747/baguette-mit-pfefferkruste"
    assert _article_number_from_href(href) == "117747"


def test_ean_is_set_only_when_the_number_is_barcode_shaped(products):
    joghurt = next(p for p in products if p["article_number"] == "4104060000065")
    assert joghurt["ean"] == "4104060000065"


def test_pagination_uses_p_because_limit_renders_no_cards():
    assert category_url("obst-gemuese/frisches-obst") == (
        "https://produkte.globus.de/obst-gemuese/frisches-obst/"
    )
    assert category_url("obst-gemuese/frisches-obst", 3) == (
        "https://produkte.globus.de/obst-gemuese/frisches-obst/?p=3"
    )
