"""The offers search, checked against its privacy rule, on made-up data.

The rule, in words (owner, 2026-10-23):

1. Only marktguru is asked, with a search word and a postcode. The word is a
   product's catalog name without its size; the postcode is a shop address
   printed on the person's receipts. Nothing about the person goes out: no
   user id, name, email, token, receipt text, raw line, date or amount, and
   no header that carries any of it.
2. Each person's searches are their own shop postcodes x their own regular
   groceries (bought on 3+ days in the last 90 days). Never one person's
   product with another's postcode; never a non-grocery; never a shop only
   visited more than 90 days ago.
3. `offers` and `offer_searches` hold public offer data and postcode/word
   pairs only, never a user.
4. `GET /v1/offers/rhythm` is the owner's only, and carries no postcode or word.
5. Nothing reaches the network unless `offers=` is given; the demo never
   starts the offers thread.
6. A failing or hostile source never crashes anything, never leaves a
   half-written row, and a failed search is not recorded as done.
7. The privacy page says what is sent and to whom, in German and English.

Every source here is a fake: nothing leaves the machine.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from grocery_app import offers
from grocery_app.api import offers as offers_api
from grocery_app.api.app import create_app
from grocery_app.api.images import DiskImageStore
from grocery_app.api.repository import PostgresRepository
from grocery_app.db.io import receipt_from_dict
from grocery_app.db.models import Offer, OfferSearch, Product, Resolution
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL as URL
from tests.test_upload import FakeExtractor

needs_db = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")

NOW = datetime(2026, 10, 23, 10, 0, tzinfo=UTC)
OWNER = {"Authorization": "Bearer owner-secret"}

# What the people bought: (store, address, user, date, raw line, product, price)
OWNER_SHOP = ("Musterladen", "Musterweg 17, 12345 Musterstadt")
OLD_SHOP = ("Altladen", "Altgasse 2, 99999 Altstadt")
SARAS_SHOP = ("Beispielmarkt", "Beispielallee 3, 54321 Beispielstadt")

PRODUCTS = [
    # id, catalog name, category
    ("p-milch", "Vollmilch 1L", "milch"),          # owner's regular grocery
    ("p-rosen", "Rosen", "blumen"),                # owner's regular, not a grocery
    ("p-cafe", "Cappuccino", "cafe-imbiss"),       # owner's regular, a café
    ("p-hafer", "Haferdrink 1 l", "pflanzendrink"),  # 3 days, all long ago
    ("p-butter", "Butter 250 g", "butter"),        # 3 days, only one recent
    ("p-skyr", "Skyr 450 g", "skyr"),              # Sara's regular
    ("p-quark", "Quark 500 g", "quark"),           # Sara, once only
]
RAW = {"p-milch": "MU VOLLMILCH H", "p-rosen": "ROSEN BUND", "p-cafe": "KAFFEE TO GO",
       "p-hafer": "ALT HAFERDR", "p-butter": "BUTTER MU", "p-skyr": "BSP SKYR NAT",
       "p-quark": "BSP QUARK MAG"}

EXPECTED = {("12345", "Vollmilch"), ("54321", "Skyr")}
KNOWN_WORDS = ("Vollmilch", "Skyr", "Rosen", "Cappuccino", "Haferdrink", "Butter", "Quark")

# Nothing of these may ever be sent or stored.
PERSONAL = ["Sara", "sara@example.com", "owner-secret", "Musterweg", "Beispielallee",
            "Altgasse", "Musterstadt", "Beispielstadt", *RAW.values(), "2026-10-",
            "2026-03-", "1.37", "2.43", "4.21", "Rosen", "Cappuccino"]


def add_receipt(session, shop, user_id, day, product_ids, price=1.37):
    store, location = shop
    receipt = receipt_from_dict({
        "source_image": f"{store}-{user_id}-{day}-{product_ids[0]}.jpeg",
        "transcribed_by": "llm",
        "store": store, "store_location": location, "date": day, "time": "10:00",
        "currency": "EUR", "printed_total": round(price * len(product_ids), 2),
        "lines": [{"type": "product", "raw_name": RAW[pid], "qty": 1, "gross": price,
                   "discount": 0.0, "net": price, "tax_class": "A"} for pid in product_ids]})
    receipt.user_id = user_id
    session.add(receipt)


@pytest.fixture
def people(engine, session):
    for pid, name, category in PRODUCTS:
        session.add(Product(id=pid, name=name, brand="Muster", category=category))
    for store, _ in (OWNER_SHOP, OLD_SHOP, SARAS_SHOP):
        for pid, raw in RAW.items():
            session.add(Resolution(store=store, raw_name=raw, line_type="product",
                                   product_id=pid, confirmed_by="test"))
    session.commit()
    repository = PostgresRepository(make_session_factory(engine))
    sara = repository.create_user("Sara", "sara@example.com")
    PERSONAL.append(sara["password"])
    for day in ("2026-10-01", "2026-10-08", "2026-10-15"):
        add_receipt(session, OWNER_SHOP, None, day, ["p-milch", "p-rosen", "p-cafe"])
    add_receipt(session, OWNER_SHOP, None, "2026-10-15", ["p-butter"], price=2.43)
    for day in ("2026-03-01", "2026-03-08", "2026-03-15"):
        add_receipt(session, OLD_SHOP, None, day, ["p-hafer"])
    for day in ("2026-03-01", "2026-03-08"):
        add_receipt(session, OLD_SHOP, None, day, ["p-butter"], price=2.43)
    for day in ("2026-10-02", "2026-10-09", "2026-10-16"):
        add_receipt(session, SARAS_SHOP, sara["id"], day, ["p-skyr"], price=4.21)
    add_receipt(session, SARAS_SHOP, sara["id"], "2026-10-16", ["p-quark"])
    session.commit()
    yield repository, sara
    PERSONAL.remove(sara["password"])


# --- a fake marktguru ---------------------------------------------------------------

HOME = b'<html><script>{"config":{"apiKey":"fake-api","clientKey":"fake-client"}}</script>'


def an_offer(n, chain="Musterkette"):
    return {"id": n, "advertisers": [{"name": chain}], "brand": {"name": "Muster"},
            "product": {"name": "Etwas"}, "description": "1 Stück",
            "categories": [{"name": "Milch"}], "price": 0.99, "oldPrice": 1.19,
            "unit": {"shortName": "l"}, "volume": 1, "quantity": 1, "referencePrice": 0.99,
            "validityDates": [{"from": "2026-10-25T23:00:00Z", "to": "2026-10-31T22:59:59Z"}]}


class FakeSource:
    """Records every (url, headers); `answer(params, n)` gives the n-th search body."""

    def __init__(self, answer=None):
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.answer = answer or self.one_offer_each
        self.stop = False

    @staticmethod
    def one_offer_each(params, n):
        key = abs(hash((tuple(sorted(params.items())),))) % 10**8
        return json.dumps({"results": [an_offer(key)], "totalResults": 1}).encode()

    def __call__(self, url, headers):
        if self.stop:
            raise Stop()
        self.calls.append((url, dict(headers)))
        parts = urllib.parse.urlsplit(url)
        if not parts.netloc.startswith("api."):
            return HOME
        params = dict(urllib.parse.parse_qsl(parts.query))
        return self.answer(params, len(self.searches()))

    def searches(self):
        return [(u, h) for u, h in self.calls if urllib.parse.urlsplit(u).netloc.startswith("api.")]

    def pairs(self):
        out = set()
        for url, _ in self.searches():
            params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
            postcode = [v for v in params.values() if v.isdigit() and len(v) == 5]
            words = [v for v in params.values() if not v.isdigit()
                     and v.startswith(KNOWN_WORDS)]
            out.add((postcode[0] if postcode else None, words[0] if words else None))
        return out


class Stop(BaseException):
    """Ends a test's offers thread: not an Exception, so not caught as one."""


def run(repository, fetch):
    return offers_api.fetch_due(repository, offers.Marktguru(fetch), now=NOW, pause=0)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any attempt to open a connection is recorded and refused."""
    tried: list[object] = []

    def refuse(*args, **kwargs):
        tried.append(args)
        raise OSError("no network in tests")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    return tried


# --- 1 and 2: what is sent, and whose ------------------------------------------------

@pytest.mark.parametrize("name, word", [
    ("Skyr 450 g", "Skyr"), ("Vollmilch 1L", "Vollmilch"), ("Mehl 1 kg", "Mehl"),
    ("Mineralwasser 6 x 1,5 l", "Mineralwasser"), ("Haferdrink 1 l", "Haferdrink"),
])
def test_the_word_is_the_name_without_its_size(name, word):
    assert offers.search_word(name) == word


@needs_db
def test_each_person_is_searched_with_their_own_shops_and_regular_groceries(people):
    repository, _ = people
    source = FakeSource()
    run(repository, source)
    assert source.pairs() == EXPECTED


@needs_db
def test_nothing_about_the_person_leaves_the_server(people):
    repository, _ = people
    source = FakeSource()
    run(repository, source)
    assert source.searches(), "something was searched"
    for url, headers in source.calls:
        host = urllib.parse.urlsplit(url).netloc
        assert host == "marktguru.de" or host.endswith(".marktguru.de"), url
        sent = urllib.parse.unquote_plus(url) + json.dumps(headers, ensure_ascii=False)
        for secret in PERSONAL:
            assert secret not in sent, f"{secret!r} sent in {url}"
    # Every header is the same on every request: none can carry a person.
    assert len({json.dumps(h, sort_keys=True) for _, h in source.searches()}) == 1
    # Every query parameter but the word and the postcode is the same on every search.
    rest = set()
    for url, _ in source.searches():
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        rest.add(json.dumps({k: v for k, v in params.items()
                             if v not in {p for p, _ in EXPECTED}
                             and not v.startswith(KNOWN_WORDS)}, sort_keys=True))
    assert len(rest) == 1, rest


# --- 3: what is kept --------------------------------------------------------------

@needs_db
def test_the_offer_tables_hold_no_person(people, engine, session):
    repository, _ = people
    source = FakeSource()
    run(repository, source)
    for table in ("offers", "offer_searches"):
        columns = {c["name"] for c in inspect(engine).get_columns(table)}
        assert not any("user" in c for c in columns), (table, columns)
        assert all(fk["referred_table"] != "users"
                   for fk in inspect(engine).get_foreign_keys(table))
    stored = [(s.postcode, s.word) for s in session.query(OfferSearch)]
    assert set(stored) == source.pairs(), "what was searched, and only that"
    for offer in session.query(Offer):
        text = json.dumps(offer.record, ensure_ascii=False)
        for secret in PERSONAL:  # an offer's own validity dates are public
            if not secret.startswith("2026-"):
                assert secret not in text


# --- 4: the rhythm ------------------------------------------------------------------

@needs_db
def test_the_rhythm_is_the_owners_and_names_no_postcode_or_word(people, tmp_path):
    repository, sara = people
    run(repository, FakeSource())
    client = TestClient(create_app(repository, DiskImageStore(tmp_path), FakeExtractor(),
                                   token="owner-secret"))
    mine = client.get("/v1/offers/rhythm", headers=OWNER)
    assert mine.status_code == 200
    assert "Musterkette" in mine.text, "there is something to show"
    for leak in ("12345", "54321", "Vollmilch", "Skyr"):
        assert leak not in mine.text
    hers = client.get("/v1/offers/rhythm",
                      headers={"Authorization": f"Bearer {sara['password']}"})
    assert hers.status_code == 403
    assert "Musterkette" not in hers.text
    for headers in ({}, {"Authorization": "Bearer guessed"}, {"Authorization": "owner-secret"}):
        answer = client.get("/v1/offers/rhythm", headers=headers)
        assert answer.status_code in (401, 403), headers
        assert "Musterkette" not in answer.text


# --- 5: no network unless asked; never in the demo ------------------------------------

@pytest.fixture
def started(monkeypatch):
    """Every thread started, by target, and every call of the offers loop."""
    targets: list[str] = []
    loops: list[tuple] = []
    original = threading.Thread.start

    def start(self):
        target = getattr(self, "_target", None)
        targets.append(f"{getattr(target, '__module__', '')}.{getattr(target, '__qualname__', '')}"
                       f"{getattr(self, '_args', ())!r}")
        return original(self)

    monkeypatch.setattr(threading.Thread, "start", start)
    monkeypatch.setattr(offers_api, "keep_fetching", lambda *a, **k: loops.append(a))
    return targets, loops


def offers_threads(targets, loops):
    return loops or [t for t in targets if "offer" in t.lower() or "Marktguru" in t]


@needs_db
def test_an_app_without_a_source_never_reaches_the_network(people, tmp_path, started,
                                                            no_network):
    repository, _ = people
    with TestClient(create_app(repository, DiskImageStore(tmp_path), FakeExtractor(),
                               token="owner-secret")) as client:
        client.get("/v1/offers/rhythm", headers=OWNER)
        time.sleep(0.3)
    assert not no_network
    assert not offers_threads(*started)


@needs_db
def test_the_demo_never_starts_the_offers_thread(people, tmp_path, started, no_network):
    repository, _ = people
    source = FakeSource()
    with TestClient(create_app(repository, DiskImageStore(tmp_path), FakeExtractor(),
                               demo=True, offers=offers.Marktguru(source))):
        time.sleep(0.3)
    source.stop = True
    assert not offers_threads(*started)
    assert not source.calls and not no_network


@needs_db
def test_a_server_given_a_source_does_start_it(people, tmp_path, started):
    """The two tests above would pass on an app that never starts the thread."""
    repository, _ = people
    source = FakeSource()
    with TestClient(create_app(repository, DiskImageStore(tmp_path), FakeExtractor(),
                               token="owner-secret", offers=offers.Marktguru(source))):
        time.sleep(0.3)
    source.stop = True
    assert offers_threads(*started)


# --- 6: a hostile source ------------------------------------------------------------

def raises(error):
    def answer(params, n):
        raise error
    return answer


HOSTILE = {
    "refused": raises(OSError("connection refused")),
    "timeout": raises(TimeoutError("slow")),
    "unexpected": raises(ValueError("odd")),
    "garbage": lambda p, n: b"\x00not json{{",
    "null": lambda p, n: b"null",
    "a list": lambda p, n: b"[1, 2]",
    "results not a list": lambda p, n: b'{"results": "x", "totalResults": 1}',
    "results of numbers": lambda p, n: b'{"results": [1, 2], "totalResults": 2}',
    "empty offers": lambda p, n: json.dumps({"results": [{}, {}], "totalResults": 2}).encode(),
    "no id": lambda p, n: json.dumps(
        {"results": [{k: v for k, v in an_offer(1).items() if k != "id"}],
         "totalResults": 1}).encode(),
    "nameless chain": lambda p, n: json.dumps(
        {"results": [{**an_offer(2), "advertisers": [{}]}], "totalResults": 1}).encode(),
    "bad dates": lambda p, n: json.dumps(
        {"results": [{**an_offer(3), "validityDates": [{"from": "soon"}]}],
         "totalResults": 1}).encode(),
    "huge postcode-less offer": lambda p, n: json.dumps(
        {"results": [{**an_offer(4), "description": "x" * 2_000_000}],
         "totalResults": 1}).encode(),
}


@needs_db
@pytest.mark.parametrize("kind", sorted(HOSTILE))
def test_a_hostile_answer_crashes_nothing_and_leaves_nothing_half_done(people, session, kind):
    repository, _ = people
    source = FakeSource(HOSTILE[kind])
    try:
        run(repository, source)
    except offers.OffersUnavailable:
        pass  # said plainly; the thread decides what to do
    session.expire_all()
    for offer in session.query(Offer):
        assert offer.chain and offer.valid_from and offer.valid_to
        assert offer.record and offer.record.get("price") is not None
    searched = {(s.postcode, s.word) for s in session.query(OfferSearch)}
    if kind in ("refused", "timeout", "unexpected", "garbage", "null", "a list",
                "results not a list", "results of numbers"):
        assert not searched, "a failed search is not done"
    # Whatever happened, a good source afterwards finds everything not done.
    good = FakeSource()
    run(repository, good)
    assert len(good.searches()) == len(EXPECTED) - len(searched)


@needs_db
def test_a_search_that_fails_on_its_second_page_is_not_done(people, session):
    repository, _ = people

    def answer(params, n):
        offset = int(params.get("offset", 0) or 0)
        if offset == 0:
            return json.dumps({"results": [an_offer(i) for i in range(100)],
                               "totalResults": 250}).encode()
        raise OSError("dropped")

    source = FakeSource(answer)
    try:
        run(repository, source)
    except offers.OffersUnavailable:
        pass
    assert len(source.searches()) >= 2, "a second page was asked for"
    assert not session.query(OfferSearch).count()


@needs_db
def test_an_endless_answer_is_not_followed_forever(people):
    repository, _ = people
    counter = iter(range(10**9))

    def answer(params, n):
        return json.dumps({"results": [an_offer(next(counter)) for _ in range(100)],
                           "totalResults": 10**9}).encode()

    source = FakeSource(answer)
    run(repository, source)
    assert len(source.searches()) <= 2 * 5, "a bounded number of pages per search"


class EndlessResponse:
    """A body that never ends; reading it without a limit is reading forever."""

    def __init__(self):
        self.total = 0
        self.unbounded = False
        self.status = 200
        self.headers = {}

    def read(self, n=-1):
        if n is None or n < 0:
            self.unbounded = True
            n = 1 << 20
        self.total += n
        if self.total > 64 << 20:
            raise OSError("gave up after 64 MB")
        return b"x" * n

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass

    def getcode(self):
        return 200


def test_a_huge_answer_is_not_read_whole(monkeypatch):
    response = EndlessResponse()
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: response)
    try:
        offers.http_get(offers.SEARCH_URL, {"User-Agent": "test"})
    except (offers.OffersUnavailable, OSError, ValueError):
        pass
    assert not response.unbounded, "the whole body was asked for at once"
    assert response.total <= 64 << 20


@needs_db
# An answer with one odd offer is not a failure: that offer is skipped and the
# search is done (the hostile-answer test above), so only real failures here.
@pytest.mark.parametrize("kind", ["refused", "null", "garbage", "results of numbers"])
def test_the_offers_thread_survives_a_source_that_keeps_failing(people, kind):
    repository, _ = people
    source = FakeSource(HOSTILE[kind])
    monkey_pause = offers_api.PAUSE_BETWEEN_SEARCHES_S
    offers_api.PAUSE_BETWEEN_SEARCHES_S = 0
    thread = threading.Thread(target=offers_api.keep_fetching,
                              args=(repository, offers.Marktguru(source)),
                              kwargs={"every": 0.05}, daemon=True)
    try:
        thread.start()
        deadline = time.monotonic() + 10
        while len(source.searches()) < 3 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert thread.is_alive(), "the thread died on a failed search"
        assert len(source.searches()) >= 3, "and kept trying on later passes"
    finally:
        source.stop = True
        thread.join(timeout=5)
        offers_api.PAUSE_BETWEEN_SEARCHES_S = monkey_pause


# --- 7: the privacy page -------------------------------------------------------------

@needs_db
def test_the_privacy_page_names_marktguru_and_what_is_sent_in_both_languages(people,
                                                                            tmp_path):
    repository, _ = people
    client = TestClient(create_app(repository, DiskImageStore(tmp_path), FakeExtractor(),
                                   token="owner-secret"))
    page = client.get("/privacy").text
    assert page.lower().count("marktguru") >= 2, "named in German and in English"
    assert "Postleitzahl" in page and "postcode" in page.lower()
