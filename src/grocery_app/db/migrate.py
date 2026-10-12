"""Run Alembic from code, so `grocery-app db upgrade` and the tests share one path."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    # Alembic's config treats `%` as interpolation: an address with an
    # escaped character in it (`host=%2Fcloudsql...`) stopped the demo from
    # starting (2026-10-12), and the error printed the address, password and all.
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade(url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str, revision: str = "base") -> None:
    command.downgrade(alembic_config(url), revision)
