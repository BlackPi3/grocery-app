"""What a receipt line is, in the app's own words (`docs/designs/what-a-line-is.md`).

The matcher can only pick among products that already exist, so a line nobody
has seen before (`Erdbeeren 400g` at a shop whose online range has no fruit)
became a question for the shopper. This step answers the question the
insights actually need, from the printed name alone: what is it?

The answer has one fixed format, level 1 of the design:

- `name`: plain German, what you would write on a shopping list
  (`Erdbeeren`, `Kartoffelsalat mit Ei`). No size, no shop wording.
- `category`: a key from `categories.py`, or none when none fits.
- `brand`, `details`: only when the line prints them. `details` is a list of
  anything else the pack says, any number: a range, a strength, a flavour.
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

# v6 (2026-09-29): every example in the prompt is made up. Until v5 several came
# from the 135 lines it is scored on (a café breakfast, `Kartoffelr.`, `Tatü`,
# `BERT.`), and the shop abbreviations were a hand-written list from the same
# receipts; both flatter the score and teach nothing that carries to another
# shopper's receipt. Abbreviations are learned from the memory instead
# (`abbreviations`). A change to this prompt must be general: evidence a person
# would use, tools, knowing when to ask, or learning from confirmations; never
# a rule for one line.
# v7 (2026-10-02): search is a step the code runs, not something the reader may
# choose (`read_line`): in the v6 comparison Gemini searched 2 lines in 154 and
# both models read `Ult.` and `SCHOKO` wrongly without checking. The reader now
# sees what the search found, and a line it still cannot tell comes with the
# choices the search left (`choices`), so a question is never a bare name.
# v8 (2026-10-08): nothing read is dropped. In real use the reader explained
# every printed part and then left some out of the product, because the format
# had nowhere for them: a cigarette line lost its product line, a supplement
# line its strength and its range. Each part now says
# which field it goes into (`into`), there was a `product_line` field, and the
# code lists any part whose field came back empty (`dropped`). Scored against
# v7: the first draft cut a printed word in two to fill a variant (a greeting
# card line), so a part is now a whole printed word.
# v9 (2026-10-09): the range and the variant are one list, `details` (Parham:
# fixed slots are a presumption; which slot a word belongs in was a guess the
# reader made differently each time, and each guess could make a duplicate).
PROMPT_VERSION = "v9"
# s2 (2026-10-02): the searcher is told where the shop is and searches there
# (Parham: "at least search in that country").
SEARCH_VERSION = "s2"
# Every receipt so far is German; the address printed on it says where.
SHOP_COUNTRY = "Germany"
# A line that is not groceries (café, flowers, a carrier bag, a photo print:
# `categories.is_grocery`) does not concern the insights: once a line reads as
# one, it is neither searched nor asked about (Parham, 2026-10-02: "you should
# know it isn't groceries. not just for cafe").


# The answer's fields a printed part can go into (`into`), name first.
FIELDS = ("name", "brand", "details", "size")


def _category_list() -> str:
    return "\n".join(f"{key}: {' > '.join(categories.path(key))}"
                     for key in sorted(categories.CATEGORIES))


SYSTEM_PROMPT = f"""\
You read one line of a German supermarket receipt and say what the product is.

Tills print short, abbreviated, truncated names. A `?` stands for an umlaut
the printer could not print.

Tills print nothing by accident: every part of the line is there because it
means something, a brand, a kind, a flavour, a size. So first split the line
into its parts and say what each one means:
- parts: every part of the printed line, in order, each with `printed` (the
  characters exactly as on the line), `means` (what it stands for), or null
  when you cannot say, and `into`: the field of your answer it goes into,
  `name`, `brand`, `details` or `size`, or `none` for shop wording and codes
  that say nothing about the product. For `MUSTR. Kids Zahnp. Erdb. 50ml`:
  `MUSTR.` Mustermann (brand), `Kids` the brand's range for children
  (details), `Zahnp.` toothpaste (name), `Erdb.` strawberry (details), `50ml`
  (size). Leave nothing out. A part is a
  whole printed word or abbreviation: never cut a word into pieces to fill a
  field (`Gemüsebrühe` is one part, the name).

Then answer from the parts, and only from them. Nothing you read is dropped:
every part goes into the field its `into` names, and that field shows it.
The answer must fit every part: a brand tells you what the rest of the name
can be, so read the rest as a product that brand makes. If a part you cannot
read could change what the product is, not only who made it, set can_tell to
false.

Answer in this format:
- name: what the product is, in plain German, as you would write it on a
  shopping list: `Himbeeren`, `Nudelsalat mit Ei`, `Schmand`, `Fladenbrot`.
  Never a size, a pack count, a brand or shop wording in the name. Bio goes in
  the name when printed (`Bananen Bio`).
- category: the one key from the list below that fits, or null if none does.
- brand: only when the line prints it or a known abbreviation of it. Never
  guess a brand from what is likely.
- details: everything else the line prints about the product, one entry per
  thing, as the brand would write it: a range (`Kids`, `Pro`), a flavour or
  colour (`rot`, `mittelscharf`), a strength (`500 mg`). As many as the line
  prints, in printed order; empty when it prints none.
- size: the pack size exactly as printed (`125g`, `0,75l`, `6er`), or null.
- can_tell: false when the printed words do not say what the product is: a
  brand or code alone (`MUSTRA`), a name a till prints for anything
  (`Sonstiges 7%`, `Warengruppe 12`), or a word you do not know. Then the other
  fields are your best reading and are not used. A wrong answer costs more
  than a question. A flavour or version the line does not print is NOT a
  reason: `Blattsalat Mix` is a Blattsalat Mix, `Brezeln` are Brezeln,
  whichever kind.

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
they tell you what kind of shop and visit this was. A receipt of drinks and
dishes served to eat on the spot is a café or snack bar, and its lines are
`cafe-imbiss`, not groceries. Things a supermarket sells that are not
groceries (stationery, cosmetics, flowers, a carrier bag) go in the
categories under "Kein Lebensmitteleinkauf".

Tills cut names off. When a word is cut (`Gemüsebr.`), do not guess how it
ends: `Gemüsebr.` could be Gemüsebrühe or Gemüsebratlinge. Use the shop's
products listed with the line, when there are any: they are what this shop
sells under similar names, and one of them may settle how a word ends, what
an abbreviation means or what a brand-like word is. They may also all be
unrelated. If nothing settles a cut word, set can_tell to false.

You may also see what a web search for the whole printed line found: the
titles of the pages it returned, exactly as they came back, and the products
those pages show. It is evidence like the rest, and often the best there is
for a cut word or a brand-like word. Trust what the pages print over what you
expect a word to mean: a page naming a product that fits every printed part,
the price and the VAT rate settles what the line is. If the results do not
settle it, set can_tell to false.
- choices: when can_tell is false, what the line can still be, best first,
  narrowed by everything above (the search, the price, the VAT rate), each a
  product in a few words; empty when can_tell is true or nothing narrows it.
- reason: one short sentence, in English.

Categories:
{_category_list()}"""

SEARCH_SYSTEM = """\
You look up one printed line of a German supermarket receipt on the web, for
someone who will then decide what the product is.

Search first for exactly the query you are given: the whole printed line and
the shop's name, as a person would type it into Google. Then search once or
twice more for what those results show, to check it.

You are told where the shop is. Search as a shopper there would: in that
country's language and on that country's sites. When results come from
another country, search again with the country or the town in the query.

Report what the pages say, not what you expect: write product names as the
pages write them. A word cut off on the receipt is completed only by what a
page shows. Do not decide which product it is.
- products: the products the line could be, at most five, best first, each
  with `product` (as a page names it), `brand`, `size` and `price` when a page
  shows them, and `seen_at` (the site).
- note: one short sentence, in English, on how well the results fit the line."""

SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "products": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"product": {"type": "string"},
                               "brand": {"type": ["string", "null"]},
                               "size": {"type": ["string", "null"]},
                               "price": {"type": ["string", "null"]},
                               "seen_at": {"type": ["string", "null"]}},
                "required": ["product", "brand", "size", "price", "seen_at"],
                "additionalProperties": False,
            },
        },
        "note": {"type": "string"},
    },
    "required": ["products", "note"],
    "additionalProperties": False,
}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"printed": {"type": "string"},
                               "means": {"type": ["string", "null"]},
                               "into": {"type": "string", "enum": [*FIELDS, "none"]}},
                "required": ["printed", "means", "into"],
                "additionalProperties": False,
            },
        },
        "name": {"type": "string"},
        "category": {"type": ["string", "null"]},
        "brand": {"type": ["string", "null"]},
        "details": {"type": "array", "items": {"type": "string"}},
        "size": {"type": ["string", "null"]},
        "can_tell": {"type": "boolean"},
        "choices": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["parts", "name", "category", "brand", "details", "size", "can_tell",
                 "choices", "reason"],
    "additionalProperties": False,
}


@dataclass
class Identity:
    """What a line is, level 1 of the design, or that the app cannot tell."""

    name: str
    category: str | None
    brand: str | None
    # Everything else the line prints about the product, any number. Given as
    # one text or None, it is made a list.
    details: list[str] | str | None
    size: str | None
    can_tell: bool
    reason: str
    parts: list[dict[str, str | None]] = field(default_factory=list)
    # What the line can still be when the app cannot tell, from the search.
    choices: list[str] = field(default_factory=list)
    # What was searched before this answer; empty when nothing was.
    searched: list[str] = field(default_factory=list)
    # The line was due a search and the searcher did not search, even when
    # told twice: it is neither saved nor asked about, and is read again later.
    unsearched: bool = False
    # Printed parts the reader put into a field that came back empty
    # (`dropped`): read, then left out of the product.
    dropped: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.details, list):
            self.details = [self.details] if self.details else []
        self.details = [d.strip() for d in self.details if d and d.strip()]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Findings:
    """What a web search for the whole printed line found (`search_line`)."""

    queries: list[str]
    titles: list[str]
    products: list[dict[str, Any]]
    note: str = ""

    def as_text(self) -> str:
        out = ["What a web search for the whole printed line found.",
               "Searched for: " + "; ".join(f"`{q}`" for q in self.queries)]
        if self.titles:
            out += ["Titles of the pages returned, exactly as they came back:"]
            out += [f"- {title}" for title in self.titles[:MAX_TITLES]]
        if self.products:
            out += ["Products those pages show:"]
            out += ["- " + " | ".join(str(p[k]) for k in ("product", "brand", "size", "price",
                                                           "seen_at") if p.get(k))
                    for p in self.products]
        if self.note:
            out.append(f"Searcher's note: {self.note}")
        return "\n".join(out)


MAX_TITLES = 15


def dropped(answer: dict[str, Any]) -> list[str]:
    """The printed parts the reader said go into a field that it left empty.

    A part it read and placed, then lost: `Vit400` into the details, with no
    details in the answer. The name is not checked: it is never empty on an
    answer that is used, and it is plain German, not the printed words.
    """
    return [str(part.get("printed") or "") for part in answer.get("parts") or []
            if part.get("into") in FIELDS[1:] and not _filled(answer.get(part["into"]))]


def _filled(value: Any) -> bool:
    if isinstance(value, list):
        return any(str(v).strip() for v in value)
    return bool((value or "").strip())


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
                 abbreviations_seen: list[str] | None = None,
                 description: str | None = None, findings: Findings | None = None) -> str:
    prompt = f"Shop: {store or 'unknown'}\nReceipt line: `{raw_name}`"
    if description:
        # In the line's prompt, not the system prompt: the scored prompt and
        # its cached answers stay what they were.
        prompt += (f"\n\nThe shopper who bought it says what it is, in their own words:\n"
                   f"<<{description}>>\nThey are right about what it is: take the kind, brand "
                   f"and details from their words, read together with the printed line. Never "
                   f"contradict them. Your job is only the format above, in German.")
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
    if findings and findings.queries:
        prompt += "\n\n" + findings.as_text()
    return prompt


def identify(raw_name: str, store: str | None, decider: Decider,
             shop_products: list[dict[str, Any]] | None = None,
             receipt_lines: list[str] | None = None, paid_text: str = "",
             learned: dict[str, Counter] | None = None,
             description: str | None = None, findings: Findings | None = None) -> Identity:
    """Read one printed name, as a person would, with its context.

    `shop_products` are candidates the matcher gathered (`matcher.gather`):
    names, brands and pack sizes, never prices. They help read a cut word or a
    shop abbreviation; they are not a list to choose from. `receipt_lines` are
    the other printed names on the same receipt: they say what kind of visit
    it was (`CAFE CREME`, `CAPPUCCINO` next to `FRUEHSTUECKKOMP` is a café
    breakfast, not a jar of compote). A category outside the vocabulary is
    none, never kept. An answer that leaves a printed word out of its `parts`
    cannot tell, and says which word. `paid_text` is `paid(...)` for this
    line; `learned` is this store's part of `abbreviations(...)`. `description`
    is the shopper's own words for what the line was: the meaning is theirs,
    the format is ours (Parham, 2026-10-01). `findings` is what a search for
    the whole line found (`search_line`); `read_line` decides when to search.
    """
    answer = decider(SYSTEM_PROMPT,
                     build_prompt(raw_name, store, shop_products, receipt_lines, paid_text,
                                  known_abbreviations(raw_name, learned), description,
                                  findings), SCHEMA)
    category = answer.get("category")
    parts = [{"printed": str(p.get("printed") or ""), "means": p.get("means") or None,
              "into": p.get("into")} for p in answer.get("parts") or []]
    missing = left_out(raw_name, parts)
    lost = dropped(answer)
    reason = answer.get("reason") or ""
    if missing:
        reason = f"left out {', '.join(f'`{w}`' for w in missing)}: {reason}"
    if lost:
        reason = f"read but dropped {', '.join(f'`{w}`' for w in lost)}: {reason}"
    can_tell = (bool(answer.get("can_tell")) and bool((answer.get("name") or "").strip())
                and not missing)
    return Identity(
        name=(answer.get("name") or "").strip(),
        category=category if category in categories.CATEGORIES else None,
        brand=answer.get("brand") or None,
        details=[str(d) for d in answer.get("details") or []],
        size=answer.get("size") or None,
        can_tell=can_tell,
        reason=reason,
        parts=parts,
        choices=[] if can_tell else [str(c) for c in answer.get("choices") or [] if c],
        searched=list(findings.queries) if findings else [],
        dropped=lost,
    )


def search_line(raw_name: str, store: str | None, searcher: Decider,
                paid_text: str = "", place: str | None = None) -> Findings:
    """Search the web for the whole printed line, as a person would type it.

    The query is built here, from the whole line and the shop's name: a part
    alone (`TC`) finds nothing (Parham, 2026-09-29). The searcher must search;
    one that answers without searching is told once more, and if it still
    has not, the findings say so (no queries) rather than pass off what the
    model already believed as something it found. What was searched is read
    from the searcher (`last_search`), not from its own account. `place` is
    the shop's address as the receipt prints it; the country is added.
    """
    from grocery_app.matcher import DeciderError

    query = " ".join(part for part in (raw_name, store) if part)
    where = ", ".join(part for part in (place, SHOP_COUNTRY) if part)
    prompt = (f"Query to search first: {query}\nThe shop is at: {where}"
              + (f"\n{paid_text}" if paid_text else ""))
    try:
        answer = searcher(SEARCH_SYSTEM, prompt, SEARCH_SCHEMA)
        searched = searcher.last_search  # type: ignore[attr-defined]
        if not searched.queries:
            answer = searcher(SEARCH_SYSTEM, prompt + "\n\nYou have not searched yet. Search "
                              "before you answer.", SEARCH_SCHEMA)
            searched = searcher.last_search  # type: ignore[attr-defined]
    except DeciderError:
        # A failed or refused search (no key, the search budget spent) is no
        # search: the line waits rather than being read unchecked.
        return Findings([], [], [], "")
    if not searched.queries:
        return Findings([], [], [], "")
    return Findings(list(searched.queries), list(searched.titles),
                    [p for p in answer.get("products") or [] if isinstance(p, dict)],
                    answer.get("note") or "")


def read_line(raw_name: str, store: str | None, reader: Decider,
              searcher: Decider | None = None,
              shop_products: list[dict[str, Any]] | None = None,
              receipt_lines: list[str] | None = None, paid_text: str = "",
              learned: dict[str, Counter] | None = None,
              description: str | None = None, place: str | None = None) -> Identity:
    """What a line is, with search as a step rather than the reader's choice.

    The line is read once as it is. A line that is not groceries stops there,
    told or not exactly what it is: it is neither searched nor asked about.
    Every other line is searched (`search_line`) and read again with what the
    search found, however sure the first reading was: in the v6 comparison the
    wrong answers were the confident ones (`Ult.` read as Ultra, a muesli read
    as chocolate). A line whose searcher would not search is `unsearched`: an
    answer nobody checked is not saved, and nothing is asked before a search.
    A shopper's own description needs no search. Without a searcher this is
    `identify`.
    """
    def read(findings: Findings | None = None) -> Identity:
        return identify(raw_name, store, reader, shop_products, receipt_lines, paid_text,
                        learned, description, findings)

    first = read()
    if searcher is None or description:
        return first
    if first.category and not categories.is_grocery(first.category):
        first.can_tell = bool(first.name)
        first.choices = []
        first.reason = f"not groceries, so the exact item does not matter: {first.reason}"
        return first
    findings = search_line(raw_name, store, searcher, paid_text, place)
    if not findings.queries:
        first.can_tell, first.choices, first.unsearched = False, [], True
        first.reason = f"not searched, so not read: {first.reason}"
        return first
    return read(findings)
