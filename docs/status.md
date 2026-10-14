# Status

Where the work stands, kept current by every PR that changes it, so that any
session (laptop or cloud) can pick up from here. How we work is in
`docs/working-agreement.md`.

**Last updated:** 2026-10-14, laptop: the product's price line and the rotating regulars built (PR open, shown to the owner, waiting for his look).

## Now

- `main` deploys the server and the public demo on every merge
  (`.github/workflows/deploy.yml`). **Mid-flight:** the branch
  `feat/price-line-and-regulars` (PR open), shown to the owner by
  screenshot; merge on his yes.
- Built, waiting for the owner's look (2026-10-14): **the product's price
  line, and your regulars, rotating.** The product page opens with the shelf
  price per unit before discounts over the whole history (each purchase
  carries `shelf_unit_price`, the price every price insight reads): one line
  per shop, and per loose or pack where a shop sold both, each named at its
  end; a dot per day bought, a tap opens that receipt; prices in another unit
  than most (per item against per kg) are counted under the chart, not drawn.
  The calendar moved to its own card, with weekday letters that stay in view
  while the weeks scroll. Home's regular tile turns through `regulars`
  (insights contract 10: bought on 3 days or more, most days first, up to 8
  shown): "8×, Rispentomaten, in 4 months, last on 13 Oct"; it turns half a
  turn after the price tile, so the two never turn together. The two tiles
  share one turning card (`turningCard`). `scripts/preview.py` fills in the
  shelf price from the live history while the live server is older.
- Done (owner, 2026-10-14, "looks good" on the screenshot; #150): **what discounts saved you**, a card on
  Insights after "Prices that moved". This month's saving and its share of
  the shelf price, then the last 6 months and the shops, most saved first
  (`insights.discounts`, insights contract 9). Only discounts printed on a
  product line count, over every line the shopper counts (groceries or not,
  like the month view). Not split by kind (staff discount, offer, shop card):
  the reading keeps the amount, not the discount's printed name; keeping it
  is an extraction change with a paid test, left for later. Live: 84,23 €
  since June, 83,83 € of it at GLOBUS (mostly 10%, likely the staff
  discount), October 20,90 € (9% off the shelf price). A line marked not
  counted is left out (1,31 € in October).
- Done (owner, 2026-10-14, "makes sense" on the six live moves): **prices on the shelf price, and Home's
  price tile turns.** Every price measure (price changes, the basket, the
  same item at other shops) uses the shelf price per unit before printed
  discounts (`insights._shelf_unit_price`); spend stays what was paid. Live:
  31 of 60 price histories held once discounts stopped counting. Each history
  is read as runs of one price (`insights.price_move`): `stayed` (one way, in
  one step or several, the last price paid twice), `latest` (only the last
  date new), `offer` (one date off and back: not a change), `keeps_changing`;
  within 3% is one price. Home's tile turns through `price_moves` (3+ buys,
  10%+, not an offer, newest move first): every 6 s, a swipe either way, a
  tap opens the product, "Up on 4 Sep, and stayed" / "Up in 2 steps since 21
  Jul" / "Down on 29 Sep, the last time" / "Keeps changing". Live: 6 moves.
  Insights contract 8. Merged as #148.
- Done (owner, 2026-10-14, after five rounds of screenshots): **Home's
  month tile says the pace.** This month so far and one word ("Faster than
  usual", "About as usual", "Slower than usual"; within a tenth either way is
  about as usual; nothing said before the 7th). The tile's colour says how
  far off the usual the month is: green when consistent or spending less,
  through orange to a soft coral from 70% above, never a warning red ("an
  insight; we don't want users to feel bad"). Only when the month is
  noticeably off (beyond a tenth, from the 7th) does the tile show a small
  chart: running totals over the last 10 days, this month bright with a dot,
  the usual dashed, last month faint, each named at its end (no legend),
  smoothed through the real totals every 4 days (monotone, so a total never
  dips; the dot exact), the gap shaded with the difference ("+82,64 €").
  Otherwise one line: "Usually 119,28 € by the 14th · September 145,21 €".
  A tap opens the whole month's chart and "A usual month ends at …".
  The usual is the mean of up to 6 whole months before, each cut at the
  same day (`insights.usual_by_day`, `usual.running`, each month's
  `running`); the split into causes (#145) stays in `insights.json`, off
  Home. Merged as #146 on the owner's "good". Seen only in its coral case
  (the live data); green and "about as usual" are untested on screen.
- Built (owner, 2026-10-13: barcodes first, **exact matches only**, "might
  move to best guess, let's see how it looks"): `grocery-app db barcodes`
  searches Open Food Facts (free) by brand and name, sold in Germany, for
  every product with a brand and no barcode, and writes one only when brand,
  name (their name says nothing ours does not) and size all match and exactly
  one barcode does, and no other product of ours has it
  (`grocery_app.barcodes`, `provenance.barcode_from`). Shown only unless
  `--write`. First run, laptop copy of the catalog (96 products without a
  barcode): **3 found, 19 near misses, 74 nothing.** 14 of the 19 near misses
  fall short only because the product's size is unknown (the receipt names a
  family). Best-guess (B) would be visibly wrong on some: one barcode for all
  three Mini Muffins flavours, one for both Milsani Skyr products. Of the 3
  found, Kerrygold Butter 250 g got a Norwegian-prefixed barcode that Open
  Food Facts lists as sold in Germany (crowd data). **Nothing written yet,
  live not run**: the owner looks first. The user's barcode photo waits until
  after the Ready-for-iOS milestone (it adds a button, which restarts the
  screens-unchanged clock).
- Fixed (owner, 2026-10-14): **removed receipts came back** after a reload.
  The removal waits 8 s for Undo and was dropped when the page reloaded or
  closed first (a new deploy reloads the phone's page too). Leaving or hiding
  the page now sends it (`keepalive`). A receipt being removed takes its
  questions and checks with it at once. Question cards say "Thank you: your
  answer helps the app learn." (owner: kinder, short).
- Tried and removed (owner, 2026-10-14): **paste a receipt**. A PDF copied
  from the Kaufland app did not reach the page on the iPhone. Researched the
  same day: REWE emails each eBon as a PDF, so a per-user forwarding address
  could import REWE without a tap (later, not agreed); Kaufland and Lidl keep
  receipts in their apps only, and fetching them would mean holding users'
  shop passwords (recommended no). One tap per receipt comes with the iOS
  app's share extension.
- Done (owner, 2026-10-14): **no People card**. Google sign-in decides who
  gets in: any verified address Google lets through (while the consent screen
  is in Testing, only its test users, up to 100) gets an account at its first
  sign-in, named with their Google first name ("Lea"; "Lea (address)" when a
  name is taken). The owner's step for a new person is now only: add them as
  a test user in Google Cloud. **Before publishing the consent screen**,
  anyone with a Google account could sign up and spend money: a limit comes
  first. Passwords and `/v1/users` stay (no page uses them now).
- Done (owner, 2026-10-14): **uploads are read 3 at a time**. Every upload
  is taken and stored at once and waits as `queued`; a reading line
  (`jobs.reading_line`, `READING_AT_ONCE`) reads three together, oldest
  first. Before, every upload was read at the same moment, and a batch of 20
  or 30 could run out of database connections (about 15), memory (1 GB) or
  the model's rate. A restart loses nothing: waiting jobs are rows, and
  `resume_unfinished` reads them. Tests read straight away (no line).
- Done (2026-10-14): **a refused Google sign-in is logged** with its reason
  ("… has not been invited", a missing CSRF cookie), in the server's log.
  A friend's sign-in reached Google and came back three times (11:19-11:22
  UTC) and was refused; the People card has no Google address but the
  owner's, so "not invited" is the likely reason, not yet confirmed.
- Done (owner, 2026-10-14): **Undo shows a ring** that empties like a clock
  as its 8 s run out (`UNDO_MS`, the same time the removal waits).
- Fixed (owner, 2026-10-14, a Kaufland app PDF): while a receipt was being
  read, with no receipt open, the page asked for `/v1/receipts/null` every
  3 s and showed "Input should be a valid integer". A queued job has no
  receipt id yet, and null matched the closed receipt's null
  (`openBeingRead`). Any upload on the Receipts tab did it. The PDF itself
  read perfectly: 10 of 10 lines, the total, the tax classes, both deposit
  returns, and the Kaufland Card discount on its line.
- Done (owner, 2026-10-14): **a newcomer's Home is a bar to 10 receipts**
  ("2 of 10 receipts") with three stops, each a promise: 1, where your money
  goes; 5, your regulars; 10, the full picture with prices that moved. A
  stop's Home card opens when it is reached (the month at 1, "your regular"
  at 5, "price up/down" at 10), and only if its data is real. From 10 the bar
  is gone. Stops from replaying the owner's first 27 receipts: a regular at 2
  (4 by 5), a price that moved at 11, Home's price card (3 buys) at 15.
  "What's due" is not promised (the owner: looking forward is a later
  stage). Insights shows a card with nothing yet closed, saying what opens it;
  Insights and Receipts say plainly when empty. Insights is not gated by the
  stops: a card shows as soon as its data is real. The demo has 10 receipts,
  so no bar.
- Done (owner, 2026-10-14): the costs card shows **what is billed** beside
  the list price. List price counts every web search at 1.4 cents, but the
  first 5,000 a month are free: October so far read as 21 cents a receipt at
  list price, about 3 cents billed. `/v1/costs` gained `billed_usd` and
  `billed_per_receipt_usd` (free searches shared evenly over the month's
  searches). Prices double on 2027-01-01 (`spend.py`).
- Fixed (owner, 2026-10-14): offline, the page said "Cannot load: Load
  failed" (the browser's words), as if the app broke. A request that never
  reached the server now says "no internet connection" (or "the server could
  not be reached; check your connection" when the phone thinks it is online),
  everywhere the page talks to the server, and the page loads again by itself
  when the connection comes back (`reach` in `review.html`).
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
- Done (owner, 2026-10-13, `JT Tortilla Wraps`): **a family line is named,
  not counted**. A line the receipt leaves at several products showed "2
  candidates"; it now shows the words every member's name starts with
  (`Tortilla Wraps`), else the deepest category they share, and only then a
  count (`normalizer.family_name`).
- Done (owner, 2026-10-13): **a typed answer is a hint**, not the product.
  Words typed in a line's fix box ("None of these: save my description")
  are searched with the printed line and the shop, and the reader takes the
  product the pages show that fits them, keeping the words beside it; only
  when nothing found fits do the words make the product (the Pepsi case:
  "Pepsi. Not cola" had become a product "Pepsi · Pepsi"). A failed search
  reads the words alone, never leaves the answer waiting. One extra search
  per typed answer, which the minimum-input rule keeps rare. One real check
  (Gemini, 2026-10-13, `PEPSI 1,25l` with "Pepsi. Not cola"): it searched
  the words, then read **Limonade, Pepsi**: better than "Pepsi · Pepsi", but
  it followed "not cola" over the pages (Cola, Pepsi was right). Open, the
  owner's call: when the pages and the typed words disagree, which wins.
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
  then days, inside a month.** The owner, 2026-10-13: the view opens at the
  level the receipts fill (early in a month, its weeks or days; further back,
  months, then years), and each tap zooms one level in.
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
- Switched on (2026-10-13): **Google sign-in**. The deploy carries
  `GOOGLE_CLIENT_ID` and `GROCERY_OWNER_EMAIL`; `/v1/auth/config` names the
  client id on both server addresses (both are Authorized JavaScript origins).
  The consent screen is still in Testing. The OAuth client secret is not used
  (the server checks the ID token Google signs) and is stored nowhere.
  First try on the owner's phone: picking the account did nothing (the
  pop-up never handed its answer back; no request reached the server). The
  page now uses Google's **redirect mode** (`POST /v1/auth/google/redirect`,
  the sign-in comes back after the `#`). Needs both addresses +
  `/v1/auth/google/redirect` as Authorized redirect URIs (exact URIs, path
  included; the JavaScript origins take no path). Both set by the owner.
  Confirmed 2026-10-13 20:34: the owner signed in on the phone through the
  redirect. The first pop-up failure was probably Google still taking up the
  origins just added; redirect is kept as the surer way on phones. The 16 s
  wait on a sleeping server: the bottom bar is now hidden under the sign-in
  card (#127), where its tabs looked live and did nothing.
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
3. ~~Google sign-in on the web.~~ Built, and **switched on 2026-10-13**. Who may sign up was decided by the lead while the owner was away, as
   the safe default (reversible): **invite-only**; dropped 2026-10-14 by the
   owner (see Now: a first sign-in makes the account). Passwords keep working. Sign-ins last 90 days (migration 0020,
   `api/google_sign_in.py`). The owner's steps (details in
   `docs/designs/backend-api.md`, "Switching on Sign in with Google"):
   1. Google Cloud Console: an OAuth consent screen, then an OAuth client
      (Web application) with the server's address as Authorized JavaScript
      origin.
   2. GitHub repo settings: variable `GOOGLE_CLIENT_ID`, secret
      `GROCERY_OWNER_EMAIL`.
   3. Run the deploy workflow.
   4. Add each person as a test user while the consent screen is in Testing.
   Done 2026-10-13: steps 1-3. The consent screen is in Testing (only its
   test users can sign in).
   No route removes a user yet (their receipts would go with them); a
   removed user's sign-ins end with the row. Apple sign-in is deferred (it
   needs the paid developer account).
4. ~~Insights screen.~~ Done (2026-10-13): five cards, one question each,
   with their coverage; every product opens the drill-down (see Now).

## Open decisions (the owner's), as of 2026-10-14

- **Barcodes: keep exact-only (A)?** Asked 2026-10-13 after the first run
  (see Now), unanswered. Recommendation: yes; the gap is the unknown size,
  not the rule, so the next barcode step would be a size for products read
  from a receipt (e.g. from the price paid). Then run `db barcodes` on live
  and `--write` what it finds.
0. **Ready for iOS criteria** (owner, 2026-10-13: "no hand database fixes"
   is not needed, and "two weeks unchanged" was the lead's stand-in).
   Proposed: the owner says the screens are settled, Google sign-in is on,
   a second person uses it. Unanswered. Also: GDPR items (privacy page,
   deleting users, what the owner sees of others) wait until the legal side
   is clear (owner).

**Next session:** merge `feat/price-line-and-regulars` on the owner's yes
(or change it as he says). After that the agreed list is empty. Proposed
(2026-10-14, unanswered): no new features until the milestone, except
privacy and account deletion, moved up before a second person.

## Next build (agreed 2026-10-14): insights about the past, done right

The owner: past and present first, no recommendations until the insights are
complete ("this receipt at the other chain" is a recommendation: parked).
A comparison must be like for like, and an insight must have one meaning.

1. ~~**Home's month comparison, split into its causes.**~~ Built 2026-10-14,
   then replaced on Home by the pace (see Now). Today Home sets
   "October so far" (14 days) against all of September. Instead: the same
   days of both months (1-14 Oct against 1-14 Sep), and the difference split
   so every euro lands in one part: **different things** (bought in only one
   of the two periods), **more or less of the same things** (bought in both,
   in other amounts), and **prices** (the same things, priced now against
   then; shelf price, see 2). Lines not placed on a product are their own
   small amount. Example: "+40 € against 1-14 Sep: 25 € from things you
   didn't buy then, 12 € from buying more of the same, 3 € from higher
   prices." The owner: "do it, then I'll comment" (build it and show him;
   he decides on seeing it).
2. **Prices on the shelf price, and the price tile that rotates.**
   - (Done, #148.) Price changes are measured on the **shelf price before printed
     discounts** (`gross`), not on what was paid: on the owner's first 27
     receipts, 109 of 237 product lines carry a printed discount, many 10%
     (likely his GLOBUS staff discount), and today each counts as a price
     change (`insights._paid_unit_price` uses `net_paid`).
   - (Done, #150.) **A new insight: what discounts saved you** (owner: "tell me how much I
     saved with the discount"; Kaufland's receipt prints it too), from the
     printed discounts, per shop and per month.
   - Home's price tile **rotates** through several products (auto-advance,
     swipe back and forth, tap opens that product). Only real changes:
     bought at least 3 times and moved at least 10% (live, 2026-10-14: 35
     products changed, 21 of them on just two buys, e.g. Cola 1,07 -> 0,54,
     an offer). Each says **when** and **how**: "went up 4 Jul and stayed",
     "dropped once, then back (probably an offer, not counted)", "keeps
     changing". No fixed window: the date of the change is the window.
   - (Built, PR open.) The product page opens with a **price line** (date
     across, price up) over the whole history, the purchase list under it;
     the calendar gets **weekday letters**.
3. (Built, PR open.) **Your regulars, rotating** like the price tile ("7× in
   6 weeks").

Research (private claude.ai pages, the owner's account): the landscape of
apps and 75 open-source projects, with "Where your app wins",
https://claude.ai/artifact/4hVAEvSZi814KQNWH3d8F6; the open-questions list,
https://claude.ai/artifact/WHW7obc3X2YrQYAnpwvSJs.

**The owner's to-dos** (none blocks building): use the app for two weeks
with every receipt from the phone; a second person with real receipts;
the demo pictures laptop run
(above); the billing alert; two receipt questions on the open-questions
list (`Kleenex Ultra Soft W`, `Volvic 1,5 L`).

## Milestone: Ready for iOS (target 2026-11-02)

- The screens are settled: unchanged for 2 weeks after the designer's input.
  All screens are redesigned as of 2026-10-13 (Insights last); the two weeks
  run from there.
- 2 weeks of real use with no database fix by hand.
- ~~Google sign-in on the web.~~ Works (2026-10-13, the owner's phone).
- A second person using it with real receipts.

## Parked (later, not now)

- A phone preview of a branch (owner, 2026-10-14: "having it deployed is
  best, it can support many possibilities; backlog, not now"). A Cloud Run
  service `grocery-preview` of its own, deployed by hand from a branch, on
  the live data but looking only (no migrations, no jobs or pictures, every
  write refused but signing in), a strip naming the branch. Needs: the
  owner's OK on the risk (unmerged code reading live data, a second public
  address), GitHub's deploy permission widened to hand-started runs, and the
  preview address added to the Google sign-in client. A first version of
  the server part is in a git stash (`preview-mode`) on the laptop. Until
  then, screens are shown by screenshot (`scripts/preview.py --shot`), or a
  short video for a flow.

- Barcodes, the rest: a barcode photo from the user (after the milestone),
  and a known size for products read from a receipt (see Now).
- Attention follows seriousness and freshness (a level-4 line right after
  the scan asks loudly; a random check waits). The levels it would use are
  counted (`GET /v1/sureness`).
- Lifestyle, personas (the owner's three, 2026-10-12: the trend lover, the
  saver, the deal hunter; features are checked against who they serve), deals, dislikes, and zooming through time in insights
  (Receipts zooms by month now; weeks and days are next there).
- Cleanup: old English-named products, doubles from early catalog work.
- Insight tiles people choose (owner, 2026-10-14): remove a tile, add
  another from the insights there are. Worth building once there are more
  insights than Home fits.
- Offers not printed on the receipt (owner, 2026-10-14): a lower shelf
  price, a near-expiry sticker, the shops' weekly offer lists; and an
  optional "Was this on offer?" when a known product's price differs, asked
  only behind the questions button with its badge, never forced, and never
  again for someone who doesn't answer.
- Health-related insights (owner, 2026-10-14): later.
- "This receipt at the other chain" (2026-10-14): a recommendation, parked
  until the insights are complete. Checked: under 5% of the owner's products
  exist at the other chain as the same product, so it needs the closest
  equivalent (same kind, size, price tier), the owner's call when it comes.
- Fuel (owner, 2026-10-14): supermarkets often sit next to a petrol or
  charging station, and filling up repeats like shopping. Track fuel
  receipts and prices, so a later recommendation can weigh the station's
  price too. Germany publishes every station's fuel prices live (the
  Markttransparenzstelle, open through Tankerkönig).
- Families (owner, 2026-10-14): connect people, so a household sees its
  shopping together as well as each person's own.
- A grocery budget (owner, 2026-10-13): set one for the month and see how far
  off you are, or the app suggests one from past months. Serves the saver.
- A privacy line on You (owner, 2026-10-14: parked, "we are making the app
  better"). Proposed wording, true today: only you see your receipts in the
  app; photos are read by Google's Gemini and stored in Frankfurt; the
  developer may look at an upload to fix reading mistakes; nothing is sold.
- Privacy page and account deletion (owner, 2026-10-13: backlog, not now).
  Needed before Google sign-in leaves Testing: publishing asks for a homepage
  and a privacy policy URL (`/privacy` on the server; Google may refuse a
  `run.app` address, then a domain of our own, about 10 EUR a year). GDPR
  starts with the second person's data: say what is stored, where (Frankfurt,
  read by Gemini) and who sees it (the owner), and let a person delete their
  account and receipts (no route does that yet).

## Gotchas

- Database backups (on since 2026-10-13, owner: top priority): Cloud SQL
  takes one a day at 01:00 UTC and keeps the last 7, stored in the EU
  multi-region; a first one was taken by hand the same day. Automated backups
  are deleted with the instance. Restore:
  `gcloud sql backups list --instance=grocery`, then
  `gcloud sql backups restore <id> --restore-instance=grocery` (overwrites
  the database).

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
