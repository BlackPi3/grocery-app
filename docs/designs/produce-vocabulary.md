# Design: Produce

Status: built (2026-09-20). `grocery-app produce propose` / `confirm`, vocabulary in
`src/grocery_app/produce.py`.

## The problem

Packaged goods can be identified from outside this project: an EAN, an article number,
a shop's online catalogue. Loose produce cannot. There is no barcode on a cucumber, no
article number on the receipt, and no brand — and the store catalogues that resolve
packaged goods carry no loose produce at all, so the proposals they generate are noise:

```
Kiwi grün Stück  ->  Joghurt 150 g, Kiwi-Stachelbeere
Gurke Stk        ->  Fleischsalat 400 g, mit Gurke
Schnittkräuter   ->  (nothing)
```

No amount of scraping fixes that. Produce needs a different mechanism.

## The idea

Produce is **generic**, and that is the lever. A cucumber is the same cucumber in every
shop, so one vocabulary entry resolves a name at *every* store at once — where catalogue
work resolves one name at one store. It also means cross-store comparison is easier for
produce than for anything else: comparing two shops' own-brand chocolate is meaningless,
comparing their cucumbers is not.

So a **kind** is what the thing is, not which SKU it was. Kinds become ordinary catalog
products (`brand: null`, `eans: []`, `category: "Produce"`), so nothing downstream needs
a second notion of a product, and cadence, price watch, own-brand share and the basket
index all work unchanged.

## Decisions

- **Granularity follows price, not taste.** The rule: *split when the printed name
  distinguishes something whose price actually differs, and you buy more than one of
  them.* The receipts settle each case. Tomatoes run from €0.99/kg (Rispen, loose) to
  €4.47/kg (San Marzano), so one `Tomaten` product would read a change of variety as
  350% inflation — a false number, which is worse than a missing one. Paprika follows
  colour (rot €2.21 and €3.99/kg, grün €3.61/kg), and colour is printed. Cucumbers
  follow size: a 750 g box of snack cucumbers is not big cucumbers in a bag. Kiwi, by
  the same test, stays one kind — only green has ever appeared, always at €0.49. Split
  it the day a golden one does; that is a catalog edit and the history re-resolves.
- **Splitting later is cheap**, which is what makes the rule safe to apply case by case:
  `purchases.json` is derived on every read, so minting products and editing resolution
  entries re-resolves the whole history with no migration and no backfill.
- **A generic name resolves to a family, not to a guess.** `Tomaten` on a till roll
  genuinely cannot say which tomato. So it resolves to all of them, the shopper settles
  it per line, and the answer is recorded as `resolution: "user"` — the same mechanism
  that already handles `Dove Dusche`, reached with no new machinery.
- **Organic is a separate product**, not a flag on the same one. `Bananen` and
  `Bananen Bio` are different entries because the price gap between them is exactly what
  the project exists to measure; merging them would quietly corrupt any inflation figure.
  `is_organic` still carries the fact for machines.
- **Piece and weight are not compared.** `Gurke Stk` and `Gurken kg` are the same
  vegetable priced on different bases. A cucumber's weight is not on the receipt, so an
  insight refuses the comparison rather than inventing a conversion.
- **The kind name is a label, not a count.** `Gurken` does not claim several were
  bought: quantity lives on the line, in `qty`, `sold_by_weight`, `weight_kg` and
  `unit_price_basis`, which is the only level where "sold by the piece here and by the
  kilo there" is true. Plural for countable produce, singular for herbs and uncountables.
- **The names are German, and that is deferred rather than ignored.** Identity is
  `p-0001`, not the word, so a label is one field per product and every purchase
  re-derives; the alias lists are market-specific by nature. The one coupling to break
  for a second market is that the `VOCABULARY` key doubles as the product name.
- **Origin is not modelled.** It matters — Dutch tomatoes and Italian ones are different
  prices — but it is printed on the shelf label, never on the receipt (checked: zero
  mentions of any country across every printed line). It is also a fact about one
  purchase, not about the product, since the same tomatoes change country by season. It
  would have to be captured at purchase time, which makes it a phone feature.
  `line_resolutions` is the precedent for a per-line shopper-supplied fact.

## How a name reaches a kind

`match(raw_name)` in two passes, both of them only ever a *proposal*:

1. **alias** — the printed name, once quantity, packaging and Bio markers are stripped,
   is one the vocabulary lists. `Paprika rot lose` -> `paprika rot`.
2. **prefix** — either string is the start of the other, because tills truncate
   (`Johannisbeer`, `BioBabyWasserme`) and qualify (`Bio-Mini Möh. 200g`).

The prefix pass is what makes the thing useful and also what makes it wrong sometimes:
it cannot tell `Birne Conference` (a pear) from `Orangendirektsaft` (juice). A short
veto list of processed-food words blocks the obvious cases; the rest is why every guess
goes through a human. The veto is checked as a substring and is deliberately short — a
word that can hide inside a vegetable is worse than a miss, and `eis` was on the list
until it vetoed `Speisezwiebeln`.

## The loop

```
grocery-app produce propose            # a CSV of unresolved names, best guesses first
   ... mark `decision`: y, n, a kind name to override, or several
       separated by `|` when the name cannot say which it was ...
grocery-app produce confirm            # mints kinds, writes resolution entries
```

Re-running `propose` carries decisions forward, so improving the vocabulary does not
throw away an afternoon of review. A decision is kept only while the guess it was made
against is unchanged: when the proposal moves, the reviewer agreed to something that is
no longer on offer, so the row goes back to undecided and they see it again.

Same shape as the store catalogues: a machine proposes, a human decides, only marked
rows are written. Produce needs its own pair because `resolver.confirm` is built around
article numbers and catalogue URLs.

A kind earns an id the first time it is accepted, and every store that prints a name for
it resolves to that one id. Typing a kind the vocabulary has never heard of is accepted
and reported — a reviewer doing that has found a gap, not made a mistake.

## What it does not reach

- Counter goods — `Gouda jung`, `Mozzarella, ger.` — have the same no-barcode problem and
  are not produce. The same mechanism would fit; the vocabulary does not cover them.
- Flowers (`Chrysanthemen`, `Fairtrade Rosen`) are in the receipts and out of scope.
- Everything packaged. Those names belong to the catalogue route, or to a shopper
  scanning the item's barcode.
