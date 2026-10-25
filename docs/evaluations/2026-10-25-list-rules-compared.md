# The shopping list: which rule suggests best?

2026-10-25 · the owner's live history, with the paper-list words (#194). Each
day of the last 8 weeks, each rule drafts a list from what was bought before
that day; an item counts as needed when it was bought in the 7 days after.
That is a stand-in: nothing records what was needed but not bought. No
receipt text here: the repo is public.

**Terms** (owner, 2026-10-25: fewer false positives). Good: suggested and
bought. Noise: suggested, not bought (a false positive). Caught: the share
of the week's buys the list had.

| rule | a day | good | noise | right | caught | household caught |
|---|---|---|---|---|---|---|
| A: bought often (chance of 1 in 4 this week) | 17.9 | 6.4 | 11.5 | 36% | 26% | 0% |
| B: A, and half its usual time passed (live) | 9.3 | 3.9 | 5.4 | 42% | 16% | 0% |
| C: its usual time has passed | 21.2 | 4.1 | 17.1 | 19% | 17% | 7% |
| D: its usual time passes this week | 28.5 | 7.3 | 21.2 | 25% | 30% | 11% |
| E: C, and not twice its usual time | 8.3 | 2.0 | 6.2 | 25% | 8% | 5% |
| F: D, and not twice its usual time | 15.4 | 5.2 | 10.2 | 34% | 21% | 9% |
| G: A or C | 34.6 | 8.6 | 26.0 | 25% | 35% | 7% |

- **How often an item is bought predicts better than how long since it was.**
  The rules on the usual time alone (C, D) are right a fifth to a quarter of
  the time; the owner: "people's use is not that predictable".
- **The ceiling is the history.** Of 24.3 items bought in a week, 11.6 had
  been bought on two days before, the least an item needs to be guessed; no
  rule can catch more than about half.
- **Household and drugstore items are barely caught by any rule**: of 40 in
  the history, 30 were bought once.
