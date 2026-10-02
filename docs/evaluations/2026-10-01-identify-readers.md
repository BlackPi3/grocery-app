# A comparison that did not happen: Claude and Gemini with web search

2026-10-01 · **Status: invalid. Do not use its numbers.** The valid comparison is
`2026-10-02-search-as-a-step.md`. Kept as a record of
what went wrong, so the next comparison does not repeat it.

## What it set out to do

Parham's question: most lines the app asked him about, Google answers with
its first result. Would Gemini, which is Google's, do better than Claude if
both may search? Three readers on the same lines, prompt (identify v6),
evidence and judge:

| reader | model | search |
|---|---|---|
| Claude | Claude Sonnet (`claude -p`) | none |
| Claude + search | Claude Sonnet (`claude -p`, WebSearch tool only) | web search |
| Gemini + search | Gemini 3.8 Flash (Google API) | Google Search |

## What went wrong

1. **The variable under test was never exercised.** Search was only offered,
   never required. Claude used it: two to four searches on most lines it
   could not read. Gemini used it twice in about 160 calls, and before none
   of its questions. "Gemini + search" was Gemini without search, so the
   field was not level and the comparison says nothing about Gemini with
   search.
2. **The searches were not recorded** for Claude, so the mismatch was
   invisible until after a result had been reported.
3. **Conclusions were drawn anyway** ("no clear winner", "Gemini is the more
   careful reader"). They rest on a comparison of the models' own knowledge
   and caution, not of search, and are withdrawn.
4. **It ran on all 154 lines.** The signal was in the fifteen or so lines a
   reader asked about or got wrong; the rest only cost time. Next time: only
   those lines (Parham, 2026-10-01).
5. Lesser, but real: identify's instructions were tuned on Claude's answers,
   and the judge is Claude.

## What was learned on the way

- **Gemini declines to search when it believes the line lacks the
  information**: "only the brand is printed", "a generic till entry",
  "truncated". Asking for the answer without the strict output format did
  not change that: re-run on its seven question lines, it searched for one.
- **Claude searches, then throws the findings away.** For a line printing
  only a brand, it found that the brand makes sausages, cheese and yogurt,
  and still asked the shopper the bare name, without the choices it had
  found or what the price suggests.
- **Neither model searches lines it is wrongly sure of.** A cereal line
  printed as brand + "Bio Schoko" was called chocolate (it is muesli); an
  abbreviated product-line name was expanded wrongly. A search for the whole
  line finds both.

## What a valid comparison needs

- Search as a **step**, not an option: when a reader cannot tell, or marks a
  part of the line as not sure, a search on the whole line runs before any
  answer or question, for every reader alike.
- Every search **recorded**, per line, per reader, and checked to have
  happened before any number is read.
- Only the lines that were asked or wrong, plus the untouched October set.
