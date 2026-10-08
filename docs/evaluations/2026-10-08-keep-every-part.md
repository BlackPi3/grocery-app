# Keep every printed part: identify v8 against v7

2026-10-08 · No receipt text in this document: the repo is public.

## Why

In real use two spot checks showed products that were right but incomplete.
The reader had explained every printed part of the line (a product range, a
strength) and then left some of them out of the product, because its answer
format had no field for a range and nothing asked it to keep what it read.

## What changed (identify v8)

- Every part the reader explains now says which field it goes into (`into`:
  name, brand, product line, variant, size, or none for shop wording).
- The answer has a `product_line` field; a strength is a variant.
- The code lists any part whose field came back empty (`dropped`), and the
  evaluation counts those lines. Counted by code, not by the judge.
- A part is a whole printed word: the first draft cut a greeting-card word in
  two to fill a variant, a false detail. Fixed before the numbers below.

## Results

The 13 printed names of the answer sheet that v7 was last scored on (23
lines, since some names recur), Gemini reading and searching, judge-v2;
every changed verdict read by hand.

| prompt | right | missing | false detail | wrong | asked | read but dropped |
|---|---|---|---|---|---|---|
| v7 | 8 | 10 | 0 | 0 | 5 | not measured |
| v8, first draft | 6 | 11 | 2 | 0 | 4 | 0 |
| v8 | 8 | 10 | 0 | 0 | 5 | 0 |
| v9 (2026-10-09, one list of details) | 7 | 10 | 2 | 0 | 4 | 0 |

- **On the answer sheet v8 is no better and no worse than v7.** Its lines
  print few ranges or strengths, so the case v8 fixes barely occurs there.
  The "missing" lines are details the shopper knows and the till does not
  print (a milk's brand, the wraps' kind); no prompt can read those.
- **On the two real lines that showed the fault,** v8 keeps the range and the
  strength the receipt prints, with nothing dropped. They are not on the
  answer sheet, so this is two lines, not a score.

## Not measured

How often the fault happens. The answer sheet would need lines that print a
range or a strength; the live spot checks will show it on new receipts.

## v9: one list of details (2026-10-09)

Parham's call: the range and the variant became one list of `details`, any
length (migration 0011), because which of two slots a word belonged in was a
guess the reader made differently on each run. Same 23 lines, same judge.

- **Grocery lines: the same answers as v7 and v8.** One line moved from asked
  to answered (a greeting card, read as such).
- **The judge's two false details, read by hand:** one is a judge error (its
  own reason says "missing, not false" for the greeting card); the other is
  a household line whose last printed letter the reader took for the box
  shape the search found. Plausible, not confirmed; the shopper would know.
  Neither line is groceries.
- **The two real lines** that started this come out complete, every printed
  part kept, nothing dropped.
