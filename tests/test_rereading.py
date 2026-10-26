"""Lines a failed search left waiting are read again by the server (the
owner, 2026-10-26: 175 lines of old receipts stayed grey, with nothing to tap,
because "the next run reads it again" had no next run).

The matcher and the reader are made up; no model is called.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from grocery_app.api import matching
from grocery_app.api.matching import reread_waiting, waiting_receipts
from grocery_app.db.models import Job, Question, Resolution
from grocery_app.db.session import make_session_factory
from grocery_app.identify import Identity
from tests.conftest import DATABASE_URL as URL
from tests.test_matching_server import TableMatcher, add_receipt

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")


class Reader:
    """Cannot search until `search_works`; then reads every line as itself."""

    def __init__(self, search_works=False):
        self.search_works = search_works
        self.calls = []

    def __call__(self, position, receipt, proposal, inputs):
        raw_name = receipt["lines"][position]["raw_name"]
        self.calls.append(raw_name)
        if not self.search_works:
            return Identity(raw_name, None, None, None, None, False, "not searched",
                            unsearched=True)
        return Identity(raw_name.title(), "aepfel", None, None, None, True, "test")


@pytest.fixture
def factory(engine, session):
    return make_session_factory(engine)


def test_a_line_whose_search_failed_waits_and_is_placed_when_read_again(factory, session):
    receipt = add_receipt(session, "IMG_1.jpeg", ["XY APFEL ROT"])
    failing = Reader()
    matching.match_receipt(session, receipt, TableMatcher({}), failing)
    session.commit()
    assert waiting_receipts(session) == [receipt], "unplaced, unasked, unanswered"

    working = Reader(search_works=True)
    assert reread_waiting(factory, TableMatcher({}), working) == [receipt]
    assert working.calls == ["XY APFEL ROT"]
    session.expire_all()
    assert session.scalars(select(Resolution).where(
        Resolution.raw_name == "XY APFEL ROT")).one().confirmed_by == "identify"
    assert waiting_receipts(session) == [], "placed: nothing waits any more"


def test_a_line_already_asked_or_placed_does_not_wait(factory, session):
    receipt = add_receipt(session, "IMG_1.jpeg", ["XY DING"])
    session.add(Question(receipt_id=receipt, position=0, raw_name="XY DING", proposal={}))
    session.commit()
    assert waiting_receipts(session) == []


def test_a_line_the_shopper_left_out_does_not_wait(factory, session):
    from grocery_app.db.models import UncountedLine

    receipt = add_receipt(session, "IMG_1.jpeg", ["XY GESCHENK"])
    session.add(UncountedLine(receipt_id=receipt, position=0, raw_name="XY GESCHENK"))
    session.commit()
    assert waiting_receipts(session) == [], "not theirs to count, not ours to pay for"


def test_a_receipt_still_being_read_is_left_to_its_upload(factory, session):
    receipt = add_receipt(session, "IMG_1.jpeg", ["XY DING"])
    session.add(Job(status="running", image_sha256="a" * 64, receipt_id=receipt))
    session.commit()
    assert waiting_receipts(session) == []


def test_each_try_is_kept_on_the_receipt_and_the_next_waits_longer(factory, session):
    from datetime import UTC, datetime, timedelta

    from grocery_app.db.models import Receipt

    receipt = add_receipt(session, "IMG_1.jpeg", ["XY DING"])
    reader, start = Reader(), datetime(2026, 10, 26, 12, tzinfo=UTC)
    for hours, read in ((0, True), (0.9, False), (1, True), (24, False), (25, True),
                        (24 * 365, False)):
        before = len(reader.calls)
        reread_waiting(factory, TableMatcher({}), reader, start + timedelta(hours=hours))
        assert (len(reader.calls) > before) == read, hours
    session.expire_all()
    kept = session.get(Receipt, receipt)
    assert (kept.reread_tries, kept.reread_at) == (3, start + timedelta(hours=25))


def test_a_pass_reads_a_few_receipts_oldest_first(factory, session):
    receipts = [add_receipt(session, f"IMG_{n}.jpeg", [f"XY DING {n}"])
                for n in range(matching.REREAD_PER_PASS + 2)]
    due = reread_waiting(factory, TableMatcher({}), Reader())
    assert due == receipts[:matching.REREAD_PER_PASS]


def test_only_a_server_told_to_starts_the_thread(engine, session, monkeypatch):
    from fastapi.testclient import TestClient

    from grocery_app.api.app import create_app
    from grocery_app.api.repository import PostgresRepository

    started = []
    # The real thread would keep reading the test database after the test.
    monkeypatch.setattr(matching, "keep_rereading", lambda *args: started.append(args))

    class Images:
        def save(self, data, suffix):
            return "x"

    repository = PostgresRepository(make_session_factory(engine))
    common = dict(image_store=Images(), extractor=lambda *a: {}, matcher=TableMatcher({}),
                  identify=Reader())
    with TestClient(create_app(repository, **common)):
        pass
    assert started == [], "tests and the laptop's server read nothing again"
    with TestClient(create_app(repository, reread=True, **common)) as client:
        client.app.state.rereading.join(timeout=5)
    assert len(started) == 1


def test_a_searcher_with_searches_to_spare_reads_on(factory, session):
    add_receipt(session, "IMG_1.jpeg", ["XY EINS"])
    reader = Reader()
    reader.searcher = Searcher(searched=149 - matching.REREAD_LEAVES_SEARCHES)
    reread_waiting(factory, TableMatcher({}), reader)
    assert reader.calls == ["XY EINS"]


class Searcher:
    def __init__(self, searched=0, max_searches=150):
        self.searched, self.max_searches = searched, max_searches


def tries(session, receipt_id):
    from grocery_app.db.models import Receipt

    session.expire_all()
    return session.get(Receipt, receipt_id).reread_tries


def test_gemini_turning_calls_away_costs_no_try_and_ends_the_pass(factory, session):
    """Live, 2026-10-26: Vertex answered 429 (RESOURCE_EXHAUSTED) on five
    receipts in a row, and each lost a try for it."""
    from grocery_app.matcher import DeciderError

    first = add_receipt(session, "IMG_1.jpeg", ["XY EINS"])
    second = add_receipt(session, "IMG_2.jpeg", ["XY ZWEI"])

    class Busy(Reader):
        def __call__(self, *args):
            super().__call__(*args)
            raise DeciderError('Gemini 429: {"status": "RESOURCE_EXHAUSTED"}')

    reader = Busy()
    assert reread_waiting(factory, TableMatcher({}), reader) == []
    assert reader.calls == ["XY EINS"], "the pass ends: the next would be turned away too"
    assert (tries(session, first), tries(session, second)) == (0, 0)


def test_another_failure_still_counts_its_try(factory, session):
    receipt = add_receipt(session, "IMG_1.jpeg", ["XY EINS"])

    class Broken(Reader):
        def __call__(self, *args):
            raise ValueError("a bug")

    reread_waiting(factory, TableMatcher({}), Broken())
    assert tries(session, receipt) == 1


def test_a_searcher_out_of_searches_reads_nothing_and_counts_no_try(factory, session):
    """Out for the rereading: the last searches of a start are left to uploads."""
    receipt = add_receipt(session, "IMG_1.jpeg", ["XY EINS"])
    reader = Reader()
    reader.searcher = Searcher(searched=150 - matching.REREAD_LEAVES_SEARCHES)
    assert reread_waiting(factory, TableMatcher({}), reader) == []
    assert reader.calls == [] and tries(session, receipt) == 0


def test_searches_running_out_part_way_give_the_try_back(factory, session):
    first = add_receipt(session, "IMG_1.jpeg", ["XY EINS"])
    add_receipt(session, "IMG_2.jpeg", ["XY ZWEI"])

    class Spends(Reader):
        def __call__(self, *args):
            self.searcher.searched += 1
            return super().__call__(*args)

    reader = Spends()
    reader.searcher = Searcher(searched=149 - matching.REREAD_LEAVES_SEARCHES)
    assert reread_waiting(factory, TableMatcher({}), reader) == []
    assert reader.calls == ["XY EINS"] and tries(session, first) == 0
