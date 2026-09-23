# Design: Categories and Budget Brands

Written 2026-09-21 · Status: the brand half is built (2026-09-22); the category
half is built (2026-09-23).

**The name changed, and so did the question.** This document was written about
"own brands" and tested them by ownership. Parham corrected that on 2026-09-22:
the question a shopper asks is *"is this the cheaper one?"*, not *"who owns this
label?"*. In his words: "the word `own_brand` is wrong. there are some brands
that are cheaper. that's it. and it's not that their quality is better or
anything." Read every "own brand" below as "budget brand", and see "What the
build changed" at the end for what that cost.

What shipped: `is_own_brand` no longer exists on a product record. The
normalizer derives `is_budget_brand` per purchase line from the line's store and
the product's brand; `BUDGET_BRANDS` covers ALDI SÜD, Lidl, Kaufland and Rewe
alongside GLOBUS; Jeden Tag is modelled as a cooperative brand rather than any
shop's property; and the insight separates produce (no brand to find) from a
brand nobody has read yet. `purchases.json` is contract 3 and `insights.json`
contract 2.

What shipped since: the category half. `categories.py` holds the closed
vocabulary — 13 branches, 32 sections, 112 categories — and `categorize.py`
proposes a key per product from three sources of evidence. 179 of 181 products
were reviewed and migrated off the old 46 free-text values; the remaining two
are recorded as `category unknown` because the shopper looked and could not
say. A value outside the vocabulary is now
a reported problem in `product_store.problems()`, so free text cannot walk back
in the way `cut` and `chia` did. `purchases.json` is contract 4:
`category` is now a vocabulary key and `category_path` carries the three labels
beside it. The brandless invariant no longer reads `category.startswith
("Produce")` — it asks `categories.is_produce()`, which is a question about
which section of the shop a thing comes from rather than about a string. See
"What the category build changed" at the end.

Two fields already in `products.json` are doing their jobs badly, and a third
meaning has been quietly read into a fourth. This is what each should mean.

## The problem

Five insights are built, and all five group by `product_id`. That works for the
two questions that are genuinely about one product — personal inflation, and the
same item across stores. It fails for every question about a *kind* of thing:

- how much do I spend on chips
- how often do I buy chips
- how much of my chips money goes to a shop's own label

Nothing in the contract answers those, because nothing says which products are
the same kind of thing. Six products in the catalog are potato chips across
three shops, and the only thing that knows is a person reading the names.

`category` exists on every product and is supposed to be that answer. As of
2026-09-21 it was not used by `insights.py` — zero references — and it was not
in a state where it could be:

- 27 of the 99 older products have no category at all, and all 53 products the
  coarse pass minted have none, because `enrich` needs an EAN to ask
  Open Food Facts and a coarse product deliberately has none
- two vocabularies are mixed: curated title case (`Dairy`, `Snacks`,
  `Personal Care`) and raw Open Food Facts taxonomy leaves (`chia`,
  `mozzarella`, `stuffed wafers`, `cooked chicken breast slices`)
- the depth is inconsistent: `Cleaning`, `Cleaning / Dishwashing`,
  `Cleaning / Laundry`
- `cut` is a category

Separately, `is_own_brand` is a boolean on each product, but the fact it records
is not about the product. It is *"the brand Milsani belongs to ALDI SÜD"*.

The table that says so already exists — `OWN_BRANDS` in `resolver.py`, with
`own_brand_status(store, brand)` beside it — and only GLOBUS is filled in. The
problem is not that it is missing. It is that the answer is **computed once at
mint time and frozen onto the product**, by two of the four writers that mint
products; the other two leave the field null. So the same fact about 66 brands
is copied onto 181 rows, and extending the table does not reach the rows already
written.

It has already drifted. `p-0095` carries the brand `OHO`, which is on the GLOBUS
list, and `is_own_brand: None`, because it was minted by a writer that never
asks. `Alnatura`, `funny-frisch`, `Dove` and `Dallmayr` each carry different
values on different products. 28 brands have no value at all, including every own
label the coarse pass minted, so their money lands in the insight's `unknown`
bucket rather than in `own_brand`.

## Decisions

- **A category is what you would write on a shopping list.** This is the whole
  granularity rule and it comes from what the app is for: predicting what is
  needed. A list says *chips*, *milk*, *yogurt*. It does not say *snacks*, and
  it does not say *funny-frisch Chipsfrisch Salt & Vinegar 175 g*. Too wide and
  cadence says nothing — "I buy Food every day" is not an insight. Too narrow
  and it is just the product again.
- **The vocabulary is closed and lives in code**, like `VOCABULARY` in
  `produce.py`. A free-text category field is how `cut` and `chia` got in. A
  product whose category is not in the list is a gap to be reported, not a new
  category quietly minted.
- **Open Food Facts supplies a chain, not a category.** `enrich` already returns
  a taxonomy chain (`seeds -> chia`). The leaf is too fine and the wording is
  crowd-sourced, so the chain is mapped onto a vocabulary entry rather than
  written through. Products with no EAN — every produce kind and every coarse
  product — get a category the same way they get everything else: proposed, then
  confirmed.
- **Own-brand is derived, never stored.** The table exists; what has to go is
  the frozen copy. `is_own_brand` leaves the product record, and the normalizer
  computes it from the line's store and the product's brand as purchases are
  built — it already copies the field across at exactly that point. Extending
  `OWN_BRANDS` then reaches every row ever written, and the field cannot drift
  because there is nothing to drift from. Closing the 28 unrecorded brands
  becomes a few lines in one table, not 99 product edits.
- **The table is chain to brands, and a brand may sit under several chains, or
  none.** This doc raised `Jeden Tag` as an open question: it is recorded as
  GLOBUS's on Parham's authority — he works there — but it also turns up in other
  shops. **Resolved 2026-09-22, and the doc had the wrong test.** Jeden Tag
  belongs to **Markant**, a buying cooperative whose subsidiary trades goods "im
  Preiseinstiegsbereich" — the entry-price segment — and whose retail partners
  include Globus, Kaufland, tegut, real and Bartels-Langness (famila, Combi,
  K+K). So nobody at GLOBUS owns it, and an ownership or exclusivity test throws
  it out. Under the budget test it passes easily: it is the cheap line. Parham's
  answer stands, for a better reason than the one he gave it. It is modelled as
  a cooperative brand reaching member chains, not copied into each shop's tuple.
  In the current data it is bought only at GLOBUS, so nothing moves either way.
- **Deriving the answer per line makes a new question askable.** Because the
  fact is about brand *and* shop, "am I reaching for the cheap line when I shop
  at ALDI" is answerable, which it is not while a flag lives on the product.
- **A shop's own label is not automatically its cheap one.** German chains run
  their labels in price tiers. Kaufland's `K-Classic` is the entry line but
  `K-Favourites` is premium; ALDI SÜD's `Moser Roth` and `Gourmet Finest
  Cuisine` are premium too, as is Lidl's `Deluxe`. Reaching for Moser Roth
  instead of Milka is not the saving this insight measures, so premium store
  lines answer False beside the manufacturers. This is the one part of the
  reframing that is a judgement rather than a fact, and it is Parham's: he
  approved it on 2026-09-22.
- **`brandless` means no brand is recorded — never that this is a type.** It
  does not mark a category or a placeholder. A brandless product is an ordinary
  product that was ordinarily bought.
- **A null brand is two different answers, and the record must say which.**
  Either there is nothing to find — loose produce, counter goods, a carrier bag,
  where no barcode exists so no lookup, no scan and no shopper will ever supply
  one — or there is a label on the box that we have not read. The first is
  final; the second is a gap, and it belongs in `open_questions` as
  `brand unknown`, which is that field's job and not a second one.
  The test is whether a barcode could ever answer it.
  Today 22 coarse products silently give the first answer while meaning the
  second: ALDI SÜD's `Chips gesalzen` has a brand printed on the bag.
- **Produce is treated as brandless by decision, not by definition.** A banana
  can be Chiquita. Nothing in this system's reach ever carries that — the
  receipt does not print it, there is no barcode, and the price is per kilo —
  so produce kinds are minted with no brand and no question. Saying this out
  loud matters because the honest reason is "unreachable", not "does not exist".
- **Absence of a question must not be how "nothing to find" is encoded, on its
  own.** A missing question cannot be told from an oversight, which is exactly
  how those 22 went wrong. An invariant enforces it instead, and it needs no new
  field, because the set of genuinely unbranded things is small and the catalog
  already marks it: you pick up loose fruit and vegetables by weight, and you do
  not pick up a kilo and a half of crisps. 32 of the 33 brandless products are
  already categorised as produce. So: a null brand is allowed only where the
  category says produce, or where `open_questions` says the brand is unknown.
  This leans on `category` only at its coarsest level, which is the part of that
  field that is currently trustworthy.

## What this replaces

PR #25 added `parent_id`: a branded product hung off a brandless one that acted
as the type. It was closed unmerged, for two reasons worth keeping written down
so it is not rebuilt.

**"Brandless" could not carry the meaning.** The invariant required a parent to
be brandless, but `Kartoffelchips gesalzen` is brandless because the ALDI SÜD
till printed no brand — a real bag of crisps, not a category. The catalog could
not tell a purchased brandless product from a grouping node, so the name matcher
would have made ALDI's chips the parent of funny-frisch's chips. They are
siblings.

**It duplicated `category`.** "These six are all potato chips" is what a category
says. The mechanism was built because the category field was empty and messy —
routing around the broken thing instead of fixing it, and ending with two
grouping mechanisms where one was already specified.

## What a category does not do

- **It does not carry price.** Inflation stays per product. A category spans an
  own label and a national brand, which differ systematically, so a category
  price average would move when the shopper switches brand and read as
  inflation. Spend and cadence roll up; price does not.
- **It does not identify an item across stores.** That stays the EAN.
- **It does not make coarse products fine.** A coarse product with `variant:
  null` stays coarse; a category tells you what kind of thing it is, not which
  one it was.

## What the build changed

Two things the design did not anticipate, found while building it on 2026-09-22.

**A store's own-brand list is usually a selection, and absence from a selection
means nothing.** The design assumed the table could simply be extended, and that
`own_brand_status` would go on reading "brand recorded, not on the store's list"
as *not the store's*. That reading is safe at GLOBUS, where Parham named the
whole set on his own authority, and wrong at ALDI SÜD, which publishes its
labels as explicitly "eine Auswahl" and sells mostly own label. Shipping a
partial ALDI list under the old rule would have filed the chain's own chocolate,
kitchen roll and cheese under national brands — a wrong answer written down,
which is the failure the whole change exists to remove.

So the table gained two companions. `NATIONAL_BRANDS` records brands a
manufacturer owns, which is a fact about the brand alone and so needs no store.
`COMPLETE_OWN_BRAND_LISTS` names the stores whose own list is known exhaustive,
and only there does absence still settle the question. Everywhere else an
unsourced brand returns `None`: a gap, and one that now lands in the insight's
`unknown` bucket where it can be seen and closed.

**The question was the wrong one, and the name said so.** Everything above was
built around ownership: a table of each chain's own labels, and a test asking
whether the shop owned the name. Parham stopped it there. The shopper's question
is whether a brand is the shop's *cheaper* option, and three arrangements answer
it the same way — the chain owns the trademark (Milsani at ALDI SÜD), a supplier
sells to that chain alone, or the chain buys through a cooperative (Jeden Tag).
Ownership separates those three; price does not. So `is_own_brand` became
`is_budget_brand`, `OWN_BRANDS` became `BUDGET_BRANDS`, the insight section
`own_brand` became `budget_brand`, and both contracts took a version bump.

The cost of getting it wrong first was small, because the plumbing did not care:
the field still leaves the product, is still derived per line, and the tables are
still keyed by store. What changed was the name, the membership of the tables,
and the test in the middle.

**A receipt's silence about a brand is evidence, not a rule.** Parham noticed
that ALDI SÜD prints `Persil`, `Lenor`, `Coca-Cola` and `true fruits` on the
line but prints `HP Skyr Drink 330` for Milsani and `Basmati Reis` for BON-RI —
the chain names a manufacturer and stays quiet about itself. The pattern is
real and holds across most of the 81 ALDI lines. It was deliberately not turned
into an inference, for two reasons: his own data breaks it (`BB Heumil 3.8% 1L`
is BIO BIO, an own label, printed in abbreviation), and the chain's catalog
answers the same question exactly, for free, with no guess. It is worth keeping
as a **cross-check** — a line where the till printed no brand but the catalog
matched a manufacturer is odd, and odd is worth flagging — in the same spirit as
the VAT-class alarm in `ROADMAP.md`.

### What the numbers did

Against the 27 receipts as of 2026-08-29, on €455.95 of resolved spend:

| | before | after |
|---|---|---|
| budget | €66.64 | €106.42 |
| name brand | €168.02 | €205.65 |
| no brand to find (produce) | — | €86.02 |
| brand not yet known | €221.29 | €57.86 |
| budget share of known | 28.4% | 34.1% |

The reframing from ownership to price moved **no number in this data**: no
premium store line has been bought yet, and Jeden Tag appears only at GLOBUS.
The concept is now right and the figures happen to agree with the wrong one.
That is worth writing down, because the first receipt carrying Moser Roth or
Jeden Tag at Kaufland is where the two definitions part company.

The last row is the honest one: `unknown` is now €57.86 and consists entirely
of `(no brand recorded)` — packaged goods whose label exists and has not been
read. Every brand the catalog does record is now answered. That remainder is
the gap worth working on, and it is a catalog-matching problem rather than a
question for the shopper: ALDI's own crawl already holds `Chips gesalzen` as
SUNSNACKS and `Mozzarella, ger.` as HOFBURGER.

## What the category build changed

Five things the design did not anticipate, found while building it on 2026-09-23.

**The strongest evidence was already on disk and nobody had read it.** The design
listed Open Food Facts and the printed name as the two sources. There is a third
and it is better than both: 47 of the 181 products were matched to a GLOBUS
listing, and every listing URL carries the shop's own three-level path —
`milchprodukte-eier/kaese/reibekaese/4306188407508/mozzarella-gerieben`. That is
not a guess about what the thing is; it is where the shop put it. Across the
whole catalog those 47 products sit on 28 distinct shelves, so mapping their
tree onto ours is a 28-line table, and it answered three of the four failures
the name matcher was known to make — `Mozzarella, gerieben` is grated cheese,
`Eis, Schokolade` is ice cream, `Linsen Chips Paprika` is crisps.

**A shop's shelf is sometimes wider than a category, and that is still useful.**
GLOBUS files Kühne's Salz-Dill-Gurken under `gemuesekonserven`, but a jar of
pickles and a tin of chopped tomatoes are different lines on a shopping list, so
our vocabulary separates them. The mapping table therefore has two kinds of
value: a category key, or `@section` — the shop narrows it to a section and the
name picks the entry inside it. That combination is strictly better than either
alone, because the section throws out every alias that matched the wrong aisle.

**The flavour is not what the thing is.** `variant` was in the matched text at
first, which is how `Lay's Potato chips` in `Kräuterbutter` proposed butter,
`Potato chips Peperoni` proposed chilli peppers and `Somat 5in1 Deo Perls`
proposed deodorant. One field, one job: `name` says what it is, `variant` says
which one it was, and only the first is read.

**The rule that makes the migration honest: a name alone is a question, two
independent sources agreeing is an answer.** 42 of the 181 rows came back
settled — the shop's shelf and the product's own words saying the same thing, or
the name and the Open Food Facts chain agreeing. Nothing else was settled by
machine, including the 110 rows where a single alias matched cleanly, because
that source is wrong about one product in twenty-five. Three rows went to the
shopper and nobody else could have answered them: two Kaufland products nobody
can identify from the receipt (`Bubble Chill Wild.`, `Blitzstart Mix`) and an
ALDI `Blätterteiggebäcke` that is sweet or savoury depending on which one he
picked up. He answered one of the three. That is the expected hit rate two
months after the trip and it is the reason `n` had to mean something.

**"I do not remember" is an answer and the catalog has to hold it.** `n` in the
review file does not mean "reject and move on" — it writes `category unknown`
into the product's `open_questions`, and a re-run brings the row back already
marked `n` rather than asking a dead question twice. Without that, a product
nobody can place is indistinguishable from a product nobody has looked at, which
is the same failure as the twenty-two coarse products that silently claimed to
have no brand. Two products are in this state: a €2.99 Kaufland drink and a
€1.39 ALDI pastry, €4.38 of spend between them. They are closable — a catalog
match or a second receipt would settle either — just not by memory.

**One row was a missing word rather than a hard question.** GLOBUS files
Ponnath's `Hähnchenbrustfilet, Natur` under `kochschinken-braten`, and the
vocabulary had `Schinken` and nothing else in that section — so the shop was
right about the shelf and our only word for it was wrong about the meat. Calling
sliced chicken breast `Schinken` is the `cut` mistake from the other direction:
true of where it sits, unrecognisable on a list. The fix was a vocabulary entry,
`Geflügelaufschnitt`, not a compromise on those two products.

**Who reviewed a category is not recorded, and should be.** `resolution.json`
carries `confirmed_by` per entry; a product's `category` carries nothing, so the
catalog cannot tell a row a person read from a row a model read. That is a real
gap and it is left open deliberately rather than papered over: per-field
provenance on a product record is its own decision, and this change did not
need it.

**A produce kind with no category is refused rather than minted.** This reverses
a decision from the produce loop, where a kind the vocabulary had never heard of
was accepted and reported: "take the answer, and say what is missing". It cannot
stay. A produce product is brandless on purpose, and after this change the only
thing distinguishing that from a brand nobody read is its category — so minting
`Pastinaken` with no category would write a record the store's own invariant
rejects. The row is reported and left in the CSV instead, where re-running
`confirm` after two lines in `produce.py` banks it unchanged. Nothing is lost
except the illusion that it was already banked.

### What the numbers did

Against the same 27 receipts, on €515.88 of spend:

| | before | after |
|---|---|---|
| distinct category values | 46 free text | 80 of a closed 112 |
| products with no category | 79 | 2, both recorded as a question |
| resolved spend with no category | €455.95 | €4.38 |
| largest bar in "Where the money goes" | `Uncategorised` | Obst & Gemüse, €92.71 |

The €4.38 is the two products above. The rest of what the demo still shows as
uncategorised — €49.20 — is lines that never resolved to a product at all, which
is a different problem and already counted as one.

`insights.py` still does not group by category. The field is now trustworthy
enough that it could; doing it is the next piece, not this one.
