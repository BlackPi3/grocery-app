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

`token` locks the `/v1` routes behind `Authorization: Bearer <token>`: the
owner's password, from `GROCERY_TOKEN` (backend-api.md, phase 3). Since
2026-10-11 other people have passwords of their own (`users`): the password
says who is asking, and every route reads and writes that person's receipts
only (`PostgresRepository.as_user`); the catalog and the memory are shared.
Without a token the server is the owner's alone, as on the laptop. The page
at `/`, `/health` and the schema stay open; they hold no history.

`google`, when given, switches on Sign in with Google (`google_sign_in`): an
invited person trades Google's ID token for a sign-in token of their own,
sent like a password. It locks `/v1` even without `token`. Never in the demo.

`resume_after`, when set, makes a starting server finish the jobs the last
one left half done, that many seconds after it starts (`jobs.resume_unfinished`).
Off by default, so a test's app never sets work off on its own.

`readers`, when given, is the line uploads wait in to be read
(`jobs.reading_line`: a few at a time). Without it a job runs straight after
its upload's response, as a test wants.

`offers`, when given, is where the shops' weekly offers are searched
(`grocery_app.offers.Marktguru`): a thread keeps those near the shops people
visit, for what they buy (`api.offers`). Off by default and in the demo, so a
test's app never reaches the network. `offer_judge`, with it, is the model
that says which offers are a person's products (`offer_match.judge`).
"""

from __future__ import annotations

import hmac
import logging
import os
import re
import threading
import time
from concurrent.futures import Executor, Future
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from grocery_app.api.google_sign_in import (
    GoogleSignIn,
    GoogleUnavailable,
    NotSignedIn,
)
from grocery_app.api.google_sign_in import configured as google_configured
from grocery_app.api.images import (
    ImageStore,
    default_image_store,
    looks_readable,
    sha256_of,
)
from grocery_app.api.jobs import (
    Extractor,
    configured_extractor,
    reading_line,
    resume_unfinished,
    run_job,
)
from grocery_app.api.matching import LineIdentifier, LineMatcher, line_identifier, line_matcher
from grocery_app.api.pictures import (
    CHECK_WAITS_UP_TO,
    Pictures,
    default_pictures,
    keep_filling,
    media_type,
)
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
    AuthConfig,
    ChecksDocument,
    CostsDocument,
    CountedKinds,
    CountedKindsRequest,
    GoogleSignInRequest,
    Health,
    InsightsDocument,
    JobDocument,
    JobsDocument,
    LineCountedRequest,
    LineResolutionRequest,
    ListEditRequest,
    ListWriteRequest,
    Me,
    NearbyDocument,
    NewUser,
    NewUserRequest,
    OffersDocument,
    OffersRhythm,
    ProductMatch,
    ProductPurchases,
    PurchasesDocument,
    QuestionsDocument,
    ReceiptDocument,
    ReceiptPatch,
    ReceiptSummary,
    Seen,
    SharedRequest,
    ShoppingListDocument,
    SignedIn,
    SurenessDocument,
    UserPatch,
    UserSummary,
)
from grocery_app.insights import build_insights
from grocery_app.matcher import ClaudeCodeDecider, GeminiDecider

__all__ = ["DEFAULT_PURCHASES", "MAX_UPLOAD_BYTES", "create_app", "default_app"]

# The shopper's page (`GET /`): one static file, shipped with the package.
REVIEW_PAGE = Path(__file__).with_name("review.html")
PRIVACY_PAGE = Path(__file__).with_name("privacy.html")
PAGE_WORKER = Path(__file__).with_name("sw.js")

# A receipt photo off a phone is a few megabytes. The cap is not a security
# boundary, it is a promise that one request cannot read an arbitrary amount
# into memory before anyone has looked at it.
log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _said_if_failed(done: Future) -> None:
    """A job that crashed past its own error handling is logged, not lost in
    the reading line's thread. Its row stays unfinished for the next start."""
    if done.exception() is not None:
        log.error("a reading crashed", exc_info=done.exception())

# How long a photo no receipt was made from is kept (owner, 2026-10-15): long
# enough for a developer to learn from it (`/v1/inbox`), then deleted.
FORGET_PHOTOS_AFTER = timedelta(days=30)
FORGET_EVERY_SECONDS = 6 * 3600


def forget_old_photos(repository: Any, image_store: Any, now: datetime | None = None) -> int:
    """Delete the photos `photos_to_forget` names; how many were there."""
    forgotten = 0
    for photo in repository.photos_to_forget((now or datetime.now(UTC)) - FORGET_PHOTOS_AFTER):
        if image_store.size(photo) is not None:
            image_store.delete(photo)
            forgotten += 1
    return forgotten


def keep_forgetting(repository: Any, image_store: Any,
                    every: float = FORGET_EVERY_SECONDS) -> None:
    """The server's forgetting thread: a pass, a pause, for as long as it runs."""
    while True:
        try:
            if forgotten := forget_old_photos(repository, image_store):
                log.info("deleted %d photos older than %s that no receipt came from",
                         forgotten, FORGET_PHOTOS_AFTER)
        except Exception:  # a failed pass is tried again at the next
            log.exception("deleting old photos failed")
        time.sleep(every)


# The /v1 routes that answer without a password: they are how one gets one.
SIGN_IN_PATHS = frozenset({"/v1/auth/config", "/v1/auth/google", "/v1/auth/google/redirect"})


def create_app(repository: Repository, image_store: ImageStore | None = None,
               extractor: Extractor | None = None,
               matcher: LineMatcher | None = None,
               identify: LineIdentifier | None = None,
               token: str | None = None, resume_after: float | None = None,
               pictures: Pictures | None = None, demo: bool = False,
               google: GoogleSignIn | None = None, readers: Executor | None = None,
               sorter: Any | None = None, forget_photos: bool = False,
               reread: bool = False,
               offers: Any | None = None, offer_judge: Any | None = None,
               maps: Any | None = None) -> FastAPI:
    if demo:
        google = None  # the demo has no accounts: every guest is the owner
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if pictures is not None and writes_available:
            # Finding pictures reads web pages: a thread of its own. The demo
            # starts from its seed every time: a picture it looked up again
            # would be lost, and paid for again, at every start.
            app.state.pictures = threading.Thread(
                target=keep_filling, args=(repository.session_factory, pictures),
                kwargs={"refresh": not demo}, name="pictures", daemon=True)
            app.state.pictures.start()
            if hasattr(repository, "picture_wait"):
                repository.picture_wait = CHECK_WAITS_UP_TO  # checks come with theirs
        if sorter is not None and writes_available:
            # A product made with no category is sorted within a minute
            # (`matching.keep_sorting`): a thread, as for the pictures.
            from grocery_app.api.matching import keep_sorting

            app.state.sorting = threading.Thread(
                target=keep_sorting, args=(repository.session_factory, sorter),
                name="sorting", daemon=True)
            app.state.sorting.start()
        if reread and matcher is not None and identify is not None and uploads_available \
                and not demo:
            # Lines a failed search left waiting are read again, a few
            # receipts every few minutes (`matching.keep_rereading`).
            from grocery_app.api.matching import keep_rereading

            app.state.rereading = threading.Thread(
                target=keep_rereading, args=(repository.session_factory, matcher, identify),
                name="rereading", daemon=True)
            app.state.rereading.start()
        if offers is not None and writes_available and not demo:
            # The offers near the shops people visit, once a day (`api.offers`).
            from grocery_app.api.offers import keep_fetching

            app.state.offers = threading.Thread(
                target=keep_fetching, args=(repository, offers, offer_judge),
                name="offers", daemon=True)
            app.state.offers.start()
        if maps is not None and writes_available and not demo:
            # The supermarkets near the shops people use (`api.nearby`).
            from grocery_app.api.nearby import keep_looking

            app.state.nearby = threading.Thread(
                target=keep_looking, args=(repository, maps), name="nearby", daemon=True)
            app.state.nearby.start()
        if forget_photos and uploads_available and not demo:
            # Photos no receipt came from are kept 30 days, then deleted.
            app.state.forgetting = threading.Thread(
                target=keep_forgetting, args=(repository, image_store),
                name="forgetting", daemon=True)
            app.state.forgetting.start()
        if resume_after is not None and uploads_available:
            started = datetime.now(UTC)

            def resume() -> None:
                time.sleep(resume_after)
                resume_unfinished(repository.session_factory, image_store, extractor,
                                  matcher, identify, started_before=started)

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

    if token or google is not None:
        expected = f"Bearer {token}".encode() if token else None

        def who_holds(given: str) -> dict | None:
            """`{"user": ...}` for a password or a sign-in, None for neither."""
            if not given.startswith("Bearer "):
                return None
            secret = given.removeprefix("Bearer ")
            if hasattr(repository, "user_for_password"):
                if user := repository.user_for_password(secret):
                    return {"user": user}
            if google is not None and hasattr(repository, "signed_in"):
                found = repository.signed_in(secret)
                # An owner's sign-in lasts while their address is the owner's.
                if found and (found["user"] is not None or google.is_owner(found["email"])):
                    return {"user": found["user"]}
            return None

        # A middleware rather than a dependency per route, so a route added
        # later under /v1 cannot be added unlocked. Only the two routes that
        # sign someone in are open, by their exact paths.
        @app.middleware("http")
        async def require_token(request: Request, call_next):
            request.state.user = None  # the owner
            path = request.url.path
            if path.startswith("/v1") and path not in SIGN_IN_PATHS:
                given = request.headers.get("authorization", "")
                if expected is None or not hmac.compare_digest(given.encode(), expected):
                    found = await run_in_threadpool(who_holds, given)
                    if found is None:
                        return JSONResponse(status_code=401,
                                            content={"detail": "wrong or no token"},
                                            headers={"WWW-Authenticate": "Bearer"})
                    request.state.user = found["user"]
            return await call_next(request)

    # Corrections need a database. A photo needs that and somewhere to put the
    # bytes and something that can read them, so uploads are the stricter test.
    writes_available = isinstance(repository, WriteRepository)
    uploads_available = (writes_available
                         and image_store is not None and extractor is not None)

    def asking(request: Request) -> dict | None:
        """Who sent this request: a user, or None for the owner."""
        return getattr(request.state, "user", None)

    def seen_by(request: Request) -> Repository:
        """The repository as the person asking sees it: their receipts only."""
        user = asking(request)
        if hasattr(repository, "as_user"):
            return repository.as_user(user)
        if user is not None:  # a file holds the owner's history and nobody else's
            raise HTTPException(status_code=403, detail="this server has no accounts")
        return repository

    # In the demo every guest is the owner: the photos it shows are the
    # made-up receipts' only, never one a guest sent (`demo.seeded_photos`).
    demo_photos: frozenset[str] = frozenset()
    if demo:
        from grocery_app import demo as demo_mode

        demo_photos = demo_mode.seeded_photos()

    def photo_shown(sha256: str | None) -> bool:
        """Is this upload's file kept here, and may this server show it?"""
        return (sha256 is not None and image_store is not None
                and (not demo or sha256 in demo_photos)
                and image_store.size(sha256) is not None)

    def owner_only(request: Request) -> None:
        if asking(request) is not None:
            raise HTTPException(status_code=403, detail="only the owner can see this")

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
    def purchases(request: Request) -> PurchasesDocument:
        """The purchases.json contract, exactly as the CLI writes it."""
        return PurchasesDocument.model_validate(seen_by(request).purchases())

    @app.get("/v1/insights", response_model=InsightsDocument)
    def insights(
        request: Request,
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
        person = seen_by(request)
        doc = build_insights(person.purchases(), as_of=as_of_date, also=person.counted_kinds())
        return InsightsDocument.model_validate(doc)

    def require_uploads(request: Request) -> WriteRepository:
        if not uploads_available:
            raise HTTPException(
                status_code=503,
                detail="this server cannot accept photos: it needs DATABASE_URL, an "
                       "image store and an extractor",
            )
        return seen_by(request)  # type: ignore[return-value]

    @app.post("/v1/receipts", response_model=JobDocument, status_code=202)
    async def upload_receipt(request: Request, background: BackgroundTasks,
                             response: Response, file: UploadFile) -> JobDocument:
        """Take a photo, return the job that will read it.

        Extraction takes seconds and costs money, so it does not happen inside
        the request. The response carries a job id to poll: `202` when this
        photo is new and work was scheduled, `200` when it had already been
        read and the existing job is being handed back. Not in the demo: a
        guest is told to ask for an account (`demo.NO_UPLOADS`).
        """
        if demo:
            from grocery_app import demo as demo_mode

            raise HTTPException(status_code=403, detail=demo_mode.NO_UPLOADS)
        repo = require_uploads(request)
        data = await file.read()
        if not data:
            raise HTTPException(status_code=422, detail="file is empty")
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"file is {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES}")
        if not looks_readable(data):
            raise HTTPException(status_code=422,
                                detail="file is not a photo or a PDF this can read")

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
        work = (run_job, repo.session_factory, image_store, extractor, job["job_id"], matcher,
                identify)
        if readers is None:
            background.add_task(*work)
        else:
            readers.submit(*work).add_done_callback(_said_if_failed)
        return JobDocument.model_validate(job)

    @app.get("/v1/jobs", response_model=JobsDocument)
    def jobs(request: Request) -> JobsDocument:
        """Every photo still being read or placed, and those that failed in the
        last hour, oldest first. The page's Add tab is this list, so every
        device shows the same thing, whichever one sent the photo."""
        repo = require_uploads(request)
        return JobsDocument(jobs=[JobDocument.model_validate(job)
                                  for job in repo.jobs_in_progress()])

    @app.get("/v1/jobs/{job_id}", response_model=JobDocument)
    def job(request: Request, job_id: str) -> JobDocument:
        repo = require_uploads(request)
        found = repo.job(job_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"no job {job_id}")
        return JobDocument.model_validate(found)

    def require_writes(request: Request) -> WriteRepository:
        if not writes_available:
            raise HTTPException(
                status_code=503,
                detail="this server cannot record corrections: it needs DATABASE_URL")
        return seen_by(request)  # type: ignore[return-value]

    # The same `exclude_unset` rule as /v1/purchases: a line the normalizer
    # left unresolved carries no product attributes, and the wire format must
    # not invent them as nulls.
    @app.get("/v1/receipts/{receipt_id}", response_model=ReceiptDocument,
             response_model_exclude_unset=True)
    def receipt(request: Request, receipt_id: int) -> ReceiptDocument:
        """One receipt as the paper has it, with the normalizer's reading of each line."""
        found = require_writes(request).receipt(receipt_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"no receipt {receipt_id}")
        return ReceiptDocument.model_validate(found)

    @app.put("/v1/receipts/{receipt_id}/lines/{position}/resolution",
             response_model=ReceiptDocument, response_model_exclude_unset=True)
    def resolve_line(request: Request, receipt_id: int, position: int,
                     answer: LineResolutionRequest) -> ReceiptDocument:
        """Say what one line actually was, or withdraw a previous answer.

        The whole receipt comes back, because one answer can change more than
        one line's reading: the same printed name on another line of the same
        receipt is still resolved by the catalog, and the caller should see
        the state it is now in rather than guess.
        """
        repo = require_writes(request)
        given = [k for k in ("product_id", "candidate", "new_product", "none_of_these")
                 if k in answer.model_fields_set]
        if len(given) != 1:
            raise HTTPException(
                status_code=422,
                detail="send exactly one of product_id (null withdraws), candidate, new_product, "
                       "none_of_these")
        try:
            product_id = answer.product_id
            if given[0] not in ("product_id", "none_of_these"):
                product_id = repo.product_for_answer(
                    receipt_id, position, answer.candidate,
                    answer.new_product.model_dump() if answer.new_product else None,
                    identify)
            updated = repo.set_line_resolution(
                receipt_id, position, product_id, answer.confirmed_by, answer.basis,
                answer.new_product.description if answer.new_product else None,
                none_of_these=bool(answer.none_of_these))
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (UnknownProduct, NotAProductLine, NoSuchCandidate) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ReceiptDocument.model_validate(updated)

    @app.get("/v1/receipts", response_model=list[ReceiptSummary])
    def receipts(request: Request) -> list[ReceiptSummary]:
        """Every receipt, newest first, with how many of its product lines are
        placed on the shopper's word, on the app's, or not at all."""
        return [ReceiptSummary.model_validate({**r, "photo": photo_shown(r.get("image_sha256"))})
                for r in require_writes(request).receipts()]

    @app.put("/v1/receipts/{receipt_id}/seen", response_model=Seen)
    def mark_seen(request: Request, receipt_id: int) -> Seen:
        """The shopper opened this receipt: its "new" mark goes, on every
        device (2026-10-13). Never set by a GET, so nothing that only looks,
        a preview or a second tab, takes the mark away unopened."""
        try:
            seen_at = require_writes(request).mark_seen(receipt_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Seen(receipt_id=receipt_id, seen_at=seen_at)

    @app.get("/v1/receipts/{receipt_id}/photo")
    def receipt_photo(request: Request, receipt_id: int) -> Response:
        """The photo or PDF a receipt was read from, as it arrived: the last
        step of the drill-down, to set a line against the paper. Whoever may
        see the receipt may see its photo, and no one else (another person's
        receipt is a 404, as everywhere). In the demo, only the made-up
        receipts' photos: a guest is the owner there, and must not see a
        photo another guest sent."""
        try:
            sha256 = require_writes(request).receipt_image(receipt_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if demo and sha256 not in demo_photos:
            raise HTTPException(status_code=403,
                                detail="the demo shows the photos of its made-up receipts only")
        if not photo_shown(sha256):
            raise HTTPException(status_code=404, detail=f"no photo kept for receipt {receipt_id}")
        data = image_store.path(sha256).read_bytes()
        return Response(data, media_type="application/pdf" if data[:5] == b"%PDF-"
                        else media_type(data), headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/v1/products/{product_id}/purchases", response_model=ProductPurchases)
    def product_purchases(request: Request, product_id: str) -> ProductPurchases:
        """Every purchase of one product, oldest first, each with the receipt
        line to open (`receipt_id`, `position`): what an insight about it was
        computed from. The asker's own receipts only; the catalog is shared."""
        found = require_writes(request).product_purchases(product_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"no product {product_id}")
        return ProductPurchases.model_validate(found)

    @app.get("/v1/products", response_model=list[ProductMatch])
    def products(request: Request,
                 q: str = Query(min_length=1, description="Words in the name or brand")
                 ) -> list[ProductMatch]:
        """Catalog products to answer a line with: every word of `q` in the
        name or brand, shortest name first, at most 20. The catalog is shared."""
        return [ProductMatch.model_validate(p)
                for p in require_writes(request).search_products(q)]

    @app.get("/", include_in_schema=False)
    def review_page() -> HTMLResponse:
        """The review page: what is waiting for the shopper, and every receipt
        with who said what each line is. It reads and answers through the
        routes above, nothing else."""
        return HTMLResponse(REVIEW_PAGE.read_text(encoding="utf-8"))

    @app.get("/privacy", include_in_schema=False)
    def privacy_page() -> HTMLResponse:
        """What the app keeps and why, open to anyone (2026-10-15). Who runs
        this server and how to reach them come from its environment, so the
        public repo holds no address."""
        from html import escape

        name = os.environ.get("GROCERY_OWNER_NAME") or "The person who runs this server"
        email = os.environ.get("GROCERY_OWNER_EMAIL")
        contact = (f'<a href="mailto:{escape(email)}">{escape(email)}</a>' if email
                   else "the address they gave you")
        return HTMLResponse(PRIVACY_PAGE.read_text(encoding="utf-8")
                            .replace("{{NAME}}", escape(name)).replace("{{EMAIL}}", contact))

    @app.get("/sw.js", include_in_schema=False)
    def page_worker() -> Response:
        """The page's service worker: the phone keeps a copy of the page, so a
        reload need not wait for a server that is starting up. Never cached
        itself, so a new version reaches the phone on the next visit."""
        return Response(PAGE_WORKER.read_text(encoding="utf-8"),
                        media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})

    @app.get("/pictures/{file}", include_in_schema=False)
    def picture(file: str) -> Response:
        """A product's photo, the app's own copy (`api.pictures`). Outside
        /v1, with no token: an <img> cannot send one, and these are the
        shops' public pack photos, named by the hash of their bytes."""
        if pictures is None or not re.fullmatch(r"[0-9a-f]{64}", file):
            raise HTTPException(status_code=404, detail="no such picture")
        path = pictures.store.path(file)
        if not path.exists():
            raise HTTPException(status_code=404, detail="no such picture")
        data = path.read_bytes()
        return Response(data, media_type=media_type(data),
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/v1/checks", response_model=ChecksDocument)
    def checks(request: Request) -> ChecksDocument:
        """Spot checks: lines the app placed on its own, put to the shopper at
        random, two per uploaded receipt, and the app's mistake rate on them.

        Answer one as any line, `PUT /v1/receipts/{receipt_id}/lines/{position}/resolution`:
        `product_id` = `app_product_id` when the app was right, another product
        when it was not (the mistake is counted in `corrections` as well).
        """
        return ChecksDocument.model_validate(require_writes(request).checks())

    @app.get("/v1/questions", response_model=QuestionsDocument)
    def questions(request: Request, searched: bool = Query(
            default=False,
            description="Only questions a web search narrowed down; the rest are counted "
                        "in `meta.held_back`")) -> QuestionsDocument:
        """Every line nothing could place, with what the matcher found for it.

        Answer one with `PUT /v1/receipts/{receipt_id}/lines/{position}/resolution`:
        a `candidate` number from here, a `product_id` from the catalog, or a
        `new_product` in words when it is none of them.
        """
        return QuestionsDocument.model_validate(require_writes(request).questions(searched))

    @app.patch("/v1/receipts/{receipt_id}", response_model=ReceiptDocument,
               response_model_exclude_unset=True)
    def correct_receipt(request: Request, receipt_id: int, patch: ReceiptPatch) -> ReceiptDocument:
        """Correct the store."""
        repo = require_writes(request)
        if patch.store is None:
            raise HTTPException(status_code=422, detail="nothing to change: send store")
        try:
            updated = repo.update_receipt(receipt_id, patch.store)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ReceiptDocument.model_validate(updated)

    @app.get("/v1/costs", response_model=CostsDocument)
    def costs(request: Request) -> CostsDocument:
        """What the model calls cost: per month (when the money was spent) and
        per receipt (reading it, and finding what its lines are). List prices
        in dollars; the server and the database are on Google's bill, not here.
        The whole app's bill, so the owner's only to see."""
        owner_only(request)
        return CostsDocument.model_validate(require_writes(request).costs())

    @app.get("/v1/sureness", response_model=SurenessDocument)
    def sureness(request: Request) -> SurenessDocument:
        """How sure the app is of every product line, by level, and how many a
        person answered: overall and per shopping month, over everyone's
        receipts, with the spot checks' yes rate. The owner's only: it is
        about the app, not one person's shopping. The level rules are in
        `grocery_app.sureness`."""
        owner_only(request)
        return SurenessDocument.model_validate(require_writes(request).sureness())

    @app.get("/v1/offers", response_model=OffersDocument)
    def my_offers(request: Request) -> OffersDocument:
        """The asker's offers for the coming week: for each of their regular
        groceries, offers near their shops that are that product ("your
        product") or the same kind ("like yours"), and what they save per
        unit against what the asker usually pays (`api.offers.offers_for`)."""
        from grocery_app.api.offers import offers_for
        from grocery_app.offers import GERMANY

        today = datetime.now(UTC).astimezone(GERMANY).date()
        return OffersDocument(as_of=today.isoformat(),
                              offers=offers_for(require_writes(request), today))

    @app.get("/v1/stores/nearby", response_model=NearbyDocument)
    def stores_nearby(request: Request) -> NearbyDocument:
        """The shops on the asker's receipts, and for each chain its
        supermarket nearest any of them (`api.nearby.stores_near`): where the
        shopping list can be priced, whether or not the asker goes there."""
        from grocery_app.api.nearby import stores_near
        from grocery_app.offers import GERMANY

        today = datetime.now(UTC).astimezone(GERMANY).date()
        return NearbyDocument.model_validate(stores_near(require_writes(request), today))

    def my_list(person: WriteRepository) -> ShoppingListDocument:
        from grocery_app.offers import GERMANY
        from grocery_app.shopping_list import list_rows, with_edits

        today = datetime.now(UTC).astimezone(GERMANY).date()
        return ShoppingListDocument.model_validate(
            with_edits(list_rows(person.purchases()), person.list_edits(), today))

    @app.get("/v1/list", response_model=ShoppingListDocument)
    def the_list(request: Request) -> ShoppingListDocument:
        """The asker's shopping list today: the kinds they are likely to buy
        this week, most urgent first, after what they added and without what
        they removed for now (`shopping_list.with_edits`)."""
        return my_list(require_writes(request))

    # `:path`: an item word may hold a slash (`Milch/Kakao`), which arrives
    # decoded however the page encoded it.
    @app.put("/v1/list/{kind:path}", response_model=ShoppingListDocument)
    def edit_list(request: Request, kind: str, body: ListEditRequest) -> ShoppingListDocument:
        """Put an item on the list, take it off for now (a snooze that doubles
        each time it is taken off without a buy), cross it off or back, or
        delete a typed line. Answers the new list."""
        from grocery_app import categories
        from grocery_app.shopping_list import known, list_rows

        person = require_writes(request)
        # An item the asker bought (`walnüsse`), any category, or words the
        # asker typed onto their list.
        if kind not in categories.CATEGORIES \
                and kind not in known(list_rows(person.purchases())) \
                and not any(e["kind"] == kind and e["edit"] == "write"
                            for e in person.list_edits()):
            raise HTTPException(status_code=422, detail=f"no kind {kind!r}")
        person.edit_list(kind, body.what)
        return my_list(person)

    @app.post("/v1/list", response_model=ShoppingListDocument)
    def write_on_list(request: Request, body: ListWriteRequest) -> ShoppingListDocument:
        """Words typed onto the list (`shopping_list` on the paper list): an
        item the asker bought or a category, when they name one, else a line
        of their own. Answers the new list."""
        from grocery_app.shopping_list import list_rows, typed_key, written

        person = require_writes(request)
        text = written(body.text)
        if not text:
            raise HTTPException(status_code=422, detail="nothing typed")
        key = typed_key(text, list_rows(person.purchases()))
        person.edit_list(key or text, "add" if key else "write")
        return my_list(person)

    def counted(person: Repository) -> CountedKinds:
        from grocery_app import categories

        return CountedKinds(kinds=sorted(person.counted_kinds()),
                            choices=categories.CLOSE_KINDS)

    @app.get("/v1/counted", response_model=CountedKinds)
    def counted_kinds(request: Request) -> CountedKinds:
        """What the asker's history counts: groceries, and the kinds close to
        groceries they switched on."""
        return counted(seen_by(request))

    @app.put("/v1/counted", response_model=CountedKinds)
    def set_counted_kinds(request: Request, body: CountedKindsRequest) -> CountedKinds:
        """Count exactly these close kinds beside groceries from now on."""
        from grocery_app import categories

        person = require_writes(request)
        unknown = sorted(set(body.kinds) - set(categories.CLOSE_KINDS))
        if unknown:
            raise HTTPException(status_code=422, detail=f"no kind {', '.join(unknown)}")
        person.set_counted_kinds(frozenset(body.kinds))
        return counted(person)

    @app.get("/v1/offers/rhythm", response_model=list[OffersRhythm])
    def offers_rhythm(request: Request) -> list[OffersRhythm]:
        """On which weekday each chain's offers are first seen, and how many
        days before they start (`offers.rhythm`). The owner's only: it is
        about the app, not one person's shopping."""
        from grocery_app.api.offers import rhythm

        owner_only(request)
        with require_writes(request).session_factory() as session:
            return [OffersRhythm.model_validate(r) for r in rhythm(session)]

    def not_in_demo() -> None:
        """In the demo every guest is the owner (there is no password), so
        what is the owner's for another person's sake is no one's there."""
        if demo:
            raise HTTPException(status_code=403, detail="not in the demo")

    @app.get("/v1/me", response_model=Me)
    def me(request: Request) -> Me:
        """Who the password belongs to: the owner, or a user by name."""
        user = asking(request)
        return Me(role="user" if user else "owner", name=user["name"] if user else None,
                  demo=demo,
                  contact=os.environ.get("GROCERY_OWNER_EMAIL") or None if demo else None)

    @app.get("/v1/users", response_model=list[UserSummary])
    def users(request: Request) -> list[UserSummary]:
        """The people who use the app besides the owner. The owner's only."""
        owner_only(request)
        return [UserSummary.model_validate(u) for u in require_writes(request).users()]

    @app.post("/v1/users", response_model=NewUser, status_code=201)
    def add_user(request: Request, body: NewUserRequest) -> NewUser:
        """A new user, with their own receipts and a password shown only in this
        answer (only its hash is kept), and the Google address they may sign
        in with, if given. The owner's only, and not in the demo."""
        owner_only(request)
        not_in_demo()
        if body.email and google is not None and google.is_owner(body.email):
            raise HTTPException(status_code=422, detail="that is the owner's own address")
        try:
            return NewUser.model_validate(
                require_writes(request).create_user(body.name, body.email))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.patch("/v1/users/{user_id}", response_model=UserSummary)
    def change_user(request: Request, user_id: int, body: UserPatch) -> UserSummary:
        """Give a user the Google address they sign in with, change it, or take
        it away (null): their Google sign-ins with the old address end. The
        owner's only, and not in the demo."""
        owner_only(request)
        not_in_demo()
        try:
            return UserSummary.model_validate(
                require_writes(request).set_user_email(user_id, body.email))
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # --- signing in -------------------------------------------------------------

    @app.get("/v1/auth/config", response_model=AuthConfig)
    def auth_config() -> AuthConfig:
        """How one may sign in here, asked before there is a password: the
        Google button is shown only when this names a client id. Open."""
        return AuthConfig(google_client_id=google.client_id if google else None)

    def sign_in_with(credential: str) -> SignedIn:
        """A sign-in token for the address Google's ID token is for: the
        owner's (`GROCERY_OWNER_EMAIL`), or a user's, made at their first
        sign-in. Who may sign in at all is Google's to say: while the consent
        screen is in Testing, only its test users get a token (the owner,
        2026-10-14: the People card's invitations repeated that list)."""
        if not writes_available:
            raise HTTPException(status_code=503,
                                detail="signing in needs the database (DATABASE_URL)")
        try:
            email, name = google.identity(credential)
        except NotSignedIn as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except GoogleUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        user = None if google.is_owner(email) else (
            repository.user_for_email(email) or new_user(email, name))
        made = repository.start_sign_in(user, email)
        return SignedIn(token=made["token"], role="user" if user else "owner",
                        name=user["name"] if user else None, expires_at=made["expires_at"])

    def new_user(email: str, name: str | None) -> dict[str, Any]:
        """A first sign-in's user, named as Google names them; a name another
        user has already gets their address beside it."""
        name = (name or email.split("@")[0])[:40]
        try:
            return repository.create_user(name, email)
        except ValueError:
            return repository.create_user(f"{name} ({email})"[:60], email)

    if google is not None:
        @app.post("/v1/auth/google", response_model=SignedIn)
        def sign_in_with_google(body: GoogleSignInRequest) -> SignedIn:
            """Trade an ID token from Google for a sign-in token, sent as
            `Authorization: Bearer` from then on (for an app; the page uses
            the redirect below). Open."""
            return sign_in_with(body.credential)

        @app.post("/v1/auth/google/redirect", include_in_schema=False)
        async def sign_in_with_google_redirect(request: Request) -> RedirectResponse:
            """Where Google sends the page's sign-in (its "redirect" mode): a
            form with the ID token, and a `g_csrf_token` that must match the
            cookie of that name Google's script set on this site, so another
            site cannot sign this browser in as someone else. Answers with
            the page, the sign-in token (or what went wrong) after the `#`,
            which never reaches a server; the page keeps it and clears it.
            Redirect, not Google's pop-up: on phones the pop-up often never
            hands its answer back to the page (2026-10-13)."""
            form = await request.form()
            sent, kept = form.get("g_csrf_token"), request.cookies.get("g_csrf_token")
            # Why a sign-in was refused is logged: the answer after the `#`
            # never reaches a server, and a friend's failed sign-in could
            # only be guessed at (2026-10-14).
            if not isinstance(sent, str) or not sent or not kept \
                    or not hmac.compare_digest(sent, kept):
                log.warning("Google sign-in refused: the CSRF cookie %s",
                            "is missing" if not kept else "does not match")
                return RedirectResponse("/#google-error=" + quote(
                    "Google sign-in could not be checked: try again"), status_code=303)
            try:
                made = await run_in_threadpool(sign_in_with, str(form.get("credential", "")))
            except HTTPException as exc:
                log.warning("Google sign-in refused: %s", exc.detail)
                return RedirectResponse("/#google-error=" + quote(str(exc.detail)),
                                        status_code=303)
            return RedirectResponse("/#google=" + quote(made.token), status_code=303)

    @app.post("/v1/auth/sign-out", status_code=204)
    def sign_out(request: Request) -> Response:
        """End the sign-in this request was made with. A password is not
        ended by this: it is not a sign-in."""
        given = request.headers.get("authorization", "")
        if given.startswith("Bearer ") and hasattr(repository, "end_sign_in"):
            repository.end_sign_in(given.removeprefix("Bearer "))
        return Response(status_code=204)

    @app.post("/v1/inbox")
    def claim_inbox(request: Request) -> list[dict]:
        """Uploads a developer should look at (another person's, a PDF, a
        failure), each with what was read from it; each is handed over once.
        The owner's only: `scripts/dev_inbox.py` calls it when a development
        session starts. Not in the demo."""
        owner_only(request)
        not_in_demo()
        repo = require_writes(request)

        def is_pdf(sha256: str) -> bool:
            if image_store is None or image_store.size(sha256) is None:
                return False
            with open(image_store.path(sha256), "rb") as file:
                return file.read(5) == b"%PDF-"

        return repo.claim_inbox(is_pdf)

    @app.get("/v1/inbox/withdrawn")
    def inbox_withdrawn(request: Request) -> list[str]:
        """Job ids of other people's uploads the developer may no longer keep
        (sharing taken back): `scripts/dev_inbox.py` deletes its copies."""
        owner_only(request)
        not_in_demo()
        return require_writes(request).withdrawn_from_inbox()

    @app.get("/v1/inbox/{job_id}/file")
    def inbox_file(request: Request, job_id: str) -> Response:
        """The file an upload sent, as it arrived. The owner's only, and not in
        the demo: one guest must not fetch the receipt photo another sent."""
        owner_only(request)
        not_in_demo()
        sha256 = require_writes(request).job_image(job_id)
        if sha256 is None or image_store is None or image_store.size(sha256) is None:
            raise HTTPException(status_code=404, detail=f"no file for job {job_id}")
        data = image_store.path(sha256).read_bytes()
        return Response(data, media_type="application/pdf" if data[:5] == b"%PDF-"
                        else "image/jpeg")

    @app.delete("/v1/receipts/{receipt_id}", status_code=204)
    def remove_receipt(request: Request, receipt_id: int) -> Response:
        """Take a receipt out of the history, with its lines and the answers on
        them. The page waits a few seconds before calling this, so its Undo
        never needs the server."""
        try:
            photo = require_writes(request).remove_receipt(receipt_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if photo and image_store is not None:
            image_store.delete(photo)  # deleting means deleting (2026-10-15)
        return Response(status_code=204)

    @app.put("/v1/receipts/{receipt_id}/shared", status_code=204)
    def share_receipt(request: Request, receipt_id: int, body: SharedRequest) -> Response:
        """Share this receipt's upload with the developer to make the app
        better, or take it back (owner, 2026-10-15: consent, one tap)."""
        try:
            require_writes(request).share_receipt(receipt_id, body.shared)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.put("/v1/jobs/{job_id}/shared", status_code=204)
    def share_job(request: Request, job_id: str, body: SharedRequest) -> Response:
        """The same for one upload, such as one that could not be read."""
        if not require_writes(request).share_job(job_id, body.shared):
            raise HTTPException(status_code=404, detail=f"no upload {job_id}")
        return Response(status_code=204)

    @app.delete("/v1/me", status_code=204)
    def delete_account(request: Request) -> Response:
        """Delete the asker's account and everything that is theirs: receipts,
        photos, answers, sign-ins (owner, 2026-10-15, the privacy work). A
        user's only: the owner's account is the server. Not in the demo."""
        if asking(request) is None:
            raise HTTPException(status_code=403,
                                detail="the owner's account is the server; it is not deleted here")
        not_in_demo()
        for photo in require_writes(request).remove_account():
            if image_store is not None:
                image_store.delete(photo)
        from grocery_app.api.nearby import forget_unused
        from grocery_app.offers import GERMANY

        # The shops only they used, and what was found around them, go now.
        with repository.session_factory() as session:
            forget_unused(repository, session, datetime.now(UTC).astimezone(GERMANY).date())
            session.commit()
        return Response(status_code=204)

    @app.put("/v1/receipts/{receipt_id}/lines/{position}/counted",
             response_model=ReceiptDocument, response_model_exclude_unset=True)
    def count_line(request: Request, receipt_id: int, position: int,
                   body: LineCountedRequest) -> ReceiptDocument:
        """Leave one line out of the shopper's numbers (a wine bought for a
        friend), or count it again. It stays on the receipt and in the prices."""
        try:
            updated = require_writes(request).set_counted(receipt_id, position, body.counted)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ReceiptDocument.model_validate(updated)

    @app.put("/v1/receipts/{receipt_id}/lines/{position}/skipped", status_code=204)
    def skip_line(request: Request, receipt_id: int, position: int) -> Response:
        """Skip what the app asks about this line: no answer, the line keeps the
        app's guess, and the card comes again after the others."""
        try:
            require_writes(request).skip_line(receipt_id, position)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(status_code=204)

    return app


def default_app() -> FastAPI:
    """The app `uvicorn --factory grocery_app.api.app:default_app` runs.

    `DATABASE_URL` selects PostgreSQL; otherwise `GROCERY_PURCHASES` names the
    purchases.json to serve. This is the one place the real, paid extractor is
    wired in: `GROCERY_READER` picks the API (default) or `claude -p` on the
    subscription, or `gemini`. `GROCERY_TOKEN`, when set, is the password the
    `/v1` routes ask for. `GOOGLE_CLIENT_ID` switches on Sign in with Google,
    and `GROCERY_OWNER_EMAIL` says which Google address is the owner's
    (`google_sign_in.configured`). `GROCERY_IMAGES` says where uploaded photos are
    kept. The matcher asks the model `GROCERY_MATCHER` names
    (`matcher_decider`); identify reads and searches with `GROCERY_IDENTIFY`
    (`identify_decider`).
    """
    import os

    from grocery_app import demo
    from grocery_app import matcher as matching
    from grocery_app.db.migrate import upgrade
    from grocery_app.db.session import database_url
    from grocery_app.nearby import OpenStreetMap
    from grocery_app.offers import Marktguru

    # The migrations run here rather than as a step before the server starts:
    # one Python start instead of two, and every start is a wait for whoever
    # opened the page (Cloud Run stops the server after a quiet spell). A no-op
    # on a current database; a new image still never serves an old schema.
    if url := database_url():
        if demo.is_demo():
            demo.reset(url)  # every start is a fresh demo
        upgrade(url)
        if demo.is_demo():
            from grocery_app.api.images import DEFAULT_ROOT
            from grocery_app.api.images import ENV_VAR as IMAGES

            demo.prune_uploads(url, Path(os.environ.get(IMAGES, DEFAULT_ROOT)))
    repository = default_repository()
    if type(repository).__name__ == "PostgresRepository":
        # Every model call this server pays for is written down (`spend`).
        from grocery_app import spend

        spend.install(spend.database_sink(repository.session_factory))
    matcher = line_matcher(matcher_decider(), matching.default_shops())
    # Identify runs only on uploads, which need PostgreSQL: a server that only
    # serves purchases.json needs no reader and no key.
    identifier = (line_identifier(identify_decider(), identify_searcher())
                  if type(repository).__name__ == "PostgresRepository" else None)
    return create_app(repository, default_image_store(), configured_extractor(), matcher,
                      identifier, token=os.environ.get("GROCERY_TOKEN") or None,
                      resume_after=RESUME_AFTER_SECONDS,
                      pictures=default_pictures(model=GEMINI_MODEL)
                      if type(repository).__name__ == "PostgresRepository" else None,
                      demo=demo.is_demo(),
                      google=None if demo.is_demo() else google_configured(),
                      readers=reading_line(),
                      sorter=sorting_decider()
                      if type(repository).__name__ == "PostgresRepository" else None,
                      forget_photos=True, reread=True,
                      offers=Marktguru()
                      if type(repository).__name__ == "PostgresRepository" else None,
                      offer_judge=offer_judge()
                      if type(repository).__name__ == "PostgresRepository" else None,
                      maps=OpenStreetMap()
                      if type(repository).__name__ == "PostgresRepository" else None)


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


def sorting_decider(kind: str | None = None) -> ClaudeCodeDecider | GeminiDecider:
    """Who reads a product's name for its category (`categorize.read_names`),
    on the identify reader, cached under data/categorized/ as `db categorize`
    caches it."""
    if identify_reader_kind(kind) == "gemini":
        return GeminiDecider(GEMINI_MODEL, "data/categorized", "names-v1", search=False)
    return ClaudeCodeDecider("sonnet", "data/categorized", version="names-v1")


def offer_judge(kind: str | None = None) -> ClaudeCodeDecider | GeminiDecider:
    """Who judges which offers are a person's products (`offer_match.judge`),
    on the identify reader, cached under data/offer-verdicts/."""
    from grocery_app.offer_match import JUDGE_VERSION

    if identify_reader_kind(kind) == "gemini":
        return GeminiDecider(GEMINI_MODEL, "data/offer-verdicts", JUDGE_VERSION, search=False)
    return ClaudeCodeDecider("sonnet", "data/offer-verdicts", version=JUDGE_VERSION)


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
