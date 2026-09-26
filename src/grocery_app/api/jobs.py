"""Running an extraction after the response has gone out.

The web request saves the photo, writes the job row, commits, and returns a
job id. This module is what happens next, in the same process, through
FastAPI's `BackgroundTasks`.

Two properties of that are worth stating rather than discovering:

- **It dies with the process.** A restart mid-extraction leaves a `running`
  row that nobody revives. For one user that is acceptable; the row is still
  in PostgreSQL, so recovery is a startup scan whenever it is worth writing.
  Moving to a real queue later changes the line that schedules work, and
  nothing here.
- **It cannot use the request's session.** That one is closed when the
  response is sent. So `run_job` takes a `job_id` — a value, not an ORM
  object, which would arrive detached from a dead session — and opens its own.

The extractor is a parameter, never a default. A model call costs real money,
so there is no argument a test can forget that would make one happen.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.orm import Session, sessionmaker

from grocery_app.api.images import ImageStore
from grocery_app.db.io import receipt_from_dict
from grocery_app.db.models import Job

__all__ = ["Extractor", "anthropic_extractor", "configured_extractor", "job_to_dict",
           "run_job"]

# Derived at extraction time from the lines and the printed total. The receipt
# tables hold what the paper says; these two are a reading of it, recomputable,
# and there is no column for them on purpose.
DERIVED_KEYS = ("computed_total", "reconciled")


class Extraction(Protocol):
    receipt: dict[str, Any]
    meta: dict[str, Any]


Extractor = Callable[[Path], Extraction]


def anthropic_extractor(model: str | None = None) -> Extractor:
    """The real thing: a paid model call per photo.

    The client is built on first use so that importing this module, or
    constructing an app that never extracts anything, needs no API key.
    """
    import anthropic

    from grocery_app.extract import DEFAULT_MODEL, extract_receipt

    client: anthropic.Anthropic | None = None

    def extract(path: Path) -> Extraction:
        nonlocal client
        if client is None:
            client = anthropic.Anthropic()
        return extract_receipt(path, client, model=model or DEFAULT_MODEL)

    return extract


READER_ENV = "GROCERY_READER"
READERS = ("api", "claude-code")


def configured_extractor(reader: str | None = None) -> Extractor:
    """The extractor `GROCERY_READER` names: `api` (the default) or `claude-code`.

    `claude-code` reads through `claude -p` on the subscription, for a server
    running where `claude` is logged in. It is measurably less accurate than
    the API (docs/designs/catalog-growth.md, step 6), so it is a choice, not
    a fallback: a server whose API calls fail says so rather than quietly
    reading worse.
    """
    import os

    reader = reader or os.environ.get(READER_ENV, "api")
    if reader not in READERS:
        raise ValueError(f"{READER_ENV}={reader!r}: expected one of {', '.join(READERS)}")
    if reader == "claude-code":
        from grocery_app.extract import claude_code_reader

        return claude_code_reader()
    return anthropic_extractor()


def job_to_dict(job: Job) -> dict[str, Any]:
    return {
        "job_id": str(job.id),
        "status": job.status,
        "image_sha256": job.image_sha256,
        "original_filename": job.original_filename,
        "receipt_id": job.receipt_id,
        "model": job.model,
        "prompt_version": job.prompt_version,
        "cost_usd": float(job.cost_usd) if job.cost_usd is not None else None,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def _now() -> datetime:
    return datetime.now(UTC)


def _store_receipt(session: Session, job: Job, extraction: Extraction) -> None:
    """The extracted receipt, as a receipt row, marked as a model's reading.

    `transcribed_by = "llm"` is not a formality: the eval harness scores the
    model against hand-verified receipts, and a model's output silently
    entering that set as truth would make the score a lie.
    """
    receipt_dict = {k: v for k, v in extraction.receipt.items() if k not in DERIVED_KEYS}
    receipt_dict["transcribed_by"] = "llm"
    receipt = receipt_from_dict(receipt_dict)
    receipt.image_sha256 = job.image_sha256
    session.add(receipt)
    session.flush()
    job.receipt_id = receipt.id


def run_job(session_factory: sessionmaker[Session], image_store: ImageStore,
            extractor: Extractor, job_id: str, matcher: Any | None = None) -> None:
    """Extract one photo and record what happened, whatever happens.

    With a `matcher` (`api.matching.line_matcher`), the lines the memory cannot
    place are matched before the job is `done`, so a client polling the job
    sees the receipt as it will stay. A matcher that fails does not fail the
    job: the receipt is stored and read, and `error` says what went wrong.
    """
    with session_factory() as session:
        job = session.get(Job, job_id)
        if job is None or job.status != "queued":
            return  # already taken: a queue may deliver the same work twice
        job.status = "running"
        job.started_at = _now()
        session.commit()

        try:
            extraction = extractor(image_store.path(job.image_sha256))
        except Exception as exc:  # noqa: BLE001 - a failed job must say why, not crash a thread
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
            job.finished_at = _now()
            session.commit()
            return

        meta = extraction.meta
        job.model = meta.get("model")
        job.prompt_version = meta.get("prompt_version")
        job.request_id = meta.get("request_id")
        job.usage = meta.get("usage")
        cost = meta.get("cost_usd")
        job.cost_usd = Decimal(str(cost)) if cost is not None else None
        # Committed before the receipt is built: the call has been paid for,
        # and a receipt that will not store must not roll that fact away.
        session.commit()

        try:
            _store_receipt(session, job, extraction)
        except Exception as exc:  # noqa: BLE001 - a receipt that will not store is a failed job
            session.rollback()
            job = session.get(Job, job_id)
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
            job.finished_at = _now()
            session.commit()
            return

        session.commit()
        if matcher is not None:
            from grocery_app.api.matching import match_receipt

            try:
                match_receipt(session, job.receipt_id, matcher)
                session.commit()
            except Exception as exc:  # noqa: BLE001 - the receipt stands without matching
                session.rollback()
                job = session.get(Job, job_id)
                job.error = f"matching failed: {type(exc).__name__}: {exc}"

        job.status = "done"
        job.finished_at = _now()
        session.commit()
