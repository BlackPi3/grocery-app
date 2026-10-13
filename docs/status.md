# Status

Where the work stands, kept current by every PR that changes it, so that any
session (laptop or cloud) can pick up from here. How we work is in
`docs/working-agreement.md`.

**Last updated:** 2026-10-13, end of the cloud session: open decisions and research.

## Now

- Everything is merged. `main` deploys the server and the public demo on every
  merge (`.github/workflows/deploy.yml`). Nothing is mid-flight.
- Just shipped: **the Insights screen** (the last screen of the redesign).
  A short scroll of cards, each answering one question and saying what it
  rests on: where the money went this month (ranked bars by part of the shop,
  names never cut; tap a part for its products), prices that moved (one
  product at one shop, biggest first, old and new price with the dates), due
  again soon (from the last receipt; "bought twice, N days apart" when one gap
  is all there is; products not bought for longer than their usual gap are
  named under the list, not in it), the budget-brand share and the basket
  price (with the money each leaves out), and the same item at other shops.
  Every product on it opens the drill-down; back returns to the same place.
  Brands are the owner's only, on Home too. `insights.json` gained
  `coverage.products` (different products placed), so "18 of 24 products
  bought again" can be said. The squarified tiles are gone.
- Done (owner, 2026-10-13): **processing is quiet; new receipts and
  questions are marks**. A receipt on its way in is a slim note at the top
  ("Your receipt is being processed") that fades after a few seconds;
  nothing counts or ticks. A failure is a small note on Home until put
  away. A finished receipt never opens by itself: a blue dot on the
  Receipts tab, the receipt and its folded month says it is new, from the
  first reading on; opening it takes the mark away on every device
  (`receipts.seen_at`, migration 0021, existing receipts count as seen;
  `PUT /v1/receipts/{id}/seen`, the asker's receipts only). Open questions
  and spot checks are an orange count on the tab, each receipt and folded
  month, and an orange "?" on the line; tapping that line opens its cards.
  Page counts come from `/v1/questions` and `/v1/checks`, no new count API.
- Done (owner, 2026-10-09; designer, 2026-10-12): **receipts by month**,
  step 1 of zooming through time (year → month → week → day, one level at a
  time). Receipts shows one compact row per month, newest first: the month,
  its number of receipts and their total (printed totals only; "1 without a
  total" when one is missing). This month is open (else the newest), the rest
  folded; a tap opens or closes one, remembered for the visit only. A year
  switch shows only when receipts span more than one year; undated receipts
  sit under "No date" at the end. Receipts still being read stay at the top.
  The drill-down and "Open the receipt" open the receipt's month (and year)
  first. Page only, computed from `/v1/receipts`. **Next zoom step: weeks,
  then days, inside a month.**
- Done (owner, 2026-10-03, faint print read a shop's brand one letter
  wrong): **a brand one letter from the shop's own is asked**, not made.
  A brand no shop has been seen with, one letter from a brand seen at this
  shop (3 letters or more), makes the line a question; its cards are that
  shop's products of the near brand, the same name first, then the reading
  as it stands (`identify.misread_brand`, `api.matching.brand_question`;
  `what-a-line-is.md`). Products already made from such a misread are not
  changed; a spot check or a correction fixes them.
- Done (owner, 2026-10-12): **how sure the app is**, counted. Every
  counted product line, everyone's receipts, by level, from fields that
  already exist (`grocery_app.sureness`): answered (a person said it, "none
  of these" too) apart; 1 sure (`exact`, `produce`); 2 unclear print,
  product found (`price`); 3 only the kind (`family` with a category); 4
  needs an answer (`none`, or a family with no shared category). Unclear
  print is told apart only where the line records it (price, family); in
  level 4 the till's catch-all names and the reading's guessed kinds are
  counted. Owner-only `GET /v1/sureness` (per month, with the random
  checks' yes rate), shown on "How the app is doing" (You).
- Done (owner, 2026-10-03, from `Minze 15g`): a spot check card says
  "Random check: the app placed this itself. Right?", so it no longer reads
  like a confused question. Questions keep "Did you buy this?".
- Earlier: **redesign step 2** (#108). Spot checks and questions are
  yes/no cards with pictures, one at a time, behind the Receipts badge
  (swipe right for Yes, left for No; Undo restores). A question shows up to 5
  cards, ordered: the price paid first, then the model's pick, then the search
  choices, then by price (`api/cards.py`). No on every card stores a
  `none_of_these` answer (`line_resolutions.product_id` NULL). No on a spot
  check leaves the line unplaced, counts a mistake, and forgets the *machine's*
  memory entry for that printed name (a person's entry is never forgotten).
  #109: a card without a photo shows no empty box.
- Decided and done (owner: yes): no spot check whose only claim beyond the
  paper is how the item was sold. A word like `lose` or `Stück`
  (`normalizer.SOLD_AS_WORDS`) is not a claim, so `Bananen` placed as
  Bananen, lose is not checked; such checks picked earlier are not shown.
- Waiting on the owner: **Google sign-in** is built and off; the owner
  switches it on later (steps under Next build, item 3).
- Demo pictures: #112 is merged and deployed (a failed search stays due,
  searches wait 180 s, the demo looks up only guests' products). 7 of 24 demo
  products have a picture; filling the rest is a **laptop step** (some 20
  cents a search, 11 searches):
  `GEMINI_VERTEX_PROJECT=<project> .venv/bin/python scripts/build_demo_seed.py --resume --retry-pictures`
  (without `--resume` if the local `grocery_demo` database is gone), then
  copy `data/demo/pictures/` to the bucket's `demo/pictures/`, commit
  `demo_seed.sql`. Its log says why each search found nothing; if the 8 stay
  empty, the matching rule (`pictures.same_product`) is the next suspect.

## Next build (agreed)

1. ~~Redesign step 3.~~ Done: each receipt line shows an easy product name
   and its deepest category (left out when it repeats the name). A line
   nothing placed shows the reading's guess, marked, or the printed text in
   grey. The brand, size, details, who said it and the printed line are the
   owner's only; the receipt header says "6 items" (owner: "6 items: 2 you,
   4 app").
2. ~~Drill-down.~~ Done: the price that moved, your regular and a product
   tile open the product's purchases (calendar of dots and a list), then the
   receipt with the line marked (fix it there), then its photo
   (`GET /v1/products/{id}/purchases`, `GET /v1/receipts/{id}/photo`, the
   asker's receipts only; the demo shows only the made-up receipts' photos).
3. ~~Google sign-in on the web.~~ Built, **off until the owner switches it
   on**. Who may sign up was decided by the lead while the owner was away, as
   the safe default (reversible): **invite-only**. The owner's address is
   `GROCERY_OWNER_EMAIL`; anyone else needs their address added on the People
   card. Passwords keep working. Sign-ins last 90 days (migration 0020,
   `api/google_sign_in.py`). The owner's steps (details in
   `docs/designs/backend-api.md`, "Switching on Sign in with Google"):
   1. Google Cloud Console: an OAuth consent screen, then an OAuth client
      (Web application) with the server's address as Authorized JavaScript
      origin.
   2. GitHub repo settings: variable `GOOGLE_CLIENT_ID`, secret
      `GROCERY_OWNER_EMAIL`.
   3. Run the deploy workflow.
   4. Add each person's Google address on the People card (and as a test
      user while the consent screen is in Testing).
   No route removes a user yet (their receipts would go with them); a
   removed user's sign-ins end with the row. Apple sign-in is deferred (it
   needs the paid developer account).
4. ~~Insights screen.~~ Done (2026-10-13): five cards, one question each,
   with their coverage; every product opens the drill-down (see Now).

## Open decisions (the owner's), as of 2026-10-13

Nothing is being built. The next session starts by putting these to the owner:

1. **Who to win first.** The research (below) found that the idea itself is
   not unique; what is: each line tied to the shop's real product, a memory
   kept per shop, every figure saying how much of it is known, budget-brand
   share, and restock dates that admit thin evidence. Pick one person and one
   promise: the saver ("see exactly where your money went, no typing, it says
   what it isn't sure of") or the deal hunter ("your own basket priced at
   every shop near you this week"). Recommendation: the saver.
2. **Next build.** Recommendation: talk through barcodes first (parked
   above; the step none of 75 open-source projects takes, and the base for
   the next two). Then "this receipt at the other chain" for ALDI SÜD and
   GLOBUS, from the prices the catalog fetch already has.
3. **Live prices from other chains** (owner's question): full shelf prices
   per branch exist for ALDI SÜD and GLOBUS (fetched today) and REWE
   (unofficial app API, with barcodes); EDEKA, Kaufland, ALDI Nord and Lidl
   give weekly offers only (Korbuino, BSD; marktguru). Unofficial APIs can
   break, and no shop's terms are checked yet.
4. The research page's three questions: a business model; whether digital
   receipts (REWE eBon, the 2028 German digital receipt, a draft) belong in
   the pipeline; whether the shops' terms allow fetching their catalogues.

Research (private claude.ai pages, the owner's account): the landscape of
apps and 75 open-source projects, with "Where your app wins",
https://claude.ai/artifact/4hVAEvSZi814KQNWH3d8F6; the open-questions list,
https://claude.ai/artifact/WHW7obc3X2YrQYAnpwvSJs.

**The owner's to-dos** (none blocks building): use the app for two weeks
with every receipt from the phone; a second person with real receipts;
Google sign-in setup (steps above; later); the demo pictures laptop run
(above); the billing alert; two receipt questions on the open-questions
list (`Kleenex Ultra Soft W`, `Volvic 1,5 L`).

## Milestone: Ready for iOS (target 2026-11-02)

- The screens are settled: unchanged for 2 weeks after the designer's input.
  All screens are redesigned as of 2026-10-13 (Insights last); the two weeks
  run from there.
- 2 weeks of real use with no database fix by hand.
- Google sign-in on the web (built; the owner switches it on).
- A second person using it with real receipts.

## Parked (later, not now)

- A "none of these" answer used as a search hint (see the working agreement).
- Barcodes: connect every packaged product to a real barcode (shop barcode,
  Open Food Facts name search, a barcode photo from the user).
- Attention follows seriousness and freshness (a level-4 line right after
  the scan asks loudly; a random check waits). The levels it would use are
  counted (`GET /v1/sureness`).
- Lifestyle, personas, deals, dislikes, and zooming through time in insights
  (Receipts zooms by month now; weeks and days are next there).
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
