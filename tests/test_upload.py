"""The upload path: a photo in, a job id back, a receipt when it finishes.

Nothing here calls a model. `create_app` takes the extractor as an argument
and has no default, so a test that forgot to pass one would get a 503 rather
than a bill — and that is itself one of the tests below.

The fakes are deliberate about what they fake: the extractor returns the real
`Extraction` dataclass the real one returns, and the receipt inside it is in
the truth schema, so everything downstream of the model call is the real code.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from grocery_app.api.app import MAX_UPLOAD_BYTES, create_app
from grocery_app.api.images import DiskImageStore, sha256_of
from grocery_app.api.repository import InMemoryRepository, PostgresRepository
from grocery_app.db.session import make_session_factory
from grocery_app.extract import Extraction
from tests.conftest import DATABASE_URL as URL

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")


def a_photo(colour: str = "white", size: tuple[int, int] = (40, 60)) -> bytes:
    """A real JPEG, so the upload check and Pillow both see what they expect."""
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="JPEG")
    return buffer.getvalue()


RECEIPT = {
    "store": "Musterladen", "store_location": "Musterstadt", "date": "2026-03-05",
    "time": "11:30", "currency": "EUR", "printed_total": 1.29, "printed_savings": None,
    "tax_buckets": {"7%": 0.08},
    "lines": [{"type": "product", "raw_name": "MU Butter", "qty": 1, "gross": 1.29,
               "discount": 0.0, "net": 1.29, "tax_class": "A"}],
    "computed_total": 1.29, "reconciled": True,
}

META = {"model": "test-model", "prompt_version": "v1", "request_id": "req_1",
        "usage": {"input_tokens": 1500, "output_tokens": 900}, "cost_usd": 0.03102}


class FakeExtractor:
    """Stands in for the paid call, and counts how often it was made."""

    def __init__(self, receipt: dict | None = None, error: Exception | None = None) -> None:
        self.receipt = receipt if receipt is not None else RECEIPT
        self.error = error
        self.calls: list[str] = []

    def __call__(self, path):
        self.calls.append(path.name)
        if self.error is not None:
            raise self.error
        # The real extractor names the receipt after the file it read.
        return Extraction(receipt={**self.receipt, "source_image": path.name}, meta=dict(META))


@pytest.fixture
def uploads(engine, session, tmp_path):
    """A server that can accept photos, with a fake extractor and a temp folder."""
    repository = PostgresRepository(make_session_factory(engine))
    store = DiskImageStore(tmp_path / "uploads")
    extractor = FakeExtractor()
    client = TestClient(create_app(repository, store, extractor))
    return client, extractor, store, repository


def test_a_photo_becomes_a_queued_job_and_then_a_receipt(uploads):
    """TestClient runs the background task before handing back the response,
    so the body is the job as it was queued and the poll is the job as it
    finished. Both halves matter: the phone sees the first and polls for the
    second."""
    client, extractor, _, _ = uploads
    photo = a_photo()

    response = client.post("/v1/receipts", files={"file": ("image.jpg", photo, "image/jpeg")})
    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "queued"
    assert queued["receipt_id"] is None
    assert queued["image_sha256"] == sha256_of(photo)
    assert queued["original_filename"] == "image.jpg"

    done = client.get(f"/v1/jobs/{queued['job_id']}").json()
    assert done["status"] == "done"
    assert done["receipt_id"] is not None
    assert done["model"] == "test-model"
    assert done["cost_usd"] == pytest.approx(0.03102), "what the call cost, in dollars"
    assert done["error"] is None
    assert extractor.calls == [sha256_of(photo)], "the file is named by its hash"


def test_the_extracted_receipt_reaches_the_history_marked_as_a_model_reading(uploads, session):
    from grocery_app.db.models import Receipt

    client, _, _, _ = uploads
    photo = a_photo()
    client.post("/v1/receipts", files={"file": ("image.jpg", photo, "image/jpeg")})

    stored = session.query(Receipt).all()
    assert len(stored) == 1
    assert stored[0].transcribed_by == "llm", \
        "never 'hand': the eval harness scores the model against hand-verified receipts"
    assert stored[0].image_sha256 == sha256_of(photo)
    assert stored[0].store == "Musterladen"

    served = client.get("/v1/purchases").json()
    assert [p["raw_name"] for p in served["purchases"]] == ["MU Butter"]
    assert served["meta"]["receipts"] == 1


def test_the_same_photo_is_never_extracted_twice(uploads):
    client, extractor, _, _ = uploads
    photo = a_photo()
    files = {"file": ("image.jpg", photo, "image/jpeg")}

    first = client.post("/v1/receipts", files=files)
    again = client.post("/v1/receipts",
                        files={"file": ("a-different-name.jpg", photo, "image/jpeg")})

    assert first.status_code == 202 and again.status_code == 200
    assert again.json()["job_id"] == first.json()["job_id"]
    assert len(extractor.calls) == 1, "the second upload must not pay for the same bytes"


def test_a_different_photo_is_a_different_job(uploads):
    client, extractor, _, _ = uploads
    client.post("/v1/receipts", files={"file": ("a.jpg", a_photo("white"), "image/jpeg")})
    client.post("/v1/receipts", files={"file": ("b.jpg", a_photo("black"), "image/jpeg")})
    assert len(extractor.calls) == 2
    assert len(set(extractor.calls)) == 2


def test_a_failed_extraction_is_recorded_rather_than_raised(engine, session, tmp_path):
    from grocery_app.db.models import Receipt

    repository = PostgresRepository(make_session_factory(engine))
    extractor = FakeExtractor(error=RuntimeError("model declined the request"))
    client = TestClient(create_app(repository, DiskImageStore(tmp_path), extractor))

    queued = client.post("/v1/receipts",
                         files={"file": ("image.jpg", a_photo(), "image/jpeg")}).json()
    failed = client.get(f"/v1/jobs/{queued['job_id']}").json()

    assert failed["status"] == "failed"
    assert failed["error"] == "RuntimeError: model declined the request"
    assert failed["receipt_id"] is None
    assert session.query(Receipt).all() == [], "a failed reading stores no receipt"


def test_a_photo_may_be_retried_after_a_failure(engine, tmp_path):
    """A failed job must not become a tombstone that blocks the same photo
    for ever, which is why the dedup lookup ignores failures."""
    repository = PostgresRepository(make_session_factory(engine))
    store = DiskImageStore(tmp_path)
    photo = a_photo()
    files = {"file": ("image.jpg", photo, "image/jpeg")}

    broken = FakeExtractor(error=RuntimeError("timeout"))
    first = TestClient(create_app(repository, store, broken)).post("/v1/receipts", files=files)
    working = FakeExtractor()
    second = TestClient(create_app(repository, store, working)).post("/v1/receipts", files=files)

    assert second.status_code == 202, "a retry is a new job, not the dead one"
    assert second.json()["job_id"] != first.json()["job_id"]
    assert len(working.calls) == 1


def test_a_file_that_is_not_an_image_is_refused_before_anything_is_stored(uploads):
    client, extractor, store, _ = uploads
    response = client.post("/v1/receipts",
                           files={"file": ("notes.txt", b"not a photo", "text/plain")})
    assert response.status_code == 422
    assert "not an image" in response.json()["detail"]
    assert extractor.calls == [], "nothing is paid for, and no job is created"
    assert not list(store.root.glob("*")) if store.root.exists() else True


def test_an_empty_upload_is_refused(uploads):
    client, extractor, _, _ = uploads
    response = client.post("/v1/receipts", files={"file": ("image.jpg", b"", "image/jpeg")})
    assert response.status_code == 422
    assert extractor.calls == []


def test_an_oversized_upload_is_refused(uploads):
    client, extractor, _, _ = uploads
    huge = b"\xff\xd8\xff" + b"0" * MAX_UPLOAD_BYTES
    response = client.post("/v1/receipts", files={"file": ("image.jpg", huge, "image/jpeg")})
    assert response.status_code == 413
    assert extractor.calls == []


def test_stored_bytes_that_disagree_with_the_upload_are_an_error(uploads):
    """The guard against a bug in this code — the wrong buffer hashed, a short
    read — rather than against sha256. Same hash, different length: refuse."""
    client, _, store, _ = uploads
    photo = a_photo()
    files = {"file": ("image.jpg", photo, "image/jpeg")}
    client.post("/v1/receipts", files=files)

    store.path(sha256_of(photo)).write_bytes(photo + b"tampered")
    response = client.post("/v1/receipts", files=files)
    assert response.status_code == 500
    assert "bytes" in response.json()["detail"]


def test_an_unknown_job_is_a_404(uploads):
    client, _, _, _ = uploads
    assert client.get("/v1/jobs/4f1c0e2a-0000-4000-8000-000000000000").status_code == 404


def test_a_server_with_no_extractor_refuses_to_upload(engine, tmp_path):
    """The money guard: `create_app` has no default extractor, so forgetting
    the argument cannot cause a paid call — it causes a 503."""
    repository = PostgresRepository(make_session_factory(engine))
    client = TestClient(create_app(repository, DiskImageStore(tmp_path)))

    response = client.post("/v1/receipts",
                           files={"file": ("image.jpg", a_photo(), "image/jpeg")})
    assert response.status_code == 503
    assert client.get("/health").json()["uploads"] is False
    assert client.get("/v1/purchases").status_code == 200, "reading still works"


def test_a_file_backed_server_cannot_take_photos(tmp_path):
    """`JsonRepository` has no place to put a job, and says so plainly."""
    client = TestClient(create_app(InMemoryRepository({"contract_version": 3, "meta": {},
                                                       "purchases": []}),
                                   DiskImageStore(tmp_path), FakeExtractor()))
    response = client.post("/v1/receipts",
                           files={"file": ("image.jpg", a_photo(), "image/jpeg")})
    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]
