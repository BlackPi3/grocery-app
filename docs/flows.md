# Flows

The drawing board: how the app works, drawn as boxes, so the owner and the
assistant can come back to a flow and talk about it. Each box says who does
the step:

- **CODE**: our own code. It does exactly what it says, every time.
- **GEMINI**: one call to the model. Code decides what it is shown and the
  form of its answer, and checks the answer after; the model decides the rest.
- **GEMINI + GOOGLE**: one call to the model with Google search switched on.
  The model also decides what to search and how often, and we never see the
  pages it read.

A PR that changes a step drawn here redraws it in the same PR. A new flow
worth talking about gets its own section. Examples are made up (the repo is
public).

## Contents

1. [A line the app has not seen before](#1-a-line-the-app-has-not-seen-before)

## 1. A line the app has not seen before

From an uploaded photo to a saved product or a question to the shopper, as
the live server does it (its three model settings are all `gemini`). Drawn
2026-10-28. The example is a made-up line, `Pud. V. / Wolkenz.`, where the
shop sells five flavours of one pudding at the same price.

```
 PHOTO
   │
   ▼
┌─────────────────────────────────────┐
│ 1  READ THE PHOTO            GEMINI │  1 call per receipt
│    photo → shop, date, lines, €     │  answer must fit our JSON form
└──────────────────┬──────────────────┘
                   ▼   then, for each line:
┌─────────────────────────────────────┐
│ 2  MEMORY                      CODE │  printed this before at this shop?
└───────┬─────────────────────┬───────┘
     yes│                   no│
        ▼                     ▼
      done    ┌─────────────────────────────────────┐
              │ 3a GATHER CANDIDATES           CODE │  shop's product list + our catalog,
              │    → the 5 flavours                 │  letter by letter
              ├─────────────────────────────────────┤
              │ 3b PICK ONE                  GEMINI │  numbered list: it can't invent;
              │                                     │  never sees prices
              ├─────────────────────────────────────┤
              │ 3c ACCEPT?                     CODE │  price singles it out + "sure"
              └───────┬─────────────────────┬───────┘
                   yes│                   no│  (all 5 cost the same)
                      ▼                     ▼
               save to memory ┌─────────────────────────────────────┐
                              │ 4a FIRST READ                GEMINI │  line + candidates + rest of
                              │    → its own guess                  │  receipt → a guess
                              ├─────────────────────────────────────┤
                              │    groceries?                  CODE │  no → stop here, no search
                              ├─────────────────────────────────────┤
                              │ 4b SEARCH           GEMINI + GOOGLE │  gets ONLY line, shop, price
                              │    Gemini picks the queries         │  ~10 searches = 84% of cost
                              │    and how many                     │
                              ├─────────────────────────────────────┤
                              │ 4c SECOND READ               GEMINI │  line + candidates + what
                              │                                     │  the search found → answer
                              └───────┬─────────────────────┬───────┘
                              can tell│           can't tell│
                                      ▼                     ▼
                              save (CODE)        question to shopper (CODE)
```

Where each step lives:

| Step | Code |
|---|---|
| 1 | `extract.py` |
| 2 | `normalizer.py`, `memory.py` |
| 3a–3c | `matcher.py`: `gather`, `propose` |
| 4a–4c | `identify.py`: `read_line` (4a and 4c are `identify`, 4b is `search_line`) |
| saving, questions | `api/matching.py` |

What the drawing shows (2026-10-27/28, the line search investigation in
`docs/status.md`):

- Step 4b is blind. It is given neither 4a's guess nor 3a's candidates, so it
  searches from scratch for what the app already had.
- Step 4b is the one step where the model has a free hand, and where 84% of a
  line's cost goes.
