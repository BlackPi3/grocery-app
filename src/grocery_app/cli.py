from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from grocery_app.catalog_globus import (
    DEFAULT_CACHE_DIR,
    DEFAULT_OUTPUT,
    STARTER_CATEGORIES,
    crawl,
)
from grocery_app.evaluate import evaluate, format_report
from grocery_app.extract import DEFAULT_MODEL, PROMPT_VERSION, extract_directory
from grocery_app.normalizer import build_purchases, save_json
from grocery_app.resolver import (
    DEFAULT_CATALOG,
    DEFAULT_OUTPUT as PROPOSALS_OUTPUT,
    build_proposals,
    build_proposals_via_search,
    confirm,
    confirm_pairs,
    read_pairs,
    to_csv,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Grocery receipt pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser(
        "purchases",
        help="Build purchases.json from verified receipts + products + resolution",
    )
    p.add_argument("--receipts-dir", default="data/gold")
    p.add_argument("--products", default="data/products.json")
    p.add_argument("--resolution", default="data/resolution.json")
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

    x = subparsers.add_parser(
        "extract",
        help="Extract structured receipts from photos with a vision model",
    )
    x.add_argument("--images", default="data/holdout/images", help="Directory of receipt photos")
    x.add_argument("--out", default="data/extracted",
                   help="Base output dir; results land in <out>/<model>/<prompt version>/")
    x.add_argument("--model", default=DEFAULT_MODEL)
    x.add_argument("--force", action="store_true", help="Re-extract even if a cached result exists")
    x.add_argument("--limit", type=int, default=None, help="Only process the first N images")

    c = subparsers.add_parser(
        "catalog",
        help="Fetch a store's product catalog from its own category listings",
    )
    c.add_argument("--store", default="globus", choices=["globus"])
    c.add_argument(
        "--category",
        action="append",
        default=[],
        metavar="PATH",
        help="Category to crawl, e.g. obst-gemuese/frisches-obst (repeatable). "
             "Defaults to the starter set.",
    )
    c.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    c.add_argument("--output", default=DEFAULT_OUTPUT)
    c.add_argument("--force", action="store_true", help="Re-fetch even if a page is cached")

    r = subparsers.add_parser(
        "propose",
        help="Propose catalog products for receipt lines resolution.json lacks",
    )
    r.add_argument("--store", default="GLOBUS")
    r.add_argument("--receipts-dir", default="data/holdout",
                   help="Verified receipt JSON; never model output")
    r.add_argument("--resolution", default="data/resolution.json")
    r.add_argument("--catalog", default=DEFAULT_CATALOG)
    r.add_argument("--output", default=PROPOSALS_OUTPUT)
    r.add_argument("--offline", action="store_true",
                   help="Rank the locally fetched catalog instead of using GLOBUS search")

    f = subparsers.add_parser(
        "confirm",
        help="Write reviewed proposals into products, resolution and store listings",
    )
    f.add_argument("--reviewed", default="data/proposals/globus.csv",
                   help="The proposal file you marked up")
    f.add_argument("--store", default="GLOBUS")
    f.add_argument("--products", default="data/products.json")
    f.add_argument("--resolution", default="data/resolution.json")
    f.add_argument("--listings", default="data/store_listings/globus.json")
    f.add_argument("--observed-on", default=date.today().isoformat(),
                   help="Date the catalog prices were observed")
    f.add_argument("--pairs", default=None,
                   help="TSV of 'raw_name<TAB>product url' to confirm directly")

    args = parser.parse_args()

    if args.command == "purchases":
        data = build_purchases(args.receipts_dir, args.products, args.resolution)
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

    if args.command == "extract":
        print(f"Extracting with {args.model} (prompt {PROMPT_VERSION}) -> {args.out}")
        summary = extract_directory(
            args.images, args.out, model=args.model, force=args.force, limit=args.limit
        )
        print(
            f"\n{summary['extracted']} extracted, {summary['cached']} cached, "
            f"{summary['failed']} failed, ${summary['cost_usd']:.3f} this run"
        )
        print(f"Score with: grocery-app eval --pred-dir {summary['out_dir']}")

    if args.command == "catalog":
        categories = args.category or STARTER_CATEGORIES
        print(f"Fetching {len(categories)} {args.store} categories -> {args.output}")
        summary = crawl(categories, args.cache_dir, args.output, force=args.force)
        print(
            f"\n{summary['products']} products in catalog "
            f"({summary['added']} new this run)"
        )
        print(f"  with price: {summary['with_price']}")
        print(f"  with brand: {summary['with_brand']}")

    if args.command == "propose":
        if args.offline:
            proposals = build_proposals(args.receipts_dir, args.resolution,
                                        args.catalog, args.store)
        else:
            proposals = build_proposals_via_search(args.receipts_dir, args.resolution,
                                                   args.store)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(to_csv(proposals, args.store), encoding="utf-8")
        with_candidates = sum(1 for p in proposals if p["candidates"])
        print(f"Wrote {out}")
        print(f"  names needing a decision: {len(proposals)}")
        print(f"  with at least one candidate: {with_candidates}")
        print(f"  no candidate found: {len(proposals) - with_candidates}")
        print("\nIn the decision column write:")
        print("  y   this candidate is the product")
        print("  n   none of these is right, and you checked")
        print("  ?   not sure — you will be asked again")
        print("  (blank means not looked at yet, which is different from 'n')")

    if args.command == "confirm":
        if args.pairs:
            result = confirm_pairs(read_pairs(args.pairs), args.products,
                                   args.resolution, args.listings, args.store,
                                   args.observed_on, args.pairs)
            print(f"Confirmed {result['added']} from {args.pairs}"
                  f" ({result['skipped']} already known)")
            return
        summary = confirm(args.reviewed, args.products, args.resolution,
                          args.listings, args.store, args.observed_on)
        print(f"Confirmed into {args.products}, {args.resolution}, {args.listings}")
        print(f"  new products:  {summary['products']}")
        print(f"  new resolution entries: {summary['entries']}")
        print(f"  store listings written: {summary['listings']}")
        if summary.get("no_match"):
            print(f"  recorded as 'no match in catalog': {summary['no_match']}")
        for decision, raw_name in summary.get("unclear", []):
            print(f"  NOT UNDERSTOOD {decision!r} on {raw_name!r} — left undecided")
        for raw_name in summary.get("ambiguous", []):
            print(f"  NEEDS YOU: {raw_name!r} — accepted rows are different products")
        if summary["skipped"]:
            print(f"  already known, skipped: {summary['skipped']}")

    if args.command == "eval":
        report = evaluate(args.truth_dir, args.pred_dir, tuple(args.exclude_store))
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(format_report(report))


if __name__ == "__main__":
    main()
