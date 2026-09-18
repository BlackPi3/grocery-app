"""The database layer, against a real PostgreSQL.

Skipped without `DATABASE_URL`; CI provides one through a service container
(SQLite is not a stand-in: jsonb and arrays are used on purpose). The whole
test module runs inside one database, migrated from scratch and torn down.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from grocery_app.db.models import Base, Product, Receipt, ReceiptLine, Resolution
from grocery_app.db.session import make_engine, make_session_factory

URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")


@pytest.fixture(scope="module")
def engine():
    from grocery_app.db.migrate import downgrade, upgrade

    upgrade(URL)
    engine = make_engine(URL)
    yield engine
    engine.dispose()
    downgrade(URL)


@pytest.fixture
def session(engine):
    factory = make_session_factory(engine)
    with factory() as s:
        yield s
        s.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            s.execute(table.delete())
        s.commit()


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
        printed_total=Decimal("3.09"), tax_buckets={"7%": Decimal("0.20")},
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
    assert not hasattr(ReceiptLine, "product_id"), "resolution is a join, not a column"


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
