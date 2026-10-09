"""Insights over made-up purchase rows: nothing here comes from a receipt."""

from datetime import date

from grocery_app.insights import (
    MIN_BASKET_PRODUCTS,
    basket_index,
    budget_brand,
    build_insights,
    cross_store,
    price_changes,
    repurchase,
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


# --- price over time ---------------------------------------------------------

def test_price_change_follows_the_paid_unit_price():
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
