# Grocery App

Turns grocery receipts into an item-level purchase history with spending insights.

## Goal

Supermarket and banking apps show what a shop cost, not what was bought. The goal here is the item level:
what I actually buy, how often, and how the price of those items moves over time.

Pipeline: receipt photo -> extraction -> normalization against a product catalog -> purchase history -> insights.

## Current state (work in progress)

- **Extraction**: receipt photos are read with an LLM, currently driven by a prompt I run over a batch of receipts. The extracted receipts live in `data/gold`, gitignored because they are my own shopping.
- **Catalog**: `grocery-app catalog` fetches real products from GLOBUS's own category listings (name, brand, price, pack size, barcode), so the catalog comes from the retailer instead of being guessed from receipt abbreviations. Output is gitignored.
- **Normalization**: a Python layer that resolves raw receipt lines to products, split across three files — `data/products.json` (what a product is), `data/resolution.json` (which receipt text means which product, store-scoped and with provenance), and `data/store_listings/<store>.json` (what one store sells it as, with price history).
- **Purchase history**: `purchases.json`, built from the extracted receipts by the normalization layer.
- **Demo**: a self-contained static web page (`web/index.html`) presenting the history in a mobile-style layout.

## Next

- **Done:** the extraction call is in the pipeline — `grocery-app extract` turns a photo into
  structured JSON, scored by `grocery-app eval` against a hand-transcribed held-out set of 17
  receipts across 6 chains. Measured at 1 error in 180 line items. See
  `docs/designs/receipt-ingestion-pipeline.md` for the numbers and
  `docs/receipt-quirks.md` for what real receipts turned out to require.
- **In progress:** product normalization. Extraction produces raw receipt text; only 4 of 154 item
  names resolve against the current catalog. The catalog is now sourced from the retailer rather
  than derived from receipts; next is proposing matches and confirming them by hand to form the
  resolution eval set. See `docs/designs/product-normalization.md`.
- Serve the history through a FastAPI backend on PostgreSQL, replacing the JSON artifacts.
- Test suite around the normalization layer, then CI on every push.
- Insights on top of the history: personal inflation per basket, repurchase cadence, own-brand vs brand spend.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
source .venv/bin/activate

# fetch the product catalog from the store's own listings (starter categories)
grocery-app catalog
# build the purchase history from extracted receipts
grocery-app purchases
# score a directory of extracted receipts against the held-out set
grocery-app eval --pred-dir <dir>
# tests
pytest
open web/index.html
```

Extraction calls the Claude API and reads `ANTHROPIC_API_KEY` from the environment.
