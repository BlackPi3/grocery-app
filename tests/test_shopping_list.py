"""The shopping list over made-up purchase rows: nothing here comes from a receipt."""

from datetime import UTC, date, datetime, timedelta

import pytest

from grocery_app import shopping_list as sl
from grocery_app.evaluate_list import backtest, format_report, gap_rule
from grocery_app.shopping_list import (
    chance,
    kinds,
    list_rows,
    runs_out,
    shopping_list,
    snooze_days,
    with_edits,
)
from tests.conftest import DATABASE_URL

START = date(2026, 1, 1)


def row(kind, day, pid="p-1", qty=1, net=1.0, unit=None, per=None, product="Ding",
        brand="Marke", **extra):
    return {"type": "product", "date": day.isoformat(), "category": kind,
            "category_path": ["Abteilung", "Regal", kind.title()],
            "product_id": pid, "product": product, "brand": brand, "qty": qty,
            "net_paid": net, "unit_price": {"amount": unit, "per": per} if unit else None,
            **extra}


def every(kind, days, start=START, times=10, **kw):
    return [row(kind, start + timedelta(days=days * i), **kw) for i in range(times)]


# --- chance --------------------------------------------------------------------

def test_a_weekly_buy_is_likely_this_week_and_a_monthly_one_is_not():
    weekly = [START + timedelta(days=7 * i) for i in range(12)]
    monthly = [START + timedelta(days=28 * i) for i in range(3)]
    as_of = START + timedelta(days=84)
    # Once a week is a rate of 1/7 a day: 1 - e^-1 = 63% of a buy in 7 days,
    # a little less here, as the last buy was a week ago.
    assert 0.55 < chance(weekly, START, as_of) < 0.64
    assert chance(monthly, START, as_of) < 0.3


def test_recent_buys_count_more_than_old_ones():
    # Same number of buying days: early in the history, or lately.
    early = [START + timedelta(days=i) for i in range(0, 30, 5)]
    lately = [START + timedelta(days=i) for i in range(60, 90, 5)]
    as_of = START + timedelta(days=90)
    assert chance(lately, START, as_of) > 2 * chance(early, START, as_of)


def test_a_stopped_habit_leaves_the_list():
    rows = every("quark", 4, times=10)                      # to day 36
    rows += every("brot", 7, times=20)                      # still going
    as_of = START + timedelta(days=140)
    assert [k["kind"] for k in shopping_list(rows, as_of)] == ["brot"]


# --- runs out ------------------------------------------------------------------

def test_two_tubs_last_twice_as_long_as_one():
    days = [(START, 1.0), (START + timedelta(days=5), 1.0), (START + timedelta(days=10), 2.0)]
    out, per_buy = runs_out(days)
    assert per_buy == 5
    assert out == START + timedelta(days=20)


def test_units_do_not_mix_a_weighed_line_counts_against_weighed_lines():
    # 0.5 kg loose twice, then a 1 kg bag: the bag is two usual buys. A pack
    # with no weight beside them is one usual buy of its own unit.
    rows = [row("tomaten", START, net=1.0, unit=2.0, per="kg"),
            row("tomaten", START + timedelta(days=4), net=1.0, unit=2.0, per="kg"),
            row("tomaten", START + timedelta(days=8), net=1.0),
            row("tomaten", START + timedelta(days=12), net=2.0, unit=2.0, per="kg")]
    line = kinds(rows, START + timedelta(days=13))[0]
    assert line["days_per_buy"] == 4
    assert line["runs_out"] == (START + timedelta(days=20)).isoformat()


def test_urgency_follows_the_day_it_runs_out():
    rows = every("milch", 4, times=6)                       # last on day 20
    as_of = START + timedelta(days=21)
    assert kinds(rows, as_of)[0]["when"] == "this_week"     # out on day 24
    assert kinds(rows, START + timedelta(days=24))[0]["when"] == "now"
    rows = every("reis", 14, times=6)                       # last on day 70, out on 84
    assert kinds(rows, START + timedelta(days=71))[0]["when"] == "later"


# --- the list ------------------------------------------------------------------

def test_the_list_takes_kinds_above_the_chance_most_urgent_first():
    rows = (every("quark", 3, times=20, pid="p-q")
            + every("brot", 7, times=9, pid="p-b")
            + every("salz", 40, times=2, pid="p-s"))
    as_of = START + timedelta(days=61)
    out = shopping_list(rows, as_of)
    assert {k["kind"] for k in out} == {"quark", "brot"}    # salt: twice in 40 days
    assert [k["when"] for k in out] == sorted((k["when"] for k in out),
                                              key=["now", "this_week", "later"].index)
    assert all(k["chance"] >= sl.LIST_CHANCE for k in out)


def test_a_kind_bought_once_is_not_judged():
    assert kinds([row("eis", START)], START + timedelta(days=3)) == []


def test_only_what_was_bought_before_the_day_counts():
    rows = every("milch", 3, times=10)
    as_of = START + timedelta(days=9)
    assert kinds(rows, as_of)[0]["last_bought"] == (START + timedelta(days=6)).isoformat()


def test_the_usual_product_is_the_most_frequent_of_the_last_few():
    days = [START + timedelta(days=i) for i in range(0, 70, 7)]
    pids = ["p-old"] * 5 + ["p-new", "p-new", "p-new", "p-other", "p-other"]
    rows = [row("kaese", d, pid=p, product=p.upper()) for d, p in zip(days, pids, strict=True)]
    line = kinds(rows, START + timedelta(days=70))[0]
    assert line["usual"]["product_id"] == "p-new"
    assert line["products"] == 3


def test_of_two_equally_frequent_products_the_last_bought_is_usual():
    rows = [row("kaese", START, pid="p-a"), row("kaese", START + timedelta(days=7), pid="p-b"),
            row("kaese", START + timedelta(days=14), pid="p-a"),
            row("kaese", START + timedelta(days=21), pid="p-b")]
    assert kinds(rows, START + timedelta(days=22))[0]["usual"]["product_id"] == "p-b"


def test_list_rows_keep_the_shoppers_own_dated_groceries():
    purchases = {"purchases": [
        row("quark", START),
        row("cafe-imbiss", START),                          # not groceries
        row("quark", START, not_counted=True),              # bought for someone else
        {**row("quark", START), "date": None},              # a receipt with no date
        {**row("quark", START), "type": "deposit"},
    ]}
    assert list_rows(purchases) == [purchases["purchases"][0]]


# --- the person's edits --------------------------------------------------------

# Quark every 6 days to day 54, bread every 7 to day 53: both on the list
# for day 58, the morning after day 57.
STEADY = every("quark", 6, times=10) + every("brot", 7, times=9, start=START - timedelta(days=3))
DAY = START + timedelta(days=57)


def edit(kind, edit, day):
    return {"kind": kind, "edit": edit, "day": day}


def listed(result):
    return [line["kind"] for line in result["lines"]]


def test_with_no_edits_the_list_is_the_draft_for_the_morning_after():
    result = with_edits(STEADY, [], DAY)
    assert result["lines"] == [{**k, "added": False, "crossed": False, "typed": False}
                               for k in shopping_list(STEADY, DAY + timedelta(days=1))]
    assert set(listed(result)) == {"quark", "brot"} and result["snoozed"] == []


def test_todays_receipt_counts():
    today = START + timedelta(days=54)                       # quark bought today
    assert "quark" in listed(with_edits(STEADY, [], today - timedelta(days=1)))
    assert "quark" not in listed(with_edits(STEADY, [], today)), "just bought"


def test_a_kind_just_bought_is_not_suggested_until_half_a_usual_buy_has_passed():
    """The owner, 2026-10-25: "these aren't suggestions when I just bought
    them". Eggs every 6 days: back on the list 3 days after a buy, whatever
    their chance."""
    rows = every("eier", 6, times=10)                        # last on day 54
    assert [k["kind"] for k in kinds(rows, START + timedelta(days=56))] == ["eier"]
    assert shopping_list(rows, START + timedelta(days=56)) == []
    assert [k["kind"] for k in shopping_list(rows, START + timedelta(days=57))] == ["eier"]


def test_a_first_removal_snoozes_for_half_a_usual_buy():
    result = with_edits(STEADY, [edit("quark", "remove", DAY)], DAY)
    assert listed(result) == ["brot"]
    assert result["snoozed"] == [{"kind": "quark", "name": "Quark",
                                  "until": (DAY + timedelta(days=3)).isoformat(), "times": 1}]
    assert "quark" not in listed(with_edits(STEADY, [edit("quark", "remove", DAY)],
                                            DAY + timedelta(days=2)))
    assert "quark" in listed(with_edits(STEADY, [edit("quark", "remove", DAY)],
                                        DAY + timedelta(days=3))), "back on the third day"


def test_each_removal_without_a_buy_snoozes_twice_as_long():
    assert [snooze_days(6, n) for n in (1, 2, 3, 4)] == [3, 6, 12, 24]
    second = DAY + timedelta(days=3)
    edits = [edit("quark", "remove", DAY), edit("quark", "remove", second)]
    snoozed = with_edits(STEADY, edits, second)["snoozed"]
    assert snoozed == [{"kind": "quark", "name": "Quark",
                        "until": (second + timedelta(days=6)).isoformat(), "times": 2}]


def test_a_short_lived_kind_is_snoozed_for_a_day_at_least():
    assert snooze_days(1, 1) == 1 and snooze_days(0.4, 1) == 1


def test_a_buy_ends_the_snooze_and_the_next_removal_is_a_first_one_again():
    edits = [edit("quark", "remove", DAY), edit("quark", "remove", DAY + timedelta(days=3))]
    bought = STEADY + [row("quark", DAY + timedelta(days=4))]
    later = DAY + timedelta(days=7)                         # on the list again
    assert "quark" in listed(with_edits(bought, edits, later + timedelta(days=4))), \
        "bought after the removals: nothing is snoozed"
    again = edits + [edit("quark", "remove", later)]
    assert with_edits(bought, again, later)["snoozed"][0]["times"] == 1


def test_a_removal_on_the_day_of_a_buy_is_undone_by_the_buy():
    bought = STEADY + [row("quark", DAY)]
    assert with_edits(bought, [edit("quark", "remove", DAY)], DAY)["snoozed"] == []


def test_an_added_kind_comes_first_as_needed_now_until_it_is_bought():
    rows = STEADY + [row("reibekaese", START + timedelta(days=2))]    # bought once
    added = with_edits(rows, [edit("reibekaese", "add", DAY)], DAY)
    assert listed(added)[0] == "reibekaese"
    line = added["lines"][0]
    assert line["added"] and line["when"] == "now" and line["chance"] is None
    assert line["name"] == "Reibekaese" and line["usual"]["product_id"] == "p-1"
    assert line["last_bought"] == (START + timedelta(days=2)).isoformat()
    bought = rows + [row("reibekaese", DAY + timedelta(days=1))]
    crossed = with_edits(bought, [edit("reibekaese", "add", DAY)], DAY + timedelta(days=1))
    assert crossed["lines"][0]["kind"] == "reibekaese" and crossed["lines"][0]["crossed"], \
        "the receipt crosses it off for the rest of the day"
    assert "reibekaese" not in listed(with_edits(bought, [edit("reibekaese", "add", DAY)],
                                                 DAY + timedelta(days=2)))


def test_a_kind_never_bought_can_be_added_by_its_name():
    line = with_edits(STEADY, [edit("toilettenpapier", "add", DAY)], DAY)["lines"][0]
    assert (line["kind"], line["name"], line["usual"], line["last_bought"]) == (
        "toilettenpapier", "Toilettenpapier", None, None)


def test_putting_a_snoozed_kind_back_lists_it_as_added():
    edits = [edit("quark", "remove", DAY), edit("quark", "add", DAY)]
    result = with_edits(STEADY, edits, DAY)
    assert listed(result) == ["quark", "brot"] and result["snoozed"] == []
    assert result["lines"][0]["added"] and result["lines"][0]["chance"] is not None


def test_an_added_kind_can_be_snoozed_and_comes_back_on_the_list():
    """The owner, 2026-10-26: anything on the list can be snoozed. One of the
    person's own, with no usual buy to go by, for a day, then two, then four."""
    edits = [edit("toilettenpapier", "add", DAY), edit("toilettenpapier", "remove", DAY)]
    result = with_edits(STEADY, edits, DAY)
    assert "toilettenpapier" not in listed(result)
    assert result["snoozed"] == [{"kind": "toilettenpapier", "name": "Toilettenpapier",
                                  "until": (DAY + timedelta(days=1)).isoformat(), "times": 1}]
    back = with_edits(STEADY, edits, DAY + timedelta(days=1))
    assert back["lines"][0]["kind"] == "toilettenpapier" and back["lines"][0]["added"]
    twice = edits + [edit("toilettenpapier", "remove", DAY + timedelta(days=1))]
    assert with_edits(STEADY, twice, DAY + timedelta(days=1))["snoozed"][0]["until"] == \
        (DAY + timedelta(days=3)).isoformat()


# --- the paper list (owner, 2026-10-26) -------------------------------------------

def test_typed_words_are_a_line_of_their_own_until_deleted():
    edits = [edit("Geburtstagskerzen", "write", DAY)]
    line = with_edits(STEADY, edits, DAY)["lines"][0]
    assert (line["kind"], line["name"], line["typed"], line["added"], line["crossed"]) == (
        "Geburtstagskerzen", "Geburtstagskerzen", True, True, False)
    assert line["usual"] is None and line["when"] == "now"
    assert "Geburtstagskerzen" in listed(with_edits(STEADY, edits, DAY + timedelta(days=9))), \
        "a typed line waits for the person, not for a usual buy"
    gone = edits + [edit("Geburtstagskerzen", "delete", DAY + timedelta(days=1))]
    result = with_edits(STEADY, gone, DAY + timedelta(days=1))
    assert "Geburtstagskerzen" not in listed(result) and result["snoozed"] == []


def test_a_crossed_line_stays_crossed_today_and_is_gone_tomorrow():
    edits = [edit("Geburtstagskerzen", "write", DAY), edit("Geburtstagskerzen", "cross", DAY)]
    assert with_edits(STEADY, edits, DAY)["lines"][0]["crossed"]
    assert "Geburtstagskerzen" not in listed(with_edits(STEADY, edits, DAY + timedelta(days=1)))
    undone = edits + [edit("Geburtstagskerzen", "uncross", DAY)]
    assert not with_edits(STEADY, undone, DAY)["lines"][0]["crossed"], "a mistap undone"
    assert "Geburtstagskerzen" in listed(with_edits(STEADY, undone, DAY + timedelta(days=1)))


def test_a_receipt_crosses_off_a_typed_line_whose_words_end_what_was_bought():
    """`Tomaten` is bought as Rispentomaten, `Milch` as H-Milch; a receipt
    from before the line was typed buys nothing for it."""
    rows = STEADY + [row("gemuese", DAY, item="Rispentomaten", product="Rispentomaten lose"),
                     row("milch", DAY, item="H-Milch", product="Haltbare Milch 1,5%")]
    edits = [edit("Tomaten", "write", DAY), edit("milch", "write", DAY),
             edit("Brot vom Bäcker", "write", DAY)]
    result = with_edits(rows, edits, DAY)
    crossed = {line["kind"]: line["crossed"] for line in result["lines"] if line["typed"]}
    assert crossed == {"Tomaten": True, "milch": True, "Brot vom Bäcker": False}
    earlier = [edit("Tomaten", "write", DAY + timedelta(days=1))]
    line = with_edits(rows, earlier, DAY + timedelta(days=1))["lines"][0]
    assert line["kind"] == "Tomaten" and not line["crossed"]


def test_too_short_typed_words_are_never_crossed_off_by_a_receipt():
    from grocery_app.shopping_list import bought_as

    brei = row("babynahrung", DAY, item="Brei", product="Hirsebrei")
    assert not bought_as("Ei", brei)
    assert bought_as("brei", brei)


def test_crossing_off_a_suggested_item_counts_as_a_buy_until_the_receipt_comes():
    """Quark every 6 days, last bought day 54: on the list on day 57. Put on
    and crossed off then, it is not suggested again the next day, as if
    bought (half a usual buy, 3 days, must pass)."""
    today = START + timedelta(days=57)
    assert "quark" in listed(with_edits(STEADY, [], today))
    edits = [edit("quark", "add", today), edit("quark", "cross", today)]
    assert with_edits(STEADY, edits, today)["lines"][0]["crossed"]
    assert "quark" not in listed(with_edits(STEADY, edits, today + timedelta(days=1)))
    assert "quark" in listed(with_edits(STEADY, edits, today + timedelta(days=3)))


def test_crosses_with_no_receipt_since_are_said_on_home_for_three_days():
    """The owner, 2026-10-26: "a home line saying you crossed off but didn't
    upload receipt". STEADY's last receipt is from day 56."""
    edits = [edit("Kerzen", "write", DAY), edit("Kerzen", "cross", DAY),
             edit("quark", "add", DAY), edit("quark", "cross", DAY),
             edit("brot", "add", DAY), edit("brot", "cross", DAY),
             edit("brot", "uncross", DAY)]
    assert with_edits(STEADY, edits, DAY)["unscanned"] == {"day": DAY.isoformat(), "items": 2}
    assert with_edits(STEADY, edits, DAY + timedelta(days=2))["unscanned"]["items"] == 2
    assert with_edits(STEADY, edits, DAY + timedelta(days=3))["unscanned"] is None, \
        "after three days the receipt is not coming"
    scanned = STEADY + [row("milch", DAY)]
    assert with_edits(scanned, edits, DAY)["unscanned"] is None, "a receipt of that day"
    assert with_edits(STEADY, [], DAY)["unscanned"] is None


def test_a_typed_line_can_be_snoozed():
    edits = [edit("Kerzen", "write", DAY), edit("Kerzen", "remove", DAY)]
    result = with_edits(STEADY, edits, DAY)
    assert "Kerzen" not in listed(result) and result["snoozed"][0]["kind"] == "Kerzen"
    assert "Kerzen" in listed(with_edits(STEADY, edits, DAY + timedelta(days=1)))


# --- the backtest --------------------------------------------------------------

def test_a_steady_shopper_is_caught_and_the_report_reads():
    """Bread every 7 days, last bought the day before each week is drafted:
    the list leaves it out as just bought, and misses it."""
    rows = every("quark", 3, times=40) + every("brot", 7, times=18)
    result = backtest(rows, weeks=4)
    assert result["methods"]["chance >= 25%, just bought too"] == {
        "per_week": 2.0, "bought": 1.0, "caught": 1.0}
    assert result["methods"]["chance >= 25%"]["bought"] == 1.0
    assert result["methods"]["chance >= 25%"]["caught"] < 1.0
    assert "gap rule" in format_report(result)


def test_the_gap_rule_calls_a_kind_due_when_its_median_gap_ends_within_the_week():
    rows = every("quark", 10, times=4) + every("brot", 30, times=2)   # quark last on day 30
    assert gap_rule(rows, START + timedelta(days=34)) == {"quark"}     # brot: two days only
    assert gap_rule(rows, START + timedelta(days=80)) == set()        # three gaps and a week on


def test_an_empty_history_has_nothing_to_test():
    assert backtest([])["weeks"] == 0
    assert "nothing to test" in format_report({"weeks": 0})


# --- on the server (PostgreSQL) --------------------------------------------------

db = pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set")


@pytest.fixture
def two_lists(engine, session):
    """The owner buys milk every 7 days lately; Sara buys bananas every 5."""
    from grocery_app.api.repository import PostgresRepository
    from grocery_app.db.io import product_from_dict, receipt_from_dict, resolution_from_dict
    from grocery_app.db.session import make_session_factory
    from grocery_app.offers import GERMANY
    from tests.conftest import PRODUCTS, RESOLUTION

    for pid, product in PRODUCTS["products"].items():
        session.add(product_from_dict(pid, product))
    for entry in RESOLUTION["entries"]:
        session.add(resolution_from_dict(entry))
    session.commit()
    repository = PostgresRepository(make_session_factory(engine))
    sara = repository.create_user("Sara")
    today = datetime.now(UTC).astimezone(GERMANY).date()

    def receipt(image, days_ago, raw_name, user_id=None):
        made = receipt_from_dict({
            "source_image": image, "store": "Musterladen",
            "date": (today - timedelta(days=days_ago)).isoformat(), "currency": "EUR",
            "lines": [{"type": "product", "raw_name": raw_name, "qty": 1, "gross": 1.0,
                       "discount": 0.0, "net": 1.0, "tax_class": "A"}]})
        made.user_id = user_id
        return made

    for days_ago in (5, 12, 19, 26):
        session.add(receipt(f"o{days_ago}.jpeg", days_ago, "MU Milch 1,5%"))
    for days_ago in (4, 9, 14, 19):
        session.add(receipt(f"s{days_ago}.jpeg", days_ago, "Bananen", sara["id"]))
    session.commit()
    return repository, sara


def _client(repository):
    from fastapi.testclient import TestClient

    from grocery_app.api.app import create_app

    return TestClient(create_app(repository, token="owner-secret"))


OWNER = {"Authorization": "Bearer owner-secret"}


@db
def test_each_person_has_their_own_list_and_their_own_edits(two_lists):
    repository, sara = two_lists
    client = _client(repository)
    hers = {"Authorization": f"Bearer {sara['password']}"}
    assert listed(client.get("/v1/list", headers=OWNER).json()) == ["milch"]
    assert listed(client.get("/v1/list", headers=hers).json()) == ["gurken"]

    taken_off = client.put("/v1/list/milch", headers=OWNER, json={"on_list": False}).json()
    assert listed(taken_off) == [] and taken_off["snoozed"][0]["kind"] == "milch"
    assert taken_off["snoozed"][0]["times"] == 1
    assert listed(client.get("/v1/list", headers=OWNER).json()) == [], "kept"
    assert listed(client.get("/v1/list", headers=hers).json()) == ["gurken"], \
        "the owner's removal is not Sara's"

    put_on = client.put("/v1/list/toilettenpapier", headers=hers, json={"on_list": True})
    assert listed(put_on.json()) == ["toilettenpapier", "gurken"]
    assert "toilettenpapier" not in listed(client.get("/v1/list", headers=OWNER).json())


@db
def test_a_kind_that_is_no_category_is_refused(two_lists):
    repository, _ = two_lists
    client = _client(repository)
    answer = client.put("/v1/list/irgendwas", headers=OWNER, json={"on_list": True})
    assert answer.status_code == 422
    assert repository.list_edits() == [], "nothing kept"


@db
def test_typed_words_go_on_the_asker_list_and_only_theirs(two_lists):
    """The paper list over the server: words naming an item they bought put
    that item on; any other words are a line of their own, crossed off and
    deleted by those words, and by no one else."""
    repository, sara = two_lists
    client = _client(repository)
    hers = {"Authorization": f"Bearer {sara['password']}"}

    typed = client.post("/v1/list", headers=OWNER, json={"text": "  Geburtstags   kerzen "})
    assert typed.status_code == 200
    line = typed.json()["lines"][0]
    assert (line["kind"], line["typed"], line["added"]) == ("Geburtstags kerzen", True, True)
    milk = client.post("/v1/list", headers=OWNER, json={"text": "MILCH"}).json()["lines"]
    assert [(m["kind"], m["typed"]) for m in milk][:2] == [
        ("Geburtstags kerzen", True), ("milch", False)], "the item, not new words"

    assert client.put("/v1/list/Geburtstags kerzen", headers=hers,
                      json={"edit": "cross"}).status_code == 422, "not Sara's line"
    crossed = client.put("/v1/list/Geburtstags kerzen", headers=OWNER, json={"edit": "cross"})
    assert crossed.json()["lines"][0]["crossed"]
    deleted = client.put("/v1/list/Geburtstags kerzen", headers=OWNER,
                         json={"edit": "delete"}).json()
    assert "Geburtstags kerzen" not in listed(deleted)
    assert client.post("/v1/list", headers=OWNER, json={"text": "   "}).status_code == 422
    assert client.put("/v1/list/milch", headers=OWNER,
                      json={"edit": "cross", "on_list": True}).status_code == 422


@db
def test_a_deleted_account_takes_its_list_edits_with_it(two_lists, session):
    from grocery_app.db.models import ListEdit

    repository, sara = two_lists
    as_sara = repository.as_user({"id": sara["id"], "name": "Sara"})
    as_sara.edit_list("gurken", "remove")
    repository.edit_list("milch", "remove")
    as_sara.remove_account()
    assert [(e.user_id, e.kind) for e in session.query(ListEdit)] == [(None, "milch")]


def test_without_a_database_there_is_no_list():
    from fastapi.testclient import TestClient

    from grocery_app.api.app import create_app
    from grocery_app.api.repository import InMemoryRepository

    client = TestClient(create_app(InMemoryRepository({"purchases": []})))
    assert client.get("/v1/list").status_code == 503
    assert client.put("/v1/list/milch", json={"on_list": True}).status_code == 503


# --- the screen (the page's own code, in Node) --------------------------------------

def test_the_list_reads_bottom_to_top_accepted_first_and_the_most_urgent_last():
    """For the thumb (owner, 2026-10-24): what was accepted at the top, the
    suggestions under it, the most urgent right above the tab bar. While its
    Undo runs, a kind snoozed is off the page and one added is on the list."""
    from grocery_app.api.app import REVIEW_PAGE
    from tests.test_api import run_page_function

    page = REVIEW_PAGE.read_text(encoding="utf-8")
    out = run_page_function(page, "listParts backDay", """
        const day = iso => new Date(iso + "T00:00:00Z");
        const doc = { lines: [{ kind: "brot", added: true }, { kind: "milch", added: false },
                              { kind: "eier", added: false }, { kind: "quark", added: false }] };
        const waiting = new Map([["eier", { edit: "remove", timer: 1 }],
                                 ["quark", { edit: "add", timer: 2 }]]);
        const parts = listParts(doc, waiting);
        console.log(parts.accepted.map(l => l.kind).join(","));
        console.log(parts.suggested.map(l => l.kind).join(","));
        console.log(JSON.stringify(listParts(null, new Map())));
        const at = d => new Date(Date.now() + d * 864e5).toISOString().slice(0, 10);
        console.log(backDay(at(1)));
        console.log(backDay("2026-10-29"));
    """)
    assert out == ["brot,quark", "milch", '{"accepted":[],"suggested":[]}',
                   "Back tomorrow", "Back Thu 29 Oct"]


def test_the_list_has_the_tab_and_insights_opens_from_home():
    from grocery_app.api.app import REVIEW_PAGE

    page = REVIEW_PAGE.read_text(encoding="utf-8")
    assert '<button id="tab-list">' in page and 'id="tab-insights"' not in page
    assert 'const TABS = ["home", "receipts", "list", "you"];' in page
    assert "cards.push(insightsTile());" in page


def test_an_add_or_snooze_is_sent_when_its_undo_runs_out_or_the_page_is_left():
    """As a removed receipt: Undo sends nothing, leaving the page sends what
    is still waiting, and a kind put back is sent at once. Both an add and a
    snooze can be undone, for 3 seconds (owner, 2026-10-25)."""
    from grocery_app.api.app import REVIEW_PAGE
    from tests.test_api import run_page_function

    page = REVIEW_PAGE.read_text(encoding="utf-8")
    assert "const LIST_UNDO_MS = 3000;" in page
    assert 'window.addEventListener("pagehide", sendListWaitingNow)' in page
    out = run_page_function(page, "decide accept snooze sendListEdit sendListWaitingNow "
                                  "markListUsed", """
        const LIST_UNDO_MS = 3000;
        const LIST_SAID = { add: "added", remove: "snoozed", delete: "deleted" };
        const listWaiting = new Map();
        const sent = [];
        let undo = null, undoFor = null;
        globalThis.api = async (path, opts) => {
          sent.push([opts.method, path, opts.body, opts.keepalive ? "keepalive" : ""].join(" "));
          return { lines: [], snoozed: [] };
        };
        globalThis.toast = (text, onUndo, ms) => { undo = onUndo; undoFor = ms; };
        globalThis.render = () => {};
        globalThis.saveCopy = () => {};
        globalThis.state = {};
        snooze({ kind: "milch", name: "Milch" });
        console.log(undoFor);
        undo();
        accept({ kind: "brot", name: "Brot" });
        undo();
        snooze({ kind: "eier", name: "Eier" });
        accept({ kind: "skyr", name: "Skyr" });
        console.log([...listWaiting.keys()].join(","));
        sendListWaitingNow();
        sendListWaitingNow();
        sendListEdit("quark", "add");
        setTimeout(() => { console.log(sent.join(" | ")); process.exit(0); }, 10);
    """)
    assert out == ["3000", "eier,skyr",
                   'PUT /v1/list/eier {"edit":"remove"} keepalive | '
                   'PUT /v1/list/skyr {"edit":"add"} keepalive | '
                   'PUT /v1/list/quark {"edit":"add"} keepalive'], \
        "Milch and Brot undone; Eier and Skyr sent once, on leaving; Quark put back at once"


# --- items, not categories (owner, 2026-10-24) -------------------------------------

def test_lines_are_items_and_a_product_not_named_yet_counts_under_its_category():
    rows = (every("nuesse-kerne", 7, times=8, item="Walnüsse", pid="p-wal")
            + every("nuesse-kerne", 7, times=8, item="Mandeln", pid="p-man")
            + every("nuesse-kerne", 7, times=8, pid="p-mix"))           # not named yet
    as_of = START + timedelta(days=57)
    assert sorted((k["kind"], k["name"]) for k in kinds(rows, as_of)) == [
        ("mandeln", "Mandeln"), ("nuesse-kerne", "Nuesse-Kerne"), ("walnüsse", "Walnüsse")]


def test_one_item_however_its_word_is_written():
    rows = (every("eier", 7, times=4, item="Eier", pid="p-a")
            + every("eier", 7, start=START + timedelta(days=28), times=4, item="eier", pid="p-b"))
    [line] = kinds(rows, START + timedelta(days=57))
    assert (line["kind"], line["name"], line["products"]) == ("eier", "eier", 2), \
        "the name as last written"


def test_an_add_under_a_category_whose_products_all_have_items_now_is_dropped():
    """The owner, 2026-10-25: "Haushaltswaren", added under the category the
    day before the list became items, named nothing he knew. Gloves and
    distilled water have item words now, so no line is "haushaltswaren"."""
    rows = (STEADY + every("haushaltswaren", 20, times=3, item="Handschuhe")
            + every("haushaltswaren", 25, times=2, item="Destilliertes Wasser"))
    result = with_edits(rows, [edit("haushaltswaren", "add", DAY - timedelta(days=1))], DAY)
    assert "haushaltswaren" not in listed(result)
    named_later = rows + [row("haushaltswaren", START + timedelta(days=3))]   # one not named
    assert listed(with_edits(named_later, [edit("haushaltswaren", "add", DAY)], DAY))[0] \
        == "haushaltswaren", "while a product still counts under it, the line is there"


def test_a_snooze_of_an_item_that_is_named_otherwise_now_is_dropped():
    """Romatomaten became Tomaten (owner, 2026-10-25: a line is the word on a
    paper list); a snooze under the old name names no line."""
    rows = every("tomaten", 6, times=10, item="Tomaten") + STEADY
    result = with_edits(rows, [edit("romatomaten", "remove", DAY)], DAY)
    assert "tomaten" in listed(result) and result["snoozed"] == []
    assert "romatomaten" not in listed(with_edits(rows, [edit("romatomaten", "add", DAY)], DAY))


def test_an_item_can_be_snoozed_and_put_back_by_its_key():
    rows = (every("nuesse-kerne", 6, times=10, item="Walnüsse")
            + every("brot", 7, times=9, start=START - timedelta(days=3)))
    day = START + timedelta(days=57)
    result = with_edits(rows, [edit("walnüsse", "remove", day)], day)
    assert listed(result) == ["brot"] and result["snoozed"][0]["name"] == "Walnüsse"
    put_back = with_edits(rows, [edit("walnüsse", "remove", day), edit("walnüsse", "add", day)],
                          day)
    assert listed(put_back)[0] == "walnüsse"


@db
def test_the_server_takes_an_item_the_asker_bought_and_nothing_made_up(two_lists, session):
    from grocery_app.db.models import Product

    repository, _ = two_lists
    session.get(Product, "p-0001").offer_word = "H-Milch"
    session.commit()
    client = _client(repository)
    assert listed(client.get("/v1/list", headers=OWNER).json()) == ["h-milch"]
    snoozed = client.put("/v1/list/h-milch", headers=OWNER, json={"on_list": False})
    assert snoozed.status_code == 200 and snoozed.json()["snoozed"][0]["name"] == "H-Milch"
    assert client.put("/v1/list/walnüsse", headers=OWNER,
                      json={"on_list": True}).status_code == 422, "never bought"


def test_typing_crossing_off_and_deleting_on_the_page():
    """The paper list (owner, 2026-10-26): what is typed is sent as typed and
    the field empties only once it is on the list; a cross is sent at once,
    and a second tap uncrosses; a delete waits out its Undo, hidden."""
    from grocery_app.api.app import REVIEW_PAGE
    from tests.test_api import run_page_function

    page = REVIEW_PAGE.read_text(encoding="utf-8")
    out = run_page_function(page, "writeOnList crossOff sendListEdit decide deleteTyped "
                                  "markListUsed listParts", """
        const LIST_UNDO_MS = 3000;
        const LIST_SAID = { add: "added", remove: "snoozed", delete: "deleted" };
        const listWaiting = new Map();
        const sent = [];
        let fail = false;
        globalThis.api = async (path, opts) => {
          sent.push([opts.method, path, opts.body].join(" "));
          if (fail) throw new Error("offline");
          return { lines: [{ kind: "Kerzen", added: true, typed: true }], snoozed: [] };
        };
        globalThis.toast = text => sent.push("toast " + text);
        globalThis.render = () => {};
        globalThis.saveCopy = () => {};
        globalThis.document = { querySelector: () => null };
        globalThis.state = { listDraft: "Kerzen" };
        (async () => {
          const input = { value: "Kerzen" };
          await writeOnList("   ", input);
          await writeOnList("Kerzen", input);
          console.log(JSON.stringify([input.value, state.listDraft, state.list.lines.length]));
          fail = true;
          input.value = "Ballons";
          await writeOnList("Ballons", input);
          console.log(input.value);
          fail = false;
          const line = { kind: "Kerzen", name: "Kerzen", crossed: false };
          crossOff(line);
          console.log(line.crossed);
          crossOff(line);
          console.log(line.crossed);
          deleteTyped({ kind: "Kerzen", name: "Kerzen" });
          console.log(listParts({ lines: [{ kind: "Kerzen", added: true }] },
                                listWaiting).accepted.length);
          setTimeout(() => { console.log(sent.join(" | ")); process.exit(0); }, 20);
        })();
    """)
    assert out[:5] == ['["","",1]', "Ballons", "true", "false", "0"], out
    assert out[5] == ('POST /v1/list {"text":"Kerzen"} | POST /v1/list {"text":"Ballons"} | '
                      'toast Not added: offline | '
                      'PUT /v1/list/Kerzen {"edit":"cross"} | '
                      'PUT /v1/list/Kerzen {"edit":"uncross"} | toast Kerzen: deleted'), \
        "nothing typed sends nothing; a failed add keeps the words"


def test_home_says_what_was_crossed_off_with_no_receipt_yet():
    """One line on Home; its button opens the photo picker the + opens."""
    from grocery_app.api.app import REVIEW_PAGE
    from tests.test_api import run_page_function

    page = REVIEW_PAGE.read_text(encoding="utf-8")
    assert "const scan = scanNote(state.list && state.list.unscanned);" in page
    out = run_page_function(page, "scanNote day", """
        let picked = 0;
        globalThis.document = { getElementById: id => ({ click: () => {
          if (id === "add-file") picked += 1; } }) };
        globalThis.el = (tag, attrs, ...kids) => ({ attrs, kids });
        const text = note => note.kids[0].kids[0];
        const at = d => new Date(Date.now() + d * 864e5).toISOString().slice(0, 10);
        console.log(scanNote(null));
        console.log(text(scanNote({ day: at(0), items: 1 })));
        console.log(text(scanNote({ day: at(-1), items: 4 })));
        console.log(text(scanNote({ day: "2025-10-19", items: 2 })));
        scanNote({ day: at(0), items: 1 }).kids[1].attrs.onclick();
        console.log(picked);
    """)
    assert out == ["null", "You crossed off 1 item today; no receipt yet",
                   "You crossed off 4 items yesterday; no receipt yet",
                   "You crossed off 2 items on Sunday; no receipt yet", "1"]


def test_the_swipe_hint_goes_once_the_person_has_added_or_snoozed():
    from grocery_app.api.app import REVIEW_PAGE
    from tests.test_api import run_page_function

    page = REVIEW_PAGE.read_text(encoding="utf-8")
    assert "function decide(line, edit) {\n  markListUsed();" in page
    assert 'function accept(line) { decide(line, "add"); }' in page
    assert 'function snooze(line) { decide(line, "remove"); }' in page
    out = run_page_function(page, "listUsed markListUsed", """
        const LIST_USED_KEY = "grocery-list-used";
        const kept = {};
        globalThis.localStorage = { getItem: k => kept[k] ?? null,
                                    setItem: (k, v) => { kept[k] = v; } };
        console.log(listUsed());
        markListUsed();
        console.log(listUsed());
        globalThis.localStorage = { getItem: () => { throw new Error("private"); },
                                    setItem: () => { throw new Error("private"); } };
        markListUsed();
        console.log(listUsed());
    """)
    assert out == ["false", "true", "false"], "no storage: the hint stays, nothing breaks"


def test_the_backtest_scores_items_not_categories():
    """Walnuts every 3 days are listed and bought as walnuts: scored by
    category, the buys would count for "nuesse-kerne" and none would match."""
    rows = every("nuesse-kerne", 3, times=40, item="Walnüsse")
    walnuts = backtest(rows, weeks=4)["methods"]["chance >= 25%, just bought too"]
    assert walnuts["bought"] == 1.0 and walnuts["caught"] == 1.0
