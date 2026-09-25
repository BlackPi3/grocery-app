# Design: The Catalog Grows Itself

Written 2026-09-24 · Status: all six steps built (2026-09-25).

## Why

On 2026-09-24 the app was tested on receipts it had never seen: 22 photos from
31 August to 24 September, read by the same model and prompt as always, and
uploaded through the laptop server exactly as a phone would. It recognised
**30 of 135 product lines, €50 of €300**. On the 27 receipts the catalog was
built from, the same code recognises about 93%.

The reason is simple. A line is recognised only when its exact printed name at
that store has been seen before. Anything new — a new product, or a known one
printed slightly differently — comes back unrecognised, and the only way it
ever becomes known is a review session on the laptop (`propose`, a CSV,
`confirm`). That scales with the shopper's attention, which is the one resource
the app must not spend.

Parham's requirement, in his words: "it's of utmost importance that we can
automatically extend the catalog. I can't be manually verifying everything. We
need a learning thing, which asks the user when in doubt, or takes feedback
from the user."

## What was decided (2026-09-24)

1. **The server resolves new lines itself.** Nothing waits for a laptop session.
2. **It accepts an answer without asking when two independent sources agree**,
   the rule that made the category migration trustworthy: a name alone is a
   question; two sources agreeing is an answer.
3. **When unsure, it asks the shopper one short question**: "is it one of
   these?", plus "none of these, it's …".
4. **Answers are remembered and apply to the next receipt at once.** There is no
   separate promotion step. This replaces the stance in `backend-api.md` that a
   shopper's answer stays provisional until confirmed on the laptop.
5. **A machine answer the shopper corrects is new information, not noise.** The
   correction replaces the remembered answer, and the machine's mistake is
   counted, so the rate of wrong automatic answers is always known.
6. **Every claim is scored against a test set** kept apart from what the
   matcher learns from.

## The memory

The memory is the table `resolution.json` already is: **(store, printed name)
-> product.** It is not a rule engine. It is what a person does: you do not work
out what `JT` means each time, you remember it.

It stays small because it grows with the number of *different* things bought,
not with the number of receipts: a household buys a few hundred distinct items a
year. It keeps answers consistent, where asking the model afresh would cost
money each time and could answer differently next week. And it is where
corrections live; without it nothing is learned.

Each entry gains what it needs to be trusted:

- **who decided it**: `shop`, `openfoodfacts`, `model`, or `shopper`. A
  shopper's answer always beats a machine's.
- **a list of names that mean nothing.** `Diverse Lebensmittel` at FK Frisch
  Kauf means the shop never entered the item into its till; on 10 September
  both such lines were Kashk, and the next one could be anything. Names on this
  list never get an entry. Each occurrence is its own question.
- **a price check.** If a remembered name suddenly costs very different money,
  the shop may have reused it for another product. The line becomes a question
  instead of a silent match.

Lookup is spelling-tolerant. The GLOBUS till used to print `SAATENBR?TCHEN` and
now prints `SAATENBRÖTCHEN` (checked on the photo of 8 September); the product
did not change. `?` matches any umlaut. Spelling tolerance stops there: a
trailing code can be the whole difference between two products. `JT Eier 10er FH`
is free-range eggs (*Freilandhaltung*), while `JT Eier 10er`, at €2.49, is the
shop's barn eggs. Anything looser than an umlaut is a candidate for the
matcher, not a memory hit.

## A new line: three ways a product comes to exist

Most unrecognised lines are products the catalog has never held, so growing the
catalog is the main job, not a side case.

**1. The shop lists it: copy the product from the shop.** `Zupfkuchen rund` is on
the GLOBUS site as `Zupfkuchen hoch rund ganz 1100g`. The new product takes the
shop's own name, brand, pack size, barcode where one is printed, and shelf.
Nothing is guessed. Sources: the GLOBUS site search `resolver.search` already
does (the 9,700-product crawl on disk is not the whole range — `JT Penne`,
`Swiffer` and `Alnatura Bulgur` are missing from it), and the ALDI SÜD API.

**2. No shop lists it, but the world knows it: Open Food Facts or the model.**
`Condeli Mac & Cheese`, `TC Pads 36er`. The product is recorded as far as the
evidence goes — brand, product line, category — and what nobody can know from
a till line (flavour, size) stays empty, exactly as `coarse.py` does today.

**3. Nobody knows it: the shopper.** FK Frisch Kauf, `Firouzeh City`, Kashk. The
app asks, and the answer becomes a product whose source is `shopper`. A barcode
scanned at home later can fill in the rest from Open Food Facts.

Two guards apply to all three. **Search our own catalog first**, so a known
product is never created twice (`JT Eier 10er` did exactly that in the test).
And **record where every product came from**, so the weakest ones — made by the
model alone — are the first a question corrects.

## How a line is decided

The sequence is fixed, not an agent choosing its own tools. The same steps run
every time, so the cost is predictable and the steps can be tested one by one.
(During the test, reading receipts through an agent took 4 steps on one photo
and 50 on another.)

1. **Memory.** A spelling-tolerant hit that passes the price check is the answer.
2. **Gather candidates.** Our catalog, the store's catalog and site search, and
   the produce vocabulary; about ten real products per line.
3. **The model decides**, from those candidates only: one of them, or "none",
   with how sure it is and why, as structured output. It cannot invent a
   product, because it can only pick from real ones. (This is retrieval-
   augmented generation in its plain form: fetch the facts, then let the model
   choose among them.)
4. **Accept or ask.** Accept when two independent sources agree, for example
   the shop's listing and the price paid, or the model's pick and the shop's
   shelf. Otherwise the line becomes a question for the shopper.
5. **Create when nothing fits**, by the three ways above.

## The test set

A test set is a list of lines where the right product is already known, used to
score the matcher, like an exam with an answer key. Receipt reading has one (the
verified transcriptions). Matching has none, so today nothing measures the part
of the project `CLAUDE.md` calls the most important.

The first one is the 22 fresh receipts. The machine pre-fills the likely
product for every line from the shop listings and Open Food Facts; Parham
confirms or corrects, once. The answers live in
`data/receipts/product_truth.json`, whose provenance is the shopper, never a
model — the second truth set `grocery-app-two-truth-sets` asked for.

The matcher is always **scored before it learns**: each batch is run against the
memory as it stood before that batch, and only then are its answers added. A
matcher scored on answers it has already memorised is marking its own homework.

The numbers that matter:

- how many lines it answered on its own, and how many of those were right;
- how many it asked about;
- how many new products it created, and from which source.

The threshold for "sure enough not to ask" is set from these numbers, not
guessed.

## What is deliberately not used

- **A knowledge graph.** Product -> brand, product -> category, product -> store
  listing are ordinary tables, and PostgreSQL holds them. A graph database adds
  something to run without answering any question we have.
- **An agent loop.** See the fixed sequence above.
- **Vector search, until measured.** Till names are truncated abbreviations
  (`ALN.BIO MAND.BLANCH.`), which letter-based search usually handles better
  than meaning-based search. It starts letter-based inside PostgreSQL; `pgvector`
  comes in only if the test set shows letter-based search missing matches.
- **Fine-tuning.** A few hundred examples is too few, and the memory plus
  retrieval does the same job and can be corrected.

## Build order

Each step is its own pull request, each scored against the test set from step 2
on.

1. This document.
2. The test set: pre-filled answers for the 22 fresh receipts, confirmed by
   Parham; a `grocery-app eval` mode that scores matching.
3. Spelling-tolerant memory (built 2026-09-25). `normalizer.spelling_key`
   ignores case, an umlaut against its `?`, and a full stop outside a number;
   nothing else. It moved the score from 30 to 36 right, still with none
   wrong. It could not reach the other eight misses, and was not meant to:
   seven are fruit and vegetables remembered at a different shop
   (`Rispentomaten lose` is known at ALDI, bought at GLOBUS), which the produce
   vocabulary answers in step 4, and one is a different name for a known
   product (`Kleenex Ultra Soft W`).
4. The matcher, in three pull requests:
   - **4a, the produce vocabulary** (built 2026-09-25). When the memory has
     nothing for a name at this store, the vocabulary's sure matches answer it
     (`resolution: "produce"`); see `produce-vocabulary.md`. Score: 36 to 43
     right, none wrong, 1 missed (`Kleenex Ultra Soft W`, left for 4b).
   - **4b, the model decides** (built 2026-09-25, `matcher.py`). Candidates
     from our catalog, GLOBUS's search at the shopper's own store
     (Dudweiler) and the ALDI SÜD crawl; the model (through `claude -p`, on
     the subscription, answers cached in `data/matched/`) picks one or none,
     seeing names and sizes but never prices. A pick is accepted only when
     the model calls it `high` **and** the price paid equals the pick's
     listed price **and** no variant of it (`Bio Mangostreifen`) costs the
     same. Everything else is a question. It proposes; it writes nothing.
     `grocery-app eval-matching --matcher claude-code` scores it.

     What the numbers said while building it:
     - GLOBUS's default prices disagreed with the receipts for 16 of 20
       products; the Dudweiler store's pages agreed for 11. Prices are
       per store.
     - Of the model's picks, `high` ones were 27 right, 0 wrong; `medium`
       ones 1 right, 3 wrong, so only `high` is accepted. That was tuned on
       this set, so the next receipts are the real test.
     - Score: **63 right, 0 wrong, 72 asked** (from 43 right with 91 lines
       open). 20 lines answered by the matcher, all right.
     - Why 72 are asked: dm and FK Frisch Kauf have no source but our
       catalog (11 lines); for 49 the right product was not among the
       candidates at all (fresh fruit is not in the ALDI crawl, Kashk is
       nowhere); for 23 it was, and the model either said none — the till
       printed no flavour (`JT Tortilla Wraps`, `Bitter-Getränk`) — or was
       right but not sure, or the price disagreed.
     - **Decided 2026-09-25: a name the till prints for several versions
       (`JT Tortilla Wraps`: Classic or Mehrkorn, same price) is recorded
       as a family, and nobody is asked.** Knowing the version changes no
       number the app shows: the versions share a price, a brand and a
       category, and where versions differ in price the price already
       tells them apart. If the shopper does say which it was, that is true
       for that line only; next week it may be the other one. (An earlier
       note here said "asked once, then remembered"; Parham corrected it
       the same day.) The rule behind it: ask only when the answer changes
       a number.
   - **4c, creating products** (built 2026-09-25, `matcher.new_product`).
     A shop listing the catalog does not hold becomes a product copied from
     it: the shop's name, brand, pack size and barcode, and a category only
     when the shop's shelf and the name agree. `provenance` says which shop
     listing it came from and who decided (`matcher` or `shopper`).
     **Decided: 4c builds the product and saves nothing**; step 5 saves a
     product together with the printed name that led to it, whether the
     answer came from the matcher or the shopper, so there is one way of
     writing to the catalog.

     On the test set, accepting would create 17 products, all from GLOBUS,
     all for lines answered right. 10 get a category; 7 carry
     `category unknown`: three where shelf and name disagree
     (`Kühlschrank Deo` on the kitchen-cleaner shelf), four where there is
     too little to go on (`Bio Bulgur`: the vocabulary has no grain but
     rice). Ten GLOBUS shelves were added to `categorize.SHOP_PATHS`, only
     where a shelf is plainly one of our categories or sections.
5. **5a, remembering answers** (built 2026-09-25, `memory.py`). A shopper's
   answer on a line now also teaches the memory what the printed name means
   at that store, so the next receipt needs no question:

   | held | answer X | afterwards |
   |---|---|---|
   | nothing | X | X |
   | a machine's answer Y | X | X, and the mistake is logged in `corrections` |
   | a person's answer Y | X | the family {Y, X}: the till prints one name for both |
   | a family | X | the family, with X added if it was not in it |

   The answer itself stays true for its own line. Names on
   `normalizer.NEVER_REMEMBERED` teach nothing and are never looked up:
   FK Frisch Kauf's `Diverse Lebensmittel`, `Brot und Backwaren` and
   `Exportware /Haushaltsware` (decided 2026-09-25). Withdrawing an answer
   takes back the line's answer, not what the name was learned to mean.

   **5b, the matcher on the server** (built 2026-09-25, `api/matching.py`).
   After a photo is read, and before its job says `done`, every product line
   the memory cannot place goes to the matcher. An accepted answer is saved to
   the memory as the matcher's (`confirmed_by = "matcher"`), with any new
   product copied from its shop listing, listing and price included. A line
   it cannot settle becomes a row in `questions`, holding everything the
   matcher saw. `grocery-app db match` does the same for receipts already
   stored. A matcher that fails leaves the receipt stored and says why.

   The model can now also answer "one of these versions" (`versions`,
   prompt v2), and a line is recorded as that family, unasked, when the
   model is sure and the price paid is one of theirs. On the test set:
   **68 right, 0 wrong, 4 unchecked, 63 asked** (from 63 right, 72 asked);
   9 lines became families (`JT Tortilla Wraps`, `Bitter-Getränk`,
   `Mövenpick Eis`, …). To watch: a family creates a product for every
   version, so accepting everything would create 42 products, about 30 of
   them versions never known to have been bought (8 flavours of Mövenpick).

   **5c, the questions list** (built 2026-09-25). `GET /v1/questions` lists
   every line nothing could place, oldest receipt first, with the matcher's
   candidates where it ran, its pick and its reason, and `per_line` for the
   names that are never remembered. It is derived on each call, so a line
   stops being a question the moment anything places it. Families are never
   questions. `meta` carries the machine's record: how many names the memory
   holds on the matcher's word, and how many machine answers were overruled.

   An answer goes through the one existing route, `PUT
   .../lines/{position}/resolution`, in exactly one of three ways: a
   `product_id` from the catalog; a `candidate` number from the question (a
   shop listing the catalog lacks becomes a product, decided by the shopper);
   or `new_product` with a name, for "none of these, it's Kashk", which
   makes a product holding only what was said, with `brand unknown` and
   `category unknown` as open questions. Either way the answer is then
   remembered by 5a's rules.

   The original plan for this step read:
   The list of meaningless names, moved here from step 3: it exists to stop
   an answer being remembered for `Diverse Lebensmittel`, and nothing
   remembers answers until this step. Questions and corrections through the
   server: `PUT .../resolution` learns to
   create a product from an answer and to replace a machine answer, and a
   `questions` endpoint lists what is waiting. Until there is a phone screen,
   questions are put to Parham in the chat, through that endpoint.
6. Housekeeping (2026-09-25): the fresh receipts moved into the real
   history, and the subscription reader.

   - **The subscription reader** is its own pull request, held until the
     one paid test can run (the API account was out of credit on
     2026-09-25).
   - **The real history is the `grocery` database from now on.** It was
     behind the files (schema 0002, 99 products); it was backed up to
     `data/backups/`, upgraded, and loaded with the files (`db import`), and
     the 27 original receipts come out of it line for line as they do from
     the files. The 22 fresh receipts went in as model readings
     (`db add-readings`, `transcribed_by = llm`), then the matcher ran
     (`db match`: 18 answers, 7 families, 47 products from shop listings),
     then Parham's answer sheet was given to the open questions
     (`db answer`: 16 answered). New products and answers now live in the
     database; the files are what `db export` writes. `web/purchases.json`
     is unchanged: it still shows only the hand-verified receipts.
   - Result on the fresh receipts: **89 of 135 lines placed, €190 of €300**
     (on 24 September: 30 lines, €50). 60 questions are open, 46 of them
     from the fresh receipts: 41 whose answer on the sheet is a description
     rather than a product ("lemon, premium, 1"), which is not turned into a
     product name without the shopper, and 5 whose shop article was not
     among the matcher's candidates.

   The fresh receipts are now what the matcher has learned from, so they no
   longer test it. The next batch of receipts is the untouched test: score it
   (`eval-matching` against an export of the database as it stood) before
   its answers are added.

## Open questions

- **Non-grocery lines.** The dm receipt of 17 August has groceries (tea, coffee
  pads, spaghetti) alongside non-food items; one receipt is a café breakfast. The
  receipts stay; whether their non-food lines count in spending insights is not
  decided.
- **Receipts that do not add up.** Two fresh receipts are €0.50 off their printed
  total. The reader records it; nothing acts on it yet.
- **A missing store name.** Three older GLOBUS photos have the header cut off.
  The reader rightly leaves `store` empty, so nothing on them can match. A
  question ("which shop was this?") fits the same questions flow.
