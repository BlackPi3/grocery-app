"""Score `identify` against the shopper's answer sheet, before anything relies on it.

The sheet (`data/receipts/product_truth.json`) says what each line of the 22
fresh receipts was, in the shopper's words: `strawberries 400 g`, `potato salad
with egg, brand unknown`, `Kashk`. Words cannot be compared by string, so a
second model call judges each pair, strictly, and every line it does not call
`right` is listed for a person to read. The judge is a convenience for
sorting, not the authority: the listed lines are.

Every line gets one outcome:

- `right`         it said what it is, and that is what the sheet says;
- `missing`       the right thing, with a detail the sheet names left out
                  (the milk's brand, which the till does not print);
- `false_detail`  the right kind of thing, with a detail that is false or a
                  guess (`F.K.` read as Frühkartoffeln: it is festkochend);
- `wrong`         it said what it is, and it is something else;
- `asked`         it said it cannot tell, so the shopper would be asked.

`missing` is no mistake: saying less than the sheet is what a line that prints
less allows. `false_detail` and `wrong` are mistakes: both write something
untrue into the history without asking, and together they are the number that
must stay at zero. They were one outcome, `close`, with the missing details,
until 2026-09-29, when a score of 0 wrong turned out to hide four false
details. `asked` is the number to keep small.

When the reader comes with a searcher, every line that is groceries must
have been searched before its outcome means anything; the report lists those
that were not first (`search`), because the v6 comparison read numbers from a
run in which the search it was testing had barely happened.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

from grocery_app.categories import is_grocery
from grocery_app.identify import Identity, line_vat_rates, paid, read_line
from grocery_app.matcher import Decider
from grocery_app.resolver import store_key

OUTCOMES = ("right", "missing", "false_detail", "wrong", "asked")
MISTAKES = ("false_detail", "wrong")

JUDGE_PROMPT = """\
You check one answer against the shopper's own description of what they bought.
The shopper is always right. Compare only what the product is: its kind, and
its brand, variant and other details. Ignore language (English or German),
word order, pack sizes and quantities. A detail printed on the receipt line
is supported even when the shopper does not mention it.

- right: the same product, and every detail the answer states is true.
- missing: the same kind of product, and nothing the answer states is false,
  but it leaves out a brand or variant the shopper names.
- false_detail: the same kind of product, but the answer states a brand,
  variant or other detail that the description contradicts, or that neither
  the description nor the receipt line supports (a guess).
- wrong: a different product.
Check every detail in the answer. A true kind with one false detail is
false_detail, not missing.
reason: one short sentence."""

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"verdict": {"type": "string",
                               "enum": ["right", "missing", "false_detail", "wrong"]},
                   "reason": {"type": "string"}},
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}

# (printed name, store, the other printed names on the receipt, what the
# receipt says was paid for the line, the shop's printed address) -> what it is
Identifier = Callable[[str, str | None, list[str], str, str | None], Identity]


def judge(identity: Identity, sheet: dict[str, Any], decider: Decider) -> dict[str, str]:
    said = ", ".join(f"{k}: {v}" for k, v in (("name", identity.name),
                                               ("brand", identity.brand),
                                               ("details", ", ".join(identity.details)))
                     if v)
    words = sheet["product"] + (f" (note: {sheet['note']})" if sheet.get("note") else "")
    return decider(JUDGE_PROMPT, f"Receipt line: `{sheet['raw_name']}`\n"
                                 f"Answer: {said}\nShopper's description: {words}", JUDGE_SCHEMA)


def paid_texts(truth_doc: dict[str, Any],
               readings: dict[str, dict[str, Any]]) -> dict[tuple[str, int], str]:
    """(photo, position) -> what was paid, from the parser's reading of the
    photo, for each sheet line whose position still holds the same name."""
    out = {}
    for sheet in truth_doc["lines"]:
        reading = readings.get(sheet["source_image"])
        lines = (reading or {}).get("lines") or []
        position = sheet["position"]
        if position < len(lines) and lines[position].get("raw_name") == sheet["raw_name"]:
            out[(sheet["source_image"], position)] = paid(
                lines[position], line_vat_rates(reading)[position])
    return out


def evaluate_identify(truth_doc: dict[str, Any], identifier: Identifier,
                      judge_decider: Decider,
                      readings: dict[str, dict[str, Any]] | None = None,
                      searching: bool = False) -> dict[str, Any]:
    paid_for = paid_texts(truth_doc, readings or {})
    receipts: dict[str, list[str]] = {}
    for sheet in sorted(truth_doc["lines"], key=lambda t: t["position"]):
        receipts.setdefault(sheet["source_image"], []).append(sheet["raw_name"])
    lines = []
    only = truth_doc.get("score_only")
    for sheet in truth_doc["lines"]:
        if only and sheet["raw_name"] not in only:
            continue
        identity = identifier(sheet["raw_name"], sheet.get("store"),
                              receipts[sheet["source_image"]],
                              paid_for.get((sheet["source_image"], sheet["position"]), ""),
                              (readings or {}).get(sheet["source_image"], {}).get(
                                  "store_location"))
        verdict = {"verdict": "asked", "reason": identity.reason}
        if identity.can_tell:
            verdict = judge(identity, sheet, judge_decider)
        lines.append({"source_image": sheet["source_image"], "position": sheet["position"],
                      "store": sheet.get("store"), "raw_name": sheet["raw_name"],
                      "sheet": sheet["product"], "identity": identity.as_dict(),
                      "paid": paid_for.get((sheet["source_image"], sheet["position"]), ""),
                      "outcome": verdict["verdict"], "why": verdict.get("reason", "")})
    count = Counter(line["outcome"] for line in lines)
    report = {"totals": {o: count[o] for o in OUTCOMES},
              "mistakes": sum(count[o] for o in MISTAKES), "lines": lines,
              # Lines whose answer lost a part the reader itself had read and
              # placed (`identify.dropped`); counted by code, not by the judge.
              "dropped": [line["raw_name"] for line in lines
                          if line["identity"].get("dropped")]}
    if searching:
        due = [line for line in lines if is_grocery(line["identity"]["category"])]
        report["search"] = {
            "due": len(due), "searched": sum(bool(line["identity"]["searched"]) for line in due),
            "not_searched": [line["raw_name"] for line in due if not line["identity"]["searched"]],
            "not_groceries": len(lines) - len(due)}
    return report


def bound_identifier(decider: Decider,
                     context: Callable[[str, str | None], list[dict[str, Any]]] | None = None,
                     learned: dict[str, dict[str, Counter]] | None = None,
                     searcher: Decider | None = None) -> Identifier:
    """`identify.read_line` bound to a reader, to where the shop's similar
    products come from (`matcher.gather`), to the abbreviations learned from
    the memory (`identify.abbreviations`), and to a searcher, when there are
    such sources."""
    return lambda raw_name, store, receipt_lines, paid_text="", place=None: read_line(
        raw_name, store, decider, searcher, context(raw_name, store) if context else None,
        receipt_lines, paid_text, (learned or {}).get(store_key(store)), place=place)


def format_report(report: dict[str, Any]) -> str:
    totals = report["totals"]
    n = sum(totals.values()) or 1
    out = [f"What a line is: {n} lines of the answer sheet", ""]
    search = report.get("search")
    if search:
        out += [f"Searched: {search['searched']} of the {search['due']} lines due a search "
                f"({search['not_groceries']} lines that are not groceries are not searched)"]
        if search["not_searched"]:
            out += ["  NOT SEARCHED, so the numbers below do not measure search: "
                    + ", ".join(f"`{name}`" for name in search["not_searched"])]
        out += [""]
    out += ["  " + "  ".join(f"{o} {totals[o]} ({100 * totals[o] / n:.0f}%)" for o in OUTCOMES),
            f"  mistakes (false_detail + wrong): {report['mistakes']}",
            f"  read but dropped a part: {len(report['dropped'])}"
            + (": " + ", ".join(f"`{name}`" for name in report["dropped"])
               if report["dropped"] else "")]
    for outcome in ("wrong", "false_detail", "missing", "asked"):
        listed = [line for line in report["lines"] if line["outcome"] == outcome]
        if listed:
            out += ["", f"{outcome.replace('_', ' ').capitalize()}:"]
            for line in listed:
                who = line["identity"]
                said = " | ".join([str(who[k]) for k in ("name", "brand") if who.get(k)]
                                  + ([", ".join(who["details"])] if who.get("details") else []))
                out.append(f"  {line['raw_name']:<28} said: {said:<40} sheet: {line['sheet']}")
                out.append(f"  {'':<28} {line['why']}")
                if who.get("parts"):
                    out.append(f"  {'':<28} parts: " + "; ".join(
                        f"{part['printed']} = {part['means'] or '?'}"
                        + (f" -> {part['into']}" if part.get("into") else "")
                        for part in who["parts"]))
                if who.get("choices"):
                    out.append(f"  {'':<28} choices: " + "; ".join(who["choices"]))
                if who.get("searched"):
                    out.append(f"  {'':<28} searched: " + "; ".join(who["searched"]))
    return "\n".join(out)
