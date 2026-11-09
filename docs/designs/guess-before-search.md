# The guess before the search

Agreed with the owner on 2026-11-08, as a test on the live app. Words as in
`docs/glossary.md`. Examples are made up.

## The idea

Tills shorten names in too many ways to write a rule for each. A model is good
at reading them, and code is good at finding words among 65,000 products. So
before 3a, one model call per receipt writes out each unknown line's full name
(`Pud. V.` → `Vanille Pudding`, without sizes): up to 3 guesses per line, each
for the whole line, the later ones only when really different (`Karotten`,
`Möhren`). 3a then searches by the printed text and by each guess, with the
same loose letter matching. 3b picks
from everything found, as before.

## Why a wrong guess does little harm

- A guess is only searched with. It is never saved as an answer.
- Everything the printed text finds stays on the list, in front, so nothing
  can drop off because of a guess.
- The list still holds only real products, and 3b cannot invent one.

## How we tell if it helps

On the same line, not before against after: before and after differ in which
method ran, and later lines are harder because known lines never reach 3a.
Each candidate records which search found it, and each saved line says so in
`resolutions.source`:

| `source` | Meaning |
|---|---|
| `matcher v2 g1 guess1`, `guess2`, `guess3` | Only that guess found the answer (for a family, the highest any version needed): the old way would have missed it. |
| `matcher v2 g1 both` | Both the printed text and a guess found it. |
| `matcher v2 g1 printed-only` | Only the printed text found it: no guess would have. This is what says whether the printed-text search is still worth having. |
| `matcher v2 g1 printed` | Saved between 8 and 9 Nov, before the two above: the printed text found it, a guess maybe too. |
| `matcher v2` | No guess was made (switched off, or the call failed). |
| `identify v9 g1` | Had a guess, still went on to the paid search. |

Shares to read: of the lines with a guess, how many were `guess`, and how many
still went to the paid search; and the cost per line.

## What would show it is wrong

Each fires a `GROCERY_TRAP` log line, which emails the owner
(`scripts/setup-alerts.sh`):

- `guess-gave-nothing`: a receipt had unknown lines and the guess call failed
  or named none of them.
- `guess-pick-corrected`: a shopper overruled a product or family only the
  guess found.

A longer list could confuse 3b, so it is capped: the printed text's up to 13
stay, and each guess adds at most its best 4 new products (3 from the chain
products, the rest ours), so a list stops at 25. The number is not measured. Compare the corrections of `guess` and
`printed` lines; many on `guess` lines would show it.

## Limits

- One call per receipt each time it is matched. A receipt matched again (a job
  resumed after a restart, the rereading when it is on) makes another call,
  a fraction of a cent, unless its unknown lines are unchanged and the saved
  answer is reused.

- Different words for one thing: found only if one of the guesses uses the
  chain's word.
- A chain's own initials may be unknown to the model.
- GLOBUS and ALDI SÜD have chain products; at other chains the guess can only
  find our products.
