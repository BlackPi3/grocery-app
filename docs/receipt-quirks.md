# Receipt quirks observed in the held-out set

Working notes from hand-transcribing `data/holdout/`. Every entry here is a real
behaviour seen on paper, not a hypothetical. This file is the **input spec for
the extraction prompt** — anything listed here is something the vision model has
to get right, and something the evaluation harness will score it on.

Stores represented so far: Lidl, ALDI SÜD (x2), Globus (x4), Kaufland,
SVG Autohof, Eifel West.

## Per-chain differences

| Quirk | Lidl / ALDI SÜD | Globus |
|---|---|---|
| Tax class notation | letters (`A`, `B`) | digits (`1` = 19%, `2` = 7%) |
| Umlauts | printed correctly (`Schokokränze`) | **printed as `?`** (`SAATENBR?TCHEN`) |
| Line discounts | occasional (Preisvorteil) | on nearly every line (personal discount) |

The symbol→rate mapping is printed in the receipt footer and **differs by chain**:
Lidl `A` = 7%, `B` = 19%; Globus `1` = 19%, `2` = 7%. Ground truth records the symbol
as printed; mapping it to a rate is the normalizer's job. (The first transcription
pass wrote Globus's resolved rates; the first extraction run caught that.)

## Transcription convention

**Text is literal; structured values are canonical.**

- Item names, store names, and anything else printed as words are recorded
  exactly as they appear — truncations, capitalisation, `?`-for-umlaut and all.
  Two ALDI branches print `ALDI SÜD` and `Aldi Süd`; both are recorded as
  printed, because the parser is graded on reading the paper, not on knowing the
  brand. Mapping those to one canonical chain is the **normalizer's** job, the
  same way `raw_name` maps to `product_id` through `resolution_map.json`.
- Dates, times and amounts are written canonically (`2026-06-26`, `1.98`) even
  though receipts print `26.06.26` and `1,98`. These have one unambiguous
  meaning, so a canonical form loses nothing — and gold already does this.

A corollary: cross-store price comparison (the top want from the 2026-08-29
interview) needs canonical **store identity**, not just canonical products. That
is a normalizer gap, not a parser one, and it does not exist yet.

## Extraction rules this implies

1. **Transcribe literally; never repair.** Globus prints `?` where an umlaut
   belongs. A model that "helpfully" writes `SAATENBRÖTCHEN` is wrong, even
   though it is more readable. Same for truncated names (`BioBabyWasserme`),
   odd capitalisation (`Apl.Voll.Schokolinse`), and lowercase starts
   (`romatomaten`). Cleaning names up is the *normalizer's* job, downstream.
2. **Weight-priced lines** carry three numbers, not one:
   `2.434 kg * 2.49 EUR/kg` -> `6.06`. All three must survive.
3. **Multi-count lines** print unit price and count: `0.99 * 2` -> `1.98`.
4. **Deposits (Pfand)** are their own line, taxed at the rate of the drink they
   belong to (19% at Lidl), not as food. **Returned empties are a separate case**
   and are named differently per chain — `PFAND` at Lidl, `Retoure Leergut ...`
   at Globus — so the reliable signal is the negative price, not the wording.
   Gold records a return as a bare negative `net` with no gross/discount.
5. **Discounts attach to a line** and are separate from the line price. Keep both
   gross and net — the difference between "the shelf price rose" and "I
   discounted less" depends on it.
6. **Savings recaps** ("Preisvorteil gesamt") are a summary of discounts already
   applied per line. Adding them again double-counts.
7. **Tax class per line** is worth extracting: it is the free food/non-food
   signal behind roadmap idea #9.
8. **Reversed lines (Sofortstorno) must be dropped.** ALDI SÜD prints items that
   were scanned and immediately voided, then prints the replacement purchase
   below. They appear on the paper but were never bought, and the receipt's own
   total excludes them. A model that transcribes everything it sees will invent
   purchases — corrupting both spend and repurchase cadence — so "extract every
   line" is the wrong instruction. The printed total is what proves which reading
   is right.
9. **Weights sometimes appear without a unit price** (Kaufland: `0.208 kg` and a
   line total, no €/kg). Record the weight and leave `unit_price` absent. Do not
   divide the total by the weight to recover it — a derived number the receipt
   never printed does not belong in ground truth, and the parser would be graded
   on inventing it.

10. **Some receipts print no per-line tax class at all** (FK Frisch Kauf), only a
   VAT summary at the bottom. Do not back-solve per-item classes from the
   buckets: it is only unambiguous on short receipts, and on a long one the
   assignment is a subset-sum with many valid answers. Record the buckets at
   receipt level (gold's `tax_buckets`) and leave the per-line class empty —
   otherwise the eval rewards a model for guessing.
11. **Generic line descriptions exist.** The same receipt lists
   `Diverse Lebensmittel` ("various foodstuffs") and `Exportware /Haushaltsware`.
   These parse fine but can never resolve to a catalog product — a normalizer
   problem, not a parser one, and a good argument for scoring extraction and
   resolution separately.
## Model failure modes observed (claude-opus-5, prompt v1, 2026-08-30)

Five errors in 180 lines, all verified against the photos:

- **Brand names get "repaired" into dictionary words.** `Manner` (a wafer
  brand) became `Männer`. The literal-transcription rule in the prompt did not
  stop it. This is the mirror image of the `?`-for-umlaut case: the model added
  an umlaut a Globus printer cannot even produce.
- **Own-brand prefixes on poor print.** `JT` (Globus's "Jeden Tag" line) read as
  `GT` twice on one faded receipt; correct on three cleaner ones. A normalizer
  that knows the chain's own-brand prefixes could absorb this.
- **One tax-class misread** (`B` as `A`) on a 31-line ALDI receipt.

What did *not* fail, across 15 receipts: no line missed, none invented (the
Sofortstorno receipt was handled correctly), every price and quantity exact,
every header field exact.

## Size range

2 to 31 line items. The long ones matter — a model that drops or duplicates a
line in the middle of a 31-line receipt is the failure mode most likely to go
unnoticed, and the printed total is what catches it.

## Open

- Non-grocery stops (SVG Autohof, Eifel West) are in the set. Scope is
  grocery-only, so decide whether they stay as format-variety or are excluded
  from the headline accuracy number.
