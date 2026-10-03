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

4. **Create when the pick is new.** A shop listing the catalog does not hold
   becomes a product copied from the listing (`new_product`, step 4c).

Nothing here writes to the catalog or the memory. `propose` returns a
proposal, with the product it would create; saving is step 5's job.

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
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from grocery_app import gemini
from grocery_app.resolver import expand_abbreviations, fold, store_key

PROMPT_VERSION = "v2"
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
- When the line cannot tell listed products apart (a flavour or version it does
  not print), answer 0 and list their numbers in `versions`. Only versions of
  one product go there: the same brand, product and size, differing in what
  the line does not print. A wrong answer costs more than a question.
- confidence: `high` when the line names the product (or, with `versions`, the
  product the versions belong to) unambiguously, `medium` when it very probably
  does, `low` when it is a guess.
- reason: one short sentence, in English."""

DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "choice": {"type": "integer", "minimum": 0},
        "versions": {"type": "array", "items": {"type": "integer", "minimum": 1}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reason": {"type": "string"},
    },
    "required": ["choice", "versions", "confidence", "reason"],
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
    # The versions of one product the line could be, when it cannot say which.
    versions: list[Candidate] = field(default_factory=list)


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
    numbers = sorted({n for n in answer.get("versions") or []
                      if isinstance(n, int) and 1 <= n <= len(candidates)})
    # A pick is one product; versions are only read when there is none, and
    # one version is not a family.
    versions = [candidates[n - 1] for n in numbers] if pick is None and len(numbers) > 1 else []
    return Decision(pick, answer.get("confidence") or "low", answer.get("reason") or "",
                    versions)


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

    `verdict` is one of:

    - `accept`: the model picked a product, is sure of it
      (`ACCEPTED_CONFIDENCE`), and the price paid singles it out;
    - `family`: the model is sure the line is one of several versions of a
      product it cannot tell apart (`JT Tortilla Wraps`: Classic or
      Mehrkorn), and the price paid is one of theirs. Recorded as the
      family, and nobody is asked, because the version changes no number
      the app shows (decided 2026-09-25);
    - `ask`: anything else, with the candidates to ask about.
    """
    raw_name = line["raw_name"]
    candidates = gather(raw_name, store, products, resolution, shelf_prices, index, shops)
    decision = decide(raw_name, store, candidates, decider)
    agrees = decision.pick is not None and price_singles_out(line, decision.pick, candidates)
    sure = decision.confidence in ACCEPTED_CONFIDENCE
    family = sure and any(price_agrees(line, v) for v in decision.versions)
    verdict = "accept" if agrees and sure else "family" if family else "ask"
    chosen = ([decision.pick] if verdict == "accept" else
              decision.versions if verdict == "family" else [])
    return {
        "raw_name": raw_name,
        "store": store,
        "paid": paid_price(line),
        "candidates": [asdict(c) for c in candidates],
        "pick": asdict(decision.pick) if decision.pick else None,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "versions": [asdict(c) for c in decision.versions],
        "price_agrees": agrees,
        "verdict": verdict,
        # What accepting would add to the catalog: a product copied from the
        # shop's listing for each chosen candidate that is not ours already.
        "creates": [new_product(asdict(c), "matcher") for c in chosen if not c.product_id],
    }


# --- 4. a new product from a shop listing ------------------------------------------


def new_product(pick: dict[str, Any], decided_by: str) -> dict[str, Any]:
    """The catalog product a picked shop listing becomes. Nothing is guessed.

    Name, brand, pack size and barcode are the shop's own. The category is
    set only when the shop's shelf and the name agree (`categorize.propose`,
    the rule every category in the catalog follows); otherwise it stays empty
    and the product says so in `open_questions`. `provenance` records where
    the product came from and who decided the line was it: `matcher` for a
    model pick the price agreed with, `shopper` for an answer to a question.

    It returns the record without an id. Minting the id and saving it,
    together with the printed name that led to it, is step 5's job.
    """
    from grocery_app import categorize
    from grocery_app.resolver import _BARCODE_LENGTHS, _size_from_row, brand_questions

    article = pick.get("article") or ""
    product: dict[str, Any] = {
        "label": pick["name"],
        "name": pick["name"],
        "brand": pick.get("brand") or None,
        "product_line": None,
        "variant": None,
        "size": _size_from_row({"pack_size": pick.get("pack_size"),
                                "catalog_name": pick["name"]}),
        "category": None,
        "is_organic": True if "bio" in fold(pick["name"]).split() else None,
        "eans": [article] if len(article) in _BARCODE_LENGTHS else [],
        "open_questions": brand_questions(pick.get("brand")),
        "provenance": {"attributes": f"{pick['source']}-listing",
                       "source": pick.get("url"), "decided_by": decided_by},
    }
    category = categorize.propose("new", product)
    if category.settled:
        product["category"] = category.key
    else:
        product["open_questions"].append(categorize.CATEGORY_UNKNOWN)
    return product


# --- deciders ---------------------------------------------------------------------


class DeciderError(Exception):
    pass


@dataclass
class Searched:
    """What one call searched the web for, and the titles of what came back,
    exactly as the search returned them."""

    queries: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)


def _claude_searches(events: list[dict[str, Any]]) -> Searched:
    """The WebSearch queries in a `claude -p` event stream, and the titles of
    the links each one returned."""
    searched = Searched()
    for event in events:
        content = (event.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_use" and block.get("name") == "WebSearch":
                searched.queries.append(str((block.get("input") or {}).get("query") or ""))
            if block.get("type") == "tool_result":
                text = block.get("content")
                if isinstance(text, list):
                    text = " ".join(str(part.get("text") or "") for part in text
                                    if isinstance(part, dict))
                start = str(text or "").find("Links: [")
                if start < 0:
                    continue
                try:
                    links, _ = json.JSONDecoder().raw_decode(str(text)[start + 7:])
                except ValueError:
                    continue
                searched.titles += [str(link.get("title") or "") for link in links
                                    if isinstance(link, dict) and link.get("title")]
    return searched


class ClaudeCodeDecider:
    """The model through `claude -p`, on the shopper's subscription.

    Every answer is cached under `<cache_dir>/claude-code-<model>/<prompt
    version>/<hash>.json`, keyed on the exact prompt, so re-running a score
    costs nothing until a candidate list or the prompt changes. It runs with
    no tools and from an empty directory, so nothing but the prompt reaches
    the model.
    """

    # One more try after a pause: on 2026-09-27 a scoring run stopped after
    # 76 of 135 lines on a single momentary "Not logged in", and the next
    # call worked. A second failure in a row is a real one and is raised.
    RETRY_AFTER_S = 20

    def __init__(self, model: str = "sonnet", cache_dir: str | Path = "data/matched",
                 timeout_s: int = 180, version: str = PROMPT_VERSION, search: bool = False):
        self.model = model
        # With search the same prompt can get another answer, so the answers
        # live apart: a cached answer never crosses from one setup to the other.
        self.cache = (Path(cache_dir) / f"claude-code-{model}{'-search' if search else ''}"
                      / version)
        self.timeout_s = timeout_s
        # `searches`: this decider may search the web (`identify.search_line`).
        self.searches = search
        self.last_search = Searched()

    def __call__(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        key = hashlib.sha256(json.dumps([self.model, system, prompt, schema],
                                        sort_keys=True).encode()).hexdigest()[:24]
        path = self.cache / f"{key}.json"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.last_search = Searched(saved.get("searched") or [], saved.get("titles") or [])
            return saved["answer"]
        try:
            answer, searched = self._ask(system, prompt, schema)
        except (DeciderError, subprocess.TimeoutExpired):
            time.sleep(self.RETRY_AFTER_S)
            answer, searched = self._ask(system, prompt, schema)
        self.last_search = searched
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"prompt": prompt, "answer": answer,
                                    "searched": searched.queries, "titles": searched.titles},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        return answer

    def _ask(self, system: str, prompt: str,
             schema: dict[str, Any]) -> tuple[dict[str, Any], Searched]:
        # No tools at all, or web search alone: never files, never a shell. With
        # search the output is a stream of events, so what was searched and
        # what came back can be recorded (`last_search`).
        tools = ["--tools", "WebSearch", "--allowedTools", "WebSearch",
                 "--output-format", "stream-json", "--verbose"] if self.searches \
            else ["--tools", "", "--output-format", "json"]
        command = ["claude", "-p", prompt, "--model", self.model, *tools,
                   "--no-session-persistence", "--system-prompt", system,
                   "--json-schema", json.dumps(schema)]
        with tempfile.TemporaryDirectory() as empty:
            done = subprocess.run(command, capture_output=True, text=True, cwd=empty,
                                  timeout=self.timeout_s, check=False)
        events = []
        for raw in done.stdout.splitlines():
            try:
                events.append(json.loads(raw))
            except ValueError:
                continue
        result = next((e for e in reversed(events) if e.get("type") == "result"
                       or "structured_output" in e or "is_error" in e), None)
        if result is None:
            raise DeciderError(f"claude -p gave no JSON: {done.stderr[:300]}")
        answer = result.get("structured_output")
        if result.get("is_error") or not isinstance(answer, dict):
            raise DeciderError(f"claude -p failed: {str(result.get('result'))[:300]}")
        return answer, _claude_searches(events)


def _json_in(text: str) -> dict[str, Any] | None:
    """The first JSON object in a model's text, fenced in ``` or not."""
    decoder = json.JSONDecoder()
    for start in [i for i, char in enumerate(text) if char == "{"]:
        try:
            found, _ = decoder.raw_decode(text[start:])
        except ValueError:
            continue
        if isinstance(found, dict):
            return found
    return None


class SearchBudgetExceeded(DeciderError):
    pass


class GeminiDecider:
    """Gemini through Google's API, with Google Search, paid per call.

    The same contract as `ClaudeCodeDecider`: (system, prompt, schema) -> the
    structured answer, cached under `<cache_dir>/gemini-<model>[-search]/
    <version>/`, so re-scoring costs nothing. The key is `GEMINI_API_KEY`.

    Searches cost money, so they are counted (what each call searched is kept
    in its cache file) and a run stops at `max_searches` rather than spend
    past what the shopper put in (Parham charged 5 EUR, 2026-10-01).

    Gemini does not search while it is asked for JSON, by a schema or in
    words (2026-10-02: the same request searched five times with no format
    and never with one; the v6 comparison's "Gemini with search" searched 2
    lines in 154 for this reason). So a decider that searches makes two
    calls: the search, answered in free text, then the same model without
    search copying that report into the schema (`COPY_INTO_FORMAT`).
    """

    COPY_INTO_FORMAT = ("Copy the report below into the JSON format you are given. Add "
                        "nothing that is not in the report, and leave out nothing it found.")

    def __init__(self, model: str, cache_dir: str | Path, version: str, search: bool = True,
                 max_searches: int = 150, api_key: str | None = None, timeout_s: int = 180):
        import os

        self.model = model
        self.cache = (Path(cache_dir) / f"gemini-{model}{'-search' if search else ''}"
                      / version)
        self.searches = search
        self.max_searches = max_searches
        self.searched = 0
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.timeout_s = timeout_s
        self.last_search = Searched()

    def __call__(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        key = hashlib.sha256(json.dumps([self.model, self.searches, system, prompt, schema]
                                        + (["free-text-then-copy"] if self.searches else []),
                                        sort_keys=True).encode()).hexdigest()[:24]
        path = self.cache / f"{key}.json"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.last_search = Searched(saved.get("searched") or [], saved.get("titles") or [])
            return saved["answer"]
        if self.searched >= self.max_searches:
            raise SearchBudgetExceeded(f"{self.searched} searches made; the limit is "
                                       f"{self.max_searches}")
        answer, searched, usage = self._ask(system, prompt, schema)
        self.searched += len(searched.queries)
        self.last_search = searched
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"prompt": prompt, "answer": answer,
                                    "searched": searched.queries, "titles": searched.titles,
                                    "usage": usage}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return answer

    def _ask(self, system: str, prompt: str,
             schema: dict[str, Any]) -> tuple[dict[str, Any], Searched, dict[str, Any]]:
        if not self.searches:
            data = self._post({"systemInstruction": {"parts": [{"text": system}]},
                               "contents": [{"parts": [{"text": prompt}]}],
                               "generationConfig": {"responseMimeType": "application/json",
                                                    "responseJsonSchema": schema}})
            return self._answer(data), Searched(), data.get("usageMetadata") or {}
        found = self._post({"systemInstruction": {"parts": [{"text": system}]},
                            "contents": [{"parts": [{"text": prompt}]}],
                            "tools": [{"google_search": {}}]})
        candidate = (found.get("candidates") or [{}])[0]
        grounding = candidate.get("groundingMetadata") or {}
        titles = [str((chunk.get("web") or {}).get("title") or "")
                  for chunk in grounding.get("groundingChunks") or []]
        searched = Searched(list(grounding.get("webSearchQueries") or []),
                            [title for title in titles if title])
        copied = self._post({"systemInstruction": {"parts": [{"text": self.COPY_INTO_FORMAT}]},
                             "contents": [{"parts": [{"text": self._text(found)}]}],
                             "generationConfig": {"responseMimeType": "application/json",
                                                  "responseJsonSchema": schema}})
        usage = {"search": found.get("usageMetadata") or {},
                 "copy": copied.get("usageMetadata") or {}}
        return self._answer(copied), searched, usage

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            return gemini.generate(self.model, body, self.api_key, self.timeout_s)
        except gemini.GeminiError as error:
            raise DeciderError(str(error)) from error

    _text = staticmethod(gemini.text_of)

    def _answer(self, data: dict[str, Any]) -> dict[str, Any]:
        text = self._text(data)
        answer = _json_in(text)
        if answer is None:
            raise DeciderError(f"Gemini gave no JSON: {text[:300]}")
        return answer
