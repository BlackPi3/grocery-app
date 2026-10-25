# Can ALDI SÜD's prices stand in for Lidl's? (2026-10-25)

Lidl publishes no regular shelf prices (lidl.de lists only flyer food and
non-food: no result for H-Milch, Penne, Tomaten or Eier). The question: do the
two discounters charge the same for the same kind, so ALDI's price list
(aldi-sued.de, 18 Sep 2026) can stand in for Lidl's with a known error?

## Data

- **Lidl:** Open Prices (Open Food Facts' crowd-sourced prices), every price at
  the 138 Lidl stores in Germany it knows, dated 2026: 615 prices, 483
  products. Offer prices dropped; the latest shelf price per product kept:
  343 products.
- **Matching:** for each, Claude (Sonnet, subscription) picked from the 30
  ALDI products nearest by name the like-for-like counterpart (same product,
  else the same kind, form and tier, organic for organic) and the pack ratio.
  181 of 343 matched; the rest had no fair counterpart or no pack size.

## Result

| Lidl price against ALDI's | Pairs | Share |
|---|---:|---:|
| to the cent | 88 | 49% |
| within 10% | 112 | 62% |
| within 25% | 133 | 73% |
| Lidl more than 10% cheaper | 31 | 17% |
| Lidl more than 10% dearer | 38 | 21% |

Median ratio 1.00. Summed: Lidl 354.90, ALDI 374.50 (-5.2%); prices since
July only (118 pairs): +1.2%.

Milk, quark, butter cheese, pasta, pesto, salt, water, müsli, nuts, chips,
yogurt: the same price to the cent. Most pairs far apart are a matching
mistake, not a price: a pack size not read (Sweet-Chili 700 ml against 455 ml,
a 20-wash gel against a powder), a famous brand set against ALDI's own
(Monster against an ALDI energy drink), or a different kind (Brathering
against Heringsfilet).

## What it means

For own-brand basics, Lidl's shelf price is ALDI's price, at least half the
time exactly; ALDI's list can stand in for Lidl's there, with the error
measured, not guessed. It cannot for named brands, fresh produce, or anything
Lidl sells under its own concept (Lidl's bakery).

## Limits

- Open Prices is a few hundred prices from strangers, all over Germany, over
  ten months; prices may differ by region and month.
- The pairing is a model's; the tails show it errs mostly on pack sizes.
