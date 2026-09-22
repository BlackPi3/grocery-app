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
    assert purchases["contract_version"] == 3
    assert purchases["meta"]["receipts"] == 2
    assert purchases["meta"]["product_lines"] == 5
    assert purchases["meta"]["unresolved_items"] == ["Geheimnis"]
    milk = [p for p in purchases["purchases"] if p["product_id"] == "p-0001"]
    assert [p["resolution"] for p in milk] == ["exact", "exact"], \
        "store spelled two ways still resolves"
    assert milk[0]["unit_price"] == {"amount": 1.09, "per": "l"}

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
