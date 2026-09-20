"""The FastAPI application.

`create_app(repository, ...)` is the only constructor. The routes close over
what they are given, so tests hand in an in-memory repository and a fake
extractor, and the server hands in PostgreSQL and a real one; `default_app()`
is the latter, for uvicorn.

The upload path needs three things the read path does not: somewhere to put
the bytes (`image_store`), somewhere to track the work (a repository that
satisfies `JobRepository`), and something that can read a photo
(`extractor`). Any of them missing is a 503 — an honest "this server cannot
do that" — rather than a route that half works.

`extractor` has no default on purpose. A model call costs real money, so
there is no argument a test can forget that would make one happen.
"""

from __future__ import annotations

from datetime import date

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Response, UploadFile

from grocery_app.api.images import (
    ImageStore,
    default_image_store,
    looks_like_an_image,
    sha256_of,
)
from grocery_app.api.jobs import Extractor, anthropic_extractor, run_job
from grocery_app.api.repository import (
    DEFAULT_PURCHASES,
    JobRepository,
    Repository,
    default_repository,
)
from grocery_app.api.schemas import (
    INSIGHTS_CONTRACT_VERSION,
    PURCHASES_CONTRACT_VERSION,
    Health,
    InsightsDocument,
    JobDocument,
    PurchasesDocument,
)
from grocery_app.insights import build_insights

__all__ = ["DEFAULT_PURCHASES", "MAX_UPLOAD_BYTES", "create_app", "default_app"]

# A receipt photo off a phone is a few megabytes. The cap is not a security
# boundary, it is a promise that one request cannot read an arbitrary amount
# into memory before anyone has looked at it.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def create_app(repository: Repository, image_store: ImageStore | None = None,
               extractor: Extractor | None = None) -> FastAPI:
    app = FastAPI(
        title="Grocery App API",
        version="0.1.0",
        summary="Item-level grocery purchase history and the insights computed from it.",
    )

    uploads_available = (isinstance(repository, JobRepository)
                         and image_store is not None and extractor is not None)

    @app.get("/health", response_model=Health)
    def health() -> Health:
        doc = repository.purchases()
        return Health(
            status="ok",
            purchases_contract_version=PURCHASES_CONTRACT_VERSION,
            insights_contract_version=INSIGHTS_CONTRACT_VERSION,
            receipts=doc.get("meta", {}).get("receipts", 0),
            uploads=uploads_available,
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

    def require_uploads() -> JobRepository:
        if not uploads_available:
            raise HTTPException(
                status_code=503,
                detail="this server cannot accept photos: it needs DATABASE_URL, an "
                       "image store and an extractor",
            )
        return repository  # type: ignore[return-value]

    @app.post("/v1/receipts", response_model=JobDocument, status_code=202)
    async def upload_receipt(background: BackgroundTasks, response: Response,
                             file: UploadFile) -> JobDocument:
        """Take a photo, return the job that will read it.

        Extraction takes seconds and costs money, so it does not happen inside
        the request. The response carries a job id to poll: `202` when this
        photo is new and work was scheduled, `200` when it had already been
        read and the existing job is being handed back.
        """
        repo = require_uploads()
        data = await file.read()
        if not data:
            raise HTTPException(status_code=422, detail="file is empty")
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"file is {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES}")
        if not looks_like_an_image(data):
            raise HTTPException(status_code=422, detail="file is not an image this can read")

        digest = sha256_of(data)
        existing = repo.job_for_image(digest)
        if existing is not None:
            # Same bytes, same hash: already paid for. The length check is a
            # guard against a bug in this code (hashing the wrong buffer, a
            # short read), not against sha256 itself.
            held = image_store.size(digest)
            if held is not None and held != len(data):
                raise HTTPException(
                    status_code=500,
                    detail=f"stored image for {digest} is {held} bytes, upload is {len(data)}")
            response.status_code = 200  # nothing was created; this is the job you already have
            return JobDocument.model_validate(existing)

        image_store.put(digest, data)
        job = repo.create_job(digest, file.filename)
        # Only now, with the row committed, is there something to poll and
        # something to recover.
        background.add_task(run_job, repo.session_factory, image_store, extractor,
                            job["job_id"])
        return JobDocument.model_validate(job)

    @app.get("/v1/jobs/{job_id}", response_model=JobDocument)
    def job(job_id: str) -> JobDocument:
        repo = require_uploads()
        found = repo.job(job_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"no job {job_id}")
        return JobDocument.model_validate(found)

    return app


def default_app() -> FastAPI:
    """The app `uvicorn --factory grocery_app.api.app:default_app` runs.

    `DATABASE_URL` selects PostgreSQL; otherwise `GROCERY_PURCHASES` names the
    purchases.json to serve. This is the one place the real, paid extractor is
    wired in, and `GROCERY_IMAGES` says where uploaded photos are kept.
    """
    return create_app(default_repository(), default_image_store(), anthropic_extractor())
