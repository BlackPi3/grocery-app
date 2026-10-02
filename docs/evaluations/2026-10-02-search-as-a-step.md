# Search as a step: Claude and Gemini, both searching every line

2026-10-02 · Follows `2026-10-01-identify-readers.md`, which was invalid
because the search it set out to compare barely happened. No receipt text in
this document: the repo is public.

## What changed since the invalid comparison

- **The code searches, not the model.** Every line that is groceries is
  searched for the whole printed line, the shop's name and the address the
  receipt prints, and read again with the results (`identify.read_line`). A
  line that is not groceries (café, cards, flowers, bags) is not searched:
  which photo print it was does not concern the insights.
- **Every search is recorded** (queries and the titles of the pages returned),
  and the report lists any line due a search that was not searched *before*
  it shows a number. Both runs below searched every line due one.
- **Why Gemini had not searched.** Gemini does not search while it is asked
  for JSON, by a schema or in words: the same request searched five times with
  no format and never with one. Its search is now free text, then a second
  call copies the report into the format.
- **A question carries choices.** A line the reader still cannot tell comes
  with what the search narrowed it to.

## The lines

Only lines that went wrong or were asked in the invalid run, plus the
untouched October receipts (Parham: "never the whole set again"):

| set | lines | what they are |
|---|---|---|
| problem lines | 9 | the mistakes and questions of the invalid run, café lines left out |
| October | 13 | four receipts no prompt was tuned on |

Same reader prompt (identify v7) and judge (judge-v2) for both readers; every
verdict below was read by hand.

## Results

| reader | mistakes | questions | right answer among the choices |
|---|---|---|---|
| Claude, before search (v6) | 2 | — | — (bare questions) |
| Claude + web search, told the shop's location | 1 | 7 | 1 of 3 |
| Gemini + Google Search, told the shop's location | 0 | 6 | 3 of 3 |

- **Claude's one mistake:** a cut product-line word completed the wrong way,
  although its own search had returned the right product first. Gemini left
  the cut word out instead of guessing (said less, not a mistake).
- **Where they asked,** Gemini's choices held the right product each time (a
  brand-only meat line, a brand-only herb mix, a cereal line whose words say
  chocolate); Claude's held it once.
- **Two questions remain that search cannot help:** a till that prints only a
  category, and a deli tub whose variety the shopper did not know either.
- Telling Claude the shop's location turned one question into an answer and
  improved one set of choices; both readers' results were mostly German sites
  before and after.

## Cost

Gemini: 62 Google searches on the 22 lines in the final run. Google lists
5,000 searches a month as free on a paid account, then $14 per 1,000; the
billing page has the exact figure. Claude: on the subscription.

## Decided

Identify reads and searches with Gemini through the API (Parham,
2026-10-02). Not a Gemini subscription: since 18 June 2026 a personal plan
gives no programmatic access.
