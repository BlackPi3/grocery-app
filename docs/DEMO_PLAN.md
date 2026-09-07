# Demo Plan & Build Status

Status of the web demo and the pipeline behind it. Honest about accuracy and thin data.
For the longer-term product ideas, see `ROADMAP.md`.

Last updated: reflects the app as actually built (List/Stats/Scan/History dashboard).

---

## Current status (as built)

| Piece | State |
|---|---|
| Gold receipts (`data/gold/*.json`) | ✅ 9 unique receipts (10 images − 1 duplicate), all reconciled to printed total + tax buckets |
| Catalog (`data/catalog.json`) | ✅ 53 products, structured brand/line/variant/size/organic/own-brand |
| Resolution map (`data/resolution_map.json`) | ✅ every raw string resolves; 0 unknowns |
| Normalizer + CLI (`src/grocery_app/`) | ✅ real join + unit-price derivation; `python -m grocery_app.cli purchases` |
| `data/purchases.json` (the contract) | ✅ 55 records, `contract_version: 1` |
| Held-out eval set (`data/holdout/`) | ✅ 17 hand-transcribed receipts, 6 chains, 184 lines; arithmetic-checked by `scripts/convert_holdout.py` |
| Extraction eval harness | ✅ `python -m grocery_app.cli eval` — per-store field accuracy, missed/spurious lines; 11 tests |
| Web dashboard (`web/index.html`) | ✅ built, verified (screenshots + no JS errors) |
| Deploy | ⏸ deferred (see below) |

Data reality: ~€114 of verified spend across **7 shopping days in one month** (July 2026),
one store (GLOBUS). So monthly-trend, repurchase-cadence and inflation signals are
**thin but real** — they sharpen as more receipts arrive. Stated honestly in the UI.

---

## The interface decision (still holds)

- **Ingestion** (receipt → structured data): offline pipeline. Live scanning is NOT wired up;
  the Scan tab is an honest stub. The photo→LLM path is in progress — see
  `designs/receipt-ingestion-pipeline.md` and `receipt-quirks.md`.
- **Consumption** (the shared demo): a static, mobile-first web app reading `purchases.json`.
  No backend. User edits persist in the browser (`localStorage`).

---

## What was actually built (vs. the original plan)

The demo grew past "read-only insights dashboard" into a small interactive app.
Key deviations from the first plan, and why:

- **No separate `insights.json`.** Insights are computed **in-browser** from `purchases.json`.
  Reason: the exclude/edit/recategorize features must recompute stats live, so the aggregation
  had to be reactive. The durable *normalizer* logic stays in Python; only the light,
  interactive aggregation lives in JS. (A Python insights module can still be added later for a
  FastAPI backend.)
- **List is the home tab, not insights.** The shopping list is the daily-use surface;
  insights are secondary.
- **"Own-brand vs brand" card was removed.** Judged low-value; that slot is reserved for
  product-info (nutrition/allergens) later.
- **The "how it works / accuracy" receipt view was not built.** Optional; can add later.

### The four tabs (current)
- **🛒 List (home)** — predicted needs (from repurchase cadence), recipe chips
  (`data/recipes.json` → ingredients into the list), add-your-own, check-off list.
- **📊 Stats** — monthly spend, ⚠ price watch (repeat items whose €/unit moved),
  spend by category (**editable** categories), savings via Personalrabatt, Pfand net.
- **＋ Scan** — honest stub (no live scanning).
- **🧾 History** — trips with per-item rename / recategorize / exclude, persisted in localStorage.

---

## Deploy (deferred — decision recorded)

Deployment is intentionally **not done**. Rationale:
- The only value of deploying is a **portfolio shareable link**; there's no live scanning for a
  viewer to use their own data, so a local `python -m http.server` suffices until that link is needed.
- Deploying would **publish the real GLOBUS basket** (store, dates, items, prices) to a public page.
- **When we do deploy:** swap in a small **synthetic dataset** so the public demo shows the product
  without publishing real shopping data. Then GitHub Pages for the static link.


---

## Known gaps / cleanup (non-blocking)
- `web/purchases.json` is a **copy** of `data/purchases.json` — re-copy after regenerating the contract.
- A few catalog `net_quantity` sizes still `null` (flagged `needs_review`).
- Categories are fairly granular (24) — could merge some defaults in the catalog.
- Isolated Python env still deferred (currently installed in conda base).
