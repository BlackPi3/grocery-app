"""The trip plan and its backtest over made-up purchase rows: invented shops,
nothing from a receipt."""

from datetime import date, timedelta

from grocery_app.evaluate_plan import backtest, format_report
from grocery_app.trip_plan import (
    base_shop,
    line_cost,
    named,
    next_trip,
    plan_trip,
    price_book,
    usual_amounts,
)

START = date(2026, 3, 1)


def row(item, day, store="Großmarkt", net=1.0, qty=1, unit=None, per=None, image=None):
    return {"type": "product", "date": day.isoformat(), "store": store, "item": item,
            "category": "x", "net_paid": net, "qty": qty,
            "unit_price": {"amount": unit, "per": per} if unit else None,
            "source_image": image or f"{store}-{day.isoformat()}.jpg"}


def line(kind, amount=1, unit="item"):
    return {"kind": kind, "amount": amount, "unit": unit}


# --- the base and the prices ------------------------------------------------------

def test_the_base_is_the_shop_on_most_receipts_not_the_most_lines():
    day = START
    rows = [row(i, day, "Sparladen") for i in "abcdefgh"]          # one big receipt
    rows += [row("a", day + timedelta(days=d), "Großmarkt") for d in (1, 2, 3)]
    assert base_shop(rows, day + timedelta(days=10)) == "grossmarkt"
    assert base_shop(rows, day + timedelta(days=1)) == "sparladen", "only what came before"


def test_two_spellings_of_a_shop_are_one_shop():
    rows = [row("milch", START, "Sparladen"), row("milch", START, "SPARLADEN ")]
    assert set(price_book(rows, START + timedelta(days=1))) == {"sparladen"}


def test_a_price_is_the_median_of_the_last_five_paid_and_only_before_the_day():
    prices = [9.0, 1.0, 1.2, 1.1, 1.3, 1.0]
    rows = [row("milch", START + timedelta(days=i), net=n) for i, n in enumerate(prices)]
    rows.append(row("milch", START + timedelta(days=20), net=5.0))
    book = price_book(rows, START + timedelta(days=20))
    assert book == {"grossmarkt": {"milch": {"item": 1.1}}}, "9.0 is past the last five"


def test_a_price_is_per_kilo_for_what_is_weighed_and_units_never_mix():
    rows = [row("tomaten", START, net=1.5, unit=3.0, per="kg"),       # 500 g
            row("tomaten", START, "Sparladen", net=0.99)]               # a pack
    book = price_book(rows, START + timedelta(days=1))
    assert book["grossmarkt"]["tomaten"] == {"kg": 3.0}
    assert line_cost(book, "grossmarkt", line("tomaten", 0.5, "kg")) == 1.5
    assert line_cost(book, "sparladen", line("tomaten", 0.5, "kg")) is None, \
        "a pack has no price per kilo"


def test_a_discount_paid_is_the_price_paid():
    paid = row("käse", START, net=1.8)
    paid["gross"], paid["discount"] = 2.0, -0.2
    assert price_book([paid], START + timedelta(days=1))["grossmarkt"]["käse"] == {"item": 1.8}


def test_a_usual_buy_is_the_median_line_in_the_most_common_unit():
    rows = [row("äpfel", START, net=1.0, unit=2.0, per="kg"),
            row("äpfel", START, net=2.0, unit=2.0, per="kg"),
            row("äpfel", START, net=3.0, unit=2.0, per="kg"),
            row("äpfel", START, net=2.5)]
    assert usual_amounts(rows, START + timedelta(days=1)) == {"äpfel": (1.0, "kg")}


# --- the engine -------------------------------------------------------------------

BOOK = {"grossmarkt": {"a": {"item": 2.0}, "b": {"item": 2.0}, "c": {"item": 2.0},
                      "d": {"item": 2.0}},
        "sparladen": {"a": {"item": 1.5}, "b": {"item": 1.5}, "c": {"item": 1.5}},
        "eckladen": {"a": {"item": 0.5}, "b": {"item": 0.5}}}
LIST = [line("a"), line("b"), line("c"), line("d")]


def test_the_shop_that_prices_most_of_the_list_cheapest_goes_and_tops_up_at_the_base():
    trip = plan_trip(LIST, BOOK, "grossmarkt")
    assert trip["shop"] == "sparladen"
    assert trip["top_up"] == ["d"]
    # Like for like: all four lines, d topped up at the base's 2.00.
    shops = {s["shop"]: s for s in trip["shops"]}
    assert (shops["sparladen"]["total"], shops["grossmarkt"]["total"]) == (6.5, 8.0)
    assert trip["saves"] == 1.5 and trip["compared"] == 4


def test_a_cheap_shop_that_prices_half_the_list_is_not_a_candidate():
    """Eckladen is cheapest for a and b, but a trip there leaves half the
    list to the top-up: shop to shop, not one shop."""
    shops = {s["shop"]: s for s in plan_trip(LIST, BOOK, "grossmarkt")["shops"]}
    assert shops["eckladen"]["cover"] == 0.5
    assert not shops["eckladen"]["candidate"] and shops["eckladen"]["total"] is None


def test_an_even_total_stays_at_the_base():
    book = {"grossmarkt": {"a": {"item": 1.0}}, "sparladen": {"a": {"item": 1.0}}}
    trip = plan_trip([line("a")], book, "sparladen")
    assert trip["shop"] == "sparladen", "the base, though großmarkt sorts first"
    trip = plan_trip([line("a")], book, "grossmarkt")
    assert (trip["shop"], trip["saves"], trip["top_up"]) == ("grossmarkt", 0.0, [])


def test_a_line_only_one_candidate_prices_is_left_out_of_the_comparison():
    """e is priced at Sparladen only: counting it would make Sparladen dearer
    for covering more, so no candidate's total has it."""
    book = {"grossmarkt": {"a": {"item": 2.0}},
            "sparladen": {"a": {"item": 1.0}, "e": {"item": 9.0}}}
    trip = plan_trip([line("a"), line("e")], book, "grossmarkt")
    assert trip["shop"] == "sparladen" and trip["compared"] == 1 and trip["saves"] == 1.0


def test_no_list_or_no_base_is_no_plan():
    assert plan_trip([], BOOK, "grossmarkt") is None
    assert plan_trip(LIST, BOOK, None) is None


def test_the_next_trip_plans_the_drafted_list_at_usual_amounts():
    rows = []
    for w in range(10):
        day = START + timedelta(days=7 * w)
        rows += [row(i, day, "Großmarkt", net=2.0) for i in "abc"]
        rows += [row(i, day + timedelta(days=1), "Sparladen", net=1.0) for i in "abc"]
    rows += [row(i, START + timedelta(days=7 * w + 3), "Großmarkt", net=2.0)
             for w in range(10) for i in "d"]
    trip = next_trip(rows, START + timedelta(days=70))
    assert trip["base"] == "grossmarkt", "20 receipts to 10"
    assert trip["lines"] == 4 and trip["shop"] == "sparladen"
    assert trip["top_up"] == ["d"] and trip["saves"] == 3.0
    shown = named(trip, rows)
    assert (shown["shop"], shown["base"]) == ("Sparladen", "Großmarkt")
    assert [s["shop"] for s in shown["shops"]] == ["Großmarkt", "Sparladen"]


# --- the backtest -----------------------------------------------------------------

def history(sparladen, weeks=12):
    """Each week: a, b, c, d at the base, Großmarkt, for 2.00 each on day 1, and
    z on day 6 (the last receipt, so each trip starts on day 0); on day 3,
    `sparladen` ({item: price}) at Sparladen."""
    rows = []
    for w in range(weeks):
        day = START + timedelta(days=7 * w)
        rows += [row(i, day + timedelta(days=1), net=2.0) for i in "abcd"]
        rows += [row(i, day + timedelta(days=3), "Sparladen", net=n)
                 for i, n in sparladen.items()]
        rows.append(row("z", day + timedelta(days=6), net=2.0))
    return rows


def test_a_shop_that_prices_little_of_the_list_is_never_planned():
    report = backtest(history({"a": 1.0}), weeks=4, spacing=7)
    assert [t["day"] for t in report["trips"]] == [
        (START + timedelta(days=7 * w)).isoformat() for w in (8, 9, 10, 11)]
    assert report["lines"] == 4 * 6
    plan, base = report["methods"]["plan"], report["methods"]["base"]
    # The base buys Sparladen's a too, 1.00 dearer, once a week: one shop a
    # trip costs more than the habit, and the plan says so.
    assert base["saved"] == -4.0 and base["saved_a_week"] == -1.0
    assert plan["away"] == 0 and plan["saved"] == base["saved"]
    assert base["followed"] == round(5 / 6, 3) and base["compared"] == 1.0


def test_the_plan_goes_where_most_of_the_list_is_cheaper():
    report = backtest(history({"a": 1.0, "b": 1.0, "c": 1.5}), weeks=4, spacing=7)
    plan, hind = report["methods"]["plan"], report["methods"]["hindsight"]
    assert plan["away"] == 4 and all(t["plan"] == "Sparladen" for t in report["trips"])
    # A week as bought: a, b, c, d, z at 2.00, and a, b, c at 1.00, 1.00, 1.50:
    # 13.50. As planned: a, b, c at Sparladen twice, 7.00; d and z topped up
    # at the base, 4.00.
    assert plan["saved_a_week"] == 2.5 and plan["saved"] == 10.0
    assert plan["saved_share"] == round(10.0 / (4 * 13.5), 3)
    assert hind["saved"] == plan["saved"]
    assert plan["followed"] == round(3 / 8, 3), "Sparladen's own lines"
    assert report["trips"][0]["saved_plan"] == 2.5


def test_a_price_seen_after_the_trip_day_does_not_pick_the_shop():
    """Sparladen's b and c are first bought in the last week, after its trip
    started: no trip knows them, so no trip goes there."""
    rows = history({"a": 1.0})
    last = START + timedelta(days=7 * 11 + 3)
    rows += [row("b", last, "Sparladen", net=1.0), row("c", last, "Sparladen", net=1.0)]
    trips = backtest(rows, weeks=4, spacing=7)["trips"]
    assert [t["hindsight"] for t in trips] == ["Großmarkt"] * 4
    # Known in advance, they would have sent the last trip there.
    assert plan_trip([{"kind": k, "amount": 1, "unit": "item"} for k in "abcdzabc"],
                     price_book(rows, last + timedelta(days=1)), "grossmarkt"
                     )["shop"] == "sparladen"


def test_no_rows_is_nothing_to_test():
    assert backtest([]) == {"weeks": 0, "trips": []}
    assert format_report(backtest([])) == "No purchases with a shop and a price: nothing to test."


def test_the_report_reads_as_a_table():
    text = format_report(backtest(history({"a": 1.0}), weeks=4, spacing=7))
    assert text.startswith("A trip every 7 days, ")
    assert "4 trips, 24 lines, 44.00 EUR paid" in text
    assert "base                 0      100%    -4.00   -1.00    -9%       83%" in text
    assert f"{(START + timedelta(days=56)).isoformat()}  Großmarkt       Großmarkt" in text
