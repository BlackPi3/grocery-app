"""What model calls cost, on made-up answers (`grocery_app.spend`).

Parham, 2026-10-11: see what processing a receipt costs, reading it and
finding its items. Every Gemini call is written down where it is made; what
it was for and which upload it served come from the code around it.
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from grocery_app import gemini, spend
from grocery_app.api.app import create_app
from grocery_app.api.images import DiskImageStore
from grocery_app.api.repository import PostgresRepository
from grocery_app.db.models import Job, ModelCall
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL as URL
from tests.test_upload import RECEIPT, FakeExtractor

SEARCHED = {
    "candidates": [{"content": {"parts": [{"text": "{}"}]},
                    "groundingMetadata": {"webSearchQueries": ["MU Butter", "Muster Butter"]}}],
    "usageMetadata": {"promptTokenCount": 1_000_000, "candidatesTokenCount": 100_000,
                      "thoughtsTokenCount": 100_000},
}


def test_a_call_is_priced_by_its_tokens_and_its_searches():
    cost = 0.825 + 0.2 * 4.125 + 2 * spend.SEARCH_PRICE_USD
    with spend.tagged("finding", job_id="job-1"):
        row = spend.call_record("gemini-3.8-flash", SEARCHED)
    assert row == {"purpose": "finding", "job_id": "job-1", "model": "gemini-3.8-flash",
                   "input_tokens": 1_000_000, "output_tokens": 200_000, "searches": 2,
                   "cost_usd": pytest.approx(cost)}
    assert spend.call_record("gemini-3.8-flash", SEARCHED)["purpose"] == "other", \
        "a call nobody tagged is still counted"
    assert spend.call_record("an-unpriced-model", SEARCHED)["cost_usd"] is None


def test_tags_nest_and_come_off():
    with spend.tagged(job_id="job-1"):
        with spend.tagged("reading"):
            assert spend.call_record("m", {})["purpose"] == "reading"
        row = spend.call_record("m", {})
        assert (row["purpose"], row["job_id"]) == ("other", "job-1")
    assert spend.call_record("m", {})["job_id"] is None


def test_every_answered_gemini_call_is_written_down(monkeypatch):
    import urllib.request

    written = []
    spend.install(written.append)
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda request, timeout=None: io.BytesIO(json.dumps(SEARCHED).encode()))
    with spend.tagged("pictures"):
        gemini.generate("gemini-3.8-flash", {"contents": []}, api_key="k")
    assert [(row["purpose"], row["searches"]) for row in written] == [("pictures", 2)]


def test_a_cost_that_cannot_be_written_never_fails_the_call(monkeypatch):
    import urllib.request

    def broken(row):
        raise RuntimeError("database gone")

    spend.install(broken)
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda request, timeout=None: io.BytesIO(json.dumps(SEARCHED).encode()))
    assert gemini.generate("gemini-3.8-flash", {"contents": []}, api_key="k") == SEARCHED


pytestmark_db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")


def a_photo(colour: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 60), colour).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytestmark_db
def test_a_receipt_costs_its_reading_and_finding_its_items(engine, session, tmp_path):
    factory = make_session_factory(engine)
    client = TestClient(create_app(PostgresRepository(factory), DiskImageStore(tmp_path),
                                   FakeExtractor()))
    sent = client.post("/v1/receipts", files={"file": ("r.jpg", a_photo(), "image/jpeg")})
    job_id = sent.json()["job_id"]
    receipt_id = client.get(f"/v1/jobs/{job_id}").json()["receipt_id"]

    write = spend.database_sink(factory)
    with spend.tagged("reading", job_id):
        write(spend.call_record("gemini-3.8-flash", {"usageMetadata": {
            "promptTokenCount": 4000, "candidatesTokenCount": 800}}))
    with spend.tagged("finding", job_id):
        write(spend.call_record("gemini-3.8-flash", SEARCHED))
    with spend.tagged("pictures"):
        write(spend.call_record("gemini-3.8-flash", SEARCHED))
    # An upload from before finding was written down: its reading only.
    evening = TestClient(create_app(PostgresRepository(factory), DiskImageStore(tmp_path),
                                    FakeExtractor({**RECEIPT, "time": "18:40"})))
    sent = evening.post("/v1/receipts", files={"file": ("e.jpg", a_photo("blue"), "image/jpeg")})
    old = session.get(Job, uuid.UUID(sent.json()["job_id"]))
    old.created_at = datetime(2026, 9, 1, tzinfo=UTC)
    session.add(ModelCall(purpose="reading", job_id=old.id, model="gemini-3.8-flash",
                          input_tokens=0, output_tokens=0, searches=0,
                          cost_usd=Decimal("0.00400"), at=datetime(2026, 9, 1, tzinfo=UTC)))
    session.commit()

    doc = client.get("/v1/costs").json()
    reading = 4000 * 0.825 / 1e6 + 800 * 4.125 / 1e6
    finding = 0.825 + 0.2 * 4.125 + 2 * spend.SEARCH_PRICE_USD
    (this_month, september) = doc["months"]
    assert september["month"] == "2026-09" and september["reading_usd"] == 0.004
    assert this_month["reading_usd"] == pytest.approx(reading, abs=1e-5)
    assert this_month["finding_usd"] == pytest.approx(finding, abs=1e-5)
    assert this_month["pictures_usd"] == pytest.approx(finding, abs=1e-5)
    assert this_month["searches"] == 4
    assert this_month["receipts"] == 1
    assert this_month["per_receipt_usd"] == pytest.approx(reading + finding, abs=1e-5)
    # Its 4 searches are inside the month's free ones: billed without them
    # (the owner, 2026-10-14: list price alone read as 21 cents a receipt).
    assert this_month["billed_usd"] == pytest.approx(
        reading + 2 * finding - 4 * spend.SEARCH_PRICE_USD, abs=1e-5)
    assert this_month["billed_per_receipt_usd"] == pytest.approx(
        reading + finding - 2 * spend.SEARCH_PRICE_USD, abs=1e-5)
    assert september["billed_usd"] == 0.004 and september["billed_per_receipt_usd"] is None

    (now, before) = sorted(doc["receipts"], key=lambda r: r["month"], reverse=True)
    assert now["receipt_id"] == receipt_id and now["finding_recorded"]
    assert now["total_usd"] == pytest.approx(reading + finding, abs=1e-5)
    assert not before["finding_recorded"], "finding was not written down then: unknown, not 0"
    assert doc["free_searches_per_month"] == 5000


@pytestmark_db
def test_a_day_past_each_spend_mark_says_so_once(engine, session, monkeypatch, caplog):
    """2026-10-12: guests can spend money now; an unusual day must not go unseen."""
    monkeypatch.setenv("GROCERY_SPEND_ALERT_USD", "1.00")
    write = spend.database_sink(make_session_factory(engine))

    def costing(dollars):  # output tokens only, at $4.125 a million
        return spend.call_record("gemini-3.8-flash", {"usageMetadata": {
            "candidatesTokenCount": round(dollars / 4.125 * 1e6)}})

    for dollars in (0.6, 0.3, 0.2, 0.5, 0.6):  # 0.6, 0.9, 1.1, 1.6, 2.2
        write(costing(dollars))
    alerts = [r.getMessage() for r in caplog.records if spend.ALERT_MARK in r.getMessage()]
    assert len(alerts) == 2, alerts
    assert "$1.10 today" in alerts[0] and "$2.20 today" in alerts[1]


@pytestmark_db
def test_past_the_free_searches_the_rest_are_billed_shared_over_every_search(
        engine, session, tmp_path, monkeypatch):
    monkeypatch.setattr(spend, "FREE_SEARCHES_PER_MONTH", 3)
    factory = make_session_factory(engine)
    client = TestClient(create_app(PostgresRepository(factory), DiskImageStore(tmp_path),
                                   FakeExtractor()))
    job_id = client.post("/v1/receipts", files={"file": ("r.jpg", a_photo(), "image/jpeg")}
                         ).json()["job_id"]
    write = spend.database_sink(factory)
    with spend.tagged("finding", job_id):
        write(spend.call_record("gemini-3.8-flash", SEARCHED))
    with spend.tagged("pictures"):
        write(spend.call_record("gemini-3.8-flash", SEARCHED))

    (month,) = client.get("/v1/costs").json()["months"]
    tokens = 0.825 + 0.2 * 4.125
    assert month["searches"] == 4
    assert month["billed_usd"] == pytest.approx(2 * tokens + 1 * spend.SEARCH_PRICE_USD,
                                                abs=1e-5), "3 of 4 free, the 4th billed"
    assert month["billed_per_receipt_usd"] == pytest.approx(
        tokens + 2 * 0.25 * spend.SEARCH_PRICE_USD, abs=1e-5), "a quarter of its 2 billed"
