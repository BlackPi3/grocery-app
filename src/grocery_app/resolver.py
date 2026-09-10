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


def store_key(store: str | None) -> str:
    """Stores are compared case-insensitively; GLOBUS and Globus are one chain."""
    return (store or "").strip().casefold()


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
    # Store names are an identity, not a transcription: one chain prints GLOBUS
    # and another receipt of the same chain prints Globus.
    known = {(store_key(e["store"]), e["raw_name"]) for e in resolution["entries"]}

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
            if raw_name and (store_key(store), raw_name) not in known:
                # `gross` is the line total. Two quark pots at 0.69 print as
                # 1.38, so comparing that against a shelf price is meaningless.
                gross, qty = line.get("gross"), line.get("qty") or 1
                pending.setdefault(raw_name, round(gross / qty, 2) if gross else None)
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


# --- ingesting reviewed proposals ---------------------------------------------

def read_reviewed(path: str | Path) -> list[dict[str, str]]:
    """Read a reviewed proposal table, accepting comma or semicolon delimiters.

    Excel writes `;` under a German locale, which is how this file comes back.
    """
    import csv

    text = Path(path).read_text(encoding="utf-8-sig")
    delimiter = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
    return list(csv.DictReader(text.splitlines(), delimiter=delimiter))


def accepted_rows(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """raw_name -> the rows marked `y`, in file order.

    More than one row may be accepted for a name: the catalog can carry several
    article numbers for what is one product to a shopper (three listings of the
    same Alnatura eggs). They become one product with several barcodes.
    """
    picked: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if decision_of(row) == "y":
            picked.setdefault(row["raw_name"], []).append(row)
    return picked


# The vocabulary a reviewer can write in the decision column. Blank has to keep
# meaning "not looked at yet", so "I looked and none of these is right" needs a
# mark of its own -- otherwise the two collapse and we cannot tell whether to
# widen the search or simply wait.
DECISIONS = {
    "y": "this candidate is the product",
    "n": "none of these is right, and I checked",
    "?": "I am not sure; ask me again",
}


def decision_of(row: dict[str, str]) -> str | None:
    """The mark, or None when the cell is blank.

    A cell that holds something unrecognised returns None here but must never be
    treated as blank by callers: `unclear_rows` collects those so a reviewer's
    note is reported rather than silently dropped. Dropping them once cost
    Parham a whole review pass.
    """
    value = (row.get("decision") or "").strip().lower()
    if not value:
        return None
    return value[0] if value[0] in DECISIONS else None


def unclear_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Rows whose decision cell holds something we cannot interpret."""
    return [r for r in rows
            if (r.get("decision") or "").strip() and decision_of(r) is None]


def ambiguous_names(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Names with several `y` rows pointing at products with different names.

    Several accepted rows usually mean one product listed more than once (three
    entries for the same Alnatura eggs), which merges into one product with
    several barcodes. But `Dusche Fruchtig Leicht` and `Dusche Sweet Treat` are
    genuinely different products, and merging those would invent a fact. Where
    the accepted names differ, a person has to say which it is.
    """
    ambiguous = {}
    for raw_name, picked in accepted_rows(rows).items():
        # Size counts as a difference: `Bio Chia Samen` at 0,5 kg and at 0,2 kg
        # are two products, and the receipt prints the same text for both.
        identities = {((r.get("catalog_name") or "").strip().lower(),
                       (r.get("pack_size") or "").strip().lower()) for r in picked}
        if len(identities) > 1:
            ambiguous[raw_name] = picked
    return ambiguous


def marked_names(rows: list[dict[str, str]], mark: str) -> set[str]:
    return {r["raw_name"] for r in rows if decision_of(r) == mark}


_BARCODE_LENGTHS = {8, 12, 13, 14}


def _size_from_row(row: dict[str, str]) -> dict[str, Any]:
    parsed = parse_size(row.get("pack_size") or "") or parse_size(row.get("catalog_name") or "")
    if not parsed:
        return {"count": 1, "value": None, "unit": None}
    return {"count": 1, "value": parsed[0], "unit": parsed[1]}


def confirm(reviewed_path: str | Path, products_path: str | Path,
            resolution_path: str | Path, listings_path: str | Path,
            store: str, observed_on: str) -> dict[str, Any]:
    """Write accepted proposals into products, resolution and store listings.

    Only rows a human marked are written. An accepted row is the moment a
    product earns an id, so ids are minted here and nowhere else.
    """
    products_doc = json.loads(Path(products_path).read_text(encoding="utf-8"))
    resolution_doc = json.loads(Path(resolution_path).read_text(encoding="utf-8"))
    listings_doc = json.loads(Path(listings_path).read_text(encoding="utf-8"))

    known = {(store_key(e["store"]), e["raw_name"]) for e in resolution_doc["entries"]}
    rows = read_reviewed(reviewed_path)
    all_accepted = accepted_rows(rows)
    # A name whose accepted rows disagree needs a person, not a merge.
    held_back = ambiguous_names(rows)
    accepted = {k: v for k, v in all_accepted.items() if k not in held_back}

    # A row offered no candidate but carries a url: the reviewer looked the
    # product up and pasted the answer in. That is a decision, not a proposal,
    # so it is taken from the page itself.
    supplied: list[tuple[str, str]] = []
    for row in rows:
        if row.get("rank", "").strip() != "-":
            continue
        url = (row.get("url") or "").strip()
        if url.startswith("http") and (store_key(store), row["raw_name"]) not in known:
            supplied.append((row["raw_name"], url))

    # "None of these is right" is an answer worth keeping: it stops the name
    # being re-proposed with the same candidates, and marks it as needing a
    # different source rather than more ranking.
    no_match = 0
    supplied_names = {name for name, _ in supplied}
    # A note on a row with no candidate and no url means the reviewer searched
    # and the product is not on the site.
    unmatched_names = {r["raw_name"] for r in unclear_rows(rows)
                       if r.get("rank", "").strip() == "-"} - supplied_names
    for raw_name in sorted(marked_names(rows, "n") | unmatched_names):
        # `all_accepted`, not `accepted`: a name held back for disambiguation
        # still has a `y` on it and is emphatically not a no-match.
        if (store_key(store), raw_name) in known or raw_name in all_accepted:
            continue
        resolution_doc["entries"].append({
            "store": store, "raw_name": raw_name, "line_type": "product",
            "product_id": None, "status": "no_match_in_catalog",
            "confirmed_by": "parham", "confirmed_at": observed_on,
            "source": str(reviewed_path),
        })
        no_match += 1

    added_products = added_entries = added_listings = 0
    for raw_name, picked in accepted.items():
        if (store_key(store), raw_name) in known:
            continue

        product_id = f"p-{products_doc['meta']['next_id']:04d}"
        products_doc["meta"]["next_id"] += 1
        first = picked[0]

        # Several accepted rows mean several article numbers for one product;
        # they become barcodes on it rather than separate products.
        eans = [r["article_number"] for r in picked
                if len(r.get("article_number") or "") in _BARCODE_LENGTHS]

        products_doc["products"][product_id] = {
            "label": first.get("catalog_name"),
            "name": first.get("catalog_name"),
            "brand": first.get("brand") or None,
            "product_line": None,
            "variant": None,
            "size": _size_from_row(first),
            "category": None,
            "is_organic": None,
            "is_own_brand": None,
            "eans": eans,
            "open_questions": [],
            "provenance": {"attributes": "globus-catalog", "source": first.get("url")},
        }
        added_products += 1

        resolution_doc["entries"].append({
            "store": store,
            "raw_name": raw_name,
            "line_type": "product",
            "product_id": product_id,
            "confirmed_by": "parham",
            "confirmed_at": observed_on,
            "source": str(reviewed_path),
        })
        added_entries += 1

        for row in picked:
            article = row.get("article_number")
            if not article:
                continue
            price = row.get("catalog_price")
            listings_doc["listings"][article] = {
                "product_id": product_id,
                "url": row.get("url"),
                # Shelf price observed at fetch time; a different series from
                # what was paid, which lives in purchases.json.
                "prices": [{"date": observed_on, "price": float(price)}] if price else [],
            }
            added_listings += 1

    resolution_doc["entries"].sort(key=lambda e: (e["store"], e["raw_name"]))

    for path, doc in ((products_path, products_doc), (resolution_path, resolution_doc),
                      (listings_path, listings_doc)):
        Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")

    return {"products": added_products, "entries": added_entries,
            "listings": added_listings, "no_match": no_match,
            "supplied": supplied,
            "ambiguous": sorted(held_back),
            "unclear": [(r.get("decision"), r["raw_name"]) for r in unclear_rows(rows)
                        if r["raw_name"] not in supplied_names
                        and r["raw_name"] not in unmatched_names],
            "skipped": len(accepted) - added_entries}


# --- search-backed candidates -------------------------------------------------
#
# Ranking over a locally fetched catalog missed badly: it only knew the three
# categories that had been crawled, and exact token equality cannot follow a
# till's truncations (`Konf.Erdbeer` never equals `Konfitüre, Erdbeere`).
# GLOBUS's own search does German stemming over their whole range, so it is a
# far better candidate generator than anything hand-rolled here. Local scoring
# then only has to re-order what it returns.

import time
import urllib.parse
import urllib.request

SEARCH_URL = "https://produkte.globus.de/search?query="
SEARCH_CACHE = "data/catalog_cache/globus/_search"
SEARCH_DELAY_S = 1.0


def search(query: str, cache_dir: str | Path = SEARCH_CACHE,
           force: bool = False) -> list[dict[str, Any]]:
    """Products GLOBUS's own search returns for a query, in their order."""
    from grocery_app.catalog_globus import USER_AGENT, parse_listing

    slug = re.sub(r"[^a-z0-9]+", "_", fold(query)).strip("_") or "_"
    path = Path(cache_dir) / f"{slug}.html"

    if path.exists() and not force:
        html = path.read_text(encoding="utf-8")
    else:
        request = urllib.request.Request(
            SEARCH_URL + urllib.parse.quote(query),
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            html = response.read().decode("utf-8", errors="replace")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        time.sleep(SEARCH_DELAY_S)

    return parse_listing(html)


MAX_UMLAUT_VARIANTS = 9


def umlaut_variants(raw_name: str) -> list[str]:
    """Fill in `?` placeholders a till printed where it could not render an umlaut.

    Search cannot match `SAATENBR?TCHEN`, but it finds `Saatenbrötchen` at once.
    Every combination of ä/ö/ü is tried because which vowel it was is exactly
    what the receipt failed to record; wrong guesses simply return nothing.
    """
    if "?" not in raw_name:
        return []
    variants = [raw_name]
    for _ in range(raw_name.count("?")):
        expanded = []
        for variant in variants:
            position = variant.index("?")
            # Match the case of the word the placeholder sits in, so
            # SAATENBR?TCHEN becomes SAATENBRÖTCHEN and not SAATENBRäTCHEN.
            before = variant[:position]
            neighbour = next((c for c in reversed(before) if c.isalpha()), "")
            vowels = "ÄÖÜ" if neighbour.isupper() else "äöü"
            for vowel in vowels:
                expanded.append(variant[:position] + vowel + variant[position + 1:])
        variants = expanded
        if len(variants) > MAX_UMLAUT_VARIANTS:
            break
    return [v for v in variants if "?" not in v][:MAX_UMLAUT_VARIANTS]


def queries_for(raw_name: str) -> list[str]:
    """The raw line, a brand-expanded form, and umlaut fill-ins for `?`.

    All are worth asking: searching `JT Magerquark 250g` finds the Hansano one,
    while `Jeden Tag Magerquark` finds the own-brand the receipt actually means.
    Their engine ignores the `JT` token entirely.
    """
    queries = [raw_name]
    expanded = expand_abbreviations(raw_name)
    if fold(expanded) != fold(raw_name):
        queries.append(expanded)
    queries.extend(umlaut_variants(raw_name))
    return queries


def search_candidates(raw_name: str, receipt_price: float | None,
                      cache_dir: str | Path = SEARCH_CACHE,
                      top_n: int = TOP_N) -> list[dict[str, Any]]:
    """Rank what search returns. Their relevance leads; ours breaks ties."""
    seen: dict[str, dict[str, Any]] = {}
    for query in queries_for(raw_name):
        for position, product in enumerate(search(query, cache_dir)):
            article = product.get("article_number")
            if not article or article in seen:
                continue
            points, evidence = score(raw_name, receipt_price, product)
            # Search position is the strongest signal available; a hit they put
            # first is usually right, and our scoring only reorders near-ties.
            points += max(0.0, 3.0 - 0.3 * position)
            evidence.insert(0, f"search#{position + 1}")
            seen[article] = {"score": round(points, 2), "evidence": evidence,
                             "product": product}
    ranked = sorted(seen.values(), key=lambda c: -c["score"])
    return ranked[:top_n]


def build_proposals_via_search(receipts_dir: str | Path, resolution_path: str | Path,
                               store: str, cache_dir: str | Path = SEARCH_CACHE,
                               top_n: int = TOP_N) -> list[dict[str, Any]]:
    pending = unresolved_lines(receipts_dir, resolution_path, store)
    proposals = []
    for raw_name, price in sorted(pending.items()):
        candidates = search_candidates(raw_name, price, cache_dir, top_n)
        log_line = f"  {raw_name[:28]:28s} {len(candidates)} candidates"
        print(log_line, flush=True)
        proposals.append({"raw_name": raw_name, "receipt_price": price,
                          "candidates": candidates})
    return proposals


# --- confirming by URL --------------------------------------------------------
#
# When Parham already knows the product, a link is the shortest path: he pastes
# it, and the page itself supplies name, brand, barcode and price. No ranking is
# involved and none is wanted -- this is a decision, not a proposal.

def product_from_url(url: str, cache_dir: str | Path = SEARCH_CACHE,
                     force: bool = False) -> dict[str, Any]:
    """Read one product page's schema.org JSON-LD."""
    from grocery_app.catalog_globus import USER_AGENT, _article_number_from_href

    article = _article_number_from_href(url.split("?")[0])
    path = Path(cache_dir).parent / "_products" / f"{article or 'unknown'}.html"

    if path.exists() and not force:
        html = path.read_text(encoding="utf-8")
    else:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=45) as response:
            html = response.read().decode("utf-8", errors="replace")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        time.sleep(SEARCH_DELAY_S)

    for block in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>",
                            html, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in (data if isinstance(data, list) else [data]):
            if not isinstance(item, dict) or item.get("@type") != "Product":
                continue
            offers = item.get("offers")
            offers = offers[0] if isinstance(offers, list) else (offers or {})
            return {
                "article_number": item.get("sku") or article,
                "name": item.get("name"),
                "brand": (item.get("brand") or {}).get("name"),
                "price": offers.get("price"),
                "pack_size": item.get("description"),
                "url": url.split("?")[0],
            }
    raise ValueError(f"no product JSON-LD found at {url}")


def read_pairs(path: str | Path) -> list[tuple[str, str]]:
    """`raw_name<TAB>url` lines; blank lines and # comments ignored."""
    pairs = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        raw_name, _, url = line.partition("\t")
        if url.strip():
            pairs.append((raw_name.strip(), url.strip()))
    return pairs


def confirm_pairs(pairs: list[tuple[str, str]], products_path: str | Path,
                  resolution_path: str | Path, listings_path: str | Path,
                  store: str, observed_on: str,
                  source: str) -> dict[str, Any]:
    products_doc = json.loads(Path(products_path).read_text(encoding="utf-8"))
    resolution_doc = json.loads(Path(resolution_path).read_text(encoding="utf-8"))
    listings_doc = json.loads(Path(listings_path).read_text(encoding="utf-8"))
    known = {(store_key(e["store"]), e["raw_name"]) for e in resolution_doc["entries"]}

    added = skipped = 0
    for raw_name, url in pairs:
        if (store_key(store), raw_name) in known:
            skipped += 1
            continue
        found = product_from_url(url)
        product_id = f"p-{products_doc['meta']['next_id']:04d}"
        products_doc["meta"]["next_id"] += 1
        article = found["article_number"] or ""

        products_doc["products"][product_id] = {
            "label": found["name"],
            "name": found["name"],
            "brand": found["brand"],
            "product_line": None,
            "variant": None,
            "size": _size_from_row({"pack_size": found.get("pack_size"),
                                    "catalog_name": found.get("name")}),
            "category": None,
            "is_organic": None,
            "is_own_brand": None,
            "eans": [article] if len(article) in _BARCODE_LENGTHS else [],
            "open_questions": [],
            "provenance": {"attributes": "globus-product-page", "source": found["url"]},
        }
        resolution_doc["entries"].append({
            "store": store, "raw_name": raw_name, "line_type": "product",
            "product_id": product_id, "confirmed_by": "parham",
            "confirmed_at": observed_on, "source": source,
        })
        if article:
            listings_doc["listings"][article] = {
                "product_id": product_id, "url": found["url"],
                "prices": ([{"date": observed_on, "price": float(found["price"])}]
                           if found.get("price") else []),
            }
        added += 1

    resolution_doc["entries"].sort(key=lambda e: (e["store"], e["raw_name"]))
    for path, doc in ((products_path, products_doc), (resolution_path, resolution_doc),
                      (listings_path, listings_doc)):
        Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    return {"added": added, "skipped": skipped}
