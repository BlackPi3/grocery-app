# Design: The Backend

Status: phase 0 built (2026-09-18). Phases 1 to 3 are specified here and not started.
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
receipts, products, resolutions and line resolutions, and calls the same
`normalize_receipt` the CLI calls. Storing purchases would be a second source of truth
that goes stale the moment a resolution is confirmed. If it is ever too slow, cache
the document with an invalidation key; do not persist it.

**Commands**: `grocery-app db upgrade` (Alembic), `grocery-app db import [--data
data/]` (files to tables, idempotent, keyed by `source_image` and `p-xxxx` ids),
`grocery-app db export` (tables to files, so `eval` and the tests keep their inputs).

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

**Jobs**: a `jobs` table and a worker loop in the same process (FastAPI
`BackgroundTasks` is enough for one user; a queue is a later problem). Extraction
costs money per call (see `receipt-ingestion-pipeline.md` for the numbers), so the job
stores the model, prompt version and cost, the same as the `.meta.json` sidecar does
today, and a receipt is never extracted twice for the same image hash.

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
2. Add `sqlalchemy>=2`, `alembic`, `psycopg[binary]` to the `api` extra.
3. Write the models in `src/grocery_app/db/models.py` from the table sketch above, and
   the first Alembic migration.
4. Write `PostgresRepository.purchases()` in `api/repository.py` by loading rows into
   the dict shapes `normalize_receipt` already takes. Do not reimplement normalization.
5. `grocery-app db import` from `data/`, idempotent. Then `db export`.
6. Add the PostgreSQL service to `.github/workflows/ci.yml` and the seam test.
7. `serve` picks the repository from `DATABASE_URL`.

Each step is one PR with tests on made-up data (`CLAUDE.md` rules apply: every branch
gets a PR, CI must be green).
