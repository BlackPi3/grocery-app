# Roadmap & Idea Backlog

Captured product ideas and the guiding principle for how we build. This is a
*thinking* document — nothing here is committed scope. It records intent so we
don't lose it between sessions.

---

## Guiding principle: start small, grow incrementally

We do **not** try to ship a full-featured app on day one — it's too complex and
would collapse under its own weight. Build a small, honest core, then add one
capability at a time.

**Suggested initial core (the MVP surface):**
1. Scan receipts (offline pipeline for now; live scanning later)
2. Build a purchase history
3. Ask the user for corrections (names, categories, exclusions)
4. Show insights on top of that history

Everything else below is layered on *after* that core feels solid.

---

## Idea backlog

### 1. Product context matters more than discounts
A shopper may not care much about a 10% saving, but they *do* care about what a
product **is** — nutrients, whether it's Bio/organic, allergens, origin, etc.
→ De-emphasize the savings framing; prioritize **product-info enrichment**
(nutrition table + allergens + organic), attached to the catalog entry by
`product_id`. (Already the top FUTURE item; this note raises its priority and
reframes *why* it matters.)

### 2. Presentation style / user personas  *(very far down the road)*
Different users want very different UIs: some love flashy, image-rich layouts;
others are overwhelmed by that and want minimal. Idea: define **personas**, and
when a persona is active the **whole UI adapts** to match it.
→ Near term: **start minimalist** (the current dashboard is deliberately clean).
→ Long term: persona-driven theming/layout switching. This is ambitious — parked
far out.

### 3. Suggestion list for what to buy
Predicted/suggested items to buy. **Already built** (List → Predicted needs +
Buy again), driven by repurchase cadence. Room to grow as more data arrives.

### 4. Share the list with others
Let a user share their shopping list with someone else (partner, flatmate).
→ Implies real state/identity/sync — a **backend concern**, not the static demo.
Needs an account model. Parked until there's a backend.

### 5. Recipes → ingredients into the list
Selecting a recipe dumps its ingredients into the list. **Already built**
(List → recipe chips, from `data/recipes.json`). Could grow: quantities,
servings, matching ingredients to catalog products.

### 6. Two lists: urgent vs. can-wait
Split the shopping list into **urgent** items and things that **can wait**. This
should also influence **how we recommend** — e.g. overdue predicted needs land in
"urgent", nice-to-haves in "later".
→ Affects both the List UI (two sections/lists) and the recommendation logic.

### 7. In-store findability — help people locate items
Finding a specific product in a large supermarket is genuinely hard. Could we help
users **locate items in the store** — aisle/section, an ordered walk-through of
their list by store layout, "where is X"?
→ Needs **store-layout / planogram data** per store (aisle → product mapping),
which retailers rarely publish — the hard part is the data, not the UI. Might
start coarse (category → typical aisle) before anything store-specific. Big idea,
data-dependent.

### 8. Scan a product (not just the receipt) for info
Let a user **scan a product** (barcode or photo) and get info about it —
nutrition, Bio/organic, allergens, price history, own-brand alternatives.
→ Barcode (EAN/GTIN) is the clean key; pairs naturally with the **product-info
enrichment** (#1) and the web-crawl enrichment backlog. Note this is a *different
scan* from receipt-scanning: single product lookup vs. whole-basket parse. Could
also **feed the catalog** — a scanned product with confirmed info enriches the
same `product_id` records.

### 9. VAT class as a free signal (essentials split, tax paid, reclassification)
German receipts print a tax class per line (letters whose mapping is printed in
the receipt footer and differs by chain — at Lidl, `A` = 7% and `B` = 19%). We
capture it already in the gold and held-out schemas, so three insights come for
free — no product classification, no enrichment, no extra data source:

- **Essentials vs. discretionary split.** The reduced 7% rate is a legal list of
  foodstuffs — including sweets and chocolate, which surprises people — while 19%
  covers drinks (except milk and still water), alcohol, and all non-food. So the
  split is really *food vs. drink-and-household*, not staples vs. luxuries. That
  gives an honest
  "€180 staples / €60 discretionary" breakdown that would otherwise require
  classifying every product by hand. Trended monthly, it's arguably a sharper
  behaviour signal than total spend.
- **How much tax you pay on groceries.** Directly computable from the same field,
  and a number nobody normally sees. Also decomposes: how much of your VAT comes
  from staples vs. discretionary items.
- **Tax class changes over time.** A product whose class moves between receipts is
  worth flagging — VAT rates do change by law, and products do get reclassified.
  → Caveat: at our data volume, a changed class is *far* more likely to be a
  parser misread or an own-brand product swap than a real reclassification. Treat
  it as a data-quality alarm first and an insight second, or it will cry wolf.

→ Depends on nothing but the tax class surviving the parser into `purchases.json`
— which makes it one of the cheapest insights in this document, and a good early
test of whether ingestion preserves the fields insights actually need.

### 10. Revealed taste preference — "which one did I actually like?"
From the 2026-08-29 interview: for a product like tuna, he wants to know which
variant is *better*, not which is cheaper. Price only matters once quality is
comparable.
→ The interesting part is that this needs **no explicit ratings**. Repurchase is
a revealed preference: buying the same tuna five times and never returning to the
other one *is* the verdict. The purchase history already contains this — it needs
surfacing, not collecting. "You've bought this 6 times and tried that one once"
is an honest answer built from data we already have.
→ Sharpens idea #1: product context matters more than discounts, and the user's
*own* history is the most trustworthy context available.

### 11. Availability before the trip
Same interview: he lives in a smaller part of the city, so a shopping trip where
the wanted items are out of stock is wasted time. Knowing what's actually in
stock before leaving would be valuable.
→ Blocked on **retailer inventory data**, which is harder to get than the layout
data behind idea #7 — real-time stock is rarely public. Related to #7 but
distinct: #7 is *where is it in the store*, #11 is *is it there at all*.
→ Honest near-term substitute: track which items *he* has failed to find or
stopped buying at a given store, from his own history. Weaker than real stock
data, but needs no external source.

### 12. Storage-constrained shopping
Same interview: a small refrigerator means running out mid-week. He wants to buy
in a way that fits limited storage and still lasts.
→ Combines repurchase cadence (#3) with a capacity constraint: not just "you'll
need milk in 3 days" but "you can't hold a week of it". Also argues for the
urgent/can-wait split (#6) — a small fridge forces more, smaller trips, which
makes trip planning matter more, not less.
→ Needs perishability per product, which pairs with the enrichment work in #1.

---

## Where these touch the existing architecture
- Ideas #1 and #8 ride the **catalog + enrichment** layer (keyed by `product_id`
  / barcode) — no receipt/parser changes needed. #8 can even *feed* the catalog.
- Ideas #4 and #6 (sharing, urgency that syncs) push toward a **real backend**
  (FastAPI), which the layered design already anticipates.
- Idea #2 is pure **UI layer** — the disposable part — so it can change freely
  without touching the durable pipeline.
- Idea #7 (in-store findability) is **blocked on external data** (store layouts),
  not on our architecture — flag it as data-acquisition-first.
- Ideas #10 and #12 ride the **purchase history** — #10 needs no new data at
  all (repurchase *is* the preference signal), #12 needs perishability from the
  #1 enrichment work. #11 is **blocked on external data** like #7, and harder.
- Idea #9 (VAT signal) rides the **parser/normalizer** layer: it needs no new
  data, only that `tax_class` is extracted faithfully and carried through to
  `purchases.json`. It is the one idea here that the current ingestion work
  directly unblocks.
