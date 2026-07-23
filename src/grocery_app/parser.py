from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def parse_receipt_text(text: str) -> dict[str, Any]:
    """Create a simple parsed receipt structure from raw text.

    This is a lightweight baseline for the portfolio scaffold.
    It intentionally favors transparency over polished OCR output.
    """

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    store_name = lines[0] if lines else "Unknown store"
    date = ""
    items: list[dict[str, Any]] = []

    for line in lines:
        if re.search(r"\d{4}-\d{2}-\d{2}", line):
            date = re.search(r"\d{4}-\d{2}-\d{2}", line).group(0)
            break

    for line in lines:
        if line.startswith("SUMME"):
            continue
        if line.startswith("MwSt"):
            continue
        if line.startswith("BEZAHL"):
            continue
        if line.startswith("REWE"):
            continue
        if re.match(r"^\d{4}-\d{2}-\d{2}$", line):
            continue

        price_match = re.search(r"(\d+),(\d{2})", line)
        if not price_match:
            continue

        price = float(f"{price_match.group(1)}.{price_match.group(2)}")
        name = line[: price_match.start()].strip(" -")
        if not name:
            continue

        items.append({"name": name, "price": round(price, 2)})

    total = round(sum(item["price"] for item in items), 2)
    return {
        "store": store_name,
        "date": date,
        "items": items,
        "total": total,
        "confidence": 0.72,
    }


def save_json(data: dict[str, Any], output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
