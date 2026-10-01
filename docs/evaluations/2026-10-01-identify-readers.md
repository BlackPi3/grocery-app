# Comparison: who reads a receipt line best, with and without web search

2026-10-01 · Parham asked for a level playing field: "most of these questions
Google answers with its first result; maybe Gemini, which is Google's, is
better suited." This compares three readers on the same lines.

## The three readers

| reader | model | search | runs on |
|---|---|---|---|
| Claude | Claude Sonnet (`claude -p`) | none | the subscription |
| Claude + search | Claude Sonnet (`claude -p`, WebSearch tool only) | web search | the subscription |
| Gemini + search | Gemini 3.8 Flash (Google API) | Google Search | paid per call |

Sonnet and Flash are the same size class, as Parham asked (not Opus, not Pro).

## What was held equal

- **Instructions:** identify prompt v6 for all three. Both search readers also
  get the same added paragraph (`identify.SEARCH_HINT`): search when a part is
  unclear, using the whole printed line with the shop's name, then check what
  was found.
- **Evidence:** price paid, VAT rate, the other lines of the receipt, the
  shop's similar products, the abbreviations learned from the memory.
- **Judge:** the same Claude judge (judge-v2) for all three, and every line it
  did not call `right` read by hand, for all three alike. The judge is Claude,
  so it could favour Claude's wording; reading every non-right line is the
  check on that.
- **Lines:** three sets, each scored the same way.

| set | lines | what it is |
|---|---|---|
| answer sheet | 135 | the September receipts; v1 to v6 were tuned on it |
| page answers | 6 | lines Parham answered on the review page on 2026-10-01 |
| October | 13 | four receipts no reader and no prompt version had seen, answered by Parham before anything was saved |

The first set flatters every reader, and Claude most: the instructions were
written while scoring Claude on it. The October set is the only untouched one,
and it is small.

## Results

The judge's counts (mistakes = false detail + wrong):

| set | reader | right | missing | false detail | wrong | asked |
|---|---|---|---|---|---|---|
| answer sheet | Claude | 84 | 44 | 1 | 0 | 6 |
| | Claude + search | 80 | 46 | 3 | 0 | 6 |
| | Gemini + search | 82 | 43 | 1 | 0 | 9 |
| page answers | Claude | 2 | 3 | 0 | 0 | 1 |
| | Claude + search | 1 | 4 | 0 | 0 | 1 |
| | Gemini + search | 3 | 2 | 0 | 0 | 1 |
| October | Claude | 5 | 6 | 1 | 1 | 0 |
| | Claude + search | 6 | 5 | 1 | 1 | 0 |
| | Gemini + search | 5 | 6 | 1 | 0 | 1 |

Read by hand, across all 154 lines:

| reader | real mistakes | asked | notes |
|---|---|---|---|
| Claude | 2 | 7 | both mistakes on the October set |
| Claude + search | 6 | 7 | four more on the answer sheet, two of which the judge missed |
| Gemini + search | 2 | 11 | asks more; said "cannot tell" where both Claudes were wrong |

What decided it, in kinds of line (no receipt text here: the repo is public):

- **Found only with search:** a store-brand line whose word looks like a
  medicine but is a greeting card. Both search readers got it; Claude asked.
- **Read better by Gemini:** a tissue box's `4l`, which is four-ply, not four
  litres; and a cereal line printed with brand and "Bio Schoko" only, which
  Gemini declined to guess while both Claudes called it chocolate (it is
  muesli).
- **Bolder, not better, with search:** given the search paragraph, Claude
  guessed more details (a dessert as "pudding powder", tissues as pocket
  tissues, a cut café word as "compote" twice) without searching for them.
- **Missed by all three:** a regional meat brand alone on the line, an
  abbreviated product-line name (`Ult.` read as "Ultra"; it is "Ultimate"), and
  the cereal line above. A web search for the whole line finds each one.

## The finding that matters

**Search was hardly used.** Gemini searched twice in about 160 calls. It and
Claude both answered from what they already know, confidently, even on the
three lines a search would have settled. So this comparison mostly measured
each model's own knowledge and caution, not search:

- Gemini Flash is the more careful reader: the same real mistakes as Claude
  without search, fewer than Claude with search, and more questions.
- Giving Claude search, as an option, made it bolder, not more accurate.
- Neither model searches when it should. Search as an option does not work;
  it has to be triggered when the reader is unsure.

## Cost and time

- Gemini: about 160 calls, 0.59 M input and 0.17 M output tokens (thinking
  included), 2 Google searches. At Flash prices that is well under 1 EUR of
  the 5 EUR put in; AI Studio shows the exact figure.
- Claude: on the subscription, no money.
- Speed: both took a few seconds per line; neither is a bottleneck.

## Next

The same comparison again, with search made a step rather than an option:
the reader marks each part of the line as sure or not, and a part that is not
sure triggers a search, built from the whole line, before the answer.
Then the October lines and the next untouched batch decide.
