"""Score how well receipt lines are matched to products, against the shopper's answers.

`evaluate.py` scores the parser: did it read what the paper prints. This scores
the step after it: given what was read, did the line land on the right product.
The two are kept apart because they fail for different reasons and are fixed in
different places; a missing catalog entry is not a reading error.

The answer key is `data/receipts/product_truth.json`, and its provenance is the
shopper, never a model. Each line there names its product in up to two ways
that can be checked by machine:

- `catalog_ids`: the catalog product(s) it is, when the catalog already holds
  it. More than one means the shopper knows the family, not the variant.
- `article`: the shop's own article number, when the shop lists it.

A line with neither (Kashk from a local shop, a birthday card) is described
only in words, and nothing here pretends to check a machine answer against
words.

The matcher is run exactly as the server runs it — `normalize_receipt` — with
**no** shopper answers for these lines. Scoring a matcher on answers it has
already been given would be marking its own homework.

Every line gets one outcome:

- `right`   it answered, and the answer is the shopper's product (for a family,
            the shopper's product is among the choices);
- `wrong`   it answered, and the answer is some other product;
- `unchecked` it answered, but the key has only words to compare with;
- `asked`   it put the line to the shopper as a question (only with `--matcher`);
- `missed`  it left the line open, but the product was already in the catalog;
- `new`     it left the line open, and the product is not in the catalog yet.

`missed` is the matcher's fault. `new` is the catalog's gap, and the number the
catalog-growth work exists to bring down.

With a matcher (`matcher.propose`, step 4b), every line the memory leaves open
goes to it. An accepted pick is judged like any answer, and a pick of a shop
listing is right when its article number is the shopper's. A question is
`asked`, and the model's pick on it is judged all the same, as `model_alone`:
how often a question was one the model would have got right is what tells
whether the rule for accepting is too strict.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from grocery_app.normalizer import load_json, normalize_receipt

OUTCOMES = ("right", "wrong", "unchecked", "asked", "missed", "new")
ANSWERED = {"exact", "price", "user", "family", "produce"}


def article_index(products: dict[str, dict[str, Any]],
                  products_dir: str | Path | None) -> dict[str, str]:
    """Shop article number or barcode -> catalog product id.

    Two routes lead from a shop's number to our product: a listing banked by
    `confirm` (`<store>/listings.json`), and a barcode recorded on the product.
    """
    index: dict[str, str] = {}
    for product_id, product in products.items():
        for ean in product.get("eans") or []:
            index[str(ean)] = product_id
    if products_dir and Path(products_dir).is_dir():
        for path in sorted(Path(products_dir).glob("*/listings.json")):
            for article, listing in load_json(path).get("listings", {}).items():
                index[str(article)] = listing["product_id"]
    return index


def expected_ids(truth_line: dict[str, Any], index: dict[str, str]) -> set[str]:
    """The catalog products the shopper's answer points at, by either route."""
    ids = set(truth_line.get("catalog_ids") or [])
    article = truth_line.get("article")
    if article and str(article) in index:
        ids.add(index[str(article)])
    return ids


def answered_ids(record: dict[str, Any]) -> set[str]:
    """The catalog products the matcher's reading of a line points at."""
    if record.get("resolution") not in ANSWERED:
        return set()
    if record.get("product_id"):
        return {record["product_id"]}
    return set(record.get("candidate_ids") or [])


def judge(record: dict[str, Any], truth_line: dict[str, Any],
          index: dict[str, str]) -> str:
    """One line's outcome. See the module docstring for what each means."""
    expected = expected_ids(truth_line, index)
    answered = answered_ids(record)
    if answered:
        if expected & answered:
            return "right"
        return "wrong" if expected else "unchecked"
    return "missed" if expected else "new"


def judge_pick(pick: dict[str, Any] | None, truth_line: dict[str, Any],
               index: dict[str, str]) -> str:
    """How a matcher's pick fares against the key: right, wrong, unchecked or none.

    A pick is our product (`product_id`), a shop's listing (`article`), or
    both. Either route to the shopper's answer makes it right.
    """
    if pick is None:
        return "none"
    expected = expected_ids(truth_line, index)
    article = truth_line.get("article")
    if (pick.get("product_id") and pick["product_id"] in expected) or \
            (article and pick.get("article") == str(article)):
        return "right"
    return "wrong" if expected or article else "unchecked"


Matcher = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def evaluate_matching(truth_doc: dict[str, Any], readings: dict[str, dict[str, Any]],
                      resolution: dict[tuple[str, str], list[str]],
                      products: dict[str, dict[str, Any]],
                      shelf_prices: dict[str, set[float]] | None = None,
                      index: dict[str, str] | None = None,
                      matcher: Matcher | None = None) -> dict[str, Any]:
    """Run the matcher over the read receipts and score it line by line.

    `readings` maps a photo name to the receipt as the parser read it. A truth
    line whose photo has no reading, or whose position no longer holds the same
    printed name, is reported as `stale` rather than scored: the key was
    written against a different reading, and guessing which line it meant would
    make the score depend on the guess.
    """
    index = index or {}
    records: dict[str, list[dict[str, Any]]] = {}
    for image in {t["source_image"] for t in truth_doc["lines"]}:
        if image in readings:
            records[image] = normalize_receipt(readings[image], resolution, products,
                                               None, shelf_prices)

    lines: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    for truth_line in truth_doc["lines"]:
        image, position = truth_line["source_image"], truth_line["position"]
        read = records.get(image)
        if read is None or position >= len(read) or \
                read[position].get("raw_name") != truth_line["raw_name"]:
            stale.append(truth_line)
            continue
        record = read[position]
        scored = {
            "source_image": image, "position": position, "store": truth_line["store"],
            "raw_name": truth_line["raw_name"], "net_paid": record.get("net_paid") or 0.0,
            "expected": truth_line["product"], "known": truth_line.get("known"),
            "resolution": record.get("resolution"),
            "answered": sorted(answered_ids(record)),
            "outcome": judge(record, truth_line, index),
        }
        if matcher is not None and record.get("resolution") == "none" and \
                record.get("type") == "product":
            proposal = matcher(readings[image]["lines"][position], readings[image])
            model_alone = judge_pick(proposal["pick"], truth_line, index)
            scored.update(proposal=proposal, model_alone=model_alone,
                          offered=any(judge_pick(c, truth_line, index) == "right"
                                      for c in proposal["candidates"]))
            if proposal["verdict"] == "accept":
                scored["resolution"] = "matcher"
                scored["answered"] = [proposal["pick"].get("product_id")
                                      or proposal["pick"].get("article")]
                scored["outcome"] = model_alone
            else:
                scored["outcome"] = "asked"
        lines.append(scored)

    return {"totals": _tally(lines),
            "by_store": {store: _tally([line for line in lines if line["store"] == store])
                         for store in sorted({line["store"] for line in lines})},
            "lines": lines, "stale": stale}


def _tally(lines: list[dict[str, Any]]) -> dict[str, Any]:
    count: Counter = Counter()
    euros: defaultdict[str, float] = defaultdict(float)
    for line in lines:
        count[line["outcome"]] += 1
        euros[line["outcome"]] += line["net_paid"]
    return {"lines": len(lines),
            "count": {outcome: count[outcome] for outcome in OUTCOMES},
            "euros": {outcome: round(euros[outcome], 2) for outcome in OUTCOMES},
            "total_euros": round(sum(euros.values()), 2)}


def _answer_label(line: dict[str, Any]) -> str:
    if line.get("resolution") == "matcher":
        return (line["proposal"]["pick"] or {}).get("name") or "-"
    return ",".join(line["answered"]) or "-"


def load_readings(directory: str | Path, images: set[str]) -> dict[str, dict[str, Any]]:
    """The parser's reading of each photo in `images`, from `<directory>/<stem>.json`."""
    readings = {}
    for image in images:
        path = Path(directory) / f"{Path(image).stem}.json"
        if path.exists():
            readings[image] = json.loads(path.read_text(encoding="utf-8"))
    return readings


def format_matching_report(report: dict[str, Any]) -> str:
    totals = report["totals"]
    lines = [f"Matching: {totals['lines']} product lines, "
             f"€{totals['total_euros']:.2f} spent", ""]

    def row(label: str, tally: dict[str, Any]) -> str:
        n = tally["lines"] or 1
        cells = "  ".join(f"{o} {tally['count'][o]:>3} ({100 * tally['count'][o] / n:3.0f}%)"
                          for o in OUTCOMES)
        return f"  {label:<22} {cells}"

    lines.append(row("all", totals))
    for store, tally in report["by_store"].items():
        lines.append(row(store[:22], tally))
    lines += ["", "  by money: " + "  ".join(
        f"{o} €{totals['euros'][o]:.2f}" for o in OUTCOMES)]
    # Which step gave each answer: the memory (`exact`, `family`, `price`) or
    # the produce vocabulary. A score that rose says nothing about which part
    # of the matcher earned it.
    how = Counter(line["resolution"] for line in report["lines"] if line["answered"])
    if how:
        lines.append("  answered by: " + "  ".join(f"{h} {n}" for h, n in how.most_common()))

    asked = [line for line in report["lines"] if line["outcome"] == "asked"]
    if asked:
        alone = Counter(line["model_alone"] for line in asked)
        picks = "  ".join(f"{k} {alone[k]}" for k in ("right", "wrong", "unchecked", "none"))
        offered = sum(line["offered"] for line in asked)
        lines += ["", f"  asked {len(asked)}: the model's own pick was {picks}; "
                      f"the right answer was among the candidates for {offered}"]

    for outcome in ("wrong", "missed"):
        bad = [line for line in report["lines"] if line["outcome"] == outcome]
        if bad:
            lines += ["", f"{outcome.capitalize()}:"]
            lines += [f"  {line['store'][:10]:<10} {line['raw_name']:<28} "
                      f"answered {_answer_label(line):<14} "
                      f"expected {line['expected']}" for line in bad]
    if report["stale"]:
        lines += ["", f"Stale: {len(report['stale'])} truth lines no longer match "
                      "the reading at their position, and were not scored."]
    return "\n".join(lines)
