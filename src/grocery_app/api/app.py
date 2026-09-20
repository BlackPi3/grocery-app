"""The FastAPI application.

`create_app(repository)` is the only constructor. The routes close over the
repository they are given, so tests hand in an in-memory one and the server
hands in the JSON files; `default_app()` is the latter, for uvicorn.
"""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException, Query

from grocery_app.api.repository import DEFAULT_PURCHASES, Repository, default_repository
from grocery_app.api.schemas import (
    INSIGHTS_CONTRACT_VERSION,
    PURCHASES_CONTRACT_VERSION,
    Health,
    InsightsDocument,
    PurchasesDocument,
)
from grocery_app.insights import build_insights

__all__ = ["DEFAULT_PURCHASES", "create_app", "default_app"]


def create_app(repository: Repository) -> FastAPI:
    app = FastAPI(
        title="Grocery App API",
        version="0.1.0",
        summary="Item-level grocery purchase history and the insights computed from it.",
    )

    @app.get("/health", response_model=Health)
    def health() -> Health:
        doc = repository.purchases()
        return Health(
            status="ok",
            purchases_contract_version=PURCHASES_CONTRACT_VERSION,
            insights_contract_version=INSIGHTS_CONTRACT_VERSION,
            receipts=doc.get("meta", {}).get("receipts", 0),
        )

    # `exclude_unset` is what makes "exactly as the CLI writes it" true: the
    # normalizer omits the product attributes on an unresolved line, and
    # without this the response model would send them as seven explicit nulls.
    # Nulls the document really does carry (unit_price, tax_class) still go out.
    @app.get("/v1/purchases", response_model=PurchasesDocument,
             response_model_exclude_unset=True)
    def purchases() -> PurchasesDocument:
        """The purchases.json contract, exactly as the CLI writes it."""
        return PurchasesDocument.model_validate(repository.purchases())

    @app.get("/v1/insights", response_model=InsightsDocument)
    def insights(
        as_of: str | None = Query(
            default=None,
            description="ISO date the insights are computed as of; "
                        "defaults to the last purchase date",
        ),
    ) -> InsightsDocument:
        """insights.json computed on request from the served history."""
        try:
            as_of_date = date.fromisoformat(as_of) if as_of else None
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail=f"as_of is not an ISO date: {as_of!r}") from exc
        doc = build_insights(repository.purchases(), as_of=as_of_date)
        return InsightsDocument.model_validate(doc)

    return app


def default_app() -> FastAPI:
    """The app `uvicorn --factory grocery_app.api.app:default_app` runs.

    `DATABASE_URL` selects PostgreSQL; otherwise `GROCERY_PURCHASES` names the
    purchases.json to serve.
    """
    return create_app(default_repository())
