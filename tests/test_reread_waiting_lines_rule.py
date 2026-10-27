"""The rule, as given to the check (2026-10-26), tested without the code.

The deployed server reads again, by itself, every receipt line that nothing
placed, nobody was asked about and nobody answered (a "waiting" line, left
when the web search failed), exactly as an upload's receipt is matched. It
never touches an answered line ("none of these" included), a line with a
question, a placed line, a deposit, or a receipt whose upload is still
queued or running. At most 5 receipts a pass, oldest first, 3 tries per
receipt (at once, an hour later, a day later), counted on the receipt so a
server's restart does not start the count anew (amended after the review:
the server stops and starts often); one receipt failing never stops the
others. Only
`create_app(reread=True)` starts the thread, and the demo never does. The
calls are tagged "finding".

Made-up receipts and fake matchers/readers only; no model is called.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from grocery_app import spend
from grocery_app.api import matching
from grocery_app.api.matching import reread_waiting, waiting_receipts
from grocery_app.db.models import Job, LineResolution, Question, Resolution
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL as URL
from tests.test_matching_server import TableMatcher, add_receipt, reading, server  # noqa: F401
from tests.test_rereading import Reader

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")


@pytest.fixture
def factory(engine, session):
    return make_session_factory(engine)


class Raising(TableMatcher):
    """A matcher that fails on the names given, and answers "ask" otherwise."""

    def __init__(self, *broken):
        super().__init__({})
        self.broken = set(broken)

    def __call__(self, line, store, inputs):
        if line["raw_name"] in self.broken or "*" in self.broken:
            self.calls.append(line["raw_name"])
            raise RuntimeError("model gone")
        return super().__call__(line, store, inputs)


def test_the_bounds_are_the_ones_agreed():
    assert matching.REREAD_PER_PASS == 5
    assert matching.REREAD_TRIES == 3


# --- what waits, and what never does -----------------------------------------

def test_a_receipt_nobody_has_read_yet_waits(factory, session):
    receipt = add_receipt(session, "IMG_1.jpeg", ["XY APFEL"])
    assert waiting_receipts(session) == [receipt]


def test_a_receipt_with_only_a_deposit_never_waits(factory, session):
    add_receipt(session, "IMG_1.jpeg", ["Pfand"])
    reader, matcher = Reader(search_works=True), TableMatcher({})
    assert waiting_receipts(session) == []
    assert reread_waiting(factory, matcher, reader) == []
    assert (reader.calls, matcher.calls) == ([], [])


@pytest.mark.parametrize("status", ["queued", "running"])
def test_a_receipt_whose_upload_is_not_finished_is_left_alone(factory, session, status):
    receipt = add_receipt(session, "IMG_1.jpeg", ["XY DING"])
    session.add(Job(status=status, image_sha256="b" * 64, receipt_id=receipt))
    session.commit()
    reader, matcher = Reader(search_works=True), TableMatcher({})
    assert waiting_receipts(session) == []
    assert reread_waiting(factory, matcher, reader) == []
    assert (reader.calls, matcher.calls) == ([], [])


def test_a_receipt_whose_upload_is_done_may_wait(factory, session):
    receipt = add_receipt(session, "IMG_1.jpeg", ["XY DING"])
    session.add(Job(status="done", image_sha256="c" * 64, receipt_id=receipt))
    session.commit()
    assert waiting_receipts(session) == [receipt]


def test_a_line_with_a_question_alone_does_not_wait(factory, session):
    receipt = add_receipt(session, "IMG_1.jpeg", ["XY DING"])
    session.add(Question(receipt_id=receipt, position=0, raw_name="XY DING", proposal={}))
    session.commit()
    reader, matcher = Reader(search_works=True), TableMatcher({})
    assert reread_waiting(factory, matcher, reader) == []
    assert (reader.calls, matcher.calls) == ([], [])


def test_a_placed_line_does_not_wait(server, factory):  # noqa: F811
    _, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["MU Milch 1,5%"])
    # (the fixture's own IMG_2.jpeg holds an unplaced line, so it may wait)
    assert receipt not in waiting_receipts(session)


@pytest.mark.parametrize("answer", [{"none_of_these": True}, {"product_id": "p-0002"}])
def test_a_line_the_shopper_answered_does_not_wait(server, factory, answer):  # noqa: F811
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["XY RAETSEL"])
    assert client.put(f"/v1/receipts/{receipt}/lines/0/resolution",
                      json=answer).status_code == 200
    session.expire_all()
    assert session.scalars(select(LineResolution).where(
        LineResolution.receipt_id == receipt)).one()
    reader, matcher = Reader(search_works=True), TableMatcher({})
    assert receipt not in waiting_receipts(session)
    assert receipt not in reread_waiting(factory, matcher, reader)
    assert "XY RAETSEL" not in reader.calls + matcher.calls


def test_reading_a_receipt_again_touches_only_its_waiting_line(server, factory):  # noqa: F811
    """One receipt holds a waiting line beside an answered "none of these", an
    answered product, a question, a placed line and a deposit. Read again,
    only the waiting line reaches the matcher and the reader, and every other
    line is as it was."""
    client, session = server
    names = ["XY WARTET", "XY NEIN", "XY JA", "XY GEFRAGT", "MU Milch 1,5%", "Pfand"]
    receipt = add_receipt(session, "IMG_7.jpeg", names)
    session.add(Question(receipt_id=receipt, position=3, raw_name="XY GEFRAGT", proposal={}))
    session.commit()
    client.put(f"/v1/receipts/{receipt}/lines/1/resolution", json={"none_of_these": True})
    client.put(f"/v1/receipts/{receipt}/lines/2/resolution", json={"product_id": "p-0002"})
    before = reading(client, receipt)
    session.expire_all()
    others = ["XY NEIN", "XY JA", "XY GEFRAGT"]

    def memory():
        return sorted((r.raw_name, r.product_id, r.confirmed_by) for r in session.scalars(
            select(Resolution).where(Resolution.raw_name.in_(others))))
    remembered = memory()
    assert receipt in waiting_receipts(session)

    reader, matcher = Reader(search_works=True), TableMatcher({})
    assert receipt in reread_waiting(factory, matcher, reader)

    # (the fixture's IMG_2.jpeg may be read too: its `Geheimnis` waits)
    mine = set(names)
    assert [n for n in matcher.calls if n in mine] == ["XY WARTET"]
    assert [n for n in reader.calls if n in mine] == ["XY WARTET"]
    after = reading(client, receipt)
    assert after[1:] == before[1:], "every line but the waiting one is as it was"
    assert after[1] == ("none", None, []), "none of these stays none"
    assert after[2][1] == "p-0002"
    session.expire_all()
    assert len(session.scalars(select(Question).where(
        Question.receipt_id == receipt)).all()) == 1, "the question is not asked twice"
    assert {a.position for a in session.scalars(select(LineResolution).where(
        LineResolution.receipt_id == receipt))} == {1, 2}, "the answers are kept"
    assert memory() == remembered, "nothing remembered for the other lines changes"


# --- matched as an upload is ------------------------------------------------

def test_a_waiting_receipt_is_matched_by_match_receipt(factory, session, monkeypatch):
    receipt = add_receipt(session, "IMG_1.jpeg", ["XY APFEL"])
    real, seen = matching.match_receipt, []

    def spy(s, receipt_id, matcher, identify=None, *args, **kwargs):
        seen.append((receipt_id, matcher, identify))
        return real(s, receipt_id, matcher, identify, *args, **kwargs)

    monkeypatch.setattr(matching, "match_receipt", spy)
    matcher, reader = TableMatcher({}), Reader(search_works=True)
    reread_waiting(factory, matcher, reader)
    assert seen == [(receipt, matcher, reader)]


def test_the_calls_are_tagged_as_finding(factory, session):
    add_receipt(session, "IMG_1.jpeg", ["XY APFEL"])
    tags = []

    class Tagging(Reader):
        def __call__(self, *args):
            tags.append(spend.call_record("m", {})["purpose"])
            return super().__call__(*args)

    class TaggingMatcher(TableMatcher):
        def __call__(self, *args):
            tags.append(spend.call_record("m", {})["purpose"])
            return super().__call__(*args)

    reread_waiting(factory, TaggingMatcher({}), Tagging(search_works=True))
    assert tags and set(tags) == {"finding"}


# --- spending is bounded ----------------------------------------------------

def test_a_pass_reads_at_most_five_receipts_oldest_first(factory, session):
    receipts = [add_receipt(session, f"IMG_{n}.jpeg", [f"XY DING {n}"]) for n in range(7)]
    reader = Reader()
    assert reread_waiting(factory, TableMatcher({}), reader) == receipts[:5]
    assert reader.calls == [f"XY DING {n}" for n in range(5)]


def test_receipts_past_the_first_five_are_read_once_those_are_spent(factory, session):
    """Oldest first must not starve the rest: once the five oldest have used
    their tries, the next pass reads the next ones."""
    receipts = [add_receipt(session, f"IMG_{n}.jpeg", [f"XY DING {n}"]) for n in range(7)]
    reader = Reader()
    reread_waiting(factory, TableMatcher({}), reader)
    assert reread_waiting(factory, TableMatcher({}), reader) == receipts[5:], \
        "the five just tried wait an hour"


def test_a_receipt_that_keeps_failing_is_tried_three_times_then_never(factory, session):
    from datetime import UTC, datetime, timedelta

    add_receipt(session, "IMG_1.jpeg", ["XY KAPUTT"])
    matcher, start = Raising("*"), datetime(2026, 10, 26, 12, tzinfo=UTC)
    for hours in (0, 0.5, 1, 2, 25, 26, 24 * 30):
        reread_waiting(factory, matcher, Reader(search_works=True),
                       start + timedelta(hours=hours))
    assert matcher.calls == ["XY KAPUTT"] * 3, "at once, after an hour, after a day"

    again = Raising("*")
    reread_waiting(factory, again, Reader(search_works=True), start + timedelta(days=60))
    assert again.calls == [], "a restart does not start the count anew"


def test_one_receipt_failing_never_stops_the_others(factory, session):
    add_receipt(session, "IMG_1.jpeg", ["XY KAPUTT"])
    later = add_receipt(session, "IMG_2.jpeg", ["XY GUT"])
    reader = Reader(search_works=True)
    reread_waiting(factory, Raising("XY KAPUTT"), reader)
    assert "XY GUT" in reader.calls
    session.expire_all()
    assert session.scalars(select(Resolution).where(
        Resolution.raw_name == "XY GUT")).one().confirmed_by == "identify"
    assert later not in waiting_receipts(session)


def test_a_reader_failing_never_stops_the_others(factory, session):
    add_receipt(session, "IMG_1.jpeg", ["XY KAPUTT"])
    add_receipt(session, "IMG_2.jpeg", ["XY GUT"])

    class Breaks(Reader):
        def __call__(self, position, receipt, proposal, inputs):
            if receipt["lines"][position]["raw_name"] == "XY KAPUTT":
                raise RuntimeError("search gone")
            return super().__call__(position, receipt, proposal, inputs)

    reader = Breaks(search_works=True)
    reread_waiting(factory, TableMatcher({}), reader)
    session.expire_all()
    assert session.scalars(select(Resolution).where(Resolution.raw_name == "XY GUT")).one()


# --- who starts the thread ----------------------------------------------------

def _app_parts(engine, tmp_path):
    from grocery_app.api.images import DiskImageStore
    from grocery_app.api.repository import PostgresRepository
    from tests.test_upload import FakeExtractor

    return (PostgresRepository(make_session_factory(engine)),
            dict(image_store=DiskImageStore(tmp_path), extractor=FakeExtractor(),
                 matcher=TableMatcher({}), identify=Reader()))


def test_the_demo_never_starts_the_thread(engine, session, tmp_path, monkeypatch):
    from grocery_app.api.app import create_app

    started = []
    monkeypatch.setattr(matching, "keep_rereading", lambda *a, **k: started.append(a))
    monkeypatch.setattr(matching, "reread_waiting", lambda *a, **k: started.append(a) or [])
    repository, parts = _app_parts(engine, tmp_path)
    app = create_app(repository, demo=True, reread=True, **parts)
    with TestClient(app):
        thread = getattr(app.state, "rereading", None)
        if thread is not None:
            thread.join(timeout=5)
    assert started == [], "the public demo reads nothing again"


def test_a_plain_create_app_starts_nothing(engine, session, tmp_path, monkeypatch):
    from grocery_app.api.app import create_app

    started = []
    monkeypatch.setattr(matching, "keep_rereading", lambda *a, **k: started.append(a))
    repository, parts = _app_parts(engine, tmp_path)
    app = create_app(repository, **parts)
    with TestClient(app):
        pass
    assert started == [] and getattr(app.state, "rereading", None) is None


# --- added after reading the diff -------------------------------------------

class _Stop(BaseException):
    """Ends `keep_rereading`'s endless loop at its first pause."""


def test_the_servers_loop_waits_then_tags_its_calls_as_finding_and_pauses(
        factory, session, monkeypatch):
    import time

    add_receipt(session, "IMG_1.jpeg", ["XY APFEL"])
    tags, pauses = [], []

    class Tagging(Reader):
        def __call__(self, *args):
            tags.append(spend.call_record("m", {})["purpose"])
            return super().__call__(*args)

    def sleep(seconds):
        pauses.append(seconds)
        if len(pauses) == 2:
            raise _Stop

    monkeypatch.setattr(time, "sleep", sleep)
    with pytest.raises(_Stop):
        matching.keep_rereading(factory, TableMatcher({}), Tagging(search_works=True))
    assert tags == ["finding"]
    assert pauses == [30, 300], "a deploy's old server is gone before the first pass"


def test_a_receipt_of_a_file_still_being_placed_is_left_to_its_upload(factory, session):
    """A PDF export makes one receipt per purchase; the job points at the
    first, and places all of them before it is done. While it runs, none of
    them is the rereading's to match."""
    from grocery_app.db.models import Receipt

    first = add_receipt(session, "IMG_PDF_a.jpeg", ["XY EINS"])
    second = add_receipt(session, "IMG_PDF_b.jpeg", ["XY ZWEI"])
    for receipt_id in (first, second):
        session.get(Receipt, receipt_id).image_sha256 = "d" * 64
    session.add(Job(status="running", image_sha256="d" * 64, receipt_id=first))
    session.commit()
    reader = Reader(search_works=True)
    assert waiting_receipts(session) == []
    assert reread_waiting(factory, TableMatcher({}), reader) == []
    assert reader.calls == []


def test_an_answer_given_while_the_receipt_is_read_again_is_not_overridden(
        server, factory):  # noqa: F811
    """The shopper says "none of these" for line 1 while the thread is still
    on line 0 of the same receipt (a search takes seconds). Line 1 is theirs
    from then on: the thread neither reads it nor asks about it."""
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["XY WARTET", "XY SPAETER"])

    class AnswersMeanwhile(TableMatcher):
        def __call__(self, line, store, inputs):
            if line["raw_name"] == "XY WARTET":
                client.put(f"/v1/receipts/{receipt}/lines/1/resolution",
                           json={"none_of_these": True})
            return super().__call__(line, store, inputs)

    reader, matcher = Reader(search_works=True), AnswersMeanwhile({})
    reread_waiting(factory, matcher, reader)
    assert "XY SPAETER" not in matcher.calls + reader.calls
    session.expire_all()
    assert session.scalars(select(Resolution).where(
        Resolution.raw_name == "XY SPAETER")).all() == []
