"""Insights over made-up purchase rows: nothing here comes from a receipt."""

from datetime import date

import pytest

from grocery_app.insights import (
    MIN_BASKET_PRODUCTS,
    basket_index,
    budget_brand,
    build_insights,
    compare_month,
    cross_store,
    discounts,
    price_changes,
    price_move,
    price_moves,
    regulars,
    repurchase,
    running_totals,
    usual_by_day,
)


def row(pid, day, net, qty=1, unit=None, per=None, store="Musterladen",
        budget=None, brand="Marke", product="Ding", type_="product", category=None):
    r = {"type": type_, "date": day, "store": store, "product_id": pid, "product": product,
         "brand": brand, "is_budget_brand": budget, "category": category, "qty": qty,
         "net_paid": net, "unit_price": {"amount": unit, "per": per} if unit else None}
    return r


# --- repurchase --------------------------------------------------------------

def test_repurchase_uses_the_median_gap_and_the_last_receipt_date():
    rows = [row("p-1", "2026-01-01", 1.0), row("p-1", "2026-01-08", 1.0),
            row("p-1", "2026-01-15", 1.0), row("p-1", "2026-02-14", 1.0),  # one long gap
            row("p-2", "2026-01-03", 2.0)]                                 # bought once
    out = repurchase(rows, as_of=date(2026, 2, 20))
    assert [r["product_id"] for r in out] == ["p-1"]
    assert out[0]["typical_interval_days"] == 7   # median of 7, 7, 30
    assert out[0]["expected_next"] == "2026-02-21"
    assert out[0]["status"] == "upcoming"
    assert out[0]["trips"] == 4
    assert out[0]["gaps_observed"] == 3


def test_repurchase_is_due_when_the_expected_date_has_passed():
    rows = [row("p-1", "2026-01-01", 1.0), row("p-1", "2026-01-11", 1.0)]
    out = repurchase(rows, as_of=date(2026, 1, 31))
    assert out[0]["status"] == "due"
    assert out[0]["days_overdue"] == 10


def test_two_lines_on_one_day_are_one_trip():
    rows = [row("p-1", "2026-01-01", 1.0), row("p-1", "2026-01-01", 1.0)]
    assert repurchase(rows, as_of=date(2026, 1, 2)) == []


def test_regulars_are_bought_on_three_days_or_more_most_days_first():
    rows = [*(row("milk", f"2026-01-{d:02d}", 1.0) for d in (1, 8, 15, 22)),
            *(row("bread", f"2026-01-{d:02d}", 2.0) for d in (10, 17, 24)),
            *(row("eggs", f"2026-01-{d:02d}", 2.0) for d in (2, 30, 31)),  # 3 days, longer
            row("tea", "2026-01-03", 3.0), row("tea", "2026-01-29", 3.0),   # 2 days: no habit
            row("milk", "2026-01-22", 1.0)]                                  # one day, two lines
    out = regulars(rows, as_of=date(2026, 1, 31))
    assert [(r["product_id"], r["trips"], r["days"]) for r in out] == [
        ("milk", 4, 31), ("bread", 3, 22), ("eggs", 3, 30)]
    assert (out[0]["first_bought"], out[0]["last_bought"]) == ("2026-01-01", "2026-01-22")


# --- price over time ---------------------------------------------------------

def test_price_change_follows_the_unit_price():
    rows = [row("p-1", "2026-01-01", 1.60, unit=1.60, per="piece"),
            row("p-1", "2026-02-01", 1.65, unit=1.65, per="piece")]
    (change,) = price_changes(rows)
    assert change["per"] == "piece"
    assert change["change_pct"] == 3.1
    assert change["observations"] == [{"date": "2026-01-01", "price": 1.6},
                                      {"date": "2026-02-01", "price": 1.65}]


def test_price_change_falls_back_to_paid_per_item():
    rows = [row("p-1", "2026-01-01", 2.0, qty=2), row("p-1", "2026-02-01", 1.2, qty=1)]
    (change,) = price_changes(rows)
    assert change["per"] == "item"
    assert change["first"]["price"] == 1.0 and change["last"]["price"] == 1.2


def test_a_price_change_compares_one_shop_with_itself():
    """Cheap in one shop, dearer in another later, is not a price going up."""
    rows = [row("p-1", "2026-06-29", 0.49, unit=0.99, per="kg", store="Billigmarkt"),
            row("p-1", "2026-07-18", 0.34, unit=1.18, per="kg", store="Billigmarkt"),
            row("p-1", "2026-09-04", 0.43, unit=2.24, per="kg", store="Großmarkt"),
            row("p-1", "2026-09-23", 1.83, unit=2.69, per="kg", store="Großmarkt")]
    changes = {c["store"]: c for c in price_changes(rows)}
    assert set(changes) == {"Billigmarkt", "Großmarkt"}
    assert (changes["Großmarkt"]["first"]["price"], changes["Großmarkt"]["change_pct"]) == \
        (2.24, 20.1)
    assert [o["date"] for o in changes["Billigmarkt"]["observations"]] == \
        ["2026-06-29", "2026-07-18"]


def test_a_product_priced_per_kg_once_and_per_piece_once_is_skipped():
    rows = [row("p-1", "2026-01-01", 2.0, unit=4.0, per="kg"),
            row("p-1", "2026-02-01", 2.0, unit=2.0, per="piece")]
    assert price_changes(rows) == []


# --- basket index ------------------------------------------------------------

def test_basket_index_prices_last_months_basket_at_this_months_prices():
    jan = [row(f"p-{i}", "2026-01-05", 1.0 * i, unit=1.0 * i, per="piece") for i in range(1, 4)]
    feb = [row("p-1", "2026-02-05", 1.1, unit=1.1, per="piece"),   # +10 %
           row("p-2", "2026-02-05", 2.0, unit=2.0, per="piece"),   # flat
           row("p-3", "2026-02-05", 3.0, unit=3.0, per="piece")]   # flat
    out = basket_index(jan + feb)
    (feb_entry,) = out["series"]
    assert feb_entry["products"] == 3
    # base basket: 1 + 2 + 3 = 6; at Feb prices: 1.1 + 2 + 3 = 6.1
    assert feb_entry["basket_cost_at_previous_prices"] == 6.0
    assert feb_entry["basket_cost_at_current_prices"] == 6.1
    assert feb_entry["month_over_month_pct"] == 1.7
    assert feb_entry["index"] == 101.7


def test_basket_index_quantity_is_in_the_units_of_the_price():
    # 2 kg of apples at 3 €/kg in January, 1 kg at 4 €/kg in February:
    # last month's 2 kg would cost 8 now instead of 6.
    jan = [row("p-a", "2026-01-05", 6.0, unit=3.0, per="kg"),
           row("p-b", "2026-01-05", 1.0, unit=1.0, per="piece"),
           row("p-c", "2026-01-05", 1.0, unit=1.0, per="piece")]
    feb = [row("p-a", "2026-02-05", 4.0, unit=4.0, per="kg"),
           row("p-b", "2026-02-05", 1.0, unit=1.0, per="piece"),
           row("p-c", "2026-02-05", 1.0, unit=1.0, per="piece")]
    (entry,) = basket_index(jan + feb)["series"]
    assert entry["basket_cost_at_previous_prices"] == 8.0
    assert entry["basket_cost_at_current_prices"] == 10.0


def test_basket_index_refuses_a_thin_overlap():
    rows = [row("p-1", "2026-01-05", 1.0), row("p-1", "2026-02-05", 2.0)]
    (entry,) = basket_index(rows)["series"]
    assert entry["index"] is None
    assert str(MIN_BASKET_PRODUCTS) in entry["reason"]


# --- budget brand ------------------------------------------------------------

def test_budget_split_keeps_unknown_and_unresolved_apart():
    rows = [row("p-1", "2026-01-01", 2.0, budget=True), row("p-2", "2026-01-01", 6.0, budget=False),
            row("p-3", "2026-01-01", 1.0, budget=None, brand="Rätsel"),
            row(None, "2026-01-01", 5.0)]
    out = budget_brand(rows)
    assert out["overall"] == {"budget": 2.0, "name_brand": 6.0, "unbranded": 0.0,
                              "unknown": 1.0, "unresolved": 5.0,
                              "budget_share_of_known": 0.25}
    assert out["unknown_brands"] == [{"brand": "Rätsel", "spend": 1.0}]


def test_produce_with_no_brand_is_unbranded_not_unknown():
    """A cucumber has no brand to find, so it is not a gap anyone can close.

    Counting it as unknown would report work that cannot be done, and would
    leave `(no brand recorded)` permanently at the top of `unknown_brands`.
    """
    rows = [row("p-1", "2026-01-01", 2.0, budget=True),
            row("p-2", "2026-01-01", 4.0, budget=None, brand=None, category="gurken"),
            row("p-3", "2026-01-01", 1.0, budget=None, brand=None, category="chips")]
    out = budget_brand(rows)
    assert out["overall"]["unbranded"] == 4.0
    assert out["overall"]["unknown"] == 1.0
    # Only the packaged line is offered as something to go and find out.
    assert out["unknown_brands"] == [{"brand": "(no brand recorded)", "spend": 1.0}]


def test_unbranded_money_stays_out_of_the_known_share():
    """Produce is neither a budget line nor a name brand, so it cannot move the ratio."""
    rows = [row("p-1", "2026-01-01", 1.0, budget=True), row("p-2", "2026-01-01", 1.0, budget=False)]
    without = budget_brand(rows)["overall"]["budget_share_of_known"]
    rows.append(row("p-3", "2026-01-01", 98.0, budget=None, brand=None, category="gurken"))
    assert budget_brand(rows)["overall"]["budget_share_of_known"] == without == 0.5


# --- cross store -------------------------------------------------------------

def test_cross_store_is_empty_and_says_so_until_a_product_resolves_twice():
    rows = [row("p-1", "2026-01-01", 1.0, store="A"), row("p-2", "2026-01-01", 1.0, store="B")]
    out = cross_store(rows)
    assert out["products"] == []
    assert "2 store(s)" in out["note"]


def test_one_store_spelled_two_ways_is_one_store():
    rows = [row("p-1", "2026-01-01", 1.0, store="GLOBUS"),
            row("p-1", "2026-01-09", 1.0, store="Globus"),
            row("p-2", "2026-01-09", 1.0, store="GLOBUS")]
    assert cross_store(rows)["products"] == []
    assert list(budget_brand(rows)["by_store"]) == ["GLOBUS"], "the common spelling is the label"
    assert repurchase(rows, as_of=date(2026, 1, 10))[0]["store"] == "GLOBUS"


def test_cross_store_reports_the_latest_price_at_each_store():
    rows = [row("p-1", "2026-01-01", 1.0, store="A", unit=1.0, per="piece"),
            row("p-1", "2026-01-09", 1.2, store="A", unit=1.2, per="piece"),
            row("p-1", "2026-01-05", 0.9, store="B", unit=0.9, per="piece")]
    (product,) = cross_store(rows)["products"]
    assert product["stores"]["A"]["price"] == 1.2
    assert product["stores"]["B"]["price"] == 0.9


# --- assembly ----------------------------------------------------------------

def test_build_insights_defaults_as_of_to_the_last_receipt_not_today():
    purchases = {"meta": {"receipts": 2, "date_range": ["2026-01-01", "2026-01-09"]},
                 "purchases": [row("p-1", "2026-01-01", 1.0), row("p-1", "2026-01-09", 1.0),
                               row(None, "2026-01-09", 0.25, type_="deposit")]}
    out = build_insights(purchases)
    assert out["as_of"] == "2026-01-09"
    assert out["coverage"]["product_lines"] == 2, "deposits are not product lines"
    assert out["coverage"]["resolved_share_of_spend"] == 1.0
    assert out["repurchase"][0]["status"] == "upcoming"


def test_coverage_counts_the_products_the_insights_can_speak_about():
    """"Bought again: 1 of 2 products" reads against this number, so it holds
    each counted grocery product once, however often it was bought."""
    rows = [row("p-1", "2026-01-01", 1.0), row("p-1", "2026-01-09", 1.0),
            row("p-2", "2026-01-09", 2.0),
            row(None, "2026-01-09", 3.0),                                  # nothing placed it
            row("p-cafe", "2026-01-09", 8.0, category="cafe-imbiss"),      # not a grocery
            {**row("p-gift", "2026-01-09", 5.0), "not_counted": True}]     # for a friend
    out = build_insights({"meta": {}, "purchases": rows})
    assert out["coverage"]["products"] == 2
    assert len(out["repurchase"]) == 1


# --- groceries only ----------------------------------------------------------

def test_a_line_that_is_not_a_grocery_leaves_every_insight_but_is_counted():
    # A café breakfast bought three times with the same price rise would make a
    # repurchase, a price change and a basket product if it were counted.
    cafe = [row("p-cafe", d, net, category="cafe-imbiss", product="Frühstück")
            for d, net in (("2026-01-03", 8.0), ("2026-02-03", 9.0), ("2026-02-10", 9.0))]
    milk = [row("p-milk", d, 1.0, category="milch-joghurt") for d in ("2026-01-03", "2026-02-03")]
    out = build_insights({"meta": {}, "purchases": cafe + milk})
    # The month view counts it on purpose: it asks what the money went on.
    everywhere = str({k: v for k, v in out.items() if k not in ("coverage", "months")})
    assert "p-cafe" not in everywhere
    assert "p-milk" in everywhere
    assert out["budget_brand"]["overall"]["unknown"] == 2.0, "only the milk's money"
    assert out["coverage"]["spend"] == 2.0
    assert out["coverage"]["product_lines"] == 2
    assert out["coverage"]["not_grocery"] == {"lines": 3, "spend": 26.0,
                                              "by_category": {"Café & Imbiss": 26.0}}


def test_a_line_the_shopper_does_not_count_leaves_their_numbers_but_not_the_prices():
    """A wine bought for a friend, three times: not the shopper's spend, habit
    or basket, but still what the shops charged for it."""
    wine = [{**row("p-wine", d, net, unit=net, per="piece", store=store,
                   category="rotwein", product="Rotwein"), "not_counted": True}
            for d, net, store in (("2026-01-03", 6.0, "Musterladen"),
                                  ("2026-02-03", 7.0, "Musterladen"),
                                  ("2026-02-10", 6.5, "Beispielmarkt"))]
    milk = [row("p-milk", d, 1.0, category="milch") for d in ("2026-01-03", "2026-02-03")]
    out = build_insights({"meta": {}, "purchases": wine + milk})

    for mine in ("repurchase", "basket_index", "budget_brand"):
        assert "p-wine" not in str(out[mine]), mine
    assert out["budget_brand"]["overall"]["unknown"] == 2.0, "only the milk's money"
    assert out["coverage"]["spend"] == 2.0 and out["coverage"]["product_lines"] == 2
    assert out["coverage"]["not_counted"] == {"lines": 3, "spend": 19.5}

    assert "p-wine" in str(out["price_changes"])
    (across,) = out["cross_store"]["products"]
    assert across["product_id"] == "p-wine"


def test_an_unknown_or_missing_category_still_counts_as_a_grocery():
    rows = [row(None, "2026-01-03", 2.0), row("p-1", "2026-01-03", 3.0, category="kein-key")]
    cov = build_insights({"meta": {}, "purchases": rows})["coverage"]
    assert cov["spend"] == 5.0
    assert cov["not_grocery"] == {"lines": 0, "spend": 0.0, "by_category": {}}


# --- like with like ------------------------------------------------------------

def sold(form):
    return {"form": form, "size": None}


def test_a_change_of_form_is_not_a_change_of_price():
    """Loose tomatoes at 1 €/kg twice, then a 650 g pack at 2,75 €/kg: the
    loose price did not move, and the pack was bought once."""
    rows = [{**row("p-1", "2026-06-01", 0.5, unit=1.0, per="kg"), "sold_as": sold("loose")},
            {**row("p-1", "2026-07-01", 0.5, unit=1.0, per="kg"), "sold_as": sold("loose")},
            {**row("p-1", "2026-08-01", 1.79, unit=2.75, per="kg"), "sold_as": sold("pack")}]
    (change,) = price_changes(rows)
    assert (change["sold_as"], change["change_pct"]) == ("loose", 0.0)


def test_the_basket_compares_a_product_in_the_same_form_and_unit():
    def month(day, form, price):
        return {**row("p-1", day, price, unit=price, per="kg"), "sold_as": sold(form)}

    others = [row(pid, d, 1.0) for pid in ("p-2", "p-3", "p-4") for d in ("2026-06-01",
                                                                          "2026-07-01")]
    rows = others + [month("2026-06-01", "loose", 1.0), month("2026-07-01", "pack", 2.75)]
    (step,) = basket_index(rows)["series"]
    assert step["month_over_month_pct"] == 0.0, "loose in June and a pack in July: no overlap"
    assert {"product_id": "p-1", "sold_as": "loose", "per": "kg"} not in step["compared"]
    rows += [month("2026-07-01", "loose", 1.1)]
    (step,) = basket_index(rows)["series"]
    assert {"product_id": "p-1", "sold_as": "loose", "per": "kg"} in step["compared"]


# --- the month view ------------------------------------------------------------
# Parham, 2026-10-09: "what happened last month?" What the money went on, by
# kind of thing, groceries or not.

def test_a_month_is_split_by_branch_with_its_products_most_money_first():
    rows = [row("p-1", "2026-09-02", 1.0, category="aepfel", product="Äpfel"),
            row("p-1", "2026-09-20", 2.0, category="aepfel", product="Äpfel"),
            row("p-2", "2026-09-05", 5.0, category="wasser", product="Wasser"),
            row("p-3", "2026-09-05", 8.0, category="cafe-imbiss", product="Frühstück"),
            row(None, "2026-09-06", 0.5, product=None) | {"raw_name": "XY Unklar"},
            row("p-2", "2026-10-01", 9.0, category="wasser", product="Wasser")]
    for r, image in zip(rows, ["a", "b", "c", "c", "c", "d"], strict=True):
        r["source_image"] = image
    october, september = build_insights({"meta": {}, "purchases": rows})["months"]

    assert october["month"] == "2026-10" and october["spend"] == 9.0
    assert september["month"] == "2026-09"
    assert (september["spend"], september["receipts"], september["lines"]) == (16.5, 3, 5)
    assert [(b["branch"], b["spend"]) for b in september["branches"]] == [
        ("Kein Lebensmitteleinkauf", 8.0), ("Getränke", 5.0), ("Obst & Gemüse", 3.0),
        (None, 0.5)], "a café breakfast is money spent; a line with no category comes last"
    produce = september["branches"][2]
    assert produce["items"] == [{"product_id": "p-1", "product": "Äpfel", "brand": "Marke",
                                 "lines": 2, "spend": 3.0}]
    assert september["branches"][3]["items"][0]["product"] == "XY Unklar"


def test_a_line_the_shopper_left_out_is_not_in_the_month():
    rows = [row("p-1", "2026-09-02", 1.0, category="aepfel"),
            row("p-2", "2026-09-02", 7.0, category="wasser") | {"not_counted": True}]
    (september,) = build_insights({"meta": {}, "purchases": rows})["months"]
    assert september["spend"] == 1.0


# --- a month against the one before ----------------------------------------------
# The owner, 2026-10-14: the same days of both months, and the difference split
# so every euro lands in one part.

def shelf(r, gross, discount=0.0):
    """A row with its shelf price and printed discount: net = gross + discount."""
    return r | {"gross": gross, "discount": discount}


def test_a_month_s_difference_is_split_into_its_causes_to_the_cent():
    then = [shelf(row("p-1", "2026-09-03", 2.00, qty=2), 2.00),          # milk, 2 at 1,00
            shelf(row("p-2", "2026-09-03", 2.00), 2.00),                 # butter, then only
            shelf(row("p-3", "2026-09-04", 2.00), 2.00),                 # coffee, no discount
            row(None, "2026-09-04", 3.00) | {"raw_name": "XY Unklar"}]
    now = [shelf(row("p-1", "2026-10-03", 3.30, qty=3), 3.30),           # 3 at 1,10
           shelf(row("p-4", "2026-10-03", 5.00), 5.00),                  # cheese, now only
           shelf(row("p-3", "2026-10-04", 1.80), 2.00, -0.20),           # coffee, 10 % off
           row(None, "2026-10-04", 4.00) | {"raw_name": "XY Unklar"}]
    out = compare_month(then + now, "2026-10")

    assert (out["versus"], out["spend"], out["versus_spend"], out["difference"]) == \
        ("2026-09", 14.10, 9.00, 5.10)
    assert out["parts"] == {"new": 5.00, "gone": -2.00, "amounts": 1.00, "prices": 0.30,
                            "discounts": -0.20, "not_placed": 1.00}
    assert round(sum(out["parts"].values()), 2) == out["difference"]


def test_a_month_so_far_is_set_against_the_same_days_of_the_month_before():
    rows = [row("p-1", "2026-09-14", 1.00), row("p-1", "2026-09-15", 9.00),
            row("p-1", "2026-10-14", 2.00)]
    so_far = compare_month(rows, "2026-10", through_day=14)
    assert (so_far["through_day"], so_far["versus_spend"]) == (14, 1.00), \
        "15 September is after the 14th"
    whole = compare_month(rows, "2026-10")
    assert (whole["through_day"], whole["versus_spend"]) == (None, 10.00)


def test_the_31st_is_set_against_the_end_of_a_shorter_month():
    rows = [row("p-1", "2026-02-28", 1.00), row("p-1", "2026-03-31", 2.00)]
    assert compare_month(rows, "2026-03", through_day=31)["versus_spend"] == 1.00


def test_no_receipt_in_those_days_before_is_no_comparison():
    rows = [row("p-1", "2026-09-20", 1.00), row("p-1", "2026-10-05", 2.00)]
    assert compare_month(rows, "2026-10", through_day=14) is None, \
        "against nothing tracked, +2 € means nothing"
    assert compare_month(rows, "2026-09") is None


def test_the_same_product_at_another_shop_is_another_thing_not_a_price():
    rows = [shelf(row("p-1", "2026-09-03", 1.00, store="Billigmarkt"), 1.00),
            shelf(row("p-1", "2026-10-03", 1.50, store="Großmarkt"), 1.50)]
    parts = compare_month(rows, "2026-10")["parts"]
    assert (parts["new"], parts["gone"], parts["prices"]) == (1.50, -1.00, 0.0)


def test_loose_goods_are_split_by_weight_on_the_shelf_price():
    rows = [shelf(row("p-1", "2026-09-03", 1.00, unit=2.00, per="kg"), 1.00),   # 0,5 kg
            shelf(row("p-1", "2026-10-03", 1.98, unit=1.98, per="kg"), 2.20, -0.22)]  # 1 kg
    parts = compare_month(rows, "2026-10")["parts"]
    assert (parts["amounts"], parts["prices"], parts["discounts"]) == (1.00, 0.20, -0.22), \
        "half a kilo more at 2,00, the shelf 20 cents up, the discount apart"


def test_the_usual_by_this_day_is_the_mean_of_whole_tracked_months():
    rows = [row("p-1", "2026-06-20", 50.00),                          # history starts: partial
            row("p-1", "2026-07-10", 10.00), row("p-1", "2026-07-20", 99.00),
            row("p-1", "2026-09-03", 30.00), row("p-1", "2026-09-28", 1.00),
            row("p-1", "2026-10-05", 7.00)]
    usual = usual_by_day(rows, "2026-10", through_day=14)
    assert {k: usual[k] for k in ("through_day", "months", "spend")} == \
        {"through_day": 14, "months": ["2026-09", "2026-07"], "spend": 20.00}, \
        "August has no receipt (not tracked) and June is where the history starts"
    assert usual_by_day(rows, "2026-10")["spend"] == 70.00


def test_a_month_s_line_is_what_was_spent_by_the_end_of_each_day():
    rows = [row("p-1", "2026-10-02", 1.50), row("p-1", "2026-10-02", 0.50),
            row("p-1", "2026-10-04", 3.00), row("p-1", "2026-10-09", 9.00),
            row("p-1", "2026-09-30", 7.00)]
    assert running_totals(rows, "2026-10", through_day=5) == [0.0, 2.0, 2.0, 5.0, 5.0]
    assert len(running_totals(rows, "2026-10")) == 31
    assert running_totals(rows, "2026-10")[-1] == 14.00


def test_the_usual_line_is_the_mean_of_the_months_and_a_short_month_stays_at_its_total():
    rows = [row("p-1", "2026-01-31", 1.00),                           # history starts
            row("p-1", "2026-02-01", 2.00), row("p-1", "2026-02-28", 4.00),   # 28 days
            row("p-1", "2026-03-01", 6.00), row("p-1", "2026-03-31", 8.00)]
    running = usual_by_day(rows, "2026-05", through_day=10)["running"]
    assert len(running) == 31, "the line runs over May's days"
    assert (running[0], running[27], running[29], running[30]) == (4.00, 6.00, 6.00, 10.00), \
        "on the 30th February has long ended at 6,00 and March is still at 6,00"


def test_one_month_before_is_not_a_usual():
    rows = [row("p-1", "2026-08-31", 1.00), row("p-1", "2026-09-05", 2.00),
            row("p-1", "2026-10-05", 3.00)]
    assert usual_by_day(rows, "2026-10", through_day=14) is None, \
        "only September is whole: that is last month, not a habit"


def test_a_month_with_nothing_by_this_day_counts_as_nothing_spent():
    rows = [row("p-1", "2026-07-31", 1.00), row("p-1", "2026-08-02", 8.00),
            row("p-1", "2026-09-25", 4.00), row("p-1", "2026-10-05", 3.00)]
    assert usual_by_day(rows, "2026-10", through_day=14)["spend"] == 4.00


def test_this_month_stops_today_and_older_months_are_whole():
    rows = [row("p-1", "2026-08-31", 1.00), row("p-1", "2026-09-10", 2.00),
            row("p-1", "2026-09-25", 4.00), row("p-1", "2026-10-05", 3.00)]
    october, september, august = build_insights(
        {"meta": {}, "purchases": rows}, today=date(2026, 10, 14))["months"]
    assert (october["compared"]["through_day"], october["compared"]["versus_spend"]) == (14, 2.00)
    assert (september["compared"]["through_day"], september["compared"]["difference"]) == \
        (None, 5.00)
    assert august["compared"] is None
    assert october["running"]["this"][-1] == 3.00 and len(october["running"]["this"]) == 14
    assert len(october["running"]["before"]) == 30, "September drawn whole"
    assert august["running"]["before"] is None


# --- prices on the shelf -----------------------------------------------------------
# The owner, 2026-10-14: a price change is the shelf price moving; a discount
# printed on the receipt (an offer, a card, a staff discount) is not one.

def test_a_printed_discount_is_not_a_price_change():
    rows = [shelf(row("p-1", "2026-09-01", 1.00), 1.00),
            shelf(row("p-1", "2026-09-08", 0.90), 1.00, -0.10),     # 10 % off at the till
            shelf(row("p-1", "2026-09-15", 1.10), 1.10)]            # the shelf moved
    (change,) = price_changes(rows)
    assert [o["price"] for o in change["observations"]] == [1.00, 1.00, 1.10]
    assert change["move"]["kind"] == "latest" and change["move"]["since"] == "2026-09-15"


def test_the_basket_is_priced_on_the_shelf():
    rows = [shelf(row(f"p-{i}", "2026-01-05", 1.00), 1.00) for i in range(3)] + \
           [shelf(row(f"p-{i}", "2026-02-05", 0.80), 1.00, -0.20) for i in range(3)]
    (step,) = basket_index(rows)["series"]
    assert step["month_over_month_pct"] == 0.0, "20 % off at the till is not inflation"


def obs(*prices):
    return [{"date": f"2026-0{1 + i // 28}-{1 + i % 28:02d}", "price": p}
            for i, p in enumerate(prices)]


def test_a_price_that_went_up_and_stayed():
    move = price_move(obs(1.00, 1.00, 1.20, 1.20))
    assert (move["kind"], move["since"], move["before"], move["after"], move["change_pct"]) == \
        ("stayed", "2026-01-03", 1.00, 1.20, 20.0)


def test_a_price_that_went_up_in_steps_dates_each_step():
    move = price_move(obs(0.85, 0.85, 1.10, 1.19, 1.19))
    assert (move["kind"], move["steps"], move["change_pct"]) == \
        ("stayed", ["2026-01-03", "2026-01-04"], 40.0)


def test_a_new_price_seen_once_is_the_latest_not_stayed():
    assert price_move(obs(1.00, 1.00, 0.89))["kind"] == "latest"


def test_one_date_off_and_back_is_an_offer_not_a_change():
    move = price_move(obs(2.00, 2.00, 1.49, 2.00))
    assert (move["kind"], move["since"], move["change_pct"]) == ("offer", "2026-01-03", None)


def test_up_and_down_keeps_changing():
    move = price_move(obs(2.50, 3.67, 2.98, 1.97))
    assert (move["kind"], move["since"], move["change_pct"]) == \
        ("keeps_changing", "2026-01-01", -21.2)


def test_a_cent_of_rounding_is_no_move():
    assert price_move(obs(1.99, 2.00, 1.99)) is None


def test_home_tells_only_real_moves_newest_first():
    def change(pid, *prices):
        o = obs(*prices)
        return {"product_id": pid, "product": pid, "brand": None, "store": "Musterladen",
                "sold_as": None, "per": "item", "observations": o, "move": price_move(o)}
    moves = price_moves([change("two-buys", 1.00, 1.50),          # too few buys
                         change("small", 1.00, 1.00, 1.05, 1.05),  # under 10 %
                         change("offer", 2.00, 1.00, 2.00),        # not a change
                         change("old", 1.00, 1.20, 1.20, 1.20, 1.20),
                         change("new", 1.00, 1.00, 1.00, 0.80, 0.80)])
    assert [m["product_id"] for m in moves] == ["new", "old"]


# --- what discounts saved -------------------------------------------------------

def discounted(day, gross, discount, store="Musterladen", pid="p-1"):
    r = row(pid, day, round(gross + discount, 2), store=store)
    r.update(gross=gross, discount=discount)
    return r


def test_discounts_saved_per_month_newest_first_against_the_shelf_price():
    rows = [discounted("2026-01-05", 10.0, -1.0), discounted("2026-01-20", 10.0, 0.0),
            discounted("2026-02-03", 4.0, -2.0)]
    out = discounts(rows)
    assert out["saved"] == 3.0
    assert out["lines"] == 2
    assert out["months"] == [
        {"month": "2026-02", "saved": 2.0, "shelf": 4.0, "share": 0.5, "lines": 1},
        {"month": "2026-01", "saved": 1.0, "shelf": 20.0, "share": 0.05, "lines": 1}]


def test_a_month_with_no_discount_says_nothing_was_saved():
    out = discounts([discounted("2026-03-01", 5.0, 0.0)])
    assert out["months"] == [
        {"month": "2026-03", "saved": 0.0, "shelf": 5.0, "share": 0.0, "lines": 0}]
    assert out["by_store"] == []


def test_discounts_per_shop_whatever_the_receipt_spelled_most_saved_first():
    rows = [discounted("2026-01-05", 10.0, -1.0, store="GLOBUS"),
            discounted("2026-01-06", 10.0, -1.0, store="Globus"),
            discounted("2026-01-06", 10.0, -1.0, store="GLOBUS"),
            discounted("2026-01-07", 5.0, -0.5, store="Lidl"),
            discounted("2026-01-07", 5.0, 0.0, store="ALDI SÜD")]
    assert discounts(rows)["by_store"] == [
        {"store": "GLOBUS", "saved": 3.0, "lines": 3},
        {"store": "Lidl", "saved": 0.5, "lines": 1}]


def test_a_line_bought_for_someone_else_saves_the_shopper_nothing():
    gift = discounted("2026-01-05", 10.0, -1.0, pid="p-2")
    gift["not_counted"] = True
    doc = build_insights({"purchases": [discounted("2026-01-05", 2.0, -0.2), gift]})
    assert doc["discounts"]["saved"] == 0.2
    assert doc["discounts"]["months"][0]["shelf"] == 2.0


# --- why a month is off its usual (owner, 2026-10-15) --------------------------

def test_why_a_month_is_above_its_usual_trips_parts_of_the_shop_and_prices():
    """"Why did that happen? More trips, more prices ... what is the key
    factor?" Against the same usual months, each cut at the same day."""
    def bought(pid, day, net, receipt, category):
        r = row(pid, day, net, category=category)
        r["source_image"] = receipt
        return r

    rows = [bought("p-1", "2026-07-31", 9.00, "j1", "milch"),           # history starts
            bought("p-1", "2026-08-02", 1.00, "a1", "milch"),
            bought("p-1", "2026-09-03", 1.00, "s1", "milch"),
            bought("p-2", "2026-09-20", 5.00, "s2", "duschgel"),        # after the 14th
            bought("p-1", "2026-10-02", 1.20, "o1", "milch"),
            bought("p-2", "2026-10-05", 4.00, "o2", "duschgel"),
            bought("p-1", "2026-10-09", 1.20, "o3", "milch")]
    october = build_insights({"meta": {}, "purchases": rows},
                             today=date(2026, 10, 14))["months"][0]
    why = october["why"]
    assert october["usual"]["months"] == ["2026-09", "2026-08"]
    assert why["difference"] == pytest.approx(october["spend"] - october["usual"]["spend"])
    assert why["difference"] == 5.40
    assert why["trips"] == {"now": 3, "usual": 1}
    assert [(b["branch"], b["spend"], b["usual"], b["difference"]) for b in why["branches"]] == [
        ("Drogerie & Kosmetik", 4.00, 0.00, 4.00), ("Molkereiprodukte & Eier", 2.40, 1.00, 1.40)], \
        "biggest difference first; September's shower gel came after the 14th"
    assert sum(b["difference"] for b in why["branches"]) == pytest.approx(why["difference"])
    assert why["prices"] == 0.40, "milk: 1,20 now against 1,00 usually, twice"


def test_no_usual_no_why():
    rows = [row("p-1", "2026-09-05", 2.00), row("p-1", "2026-10-05", 3.00)]
    october = build_insights({"meta": {}, "purchases": rows}, today=date(2026, 10, 14))["months"][0]
    assert (october["usual"], october["why"]) == (None, None)
