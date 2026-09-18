"""Where the API's data comes from.

`Repository` is the seam between the routes and storage. Today the only
implementation reads the JSON artifacts the CLI writes; the planned one reads
PostgreSQL. Routes depend on the protocol, tests pass whatever they like.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.orm import Session, sessionmaker

from grocery_app.db.io import load_normalizer_inputs
from grocery_app.db.session import database_url, make_engine, make_session_factory
from grocery_app.normalizer import assemble_purchases

DEFAULT_PURCHASES = "data/purchases.json"


class Repository(Protocol):
    def purchases(self) -> dict[str, Any]:
        """The purchases.json document (contract 2), as a plain dict."""
        ...


class JsonRepository:
    """Serves the `purchases.json` the CLI wrote.

    The file is read on every call so a `grocery-app purchases` run shows up
    without a restart. At the sizes involved (hundreds of lines) that costs
    nothing; caching is a later concern and belongs behind this same class.
    """

    def __init__(self, purchases_path: str | Path) -> None:
        self.purchases_path = Path(purchases_path)

    def purchases(self) -> dict[str, Any]:
        return json.loads(self.purchases_path.read_text(encoding="utf-8"))


class InMemoryRepository:
    """Holds one document; for tests and for serving a freshly built history."""

    def __init__(self, purchases_doc: dict[str, Any]) -> None:
        self._purchases = purchases_doc

    def purchases(self) -> dict[str, Any]:
        return self._purchases


class PostgresRepository:
    """Serves the history from the tables in `grocery_app.db`.

    Purchases are derived on every call by the same normalizer the CLI runs,
    from receipts, products, resolutions and the shopper's line answers.
    They are never stored: a stored copy would go stale the moment a
    resolution is confirmed.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def purchases(self) -> dict[str, Any]:
        with self.session_factory() as session:
            return assemble_purchases(**load_normalizer_inputs(session))


def default_repository(purchases_path: str | Path | None = None) -> Repository:
    """PostgreSQL when `DATABASE_URL` is set, else the JSON file.

    The file defaults to `GROCERY_PURCHASES`, then data/purchases.json.
    """
    url = database_url()
    if url:
        return PostgresRepository(make_session_factory(make_engine(url)))
    return JsonRepository(purchases_path or os.environ.get("GROCERY_PURCHASES", DEFAULT_PURCHASES))
