"""Engine and session construction from `DATABASE_URL`."""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

ENV_VAR = "DATABASE_URL"


def database_url() -> str | None:
    """The configured URL, or None when the server should fall back to files."""
    return os.environ.get(ENV_VAR) or None


def make_engine(url: str | None = None) -> Engine:
    url = url or database_url()
    if not url:
        raise RuntimeError(f"{ENV_VAR} is not set")
    return create_engine(url, future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
