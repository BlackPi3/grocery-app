from __future__ import annotations

import argparse
from pathlib import Path

from grocery_app.normalizer import normalize_purchases, save_json as save_normalized
from grocery_app.parser import load_json, parse_receipt_text, save_json as save_parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Grocery receipt parsing and normalization CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_parser = subparsers.add_parser("parse", help="Parse a raw receipt text file")
    parse_parser.add_argument("--input", required=True)
    parse_parser.add_argument("--output", required=True)

    normalize_parser = subparsers.add_parser("normalize", help="Normalize parsed receipt JSON")
    normalize_parser.add_argument("--input", required=True)
    normalize_parser.add_argument("--output", required=True)

    args = parser.parse_args()

    if args.command == "parse":
        text = Path(args.input).read_text(encoding="utf-8")
        parsed = parse_receipt_text(text)
        save_parsed(parsed, args.output)
        print(f"Wrote parsed receipt JSON to {args.output}")

    if args.command == "normalize":
        parsed = load_json(args.input)
        normalized = normalize_purchases(parsed)
        save_normalized(normalized, args.output)
        print(f"Wrote normalized purchases JSON to {args.output}")


if __name__ == "__main__":
    main()
