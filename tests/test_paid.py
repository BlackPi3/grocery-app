"""The seam check: one real photo, through the real model, into the database.

Everything else in this suite fakes the model call, which means nothing else
proves that what the model returns today still fits the code that stores it.
The fake promises a shape; this is the only test that checks the promise.

It makes a real model call, so it is marked `paid` and deselected by default.
It reads through the reader the server uses (`GROCERY_READER`: `api`, a few
cents; `claude-code`, the subscription). Run it deliberately:

    DATABASE_URL=... GROCERY_READER=claude-code \
        GROCERY_TEST_PHOTO=data/receipts/images/IMG_5384.jpeg pytest -m paid

Run it when the model changes, the prompt changes, the receipt schema changes,
or the upload route changes. One photo is enough: "does it still fit?" is a
yes-or-no question, and the eval harness is what measures *how well* the model
reads (see docs/designs/backend-api.md).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from grocery_app.api.app import create_app
from grocery_app.api.images import DiskImageStore
from grocery_app.api.jobs import READER_ENV, configured_extractor
from grocery_app.api.repository import PostgresRepository
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL as URL

pytestmark = [
    pytest.mark.paid,
    pytest.mark.skipif(not URL, reason="DATABASE_URL not set"),
]

PHOTO = os.environ.get("GROCERY_TEST_PHOTO")


@pytest.mark.skipif(not PHOTO, reason="GROCERY_TEST_PHOTO is not set")
def test_a_real_photo_becomes_a_real_receipt(engine, session, tmp_path):
    photo = Path(PHOTO)
    assert photo.exists(), f"GROCERY_TEST_PHOTO does not exist: {photo}"

    client = TestClient(create_app(
        PostgresRepository(make_session_factory(engine)),
        DiskImageStore(tmp_path / "uploads"),
        configured_extractor(),
    ))

    queued = client.post("/v1/receipts",
                         files={"file": (photo.name, photo.read_bytes(), "image/jpeg")})
    assert queued.status_code == 202, queued.text

    job = client.get(f"/v1/jobs/{queued.json()['job_id']}").json()
    assert job["status"] == "done", job.get("error")
    if os.environ.get(READER_ENV, "api") == "api":
        assert job["cost_usd"] and job["cost_usd"] > 0, "a real call costs real money"
    assert job["receipt_id"] is not None

    receipt = client.get(f"/v1/receipts/{job['receipt_id']}").json()
    assert receipt["receipt"]["transcribed_by"] == "llm"
    assert receipt["lines"], "a receipt with no lines means the shape stopped fitting"
    assert receipt["receipt"]["printed_total"] > 0

    served = client.get("/v1/purchases").json()
    assert any(p["source_image"] == receipt["receipt"]["source_image"]
               for p in served["purchases"]), "the real receipt reached the history"

    print(f"\n  {photo.name}: {len(receipt['lines'])} lines, "
          f"{receipt['receipt']['printed_total']:.2f}, "
          f"{os.environ.get(READER_ENV, 'api')} reader, cost {job['cost_usd']}")
