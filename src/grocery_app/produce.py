"""Produce: the part of the basket with no barcode.

Packaged goods can be identified from outside this project — an EAN, an
article number, an online catalogue. Loose produce cannot. No barcode, no
article number, no brand: a cucumber is printed as `Gurke Stk` at one till and
`Salatgurken St` at another, and nothing on the internet will ever join those
two strings for you.

The flip side is what this module is built on: **produce is generic**. A
cucumber is the same cucumber in every shop, which makes cross-store
comparison easier for produce than for anything else — comparing two shops'
own-brand chocolate is meaningless, comparing their cucumbers is not. So one
vocabulary entry resolves a name at every store at once, where catalogue work
resolves one name at one store.

A `kind` is therefore not a SKU. It is what the thing *is*. Kinds become
ordinary catalog products (`brand: null`, `eans: []`, `category: "Produce"`),
so nothing downstream needs a second notion of a product.

The vocabulary starts coarse on purpose — `Tomaten`, not `Rispentomaten` —
because splitting it later is cheap: purchases are derived on every read, so
minting two products and editing resolution entries re-resolves the whole
history with no migration. The finer split, when it comes, is the `variant`
field and the family mechanism that already handles `Dove Dusche`.

Nothing here decides anything. `match` proposes, a human confirms.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from grocery_app.resolver import fold, store_key

# Canonical kind -> the folded surface forms tills print for it. Aliases are
# written folded (lower case, umlauts expanded) because that is what `match`
# compares against; see `normalise`.
VOCABULARY: dict[str, tuple[str, ...]] = {
    # --- vegetables ---
    "Gurken": ("gurke", "gurken", "salatgurke", "salatgurken"),
    "Mini-Gurken": ("mini gurken", "minigurken", "snack gurken", "snackgurken"),
    "Tomaten": ("tomate", "tomaten", "rispentomaten", "datteltomaten", "romatomaten",
                "cherrytomaten", "strauchtomaten", "kirschtomaten"),
    "Paprika": ("paprika", "paprika rot", "paprika gelb", "paprika gruen", "paprika mix"),
    "Zucchini": ("zucchini",),
    "Zwiebeln": ("zwiebel", "zwiebeln", "speisezwiebeln", "zwiebeln rot", "zwiebeln gelb"),
    "Lauchzwiebeln": ("lauchzwiebel", "lauchzwiebeln", "fruehlingszwiebeln"),
    "Porree": ("porree", "lauch"),
    "Möhren": ("moehren", "moehre", "karotten", "karotte", "mini moehren", "babymoehren"),
    "Radieschen": ("radieschen",),
    "Babyspinat": ("babyspinat", "baby spinat"),
    "Salatherzen": ("salatherzen", "salatherz"),
    "Kartoffeln": ("kartoffel", "kartoffeln", "speisekartoffeln", "drillinge"),
    "Champignons": ("champignons", "champignon"),
    # --- fruit ---
    "Bananen": ("banane", "bananen"),
    "Äpfel": ("apfel", "aepfel"),
    "Birnen": ("birne", "birnen", "birneconference", "conference"),
    "Trauben": ("trauben", "weintrauben", "trauben mix"),
    "Heidelbeeren": ("heidelbeeren", "blaubeeren"),
    "Johannisbeeren": ("johannisbeeren", "johannisbeer"),
    "Erdbeeren": ("erdbeeren",),
    "Himbeeren": ("himbeeren",),
    "Kiwi": ("kiwi", "kiwi gruen", "kiwis"),
    "Limetten": ("limette", "limetten"),
    "Zitronen": ("zitrone", "zitronen"),
    "Orangen": ("orange", "orangen"),
    "Nektarinen": ("nektarine", "nektarinen"),
    "Plattpfirsiche": ("plattpfirsiche", "plattpfirsich", "weinbergpfirsiche"),
    "Wassermelone": ("wassermelone", "babywassermelone", "melone"),
    "Physalis": ("physalis",),
    "Avocado": ("avocado", "avocados"),
    # --- fresh herbs, sold by the bunch ---
    "Schnittkräuter": ("schnittkraeuter",),
    "Dill": ("dill",),
    "Minze": ("minze",),
    "Petersilie": ("petersilie",),
    "Basilikum": ("basilikum",),
}

# A name that says the shopper chose the organic version. `bioft` is Bio
# Fairtrade and `kbio` is a chain's own organic line: both are markers, not
# words about the vegetable.
ORGANIC_MARKERS = ("bio", "oeko", "demeter", "bioft", "kbio", "naturkind")

# Tokens that say how a thing was sold, not what it is.
PACKAGING = (
    "lose", "stk", "stueck", "st", "stueckpreis", "kg", "g", "bund", "netz", "schale",
    "beutel", "pack", "packung", "ca", "je", "pro", "frisch", "klasse", "kl",
    "deutschland", "import",
)

# Words that mean the fruit was processed into something else. Checked as
# substrings, because tills glue them on (`Orangendirektsaft`). They only veto
# a *prefix* guess: an explicit alias is a decision someone already made, and
# `Saftorangen` — oranges for juicing — is real produce that would be caught
# here, so it would be added as an alias rather than matched by prefix.
# Kept deliberately short: a substring that can hide inside a vegetable is
# worse than a miss. `eis` was here and vetoed `Speisezwiebeln`.
PROCESSED = ("saft", "nektar", "konfit", "marmelade", "getrocknet", "konserve",
             "sirup", "joghurt", "quark")

# "500g", "1kg", "4stk", "2er", "650" — a quantity, never an identity.
_QUANTITY = re.compile(r"^\d+([.,]\d+)?(kg|g|ml|l|stk|st|er|x\d+)?$")
_SPLIT_DIGITS = re.compile(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])")
_MIN_PREFIX = 5


@dataclass(frozen=True)
class Match:
    kind: str
    is_organic: bool
    how: str  # "alias" | "prefix"

    @property
    def product_name(self) -> str:
        return f"{self.kind} Bio" if self.is_organic else self.kind


def _tokens(raw_name: str) -> list[str]:
    text = fold(raw_name)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    # `BirneConference1kg` arrives as one word; split where letters meet digits.
    return [part for token in text.split() for part in _SPLIT_DIGITS.split(token) if part]


def is_organic(raw_name: str) -> bool:
    """True when the printed name says organic, glued or not (`KBio`, `Bio-Mini`)."""
    tokens = _tokens(raw_name)
    return any(token in ORGANIC_MARKERS or
               (token.startswith("bio") and len(token) > 3 and token not in VOCABULARY)
               for token in tokens)


def normalise(raw_name: str) -> str:
    """What is left of a printed name once quantity, packaging and Bio are gone.

    `Bio-Mini Möh. 200g` -> `mini moeh`; `Paprika rot lose` -> `paprika rot`.
    The result is deliberately not a word: it is a comparison key.
    """
    kept = []
    for token in _tokens(raw_name):
        if token in ORGANIC_MARKERS or token in PACKAGING or _QUANTITY.match(token):
            continue
        if token.startswith("bio") and len(token) > 3:
            token = token[3:]  # `biobabywasserme`, `biogurken`
        if token:
            kept.append(token)
    return " ".join(kept)


_INDEX: dict[str, str] = {alias: kind for kind, aliases in VOCABULARY.items()
                          for alias in aliases}


def match(raw_name: str) -> Match | None:
    """Propose a kind for a printed name, or nothing.

    Two passes. An exact alias hit is the confident case. Failing that, a
    two-way prefix: tills truncate (`Johannisbeer`, `BioBabyWasserme`) and
    qualify (`mini moehren` for `Mini Möh.`), so either string may be the start
    of the other. Both are only ever proposals — `produce propose` writes them
    into a CSV a human decides on.
    """
    key = normalise(raw_name)
    if not key:
        return None
    organic = is_organic(raw_name)
    if key in _INDEX:
        return Match(_INDEX[key], organic, "alias")
    if any(word in key for word in PROCESSED):
        return None
    for alias, kind in _INDEX.items():
        if len(key) >= _MIN_PREFIX and len(alias) >= _MIN_PREFIX and \
                (key.startswith(alias) or alias.startswith(key)):
            return Match(kind, organic, "prefix")
    return None


def near_misses(raw_name: str, limit: int = 3) -> list[str]:
    """Kinds worth showing a reviewer when nothing matched."""
    import difflib

    key = normalise(raw_name)
    if not key:
        return []
    close = difflib.get_close_matches(key, list(_INDEX), n=limit, cutoff=0.6)
    seen: list[str] = []
    for alias in close:
        if _INDEX[alias] not in seen:
            seen.append(_INDEX[alias])
    return seen


# --- propose / confirm -------------------------------------------------------
#
# The same loop as the store catalogues: a machine proposes, a human decides in
# a CSV, and only marked rows are written. Produce needs its own pair because
# `resolver.confirm` is built around article numbers and catalogue URLs, and a
# cucumber has neither.

PROPOSAL_FIELDS = ("decision", "store", "raw_name", "lines", "spend", "kind",
                   "organic", "confidence", "alternatives")


def unresolved_names(purchases_doc: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """Every (store, printed name) the normalizer could not place, with its weight.

    Weight matters for review order: a name on nine lines is worth more of the
    reviewer's attention than one on a single line.
    """
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for purchase in purchases_doc.get("purchases", []):
        if purchase.get("type") != "product" or purchase.get("resolved"):
            continue
        key = (purchase.get("store") or "", purchase["raw_name"])
        entry = found.setdefault(key, {"lines": 0, "spend": 0.0})
        entry["lines"] += 1
        entry["spend"] = round(entry["spend"] + (purchase.get("net_paid") or 0.0), 2)
    return found


def propose(purchases_doc: dict[str, Any]) -> list[dict[str, Any]]:
    """A review row per unresolved name the vocabulary has an opinion about.

    Names it cannot place are included with an empty `kind` and whatever near
    misses there are, because "nothing matched" is information: it is how the
    vocabulary learns what it is missing.
    """
    rows = []
    for (store, raw_name), weight in unresolved_names(purchases_doc).items():
        found = match(raw_name)
        rows.append({
            "decision": "",
            "store": store,
            "raw_name": raw_name,
            "lines": weight["lines"],
            "spend": f"{weight['spend']:.2f}",
            "kind": found.product_name if found else "",
            "organic": "y" if found and found.is_organic else "",
            "confidence": found.how if found else "",
            "alternatives": ", ".join(near_misses(raw_name)) if not found else "",
        })
    # Best guesses first, then by how much of the basket rides on the name.
    rows.sort(key=lambda r: (r["confidence"] != "alias", r["confidence"] != "prefix",
                             -float(r["spend"]), r["raw_name"]))
    return rows


def write_proposals(rows: list[dict[str, Any]], path: str | Path) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROPOSAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _label(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(name)).strip("-")


def confirm(reviewed_path: str | Path, products_path: str | Path,
            resolution_path: str | Path) -> dict[str, Any]:
    """Write the rows a human marked into products and resolution.

    `decision` is `y` to accept the proposed kind, `n` to reject it, or the
    name of a kind to use instead — typing `Kartoffeln` over a wrong guess is
    the fastest correction there is, and a name the vocabulary has never heard
    of is allowed and reported, because that is a vocabulary gap the reviewer
    has just found.

    A kind earns a product id the first time it is accepted, and every store
    that prints a name for it resolves to that same one id. That is the whole
    point: one entry, every shop.
    """
    products_doc = json.loads(Path(products_path).read_text(encoding="utf-8"))
    resolution_doc = json.loads(Path(resolution_path).read_text(encoding="utf-8"))

    by_name = {p["name"]: pid for pid, p in products_doc["products"].items()
               if p.get("category") == "Produce"}
    known = {(store_key(e["store"]), e["raw_name"]) for e in resolution_doc["entries"]}
    summary = {"products": 0, "entries": 0, "rejected": 0, "skipped": 0,
               "new_kinds": [], "undecided": 0}

    with Path(reviewed_path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        decision = (row.get("decision") or "").strip()
        if not decision:
            summary["undecided"] += 1
            continue
        if decision.lower() == "n":
            summary["rejected"] += 1
            continue

        name = row["kind"].strip() if decision.lower() == "y" else decision
        if not name:
            summary["undecided"] += 1
            continue
        if decision.lower() != "y" and name not in VOCABULARY and \
                name.removesuffix(" Bio") not in VOCABULARY:
            summary["new_kinds"].append(name)

        if (store_key(row["store"]), row["raw_name"]) in known:
            summary["skipped"] += 1
            continue

        product_id = by_name.get(name)
        if product_id is None:
            product_id = f"p-{products_doc['meta']['next_id']:04d}"
            products_doc["meta"]["next_id"] += 1
            products_doc["products"][product_id] = {
                "label": _label(name),
                # The name carries "Bio" because a person reads it; `is_organic`
                # carries it because a machine does.
                "name": name,
                "brand": None,
                "product_line": None,
                "variant": None,
                "size": None,
                "category": "Produce",
                "is_organic": name.endswith(" Bio") or (row.get("organic") or "") == "y",
                "is_own_brand": None,
                "eans": [],
                "open_questions": [],
                "provenance": {"attributes": "produce-vocabulary", "source": "hand"},
            }
            by_name[name] = product_id
            summary["products"] += 1

        resolution_doc["entries"].append({
            "store": row["store"],
            "raw_name": row["raw_name"],
            "line_type": "product",
            "product_id": product_id,
            "confirmed_by": "produce-vocabulary",
            "confirmed_at": date.today().isoformat(),
            "source": "produce-vocabulary",
        })
        known.add((store_key(row["store"]), row["raw_name"]))
        summary["entries"] += 1

    Path(products_path).write_text(
        json.dumps(products_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(resolution_path).write_text(
        json.dumps(resolution_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
