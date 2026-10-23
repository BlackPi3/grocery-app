"""The shops' weekly offers (Angebote), read into a record of our own.

The owner, 2026-10-23: show the user an offer for something they buy, in a
Home tile for the coming week, refreshed when each chain puts out its new
offers. This module is the reading half: where offers come from, what one
offer says, and on which day of the week each chain is seen to publish.
Matching offers to what a person buys comes after, on top of this.

**Where they come from.** marktguru.de collects the flyers of Lidl,
Kaufland, EDEKA, REWE, PENNY, ALDI SÜD, Netto and some local chains, by
postcode, for this week and the next (tested 2026-10-15). Its interface is
not official: the keys the site's own page uses are read from that page's
embedded config, as the site does. Fine for finding out whether offers save
a shopper money; a paid app needs a licence (marktguru/Bonial) or must read
the flyers itself. GLOBUS and ALDI Nord are not on it.

**What is sent.** A search word (a product's name, never a receipt line or
anything about the shopper) and a shop's postcode. Nothing else.

**What one offer says** (`read_offer`): the chain, brand, product, the
flyer's description, the price, the price before if the flyer gives one,
the pack (`amount` of `unit`, `count` packs) and the price per unit, the
days it is valid (in Germany's time: the source gives UTC), and whether it
needs the chain's loyalty card. On every offer read so far, price ÷ (amount
× count) is the price per unit, so the three are kept as given, and the
price per unit is worked out that way when the source leaves it out.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

SOURCE = "marktguru"
HOME_URL = "https://www.marktguru.de/"
SEARCH_URL = "https://api.marktguru.de/api/v1/offers/search"
# Names the app, not who runs it: the first searches are the owner's, and a
# link to his account would tie them to where he shops.
USER_AGENT = "Mozilla/5.0 (compatible; grocery-app)"
GERMANY = ZoneInfo("Europe/Berlin")
PAGE = 100  # the most one search answer holds
TIMEOUT_S = 20
# An answer of 100 offers is about 200 KB; one past these is not an answer.
MAX_ANSWER_BYTES = 8 << 20
MAX_ANSWER_S = 60


class OffersUnavailable(Exception):
    """The source could not be asked, or answered something unreadable."""


# --- one offer -----------------------------------------------------------------

def _local_day(stamp: str) -> date:
    """`2026-10-18T22:00:00Z` is Monday the 19th in Germany."""
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(GERMANY).date()


def _name(part: dict[str, Any] | None) -> str | None:
    return (part or {}).get("name") or None


def _per_unit(raw: dict[str, Any], unit: str | None, amount: float | None,
              count: float | None) -> dict[str, Any] | None:
    """The source's price per unit, or the price over the pack when it gives
    none: an offer whose pack is known is never left without one."""
    if not unit:
        return None
    if raw.get("referencePrice"):
        return {"amount": raw["referencePrice"], "per": unit}
    if amount and raw.get("price"):
        return {"amount": round(raw["price"] / (amount * (count or 1)), 2), "per": unit}
    return None


def read_offer(raw: dict[str, Any]) -> dict[str, Any] | None:
    """One marktguru search result as our record, or None for one that is no
    use: no chain, no price, no dates, or not in the shape it should be. One
    odd offer is skipped, never the answer it came in."""
    try:
        return _read_offer(raw)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return None


# The source's brand for an offer with none (`thisisnobrand123`, seen
# 2026-10-23 on loose carrots and tomatoes): no brand, not one to show.
_NO_BRAND = re.compile(r"thisisnobrand", re.IGNORECASE)


def brand_of(name: str | None) -> str | None:
    return None if not name or _NO_BRAND.match(name) else name


def _read_offer(raw: dict[str, Any]) -> dict[str, Any] | None:
    advertisers = raw.get("advertisers") or []
    validity = raw.get("validityDates") or []
    if not advertisers or raw.get("price") is None or not validity:
        return None
    unit = (raw.get("unit") or {}).get("shortName")
    amount, count = raw.get("volume"), raw.get("quantity")
    return {
        "source": SOURCE,
        "id": str(raw["id"]),
        "chain": advertisers[0]["name"],
        "brand": brand_of(_name(raw.get("brand"))),
        "product": _name(raw.get("product")),
        "description": (raw.get("description") or "").strip() or None,
        "category": _name((raw.get("categories") or [None])[0]),
        "price": raw["price"],
        "price_before": raw.get("oldPrice"),
        "pack": {"amount": amount, "unit": unit, "count": count} if amount and unit else None,
        "per_unit": _per_unit(raw, unit, amount, count),
        "valid_from": min(_local_day(v["from"]) for v in validity).isoformat(),
        "valid_to": max(_local_day(v["to"]) for v in validity).isoformat(),
        "loyalty_card": bool(raw.get("requiresLoyalityMembership")),
    }


# --- what to search for --------------------------------------------------------

_POSTCODE = re.compile(r"(?<!\d)(\d{5})\s+(?=[^\W\d_])")


def postcode_of(store_location: str | None) -> str | None:
    """The German postcode in a receipt's printed address, if there is one:
    five digits followed by the town's name. A phone number or a house
    number has no town after it."""
    found = _POSTCODE.search(store_location or "")
    return found[1] if found else None


def shopping_postcodes(locations: Iterable[str | None], most: int = 3) -> list[str]:
    """Where a person shops: the postcodes of their receipts, most visits
    first, at most `most`. A postcode seen once counts only when it is the
    only one (a single receipt is still somewhere they shop)."""
    counts = Counter(p for p in map(postcode_of, locations) if p)
    ranked = [p for p, n in counts.most_common() if n >= 2] or [
        p for p, _ in counts.most_common(1)]
    return ranked[:most]


_BRACKETS = re.compile(r"\([^)]*\)")
# A size or a count: a number, perhaps `6 x 1,5`, and the unit after it.
_SIZE = re.compile(r"(?<!\w)\d+(?:[.,]\d+)?(?:\s*[x×]\s*\d+(?:[.,]\d+)?)?\s*"
                   r"(?:kg|g|mg|ml|cl|l|ltr|liter|stk|stück|st|er|pack|pck|%)?(?!\w)",
                   re.IGNORECASE)
_NOT_A_WORD = re.compile(r"\b\w*\d\w*\b|[%,;/]")


def search_word(name: str | None) -> str | None:
    """The words a product's name is searched by: without its sizes, counts
    and the bracketed English the first catalog added.
    `Saatenbrötchen 3er (3x 1,000 Stück)` is searched as `Saatenbrötchen`,
    `Mineralwasser 6 x 1,5 l` as `Mineralwasser`."""
    bare = _NOT_A_WORD.sub(" ", _SIZE.sub(" ", _BRACKETS.sub(" ", name or "")))
    words = " ".join(bare.split())
    return words if len(words) >= 3 else None


# --- the source ------------------------------------------------------------------

Fetch = Callable[[str, dict[str, str]], bytes]


def http_get(url: str, headers: dict[str, str]) -> bytes:
    """The body at `url`, read in pieces: one too large, or too slow in
    coming, is an error rather than the server's memory or its thread."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    started, body = time.monotonic(), bytearray()
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        while piece := response.read(1 << 16):
            body += piece
            if len(body) > MAX_ANSWER_BYTES:
                raise OSError(f"answer over {MAX_ANSWER_BYTES} bytes")
            if time.monotonic() - started > MAX_ANSWER_S:
                raise OSError(f"answer took over {MAX_ANSWER_S} s")
    return bytes(body)


_CONFIG_KEYS = re.compile(r'"apiKey":"([^"]+)","clientKey":"([^"]+)"')


class Marktguru:
    """Offers by search word and postcode. `fetch` is how a URL is read: the
    network by default, a fake in tests."""

    def __init__(self, fetch: Fetch = http_get) -> None:
        self.fetch = fetch
        self._keys: tuple[str, str] | None = None

    def keys(self) -> tuple[str, str]:
        """The keys the site's own page sends, read from its config once."""
        if self._keys is None:
            try:
                page = self.fetch(HOME_URL, {}).decode("utf-8", "replace")
            except OSError as exc:
                raise OffersUnavailable(f"marktguru's page did not load: {exc}") from exc
            found = _CONFIG_KEYS.search(page)
            if not found:
                raise OffersUnavailable("marktguru's page no longer carries its keys")
            self._keys = (found[1], found[2])
        return self._keys

    def search(self, word: str, postcode: str, most: int = 300) -> list[dict[str, Any]]:
        """Every offer the source finds for `word` near `postcode`, read
        (`read_offer`), up to `most`."""
        api_key, client_key = self.keys()
        headers = {"x-apikey": api_key, "x-clientkey": client_key}
        found: list[dict[str, Any]] = []
        offset = 0
        while offset < most:
            query = urllib.parse.urlencode({"as": "web", "q": word, "zipCode": postcode,
                                            "limit": PAGE, "offset": offset})
            try:
                answer = json.loads(self.fetch(f"{SEARCH_URL}?{query}", headers))
                results = answer.get("results") or []
                if not isinstance(results, list) or not all(
                        isinstance(r, dict) for r in results):
                    raise ValueError("results are not a list of offers")
                total = int(answer.get("totalResults") or 0)
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                self._keys = None  # keys can change; read them again next time
                raise OffersUnavailable(f"searching {word!r} failed: {exc}") from exc
            found.extend(o for o in map(read_offer, results) if o)
            offset += PAGE
            if len(results) < PAGE or offset >= total:
                break
        return found


# --- when each chain publishes ------------------------------------------------------

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def rhythm(seen: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """For each chain, on which weekday its offers are first seen, and how
    many days before they start.

    `seen` holds one row per offer: `chain`, `valid_from` (a date) and
    `first_seen` (a datetime). An offer already running when first seen
    says nothing about when it was published (the server may simply not
    have looked before), so only offers first seen before their first day
    count. The tile refreshes on the weekday most of a chain's offers
    appear (`usual_day`)."""
    by_chain: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for row in seen:
        first = row["first_seen"]
        first_day = (first.astimezone(GERMANY) if first.tzinfo else
                     first.replace(tzinfo=UTC).astimezone(GERMANY)).date()
        ahead = (row["valid_from"] - first_day).days
        if ahead > 0:
            by_chain[row["chain"]].append((first_day.weekday(), ahead))
    out = []
    for chain, rows in sorted(by_chain.items()):
        days = Counter(weekday for weekday, _ in rows)
        usual, _ = days.most_common(1)[0]
        aheads = sorted(ahead for weekday, ahead in rows if weekday == usual)
        out.append({
            "chain": chain,
            "offers": len(rows),
            "usual_day": WEEKDAYS[usual],
            "days_ahead": aheads[len(aheads) // 2],
            "by_day": {WEEKDAYS[d]: n for d, n in sorted(days.items())},
        })
    return out
