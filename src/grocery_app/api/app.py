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

`token` locks the `/v1` routes behind `Authorization: Bearer <token>`: one
shopper, one password, from `GROCERY_TOKEN` (backend-api.md, phase 3). The
page at `/`, `/health` and the schema stay open; they hold no history.

`resume_after`, when set, makes a starting server finish the jobs the last
one left half done, that many seconds after it starts (`jobs.resume_unfinished`).
Off by default, so a test's app never sets work off on its own.
"""

from __future__ import annotations

import hmac
import threading
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from grocery_app.api.images import (
    ImageStore,
    default_image_store,
    looks_like_an_image,
    sha256_of,
)
from grocery_app.api.jobs import Extractor, configured_extractor, resume_unfinished, run_job
from grocery_app.api.matching import LineIdentifier, LineMatcher, line_identifier, line_matcher
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
    ChecksDocument,
    Health,
    InsightsDocument,
    JobDocument,
    JobsDocument,
    LineCountedRequest,
    LineResolutionRequest,
    ProductMatch,
    PurchasesDocument,
    QuestionsDocument,
    ReceiptDocument,
    ReceiptPatch,
    ReceiptSummary,
)
from grocery_app.insights import build_insights
from grocery_app.matcher import ClaudeCodeDecider, GeminiDecider

__all__ = ["DEFAULT_PURCHASES", "MAX_UPLOAD_BYTES", "create_app", "default_app"]

# The shopper's page (`GET /`): one static file, shipped with the package.
REVIEW_PAGE = Path(__file__).with_name("review.html")

# A receipt photo off a phone is a few megabytes. The cap is not a security
# boundary, it is a promise that one request cannot read an arbitrary amount
# into memory before anyone has looked at it.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def create_app(repository: Repository, image_store: ImageStore | None = None,
               extractor: Extractor | None = None,
               matcher: LineMatcher | None = None,
               identify: LineIdentifier | None = None,
               token: str | None = None, resume_after: float | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if resume_after is not None and uploads_available:
            def resume() -> None:
                time.sleep(resume_after)
                resume_unfinished(repository.session_factory, image_store, extractor,
                                  matcher, identify)

            # A thread, so the server answers the phone while it catches up.
            app.state.resuming = threading.Thread(target=resume, name="resume-jobs",
                                                  daemon=True)
            app.state.resuming.start()
        yield

    app = FastAPI(
        title="Grocery App API",
        version="0.1.0",
        summary="Item-level grocery purchase history and the insights computed from it.",
        lifespan=lifespan,
    )

    if token:
        expected = f"Bearer {token}".encode()

        # A middleware rather than a dependency per route, so a route added
        # later under /v1 cannot be added unlocked.
        @app.middleware("http")
        async def require_token(request: Request, call_next):
            if request.url.path.startswith("/v1"):
                given = request.headers.get("authorization", "").encode()
                if not hmac.compare_digest(given, expected):
                    return JSONResponse(status_code=401, content={"detail": "wrong or no token"},
                                        headers={"WWW-Authenticate": "Bearer"})
            return await call_next(request)

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
                            job["job_id"], matcher, identify)
        return JobDocument.model_validate(job)

    @app.get("/v1/jobs", response_model=JobsDocument)
    def jobs() -> JobsDocument:
        """Every photo still being read or placed, and those that failed in the
        last hour, oldest first. The page's Add tab is this list, so every
        device shows the same thing, whichever one sent the photo."""
        repo = require_uploads()
        return JobsDocument(jobs=[JobDocument.model_validate(job)
                                  for job in repo.jobs_in_progress()])

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
                    answer.new_product.model_dump() if answer.new_product else None,
                    identify)
            updated = repo.set_line_resolution(
                receipt_id, position, product_id, answer.confirmed_by, answer.basis,
                answer.new_product.description if answer.new_product else None)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (UnknownProduct, NotAProductLine, NoSuchCandidate) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ReceiptDocument.model_validate(updated)

    @app.get("/v1/receipts", response_model=list[ReceiptSummary])
    def receipts() -> list[ReceiptSummary]:
        """Every receipt, newest first, with how many of its product lines are
        placed on the shopper's word, on the app's, or not at all."""
        return [ReceiptSummary.model_validate(r) for r in require_writes().receipts()]

    @app.get("/v1/products", response_model=list[ProductMatch])
    def products(q: str = Query(min_length=1, description="Words in the name or brand")
                 ) -> list[ProductMatch]:
        """Catalog products to answer a line with: every word of `q` in the
        name or brand, shortest name first, at most 20."""
        return [ProductMatch.model_validate(p) for p in require_writes().search_products(q)]

    @app.get("/", include_in_schema=False)
    def review_page() -> HTMLResponse:
        """The review page: what is waiting for the shopper, and every receipt
        with who said what each line is. It reads and answers through the
        routes above, nothing else."""
        return HTMLResponse(REVIEW_PAGE.read_text(encoding="utf-8"))

    @app.get("/v1/checks", response_model=ChecksDocument)
    def checks() -> ChecksDocument:
        """Spot checks: lines the app placed on its own, put to the shopper at
        random, two per uploaded receipt, and the app's mistake rate on them.

        Answer one as any line, `PUT /v1/receipts/{receipt_id}/lines/{position}/resolution`:
        `product_id` = `app_product_id` when the app was right, another product
        when it was not (the mistake is counted in `corrections` as well).
        """
        return ChecksDocument.model_validate(require_writes().checks())

    @app.get("/v1/questions", response_model=QuestionsDocument)
    def questions(searched: bool = Query(
            default=False,
            description="Only questions a web search narrowed down; the rest are counted "
                        "in `meta.held_back`")) -> QuestionsDocument:
        """Every line nothing could place, with what the matcher found for it.

        Answer one with `PUT /v1/receipts/{receipt_id}/lines/{position}/resolution`:
        a `candidate` number from here, a `product_id` from the catalog, or a
        `new_product` in words when it is none of them.
        """
        return QuestionsDocument.model_validate(require_writes().questions(searched))

    @app.patch("/v1/receipts/{receipt_id}", response_model=ReceiptDocument,
               response_model_exclude_unset=True)
    def correct_receipt(receipt_id: int, patch: ReceiptPatch) -> ReceiptDocument:
        """Correct the store."""
        repo = require_writes()
        if patch.store is None:
            raise HTTPException(status_code=422, detail="nothing to change: send store")
        try:
            updated = repo.update_receipt(receipt_id, patch.store)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ReceiptDocument.model_validate(updated)

    @app.put("/v1/receipts/{receipt_id}/lines/{position}/counted",
             response_model=ReceiptDocument, response_model_exclude_unset=True)
    def count_line(receipt_id: int, position: int,
                   body: LineCountedRequest) -> ReceiptDocument:
        """Leave one line out of the shopper's numbers (a wine bought for a
        friend), or count it again. It stays on the receipt and in the prices."""
        try:
            updated = require_writes().set_counted(receipt_id, position, body.counted)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ReceiptDocument.model_validate(updated)

    return app


def default_app() -> FastAPI:
    """The app `uvicorn --factory grocery_app.api.app:default_app` runs.

    `DATABASE_URL` selects PostgreSQL; otherwise `GROCERY_PURCHASES` names the
    purchases.json to serve. This is the one place the real, paid extractor is
    wired in: `GROCERY_READER` picks the API (default) or `claude -p` on the
    subscription, or `gemini`. `GROCERY_TOKEN`, when set, is the password the
    `/v1` routes ask for. `GROCERY_IMAGES` says where uploaded photos are
    kept. The matcher asks the model `GROCERY_MATCHER` names
    (`matcher_decider`); identify reads and searches with `GROCERY_IDENTIFY`
    (`identify_decider`).
    """
    import os

    from grocery_app import matcher as matching

    repository = default_repository()
    matcher = line_matcher(matcher_decider(), matching.default_shops())
    # Identify runs only on uploads, which need PostgreSQL: a server that only
    # serves purchases.json needs no reader and no key.
    identifier = (line_identifier(identify_decider(), identify_searcher())
                  if type(repository).__name__ == "PostgresRepository" else None)
    return create_app(repository, default_image_store(), configured_extractor(), matcher,
                      identifier, token=os.environ.get("GROCERY_TOKEN") or None,
                      resume_after=RESUME_AFTER_SECONDS)


# A deploy stops the old server within ten seconds of starting the new one
# (Cloud Run's default grace period); waiting longer means no job is ever
# worked on by both.
RESUME_AFTER_SECONDS = 30


# Who reads and searches a line nothing else could place. Gemini through
# Google's API, paid per search, is the default (Parham, 2026-10-02): on the 22
# test lines it made no mistake and, where it asked, the right answer was among
# its choices every time; Claude through `claude -p` is free on the
# subscription and kept as the alternative.
IDENTIFY_READERS = ("gemini", "claude-code")
GEMINI_MODEL = "gemini-3.8-flash"


def identify_reader_kind(kind: str | None = None) -> str:
    """`kind`, else `GROCERY_IDENTIFY`, else Gemini; refuses anything else, and
    Gemini with no way in (`gemini.configured`), before a server starts rather than on the
    first upload."""
    import os

    kind = kind or os.environ.get("GROCERY_IDENTIFY", "gemini")
    if kind not in IDENTIFY_READERS:
        raise SystemExit(f"unknown identify reader {kind!r}: expected "
                         f"{', '.join(IDENTIFY_READERS)}")
    from grocery_app import gemini

    if kind == "gemini" and not gemini.configured():
        raise SystemExit(f"identify reads with Gemini, and {gemini.NOT_CONFIGURED}: set one, "
                         "or GROCERY_IDENTIFY=claude-code to read on the subscription")
    return kind


# Who picks among the candidates the matcher gathered for a line. `claude -p`
# on the subscription is what every matcher score so far was measured with;
# Gemini is for a server, where `claude -p` cannot run.
MATCHERS = ("claude-code", "gemini")


def matcher_kind(kind: str | None = None) -> str:
    """`kind`, else `GROCERY_MATCHER`, else `claude-code`; refuses anything
    else, and Gemini with no way in (`gemini.configured`), before a server starts."""
    import os

    kind = kind or os.environ.get("GROCERY_MATCHER", "claude-code")
    if kind not in MATCHERS:
        raise SystemExit(f"unknown matcher {kind!r}: expected {', '.join(MATCHERS)}")
    from grocery_app import gemini

    if kind == "gemini" and not gemini.configured():
        raise SystemExit(f"the matcher asks Gemini, and {gemini.NOT_CONFIGURED}: set one, "
                         "or GROCERY_MATCHER=claude-code to ask on the subscription")
    return kind


def matcher_decider(kind: str | None = None,
                    model: str = "sonnet") -> ClaudeCodeDecider | GeminiDecider:
    """The matcher's model, cached under data/matched/ as `eval-matching`
    caches it; `model` is the Claude model and does not apply to Gemini."""
    from grocery_app import matcher as matching

    if matcher_kind(kind) == "gemini":
        return GeminiDecider(GEMINI_MODEL, "data/matched", matching.PROMPT_VERSION,
                             search=False)
    return ClaudeCodeDecider(model)


def identify_decider(kind: str | None = None) -> ClaudeCodeDecider | GeminiDecider:
    """identify's reader, cached where `eval-identify` caches it: a line scored
    once is not paid for again when it is uploaded."""
    from grocery_app import identify as identifying

    if identify_reader_kind(kind) == "gemini":
        return GeminiDecider(GEMINI_MODEL, "data/identified", identifying.PROMPT_VERSION,
                             search=False)
    return ClaudeCodeDecider("sonnet", "data/identified", version=identifying.PROMPT_VERSION)


def identify_searcher(kind: str | None = None) -> ClaudeCodeDecider | GeminiDecider:
    """The web search identify runs on a line before reading it
    (`identify.search_line`), by the same model as the reader; cached like it.
    A Gemini server stops searching after `GROCERY_MAX_SEARCHES` searches
    (150 unless set), so a fault cannot spend without limit."""
    import os

    from grocery_app import identify as identifying

    if identify_reader_kind(kind) == "gemini":
        return GeminiDecider(GEMINI_MODEL, "data/identified", identifying.SEARCH_VERSION,
                             max_searches=int(os.environ.get("GROCERY_MAX_SEARCHES", "150")))
    return ClaudeCodeDecider("sonnet", "data/identified", version=identifying.SEARCH_VERSION,
                             search=True)
