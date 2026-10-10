"""Where a product's picture comes from, on made-up pages; no network."""

from __future__ import annotations

import json

from grocery_app.pictures import PICTURE_FROM_OFF, find_picture, picture_on_page


def page(*blocks):
    scripts = "".join(f'<script type="application/ld+json">{json.dumps(b)}</script>'
                      for b in blocks)
    return f"<html><head>{scripts}</head><body></body></html>"


SHOP_LOGO = {"@type": "Organization", "image": "https://laden.example/logo.jpg"}
PRODUCT = {"@type": "Product", "name": "Muster Ding",
           "image": ["https://laden.example/media/muster-ding.jpg"]}


def test_the_photo_is_the_products_not_the_shops_logo():
    assert picture_on_page(page(SHOP_LOGO, PRODUCT)) == "https://laden.example/media/muster-ding.jpg"
    assert picture_on_page(page({"@graph": [SHOP_LOGO, {**PRODUCT, "image": {
        "url": "https://laden.example/a.jpg"}}]})) == "https://laden.example/a.jpg"
    assert picture_on_page(page(SHOP_LOGO)) is None
    assert picture_on_page("<script type=\"application/ld+json\">{broken</script>") is None


def finder(pages=None, crawl=None, off=None):
    pages, crawl, off = pages or {}, crawl or {}, off or {}

    def fetch_page(url):
        if url not in pages:
            raise OSError("unreachable")
        return pages[url]

    return lambda product, listings: find_picture(
        product, listings, fetch_page=fetch_page,
        crawled=lambda store, article: crawl.get((store, article)),
        fetch_off=lambda ean: off.get(ean))


LADEN = {"store": "Musterladen", "article_number": "1", "url": "https://laden.example/p/1"}
DISCOUNTER = {"store": "ALDI SÜD", "article_number": "9",
              "url": "https://www.aldi-sued.de/produkt/ding-9"}


def test_the_shop_comes_first_then_open_food_facts():
    find = finder(pages={LADEN["url"]: page(PRODUCT)},
                  off={"4000000000001": "https://off.example/front.jpg"})
    product = {"eans": ["4000000000001"]}
    assert find(product, [LADEN]) == {"url": "https://laden.example/media/muster-ding.jpg",
                                      "from": "Musterladen", "page": LADEN["url"]}
    assert find(product, []) == {"url": "https://off.example/front.jpg",
                                 "from": PICTURE_FROM_OFF,
                                 "page": "https://world.openfoodfacts.org/product/4000000000001"}


def test_aldis_photo_comes_from_its_crawl_and_its_page_is_never_asked():
    find = finder(crawl={("ALDI SÜD", "9"): {"image_url": "https://aldi.example/front"}})
    assert find({}, [DISCOUNTER])["url"] == "https://aldi.example/front"
    assert finder()({}, [DISCOUNTER]) is None


def test_a_source_that_fails_is_passed_over_and_a_kind_of_thing_gets_none():
    find = finder(off={"4000000000001": "https://off.example/front.jpg"})
    assert find({"eans": ["4000000000001"]}, [LADEN])["from"] == PICTURE_FROM_OFF
    assert find({"name": "Sandkuchen", "eans": []}, []) is None
