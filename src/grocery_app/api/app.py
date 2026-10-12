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
"""

from __future__ import annotations

import hmac
import re
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
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
from grocery_app.api.jobs import Extractor, configured_extractor, resume_unfinished, run_job
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
    GoogleSignInRequest,
    Health,
    InsightsDocument,
    JobDocument,
    JobsDocument,
    LineCountedRequest,
    LineResolutionRequest,
    Me,
    NewUser,
    NewUserRequest,
    ProductMatch,
    ProductPurchases,
    PurchasesDocument,
    QuestionsDocument,
    ReceiptDocument,
    ReceiptPatch,
    ReceiptSummary,
    SignedIn,
    UserPatch,
    UserSummary,
)
from grocery_app.insights import build_insights
from grocery_app.matcher import ClaudeCodeDecider, GeminiDecider

__all__ = ["DEFAULT_PURCHASES", "MAX_UPLOAD_BYTES", "create_app", "default_app"]

# The shopper's page (`GET /`): one static file, shipped with the package.
REVIEW_PAGE = Path(__file__).with_name("review.html")
PAGE_WORKER = Path(__file__).with_name("sw.js")

# A receipt photo off a phone is a few megabytes. The cap is not a security
# boundary, it is a promise that one request cannot read an arbitrary amount
# into memory before anyone has looked at it.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# The /v1 routes that answer without a password: they are how one gets one.
SIGN_IN_PATHS = frozenset({"/v1/auth/config", "/v1/auth/google"})


def create_app(repository: Repository, image_store: ImageStore | None = None,
               extractor: Extractor | None = None,
               matcher: LineMatcher | None = None,
               identify: LineIdentifier | None = None,
               token: str | None = None, resume_after: float | None = None,
               pictures: Pictures | None = None, demo: bool = False,
               google: GoogleSignIn | None = None) -> FastAPI:
    if demo:
        google = None  # the demo has no accounts: every guest is the owner
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if pictures is not None and writes_available:
            # Finding pictures reads web pages: a thread of its own.
            app.state.pictures = threading.Thread(
                target=keep_filling, args=(repository.session_factory, pictures),
                name="pictures", daemon=True)
            app.state.pictures.start()
            if hasattr(repository, "picture_wait"):
                repository.picture_wait = CHECK_WAITS_UP_TO  # checks come with theirs
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
        doc = build_insights(seen_by(request).purchases(), as_of=as_of_date)
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
        read and the existing job is being handed back.
        """
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
        if demo:
            from grocery_app import demo as demo_mode

            with repo.session_factory() as session:
                if demo_mode.readings_today(session) >= demo_mode.readings_per_day():
                    raise HTTPException(
                        status_code=429, detail="The demo reads "
                        f"{demo_mode.readings_per_day()} receipts a day, and today's are "
                        "used up. Try again tomorrow.")
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
                  demo=demo)

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

    if google is not None:
        @app.post("/v1/auth/google", response_model=SignedIn)
        def sign_in_with_google(body: GoogleSignInRequest) -> SignedIn:
            """Trade the ID token Google gave the page for a sign-in token,
            sent as `Authorization: Bearer` from then on. Invite-only: the
            owner's address (`GROCERY_OWNER_EMAIL`) or one the owner added on
            the People card; any other verified address is a 403. Open."""
            if not writes_available:
                raise HTTPException(status_code=503,
                                    detail="signing in needs the database (DATABASE_URL)")
            try:
                email = google.email(body.credential)
            except NotSignedIn as exc:
                raise HTTPException(status_code=401, detail=str(exc)) from exc
            except GoogleUnavailable as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            user = None if google.is_owner(email) else repository.user_for_email(email)
            if user is None and not google.is_owner(email):
                raise HTTPException(status_code=403,
                                    detail=f"{email} has not been invited: ask the owner "
                                           "to add it on their People card")
            made = repository.start_sign_in(user, email)
            return SignedIn(token=made["token"], role="user" if user else "owner",
                            name=user["name"] if user else None, expires_at=made["expires_at"])

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
            require_writes(request).remove_receipt(receipt_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
                      google=None if demo.is_demo() else google_configured())


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
