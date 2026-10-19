"""Write the demo's made-up receipts to demo/receipts/*.json.

Every receipt here is invented: real shops and real products, so the app has
something true to find, but no purchase anyone made. Six months of shopping
at four chains, enough for every screen of the app to have something to show
(Parham, 2026-10-19: "sufficient receipts to show all capabilities"):

- **regulars**, bought nearly every trip, and things bought now and then;
- **prices that move** in steps, up and down, some the same product at two
  chains (same item, other shops), budget lines beside famous brands;
- **seasons**: strawberries in early summer, gingerbread from September;
- **this month against the usual one**: in the last four weeks a few new
  things come in (a dinner party, a new coffee) and a few drop out, so the
  month page has a why with every kind of reason;
- weighed fruit, discounts, deposits and a bottle return, as tills print them.

The newest receipt is dated `ANCHOR`; the demo moves every date forward at
each start so that it lands on the day of the visit (`grocery_app.demo`), so
"this month" is always the month of the visit.

    python demo/make_receipts.py

Deterministic: the same files every run. The JSON is what a receipt reading
looks like (`extract.receipt_from_answer`), so `scripts/build_demo_seed.py`
can hand it to the upload path in place of the photo reader.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).parent / "receipts"
ANCHOR = date(2026, 10, 19)  # the newest receipt; the demo moves it to the visit's day
START = ANCHOR - timedelta(weeks=26)
RECENT = ANCHOR - timedelta(days=27)  # "this month" as the demo tells it


@dataclass(frozen=True)
class Item:
    """One product as a chain's till prints it."""

    name: str
    price: float  # per pack, or per kg when weighed
    chance: float  # of being bought on a trip to this chain
    food: bool = True
    steps: tuple[tuple[date, float], ...] = ()  # (from this day, the new price)
    window: tuple[date, date] = (START, ANCHOR)  # sold, or wanted, only then
    weighed: tuple[float, float] | None = None  # kg bought, from .. to
    deposit: float = 0.0  # per unit, charged on its own line

    def price_on(self, day: date) -> float:
        price = self.price
        for since, new in self.steps:
            if day >= since:
                price = new
        return price


def d(month: int, day: int) -> date:
    return date(2026, month, day)


@dataclass(frozen=True)
class Shop:
    location: str
    food: str  # the tax class the till prints for 7 %
    other: str  # and for 19 %
    first: date
    every: int  # days between trips
    discount_chance: float
    items: tuple[Item, ...] = field(default_factory=tuple)


SHOPS = {
    "GLOBUS": Shop(
        "Musterstraße 1, 66111 Saarbrücken", "2", "1", d(4, 25), 7, 0.06, (
            Item("Weihenst. Frische Milch 3,5% 1L", 1.45, 0.9,
                 steps=((d(6, 1), 1.49), (d(8, 3), 1.55), (d(10, 1), 1.59))),
            Item("Kerrygold Butter 250g", 2.49, 0.7,
                 steps=((d(5, 18), 2.69), (d(7, 6), 2.89), (d(9, 21), 2.79))),
            Item("Barilla Spaghetti No.5 500g", 1.79, 0.45, steps=((d(8, 10), 1.99),)),
            Item("Mutti Passata 500g", 1.29, 0.4, steps=((d(7, 1), 1.39),)),
            Item("Bananen", 1.49, 0.8, weighed=(0.9, 1.4), steps=((d(9, 1), 1.69),)),
            Item("Rispentomaten", 2.99, 0.55, weighed=(0.4, 0.8),
                 steps=((d(6, 15), 2.49), (d(9, 15), 3.49))),
            Item("Salatgurke St.", 0.79, 0.5,
                 steps=((d(5, 25), 0.59), (d(9, 7), 0.89))),
            Item("Bio Eier Freiland 10St", 3.99, 0.6, steps=((d(9, 1), 4.29),)),
            Item("Philadelphia Original 175g", 1.99, 0.3),
            Item("Dr.Oetker Ristorante Salame", 2.79, 0.3, steps=((d(7, 20), 2.99),)),
            Item("Haribo Goldbären 175g", 1.29, 0.35, window=(START, RECENT)),
            Item("Coca-Cola 1,5L", 1.69, 0.45, food=False, deposit=0.25,
                 steps=((d(6, 22), 1.79),)),
            Item("Gerolsteiner Naturell 1,5L", 0.79, 0.5, food=False, deposit=0.25),
            Item("Tempo Taschent. 10x10", 2.29, 0.2, food=False),
            Item("Globus Toastbrot Weizen 500g", 0.99, 0.5, steps=((d(8, 24), 1.09),)),
            Item("Ja! Haferflocken 500g", 0.89, 0.35),
            Item("Nutella 450g", 3.49, 0.25, steps=((d(7, 27), 3.79),)),
            Item("Erdbeeren 500g", 2.99, 0.7, window=(d(5, 10), d(7, 20)),
                 steps=((d(6, 8), 2.49),)),
            Item("Lindt Excellence 70% 100g", 2.79, 0.6, window=(RECENT, ANCHOR)),
            Item("Rinderhackfleisch 500g", 5.49, 0.7, window=(RECENT, ANCHOR)),
            Item("Avocado Hass St.", 1.29, 0.6, window=(RECENT, ANCHOR)),
        )),
    "ALDI SÜD": Shop(
        "Beispielweg 5, 66113 Saarbrücken", "A", "B", d(4, 21), 10, 0.0, (
            Item("Milsani H-Milch 1,5% 1L", 0.99, 0.85, steps=((d(8, 1), 1.05),)),
            Item("Bananen", 1.19, 0.6),
            Item("Hähnchenbrustfilet 400g", 4.49, 0.6,
                 steps=((d(6, 1), 4.79), (d(9, 1), 4.99))),
            Item("Milsani Joghurt Natur 500g", 0.79, 0.6),
            Item("Gouda jung Scheiben 400g", 2.79, 0.5,
                 steps=((d(7, 1), 2.99), (d(10, 1), 2.79))),
            Item("Moser Roth Edel-Vollmilch", 1.39, 0.3),
            Item("Bio Haferflocken 500g", 0.99, 0.4),
            Item("Kokett Toilettenpapier 8x", 2.99, 0.25, food=False),
            Item("Lacura Duschgel 300ml", 0.89, 0.2, food=False, window=(START, RECENT)),
            Item("Lebkuchen Herzen 500g", 2.49, 0.6, window=(d(9, 1), ANCHOR)),
            Item("Cucina Pesto Verde 190g", 1.49, 0.35),
        )),
    "Lidl": Shop(
        "Probeplatz 3, 66117 Saarbrücken", "A", "B", d(4, 27), 21, 0.15, (
            Item("Milbona Frische Vollmilch 1L", 1.09, 0.7, steps=((d(8, 1), 1.15),)),
            Item("Barissimo Crema Bohnen 1kg", 12.99, 0.6,
                 steps=((d(6, 15), 13.99), (d(9, 1), 14.49)), window=(START, RECENT)),
            Item("Bellarom Espresso Bohnen 1kg", 11.99, 1.0, window=(RECENT, ANCHOR)),
            Item("Bananen lose", 1.25, 0.5),
            Item("Pilos Schmand 200g", 0.79, 0.4),
            Item("Salatgurke", 0.59, 0.5, steps=((d(9, 1), 0.79),)),
            Item("Nutella 450g", 3.29, 0.35, steps=((d(8, 1), 3.59),)),
            Item("Freeway Cola 1,5L", 0.65, 0.4, food=False, deposit=0.25),
            Item("Cien Zahncreme 125ml", 0.65, 0.2, food=False),
        )),
    "Kaufland": Shop(
        "Testallee 9, 66119 Saarbrücken", "B", "A", d(5, 2), 35, 0.2, (
            Item("K-Classic Spaghetti 500g", 0.79, 0.7),
            Item("Barilla Spaghetti No.5 500g", 1.69, 0.5, steps=((d(8, 1), 1.89),)),
            Item("Kerrygold Butter 250g", 2.39, 0.8, steps=((d(6, 1), 2.59), (d(9, 1), 2.69))),
            Item("Ritter Sport Alpenmilch 100g", 1.49, 0.5, steps=((d(7, 1), 1.69),)),
            Item("Coca-Cola 1,5L", 1.59, 0.6, food=False, deposit=0.25),
            Item("Frosch Spülmittel Zitrone", 1.19, 0.4, food=False),
            Item("Mutti Passata 500g", 1.19, 0.4),
        )),
}


def euros(amount: float) -> float:
    return round(amount + 0.0, 2)


def receipt(shop_name: str, day: date, rng: random.Random) -> dict:
    shop = SHOPS[shop_name]
    on_sale = [i for i in shop.items if i.window[0] <= day <= i.window[1]]
    picked = [i for i in on_sale if rng.random() < i.chance] or on_sale[:2]
    lines, buckets = [], {}

    def add(line: dict, rate: str) -> None:
        lines.append(line)
        buckets[rate] = euros(buckets.get(rate, 0.0) + line["net"])

    if rng.random() < 0.15 and any(i.deposit for i in shop.items):  # a bag of empties
        bottles = rng.randint(4, 8)
        add({"type": "deposit_return", "raw_name": "Leergut", "qty": 1,
             "net": euros(-0.25 * bottles), "tax_class": shop.other}, "19%")
    for item in picked:
        tax_class, rate = (shop.food, "7%") if item.food else (shop.other, "19%")
        unit = item.price_on(day)
        line = {"type": "product", "raw_name": item.name}
        if item.weighed:
            kg = round(rng.uniform(*item.weighed), 3)
            gross = euros(unit * kg)
            line.update(qty=1, sold_by_weight=True, weight_kg=kg, unit_price=unit,
                        unit_price_basis="kg")
            qty = 1
        else:
            qty = 2 if rng.random() < 0.15 else 1
            gross = euros(unit * qty)
            line["qty"] = qty
            if qty > 1:
                line["unit_gross"] = unit
        discount = -euros(gross * rng.choice((0.2, 0.3))) \
            if rng.random() < shop.discount_chance else 0.0
        line.update(gross=gross, discount=discount, net=euros(gross + discount),
                    tax_class=tax_class)
        add(line, rate)
        if item.deposit:
            add({"type": "deposit", "raw_name": "Pfand", "qty": qty,
                 "gross": euros(item.deposit * qty), "discount": 0.0,
                 "net": euros(item.deposit * qty), "tax_class": shop.other}, "19%")
    total = euros(sum(line["net"] for line in lines))
    savings = euros(-sum(line.get("discount", 0.0) for line in lines))
    return {
        "source_image": "", "transcribed_by": "made-up", "store": shop_name,
        "store_location": shop.location, "date": day.isoformat(),
        "time": f"{rng.randint(9, 19):02d}:{rng.randint(0, 59):02d}", "currency": "EUR",
        "printed_total": total, "printed_savings": savings or None,
        "tax_buckets": {rate: amount for rate, amount in sorted(buckets.items())},
        "lines": lines,
    }


def main() -> None:
    rng = random.Random(20261019)
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    days: dict[str, list[date]] = {}
    for name, shop in SHOPS.items():
        day = shop.first
        while day < ANCHOR:
            days.setdefault(name, []).append(day)
            day += timedelta(days=shop.every + rng.choice((-1, 0, 0, 1)))
    # The newest receipt is the anchor's: the last trip moves to it, or one is added.
    if (ANCHOR - days["GLOBUS"][-1]).days <= 3:
        days["GLOBUS"][-1] = ANCHOR
    else:
        days["GLOBUS"].append(ANCHOR)
    for name, trips in days.items():
        for day in trips:
            slug = name.lower().replace(" ", "-").replace("ü", "ue")
            path = OUT / f"{day.isoformat()}-{slug}.json"
            path.write_text(json.dumps(receipt(name, day, rng), ensure_ascii=False, indent=2)
                            + "\n", encoding="utf-8")
    print(f"{len(list(OUT.glob('*.json')))} receipts in {OUT}")


if __name__ == "__main__":
    main()
