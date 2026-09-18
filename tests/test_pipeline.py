"""The pipeline end to end on made-up data: receipts -> purchases.json -> insights.json.

The unit tests pin each stage; this one pins the seams between them and the
CLI that developers actually run, so a change to one stage that silently
breaks the next cannot merge. Every file here is invented (Musterladen).
"""

import json
import sys

import pytest

from grocery_app.cli import main
from grocery_app.insights import build_insights
from grocery_app.normalizer import build_purchases

RECEIPTS = [
    {
        "source_image": "IMG_1.jpeg", "transcribed_by": "hand", "store": "Musterladen",
        "date": "2026-01-05", "time": "10:00", "currency": "EUR", "printed_total": 3.09,
        "lines": [
            {"type": "product", "raw_name": "MU Milch 1,5%", "qty": 1,
             "gross": 1.09, "discount": 0.0, "net": 1.09, "tax_class": "A"},
            {"type": "product", "raw_name": "Bananen", "qty": 1, "sold_by_weight": True,
             "weight_kg": 1.0, "unit_price": 1.75, "unit_price_basis": "kg",
             "gross": 1.75, "discount": 0.0, "net": 1.75, "tax_class": "A"},
            {"type": "deposit", "raw_name": "Pfand", "qty": 1,
             "gross": 0.25, "discount": 0.0, "net": 0.25, "tax_class": "B"},
        ],
    },
    {
        "source_image": "IMG_2.jpeg", "transcribed_by": "hand", "store": "musterladen",
        "date": "2026-02-05", "time": "10:00", "currency": "EUR", "printed_total": 3.19,
        "lines": [
            {"type": "product", "raw_name": "MU Milch 1,5%", "qty": 1,
             "gross": 1.19, "discount": 0.0, "net": 1.19, "tax_class": "A"},
            {"type": "product", "raw_name": "Bananen", "qty": 1, "sold_by_weight": True,
             "weight_kg": 1.0, "unit_price": 1.75, "unit_price_basis": "kg",
             "gross": 1.75, "discount": 0.0, "net": 1.75, "tax_class": "A"},
            {"type": "product", "raw_name": "Geheimnis", "qty": 1,
             "gross": 0.25, "discount": 0.0, "net": 0.25, "tax_class": "A"},
        ],
    },
]

PRODUCTS = {
    "meta": {"next_id": 3},
    "products": {
        "p-0001": {"label": "mu-milch", "name": "Milch 1,5%", "brand": "Muster",
                   "product_line": None, "variant": None,
                   "size": {"count": 1, "value": 1.0, "unit": "l"}, "category": "Dairy",
                   "is_organic": False, "is_own_brand": True, "eans": [],
                   "open_questions": [], "provenance": {"attributes": "test", "source": "test"}},
        "p-0002": {"label": "bananen", "name": "Bananen", "brand": None,
                   "product_line": None, "variant": None, "size": None, "category": "Produce",
                   "is_organic": False, "is_own_brand": None, "eans": [],
                   "open_questions": [], "provenance": {"attributes": "test", "source": "test"}},
    },
}

RESOLUTION = {
    "meta": {"schema": 1},
    "entries": [
        {"store": "Musterladen", "raw_name": "MU Milch 1,5%", "line_type": "product",
         "product_id": "p-0001", "confirmed_by": "test", "confirmed_at": "2026-01-01",
         "source": "test"},
        {"store": "Musterladen", "raw_name": "Bananen", "line_type": "product",
         "product_id": "p-0002", "confirmed_by": "test", "confirmed_at": "2026-01-01",
         "source": "test"},
    ],
}


@pytest.fixture
def data(tmp_path):
    truth = tmp_path / "receipts" / "truth"
    truth.mkdir(parents=True)
    for r in RECEIPTS:
        (truth / r["source_image"].replace(".jpeg", ".json")).write_text(
            json.dumps(r), encoding="utf-8")
    # extract's sidecar must not be mistaken for a receipt
    (truth / "IMG_1.meta.json").write_text(json.dumps({"cost_usd": 0.01}), encoding="utf-8")
    products_dir = tmp_path / "products"
    products_dir.mkdir()
    (products_dir / "products.json").write_text(json.dumps(PRODUCTS), encoding="utf-8")
    (products_dir / "resolution.json").write_text(json.dumps(RESOLUTION), encoding="utf-8")
    return tmp_path


def test_receipts_become_purchases_become_insights(data):
    purchases = build_purchases(data / "receipts" / "truth",
                                data / "products" / "products.json",
                                data / "products" / "resolution.json",
                                None, data / "products")
    assert purchases["contract_version"] == 2
    assert purchases["meta"]["receipts"] == 2
    assert purchases["meta"]["product_lines"] == 5
    assert purchases["meta"]["unresolved_items"] == ["Geheimnis"]
    milk = [p for p in purchases["purchases"] if p["product_id"] == "p-0001"]
    assert [p["resolution"] for p in milk] == ["exact", "exact"], \
        "store spelled two ways still resolves"
    assert milk[0]["unit_price"] == {"amount": 1.09, "per": "l"}

    insights = build_insights(purchases)
    assert insights["contract_version"] == 1
    assert insights["as_of"] == "2026-02-05"
    assert insights["coverage"]["resolved_lines"] == 4
    (change,) = [c for c in insights["price_changes"] if c["product_id"] == "p-0001"]
    assert change["change_pct"] == 9.2
    assert [r["product_id"] for r in insights["repurchase"]] == ["p-0001", "p-0002"]
    assert insights["basket_index"]["series"][0]["index"] is None, \
        "two overlapping products is too thin for an index, and it says so"
    (label,) = insights["own_brand"]["by_store"]
    assert label.casefold() == "musterladen", "two spellings, one store"
    assert insights["own_brand"]["by_store"][label] == insights["own_brand"]["overall"]
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
                            "price_changes", "basket_index", "own_brand", "cross_store"}
