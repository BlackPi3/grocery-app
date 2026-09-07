# Design: Live Receipt Ingestion Pipeline for Grocery Tracking

Written 2026-08-27 · Status: approved, in progress

## Problem Statement

Track personal grocery spend automatically from receipt photos, surfacing patterns
(price creep on individual items, monthly spend totals) that a bank or card app
cannot show, because bank apps only see "$X at Store Y" — never the line-item
detail (which product went up, by how much, or that you're suddenly buying 30%
more paper towels than usual).

## Demand Evidence

- The founder is the only validated user: he already manually photographs his
  own grocery receipts and wants this tracked with as little manual effort as
  possible.
- A handful of other people have seen the app and found it "interesting" —
  mild social validation, not committed usage.
- A related but distinct feature — suggesting cheaper alternatives across
  stores based on a grocery list — was built and evaluated by a team of 6
  developers for a company considering funding it further. They passed. This
  is real signal against *that specific feature* (cross-store deal matching),
  not against the tracking/insights concept, which was never tested with end
  users.
- **First end-user interview conducted 2026-08-29** (previously: none). Subject
  is an IT professional with an analytical mindset, described by the founder as
  "a very similar personality to me". What he said, in his own framing:
  - **Saving ~10% would matter a lot.** Wants to be told when a similar item is
    cheaper, including at a nearby store he isn't shopping at. He has no way to
    know this today.
  - **Grocery spend is a hidden cost.** You shop quickly and repeatedly, then
    notice at month-end that it added up. Tracking it manually is too much work.
    This is direct confirmation of the app's core thesis.
  - **Small refrigerator.** Runs out mid-week; wants help buying in a way that
    fits limited storage and lasts the week.
  - **Availability before travelling.** Lives in a smaller part of the city; a
    trip where the wanted items are out of stock is wasted time.
  - **Quality comparison, not only price.** For something like tuna, he wants to
    know which variant is *better* — taste, not cost. Implies remembering what he
    has tried and preferred.
  - **Willing to photograph receipts**, unprompted — while noting himself that
    not everyone would be.
- Caveats on that interview, stated plainly: n=1, and the subject was selected
  as someone similar to the founder. It confirms the founder's persona is not
  unique; it does not establish a broad market. Note also the tension with the
  bullet above — his top want (cheaper equivalents across nearby stores) is the
  very feature a company already passed on. A company declining to fund a feature
  and a user wanting it are not contradictory, but they do need separating: this
  is evidence of *user pull*, not of *business viability*.

## Status Quo

The founder currently takes photos of receipts with no systematic tracking
beyond this app. The only alternative anyone has is a bank/card app's
merchant-level spend category, which is coarse (total per store, not per
item) and free. No one else's workaround has been investigated — this is an
acknowledged, explicit gap, not an assumption.

## Target User & Narrowest Wedge

Target user: the founder himself, solving his own problem. The narrowest
thing he said he'd actually use weekly: a single, sharp monthly-spend +
price-creep view. This is largely already computed in the existing Stats tab
(monthly spend, price-watch on repeat items whose unit price moved) — it is
not yet the headline, most legible feature of the app.

## Constraints

- Grocery-only scope, by explicit choice — the founder considered and
  rejected expanding to all personal spend categories (gas, home, clothes)
  for now; he wants groceries working end-to-end first.
- Receipt ingestion is currently offline/manual: the Scan tab is an honest
  stub with no live scanning wired up (per `docs/DEMO_PLAN.md`).
- **"Live" means a real pipeline processes an uploaded photo, not an in-app
  camera.** CLAUDE.md's Demo Philosophy explicitly forbids the web demo
  depending on camera permissions — this design stays inside that: the
  founder takes the photo with his phone's own camera app as he does today,
  then uploads/shares it in; the app never requests camera access itself.
- CLAUDE.md mandates honest accuracy reporting and forbids hand-fixing
  parser output in demos — any ingestion work must be evaluable, not just
  demoable.
- Only one grocery chain (GLOBUS) represented in the current gold dataset (9
  receipts); other stores' formats are untested.

## Premises

1. The wedge the founder said he'd use weekly (monthly spend + price creep)
   is already mostly built in the Stats tab — the next move there is
   surfacing/sharpening it, not building something new.
2. There is no direct end-user validation of the tracking/insights concept
   itself. The one existing data point (6 devs + a company passing on a
   cross-store deal-matching variant) is scoped to that specific feature, not
   to this concept.
3. The real constraint on this becoming usable by anyone beyond the founder
   is receipt ingestion, not insights — every roadmap idea (deals, nutrition,
   budget planning) assumes a data pipeline that currently only works because
   the founder manually feeds it his own receipts.
4. Given 1-3, the founder explicitly chose to defer user-interview validation
   (Approach B) and prioritize a working personal tool (Approach C): build
   live receipt scanning for groceries, scoped narrowly, rather than
   expanding scope or pausing for interviews. This is a conscious trade of
   "validated business" for "working personal tool" — not an oversight.

## Approaches Considered

### Approach A: Sharpen the wedge
Make personal inflation/price-creep the headline, standalone insight in the
Stats tab — one unmistakable number/chart instead of one line among several.
No new data pipeline required. Ships in days. Rejected as the *primary* next
step because it doesn't unblock anything else — it's a polish move, not a
capability.

### Approach B: Validate before building
Pause feature work and run real interviews about grocery-spend pain before
deciding what to build. Rejected for now — the founder has decided this is a
personal tool first; validation is deferred, not abandoned.

### Approach C: Fix the real blocker — live ingestion + evaluation harness
Build the actual receipt-scanning pipeline (photo → structured data) for
grocery receipts, scoped to the stores the founder actually shops at, paired
with a rigorous, honestly-reported accuracy-evaluation harness. This is what
unblocks everything else — a hand-maintained pipeline isn't a "product,"
it's a personal script.

## Recommended Approach

**Approach C**, scoped narrowly:
- Live photo → structured-data parsing for grocery receipts only (not other
  spend categories).
- Prioritize the store formats the founder actually shops at (GLOBUS first),
  accept that other formats may fail initially — that's expected, not a
  blocker.
- Build the accuracy-evaluation harness *alongside* the parser work, not
  after — this matches CLAUDE.md's own suggested development sequence (step
  1: improve the parser, step 2: add evaluation/accuracy reporting) and is
  the only way to know whether changes are actual improvements rather than
  just different failure modes.
- No hand-fixing of parser output, per existing project constraints — errors
  get reported, not silently corrected.

## Open Questions

- **OCR vs. LLM vision for the live-scan step — provisional pick: LLM vision.**
  A local OCR + heuristics pipeline needs hand-built layout parsing per store
  format; a vision model handles messy/varied layouts out of the box and
  matches the "no hand-fixing" honesty constraint better (failures are model
  failures, not brittle regex failures). This is provisional, not locked —
  but the evaluation harness's I/O format (Success Criteria, Dependencies)
  is built against this choice, so revisiting it later means revisiting the
  harness too.
- What accuracy target counts as "good enough" for personal use, and should
  it be tracked separately for item name / price / quantity extraction? Left
  open deliberately — see Success Criteria below for how this gets resolved
  in practice rather than guessed at upfront.
- Image capture mechanics: file size limits, HEIC vs. JPEG, multi-page
  receipts (a long receipt photographed in two shots). Not yet addressed —
  first pass can assume single-image, single-page JPEG/PNG and expand later.
- What does the founder see when a receipt fails to parse? See Failure
  Handling below.
- Beyond GLOBUS, which additional store formats are worth prioritizing next?
  If non-GLOBUS receipts in the held-out set score poorly, that's expected
  and out-of-scope for this pass, not a bug — this design only commits to
  GLOBUS working well.
- LLM vision cost and latency per call are unestimated. Since the evaluation
  harness re-runs the held-out set repeatedly during iteration, this is a
  real recurring cost, not a one-time one — get a rough per-call cost/latency
  number before committing to running the harness on every change.
- User-interview validation (Approach B) is deferred, not cancelled — revisit
  once the ingestion pipeline is trustworthy enough to show people a real
  working product instead of a stub.

## Success Criteria

The founder can photograph a real grocery receipt and get correctly parsed
structured data without hand-fixing. The accuracy target is intentionally
**not fixed in this doc** — it gets set empirically from the first
evaluation run against the assignment's held-out set (below), then written
back into this doc once known, rather than guessed at now. `purchases.json`
remains the single contract driving all insights. Parsing failures are
visible and flagged, never silently hidden or corrected behind the scenes.

**Feasibility risk, named explicitly:** a 10-receipt held-out set (on top of
the 9 in `data/gold/`) is small — accuracy deltas between parser versions
will be noisy at that sample size, especially skewed toward GLOBUS's format.
Treat early numbers as directional, not final; grow the held-out set over
time rather than trusting a single run's percentage.

### Evaluation Methodology

Comparing parser output to the held-out set's ground truth needs explicit
matching rules, not eyeballing: item name matched via the existing
`resolution_map.json` join (not raw string equality — that's what the
resolution layer already exists to handle), price matched exactly (receipt
prices aren't fuzzy), quantity matched exactly. A receipt counts as fully
correct only if every line item matches on all three; partial-match rate
per field should also be reported so "70% correct" doesn't hide whether
failures cluster on name resolution vs. price extraction vs. quantity.

### Failure Handling

Two distinct failure modes, handled differently:
- **Parse failure** (the pipeline runs but produces wrong/incomplete data):
  the founder sees the failure explicitly — e.g. a flagged "needs review"
  state on that receipt in the History tab, alongside the existing per-item
  rename/recategorize/exclude actions — rather than a silently dropped or
  partially-wrong entry in `purchases.json`. Manual re-entry or retry is the
  fallback, not automatic correction.
- **Transport/API failure** (the vision model call itself times out, errors,
  or returns malformed/non-JSON output): treated as a retryable failure at
  upload time, not a data-quality issue — the founder is told the upload
  didn't go through and can retry, distinct from "this receipt parsed but
  looks wrong."

## Dependencies

Existing parser baseline and normalizer (`src/grocery_app/`), the gold
receipt set (`data/gold/`, 9 receipts), and the existing catalog/resolution
map infrastructure (`data/catalog.json`, `data/resolution_map.json`). The
new 10-receipt set from the assignment below is a **held-out evaluation
set** that supplements `data/gold/` — it does not replace or merge into it;
`data/gold/` stays the reference/training data, the new set is what accuracy
gets measured against.

## The Assignment

Before writing any new parsing code: take 10 real grocery receipt photos
under realistic bad conditions (crumpled, faded, bad lighting, different
stores if possible) and manually transcribe the ground-truth data for each,
**using the same schema as `data/gold/`** so the new set is directly
comparable and reusable by the same evaluation tooling. This becomes the
held-out evaluation set. Without it, there's no way to honestly tell whether
the new live-scan pipeline is actually better than the current baseline, or
just different.

## Reviewer Concerns

Issues raised in review that were left open deliberately — to be settled during
implementation rather than guessed at in the doc. Status is tracked inline:

- The "needs review" flag (Failure Handling) implies a schema change to
  `purchases.json` (or a side-channel) that isn't named explicitly. Decide
  which before implementing.
- No defined trigger/threshold for when a receipt gets flagged "needs
  review" vs. silently accepted as correct.
- Evaluation harness implementation location (CLI subcommand vs. standalone
  script) and the exact calculation for aggregating partial-match rate into
  a reportable number are unspecified.
  → **Resolved:** `grocery_app.cli eval` (`src/grocery_app/evaluate.py`). Lines
  are matched by name similarity and price, never by position; per-field exact
  match rates are reported alongside missed and spurious line counts, and a
  receipt counts as correct only when every line matches on every field.
- The History-tab UI work implied by Failure Handling (a new flagged state
  alongside existing rename/recategorize/exclude actions) is real feature
  scope not listed under Recommended Approach's bullets — treat it as a
  required companion change, not a footnote.
- Evaluation Methodology matches item names via `resolution_map.json`, which
  means a failed match for a new/unrecognized item is a normalizer-coverage
  gap, not necessarily a parser error. Early accuracy numbers may conflate
  the two — worth separating "parser extracted the right raw text" from
  "normalizer resolved it to a catalog entry" as distinct metrics.
  → **Resolved:** the held-out ground truth carries no `product_id`, so the
  harness measures extraction only. Resolution coverage is a separate metric.
- No fallback defined for a receipt that *consistently* (not just
  transiently) returns malformed model output — the current retry model
  assumes the failure is transient.
- No duplicate-receipt detection or photo storage/retention policy defined.
