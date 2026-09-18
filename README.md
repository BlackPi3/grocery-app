# Grocery App

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
- **Purchase history**: `purchases.json`, built from the extracted receipts by the normalization layer.
- **Demo**: a self-contained static web page (`web/index.html`) presenting the history in a mobile-style layout.

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
- Serve the history through a FastAPI backend on PostgreSQL, replacing the JSON artifacts.
- Test suite around the normalization layer, then CI on every push.
- Insights on top of the history: personal inflation per basket, repurchase cadence, own-brand vs brand spend.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
source .venv/bin/activate

# fetch the product catalog from the store's own listings (starter categories)
grocery-app catalog
# build the purchase history from the verified receipts
grocery-app purchases
# score a directory of extracted receipts against the verified ones
grocery-app eval --pred-dir <dir>
# tests
pytest
open web/index.html
```

Extraction calls the Claude API and reads `ANTHROPIC_API_KEY` from the environment.
