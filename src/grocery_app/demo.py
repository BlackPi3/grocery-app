"""The public demo: the same app, made-up receipts, open to any guest.

Parham, 2026-10-12: a page anyone can poke around in (a recruiter, a
friend), always the latest version, with dummy receipts in it; guests may
scan and save receipts of their own, just for fun. It is a second server
running the same image with `GROCERY_DEMO=1` and its own database, so a
guest never touches a real history, catalog or memory.

- **Fresh on every start.** The server rebuilds its database from
  `demo_seed.sql` before it serves (`reset`). Cloud Run stops an idle server
  after a quiet spell and a deploy starts a new one, so whatever a guest
  added is gone by the next visit, and every visitor finds the same demo.
  A guest's photos go too (`prune_uploads`): nothing they sent is kept.
- **The seed is the real pipeline's output.** `scripts/build_demo_seed.py`
  sends each made-up receipt (`demo/receipts/`) through the upload path a
  phone uses, with only the photo reading replaced by the made-up text: the
  catalog, the questions and the insights are what the app made of them.
- **A daily cap on readings.** A guest's photo is read by the paid model
  like anyone's; `READINGS_PER_DAY` keeps a public link from running up a
  bill.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

ENV_VAR = "GROCERY_DEMO"
SEED = Path(__file__).parent / "demo_seed.sql"
# Ten photos a day at about 2.4 cents each: at most some 7 euros a month.
READINGS_PER_DAY = 10


def is_demo() -> bool:
    return os.environ.get(ENV_VAR, "").strip().lower() in ("1", "true", "yes")


def readings_per_day() -> int:
    return int(os.environ.get("GROCERY_DEMO_READINGS_PER_DAY", READINGS_PER_DAY))


def readings_today(session: Session) -> int:
    """Photos sent today (UTC), whatever became of them: each was paid for."""
    from grocery_app.db.models import Job

    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return session.scalar(select(func.count()).select_from(Job)
                          .where(Job.created_at >= midnight)) or 0


def seed_statements(sql: str) -> str:
    """A `pg_dump` file as one script the driver can run: psql's own
    commands (lines starting with a backslash) are not SQL."""
    return "\n".join(line for line in sql.splitlines() if not line.startswith("\\"))


def reset(url: str, seed: Path = SEED) -> None:
    """Empty the database and load the seed; the caller migrates after.

    Drops what this database user owns in `public` rather than the schema
    itself: on a managed database the schema belongs to someone else.

    Refuses any database whose name says neither demo nor test: this empties
    a database, and a missing setting must never make that the real history.
    """
    from sqlalchemy.engine import make_url

    name = make_url(url).database or ""
    if "demo" not in name and "test" not in name:
        raise RuntimeError(f"refusing to reset {name!r}: not a demo database")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            for kind, query in (
                    ("TABLE", "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                              "AND tableowner = current_user"),
                    ("SEQUENCE", "SELECT sequencename FROM pg_sequences "
                                 "WHERE schemaname = 'public' AND sequenceowner = current_user")):
                for (name,) in connection.execute(text(query)).all():
                    connection.execute(text(f'DROP {kind} IF EXISTS public."{name}" CASCADE'))
            # Straight to the driver with no parameters, so a `%` in the data
            # ("Milch 3,5%") is text, not a placeholder.
            connection.connection.dbapi_connection.cursor().execute(
                seed_statements(seed.read_text(encoding="utf-8")))
    finally:  # the dump empties the search path: no connection of it is reused
        engine.dispose()


def seeded_photos(seed: Path | None = None) -> frozenset[str]:
    """The photos the seed's receipts were read from, by hash: the only
    receipt photos the demo shows (`GET /v1/receipts/{id}/photo`). In the
    demo every guest is the owner, so a photo a guest sent would be anyone's
    to see; the made-up receipts' drawings are no one's."""
    found: set[str] = set()
    for line in (seed or SEED).read_text(encoding="utf-8").splitlines():
        if line.startswith("INSERT INTO public.receipts VALUES"):
            found.update(re.findall(r"'([0-9a-f]{64})'", line))
    return frozenset(found)


def prune_uploads(url: str, root: Path) -> int:
    """Delete every uploaded file the (fresh) database has no job for: the
    photos guests sent since the last start. Returns how many went."""
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            keep = set(connection.execute(text("SELECT image_sha256 FROM jobs")).scalars())
    finally:
        engine.dispose()
    gone = 0
    for path in root.glob("*") if root.is_dir() else ():
        if path.is_file() and path.name not in keep:
            path.unlink()
            gone += 1
    return gone
