# CLAUDE.md

## Project overview
This project is a portfolio-oriented grocery receipt intelligence app.

The long-term product goal is to read grocery receipts, build item-level purchase history, and surface insights that banks and supermarket apps cannot provide, including:
- personal inflation by basket
- repurchase cadence and predicted needs
- own-brand vs. brand spend
- same-item comparison across stores

The project is being built as a reusable pipeline with a disposable demo UI:
1. receipt parsing
2. product normalization
3. purchase history and insight generation
4. web demo (temporary) and later iOS app

## Architecture
The durable part of the system should be a Python package with a CLI.

The intended shape is:
- receipts/*.jpg -> parser -> parsed.json
- parsed.json -> normalizer -> purchases.json
- purchases.json -> web demo and later iOS app

The contract that matters most is purchases.json.
Everything above it should be durable and reusable.
Everything below it can be throwaway UI work.

## Product priorities
The project has three goals in priority order:
1. Portfolio piece for software developers
2. Demoable via a shareable link
3. Real product eventually, so avoid throwaway implementation choices where possible

## Important constraints
- Never commit personal data. The repo is public: everything under `data/` and `web/purchases.json` is gitignored, and docs, tests and fixtures use made-up examples only.
- Do not hand-fix parser output in demos. Report accuracy honestly.
- The parser should be treated as an imperfect, testable system rather than a polished demo trick.
- The normalization layer is one of the most important and interesting parts of the project.
- The project should be designed so the same backend logic can eventually support a FastAPI service and later an iOS app.

## Demo philosophy
The web demo should be lightweight and mobile-friendly.
It should feel like a concept demo that can be shared with someone on their phone.
It should not depend on Xcode, provisioning, camera permissions, or a simulator.

## Technical direction
- Use Python for the durable parsing/normalization pipeline.
- Keep the CLI as a practical developer interface for running batch processing and testing.
- Favor a clear, explicit, reusable data contract over quick ad hoc scripts.
- Keep the project structured so later work can evolve into a real backend and app.

## Current implementation status
The current repository includes:
- a Python package with a CLI (`purchases`, `eval`)
- a normalizer that resolves raw receipt lines to a product catalog
- one set of verified receipts under `data/receipts/` (gitignored): photos,
  `truth/` JSON, and the hand-typed `transcripts/` plus the converter that builds them
- `grocery-app extract`, the vision-model parser, cached per model and prompt version
- an evaluation harness that scores extraction per store and per field
- a static web demo page

Layout rule for `data/`: name things by what they are (receipts, extracted,
products, purchases), and keep interpretation out of the truth files — a truth
file holds what the paper prints (`tax_class` `A`/`1`), never what it means.

## Guidance for future changes
Every change goes through a pull request with green CI (`ruff check src tests` and
`pytest`). New behaviour comes with tests on made-up data; a change that touches a
seam between stages extends `tests/test_pipeline.py`.

No test may call a paid model: `create_app` takes the extractor as an argument with
no default, so forgetting it is a 503 rather than a charge. The one test that does
make a real call is marked `paid` and deselected by default. Run it before merging
any change to `extract.py`, the receipt schema, or the upload route, with the
reader the server uses (`GROCERY_READER`: `api` or `claude-code`, the subscription;
decided 2026-09-26, when the API account had no credit and was not to be topped up):

```
DATABASE_URL=... GROCERY_READER=claude-code \
    GROCERY_TEST_PHOTO=data/receipts/images/IMG_5384.jpeg pytest -m paid
```

When making changes:
- preserve the separation between parsing, normalization, and UI
- keep artifacts like parsed.json and purchases.json well-structured and explicit
- prefer small, modular components over a single monolithic script
- document assumptions and limitations clearly
- avoid hiding poor parsing quality behind polished output

## Suggested development sequence
1. Improve the parser with more realistic receipt handling
2. Add stronger evaluation and accuracy reporting
3. Build a more thoughtful normalization layer
4. Generate richer purchase-history insights
5. Create a stronger web demo around the insights

## Working mode: I decide, you implement
I am not here to type. My job on this project is the design decisions and the
judgement — what we build, at what granularity, what the data is allowed to
claim, and whether the result actually makes sense. Your job is to write the
code that follows from that.

Therefore, by default in this repository:
- Implement directly. Write the code, the tests, and the commits; do not hand me
  commands to run on my behalf unless I ask for them.
- Bring me the decisions, not the typing. When something turns on a judgement
  call — granularity, what counts as a product, whether a guess may be written
  down — stop and put the choice to me with a recommendation.
- Explain what you built and why, in terms of the decision it implements. I need
  to be able to tell whether it makes sense, not to have written it myself.
- Check the existing design docs and the actual data before proposing anything.
  Several times a proposal has been made against a field that turned out to be
  empty or a decision that was already taken.
- Tell me plainly when I am wrong, and expect me to be right often. I am the
  only authority on what I actually bought and on how these stores behave.
- Never route something to me that a lookup, the existing catalog, or a model
  could answer. My attention is for what only I can answer.
- Ask before committing, pushing, or opening a PR; then do it yourself.

## gstack
Use the `/browse` skill from gstack for all web browsing in this project. Never use `mcp__claude-in-chrome__*` tools.

Available gstack skills: `/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/design-shotgun`, `/design-html`, `/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`, `/connect-chrome`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/setup-deploy`, `/setup-gbrain`, `/retro`, `/investigate`, `/document-release`, `/document-generate`, `/codex`, `/cso`, `/autoplan`, `/plan-devex-review`, `/devex-review`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`, `/learn`.

## Notes for AI assistance
When helping with this repository:
- keep the portfolio goal in mind
- favor durable architecture over trivial shortcuts
- preserve the idea that purchases.json is the central contract
- be explicit about accuracy, limitations, and missing functionality
- help make the project feel like a serious engineering effort rather than a fake demo
