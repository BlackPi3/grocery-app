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

The paper says more than the name, and the model sees it: what was paid and
the VAT rate (7 % is food, so `TC Pads` at 7 % are not cotton pads), and the
abbreviations this shop's till has printed on lines the shopper already
confirmed (`JT` = Jeden Tag), learned from the memory rather than written into
the prompt.

Or the model says it cannot tell (`DESTAN`, `Diverse Lebensmittel`), and only
then is the shopper asked. Whether its answers can be trusted is measured
before anything is built on them (`evaluate_identify`).

Nothing here writes anything.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from grocery_app import categories
from grocery_app.matcher import Decider
from grocery_app.normalizer import tax_rate

PROMPT_VERSION = "v5"


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

Under the line you may see what was paid and the VAT rate. German VAT is
evidence about what a thing can be, and the answer must fit it:
- 7 %: food, including coffee, tea, milk drinks, sweets and snacks, and food
  served in a café; also flowers and plants, books and newspapers.
- 19 %: every other drink (water, juice, soft drinks, plant drinks, beer,
  wine, coffee drinks served in a café), cosmetics, hygiene, cleaning and
  household goods, and everything else that is not food.
The price must fit too: a price far from what such a product costs means you
have the wrong product. You may also see abbreviations this shop's till has
printed on lines the shopper confirmed, with how many names each comes from.

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


def _letters(text: str) -> str:
    return re.sub(r"\W|_|\d", "", text).casefold()


def _abbreviation(word: str) -> str:
    """A printed word up to its first full stop: `ALN.3-KORN-FLOCKEN` -> `ALN.`."""
    return word[:word.index(".") + 1] if "." in word else word


def _stands_for(short: str, brand: str) -> bool:
    """Whether `short` can abbreviate `brand`: same first letter, its letters in
    order inside the brand's (`JT` in Jeden Tag, `KLC` in K-Classic), and not
    simply the brand or its first word. This is what keeps `Avocados` from
    becoming an abbreviation of GLOBUS because a GLOBUS avocado was confirmed,
    and `Dr.` from meaning Dr. Beckmann on a Dr. Oetker line."""
    s, b = _letters(short), _letters(brand)
    first_word = _letters(brand.split()[0]) if brand.split() else ""
    if len(s) < 2 or s in (b, first_word) or not b.startswith(s[0]):
        return False
    rest = iter(b)
    return all(letter in rest for letter in s)


def abbreviations(resolution: dict[tuple[str, str], list[str]],
                  products: dict[str, dict[str, Any]]) -> dict[str, dict[str, Counter]]:
    """store -> printed abbreviation -> brand -> how many confirmed names show it.

    Learned from the memory: a name that resolves to exactly one product with
    a brand, whose first printed word can abbreviate that brand."""
    learned: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for (store, raw_name), ids in resolution.items():
        brand = (products.get(ids[0]) or {}).get("brand") if len(ids) == 1 else None
        words = raw_name.split()
        if brand and words and _stands_for(_abbreviation(words[0]), brand):
            learned[store][_abbreviation(words[0])][brand] += 1
    return learned


def line_vat_rates(receipt: dict[str, Any]) -> list[float | None]:
    """The VAT rate of each line, from whatever the receipt prints.

    In order: the store's class table (`normalizer.tax_rate`); a rate printed
    or read in place of the class (`7%`); a receipt with a single VAT bucket;
    a class whose lines add up to exactly one bucket's total. Anything else is
    None, never guessed."""
    lines = receipt.get("lines") or []
    buckets = {float(k.rstrip("%")) / 100: v
               for k, v in (receipt.get("tax_buckets") or {}).items()
               if re.fullmatch(r"\d+(\.\d+)?%", k.strip())}
    by_class: dict[str, float] = defaultdict(float)
    for line in lines:
        by_class[str(line.get("tax_class"))] += line.get("net") or 0.0
    solved = {code: rate for code, total in by_class.items()
              for rate, amount in buckets.items() if abs(total - amount) < 0.015}
    rates: list[float | None] = []
    for line in lines:
        code = line.get("tax_class")
        printed = re.fullmatch(r"(\d+)\s*%", str(code or "").strip())
        rate = tax_rate(receipt.get("store"), code) if code else None
        if rate is None and printed:
            rate = int(printed.group(1)) / 100
        if rate is None and len(buckets) == 1:
            rate = next(iter(buckets))
        if rate is None:
            rate = solved.get(str(code))
        rates.append(rate)
    return rates


def _money(amount: float) -> str:
    return f"{amount:.2f}".replace(".", ",") + " €"


def paid(line: dict[str, Any], vat: float | None) -> str:
    """What the receipt says was paid for this line, in one line of text."""
    net = line.get("net")
    if net is None:
        return ""
    if line.get("sold_by_weight") and line.get("weight_kg"):
        weight = f"{line['weight_kg']:g}".replace(".", ",")
        text = f"Paid: {_money(net)} for {weight} kg"
        if line.get("unit_price"):
            text += f" at {_money(line['unit_price'])}/{line.get('unit_price_basis') or 'kg'}"
    else:
        qty = line.get("qty") or 1
        text = f"Paid: {_money(net)} for {qty:g}" + (
            f" ({_money(net / qty)} each)" if qty > 1 else "")
    return text + (f", VAT {vat * 100:g} %" if vat is not None else "")


def known_abbreviations(raw_name: str, learned: dict[str, Counter] | None) -> list[str]:
    """The learned abbreviations that appear in this printed name."""
    out = []
    for word in dict.fromkeys(_abbreviation(w) for w in raw_name.split()):
        for brand, n in (learned or {}).get(word, Counter()).most_common(1):
            out.append(f"`{word}` = {brand} ({n} confirmed name{'s' if n > 1 else ''})")
    return out


def build_prompt(raw_name: str, store: str | None,
                 shop_products: list[dict[str, Any]] | None = None,
                 receipt_lines: list[str] | None = None, paid_text: str = "",
                 abbreviations_seen: list[str] | None = None) -> str:
    prompt = f"Shop: {store or 'unknown'}\nReceipt line: `{raw_name}`"
    if paid_text:
        prompt += f"\n{paid_text}"
    if abbreviations_seen:
        prompt += ("\n\nAbbreviations this shop's till printed on lines the shopper "
                   "confirmed:\n" + "\n".join(f"- {a}" for a in abbreviations_seen))
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
             receipt_lines: list[str] | None = None, paid_text: str = "",
             learned: dict[str, Counter] | None = None) -> Identity:
    """Read one printed name, as a person would, with its context.

    `shop_products` are candidates the matcher gathered (`matcher.gather`):
    names, brands and pack sizes, never prices. They help read a cut word or a
    shop abbreviation; they are not a list to choose from. `receipt_lines` are
    the other printed names on the same receipt: they say what kind of visit
    it was (`CAFE CREME`, `CAPPUCCINO` next to `FRUEHSTUECKKOMP` is a café
    breakfast, not a jar of compote). A category outside the vocabulary is
    none, never kept. An answer that leaves a printed word out of its `parts`
    cannot tell, and says which word. `paid_text` is `paid(...)` for this
    line; `learned` is this store's part of `abbreviations(...)`.
    """
    answer = decider(SYSTEM_PROMPT,
                     build_prompt(raw_name, store, shop_products, receipt_lines, paid_text,
                                  known_abbreviations(raw_name, learned)), SCHEMA)
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
