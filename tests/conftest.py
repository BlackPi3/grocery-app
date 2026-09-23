"""Shared fixtures: one made-up store (Musterladen), in every file the pipeline reads.

`data` writes the files under a temporary directory in the same layout as
`data/` (see docs/data-layout.md), so a test can run any stage, or the
whole pipeline, without anything real.
"""

import json
import os

import pytest

DATABASE_URL = os.environ.get("DATABASE_URL")

RECEIPTS = [
    {
        "source_image": "IMG_1.jpeg", "transcribed_by": "hand", "store": "Musterladen",
        "date": "2026-01-05", "time": "10:00", "currency": "EUR", "printed_total": 3.09,
        "lines": [
            {"type": "product", "raw_name": "MU Milch 1,5%", "qty": 1,
             "gross": 1.09, "discount": 0.0, "net": 1.09, "tax_class": "A"},
            {"type": "product", "raw_name": "Bananen", "qty": 1, "sold_by_weight": True,
             "weight_kg": 1.0, "unit_price": 1.75, "unit_price_basis": "kg",
             "gross": 1.75, "discount": 0.0, "net": 1.75, "tax_class": "A"},
            {"type": "deposit", "raw_name": "Pfand", "qty": 1,
             "gross": 0.25, "discount": 0.0, "net": 0.25, "tax_class": "B"},
        ],
    },
    {
        "source_image": "IMG_2.jpeg", "transcribed_by": "hand", "store": "musterladen",
        "date": "2026-02-05", "time": "10:00", "currency": "EUR", "printed_total": 3.19,
        "lines": [
            {"type": "product", "raw_name": "MU Milch 1,5%", "qty": 1,
             "gross": 1.19, "discount": 0.0, "net": 1.19, "tax_class": "A"},
            {"type": "product", "raw_name": "Bananen", "qty": 1, "sold_by_weight": True,
             "weight_kg": 1.0, "unit_price": 1.75, "unit_price_basis": "kg",
             "gross": 1.75, "discount": 0.0, "net": 1.75, "tax_class": "A"},
            {"type": "product", "raw_name": "Geheimnis", "qty": 1,
             "gross": 0.25, "discount": 0.0, "net": 0.25, "tax_class": "A"},
        ],
    },
]

PRODUCTS = {
    "meta": {"next_id": 3},
    "products": {
        "p-0001": {"label": "mu-milch", "name": "Milch 1,5%", "brand": "Muster",
                   "product_line": None, "variant": None,
                   "size": {"count": 1, "value": 1.0, "unit": "l"}, "category": "milch",
                   "is_organic": False, "eans": [],
                   "open_questions": [], "provenance": {"attributes": "test", "source": "test"}},
        "p-0002": {"label": "bananen", "name": "Bananen", "brand": None,
                   "product_line": None, "variant": None, "size": None, "category": "gurken",
                   "is_organic": False, "eans": [],
                   "open_questions": [], "provenance": {"attributes": "test", "source": "test"}},
    },
}

RESOLUTION = {
    "meta": {"schema": 1},
    "entries": [
        {"store": "Musterladen", "raw_name": "MU Milch 1,5%", "line_type": "product",
         "product_id": "p-0001", "confirmed_by": "test", "confirmed_at": "2026-01-01",
         "source": "test"},
        {"store": "Musterladen", "raw_name": "Bananen", "line_type": "product",
         "product_id": "p-0002", "confirmed_by": "test", "confirmed_at": "2026-01-01",
         "source": "test"},
    ],
}


LISTINGS = {
    "meta": {"schema": 1, "store": "Musterladen"},
    "listings": {
        "4000000000001": {"product_id": "p-0001", "url": "https://musterladen.example/milch",
                          "prices": [{"date": "2026-01-01", "price": 1.09},
                                     {"date": "2026-02-01", "price": 1.19}]},
    },
}

# An answer for a line the catalog cannot place at all: the shopper says what
# `Geheimnis` was, and the normalizer takes it (see `normalize_line`).
LINE_RESOLUTIONS = {
    "meta": {"schema": 1},
    "entries": [
        {"source_image": "IMG_2.jpeg", "line_index": 2, "raw_name": "Geheimnis",
         "product_id": "p-0001", "confirmed_by": "test", "confirmed_at": "2026-02-06",
         "basis": "memory"},
    ],
}


@pytest.fixture
def data(tmp_path):
    truth = tmp_path / "receipts" / "truth"
    truth.mkdir(parents=True)
    for r in RECEIPTS:
        (truth / r["source_image"].replace(".jpeg", ".json")).write_text(
            json.dumps(r), encoding="utf-8")
    # extract's sidecar must not be mistaken for a receipt
    (truth / "IMG_1.meta.json").write_text(json.dumps({"cost_usd": 0.01}), encoding="utf-8")
    products_dir = tmp_path / "products"
    products_dir.mkdir()
    (products_dir / "products.json").write_text(json.dumps(PRODUCTS), encoding="utf-8")
    (products_dir / "resolution.json").write_text(json.dumps(RESOLUTION), encoding="utf-8")
    store_dir = products_dir / "musterladen"
    store_dir.mkdir()
    (store_dir / "listings.json").write_text(json.dumps(LISTINGS), encoding="utf-8")
    (truth.parent / "line_resolutions.json").write_text(
        json.dumps(LINE_RESOLUTIONS), encoding="utf-8")
    return tmp_path


# --- PostgreSQL, for the tests that need the real thing -----------------------
#
# One database per module, migrated from scratch and torn down. Skipped
# without `DATABASE_URL`; CI provides one through a service container, and
# SQLite is not a stand-in (jsonb and arrays are used on purpose).


@pytest.fixture(scope="module")
def engine():
    from grocery_app.db.migrate import downgrade, upgrade
    from grocery_app.db.session import make_engine

    upgrade(DATABASE_URL)
    engine = make_engine(DATABASE_URL)
    yield engine
    engine.dispose()
    downgrade(DATABASE_URL)


@pytest.fixture
def session(engine):
    from grocery_app.db.models import Base
    from grocery_app.db.session import make_session_factory

    factory = make_session_factory(engine)
    with factory() as s:
        yield s
        s.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            s.execute(table.delete())
        s.commit()
