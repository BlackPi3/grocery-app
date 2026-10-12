"""The order of a question's yes/no cards (`api.cards`), on made-up products."""

from __future__ import annotations

from grocery_app.api.cards import MOST_CARDS, card_order, nearest_price


def test_the_product_that_costs_what_was_paid_comes_first():
    candidates = [{"name": "Honig 250 g", "prices": [3.49]},
                  {"name": "Honig 500 g", "prices": [5.99, 6.49]},
                  {"name": "Honig Bio", "prices": []}]

    order = card_order(candidates, [], None, 5.99)

    assert order == [{"candidate": 2}, {"candidate": 1}, {"candidate": 3}]


def test_then_the_models_pick_then_the_search_then_the_rest():
    candidates = [{"name": "A", "prices": [1.00]}, {"name": "B", "prices": [9.00]},
                  {"name": "C", "prices": [2.00]}]

    order = card_order(candidates, ["Musterhonig Akazie"], 2, 2.00)

    assert order == [{"candidate": 3}, {"candidate": 2}, {"choice": "Musterhonig Akazie"},
                     {"candidate": 1}]


def test_at_most_a_few_cards():
    candidates = [{"name": str(n), "prices": [float(n)]} for n in range(10)]

    assert len(card_order(candidates, ["x", "y"], None, 3.0)) == MOST_CARDS


def test_the_nearest_shelf_price_is_the_one_shown():
    assert nearest_price([1.99, 2.49, 2.99], 2.40) == 2.49
    assert nearest_price([1.99], None) == 1.99
    assert nearest_price([], 2.0) is None
