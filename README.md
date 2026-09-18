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
- **Insights**: `grocery-app insights` reads purchases.json and writes `insights.json`: repurchase cadence with an expected next date, price over time per product, a personal basket index (last month's repeat basket priced at this month's prices), own-brand vs brand share, and the same item across stores. Every figure carries the coverage it rests on.
- **API**: `grocery-app serve` exposes the same two documents over HTTP (`/v1/purchases`, `/v1/insights`, OpenAPI at `/docs`), read-only, from the JSON files or from PostgreSQL (`grocery-app db upgrade`, `db import`, `db export`); the same normalizer runs either way, and a test proves the two agree. The plan for that, and for receipt upload and corrections from a phone, is in `docs/designs/backend-api.md`.
- **Demo**: a self-contained static web page (`web/index.html`) presenting the history and the insights in a mobile-style layout, live at **https://blackpi3.github.io/grocery-app/**. The two JSON files it reads are my real shopping history, published deliberately.

## What it says today

From 27 receipts across 7 stores, 26 June to 29 August 2026. Product-level insights use the 106 of 237 lines (49% of spend) that resolve to a catalog product; the rest counts as money only, and the demo says so in its footer.

- **Price watch**: 10 products bought on more than one date; 3 changed price. The quark went up 30% per kg, avocados came down 25%, the bread rolls up 2%.
- **Personal basket index**: August vs July, over the 5 products bought in both months: 94.0, so last month's repeat basket cost 6% less at August prices. Five products is a thin basket; the index refuses to report on fewer than three.
- **Repurchase cadence**: 10 products with a typical interval; most rest on a single gap between two trips, and the demo labels those "bought twice, N days apart" rather than "every N days".
- **Own brand**: 28% of the resolved spend goes to GLOBUS's own brands (GLOBUS, Jeden Tag and OHO). The status comes from a per-store own-brand list applied when a product enters the catalog; the insight lists the brands still unknown instead of guessing.
- **Same item across stores**: nothing yet. Only GLOBUS lines resolve so far, and the insight says exactly that.

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
- Next on the insights: mark own-brand status on the catalog products, resolve the other stores so the cross-store comparison has data.

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
