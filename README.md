# Grocery App

[![ci](https://github.com/BlackPi3/grocery-app/actions/workflows/ci.yml/badge.svg)](https://github.com/BlackPi3/grocery-app/actions/workflows/ci.yml)

Turns grocery receipts into an item-level purchase history with spending insights.

## Goal

Supermarket and banking apps show what a shop cost, not what was bought. The goal here is the item level:
what I actually buy, how often, and how the price of those items moves over time.

Pipeline: receipt photo -> extraction -> normalization against a product catalog -> purchase history -> insights.

## Current state (work in progress)

- **Receipts**: `data/receipts/` holds the photos, one verified transcription per receipt (`truth/`, the schema everything downstream reads), and the hand-typed sources those were converted from (`transcripts/`). All gitignored: it is my own shopping.
- **Extraction**: `grocery-app extract` reads a photo with a vision model into the same schema; results are cached under `data/extracted/<model>/<prompt version>/` with their cost.
- **Catalog**: `grocery-app catalog` fetches real products from the retailer (GLOBUS's category listings; ALDI Süd's JSON API, per branch), so the catalog comes from the store instead of being guessed from receipt abbreviations. Output is gitignored.
- **Normalization**: a Python layer that resolves raw receipt lines to products, split across `data/products/`: `products.json` (what a product is), `resolution.json` (which receipt text means which product — or which *family* of products, when the till prints one name for several — store-scoped and with provenance), `<store>/listings.json` (what one store sells it as, with price history), and `data/receipts/line_resolutions.json` (the shopper's own answer for a line the receipt could not pin down). The full tree is in `docs/data-layout.md`.
- **Enrichment**: `grocery-app enrich` fills what a store listing never says (category, organic label, Nutri-Score, NOVA group) from [Open Food Facts](https://openfoodfacts.org) by barcode, only where the product has no confirmed value. Open Food Facts data is licensed under the [ODbL](https://opendatacommons.org/licenses/odbl/1-0/).
- **Purchase history**: `purchases.json`, built from the extracted receipts by the normalization layer.
- **Insights**: `grocery-app insights` reads purchases.json and writes `insights.json`: repurchase cadence with an expected next date, price over time per product, a personal basket index (last month's repeat basket priced at this month's prices), budget vs name brand share, and the same item across stores. Every figure carries the coverage it rests on.
- **API**: `grocery-app serve` exposes the same two documents over HTTP (`/v1/purchases`, `/v1/insights`, OpenAPI at `/docs`), from the JSON files or from PostgreSQL (`grocery-app db upgrade`, `db import`, `db export`); the same normalizer runs either way, and a test proves the two agree. With PostgreSQL it also takes photos: `POST /v1/receipts` stores the image, returns a job id, and extracts in the background; `GET /v1/jobs/{id}` reports `queued` / `running` / `done` / `failed` with the model's cost. One photo is never extracted twice. A shopper can read a receipt back (`GET /v1/receipts/{id}`), say what a line actually was (`PUT .../lines/{position}/resolution`), and mark a receipt as a duplicate (`PATCH /v1/receipts/{id}`) — the corrections land in `line_resolutions` and `db export` writes them back out for the catalog loop. The plan, and what is deliberately not done yet, is in `docs/designs/backend-api.md`.
- **Demo**: a self-contained static web page (`web/index.html`) presenting the history and the insights in a mobile-style layout, live at **https://blackpi3.github.io/grocery-app/**. The two JSON files it reads are my real shopping history, published deliberately.

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

From 27 receipts across 7 stores, 26 June to 29 August 2026. Product-level insights use the 218 of 237 lines (88% of spend) that resolve to a catalog product; the rest counts as money only, and the demo says so in its footer.

- **Price watch**: 21 products bought on more than one date; 12 of them at a different price. Snack cucumbers tripled between June and July; radishes came down a third.
- **Personal basket index**: August vs July, over the 11 products bought in both months: 155.2. The series starts in a June of cheap summer produce, so it reads high; eleven products is still a thin basket, and the index refuses to report on fewer than three.
- **Repurchase cadence**: 23 products bought more than once, 13 of them due. Most rest on a single gap between two trips, and the demo labels those "bought twice, N days apart" rather than "every N days".
- **Budget vs name brand**: 34% of the €312 with a known status goes to a shop's cheaper line — 68% at ALDI SÜD. The status is derived per line from the store and the brand, never stored on the product, and €57.86 sits in "brand not yet read" rather than being guessed at.
- **Where the money goes**: every resolved line now carries a category, so the demo breaks spend down by part of the shop — €92.71 fruit and veg, €84.12 sweet and salty snacks, €68.81 dairy. Two products are still uncategorised, worth €4.38 — the shopper looked and could not remember, which the catalog records as a question rather than a blank.
- **Same item across stores**: 11 products bought at more than one shop. Snack cucumbers run €0.99 at Lidl against €1.11 at ALDI SÜD; redcurrants are not comparable at all, sold by the kilo at one and by the punnet at the other, and the insight says so rather than dividing.

## Next

- **Done:** the extraction call is in the pipeline — `grocery-app extract` turns a photo into
  structured JSON, scored by `grocery-app eval` against the verified receipts (17 of the 26
  were hand-transcribed, across 6 chains). Measured at 1 error in 180 line items. See
  `docs/designs/receipt-ingestion-pipeline.md` for the numbers and
  `docs/receipt-quirks.md` for what real receipts turned out to require.
- **In progress:** product normalization. Extraction produces raw receipt text; only 4 of 154 item
  names resolve against the current catalog. The catalog is now sourced from the retailer rather
  than derived from receipts; next is proposing matches and confirming them by hand to form the
  resolution eval set. See `docs/designs/product-normalization.md`.
- **In progress:** the backend. Phase 0 (a read-only FastAPI layer over the JSON files, with a
  strict schema for the purchase record) is in; phases 1 to 3 (PostgreSQL, receipt upload and
  line corrections, auth and deployment) are specified in `docs/designs/backend-api.md`.
- Test suite around the normalization layer, then CI on every push.
- **Done:** the first insights, computed from purchases.json alone (see "What it says today").
- Next on the insights: roll spend and cadence up by category now that every resolved line carries one, and resolve the last stores so the cross-store comparison has more than eleven products.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,api]"
source .venv/bin/activate

# fetch the product catalog from the store's own listings (starter categories)
grocery-app catalog
# build the purchase history from the verified receipts
grocery-app purchases
# compute the insights from it, then give the demo its copies
grocery-app insights
cp data/purchases.json data/insights.json web/
# score a directory of extracted receipts against the verified ones
grocery-app eval --pred-dir <dir>
# tests
pytest
open web/index.html
# serve purchases.json and the insights over HTTP, OpenAPI docs at /docs
grocery-app serve
# or serve from PostgreSQL: migrate, load the data/ files, serve (DATABASE_URL selects it)
export DATABASE_URL=postgresql+psycopg://user@localhost:5432/grocery
grocery-app db upgrade && grocery-app db import && grocery-app serve
# upload a receipt photo (PostgreSQL only; extraction costs a few cents per photo)
export GROCERY_IMAGES=data/uploads          # where uploaded photos are kept
curl -F file=@data/receipts/photos/IMG_1.jpeg http://127.0.0.1:8000/v1/receipts
curl http://127.0.0.1:8000/v1/jobs/<job-id>
```

Extraction calls the Claude API and reads `ANTHROPIC_API_KEY` from the environment.

## Development

Every change goes through a pull request, and `main` only takes a PR whose checks are green:

```bash
ruff check src tests   # lint: errors, unused names, import order, bugbear, modern syntax
pytest                 # unit tests per stage, plus tests/test_pipeline.py end to end
```

CI (`.github/workflows/ci.yml`) runs both on Python 3.11 and 3.12 for every push and PR.
Tests use made-up data only; nothing under `data/` is needed to run them.
