"""The FastAPI application.

`create_app(repository, ...)` is the only constructor. The routes close over
what they are given, so tests hand in an in-memory repository and a fake
extractor, and the server hands in PostgreSQL and a real one; `default_app()`
is the latter, for uvicorn.

The upload path needs three things the read path does not: somewhere to put
the bytes (`image_store`), somewhere to track the work (a repository that
satisfies `WriteRepository`), and something that can read a photo
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
from grocery_app.api.jobs import Extractor, configured_extractor, run_job
from grocery_app.api.matching import LineMatcher, line_matcher
from grocery_app.api.repository import (
    DEFAULT_PURCHASES,
    NoSuchCandidate,
    NotAProductLine,
    NotFound,
    Repository,
    UnknownProduct,
    WriteRepository,
    default_repository,
)
from grocery_app.api.schemas import (
    INSIGHTS_CONTRACT_VERSION,
    PURCHASES_CONTRACT_VERSION,
    Health,
    InsightsDocument,
    JobDocument,
    LineResolutionRequest,
    PurchasesDocument,
    QuestionsDocument,
    ReceiptDocument,
    ReceiptPatch,
)
from grocery_app.insights import build_insights

__all__ = ["DEFAULT_PURCHASES", "MAX_UPLOAD_BYTES", "create_app", "default_app"]

# A receipt photo off a phone is a few megabytes. The cap is not a security
# boundary, it is a promise that one request cannot read an arbitrary amount
# into memory before anyone has looked at it.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def create_app(repository: Repository, image_store: ImageStore | None = None,
               extractor: Extractor | None = None,
               matcher: LineMatcher | None = None) -> FastAPI:
    app = FastAPI(
        title="Grocery App API",
        version="0.1.0",
        summary="Item-level grocery purchase history and the insights computed from it.",
    )

    # Corrections need a database. A photo needs that and somewhere to put the
    # bytes and something that can read them, so uploads are the stricter test.
    writes_available = isinstance(repository, WriteRepository)
    uploads_available = (writes_available
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
            writes=writes_available,
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

    def require_uploads() -> WriteRepository:
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
                            job["job_id"], matcher)
        return JobDocument.model_validate(job)

    @app.get("/v1/jobs/{job_id}", response_model=JobDocument)
    def job(job_id: str) -> JobDocument:
        repo = require_uploads()
        found = repo.job(job_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"no job {job_id}")
        return JobDocument.model_validate(found)

    def require_writes() -> WriteRepository:
        if not writes_available:
            raise HTTPException(
                status_code=503,
                detail="this server cannot record corrections: it needs DATABASE_URL")
        return repository  # type: ignore[return-value]

    # The same `exclude_unset` rule as /v1/purchases: a line the normalizer
    # left unresolved carries no product attributes, and the wire format must
    # not invent them as nulls.
    @app.get("/v1/receipts/{receipt_id}", response_model=ReceiptDocument,
             response_model_exclude_unset=True)
    def receipt(receipt_id: int) -> ReceiptDocument:
        """One receipt as the paper has it, with the normalizer's reading of each line."""
        found = require_writes().receipt(receipt_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"no receipt {receipt_id}")
        return ReceiptDocument.model_validate(found)

    @app.put("/v1/receipts/{receipt_id}/lines/{position}/resolution",
             response_model=ReceiptDocument, response_model_exclude_unset=True)
    def resolve_line(receipt_id: int, position: int,
                     answer: LineResolutionRequest) -> ReceiptDocument:
        """Say what one line actually was, or withdraw a previous answer.

        The whole receipt comes back, because one answer can change more than
        one line's reading: the same printed name on another line of the same
        receipt is still resolved by the catalog, and the caller should see
        the state it is now in rather than guess.
        """
        repo = require_writes()
        given = [k for k in ("product_id", "candidate", "new_product")
                 if k in answer.model_fields_set]
        if len(given) != 1:
            raise HTTPException(
                status_code=422,
                detail="send exactly one of product_id (null withdraws), candidate, new_product")
        try:
            product_id = answer.product_id
            if given[0] != "product_id":
                product_id = repo.product_for_answer(
                    receipt_id, position, answer.candidate,
                    answer.new_product.model_dump() if answer.new_product else None)
            updated = repo.set_line_resolution(receipt_id, position, product_id,
                                               answer.confirmed_by, answer.basis)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (UnknownProduct, NotAProductLine, NoSuchCandidate) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ReceiptDocument.model_validate(updated)

    @app.get("/v1/questions", response_model=QuestionsDocument)
    def questions() -> QuestionsDocument:
        """Every line nothing could place, with what the matcher found for it.

        Answer one with `PUT /v1/receipts/{receipt_id}/lines/{position}/resolution`:
        a `candidate` number from here, a `product_id` from the catalog, or a
        `new_product` in words when it is none of them.
        """
        return QuestionsDocument.model_validate(require_writes().questions())

    @app.patch("/v1/receipts/{receipt_id}", response_model=ReceiptDocument,
               response_model_exclude_unset=True)
    def correct_receipt(receipt_id: int, patch: ReceiptPatch) -> ReceiptDocument:
        """Correct the store, or mark the receipt as a duplicate of another."""
        repo = require_writes()
        if patch.is_duplicate is None and patch.store is None:
            raise HTTPException(status_code=422,
                                detail="nothing to change: send is_duplicate or store")
        try:
            updated = repo.update_receipt(receipt_id, patch.is_duplicate, patch.store)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ReceiptDocument.model_validate(updated)

    return app


def default_app() -> FastAPI:
    """The app `uvicorn --factory grocery_app.api.app:default_app` runs.

    `DATABASE_URL` selects PostgreSQL; otherwise `GROCERY_PURCHASES` names the
    purchases.json to serve. This is the one place the real, paid extractor is
    wired in: `GROCERY_READER` picks the API (default) or `claude -p` on the
    subscription. `GROCERY_IMAGES` says where uploaded photos are kept. The
    matcher asks the model through `claude -p`, on the subscription.
    """
    from grocery_app import matcher as matching

    matcher = line_matcher(matching.ClaudeCodeDecider(), matching.default_shops())
    return create_app(default_repository(), default_image_store(), configured_extractor(),
                      matcher)
