# Glossary

The words the owner and the assistant use to talk about the app. They stay
close to the code's names, and the code is not renamed to match them. Use these
words in messages and docs; a word not here is explained when it is used.
Examples are made up (the repo is public).

## Where things are sold

| Word | Meaning | In the code today |
|---|---|---|
| **Chain** | The brand, e.g. GLOBUS. | `store` |
| **Branch** | One real place of a chain: chain + street + postcode, e.g. GLOBUS, Musterstraße 1, 12345 Musterstadt. | `store_location`, as printed, in several spellings |

Avoid "shop" and "store" alone: they hide whether the chain or the branch is meant.

## What the till does

| Word | Meaning | In the code today |
|---|---|---|
| **Line** | One printed row of a receipt. | `receipt_lines` |
| **Printed text** | The words a line prints, e.g. `WALNUSSKERNE`. Retail calls it the Bontext. | `raw_name` |
| **Till function** | The real rule by which a branch's till turns a product into printed text. Unknown to us: we only see its output on receipts, and try to work it out. | none |
| **Resolutions** | What we have worked out of the till function so far, stored backwards: printed text → product. One entry is a resolution. Should be held per branch. Not "memory". | `resolutions`, keyed by chain + text, no branch yet |

Do not assume two branches of a chain share a till function. That is to be
measured.

## What we know about products

| Word | Meaning | In the code today |
|---|---|---|
| **Product** | One real thing that is sold. | a `products` row |
| **Family** | Versions of one product that a line cannot tell apart, e.g. flavours. | `family`, `product_ids` |
| **Our products** | Every product the app has identified from receipt lines, all chains, shared by all users. | `products` |
| **Chain products** | What one chain sells, as its website showed on the day we downloaded it (GLOBUS and ALDI SÜD so far): "the GLOBUS products". Never complete; prices are as of that day. | JSON files today, `crawl.json` |
| **Website** | The chain's live site. Not what section 3 searches. | |

## The steps

Drawn in `docs/flows.md`.

| Word | Meaning |
|---|---|
| **Section 1** | Read the photo into lines. |
| **Section 2** | Look the printed text up in the resolutions. |
| **Section 3** | Match the line ourselves, against data we hold. |
| **Guess** | The model's reading of a line's full name, one call per receipt. Only searched with, never saved as an answer. |
| **3a** | Gather candidates from the chain products and our products, by the printed text and by the guess. Code only. |
| **Candidates** | The short list 3a hands to 3b. |
| **3b** | The model picks one candidate, or none. Never sees prices. |
| **3c** | Code accepts the pick, or not. |
| **Section 4** | Identify the line with a paid web search. |

## Testing

| Word | Meaning |
|---|---|
| **Answer key** | For each test line, the right product. Say where it came from: a shopper's answer is proof; a pick made by the step under test is not. |
| **Real data** | Receipts the live server processed; not eval sets or laptop runs. |
