"""The rule, as given to the check (2026-11-08), tested without the code.

Before a receipt's unknown lines are matched, a model may write out each
one's likely full name (the "guess").

1. At most one guess call per receipt, and only for lines the memory does not
   already place. A receipt with nothing unknown makes no call.
2. The guess only widens the search for candidates. It is never saved as an
   answer, and a product may be saved only if it is a real candidate that the
   picking step chose.
3. Everything the printed text alone would have found stays on the candidate
   list, so a guess can never remove a candidate.
4. If the guess call fails or names nothing, the receipt is still matched by
   its printed text: no line is lost and no job fails. The owner is notified
   through a log line containing GROCERY_TRAP.
5. Each line settled by the matcher records whether only the guess found its
   answer. When a shopper overrules such a line, a GROCERY_TRAP log line
   fires. A line the printed text also found fires nothing.
6. GROCERY_TRAP log lines never contain receipt text or product names, only
   ids and counts.
7. GROCERY_GUESS=off means no guess call is ever made.
8. No test makes a paid model call.

Made-up receipts, listings and fake models only; no model is called.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import urllib.request

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from grocery_app import matcher as matching
from grocery_app.api.app import create_app
from grocery_app.api.images import DiskImageStore
from grocery_app.api.matching import line_matcher, match_receipt
from grocery_app.api.repository import PostgresRepository
from grocery_app.db.models import LineResolution, Product, Question, Resolution
from grocery_app.db.session import make_session_factory
from grocery_app.identify import Identity
from grocery_app.matcher import DeciderError, found_only_by_guess, gather
from tests.conftest import DATABASE_URL as URL
from tests.test_matching_server import add_receipt, reading, server  # noqa: F401
from tests.test_upload import RECEIPT, FakeExtractor, a_photo, todays

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")

UNSET = object()
RAW = "MU H.Dr."
GUESS = "Erfundener Haferdrink Lang"
LISTED = "Hafer Trunk Natur"


def listing(article, name, price=1.19):
    """A shop listing in the shape a shop source hands to `gather`."""
    return {"article_number": article, "name": name, "brand": "Muster", "pack_size": "1 l",
            "price": price, "url": f"https://musterladen.example/{article}"}


def shop(table):
    return {"musterladen": lambda text: list(table.get(text, []))}


HAFER = listing("4000000000099", LISTED)
ONLY_THE_GUESS_FINDS = shop({GUESS: [HAFER]})
BOTH_FIND = shop({RAW: [HAFER], GUESS: [HAFER]})
ONLY_THE_PRINTED_TEXT_FINDS = shop({RAW: [HAFER]})


class Guesser:
    """A fake model: answers per printed line and keeps every prompt it was sent."""

    def __init__(self, table=None, error=None, reply=UNSET):
        self.table = table if table is not None else {RAW: GUESS}
        self.error = error
        self.reply = reply
        self.prompts = []

    def __call__(self, system, prompt, schema):
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        if self.reply is not UNSET:
            return self.reply
        return {"guesses": [{"line": n, "names": [self.table[raw]]}
                            for n, raw in enumerate(lines_asked(prompt), 1)
                            if raw in self.table]}


def lines_asked(prompt):
    section = prompt.split("Lines to write out:")[1]
    return re.findall(r"^\s*\d+\.\s+`([^`]*)`", section, flags=re.MULTILINE)


class Picks:
    """A fake picking step: takes the row naming `name`; remembers the rows it saw."""

    def __init__(self, name=LISTED, choice=None):
        self.name = name
        self.choice = choice
        self.rows = []

    def __call__(self, system, prompt, schema):
        rows = prompt.split("Products:\n")[1].splitlines()
        self.rows.append(rows)
        number = self.choice if self.choice is not None else next(
            (i for i, row in enumerate(rows, 1) if self.name in row), 0)
        return {"choice": number, "versions": [], "confidence": "high", "reason": "test"}


def all_versions(system, prompt, schema):
    rows = [r for r in prompt.split("Products:\n")[1].splitlines() if r.strip()]
    return {"choice": 0, "versions": list(range(1, len(rows) + 1)), "confidence": "high",
            "reason": "the line prints no version"}


def traps(caplog):
    return [r for r in caplog.records if "GROCERY_TRAP" in r.getMessage()]


@pytest.fixture(autouse=True)
def every_log_line(caplog):
    caplog.set_level(logging.DEBUG)


def memory(session, raw_name):
    session.expire_all()
    return session.scalars(select(Resolution).where(Resolution.raw_name == raw_name)).all()


def product_names(session):
    session.expire_all()
    return [p.name for p in session.scalars(select(Product)).all()]


# --- 1. at most one call, only for what the memory does not place --------------------


def test_a_long_receipt_of_unknown_lines_is_one_call(server):  # noqa: F811
    _, session = server
    names = [f"MU Ding {n}" for n in range(60)]
    receipt = add_receipt(session, "IMG_7.jpeg", names)
    guesser = Guesser(table={})
    match_receipt(session, receipt, line_matcher(Picks(), shop({}), guesser))
    assert len(guesser.prompts) == 1
    assert lines_asked(guesser.prompts[0]) == names


def test_only_the_lines_the_memory_does_not_place_are_asked(server):  # noqa: F811
    _, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", ["MU Milch 1,5%", RAW, "Pfand", "Bananen"])
    guesser = Guesser()
    match_receipt(session, receipt, line_matcher(Picks(), BOTH_FIND, guesser))
    assert len(guesser.prompts) == 1
    assert lines_asked(guesser.prompts[0]) == [RAW]


@pytest.mark.parametrize("names, store", [
    (["MU Milch 1,5%"], "Musterladen"),
    (["MU Milch 1,5%", "Bananen"], "musterladen"),
    (["Pfand"], "Musterladen"),
    (["MU Milch 1,5%", "Pfand"], "Musterladen"),
    (["Diverse Lebensmittel"], "FK Frisch Kauf GmbH"),
])
def test_nothing_unknown_makes_no_call_and_no_trap(server, caplog, names, store):  # noqa: F811
    _, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", names, store=store)
    guesser = Guesser()
    match_receipt(session, receipt, line_matcher(Picks(), BOTH_FIND, guesser))
    assert guesser.prompts == []
    assert traps(caplog) == []


def test_a_family_in_the_memory_is_already_placed(server):  # noqa: F811
    _, session = server
    session.add(Product(id="p-0003", name="Bananen Bio", brand=None))
    row = memory(session, "Bananen")[0]
    row.product_id, row.product_ids, row.status = None, ["p-0002", "p-0003"], "ambiguous_on_receipt"
    session.commit()
    receipt = add_receipt(session, "IMG_7.jpeg", ["Bananen"])
    guesser = Guesser()
    match_receipt(session, receipt, line_matcher(Picks(), BOTH_FIND, guesser))
    assert guesser.prompts == []


def test_a_line_the_shopper_already_answered_is_not_guessed(server):  # noqa: F811
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [RAW])
    client.put(f"/v1/receipts/{receipt}/lines/0/resolution", json={"product_id": "p-0001"})
    session.expire_all()
    guesser = Guesser()
    match_receipt(session, receipt, line_matcher(Picks(), BOTH_FIND, guesser))
    assert guesser.prompts == []


def test_matching_a_receipt_twice_guesses_once_when_a_question_is_open(server):  # noqa: F811
    _, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [RAW])
    guesser = Guesser()
    matcher = line_matcher(Picks("nothing like this"), BOTH_FIND, guesser)
    match_receipt(session, receipt, matcher)
    session.commit()
    match_receipt(session, receipt, matcher)
    session.commit()
    assert len(guesser.prompts) == 1


def unsearched(position, receipt_doc, proposal, inputs):
    return Identity("Ding", None, None, None, None, False, "not searched", unsearched=True)


# --- 2. never an answer; a product only if a real candidate was picked ---------------


def test_a_guess_nothing_lists_saves_nothing(server):  # noqa: F811
    client, session = server
    before = set(product_names(session))
    receipt = add_receipt(session, "IMG_7.jpeg", [RAW])
    match_receipt(session, receipt, line_matcher(Picks("no such row"), shop({}), Guesser()))
    session.commit()

    assert set(product_names(session)) == before
    assert memory(session, RAW) == []
    assert reading(client, receipt) == [("none", None, [])]
    served = json.dumps(client.get("/v1/questions").json(), ensure_ascii=False)
    assert GUESS not in served, "a guess is not offered to the shopper as a candidate"


def test_the_picked_listing_is_saved_under_its_own_name_not_the_guess(server):  # noqa: F811
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [RAW])
    match_receipt(session, receipt, line_matcher(Picks(), ONLY_THE_GUESS_FINDS, Guesser()))
    session.commit()

    (_, product_id, _), = reading(client, receipt)
    assert session.get(Product, product_id).name == LISTED
    assert GUESS not in product_names(session)


@pytest.mark.parametrize("choice", [0, 99, -1])
def test_a_pick_off_the_list_saves_nothing_even_with_a_guess(server, choice):  # noqa: F811
    client, session = server
    before = set(product_names(session))
    receipt = add_receipt(session, "IMG_7.jpeg", [RAW])
    match_receipt(session, receipt,
                  line_matcher(Picks(choice=choice), ONLY_THE_GUESS_FINDS, Guesser()))
    session.commit()

    assert set(product_names(session)) == before
    assert memory(session, RAW) == []
    assert reading(client, receipt)[0][1] is None


def test_nothing_the_guess_said_is_on_a_question_as_a_product(server):  # noqa: F811
    _, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [RAW])
    match_receipt(session, receipt,
                  line_matcher(Picks("no such row"), ONLY_THE_PRINTED_TEXT_FINDS, Guesser()))
    session.commit()

    (question,) = session.scalars(select(Question).where(Question.receipt_id == receipt)).all()
    names = [c.get("name") for c in question.proposal.get("candidates", [])]
    assert LISTED in names and GUESS not in names


# --- 3. a guess can never remove a candidate ------------------------------------------

MANY = 40


def catalog_like(words):
    return {f"p-{i + 1000:04d}": {"name": f"{words} {i}", "brand": "Muster", "category": None,
                                  "size": None} for i in range(MANY)}


def keys(found):
    return {(c.product_id, c.article) for c in found}


def test_many_shop_results_for_the_guess_push_out_none_of_the_printed_text():
    printed = [listing(f"1{i:03d}", f"Reinex Deo {i}") for i in range(MANY)]
    guessed = [listing(f"2{i:03d}", f"Vanille Pudding {i}") for i in range(MANY)]
    shops = shop({"Reinex Deo": printed, "Vanille Pudding": guessed})

    without = gather("Reinex Deo", "Musterladen", {}, {}, {}, {}, shops)
    widened = gather("Reinex Deo", "Musterladen", {}, {}, {}, {}, shops, ["Vanille Pudding"])
    assert without, "the printed text must have found something for this to mean anything"
    assert keys(without) - keys(widened) == set()


def test_catalog_products_close_to_the_guess_push_out_none_of_the_printed_text():
    products = {**catalog_like("Reinex Deo"),
                **{f"p-{i + 2000:04d}": {"name": f"Vanille Pudding {i}", "brand": "Muster",
                                         "category": None, "size": None} for i in range(MANY)}}
    without = gather("Reinex Deo", "Musterladen", products, {}, {}, {}, shop({}))
    widened = gather("Reinex Deo", "Musterladen", products, {}, {}, {}, shop({}),
                     "Vanille Pudding")
    assert without
    assert keys(without) - keys(widened) == set()


def test_a_guess_equal_to_listings_from_the_catalog_and_shop_keeps_every_printed_one():
    products = catalog_like("Reinex Deo")
    printed = [listing(f"1{i:03d}", f"Reinex Deo {i}") for i in range(MANY)]
    guessed = [listing(f"2{i:03d}", f"Reinex Deo Spray {i}") for i in range(MANY)]
    shops = shop({"Reinex Deo": printed, "Reinex Deo Spray": guessed})
    without = gather("Reinex Deo", "Musterladen", products, {}, {}, {}, shops)
    widened = gather("Reinex Deo", "Musterladen", products, {}, {}, {}, shops, ["Reinex Deo Spray"])
    assert without
    assert keys(without) - keys(widened) == set()


def test_two_articles_under_one_name_do_not_merge_away_the_printed_one():
    shops = shop({"Reinex Deo": [listing("1", "Reinex Deo")],
                  "Vanille": [listing("2", "Reinex Deo")]})
    widened = gather("Reinex Deo", "Musterladen", {}, {}, {}, {}, shops, ["Vanille"])
    assert "1" in {c.article for c in widened}


def test_the_crawl_keeps_the_printed_results_when_a_guess_is_searched_too(tmp_path):
    path = tmp_path / "globus" / "crawl.json"
    path.parent.mkdir(parents=True)
    rows = [("Reinex", f"Deo Kuehlschrank {i}") for i in range(MANY)] + \
        [("Muster", f"Vanille Pudding {i}") for i in range(MANY)]
    path.write_text(json.dumps({f"4{i:012d}": {"article_number": f"4{i:012d}", "name": name,
                                               "brand": brand, "price": 1.0}
                                for i, (brand, name) in enumerate(rows)}), encoding="utf-8")
    shops = matching.default_shops(tmp_path)
    without = gather("Reinex Deo Kuehlschr", "GLOBUS", {}, {}, {}, {}, shops)
    widened = gather("Reinex Deo Kuehlschr", "GLOBUS", {}, {}, {}, {}, shops, ["Vanille Pudding"])
    assert without
    assert keys(without) - keys(widened) == set()


def test_the_list_the_picker_and_the_shopper_see_keeps_every_printed_candidate(server):  # noqa: F811
    client, session = server
    printed = [listing(f"1{i:03d}", f"Reinex Deo {i}") for i in range(MANY)]
    guessed = [listing(f"2{i:03d}", f"Vanille Pudding {i}") for i in range(MANY)]
    table = {"MU Deo Eins": printed, "MU Deo Zwei": printed, "Vanille Pudding": guessed}
    plain = add_receipt(session, "IMG_7.jpeg", ["MU Deo Eins"])
    widened = add_receipt(session, "IMG_8.jpeg", ["MU Deo Zwei"])

    no_guess_picker, guess_picker = Picks("no such row"), Picks("no such row")
    match_receipt(session, plain, line_matcher(no_guess_picker, shop(table)))
    match_receipt(session, widened, line_matcher(
        guess_picker, shop(table), Guesser(table={"MU Deo Zwei": "Vanille Pudding"})))
    session.commit()

    def names(rows):
        return {re.sub(r"^\s*\d+\.\s*", "", row).split("|")[0].strip() for row in rows}

    shown_alone, shown_widened = names(no_guess_picker.rows[0]), names(guess_picker.rows[0])
    assert shown_alone
    assert shown_alone - shown_widened == set(), "the picking step lost a printed candidate"

    questions = {q["raw_name"]: {c["name"] for c in q["candidates"]}
                 for q in client.get("/v1/questions").json()["questions"]}
    assert questions["MU Deo Eins"] - questions["MU Deo Zwei"] == set(), \
        "the shopper's list lost a printed candidate"


def test_a_shop_search_that_breaks_on_the_guess_keeps_the_printed_candidates():
    def source(text):
        if text == "Vanille Pudding":
            raise RuntimeError("the shop's search broke")
        return [listing("1", "Reinex Deo")]

    widened = gather("Reinex Deo", "Musterladen", {}, {}, {}, {}, {"musterladen": source},
                     "Vanille Pudding")
    assert "1" in {c.article for c in widened}


# --- 4. a failed or empty guess: printed text, nothing lost, the owner told ----------

FAILURES = [
    DeciderError("refused"), RuntimeError("model gone"), TimeoutError("timed out"),
    ConnectionError("no route"), KeyError("guesses"), ValueError("bad json"),
    json.JSONDecodeError("bad", "doc", 0),
    subprocess.TimeoutExpired("claude", 30),
]

EMPTY_OR_BROKEN_REPLIES = [
    None, [], "words", 7, {}, {"guesses": None}, {"guesses": "x"}, {"guesses": []},
    {"guesses": [None]}, {"guesses": ["x"]}, {"guesses": [{}]},
    {"guesses": [{"line": 1}]}, {"guesses": [{"names": ["x"]}]},
    {"guesses": [{"line": "one", "names": ["x"]}]}, {"guesses": [{"line": 1.5, "names": ["x"]}]},
    {"guesses": [{"line": 1, "names": None}]}, {"guesses": [{"line": 1, "names": 7}]},
    {"guesses": [{"line": 1, "names": [""]}]}, {"guesses": [{"line": 99, "names": ["x"]}]},
]


def assert_matched_by_printed_text(client, session, receipt, caplog):
    assert [r[0] for r in reading(client, receipt)] == ["exact", "exact"]
    for name in (RAW, "MU Anderes"):
        (entry,) = memory(session, name)
        assert not found_only_by_guess(entry.source)
    assert traps(caplog), "the owner must be told"


def two_lines_found_by_print():
    other = listing("4000000000088", "Anderes Natur")
    return shop({RAW: [HAFER], "MU Anderes": [other]}), Picks("Natur")


@pytest.mark.parametrize("error", FAILURES, ids=lambda e: type(e).__name__)
def test_a_guess_call_that_fails_leaves_the_printed_text_to_match(server, caplog, error):  # noqa: F811
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [RAW, "MU Anderes"])
    shops, picks = two_lines_found_by_print()
    match_receipt(session, receipt, line_matcher(picks, shops, Guesser(error=error)))
    session.commit()
    assert_matched_by_printed_text(client, session, receipt, caplog)


@pytest.mark.parametrize("reply", EMPTY_OR_BROKEN_REPLIES, ids=repr)
def test_a_guess_that_names_nothing_leaves_the_printed_text_to_match(server, caplog, reply):  # noqa: F811
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [RAW, "MU Anderes"])
    shops, picks = two_lines_found_by_print()
    match_receipt(session, receipt, line_matcher(picks, shops, Guesser(reply=reply)))
    session.commit()
    assert_matched_by_printed_text(client, session, receipt, caplog)


def test_a_guess_for_one_line_of_two_loses_neither(server):  # noqa: F811
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [RAW, "MU Anderes"])
    shops, picks = two_lines_found_by_print()
    match_receipt(session, receipt, line_matcher(picks, shops, Guesser(table={RAW: GUESS})))
    session.commit()
    assert [r[0] for r in reading(client, receipt)] == ["exact", "exact"]


@pytest.mark.parametrize("guesser", [
    Guesser(error=RuntimeError("model gone")), Guesser(reply={"guesses": []})],
    ids=["fails", "names-nothing"])
def test_an_upload_job_finishes_with_its_line_placed(engine, session, tmp_path, caplog, guesser):
    butter = listing("4000000000077", "Deutsche Markenbutter", price=1.29)
    repository = PostgresRepository(make_session_factory(engine))
    client = TestClient(create_app(
        repository, DiskImageStore(tmp_path / "uploads"), FakeExtractor(todays(RECEIPT)),
        line_matcher(Picks("Markenbutter"), shop({"MU Butter": [butter]}), guesser)))

    queued = client.post("/v1/receipts",
                         files={"file": ("image.jpg", a_photo(), "image/jpeg")}).json()
    job = client.get(f"/v1/jobs/{queued['job_id']}").json()

    assert job["status"] == "done" and not job["error"]
    (line,) = client.get(f"/v1/receipts/{job['receipt_id']}").json()["lines"]
    assert line["resolution"] == "exact" and line["product"] == "Deutsche Markenbutter"
    assert traps(caplog)


def test_a_guess_that_works_fires_no_trap(server, caplog):  # noqa: F811
    _, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [RAW])
    match_receipt(session, receipt, line_matcher(Picks(), BOTH_FIND, Guesser()))
    session.commit()
    assert traps(caplog) == []


# --- 5. recording who found it; the trap when a shopper overrules --------------------


def settle(server, shops, picks=None, guesser=None):  # noqa: F811
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [RAW])
    match_receipt(session, receipt, line_matcher(picks or Picks(), shops, guesser or Guesser()))
    session.commit()
    return client, session, receipt


def overrule(client, receipt, answer):
    response = client.put(f"/v1/receipts/{receipt}/lines/0/resolution", json=answer)
    assert response.status_code == 200, response.text
    return response


def test_the_record_says_only_the_guess_found_it(server):  # noqa: F811
    _, session, _ = settle(server, ONLY_THE_GUESS_FINDS)
    (entry,) = memory(session, RAW)
    assert found_only_by_guess(entry.source) is True


def test_the_record_says_the_printed_text_found_it_too(server):  # noqa: F811
    _, session, _ = settle(server, BOTH_FIND)
    (entry,) = memory(session, RAW)
    assert found_only_by_guess(entry.source) is False


def test_the_record_says_printed_when_only_the_printed_text_found_it(server):  # noqa: F811
    _, session, _ = settle(server, ONLY_THE_PRINTED_TEXT_FINDS)
    (entry,) = memory(session, RAW)
    assert found_only_by_guess(entry.source) is False


OVERRULES = [{"product_id": "p-0002"}, {"none_of_these": True},
             {"new_product": {"description": "Etwas ganz anderes"}}]
IDS = ["other-product", "none-of-these", "described"]


@pytest.mark.parametrize("answer", OVERRULES, ids=IDS)
def test_overruling_a_line_only_the_guess_found_fires(server, caplog, answer):  # noqa: F811
    client, _, receipt = settle(server, ONLY_THE_GUESS_FINDS)
    caplog.clear()
    overrule(client, receipt, answer)
    assert traps(caplog), "the owner must hear about a pick only the guess found"


@pytest.mark.parametrize("answer", OVERRULES, ids=IDS)
def test_overruling_a_line_the_printed_text_found_fires_nothing(server, caplog, answer):  # noqa: F811
    client, _, receipt = settle(server, BOTH_FIND)
    caplog.clear()
    overrule(client, receipt, answer)
    assert traps(caplog) == []


def test_agreeing_with_a_line_only_the_guess_found_fires_nothing(server, caplog):  # noqa: F811
    client, _, receipt = settle(server, ONLY_THE_GUESS_FINDS)
    picked = reading(client, receipt)[0][1]
    caplog.clear()
    overrule(client, receipt, {"product_id": picked})
    assert traps(caplog) == []


def test_overruling_the_same_guess_found_line_on_a_later_receipt_fires(server, caplog):  # noqa: F811
    client, session, _ = settle(server, ONLY_THE_GUESS_FINDS)
    later = add_receipt(session, "IMG_8.jpeg", [RAW])
    caplog.clear()
    overrule(client, later, {"product_id": "p-0002"})
    assert traps(caplog), "the memory holds a pick only the guess found, whichever receipt shows it"


def test_a_family_only_the_guess_found_fires_when_overruled(server, caplog):  # noqa: F811
    shops = shop({GUESS: [listing("11", "Hafer Trunk Natur"), listing("12", "Hafer Trunk Bio")]})
    client, session, receipt = settle(server, shops, picks=all_versions)
    assert reading(client, receipt)[0][0] == "family"
    (entry,) = memory(session, RAW)
    assert found_only_by_guess(entry.source) is True
    session.add(Product(id="p-0099", name="Ganz etwas anderes", brand=None))
    session.commit()
    assert "p-0099" not in entry.product_ids
    caplog.clear()
    overrule(client, receipt, {"product_id": "p-0099"})
    assert traps(caplog)


def test_choosing_one_version_of_a_family_only_the_guess_found_is_no_correction(server, caplog):  # noqa: F811
    shops = shop({GUESS: [listing("11", "Hafer Trunk Natur"), listing("12", "Hafer Trunk Bio")]})
    client, session, receipt = settle(server, shops, picks=all_versions)
    (entry,) = memory(session, RAW)
    caplog.clear()
    overrule(client, receipt, {"product_id": entry.product_ids[0]})
    assert traps(caplog) == []


def test_a_family_the_printed_text_found_fires_nothing_when_overruled(server, caplog):  # noqa: F811
    versions = [listing("11", "Hafer Trunk Natur"), listing("12", "Hafer Trunk Bio")]
    client, session, receipt = settle(server, shop({RAW: versions, GUESS: versions}),
                                      picks=all_versions)
    assert reading(client, receipt)[0][0] == "family"
    caplog.clear()
    overrule(client, receipt, {"product_id": "p-0002"})
    assert traps(caplog) == []


def test_a_shop_listing_found_by_the_guess_but_held_as_a_printed_catalog_hit_is_not_guess_only():
    """The printed text finds our product in the catalog; the guess finds that
    product's shop listing. The printed text found this answer too."""
    products = {"p-0001": {"name": "Reinex Deo", "brand": "Reinex", "category": None,
                           "size": None}}
    index = {"4000000000011": "p-0001"}
    shops = shop({"Vanille Pudding": [listing("4000000000011", "Reinex Deo Original")]})
    (found,) = [c for c in gather("Reinex Deo", "Musterladen", products, {}, {}, index, shops,
                                  "Vanille Pudding") if c.product_id == "p-0001"]
    assert "printed" in found.found_by


# --- 6. the traps name ids and counts only -------------------------------------------


def assert_no_receipt_text(caplog, *forbidden):
    fired = traps(caplog)
    assert fired, "this test only means something if a trap fired"
    for record in fired:
        everything = f"{record.getMessage()} {record.exc_text or ''} {vars(record)!r}"
        for text in forbidden:
            assert text not in everything, f"{text!r} is in a GROCERY_TRAP line"
        assert re.fullmatch(r"\s*GROCERY_TRAP [\w-]+( [\w.-]+=[\w.-]+)*\s*",
                            record.getMessage()), record.getMessage()


SECRET_LINE = "MU Geheimzutat Zeile"
SECRET_GUESS = "Erfundene Geheimzutat Lang"
SECRET_PRODUCT = "Heimliches Produkt Xyz"


@pytest.mark.parametrize("error", [
    DeciderError(f"refused `{SECRET_LINE}` as {SECRET_GUESS}"),
    RuntimeError(f"could not parse {SECRET_LINE} from Musterladen"),
    KeyError(SECRET_LINE)], ids=["decider", "runtime", "keyerror"])
def test_a_failed_guess_keeps_the_receipt_out_of_the_trap(server, caplog, error):  # noqa: F811
    _, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [SECRET_LINE])
    match_receipt(session, receipt, line_matcher(Picks("no row"), shop({}), Guesser(error=error)))
    session.commit()
    assert_no_receipt_text(caplog, SECRET_LINE, SECRET_GUESS, "Musterladen")


def test_a_guess_that_names_nothing_keeps_the_receipt_out_of_the_trap(server, caplog):  # noqa: F811
    _, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [SECRET_LINE])
    match_receipt(session, receipt,
                  line_matcher(Picks("no row"), shop({}), Guesser(reply={"guesses": []})))
    session.commit()
    assert_no_receipt_text(caplog, SECRET_LINE, "Musterladen")


@pytest.mark.parametrize("answer", OVERRULES, ids=IDS)
def test_an_overruled_guess_keeps_the_names_out_of_the_trap(server, caplog, answer):  # noqa: F811
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [SECRET_LINE])
    shops = shop({SECRET_GUESS: [listing("4000000000055", SECRET_PRODUCT)]})
    match_receipt(session, receipt, line_matcher(Picks(SECRET_PRODUCT), shops,
                                                 Guesser(table={SECRET_LINE: SECRET_GUESS})))
    session.commit()
    caplog.clear()
    overrule(client, receipt, answer)
    assert_no_receipt_text(caplog, SECRET_LINE, SECRET_GUESS, SECRET_PRODUCT, "Musterladen",
                           "Bananen", "Etwas ganz anderes")


# --- 7. GROCERY_GUESS=off ------------------------------------------------------------


@pytest.mark.parametrize("value", ["off", "OFF", " Off "])
def test_off_means_the_server_is_wired_with_no_guesser(monkeypatch, value):
    from grocery_app.api.app import guess_decider

    monkeypatch.setenv("GROCERY_GUESS", value)
    assert guess_decider("gemini") is None


def test_the_server_guesses_unless_switched_off(monkeypatch):
    from grocery_app.api.app import guess_decider

    monkeypatch.delenv("GROCERY_GUESS", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "made-up, and no call is made")
    assert guess_decider("gemini") is not None


# --- 8. nothing here is paid ----------------------------------------------------------


def no_outside_call(*args, **kwargs):
    raise AssertionError("a test reached a real model")


def test_no_guesser_given_means_nothing_leaves_the_process(server, monkeypatch):  # noqa: F811
    monkeypatch.setattr(subprocess, "run", no_outside_call)
    monkeypatch.setattr(urllib.request, "urlopen", no_outside_call)
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [RAW])
    match_receipt(session, receipt, line_matcher(Picks(), ONLY_THE_PRINTED_TEXT_FINDS))
    session.commit()
    assert reading(client, receipt)[0][0] == "exact"


def test_a_shopper_answer_is_kept_for_the_line_it_was_given_to(server):  # noqa: F811
    """A guard on the fakes above: an answered line stays answered after matching."""
    client, session = server
    receipt = add_receipt(session, "IMG_7.jpeg", [RAW])
    overrule(client, receipt, {"product_id": "p-0001"})
    session.expire_all()
    assert session.scalars(select(LineResolution).where(
        LineResolution.receipt_id == receipt)).one().product_id == "p-0001"
