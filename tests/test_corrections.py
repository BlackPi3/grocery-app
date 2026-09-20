"""The write half of phase 2: read one receipt back, and correct it.

These are the two things the product is actually about. The catalog can say
what `MU Milch 1,5%` means at Musterladen; only the person who was there knows
which of three Chia packs `MU Chia` was, or that this photo is the same paper
they already shot. Everything here goes through the real normalizer, so a
line's reading on this screen is the reading the insights will use.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from grocery_app.api.app import create_app
from grocery_app.api.repository import InMemoryRepository, PostgresRepository
from grocery_app.db.models import Product, Receipt, Resolution
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL as URL

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")


@pytest.fixture
def corrections(engine, session, data):
    from grocery_app.db.io import import_data

    # No line answers imported: every test here makes its own, so the state
    # each one starts from is visible in the test rather than in a fixture.
    import_data(session, data / "receipts" / "truth", data / "products" / "products.json",
                data / "products" / "resolution.json", data / "absent.json",
                data / "products")
    session.commit()
    client = TestClient(create_app(PostgresRepository(make_session_factory(engine))))
    receipt_id = session.scalars(
        select(Receipt).where(Receipt.source_image == "IMG_2.jpeg")).one().id
    return client, session, receipt_id


def make_bananas_ambiguous(session):
    """Two pack sizes the till prints the same name for — the case a shopper
    can settle and the catalog cannot."""
    session.add(Product(id="p-0003", name="Bananen Bio", brand=None))
    row = session.scalars(
        select(Resolution).where(Resolution.raw_name == "Bananen")).one()
    row.product_id = None
    row.product_ids = ["p-0002", "p-0003"]
    row.status = "ambiguous_on_receipt"
    session.commit()


def test_a_receipt_comes_back_with_every_line_read(corrections):
    client, _, receipt_id = corrections
    body = client.get(f"/v1/receipts/{receipt_id}").json()

    assert body["receipt_id"] == receipt_id
    assert body["receipt"]["source_image"] == "IMG_2.jpeg"
    assert body["receipt"]["transcribed_by"] == "hand"
    assert [line["position"] for line in body["lines"]] == [0, 1, 2]
    assert [line["raw_name"] for line in body["lines"]] == \
        ["MU Milch 1,5%", "Bananen", "Geheimnis"]
    assert [line["resolution"] for line in body["lines"]] == ["exact", "exact", "none"]


def test_an_unresolved_line_carries_no_invented_product_fields(corrections):
    """The same rule as /v1/purchases: the wire format says what the document
    says, and the document has no brand for a line nothing could place."""
    client, _, receipt_id = corrections
    unknown = client.get(f"/v1/receipts/{receipt_id}").json()["lines"][2]

    assert unknown["resolved"] is False
    for invented in ("product", "brand", "category", "is_own_brand"):
        assert invented not in unknown


def test_answering_narrows_a_family_to_one_product(corrections):
    client, session, receipt_id = corrections
    make_bananas_ambiguous(session)

    before = client.get(f"/v1/receipts/{receipt_id}").json()["lines"][1]
    assert (before["resolution"], before["resolved"]) == ("family", False)
    assert before["candidate_ids"] == ["p-0002", "p-0003"]

    answered = client.put(f"/v1/receipts/{receipt_id}/lines/1/resolution",
                          json={"product_id": "p-0003", "basis": "memory"})
    assert answered.status_code == 200
    line = answered.json()["lines"][1]
    assert (line["resolution"], line["product_id"], line["resolved"]) == ("user", "p-0003", True)

    # An answer is about one line, not about the name. The identical line on
    # the other receipt has no answer and stays ambiguous, which is correct:
    # the shopper said what *that* purchase was, not what the word means.
    served = client.get("/v1/purchases").json()
    bananas = {p["source_image"]: p["resolution"] for p in served["purchases"]
               if p["raw_name"] == "Bananen"}
    assert bananas == {"IMG_2.jpeg": "user", "IMG_1.jpeg": "family"}
    assert served["meta"]["ambiguous_items"] == ["Bananen"]


def test_withdrawing_an_answer_returns_the_line_to_the_family(corrections):
    client, session, receipt_id = corrections
    make_bananas_ambiguous(session)
    client.put(f"/v1/receipts/{receipt_id}/lines/1/resolution", json={"product_id": "p-0003"})

    withdrawn = client.put(f"/v1/receipts/{receipt_id}/lines/1/resolution",
                           json={"product_id": None})
    assert withdrawn.status_code == 200
    assert withdrawn.json()["lines"][1]["resolution"] == "family"


def test_an_answer_is_bound_to_the_line_text_not_just_its_position(corrections):
    """Re-extracting a photo can change what line 1 says. An answer that was
    about bananas must not silently become an answer about whatever now sits
    in that slot."""
    client, session, receipt_id = corrections
    make_bananas_ambiguous(session)
    client.put(f"/v1/receipts/{receipt_id}/lines/1/resolution", json={"product_id": "p-0003"})

    receipt = session.get(Receipt, receipt_id)
    receipt.lines[1].raw_name = "Bananen Chiquita"
    session.add(Resolution(store="Musterladen", raw_name="Bananen Chiquita",
                           line_type="product", product_ids=["p-0002", "p-0003"]))
    session.commit()

    line = client.get(f"/v1/receipts/{receipt_id}").json()["lines"][1]
    assert line["resolution"] == "family", "the stale answer is ignored, not reapplied"


def test_answering_a_line_the_catalog_cannot_place_at_all(corrections, tmp_path):
    """The case the phone flow exists for, and the one that makes a product
    reachable from a second store: the name means nothing to the catalog, and
    the shopper says which known product it was."""
    from grocery_app.db.io import export_data
    from grocery_app.normalizer import load_json

    client, session, receipt_id = corrections
    assert client.get(f"/v1/receipts/{receipt_id}").json()["lines"][2]["resolution"] == "none"

    response = client.put(f"/v1/receipts/{receipt_id}/lines/2/resolution",
                          json={"product_id": "p-0001", "basis": "memory"})
    assert response.status_code == 200
    line = response.json()["lines"][2]
    assert (line["resolution"], line["product_id"], line["resolved"]) == ("user", "p-0001", True)
    assert line["product"] == "Milch 1,5%"

    served = client.get("/v1/purchases").json()
    assert served["meta"]["unresolved_items"] == [], "it counts in the history now"

    # And it is still the shopper's note, not catalog fact: `db export` hands
    # it back to the propose/confirm loop on the laptop.
    export_data(session, tmp_path / "out")
    answers = load_json(tmp_path / "out" / "receipts" / "line_resolutions.json")["entries"]
    assert {"source_image": "IMG_2.jpeg", "line_index": 2, "product_id": "p-0001"}.items() <= \
        next(e for e in answers if e["line_index"] == 2).items()


def test_a_deposit_line_cannot_be_answered_as_a_product(corrections):
    """Pfand is not a product, so an answer on it is a misclick. Refused at the
    route so the shopper hears about it, and ignored by the normalizer so a
    hand-written file cannot do it either."""
    client, session, _ = corrections
    first = session.scalars(select(Receipt).where(Receipt.source_image == "IMG_1.jpeg")).one()

    response = client.put(f"/v1/receipts/{first.id}/lines/2/resolution",
                          json={"product_id": "p-0001"})
    assert response.status_code == 422
    assert "deposit" in response.json()["detail"]


def test_an_answer_naming_a_product_the_catalog_lacks_is_refused(corrections):
    client, _, receipt_id = corrections
    response = client.put(f"/v1/receipts/{receipt_id}/lines/1/resolution",
                          json={"product_id": "p-9999"})
    assert response.status_code == 422
    assert "p-9999" in response.json()["detail"]


def test_a_line_or_receipt_that_does_not_exist_is_a_404(corrections):
    client, _, receipt_id = corrections
    assert client.get("/v1/receipts/424242").status_code == 404
    assert client.put(f"/v1/receipts/{receipt_id}/lines/99/resolution",
                      json={"product_id": "p-0001"}).status_code == 404
    assert client.patch("/v1/receipts/424242", json={"is_duplicate": True}).status_code == 404


def test_marking_a_receipt_duplicate_takes_it_out_of_the_history(corrections):
    """Not a label: the normalizer drops a duplicate, so this changes the money."""
    client, _, receipt_id = corrections
    before = client.get("/v1/purchases").json()["meta"]

    patched = client.patch(f"/v1/receipts/{receipt_id}", json={"is_duplicate": True})
    assert patched.status_code == 200
    assert patched.json()["receipt"]["is_duplicate"] is True

    after = client.get("/v1/purchases").json()
    assert after["meta"]["receipts"] == before["receipts"] - 1
    assert after["meta"]["total_net_paid"] < before["total_net_paid"]
    assert [p for p in after["purchases"] if p["source_image"] == "IMG_2.jpeg"] == []


def test_correcting_the_store_changes_what_resolves(corrections):
    """Resolution is store-scoped, which is why a photo with its header cropped
    off leaves every line unplaceable until someone says where they were."""
    client, _, receipt_id = corrections
    response = client.patch(f"/v1/receipts/{receipt_id}", json={"store": "Woanders"})

    assert response.status_code == 200
    assert response.json()["receipt"]["store"] == "Woanders"
    assert [line["resolution"] for line in response.json()["lines"]] == ["none", "none", "none"]


def test_a_patch_that_changes_nothing_is_refused(corrections):
    client, _, receipt_id = corrections
    response = client.patch(f"/v1/receipts/{receipt_id}", json={})
    assert response.status_code == 422
    assert "is_duplicate" in response.json()["detail"]


def test_a_patch_may_not_rewrite_the_receipt(corrections):
    """Only two header facts are writable. The paper is not editable over HTTP."""
    client, _, receipt_id = corrections
    response = client.patch(f"/v1/receipts/{receipt_id}", json={"printed_total": 0.01})
    assert response.status_code == 422


def test_a_file_backed_server_cannot_record_corrections():
    client = TestClient(create_app(InMemoryRepository(
        {"contract_version": 2, "meta": {}, "purchases": []})))

    assert client.get("/health").json()["writes"] is False
    assert client.get("/v1/receipts/1").status_code == 503
    assert client.put("/v1/receipts/1/lines/0/resolution",
                      json={"product_id": "p-0001"}).status_code == 503
    assert client.patch("/v1/receipts/1", json={"is_duplicate": True}).status_code == 503
