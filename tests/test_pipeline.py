"""The pipeline end to end on made-up data: receipts -> purchases.json -> insights.json.

The unit tests pin each stage; this one pins the seams between them and the
CLI that developers actually run, so a change to one stage that silently
breaks the next cannot merge. Every file here is invented (Musterladen).
"""

import json
import sys

from grocery_app.cli import main
from grocery_app.insights import build_insights
from grocery_app.normalizer import build_purchases


def test_receipts_become_purchases_become_insights(data):
    purchases = build_purchases(data / "receipts" / "truth",
                                data / "products" / "products.json",
                                data / "products" / "resolution.json",
                                None, data / "products")
    assert purchases["contract_version"] == 4
    assert purchases["meta"]["receipts"] == 2
    assert purchases["meta"]["product_lines"] == 5
    assert purchases["meta"]["unresolved_items"] == ["Geheimnis"]
    milk = [p for p in purchases["purchases"] if p["product_id"] == "p-0001"]
    assert [p["resolution"] for p in milk] == ["exact", "exact"], \
        "store spelled two ways still resolves"
    assert milk[0]["unit_price"] == {"amount": 1.09, "per": "l"}
    # The catalog stores the vocabulary key and nothing else; the three labels
    # a reader sees are derived here, once, on the way into the contract.
    assert milk[0]["category"] == "milch"
    assert milk[0]["category_path"] == ["Molkereiprodukte & Eier",
                                        "Milch & Joghurt", "Milch"]
    unresolved = next(p for p in purchases["purchases"] if not p["product_id"])
    assert "category_path" not in unresolved, \
        "a line with no product gains no attributes, this one included"

    insights = build_insights(purchases)
    assert insights["contract_version"] == 2
    assert insights["as_of"] == "2026-02-05"
    assert insights["coverage"]["resolved_lines"] == 4
    (change,) = [c for c in insights["price_changes"] if c["product_id"] == "p-0001"]
    assert change["change_pct"] == 9.2
    assert [r["product_id"] for r in insights["repurchase"]] == ["p-0001", "p-0002"]
    assert insights["basket_index"]["series"][0]["index"] is None, \
        "two overlapping products is too thin for an index, and it says so"
    (label,) = insights["budget_brand"]["by_store"]
    assert label.casefold() == "musterladen", "two spellings, one store"
    assert insights["budget_brand"]["by_store"][label] == insights["budget_brand"]["overall"]
    assert insights["cross_store"]["products"] == []


def test_the_cli_runs_the_same_path(data, monkeypatch, capsys):
    out_purchases = data / "purchases.json"
    out_insights = data / "insights.json"
    monkeypatch.setattr(sys, "argv", [
        "grocery-app", "purchases",
        "--receipts-dir", str(data / "receipts" / "truth"),
        "--products", str(data / "products" / "products.json"),
        "--resolution", str(data / "products" / "resolution.json"),
        "--line-resolutions", str(data / "absent.json"),
        "--products-dir", str(data / "products"),
        "--output", str(out_purchases),
    ])
    main()
    assert "UNRESOLVED:     ['Geheimnis']" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", [
        "grocery-app", "insights", "--purchases", str(out_purchases),
        "--output", str(out_insights),
    ])
    main()
    printed = capsys.readouterr().out
    assert "repurchase:     2 products bought more than once" in printed
    written = json.loads(out_insights.read_text(encoding="utf-8"))
    assert set(written) == {"contract_version", "as_of", "coverage", "repurchase",
                            "price_changes", "basket_index", "budget_brand", "cross_store"}


def test_the_server_serves_what_the_normalizer_built(data):
    """The seam between the pipeline and the HTTP layer.

    The schema is strict, so a field added to `normalize_line` without a
    matching line in `api/schemas.py` fails here, not on a client.
    """
    from fastapi.testclient import TestClient

    from grocery_app.api.app import create_app
    from grocery_app.api.repository import InMemoryRepository
    from grocery_app.api.schemas import PurchasesDocument

    purchases = build_purchases(data / "receipts" / "truth",
                                data / "products" / "products.json",
                                data / "products" / "resolution.json",
                                None, data / "products")
    PurchasesDocument.model_validate(purchases)

    client = TestClient(create_app(InMemoryRepository(purchases)))
    # The whole document, not a summary of it: comparing only `meta` and the
    # names let the server add null attributes to unresolved lines unnoticed.
    assert client.get("/v1/purchases").json() == purchases
    assert client.get("/v1/insights").json() == build_insights(purchases)


def test_budget_brand_is_derived_at_the_seam_and_not_stored_in_the_catalog(data):
    """The catalog holds no own-brand answer; purchases.json holds one per line.

    This is the seam the change is about. Products are permanent and shared
    across shops, so a value frozen onto one could only ever be right in the
    shop it was minted in. Deriving it as purchases are built means a correction
    to the brand tables reaches every line ever written, with no migration.
    """
    catalog = json.loads((data / "products" / "products.json").read_text())["products"]
    assert catalog, "fixture has products"
    for product_id, product in catalog.items():
        assert "is_budget_brand" not in product, \
            f"{product_id}: the catalog must not freeze a per-shop fact onto a product"

    purchases = build_purchases(data / "receipts" / "truth",
                                data / "products" / "products.json",
                                data / "products" / "resolution.json",
                                None, data / "products")
    resolved = [p for p in purchases["purchases"] if p.get("product_id")]
    assert resolved, "fixture resolves something"
    assert all("is_budget_brand" in p for p in resolved), \
        "every resolved line answers the question the catalog no longer stores"
    # A line nothing could place invents nothing, this field included.
    for line in purchases["purchases"]:
        if line["type"] == "product" and not line.get("product_id"):
            assert "is_budget_brand" not in line


def test_the_matching_score_reads_what_the_normalizer_reads_but_not_the_answers(data):
    """The score runs the normalizer on the same files, minus the shopper's answers.

    `Geheimnis` on IMG_2 has an answer in `line_resolutions.json`, so
    purchases.json places it. The score must not: a line the shopper answered
    is exactly the line the matcher is being tested on.
    """
    from grocery_app.evaluate_matching import article_index, evaluate_matching, load_readings
    from grocery_app.normalizer import load_products, load_resolution

    products = load_products(data / "products" / "products.json")
    key = {"meta": {}, "lines": [
        {"source_image": "IMG_2.jpeg", "position": 0, "store": "musterladen",
         "raw_name": "MU Milch 1,5%", "product": "Muster Milch", "article": "4000000000001",
         "catalog_ids": [], "known": "exact"},
        {"source_image": "IMG_2.jpeg", "position": 2, "store": "musterladen",
         "raw_name": "Geheimnis", "product": "Muster Milch", "article": None,
         "catalog_ids": ["p-0001"], "known": "exact"},
    ]}
    report = evaluate_matching(
        key, load_readings(data / "receipts" / "truth", {"IMG_2.jpeg"}),
        load_resolution(data / "products" / "resolution.json"), products,
        index=article_index(products, data / "products"))
    assert [line["outcome"] for line in report["lines"]] == ["right", "missed"], \
        "the listing links the shop's number to p-0001; the answer file is not read"
