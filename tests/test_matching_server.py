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


# --- the questions list, and answering it (5c) ----------------------------------------


def test_questions_are_the_lines_nothing_placed_with_what_the_matcher_found(server):
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["Rätsel", "MU Wraps", "MU Milch 1,5%"])
    catch_all = add_receipt(session, "IMG_8.jpeg", ["Diverse Lebensmittel"],
                            store="FK Frisch Kauf GmbH")
    wraps = [listing("11", "Tortilla Wraps, Classic"), listing("12", "Tortilla Wraps Mehrkorn")]
    rätsel = [listing("21", "Rätselheft"), OURS]
    table = TableMatcher({"MU Wraps": ("family", wraps), "Rätsel": ("ask", rätsel)})
    match_receipt(session, receipt, table)
    match_receipt(session, catch_all, table)
    session.commit()

    body = client.get("/v1/questions").json()
    asked = {(q["receipt_id"], q["raw_name"]): q for q in body["questions"]}
    # Geheimnis from the fixture's IMG_2 is open too; the family and the known
    # milk are not questions.
    assert set(asked) == {(receipt, "Rätsel"), (catch_all, "Diverse Lebensmittel"),
                          (asked_id(body, "Geheimnis"), "Geheimnis")}
    rq = asked[(receipt, "Rätsel")]
    assert [c["name"] for c in rq["candidates"]] == ["Rätselheft", "Milch 1,5%"]
    assert rq["candidates"][1]["product_id"] == "p-0001"
    assert rq["paid"] == 1.19 and rq["per_line"] is False
    assert asked[(catch_all, "Diverse Lebensmittel")]["per_line"] is True
    assert asked[(catch_all, "Diverse Lebensmittel")]["candidates"] == [], "never matched"
    assert body["meta"] == {"open": 3, "matcher_answers": 1, "overruled": 0}


def asked_id(body, raw_name):
    return next(q["receipt_id"] for q in body["questions"] if q["raw_name"] == raw_name)


def test_answering_with_a_candidate_makes_the_listing_a_product_the_shopper_chose(server):
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["Rätsel"])
    match_receipt(session, receipt, TableMatcher(
        {"Rätsel": ("ask", [listing("21", "Rätselheft", price=2.5)])}))
    session.commit()

    response = client.put(f"/v1/receipts/{receipt}/lines/0/resolution", json={"candidate": 1})
    assert response.status_code == 200
    line = response.json()["lines"][0]
    assert (line["resolution"], line["product"]) == ("user", "Rätselheft")
    product = session.get(Product, line["product_id"])
    assert product.provenance["decided_by"] == "shopper"
    assert [q["raw_name"] for q in client.get("/v1/questions").json()["questions"]] == \
        ["Geheimnis"], "answered, and remembered for the next receipt"


def test_none_of_these_makes_a_product_in_the_shoppers_words(server):
    """Kashk: no shop lists it, the shopper knows it. The product holds what
    was said and says what is still unknown."""
    client, session = server
    receipt = add_receipt(session, "IMG_8.jpeg", ["Diverse Lebensmittel"],
                          store="FK Frisch Kauf GmbH")

    response = client.put(f"/v1/receipts/{receipt}/lines/0/resolution",
                          json={"new_product": {"name": "Kashk"}})
    line = response.json()["lines"][0]
    assert (line["resolution"], line["product"]) == ("user", "Kashk")
    product = session.get(Product, line["product_id"])
    assert product.open_questions == ["brand unknown", "category unknown"]
    assert product.provenance == {"attributes": "shopper", "source": None,
                                  "decided_by": "shopper"}
    assert session.scalars(select(Resolution).where(
        Resolution.raw_name == "Diverse Lebensmittel")).all() == [], "per line, never a rule"


@pytest.mark.parametrize("body, detail", [
    ({"candidate": 3}, "offers no candidate 3"),
    ({"candidate": 1, "product_id": "p-0001"}, "exactly one of"),
    ({}, "exactly one of"),
])
def test_an_answer_must_name_one_real_thing(server, body, detail):
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["Rätsel"])
    match_receipt(session, receipt, TableMatcher({"Rätsel": ("ask", [listing("21", "Heft")])}))
    session.commit()

    response = client.put(f"/v1/receipts/{receipt}/lines/0/resolution", json=body)
    assert response.status_code == 422
    assert detail in response.json()["detail"]


# --- answers from a sheet, and receipts read elsewhere (step 6) --------------------------


def test_answers_from_a_sheet_are_given_only_where_they_name_a_real_product(server):
    from grocery_app.api.answers import apply_answers

    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["Rätsel", "Kashk-ish", "MU Milch 1,5%"])
    match_receipt(session, receipt, TableMatcher(
        {"Rätsel": ("ask", [listing("21", "Rätselheft")]), "Kashk-ish": ("ask", [])}))
    session.commit()

    def truth(image, position, name, catalog_ids=(), article=None):
        return {"source_image": image, "position": position, "raw_name": name,
                "catalog_ids": list(catalog_ids), "article": article, "product": "x"}

    sheet = {"lines": [
        truth("IMG_7.jpeg", 0, "Rätsel", article="21"),         # a shop listing offered
        truth("IMG_7.jpeg", 1, "Kashk-ish"),                     # words only
        truth("IMG_7.jpeg", 2, "MU Milch 1,5%", ["p-0002"]),     # placed already
        truth("IMG_2.jpeg", 2, "Geheimnis", ["p-0001"]),         # a catalog id
        truth("IMG_9.jpeg", 0, "Nirgends", ["p-0001"]),          # no such receipt
    ]}
    done = apply_answers(PostgresRepository(make_session_factory(session.get_bind())),
                         sheet, "parham", "answer sheet")

    assert {kind: len(labels) for kind, labels in done.items()} == {
        "answered": 2, "placed_already": 1, "words_only": 1, "not_offered": 0,
        "family": 0, "no_receipt": 1}
    open_names = [q["raw_name"] for q in client.get("/v1/questions").json()["questions"]]
    assert open_names == ["Kashk-ish"], "only the words-only line is still a question"
    milk = client.get(f"/v1/receipts/{receipt}").json()["lines"][2]
    assert milk["product_id"] == "p-0001", "a placed line is not overruled by the sheet"


def test_readings_are_added_only_for_the_named_photos(server, tmp_path, monkeypatch):
    import json
    import sys

    from grocery_app.cli import main
    from grocery_app.db.models import Receipt

    _, session = server
    readings, photos = tmp_path / "readings", tmp_path / "photos"
    readings.mkdir()
    photos.mkdir()
    for image in ("IMG_20.jpeg", "IMG_21.jpeg"):
        (readings / image.replace(".jpeg", ".json")).write_text(json.dumps({
            "source_image": image, "transcribed_by": "llm", "store": "Musterladen",
            "date": "2026-03-02", "currency": "EUR", "printed_total": 1.0,
            "lines": [{"type": "product", "raw_name": "Rätsel", "qty": 1, "gross": 1.0,
                       "discount": 0.0, "net": 1.0, "tax_class": "A"}]}))
    (photos / "IMG_20.jpeg").write_bytes(b"photo")

    monkeypatch.setattr(sys, "argv", ["grocery-app", "db", "add-readings", "--url", URL,
                                      "--readings", str(readings), "--photos", str(photos)])
    main()
    stored = {r.source_image: r.transcribed_by
              for r in session.scalars(select(Receipt).where(Receipt.store == "Musterladen"))}
    assert stored.get("IMG_20.jpeg") == "llm" and "IMG_21.jpeg" not in stored
