# Design: Product Normalization

Written 2026-08-30 · Status: direction agreed, nothing built

## Problem

Extraction is solved (see `receipt-ingestion-pipeline.md`). It produces raw
receipt text that nothing downstream understands.

Measured against the 17 extracted receipts:

| | |
|---|---|
| distinct item names | 154 |
| resolvable by the existing map | 4 |
| unmapped | 150 |
| Globus-to-Globus overlap (new receipts vs. the 9 gold ones) | 3 of 42 (7%) |

The catalog (53 products) and resolution map (53 entries) were both built from
9 GLOBUS receipts. They do not generalize: widen to six chains and 97% of item
names are strangers. Even the same product from the same store fails when the
printer renders an umlaut as `?` (`SAATENBRÖTCHEN` vs `SAATENBR?TCHEN`).

String normalization does not rescue this. Treating `?` as a wildcard recovers
exactly one name out of 154.

## Direction

**The catalog should come from the store, not from receipts.**

The current catalog was built backwards — derived from what was bought, with a
model guessing what each abbreviation meant. That makes every entry unverifiable
and limits the catalog to items already purchased. Inverting it:

- **catalog** = real products, from the retailer's own published data, existing
  independently of any receipt
- **resolution_map** = the bridge, deduced per receipt line and confirmed by the
  user

This turns resolution from *generation* (invent a plausible product entry, which
is where models hallucinate) into *retrieval* (which of these real products is
this?) — a bounded, checkable question. Brand, size, category and barcode come
from the source instead of being guessed.

It also lowers the cost of the human step. The user confirms a match from a
short ranked list rather than authoring an entry from scratch. That step is
already MVP item 3 in `ROADMAP.md` ("ask the user for corrections").

## What was verified (GLOBUS, 2026-08-30)

Checked with `/browse` against the live site. Verified on three product pages —
the mechanism, not the data. Nothing has been downloaded.

- `robots.txt` on both `www.globus.de` and `produkte.globus.de` permits product
  pages; only account, checkout and navigation paths are disallowed.
- `produkte.globus.de/sitemap.xml` is a sitemap index of gzipped product
  sitemaps — the catalog is enumerable through the mechanism the site publishes
  for that purpose.
- **Every product page carries `schema.org` JSON-LD** with `name`, `brand`,
  `sku` (the EAN barcode), `offers.price`, and availability. The category path
  is in the URL.
- **Own-brand items are present with a proper brand field** — this was the
  make-or-break test, since own-brand staples dominate the basket (12 of 42
  GLOBUS item names are Jeden Tag / GLOBUS / OHO) and never appear in
  promotional flyers.
- Search endpoint is `?query=`. **`?search=` silently redirects to the homepage
  rather than erroring** — a real time-waster.
- Per-branch pages (`globus.de/dudweiler`) are marketing only; they link to the
  same shared shop. Store selection happens inside the shop via a
  `market-selection` widget. Whether branch-specific pricing is reachable was
  not confirmed.

## The matching signal, reordered

The decisive finding. Receipt text and catalog text share almost nothing:

```
receipt:   JT Magerquark 250g            0.69
catalog:   Speisequark Magerstufe        0.69   brand: "Jeden Tag"
```

Not one word in common. Name similarity would never have found this. **Price
matched exactly**, and brand matched once `JT -> Jeden Tag` is known. So the
ranking of matching signals is roughly:

1. **Price** — strongest. The receipt carries it, the catalog carries it.
   Promotional prices differ from regular ones, so it is a strong filter rather
   than a proof.
2. **Brand**, once the chain's abbreviations are learned (`JT`, `ALN`, `OHO`).
3. **Category**, from the catalog's URL path.
4. **Name similarity** — weakest, contrary to first assumptions.

**Receipt naming is a per-chain convention, and conventions are learnable.**
GLOBUS prints `<brand abbreviation> <product> <size>`. Decomposing a receipt
name into those fields makes structured matching possible instead of comparing
opaque strings. Each chain's convention is learned once and is permanent.

## Coverage is reported, never a gate

The catalog is not a reference database of all German groceries. It is *this
user's* products — a few hundred items with a long tail. It is never complete
and does not need to be.

`normalizer.py` already degrades correctly: unknown items get `resolved: false`,
their money still counts toward totals, and they are listed in
`meta.unresolved_items`. Nothing breaks at partial coverage.

So insights split into two tiers:

- **Works at 0% coverage** — total and monthly spend, spend per store, per-trip
  totals, the VAT staples/discretionary split (`ROADMAP.md` #9). These could
  ship on the extracted receipts today.
- **Needs coverage, degrades gracefully** — repurchase cadence, same-item price
  across stores, personal inflation, own-brand share. These run on the resolved
  subset and must state their own coverage ("based on 62% of your items"),
  per the honesty constraint in `CLAUDE.md`.

## Open questions

- **Other chains.** Kaufland has a real online shop. Lidl and ALDI are
  discounters with rotating own-brand assortment and thin product data, and 4 of
  the 17 receipts are ALDI. Check before assuming the approach generalizes.
- **Branch-specific pricing.** Are the observed prices regional defaults or
  Dudweiler's? Needs a market-selected session.
- **Ground truth for the resolution eval.** `data/gold/` has 55 raw-name ->
  product_id pairs, but they were produced by the early LLM prompt (the lines
  carry a model `confidence` field) and were not fully verified. Scoring against
  unverified pairs would measure agreement with an earlier model, not
  correctness — the same correlated-error trap that already inflated one score
  during extraction (see `receipt-ingestion-pipeline.md`). A user-confirmed
  sample is needed first.
- **Terms of service.** `robots.txt` permits the product pages, but read the
  site terms before building anything that fetches at volume.

## Next step (undecided)

Two candidates, deliberately not chosen yet:

1. **Eval first**, as with extraction. Have the user confirm a sample of ~40-50
   raw-name -> product pairs across chains, build the resolution harness against
   it, then build the resolver. The discipline paid for itself twice during
   extraction — it caught a real bug in the extractor and 9 errors in the
   answer key.
2. **Bootstrap first.** Fetch the GLOBUS catalog, propose matches for the 42
   GLOBUS names, have the user confirm in bulk, and let the confirmed set become
   the eval.

The difference from extraction: "correct" here is partly the user's judgment
(whether `Kerrygold Butter 250g` and `Kerrygold Butter` are one product or two),
not a fact readable off the paper. Either path needs the user's decisions before
any score means anything.
