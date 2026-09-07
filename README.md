# Grocery App

Turns grocery receipts into an item-level purchase history with spending insights.

## Goal

Supermarket and banking apps show what a shop cost, not what was bought. The goal here is the item level:
what I actually buy, how often, and how the price of those items moves over time.

Pipeline: receipt photo -> extraction -> normalization against a product catalog -> purchase history -> insights.

## Current state (work in progress)

- **Extraction**: receipt photos are read with an LLM, currently driven by a prompt I run over a batch of receipts. The extracted receipts live in `data/gold`, gitignored because they are my own shopping.
- **Normalization**: a Python layer that resolves raw receipt lines to a product catalog (`data/catalog.json`) through a resolution map (`data/resolution_map.json`), so the same item is recognised across stores and spellings.
- **Purchase history**: `purchases.json`, built from the extracted receipts by the normalization layer.
- **Demo**: a self-contained static web page (`web/index.html`) presenting the history in a mobile-style layout.

## Next

- Bring the LLM extraction call into the pipeline so a photo goes end to end without a manual step.
  Groundwork is in: a hand-transcribed held-out set (`data/holdout/`, gitignored) and an evaluation
  harness that scores extraction per store and per field — see `docs/receipt-quirks.md` for what
  real receipts turned out to require.
- Serve the history through a FastAPI backend on PostgreSQL, replacing the JSON artifacts.
- Test suite around the normalization layer, then CI on every push.
- Insights on top of the history: personal inflation per basket, repurchase cadence, own-brand vs brand spend.

## Run locally

```bash
python3 -m pip install -e .
# build the purchase history from extracted receipts
PYTHONPATH=src python3 -m grocery_app.cli purchases
# score a directory of extracted receipts against the held-out set
PYTHONPATH=src python3 -m grocery_app.cli eval --pred-dir <dir>
# tests
PYTHONPATH=src python3 -m pytest
open web/index.html
```
