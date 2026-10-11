"""Where the API's data comes from.

`Repository` is the seam between the routes and storage. Today the only
implementation reads the JSON artifacts the CLI writes; the planned one reads
PostgreSQL. Routes depend on the protocol, tests pass whatever they like.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from grocery_app import categories, memory
from grocery_app.api.jobs import UNFINISHED, job_to_dict
from grocery_app.api.matching import article_index
from grocery_app.db.io import load_normalizer_inputs, receipt_to_dict, whose
from grocery_app.db.models import (
    Check,
    Correction,
    Job,
    LineGuess,
    LineResolution,
    ModelCall,
    Product,
    Question,
    Receipt,
    Resolution,
    UncountedLine,
    User,
)
from grocery_app.db.session import database_url, make_engine, make_session_factory
from grocery_app.normalizer import (
    assemble_purchases,
    never_remembered,
    normalize_receipt,
    spelling_key,
)
from grocery_app.resolver import store_key

DEFAULT_PURCHASES = "data/purchases.json"

# Long enough to see why a photo was not read, short enough that the Add tab
# does not fill up with old failures nobody can dismiss.
FAILED_JOBS_SHOWN_FOR = timedelta(hours=1)


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


class NoSuchCandidate(ValueError):
    """An answer quoting a candidate number the line's question does not offer."""


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

    def jobs_in_progress(self) -> list[dict[str, Any]]:
        ...

    def receipt(self, receipt_id: int) -> dict[str, Any] | None:
        ...

    def set_line_resolution(self, receipt_id: int, position: int, product_id: str | None,
                            confirmed_by: str | None, basis: str | None,
                            shopper_words: str | None = None) -> dict[str, Any]:
        ...

    def product_for_answer(self, receipt_id: int, position: int, candidate: int | None,
                           new_product: dict[str, Any] | None,
                           identify: Any | None = None) -> str:
        ...

    def questions(self, searched_only: bool = False) -> dict[str, Any]:
        ...

    def checks(self) -> dict[str, Any]:
        ...

    def receipts(self) -> list[dict[str, Any]]:
        ...

    def search_products(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        ...

    def update_receipt(self, receipt_id: int, store: str) -> dict[str, Any]:
        ...

    def set_counted(self, receipt_id: int, position: int, counted: bool) -> dict[str, Any]:
        ...

    def remove_receipt(self, receipt_id: int) -> None:
        ...

    def costs(self) -> dict[str, Any]:
        ...

    def as_user(self, user: dict[str, Any] | None) -> Any:
        ...

    def user_for_password(self, password: str) -> dict[str, Any] | None:
        ...

    def create_user(self, name: str) -> dict[str, Any]:
        ...

    def users(self) -> list[dict[str, Any]]:
        ...

    def claim_inbox(self, is_pdf: Any) -> list[dict[str, Any]]:
        ...

    def job_image(self, job_id: str) -> str | None:
        ...


# The inbox starts the day it was built: older uploads were looked at already.
INBOX_FROM = datetime(2026, 10, 11, tzinfo=UTC)

# When finding a receipt's items was first written down (`spend`, PR of
# 2026-10-11): a receipt uploaded before it has its reading cost only.
FINDING_RECORDED_FROM = datetime(2026, 10, 11, tzinfo=UTC)


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

    def __init__(self, session_factory: sessionmaker[Session],
                 user: dict[str, Any] | None = None) -> None:
        self.session_factory = session_factory
        # Who is asking: a user (`{"id", "name"}`), or the owner when None.
        # Every receipt and job read or written here is that person's only.
        self.user = user

    def as_user(self, user: dict[str, Any] | None) -> PostgresRepository:
        """The same tables, seen by `user` (None: the owner)."""
        return PostgresRepository(self.session_factory, user)

    @property
    def user_id(self) -> int | None:
        return self.user["id"] if self.user else None

    def _my_jobs(self) -> Any:
        return Job.user_id.is_(None) if self.user is None else Job.user_id == self.user_id

    def purchases(self) -> dict[str, Any]:
        with self.session_factory() as session:
            return assemble_purchases(**load_normalizer_inputs(session, self.user_id))

    # --- people ---------------------------------------------------------------

    def create_user(self, name: str) -> dict[str, Any]:
        """A new user and their password, which is shown this once: only its
        hash is kept. A name already taken is refused."""
        name = name.strip()
        if not name:
            raise ValueError("a user needs a name")
        password = new_password()
        with self.session_factory() as session:
            if session.scalar(select(User).where(func.lower(User.name) == name.lower())):
                raise ValueError(f"there is already a user called {name}")
            user = User(name=name, token_sha256=password_hash(password))
            session.add(user)
            session.commit()
            return {"id": user.id, "name": user.name, "password": password}

    def users(self) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            return [{"id": u.id, "name": u.name, "receipts": session.scalar(
                         select(func.count()).select_from(Receipt)
                         .where(Receipt.user_id == u.id))}
                    for u in session.scalars(select(User).order_by(User.id))]

    # --- the developer's inbox ---------------------------------------------------

    def claim_inbox(self, is_pdf: Any) -> list[dict[str, Any]]:
        """Finished uploads a developer should look at, not yet handed over;
        handing them over marks them, so each arrives once (2026-10-11).

        Worth a look: anything another person sent (their shops are new to the
        app), any PDF (a format still being learned), anything that failed or
        was turned away. The owner's ordinary photos are not. Each comes with
        what was read from it, receipt by receipt, to set against the file.
        `is_pdf(sha256)` says whether the stored upload is a PDF.
        """
        with self.session_factory() as session:
            names = {u.id: u.name for u in session.scalars(select(User))}
            found = []
            for job in session.scalars(select(Job).where(
                    Job.dev_seen_at.is_(None), Job.status.in_(("done", "failed")),
                    Job.created_at >= INBOX_FROM).order_by(Job.created_at)):
                pdf = is_pdf(job.image_sha256)
                if not (job.user_id or pdf or job.status == "failed" or job.turned_away):
                    continue
                receipts = session.scalars(select(Receipt).where(
                    Receipt.image_sha256 == job.image_sha256,
                    whose(job.user_id)).order_by(Receipt.id)).all()
                viewer = self.as_user({"id": job.user_id, "name": names.get(job.user_id)}
                                      if job.user_id else None)
                found.append({**job_to_dict(job), "user": names.get(job.user_id),
                              "kind": "pdf" if pdf else "photo",
                              "read": [viewer._receipt_view(session, r) for r in receipts]})
                job.dev_seen_at = datetime.now(UTC)
            session.commit()
            return found

    def job_image(self, job_id: str) -> str | None:
        """The stored upload's hash, for the developer to fetch the file."""
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            return job.image_sha256 if job else None

    def user_for_password(self, password: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            user = session.scalar(select(User).where(
                User.token_sha256 == password_hash(password)))
            return {"id": user.id, "name": user.name} if user else None

    def create_job(self, image_sha256: str,
                   original_filename: str | None = None) -> dict[str, Any]:
        """Write the job and commit it, before any work is scheduled.

        A queue forgets an item once a worker takes it, and the queue here is
        an in-process list that dies with the process. Scheduling work that no
        committed row describes would leave nothing to poll and nothing to
        recover.
        """
        with self.session_factory() as session:
            job = Job(image_sha256=image_sha256, original_filename=original_filename,
                      user_id=self.user_id)
            session.add(job)
            session.commit()
            return job_to_dict(job)

    def job(self, job_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            return job_to_dict(job) if job and job.user_id == self.user_id else None

    def jobs_in_progress(self) -> list[dict[str, Any]]:
        """What every device's Add tab shows: the photos still being read or
        placed, and the ones that failed, were already added or were turned
        away (not a shop receipt) in the last hour, oldest first.

        Kept on the server, not in the browser that sent the photo, so a
        phone and a laptop show the same thing (Parham, 2026-10-08).
        """
        since = datetime.now(UTC) - FAILED_JOBS_SHOWN_FOR
        with self.session_factory() as session:
            jobs = session.scalars(select(Job).where(self._my_jobs()).where(
                Job.status.in_(UNFINISHED)
                | (((Job.status == "failed") | Job.already_added | Job.turned_away.is_not(None))
                   & (Job.finished_at >= since))
            ).order_by(Job.created_at))
            return [job_to_dict(job) for job in jobs]

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
        inputs = load_normalizer_inputs(session, row.user_id)
        doc = receipt_to_dict(row)
        records = normalize_receipt(doc, inputs["resolution"], inputs["products"],
                                    inputs["line_resolutions"], inputs["shelf_prices"],
                                    inputs["authors"], inputs["uncounted"])
        guesses = {g.position: g for g in session.scalars(
            select(LineGuess).where(LineGuess.receipt_id == row.id))}
        lines = []
        for i, record in enumerate(records):
            line = {**record, "position": i}
            guess = guesses.get(i)
            if guess is not None:
                line["first_guess"] = {
                    "name": guess.name, "category": guess.category,
                    "category_path": (list(categories.path(guess.category))
                                      if guess.category in categories.CATEGORIES else None)}
            lines.append(line)
        return {"receipt_id": row.id, "receipt": doc, "lines": lines}

    def _get(self, session: Session, receipt_id: int) -> Receipt:
        row = session.get(Receipt, receipt_id)
        # Another person's receipt is not there, as far as this one can tell.
        if row is None or row.user_id != self.user_id:
            raise NotFound(f"no receipt {receipt_id}")
        return row

    def receipt(self, receipt_id: int) -> dict[str, Any] | None:
        with self.session_factory() as session:
            try:
                return self._receipt_view(session, self._get(session, receipt_id))
            except NotFound:
                return None

    def set_line_resolution(self, receipt_id: int, position: int, product_id: str | None,
                            confirmed_by: str | None = None,
                            basis: str | None = None,
                            shopper_words: str | None = None) -> dict[str, Any]:
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
        machine's answer it overrules is logged in `corrections`.

        Withdrawing an answer takes all of that back (Parham, 2026-10-08: a
        Right pressed by accident had no undo): the memory row goes back to
        what it was, unless something else changed it since, and the
        correction it logged is removed. A new answer over an old one first
        takes the old one back, so the two are never mixed into a family.
        """
        with self.session_factory() as session:
            row = self._get(session, receipt_id)
            line = next((line for line in row.lines if line.position == position), None)
            if line is None:
                raise NotFound(f"receipt {receipt_id} has no line {position}")

            existing = session.scalars(
                select(LineResolution).where(LineResolution.receipt_id == receipt_id,
                                             LineResolution.position == position)).first()
            if product_id is not None:
                if line.type != "product":
                    raise NotAProductLine(
                        f"line {position} is a {line.type} line, not a product")
                if session.get(Product, product_id) is None:
                    raise UnknownProduct(f"no product {product_id}")
            if existing is not None:
                self._take_back(session, row, existing)
                session.flush()
            question = session.scalars(select(Question).where(
                Question.receipt_id == receipt_id, Question.position == position)).first()
            if question is not None:
                question.answered_at = None if product_id is None else datetime.now(UTC)
            if product_id is not None:
                before = self._receipt_view(session, row)["lines"][position]
                answer = LineResolution(receipt_id=receipt_id, position=position)
                answer.raw_name = line.raw_name
                answer.product_id = product_id
                # A user's answer says whose it is, whatever the request claims:
                # that is what the memory weighs it by (`memory.author_kind`).
                answer.confirmed_by = (f"{memory.USER_PREFIX}{self.user['name']}" if self.user
                                       else confirmed_by or "shopper")
                answer.confirmed_at = date.today()
                answer.basis = basis
                answer.shopper_words = shopper_words
                session.add(answer)
                answer.memory_before = self._remember(session, row, line.raw_name, position,
                                                      product_id, answer.confirmed_by, before)
            session.commit()
            return self._receipt_view(session, self._get(session, receipt_id))

    def _remember(self, session: Session, receipt: Receipt, raw_name: str, position: int,
                  product_id: str, confirmed_by: str,
                  before: dict[str, Any]) -> dict[str, Any] | None:
        """Teach the memory what one answered line says about its printed name.
        Returns the memory row as it was (`held`) and what this answer wrote
        (`wrote`), or None when the memory was left alone."""
        if not receipt.store or never_remembered(receipt.store, raw_name):
            return None
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

        if memory.author_kind(confirmed_by) == "user":
            # Her answer stands for her line; what the owner told the memory
            # stands for the name, and the disagreement is kept to look at.
            answer = session.scalar(select(LineResolution).where(
                LineResolution.receipt_id == receipt.id, LineResolution.position == position))
            answer.disagrees_with = memory.disagrees(held, product_id)
        learned = memory.learn(held, product_id, memory.author_kind(confirmed_by))
        if learned is None:
            return None
        snapshot = {"held": None if entry is None else {
                        "product_id": entry.product_id,
                        "product_ids": list(entry.product_ids or []),
                        "status": entry.status, "confirmed_by": entry.confirmed_by,
                        "confirmed_at": entry.confirmed_at and entry.confirmed_at.isoformat(),
                        "source": entry.source},
                    "wrote": learned}
        if entry is None:
            entry = Resolution(store=receipt.store, raw_name=raw_name, line_type="product")
            session.add(entry)
        entry.product_id = learned["product_id"]
        entry.product_ids = learned["product_ids"]
        entry.status = "ambiguous_on_receipt" if learned["product_ids"] else None
        entry.confirmed_by = confirmed_by
        entry.confirmed_at = date.today()
        entry.source = "shopper-answer"
        return snapshot

    def _take_back(self, session: Session, receipt: Receipt, answer: LineResolution) -> None:
        """Remove one line answer and what it taught: its correction, and its
        change to the memory if the memory still holds what it wrote."""
        for logged in session.scalars(select(Correction).where(
                Correction.receipt_id == receipt.id, Correction.position == answer.position,
                Correction.shopper_product_id == answer.product_id)):
            session.delete(logged)
        snapshot = answer.memory_before
        entry = (self._memory_entry(session, receipt.store, answer.raw_name)
                 if snapshot and receipt.store else None)
        if entry is not None and {"product_id": entry.product_id,
                                  "product_ids": list(entry.product_ids or [])} \
                == snapshot["wrote"]:
            held = snapshot["held"]
            if held is None:
                session.delete(entry)
            else:
                entry.product_id = held["product_id"]
                entry.product_ids = held["product_ids"]
                entry.status = held["status"]
                entry.confirmed_by = held["confirmed_by"]
                entry.confirmed_at = (date.fromisoformat(held["confirmed_at"])
                                      if held["confirmed_at"] else None)
                entry.source = held["source"]
        session.delete(answer)

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

    def product_for_answer(self, receipt_id: int, position: int, candidate: int | None,
                           new_product: dict[str, Any] | None,
                           identify: Any | None = None) -> str:
        """The product an answer names by candidate number or in words, made if new.

        A candidate is quoted by its number in the line's question; a shop
        listing the catalog lacks becomes a product, decided by the shopper.
        A description in the shopper's words is read into our format by
        `identify` (`matching.described_product`). Either way the
        product is committed before the answer is recorded, so a refused
        answer can leave a product behind, never an answer without one.
        """
        from grocery_app.api.matching import described_product, product_for

        with self.session_factory() as session:
            row = self._get(session, receipt_id)
            if new_product is not None:
                product_id = described_product(session, receipt_id, position,
                                               new_product["description"], identify)
            else:
                question = session.scalars(select(Question).where(
                    Question.receipt_id == receipt_id, Question.position == position)).first()
                offered = (question.proposal.get("candidates") or []) if question else []
                if candidate is None or not 1 <= candidate <= len(offered):
                    raise NoSuchCandidate(
                        f"line {position} of receipt {receipt_id} offers no candidate "
                        f"{candidate}; it has {len(offered)}")
                inputs = {"index": article_index(session),
                          "products": {p.id: {} for p in session.scalars(select(Product))}}
                decided_by = (f"{memory.USER_PREFIX}{self.user['name']}" if self.user
                              else "shopper")
                product_id = product_for(session, offered[candidate - 1], row.store or "",
                                         inputs, decided_by=decided_by)
            session.commit()
            return product_id

    def questions(self, searched_only: bool = False) -> dict[str, Any]:
        """Every line nothing could place, oldest receipt first.

        Derived, not stored: a line is a question while the normalizer leaves
        it open and the shopper has not answered it, whether or not the matcher
        saw it. The matcher's candidates come along where it did. A family is
        never a question: the version changes no number the app shows.

        `searched_only` holds back every question no web search narrowed down,
        and counts them (`held_back`): nothing reaches the shopper unsearched
        (Parham, 2026-10-02). They are not answered or dropped, only not shown.
        """
        from grocery_app import matcher as matching

        with self.session_factory() as session:
            inputs = load_normalizer_inputs(session, self.user_id)
            proposals = {(q.receipt_id, q.position): q.proposal
                         for q in session.scalars(select(Question))}
            receipts = session.scalars(select(Receipt).where(whose(self.user_id))
                                       .order_by(Receipt.date, Receipt.id)).all()
            questions = []
            held_back = 0
            for receipt in receipts:
                doc = receipt_to_dict(receipt)
                records = normalize_receipt(doc, inputs["resolution"], inputs["products"],
                                            inputs["line_resolutions"], inputs["shelf_prices"],
                                            inputs["authors"], inputs["uncounted"])
                for position, (line, record) in enumerate(zip(doc["lines"], records, strict=True)):
                    # A line the shopper does not count is not worth a question.
                    if record["resolution"] != "none" or record["type"] != "product" \
                            or record.get("not_counted"):
                        continue
                    proposal = proposals.get((receipt.id, position)) or {}
                    if searched_only and not (proposal.get("identity") or {}).get("searched"):
                        held_back += 1
                        continue
                    offered = proposal.get("candidates") or []
                    pick = proposal.get("pick")
                    questions.append({
                        "receipt_id": receipt.id, "position": position, "store": receipt.store,
                        "date": doc.get("date"), "raw_name": line["raw_name"],
                        "paid": matching.paid_price(line),
                        "per_line": never_remembered(receipt.store, line["raw_name"]),
                        "candidates": [{"number": n, **{k: c.get(k) for k in (
                            "name", "brand", "pack_size", "product_id", "article", "url")}}
                            for n, c in enumerate(offered, 1)],
                        "model_pick": offered.index(pick) + 1 if pick in offered else None,
                        "reason": proposal.get("reason"),
                        "unclear": (proposal.get("identity") or {}).get("reason"),
                        "choices": (proposal.get("identity") or {}).get("choices") or [],
                    })
            authors = [r.confirmed_by for r in session.scalars(select(Resolution))]
            matcher_answers, identify_answers = (authors.count("matcher"),
                                                 authors.count("identify"))
            overruled = len(session.scalars(select(Correction)).all())
        return {"meta": {"open": len(questions), "matcher_answers": matcher_answers,
                         "identify_answers": identify_answers,
                         "overruled": overruled, "held_back": held_back},
                "questions": questions}

    def receipts(self) -> list[dict[str, Any]]:
        """Every receipt, newest first, with how far its lines are placed and by whom."""
        with self.session_factory() as session:
            inputs = load_normalizer_inputs(session, self.user_id)
            out = []
            for row in session.scalars(select(Receipt).where(whose(self.user_id))):
                doc = receipt_to_dict(row)
                records = [r for r in normalize_receipt(
                    doc, inputs["resolution"], inputs["products"], inputs["line_resolutions"],
                    inputs["shelf_prices"], inputs["authors"], inputs["uncounted"])
                    if r["type"] == "product"]
                out.append({
                    "receipt_id": row.id, "date": doc.get("date"), "store": row.store,
                    "source_image": row.source_image,
                    "printed_total": doc.get("printed_total"),
                    "product_lines": len(records),
                    "said_by_you": sum(r["said_by"] == "you" for r in records),
                    "said_by_app": sum(r["said_by"] == "app" for r in records),
                    "unplaced": sum(r["said_by"] is None and not r.get("not_counted")
                                    for r in records),
                    "not_counted": sum(bool(r.get("not_counted")) for r in records),
                })
        out.sort(key=lambda r: (r["date"] or "", r["receipt_id"]), reverse=True)
        return out

    def search_products(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Catalog products whose name or brand holds every word of `query`,
        letter case aside, shortest name first: what a shopper picks from
        when correcting a line."""
        words = query.casefold().split()
        if not words:
            return []
        with self.session_factory() as session:
            found = [p for p in session.scalars(select(Product))
                     if all(w in f"{p.name or ''} {p.brand or ''}".casefold() for w in words)]
        found.sort(key=lambda p: (len(p.name or ""), p.name or "", p.id))
        return [{"product_id": p.id, "name": p.name, "brand": p.brand,
                 "details": list(p.details or []),
                 "category_path": (list(categories.path(p.category))
                                   if p.category in categories.CATEGORIES else None)}
                for p in found[:limit]]

    def checks(self) -> dict[str, Any]:
        """Open spot checks, and what the answered ones say (`api.checks`).

        A check is answered when the shopper has answered its line. Its
        outcome is read from that answer: the product the app said is
        `right`, any other is `corrected`. Nothing about it is stored twice.
        """
        from grocery_app import matcher as matching
        from grocery_app.api.checks import says_more_than_print
        from grocery_app.api.pictures import shown
        from grocery_app.normalizer import entry_key

        with self.session_factory() as session:
            answers = {(lr.receipt_id, lr.position): lr.product_id
                       for lr in session.scalars(select(LineResolution))}
            checks = session.scalars(select(Check).join(Receipt, Receipt.id == Check.receipt_id)
                                     .where(whose(self.user_id))).all()
            right = sum(1 for c in checks
                        if answers.get((c.receipt_id, c.position)) == c.app_product_id)
            corrected = sum(1 for c in checks if (c.receipt_id, c.position) in answers) - right
            open_checks = [c for c in checks if (c.receipt_id, c.position) not in answers]

            inputs = load_normalizer_inputs(session, self.user_id)
            views = []
            for check in open_checks:
                receipt = session.get(Receipt, check.receipt_id)
                doc = receipt_to_dict(receipt)
                line = doc["lines"][check.position]
                if (doc["source_image"], check.position, line["raw_name"]) in inputs["uncounted"]:
                    continue  # nor a spot check on a line the shopper does not count
                product = inputs["products"].get(check.app_product_id, {})
                if not says_more_than_print(check.raw_name, product):
                    continue  # picked before 2026-10-10: nothing to ask
                record = normalize_receipt(
                    {**doc, "lines": [line]}, inputs["resolution"], inputs["products"],
                    None, inputs["shelf_prices"], inputs["authors"])[0]
                decided_by = record["resolution"]
                if decided_by in ("exact", "family"):
                    decided_by = inputs["authors"].get(
                        entry_key(inputs["resolution"], receipt.store, line["raw_name"]))
                views.append({
                    "receipt_id": check.receipt_id, "position": check.position,
                    "store": receipt.store, "date": doc.get("date"),
                    "raw_name": check.raw_name, "paid": matching.paid_price(line),
                    "app_product_id": check.app_product_id,
                    "app_product": product.get("name"), "brand": product.get("brand"),
                    "details": list(product.get("details") or []),
                    "sold_as": record.get("sold_as"),
                    "category_path": (list(categories.path(product["category"]))
                                      if product.get("category") in categories.CATEGORIES
                                      else None),
                    "decided_by": decided_by,
                    "picture": (shown(session.get(Product, check.app_product_id).picture)
                                if check.app_product_id in inputs["products"] else None),
                })
        views.sort(key=lambda v: (v["date"] or "", v["receipt_id"], v["position"]))
        answered = right + corrected
        return {"meta": {"open": len(views), "right": right, "corrected": corrected,
                         "error_rate": round(corrected / answered, 3) if answered else None},
                "checks": views}

    def costs(self) -> dict[str, Any]:
        """What the model calls cost, per month and per receipt (`spend`).

        A month is when the money was spent, not when the shopping was: a
        June receipt read in October is October's cost. A receipt's cost is
        its job's calls: reading the photo, and finding what its lines are.
        Finding was first written down on `FINDING_RECORDED_FROM`; an older
        receipt has its reading cost only, and says so.
        """
        from grocery_app import spend

        cost_sum = func.coalesce(func.sum(ModelCall.cost_usd), 0)
        with self.session_factory() as session:
            month = func.to_char(func.timezone("UTC", ModelCall.at), "YYYY-MM")
            months: dict[str, dict[str, Any]] = {}
            for key, purpose, cost, searches in session.execute(
                    select(month, ModelCall.purpose, func.sum(ModelCall.cost_usd),
                           func.sum(ModelCall.searches)).group_by(month, ModelCall.purpose)):
                entry = months.setdefault(key, {
                    "month": key, "total_usd": 0.0, "searches": 0,
                    **{f"{p}_usd": 0.0 for p in spend.PURPOSES}})
                entry[f"{purpose}_usd"] = round(entry.get(f"{purpose}_usd", 0.0)
                                                + float(cost or 0), 5)
                entry["total_usd"] = round(entry["total_usd"] + float(cost or 0), 5)
                entry["searches"] += int(searches or 0)

            receipts = []
            for job, purpose, cost, searches in session.execute(
                    select(Job, ModelCall.purpose, cost_sum, func.sum(ModelCall.searches))
                    .join(ModelCall, ModelCall.job_id == Job.id)
                    .where(Job.receipt_id.is_not(None))
                    .group_by(Job.id, ModelCall.purpose)):
                found = next((r for r in receipts if r["receipt_id"] == job.receipt_id), None)
                if found is None:
                    found = {"receipt_id": job.receipt_id,
                             "month": job.created_at.astimezone(UTC).strftime("%Y-%m"),
                             "reading_usd": 0.0, "finding_usd": 0.0, "searches": 0,
                             "finding_recorded": job.created_at >= FINDING_RECORDED_FROM}
                    receipts.append(found)
                if purpose in ("reading", "finding"):
                    found[f"{purpose}_usd"] = round(found[f"{purpose}_usd"] + float(cost), 5)
                found["searches"] += int(searches or 0)
            for found in receipts:
                found["total_usd"] = round(found["reading_usd"] + found["finding_usd"], 5)

            for entry in months.values():
                whole = [r for r in receipts
                         if r["month"] == entry["month"] and r["finding_recorded"]]
                entry["receipts"] = sum(1 for r in receipts if r["month"] == entry["month"])
                entry["per_receipt_usd"] = (round(sum(r["total_usd"] for r in whole)
                                                  / len(whole), 5) if whole else None)
            return {"months": sorted(months.values(), key=lambda m: m["month"], reverse=True),
                    "receipts": sorted(receipts, key=lambda r: r["receipt_id"]),
                    "free_searches_per_month": spend.FREE_SEARCHES_PER_MONTH,
                    "finding_recorded_from": FINDING_RECORDED_FROM.date().isoformat()}

    def remove_receipt(self, receipt_id: int) -> None:
        """Take a receipt out of the history, for whatever reason the shopper
        has (Parham, 2026-10-11): a photo that should not have been added, a
        bill that is not shopping.

        Its lines, the answers given on them, its spot checks and questions go
        with it (the tables cascade). What those answers taught the memory
        about a printed name stays: it is about the name, not this paper. The
        job that read it keeps its cost, with no receipt. The photo stays in
        the image store, so adding it again reads it again (`job_for_image`).
        """
        with self.session_factory() as session:
            self._get(session, receipt_id)
            session.execute(delete(Receipt).where(Receipt.id == receipt_id))
            session.commit()

    def update_receipt(self, receipt_id: int, store: str) -> dict[str, Any]:
        """The header fact a shopper can correct from a phone: the store, for a
        photo whose header was cropped off, which leaves every line
        unresolvable because resolution is store-scoped. (A second photo of a
        receipt is not kept at all: `api.jobs.same_paper`.)
        """
        with self.session_factory() as session:
            row = self._get(session, receipt_id)
            row.store = store
            session.commit()
            return self._receipt_view(session, self._get(session, receipt_id))

    def set_counted(self, receipt_id: int, position: int, counted: bool) -> dict[str, Any]:
        """Leave one line out of the shopper's numbers, or count it again.

        One tap and no reason (Parham, 2026-10-05: the user scans, rarely
        taps, never types). The mark is bound to the line's text, like a line
        answer. It also takes the line out of the questions and spot checks:
        what the shopper does not count is not worth asking about.
        """
        with self.session_factory() as session:
            row = self._get(session, receipt_id)
            line = next((x for x in row.lines if x.position == position), None)
            if line is None:
                raise NotFound(f"receipt {receipt_id} has no line {position}")
            existing = session.scalar(select(UncountedLine).where(
                UncountedLine.receipt_id == receipt_id, UncountedLine.position == position))
            if counted and existing is not None:
                session.delete(existing)
            elif not counted and existing is None:
                session.add(UncountedLine(receipt_id=receipt_id, position=position,
                                          raw_name=line.raw_name))
            elif not counted:
                existing.raw_name = line.raw_name
            session.commit()
            return self._receipt_view(session, self._get(session, receipt_id))

    def job_for_image(self, image_sha256: str) -> dict[str, Any] | None:
        """The newest job for these exact bytes, unless it failed.

        This is what stops one photo being paid for twice. A failed job is not
        returned, so re-uploading after a timeout retries rather than handing
        back a dead job id; nor is one whose receipt the shopper removed, so
        adding it again brings it back. Re-reading a photo under a new prompt
        version is deliberate work and is not blocked here either.
        """
        with self.session_factory() as session:
            job = session.scalars(
                select(Job).where(Job.image_sha256 == image_sha256, self._my_jobs())
                .order_by(Job.created_at.desc(), Job.id)
            ).first()
            if job is None or job.status == "failed":
                return None
            if job.status == "done" and job.receipt_id is None and job.turned_away is None:
                return None  # its receipt was removed
            return job_to_dict(job)


def new_password() -> str:
    """Four groups of four, from letters and digits nobody misreads: typed
    once on a phone, then kept there."""
    import secrets

    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4))


def password_hash(password: str) -> str:
    import hashlib

    return hashlib.sha256(password.strip().encode()).hexdigest()


def default_repository(purchases_path: str | Path | None = None) -> Repository:
    """PostgreSQL when `DATABASE_URL` is set, else the JSON file.

    The file defaults to `GROCERY_PURCHASES`, then data/purchases.json.
    """
    url = database_url()
    if url:
        return PostgresRepository(make_session_factory(make_engine(url)))
    return JsonRepository(purchases_path or os.environ.get("GROCERY_PURCHASES", DEFAULT_PURCHASES))
