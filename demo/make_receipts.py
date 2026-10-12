"""Write the demo's made-up receipts to demo/receipts/*.json.

Every receipt here is invented: real shops and real products, so the app has
something true to find, but no purchase anyone made. Four months of shopping
at four chains, with a few prices that rise over the months and a few
products bought again and again, so every insight has something to show.

    python demo/make_receipts.py

Deterministic: the same file every run. The JSON is what a receipt reading
looks like (`extract.receipt_from_answer`), so `scripts/build_demo_seed.py`
can hand it to the upload path in place of the photo reader.
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).parent / "receipts"

# (printed name, price in June, price change per month, tax class), per chain.
# Tax classes as each chain prints them (`normalizer.TAX_CLASSES`).
SHOPS = {
    "GLOBUS": {
        "location": "Musterstraße 1, 66111 Saarbrücken",
        "food": "2", "other": "1",
        "products": [
            ("Weihenst. Frische Milch 3,5% 1L", 1.49, 0.02, "food"),
            ("Kerrygold Butter 250g", 2.49, 0.10, "food"),
            ("Barilla Spaghetti No.5 500g", 1.79, 0.0, "food"),
            ("Mutti Passata 500g", 1.29, 0.03, "food"),
            ("Bananen lose", 1.15, 0.0, "food"),
            ("Rispentomaten lose", 1.60, 0.08, "food"),
            ("Salatgurke St.", 0.69, 0.05, "food"),
            ("Bio Eier Freiland 10St", 3.99, 0.0, "food"),
            ("Philadelphia Original 175g", 1.99, 0.0, "food"),
            ("Dr.Oetker Ristorante Salame", 2.79, 0.0, "food"),
            ("Haribo Goldbären 175g", 1.29, 0.05, "food"),
            ("Coca-Cola 1,5L", 1.69, 0.0, "other"),
            ("Gerolsteiner Naturell 1,5L", 0.79, 0.0, "other"),
            ("Tempo Taschent. 10x10", 2.29, 0.0, "other"),
            ("Globus Toastbrot Weizen 500g", 0.99, 0.0, "food"),
            ("Ja! Haferflocken 500g", 0.89, 0.0, "food"),
        ],
    },
    "ALDI SÜD": {
        "location": "Beispielweg 5, 66113 Saarbrücken",
        "food": "A", "other": "B",
        "products": [
            ("Milsani H-Milch 1,5% 1L", 0.99, 0.02, "food"),
            ("Rispentomaten 500g", 1.49, 0.06, "food"),
            ("Bananen", 1.19, 0.0, "food"),
            ("Hähnchenbrustfilet 400g", 4.49, 0.10, "food"),
            ("Milsani Joghurt Natur 500g", 0.79, 0.0, "food"),
            ("Gouda jung Scheiben 400g", 2.79, 0.05, "food"),
            ("Moser Roth Edel-Vollmilch", 1.39, 0.0, "food"),
            ("Bio Haferflocken 500g", 0.99, 0.0, "food"),
            ("Lacura Duschgel 300ml", 0.89, 0.0, "other"),
            ("Kokett Toilettenpapier 8x", 2.99, 0.0, "other"),
        ],
    },
    "Lidl": {
        "location": "Probeplatz 3, 66117 Saarbrücken",
        "food": "A", "other": "B",
        "products": [
            ("Milbona Frische Vollmilch 1L", 1.09, 0.02, "food"),
            ("Barissimo Crema Bohnen 1kg", 12.99, 0.40, "food"),
            ("Bananen lose", 1.25, 0.0, "food"),
            ("Pilos Schmand 200g", 0.79, 0.0, "food"),
            ("Salatgurke", 0.59, 0.05, "food"),
            ("Freeway Cola 1,5L", 0.65, 0.0, "other"),
            ("Cien Zahncreme 125ml", 0.65, 0.0, "other"),
        ],
    },
    "Kaufland": {
        "location": "Testallee 9, 66119 Saarbrücken",
        "food": "B", "other": "A",
        "products": [
            ("K-Classic Spaghetti 500g", 0.79, 0.0, "food"),
            ("Kerrygold Butter 250g", 2.39, 0.08, "food"),
            ("Ritter Sport Alpenmilch 100g", 1.49, 0.05, "food"),
            ("Coca-Cola 1,5L", 1.59, 0.0, "other"),
            ("Frosch Spülmittel Zitrone", 1.19, 0.0, "other"),
        ],
    },
}

# Each chain's trips, as (first day, days between trips, trips).
TRIPS = {
    "GLOBUS": (date(2026, 6, 20), 14, 9),
    "ALDI SÜD": (date(2026, 6, 25), 21, 6),
    "Lidl": (date(2026, 7, 2), 30, 4),
    "Kaufland": (date(2026, 7, 20), 40, 2),
}
DEPOSIT = 0.25  # a 1,5 l bottle
# Ten of the trips are written (Parham, 2026-10-12: "we don't need 21, it's
# just a demo"): five at GLOBUS and three at ALDI, so prices have three
# visits or more to move over, and one each at Lidl and Kaufland.
KEEP = {"2026-06-21-globus", "2026-06-27-aldi-sued", "2026-07-04-globus", "2026-07-04-lidl",
        "2026-07-15-aldi-sued", "2026-07-18-kaufland", "2026-08-28-globus",
        "2026-09-14-globus", "2026-10-10-aldi-sued", "2026-10-10-globus"}


def price_on(base: float, per_month: float, day: date) -> float:
    months = (day.year - 2026) * 12 + day.month - 6
    return round(base + per_month * months, 2)


def receipt(shop: str, day: date, rng: random.Random) -> dict:
    spec = SHOPS[shop]
    products = spec["products"]
    # The regulars (the first three) almost every time, then a few others.
    picked = [p for p in products[:3] if rng.random() < 0.85]
    picked += rng.sample(products[3:], k=min(len(products) - 3, rng.randint(3, 7)))
    lines, buckets = [], {}
    for name, base, per_month, kind in picked:
        qty = 2 if rng.random() < 0.15 else 1
        unit = price_on(base, per_month, day)
        gross = round(unit * qty, 2)
        discount = -round(gross * 0.2, 2) if rng.random() < 0.08 else 0.0
        net = round(gross + discount, 2)
        tax_class = spec[kind]
        lines.append({"type": "product", "raw_name": name, "qty": qty, "gross": gross,
                      "discount": discount, "net": net, "tax_class": tax_class})
        rate = "7%" if kind == "food" else "19%"
        buckets[rate] = round(buckets.get(rate, 0.0) + net, 2)
        if "1,5L" in name:
            lines.append({"type": "deposit", "raw_name": "Pfand", "qty": qty,
                          "gross": DEPOSIT * qty, "discount": 0.0, "net": DEPOSIT * qty,
                          "tax_class": tax_class})
            buckets["19%"] = round(buckets.get("19%", 0.0) + DEPOSIT * qty, 2)
    total = round(sum(line["net"] for line in lines), 2)
    savings = round(-sum(line["discount"] for line in lines), 2)
    return {
        "source_image": "", "transcribed_by": "made-up", "store": shop,
        "store_location": spec["location"], "date": day.isoformat(),
        "time": f"{rng.randint(9, 19):02d}:{rng.randint(0, 59):02d}", "currency": "EUR",
        "printed_total": total, "printed_savings": savings or None, "tax_buckets": buckets,
        "lines": lines,
    }


def main() -> None:
    rng = random.Random(20261012)
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for shop, (first, every, trips) in TRIPS.items():
        for trip in range(trips):
            day = first + timedelta(days=every * trip + rng.randint(-2, 2))
            doc = receipt(shop, day, rng)
            name = f"{day.isoformat()}-{shop.lower().replace(' ', '-').replace('ü', 'ue')}"
            if name not in KEEP:
                continue  # drawn all the same, so the kept ones stay as they are
            (OUT / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
    print(f"{len(list(OUT.glob('*.json')))} receipts in {OUT}")


if __name__ == "__main__":
    main()
