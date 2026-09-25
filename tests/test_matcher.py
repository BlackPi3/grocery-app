"""The matcher (catalog growth step 4b), on made-up data and a fake model.

No test here calls a model: the decider is a plain function, and the one test
of `ClaudeCodeDecider` replaces the `claude` command. The shop is Musterladen,
and every product is invented.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from grocery_app import matcher
from grocery_app.matcher import (
    Candidate,
    ClaudeCodeDecider,
    DeciderError,
    decide,
    gather,
    new_product,
    paid_price,
    propose,
    similarity,
)

PRODUCTS = {
    "p-0001": {"name": "Kosmetiktücher Ultra Soft", "brand": "Kleenex", "category": None,
               "size": {"count": 1, "value": 80, "unit": "stk"}},
    "p-0002": {"name": "Magerquark", "brand": "Muster", "category": "quark",
               "size": {"count": 1, "value": 250, "unit": "g"}},
}
RESOLUTION = {("anderswo", "Kleenex Ultra Soft"): ["p-0001"]}
SHELF = {"p-0001": {2.49}}

LISTINGS = [
    {"article_number": "4000000000011", "name": "Kühlschrank Deo", "brand": "Reinex",
     "pack_size": "1 Stück", "price": 1.95, "url": "https://musterladen.example/deo"},
    {"article_number": "4000000000022", "name": "Kühlschrank Reiniger", "brand": "Reinex",
     "pack_size": "500 ml", "price": 2.95, "url": "https://musterladen.example/reiniger"},
    # Already ours: its article is banked against p-0001.
    {"article_number": "4000000000033", "name": "Kleenex Ultra Soft Box", "brand": "Kleenex",
     "pack_size": "80 Stück", "price": 2.29, "url": "https://musterladen.example/kleenex"},
]
INDEX = {"4000000000033": "p-0001"}
SHOPS = {"musterladen": lambda raw_name: LISTINGS}


def line(raw_name: str, gross: float, qty: int = 1, **extra) -> dict:
    return {"type": "product", "raw_name": raw_name, "qty": qty, "gross": gross,
            "net": gross, **extra}


def answering(choice: int, confidence: str = "high"):
    """A decider that always gives the same answer, and records what it was asked."""
    asked = []

    def decider(system, prompt, schema):
        asked.append(prompt)
        return {"choice": choice, "confidence": confidence, "reason": "test"}

    decider.asked = asked
    return decider


def candidates(raw_name="Reinex Kühlschr. Deo"):
    return gather(raw_name, "Musterladen", PRODUCTS, RESOLUTION, SHELF, INDEX, SHOPS)


# --- candidates -----------------------------------------------------------------


def test_letters_find_a_truncated_name_that_whole_words_miss():
    assert similarity("Kühlschr. Deo", "Kühlschrank Deo") > \
        similarity("Kühlschr. Deo", "Kühlschrank Reiniger")
    assert similarity("JT Magerquark", "Jeden Tag Magerquark") > 0.8, "JT is expanded"


def test_a_shop_listing_we_already_hold_is_shown_once_as_our_product():
    """Search our own catalog first: a known product is never proposed twice."""
    found = candidates()
    kleenex = [c for c in found if c.brand == "Kleenex"]
    assert len(kleenex) == 1
    assert kleenex[0].product_id == "p-0001" and kleenex[0].article == "4000000000033"
    assert sorted(kleenex[0].prices) == [2.29, 2.49], "the shop's price and the shelf's"
    assert kleenex[0].printed_as == ["Kleenex Ultra Soft"]


def test_a_shop_the_matcher_has_no_source_for_still_gets_our_catalog():
    found = gather("Kleenex Ultra Soft W", "Anderswo", PRODUCTS, RESOLUTION, SHELF,
                   INDEX, SHOPS)
    assert found[0].product_id == "p-0001", "closest first"
    assert all(c.source == "catalog" for c in found)


def test_the_model_is_never_shown_a_price():
    """Price is the second, independent source. A model that saw it could pick
    by it, and the two sources would be one, counted twice."""
    decider = answering(1)
    decide("Reinex Kühlschr. Deo", "Musterladen", candidates(), decider)
    (prompt,) = decider.asked
    assert "1.95" not in prompt and "1,95" not in prompt and "€" not in prompt
    assert "1. Kühlschrank Deo | brand Reinex" in prompt


# --- the pick -------------------------------------------------------------------


@pytest.mark.parametrize("choice", [0, 99, -1])
def test_none_or_a_number_off_the_list_is_no_pick(choice):
    """The model cannot invent a product: only the list's numbers mean anything."""
    assert decide("x", "Musterladen", candidates(), answering(choice)).pick is None


def test_no_candidates_means_no_question_to_the_model():
    decider = answering(1)
    assert decide("x", "Musterladen", [], decider).pick is None
    assert decider.asked == []


# --- accept or ask --------------------------------------------------------------


def test_a_pick_is_accepted_when_the_price_paid_agrees():
    proposal = propose(line("Reinex Kühlschr. Deo", 1.95), "Musterladen", PRODUCTS,
                       RESOLUTION, SHELF, INDEX, SHOPS, answering(1))
    assert proposal["verdict"] == "accept" and proposal["price_agrees"] is True
    assert proposal["pick"]["article"] == "4000000000011"


def test_a_sure_model_is_still_asked_about_when_the_price_disagrees():
    """The model's confidence is its own word for it, not a second source."""
    proposal = propose(line("Reinex Kühlschr. Deo", 1.65), "Musterladen", PRODUCTS,
                       RESOLUTION, SHELF, INDEX, SHOPS, answering(1, "high"))
    assert proposal["verdict"] == "ask" and proposal["price_agrees"] is False
    assert proposal["pick"]["name"] == "Kühlschrank Deo", "the pick is kept, to ask about"


def test_a_pick_the_model_is_not_sure_of_is_asked_even_when_the_price_agrees():
    proposal = propose(line("Reinex Kühlschr. Deo", 1.95), "Musterladen", PRODUCTS,
                       RESOLUTION, SHELF, INDEX, SHOPS, answering(1, "medium"))
    assert proposal["price_agrees"] is True and proposal["verdict"] == "ask"


def test_no_pick_is_a_question():
    proposal = propose(line("Reinex Kühlschr. Deo", 1.95), "Musterladen", PRODUCTS,
                       RESOLUTION, SHELF, INDEX, SHOPS, answering(0))
    assert (proposal["verdict"], proposal["pick"]) == ("ask", None)
    assert len(proposal["candidates"]) == 4, "three listings, one of them ours, and Quark"


def test_any_price_the_product_was_seen_at_counts():
    """A catalog product carries every shelf price seen, not only today's."""
    proposal = propose(line("Kleenex Ultra Soft W", 2.49), "Musterladen", PRODUCTS,
                       RESOLUTION, SHELF, INDEX, SHOPS, answering(3))
    assert proposal["pick"]["product_id"] == "p-0001"
    assert proposal["verdict"] == "accept"


def test_the_price_paid_is_the_shelf_price_before_discount():
    assert paid_price(line("x", 2.58, qty=2, discount=-0.26)) == 1.29
    weighed = line("x", 1.41, sold_by_weight=True, weight_kg=0.472, unit_price=2.99)
    assert paid_price(weighed) == 2.99, "per kilo, as the shop lists it"


# --- the decider -----------------------------------------------------------------


def test_claude_code_answers_are_cached_and_asked_once(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        out = {"is_error": False, "structured_output":
               {"choice": 1, "confidence": "high", "reason": "fits"}}
        return subprocess.CompletedProcess(command, 0, json.dumps(out), "")

    monkeypatch.setattr(matcher.subprocess, "run", fake_run)
    decider = ClaudeCodeDecider("sonnet", tmp_path)
    first = decider("system", "prompt", {"type": "object"})
    second = decider("system", "prompt", {"type": "object"})
    assert first == second == {"choice": 1, "confidence": "high", "reason": "fits"}
    assert len(calls) == 1, "the second answer came from the cache"
    assert calls[0][:2] == ["claude", "-p"] and "--tools" in calls[0]


def test_a_failed_call_is_an_error_and_is_not_cached(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, json.dumps(
            {"is_error": True, "result": "usage limit"}), "")

    monkeypatch.setattr(matcher.subprocess, "run", fake_run)
    with pytest.raises(DeciderError, match="usage limit"):
        ClaudeCodeDecider("sonnet", tmp_path)("s", "p", {})
    assert not list(tmp_path.rglob("*.json"))


def test_a_candidate_describes_where_it_comes_from():
    ours = Candidate(source="catalog", name="Magerquark", product_id="p-0002")
    theirs = Candidate(source="musterladen", name="Magerquark", article="1")
    assert ours.describe().endswith("in our catalog")
    assert theirs.describe().endswith("listed by musterladen")


def test_a_price_shared_with_a_variant_of_the_pick_proves_nothing():
    """The plain and the Bio version can cost the same at one store; then
    the price cannot say which was bought, and the line is a question."""
    shop = {"musterladen": lambda raw_name: [
        {"article_number": "1", "name": "Mangostreifen", "brand": "Muster",
         "pack_size": "0,1 kg", "price": 3.29},
        {"article_number": "2", "name": "Bio Mangostreifen", "brand": "Muster",
         "pack_size": "0,1 kg", "price": 3.29},
        {"article_number": "3", "name": "Kühlschrank Deo", "brand": "Reinex",
         "pack_size": "1 Stück", "price": 3.29},
    ]}
    same = propose(line("MU Mangostreifen 100", 3.29), "Musterladen", PRODUCTS,
                   RESOLUTION, SHELF, INDEX, shop, answering(1))
    assert same["price_agrees"] is False and same["verdict"] == "ask"
    unrelated = propose(line("Reinex Kühlschr. Deo", 3.29), "Musterladen", PRODUCTS,
                        RESOLUTION, SHELF, INDEX, shop, answering(3))
    assert unrelated["verdict"] == "accept", "an unrelated product at the same price is no rival"


# --- a new product from a shop listing (step 4c) ------------------------------------

PASTA = {"source": "globus", "name": "Penne", "brand": "Jeden Tag",
         "pack_size": "0,5 kg (1,38 € / 1 kg)", "article": "4000000000044",
         "url": "https://produkte.globus.de/dudweiler/nudeln-reis-konserven/"
                "nudeln-reis-getreide/nudeln-pasta/4000000000044/penne",
         "product_id": None, "prices": [0.69]}


def test_a_new_product_is_the_shops_listing_copied_not_guessed():
    product = new_product(PASTA, "matcher")
    assert (product["name"], product["brand"]) == ("Penne", "Jeden Tag")
    assert product["size"] == {"count": 1, "value": 500.0, "unit": "g"}
    assert product["eans"] == ["4000000000044"], "a barcode-shaped article is the barcode"
    assert product["provenance"] == {"attributes": "globus-listing", "source": PASTA["url"],
                                     "decided_by": "matcher"}
    assert "id" not in product, "minting an id is step 5's job"


def test_its_category_is_set_only_when_shelf_and_name_agree():
    assert new_product(PASTA, "matcher")["category"] == "nudeln"
    # Filed on the pasta shelf, but the name says something else: a question.
    odd = new_product(dict(PASTA, name="Kühlschrank Deo"), "matcher")
    assert odd["category"] is None and "category unknown" in odd["open_questions"]


def test_a_listing_without_a_brand_says_so():
    product = new_product(dict(PASTA, brand=None), "shopper")
    assert product["brand"] is None and "brand unknown" in product["open_questions"]
    assert product["provenance"]["decided_by"] == "shopper"


def test_a_new_product_passes_the_catalogs_own_checks():
    from grocery_app import product_store

    products = {"meta": {"next_id": 2},
                "products": {"p-0001": new_product(PASTA, "matcher")}}
    assert product_store.problems(products, {"entries": []}) == []


def test_accepting_a_new_listing_creates_a_product_and_a_known_one_does_not():
    new = propose(line("Reinex Kühlschr. Deo", 1.95), "Musterladen", PRODUCTS,
                  RESOLUTION, SHELF, INDEX, SHOPS, answering(1))
    assert [made["name"] for made in new["creates"]] == ["Kühlschrank Deo"]
    known = propose(line("Kleenex Ultra Soft W", 2.49), "Musterladen", PRODUCTS,
                    RESOLUTION, SHELF, INDEX, SHOPS, answering(3))
    assert known["verdict"] == "accept" and known["creates"] == [], "already ours"
    asked = propose(line("Reinex Kühlschr. Deo", 1.65), "Musterladen", PRODUCTS,
                    RESOLUTION, SHELF, INDEX, SHOPS, answering(1))
    assert asked["creates"] == [], "a question creates nothing until it is answered"


# --- versions the line cannot tell apart ---------------------------------------------

WRAPS = {"musterladen": lambda raw_name: [
    {"article_number": "11", "name": "Tortilla Wraps, Classic", "brand": "Muster",
     "pack_size": "0,37 kg", "price": 1.19},
    {"article_number": "12", "name": "Tortilla Wraps Mehrkorn", "brand": "Muster",
     "pack_size": "0,37 kg", "price": 1.19},
    {"article_number": "13", "name": "Tortilla Wraps Weizen", "brand": "Anders",
     "pack_size": "0,36 kg", "price": 1.69},
]}


def versions(numbers, confidence="high"):
    def decider(system, prompt, schema):
        return {"choice": 0, "versions": numbers, "confidence": confidence,
                "reason": "the line prints no version"}
    return decider


def test_versions_the_line_cannot_tell_apart_are_recorded_as_a_family():
    """Nobody is asked which wrap it was: the version changes no number."""
    proposal = propose(line("MU Tortilla Wraps", 1.19), "Musterladen", PRODUCTS,
                       RESOLUTION, SHELF, INDEX, WRAPS, versions([1, 2]))
    assert proposal["verdict"] == "family"
    assert [v["article"] for v in proposal["versions"]] == ["11", "12"]
    assert [made["name"] for made in proposal["creates"]] == \
        ["Tortilla Wraps, Classic", "Tortilla Wraps Mehrkorn"]


@pytest.mark.parametrize("numbers, paid, confidence, why", [
    ([1, 2], 1.29, "high", "the price paid is none of theirs"),
    ([1, 2], 1.19, "medium", "the model is not sure it is this product"),
    ([1], 1.19, "high", "one version is not a family"),
    ([1, 99], 1.19, "high", "a number off the list is not a version"),
])
def test_a_family_needs_the_model_sure_and_the_price_one_of_theirs(numbers, paid,
                                                                    confidence, why):
    proposal = propose(line("MU Tortilla Wraps", paid), "Musterladen", PRODUCTS,
                       RESOLUTION, SHELF, INDEX, WRAPS, versions(numbers, confidence))
    assert proposal["verdict"] == "ask", why
    assert proposal["creates"] == []
