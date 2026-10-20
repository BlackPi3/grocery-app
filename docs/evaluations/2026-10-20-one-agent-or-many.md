# One agent or many? (research, 2026-10-20)

Question: for which parts of building software does a dedicated agent beat one
general agent with full context, and where does splitting make things worse?

Status: desk research only. Nothing here is measured on this repo yet; the
planted-bug experiment below is what would measure it. Several numbers come
from secondary write-ups and are marked as such.

## Finding

Split for **checking**, never for **building**.

- Building (deciding, architecture, writing code) needs the reasons behind the
  work. Every handoff loses some of them.
- Reviews and test-writing are read-and-judge jobs. They work as separate,
  read-only agents that get the spec and the diff, not the chat.
- A reviewer on the same model shares the builder's blind spots. A different
  model fails differently.
- The final say stays outside every model: CI, the truth-file scores, the owner.

## The five sub-questions

1. **Context per step.** Building needs the full history. Review needs spec +
   diff + rules (CLAUDE.md, working agreement), not the conversation.
2. **Shared blind spots.** A model misses its own errors far more often than the
   same errors shown as someone else's (Self-Correction Bench: 64.5% average
   miss rate; adding "Wait" cut misses ~89%). A fresh context removes the
   "my own work" framing but not the model's systematic errors: model-written
   checks make clustered errors, human errors spread out (secondary source).
3. **Handoffs.** The MAST taxonomy ("Why Do Multi-Agent LLM Systems Fail?")
   puts roughly a third of failures in inter-agent misalignment: lost history,
   withheld information, mismatched assumptions. Cognition's example: two
   sub-agents each built a correct part that did not fit the other.
4. **Cost.** Anthropic's multi-agent research setup reportedly used ~15x the
   tokens of a chat (secondary source). Three reviewers ≈ 3x one review. On a
   subscription this is rate limits, not money.
5. **Checks outside any model:** `pytest` + `ruff` in CI, no test makes a paid
   call, truth-file scores, nothing under `data/` committed, screens shown to
   the owner before merge.

## Hypotheses

| Hypothesis | Verdict |
|---|---|
| Building needs shared context | Supported (Cognition, MAST) |
| Reviews work better narrow and read-only | Partly: read-only is where splitting wins; too narrow loses the why, so give the spec |
| Agents checking agents share blind spots | Supported; fresh context helps, a different model helps more |
| Decisions stay with the owner | Yes; each extra agent step adds a chance of failure (Huyen, *AI Engineering*, agents chapter) |

## Aspects, split, and reasoning effort

Effort = how long the model thinks before acting. It pays where a mistake is
expensive and hard to see; it is wasted where a machine checks the result.

| Aspect | One agent or split | Effort |
|---|---|---|
| Deciding what to build | Owner, with one agent | high |
| Architecture | One agent | xhigh |
| Writing code | One agent | medium (CI catches mistakes) |
| Writing tests first | Split, given the spec only | high |
| Correctness review | Split, read-only | high |
| Security / personal-data review | Split, read-only | high |
| Design / screens review | Owner, with an agent's notes | medium |
| Performance | One agent | medium |
| Pipeline-stage (seam) review | Split | high |
| Docs / status.md | One agent | low |
| CI and merge | No model | — |
| Deployment | One agent + script | low |
| User feedback | One agent sorts, owner decides | medium |

`max` only for a bug that has already beaten `xhigh`.

## Experiment (not yet run)

1. A separate agent, sharing no context with the reviewers, plants 10–20 bugs
   on a test branch, of the kinds this project actually has: a truth file
   edited to match a model, a test that makes a paid call, personal data in a
   fixture, a broken `purchases.json` seam, a plain logic error.
2. Three setups review it: one general agent with full context; three narrow
   reviewers on the same model; one reviewer on a different model (`/codex`); GitHub Copilot's
   PR review (the owner has Copilot, confirmed 2026-10-20).
3. Count bugs caught **and** false alarms per setup.
4. Tests-first agent gets the spec only, never the code, so its tests cannot
   share the code's misunderstanding.

## Results, round 1 (2026-10-20)

Setup: a separate agent seeded 12 bugs and 3 decoys (correct but odd-looking
changes) into a believable PR, "the savings recap" (`experiment/seeded-defects`,
draft PR #172, never merged). Reviewers got the PR description and the branch,
not the answer key. All Claude reviewers ran at effort `high`. CI (`ruff`,
`pytest`) caught none of the 12.

| Bug | Kind | Full-context agent | Correctness | Guardrails | Seams |
|---|---|---|---|---|---|
| B1 | crash on a missed recap (None) | ✓ | ✓ | | ✓ |
| B2 | 5-cent tolerance, not 1 | ✓ | ✓ | | |
| B3 | field written `amount`, read `saved` | ✓ | ✓ | | ✓ |
| B4 | `beyond` sign reversed | ✓ | ✓ | | ✓ |
| B5 | `beyond` uses the wrong receipts | ✓ | ✓ | | |
| B6 | percent multiplied by 100 twice | ✓ | ✓ | | ✓ |
| B7 | API `saved` negative | ✓ | ✓ | | ✓ |
| B8 | seam test compares code with itself | ✓ | ✓ | | ✓ |
| B9 | assertion always true | ✓ | ✓ | | |
| B10 | paid call without `paid` mark | ✓ | ✓ | ✓ | |
| B11 | name + address in a fixture | ✓ | ✓ (out of scope) | ✓ | |
| B12 | truth holds "19%" not printed "A" | ✓ (as minor) | | ✓ | |
| **Caught** | | **12/12** | 11/12 | 3/3 in its area | 6 |

The three narrow reviewers together: 12/12.

- **False alarms.** Full-context agent: one "unsure" note against decoy D3.
  Seams: decoy D2 as "minor". Otherwise none.
- **Bug nobody planted.** Seams found a real one: the discounts card closes
  when a month has no line discounts, so a month whose only saving is the
  printed recap never shows it (`review.html` `savedCard`). No other reviewer
  saw it.
- **Cost.** Full-context agent: ~106k tokens, ~3 min. Three narrow: ~216k
  tokens, ~4 min in parallel. About twice the tokens for the same 12, plus
  the one extra real bug.
- **Not tested.** Codex (dropped by the owner). Copilot: GitHub refused the
  review, "the user who requested the review has reached their quota limit".
- **Limits.** One PR, one seeder, same model family throughout. The seeder
  and every reviewer are Claude, so a shared blind spot could not show up as
  a miss here. The "full-context" agent had the project's documents, not
  the conversation that built the change.

Reading: on this PR, one well-briefed agent at high effort was as good as
three narrow ones at half the cost. The narrow seams reviewer earned its keep
only on the bug that was not planted. Too small a sample to change practice;
a second round with a different seeder and Copilot would.

## Tools to apply it

- **Claude Code subagents** (`.claude/agents/*.md`): each reviewer is a file
  with read-only tools and its own effort level. This is the main mechanism.
- **Reviewers built (2026-10-20):** `.claude/agents/review-correctness.md`,
  `review-guardrails.md`, `review-seams.md`, all read-only and `effort: high`.
  Codex runs with `-c model_reasoning_effort="high"` (the installed CLI,
  0.42, rejects the `xhigh` in `~/.codex/config.toml`). Copilot's PR review
  has no effort setting.
- **gstack `/codex`**: a review by a different model (OpenAI Codex) — the
  cheapest way to get a reviewer that fails differently.
- **GitHub Copilot PR review** (`gh pr edit --add-reviewer @copilot`): a
  different vendor's reviewer that runs on GitHub, outside our sessions.
- **gstack `/review`, `/cso`**: same-model pre-merge and security reviews.
- **`/code-review ultra`**: Anthropic's multi-agent cloud review; billed.
- **Ponytail** (github.com/DietrichGebert/ponytail): a "write less code" skill
  with a review command. It is about how much code to write, not about
  splitting agents; it does not test any hypothesis here.

## Sources

- [Why Do Multi-Agent LLM Systems Fail? (review)](https://www.themoonlight.io/review/why-do-multi-agent-llm-systems-fail)
- [LangChain: how and when to build multi-agent systems](https://blog.langchain.com/how-and-when-to-build-multi-agent-systems)
- [Don't Build Multi-Agents (summary)](https://echai.ventures/how-founders-use-ai/ai-agents/should-i-build-one-agent-or-a-team-of-agents-working-together)
- [15x token cost](https://hackernoon.com/your-ai-agent-is-gaslighting-itself-and-your-multi-agent-fix-might-cost-15-more)
- [Self-Correction Bench](https://arxiv.org/html/2507.02778v2)
- [Specification as Quality Gate](https://arxiv.org/pdf/2603.25773)
- [Two Labs, One Desk](https://sawinyh.com/blog/two-labs-one-desk)
- [Self-review failure in code modernization](https://agentpatterns.ai/anti-patterns/self-review-modernization-failure/)
- Chip Huyen, *AI Engineering* (O'Reilly, 2025): agents and evaluation chapters
