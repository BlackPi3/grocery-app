"""Engine and session construction from `DATABASE_URL`."""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

ENV_VAR = "DATABASE_URL"


def database_url() -> str | None:
    """The configured URL, or None when the server should fall back to files.

    `GROCERY_DATABASE` names another database on the same server: the demo
    (`grocery_app.demo`) shares the live server's address and login and
    differs only in this, so it needs no secret of its own.
    """
    url = os.environ.get(ENV_VAR) or None
    if url and (name := os.environ.get("GROCERY_DATABASE")):
        from sqlalchemy.engine import make_url

        url = make_url(url).set(database=name).render_as_string(hide_password=False)
    return url


def make_engine(url: str | None = None) -> Engine:
    url = url or database_url()
    if not url:
        raise RuntimeError(f"{ENV_VAR} is not set")
    return create_engine(url, future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
