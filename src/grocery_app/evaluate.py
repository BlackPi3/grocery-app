"""Score extracted receipts against the hand-transcribed held-out set.

This measures the **parser** only: did it read what is printed on the paper.
It deliberately does not score product resolution — the held-out ground truth in
`data/holdout/` carries no `product_id`, because a human transcribing a receipt
can only be trusted for what the receipt says, not for which catalog entry it
maps to. Normalizer coverage is a separate metric against the catalog, and
conflating the two would blame the parser for a missing catalog entry.

Lines are matched, never compared by position: a parser that drops one line
would otherwise score zero on every line after it. Unmatched ground-truth lines
are reported as *missed*, unmatched predicted lines as *spurious* — the latter
being the failure mode where a model transcribes reversed (Sofortstorno) lines
that were never actually bought.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

# A candidate pair below this combined score is treated as "no match at all"
# rather than a badly-read line, so genuine misses stay visible as misses.
MATCH_THRESHOLD = 0.45
COMPARED_FIELDS = ("raw_name", "qty", "net", "tax_class")


def load_receipts(directory: str | Path) -> dict[str, dict[str, Any]]:
    """Load receipts from a directory, keyed by the image they came from."""
    receipts = {}
    for path in sorted(Path(directory).glob("*.json")):
        if path.name.endswith(".meta.json"):
            continue  # extraction sidecar (usage, cost), not a receipt
        data = json.loads(path.read_text(encoding="utf-8"))
        receipts[data.get("source_image", path.stem)] = data
    return receipts


def _similarity(truth_line: dict, pred_line: dict) -> float:
    name_ratio = SequenceMatcher(
        None, str(truth_line.get("raw_name", "")), str(pred_line.get("raw_name", ""))
    ).ratio()
    same_price = truth_line.get("net") == pred_line.get("net")
    return 0.7 * name_ratio + 0.3 * float(same_price)


def match_lines(truth_lines: list[dict], pred_lines: list[dict]) -> tuple[list, list, list]:
    """Pair predicted lines to ground-truth lines.

    Returns (pairs, missed, spurious). Exact name+price agreements are paired
    first so that a duplicated item on a receipt cannot steal its twin's match.
    """
    remaining = list(pred_lines)
    pairs: list[tuple[dict, dict]] = []
    unpaired_truth: list[dict] = []

    for truth_line in truth_lines:
        exact = next(
            (
                p
                for p in remaining
                if p.get("raw_name") == truth_line.get("raw_name")
                and p.get("net") == truth_line.get("net")
            ),
            None,
        )
        if exact is not None:
            remaining.remove(exact)
            pairs.append((truth_line, exact))
        else:
            unpaired_truth.append(truth_line)

    missed: list[dict] = []
    for truth_line in unpaired_truth:
        best, best_score = None, 0.0
        for candidate in remaining:
            score = _similarity(truth_line, candidate)
            if score > best_score:
                best, best_score = candidate, score
        if best is not None and best_score >= MATCH_THRESHOLD:
            remaining.remove(best)
            pairs.append((truth_line, best))
        else:
            missed.append(truth_line)

    return pairs, missed, remaining


def score_receipt(truth: dict, pred: dict | None) -> dict[str, Any]:
    """Compare one predicted receipt against its ground truth."""
    truth_lines = truth.get("lines", [])
    if pred is None:
        return {
            "store": truth.get("store", "?"),
            "source_image": truth.get("source_image", "?"),
            "produced": False,
            "truth_lines": len(truth_lines),
            "matched": 0,
            "missed": len(truth_lines),
            "spurious": 0,
            "fields": {field: [0, 0] for field in COMPARED_FIELDS},
            "header": {field: False for field in ("store", "date", "printed_total")},
            "exact": False,
            "errors": ["no prediction produced for this receipt"],
        }

    pairs, missed, spurious = match_lines(truth_lines, pred.get("lines", []))

    fields = {field: [0, 0] for field in COMPARED_FIELDS}
    errors: list[str] = []
    for truth_line, pred_line in pairs:
        for field in COMPARED_FIELDS:
            fields[field][1] += 1
            if truth_line.get(field) == pred_line.get(field):
                fields[field][0] += 1
            else:
                errors.append(
                    f"{field}: {truth_line.get(field)!r} != {pred_line.get(field)!r}"
                    f" (on {truth_line.get('raw_name')!r})"
                )

    # Store is an identity, not a transcription: two ALDI branches print
    # "ALDI SÜD" and "Aldi Süd", and neither reading is wrong.
    header = {
        "store": str(truth.get("store", "")).casefold() == str(pred.get("store", "")).casefold(),
        "date": truth.get("date") == pred.get("date"),
        "printed_total": truth.get("printed_total") == pred.get("printed_total"),
    }
    errors += [f"missed line: {line.get('raw_name')!r}" for line in missed]
    errors += [f"spurious line: {line.get('raw_name')!r}" for line in spurious]
    errors += [f"header {field} wrong" for field, ok in header.items() if not ok]

    return {
        "store": truth.get("store", "?"),
        "source_image": truth.get("source_image", "?"),
        "produced": True,
        "truth_lines": len(truth_lines),
        "matched": len(pairs),
        "missed": len(missed),
        "spurious": len(spurious),
        "fields": fields,
        "header": header,
        "exact": not errors,
        "errors": errors,
    }


def evaluate(
    truth_dir: str | Path,
    pred_dir: str | Path,
    exclude_stores: tuple[str, ...] = (),
) -> dict[str, Any]:
    truth = load_receipts(truth_dir)
    predictions = load_receipts(pred_dir)

    results = [score_receipt(t, predictions.get(image)) for image, t in truth.items()]
    excluded = {s.casefold() for s in exclude_stores}
    included = [r for r in results if r["store"].casefold() not in excluded]

    # Group stores case-insensitively: the same chain transcribed as "ALDI SÜD"
    # on one receipt and "Aldi Süd" on another is one store, not two.
    spellings: dict[str, Counter] = defaultdict(Counter)
    for result in included:
        spellings[result["store"].casefold()][result["store"]] += 1

    by_store, variants = {}, {}
    for key, seen in spellings.items():
        display = seen.most_common(1)[0][0]
        by_store[display] = _aggregate(
            [r for r in included if r["store"].casefold() == key]
        )
        if len(seen) > 1:
            variants[display] = sorted(seen)

    return {
        "results": results,
        "included": included,
        "excluded_stores": sorted(exclude_stores),
        "unexpected": sorted(set(predictions) - set(truth)),
        "store_name_variants": variants,
        "totals": _aggregate(included),
        "by_store": by_store,
    }


def _aggregate(results: list[dict]) -> dict[str, Any]:
    fields = {field: [0, 0] for field in COMPARED_FIELDS}
    for result in results:
        for field, (correct, total) in result["fields"].items():
            fields[field][0] += correct
            fields[field][1] += total
    return {
        "receipts": len(results),
        "exact_receipts": sum(r["exact"] for r in results),
        "truth_lines": sum(r["truth_lines"] for r in results),
        "matched": sum(r["matched"] for r in results),
        "missed": sum(r["missed"] for r in results),
        "spurious": sum(r["spurious"] for r in results),
        "fields": fields,
        "header": {
            field: sum(r["header"][field] for r in results)
            for field in ("store", "date", "printed_total")
        },
    }


def _pct(correct: int, total: int) -> str:
    return "   n/a" if not total else f"{100 * correct / total:5.1f}%"


def format_report(report: dict[str, Any]) -> str:
    out: list[str] = []
    totals = report["totals"]
    out.append(
        f"Receipt extraction accuracy — {totals['receipts']} receipts, "
        f"{len(report['by_store'])} stores"
    )
    if report["excluded_stores"]:
        out.append(f"Excluded from totals: {', '.join(report['excluded_stores'])}")
    out.append("")

    header = f"{'store':<22}{'rcpt':>5}{'lines':>7}{'miss':>6}{'spur':>6}"
    header += "".join(f"{field:>10}" for field in COMPARED_FIELDS)
    out.append(header)
    out.append("-" * len(header))

    for store, agg in sorted(
        report["by_store"].items(), key=lambda kv: -kv[1]["truth_lines"]
    ):
        row = (
            f"{store[:21]:<22}{agg['receipts']:>5}{agg['truth_lines']:>7}"
            f"{agg['missed']:>6}{agg['spurious']:>6}"
        )
        row += "".join(_pct(*agg["fields"][field]).rjust(10) for field in COMPARED_FIELDS)
        out.append(row)

    out.append("-" * len(header))
    row = (
        f"{'TOTAL':<22}{totals['receipts']:>5}{totals['truth_lines']:>7}"
        f"{totals['missed']:>6}{totals['spurious']:>6}"
    )
    row += "".join(_pct(*totals["fields"][field]).rjust(10) for field in COMPARED_FIELDS)
    out.append(row)
    out.append("")

    out.append(
        f"Receipts fully correct: {totals['exact_receipts']}/{totals['receipts']}"
        f"  ({_pct(totals['exact_receipts'], totals['receipts']).strip()})"
    )
    out.append(
        "Header fields correct:  "
        + ", ".join(
            f"{field} {count}/{totals['receipts']}"
            for field, count in totals["header"].items()
        )
    )

    if report.get("store_name_variants"):
        out.append("\nSame store transcribed inconsistently (grouped here, but worth "
                   "making consistent in the ground truth):")
        for display, seen in sorted(report["store_name_variants"].items()):
            out.append(f"  {display}: {', '.join(repr(v) for v in seen)}")

    if report["unexpected"]:
        out.append(f"\nPredictions with no ground truth: {', '.join(report['unexpected'])}")

    worst = sorted(
        (r for r in report["included"] if not r["exact"]),
        key=lambda r: -len(r["errors"]),
    )
    if worst:
        out.append("\nReceipts with errors (worst first):")
        for result in worst:
            out.append(f"\n  {result['source_image']}  [{result['store']}]  "
                       f"{len(result['errors'])} error(s)")
            for error in result["errors"][:6]:
                out.append(f"    - {error}")
            if len(result["errors"]) > 6:
                out.append(f"    ... and {len(result['errors']) - 6} more")

    return "\n".join(out)


def error_breakdown(report: dict[str, Any]) -> Counter:
    """Count error kinds across all receipts, to see where failures cluster."""
    kinds: Counter = Counter()
    for result in report["included"]:
        for error in result["errors"]:
            kinds[error.split(":")[0].split(" (")[0]] += 1
    return kinds
