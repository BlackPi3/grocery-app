"""The public demo: the same app, made-up receipts, open to any guest.

Parham, 2026-10-12: a page anyone can poke around in (a recruiter, a
friend), always the latest version, with dummy receipts in it. 2026-10-19: it
is a playground that mirrors the real app, not a second way in: a guest
looks around and answers its questions, but sends no receipt of their own;
the + says to ask the developer for an account. It is a second server
running the same image with `GROCERY_DEMO=1` and its own database, so a
guest never touches a real history, catalog or memory.

- **Fresh on every start.** The server rebuilds its database from
  `demo_seed.sql` before it serves (`reset`). Cloud Run stops an idle server
  after a quiet spell and a deploy starts a new one, so whatever a guest
  changed is gone by the next visit, and every visitor finds the same demo.
- **Always this month.** Every date in the seed moves forward by the days
  since the newest receipt, so that receipt is today's (`move_dates`): the
  month page, "due again" and this month against the usual one show the
  months around the visit, not the week the seed was made.
- **The seed is the real pipeline's output.** `scripts/build_demo_seed.py`
  sends each made-up receipt (`demo/receipts/`) through the upload path a
  phone uses, with only the photo reading replaced by the made-up text: the
  catalog, the questions and the insights are what the app made of them.
  Insights are worked out on every request, so a change to them shows in the
  demo at once; a change to what an upload does needs the seed built again.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, text

ENV_VAR = "GROCERY_DEMO"
SEED = Path(__file__).parent / "demo_seed.sql"
# What the + says in the demo, and what the server answers an upload.
NO_UPLOADS = ("This demo is a playground with made-up receipts. To use the app with "
              "your own receipts, contact the developer to set up an account.")


def is_demo() -> bool:
    return os.environ.get(ENV_VAR, "").strip().lower() in ("1", "true", "yes")


def seed_statements(sql: str) -> str:
    """A `pg_dump` file as one script the driver can run: psql's own
    commands (lines starting with a backslash) are not SQL."""
    return "\n".join(line for line in sql.splitlines() if not line.startswith("\\"))


def reset(url: str, seed: Path = SEED, today: date | None = None) -> None:
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
            connection.execute(text("SET search_path TO public"))
            move_dates(connection, today or date.today())
    finally:  # the dump empties the search path: no connection of it is reused
        engine.dispose()


def move_dates(connection, today: date) -> int:
    """Move every date and time in the database forward by the days from the
    newest receipt to `today`, so the demo's newest receipt is today's and the
    rest keep their distance from it. Every such column, whatever its table,
    so one added later moves too. Returns the days moved."""
    if connection.execute(text("SELECT to_regclass('public.receipts')")).scalar() is None:
        return 0
    newest = connection.execute(text("SELECT max(date) FROM receipts")).scalar()
    days = (today - newest).days if newest else 0
    if days <= 0:
        return 0
    columns = connection.execute(text(
        "SELECT c.table_name, c.column_name, c.data_type FROM information_schema.columns c "
        "JOIN information_schema.tables t USING (table_schema, table_name) "
        "WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE' AND c.data_type "
        "IN ('date', 'timestamp with time zone', 'timestamp without time zone')")).all()
    for table, column, kind in columns:
        step = ":days" if kind == "date" else "make_interval(days => :days)"
        connection.execute(text(f'UPDATE "{table}" SET "{column}" = "{column}" + {step}'),
                           {"days": days})
    return days


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
