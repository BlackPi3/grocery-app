"""The matcher: a line the memory cannot place, placed from real candidates.

Step 4b of `docs/designs/catalog-growth.md`. When neither the memory nor the
produce vocabulary knows a printed name, this runs a fixed sequence, the same
every time:

1. **Gather candidates**, real products only: our own catalog first, so a
   known product is never proposed twice, then the shop's range (GLOBUS's own
   site search, the ALDI SÜD crawl on disk).
2. **The model picks one of them, or none**, and says how sure it is and why.
   It cannot invent a product, because a number outside the list is read as
   none. It is shown names, brands and sizes, and never a price: see 3.
3. **Accept or ask.** A pick is accepted only when a second, independent
   source agrees with it: the price paid equals a price the product is listed
   or was seen at, at the shopper's own store, and no variant of it costs the
   same. The model must also call itself sure; on its own word alone nothing
   is accepted. The model never saw prices, so the two cannot be one source counted
   twice. Anything else is a question for the shopper.

Nothing here writes to the catalog or the memory. `propose` returns a
proposal; what is done with it is the caller's business (step 5).

The model is reached through a *decider*, a callable taking a system prompt, a
prompt and a JSON schema and returning the answer as a dict. `ClaudeCodeDecider`
uses the shopper's own subscription through `claude -p`; an API decider is the
same shape. There is no default: code that forgets to pass one fails, rather
than quietly spending money.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from grocery_app.resolver import expand_abbreviations, fold, store_key

PROMPT_VERSION = "v1"
TOP_SHOP = 8
TOP_CATALOG = 5

# A shop source: printed name -> that shop's listings for it, best first, each
# a dict with `article_number`, `name`, `brand`, `pack_size`, `price`, `url`.
ShopSource = Callable[[str], list[dict[str, Any]]]
Decider = Callable[[str, str, dict[str, Any]], dict[str, Any]]


@dataclass
class Candidate:
    """One real product the line might be.

    `product_id` is set when it is already in our catalog, `article` when a
    shop lists it; a catalog product the shop lists has both.
    """

    source: str  # "catalog" or a shop key such as "globus"
    name: str
    brand: str | None = None
    pack_size: str | None = None
    product_id: str | None = None
    article: str | None = None
    url: str | None = None
    prices: list[float] = field(default_factory=list)
    printed_as: list[str] = field(default_factory=list)

    def describe(self) -> str:
        """What the model is shown. Deliberately no price."""
        parts = [self.name]
        if self.brand:
            parts.append(f"brand {self.brand}")
        if self.pack_size:
            parts.append(f"pack {self.pack_size}")
        if self.printed_as:
            parts.append("printed elsewhere as " + ", ".join(f"`{n}`" for n in self.printed_as))
        parts.append("in our catalog" if self.product_id else f"listed by {self.source}")
        return " | ".join(parts)


# --- 1. candidates ------------------------------------------------------------


def _grams(text: str) -> set[str]:
    padded = " " + " ".join(fold(text).replace(".", " ").split()) + " "
    return {padded[i:i + 3] for i in range(len(padded) - 2)}


def similarity(raw_name: str, text: str) -> float:
    """Share of the printed name's letter triples also found in `text`.

    Letter-based on purpose: tills truncate (`Kühlschr.`) where whole-word
    comparison finds nothing. Brand abbreviations are expanded first, so `JT`
    can meet `Jeden Tag`.
    """
    wanted = _grams(expand_abbreviations(raw_name))
    return len(wanted & _grams(text)) / len(wanted) if wanted else 0.0


def catalog_candidates(raw_name: str, products: dict[str, dict[str, Any]],
                       printed: dict[str, list[str]],
                       limit: int = TOP_CATALOG) -> list[tuple[float, str]]:
    """The catalog products whose name, brand or printed names come closest."""
    scored = []
    for product_id, product in products.items():
        texts = [f"{product.get('brand') or ''} {product.get('name') or ''}",
                 *printed.get(product_id, [])]
        scored.append((max(similarity(raw_name, t) for t in texts), product_id))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return scored[:limit]


def printed_names(resolution: dict[tuple[str, str], list[str]]) -> dict[str, list[str]]:
    """Product id -> the names tills have printed for it, from the memory."""
    names: dict[str, list[str]] = {}
    for (_, raw_name), ids in resolution.items():
        if len(ids) == 1:
            names.setdefault(ids[0], []).append(raw_name)
    return names


def gather(raw_name: str, store: str | None, products: dict[str, dict[str, Any]],
           resolution: dict[tuple[str, str], list[str]],
           shelf_prices: dict[str, set[float]], index: dict[str, str],
           shops: dict[str, ShopSource]) -> list[Candidate]:
    """Every candidate for a line: the shop's listings, then our closest products.

    A shop listing that is already one of our products (its article number is
    banked, or is a product's barcode) is shown once, as that product, with
    the shop's price added to the prices it has been seen at.
    """
    printed = printed_names(resolution)
    by_id: dict[str, Candidate] = {}
    found: list[Candidate] = []

    def ours(product_id: str) -> Candidate:
        if product_id not in by_id:
            product = products[product_id]
            size = product.get("size") or {}
            by_id[product_id] = Candidate(
                source="catalog", name=product.get("name") or product_id,
                brand=product.get("brand"), product_id=product_id,
                pack_size=(f"{size['value']:g} {size['unit']}"
                           if size.get("value") and size.get("unit") else None),
                prices=sorted(shelf_prices.get(product_id, ())),
                printed_as=printed.get(product_id, [])[:3])
            found.append(by_id[product_id])
        return by_id[product_id]

    shop = store_key(store)
    for listing in (shops[shop](raw_name) if shop in shops else [])[:TOP_SHOP]:
        article = str(listing.get("article_number") or "") or None
        price = listing.get("price")
        known = index.get(article) if article else None
        if known in products:
            candidate = ours(known)
            candidate.article = candidate.article or article
        else:
            candidate = Candidate(source=shop, name=listing.get("name") or "",
                                  brand=listing.get("brand"),
                                  pack_size=listing.get("pack_size"),
                                  article=article, url=listing.get("url"))
            found.append(candidate)
        if price is not None and float(price) not in candidate.prices:
            candidate.prices.append(float(price))

    for _, product_id in catalog_candidates(raw_name, products, printed):
        ours(product_id)
    return found


def globus_source(raw_name: str) -> list[dict[str, Any]]:
    """GLOBUS's own search at the shopper's store, cached on disk and polite.

    A listing the search page shows without a price gets it from its product
    page, because the price is the second source a pick is accepted on.
    """
    from grocery_app.resolver import MARKET, MARKET_CACHE, search_candidates, shelf_price

    listings = [c["product"] for c in search_candidates(raw_name, None, MARKET_CACHE,
                                                        TOP_SHOP, market=MARKET)]
    for listing in listings:
        if listing.get("price") is None and listing.get("url"):
            listing["price"] = shelf_price(listing["url"], MARKET_CACHE)
    return listings


def crawl_source(crawl_path: str | Path) -> ShopSource:
    """A shop with no search of its own: letter similarity over its crawl."""
    listings: list[dict[str, Any]] | None = None

    def source(raw_name: str) -> list[dict[str, Any]]:
        nonlocal listings
        if listings is None:
            path = Path(crawl_path)
            listings = (list(json.loads(path.read_text(encoding="utf-8")).values())
                        if path.exists() else [])
        scored = sorted(listings, key=lambda p: -similarity(
            raw_name, f"{p.get('brand') or ''} {p.get('name') or ''}"))
        return scored[:TOP_SHOP]

    return source


def default_shops(products_dir: str | Path = "data/products") -> dict[str, ShopSource]:
    aldi = crawl_source(Path(products_dir) / "aldi-sued" / "crawl.json")
    return {"globus": globus_source, "aldi süd": aldi, "aldi sued": aldi}


# --- 2. the model's pick --------------------------------------------------------

SYSTEM_PROMPT = """\
You match one line of a German supermarket receipt to the product it was.

The till prints short, abbreviated, often truncated names: `JT` is the shop's
budget brand Jeden Tag, `ALN.` is Alnatura, `Kühlschr.` is Kühlschrank. You are
given a numbered list of real products. Answer with the number of the one the
line was, or 0 when none of them is it.

- Choose only from the list. Never describe a product that is not on it.
- A size, count or variant the line prints must agree with the product. A
  trailing code can be the whole difference: `Eier 10er FH` is free-range
  (Freilandhaltung), not barn eggs.
- When the line cannot tell two listed products apart (a flavour or size it does
  not print), answer 0 and say which ones it could be. A wrong answer costs more
  than a question.
- confidence: `high` when the line names the product unambiguously, `medium`
  when it very probably is, `low` when it is a guess.
- reason: one short sentence, in English."""

DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "choice": {"type": "integer", "minimum": 0},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reason": {"type": "string"},
    },
    "required": ["choice", "confidence", "reason"],
    "additionalProperties": False,
}


def build_prompt(raw_name: str, store: str | None, candidates: list[Candidate]) -> str:
    listed = "\n".join(f"{n}. {c.describe()}" for n, c in enumerate(candidates, 1))
    return f"Shop: {store or 'unknown'}\nReceipt line: `{raw_name}`\n\nProducts:\n{listed}"


@dataclass
class Decision:
    pick: Candidate | None
    confidence: str
    reason: str


def decide(raw_name: str, store: str | None, candidates: list[Candidate],
           decider: Decider) -> Decision:
    """The model's pick. A number outside the list is none, never a guess."""
    if not candidates:
        return Decision(None, "high", "no candidates")
    answer = decider(SYSTEM_PROMPT, build_prompt(raw_name, store, candidates),
                     DECISION_SCHEMA)
    choice = answer.get("choice")
    pick = (candidates[choice - 1]
            if isinstance(choice, int) and 1 <= choice <= len(candidates) else None)
    return Decision(pick, answer.get("confidence") or "low", answer.get("reason") or "")


# --- 3. accept or ask ----------------------------------------------------------


def paid_price(line: dict[str, Any]) -> float | None:
    """The shelf price this line was bought at, before any discount.

    Per kilo for weighed goods, since that is what a shop lists; per item
    otherwise. `gross` is before discount, so GLOBUS's staff discount, printed
    as its own line, does not get in the way.
    """
    if line.get("sold_by_weight"):
        return line.get("unit_price")
    if line.get("gross") is None:
        return None
    return round(line["gross"] / (line.get("qty") or 1), 2)


def price_agrees(line: dict[str, Any], candidate: Candidate) -> bool:
    paid = paid_price(line)
    return paid is not None and any(abs(paid - p) < 0.005 for p in candidate.prices)


# Set from the test set on 2026-09-25, not guessed: of the model's picks, the
# `high` ones were 27 right and none wrong, the `medium` ones 1 right and 3
# wrong. A medium pick agreeing on price was `Speisekartoffeln für Back und
# Grill` for `KARTOFFELN F.K. LOSE` (festkochend): every loose potato costs the
# same per kilo. Tuned on that set, so the next batch of receipts is the test.
ACCEPTED_CONFIDENCE = ("high",)

# How alike two candidates' names must be to count as the same product in
# another variant: `Mangostreifen` and `Bio Mangostreifen` score 1.0.
SIBLING = 0.7


def price_singles_out(line: dict[str, Any], pick: Candidate,
                      candidates: list[Candidate]) -> bool:
    """The price paid agrees with the pick, and with no variant of it.

    At the shopper's GLOBUS the plain and the Bio Mangostreifen both cost
    3.29, so paying 3.29 says nothing about which it was, and the model had
    picked the wrong one. A price is a second source only when it tells the
    pick apart from its siblings, the same rule `normalizer.priced_like` uses
    to narrow a family.
    """
    if not price_agrees(line, pick):
        return False
    return not any(other is not pick and price_agrees(line, other)
                   and max(similarity(pick.name, other.name),
                           similarity(other.name, pick.name)) >= SIBLING
                   for other in candidates)


def propose(line: dict[str, Any], store: str | None, products: dict[str, dict[str, Any]],
            resolution: dict[tuple[str, str], list[str]],
            shelf_prices: dict[str, set[float]], index: dict[str, str],
            shops: dict[str, ShopSource], decider: Decider) -> dict[str, Any]:
    """What the matcher would do with one line. Writes nothing.

    `verdict` is `accept` only when the model picked a product, is sure of it
    (`ACCEPTED_CONFIDENCE`), and the price paid singles it out; otherwise
    `ask`, with the candidates to ask about.
    """
    raw_name = line["raw_name"]
    candidates = gather(raw_name, store, products, resolution, shelf_prices, index, shops)
    decision = decide(raw_name, store, candidates, decider)
    agrees = decision.pick is not None and price_singles_out(line, decision.pick, candidates)
    sure = decision.confidence in ACCEPTED_CONFIDENCE
    return {
        "raw_name": raw_name,
        "store": store,
        "paid": paid_price(line),
        "candidates": [asdict(c) for c in candidates],
        "pick": asdict(decision.pick) if decision.pick else None,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "price_agrees": agrees,
        "verdict": "accept" if agrees and sure else "ask",
    }


# --- deciders ---------------------------------------------------------------------


class DeciderError(Exception):
    pass


class ClaudeCodeDecider:
    """The model through `claude -p`, on the shopper's subscription.

    Every answer is cached under `<cache_dir>/claude-code-<model>/<prompt
    version>/<hash>.json`, keyed on the exact prompt, so re-running a score
    costs nothing until a candidate list or the prompt changes. It runs with
    no tools and from an empty directory, so nothing but the prompt reaches
    the model.
    """

    def __init__(self, model: str = "sonnet", cache_dir: str | Path = "data/matched",
                 timeout_s: int = 180):
        self.model = model
        self.cache = Path(cache_dir) / f"claude-code-{model}" / PROMPT_VERSION
        self.timeout_s = timeout_s

    def __call__(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        key = hashlib.sha256(json.dumps([self.model, system, prompt, schema],
                                        sort_keys=True).encode()).hexdigest()[:24]
        path = self.cache / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["answer"]
        command = ["claude", "-p", prompt, "--model", self.model, "--tools", "",
                   "--no-session-persistence", "--system-prompt", system,
                   "--output-format", "json", "--json-schema", json.dumps(schema)]
        with tempfile.TemporaryDirectory() as empty:
            done = subprocess.run(command, capture_output=True, text=True, cwd=empty,
                                  timeout=self.timeout_s, check=False)
        try:
            result = json.loads(done.stdout)
        except ValueError as error:
            raise DeciderError(f"claude -p gave no JSON: {done.stderr[:300]}") from error
        answer = result.get("structured_output")
        if result.get("is_error") or not isinstance(answer, dict):
            raise DeciderError(f"claude -p failed: {str(result.get('result'))[:300]}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"prompt": prompt, "answer": answer},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        return answer
