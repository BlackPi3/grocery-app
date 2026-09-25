"""Where the API's data comes from.

`Repository` is the seam between the routes and storage. Today the only
implementation reads the JSON artifacts the CLI writes; the planned one reads
PostgreSQL. Routes depend on the protocol, tests pass whatever they like.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from grocery_app import memory
from grocery_app.api.jobs import job_to_dict
from grocery_app.db.io import load_normalizer_inputs, receipt_to_dict
from grocery_app.db.models import Correction, Job, LineResolution, Product, Receipt, Resolution
from grocery_app.db.session import database_url, make_engine, make_session_factory
from grocery_app.normalizer import (
    assemble_purchases,
    never_remembered,
    normalize_receipt,
    spelling_key,
)
from grocery_app.resolver import store_key

DEFAULT_PURCHASES = "data/purchases.json"


class Repository(Protocol):
    def purchases(self) -> dict[str, Any]:
        """The purchases.json document (contract 2), as a plain dict."""
        ...


class NotFound(LookupError):
    """No such receipt, or no such line on it."""


class UnknownProduct(ValueError):
    """A resolution naming a product the catalog does not have."""


class NotAProductLine(ValueError):
    """An answer on a deposit line, which cannot be a product."""


@runtime_checkable
class WriteRepository(Protocol):
    """A repository that can accept a photo and the shopper's corrections.

    Reading and writing are separate protocols because `JsonRepository` can
    honestly do one and not the other. A job is runtime state with a lifecycle
    and a correction is a durable fact about a line; keeping either in a JSON
    file would be a second, worse database. So the write routes are served only
    by a repository that satisfies this, and a file-backed server says 503
    rather than pretending.
    """

    session_factory: sessionmaker[Session]

    def create_job(self, image_sha256: str, original_filename: str | None) -> dict[str, Any]:
        ...

    def job(self, job_id: str) -> dict[str, Any] | None:
        ...

    def job_for_image(self, image_sha256: str) -> dict[str, Any] | None:
        ...

    def receipt(self, receipt_id: int) -> dict[str, Any] | None:
        ...

    def set_line_resolution(self, receipt_id: int, position: int, product_id: str | None,
                            confirmed_by: str | None, basis: str | None) -> dict[str, Any]:
        ...

    def update_receipt(self, receipt_id: int, is_duplicate: bool | None,
                       store: str | None) -> dict[str, Any]:
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

    # --- the shopper's corrections -------------------------------------------

    def _receipt_view(self, session: Session, row: Receipt) -> dict[str, Any]:
        """One receipt as the truth schema holds it, plus the normalizer's
        reading of every line.

        The reading is not stored and not recomputed here: `normalize_receipt`
        is the same function the whole history goes through, so a line's
        `resolution` on this screen is the one the insights will use. The route
        does no joining, per the design rule that a route holding business
        logic is a bug.
        """
        inputs = load_normalizer_inputs(session)
        doc = receipt_to_dict(row)
        records = normalize_receipt(doc, inputs["resolution"], inputs["products"],
                                    inputs["line_resolutions"], inputs["shelf_prices"])
        return {"receipt_id": row.id, "receipt": doc,
                "lines": [{**record, "position": i} for i, record in enumerate(records)]}

    def _get(self, session: Session, receipt_id: int) -> Receipt:
        row = session.get(Receipt, receipt_id)
        if row is None:
            raise NotFound(f"no receipt {receipt_id}")
        return row

    def receipt(self, receipt_id: int) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.get(Receipt, receipt_id)
            return self._receipt_view(session, row) if row else None

    def set_line_resolution(self, receipt_id: int, position: int, product_id: str | None,
                            confirmed_by: str | None = None,
                            basis: str | None = None) -> dict[str, Any]:
        """Record, or withdraw, the shopper's answer for one line.

        This is the most valuable data the project has: the till prints a name
        the catalog cannot always place, and only the person who was there
        knows what it was. The answer is stored against the line's *text* as
        well as its position, so re-extracting the photo later cannot silently
        move it onto a different product.

        Whether the normalizer can act on the answer is a separate question
        answered in `normalize_line`; what is refused here is an answer that
        could never be right — an unknown product, or a deposit line.

        The answer also teaches the memory what the printed name means at this
        store (`memory.learn`), so the next receipt needs no question. A
        machine's answer it overrules is logged in `corrections`. Withdrawing
        an answer takes back the line's answer only; what the name was learned
        to mean stays.
        """
        with self.session_factory() as session:
            row = self._get(session, receipt_id)
            line = next((line for line in row.lines if line.position == position), None)
            if line is None:
                raise NotFound(f"receipt {receipt_id} has no line {position}")

            existing = session.scalars(
                select(LineResolution).where(LineResolution.receipt_id == receipt_id,
                                             LineResolution.position == position)).first()
            if product_id is None:
                if existing is not None:
                    session.delete(existing)
            else:
                if line.type != "product":
                    raise NotAProductLine(
                        f"line {position} is a {line.type} line, not a product")
                if session.get(Product, product_id) is None:
                    raise UnknownProduct(f"no product {product_id}")
                before = self._receipt_view(session, row)["lines"][position]
                answer = existing or LineResolution(receipt_id=receipt_id, position=position)
                answer.raw_name = line.raw_name
                answer.product_id = product_id
                answer.confirmed_by = confirmed_by or "shopper"
                answer.confirmed_at = date.today()
                answer.basis = basis
                session.add(answer)
                self._remember(session, row, line.raw_name, position, product_id,
                               answer.confirmed_by, before)
            session.commit()
            return self._receipt_view(session, self._get(session, receipt_id))

    def _remember(self, session: Session, receipt: Receipt, raw_name: str, position: int,
                  product_id: str, confirmed_by: str, before: dict[str, Any]) -> None:
        """Teach the memory what one answered line says about its printed name."""
        if not receipt.store or never_remembered(receipt.store, raw_name):
            return
        entry = self._memory_entry(session, receipt.store, raw_name)
        held = ({"product_id": entry.product_id, "product_ids": list(entry.product_ids or []),
                 "confirmed_by": entry.confirmed_by} if entry else None)

        overruled = memory.machine_answer(before, held)
        if overruled and overruled != product_id:
            session.add(Correction(receipt_id=receipt.id, position=position,
                                   store=receipt.store, raw_name=raw_name,
                                   machine_how=before["resolution"],
                                   machine_product_id=overruled,
                                   shopper_product_id=product_id))

        learned = memory.learn(held, product_id)
        if learned is None:
            return
        if entry is None:
            entry = Resolution(store=receipt.store, raw_name=raw_name, line_type="product")
            session.add(entry)
        entry.product_id = learned["product_id"]
        entry.product_ids = learned["product_ids"]
        entry.status = "ambiguous_on_receipt" if learned["product_ids"] else None
        entry.confirmed_by = confirmed_by
        entry.confirmed_at = date.today()
        entry.source = "shopper-answer"

    @staticmethod
    def _memory_entry(session: Session, store: str, raw_name: str) -> Resolution | None:
        """The memory's row for this name at this store, found as `lookup` finds it:
        the exact name first, then one spelled the same."""
        rows = [r for r in session.scalars(select(Resolution).where(
                    Resolution.line_type == "product"))
                if store_key(r.store) == store_key(store)]
        exact = [r for r in rows if r.raw_name == raw_name]
        if exact:
            return exact[0]
        alike = [r for r in rows if spelling_key(r.raw_name) == spelling_key(raw_name)]
        return alike[0] if len(alike) == 1 else None

    def update_receipt(self, receipt_id: int, is_duplicate: bool | None = None,
                       store: str | None = None) -> dict[str, Any]:
        """The two header facts a shopper can correct from a phone.

        `is_duplicate` is the answer to the same paper photographed twice: the
        normalizer drops such a receipt from the history entirely, so this is
        not a label, it changes the numbers. `store` is for a photo whose
        header was cropped off, which leaves every line unresolvable because
        resolution is store-scoped.
        """
        with self.session_factory() as session:
            row = self._get(session, receipt_id)
            if is_duplicate is not None:
                row.is_duplicate = is_duplicate
            if store is not None:
                row.store = store
            session.commit()
            return self._receipt_view(session, self._get(session, receipt_id))

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
