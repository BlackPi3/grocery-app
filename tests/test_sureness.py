"""How sure the app is of each line (`grocery_app.sureness`, the owner's call
of 2026-10-12), and `GET /v1/sureness`. Everything is made up: Musterladen
and the products of the shared fixtures."""

from __future__ import annotations

import pytest

from grocery_app import sureness
from tests.conftest import DATABASE_URL


def line(resolution, said_by="app", **more):
    return {"type": "product", "store": "Musterladen", "raw_name": "MU Etwas",
            "resolution": resolution, "said_by": said_by, **more}


@pytest.mark.parametrize("record, answered, expected", [
    (line("exact"), False, "sure"),
    (line("produce"), False, "sure"),
    (line("price"), False, "unclear_print"),
    (line("family", said_by="app", category="milch"), False, "category_only"),
    (line("family", said_by="app", category=None), False, "needs_answer"),
    (line("none", said_by=None), False, "needs_answer"),
    # A person's word, however it reached the line, is counted apart.
    (line("user", said_by="you"), False, "answered"),
    (line("exact", said_by="you"), False, "answered"),
    (line("none", said_by=None), True, "answered"),
    # Not counted at all: not a product, or left out of the numbers.
    ({**line("exact"), "type": "deposit"}, False, None),
    (line("exact", not_counted=True), False, None),
])
def test_each_state_a_line_records_has_one_level(record, answered, expected):
    assert sureness.level(record, answered) == expected


def test_level_four_says_when_the_paper_names_nothing_and_when_a_kind_was_guessed():
    """Inside level 4, what the data can say about why: a name the till prints
    for anything is the receipt's fault; a guessed category is not used by the
    history, so the line stays at level 4."""
    counts = sureness.empty()
    generic = {**line("none", said_by=None), "store": "FK Frisch Kauf GmbH",
               "raw_name": "Diverse Lebensmittel"}
    sureness.add(counts, generic)
    sureness.add(counts, line("none", said_by=None), category_guessed=True)
    sureness.add(counts, line("exact"), category_guessed=True)
    sureness.add(counts, line("exact", not_counted=True))
    assert counts == {"lines": 3, "answered": 0, "sure": 1, "unclear_print": 0,
                      "category_only": 0, "needs_answer": 2, "print_says_nothing": 1,
                      "category_guessed": 1}


# --- the route ------------------------------------------------------------------------

needs_db = pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set")


def receipt(session, source_image, date, lines):
    from grocery_app.db.io import receipt_from_dict

    row = receipt_from_dict({
        "source_image": source_image, "transcribed_by": "llm", "store": "Musterladen",
        "date": date, "currency": "EUR", "printed_total": sum(g for _, g in lines),
        "lines": [{"type": "product", "raw_name": name, "qty": 1, "gross": gross,
                   "discount": 0.0, "net": gross, "tax_class": "A"} for name, gross in lines]})
    session.add(row)
    session.commit()
    return row.id


@needs_db
def test_the_owner_sees_every_line_by_level_per_month_with_the_checks_yes_rate(
        engine, session, data):
    from fastapi.testclient import TestClient

    from grocery_app.api.app import create_app
    from grocery_app.api.repository import PostgresRepository
    from grocery_app.db.io import import_data, product_from_dict
    from grocery_app.db.models import Check, LineGuess, Resolution
    from grocery_app.db.session import make_session_factory

    import_data(session, data / "receipts" / "truth", data / "products" / "products.json",
                data / "products" / "resolution.json", data / "absent.json", data / "products")
    # A second milk, same kind, never seen on the shelf: `MU Milch` is either.
    session.add(product_from_dict("p-0003", {
        "label": "mu-milch-3", "name": "Milch 3,5%", "brand": "Muster", "details": [],
        "size": None, "category": "milch", "is_organic": False, "eans": [],
        "open_questions": [], "provenance": {"attributes": "test", "source": "test"}}))
    session.add_all([
        Resolution(store="Musterladen", raw_name="MU Milch fettarm", line_type="product",
                   product_id="p-0001", product_ids=[], confirmed_by="matcher"),
        Resolution(store="Musterladen", raw_name="MU Vollmilch", line_type="product",
                   product_id="p-0001", product_ids=[], confirmed_by="matcher"),
        Resolution(store="Musterladen", raw_name="MU Milch", line_type="product",
                   product_id=None, product_ids=["p-0001", "p-0003"], confirmed_by="matcher")])
    session.commit()
    march = receipt(session, "IMG_7.jpeg", "2026-03-01", [
        ("MU Milch fettarm", 1.09),   # remembered by the matcher: sure
        ("MU Milch", 1.19),           # one of two; 1.19 is p-0001's shelf price: unclear print
        ("MU Milch", 0.99),           # one of two, no price says which: the kind only
        ("Rätsel", 2.00),             # nothing: needs an answer
        ("MU Vollmilch", 1.09),       # sure, until a No on its random check
    ])
    april = receipt(session, "IMG_8.jpeg", "2026-04-02", [
        ("Rätsel", 2.00),             # needs an answer, and the reading guessed a kind
        ("Noch ein Rätsel", 1.00),    # answered "none of these": a person's answer
    ])
    session.add_all([
        LineGuess(receipt_id=april, position=0, name="Kuchen", category="milch"),
        Check(receipt_id=march, position=0, raw_name="MU Milch fettarm",
              app_product_id="p-0001"),
        Check(receipt_id=march, position=4, raw_name="MU Vollmilch",
              app_product_id="p-0001")])
    session.commit()

    client = TestClient(create_app(PostgresRepository(make_session_factory(engine))))
    put = "/v1/receipts/{}/lines/{}/resolution"
    assert client.put(put.format(april, 1), json={"none_of_these": True}).status_code == 200
    assert client.put(put.format(march, 4), json={"none_of_these": True}).status_code == 200

    body = client.get("/v1/sureness").json()
    by_month = {m["month"]: m for m in body["months"]}
    assert [m["month"] for m in body["months"]] == ["2026-04", "2026-03", "2026-02",
                                                     "2026-01"], "newest first"
    assert by_month["2026-03"] == {
        "month": "2026-03", "lines": 5, "answered": 1, "sure": 1, "unclear_print": 1,
        "category_only": 1, "needs_answer": 1, "print_says_nothing": 0, "category_guessed": 0}, \
        "the No on a random check made that line a person's answer"
    assert by_month["2026-04"] == {
        "month": "2026-04", "lines": 2, "answered": 1, "sure": 0, "unclear_print": 0,
        "category_only": 0, "needs_answer": 1, "print_says_nothing": 0, "category_guessed": 1}
    # The fixture's own receipts: every memory entry there was a person's,
    # and `Geheimnis` has no answer here.
    assert (by_month["2026-01"]["lines"], by_month["2026-01"]["answered"]) == (2, 2)
    assert [by_month["2026-02"][k] for k in ("lines", "answered", "needs_answer")] == [3, 2, 1]
    for key in sureness.COUNTS:
        assert body[key] == sum(m[key] for m in body["months"]), key
    assert body["checks"] == {"right": 0, "corrected": 1, "yes_rate": 0.0}, \
        "the open check counts for neither"

    assert client.put(put.format(march, 0), json={"product_id": "p-0001"}).status_code == 200
    after = client.get("/v1/sureness").json()
    assert after["checks"] == {"right": 1, "corrected": 1, "yes_rate": 0.5}
    assert (after["sure"], after["answered"]) == (body["sure"] - 1, body["answered"] + 1), \
        "a Yes on a random check makes the line a person's answer"
