"""The public demo (`grocery_app.demo`): a fresh copy on every start, a cap on
paid readings, and no accounts to hand out."""

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


def test_the_demo_shares_the_live_address_and_names_its_own_database(monkeypatch):
    from grocery_app.db.session import database_url

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@/grocery?host=/cloudsql/x")
    monkeypatch.setenv("GROCERY_DATABASE", "grocery_demo")
    from sqlalchemy.engine import make_url

    url = make_url(database_url())
    assert (url.database, url.query["host"], url.password) == ("grocery_demo", "/cloudsql/x", "p")


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


def test_the_demo_reads_only_so_many_photos_a_day(engine, session, tmp_path, monkeypatch):
    monkeypatch.setenv("GROCERY_DEMO_READINGS_PER_DAY", "1")
    client = demo_server(engine, tmp_path)
    first = client.post("/v1/receipts", files={"file": ("a.jpg", a_photo(), "image/jpeg")})
    assert first.status_code == 202
    second = client.post("/v1/receipts",
                         files={"file": ("b.jpg", a_photo("blue"), "image/jpeg")})
    assert second.status_code == 429 and "tomorrow" in second.json()["detail"]


def test_a_guest_cannot_hand_out_accounts_and_the_page_knows_it_is_the_demo(
        engine, session, tmp_path):
    client = demo_server(engine, tmp_path)
    assert client.post("/v1/users", json={"name": "Gast"}).status_code == 403
    assert client.get("/v1/me").json()["demo"] is True


def test_a_demo_start_deletes_the_photos_guests_sent(engine, session, tmp_path):
    from grocery_app.demo import prune_uploads

    repository = PostgresRepository(make_session_factory(engine))
    seeded = repository.create_job("a" * 64, "seed.jpg")["image_sha256"]
    (tmp_path / seeded).write_bytes(b"seed")
    (tmp_path / ("b" * 64)).write_bytes(b"a guest's photo")
    assert prune_uploads(DATABASE_URL, tmp_path) == 1
    assert [p.name for p in tmp_path.iterdir()] == [seeded]
