"""The shopping list over made-up purchase rows: nothing here comes from a receipt."""

from datetime import date, timedelta

from grocery_app import shopping_list as sl
from grocery_app.evaluate_list import backtest, format_report, gap_rule
from grocery_app.shopping_list import chance, kinds, list_rows, runs_out, shopping_list

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
            + every("brot", 7, times=9, pid="p-b", start=START + timedelta(days=3))
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


# --- the backtest --------------------------------------------------------------

def test_a_steady_shopper_is_caught_and_the_report_reads():
    rows = every("quark", 3, times=40) + every("brot", 7, times=18)
    result = backtest(rows, weeks=4)
    assert result["methods"]["chance >= 25%"]["caught"] == 1.0
    assert result["methods"]["chance >= 25%"]["bought"] == 1.0
    assert "gap rule" in format_report(result)


def test_the_gap_rule_calls_a_kind_due_when_its_median_gap_ends_within_the_week():
    rows = every("quark", 10, times=4) + every("brot", 30, times=2)   # quark last on day 30
    assert gap_rule(rows, START + timedelta(days=34)) == {"quark"}     # brot: two days only
    assert gap_rule(rows, START + timedelta(days=80)) == set()        # three gaps and a week on


def test_an_empty_history_has_nothing_to_test():
    assert backtest([])["weeks"] == 0
    assert "nothing to test" in format_report({"weeks": 0})
