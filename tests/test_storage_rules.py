"""Storage per product, checked against its rules, on made-up data (risk check, PR #207).

The rules, in words:

1. The offers thread asks a model, for each grocery product someone has bought
   and that has no storage answer yet, where it is kept until opened (`fridge`,
   `freezer`, `cupboard`) and how many days it keeps from the day bought (a
   whole number 1..3650). `storage_due(repository, decider, asked)` returns
   how many answers were kept. At most 20 products per model call; nothing due
   means no call.
2. A product with an answer is never asked again. A product given no usable
   answer is asked at most `offer_match.MOST_ASKS` times per `asked` counter.
3. The model is told only what the product is (name, brand, details, size):
   never a printed receipt line, a person, a shop, a postcode, a date or a price.
4. Only a place among the three and a whole number 1..3650 is kept; anything
   else counts as unanswered. Answers for ids not asked about are ignored.
   Nothing fills in a product with no usable answer.
5. A failed model call keeps nothing, and counts as unanswered (review of
   this PR: a batch the model keeps failing on is not paid for every hour).
6. Only products with a known grocery category are asked about, as only they
   reach the shopping list (`shopping_list.kinds` needs a category): not
   non-groceries, not an uncategorized product, not one nobody bought.
7. The kept answer reaches purchases.json (contract 10) as `storage` and
   `keeps_days` on each of that product's lines; no answer means both None.

Every decider here is a fake `(system, prompt, schema) -> dict`: no model is
reached. The fake reads the answer's shape from the schema it is handed, so
it assumes nothing about the code beyond the rule.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from grocery_app import offer_match, offers
from grocery_app.api import offers as offers_api
from grocery_app.api.app import create_app
from grocery_app.db.io import product_from_dict, receipt_from_dict, resolution_from_dict
from grocery_app.db.models import Product
from grocery_app.normalizer import build_purchases
from tests import test_offers
from tests.conftest import DATABASE_URL as URL
from tests.conftest import PRODUCTS
from tests.test_offers import FakeSite, raw_offer

# The owner buys milk p-0001, tulips p-0003 and uncategorized p-0004; Sara bananas p-0002.
history = test_offers.history

needs_db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")

ID = re.compile(r"\bp-\d{4}\b")
_ANSWER = object()  # the fake answers row by row (no raw reply given)


# --- the fake model ------------------------------------------------------------------

def _shape(schema):
    """(list key, id key, storage key, days key) of the answer the schema asks for."""
    for key, sub in (schema or {}).get("properties", {}).items():
        if sub.get("type") != "array":
            continue
        props = (sub.get("items") or {}).get("properties", {})
        storage = next((k for k, v in props.items() if "fridge" in json.dumps(v)), "storage")
        days = next((k for k, v in props.items()
                     if v.get("type") == "integer" and k != storage), "keeps_days")
        rest = [k for k in props if k not in (storage, days)]
        ident = next((k for k in rest if "id" in k or "product" in k), rest[0] if rest else "id")
        return key, ident, storage, days
    return "answers", "product", "storage", "keeps_days"


class Decider:
    """Answers every product id found in the prompt with `answer(pid)` -> (storage, days),
    or None to leave that product out. `extra` adds rows for ids never asked about;
    `raw` replies with that value verbatim."""

    def __init__(self, answer=lambda pid: ("fridge", 7), extra=(), raw=_ANSWER, raise_=None):
        self.answer, self.extra, self.raw, self.raise_ = answer, extra, raw, raise_
        self.calls: list[str] = []
        self.batches: list[list[str]] = []

    def is_storage(self, system, prompt, schema):
        return "fridge" in json.dumps(schema, default=str) or "fridge" in system + prompt

    def __call__(self, system, prompt, schema):
        if not self.is_storage(system, prompt, schema):
            return {"verdicts": []}  # the offers judge, in the thread test
        self.calls.append(f"{system}\n{prompt}\n{json.dumps(schema, default=str)}")
        ids = list(dict.fromkeys(ID.findall(prompt)))
        self.batches.append(ids)
        if self.raise_ is not None:
            raise self.raise_
        if self.raw is not _ANSWER:
            return self.raw
        key, ident, storage, days = _shape(schema)
        rows = []
        for pid in [*ids, *self.extra]:
            said = self.answer(pid)
            if said is not None:
                rows.append({ident: pid, storage: said[0], days: said[1]})
        return {key: rows}

    def asked(self):
        return Counter(pid for batch in self.batches for pid in batch)


def stored(session, pid):
    session.expire_all()
    product = session.get(Product, pid)
    return (product.storage, product.keeps_days)


# --- extra made-up purchases -----------------------------------------------------------

def add_product(session, pid, name, category="milch", **fields):
    session.add(product_from_dict(pid, {**PRODUCTS["products"]["p-0001"], "label": pid,
                                        "name": name, "category": category, **fields}))


def add_bought(session, items, store="Musterladen", location="Musterweg 1, 12345 Musterstadt",
               day="2026-10-20", price=1.0, user_id=None, image="extra.jpeg"):
    """One receipt with one line per (raw line, product id), each line resolved."""
    for raw, pid in items:
        session.add(resolution_from_dict({
            "store": store, "raw_name": raw, "line_type": "product", "product_id": pid,
            "confirmed_by": "test", "confirmed_at": "2026-01-01", "source": "test"}))
    session.flush()
    receipt = receipt_from_dict({
        "source_image": image, "store": store, "store_location": location, "date": day,
        "currency": "EUR",
        "lines": [{"type": "product", "raw_name": raw, "qty": 1, "gross": price,
                   "discount": 0.0, "net": price, "tax_class": "A"} for raw, _ in items]})
    receipt.user_id = user_id
    session.add(receipt)
    session.commit()


# --- 1, 2, 6: who is asked, how often, in what batches ----------------------------------

@needs_db
def test_each_bought_grocery_is_asked_and_its_answer_kept(history, session):
    repository, _ = history
    add_product(session, "p-0005", "Nie gekauft")  # a grocery nobody bought
    session.commit()
    decider = Decider()
    kept = offers_api.storage_due(repository, decider, Counter())
    assert set(decider.asked()) == {"p-0001", "p-0002"}, \
        "milk and bananas; never the tulips (not groceries), the uncategorized " \
        "p-0004 (not on any list until sorted) or p-0005 (never bought)"
    assert kept == 2
    for pid in ("p-0001", "p-0002"):
        assert stored(session, pid) == ("fridge", 7), pid
    for pid in ("p-0003", "p-0004", "p-0005"):
        assert stored(session, pid) == (None, None), pid


@needs_db
def test_a_product_with_an_answer_is_never_asked_again(history, session):
    repository, _ = history
    offers_api.storage_due(repository, Decider(), Counter())
    again = Decider()
    assert offers_api.storage_due(repository, again, Counter()) == 0
    assert again.calls == [], "nothing due: no model call at all"


@needs_db
def test_nothing_bought_means_no_model_call(engine, session):
    from grocery_app.api.repository import PostgresRepository
    from grocery_app.db.session import make_session_factory

    add_product(session, "p-0001", "Milch")
    session.commit()
    decider = Decider()
    repository = PostgresRepository(make_session_factory(engine))
    assert offers_api.storage_due(repository, decider, Counter()) == 0
    assert decider.calls == []


@needs_db
def test_products_are_asked_in_batches_of_at_most_twenty(history, session):
    repository, _ = history
    items = []
    for i in range(10, 56):  # 46 more bought groceries: 48 due in all
        pid = f"p-{i:04d}"
        add_product(session, pid, f"Ware {i}")
        items.append((f"WARE {i}", pid))
    session.commit()
    add_bought(session, items)
    decider = Decider()
    assert offers_api.storage_due(repository, decider, Counter()) == 48
    assert all(1 <= len(batch) <= 20 for batch in decider.batches), \
        [len(b) for b in decider.batches]
    assert len(decider.calls) == 3, "48 products in batches of 20 is three calls"
    assert max(decider.asked().values()) == 1, "each product once"


@needs_db
def test_a_product_without_a_usable_answer_is_asked_at_most_most_asks_times(history, session):
    repository, _ = history
    silent = Decider(answer=lambda pid: None if pid == "p-0001" else ("cupboard", 30))
    asked = Counter()
    for _ in range(offer_match.MOST_ASKS + 3):
        offers_api.storage_due(repository, silent, asked)
    assert silent.asked()["p-0001"] == offer_match.MOST_ASKS
    assert silent.asked()["p-0002"] == 1
    calls = len(silent.calls)
    offers_api.storage_due(repository, silent, asked)
    assert len(silent.calls) == calls, "once every product is answered or given up on, no call"
    assert stored(session, "p-0001") == (None, None)


@needs_db
def test_a_bad_answer_counts_as_unanswered_for_the_ask_limit(history, session):
    repository, _ = history
    bad = Decider(answer=lambda pid: ("pantry", 7))
    asked = Counter()
    for _ in range(offer_match.MOST_ASKS + 2):
        offers_api.storage_due(repository, bad, asked)
    assert max(bad.asked().values()) == offer_match.MOST_ASKS


# --- 3: what the model is told -------------------------------------------------------

@needs_db
def test_the_model_is_told_what_the_product_is_and_nothing_about_a_person(history, session):
    repository, _ = history
    zoltana = repository.create_user("Zoltana", "zoltana@example.com")
    add_product(session, "p-0042", "Bergkäse", brand="Alpenmuster", details=["gerieben"],
                size={"count": 1, "value": 200, "unit": "g"})
    session.commit()
    add_bought(session, [("QX ZAUBERKAESE", "p-0042")], store="Seltenladen",
               location="Rarweg 9, 67890 Rarstadt", day="2026-09-13", price=4.83,
               user_id=zoltana["id"], image="z.jpeg")
    decider = Decider()
    offers_api.storage_due(repository, decider, Counter())
    text = "\n".join(decider.calls)
    for told in ("Bergkäse", "Alpenmuster", "gerieben", "200"):
        assert told in text, f"what the product is: {told}"
    leaks = ["QX ZAUBERKAESE", "ZAUBERKAESE", "MU Milch", "Raetsel", "Zoltana",
             "zoltana@example.com", zoltana["password"], "Sara", "Seltenladen", "Musterladen",
             "Rarweg", "Rarstadt", "Musterweg", "Beispielweg", "67890", "12345", "54321",
             "99999", "2026-09-13", "13.09.2026", "2026-10", "4.83", "4,83"]
    if len(str(zoltana["id"])) > 3:
        leaks.append(str(zoltana["id"]))
    for leak in leaks:
        assert leak not in text, leak


# --- 4: what is kept ---------------------------------------------------------------

@pytest.mark.parametrize("place, days", [
    ("fridge", 1), ("freezer", 3650), ("cupboard", 365)])
@needs_db
def test_a_clean_answer_is_kept_as_given(history, session, place, days):
    repository, _ = history
    offers_api.storage_due(repository, Decider(answer=lambda pid: (place, days)), Counter())
    assert stored(session, "p-0001") == (place, days)


@pytest.mark.parametrize("place, days", [
    ("Fridge", 7), ("pantry", 7), ("", 7), (None, 7), (3, 7), ("fridge ", 7),
    ("fridge", 0), ("fridge", -1), ("fridge", 3651), ("fridge", 1.5), ("fridge", "7"),
    ("fridge", None), ("fridge", True), ("fridge", 10**12)])
@needs_db
def test_anything_else_is_dropped_and_nothing_filled_in(history, session, place, days):
    repository, _ = history
    kept = offers_api.storage_due(repository, Decider(answer=lambda pid: (place, days)),
                                  Counter())
    assert kept == 0
    for pid in ("p-0001", "p-0002", "p-0004"):
        assert stored(session, pid) == (None, None), (pid, place, days)


@needs_db
def test_an_answer_for_a_product_not_asked_about_is_ignored(history, session):
    repository, _ = history
    add_product(session, "p-0005", "Nie gekauft")
    session.commit()
    nosy = Decider(answer=lambda pid: ("freezer", 90), extra=("p-0003", "p-0005", "p-9999"))
    offers_api.storage_due(repository, nosy, Counter())
    assert not {"p-0003", "p-0005"} & set(nosy.asked())
    assert stored(session, "p-0003") == (None, None), "tulips were not asked about"
    assert stored(session, "p-0005") == (None, None), "nobody bought p-0005"
    session.expire_all()
    assert session.get(Product, "p-9999") is None, "no product made up from an answer"


@needs_db
def test_one_bad_row_does_not_spoil_the_others(history, session):
    repository, _ = history
    mixed = Decider(answer=lambda pid: ("fridge", 0) if pid == "p-0002" else ("fridge", 7))
    assert offers_api.storage_due(repository, mixed, Counter()) == 1, "milk"
    assert stored(session, "p-0001") == ("fridge", 7)
    assert stored(session, "p-0002") == (None, None)


# --- 5: a failed or hostile call -------------------------------------------------------

HOSTILE = {
    "raises": dict(raise_=RuntimeError("model down")),
    "times out": dict(raise_=TimeoutError("slow")),
    "None": dict(raw=None),
    "a string": dict(raw="fridge"),
    "a list": dict(raw=[{"product": "p-0001", "storage": "fridge", "keeps_days": 7}]),
    "rows not a list": dict(raw={"answers": "fridge", "storage": "fridge"}),
    "rows of junk": dict(raw={"answers": [1, None, "x", []], "storage": [1, None]}),
}


@pytest.mark.parametrize("kind", sorted(HOSTILE))
@needs_db
def test_a_failed_or_hostile_call_keeps_nothing(history, session, kind):
    repository, _ = history
    decider = Decider(**HOSTILE[kind])
    try:
        kept = offers_api.storage_due(repository, decider, Counter())
    except Exception:
        kept = 0  # said plainly; the thread must contain it (tested below)
    assert decider.calls, "the model was asked"
    assert kept == 0
    for pid in ("p-0001", "p-0002", "p-0003", "p-0004"):
        assert stored(session, pid) == (None, None), pid


# --- 1, 2 on the thread itself -----------------------------------------------------------

def _run_thread(repository, decider, until, seconds=10):
    class Stop(BaseException):
        pass

    stop = threading.Event()

    def guarded(system, prompt, schema):
        if stop.is_set():
            raise Stop()
        return decider(system, prompt, schema)

    real = offers_api.PAUSE_BETWEEN_SEARCHES_S
    offers_api.PAUSE_BETWEEN_SEARCHES_S = 0
    thread = threading.Thread(target=offers_api.keep_fetching,
                              args=(repository, offers.Marktguru(FakeSite([raw_offer()]))),
                              kwargs={"judge": guarded, "every": 0.05}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + seconds
        while not until() and time.monotonic() < deadline:
            time.sleep(0.05)
        return thread.is_alive()
    finally:
        stop.set()
        thread.join(timeout=5)
        offers_api.PAUSE_BETWEEN_SEARCHES_S = real


@needs_db
def test_the_offers_thread_asks_and_keeps_storage(history, session):
    repository, _ = history
    decider = Decider()
    alive = _run_thread(repository, decider, lambda: stored(session, "p-0001")[0] is not None)
    assert alive
    assert stored(session, "p-0001") == ("fridge", 7)
    assert stored(session, "p-0003") == (None, None)


@needs_db
def test_the_offers_thread_gives_up_on_a_product_it_gets_no_answer_for(history, session):
    """Money: a model that never answers usably is not asked pass after pass."""
    repository, _ = history
    useless = Decider(answer=lambda pid: ("pantry", 7))
    passes = []
    real_fetch = offers_api.fetch_due

    def counting(*a, **k):
        passes.append(1)
        return real_fetch(*a, **k)

    offers_api.fetch_due = counting
    try:
        alive = _run_thread(repository, useless, lambda: len(passes) >= 3 * offer_match.MOST_ASKS
                            + 5, seconds=8)
    finally:
        offers_api.fetch_due = real_fetch
    assert alive
    assert len(passes) > offer_match.MOST_ASKS + 1, "enough passes to show a leak"
    assert useless.asked(), "storage was asked about at all"
    assert max(useless.asked().values()) <= offer_match.MOST_ASKS, useless.asked()


@needs_db
def test_the_offers_thread_survives_a_storage_model_that_fails(history, session):
    repository, _ = history
    failing = Decider(raise_=RuntimeError("model down"))
    alive = _run_thread(repository, failing, lambda: len(failing.calls) >= 2, seconds=5)
    assert alive, "the thread died on a failing storage call"
    assert failing.calls, "storage was asked about at all"
    assert stored(session, "p-0001") == (None, None)


# --- 7: purchases.json ----------------------------------------------------------------

@needs_db
def test_the_answer_reaches_every_line_of_that_product_for_everyone(history, session):
    repository, sara = history
    offers_api.storage_due(
        repository, Decider(answer=lambda pid: None if pid == "p-0004" else ("fridge", 7)),
        Counter())
    client = TestClient(create_app(repository, token="owner-secret"))
    mine = client.get("/v1/purchases", headers={"Authorization": "Bearer owner-secret"}).json()
    hers = client.get("/v1/purchases",
                      headers={"Authorization": f"Bearer {sara['password']}"}).json()
    assert mine["contract_version"] == 11 and hers["contract_version"] == 11
    lines = mine["purchases"] + hers["purchases"]
    by = {pid: [p for p in lines if p.get("product_id") == pid]
          for pid in ("p-0001", "p-0002", "p-0003", "p-0004")}
    assert len(by["p-0001"]) == 4 and len(by["p-0002"]) >= 3, "the fixture's lines"
    for pid in ("p-0001", "p-0002"):
        assert {(p["storage"], p["keeps_days"]) for p in by[pid]} == {("fridge", 7)}, pid
    for pid in ("p-0003", "p-0004"):
        assert by[pid], pid
        assert {(p.get("storage"), p.get("keeps_days")) for p in by[pid]} == {(None, None)}, pid


def test_the_file_pipeline_is_contract_ten_with_no_storage_made_up(data):
    purchases = build_purchases(data / "receipts" / "truth",
                                data / "products" / "products.json",
                                data / "products" / "resolution.json",
                                None, data / "products")
    assert purchases["contract_version"] == 11
    assert all(p.get("storage") is None and p.get("keeps_days") is None
               for p in purchases["purchases"]), "no answer in the catalog: nothing filled in"
