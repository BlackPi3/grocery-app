"""The HTTP layer over made-up data.

The routes must return the documents the CLI writes, unchanged: the demo and
the future iOS app read the same contract whether it came from a file or a
server. So these tests compare the wire format with the pipeline's own output
rather than asserting hand-written JSON.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from grocery_app.api.app import DEFAULT_PURCHASES, create_app, default_app
from grocery_app.api.repository import InMemoryRepository, JsonRepository
from grocery_app.api.schemas import Purchase, PurchasesDocument
from grocery_app.insights import build_insights
from grocery_app.normalizer import save_json

PURCHASES = {
    "contract_version": 2,
    "meta": {
        "receipts": 2, "date_range": ["2026-01-05", "2026-02-05"], "product_lines": 3,
        "total_net_paid": 4.03, "unresolved_items": ["Geheimnis"], "ambiguous_items": [],
    },
    "purchases": [
        {"date": "2026-01-05", "store": "Musterladen", "source_image": "IMG_1.jpeg",
         "type": "product", "raw_name": "MU Milch 1,5%", "product_id": "p-0001",
         "resolved": True, "resolution": "exact", "candidate_ids": [], "qty": 1,
         "gross": 1.09, "discount": 0.0, "net_paid": 1.09, "tax_class": "A", "tax_rate": 0.07,
         "product": "Milch 1,5%", "brand": "Muster", "product_line": None, "variant": None,
         "category": "Dairy", "is_own_brand": True, "is_organic": False,
         "unit_price": {"amount": 1.09, "per": "l"}},
        {"date": "2026-02-05", "store": "Musterladen", "source_image": "IMG_2.jpeg",
         "type": "product", "raw_name": "MU Milch 1,5%", "product_id": "p-0001",
         "resolved": True, "resolution": "exact", "candidate_ids": [], "qty": 1,
         "gross": 1.19, "discount": 0.0, "net_paid": 1.19, "tax_class": "A", "tax_rate": 0.07,
         "product": "Milch 1,5%", "brand": "Muster", "product_line": None, "variant": None,
         "category": "Dairy", "is_own_brand": True, "is_organic": False,
         "unit_price": {"amount": 1.19, "per": "l"}},
        {"date": "2026-02-05", "store": "Musterladen", "source_image": "IMG_2.jpeg",
         "type": "product", "raw_name": "Geheimnis", "product_id": None,
         "resolved": False, "resolution": "none", "candidate_ids": [], "qty": 1,
         "gross": 1.75, "discount": 0.0, "net_paid": 1.75, "tax_class": "A", "tax_rate": 0.07,
         "unit_price": None},
    ],
}


@pytest.fixture
def client():
    return TestClient(create_app(InMemoryRepository(PURCHASES)))


def test_health_reports_contract_versions_and_receipts(client):
    body = client.get("/health").json()
    assert body == {"status": "ok", "purchases_contract_version": 2,
                    "insights_contract_version": 1, "receipts": 2}


def test_purchases_is_the_contract_unchanged(client):
    r = client.get("/v1/purchases")
    assert r.status_code == 200
    # Fields the normalizer leaves out for unresolved lines come back as null,
    # so compare after the schema has normalized both sides.
    assert r.json() == PurchasesDocument.model_validate(PURCHASES).model_dump()


def test_insights_are_computed_from_the_served_history(client):
    r = client.get("/v1/insights")
    assert r.status_code == 200
    assert r.json() == build_insights(PURCHASES)


def test_insights_as_of_is_honoured(client):
    body = client.get("/v1/insights", params={"as_of": "2026-03-01"}).json()
    assert body["as_of"] == "2026-03-01"
    assert body == build_insights(PURCHASES, as_of=date(2026, 3, 1))


def test_insights_rejects_a_non_date(client):
    r = client.get("/v1/insights", params={"as_of": "yesterday"})
    assert r.status_code == 422
    assert "as_of" in r.json()["detail"]


def test_schema_rejects_a_field_the_contract_does_not_know():
    record = dict(PURCHASES["purchases"][0], surprise=1)
    with pytest.raises(ValueError):
        Purchase.model_validate(record)


def test_json_repository_rereads_the_file(tmp_path):
    path = tmp_path / "purchases.json"
    save_json(PURCHASES, path)
    client = TestClient(create_app(JsonRepository(path)))
    assert client.get("/health").json()["receipts"] == 2
    updated = dict(PURCHASES, meta=dict(PURCHASES["meta"], receipts=3))
    save_json(updated, path)
    assert client.get("/health").json()["receipts"] == 3


def test_default_app_reads_the_path_from_the_environment(tmp_path, monkeypatch):
    path = tmp_path / "elsewhere.json"
    save_json(PURCHASES, path)
    monkeypatch.setenv("GROCERY_PURCHASES", str(path))
    assert TestClient(default_app()).get("/health").status_code == 200
    monkeypatch.delenv("GROCERY_PURCHASES")
    assert DEFAULT_PURCHASES == "data/purchases.json"
