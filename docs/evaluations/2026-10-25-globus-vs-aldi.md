# The owner's GLOBUS food basket, priced at ALDI SÜD (2026-10-25)

The first number for list step 4 (b): how much would the same food have cost
at the discounter next door? Asked by the owner: "we need to know a number asap".

## What was compared

- **Basket:** every food and drink line (no alcohol, no household, no drugstore)
  the owner bought at GLOBUS from 29 Aug to 24 Oct 2026: 115 products, 399.46 EUR
  at shelf price, 357.67 EUR paid after printed discounts (mostly 10%).
- **ALDI prices:** the aldi-sued.de crawl of 18 Sep 2026 (3,220 products, shelf
  prices, no offers).
- **Like for like:** for each product, Claude (Sonnet, subscription) picked from
  a shortlist of ALDI products (same shelf, plus the 30 nearest by name) the one
  a shopper would take instead: the same product, else the same kind and form,
  organic only for organic, a similar pack, the cheapest such; and how many ALDI
  packs make one unit bought. Checked by hand; one wrong kind removed (Apostels
  Greek yogurt matched to a 0.1% skimmed yogurt).

## Result

| | GLOBUS shelf | GLOBUS paid | ALDI |
|---|---:|---:|---:|
| Matched (69 products, 57% of shelf spend) | 228.62 | 202.93 | 198.75 |
| of which Jeden Tag | 86.19 | 77.61 | 88.53 |
| of which other brands | 142.43 | 125.32 | 110.22 |

- **At shelf price, ALDI is 13% cheaper**: 29.87 EUR over 8 weeks, 3.73 a week.
- **Against what the owner paid, 4.18 EUR over 8 weeks, 0.52 a week**: his
  printed discounts take almost all of the difference.
- **Jeden Tag costs what ALDI's own brand costs** (86.19 against 88.53):
  18 products at exactly ALDI's price (Magerquark 500 g 1.19 at both, Penne
  0.69, Pesto 0.99). The whole difference is in other brands (23% at shelf):
  Bertolli, Alnatura, Pepsi, the bakery's cakes. Those can be swapped to Jeden
  Tag in GLOBUS too, without a trip.
- **Not priced: 43% of shelf spend** (158.88 EUR). ALDI's online list has no
  loose fruit and vegetables (tomatoes, avocados, pomegranate), no bakery
  cakes, no organic lactose-free milk; some kinds it does not sell (bulgur).

## What it means

For the owner, a second shop saves about 50 cents a week: not worth a trip,
even to the ALDI 1.2 km from his GLOBUS (about 0.40 EUR by car). For a shopper
without his discount, about 4 EUR a week on the part priced, mostly from
brands, which a budget line in the same shop gives too.

## Limits

- ALDI's shelf prices only: offers at either shop are not counted.
- Fresh produce, where discounters may differ most, is not priced at all.
- One shopper, one pair of shops; the model's pack ratios are not all exact
  (Kidney-Bohnen 400 g against a 255 g can, counted as one).
