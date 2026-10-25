"""The supermarkets near the shops a person uses.

The owner, 2026-10-25: "the stores I buy from are known. You can just look
for stores nearby." An Aldi or a Lidl close to where someone shops counts
for comparing the shopping list's cost, even if they never go there. This
module is the finding half: where a receipt's shop is, and which
supermarkets are around it. Pricing the list at each comes after.

**Where from.** OpenStreetMap, free. Nominatim turns a shop's printed
address into a point, asked by street and postcode, which copes with the
receipts' spellings (`Fischbachstr. 121 - 66125 Sbr.-Dudweiler` is found);
Overpass lists every supermarket within `RADIUS_M` of that point, with its
chain (`brand`) where the map has one. Their usage rules: name the app, at
most one request a second.

**What is sent.** A shop's street and postcode as its receipt prints them,
then that shop's point on the map. Nothing about the person.
"""

from __future__ import annotations

import functools
import json
import math
import re
import urllib.parse
from collections import Counter
from collections.abc import Iterable
from typing import Any

from grocery_app.offers import Fetch, http_get, postcode_of

LOCATE_URL = "https://nominatim.openstreetmap.org/search"
AROUND_URL = "https://overpass-api.de/api/interpreter"
# Around one shop. Tried on the owner's GLOBUS (2026-10-25): two Aldi, two
# Lidl, two EDEKA and a Netto within 3 km. How far a saving is worth going
# is decided on the list's numbers, from the distances kept.
RADIUS_M = 3000
# Overpass took 30-40 s for any question on 2026-10-25 (a busy day; its
# answers come in under a second when it is not). The look runs in the
# background, so waiting is cheap.
WAIT_S = 90
# Overpass turns away a browser's name (406 to the offers' `Mozilla/5.0
# (compatible; grocery-app)`, 2026-10-25). The app's name, not who runs it.
USER_AGENT = "grocery-app/1.0"


class MapUnavailable(Exception):
    """The map could not be asked, or answered something unreadable."""


# --- where a shop is -------------------------------------------------------------

# Where a printed address splits: `Markthalle Dudweiler, Fischbachstr. 121 -
# 66125 Sbr.-Dudweiler` is a name, a street and a town.
_PARTS = re.compile(r"\s*(?:[,;]|\s-\s)\s*")
# A street ends in its house number: `121`, `1 A`, `86-90`, `3b`.
_STREET = re.compile(r"^(?=.*[^\W\d_]{3}).*\d+(?:\s?[a-zA-Z])?(?:\s?-\s?\d+[a-zA-Z]?)?$")


def address_of(store_location: str | None) -> dict[str, Any] | None:
    """A receipt's printed address as `street` and `postcode`, or None
    without a postcode. The street is the part before the postcode that ends
    in a house number; a motorway services' `Bundesautobahn A1 West` has
    none, and is found by its postcode alone."""
    postcode = postcode_of(store_location)
    if not postcode:
        return None
    before = (store_location or "").split(postcode, 1)[0]
    streets = [p for p in _PARTS.split(before) if _STREET.match(p)]
    return {"street": " ".join(streets[-1].split()) if streets else None,
            "postcode": postcode}


def place_key(address: dict[str, Any]) -> str:
    """One shop however its receipts space or case it: `66125 fischbachstr. 121`."""
    return f"{address['postcode']} {(address['street'] or '').casefold()}".strip()


def shopping_places(locations: Iterable[str | None], most: int = 3) -> list[dict[str, Any]]:
    """The shops a person goes to, by their receipts' addresses, most visits
    first, at most `most`; as for the offers' postcodes, a shop seen once
    counts only when it is the only one."""
    addresses = [a for a in map(address_of, locations) if a]
    counts = Counter(place_key(a) for a in addresses)
    first = {}
    for address in addresses:
        first.setdefault(place_key(address), address)
    ranked = [k for k, n in counts.most_common() if n >= 2] or [
        k for k, _ in counts.most_common(1)]
    return [first[k] for k in ranked[:most]]


# --- what is around it ---------------------------------------------------------------

def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """As the crow flies, in metres."""
    rad = math.radians
    a = (math.sin(rad(lat2 - lat1) / 2) ** 2
         + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(rad(lon2 - lon1) / 2) ** 2)
    return round(2 * 6_371_000 * math.asin(math.sqrt(a)))


def read_store(element: dict[str, Any], lat: float, lon: float) -> dict[str, Any] | None:
    """One supermarket from the map as our record, its distance from the
    shop at (`lat`, `lon`); None for one with no place or no name. `chain`
    is the map's brand, None for an independent shop."""
    try:
        tags = element.get("tags") or {}
        here = element if "lat" in element else element["center"]
        name = tags.get("name") or tags.get("brand")
        if not name:
            return None
        street = " ".join(p for p in (tags.get("addr:street"), tags.get("addr:housenumber")) if p)
        town = " ".join(p for p in (tags.get("addr:postcode"), tags.get("addr:city")) if p)
        return {
            "osm_id": f"{element['type']}/{element['id']}",
            "chain": tags.get("brand") or None,
            "name": name,
            "address": ", ".join(p for p in (street, town) if p) or None,
            "lat": float(here["lat"]),
            "lon": float(here["lon"]),
            "distance_m": distance_m(lat, lon, float(here["lat"]), float(here["lon"])),
        }
    except (KeyError, TypeError, ValueError):
        return None


class OpenStreetMap:
    """Where an address is, and the supermarkets around a point. `fetch` is
    how a URL is read: the network by default, a fake in tests."""

    def __init__(self, fetch: Fetch | None = None) -> None:
        self.fetch = fetch or functools.partial(http_get, timeout=WAIT_S, most_s=WAIT_S)

    def _ask(self, url: str) -> Any:
        try:
            return json.loads(self.fetch(url, {"User-Agent": USER_AGENT}))
        except (OSError, ValueError) as exc:
            raise MapUnavailable(f"the map did not answer: {exc}") from exc

    def locate(self, address: dict[str, Any]) -> tuple[float, float] | None:
        """The point of a shop's address, or None when the map knows no such
        place (the same question will not find it tomorrow either)."""
        query = {"postalcode": address["postcode"], "countrycodes": "de",
                 "format": "jsonv2", "limit": 1}
        if address.get("street"):
            query["street"] = address["street"]
        found = self._ask(f"{LOCATE_URL}?{urllib.parse.urlencode(query)}")
        if not isinstance(found, list):
            raise MapUnavailable("the address search answered no list")
        if not found:
            return None
        try:
            return float(found[0]["lat"]), float(found[0]["lon"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MapUnavailable(f"the address search answered no point: {exc}") from exc

    def around(self, lat: float, lon: float, radius: int = RADIUS_M) -> list[dict[str, Any]]:
        """Every supermarket within `radius` metres, nearest first."""
        # Discounters are `shop=supermarket` on the map too: around the
        # owner's GLOBUS, both Aldi, both Lidl and the Netto.
        query = (f"[out:json][timeout:{WAIT_S}];nwr[shop=supermarket]"
                 f"(around:{radius},{lat},{lon});out center tags;")
        answer = self._ask(f"{AROUND_URL}?{urllib.parse.urlencode({'data': query})}")
        elements = answer.get("elements") if isinstance(answer, dict) else None
        if not isinstance(elements, list):
            raise MapUnavailable("the map answered no list of places")
        stores = [s for s in (read_store(e, lat, lon) for e in elements
                              if isinstance(e, dict)) if s]
        return sorted(stores, key=lambda s: (s["distance_m"], s["osm_id"]))


def chains_near(stores: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """For each chain, its branch nearest any of the person's shops, nearest
    first; an independent shop is its own. `stores` are `read_store`
    records, each with `from`: the shop it was found near."""
    nearest: dict[str, dict[str, Any]] = {}
    for store in stores:
        key = (store["chain"] or store["osm_id"]).casefold()
        if key not in nearest or store["distance_m"] < nearest[key]["distance_m"]:
            nearest[key] = store
    return sorted(nearest.values(), key=lambda s: (s["distance_m"], s["name"]))
