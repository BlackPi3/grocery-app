from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CANONICAL_MAP = {
    "MILCH H 1,5%": "Milk 1.5%",
    "MILCH 3,5%": "Milk 3.5%",
    "Brot": "Bread",
    "Kaffee Bohnen": "Coffee beans",
    "Butter": "Butter",
    "Olivenöl": "Olive oil",
    "Ei": "Eggs",
}


def normalize_purchases(parsed_data: dict[str, Any]) -> dict[str, Any]:
    purchases = []
    for item in parsed_data.get("items", []):
        raw_name = item["name"]
        canonical_name = CANONICAL_MAP.get(raw_name, raw_name)
        purchases.append(
            {
                "raw_name": raw_name,
                "canonical_name": canonical_name,
                "price": item["price"],
                "date": parsed_data.get("date", ""),
                "store": parsed_data.get("store", "Unknown store"),
                "category": classify_category(canonical_name),
            }
        )

    return {
        "store": parsed_data.get("store", "Unknown store"),
        "date": parsed_data.get("date", ""),
        "purchases": purchases,
        "summary": {
            "item_count": len(purchases),
            "estimated_total": round(sum(item["price"] for item in purchases), 2),
            "top_categories": summarize_categories(purchases),
        },
    }


def classify_category(canonical_name: str) -> str:
    lowered = canonical_name.lower()
    if "milk" in lowered or "egg" in lowered:
        return "Dairy"
    if "coffee" in lowered or "bread" in lowered:
        return "Pantry"
    if "butter" in lowered or "olive" in lowered:
        return "Cooking"
    return "Other"


def summarize_categories(purchases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in purchases:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    return [{"category": category, "count": count} for category, count in sorted(counts.items())]


def save_json(data: dict[str, Any], output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
