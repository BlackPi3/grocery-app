"""The HTTP layer over made-up data.

The routes must return the documents the CLI writes, unchanged: the demo and
the future iOS app read the same contract whether it came from a file or a
server. So these tests compare the wire format with the pipeline's own output
rather than asserting hand-written JSON.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from grocery_app.api.app import create_app, default_app
from grocery_app.api.repository import InMemoryRepository, JsonRepository
from grocery_app.api.schemas import Purchase
from grocery_app.insights import build_insights
from grocery_app.normalizer import save_json

PURCHASES = {
    "contract_version": 4,
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
         "category": "milch",
         "category_path": ["Molkereiprodukte & Eier", "Milch & Joghurt", "Milch"],
         "is_budget_brand": True, "is_organic": False,
         "unit_price": {"amount": 1.09, "per": "l"}},
        {"date": "2026-02-05", "store": "Musterladen", "source_image": "IMG_2.jpeg",
         "type": "product", "raw_name": "MU Milch 1,5%", "product_id": "p-0001",
         "resolved": True, "resolution": "exact", "candidate_ids": [], "qty": 1,
         "gross": 1.19, "discount": 0.0, "net_paid": 1.19, "tax_class": "A", "tax_rate": 0.07,
         "product": "Milch 1,5%", "brand": "Muster", "product_line": None, "variant": None,
         "category": "milch",
         "category_path": ["Molkereiprodukte & Eier", "Milch & Joghurt", "Milch"],
         "is_budget_brand": True, "is_organic": False,
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
    assert body == {"status": "ok", "purchases_contract_version": 4,
                    "insights_contract_version": 2, "receipts": 2,
                    "uploads": False, "writes": False}
    assert (body["uploads"], body["writes"]) == (False, False), \
        "a file-backed server can do neither, and says so rather than 404ing later"


def test_purchases_is_the_contract_unchanged(client):
    """The wire format is the document, key for key.

    Comparing against a copy re-normalized by the same schema would prove
    nothing: it would hide exactly the kind of field the schema adds or drops
    on the way out. So this compares with the document as written.
    """
    r = client.get("/v1/purchases")
    assert r.status_code == 200
    assert r.json() == PURCHASES


def test_an_unresolved_line_gains_no_attributes_on_the_wire(client):
    """The normalizer omits the product attributes it does not know; so does
    the server. A client must not see `brand: null` where there is no brand
    field at all, or it will report a product with no brand."""
    served = next(p for p in client.get("/v1/purchases").json()["purchases"]
                  if not p["resolved"])
    for field in ("product", "brand", "product_line", "variant", "category",
                  "category_path", "is_budget_brand", "is_organic"):
        assert field not in served
    # A null the document does carry is still sent.
    assert served["unit_price"] is None
    assert served["product_id"] is None


def test_a_resolved_line_keeps_its_attributes_on_the_wire(client):
    served = next(p for p in client.get("/v1/purchases").json()["purchases"]
                  if p["resolved"])
    assert served["product"] == "Milch 1,5%"
    assert served["brand"] == "Muster"
    assert served["is_budget_brand"] is True
    # The key is the identity; the path is what a reader is shown.
    assert served["category"] == "milch"
    assert served["category_path"][-1] == "Milch"
    assert served["variant"] is None, "a known-empty attribute is still sent"


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
    """A 200 would prove nothing here: the default path answers too.

    So the file at the configured path carries a receipt count no other file
    has, and the response has to show it.
    """
    path = tmp_path / "elsewhere.json"
    save_json(dict(PURCHASES, meta=dict(PURCHASES["meta"], receipts=99)), path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("GROCERY_PURCHASES", str(path))
    assert TestClient(default_app()).get("/health").json()["receipts"] == 99


def test_the_repository_is_chosen_by_the_environment(tmp_path, monkeypatch):
    """Which store production reads from. Without a URL it is the file; with
    one it is PostgreSQL, and no connection is made to decide that."""
    from grocery_app.api.repository import JsonRepository as _Json
    from grocery_app.api.repository import PostgresRepository, default_repository

    path = tmp_path / "purchases.json"
    save_json(PURCHASES, path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("GROCERY_PURCHASES", str(path))
    chosen = default_repository()
    assert isinstance(chosen, _Json) and chosen.purchases_path == path

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://nobody@localhost:1/nothing")
    assert isinstance(default_repository(), PostgresRepository)
