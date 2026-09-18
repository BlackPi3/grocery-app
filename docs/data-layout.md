# The `data/` directory

Everything under `data/` is my own shopping and is gitignored (see the
no-personal-data rule in `CLAUDE.md`). This page is the map, so the layout can
be understood without the files.

Two rules shape it:

1. **Name things by what they are**, not by how they came to exist. The
   pipeline is `receipts -> extracted -> products -> purchases`, and the tree
   says the same.
2. **Keep interpretation out of the truth.** A truth file holds what the paper
   prints: `tax_class` is `A` or `1`, never `7%`, because the receipt does not
   print `7%` on the line. What a class *means* is a normalizer table, per
   store, since Kaufland's `A` is 19% while Lidl's is 7%.

```
data/
  receipts/                     one entry per paper receipt
    images/                     the photos (27; one is a duplicate shot with no truth)
    truth/                      26 verified transcriptions, one schema, `transcribed_by` says how
    transcripts/                the 17 hand-typed sources; scripts/convert_transcripts.py -> truth/
    line_resolutions.json       the shopper's answer for a line the receipt could not pin down
  extracted/<model>/<prompt>/   parser output per photo, with a .meta.json (tokens, cost)
  products/                     what is sold, and what receipt text means
    products.json               one entry per product, opaque `p-0001` ids
    resolution.json             (store, receipt text) -> product, or -> a family of products
    proposals/globus.csv        the review sheet `propose` writes and `confirm` reads
    globus/
      listings.json             article number -> product, with shelf price history
      crawl.json                the old category crawl (superseded by site search)
      cache/                    raw HTML fetched from the shop: listings, _search/, _products/
    aldi-sued/
      crawl.json                SKU -> product, from the store's JSON API, one branch's prices
      cache/<branch>/           raw API responses: category-tree.json, <category>/offsetN.json
      listings.json             written by `confirm` as ALDI matches are banked
    off/<ean>.json              Open Food Facts records, one per barcode, misses included
  purchases.json                the output contract (copied to web/purchases.json for the demo)
```

## What each receipt file contains

`truth/*.json` is the schema every downstream step reads:

- header: `source_image`, `transcribed_by` (`hand` | `llm-verified`), `store`,
  `store_location`, `date`, `time`, `currency`, `printed_total`, and
  `tax_buckets` / `printed_savings` when the receipt prints them;
- `lines`: `type` (`product` | `deposit` | `deposit_return`), `raw_name` exactly
  as printed, `qty`, `gross`, `discount`, `net`, `tax_class` as printed, plus
  `unit_gross` for multi-quantity lines and the `sold_by_weight` fields for
  loose produce.

No `product_id`: a receipt says what was printed, never which catalog entry it
means. Resolution is the normalizer's job, from `products/resolution.json`.

## History

Until 2026-09-18 the receipts were split into `data/gold/` (9 GLOBUS receipts,
extracted by an early LLM prompt and verified against the photos) and
`data/holdout/` (17 hand-transcribed receipts across 7 chains), a train/test
split for a parser that was never built. `eval` only read holdout, `purchases`
only read gold, and each job saw half the receipts. They were merged into
`receipts/truth/`, and the 9 older files were brought onto the shared schema:
model fields (`confidence`, `product_id`, `review_needed`, `reconciled`,
`computed_total`) dropped, `unit_gross` added where `qty > 1`, and `tax_class`
changed from the model's `7%`/`19%` to the `2`/`1` GLOBUS actually prints,
matching the hand-transcribed GLOBUS receipts. The design documents from
before that date use the old paths.
