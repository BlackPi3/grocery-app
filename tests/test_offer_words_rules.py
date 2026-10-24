"""Flyer words, checked against their rules, on made-up data (risk check).

The rules, in words (owner, 2026-10-23):

1. The offers thread asks a model, for each grocery product someone bought
   that has no flyer word yet, for the word a German flyer lists that kind of
   product under (owner, 2026-10-24: the word also names the item on the
   shopping list, so every product bought is named, not only the regulars)
   (`word_due(repository, decider, today, asked)`, returning how many
   words were kept). A product with a word (`products.offer_word`) is never
   asked again. A product given no usable word is asked at most
   `offer_match.MOST_ASKS` times per `asked` counter. When nothing is due, no
   model call is made.
2. The model is told only about the product (name, brand, details, size):
   never a receipt line's printed text, a person's name or id, a shop, a
   postcode or a price.
3. A word is kept only if it is 3-40 characters, at most three words, and has
   no numbers; anything else is dropped (and counts as unanswered). A word for
   a product id that was not asked about is ignored.
4. marktguru receives only the search word and a shop postcode: the flyer word
   when there is one, otherwise the name without sizes. Nothing about the person.
5. A failed naming call keeps no words and does not stop that pass's searches.
6. A word made for one person's regular is used for everyone who buys it; no
   person's data goes into it.

Every model and every site here is a fake: nothing leaves the machine.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
from collections import Counter
from datetime import UTC, date, datetime, timedelta

import pytest

from grocery_app import offer_match, offers
from grocery_app.api import offers as offers_api
from tests.conftest import DATABASE_URL as URL

needs_db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")

TODAY = date.today()
OWNER_SHOP = ("Musterladen", "Musterweg 17, 12345 Musterstadt")
SARAS_SHOP = ("Beispielmarkt", "Beispielallee 3, 54321 Beispielstadt")
OLD_SHOP = ("Altladen", "Altgasse 2, 99999 Altstadt")

#        id         name                  brand        details          size              category
PRODUCTS = [
    ("p-milch", "Alpenmilch 1,5%", "Musterhof", ["laktosefrei"],
     {"count": 1, "value": 1.0, "unit": "l"}, "milch"),
    ("p-gurke", "Gewürzgurken 670 g", None, [], {"count": 1, "value": 670, "unit": "g"},
     "gurken"),
    ("p-rosen", "Rosen", None, [], None, "blumen"),        # owner's regular, not a grocery
    ("p-quark", "Quark", "Musterhof", [], None, "quark"),   # Sara, once only
    ("p-hafer", "Haferdrink", None, [], None, "pflanzendrink"),  # 3 days, long ago
]
RAW = {"p-milch": "MHF ALPMI LF", "p-gurke": "BSP GURK GLAS", "p-rosen": "ROSEN BUND",
       "p-quark": "BSP QUARK MAG", "p-hafer": "ALT HAFERDR"}
PRICE = {"p-milch": 1.37, "p-gurke": 2.43, "p-rosen": 4.21, "p-quark": 0.89,
         "p-hafer": 1.99}


def days(*ago):
    return [(TODAY - timedelta(days=d)).isoformat() for d in ago]


def add_receipt(session, shop, user_id, day, pids):
    from grocery_app.db.io import receipt_from_dict

    store, location = shop
    receipt = receipt_from_dict({
        "source_image": f"{store}-{user_id}-{day}-{pids[0]}.jpeg", "transcribed_by": "llm",
        "store": store, "store_location": location, "date": day, "time": "10:00",
        "currency": "EUR", "printed_total": round(sum(PRICE[p] for p in pids), 2),
        "lines": [{"type": "product", "raw_name": RAW[p], "qty": 1, "gross": PRICE[p],
                   "discount": 0.0, "net": PRICE[p], "tax_class": "A"} for p in pids]})
    receipt.user_id = user_id
    session.add(receipt)


@pytest.fixture
def people(engine, session):
    """The owner buys milk and roses at 12345; Sara buys gherkins at 54321 and
    quark once; the owner bought oat drink at 99999 long ago."""
    from grocery_app.api.repository import PostgresRepository
    from grocery_app.db.io import product_from_dict, resolution_from_dict
    from grocery_app.db.session import make_session_factory

    for pid, name, brand, details, size, category in PRODUCTS:
        session.add(product_from_dict(pid, {
            "label": pid, "name": name, "brand": brand, "details": details, "size": size,
            "category": category, "is_organic": False, "eans": [], "open_questions": [],
            "provenance": {"attributes": "test", "source": "test"}}))
    for store, _ in (OWNER_SHOP, SARAS_SHOP, OLD_SHOP):
        for pid, raw in RAW.items():
            session.add(resolution_from_dict({
                "store": store, "raw_name": raw, "line_type": "product", "product_id": pid,
                "confirmed_by": "test", "confirmed_at": "2026-01-01", "source": "test"}))
    session.commit()
    repository = PostgresRepository(make_session_factory(engine))
    sara = repository.create_user("Sara", "sara@example.com")
    for day in days(3, 10, 17):
        add_receipt(session, OWNER_SHOP, None, day, ["p-milch", "p-rosen"])
    for day in days(4, 11, 18):
        add_receipt(session, SARAS_SHOP, sara["id"], day, ["p-gurke"])
    add_receipt(session, SARAS_SHOP, sara["id"], days(4)[0], ["p-quark"])
    for day in days(200, 207, 214):
        add_receipt(session, OLD_SHOP, None, day, ["p-hafer"])
    session.commit()
    return repository, sara


class Namer:
    """Answers `words` for the products named in the prompt; records every call."""

    def __init__(self, words=None, raw_answer=None):
        self.words, self.raw_answer, self.calls = words or {}, raw_answer, []

    def __call__(self, system, prompt, schema):
        self.calls.append((system, prompt, schema))
        if self.raw_answer is not None:
            return self.raw_answer
        return {"words": [{"product": p, "word": w} for p, w in self.words.items()
                          if f"Product {p}:" in prompt]}

    def asked_about(self, n=-1):
        return {p for p, *_ in PRODUCTS if f"Product {p}:" in self.calls[n][1]}


def word_of(session, pid):
    from grocery_app.db.models import Product

    session.expire_all()
    return session.get(Product, pid).offer_word


def set_word(session, pid, word):
    from grocery_app.db.models import Product

    session.get(Product, pid).offer_word = word
    session.commit()


# --- 1: who is asked, how often, and when not at all ---------------------------------

@needs_db
def test_each_grocery_bought_without_a_word_is_asked_and_only_those(people, session):
    repository, _ = people
    namer = Namer({"p-milch": "H-Milch", "p-gurke": "Gewürzgurken", "p-quark": "Quark"})
    assert offers_api.word_due(repository, namer, TODAY, Counter()) == 3
    assert len(namer.calls) == 1, "one batched call"
    assert namer.asked_about(0) == {"p-milch", "p-gurke", "p-quark", "p-hafer"}, \
        "every grocery anyone bought, a one-off and one from long ago too; not roses"
    assert (word_of(session, "p-milch"), word_of(session, "p-gurke")) == (
        "H-Milch", "Gewürzgurken")


@needs_db
def test_a_product_with_a_word_is_never_asked_again_even_after_a_restart(people, session):
    repository, _ = people
    set_word(session, "p-milch", "H-Milch")
    namer = Namer({"p-milch": "Vollmilch"})
    offers_api.word_due(repository, namer, TODAY, Counter())
    offers_api.word_due(repository, namer, TODAY, Counter())
    assert all("p-milch" not in prompt for _, prompt, _ in namer.calls)
    assert word_of(session, "p-milch") == "H-Milch"


@needs_db
def test_an_unanswered_product_is_asked_at_most_most_asks_times_per_counter(people, session):
    repository, _ = people
    silent = Namer()
    asked: Counter = Counter()
    for _ in range(offer_match.MOST_ASKS + 3):
        assert offers_api.word_due(repository, silent, TODAY, asked) == 0
    assert len(silent.calls) == offer_match.MOST_ASKS
    fresh = Namer()
    offers_api.word_due(repository, fresh, TODAY, Counter())
    assert len(fresh.calls) == 1, "a new counter (a server start) asks again"


@needs_db
def test_nothing_due_means_no_model_call(people, session):
    repository, _ = people
    set_word(session, "p-milch", "H-Milch")
    set_word(session, "p-gurke", "Gewürzgurken")
    set_word(session, "p-quark", "Quark")
    set_word(session, "p-hafer", "Haferdrink")
    namer = Namer()
    assert offers_api.word_due(repository, namer, TODAY, Counter()) == 0
    assert offers_api.word_due(repository, namer, TODAY) == 0
    assert namer.calls == []


@needs_db
def test_nobody_at_all_means_no_model_call(engine, session):
    from grocery_app.api.repository import PostgresRepository
    from grocery_app.db.session import make_session_factory

    namer = Namer()
    repository = PostgresRepository(make_session_factory(engine))
    assert offers_api.word_due(repository, namer, TODAY, Counter()) == 0
    assert namer.calls == []


# --- 2: what the model is told --------------------------------------------------------

@needs_db
def test_the_model_is_told_about_the_product_and_nothing_about_the_person(people, session):
    repository, sara = people
    namer = Namer()
    offers_api.word_due(repository, namer, TODAY, Counter())
    sent = json.dumps(namer.calls, ensure_ascii=False, default=str)
    for told in ("Alpenmilch 1,5%", "Musterhof", "laktosefrei", "Gewürzgurken", "670"):
        assert told in sent, f"the product's {told!r} is told"
    personal = ["Sara", "sara@example.com", sara["password"], *RAW.values(),
                "Musterladen", "Beispielmarkt", "Altladen", "Musterweg", "Beispielallee",
                "Musterstadt", "Beispielstadt", "12345", "54321", "99999",
                "1.37", "1,37", "2.43", "2,43", "0.89", "4.21",
                *days(3, 4, 10, 11, 17, 18)]
    if len(str(sara["id"])) >= 6:
        personal.append(str(sara["id"]))
    for secret in personal:
        assert secret not in sent, f"{secret!r} told to the model"


# --- 3: which words are kept ----------------------------------------------------------

KEPT = ["Eier", "abc", "a" * 40, "H-Milch", "Frische Vollmilch", "Bio frische Vollmilch",
        "Gewürzgurken"]
DROPPED = ["ab", "a" * 41, "eins zwei drei vier", "Milch 1,5%", "Cola 0", "3er Brötchen",
           "", "   ", None, 42, ["Milch"], {"w": "Milch"}]


@needs_db
@pytest.mark.parametrize("word", KEPT)
def test_a_usable_word_is_kept(people, session, word):
    repository, _ = people
    assert offers_api.word_due(repository, Namer({"p-milch": word}), TODAY, Counter()) == 1
    assert word_of(session, "p-milch") == word


@needs_db
@pytest.mark.parametrize("word", DROPPED, ids=repr)
def test_an_unusable_word_is_dropped_and_asked_again(people, session, word):
    repository, _ = people
    asked: Counter = Counter()
    namer = Namer({"p-milch": word})
    assert offers_api.word_due(repository, namer, TODAY, asked) == 0
    assert word_of(session, "p-milch") is None
    offers_api.word_due(repository, namer, TODAY, asked)
    assert len(namer.calls) == 2 and "p-milch" in namer.asked_about(1), \
        "dropped counts as unanswered: asked again"
    offers_api.word_due(repository, namer, TODAY, asked)
    assert len(namer.calls) == offer_match.MOST_ASKS


@needs_db
@pytest.mark.parametrize("answer", [{}, {"words": None}, {"words": "Milch"},
                                    {"words": [None, 3, {"product": "p-milch"}]}], ids=repr)
def test_an_odd_answer_keeps_nothing(people, session, answer):
    repository, _ = people
    try:
        kept = offers_api.word_due(repository, Namer(raw_answer=answer), TODAY, Counter())
    except Exception:  # noqa: BLE001 - said plainly is allowed; keeping something is not
        kept = 0
    assert kept == 0
    assert word_of(session, "p-milch") is None and word_of(session, "p-gurke") is None


@needs_db
def test_a_word_for_a_product_not_asked_about_is_ignored(people, session):
    repository, _ = people
    set_word(session, "p-gurke", "Gurken")
    namer = Namer(raw_answer={"words": [
        {"product": "p-milch", "word": "H-Milch"},
        {"product": "p-rosen", "word": "Blumenstrauss"},
        {"product": "p-gurke", "word": "Essiggurken"},
        {"product": "p-nirgends", "word": "Brot"}]})
    assert offers_api.word_due(repository, namer, TODAY, Counter()) == 1
    assert word_of(session, "p-milch") == "H-Milch"
    assert word_of(session, "p-rosen") is None
    assert word_of(session, "p-gurke") == "Gurken", "a kept word is not overwritten"


# --- 4: what marktguru receives -------------------------------------------------------

HOME = b'<script>{"config":{"apiHostAddress":"api.example","apiKey":"K1","clientKey":"C1"}}'


class Site:
    """A fake marktguru that records every request and finds nothing."""

    def __init__(self):
        self.asked: list[tuple[str, dict]] = []
        self.stop = False

    def __call__(self, url, headers):
        if self.stop:
            raise Stop()
        self.asked.append((url, dict(headers)))
        if url == offers.HOME_URL:
            return HOME
        return json.dumps({"totalResults": 0, "results": []}).encode()

    def searches(self):
        return [urllib.parse.parse_qs(urllib.parse.urlsplit(u).query, keep_blank_values=True)
                for u, _ in self.asked if u != offers.HOME_URL]


class Stop(BaseException):
    """Ends a test's offers thread: not an Exception, so not caught as one."""


def search_pairs(site):
    pairs = set()
    for params in site.searches():
        assert len(params.get("q", [])) == 1 and len(params.get("zipCode", [])) == 1, params
        pairs.add((params["zipCode"][0], params["q"][0]))
    return pairs


def fetch(repository, site):
    return offers_api.fetch_due(repository, offers.Marktguru(site),
                                now=datetime.now(UTC), pause=0)


@needs_db
def test_marktguru_gets_the_flyer_word_or_else_the_name_without_sizes(people, session):
    repository, _ = people
    offers_api.word_due(repository, Namer({"p-milch": "H-Milch"}), TODAY, Counter())
    site = Site()
    fetch(repository, site)
    assert search_pairs(site) == {("12345", "H-Milch"), ("54321", "Gewürzgurken")}
    keys = {tuple(sorted(p)) for p in site.searches()}
    assert len(keys) == 1, keys
    rest = {json.dumps({k: v for k, v in p.items() if k not in ("q", "zipCode")},
                       sort_keys=True) for p in site.searches()}
    assert len(rest) == 1, f"nothing else varies by person: {rest}"
    assert len({json.dumps(h, sort_keys=True) for _, h in site.asked
                if _ != offers.HOME_URL}) == 1


@needs_db
@pytest.mark.parametrize("word", ["Brot&zipCode=abc", "Brot#zipCode", "Milch?q=Sara",
                                  "Brot%26zip"])
def test_a_model_word_cannot_change_what_else_is_sent(people, session, word):
    """A word with URL characters passes the rule (no digits, one word); it must
    reach marktguru as the word, never as an extra postcode or parameter."""
    repository, _ = people
    offers_api.word_due(repository, Namer({"p-milch": word}), TODAY, Counter())
    site = Site()
    fetch(repository, site)
    pairs = search_pairs(site)
    assert {z for z, _ in pairs} == {"12345", "54321"}
    milk = {q for z, q in pairs if z == "12345"}
    assert milk in ({word}, {"Alpenmilch"}), milk


# --- 5: a failed naming call -----------------------------------------------------------

@needs_db
def test_a_failed_naming_call_keeps_no_word(people, session):
    repository, _ = people

    class Down(Namer):
        def __call__(self, *a):
            super().__call__(*a)
            raise RuntimeError("busy")

    try:
        offers_api.word_due(repository, Down({"p-milch": "H-Milch"}), TODAY, Counter())
    except RuntimeError:
        pass
    assert word_of(session, "p-milch") is None and word_of(session, "p-gurke") is None


@needs_db
def test_a_failed_naming_call_does_not_stop_the_passs_searches(people, session, monkeypatch):
    repository, _ = people
    monkeypatch.setattr(offers_api, "PAUSE_BETWEEN_SEARCHES_S", 0)
    calls: list[tuple] = []

    def down(*a):
        calls.append(a)
        raise RuntimeError("model busy")

    site = Site()
    thread = threading.Thread(target=offers_api.keep_fetching,
                              args=(repository, offers.Marktguru(site)),
                              kwargs={"judge": down, "every": 30}, daemon=True)
    try:
        thread.start()
        deadline = time.monotonic() + 10
        while len(site.searches()) < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        site.stop = True
        thread.join(timeout=5)
    assert calls, "the naming call was made (and failed)"
    assert search_pairs(site) == {("12345", "Alpenmilch"), ("54321", "Gewürzgurken")}, \
        "the first pass still searched, by name"
    assert word_of(session, "p-milch") is None


# --- 6: a word is the product's, for everyone ----------------------------------------

@needs_db
def test_one_word_serves_everyone_who_buys_the_product(people, session):
    repository, sara = people
    for day in days(5, 12, 19):
        add_receipt(session, SARAS_SHOP, sara["id"], day, ["p-milch"])
    session.commit()
    namer = Namer({"p-milch": "H-Milch", "p-gurke": "Gewürzgurken"})
    assert offers_api.word_due(repository, namer, TODAY, Counter()) == 2
    assert sum(prompt.count("Product p-milch:") for _, prompt, _ in namer.calls) == 1, \
        "asked once though two people buy it"
    site = Site()
    fetch(repository, site)
    assert search_pairs(site) == {("12345", "H-Milch"), ("54321", "H-Milch"),
                                  ("54321", "Gewürzgurken")}
