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


def searching(pages, results):
    """A finder whose web search returns `results` (addresses in `pages`)."""
    searched = []

    def search(text):
        searched.append(text)
        return results

    def fetch_page(url):
        if url not in pages:
            raise OSError("unreachable")
        return pages[url]

    def find(product, listings):
        return find_picture(product, listings, fetch_page=fetch_page,
                            crawled=lambda store, article: None,
                            fetch_off=lambda ean: None, search=search)
    return find, searched


FOUND = {"name": "Magnesium Citrat Granulat", "brand": "Musterherz",
         "details": ["System"], "size": {"count": 1, "value": 20, "unit": "piece"},
         "provenance": {"attributes": "identify"}}


def test_a_product_found_on_the_web_gets_the_photo_of_a_page_that_describes_it():
    other = page({"@type": "Product", "name": "Musterherz Vitamin D",
                  "image": "https://laden.example/vitamin-d.jpg"})
    right = page({"@type": "Product", "name": "Magnesium Citrat System Granulat",
                  "brand": {"@type": "Brand", "name": "Musterherz"},
                  "image": "https://laden.example/magnesium.jpg"})
    find, searched = searching({"https://a.example": other, "https://b.example": right},
                               ["https://a.example", "https://b.example"])
    assert find(FOUND, []) == {"url": "https://laden.example/magnesium.jpg",
                               "from": "b.example", "page": "https://b.example"}
    assert searched == ["Musterherz Magnesium Citrat Granulat System"]


def test_no_search_for_a_kind_of_thing_or_a_product_a_shop_lists():
    find, searched = searching({}, [])
    assert find({"name": "Sandkuchen", "brand": None}, []) is None
    assert find(FOUND, [LADEN]) is None, "the shop's page failed; the shop is the source"
    english = {**FOUND, "name": "Plant-based drink", "provenance": {"attributes": "model-proposed"}}
    assert find(english, []) is None, "a name not read from a receipt is not searched"
    assert searched == []


def test_same_product_needs_the_brand_and_most_of_the_name():
    from grocery_app.pictures import same_product

    assert same_product(FOUND, {"brand": "Musterherz", "name": "Magnesium-Citrat 20 Stück"})
    assert not same_product(FOUND, {"brand": "Andere", "name": "Magnesium Citrat Granulat"})
    assert not same_product(FOUND, {"brand": "Musterherz", "name": "Vitamin D3 Tabletten"})
    assert same_product({"brand": "Dr. Muster", "name": "Puddingpulver"},
                        {"brand": None, "name": "Dr.Muster Puddingpulver Vanille"})


def test_a_search_that_could_not_be_made_is_not_one_that_found_nothing():
    """2026-10-12: three demo products were marked as having no picture after
    their searches timed out."""
    import pytest

    from grocery_app.pictures import LookupFailed

    def failing(text):
        raise OSError("Gemini did not answer: timed out")

    find = lambda search: find_picture(FOUND, [], fetch_page=lambda url: "",  # noqa: E731
                                       crawled=lambda store, article: None,
                                       fetch_off=lambda ean: None, search=search)
    with pytest.raises(LookupFailed, match="timed out"):
        find(failing)
    assert find(lambda text: []) is None, "a search that found nothing is an answer"


def test_a_spent_search_budget_fails_the_lookup_rather_than_finding_nothing():
    import pytest

    from grocery_app.api.pictures import limited
    from grocery_app.pictures import LookupFailed

    asked = []
    search = limited(lambda text: asked.append(text) or ["https://a.example"], 1)
    assert search("Muster Ding") == ["https://a.example"]
    with pytest.raises(LookupFailed, match="spent"):
        search("Muster Ding")
    assert asked == ["Muster Ding"], "no search once the budget is spent"


def test_a_picture_search_waits_longer_than_a_search_takes(monkeypatch):
    """With 60 s, 6 of the demo's 18 searches timed out (2026-10-12)."""
    from grocery_app import gemini
    from grocery_app.pictures import gemini_search

    waited = []

    def generate(model, body, api_key=None, timeout_s=180):
        waited.append(timeout_s)
        return {"candidates": [{}]}

    monkeypatch.setattr(gemini, "generate", generate)
    assert gemini_search("gemini-test")("Muster Ding") == []
    assert waited and waited[0] >= 120
