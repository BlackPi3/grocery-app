# Grocery App

This project is a portfolio scaffold for a receipt-first grocery intelligence app.

## Vision

The long-term product reads grocery receipts, builds item-level purchase history, and surfaces insights that banks and supermarket apps cannot:

- personal inflation by basket
- repurchase cadence and predicted needs
- own-brand vs brand spend
- store-to-store price comparison

The architecture is intentionally split so the hard parts stay reusable:

1. receipt parsing
2. product normalization
3. purchase history and insight generation
4. demo UI

## Current state

This repository contains:

- a Python package for parsing and normalizing receipts
- a CLI for generating structured JSON artifacts
- a self-contained HTML demo for mobile-style presentation

## Pipeline

```text
receipts/*.jpg
  -> parser
  -> parsed.json
  -> normalizer
  -> purchases.json
  -> web demo / future iOS app
```

## Accuracy note

The parsing layer is intentionally honest. The current implementation is a structured baseline, not a production OCR engine. The repository is designed so accuracy can be measured and reported clearly as the project matures.

## Run locally

```bash
cd /Users/parham/Desktop/grocery-app
python3 -m pip install -e .
PYTHONPATH=src python3 -m grocery_app.cli parse --input data/samples/receipt.txt --output data/samples/parsed.json
PYTHONPATH=src python3 -m grocery_app.cli normalize --input data/samples/parsed.json --output data/samples/purchases.json
```

Then open the web page in a browser:

```bash
open web/index.html
```
