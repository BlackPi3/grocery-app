"""Migrations that change data, run against real rows.

Only migrations that rewrite existing rows are here; the schema of every
migration is exercised by the `engine` fixture going up and down.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.conftest import DATABASE_URL as URL

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")


def test_0011_makes_one_list_of_the_range_and_the_variant():
    """2026-10-09: the live catalog had ranges and comma-joined variants in two
    columns. The range comes first, then the variant split at its commas;
    empty parts and empty columns leave nothing behind; going down joins
    the list back into the variant."""
    from grocery_app.db.migrate import downgrade, upgrade
    from grocery_app.db.session import make_engine

    downgrade(URL)
    upgrade(URL, "0010")
    engine = make_engine(URL)
    try:
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO products (id, name, brand, product_line, variant, eans, open_questions)
                VALUES ('p-0001', 'Magnesium', 'Muster', 'system', '400 mg, Citrat,', '{}', '{}'),
                       ('p-0002', 'Senf', NULL, NULL, 'mittelscharf', '{}', '{}'),
                       ('p-0003', 'Bananen', NULL, NULL, NULL, '{}', '{}')"""))
        upgrade(URL, "0011")
        with engine.begin() as c:
            rows = dict(c.execute(text("SELECT id, details FROM products ORDER BY id")).all())
        assert rows == {"p-0001": ["system", "400 mg", "Citrat"], "p-0002": ["mittelscharf"],
                        "p-0003": []}

        downgrade(URL, "0010")
        with engine.begin() as c:
            back = dict(c.execute(text("SELECT id, variant FROM products ORDER BY id")).all())
        assert back == {"p-0001": "system, 400 mg, Citrat", "p-0002": "mittelscharf",
                        "p-0003": None}
    finally:
        engine.dispose()
        downgrade(URL)
