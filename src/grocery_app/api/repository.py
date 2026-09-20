"""Where the API's data comes from.

`Repository` is the seam between the routes and storage. Today the only
implementation reads the JSON artifacts the CLI writes; the planned one reads
PostgreSQL. Routes depend on the protocol, tests pass whatever they like.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from grocery_app.api.jobs import job_to_dict
from grocery_app.db.io import load_normalizer_inputs
from grocery_app.db.models import Job
from grocery_app.db.session import database_url, make_engine, make_session_factory
from grocery_app.normalizer import assemble_purchases

DEFAULT_PURCHASES = "data/purchases.json"


class Repository(Protocol):
    def purchases(self) -> dict[str, Any]:
        """The purchases.json document (contract 2), as a plain dict."""
        ...


@runtime_checkable
class JobRepository(Protocol):
    """A repository that can also accept a photo and track its extraction.

    Reading and writing are separate protocols because `JsonRepository` can
    honestly do one and not the other. A job is runtime state with a lifecycle;
    keeping it in a JSON file would be a second, worse database. So the write
    routes are served only by a repository that satisfies this, and a
    file-backed server says 503 rather than pretending.
    """

    session_factory: sessionmaker[Session]

    def create_job(self, image_sha256: str, original_filename: str | None) -> dict[str, Any]:
        ...

    def job(self, job_id: str) -> dict[str, Any] | None:
        ...

    def job_for_image(self, image_sha256: str) -> dict[str, Any] | None:
        ...


class JsonRepository:
    """Serves the `purchases.json` the CLI wrote.

    The file is read on every call so a `grocery-app purchases` run shows up
    without a restart. At the sizes involved (hundreds of lines) that costs
    nothing; caching is a later concern and belongs behind this same class.
    """

    def __init__(self, purchases_path: str | Path) -> None:
        self.purchases_path = Path(purchases_path)

    def purchases(self) -> dict[str, Any]:
        return json.loads(self.purchases_path.read_text(encoding="utf-8"))


class InMemoryRepository:
    """Holds one document; for tests and for serving a freshly built history."""

    def __init__(self, purchases_doc: dict[str, Any]) -> None:
        self._purchases = purchases_doc

    def purchases(self) -> dict[str, Any]:
        return self._purchases


class PostgresRepository:
    """Serves the history from the tables in `grocery_app.db`.

    Purchases are derived on every call by the same normalizer the CLI runs,
    from receipts, products, resolutions and the shopper's line answers.
    They are never stored: a stored copy would go stale the moment a
    resolution is confirmed.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def purchases(self) -> dict[str, Any]:
        with self.session_factory() as session:
            return assemble_purchases(**load_normalizer_inputs(session))

    def create_job(self, image_sha256: str,
                   original_filename: str | None = None) -> dict[str, Any]:
        """Write the job and commit it, before any work is scheduled.

        A queue forgets an item once a worker takes it, and the queue here is
        an in-process list that dies with the process. Scheduling work that no
        committed row describes would leave nothing to poll and nothing to
        recover.
        """
        with self.session_factory() as session:
            job = Job(image_sha256=image_sha256, original_filename=original_filename)
            session.add(job)
            session.commit()
            return job_to_dict(job)

    def job(self, job_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            return job_to_dict(job) if job else None

    def job_for_image(self, image_sha256: str) -> dict[str, Any] | None:
        """The newest job for these exact bytes, unless it failed.

        This is what stops one photo being paid for twice. A failed job is not
        returned, so re-uploading after a timeout retries rather than handing
        back a dead job id; re-reading a photo under a new prompt version is
        deliberate work and is not blocked here either.
        """
        with self.session_factory() as session:
            job = session.scalars(
                select(Job).where(Job.image_sha256 == image_sha256)
                .order_by(Job.created_at.desc(), Job.id)
            ).first()
            if job is None or job.status == "failed":
                return None
            return job_to_dict(job)


def default_repository(purchases_path: str | Path | None = None) -> Repository:
    """PostgreSQL when `DATABASE_URL` is set, else the JSON file.

    The file defaults to `GROCERY_PURCHASES`, then data/purchases.json.
    """
    url = database_url()
    if url:
        return PostgresRepository(make_session_factory(make_engine(url)))
    return JsonRepository(purchases_path or os.environ.get("GROCERY_PURCHASES", DEFAULT_PURCHASES))
