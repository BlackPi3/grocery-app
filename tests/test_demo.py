"""The public demo (`grocery_app.demo`): a fresh copy on every start, dated
around the visit, no receipts of a guest's own, and no accounts to hand out."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from grocery_app.api.app import create_app
from grocery_app.api.images import DiskImageStore
from grocery_app.api.repository import PostgresRepository
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL
from tests.test_upload import FakeExtractor, a_photo

# The shape of a pg_dump file: psql's own commands, an emptied search path,
# then the data.
SEED = """\\restrict AbC123
SET statement_timeout = 0;
SELECT pg_catalog.set_config('search_path', '', false);
CREATE TABLE public.demo_probe (x integer, name text);
INSERT INTO public.demo_probe VALUES (7, 'Milch 3,5% 1L');
\\unrestrict AbC123
"""


def test_a_demo_reset_never_touches_a_database_not_named_demo(tmp_path):
    import pytest

    from grocery_app.demo import reset

    with pytest.raises(RuntimeError, match="not a demo database"):
        reset("postgresql+psycopg://u:p@/grocery?host=/cloudsql/x", tmp_path / "seed.sql")


def test_a_demo_start_replaces_the_database_with_the_seed(engine, tmp_path):
    from grocery_app.db.migrate import upgrade
    from grocery_app.demo import reset

    seed = tmp_path / "seed.sql"
    seed.write_text(SEED)
    reset(DATABASE_URL, seed)

    tables = set(inspect(engine).get_table_names())
    assert "demo_probe" in tables and "receipts" not in tables, "what a guest added is gone"
    with engine.connect() as connection:
        assert connection.execute(text("SELECT x FROM demo_probe")).scalar() == 7
        connection.execute(text("DROP TABLE demo_probe"))
        connection.commit()
    upgrade(DATABASE_URL)  # as the server does next


def demo_server(engine, tmp_path):
    repository = PostgresRepository(make_session_factory(engine))
    return TestClient(create_app(repository, DiskImageStore(tmp_path), FakeExtractor(),
                                 demo=True))


def test_a_guest_is_told_to_ask_for_an_account_rather_than_send_a_receipt(
        engine, session, tmp_path, monkeypatch):
    monkeypatch.setenv("GROCERY_OWNER_EMAIL", "dev@example.org")
    client = demo_server(engine, tmp_path)
    sent = client.post("/v1/receipts", files={"file": ("a.jpg", a_photo(), "image/jpeg")})
    assert sent.status_code == 403 and "contact the developer" in sent.json()["detail"]
    assert not list(tmp_path.iterdir()), "nothing a guest sent is kept"
    assert client.get("/v1/me").json()["contact"] == "dev@example.org"


def test_the_demo_moves_its_dates_so_the_newest_receipt_is_today(engine, tmp_path):
    from datetime import date

    from grocery_app.db.migrate import upgrade
    from grocery_app.demo import reset

    seed = tmp_path / "seed.sql"
    seed.write_text("""\\restrict AbC123
SELECT pg_catalog.set_config('search_path', '', false);
CREATE TABLE public.receipts (id integer, date date, created_at timestamp with time zone);
INSERT INTO public.receipts VALUES (1, '2026-10-19', '2026-10-19 12:00:00+00');
INSERT INTO public.receipts VALUES (2, '2026-09-30', '2026-10-19 12:00:00+00');
CREATE VIEW public.receipt_days AS SELECT date FROM public.receipts;
""")
    reset(DATABASE_URL, seed, today=date(2026, 11, 2))
    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT date, created_at::date FROM receipts ORDER BY id")).all()
        assert rows == [(date(2026, 11, 2), date(2026, 11, 2)),
                        (date(2026, 10, 14), date(2026, 11, 2))], "14 days moved, every column"
        connection.execute(text("DROP VIEW receipt_days; DROP TABLE receipts"))
        connection.commit()
    upgrade(DATABASE_URL)


def test_a_guest_cannot_hand_out_accounts_and_the_page_knows_it_is_the_demo(
        engine, session, tmp_path):
    client = demo_server(engine, tmp_path)
    assert client.post("/v1/users", json={"name": "Gast"}).status_code == 403
    assert client.get("/v1/inbox/1/file").status_code == 403
    assert client.post("/v1/inbox").status_code == 403
    assert client.get("/v1/me").json()["demo"] is True


def test_a_demo_start_deletes_the_photos_guests_sent(engine, session, tmp_path):
    from grocery_app.demo import prune_uploads

    repository = PostgresRepository(make_session_factory(engine))
    seeded = repository.create_job("a" * 64, "seed.jpg")["image_sha256"]
    (tmp_path / seeded).write_bytes(b"seed")
    (tmp_path / ("b" * 64)).write_bytes(b"a guest's photo")
    assert prune_uploads(DATABASE_URL, tmp_path) == 1
    assert [p.name for p in tmp_path.iterdir()] == [seeded]


def test_an_address_with_escaped_characters_reaches_the_migrations():
    """The demo's address names its socket as `host=%2Fcloudsql...`: the
    migrations must take it as it is (2026-10-12, the demo's first start)."""
    from grocery_app.db.migrate import alembic_config

    url = "postgresql+psycopg://u:p@/grocery_demo?host=%2Fcloudsql%2Fx%3Ay"
    assert alembic_config(url).get_main_option("sqlalchemy.url") == url
