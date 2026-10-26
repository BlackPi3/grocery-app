"""Skip (owner, 2026-10-26): a person may not want to answer, or may not
remember. Skipping is not an answer: the line keeps the app's guess, counts
only if that guess is groceries, and the card comes again after the others.

Made-up receipts and fake matchers/readers only; no model is called.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from grocery_app.api.matching import match_receipt
from grocery_app.db.models import Check, LineGuess, Question
from grocery_app.insights import build_insights
from tests.conftest import DATABASE_URL as URL
from tests.test_api import run_page_function
from tests.test_matching_server import (  # noqa: F401
    TableMatcher,
    add_receipt,
    identified_receipt,
    reads_as,
    server,
)

db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")


def asked(client, receipt):
    return [q for q in client.get("/v1/questions").json()["questions"]
            if q["receipt_id"] == receipt]


@db
def test_a_skipped_question_stays_unanswered_and_says_when(server):  # noqa: F811
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["XY Ding"])
    match_receipt(session, receipt, TableMatcher({}), reads_as())
    session.commit()
    (before,) = asked(client, receipt)
    assert before["skipped_at"] is None

    assert client.put(f"/v1/receipts/{receipt}/lines/0/skipped").status_code == 204
    (after,) = asked(client, receipt)
    assert after["skipped_at"] and after["cards"] == before["cards"], "asked again later"
    session.expire_all()
    question = session.scalars(select(Question)).one()
    assert question.answered_at is None, "a skip is not an answer"
    line = client.get(f"/v1/receipts/{receipt}").json()["lines"][0]
    assert line["resolution"] == "none", "nothing is placed"


@db
def test_a_skipped_spot_check_says_when(server):  # noqa: F811
    from grocery_app.api.checks import pick_checks

    client, session = server
    receipt = identified_receipt(session, ["Himbeeren 250g"], known=["MU Milch 1,5%"])
    pick_checks(session, receipt)
    session.commit()
    check = session.scalars(select(Check)).one()
    assert client.put(f"/v1/receipts/{receipt}/lines/{check.position}/skipped"
                      ).status_code == 204
    (shown,) = client.get("/v1/checks").json()["checks"]
    assert shown["skipped_at"]


@db
def test_a_line_nothing_asks_about_cannot_be_skipped(server):  # noqa: F811
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["XY Ding"])
    assert client.put(f"/v1/receipts/{receipt}/lines/0/skipped").status_code == 404
    assert client.put("/v1/receipts/999999/lines/0/skipped").status_code == 404


@db
def test_a_line_nothing_placed_carries_its_guessed_category(server):  # noqa: F811
    """The seam to the contract: the photo reading's guess travels in
    purchases.json, only on a line nothing placed, and decides only whether
    it counts."""
    from grocery_app.api.schemas import PurchasesDocument

    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["XY Ding", "XY Socken"])
    session.add_all([LineGuess(receipt_id=receipt, position=0, name="Ding", category="aepfel"),
                     LineGuess(receipt_id=receipt, position=1, name="Socken",
                               category="kleidung")])
    session.commit()
    served = client.get("/v1/purchases").json()
    PurchasesDocument.model_validate(served)
    mine = {p["raw_name"]: p for p in served["purchases"] if p["raw_name"].startswith("XY ")}
    assert (mine["XY Ding"]["guessed_category"], mine["XY Socken"]["guessed_category"]) == \
        ("aepfel", "kleidung")
    assert mine["XY Ding"].get("category") is None and mine["XY Ding"]["product_id"] is None
    placed = [p for p in served["purchases"] if p["product_id"]]
    assert placed and all("guessed_category" not in p for p in placed)


def line(raw_name, net, guessed=None, category=None):
    return {"date": "2026-09-03", "store": "Musterladen", "source_image": "a", "type": "product",
            "raw_name": raw_name, "product_id": "p-1" if category else None,
            "resolved": bool(category), "resolution": "exact" if category else "none",
            "qty": 1.0, "gross": net, "discount": 0.0, "net_paid": net, "category": category,
            **({"guessed_category": guessed} if guessed else {})}


def test_a_line_nothing_placed_counts_only_if_its_guess_counts():
    doc = {"meta": {}, "purchases": [line("Milch", 1.0, category="milch"),
                                     line("XY Ding", 2.0, guessed="aepfel"),
                                     line("XY Socken", 4.0, guessed="kleidung"),
                                     line("XY Wein", 8.0, guessed="rotwein"),
                                     line("XY Unklar", 16.0)]}
    assert build_insights(doc)["months"][0]["spend"] == 19.0, \
        "groceries, a grocery guess, and a line with no guess at all"
    assert build_insights(doc, also=frozenset({"vices"}))["months"][0]["spend"] == 27.0
    from grocery_app.categories import label

    left = build_insights(doc)["coverage"]["not_grocery"]["by_category"]
    assert left == {label("rotwein"): 8.0, "Kleidung & Schuhe": 4.0}


def test_a_skipped_card_comes_after_the_others_the_longest_skipped_first():
    from grocery_app.api.app import REVIEW_PAGE

    page = REVIEW_PAGE.read_text(encoding="utf-8")
    out = run_page_function(page, "asks", """
        const state = { removing: new Set(), checks: { checks: [
            { receipt_id: 1, position: 0, app_product: "A", skipped_at: "2026-10-26T10:00:00Z" },
            { receipt_id: 1, position: 1, app_product: "B" }] },
          questions: { questions: [
            { receipt_id: 2, position: 0, candidates: [], skipped_at: "2026-10-26T09:00:00Z",
              cards: [{ choice: "C" }] },
            { receipt_id: 2, position: 1, candidates: [], cards: [{ choice: "D" }] }] } };
        console.log(asks().map(a => a.cards[0].name).join(","));
    """)
    assert out == ["B,D,C,A"]


def test_every_card_has_a_skip():
    from grocery_app.api.app import REVIEW_PAGE

    page = REVIEW_PAGE.read_text(encoding="utf-8")
    assert 'el("button", { class: "quiet skip", onclick: () => skip(line) }, "Skip")' in page
    assert "/skipped`" in page
