"""What the memory learns from a shopper's answer: the table in `memory.py`,
one test per row. Product ids are made up."""

from grocery_app.memory import learn, machine_answer
from grocery_app.normalizer import lookup, never_remembered


def entry(product_id=None, product_ids=(), by="shopper"):
    return {"product_id": product_id, "product_ids": list(product_ids), "confirmed_by": by}


def test_a_name_the_memory_never_held_learns_the_answer():
    assert learn(None, "p-1") == {"product_id": "p-1", "product_ids": []}


def test_the_same_answer_again_changes_nothing():
    assert learn(entry("p-1"), "p-1") is None


def test_a_machine_answer_is_replaced_by_the_shoppers():
    assert learn(entry("p-9", by="matcher"), "p-1") == {"product_id": "p-1", "product_ids": []}


def test_two_different_answers_from_people_make_the_name_a_family():
    """Classic one week, Mehrkorn the next: the till prints one name for both,
    so neither answer was wrong. The name becomes both, and each answer stays
    true for its own line."""
    assert learn(entry("p-1", by="parham"), "p-2") == \
        {"product_id": None, "product_ids": ["p-1", "p-2"]}


def test_an_answer_inside_a_family_is_about_that_line_only():
    assert learn(entry(product_ids=["p-1", "p-2"]), "p-2") is None


def test_an_answer_outside_a_family_joins_it():
    assert learn(entry(product_ids=["p-1", "p-2"]), "p-3") == \
        {"product_id": None, "product_ids": ["p-1", "p-2", "p-3"]}


def test_what_counts_as_a_machines_answer():
    produce = {"resolution": "produce", "product_id": "p-4"}
    by_price = {"resolution": "price", "product_id": "p-5"}
    remembered = {"resolution": "exact", "product_id": "p-6"}
    assert machine_answer(produce, None) == "p-4"
    assert machine_answer(by_price, entry(product_ids=["p-5", "p-7"])) == "p-5"
    assert machine_answer(remembered, entry("p-6", by="matcher")) == "p-6"
    assert machine_answer(remembered, entry("p-6", by="parham")) is None, "a person's"
    assert machine_answer({"resolution": "none", "product_id": None}, None) is None


def test_a_name_a_till_prints_for_anything_is_never_looked_up():
    """FK Frisch Kauf's `Diverse Lebensmittel` was Kashk twice; the next one
    could be anything, so even a memory entry that slipped in is not used."""
    memory = {("fk frisch kauf gmbh", "Diverse Lebensmittel"): ["p-1"],
              ("fk frisch kauf gmbh", "Pamir"): ["p-2"]}
    assert never_remembered("FK Frisch Kauf GmbH", "DIVERSE LEBENSMITTEL")
    assert not never_remembered("GLOBUS", "Diverse Lebensmittel"), "store-scoped"
    assert lookup(memory, "FK Frisch Kauf GmbH", "Diverse Lebensmittel") == []
    assert lookup(memory, "FK Frisch Kauf GmbH", "Pamir") == ["p-2"]
