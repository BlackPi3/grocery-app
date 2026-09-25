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
from grocery_app.evaluate_matching import (
    article_index,
    evaluate_matching,
    format_matching_report,
    load_readings,
)
from grocery_app.extract import DEFAULT_MODEL, PROMPT_VERSION, extract_directory
from grocery_app.insights import build_insights, load_purchases
from grocery_app.normalizer import (
    build_purchases,
    load_json,
    load_products,
    load_resolution,
    load_shelf_prices,
    save_json,
)
from grocery_app.resolver import (
    DEFAULT_CATALOG,
    build_proposals,
    build_proposals_via_search,
    confirm,
    confirm_pairs,
    read_pairs,
    read_reviewed,
    shelf_price,
    to_csv,
)
from grocery_app.resolver import (
    DEFAULT_OUTPUT as PROPOSALS_OUTPUT,
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

    em = subparsers.add_parser(
        "eval-matching",
        help="Score how receipt lines are matched to products, against the shopper's answers",
    )
    em.add_argument("--truth", default="data/receipts/product_truth.json")
    em.add_argument("--readings", default=f"data/extracted/{DEFAULT_MODEL}/{PROMPT_VERSION}",
                    help="Directory of the parser's readings, one <photo stem>.json each")
    em.add_argument("--products", default="data/products/products.json")
    em.add_argument("--resolution", default="data/products/resolution.json")
    em.add_argument("--products-dir", default="data/products")
    em.add_argument("--matcher", choices=["claude-code"], default=None,
                    help="Also run the matcher (step 4b) on lines the memory leaves open. "
                         "claude-code asks the model through `claude -p`, on the "
                         "subscription; answers are cached under data/matched/")
    em.add_argument("--matcher-model", default="sonnet")
    em.add_argument("--json", action="store_true", help="Emit the raw report as JSON")

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
             "budget-brand share, cross-store) from purchases.json",
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

    pr = subparsers.add_parser(
        "produce",
        help="Resolve loose produce, which has no barcode and no article number, "
             "through a store-independent vocabulary of kinds",
    )
    pr.add_argument("action", choices=["propose", "confirm"],
                    help="propose: write a review CSV of unresolved names; "
                         "confirm: write the rows you marked into the catalog")
    pr.add_argument("--purchases", default="data/purchases.json",
                    help="propose: the history to read unresolved names from")
    pr.add_argument("--out", default="data/products/proposals/produce.csv",
                    help="propose: where to write the review CSV")
    pr.add_argument("--reviewed", default="data/products/proposals/produce.csv",
                    help="confirm: the CSV you marked up")
    pr.add_argument("--products", default="data/products/products.json")
    pr.add_argument("--resolution", default="data/products/resolution.json")

    ca = subparsers.add_parser(
        "category",
        help="Attach products to the closed category vocabulary: what kind of "
             "thing each one is, on the shopping-list granularity",
    )
    ca.add_argument("action", choices=["propose", "confirm"],
                    help="propose: write a review CSV for every product with no "
                         "category from the vocabulary; confirm: write it back")
    ca.add_argument("--products", default="data/products/products.json")
    ca.add_argument("--listings", default="data/products/globus/listings.json",
                    help="propose: the shop's own shelf for products matched to "
                         "its catalogue — the strongest evidence there is")
    ca.add_argument("--out", default="data/products/proposals/categories.csv",
                    help="propose: where to write the review CSV")
    ca.add_argument("--reviewed", default="data/products/proposals/categories.csv",
                    help="confirm: the CSV you marked up")

    co = subparsers.add_parser(
        "coarse",
        help="Write reviewed coarse rows (brand + product line, no invented variant "
             "and no invented EAN) into the catalog",
    )
    co.add_argument("action", choices=["propose", "confirm"])
    co.add_argument("--purchases", default="data/purchases.json",
                    help="propose: the history to read unresolved lines from")
    co.add_argument("--out", default="data/products/proposals/coarse-resolution.csv",
                    help="propose: where to write the review CSV")
    co.add_argument("--reviewed", default="data/products/proposals/coarse-resolution.csv",
                    help="the reviewed CSV: store, raw_name, route, brand, product, ean")
    co.add_argument("--products", default="data/products/products.json")
    co.add_argument("--resolution", default="data/products/resolution.json")

    s = subparsers.add_parser(
        "serve",
        help="Serve purchases.json and the insights over HTTP (needs the 'api' extra)",
    )
    s.add_argument("--purchases", default="data/purchases.json")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)

    d = subparsers.add_parser(
        "db",
        help="The PostgreSQL store behind `serve` (needs the 'api' extra and DATABASE_URL)",
    )
    d.add_argument("action", choices=["upgrade", "import", "export", "match", "add-readings",
                                      "answer"],
                   help="upgrade: apply the migrations; import: load the data/ files into "
                        "the tables (idempotent); export: write the tables out as files; "
                        "match: run the matcher over stored receipts (claude -p, on the "
                        "subscription), saving its answers and questions; add-readings: add "
                        "model-read receipts (--readings) for the photos in --photos; answer: "
                        "give the shopper's answers in --truth to the open questions")
    d.add_argument("--url", default=None,
                   help="Database URL; defaults to the DATABASE_URL environment variable")
    d.add_argument("--receipts-dir", default="data/receipts/truth")
    d.add_argument("--products", default="data/products/products.json")
    d.add_argument("--resolution", default="data/products/resolution.json")
    d.add_argument("--line-resolutions", default="data/receipts/line_resolutions.json")
    d.add_argument("--products-dir", default="data/products")
    d.add_argument("--readings", default=f"data/extracted/{DEFAULT_MODEL}/{PROMPT_VERSION}")
    d.add_argument("--photos", default="data/receipts/fresh",
                   help="add-readings: only the readings of the photos in this directory")
    d.add_argument("--truth", default="data/receipts/product_truth.json")
    d.add_argument("--out", default=None,
                   help="export: directory to write the data/ layout into (required)")

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
        if summary["families"]:
            print(f"  of those, families the shopper settles: {summary['families']}")
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
        print(f"  repurchase:     {len(data['repurchase'])} products bought more than once, "
              f"{len(due)} due")
        moved = [r for r in data["price_changes"] if r["change_pct"]]
        print(f"  price watch:    {len(data['price_changes'])} products tracked, "
              f"{len(moved)} changed price")
        for entry in data["basket_index"]["series"]:
            if entry["index"] is None:
                print(f"  basket index:   {entry['month']}: n/a ({entry['reason']})")
            else:
                print(f"  basket index:   {entry['month']}: {entry['index']} "
                      f"({entry['month_over_month_pct']:+.1f}% on {entry['products']} products)")
        bb = data["budget_brand"]["overall"]
        share = bb["budget_share_of_known"]
        if share is None:
            print("  budget brand:   no product with a known status")
        else:
            print(f"  budget brand:   {share*100:.0f}% of the "
                  f"€{bb['budget']+bb['name_brand']:.2f} with a known status")
        print(f"  cross-store:    {len(data['cross_store']['products'])} products "
              f"at more than one store")

    if args.command == "enrich":
        from grocery_app.openfoodfacts import enrich

        print(f"Enriching {args.products} from Open Food Facts")
        summary = enrich(args.products, args.cache_dir, force=args.force)
        print(f"\n{summary['with_ean']} products with a barcode, {summary['found']} found "
              f"({summary['cached']} answered from cache), "
              f"{summary['filled']} attributes filled")

    if args.command == "coarse":
        from grocery_app import coarse as coarse_module

        if args.action == "propose":
            before = coarse_module.read_rows(args.out) if Path(args.out).exists() else []
            rows = coarse_module.propose(load_purchases(args.purchases),
                                         json.loads(Path(args.products).read_text("utf-8")),
                                         before)
            coarse_module.write_proposals(rows, args.out)
            named = sum(1 for r in rows if r["brand"])
            print(f"Wrote {len(rows)} rows to {args.out}")
            print(f"  brand read off the printed line: {named}")
            print(f"  no brand, name expanded only:    {len(rows) - named}")
            print("  set `route` to ask / nonproduct / outofscope / dropped where it "
                  "is not a product, then:")
            print(f"    grocery-app coarse confirm --reviewed {args.out}")
            return

        summary = coarse_module.confirm(args.reviewed, args.products, args.resolution)
        print(f"Confirmed into {args.products}, {args.resolution}")
        print(f"  new coarse products:    {summary['products']}"
              f" ({summary['with_ean']} with a confirmed EAN)")
        print(f"  new resolution entries: {summary['entries']}")
        print(f"  already known, skipped: {summary['skipped_known']}")
        for route, count in sorted(summary["by_route"].items()):
            if route not in coarse_module.WRITES:
                why = coarse_module.SKIPS.get(route, "unknown route")
                print(f"  not written ({route}): {count} — {why}")
        return

    if args.command == "produce":
        from grocery_app import produce as produce_module

        if args.action == "propose":
            # Decisions already made are carried over, so re-running after the
            # vocabulary improves does not throw away a review.
            before = produce_module.read_proposals(args.out)
            rows = produce_module.propose(load_purchases(args.purchases), before)
            produce_module.write_proposals(rows, args.out)
            guessed = [r for r in rows if r["kind"]]
            families = [r for r in guessed if "|" in r["kind"]]
            lines = sum(r["lines"] for r in guessed)
            kept = sum(1 for r in rows if r["decision"])
            print(f"Wrote {len(rows)} rows to {args.out}")
            print(f"  the vocabulary has a guess for: {len(guessed)} names, {lines} lines")
            print(f"  of those, ambiguous (pick one, or keep the family): {len(families)}")
            print(f"  no guess (mark them or leave them): {len(rows) - len(guessed)}")
            if before:
                dropped = sum(1 for r in before if r["decision"]) - kept
                print(f"  decisions carried over: {kept}"
                      + (f", cleared because the guess changed: {dropped}" if dropped else ""))
            print("  mark `decision` y / n, or type a kind name to override, then:")
            print(f"    grocery-app produce confirm --reviewed {args.out}")
            return

        summary = produce_module.confirm(args.reviewed, args.products, args.resolution)
        print(f"Confirmed into {args.products}, {args.resolution}")
        print(f"  new produce kinds:      {summary['products']}")
        print(f"  new resolution entries: {summary['entries']}")
        if summary["families"]:
            print(f"  of those, families the shopper settles: {summary['families']}")
        if summary["rejected"]:
            print(f"  rejected:               {summary['rejected']}")
        if summary["skipped"]:
            print(f"  already known, skipped: {summary['skipped']}")
        if summary["undecided"]:
            print(f"  left undecided:         {summary['undecided']}")
        for name in sorted(set(summary["new_kinds"])):
            print(f"  NOT IN THE VOCABULARY yet: {name!r} — add it to produce.py")
        for name in sorted(set(summary["uncategorised"])):
            print(f"  NOT WRITTEN, no category for {name!r}: add it to KIND_CATEGORIES "
                  "in produce.py and run this again — your decision is still in the CSV")

    if args.command == "category":
        from grocery_app import categorize

        products_doc = json.loads(Path(args.products).read_text(encoding="utf-8"))
        if args.action == "propose":
            listings_path = Path(args.listings)
            listings = (json.loads(listings_path.read_text(encoding="utf-8"))["listings"]
                        if listings_path.exists() else {})
            before = (categorize.read_reviewed(args.out)
                      if Path(args.out).exists() else [])
            rows = categorize.proposals(products_doc, listings, before)
            categorize.write_proposals(rows, args.out)
            settled = sum(1 for r in rows if r["decision"])
            print(f"Wrote {len(rows)} rows to {args.out}")
            print(f"  answered by two sources agreeing (already marked y): {settled}")
            for how, what in (("conflict", "the shop's shelf and the name disagree"),
                              ("name?", "the name points at more than one"),
                              ("", "nothing matched at all")):
                count = sum(1 for r in rows if r["how"] == how)
                if count:
                    print(f"  {what}: {count}")
            print("  mark `decision` y / n, or type a category key to override, then:")
            print(f"    grocery-app category confirm --reviewed {args.out}")
            return

        summary = categorize.confirm(args.reviewed, args.products)
        print(f"Confirmed into {args.products}")
        print(f"  categories written: {summary['written']}")
        if summary["rejected"]:
            print(f"  rejected:           {summary['rejected']}")
        if summary["undecided"]:
            print(f"  left undecided:     {summary['undecided']}")
        for gap in summary["unknown_categories"]:
            print(f"  NOT IN THE VOCABULARY: {gap} — add it to categories.py")
        for product_id in summary["unknown_products"]:
            print(f"  no such product: {product_id}")
        return

    if args.command == "serve":
        try:
            import uvicorn

            from grocery_app.api.app import create_app
            from grocery_app.api.images import default_image_store
            from grocery_app.api.jobs import anthropic_extractor
            from grocery_app.api.repository import default_repository
        except ImportError as exc:
            raise SystemExit(
                f"the HTTP layer is not installed ({exc.name}); run: pip install -e '.[api]'"
            ) from exc
        repository = default_repository(args.purchases)
        on_postgres = type(repository).__name__ == "PostgresRepository"
        source = "PostgreSQL (DATABASE_URL)" if on_postgres else args.purchases
        store = default_image_store()
        print(f"Serving {source} at http://{args.host}:{args.port} (docs at /docs)")
        if on_postgres:
            print(f"  uploads:  POST /v1/receipts, photos in {store.root}")
        else:
            print("  uploads:  off (needs DATABASE_URL)")
        # The extractor builds its client on first use, so no API key is
        # needed to start a server that only ever serves reads.
        uvicorn.run(create_app(repository, store, anthropic_extractor()),
                    host=args.host, port=args.port)

    if args.command == "db":
        from grocery_app.db.migrate import upgrade
        from grocery_app.db.session import database_url

        url = args.url or database_url()
        if not url:
            raise SystemExit("no database: pass --url or set DATABASE_URL")
        if args.action == "upgrade":
            upgrade(url)
            print("Database is at the current revision")
            return
        from grocery_app.db.io import export_data, import_data
        from grocery_app.db.session import make_engine, make_session_factory

        factory = make_session_factory(make_engine(url))
        if args.action == "import":
            with factory() as session:
                summary = import_data(session, args.receipts_dir, args.products, args.resolution,
                                      args.line_resolutions, args.products_dir)
                session.commit()
            for kind in ("products", "receipts", "resolutions", "listings", "line_resolutions"):
                print(f"  {kind + ':':<18}{summary[kind]['added']} added, "
                      f"{summary[kind]['updated']} updated")
            for image in summary["line_resolutions_skipped"]:
                print(f"  SKIPPED line answer for {image}: no such receipt")
        if args.action == "add-readings":
            from grocery_app.db.io import import_receipts

            photos = {p.name for p in Path(args.photos).iterdir()}
            paths = [Path(args.readings) / f"{Path(name).stem}.json" for name in sorted(photos)]
            missing = [p.name for p in paths if not p.exists()]
            if missing:
                raise SystemExit(f"no reading for: {', '.join(missing)}")
            for path in paths:
                if load_json(path).get("transcribed_by") != "llm":
                    raise SystemExit(f"{path.name} is not marked as a model's reading")
            with factory() as session:
                summary = import_receipts(session, paths)
                session.commit()
            print(f"  receipts: {summary['receipts']['added']} added, "
                  f"{summary['receipts']['updated']} updated")
        if args.action == "answer":
            from grocery_app.api.answers import apply_answers
            from grocery_app.api.repository import PostgresRepository

            truth = load_json(args.truth)
            done = apply_answers(PostgresRepository(factory), truth,
                                 truth.get("meta", {}).get("answered_by") or "shopper",
                                 f"answer sheet {Path(args.truth).name}")
            for kind, labels in done.items():
                print(f"  {kind + ':':<16}{len(labels)}")
            for label in done["words_only"] + done["not_offered"]:
                print(f"    still a question: {label}")
        if args.action == "match":
            from sqlalchemy import select

            from grocery_app import matcher as matching
            from grocery_app.api.matching import line_matcher, match_receipt
            from grocery_app.db.models import Receipt

            match = line_matcher(matching.ClaudeCodeDecider(),
                                 matching.default_shops(args.products_dir))
            totals: dict[str, int] = {}
            with factory() as session:
                for receipt in session.scalars(select(Receipt).order_by(Receipt.date,
                                                                        Receipt.id)).all():
                    counts = match_receipt(session, receipt.id, match)
                    session.commit()  # each receipt's answers stand on their own
                    for kind, n in counts.items():
                        totals[kind] = totals.get(kind, 0) + n
                    if any(counts.values()):
                        print(f"  {receipt.source_image}: {counts}", flush=True)
            print("Matched:", totals)
        if args.action == "export":
            if not args.out:
                raise SystemExit("export needs --out DIR (it will not write into data/ unasked)")
            with factory() as session:
                counts = export_data(session, args.out)
            print(f"Wrote the data/ layout to {args.out}")
            for kind, n in counts.items():
                print(f"  {kind + ':':<18}{n}")

    if args.command == "eval":
        report = evaluate(args.truth_dir, args.pred_dir, tuple(args.exclude_store))
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(format_report(report))

    if args.command == "eval-matching":
        truth = json.loads(Path(args.truth).read_text(encoding="utf-8"))
        products = load_products(args.products)
        resolution = load_resolution(args.resolution)
        shelf_prices = load_shelf_prices(args.products_dir)
        index = article_index(products, args.products_dir)
        matcher = None
        if args.matcher:
            from grocery_app import matcher as matching

            decider = matching.ClaudeCodeDecider(args.matcher_model)
            shops = matching.default_shops(args.products_dir)

            def matcher(line, receipt):
                return matching.propose(line, receipt.get("store"), products, resolution,
                                        shelf_prices, index, shops, decider)
        report = evaluate_matching(
            truth,
            load_readings(args.readings, {line["source_image"] for line in truth["lines"]}),
            resolution, products, shelf_prices, index, matcher,
        )
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(format_matching_report(report))


if __name__ == "__main__":
    main()
