# The shopping list: can a history foresee a week's shopping?

2026-10-23 · `grocery-app eval-list` on the owner's live history (22 Jun to
23 Oct 2026: 81 receipts, 551 product lines, about 5 receipts a week, most at
one shop). No receipt text in this document: the repo is public.

## The question

The owner's end goal: a drafted list of what a person needs now or will need
soon, which they shorten and add to, so offers can be compared across the whole
list. How well does the history foresee what goes on it?

## Exact products or kinds?

| | |
|---|---|
| products bought only once | 241 of 322 |
| a week's buys of a product bought before | about half |
| a week's buys of a kind bought before | 94% |

The pattern is in the kind (eggs, quark, crisps), not the product: one kind
was bought on 11 days as 16 different products. A list line is a kind, with
the usual product as a hint.

## Results

Each of the last 8 weeks drafted from what came before it only, against the
kinds bought in the 7 days from it (22.8 kinds a week).

| list | kinds on it | bought | caught |
|---|---|---|---|
| chance >= 15% | 46.9 | 35% | 71% |
| chance >= 20% | 37.0 | 37% | 60% |
| **chance >= 25% (the list)** | **28.0** | **40%** | **49%** |
| chance >= 30% | 19.2 | 46% | 38% |
| chance >= 40% | 9.1 | 56% | 22% |
| gap rule (the old "due again") | 20.4 | 42% | 37% |

*bought*: of the list, the share bought that week. *caught*: of what was
bought, the share the list had.

**The chance is honest.** Kinds given 30-40% were bought 36% of the time,
40-50% were bought 44%, and above 50% were bought 74% or more. So the list's
length can be set by one number, and later by what fits at home.

**Urgency is weak on this history.** On the list, kinds marked `now` were bought
within 3 days 19% of the time, `this_week` 15%, `later` 14%. Sorting by the day
a kind runs out also picked the week's kinds no better than the chance did (at
22 kinds: 38% bought by run-out day, 41% by chance). A shopper there almost
daily buys when they are in the shop, not when the cupboard is empty, so the
run-out day sorts the list but is not yet a measured signal.

## Limits

- One person, four months, mostly one shop, near daily.
- A missed receipt reads as a week without buying: these numbers are a floor.
- Some kinds are wide (cleaning products: 8 different products) and are not
  one need.
- "Bought that week" stands in for "needed that week"; a removal on the list
  (step 2) is the first direct signal of what was not needed.
- Settings were looked at on the same 8 weeks they are reported on: half-life,
  minimum days and the stop rule moved the result by a few points at most.
