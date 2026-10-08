# Design: What a Line Is

Written 2026-09-27 · Status: identify built and scored (#44, #46-#48); used by the
server since 2026-09-30 (option A below); catalog rewrite not built.

## The mistake this fixes

A receipt line counted as understood only when it pointed at a product that
already existed: in our catalog, or in a shop's online range. When neither had
it, the line became a question for the shopper, even when the printed name
said plainly what it was. `Erdbeeren 400g` at ALDI was a question, because
ALDI's online range has no fresh fruit and our catalog had no strawberries
yet. The matcher was not allowed to say "this is strawberries" in its own
words; it could only pick from real products, a rule meant to stop it
inventing things.

For one shopper that is a question for every new thing bought. For customers
it cannot work: nobody can load every food in the world in advance, and
nobody answers questions about strawberries.

Parham, 2026-09-27: "you should only ask me things that you genuinely can't
find."

## What the insights actually need

| insight | needs |
|---|---|
| price over time | what it is, and the size, for a price per kg or per litre |
| how often it is bought | what it is |
| budget brand vs famous brand | the brand, when the receipt prints one |
| comparing shops | what it is, at each shop |

None needs the shop's exact catalog item. `Erdbeeren` in a 400 g pack and in a
500 g pack are the same thing at a different size; the price per kilo carries
across. Origin (Spanish or Italian strawberries) may matter to a shopper one
day; not now.

## Two levels

**1. What it is: the line's product, always answered by the app.**
The thing all purchases of it share, whatever the shop or pack:

- `name`: plain German, what you would write on a shopping list:
  `Erdbeeren`, `Kartoffelsalat mit Ei`, `Frischkäse Natur`, `Tortilla Wraps`.
  No sizes, no pack counts, no shop wording, no English.
- `category`: a key from `categories.py`.
- `brand`: only when the receipt prints it (`JT` is Jeden Tag), or the shop
  listing says it. Otherwise empty, and the product says so.
- `details`: everything else the receipt prints about the product, as a list
  of any length: a range (`system`), a strength (`400 mg`), a flavour or
  colour (`rot`). Only what is printed. Until 2026-10-09 these were two fixed
  slots, `product_line` and `variant`; the reader guessed which slot a word
  belonged in and guessed differently each time, and neither slot did a job
  of its own (Parham: fixed slots were a presumption). Name, brand,
  category and size stay slots because each feeds an insight.

The **size belongs to the purchase, not the product**: it is read from the
line when printed (`400g`, `1,5l`) or from the exact item when known, and the
price per kilo or litre is worked out from it.

**2. The exact shop item: optional detail, when there is evidence.**
The shop's own entry for that pack: article number, barcode, pack size, and
the listing the price was checked against. It is filled in only when a shop
listing is found and the price paid agrees, as the matcher does today. When
it cannot be, nothing is lost: the line already knows what it is.

## Deciding what it is, and when to ask

For a line the memory does not know, the model reads the printed name and
answers in the format above, or says it cannot tell. It is accepted without
asking when **the printed words support it**: the name, once abbreviations
are expanded (`JT`, `ALN.`, `Kühlschr.`), says the thing. `Erdbeeren 400g`
says strawberries. `FRISCHKÄSE NATUR 200` says plain cream cheese.
`KÜRBISKERNBRÖT. 2er` says pumpkin-seed rolls.

It asks only when the words do not say what the thing is:

- a brand or code alone: `DESTAN`, `Pamir`, `TC Pads 36er` (the variety);
- a name a till prints for anything: `Diverse Lebensmittel`
  (`normalizer.NEVER_REMEMBERED`);
- a word the model does not know: `Lavash` was a guess away.

Measured, as everything else: the answer sheet for the 22 fresh receipts says
what each line was, so the rate of wrong "what it is" answers is scored before
anything is built on it.

## What the shopper sees

A question only for the handful the app cannot find out, one at a time, with
what the app thinks and why. Answers are remembered by the rules already
built (`memory.learn`). Corrections to a machine answer are counted, so the
error rate stays known.

## What changes

- **The catalog's products move to level 1.** Today's 254 products mix
  levels and languages: `Erdbeeren` (level 1), `Bertolli Olivenöl nativ extra
  Originale 500ml` (a shop item, size in the name), `Magerquark (low-fat
  quark)` (half English). Each becomes a level-1 product with its shop items
  under it. This is a migration, run once, and checked line by line: the
  history must say the same things before and after, only in the new format.
- **Shop listings become the level-2 records** under a product
  (`store_listings` already holds article, url and prices).
- **The matcher** first decides what the line is (level 1), then looks for
  the exact item (level 2), instead of only picking among shop items.
- **Insights** key on the level-1 product and the price per kilo or litre.

## Decided

- **The brand is part of what it is** (Parham, 2026-09-27: "they are
  definitely two products"). `Tortilla Wraps, Jeden Tag` and `Tortilla Wraps,
  Mission` are two products: budget-vs-famous is an insight of its own, and
  "all tortilla wraps" is available by grouping on the name.
- **Organic is part of it too**, as `produce-vocabulary.md` already decided
  for produce: `Bananen` and `Bananen Bio` are two products, because the price
  gap between them is what the project measures.
- **Things that are not groceries stay in the history and leave the
  insights** (Parham, 2026-09-27): café, flowers, cards, bags, make-up. They
  sit under the category group `Kein Lebensmitteleinkauf`, and
  `categories.is_grocery` is the one place that says so; a café receipt as a
  whole is not groceries. Built 2026-09-29: every insight reads grocery lines
  only, and `coverage.not_grocery` says how many lines and how much money were
  left out (insights contract 3). A line with no category still counts as a
  grocery: leaving money out needs a reason.
- **Identify goes into the app before the catalog rewrite** (Parham,
  2026-09-30, option A). A line the memory and the shop listings cannot place
  is read by identify instead of becoming a question; its answer is saved as
  identify's (`confirmed_by = "identify"`, open to correction and counted
  when overruled, like the matcher's) and points at a level-1 product: one
  with the same name, brand and details (in any order), or a new one. Until the rewrite, a
  new level-1 product can double an older one named another way; the rewrite
  merges them, and since the history points at product ids nothing is lost.
  The rewrite is a program, not hand edits, so a later change of style is a
  re-run. A level-1 product has no size; since 2026-10-01 the size is read
  from the printed line (`normalizer.printed_size`: `400g`, `0,5 L`,
  `4x100 g`, `10er`, `22St`; only with an explicit unit, and a weight or
  volume only for food), so an identified line has a price per kilo, litre or
  piece. A product's own size still wins where it has one.
- **Search is a step, not an option** (Parham, 2026-10-02; identify v7,
  search s2; `identify.read_line`). A line is read once; a line that is not
  groceries stops there, saved with its category and never searched or asked
  about. Every other line is searched by the code, for the whole printed line,
  the shop and the shop's printed address, however sure the first reading was
  (the v6 mistakes were the confident ones), and read again with what the
  pages said. What was searched is recorded per line; a line whose search did
  not happen waits, neither saved nor asked. A line still unclear after the
  search is asked with the choices the search left, never as a bare name: the
  shopper confirms, the app finds out. Reader and searcher are Gemini through
  Google's API (`GROCERY_IDENTIFY`), chosen on the comparison in
  `docs/evaluations/2026-10-02-search-as-a-step.md`.
