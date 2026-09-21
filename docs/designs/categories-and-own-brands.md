# Design: Categories and Own Brands

Written 2026-09-21 · Status: proposed, nothing built

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

`category` exists on every product and is supposed to be that answer. It is not
used by `insights.py` — zero references — and it is not in a state where it
could be:

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
is not about the product. It is *"the brand Milsani belongs to ALDI SÜD"*. Stored
per product, that one fact about 66 brands is copied onto 181 rows, and it has
already drifted: `Alnatura`, `funny-frisch`, `Dove`, `Dallmayr` and `OHO` each
carry different values on different products. 28 brands have no value at all,
including every own label the coarse pass minted, so their money lands in the
insight's `unknown` bucket rather than in `own_brand`.

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
- **Own-brand is a relationship between a chain and a brand, not a property of a
  product.** One table, chain to the brands it owns, and `is_own_brand`
  disappears from the product record and is derived when purchases are built.
  Fixing an entry then fixes every product at once and it cannot drift. Closing
  the 28 unknowns becomes 28 lines of data, not 99 product edits.
- **A brand may belong to more than one chain, and some belong to none.**
  `Jeden Tag` is a buying-group label sold across many independent shops; it is
  an own brand of no single chain, and calling it GLOBUS's — as the data
  currently does — is wrong. The table is chain to brands, which allows a brand
  under several chains, and a brand absent everywhere is simply a brand.
- **Deriving own-brand per line makes a new question askable.** Because the fact
  is about brand *and* chain, "am I buying ALDI's own labels when I shop at
  ALDI" is answerable, which it is not while the flag lives on the product.
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
