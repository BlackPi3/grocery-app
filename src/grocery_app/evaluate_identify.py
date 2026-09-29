"""Score `identify` against the shopper's answer sheet, before anything relies on it.

The sheet (`data/receipts/product_truth.json`) says what each line of the 22
fresh receipts was, in the shopper's words: `strawberries 400 g`, `potato salad
with egg, brand unknown`, `Kashk`. Words cannot be compared by string, so a
second model call judges each pair, strictly, and every line it does not call
`right` is listed for a person to read. The judge is a convenience for
sorting, not the authority: the listed lines are.

Every line gets one outcome:

- `right`   it said what it is, and that is what the sheet says;
- `close`   the right thing with a detail wrong or missing (a brand it should
            have read, a variant it dropped);
- `wrong`   it said what it is, and it is something else;
- `asked`   it said it cannot tell, so the shopper would be asked.

`wrong` is the number that must stay at zero: it is a product put on a line
without asking. `asked` is the number to keep small.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

from grocery_app.identify import Identity, identify, line_vat_rates, paid
from grocery_app.matcher import Decider
from grocery_app.resolver import store_key

OUTCOMES = ("right", "close", "wrong", "asked")

JUDGE_PROMPT = """\
You check one answer against the shopper's own description of what they bought.
The shopper is always right. Compare only what the product is: its kind, and
its brand and variant when the shopper names them. Ignore language (English or
German), word order, pack sizes and quantities.

- right: the answer is the same product as the description.
- close: the same kind of product, but a brand or variant the shopper names is
  missing or different in the answer.
- wrong: a different product.
reason: one short sentence."""

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["right", "close", "wrong"]},
                   "reason": {"type": "string"}},
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}

# (printed name, store, the other printed names on the receipt, what the
# receipt says was paid for the line) -> what it is
Identifier = Callable[[str, str | None, list[str], str], Identity]


def judge(identity: Identity, sheet: dict[str, Any], decider: Decider) -> dict[str, str]:
    said = ", ".join(f"{k}: {v}" for k, v in (("name", identity.name),
                                               ("brand", identity.brand),
                                               ("variant", identity.variant)) if v)
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
                      readings: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    paid_for = paid_texts(truth_doc, readings or {})
    receipts: dict[str, list[str]] = {}
    for sheet in sorted(truth_doc["lines"], key=lambda t: t["position"]):
        receipts.setdefault(sheet["source_image"], []).append(sheet["raw_name"])
    lines = []
    for sheet in truth_doc["lines"]:
        identity = identifier(sheet["raw_name"], sheet.get("store"),
                              receipts[sheet["source_image"]],
                              paid_for.get((sheet["source_image"], sheet["position"]), ""))
        verdict = {"verdict": "asked", "reason": identity.reason}
        if identity.can_tell:
            verdict = judge(identity, sheet, judge_decider)
        lines.append({"source_image": sheet["source_image"], "position": sheet["position"],
                      "store": sheet.get("store"), "raw_name": sheet["raw_name"],
                      "sheet": sheet["product"], "identity": identity.as_dict(),
                      "paid": paid_for.get((sheet["source_image"], sheet["position"]), ""),
                      "outcome": verdict["verdict"], "why": verdict.get("reason", "")})
    count = Counter(line["outcome"] for line in lines)
    return {"totals": {o: count[o] for o in OUTCOMES}, "lines": lines}


def bound_identifier(decider: Decider,
                     context: Callable[[str, str | None], list[dict[str, Any]]] | None = None,
                     learned: dict[str, dict[str, Counter]] | None = None) -> Identifier:
    """`identify` bound to a decider, to where the shop's similar products come
    from (`matcher.gather`), and to the abbreviations learned from the memory
    (`identify.abbreviations`), when there are such sources."""
    return lambda raw_name, store, receipt_lines, paid_text="": identify(
        raw_name, store, decider, context(raw_name, store) if context else None,
        receipt_lines, paid_text, (learned or {}).get(store_key(store)))


def format_report(report: dict[str, Any]) -> str:
    totals = report["totals"]
    n = sum(totals.values()) or 1
    out = [f"What a line is: {n} lines of the answer sheet", "",
           "  " + "  ".join(f"{o} {totals[o]} ({100 * totals[o] / n:.0f}%)" for o in OUTCOMES)]
    for outcome in ("wrong", "close", "asked"):
        listed = [line for line in report["lines"] if line["outcome"] == outcome]
        if listed:
            out += ["", f"{outcome.capitalize()}:"]
            for line in listed:
                who = line["identity"]
                said = " | ".join(str(who[k]) for k in ("name", "brand", "variant") if who[k])
                out.append(f"  {line['raw_name']:<28} said: {said:<40} sheet: {line['sheet']}")
                out.append(f"  {'':<28} {line['why']}")
                if who.get("parts"):
                    out.append(f"  {'':<28} parts: " + "; ".join(
                        f"{part['printed']} = {part['means'] or '?'}" for part in who["parts"]))
    return "\n".join(out)
