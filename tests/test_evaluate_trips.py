"""How far apart trips could be, over made-up purchase rows."""

from datetime import date, timedelta

from grocery_app.evaluate_trips import backtest, format_report, stretches

END = date(2026, 3, 28)


def row(item, day, storage="cupboard", keeps=365):
    return {"type": "product", "date": day.isoformat(), "item": item, "category": "x",
            "storage": storage, "keeps_days": keeps}


def every(item, gap, days=56, **kw):
    """Bought every `gap` days, the last on END."""
    return [row(item, END - timedelta(days=d), **kw) for d in range(0, days, gap)]


def test_stretches_are_whole_and_end_on_the_last_receipt():
    assert stretches(END, 14, 7) == [(date(2026, 3, 15), date(2026, 3, 21)),
                                     (date(2026, 3, 22), END)]
    assert len(stretches(END, 56, 10)) == 5, "the rest of 56 days is left out"


def test_bread_every_other_day_keeps_for_a_trip_every_three_days_not_for_a_week():
    """Bread keeps 4 days: bought at a weekly trip, the loaf for the sixth day is
    past it; with a trip every three days nothing is."""
    by = {s["spacing"]: s for s in backtest(every("Brot", 2, storage="cupboard", keeps=4),
                                            weeks=8, spacings=(3, 7))["spacings"]}
    assert by[3]["wont_keep"] == 0.0
    assert 0.2 < by[7]["wont_keep"] < 0.3, "one loaf in four, the one on the sixth day"
    assert by[7]["wont_keep_by_storage"] == {"cupboard": by[7]["wont_keep_by_storage"]["cupboard"]}


def test_a_line_with_no_keeping_days_is_counted_apart_never_as_keeping():
    rows = every("Brot", 2, keeps=None) + every("Reis", 7)
    (s,) = backtest(rows, weeks=8, spacings=(7,))["spacings"]
    assert s["wont_keep"] == 0.0
    assert 0.7 < s["keeps_unknown"] < 0.85, "28 loaves of 36 lines"


def test_fridge_room_is_set_beside_the_most_brought_home_in_one_day():
    rows = (every("Milch", 2, storage="fridge", keeps=10)
            + every("Joghurt", 2, storage="fridge", keeps=20) + every("Reis", 2))
    report = backtest(rows, weeks=8, spacings=(2, 14))
    assert report["fridge_room"] == 2, "milk and yoghurt on the same days, not the rice"
    by = {s["spacing"]: s for s in report["spacings"]}
    assert (by[2]["most_fridge"], by[14]["most_fridge"]) == (2, 14)
    assert by[14]["lines_a_trip"] == 21 and by[14]["trips_a_month"] == 2.1


def test_trips_a_month_beside_the_days_actually_shopped():
    report = backtest(every("Brot", 2), weeks=8)
    assert report["shopping_days_a_month"] == 15.0, "every other day"
    assert [s["trips_a_month"] for s in report["spacings"]] == [10.0, 4.3, 3.0, 2.1]
    text = format_report(report)
    assert "You shopped on 15.0 days a month" in text and "  14 d" in text


def test_an_empty_history_has_nothing_to_test():
    assert format_report(backtest([])) == "No purchases: nothing to test."
