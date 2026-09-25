"""Proposing a category for a product, and banking the answers a human gave.

`categories.py` holds the vocabulary — the closed list of things a shopping
list can say. This module is how a product gets attached to one of them. It
decides nothing on its own; it reads evidence, says what the evidence is, and
writes only what came back reviewed, the same shape as `produce.py` and the
catalogue loop.

**Three sources, and they are not equally good.**

1. *The shop's own filing.* 47 of the catalog's products were matched against
   a GLOBUS listing, and the listing URL carries the shop's three-level path:
   `milchprodukte-eier/kaese/reibekaese/4306188407508/mozzarella-gerieben`.
   That is not a guess. Somebody at the shop put that article on that shelf,
   and `SHOP_PATHS` below is the only work left — mapping their tree onto ours,
   28 entries for the whole catalog.
2. *Open Food Facts.* A taxonomy chain per barcode, already cached for 29
   products by `enrich`. Crowd-sourced and too fine at the leaf, so it is read
   rightmost-first against the vocabulary's aliases and used as a cross-check.
3. *The printed name.* Reaches nearly everything and is wrong about one product
   in twenty-five, always the same way: a flavour or an ingredient word beats
   the head noun. `Linsen Chips Paprika` is not paprika, `Eis, Schokolade` is
   not chocolate, `Mozzarella, gerieben` is not a soft cheese but grated
   cheese. A cleverer matcher does not fix this — "rightmost noun wins" would
   repair the first and break the second.

So the rule is: **a name alone is a question, two independent sources agreeing
is an answer.** Where the shop's shelf and the product's name say the same
thing, nothing is asked. Where they disagree, that row is the most interesting
one in the file and goes to the top of it. Where only the name speaks, the
reviewer reads it. This is what keeps the migration honest without routing
Coca-Cola to a human.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from grocery_app import categories
from grocery_app.resolver import fold

# --- the retailers' trees, mapped onto ours ----------------------------------
# Key: the last two slugs of a GLOBUS category path, which is as much as is
# needed to be unique and survives the chain re-parenting a section.
# Value: a category key, or `@section` where the shop's shelf is wider than one
# of our categories and only the name can say which.
#
# `konserven-feinkost/gemuesekonserven` is the example worth reading: GLOBUS
# files Kühne's Salz-Dill-Gurken under vegetable conserves, and our vocabulary
# separates `essiggemuese` from `gemuesekonserven` because a jar of pickles and
# a tin of chopped tomatoes are different lines on a shopping list. The shop
# narrows it to a section; the name finishes the job.
SHOP_PATHS: dict[str, str] = {
    # Brot, Aufstriche & Cerealien
    "aufstriche/fruchtaufstriche": "marmelade",
    "aufstriche/honig-sirup": "honig",
    "backzutaten/nuesse-zum-backen": "nuesse",
    "kaffee/kaffeesahne-kondensmilch": "sahne",
    "meisterbaeckerei/brot-broetchen": "@backwaren",
    "muesli/dinkel-getreide-haferflocken": "muesli",
    # Fleisch & Wurst
    "fleisch/gefluegel": "gefluegel",
    "wurst-aufschnitt/kochschinken-braten": "schinken",
    "wurst-aufschnitt/salami-paprikawurst": "salami",
    # Getränke
    "wein/rotwein": "rotwein",
    # Drogerie
    "hygieneartikel/kosmetik-taschentuecher": "taschentuecher",
    "koerperpflege/deodorants": "deo",
    "koerperpflege/duschgel": "duschgel",
    # Haushalt
    "reinigungsmittel/kuechenreiniger": "putzmittel",
    "kuechenzubehoer/beutel-folien": "folien-beutel",
    "kuechenzubehoer/kuechenrollen": "kuechenrolle",
    "reinigungsmittel/reinigungszubehoer": "@haushaltshelfer",
    # Molkerei
    "milchprodukte-eier/eier": "eier-kat",
    "kaese/kaesescheiben": "@kaese",
    "kaese/reibekaese": "reibekaese",
    "milchprodukte-eier/laktosefrei": "@milch-joghurt",
    "milch-molkereiprodukte/quark": "quark",
    "milch-molkereiprodukte/sahne": "sahne",
    # Konserven
    "konserven-feinkost/gemuesekonserven": "@konserven-glas",
    "konserven-feinkost/obstkonserven": "obstkonserven",
    # Nudeln, Öl & Soßen
    "nudeln-reis-getreide/nudeln-pasta": "nudeln",
    "essig-oel-gewuerze-sossen/oele": "oel-essig",
    "sossen-gewuerze/sossen-bindemittel": "@gewuerze-oele",
    # Obst & Gemüse
    "frisches-gemuese/tomaten": "tomaten",
    "frisches-obst/exotisches-obst": "exotisches-obst",
    "trockenobst-nuesse-kerne/trockenobst": "@nuesse-trockenobst",
    # Süßes & Salziges
    "gebaeck/waffelgebaeck": "waffeln",
    "schokolade/sonstige-schokoladenartikel": "schokolade",
    "schokolade/tafelschokolade": "schokolade",
    "snacks-knabberzeug/chips": "chips",
    "suessigkeiten/kaugummi": "bonbons",
    # Tiefkühlung
    "eis/eis-desserts": "speiseeis",
    "eis/eis-grosspackungen": "speiseeis",
}

# A short alias has to be a whole word; a long one may sit inside one. German
# glues nouns together — `Kartoffelchips`, `Vollkornbrötchen` — so a substring
# is how most of the catalog is reached at all. It is also how `eis` once
# vetoed `Speisezwiebeln` in `produce.py`, and `oil` would hide in `boiled`.
# Five characters is where the two stop fighting on this data.
_GLUED = 5

def _alias_index() -> dict[str, str]:
    """Every written form the vocabulary knows, folded, pointing at its key.

    The label and the key join the aliases because both are words somebody
    might type into a review file, and `categories.problems()` already refuses
    an alias claimed by two categories, so first-one-wins cannot hide a clash.
    """
    index: dict[str, str] = {}
    for key, (label, _section, aliases) in categories.CATEGORIES.items():
        for alias in (*aliases, label, key):
            index.setdefault(fold(alias), key)
    return index


_ALIASES = _alias_index()


@dataclass(frozen=True)
class Proposal:
    """One product's category, with the evidence that produced it in the open."""

    key: str | None = None
    how: str = ""
    alternatives: tuple[str, ...] = field(default_factory=tuple)
    settled: bool = False

    @property
    def path(self) -> str:
        return " / ".join(categories.path(self.key)) if self.key else ""


def _text(product: dict[str, Any]) -> str:
    """The words that say what a product *is*.

    `variant` is deliberately left out. It is the flavour — which one it was,
    not what it is — and reading it is how `Lay's Potato chips` in
    `Kräuterbutter` proposes butter, `Potato chips Peperoni` proposes chilli
    peppers and `Somat 5in1 Deo Perls` proposes deodorant. One field, one job:
    the head noun lives in `name`.
    """
    parts = (product.get("brand"), product.get("name"), product.get("product_line"))
    return fold(" ".join(p for p in parts if p))


def _words(text: str) -> set[str]:
    return set(re.split(r"[^a-z0-9]+", text)) - {""}


def name_hits(product: dict[str, Any], section: str | None = None) -> list[str]:
    """Categories the product's own words point at, best first.

    Best means the longest alias that matched, and on a tie the leftmost:
    `kartoffelchips` beats `chips`, and `Börek Stange Spinat` is a Börek
    because that word comes first. The tie-break is there to make the answer
    the same every run, not because it is clever — the moment two categories
    match at all the row stops being an answer and becomes a question.
    """
    text = _text(product)
    words = _words(text)
    found: list[tuple[int, int, str]] = []
    for alias, key in _ALIASES.items():
        if section and categories.CATEGORIES[key][1] != section:
            continue
        glued = len(alias) >= _GLUED or " " in alias
        where = text.find(alias) if glued else (
            text.find(alias) if alias in words else -1)
        if where >= 0:
            found.append((-len(alias), where, key))
    ranked: list[str] = []
    for _, _, key in sorted(found):
        if key not in ranked:
            ranked.append(key)
    return ranked


def off_hits(product: dict[str, Any]) -> list[str]:
    """Categories the Open Food Facts chain points at, most specific first.

    The chain runs general to specific (`plant based foods -> cereals ->
    flakes`), so it is read backwards and the first term the vocabulary
    recognises wins. The leaf on its own is unusable — it is where `chia`,
    `cut` and `stuffed wafers` came from.
    """
    chain = (product.get("enrichment") or {}).get("categories") or []
    found: list[str] = []
    for term in reversed(chain):
        key = _ALIASES.get(fold(term))
        if key and key not in found:
            found.append(key)
    return found


def shop_hint(product_id: str, product: dict[str, Any],
              listings: dict[str, Any] | None = None) -> str | None:
    """What the shop's own shelf says: a category key, `@section`, or nothing.

    Two places record the same fact — `listings.json` for products matched
    through the catalogue loop, and `provenance.source` for the ones confirmed
    from a product page by hand. Both are a URL and the URL is the shelf.
    """
    url = ((listings or {}).get(product_id) or {}).get("url") \
        or (product.get("provenance") or {}).get("source") or ""
    if not url.startswith("http") or "globus.de" not in url:
        return None
    parts = [part for part in url.split("globus.de/", 1)[1].split("/") if part]
    # A product page is served under a branch slug (`/dudweiler/…`); a listing
    # page is not. Either way the last two segments are the article number and
    # its name-slug, and the two before them are the shelf.
    parts = parts[:-2]
    return SHOP_PATHS.get("/".join(parts[-2:]))


def propose(product_id: str, product: dict[str, Any],
            listings: dict[str, Any] | None = None) -> Proposal:
    """Read the evidence for one product and say what it supports.

    `how` is the whole point of the return value: it names the source, so a
    reviewer knows whether to read the row or trust it.
    """
    hint = shop_hint(product_id, product, listings)

    if hint and not hint.startswith("@"):
        names = name_hits(product)
        if not names:
            return Proposal(hint, "shop", (), settled=True)
        if names[0] == hint or hint in names[:2]:
            return Proposal(hint, "agreed", (), settled=True)
        # The shop put it on a shelf and the name says another. One of the two
        # is wrong and no rule here can say which — this is the row a person is
        # for. `Hähnchenbrustfilet, Natur` under cold cuts is the shop being
        # right; `Cheese Cracker` filed with the crisps may be the shop being
        # coarse.
        return Proposal(hint, "conflict", tuple(names), settled=False)

    if hint:
        section = hint[1:]
        names = name_hits(product, section=section)
        if len(names) == 1:
            return Proposal(names[0], "shop+name", (), settled=True)
        inside = tuple(key for key, (_, sec, _) in categories.CATEGORIES.items()
                       if sec == section)
        return Proposal(names[0] if names else None, "section", names[1:] or inside)

    names, off = name_hits(product), off_hits(product)
    if names and off and names[0] == off[0]:
        return Proposal(names[0], "agreed", (), settled=True)
    if len(names) == 1:
        return Proposal(names[0], "name", tuple(off))
    if names:
        return Proposal(names[0], "name?", tuple(names[1:]) + tuple(off))
    if off:
        return Proposal(off[0], "off", tuple(off[1:]))
    return Proposal()


# --- the CSV round trip -------------------------------------------------------

# What a reviewer who cannot answer leaves behind. It is a question, in the one
# place this catalog keeps questions, so it can be closed later by a catalog
# match or a second receipt rather than waiting on a memory.
CATEGORY_UNKNOWN = "category unknown"

PROPOSAL_FIELDS = ("decision", "product_id", "name", "brand", "current",
                   "proposed", "path", "how", "alternatives")

# Weakest evidence first: the rows a person can actually help with are the ones
# worth their attention, and a file that opens on 130 pre-answered lines gets
# skimmed instead of read.
_ORDER = {"": 0, "conflict": 1, "section": 2, "off": 3, "name?": 4, "name": 5,
          "shop+name": 6, "agreed": 7, "shop": 8}


def proposals(products_doc: dict[str, Any], listings: dict[str, Any] | None = None,
              previous: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """A review row per product that has no category from the vocabulary yet.

    A product already carrying a vocabulary key is done and does not reappear;
    one carrying `Dairy`, `chia` or nothing at all is not.
    """
    decided = {row["product_id"]: row for row in (previous or [])}
    rows = []
    for product_id, product in sorted(products_doc["products"].items()):
        current = product.get("category") or ""
        if current in categories.CATEGORIES:
            continue
        found = propose(product_id, product, listings)
        before = decided.get(product_id)
        carried = (before or {}).get("decision", "") \
            if (before or {}).get("proposed") == (found.key or "") else ""
        if not carried and any(q == CATEGORY_UNKNOWN
                               for q in product.get("open_questions") or []):
            carried = "n"
        rows.append({
            "decision": carried or ("y" if found.settled else ""),
            "product_id": product_id,
            "name": product.get("name") or "",
            "brand": product.get("brand") or "",
            "current": current,
            "proposed": found.key or "",
            "path": found.path,
            "how": found.how,
            "alternatives": ", ".join(found.alternatives),
        })
    rows.sort(key=lambda r: (_ORDER.get(r["how"], 0), r["product_id"]))
    return rows


def write_proposals(rows: list[dict[str, Any]], path: str | Path) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROPOSAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def read_reviewed(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def confirm(reviewed_path: str | Path, products_path: str | Path) -> dict[str, Any]:
    """Write the reviewed rows onto the products, and report what could not be.

    `decision` is `y` to accept the proposal, a category key to use instead, or
    `n` — which means *I looked and I cannot say*, and is not the same as
    leaving the row blank. A blank is work not done; `n` is the answer that
    there is no answer, and it writes `category unknown` into the product's
    `open_questions` so the catalog carries the gap instead of looking
    untouched. Some of these are unrecoverable: `Bubble Chill Wild.` is a
    €2.99 line at Kaufland and the shopper does not remember what it was, so
    nothing in reach will ever say.

    A key the vocabulary has never heard of is refused and reported: that is a
    gap in `categories.py`, and the fix is to add the entry there, not to let a
    forty-seventh free-text value in through the same door as `cut` and `chia`.
    """
    products_doc = json.loads(Path(products_path).read_text(encoding="utf-8"))
    products = products_doc["products"]
    summary: dict[str, Any] = {"written": 0, "rejected": 0, "undecided": 0,
                               "unknown_products": [], "unknown_categories": []}

    for row in read_reviewed(reviewed_path):
        decision = (row.get("decision") or "").strip()
        product_id = (row.get("product_id") or "").strip()
        if not decision:
            summary["undecided"] += 1
            continue
        if product_id not in products:
            summary["unknown_products"].append(product_id)
            continue
        if decision.lower() == "n":
            questions = products[product_id].setdefault("open_questions", [])
            if not any(q.startswith("category ") for q in questions):
                questions.append(CATEGORY_UNKNOWN)
            summary["rejected"] += 1
            continue

        key = (row.get("proposed") or "").strip() if decision.lower() == "y" else decision
        if key not in categories.CATEGORIES:
            summary["unknown_categories"].append(f"{product_id}: {key or '(nothing proposed)'}")
            continue
        products[product_id]["category"] = key
        summary["written"] += 1

    Path(products_path).write_text(
        json.dumps(products_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
