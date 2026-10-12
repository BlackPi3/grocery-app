# Grocery App

[![ci](https://github.com/BlackPi3/grocery-app/actions/workflows/ci.yml/badge.svg)](https://github.com/BlackPi3/grocery-app/actions/workflows/ci.yml)
[![deploy](https://github.com/BlackPi3/grocery-app/actions/workflows/deploy.yml/badge.svg?branch=main)](https://github.com/BlackPi3/grocery-app/actions/workflows/deploy.yml)

Turns grocery receipts into an item-level purchase history with spending insights.

**Try it: [grocery-demo-rk2cowwvmq-ey.a.run.app](https://grocery-demo-rk2cowwvmq-ey.a.run.app)**, best on a
phone. The live app with four months of made-up receipts from four German chains; the products,
pictures, questions and insights are what the real pipeline made of them. Scan a receipt of your own if
you like (ten a day across all visitors): everything you add, photos included, is wiped when the demo
restarts. Every merge to `main` deploys it along with the real server (`grocery_app/demo.py`).

## Goal

Supermarket and banking apps show what a shop cost, not what was bought. The goal here is the item level:
what I actually buy, how often, and how the price of those items moves over time.

Pipeline: receipt photo -> extraction -> normalization against a product catalog -> purchase history -> insights.

## Current state (work in progress)

**Stage, 12 October 2026: in daily use, with a public demo.** The server is online on Google Cloud,
with a password for each person, and every merge to `main` deploys it, together with a public demo that anyone can
open (link above). The demo runs the same code on made-up receipts, in a database of its own that
resets on every start. From my phone I photograph a receipt, Gemini reads it, and the app matches each
line to a product, searching the web before it asks me. The page now has a bottom bar with a + to
scan, and a Home screen with a few things at a glance. A second person can have an account, and an
email alert fires when model spending or traffic is unusual. Next is a simpler set of screens for
people other than me, then the iOS app (work starts once the milestone below is met, aimed at
November 2026).

- **Receipts**: `data/receipts/` holds the photos, one verified transcription per receipt (`truth/`, the schema everything downstream reads), and the hand-typed sources those were converted from (`transcripts/`). All gitignored: it is my own shopping.
- **Extraction**: `grocery-app extract` reads a photo with a vision model (Claude or Gemini) into the same schema; results are cached under `data/extracted/<model>/<prompt version>/` with their cost. The server reads with Gemini: on the verified receipts it got 22 of 27 fully right, with every price right.
- **Catalog**: `grocery-app catalog` fetches real products from the retailer (GLOBUS's category listings; ALDI Süd's JSON API, per branch), so the catalog comes from the store instead of being guessed from receipt abbreviations. Output is gitignored.
- **Normalization**: a Python layer that resolves raw receipt lines to products, split across `data/products/`: `products.json` (what a product is), `resolution.json` (which receipt text means which product — or which *family* of products, when the till prints one name for several — store-scoped and with provenance), `<store>/listings.json` (what one store sells it as, with price history), and `data/receipts/line_resolutions.json` (the shopper's own answer for a line the receipt could not pin down). The full tree is in `docs/data-layout.md`.
- **Enrichment**: `grocery-app enrich` fills what a store listing never says (category, organic label, Nutri-Score, NOVA group) from [Open Food Facts](https://openfoodfacts.org) by barcode, only where the product has no confirmed value. Open Food Facts data is licensed under the [ODbL](https://opendatacommons.org/licenses/odbl/1-0/).
- **Purchase history**: `purchases.json`, built from the extracted receipts by the normalization layer.
- **Insights**: `grocery-app insights` reads purchases.json and writes `insights.json`: repurchase cadence with an expected next date, price over time per product, a personal basket index (last month's repeat basket priced at this month's prices), budget vs name brand share, and the same item across stores. Every figure carries the coverage it rests on.
- **API**: `grocery-app serve` exposes the same two documents over HTTP (`/v1/purchases`, `/v1/insights`, OpenAPI at `/docs`), from the JSON files or from PostgreSQL (`grocery-app db upgrade`, `db import`, `db export`); the same normalizer runs either way, and a test proves the two agree. With PostgreSQL it also takes photos: `POST /v1/receipts` stores the image, returns a job id, and extracts in the background; `GET /v1/jobs/{id}` reports `queued` / `running` / `done` / `failed` with the model's cost. One photo is never extracted twice. A shopper can read a receipt back (`GET /v1/receipts/{id}`), say what a line actually was (`PUT .../lines/{position}/resolution`), correct a receipt's store (`PATCH /v1/receipts/{id}`), and remove a receipt (`DELETE /v1/receipts/{id}`). Every insight can be checked line by line: `GET /v1/products/{id}/purchases` lists a product's purchases with the receipt line each came from, and `GET /v1/receipts/{id}/photo` returns the photo or PDF a receipt was read from, to whoever may see the receipt (in the demo, only the made-up receipts' photos). Each person has their own password and sees only their own receipts (`/v1/me`, owner-only `/v1/users`); the catalog and the memory are shared, and a user's answers weigh less than the owner's. Every paid model call is written down (`model_calls`), so `GET /v1/costs` says what processing cost per month and per receipt: reading the photo, finding the items, product pictures. Every line says who said what it is (`said_by`: you or the app), two random lines the app placed itself per uploaded receipt are put to the shopper as spot checks (`GET /v1/checks`, with the app's mistake rate), and a phone-sized review page at `/` shows both — the corrections land in `line_resolutions` and `db export` writes them back out for the catalog loop. The plan, and what is deliberately not done yet, is in `docs/designs/backend-api.md`.
- **Deployment**: one Docker image on Cloud Run, with Cloud SQL (PostgreSQL) and the photos in Cloud Storage, all in Frankfurt. Every route needs a password; each person has their own and sees only their own receipts. The public demo is a second Cloud Run service from the same image, with its own database and its own database login, which can open nothing else, and it sees only its own folder of the bucket. GitHub Actions deploys both after the tests on `main` pass, signing in to Google without a stored key (Workload Identity Federation). Cloud Monitoring emails me when model spending or traffic is unusual.

## Produce

Loose produce has no barcode, no article number and no brand, so the route that resolves
packaged goods — a store's online catalogue — cannot touch it. `grocery-app produce
propose` matches printed names against a store-independent vocabulary of *kinds*
(`Gurke Stk`, `Salatgurken St` and `Gurken` are all `Gurken`) and writes a CSV to review;
`produce confirm` mints the kinds and resolves them at every store at once. The design,
including what it deliberately does not model, is in `docs/designs/produce-vocabulary.md`.

## Categories

A product id answers "what did this cost last time"; it cannot answer "how much do I spend
on chips", because nothing says that six bags across three shops are the same kind of thing.
`categories.py` is that answer: a closed, three-level German vocabulary — branch, section,
category — lifted from what ALDI SÜD and GLOBUS publish rather than invented, at the
granularity of a shopping list (*Chips*, *Milch*, *Reibekäse*, never *Snacks* and never
*funny-frisch Chipsfrisch Salt & Vinegar 175 g*).

`grocery-app category propose` reads three sources of evidence per product — the shop's own
shelf for anything matched to its catalogue, the Open Food Facts chain, and the printed name
— and writes a CSV to review; `category confirm` writes back only what came back marked. The
rule it runs on is that **a name alone is a question and two independent sources agreeing is
an answer**: the printed name is wrong about one product in twenty-five, always the same way
(`Linsen Chips Paprika` is not paprika), so a row where the shop and the name disagree is
routed to a person rather than settled by a cleverer matcher. The design is in
`docs/designs/categories-and-budget-brands.md`.

## What it says today

From my own 67 receipts, 25 June to 12 October 2026, across ten shops (mostly GLOBUS and ALDI SÜD).
Of the 446 grocery lines, 419 are matched to a product, which is 93% of the €986 spent; the rest counts
as money only. 24 lines that are not groceries (a cigarette pack, photo prints, a café coffee) are
counted apart and left out of every insight.

- **Price watch**: 56 products bought more than once at the same shop (58 product-and-shop pairs); in 34 pairs the price changed. The
  biggest moves are the ones to check first: a halved cola price or a nearly doubled cream cheese can be a
  real change, a special offer, or two different packs matched to one product. Tapping through to the
  receipt behind a number is on the list below.
- **Personal basket index**: each month's repeat basket priced at the next month's prices. September
  against August, over 17 products: 1.7% cheaper; October so far, over 14: 2.8% dearer. Baskets this
  small move with single items.
- **Repurchase cadence**: 66 products bought more than once, 24 of them due again. 42 of those rest on
  a single gap between two trips, and the app says "bought twice, N days apart" rather than
  "every N days".
- **Budget vs name brand**: 34% of the €631 whose brand status is known went to a shop's cheaper line:
  71% at ALDI SÜD, 30% at GLOBUS. €158 sits under "brand not yet known" rather than being guessed.
- **Where the money goes**: a month view splits each month by part of the shop. September, the fullest
  month (24 receipts, €295), led with dairy and eggs (€45.52), then sweet and salty snacks (€42.68).
- **Same item across stores**: 18 products bought at more than one shop. Onions were bought at four;
  carrots ran €1.36/kg at ALDI SÜD against €1.79/kg at GLOBUS. Some pairs are not comparable (one shop
  sells by the kilo, the other by the piece), and the insight shows both units rather than dividing.

## Next

- **Done:** reading receipts. `grocery-app extract` turns a photo into structured JSON, scored by
  `grocery-app eval` against the verified receipts. See `docs/designs/receipt-ingestion-pipeline.md`
  for the numbers and `docs/receipt-quirks.md` for what real receipts turned out to require.
- **Done:** a catalog that grows itself: a memory of confirmed answers, the produce vocabulary, and a
  matcher that picks among real products and asks when it is not sure. See `docs/designs/catalog-growth.md`
  and `docs/designs/what-a-line-is.md`.
- **Done:** the backend, phases 0 to 3: PostgreSQL, photo upload, corrections, a password, and the
  deployment above. See `docs/designs/backend-api.md`.
- **Done:** the first weeks of real use: duplicate photos not kept, categories from the shops' shelves,
  a month view, fewer and clearer spot checks with product photos, undo, and leaving a line out.
- **Done:** a public demo with made-up receipts, accounts for a second person, cost alerts.
- **Now:** "Ready for iOS", targeted for 2 November 2026: the screens settled (yes/no cards with
  pictures, receipts showing plain product names), two weeks of real use without hand fixes, Google
  sign-in, and a second person using it.
- **After:** the iOS app, on the same API, with the share button and the document scanner.
- Later on the insights: roll spend and cadence up by category, and resolve the last stores so the
  cross-store comparison has more than eleven products.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,api]"
source .venv/bin/activate

# fetch the product catalog from the store's own listings (starter categories)
grocery-app catalog
# build the purchase history from the verified receipts
grocery-app purchases
# compute the insights from it
grocery-app insights
# score a directory of extracted receipts against the verified ones
grocery-app eval --pred-dir <dir>
# tests
pytest
# serve purchases.json and the insights over HTTP, OpenAPI docs at /docs
grocery-app serve
# or serve from PostgreSQL: migrate, load the data/ files, serve (DATABASE_URL selects it)
export DATABASE_URL=postgresql+psycopg://user@localhost:5432/grocery
grocery-app db upgrade && grocery-app db import && grocery-app serve
# upload a receipt photo (PostgreSQL only; extraction costs a few cents per photo)
export GROCERY_IMAGES=data/uploads          # where uploaded photos are kept
curl -F file=@data/receipts/photos/IMG_1.jpeg http://127.0.0.1:8000/v1/receipts
curl http://127.0.0.1:8000/v1/jobs/<job-id>
# the review page (PostgreSQL only): what is waiting for you, and every receipt
# with who said what each line is. --host 0.0.0.0 lets a phone on the same
# Wi-Fi open http://<this computer's address>:8000/ -- there is no login, so
# only on a network you trust.
grocery-app serve --host 0.0.0.0 --reader claude-code
```

Extraction calls the Claude API and reads `ANTHROPIC_API_KEY` from the environment;
`--reader gemini` (or `GROCERY_READER=gemini`) reads with Gemini instead, and
`GROCERY_MATCHER=gemini` matches with it, both on `GEMINI_API_KEY`, or through Vertex AI
when `GEMINI_VERTEX_PROJECT` is set (that is how the server runs).

## Development

Every change goes through a pull request, and `main` only takes a PR whose checks are green:

```bash
ruff check src tests   # lint: errors, unused names, import order, bugbear, modern syntax
pytest                 # unit tests per stage, plus tests/test_pipeline.py end to end
```

CI (`.github/workflows/ci.yml`) runs both on Python 3.11 and 3.12 for every push and PR.
Tests use made-up data only; nothing under `data/` is needed to run them.
