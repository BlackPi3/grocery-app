from __future__ import annotations

import argparse
from pathlib import Path

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


if __name__ == "__main__":
    main()
