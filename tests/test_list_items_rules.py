"""Item words and the list by item, checked against their rules, on made-up data (risk check).

The rules, in words (owner, 2026-10-24):

1. The offers thread (`word_due(repository, decider, today, asked)`) asks the
   model for an item word for every grocery product that anyone (the owner or
   any user) has bought, at any time, that has no word yet
   (`products.offer_word` is empty). Not only the regulars. A non-grocery
   product (a category `categories.never_counted` names, e.g. flowers)
   is never asked about. A product with no known category is never asked about.
2. A product that has a word is never asked about again. A product given no
   usable word is asked at most `offer_match.MOST_ASKS` times per `asked`
   counter. When nothing is due, no model call is made. Products go 20 to a call.
3. The model is told only about the product (name, brand, details, size):
   never a receipt's printed text, a person, a shop, a postcode or a price.
4. The word reaches every line of that product in purchases.json as `item`
   (contract version 9) for every person who bought it; a product with no word
   has no item. A user's purchases never leak into another person's purchases
   or list.
5. The shopping list groups lines by item (case-insensitive), falling back to
   the category key when there is no item. `PUT /v1/list/{kind}` accepts a
   category key, or an item key the asker has bought; any other key is 422
   and nothing is stored. One person's list edits never affect another
   person's list.

Every model here is a fake: nothing leaves the machine.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime, timedelta

import pytest

from grocery_app import offer_match
from grocery_app.api import offers as offers_api
from tests.conftest import DATABASE_URL as URL

needs_db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")

OWNER_SHOP = ("Musterladen", "Musterweg 17, 12345 Musterstadt")
SARAS_SHOP = ("Beispielmarkt", "Beispielallee 3, 54321 Beispielstadt")

#   id, name, brand, details, size, category
PRODUCTS = [
    ("p-milch", "Alpenmilch 1,5%", "Musterhof", ["laktosefrei"],
     {"count": 1, "value": 1.0, "unit": "l"}, "milch"),          # owner, weekly
    ("p-gurke", "Gewürzgurken 670 g", None, [], {"count": 1, "value": 670, "unit": "g"},
     "gurken"),                                                  # Sara, weekly
    ("p-quark", "Magerquark", "Musterhof", [], None, "quark"),   # Sara, once only
    ("p-hafer", "Haferdrink", None, [], None, "pflanzendrink"),  # owner, once, long ago
    ("p-rosen", "Rosen", None, [], None, "blumen"),              # owner, not a grocery
    ("p-rätsel", "Rätselware", None, [], None, None),            # owner, no category
    ("p-nie", "Vollkornbrot", None, [], None, "brot"),           # nobody bought it
]
RAW = {"p-milch": "MHF ALPMI LF", "p-gurke": "BSP GURK GLAS", "p-quark": "BSP QUARK MAG",
       "p-hafer": "ALT HAFERDR", "p-rosen": "ROSEN BUND", "p-rätsel": "XQ 4711 ZZ",
       "p-nie": "VK BROT"}
PRICE = {"p-milch": 1.37, "p-gurke": 2.43, "p-quark": 0.89, "p-hafer": 1.99,
         "p-rosen": 4.21, "p-rätsel": 3.33, "p-nie": 2.71}


def today():
    from grocery_app.offers import GERMANY

    return datetime.now(UTC).astimezone(GERMANY).date()


def days(*ago):
    return [(today() - timedelta(days=d)).isoformat() for d in ago]


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


def add_product(session, pid, name, brand, details, size, category):
    from grocery_app.db.io import product_from_dict

    session.add(product_from_dict(pid, {
        "label": pid, "name": name, "brand": brand, "details": details, "size": size,
        "category": category, "is_organic": False, "eans": [], "open_questions": [],
        "provenance": {"attributes": "test", "source": "test"}}))


def add_resolution(session, store, raw, pid):
    from grocery_app.db.io import resolution_from_dict

    session.add(resolution_from_dict({
        "store": store, "raw_name": raw, "line_type": "product", "product_id": pid,
        "confirmed_by": "test", "confirmed_at": "2026-01-01", "source": "test"}))


@pytest.fixture
def people(engine, session):
    """The owner buys milk weekly (and roses), a puzzle once, oat drink once long
    ago; Sara buys gherkins weekly and quark once. Nobody bought the bread."""
    from grocery_app.api.repository import PostgresRepository
    from grocery_app.db.session import make_session_factory

    for product in PRODUCTS:
        add_product(session, *product)
    for store, _ in (OWNER_SHOP, SARAS_SHOP):
        for pid, raw in RAW.items():
            add_resolution(session, store, raw, pid)
    session.commit()
    repository = PostgresRepository(make_session_factory(engine))
    sara = repository.create_user("Sara", "sara@example.com")
    for day in days(3, 10, 17, 24):
        add_receipt(session, OWNER_SHOP, None, day, ["p-milch", "p-rosen"])
    add_receipt(session, OWNER_SHOP, None, days(30)[0], ["p-rätsel"])
    add_receipt(session, OWNER_SHOP, None, days(400)[0], ["p-hafer"])
    for day in days(4, 11, 18, 25):
        add_receipt(session, SARAS_SHOP, sara["id"], day, ["p-gurke"])
    add_receipt(session, SARAS_SHOP, sara["id"], days(6)[0], ["p-quark"])
    session.commit()
    return repository, sara


class Namer:
    """Answers `words` for the products named in the prompt; records every call."""

    def __init__(self, words=None):
        self.words, self.calls = words or {}, []

    def __call__(self, system, prompt, schema):
        self.calls.append((system, prompt, schema))
        return {"words": [{"product": p, "word": w} for p, w in self.words.items()
                          if f"Product {p}:" in prompt]}

    def asked_about(self, n=-1, among=None):
        ids = among or [p for p, *_ in PRODUCTS]
        return {p for p in ids if f"Product {p}:" in self.calls[n][1]}

    def all_asked(self):
        return set().union(*(self.asked_about(i) for i in range(len(self.calls))))


def word_of(session, pid):
    from grocery_app.db.models import Product

    session.expire_all()
    return session.get(Product, pid).offer_word


def set_word(session, pid, word):
    from grocery_app.db.models import Product

    session.get(Product, pid).offer_word = word
    session.commit()


def client_for(repository):
    from fastapi.testclient import TestClient

    from grocery_app.api.app import create_app

    return TestClient(create_app(repository, token="owner-secret"))


OWNER = {"Authorization": "Bearer owner-secret"}


def as_sara(sara):
    return {"Authorization": f"Bearer {sara['password']}"}


# --- 1: who is asked -------------------------------------------------------------------

@needs_db
def test_every_bought_grocery_without_a_word_is_asked_not_only_regulars(people, session):
    repository, _ = people
    namer = Namer({"p-milch": "H-Milch", "p-gurke": "Gewürzgurken", "p-quark": "Quark",
                   "p-hafer": "Haferdrink"})
    assert offers_api.word_due(repository, namer, today(), Counter()) == 4
    assert namer.all_asked() == {"p-milch", "p-gurke", "p-quark", "p-hafer"}, \
        "the owner's and Sara's, regular or once, recent or long ago"
    assert [word_of(session, p) for p in ("p-milch", "p-gurke", "p-quark", "p-hafer")] == [
        "H-Milch", "Gewürzgurken", "Quark", "Haferdrink"]


@needs_db
def test_flowers_an_uncategorised_product_and_an_unbought_one_are_never_asked(people, session):
    repository, _ = people
    namer = Namer({"p-rosen": "Rosen", "p-rätsel": "Ware", "p-nie": "Brot"})
    asked: Counter = Counter()
    for _ in range(offer_match.MOST_ASKS + 1):
        offers_api.word_due(repository, namer, today(), asked)
    for _, prompt, _ in namer.calls:
        for pid in ("p-rosen", "p-rätsel", "p-nie"):
            assert f"Product {pid}:" not in prompt and pid not in prompt, pid
        assert "Rosen" not in prompt and "Rätselware" not in prompt
        assert "Vollkornbrot" not in prompt
    assert [word_of(session, p) for p in ("p-rosen", "p-rätsel", "p-nie")] == [None] * 3


# --- 2: how often ---------------------------------------------------------------------

@needs_db
def test_a_product_with_a_word_is_never_asked_again(people, session):
    repository, _ = people
    set_word(session, "p-quark", "Quark")
    namer = Namer({"p-quark": "Speisequark"})
    offers_api.word_due(repository, namer, today(), Counter())
    offers_api.word_due(repository, namer, today(), Counter())
    assert namer.calls, "the others are still asked"
    assert all("p-quark" not in prompt for _, prompt, _ in namer.calls)
    assert word_of(session, "p-quark") == "Quark"


@needs_db
def test_an_unanswered_one_off_is_asked_at_most_most_asks_times_per_counter(people, session):
    repository, _ = people
    for pid in ("p-milch", "p-gurke", "p-hafer"):
        set_word(session, pid, "Wort")
    silent = Namer()
    asked: Counter = Counter()
    for _ in range(offer_match.MOST_ASKS + 3):
        assert offers_api.word_due(repository, silent, today(), asked) == 0
    assert len(silent.calls) == offer_match.MOST_ASKS
    assert all(silent.asked_about(i) == {"p-quark"} for i in range(len(silent.calls)))


@needs_db
def test_once_every_bought_grocery_has_a_word_no_call_is_made(people, session):
    repository, _ = people
    for pid in ("p-milch", "p-gurke", "p-quark", "p-hafer"):
        set_word(session, pid, "Wort")
    namer = Namer()
    assert offers_api.word_due(repository, namer, today(), Counter()) == 0
    assert namer.calls == [], "roses, the puzzle and the unbought bread are not due"


@needs_db
def test_products_go_twenty_to_a_call(engine, session):
    from grocery_app.api.repository import PostgresRepository
    from grocery_app.db.session import make_session_factory

    ids = [f"p-{i:02d}" for i in range(45)]
    for pid in ids:
        add_product(session, pid, f"Ware {pid}", None, [], None, "milch")
        add_resolution(session, "Musterladen", f"WARE {pid}", pid)
    session.commit()
    from grocery_app.db.io import receipt_from_dict

    receipt = receipt_from_dict({
        "source_image": "viele.jpeg", "transcribed_by": "llm", "store": "Musterladen",
        "date": days(2)[0], "time": "10:00", "currency": "EUR", "printed_total": 45.0,
        "lines": [{"type": "product", "raw_name": f"WARE {pid}", "qty": 1, "gross": 1.0,
                   "discount": 0.0, "net": 1.0, "tax_class": "A"} for pid in ids]})
    session.add(receipt)
    session.commit()
    repository = PostgresRepository(make_session_factory(engine))
    namer = Namer()
    offers_api.word_due(repository, namer, today(), Counter())
    sizes = [len(namer.asked_about(i, among=ids)) for i in range(len(namer.calls))]
    assert sorted(sizes, reverse=True) == [20, 20, 5], sizes


# --- 3: what the model is told --------------------------------------------------------

@needs_db
def test_the_model_is_told_about_the_product_and_nothing_else(people, session):
    repository, sara = people
    namer = Namer()
    offers_api.word_due(repository, namer, today(), Counter())
    sent = json.dumps(namer.calls, ensure_ascii=False, default=str)
    for told in ("Alpenmilch 1,5%", "Musterhof", "laktosefrei", "Magerquark", "670",
                 "Haferdrink"):
        assert told in sent, f"the product's {told!r} is told"
    personal = ["Sara", "sara@example.com", sara["password"], *RAW.values(),
                "Musterladen", "Beispielmarkt", "Musterweg", "Beispielallee",
                "Musterstadt", "Beispielstadt", "12345", "54321",
                "1.37", "1,37", "2.43", "2,43", "0.89", "0,89", "1.99", "1,99",
                *days(3, 4, 6, 10, 400)]
    if len(str(sara["id"])) >= 6:
        personal.append(str(sara["id"]))
    for secret in personal:
        assert secret not in sent, f"{secret!r} told to the model"


# --- 4: the word in purchases.json ----------------------------------------------------

def lines_of(client, headers, pid=None):
    doc = client.get("/v1/purchases", headers=headers).json()
    rows = [p for p in doc["purchases"] if p.get("type") == "product"]
    return doc, [p for p in rows if pid is None or p.get("product_id") == pid]


@needs_db
def test_the_word_reaches_every_line_of_the_product_for_everyone_who_bought_it(
        people, session):
    repository, sara = people
    for day in days(5, 12):
        add_receipt(session, SARAS_SHOP, sara["id"], day, ["p-milch"])
    session.commit()
    offers_api.word_due(repository, Namer({"p-milch": "H-Milch"}), today(), Counter())
    client = client_for(repository)
    doc, owners = lines_of(client, OWNER, "p-milch")
    assert doc["contract_version"] == 11
    _, saras = lines_of(client, as_sara(sara), "p-milch")
    assert len(owners) == 4 and len(saras) == 2
    assert [p.get("item") for p in owners + saras] == ["H-Milch"] * 6


@needs_db
def test_a_product_with_no_word_has_no_item(people, session):
    repository, sara = people
    offers_api.word_due(repository, Namer({"p-milch": "H-Milch"}), today(), Counter())
    client = client_for(repository)
    _, gherkins = lines_of(client, as_sara(sara), "p-gurke")
    _, roses = lines_of(client, OWNER, "p-rosen")
    assert gherkins and roses
    assert all(p.get("item") is None for p in gherkins + roses)


@needs_db
def test_a_users_purchases_never_reach_another_persons(people, session):
    repository, sara = people
    offers_api.word_due(repository, Namer({"p-milch": "H-Milch", "p-gurke": "Gurken",
                                           "p-quark": "Quark"}), today(), Counter())
    client = client_for(repository)
    _, owners = lines_of(client, OWNER)
    _, saras = lines_of(client, as_sara(sara))
    assert {p["product_id"] for p in owners} == {"p-milch", "p-rosen", "p-rätsel", "p-hafer"}
    assert {p["product_id"] for p in saras} == {"p-gurke", "p-quark"}
    assert {p.get("item") for p in saras} == {"Gurken", "Quark"}


# --- 5: the list, by item -------------------------------------------------------------

START = date(2026, 1, 1)


def row(kind, day, pid, item=None):
    r = {"type": "product", "date": day.isoformat(), "category": kind,
         "category_path": ["Abteilung", "Regal", kind.title()], "product_id": pid,
         "product": pid, "brand": None, "qty": 1, "net_paid": 1.0, "unit_price": None}
    if item is not None:
        r["item"] = item
    return r


def test_the_list_groups_by_item_whatever_its_case():
    from grocery_app.shopping_list import shopping_list

    # Two products of two categories, one item word in two spellings: bought
    # in turn every 3 days, so each alone is every 6 and together every 3.
    rows = [row("milch" if i % 2 else "h-milch-regal", START + timedelta(days=3 * i),
                "p-a" if i % 2 else "p-b", "H-Milch" if i % 2 else "h-milch")
            for i in range(20)]
    out = shopping_list(rows, START + timedelta(days=60))
    assert len(out) == 1, [k["kind"] for k in out]
    assert out[0]["kind"].lower() == "h-milch"


def test_without_an_item_the_list_falls_back_to_the_category_key():
    from grocery_app.shopping_list import shopping_list

    rows = ([row("quark", START + timedelta(days=4 * i), "p-q") for i in range(15)]
            + [row("kaese", START + timedelta(days=5 * i), "p-g", "Gouda") for i in range(12)]
            + [row("kaese", START + timedelta(days=5 * i + 1), "p-e") for i in range(12)])
    kinds = {k["kind"] for k in shopping_list(rows, START + timedelta(days=60))}
    assert "quark" in kinds, "no item: the category key"
    assert "kaese" in kinds, "the cheese with no item keeps its category"
    assert {k.lower() for k in kinds} >= {"gouda"}, "the cheese with an item is its own line"


@pytest.fixture
def milk_word(people, session):
    repository, sara = people
    offers_api.word_due(repository, Namer({"p-milch": "H-Milch"}), today(), Counter())
    return repository, sara


def listed(doc):
    return [line["kind"] for line in doc["lines"]]


def all_edits(session):
    from grocery_app.db.models import ListEdit

    session.expire_all()
    return sorted((e.user_id, e.kind) for e in session.query(ListEdit))


@needs_db
def test_the_owners_milk_is_listed_by_its_item_and_can_be_taken_off(milk_word, session):
    repository, sara = milk_word
    client = client_for(repository)
    owners = listed(client.get("/v1/list", headers=OWNER).json())
    item_keys = [k for k in owners if k.lower() == "h-milch"]
    assert item_keys, owners
    answer = client.put(f"/v1/list/{item_keys[0]}", headers=OWNER, json={"on_list": False})
    assert answer.status_code == 200, answer.text
    assert item_keys[0] not in listed(answer.json())
    assert len(all_edits(session)) == 1


@needs_db
def test_an_item_only_another_person_bought_is_refused_and_nothing_kept(milk_word, session):
    repository, sara = milk_word
    client = client_for(repository)
    owners = listed(client.get("/v1/list", headers=OWNER).json())
    (key,) = [k for k in owners if k.lower() == "h-milch"]
    before = all_edits(session)
    for spelling in {key, key.lower(), "H-Milch"}:
        for on in (True, False):
            answer = client.put(f"/v1/list/{spelling}", headers=as_sara(sara),
                                json={"on_list": on})
            assert answer.status_code == 422, (spelling, on, answer.status_code)
    assert all_edits(session) == before, "nothing stored"
    assert not any(k.lower() == "h-milch"
                   for k in listed(client.get("/v1/list", headers=as_sara(sara)).json()))


@needs_db
@pytest.mark.parametrize("key", ["irgendwas", "rosen-bund", "p-milch", "Alpenmilch"])
def test_a_key_that_is_neither_a_category_nor_a_bought_item_is_refused(
        milk_word, session, key):
    repository, sara = milk_word
    client = client_for(repository)
    for headers in (OWNER, as_sara(sara)):
        answer = client.put(f"/v1/list/{key}", headers=headers, json={"on_list": True})
        assert answer.status_code == 422, (key, answer.status_code)
    assert all_edits(session) == []


@needs_db
def test_a_category_key_is_accepted_even_if_never_bought(milk_word, session):
    repository, sara = milk_word
    client = client_for(repository)
    answer = client.put("/v1/list/brot", headers=as_sara(sara), json={"on_list": True})
    assert answer.status_code == 200, answer.text
    assert "brot" in listed(answer.json())
    assert "brot" not in listed(client.get("/v1/list", headers=OWNER).json())


@needs_db
def test_one_persons_list_edits_never_touch_anothers(milk_word, session):
    repository, sara = milk_word
    for day in days(5, 12, 19, 26):
        add_receipt(session, SARAS_SHOP, sara["id"], day, ["p-milch"])
    session.commit()
    client = client_for(repository)
    saras = listed(client.get("/v1/list", headers=as_sara(sara)).json())
    owners = listed(client.get("/v1/list", headers=OWNER).json())
    (key,) = [k for k in owners if k.lower() == "h-milch"]
    assert key in saras, "Sara buys the milk too now"
    off = client.put(f"/v1/list/{key}", headers=OWNER, json={"on_list": False})
    assert off.status_code == 200 and key not in listed(off.json())
    assert key in listed(client.get("/v1/list", headers=as_sara(sara)).json()), \
        "the owner's removal is not Sara's"
    assert key not in listed(client.get("/v1/list", headers=OWNER).json())


# --- found in review: paths the rule covers that the change may miss ------------------

def test_an_accepted_line_ends_with_the_buy_even_if_the_product_was_named_meanwhile():
    """The offers thread names products in the background. A person accepts
    `milch` (the line of a milk not named yet); the thread names it `H-Milch`;
    they buy it. The buy must end the accepted line, as any buy does."""
    from grocery_app.shopping_list import with_edits

    before = [row("milch", START + timedelta(days=7 * i), "p-m") for i in range(8)]
    day = START + timedelta(days=50)
    accepted = [{"kind": "milch", "edit": "add", "day": day}]
    assert [line["kind"] for line in with_edits(before, accepted, day)["lines"]][0] == "milch"
    named = [{**r, "item": "H-Milch"} for r in before]
    bought = named + [row("milch", day + timedelta(days=1), "p-m", "H-Milch")]
    after = with_edits(bought, accepted, day + timedelta(days=2))
    stuck = [line for line in after["lines"] if line["kind"] == "milch" and line["added"]]
    assert stuck == [], f"bought, yet still accepted and 'now': {stuck}"


@needs_db
def test_an_item_whose_word_has_a_slash_can_be_edited(people, session):
    """`Saft/Nektar` passes the word rule (`offer_match._is_a_word`); the page
    sends it as `encodeURIComponent` does."""
    import urllib.parse

    repository, _ = people
    offers_api.word_due(repository, Namer({"p-milch": "Milch/Kakao"}), today(), Counter())
    client = client_for(repository)
    (key,) = [k for k in listed(client.get("/v1/list", headers=OWNER).json())
              if "/" in k]
    answer = client.put(f"/v1/list/{urllib.parse.quote(key, safe='')}", headers=OWNER,
                        json={"on_list": False})
    assert answer.status_code == 200, (key, answer.status_code)


@needs_db
def test_typed_words_that_name_a_bought_item_put_that_item_on(people, session):
    """The paper list (owner, 2026-10-26): `h-milch` typed is the item H-Milch
    the asker bought, with its usual product, not words of their own."""
    repository, _ = people
    offers_api.word_due(repository, Namer({"p-milch": "H-Milch"}), today(), Counter())
    client = client_for(repository)
    lines = client.post("/v1/list", headers=OWNER, json={"text": "h-MILCH"}).json()["lines"]
    assert (lines[0]["kind"], lines[0]["typed"], lines[0]["added"]) == ("h-milch", False, True)
    assert lines[0]["usual"]["product_id"] == "p-milch"
