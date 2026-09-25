"""The matcher on the server (catalog growth 5b): what it saves, and what it asks.

The line matcher is a table of made-up proposals, so no model is called and
every verdict is visible in the test. The store is Musterladen; every product
and listing is invented.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from grocery_app.api.app import create_app
from grocery_app.api.matching import match_receipt
from grocery_app.api.repository import PostgresRepository
from grocery_app.db.io import receipt_from_dict
from grocery_app.db.models import Correction, Product, Question, Resolution, StoreListing
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL as URL

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")


def listing(article, name, price=1.19):
    """A shop listing as `matcher.gather` hands it on: not in our catalog."""
    return {"source": "musterladen", "name": name, "brand": "Muster", "pack_size": "0,37 kg",
            "product_id": None, "article": article,
            "url": f"https://musterladen.example/{article}", "prices": [price],
            "printed_as": []}


OURS = {"source": "catalog", "name": "Milch 1,5%", "brand": "Muster", "pack_size": "1 l",
        "product_id": "p-0001", "article": None, "url": None, "prices": [1.09],
        "printed_as": []}


class TableMatcher:
    """Answers from a table, printed name -> (verdict, chosen), and counts calls."""

    def __init__(self, table):
        self.table = table
        self.calls = []

    def __call__(self, line, store, inputs):
        self.calls.append(line["raw_name"])
        verdict, chosen = self.table.get(line["raw_name"], ("ask", []))
        return {"raw_name": line["raw_name"], "verdict": verdict,
                "pick": chosen[0] if verdict == "accept" else None,
                "versions": chosen if verdict == "family" else [],
                "candidates": chosen, "reason": "test", "creates": []}


@pytest.fixture
def server(engine, session, data):
    from grocery_app.db.io import import_data

    import_data(session, data / "receipts" / "truth", data / "products" / "products.json",
                data / "products" / "resolution.json", data / "absent.json", data / "products")
    session.commit()
    client = TestClient(create_app(PostgresRepository(make_session_factory(engine))))
    return client, session


def add_receipt(session, source_image, raw_names, store="Musterladen"):
    receipt = receipt_from_dict({
        "source_image": source_image, "transcribed_by": "llm", "store": store,
        "date": "2026-03-01", "currency": "EUR", "printed_total": 1.19 * len(raw_names),
        "lines": [{"type": "deposit" if name == "Pfand" else "product", "raw_name": name,
                   "qty": 1, "gross": 1.19, "discount": 0.0, "net": 1.19, "tax_class": "A"}
                  for name in raw_names]})
    session.add(receipt)
    session.commit()
    return receipt.id


def reading(client, receipt_id):
    return [(line["resolution"], line["product_id"], line["candidate_ids"])
            for line in client.get(f"/v1/receipts/{receipt_id}").json()["lines"]]


def test_an_accepted_known_product_is_remembered_as_the_matchers(server):
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["MU Milch fettarm"])
    counts = match_receipt(session, receipt, TableMatcher({"MU Milch fettarm": ("accept", [OURS])}))
    session.commit()

    assert counts == {"accepted": 1, "families": 0, "questions": 0, "products": 0}
    assert reading(client, receipt) == [("exact", "p-0001", [])]
    entry = session.scalars(select(Resolution).where(
        Resolution.raw_name == "MU Milch fettarm")).one()
    assert entry.confirmed_by == "matcher", "a machine's answer, open to correction"


def test_a_new_shop_listing_becomes_a_product_with_its_listing(server):
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["MU Deo Kühlschr."])
    match_receipt(session, receipt,
                  TableMatcher({"MU Deo Kühlschr.": ("accept", [listing("4000000000077",
                                                                        "Kühlschrank Deo")])}))
    session.commit()

    (_, product_id, _), = reading(client, receipt)
    assert product_id == "p-0003", "the next id after the catalog's p-0002"
    product = session.get(Product, product_id)
    assert (product.name, product.provenance["decided_by"]) == ("Kühlschrank Deo", "matcher")
    stored = session.scalars(select(StoreListing).where(
        StoreListing.article_number == "4000000000077")).one()
    assert (stored.store, stored.product_id, stored.prices[0]["price"]) == \
        ("Musterladen", product_id, 1.19)


def test_versions_the_line_cannot_tell_apart_become_a_family(server):
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["MU Wraps"])
    wraps = [listing("11", "Tortilla Wraps, Classic"), listing("12", "Tortilla Wraps Mehrkorn")]
    counts = match_receipt(session, receipt, TableMatcher({"MU Wraps": ("family", wraps)}))
    session.commit()

    assert counts["families"] == 1 and counts["products"] == 2
    assert reading(client, receipt) == [("family", None, ["p-0003", "p-0004"])]


def test_a_line_it_cannot_settle_becomes_one_question(server):
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["Rätsel"])
    table = TableMatcher({})
    match_receipt(session, receipt, table)
    match_receipt(session, receipt, table)
    session.commit()

    (question,) = session.scalars(select(Question)).all()
    assert (question.position, question.raw_name, question.answered_at) == (0, "Rätsel", None)
    assert table.calls == ["Rätsel"], "not asked about twice"
    assert reading(client, receipt) == [("none", None, [])]


def test_known_lines_deposits_and_catch_all_names_are_not_matched(server):
    _, session = server
    known = add_receipt(session, "IMG_7.jpeg", ["MU Milch 1,5%", "Pfand"])
    catch_all = add_receipt(session, "IMG_8.jpeg", ["Diverse Lebensmittel"],
                            store="FK Frisch Kauf GmbH")
    table = TableMatcher({})
    match_receipt(session, known, table)
    match_receipt(session, catch_all, table)
    assert table.calls == []


def test_a_name_printed_twice_on_one_receipt_is_matched_once(server):
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["MU Milch fettarm", "MU Milch fettarm"])
    table = TableMatcher({"MU Milch fettarm": ("accept", [OURS])})
    match_receipt(session, receipt, table)
    session.commit()

    assert table.calls == ["MU Milch fettarm"]
    assert [r for r, _, _ in reading(client, receipt)] == ["exact", "exact"]


def test_answering_a_question_closes_it_and_overruling_the_matcher_is_counted(server):
    """5a and 5b together: the matcher's answer is a guess the shopper can
    overrule, and the overruling is counted."""
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["Rätsel", "MU Milch fettarm"])
    match_receipt(session, receipt,
                  TableMatcher({"MU Milch fettarm": ("accept", [OURS])}))
    session.commit()

    client.put(f"/v1/receipts/{receipt}/lines/0/resolution", json={"product_id": "p-0002"})
    client.put(f"/v1/receipts/{receipt}/lines/1/resolution", json={"product_id": "p-0002"})

    question = session.scalars(select(Question)).one()
    session.refresh(question)
    assert question.answered_at is not None
    (mistake,) = session.scalars(select(Correction)).all()
    assert (mistake.raw_name, mistake.machine_product_id, mistake.shopper_product_id) == \
        ("MU Milch fettarm", "p-0001", "p-0002")
