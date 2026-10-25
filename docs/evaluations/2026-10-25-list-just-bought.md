# The shopping list: no suggestion for what was just bought

2026-10-25 · `grocery-app eval-list` on the owner's live history (8 weeks
from 30 Aug 2026). No receipt text in this document: the repo is public.

## The question

The owner, on the live list the day after a shop: Frischkäse, Avocado,
Pizzateig and more were suggested, all bought the day before. "These aren't
suggestions when I just bought them. The list doesn't need to be always
filled; it needs to be filled with meaningful suggestions."

The list took every item with a chance of 25% or more of being bought in the
coming week. The chance comes from how often an item is bought, not from
when it was last bought, so a weekly item stayed on the list the day after.

## How soon is a just-bought item bought again?

Each day of the 8 weeks, the items on the list, by how much of what one
usual buy lasts had passed since the last buy:

| time passed | items a day | bought within 3 days | within 7 |
|---|---|---|---|
| under a quarter | 5.2 | 9% | 21% |
| a quarter to a half | 3.3 | 13% | 33% |
| a half to three quarters | 2.4 | 19% | 39% |
| three quarters to all | 1.3 | 23% | 41% |
| more than all | 3.4 | 23% | 34% |

## The rule

An item is suggested once half of what one usual buy lasts has passed since
its last buy (`shopping_list.DUE_SHARE`). Eggs every 6 days: back 3 days
after a buy.

| list | items a week | bought that week | caught |
|---|---|---|---|
| chance >= 25%, just bought too (before) | 17.1 | 31% | 18% |
| chance >= 25%, not just bought (now) | 6.9 | 42% | 10% |
| chance >= 30%, not just bought | 3.5 | 61% | 8% |

The list is less than half as long and right more often. What it costs: an
item bought again within a week of the last buy is no longer suggested, and
the list catches 10% of a week's items instead of 18%.

## Items catch far less than categories did

Since the list became items (#190), the backtest scores items, and they are
much harder to foresee: the categories list caught 49% of a week's
categories, the items list 18% before this rule. Two tomatoes the owner took for
the same thing (Romatomaten, Rispentomaten) are two items, so a buy of one
does nothing for the other. How fine an item is decides most of this.
