"""Running an extraction after the response has gone out.

The web request saves the photo, writes the job row, commits, and returns a
job id. This module is what happens next, in the same process, through
FastAPI's `BackgroundTasks`.

Two properties of that are worth stating rather than discovering:

- **It dies with the process.** A deploy replaces the process, and with it
  any job half done: on 2026-10-08 a long receipt was read, then cut off
  while its lines were placed, and the phone waited on a `running` job
  forever. The row is still in PostgreSQL, so `resume_unfinished` is the
  startup scan: a server that starts finishes what the last one left.
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

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from grocery_app.api.images import ImageStore
from grocery_app.db.io import receipt_from_dict
from grocery_app.db.models import Job, LineGuess, Receipt

__all__ = ["Extractor", "anthropic_extractor", "configured_extractor", "job_to_dict",
           "resume_job", "resume_unfinished", "run_job", "unfinished_jobs"]

# Derived at extraction time from the lines and the printed total. The receipt
# tables hold what the paper says; these are a reading of it, and there is no
# column for them on purpose. The first guesses are stored, but apart
# (`LineGuess`).
DERIVED_KEYS = ("computed_total", "reconciled", "first_guesses")

# A job in one of these was started and has not said how it ended.
UNFINISHED = ("queued", "running")


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
READERS = ("api", "claude-code", "gemini")


def configured_extractor(reader: str | None = None) -> Extractor:
    """The extractor `GROCERY_READER` names: `api` (the default), `claude-code`
    or `gemini`.

    `claude-code` reads through `claude -p` on the subscription, for a server
    running where `claude` is logged in. It is measurably less accurate than
    the API (docs/designs/catalog-growth.md, step 6), so it is a choice, not
    a fallback: a server whose API calls fail says so rather than quietly
    reading worse. `gemini` reads through Google's API, paid per photo: the
    reader for a server, where neither of the others is available.
    """
    import os

    reader = reader or os.environ.get(READER_ENV, "api")
    if reader not in READERS:
        raise ValueError(f"{READER_ENV}={reader!r}: expected one of {', '.join(READERS)}")
    if reader == "claude-code":
        from grocery_app.extract import claude_code_reader

        return claude_code_reader()
    if reader == "gemini":
        from grocery_app import gemini
        from grocery_app.extract import gemini_reader

        # Checked once, here: a server with no way in to Gemini refuses to
        # start reading rather than failing every upload.
        if not gemini.configured():
            raise ValueError(f"{READER_ENV}=gemini needs GEMINI_VERTEX_PROJECT or GEMINI_API_KEY")
        return gemini_reader()
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
    reading = f"{job.model} {job.prompt_version}"
    for position, guess in enumerate(extraction.receipt.get("first_guesses") or []):
        session.add(LineGuess(receipt_id=receipt.id, position=position, name=guess.get("name"),
                              category=guess.get("category"), reading=reading))


def run_job(session_factory: sessionmaker[Session], image_store: ImageStore,
            extractor: Extractor, job_id: str, matcher: Any | None = None,
            identify: Any | None = None) -> None:
    """Extract one photo and record what happened, whatever happens.

    The receipt is committed, with its first guesses, as soon as the photo is
    read, and each line as soon as it is placed: a client polling the job sees
    `receipt_id` while the job still runs, and can show the receipt filling in
    rather than wait minutes for all of it.

    With a `matcher` (`api.matching.line_matcher`), the lines the memory cannot
    place are matched before the job is `done`, so a client polling the job
    sees the receipt as it will stay, with its spot checks chosen
    (`api.checks`); with an `identify`
    (`api.matching.line_identifier`), a line the matcher cannot settle is read
    before it becomes a question. A matcher that fails does not fail the
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

        receipt = session.get(Receipt, job.receipt_id)
        if same_paper(session, receipt) is not None:
            receipt.is_duplicate = True
        session.commit()
        _place_lines(session, job_id, matcher, identify)


def same_paper(session: Session, receipt: Receipt) -> Receipt | None:
    """The earlier receipt this one is a second photo of, if any.

    Real use, 2026-10-08: the same GLOBUS receipt photographed twice became two
    receipts, counted twice and spot-checked twice. A till prints the minute,
    so the same shop, day, minute and total is the same paper. Without a
    printed time the lines must read the same as well. The photos differ, so
    their hashes never catch this.
    """
    if receipt.store is None or receipt.date is None or receipt.printed_total is None:
        return None
    earlier = session.scalars(select(Receipt).where(
        Receipt.id != receipt.id, Receipt.is_duplicate.is_(False),
        func.lower(Receipt.store) == receipt.store.lower(), Receipt.date == receipt.date,
        Receipt.printed_total == receipt.printed_total).order_by(Receipt.id))
    names = [line.raw_name for line in receipt.lines]
    for other in earlier:
        if receipt.time and other.time:
            if receipt.time == other.time:
                return other
        elif [line.raw_name for line in other.lines] == names:
            return other
    return None


def _place_lines(session: Session, job_id: str, matcher: Any | None,
                 identify: Any | None) -> None:
    """The second half of a job: its receipt is stored; place the lines, pick
    the spot checks, and say `done`.

    Safe to run again on a receipt that is partly placed: the matcher skips a
    line the memory already places or that already has a question.
    """
    job = session.get(Job, job_id)
    if session.get(Receipt, job.receipt_id).is_duplicate:
        # A second photo of a paper already in the history: nothing to place
        # and nothing to ask, the first one has it all.
        job.status = "done"
        job.finished_at = _now()
        session.commit()
        return
    if matcher is not None:
        from grocery_app.api.matching import match_receipt

        try:
            match_receipt(session, job.receipt_id, matcher, identify,
                          checkpoint=session.commit)
            session.commit()
        except Exception as exc:  # noqa: BLE001 - the receipt stands without matching
            session.rollback()
            job = session.get(Job, job_id)
            job.error = f"matching failed: {type(exc).__name__}: {exc}"

    # Chosen after matching, from what the app placed on its own. A
    # receipt stands without its spot checks.
    from grocery_app.api.checks import pick_checks

    try:
        pick_checks(session, job.receipt_id)
        session.commit()
    except Exception as exc:  # noqa: BLE001 - the receipt stands without checks
        session.rollback()
        job = session.get(Job, job_id)
        failed = f"spot checks failed: {type(exc).__name__}: {exc}"
        job.error = f"{job.error}; {failed}" if job.error else failed

    job.status = "done"
    job.finished_at = _now()
    session.commit()


def unfinished_jobs(session_factory: sessionmaker[Session]) -> list[str]:
    """The jobs a stopped server left behind, oldest first."""
    with session_factory() as session:
        return [str(job_id) for job_id in session.scalars(
            select(Job.id).where(Job.status.in_(UNFINISHED)).order_by(Job.created_at))]


def resume_job(session_factory: sessionmaker[Session], image_store: ImageStore,
               extractor: Extractor, job_id: str, matcher: Any | None = None,
               identify: Any | None = None) -> None:
    """Finish a job from the step where it stopped.

    A job that has its receipt only needs its lines placed: the photo is not
    read again. A job without one is read from the start, which pays for one
    more reading if the process stopped between the model's answer and the
    receipt being stored; that window is a second wide.
    """
    with session_factory() as session:
        job = session.get(Job, job_id)
        if job is None or job.status not in UNFINISHED:
            return
        if job.receipt_id is not None:
            _place_lines(session, job_id, matcher, identify)
            return
        job.status = "queued"
        session.commit()
    run_job(session_factory, image_store, extractor, job_id, matcher, identify)


def resume_unfinished(session_factory: sessionmaker[Session], image_store: ImageStore,
                      extractor: Extractor, matcher: Any | None = None,
                      identify: Any | None = None) -> list[str]:
    """Finish every job a stopped server left behind; returns their ids.

    Only one server may run this: two would place the same lines twice. Cloud
    Run runs one instance (`--max-instances 1`), and during a deploy the old
    one is stopped within ten seconds of the new one starting, so the caller
    waits longer than that first (`create_app(resume_after=...)`).
    """
    ids = unfinished_jobs(session_factory)
    for job_id in ids:
        resume_job(session_factory, image_store, extractor, job_id, matcher, identify)
    return ids
