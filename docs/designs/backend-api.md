# Design: The Backend

Status: phases 0 and 1 built (2026-09-18). Phase 2 is under way (the `jobs` table is
built; the routes are not). Phase 3 is specified and not started.
This is the document a future session picks up from; the checklist at the end says where.

## Why a backend

Today the whole product is files: the CLI turns receipt photos into `purchases.json`,
and a static page reads it. That is the right shape for a pipeline and the wrong shape
for a product, because three things cannot be done with files on one laptop:

1. **Read from a phone.** The iOS app (the end goal, see `ROADMAP.md`) needs the history
   over HTTP.
2. **Write from a phone.** The shopper's corrections (which product a line means, a
   receipt to exclude) are the most valuable data the project has, and today they are
   edited by hand in `data/receipts/line_resolutions.json`.
3. **Ingest a new receipt without the laptop.** Photo in, extraction job, review, done.

The backend is those three things and nothing else. Everything the pipeline computes
stays in the pipeline; the backend calls it.

## Principles

- **The contract does not change because it is served.** `GET /v1/purchases` returns
  the same document `grocery-app purchases` writes, byte for byte in meaning. The demo
  page, the iOS app, and the CLI all read one shape. If the API ever needs a different
  shape, that is a new contract version in `purchases.json`, not an API-only format.
- **The pipeline is the backend.** Routes call `build_purchases`, `build_insights`,
  `extract_directory`, and so on. A route that contains business logic is a bug.
- **Files are the developer interface, the database is the runtime store.** The CLI,
  the eval harness, and the tests keep working on files under `data/`. The database
  holds the same data for the server. `grocery-app db import` loads files into it and
  `grocery-app db export` writes them back, so neither side is a dead end.
- **Storage hides behind `Repository`.** Routes depend on the protocol in
  `api/repository.py`. Swapping JSON for PostgreSQL is a new class, not a new route.
- **Honest by construction.** Coverage and unresolved counts travel with every
  document, the same as in the files. The API never hides a parse failure.
- **No personal data in the repo, still.** The database lives outside the repo; test
  fixtures are made up (Musterladen), as everywhere else.

## Shape

```
   photo ──► extract ──► truth JSON ──► normalize ──► purchases ──► insights
                                        (products, resolution, line_resolutions)
                                                   │
                     ┌─────────────────────────────┴───────────────┐
                     │  Repository (protocol)                       │
                     │   JsonRepository   ──  reads data/*.json     │  phase 0
                     │   PostgresRepository ─ reads/writes tables   │  phase 1+
                     └─────────────────────────────┬───────────────┘
                                                   │
                                        FastAPI  (src/grocery_app/api)
                                                   │
                            ┌──────────────────────┼──────────────────────┐
                        web demo               iOS app              CLI (serve)
```

## Phases

### Phase 0: read-only over the files (built)

What exists, in `src/grocery_app/api/`:

| File | Holds |
|---|---|
| `schemas.py` | Pydantic models of `purchases.json` (contract 2, strict) and `insights.json` (contract 1, top level) |
| `repository.py` | The `Repository` protocol; `JsonRepository` (reads the CLI's file on every call) and `InMemoryRepository` (tests) |
| `app.py` | `create_app(repository)`; routes `/health`, `/v1/purchases`, `/v1/insights?as_of=` |

Run it with `grocery-app serve` (installs with `pip install -e ".[dev,api]"`); the
OpenAPI document is at `/docs` and `/openapi.json`. The pipeline test
(`tests/test_pipeline.py`) validates the normalizer's output against the strict schema
and round-trips it through the server, so the schema and the normalizer cannot drift
apart unnoticed.

Decisions made here, and why:

- **Strict purchase schema (`extra="forbid"`).** A schema that accepts anything
  documents nothing. The cost is that adding a field to `normalize_line` means adding a
  line to `schemas.py`; the pipeline test names the missing field.
- **Insights typed at the top level only.** The sections still move with each new
  insight, and no client binds to them yet. Type them when the iOS app does.
- **Insights computed on request, not cached.** Hundreds of lines take milliseconds.
  Caching is a `Repository` concern when it becomes one.
- **No filters on `/v1/purchases` yet.** A filtered document would need its `meta`
  recomputed (receipt count, totals, unresolved list) or it would lie. That
  recomputation belongs in the normalizer as a `summarize(purchases)` function, and
  should be built when a client needs a filter, not before.
- **`/v1` in the path, `contract_version` in the body.** The path version is the API
  surface; the body version is the document. They change for different reasons.

### Phase 1: PostgreSQL storage

Goal: the server no longer needs the laptop's files. Same routes, new repository.

**Stack**: SQLAlchemy 2.0 (typed, `Mapped[]` style), Alembic migrations, `psycopg`
(v3). Both are the boring default and match the FastAPI ecosystem; nothing here needs
async database access at this scale, so the sync engine is fine.

**Tables** (a sketch; the migration is the source of truth once it exists):

```
receipts        id, source_image, transcribed_by, store, store_location, date, time,
                currency, printed_total, printed_savings, tax_buckets jsonb,
                is_duplicate bool, created_at
receipt_lines   id, receipt_id, position, type, raw_name, qty, unit_gross, gross,
                discount, net, tax_class, sold_by_weight, weight_kg, unit_price,
                unit_price_basis
products        id ('p-0001' stays the public id), label, name, brand, product_line,
                variant, size jsonb, category, is_organic, is_own_brand, eans text[],
                open_questions text[], provenance jsonb
resolutions     id, store, raw_name, line_type, product_id (nullable), family_ids
                text[], confirmed_by, confirmed_at, source
                unique (store, raw_name, line_type)
store_listings  id, store, article_number, product_id, name_as_listed, price history
                jsonb, observed_at
line_resolutions id, receipt_id, position, product_id, answered_by, answered_at
```

Two rules carry over from the files (`docs/data-layout.md`):

- **Truth stays uninterpreted.** `tax_class` in `receipt_lines` is what the paper
  printed. The rate lives in the normalizer's table, not in a column.
- **A receipt never holds a `product_id`.** Resolution is a join through
  `resolutions` and `line_resolutions`, at read time, by the normalizer.

**Purchases are derived, not stored.** `PostgresRepository.purchases()` loads
receipts, products, resolutions and line resolutions into the dict shapes the
file loaders produce and calls the same `assemble_purchases` the CLI calls. Storing purchases would be a second source of truth
that goes stale the moment a resolution is confirmed. If it is ever too slow, cache
the document with an invalidation key; do not persist it.

**Commands**: `grocery-app db upgrade` (Alembic), `grocery-app db import` (files to
tables, idempotent, keyed by `source_image`, `p-xxxx` ids and the other natural keys),
`grocery-app db export --out DIR` (tables to files in the data/ layout, so `eval` and
the tests keep their inputs; it never writes into data/ unasked). Export round-trips
content, not formatting or entry order.

**Configuration**: `DATABASE_URL` in the environment; absent, `serve` falls back to
`JsonRepository` and says so on startup.

**Tests**: a PostgreSQL service container in CI (`services:` in the workflow), the
repository tested against it with the Musterladen fixtures, and one more pipeline
seam: import the fixture files, serve, and compare with `build_purchases` on the same
files. SQLite is not a substitute here; `jsonb` and arrays are used on purpose.

Definition of done: `grocery-app serve` with `DATABASE_URL` set serves the same
`/v1/purchases` as without it, proven by the seam test.

### Phase 2: writes

Goal: the phone can add a receipt and correct a line. These are the two write paths
the product is about; nothing else gets a write endpoint until they work.

| Route | Does |
|---|---|
| `POST /v1/receipts` (multipart photo) | Stores the image, creates an extraction job, returns `202` with the job id |
| `GET /v1/jobs/{id}` | `queued` / `running` / `done` / `failed`, with the receipt id when done |
| `GET /v1/receipts/{id}` | The extracted receipt in the truth schema, plus which lines resolved and how |
| `PUT /v1/receipts/{id}/lines/{position}/resolution` | The shopper's answer for one line: a `product_id` from the family, or `null` to withdraw it. Writes `line_resolutions`. |
| `PATCH /v1/receipts/{id}` | `is_duplicate`, `store` correction, nothing else |

**Jobs** (built, `db/models.py`): a `jobs` table and a worker loop in the same process
(FastAPI `BackgroundTasks` is enough for one user; a queue is a later problem).
Extraction costs money per call, so the job stores the model, prompt version, request
id, token usage and cost — the same facts as the `.meta.json` sidecar `extract` writes
today — and a photo is never extracted twice for the same image hash.

Four decisions the table encodes:

- **The row is the record; the queue is a hint.** A queue forgets an item once a worker
  takes it, and `BackgroundTasks` is an in-process list that dies with the process. So
  the row is written and committed *before* any work is scheduled. Recovery, if it is
  ever needed, is a startup scan for `queued` rows; moving to Redis later changes the
  line that schedules work and nothing else.
- **`jobs.image_sha256` is indexed, not unique.** It answers "have I already paid to
  read this photo?" before a model is called. Unique would forbid re-extracting one
  photo under a new `prompt_version`, which is deliberate work this project does.
  `receipts.image_sha256` is likewise not unique: two photos of one paper are a
  duplicate receipt (`is_duplicate`), a judgement rather than a constraint.
- **The id is a uuid.** It is the one id a client holds and quotes back.
- **`cost_usd` is `Numeric(10, 5)` and stays in dollars.** The provider bills in
  dollars and one extraction costs fractions of a cent; converting to euros would mean
  inventing an exchange rate for a date. It is not the `Money` type, which is euros off
  a receipt. A job also outlives the receipt it produced (`ON DELETE SET NULL`): what
  was spent was still spent.

**A model-extracted receipt is not truth.** It enters `receipts` with
`transcribed_by = "llm"`, and the eval harness keeps scoring the model against the
hand-verified set. The UI marks such receipts until the shopper has looked at them.

**Corrections feed the catalog work.** A line resolution from the phone is exactly
what `line_resolutions.json` holds today; `db export` writes it back so the
`propose`/`confirm` loop on the laptop sees it.

### Phase 3: identity and deployment

- **Auth**: one user, one bearer token from the environment, checked by a dependency
  on every `/v1` route. Sign in with Apple comes with the iOS app, and a `users` table
  with it; every table above gains a `user_id` then, not before.
- **Deployment**: a `Dockerfile` (python:3.12-slim, `pip install .[api]`, uvicorn) and a
  managed PostgreSQL. Fly.io or Railway both fit; the choice is cost, not architecture.
- **The demo page**: keeps reading static JSON, with an optional `?api=` origin that
  fetches `/v1/purchases` and `/v1/insights` instead. Same documents, so no page
  change beyond the fetch URLs. The static copy remains the fallback for the
  shareable link.

## Conventions

- Paths are `/v1/...`; bodies carry `contract_version`.
- Bad input is `422` with a `detail` string naming the parameter (FastAPI's default
  shape for validation errors is kept as is).
- Dates are ISO `YYYY-MM-DD` strings, as in the files. Money is a float in euros, as
  in the files, until the day a second currency shows up.
- Every document that computes something says what it rests on (`coverage`,
  `meta`). New endpoints follow that rule.
- Tests use made-up data and the `TestClient`; nothing under `data/` is read by a test.

## For the iOS app

- Generate the client models from `/openapi.json`; the Pydantic schemas are the single
  definition. This is why the purchase record is typed strictly.
- The documents are small (hundreds of lines per year of shopping). Fetch them whole;
  pagination and delta sync are not needed until they are measured to be.
- The write paths in phase 2 are designed for the phone first: photo up, job id back,
  poll, then correct a line with one `PUT`.

## Open questions

- **Where do products and resolutions get edited once the DB is live?** The current
  answer is: on the laptop, through `propose`/`confirm`, then `db import`. A phone
  flow for confirming a proposal is plausible and unspecified.
- **Multi-currency.** The truth schema has `currency`; the insights assume one. Not a
  backend question, noted so it is not forgotten.
- **Delta sync for iOS.** Not needed at current sizes; revisit when a document is
  measured over a few hundred kilobytes.

## Picking this up

Phase 1, in order:

1. `pip install -e ".[dev,api]"`, `pytest`, then `grocery-app serve` and open
   `/docs` to see phase 0 running.
2. Done: `sqlalchemy`, `alembic`, `psycopg[binary]` are in the `api` extra.
3. Done: `src/grocery_app/db/models.py`, migration `0001`, `grocery-app db upgrade`,
   and `tests/test_db.py` (runs against the PostgreSQL service in CI; skipped without
   `DATABASE_URL`, and there is no local PostgreSQL on the dev machine yet, so
   `brew install postgresql@16` is the first thing to do before working on step 4).
4. Done: `PostgresRepository.purchases()` in `api/repository.py` calls
   `normalizer.assemble_purchases` on the dicts `db/io.py` builds from the rows.
5. Done: `grocery-app db import` (idempotent, natural keys) and `db export --out DIR`.
   A key the tables have no column for fails the import rather than being dropped.
6. Done: the PostgreSQL service in CI and the seam test
   (`tests/test_db.py::test_import_then_serve_matches_the_files`).
7. Done: `serve` and `default_app()` pick PostgreSQL when `DATABASE_URL` is set.

Phase 1 is complete. Phase 2, in order:

1. Done: the `jobs` table, `receipts.image_sha256`, migration `0003`, and the job
   tests in `tests/test_db.py`.
2. `ImageStore` beside `Repository`: `put(sha256, data)` / `path(sha256)`, with
   `DiskImageStore(root)` from `GROCERY_IMAGES` as the only implementation. Object
   storage (R2/S3) is the phase 3 swap; the protocol is what makes it a swap. Store
   the bytes as uploaded, not the downscaled copy `prepare_image` makes, so a better
   prompt can be run against the original.
3. `POST /v1/receipts` and `GET /v1/jobs/{id}`, with the runner. `create_app` takes
   the extraction function as an argument, defaulting to `None` rather than to the
   real one, so no test can reach a paid API by forgetting an argument. The runner
   takes a `job_id` and opens its own session: the request's session is closed by the
   time a background task runs. `python-multipart` goes in the `api` extra for
   `UploadFile`.
4. `GET /v1/receipts/{id}`, `PUT /v1/receipts/{id}/lines/{position}/resolution`,
   `PATCH /v1/receipts/{id}`. Writes need a repository that can write: keep
   `Repository` as the read protocol, add a write protocol, and register the write
   routes only for a repository that satisfies it, so the file-backed server keeps
   serving reads.

Each step is one PR with tests on made-up data (`CLAUDE.md` rules apply: every branch
gets a PR, CI must be green).
