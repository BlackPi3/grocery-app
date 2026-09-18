"""Insights over made-up purchase rows: nothing here comes from a receipt."""

from datetime import date

from grocery_app.insights import (
    MIN_BASKET_PRODUCTS,
    basket_index,
    build_insights,
    cross_store,
    own_brand,
    price_changes,
    repurchase,
)


def row(pid, day, net, qty=1, unit=None, per=None, store="Musterladen",
        own=None, brand="Marke", product="Ding", type_="product"):
    r = {"type": type_, "date": day, "store": store, "product_id": pid, "product": product,
         "brand": brand, "is_own_brand": own, "qty": qty, "net_paid": net,
         "unit_price": {"amount": unit, "per": per} if unit else None}
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


# --- own brand ---------------------------------------------------------------

def test_own_brand_split_keeps_unknown_and_unresolved_apart():
    rows = [row("p-1", "2026-01-01", 2.0, own=True), row("p-2", "2026-01-01", 6.0, own=False),
            row("p-3", "2026-01-01", 1.0, own=None, brand="Rätsel"),
            row(None, "2026-01-01", 5.0)]
    out = own_brand(rows)
    assert out["overall"] == {"own_brand": 2.0, "brand": 6.0, "unknown": 1.0, "unresolved": 5.0,
                              "own_brand_share_of_known": 0.25}
    assert out["unknown_brands"] == [{"brand": "Rätsel", "spend": 1.0}]


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
    assert list(own_brand(rows)["by_store"]) == ["GLOBUS"], "the common spelling is the label"
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
