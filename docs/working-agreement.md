# Working agreement

How the owner and the coding assistant work on this repo. It holds for every
session, on the laptop or in the cloud. `CLAUDE.md` is the short version;
this is the long one. The current state of the work is in `docs/status.md`.

## Who does what

- The owner decides: what gets built, how fine-grained it is, what the data may
  claim, and whether the result makes sense. The assistant writes the code,
  the tests and the commits.
- Bring the owner decisions, not typing. Never route a question to the owner
  that a lookup, the catalog, a search or a model could answer.
- Agree on *what* before building *how*. A question answered with "proceed"
  approves that one thing, not a whole list of options.
- When the owner asks a question, the answer is the deliverable. Do not start
  side work alongside it.
- Say plainly when the owner is wrong, and expect them to be right often:
  they are the only authority on what they bought and how these shops behave.
- A UX designer advises. The owner relays the advice and decides. Never plan
  work as waiting on the designer.
- Push back on perfecting. When a new nuance opens up, ask whether it blocks
  getting the app ready. If not, park it on the open-questions page. Still
  report limits honestly.

## How to write to the owner

1. One topic per message. If more are waiting, end with one bold line, such
   as **2 more topics waiting.**
2. Answer first. No repetition, no long explanations: the owner asks for
   details.
3. At most one question, at the end, marked **Your decision:**, with a
   recommendation, answerable in a word or two.
4. Never mix status with questions.
5. As short as possible. Use plain, ordinary words and short, literal
   sentences. Give a real example rather than an abstraction. One idea per
   paragraph. When the owner says they are confused, remove detail rather than
   adding it.
6. Infra topics (hosting, cost, latency): explain the mechanism in a sentence
   or two. The project is also for the owner to learn from. Name the monthly
   cost of anything that runs all the time, and default to the cheap option.

## Shipping

- Once the owner agrees to build something: branch, commit, push,
  `gh pr create`, wait for CI, `gh pr merge N --merge --delete-branch`, watch
  the deploy, then report. Don't ask about any of these steps. If the owner
  dislikes the result, revert it.
- Every branch ends in a PR. Never merge, fast-forward or push into `main`
  directly. The PR history is part of the portfolio.
- Commit in small, logical steps.
- Every PR that changes the state of the work also updates `docs/status.md`,
  so any session can stop at any time without a wrap-up message.
- At a milestone (something the owner could tell someone else: a new ability,
  or the app running somewhere new), update the dated **Stage** line and
  **Next** in `README.md`.

## Tests

- Every change carries its own meaningful tests on made-up data. The owner
  should never have to ask for them.
- A test compares the real artifact, not a copy normalized by the same code
  that made it. Watch for assertions that would hold anyway (a bare `200`, a
  constant compared with its own literal).
- Prove each new test: break the behaviour it guards and check that this test,
  and only this one, fails.
- Run the suite with `DATABASE_URL` set so nothing is skipped, and only ever
  against a database named `grocery_test` (the fixtures reset its schema).
- Never run the paid test while another pytest run is using `grocery_test`.
- No known defect is left open while moving on.

## Money

- No paid model call in tests (see `CLAUDE.md`).
- State the cost before any run that spends money. Prefer cached results.
- The server reads photos with Gemini on Vertex AI. One-off curation, judging
  and analysis happen in the session, not through a paid API.

## Privacy

The repo is public. Docs, tests, fixtures and code comments use made-up
examples only: no real receipt text, no addresses, nothing that ties the data
to a person, workplace or place. Receipt photos, truth files, transcripts,
crawls and uploads live under `data/` (gitignored). Never force-add an ignored
path. Before every commit, check `git status` for anything under `data/`.

## Product rules

These are the owner's decisions. Each one came from a real case.

- **Minimum input.** The user scans. Rarely, they tap to pick an item. They
  never type. Every feature costs one tap at most.
- **General for all users.** Design every lookup for any user and any shop.
  The owner's data is test evidence, not the design target. For example,
  pictures come from the website of the shop the receipt is from, then Open
  Food Facts, then the web.
- **Search before asking.** No product question reaches a person until the
  model has searched and narrowed it down to choices to confirm. Lines that
  are not groceries (a café, a gift card) are neither searched nor asked.
- **Don't hand-classify the obvious.** If a model or a lookup knows what
  Coca-Cola is, never ask a person.
- **An answer is a hint.** When the right product is not among the options,
  the shopper's answer goes into the search with the printed line, price and
  shop. It is not stored as the product.
- **Describe, don't format.** A person explains what something is in their own
  words. The app turns that into its own format and keeps the original words
  beside it.
- **One field, one job.** A field records one fact. Before adding one, ask
  whether something already records it.
- **The answer key changes only when the photo says so**, never to match a
  model.
- **Two truth sets.** Reading truth comes from the photo. What a line *is*
  can only come from the shopper.
- **A receipt is lossy.** A printed name can stand for a family of products.
  Price is part of the evidence. Don't guess an exact article to look precise.
- **Budget brand, not own brand.** The insight is "the shop's cheaper
  alternative", whoever owns the label. Premium store lines count as name
  brands.
- **Categories:** three German levels, taken from retailer trees, not
  invented. A category must tell a person what kind of thing it is, not just
  be true.
- **Coarse lines are answers.** A till that prints only a category gives a
  category-level answer. That is not a failure.
- **Nothing the app writes is permanent.** Every line says who said what it
  is (you or the app), and spot checks measure the app's error rate.
- **Like for like.** A comparison sets equal things side by side (the same
  days of two months, not 14 days against 30), and an insight has one
  meaning: when a number could move for several reasons (more trips, other
  things, higher prices), it is split into those reasons, not shown as a
  fun fact the user cannot read.
- **Insights before recommendations.** The past and the present come first;
  nothing recommends until the insights are complete.
- **Shelf price, not discount.** A price change is the shelf price moving.
  A printed discount (an offer, a card, a staff discount) is not one; what
  discounts saved is its own insight.
- **Questions are optional.** They wait behind a button with a badge, are
  never pushed in front of the user, and someone who doesn't answer is left
  alone.
- **The owner sees it, then decides.** For a screen or an insight's look,
  build it and show it; his comments come on seeing it.
- **No per-mistake rules.** Each improvement uses one of five levers:
  evidence, tools, model, knowing when to ask, and learning from
  confirmations.
