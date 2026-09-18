"""The ALDI SÜD fetcher's pure parts, on made-up API documents shaped like the real ones."""

from __future__ import annotations

from grocery_app.catalog_aldi_sued import (
    leaf_categories,
    listing_url,
    parse_products,
    total_count,
)

TREE = {"data": [
    {"key": "100", "name": "Backwaren", "children": [
        {"key": "101", "name": "Brot", "children": []},
        {"key": "102", "name": "Müsli", "children": []},
    ]},
    {"key": "200", "name": "Angebote", "children": [
        # The same leaf can appear under a promotional parent too.
        {"key": "102", "name": "Müsli", "children": []},
    ]},
    {"key": "300", "name": "Getränke", "children": []},
]}

LISTING = {
    "meta": {"pagination": {"offset": 0, "limit": 30, "totalCount": 37}},
    "data": [
        {"sku": "000000000510935002", "name": "Premium Müsli 500 g, Honig Nuss",
         "brandName": "GOLDEN BRIDGE", "urlSlugText": "golden-bridge-premium-muesli",
         "sellingSize": "0,5 kg", "discontinued": False,
         "price": {"amount": 279, "amountRelevant": 279, "bottleDeposit": 0,
                   "comparisonDisplay": "5,58 €/1 kg"}},
        {"sku": "000000000000001234", "name": "Mineralwasser 1,5 l", "brandName": "",
         "urlSlugText": "mineralwasser", "sellingSize": "1,5 l", "discontinued": True,
         "price": {"amount": 19, "amountRelevant": 19, "bottleDeposit": 25,
                   "comparisonDisplay": "0,13 €/1 l"}},
        {"name": "no sku, skipped"},
    ],
}


def test_leaves_are_nodes_without_children_deduplicated_with_a_readable_path():
    assert leaf_categories(TREE) == {
        "101": "Backwaren / Brot",
        "102": "Backwaren / Müsli",
        "300": "Getränke",
    }


def test_products_carry_the_fields_the_resolver_ranks_on():
    muesli, water = parse_products(LISTING)
    assert muesli["article_number"] == "000000000510935002"
    assert muesli["name"] == "Premium Müsli 500 g, Honig Nuss"
    assert muesli["brand"] == "GOLDEN BRIDGE"
    assert muesli["pack_size"] == "0,5 kg"
    assert muesli["price"] == 2.79 and muesli["deposit"] is None
    assert muesli["url"].endswith("/produkt/golden-bridge-premium-muesli-000000000510935002")
    assert muesli["ean"] is None
    assert water["brand"] is None and water["deposit"] == 0.25 and water["discontinued"]


def test_pagination_reads_the_reported_total():
    assert total_count(LISTING) == 37
    assert total_count({"data": []}) is None


def test_listing_url_names_the_store_because_prices_are_per_branch():
    url = listing_url("102", 30, "BC08")
    assert "categoryKey=102" in url and "offset=30" in url and "servicePoint=BC08" in url
