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
from grocery_app.insights import build_insights, load_purchases
from grocery_app.normalizer import build_purchases, save_json
from grocery_app.resolver import (
    DEFAULT_CATALOG,
    DEFAULT_OUTPUT as PROPOSALS_OUTPUT,
    build_proposals,
    build_proposals_via_search,
    read_reviewed,
    confirm,
    confirm_pairs,
    read_pairs,
    shelf_price,
    to_csv,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Grocery receipt pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser(
        "purchases",
        help="Build purchases.json from verified receipts + products + resolution",
    )
    p.add_argument("--receipts-dir", default="data/receipts/truth")
    p.add_argument("--products", default="data/products/products.json")
    p.add_argument("--resolution", default="data/products/resolution.json")
    p.add_argument("--line-resolutions", default="data/receipts/line_resolutions.json",
                   help="Per-line answers from the shopper; optional")
    p.add_argument("--products-dir", default="data/products",
                   help="Shelf prices, used to tell same-named products apart; optional")
    p.add_argument("--output", default="data/purchases.json")

    e = subparsers.add_parser(
        "eval",
        help="Score extracted receipts against the verified receipts",
    )
    e.add_argument("--truth-dir", default="data/receipts/truth")
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
    x.add_argument("--images", default="data/receipts/images", help="Directory of receipt photos")
    x.add_argument("--out", default="data/extracted",
                   help="Base output dir; results land in <out>/<model>/<prompt version>/")
    x.add_argument("--model", default=DEFAULT_MODEL)
    x.add_argument("--force", action="store_true", help="Re-extract even if a cached result exists")
    x.add_argument("--limit", type=int, default=None, help="Only process the first N images")

    c = subparsers.add_parser(
        "catalog",
        help="Fetch a store's product catalog from its own category listings",
    )
    c.add_argument("--store", default="globus", choices=["globus", "aldi-sued"])
    c.add_argument(
        "--category",
        action="append",
        default=[],
        metavar="PATH",
        help="Category to crawl, e.g. obst-gemuese/frisches-obst (repeatable). "
             "Defaults to the starter set.",
    )
    c.add_argument("--cache-dir", default=None,
                   help="Defaults to data/products/<store>/cache")
    c.add_argument("--output", default=None,
                   help="Defaults to data/products/<store>/crawl.json")
    c.add_argument("--service-point", default=None,
                   help="aldi-sued only: the branch whose prices to fetch (default BC08)")
    c.add_argument("--force", action="store_true", help="Re-fetch even if a page is cached")

    r = subparsers.add_parser(
        "propose",
        help="Propose catalog products for receipt lines resolution.json lacks",
    )
    r.add_argument("--store", default="GLOBUS")
    r.add_argument("--receipts-dir", default="data/receipts/truth",
                   help="Verified receipt JSON; never model output")
    r.add_argument("--resolution", default="data/products/resolution.json")
    r.add_argument("--catalog", default=DEFAULT_CATALOG)
    r.add_argument("--output", default=PROPOSALS_OUTPUT)
    r.add_argument("--offline", action="store_true",
                   help="Rank the locally fetched catalog instead of using GLOBUS search")
    r.add_argument("--force", action="store_true",
                   help="Overwrite the output even if it still holds unread decisions")

    f = subparsers.add_parser(
        "confirm",
        help="Write reviewed proposals into products, resolution and store listings",
    )
    f.add_argument("--reviewed", default="data/products/proposals/globus.csv",
                   help="The proposal file you marked up")
    f.add_argument("--store", default="GLOBUS")
    f.add_argument("--products", default="data/products/products.json")
    f.add_argument("--resolution", default="data/products/resolution.json")
    f.add_argument("--listings", default="data/products/globus/listings.json")
    f.add_argument("--observed-on", default=date.today().isoformat(),
                   help="Date the catalog prices were observed")
    f.add_argument("--pairs", default=None,
                   help="TSV of 'raw_name<TAB>product url' to confirm directly")

    i = subparsers.add_parser(
        "insights",
        help="Compute the insights (repurchase cadence, price watch, basket index, "
             "own-brand share, cross-store) from purchases.json",
    )
    i.add_argument("--purchases", default="data/purchases.json")
    i.add_argument("--output", default="data/insights.json")
    i.add_argument("--as-of", default=None,
                   help="Date the cadence is judged against (default: the last receipt)")

    n = subparsers.add_parser(
        "enrich",
        help="Fill null product attributes from Open Food Facts, by barcode",
    )
    n.add_argument("--products", default="data/products/products.json")
    n.add_argument("--cache-dir", default="data/products/off")
    n.add_argument("--force", action="store_true", help="Re-ask even for cached barcodes")

    args = parser.parse_args()

    if args.command == "purchases":
        data = build_purchases(args.receipts_dir, args.products, args.resolution,
                               args.line_resolutions, args.products_dir)
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
        if meta["ambiguous_items"]:
            print(f"  ambiguous:      {meta['ambiguous_items']}")

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
        if args.store == "aldi-sued":
            from grocery_app import catalog_aldi_sued as aldi

            cache_dir = args.cache_dir or aldi.DEFAULT_CACHE_DIR
            output = args.output or aldi.DEFAULT_OUTPUT
            service_point = args.service_point or aldi.DEFAULT_SERVICE_POINT
            print(f"Fetching ALDI SÜD catalog for branch {service_point} -> {output}")
            # No category means every leaf of the store's category tree.
            summary = aldi.crawl(args.category or None, cache_dir, output,
                                 force=args.force, service_point=service_point)
            print(f"  categories: {summary['categories']}")
        else:
            categories = args.category or STARTER_CATEGORIES
            cache_dir = args.cache_dir or DEFAULT_CACHE_DIR
            output = args.output or DEFAULT_OUTPUT
            print(f"Fetching {len(categories)} {args.store} categories -> {output}")
            summary = crawl(categories, cache_dir, output, force=args.force)
        print(
            f"\n{summary['products']} products in catalog "
            f"({summary['added']} new this run)"
        )
        print(f"  with price: {summary['with_price']}")
        print(f"  with brand: {summary['with_brand']}")

    if args.command == "propose":
        # Regenerating over a marked-up file destroys the reviewer's work, which
        # has already happened once. Run `confirm` first, or pass --force.
        existing = Path(args.output)
        if existing.exists() and not args.force:
            marked = [r for r in read_reviewed(existing)
                      if (r.get("decision") or "").strip()]
            if marked:
                print(f"{existing} still holds {len(marked)} marked rows.")
                print("Run `grocery-app confirm` to bank them, or pass --force to discard.")
                return

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
                  f" ({result['skipped']} already known,"
                  f" {result['corrected']} previously recorded as no match)")
            return
        summary = confirm(args.reviewed, args.products, args.resolution,
                          args.listings, args.store, args.observed_on,
                          price_lookup=shelf_price)
        if summary.get("supplied"):
            extra = confirm_pairs(summary["supplied"], args.products, args.resolution,
                                  args.listings, args.store, args.observed_on,
                                  args.reviewed)
            print(f"  confirmed from urls you pasted: {extra['added']}")
        print(f"Confirmed into {args.products}, {args.resolution}, {args.listings}")
        print(f"  new products:  {summary['products']}")
        print(f"  new resolution entries: {summary['entries']}")
        print(f"  store listings written: {summary['listings']}")
        if summary.get("no_match"):
            print(f"  recorded as 'no match in catalog': {summary['no_match']}")
        for decision, raw_name in summary.get("unclear", []):
            print(f"  NOT UNDERSTOOD {decision!r} on {raw_name!r} — left undecided")
        for raw_name, count in summary.get("families", {}).items():
            print(f"  family: {raw_name!r} -> {count} products the receipt cannot tell apart")
        if summary["skipped"]:
            print(f"  already known, skipped: {summary['skipped']}")

    if args.command == "insights":
        purchases = load_purchases(args.purchases)
        as_of = date.fromisoformat(args.as_of) if args.as_of else None
        data = build_insights(purchases, as_of=as_of)
        save_json(data, args.output)
        cov = data["coverage"]
        print(f"Wrote {args.output} (as of {data['as_of']})")
        print(f"  based on:       {cov['resolved_lines']}/{cov['product_lines']} product lines, "
              f"€{cov['resolved_spend']:.2f} of €{cov['spend']:.2f}")
        due = [r for r in data["repurchase"] if r["status"] == "due"]
        print(f"  repurchase:     {len(data['repurchase'])} products bought more than once, {len(due)} due")
        moved = [r for r in data["price_changes"] if r["change_pct"]]
        print(f"  price watch:    {len(data['price_changes'])} products tracked, {len(moved)} changed price")
        for entry in data["basket_index"]["series"]:
            if entry["index"] is None:
                print(f"  basket index:   {entry['month']}: n/a ({entry['reason']})")
            else:
                print(f"  basket index:   {entry['month']}: {entry['index']} "
                      f"({entry['month_over_month_pct']:+.1f}% on {entry['products']} products)")
        ob = data["own_brand"]["overall"]
        share = ob["own_brand_share_of_known"]
        print(f"  own brand:      {share*100:.0f}% of the €{ob['own_brand']+ob['brand']:.2f} with a known status"
              if share is not None else "  own brand:      no product with a known status")
        print(f"  cross-store:    {len(data['cross_store']['products'])} products at more than one store")

    if args.command == "enrich":
        from grocery_app.openfoodfacts import enrich

        print(f"Enriching {args.products} from Open Food Facts")
        summary = enrich(args.products, args.cache_dir, force=args.force)
        print(f"\n{summary['with_ean']} products with a barcode, {summary['found']} found "
              f"({summary['cached']} answered from cache), "
              f"{summary['filled']} attributes filled")

    if args.command == "eval":
        report = evaluate(args.truth_dir, args.pred_dir, tuple(args.exclude_store))
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(format_report(report))


if __name__ == "__main__":
    main()
