"""The database layer, against a real PostgreSQL.

Skipped without `DATABASE_URL`; CI provides one through a service container
(SQLite is not a stand-in: jsonb and arrays are used on purpose). The whole
test module runs inside one database, migrated from scratch and torn down.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from grocery_app.db.models import Base, Job, Product, Receipt, ReceiptLine, Resolution
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL as URL

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")


def test_migration_matches_the_models(engine):
    """The hand-written migration and models.py describe the same schema."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], diff


def test_a_receipt_round_trips_with_its_lines(session):
    receipt = Receipt(
        source_image="IMG_1.jpeg", transcribed_by="hand", store="Musterladen",
        date=date(2026, 1, 5), time="10:00", currency="EUR",
        printed_total=Decimal("3.09"), tax_buckets={"7%": 0.20},  # plain JSON, as in the files
        lines=[
            ReceiptLine(position=0, type="product", raw_name="MU Milch 1,5%", qty=1,
                        gross=Decimal("1.09"), discount=Decimal("0"), net=Decimal("1.09"),
                        tax_class="A"),
            ReceiptLine(position=1, type="deposit", raw_name="Pfand", qty=1,
                        gross=Decimal("0.25"), discount=Decimal("0"), net=Decimal("0.25"),
                        tax_class="B"),
        ],
    )
    session.add(receipt)
    session.commit()

    loaded = session.scalars(select(Receipt).where(Receipt.source_image == "IMG_1.jpeg")).one()
    assert [line.raw_name for line in loaded.lines] == ["MU Milch 1,5%", "Pfand"]
    assert loaded.lines[0].net == Decimal("1.09")
    assert loaded.lines[0].tax_class == "A", "as printed, never a rate"
    assert loaded.is_duplicate is False


def test_a_receipt_line_cannot_carry_a_product_id():
    """The rule from docs/data-layout.md: a receipt says what was printed,
    never which catalog entry it means. Checked on the table, which is what
    the migration creates, rather than on the class."""
    columns = set(ReceiptLine.__table__.columns.keys())
    assert "product_id" not in columns, "resolution is a join, not a column"
    assert "tax_rate" not in columns, "the rate is the normalizer's reading, not truth"
    assert "tax_class" in columns


def test_resolution_holds_a_product_or_a_family(session):
    session.add_all([
        Product(id="p-0001", name="Milch 1,5%", brand="Muster"),
        Product(id="p-0002", name="Chiasamen 0,5 kg", brand="Muster"),
        Product(id="p-0003", name="Chiasamen 0,2 kg", brand="Muster"),
    ])
    session.add_all([
        Resolution(store="Musterladen", raw_name="MU Milch 1,5%", line_type="product",
                   product_id="p-0001", confirmed_by="test", confirmed_at=date(2026, 1, 1)),
        Resolution(store="Musterladen", raw_name="MU Chia", line_type="product",
                   product_id=None, product_ids=["p-0002", "p-0003"],
                   status="ambiguous_on_receipt"),
        Resolution(store="Musterladen", raw_name="Pfand", line_type="deposit"),
    ])
    session.commit()

    rows = {r.raw_name: r for r in session.scalars(select(Resolution))}
    assert rows["MU Milch 1,5%"].product_id == "p-0001"
    assert rows["MU Chia"].product_ids == ["p-0002", "p-0003"]
    assert rows["Pfand"].product_id is None and rows["Pfand"].product_ids == []


def test_the_same_text_at_the_same_store_resolves_once(session):
    from sqlalchemy.exc import IntegrityError

    session.add(Product(id="p-0001", name="Milch"))
    session.add(Resolution(store="Musterladen", raw_name="X", line_type="product",
                           product_id="p-0001"))
    session.commit()
    session.add(Resolution(store="Musterladen", raw_name="X", line_type="product",
                           product_id="p-0001"))
    with pytest.raises(IntegrityError):
        session.commit()


# --- extraction jobs ----------------------------------------------------------


def test_a_job_starts_queued_and_knows_nothing_yet(session):
    job = Job(image_sha256="a" * 64, original_filename="image.jpg")
    session.add(job)
    session.commit()
    session.expire_all()  # the factory keeps objects alive past commit; reload

    loaded = session.get(Job, job.id)
    assert loaded.status == "queued"
    assert loaded.created_at is not None, "written by the database, not the caller"
    assert (loaded.started_at, loaded.finished_at) == (None, None)
    assert loaded.receipt_id is None and loaded.cost_usd is None


def test_a_finished_job_records_the_receipt_and_what_it_cost(session):
    """The fields are the .meta.json sidecar `extract` writes, in a table."""
    receipt = Receipt(source_image="IMG_1.jpeg", transcribed_by="llm",
                      image_sha256="b" * 64, store="Musterladen")
    job = Job(image_sha256="b" * 64, status="running")
    session.add_all([receipt, job])
    session.commit()

    job.receipt = receipt
    job.status = "done"
    job.model = "test-model"
    job.prompt_version = "v1"
    job.request_id = "req_test_1"
    job.usage = {"input_tokens": 1500, "output_tokens": 900}
    job.cost_usd = Decimal("0.03102")
    job.finished_at = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    session.commit()
    session.expire_all()

    loaded = session.get(Job, job.id)
    assert loaded.receipt.source_image == "IMG_1.jpeg"
    assert loaded.cost_usd == Decimal("0.03102"), "cents of a cent, not rounded to money"
    assert loaded.usage["input_tokens"] == 1500
    assert loaded.receipt.transcribed_by == "llm", "a model reading is never truth"


def test_an_earlier_job_for_the_same_photo_is_findable(session):
    """The dedup check before spending money: same bytes, same hash, found."""
    done = Job(image_sha256="c" * 64, status="done", cost_usd=Decimal("0.03"))
    session.add_all([done, Job(image_sha256="d" * 64, status="done")])
    session.commit()
    session.expire_all()

    found = session.scalars(select(Job).where(Job.image_sha256 == "c" * 64)).all()
    assert [j.id for j in found] == [done.id]


def test_one_photo_may_be_extracted_again_under_a_new_prompt(session):
    """So the hash is indexed and not unique: re-reading a photo with a better
    prompt is deliberate work, not a mistake to be blocked by a constraint."""
    session.add_all([
        Job(image_sha256="e" * 64, status="done", prompt_version="v1"),
        Job(image_sha256="e" * 64, status="done", prompt_version="v2"),
    ])
    session.commit()
    assert session.scalar(
        select(func.count()).select_from(Job).where(Job.image_sha256 == "e" * 64)) == 2


def test_a_job_outlives_the_receipt_it_produced(session):
    """What was spent was still spent: deleting a receipt must not erase the
    record of the call that paid for it."""
    receipt = Receipt(source_image="IMG_2.jpeg", transcribed_by="llm")
    session.add(receipt)
    session.commit()
    job = Job(image_sha256="f" * 64, status="done", receipt=receipt,
              cost_usd=Decimal("0.03"))
    session.add(job)
    session.commit()

    session.delete(receipt)
    session.commit()
    session.expire_all()

    loaded = session.get(Job, job.id)
    assert loaded is not None and loaded.receipt_id is None
    assert loaded.cost_usd == Decimal("0.03")


# --- the files, the tables, and the server agree ------------------------------


def _paths(root):
    return (root / "receipts" / "truth", root / "products" / "products.json",
            root / "products" / "resolution.json", root / "receipts" / "line_resolutions.json",
            root / "products")


def test_import_then_serve_matches_the_files(engine, session, data):
    """The phase 1 seam: the same purchases.json from the tables as from the files."""
    from grocery_app.api.repository import PostgresRepository
    from grocery_app.db.io import import_data
    from grocery_app.normalizer import build_purchases

    summary = import_data(session, *_paths(data))
    session.commit()
    assert {k: v["added"] for k, v in summary.items() if isinstance(v, dict)} == {
        "products": 2, "receipts": 2, "resolutions": 2, "listings": 1, "line_resolutions": 1}
    assert summary["line_resolutions_skipped"] == []

    from_files = build_purchases(*_paths(data))
    repository = PostgresRepository(make_session_factory(engine))
    assert repository.purchases() == from_files

    # And the same again over HTTP: the tables, the normalizer and the wire
    # format together must produce the document the files produce.
    from fastapi.testclient import TestClient

    from grocery_app.api.app import create_app

    assert TestClient(create_app(repository)).get("/v1/purchases").json() == from_files


def test_import_twice_updates_and_adds_nothing(session, data):
    from grocery_app.db.io import import_data
    from grocery_app.db.models import LineResolution

    import_data(session, *_paths(data))
    session.commit()
    again = import_data(session, *_paths(data))
    session.commit()
    assert all(v["added"] == 0 for v in again.values() if isinstance(v, dict))
    assert again["receipts"]["updated"] == 2
    assert session.scalar(select(func.count()).select_from(ReceiptLine)) == 6
    assert session.scalar(select(func.count()).select_from(LineResolution)) == 1, \
        "a line answer survives its receipt being re-imported"


def test_export_reproduces_the_files(session, data, tmp_path):
    import json

    from grocery_app.db.io import export_data, import_data
    from grocery_app.normalizer import build_purchases, receipt_files
    from tests.conftest import LINE_RESOLUTIONS, LISTINGS, PRODUCTS, RESOLUTION

    import_data(session, *_paths(data))
    session.commit()
    out = tmp_path / "export"
    counts = export_data(session, out)
    assert counts == {"receipts": 2, "products": 2, "resolutions": 2, "listings": 1,
                      "line_resolutions": 1, "corrections": 0}

    def load(path):
        return json.loads(path.read_text(encoding="utf-8"))

    for original in receipt_files(data / "receipts" / "truth"):
        assert load(out / "receipts" / "truth" / original.name) == load(original)
    assert load(out / "products" / "products.json")["products"] == PRODUCTS["products"]
    by_name = sorted(load(out / "products" / "resolution.json")["entries"],
                     key=lambda e: e["raw_name"])
    assert by_name == sorted(RESOLUTION["entries"], key=lambda e: e["raw_name"])
    assert load(out / "products" / "musterladen" / "listings.json")["listings"] == \
        LISTINGS["listings"]
    assert load(out / "receipts" / "line_resolutions.json")["entries"] == \
        LINE_RESOLUTIONS["entries"]
    assert build_purchases(*_paths(out)) == build_purchases(*_paths(data))


def test_purchases_are_derived_on_every_call_not_stored(engine, session, data):
    """The claim the design rests on: confirming a resolution changes what the
    server says, with no re-import and no rebuild of purchases anywhere."""
    from grocery_app.api.repository import PostgresRepository
    from grocery_app.db.io import import_data

    # Without the line answers, so the only thing that resolves Geheimnis here
    # is the catalog entry this test adds.
    receipts, products, resolution, _, products_dir = _paths(data)
    import_data(session, receipts, products, resolution, data / "absent.json", products_dir)
    session.commit()
    repository = PostgresRepository(make_session_factory(engine))

    def geheimnis():
        return next(p for p in repository.purchases()["purchases"]
                    if p["raw_name"] == "Geheimnis")

    assert geheimnis()["resolved"] is False
    session.add(Resolution(store="Musterladen", raw_name="Geheimnis", line_type="product",
                           product_id="p-0001", confirmed_by="test"))
    session.commit()

    now = geheimnis()
    assert now["resolved"] is True
    assert now["product"] == "Milch 1,5%"


def test_an_answer_for_an_unknown_receipt_is_reported_not_applied(session, data, tmp_path):
    """A line answer naming a receipt that is not there must not vanish
    silently: the shopper would never learn their correction did nothing."""
    import json

    from grocery_app.db.io import import_data

    answers = tmp_path / "line_resolutions.json"
    answers.write_text(json.dumps({"meta": {"schema": 1}, "entries": [
        {"source_image": "IMG_404.jpeg", "line_index": 0, "raw_name": "Geheimnis",
         "product_id": "p-0001", "confirmed_by": "test", "confirmed_at": "2026-02-06",
         "basis": "memory"}]}), encoding="utf-8")
    receipts, products, resolution, _, products_dir = _paths(data)

    summary = import_data(session, receipts, products, resolution, answers, products_dir)
    session.commit()
    assert summary["line_resolutions_skipped"] == ["IMG_404.jpeg"]
    assert summary["line_resolutions"] == {"added": 0, "updated": 0}


def test_the_cli_imports_and_exports_the_same_data(data, tmp_path, monkeypatch, capsys):
    """The developer interface, end to end: files in through the CLI, files
    back out through the CLI, and the pipeline reads the result."""
    import sys

    from grocery_app.cli import main
    from grocery_app.normalizer import build_purchases

    receipts, products, resolution, answers, products_dir = _paths(data)
    out = tmp_path / "exported"
    common = ["--url", URL, "--receipts-dir", str(receipts), "--products", str(products),
              "--resolution", str(resolution), "--line-resolutions", str(answers),
              "--products-dir", str(products_dir)]

    monkeypatch.setattr(sys, "argv", ["grocery-app", "db", "import", *common])
    main()
    assert "receipts:         2 added" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["grocery-app", "db", "export", "--url", URL,
                                      "--out", str(out)])
    main()
    assert build_purchases(*_paths(out)) == build_purchases(*_paths(data))


def test_export_refuses_to_run_without_a_destination(monkeypatch):
    """`--out` is required so an export can never overwrite data/ by default."""
    import sys

    from grocery_app.cli import main

    monkeypatch.setattr(sys, "argv", ["grocery-app", "db", "export", "--url", URL])
    with pytest.raises(SystemExit, match="--out"):
        main()
