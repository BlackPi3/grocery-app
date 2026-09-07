from __future__ import annotations

import argparse
import json
from pathlib import Path

from grocery_app.evaluate import evaluate, format_report
from grocery_app.normalizer import build_purchases, save_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Grocery receipt pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser(
        "purchases",
        help="Build purchases.json from gold receipts + catalog + resolution map",
    )
    p.add_argument("--gold-dir", default="data/gold")
    p.add_argument("--catalog", default="data/catalog.json")
    p.add_argument("--resolution-map", default="data/resolution_map.json")
    p.add_argument("--output", default="data/purchases.json")

    e = subparsers.add_parser(
        "eval",
        help="Score extracted receipts against the hand-transcribed held-out set",
    )
    e.add_argument("--truth-dir", default="data/holdout")
    e.add_argument("--pred-dir", required=True, help="Directory of extracted receipt JSON")
    e.add_argument(
        "--exclude-store",
        action="append",
        default=[],
        metavar="NAME",
        help="Store to leave out of the totals (repeatable). Use for non-grocery "
             "receipts kept in the set for format variety.",
    )
    e.add_argument("--json", action="store_true", help="Emit the raw report as JSON")

    args = parser.parse_args()

    if args.command == "purchases":
        data = build_purchases(args.gold_dir, args.catalog, args.resolution_map)
        save_json(data, args.output)
        meta = data["meta"]
        print(f"Wrote {args.output}")
        print(f"  receipts:       {meta['receipts']}")
        print(f"  product lines:  {meta['product_lines']}")
        print(f"  total net paid: €{meta['total_net_paid']:.2f}")
        print(f"  date range:     {meta['date_range']}")
        if meta["unresolved_items"]:
            print(f"  UNRESOLVED:     {meta['unresolved_items']}")
        else:
            print("  unresolved:     none — every item resolved")

    if args.command == "eval":
        report = evaluate(args.truth_dir, args.pred_dir, tuple(args.exclude_store))
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(format_report(report))


if __name__ == "__main__":
    main()
