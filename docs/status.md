# Status

Where the work stands, kept current by every PR that changes it, so that any
session (laptop or cloud) can pick up from here. How we work is in
`docs/working-agreement.md`.

**Last updated:** 2026-10-13, redesign step 3.

## Now

- Everything is merged. `main` deploys the server and the public demo on every
  merge (`.github/workflows/deploy.yml`). Nothing is mid-flight.
- Just shipped: **redesign step 2** (#108). Spot checks and questions are
  yes/no cards with pictures, one at a time, behind the Receipts badge
  (swipe right for Yes, left for No; Undo restores). A question shows up to 5
  cards, ordered: the price paid first, then the model's pick, then the search
  choices, then by price (`api/cards.py`). No on every card stores a
  `none_of_these` answer (`line_resolutions.product_id` NULL). No on a spot
  check leaves the line unplaced, counts a mistake, and forgets the *machine's*
  memory entry for that printed name (a person's entry is never forgotten).
  #109: a card without a photo shows no empty box.

## Next build (agreed)

1. ~~Redesign step 3.~~ Done: each receipt line shows an easy product name
   and its deepest category (left out when it repeats the name). A line
   nothing placed shows the reading's guess, marked, or the printed text in
   grey. The brand, size, details, who said it and the printed line are the
   owner's only; the receipt header says "6 items" (owner: "6 items: 2 you,
   4 app").
2. **Drill-down.** Tap an insight to see a calendar of purchase dots
   (GitHub/Anki style), then the receipt line (fix it there), then the receipt
   photo. There is no photo endpoint for users yet.
3. **Google sign-in** on the web. Still open: who may sign up. Apple sign-in
   is deferred (it needs the paid developer account).

## Open decision (the owner's)

- Should the app stop spot checks whose only claim beyond the paper is how
  the item was sold (`lose`, loose)? Recommendation: yes.

## Milestone: Ready for iOS (target 2026-11-02)

- The screens are settled: unchanged for 2 weeks after the designer's input.
- 2 weeks of real use with no database fix by hand.
- Google sign-in on the web.
- A second person using it with real receipts.

## Parked (later, not now)

- Insights month view: the owner dislikes the squarified tiles (small tiles
  lose their names). Redo with the redesign.
- A "none of these" answer used as a search hint (see the working agreement).
- Barcodes: connect every packaged product to a real barcode (shop barcode,
  Open Food Facts name search, a barcode photo from the user).
- Sureness levels (4 levels; attention follows seriousness and freshness).
- Lifestyle, personas, deals, dislikes, and zooming through time in insights.
- Cleanup: old English-named products, doubles from early catalog work.

## Gotchas

- `grocery-app serve` on a laptop starts no picture thread and serves no
  `/pictures`. Only the deployed app (`default_app`) does.
- Never `git stash -u` while a build reads the tree: it hides untracked
  inputs mid-run.
- Tests: only against `grocery_test`. Never run the paid test while another
  pytest run is using that database.
- In zsh, write `${P}` rather than `$P:` (`:e` is a modifier). This once broke
  a stored secret.

## Laptop only

These need credentials or private files that the repo and cloud sessions do
not have. Leave them for a laptop session:

- Reading the live database, the dev inbox (users' uploads, read at session
  start), or Cloud logs.
- Anything with `gcloud`: secrets, deploys by hand, alerts. Normal deploys
  need none of this, since CI deploys on merge.
- The paid test with a real receipt photo, scoring readers against the truth
  files, and rebuilding the demo seed (all of these read `data/`).
- The owner's private notes outside the repo.

The open-questions page (a private claude.ai artifact, readable only by the
owner's account) tracks every open item: https://claude.ai/artifact/WHW7obc3X2YrQYAnpwvSJs.
If a session can't reach it, use this file instead.
