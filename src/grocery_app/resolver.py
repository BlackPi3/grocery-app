"""Propose catalog products for receipt lines that resolution.json does not know.

Known names are a lookup, not a guess: `resolution.json` maps (store, raw_name)
to a product_id and the normalizer reads it directly. This module handles the
other case -- a name nobody has decided on yet -- by ranking real catalog
products and asking Parham, who is the authority on what a GLOBUS line means.

What it ranks on, in order:

  1. name tokens, de-umlauted, since tills print `SAATENBR?TCHEN` for
     `Saatenbrötchen` and slugs spell it `saatenbroetchen`
  2. brand, once the chain's abbreviations are expanded (`JT` -> Jeden Tag)
  3. size, when the receipt prints one (`250g`, `1L`)
  4. price, as a weak hint only

Price is deliberately last. It changes weekly, the shop publishes only today's
value, and the receipts are months old, so an exact price agreement is a nice
corroboration and a terrible filter -- an earlier pass that gated on price
matched `Chips Salt & Vinegar` to `Erdbeeren` because both cost 1.11.

Nothing here writes to resolution.json. It emits proposals for review; a
confirmed proposal is what earns a row there.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

DEFAULT_CATALOG = "data/catalog/globus.json"
DEFAULT_OUTPUT = "data/proposals/globus.csv"

TOP_N = 3

# Chain-specific shorthand. GLOBUS prints `<brand abbreviation> <product> <size>`,
# so without expansion the brand signal is invisible: `JT Milch` shares no token
# with `Jeden Tag`.
BRAND_ABBREVIATIONS = {
    "jt": "jeden tag",
    "aln": "alnatura",
    "gt": "gut tag",
    "dh": "das gesunde",
    "lac": "laktosefrei",
    "ins": "instant",
}

_UMLAUTS = [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]

# `?` is what a till prints when it cannot render an umlaut, so it must not be
# treated as a literal character when comparing.
_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|stk|stück|er)\b", re.IGNORECASE)


def fold(text: str) -> str:
    text = (text or "").lower()
    for umlaut, replacement in _UMLAUTS:
        text = text.replace(umlaut, replacement)
    return text


def tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", fold(text)) if len(t) > 2}


def expand_abbreviations(raw_name: str) -> str:
    parts = re.split(r"([^A-Za-zÄÖÜäöüß0-9]+)", raw_name)
    return "".join(BRAND_ABBREVIATIONS.get(p.lower(), p) for p in parts)


def parse_size(text: str) -> tuple[float, str] | None:
    """Return (value, unit) for the first size in a string, normalised to g/ml/piece."""
    match = _SIZE.search(text or "")
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    unit = match.group(2).lower()
    if unit == "kg":
        return value * 1000, "g"
    if unit == "l":
        return value * 1000, "ml"
    if unit in {"stk", "stück", "er"}:
        return value, "piece"
    return value, unit


def score(raw_name: str, receipt_price: float | None,
          product: dict[str, Any]) -> tuple[float, list[str]]:
    """Return (score, evidence) for one candidate. Evidence is why, in words."""
    expanded = expand_abbreviations(raw_name)
    receipt_tokens = tokens(expanded)
    evidence: list[str] = []
    points = 0.0

    name_overlap = receipt_tokens & tokens(product.get("name"))
    if name_overlap:
        # Share of the receipt line explained by the candidate's name.
        points += 4.0 * len(name_overlap) / max(1, len(receipt_tokens))
        evidence.append("name:" + "+".join(sorted(name_overlap)))

    brand_overlap = receipt_tokens & tokens(product.get("brand"))
    if brand_overlap:
        points += 2.0
        evidence.append("brand:" + "+".join(sorted(brand_overlap)))

    receipt_size = parse_size(raw_name)
    catalog_size = parse_size(product.get("pack_size") or "") or parse_size(
        product.get("name") or "")
    if receipt_size and catalog_size and receipt_size[1] == catalog_size[1]:
        if abs(receipt_size[0] - catalog_size[0]) < 0.01:
            points += 2.0
            evidence.append(f"size:{receipt_size[0]:g}{receipt_size[1]}")
        else:
            # A confident size disagreement is real evidence against.
            points -= 1.0
            evidence.append("size-mismatch")

    price = product.get("price")
    if receipt_price and price and abs(price - receipt_price) < 0.005:
        points += 0.5
        evidence.append(f"price:{price:.2f}")

    return points, evidence


def rank(raw_name: str, receipt_price: float | None,
         catalog: Iterable[dict[str, Any]], top_n: int = TOP_N) -> list[dict[str, Any]]:
    """Best candidates for one receipt line, strongest first.

    A candidate must have some name or brand evidence to appear at all: price
    and size alone describe far too many products to be worth a person's time.
    """
    scored = []
    for product in catalog:
        points, evidence = score(raw_name, receipt_price, product)
        if points <= 0 or not any(e.startswith(("name:", "brand:")) for e in evidence):
            continue
        scored.append({"score": round(points, 2), "evidence": evidence, "product": product})
    scored.sort(key=lambda c: -c["score"])
    return scored[:top_n]


def load_catalog(path: str | Path) -> list[dict[str, Any]]:
    return list(json.loads(Path(path).read_text(encoding="utf-8")).values())


def unresolved_lines(receipts_dir: str | Path, resolution_path: str | Path,
                     store_filter: str) -> dict[str, float | None]:
    """(raw_name -> price) for lines of one store that resolution.json lacks.

    Reads verified receipt text only. Feeding it model output would mix
    extraction disagreements into the list: two models read one line as `Manner`
    and `Männer`, which would arrive here as two separate products to decide on.
    """
    resolution = json.loads(Path(resolution_path).read_text(encoding="utf-8"))
    known = {(e["store"], e["raw_name"]) for e in resolution["entries"]}

    pending: dict[str, float | None] = {}
    for path in sorted(Path(receipts_dir).glob("*.json")):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        store = receipt.get("store") or ""
        if store_filter.lower() not in store.lower():
            continue
        for line in receipt.get("lines", []):
            if line.get("type") != "product":
                continue
            raw_name = line.get("raw_name")
            if raw_name and (store, raw_name) not in known:
                pending.setdefault(raw_name, line.get("gross"))
    return pending


def build_proposals(receipts_dir: str | Path, resolution_path: str | Path,
                    catalog_path: str | Path, store: str) -> list[dict[str, Any]]:
    catalog = load_catalog(catalog_path)
    proposals = []
    for raw_name, price in sorted(unresolved_lines(receipts_dir, resolution_path, store).items()):
        candidates = rank(raw_name, price, catalog)
        proposals.append({"raw_name": raw_name, "receipt_price": price,
                          "candidates": candidates})
    return proposals


def to_csv(proposals: list[dict[str, Any]], store: str) -> str:
    """A review table: one row per candidate, a blank `decision` column to fill.

    Put `y` against the right candidate, or leave the whole group blank if none
    of them is right. Abstaining is a valid answer and a useful signal.
    """
    rows = ["decision,raw_name,receipt_price,rank,score,evidence,"
            "catalog_name,brand,pack_size,catalog_price,article_number,url"]

    def esc(value: Any) -> str:
        text = "" if value is None else str(value)
        return '"' + text.replace('"', '""') + '"' if any(c in text for c in ',"\n') else text

    for proposal in proposals:
        if not proposal["candidates"]:
            rows.append(",".join(["", esc(proposal["raw_name"]),
                                  esc(proposal["receipt_price"]), "-", "", "no candidate",
                                  "", "", "", "", "", ""]))
            continue
        for index, candidate in enumerate(proposal["candidates"], start=1):
            product = candidate["product"]
            rows.append(",".join([
                "", esc(proposal["raw_name"]), esc(proposal["receipt_price"]),
                str(index), esc(candidate["score"]), esc(" ".join(candidate["evidence"])),
                esc(product.get("name")), esc(product.get("brand")),
                esc(product.get("pack_size")), esc(product.get("price")),
                esc(product.get("article_number")), esc(product.get("url")),
            ]))
    return "\n".join(rows) + "\n"
