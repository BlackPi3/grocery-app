"""What a receipt line is, in the app's own words (`docs/designs/what-a-line-is.md`).

The matcher can only pick among products that already exist, so a line nobody
has seen before (`Erdbeeren 400g` at a shop whose online range has no fruit)
became a question for the shopper. This step answers the question the
insights actually need, from the printed name alone: what is it?

The answer has one fixed format, level 1 of the design:

- `name`: plain German, what you would write on a shopping list
  (`Erdbeeren`, `Kartoffelsalat mit Ei`). No size, no shop wording.
- `category`: a key from `categories.py`, or none when none fits.
- `brand`, `variant`: only when the line prints them.
- `size`: the pack size when the line prints it. It belongs to the purchase,
  not to the product, so strawberries in 400 g and 500 g packs stay one thing.

Before any of that, the model says what each printed part means (`parts`):
a till prints nothing by accident, so an answer that leaves a part out has
guessed. `TC Pads 36er` read as cotton pads was exactly that: `TC` ignored, the
first similar product taken. A part missing from `parts` makes the line one
the app cannot tell, whatever the model concluded.

Or the model says it cannot tell (`DESTAN`, `Diverse Lebensmittel`), and only
then is the shopper asked. Whether its answers can be trusted is measured
before anything is built on them (`evaluate_identify`).

Nothing here writes anything.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from grocery_app import categories
from grocery_app.matcher import Decider

PROMPT_VERSION = "v4"


def _category_list() -> str:
    return "\n".join(f"{key}: {' > '.join(categories.path(key))}"
                     for key in sorted(categories.CATEGORIES))


SYSTEM_PROMPT = f"""\
You read one line of a German supermarket receipt and say what the product is.

Tills print short, abbreviated, truncated names. Known shop abbreviations: `JT`
is Jeden Tag (a budget brand), `ALN.` is Alnatura, `ff` is funny-frisch, `CF`
is Chipsfrisch, `FS` is Farmer's Snack, `KBio` is Kaufland's organic line. A `?`
stands for an umlaut the printer could not print.

Tills print nothing by accident: every part of the line is there because it
means something, a brand, a kind, a flavour, a size. So first split the line
into its parts and say what each one means:
- parts: every part of the printed line, in order, each with `printed` (the
  characters exactly as on the line) and `means` (what it stands for, and
  whether it is a brand, the kind of product, a variant or a size), or null
  when you cannot say. For `WEIH. H-Milch 3,5% 1l`: `WEIH.` means Weihenstephan
  (brand), `H-Milch` long-life milk (kind), `3,5%` fat content (variant), `1l`
  the size. Leave nothing out.

Then answer from the parts, and only from them. The answer must fit every
part: a brand tells you what the rest of the name can be, so read the rest as
a product that brand makes. If a part you cannot read could change what the
product is, not only who made it, set can_tell to false.

Answer in this format:
- name: what the product is, in plain German, as you would write it on a
  shopping list: `Erdbeeren`, `Kartoffelsalat mit Ei`, `Frischkäse Natur`,
  `Tortilla Wraps`. Never a size, a pack count, a brand or shop wording in the
  name. Bio goes in the name when printed (`Bananen Bio`).
- category: the one key from the list below that fits, or null if none does.
- brand: only when the line prints it or a known abbreviation of it. Never
  guess a brand from what is likely.
- variant: a flavour, colour or kind only when the line prints it
  (`Paprika rot`, `Pesto rot`); otherwise null.
- size: the pack size exactly as printed (`400g`, `1,5l`, `36er`), or null.
- can_tell: false when the printed words do not say what the product is: a
  brand or code alone (`DESTAN`), a name a till prints for anything (`Diverse
  Lebensmittel`), or a word you do not know. Then the other fields are your
  best reading and are not used. A wrong answer costs more than a question.
  A flavour or version the line does not print is NOT a reason: `Salatschale`
  is a Salatschale, `Tortilla Wraps` are Tortilla Wraps, whichever kind.

You also see the other lines of the same receipt. Use them as a person would:
they tell you what kind of shop and visit this was. A receipt of coffees,
breakfast sets and rolls with cold cuts is a café, and its lines are
`cafe-imbiss`, not groceries. Things a supermarket sells that are not
groceries (a birthday card, a lipstick, flowers, a carrier bag) go in the
categories under "Kein Lebensmitteleinkauf".

Tills cut names off. When a word is cut (`Kartoffelr.`, `FRUEHSTUECKKOMP`),
do not guess how it ends: `Kartoffelr.` could be Kartoffelringe or
Kartoffelrösti. Use the shop's products listed with the line, when there are
any: they are what this shop sells under similar names, and one of them may
settle how the word ends, what an abbreviation means (`BERT.` next to
`Bertolli Olivenöl`) or what a brand-like word is (`Tatü` next to natuvell
tissues). They may also all be unrelated. If nothing settles a cut word, set
can_tell to false.
- reason: one short sentence, in English.

Categories:
{_category_list()}"""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"printed": {"type": "string"},
                               "means": {"type": ["string", "null"]}},
                "required": ["printed", "means"],
                "additionalProperties": False,
            },
        },
        "name": {"type": "string"},
        "category": {"type": ["string", "null"]},
        "brand": {"type": ["string", "null"]},
        "variant": {"type": ["string", "null"]},
        "size": {"type": ["string", "null"]},
        "can_tell": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["parts", "name", "category", "brand", "variant", "size", "can_tell", "reason"],
    "additionalProperties": False,
}


@dataclass
class Identity:
    """What a line is, level 1 of the design, or that the app cannot tell."""

    name: str
    category: str | None
    brand: str | None
    variant: str | None
    size: str | None
    can_tell: bool
    reason: str
    parts: list[dict[str, str | None]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def left_out(raw_name: str, parts: list[dict[str, Any]]) -> list[str]:
    """The printed words no part accounts for. Only letters and digits are
    compared, over all parts joined, so a word the model split in two
    (`KÜRBISKERN` + `BRÖT.`) or punctuation it dropped (`Kartoffelr.,Dolphy`)
    still counts; punctuation alone (`/`) is not a word."""
    def bare(text: str) -> str:
        return re.sub(r"\W|_", "", text).casefold()

    accounted = bare("".join(str(part.get("printed") or "") for part in parts))
    return [word for word in raw_name.split() if bare(word) and bare(word) not in accounted]


def build_prompt(raw_name: str, store: str | None,
                 shop_products: list[dict[str, Any]] | None = None,
                 receipt_lines: list[str] | None = None) -> str:
    prompt = f"Shop: {store or 'unknown'}\nReceipt line: `{raw_name}`"
    others = [name for name in receipt_lines or [] if name != raw_name]
    if others:
        prompt += "\n\nOther lines of the same receipt:\n" + "\n".join(
            f"- `{name}`" for name in others)
    if shop_products:
        listed = "\n".join(
            "- " + " | ".join(str(p[k]) for k in ("name", "brand", "pack_size") if p.get(k))
            for p in shop_products)
        prompt += f"\n\nProducts with similar names (context, may be unrelated):\n{listed}"
    return prompt


def identify(raw_name: str, store: str | None, decider: Decider,
             shop_products: list[dict[str, Any]] | None = None,
             receipt_lines: list[str] | None = None) -> Identity:
    """Read one printed name, as a person would, with its context.

    `shop_products` are candidates the matcher gathered (`matcher.gather`):
    names, brands and pack sizes, never prices. They help read a cut word or a
    shop abbreviation; they are not a list to choose from. `receipt_lines` are
    the other printed names on the same receipt: they say what kind of visit
    it was (`CAFE CREME`, `CAPPUCCINO` next to `FRUEHSTUECKKOMP` is a café
    breakfast, not a jar of compote). A category outside the vocabulary is
    none, never kept. An answer that leaves a printed word out of its `parts`
    cannot tell, and says which word.
    """
    answer = decider(SYSTEM_PROMPT,
                     build_prompt(raw_name, store, shop_products, receipt_lines), SCHEMA)
    category = answer.get("category")
    parts = [{"printed": str(p.get("printed") or ""), "means": p.get("means") or None}
             for p in answer.get("parts") or []]
    missing = left_out(raw_name, parts)
    reason = answer.get("reason") or ""
    if missing:
        reason = f"left out {', '.join(f'`{w}`' for w in missing)}: {reason}"
    return Identity(
        name=(answer.get("name") or "").strip(),
        category=category if category in categories.CATEGORIES else None,
        brand=answer.get("brand") or None,
        variant=answer.get("variant") or None,
        size=answer.get("size") or None,
        can_tell=(bool(answer.get("can_tell")) and bool((answer.get("name") or "").strip())
                  and not missing),
        reason=reason,
        parts=parts,
    )
