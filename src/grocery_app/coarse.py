"""Coarse resolution: name the thing at the level the evidence supports.

Most receipt lines are not produce and not in any catalogue we hold, but they
are not mysteries either. `Chipsfrisch SalVin` is funny-frisch Chipsfrisch;
what it does not say is the flavour. `HP Skyr Drink 330` is a Milsani High
Protein Skyr Drink; what it does not say is whether it was strawberry.

The temptation is to guess the missing half, and that is the one thing this
module refuses to do. A guessed flavour is indistinguishable from a confirmed
one the moment it is written, so it can never be cleaned up; a null says
"unknown" honestly and costs nothing. Three of the four insights this project
is built on — cadence, own-brand share, personal inflation — work perfectly
well at brand-and-product-line, provided the coarse product does not straddle
a price gap. Only same-item-across-stores needs the barcode, and that arrives
when someone scans one.

So a coarse product carries what is known, leaves the rest null, and says so
in `open_questions`, which doubles as the work queue for whatever asks the
shopper later. It never carries an invented EAN: the barcode *is* the
fine-grained identity, and a made-up one would be a lie the catalog cannot
detect afterwards.

Splitting later is cheap, which is what makes all of this safe. A purchase
stores no product id — `purchases.json` is derived on every read from
`(store, raw_name) -> product_id` — so when the finer answer arrives, one
resolution entry is repointed and the whole history re-derives. No migration,
no backfill.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from grocery_app.resolver import fold, store_key

# The routes a reviewed row can carry. Only the first two name a product.
WRITES = ("search", "known")
SKIPS = {
    "produce": "handled by the produce vocabulary",
    "ask": "only the shopper can say",
    "dropped": "not remembered; deliberately unresolved",
    "nonproduct": "packaging, not a grocery",
    "outofscope": "not groceries",
}

FIELDS = ("store", "raw_name", "route", "brand", "product", "ean", "options", "your_note")


def _label(name: str, brand: str | None) -> str:
    import re
    text = f"{brand} {name}" if brand else name
    return re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")


def read_rows(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def confirm(reviewed_path: str | Path, products_path: str | Path,
            resolution_path: str | Path) -> dict[str, Any]:
    """Write reviewed coarse rows into the catalog, guessing nothing.

    One product per (brand, name) across every store: two tills printing
    `Coca-Cola 1.25L` and `Coca Cola 1,25l` resolve to the same id, which is
    the whole reason a shared catalog is worth having. A row whose
    `(store, raw_name)` is already resolved is left alone — an answer given
    once is never overwritten by a later guess.
    """
    products_doc = json.loads(Path(products_path).read_text(encoding="utf-8"))
    resolution_doc = json.loads(Path(resolution_path).read_text(encoding="utf-8"))

    by_key = {(p.get("brand"), p["name"]): pid for pid, p in products_doc["products"].items()}
    known = {(store_key(e["store"]), e["raw_name"]) for e in resolution_doc["entries"]}
    summary: dict[str, Any] = {"products": 0, "entries": 0, "skipped_known": 0,
                               "with_ean": 0, "by_route": {}}

    for row in read_rows(reviewed_path):
        route = (row.get("route") or "").strip()
        summary["by_route"][route] = summary["by_route"].get(route, 0) + 1
        if route not in WRITES:
            continue

        name = (row.get("product") or "").strip()
        if not name:
            continue
        brand = (row.get("brand") or "").strip()
        ean = (row.get("ean") or "").strip()

        questions = []
        # A trailing `?` is the reviewer saying "this is my guess", which is a
        # fact about the brand, not a brand. It goes to the queue, not the field.
        if brand.endswith("?"):
            questions.append(f"brand uncertain: {brand.rstrip('?')}")
            brand = ""
        if not ean:
            questions.append("variant unknown")
        # A packaged good always has a brand on the box. Reaching here without
        # one means nobody read it, not that there is none — and the difference
        # matters, because the first is a gap worth closing and the second is a
        # final answer. Produce mints its kinds elsewhere and says nothing here,
        # which is right: no barcode exists, so nothing will ever supply one.
        if not brand and not any(q.startswith("brand ") for q in questions):
            # `brand uncertain: X` already says this and says more, so it wins.
            questions.append("brand unknown")

        if (store_key(row["store"]), row["raw_name"]) in known:
            summary["skipped_known"] += 1
            continue

        key = (brand or None, name)
        product_id = by_key.get(key)
        if product_id is None:
            product_id = f"p-{products_doc['meta']['next_id']:04d}"
            products_doc["meta"]["next_id"] += 1
            products_doc["products"][product_id] = {
                "label": _label(name, brand or None),
                "name": name,
                "brand": brand or None,
                "product_line": None,
                # Left null on purpose: see the module docstring.
                "variant": None,
                "size": {"count": 1, "value": None, "unit": None},
                "category": None,
                "is_organic": None,
                "is_own_brand": None,
                "eans": [ean] if ean else [],
                "open_questions": questions,
                "provenance": {"attributes": "coarse-resolution",
                               "source": str(reviewed_path)},
            }
            by_key[key] = product_id
            summary["products"] += 1
            if ean:
                summary["with_ean"] += 1

        resolution_doc["entries"].append({
            "store": row["store"],
            "raw_name": row["raw_name"],
            "line_type": "product",
            "product_id": product_id,
            "confirmed_by": "coarse-resolution",
            "confirmed_at": date.today().isoformat(),
            "source": str(reviewed_path),
        })
        known.add((store_key(row["store"]), row["raw_name"]))
        summary["entries"] += 1

    Path(products_path).write_text(
        json.dumps(products_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(resolution_path).write_text(
        json.dumps(resolution_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


# --- propose -----------------------------------------------------------------
#
# The other half of the loop. Until this existed the CSV that `confirm` reads
# was produced by hand, which is the thing this module exists to stop: 88% of
# printed names across the receipts so far appear exactly once, so a per-name
# manual pass grows with the shopping, forever.
#
# Two mechanisms, both dull on purpose and both only ever a proposal.

# What a till writes instead of the word. These are conventions, not guesses:
# a German receipt abbreviates the same way every time, and the expansion is
# what turns an unsearchable string into a product name. Anything genuinely
# uncertain belongs in `open_questions`, not here.
ABBREVIATIONS: dict[str, str] = {
    "wsp": "Weichspüler",
    "hp": "High Protein",
    "tk": "tiefgekühlt",
    "gr art": "griechischer Art",
    "bodenh": "Bodenhaltung",
    "okt": "10er",
    "stufu": "Studentenfutter",
    "salvin": "Salt & Vinegar",
    "meg": "Megaperls",
    "dis": "Discs",
    "konf": "Konfitüre",
    "lasagnebl": "Lasagneblätter",
    "reibek": "Reibekäse",
    "frischkaese": "Frischkäse",
    "gewuerzgurk": "Gewürzgurken",
    "heumil": "Heumilch",
    "geh": "gehackte",
    "ungesalz": "ungesalzen",
    "schokolinse": "Schokolinsen",
    "voll": "Vollmilch",
    "alp": "Alpen",
    "choco": "Chocolate",
    "wild": "Wildberry",
    "ger": "gerieben",
    "kl": "Klasse",
}

# Own-brand prefixes a chain glues onto its own lines. They identify the brand
# rather than the product, so they come off the name and go into `brand`.
# Each of these is evidenced by a line in the receipts, not inferred from the
# letters: `KLC Geh. Tomaten` and `KBio Babyspinat` at Kaufland, `BB Heumil
# 3.8% 1L` at ALDI SÜD whose listing is `bio-bio-h-vollmilch`. A prefix with
# no receipt behind it does not belong here — it would write a brand nobody
# can check.
OWN_BRAND_PREFIXES: dict[str, str] = {
    "klc": "K-Classic",   # Kaufland Classic
    "kbio": "K-Bio",      # Kaufland's organic line
    "bb": "BIO BIO",      # ALDI SÜD's organic line
}

_NOISE = {"lose", "stk", "st", "stueck", "kg", "g", "ml", "l", "je", "pro", "ca"}
_QUANTITY = re.compile(r"\d+([.,]\d+)?(kg|g|ml|l|er|x\d+)?")


def _flatten(text: str) -> str:
    """Folded and stripped of punctuation, so `Coca Cola` meets `Coca-Cola`."""
    return re.sub(r"[^a-z0-9]+", "", fold(text))


def _tokens(raw_name: str) -> list[str]:
    text = re.sub(r"[^0-9A-Za-zÄÖÜäöüß&/ .,-]+", " ", raw_name)
    return [t for t in re.split(r"[ .,/]+", text) if t]


def without(name: str, brand: str) -> str:
    """The product name with the brand taken out of it.

    `Persil Meg/Gel/Dis` gives brand Persil and product Megaperls Gel Discs;
    repeating the brand inside the name only makes the catalog read worse.
    """
    if not brand:
        return name
    drop = {_flatten(part) for part in brand.split() if part}
    kept = [t for t in name.split() if _flatten(t) not in drop]
    return " ".join(kept) or name


def brand_in(raw_name: str, brands: list[str]) -> str:
    """The brand, when the till printed it — which it very often does.

    `Dove Dusche` says Dove. `Lenor WSP Basis 71` says Lenor. Looking before
    guessing is free and it is the single cheapest resolution step there is;
    missing it once sent a row to a human that the line had already answered.
    """
    folded = _flatten(raw_name)
    hits = [b for b in brands if b and _flatten(b) in folded]
    # Longest wins: `BIO BIO` beats `BIO` when a line carries both.
    return max(hits, key=len) if hits else ""


def expand(raw_name: str) -> tuple[str, str]:
    """A till line as a searchable product name, plus any own-brand prefix.

    Returns `(brand, name)`. Quantities and packaging words are dropped, an
    own-brand prefix becomes the brand, and known abbreviations are written
    out. Nothing is invented: a token this does not recognise is kept as it
    was printed.
    """
    brand = ""
    tokens = _tokens(raw_name)

    # A multi-word abbreviation is matched before the words are split up, and
    # spliced back in place so the surrounding words keep the case they were
    # printed in.
    for short, long in ABBREVIATIONS.items():
        parts = short.split()
        if len(parts) < 2:
            continue
        for i in range(len(tokens) - len(parts) + 1):
            if [fold(t) for t in tokens[i:i + len(parts)]] == parts:
                tokens[i:i + len(parts)] = long.split()

    out: list[str] = []
    for i, token in enumerate(tokens):
        key = fold(token).strip("-")
        if i == 0 and key in OWN_BRAND_PREFIXES:
            brand = OWN_BRAND_PREFIXES[key]
            continue
        if key in _NOISE or _QUANTITY.fullmatch(key):
            continue
        out.append(ABBREVIATIONS.get(key, token))
    return brand, " ".join(out).strip()


def propose(purchases_doc: dict[str, Any], products_doc: dict[str, Any],
            previous: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """A reviewable coarse row per unresolved line, richest names first.

    `previous` carries a reviewer's decisions forward, and a decision survives
    only while the proposal it was made against is unchanged — the same rule
    the produce loop uses, for the same reason.
    """
    from grocery_app.produce import unresolved_names

    brands = sorted({p["brand"] for p in products_doc["products"].values() if p.get("brand")},
                    key=len, reverse=True)
    brands += [b for b in OWN_BRAND_PREFIXES.values() if b not in brands]
    kept = {(r["store"], r["raw_name"]): r for r in (previous or [])}

    rows = []
    for (store, raw_name), weight in unresolved_names(purchases_doc).items():
        prefix_brand, name = expand(raw_name)
        brand = brand_in(raw_name, brands) or prefix_brand
        name = without(name, brand)
        before = kept.get((store, raw_name))
        carried = before or {}
        same = carried.get("brand") == brand and carried.get("product") == name
        rows.append({
            "store": store,
            "raw_name": raw_name,
            # `route` says what kind of line this is — a bag is a bag however
            # the name was expanded — so unlike the naming below it survives a
            # changed proposal. Re-asking a settled question is the one thing
            # this loop exists to avoid.
            "route": carried.get("route") or "search",
            "brand": brand,
            "product": carried.get("product", name) if same else name,
            # An EAN is the fine-grained identity and is never proposed; it is
            # filled in only by a scan or a reviewer who checked one.
            "ean": carried.get("ean", "") if same else "",
            "options": "",
            "your_note": carried.get("your_note", "") if same else "",
            "lines": weight["lines"],
            "spend": f"{weight['spend']:.2f}",
        })
    rows.sort(key=lambda r: (not r["brand"], -float(r["spend"]), r["raw_name"]))
    return rows


def write_proposals(rows: list[dict[str, Any]], path: str | Path) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(FIELDS) + ["lines", "spend"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
