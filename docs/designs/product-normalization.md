# Design: Product Normalization

Written 2026-08-30 · Updated 2026-09-08 · Status: catalog fetcher built, bootstrap in progress

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

- ~~**Other chains.**~~ Answered 2026-09-08: see "The other chains" below. Check before assuming the approach generalizes.
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

## Next step: bootstrap first (decided 2026-09-08)

Option 2 was chosen. Fetch the GLOBUS catalog, propose matches, confirm in bulk,
and let the confirmed set become the eval.

The reasoning that settled it: name similarity alone was measured against all 95
distinct GLOBUS receipt names (not 42 — that earlier count missed
`data/extracted`; the union of gold and extracted is 95). 88 of 95 produce *a*
candidate, but the top hit is usually wrong:

```
Finish Salz 1,2kg    -> apfel-boskoop-2kg-beutel
ALN.MEERSALZ         -> kartoffelsnack-meersalz
Dallmayr Pad Classic -> kaffee-kapseln-dolce-gusto-dallmayr-prodomo
Chips Salt & Vinegar -> chips-salt-vinegar-style        <- right
```

So an eval-first pass would have had the user confirm pairs drawn from a
candidate list that cannot propose the right answer often enough to be worth
confirming. Price and brand have to exist locally before the human step is
worth anyone's time, and those only come from fetching.

## What the fetch turned out to require

Verified against the live site on 2026-09-08 and implemented in
`src/grocery_app/catalog_globus.py`.

- **The published sitemap is two years stale** (`lastmod` 2024-09-16) and the
  category tree has since been reorganised — `frische-produkte` no longer
  exists, it is now `milchprodukte-eier`, `brot-backwaren-fruehstueck` and
  others. Old product URLs still redirect correctly, keyed by article number.
- **Listing pages are the cheap source, not product pages.** One category
  listing request returns 24 products with name, brand
  (`div.product-manufacturer`), price (`.js-unit-price[data-value]`), pack size,
  base price per unit and deposit. That is ~3k requests for the whole catalog
  instead of ~73k. Product-page JSON-LD carries the same fields and is only
  worth fetching for individual confirmations.
- **`?limit=N` is not supported** and silently renders zero product cards; only
  `?p=N` paginates. Pagination must terminate on *no new article numbers*, not
  on card count.
- **Level-2 categories already list products** aggregated across their leaves,
  so the ~124 leaf categories under the three starter branches never need to be
  walked.
- **Not every product has an EAN.** Bakery and counter goods carry a short
  in-house article number (`/117747/baguette-mit-pfefferkruste`). Filtering on
  barcode-shaped identifiers silently dropped them, including
  `Baguette mit Pfefferkruste`, which is on a receipt as `Baguette Pfefferkr.`.
  The catalog is therefore keyed by article number, with `ean` set only when the
  number is barcode-shaped.
- **Prices are observed, not permanent.** Each product records `fetched_at`, or
  comparing a shop price against a months-old receipt line would be
  unfalsifiable.

## Terms of use

Checked 2026-09-08. `robots.txt` permits product and listing pages, disallowing
only account, checkout, navigation, recovery, admin and proxy paths. Neither
`www.globus.de` nor `produkte.globus.de` publishes usage terms restricting
automated access; there is no general AGB or Nutzungsbedingungen page, only
voucher terms. The Impressum asserts copyright over "Texte, Fotos und
grafischen Gestaltungen".

The real constraint is the German sui generis database right (§87b UrhG), which
restricts extraction of a *substantial part* of a database even where individual
facts are not protected. Accordingly: fetch only the categories this user's
receipts actually touch, never mirror the full 73,569-product catalog, do not
reuse their images or description text, and keep `data/catalog/` gitignored like
`data/gold/`.

## Still open

- **Branch-specific pricing.** Whether observed prices are regional defaults or
  Dudweiler's is still unconfirmed; it needs a market-selected session.
- ~~**Other chains.**~~ Answered 2026-09-08: see "The other chains" below.
- **Ground truth for the resolution eval.** `data/gold/`'s 55 raw-name ->
  product_id pairs came from the early LLM prompt and were never fully verified.
  They cannot be the answer key. The user-confirmed bootstrap set replaces them.
- **What counts as the same product.** Whether `Kerrygold Butter 250g` and
  `Kerrygold Butter` are one product or two is the user's judgment call, and it
  has to be settled while confirming the bootstrap set, not after.

## The other chains (checked 2026-09-08)

None of the three can be done the GLOBUS way, for three different reasons.

- **ALDI Süd** returns HTTP 403 from Akamai for every request, including
  `robots.txt` itself, so their crawl policy cannot even be read. That is an
  edge-level refusal of non-browser clients. It could be defeated by spoofing a
  browser User-Agent; deliberately circumventing an access control is not
  something this project should ship. (ALDI Nord serves robots.txt normally, but
  the receipts are ALDI Süd.)
- **Kaufland**: `www.kaufland.de` (the marketplace) is behind a Cloudflare block
  page. `filiale.kaufland.de` serves robots.txt and explicitly disallows
  `/sortiment/das-sortiment`, the assortment listing. Its sitemap holds 6,306
  URLs, of which 4,217 are recipes and only 73 are `sortiment` pages, all brand
  landing pages carrying neither products nor prices.
- **Lidl** is fully open — robots.txt, sitemap, 12,632 product URLs — but sells
  the wrong things. The online range is non-food Aktionsartikel: Esmara 1,558,
  Parkside 1,078, Crivit 773, Lupilu 526, Silvercrest 474, and zero products
  under Milbona, their dairy brand. Lidl does not sell groceries online in
  Germany.

What this changes: for discounters the retailer catalog is not the route.
Across the six discounter receipts there are 50 product lines, and **25 of them
are fresh produce or weighed goods** (Radieschen, Porree, Romatomaten, Zwiebeln,
Nektarinen) that carry no barcode and appear in no catalog anywhere. Those need
a small hand-written produce vocabulary, shared across every chain — cheap, and
the highest-yield work available for the discounters.

Of the remaining 25, the national brands (Coca Cola, Goldbären, Chipsfrisch)
already appear in the GLOBUS catalog, so cross-store matching covers them for
free. Only the discounter own-brands (K-Classic, K-Bio, Cremia, Choviva,
Milbona) need a separate source, and **Open Food Facts** is the honest one:
free, ODbL-licensed, EAN-keyed and built for reuse. Verified German coverage:
Milbona 1,568 products, Gut Bio 822, Combino 193. It carries no prices, but a
discounter offers no catalog price to match against either, so matching there
is name-and-size based and the receipt supplies the price.
