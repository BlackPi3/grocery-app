# Products, chain products and resolutions

How the stored data should connect. Agreed with the owner on 2026-11-08, not
built. Words as in `docs/glossary.md`. Examples are made up.

## The till function

Each branch's till turns a product into printed text by a rule we cannot see.
We only see its output on receipts, and work it out from them. It must not be
assumed the same at every branch of a chain; that is to be measured.

One paper receipt comes from one branch, but branches may share a till
function. Until shown otherwise, assume one till function per branch, and merge
branches only when the data proves them the same.

Resolutions are what we have worked out so far, stored backwards: printed text
→ product. They record the branch. Once they do, compare branches: does a
product print alike, and does one printed text come at very different prices?
Answers do not change until that shows what is true. It needs the printed
addresses cleaned into one branch per real place (chain + street + postcode).

## A resolution is a cache

A hit answers the line with no search and no model call. A miss goes on to the
search, and the answer is saved as a new resolution. So the more people buy, the
more lines are free.

A resolution points to a product, to a family, or to nothing (a deposit line).
Nothing rechecks a hit, so a wrong entry stays wrong until corrected.

## Two sets of products, complementary

The goal is one database of all products. That is parked as possibly huge. Until
then:

```
 RESOLUTION
     │ points to one
     ▼
 OUR PRODUCT      id, our category, level: exact, family or kind. Nothing copied.
     │
     ├─ exact  ──► one or more chain products (the same drink at two chains)
     ├─ family ──► several exact products of ours
     └─ kind   ──► only a category
```

- Our product stays as a thin row. It keeps one identity across chains, our
  category, what only we hold, and what corrections, checks and offer verdicts
  refer to.
- A product no chain lists keeps its own name, brand and size.
- A chain product belongs to at most one of our products, always an exact one.

### How exact we can be

The aim is the barcode (EAN) of the item behind a resolution, reached through
these links. Loose goods and counter goods have none, so the top level is the
exact product, with its barcode when it has one. A family is the versions a line
cannot tell apart. A kind is what is left when the line names only a kind
(`Juice`): the paper says no more, so it is an answer, at that level: it counts
in spending by category, but not in price comparison or repurchase. A
resolution can move up a level when a price or a shopper says more.

### How links are made

From an exact barcode or article number, for what can be filled in now; and from
section 3's accepted picks as people buy things. Barcodes alone cannot connect
chains: not every chain's download has them. A wrong name match would attach
purchases to the wrong product, so name similarity alone never makes a link.

## Chain products move to the database

They are JSON files today. Searching one means the server holds all of it in
memory (about 200 MB for one chain); a database reads only what a search needs.
High priority, right after section 3 is fixed.

Proposed, not yet agreed: one table, extending `store_listings`, with fields
the chains do not share kept as extra data.

## What must keep working

```
 OUR PRODUCT
     ├──► chain product  ── dated prices
     ├──► chain product  ── dated prices
     └──► receipt lines  ── branch, date, price paid
```

- **Where a product is found:** our product's chain products, plus the branches
  on its receipts. It claims "seen here on this date", not "available".
- **Price history:** per chain product, dated. A chain product is never
  deleted. The website price and the price paid are kept apart, since a paid
  price can be an offer.
- **A new download records only what changed**, so the table grows with
  changes, not with downloads. Each download is compared with what we hold:
  a new product gets a row; a changed price gets a dated entry; a changed name
  or pack size is updated; a product no longer there is marked gone, and
  unmarked if it comes back. An unchanged product writes nothing new but the
  date it was last seen. A product is marked gone only when the download was
  complete, so a failed page does not make a shelf look discontinued.

Proposed, not yet agreed: a chain product row holds chain, branch if known, link to our product (empty until
someone buys it), price history, last seen, source (download or receipt).

## Where things can be wrong

These are rules the data must hold. When one breaks, the owner is notified, to
look into what went wrong. How the notice reaches the owner is not settled.
None of these runs yet. When one fires, or an example fits none of this, the
design is fixed first, then the code, and a made-up version of the case becomes
a test.

- A chain product is tied to two of our products.
- One barcode is on two of our products.
- One of our products has two barcodes.
- One printed text means different products at two branches.
- An accepted pick was paid far from the chain product's price.
- A line fits none of the levels.
- A line prints a brand but is saved as a kind (kind means the line says no
  more, not that we did not try).
