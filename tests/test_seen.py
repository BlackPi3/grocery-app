"""A new receipt is marked until its owner opens it (the owner, 2026-10-13).

A finished receipt no longer opens by itself: the Receipts tab and the
receipt carry a small "new" mark instead. Whether it was opened is kept on
the server (`receipts.seen_at`), so a receipt opened on the laptop is not new
on the phone. Made-up receipts only.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from grocery_app.api.app import create_app
from grocery_app.api.images import DiskImageStore
from grocery_app.api.repository import PostgresRepository
from grocery_app.db.models import Job, Product, Receipt
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL as URL
from tests.test_upload import GUESSED, FakeExtractor, a_photo

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")

OWNER = {"Authorization": "Bearer owner-secret"}


@pytest.fixture
def server(engine, session, tmp_path):
    repository = PostgresRepository(make_session_factory(engine))
    sara = repository.create_user("Sara")
    client = TestClient(create_app(repository, DiskImageStore(tmp_path), FakeExtractor(),
                                   token="owner-secret"))
    return client, {"Authorization": f"Bearer {sara['password']}"}


def send(client, headers, colour="white"):
    job = client.post("/v1/receipts", headers=headers,
                      files={"file": ("r.jpg", a_photo(colour), "image/jpeg")}).json()
    return client.get(f"/v1/jobs/{job['job_id']}", headers=headers).json()["receipt_id"]


def summary(client, headers, receipt_id):
    return next(r for r in client.get("/v1/receipts", headers=headers).json()
                if r["receipt_id"] == receipt_id)


def test_a_new_receipt_is_unseen_until_it_is_opened(server):
    client, _ = server
    receipt_id = send(client, OWNER)
    assert summary(client, OWNER, receipt_id)["seen_at"] is None, "new: the page marks it"

    # Looking is not opening: a GET of the receipt leaves the mark.
    assert client.get(f"/v1/receipts/{receipt_id}", headers=OWNER).status_code == 200
    assert summary(client, OWNER, receipt_id)["seen_at"] is None

    opened = client.put(f"/v1/receipts/{receipt_id}/seen", headers=OWNER)
    assert opened.status_code == 200
    seen_at = opened.json()["seen_at"]
    assert opened.json()["receipt_id"] == receipt_id and seen_at
    assert summary(client, OWNER, receipt_id)["seen_at"] == seen_at, \
        "every device reads the same mark from the list"

    again = client.put(f"/v1/receipts/{receipt_id}/seen", headers=OWNER).json()
    assert again["seen_at"] == seen_at, "the first opening counts"


def test_another_persons_receipt_cannot_be_marked_seen(server):
    client, sara = server
    mine = send(client, OWNER, "red")
    assert client.put(f"/v1/receipts/{mine}/seen", headers=sara).status_code == 404
    assert summary(client, OWNER, mine)["seen_at"] is None, "still new to its owner"
    assert client.put("/v1/receipts/999999/seen", headers=OWNER).status_code == 404

    hers = send(client, sara, "blue")
    assert client.put(f"/v1/receipts/{hers}/seen", headers=sara).status_code == 200
    assert summary(client, sara, hers)["seen_at"] is not None


def test_the_mark_comes_with_the_first_reading(engine, session, tmp_path):
    """Lines are placed after the photo is read; the receipt is in the list,
    marked new, as soon as the first reading stored it."""
    repository = PostgresRepository(make_session_factory(engine))
    session.add(Product(id="p-0001", name="Butter", brand="Muster"))
    session.commit()
    while_placing = []

    def matcher(line, store, inputs):
        with make_session_factory(engine)() as outside:
            (receipt_id,) = outside.scalars(select(Job.receipt_id)).all()
        while_placing.append([(r["receipt_id"], r["seen_at"]) for r in repository.receipts()])
        return {"verdict": "accept", "pick": {"product_id": "p-0001"}, "versions": [],
                "candidates": [], "creates": []}

    client = TestClient(create_app(repository, DiskImageStore(tmp_path),
                                   FakeExtractor(GUESSED), matcher))
    job = client.post("/v1/receipts", files={"file": ("image.jpg", a_photo(), "image/jpeg")})
    done = client.get(f"/v1/jobs/{job.json()['job_id']}").json()
    assert while_placing and all(seen == [(done["receipt_id"], None)] for seen in while_placing)


def test_a_receipt_typed_in_on_the_laptop_is_not_new(session, data):
    from grocery_app.db.io import import_receipts

    import_receipts(session, sorted((data / "receipts" / "truth").glob("IMG_?.json")))
    session.commit()
    assert all(r.seen_at is not None for r in session.scalars(select(Receipt)))
