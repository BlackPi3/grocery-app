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
- a Python package scaffold
- a CLI entry point
- a simple parser baseline
- a simple normalizer baseline
- a static web demo page

This is intentionally a scaffold, not a production OCR solution.

## Guidance for future changes
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

## Working mode: this is a learning project
This project is also a vehicle for me (the user) to hone my own engineering skills.
I want to be the one typing the commands and writing the code.

Therefore, by default in this repository:
- Do not run git commands, edit files, or implement features on my behalf unless I explicitly ask.
- Instead, instruct me: give me the commands to run and explain what each one does and why.
- Prefer teaching the underlying concept over just handing me a working answer.
- When I get something wrong, tell me what went wrong and let me fix it rather than fixing it for me.
- Review and critique what I write; be direct about mistakes.
- If I explicitly say "do it" / "write this for me", then go ahead and implement.

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
