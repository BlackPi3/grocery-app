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
    found_only_by_guess,
    gather,
    guess_names,
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


def write_crawl(path, names):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({f"40000000001{i:02d}": {
        "article_number": f"40000000001{i:02d}", "name": name, "brand": brand,
        "price": 1.0 + i} for i, (brand, name) in enumerate(names)}), encoding="utf-8")


def test_globus_candidates_come_from_our_copy_of_its_range(tmp_path):
    """GLOBUS's website search is not asked (the owner, 2026-10-28: it is
    bad); its range is our crawl, the same as ALDI SÜD's."""
    write_crawl(tmp_path / "globus" / "crawl.json",
                [("Golden Crown", "Mango, tiefgekühlt"), ("Golden Crown", "Heidelbeeren")])
    shops = matcher.default_shops(tmp_path)
    found = shops["globus"]("Gld Crown Mango 750g")
    assert found[0]["name"] == "Mango, tiefgekühlt"
    assert matcher.default_shops(tmp_path / "nothing")["globus"]("Mango") == [], \
        "no crawl on disk is no listings, not a search over the network"


def test_the_crawl_ranks_by_the_same_letter_similarity(tmp_path):
    """Scored by substring per letter triple, for speed over 65,000 rows: the
    order must be the one `similarity` gives, ties kept in the crawl's order."""
    names = [("Reinex", "Kühlschrank Reiniger"), ("Reinex", "Kühlschrank Deo"),
             ("Jeden Tag", "Magerquark"), ("Muster", "Kühlregal"), ("Reinex", "Kühlschrank Deo")]
    write_crawl(tmp_path / "crawl.json", names)
    for raw in ["Reinex Kühlschr. Deo", "JT Magerquark", "Kühl"]:
        expected = sorted(range(len(names)), key=lambda i: -similarity(
            raw, f"{names[i][0]} {names[i][1]}"))
        got = matcher.crawl_source(tmp_path / "crawl.json")(raw)
        assert [p["price"] - 1.0 for p in got] == expected[:matcher.TOP_SHOP]


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


@pytest.mark.parametrize("paid, why", [
    (1.65, "an offer: the price paid is not the listed one"),
    (None, "no price to compare"),
])
def test_a_sure_pick_is_accepted_when_the_price_does_not_agree(paid, why):
    """Offers and moved prices refused right sure picks, and each refusal
    cost a paid web search; the price no longer has to agree."""
    proposal = propose(line("Reinex Kühlschr. Deo", paid), "Musterladen", PRODUCTS,
                       RESOLUTION, SHELF, INDEX, SHOPS, answering(1, "high"))
    assert proposal["verdict"] == "accept", why
    assert proposal["price_agrees"] is False, "kept, so it can be looked at later"


def test_a_sure_pick_is_asked_about_when_the_price_paid_is_a_variants():
    """The plain one picked, but the Bio one is what costs the price paid."""
    shop = {"musterladen": lambda raw_name: [
        {"article_number": "1", "name": "Mangostreifen", "brand": "Muster",
         "pack_size": "0,1 kg", "price": 3.29},
        {"article_number": "2", "name": "Bio Mangostreifen", "brand": "Muster",
         "pack_size": "0,1 kg", "price": 3.59},
    ]}
    proposal = propose(line("MU Mangostreifen 100", 3.59), "Musterladen", PRODUCTS,
                       RESOLUTION, SHELF, INDEX, shop, answering(1))
    assert proposal["verdict"] == "ask"
    assert proposal["pick"]["name"] == "Mangostreifen", "the pick is kept, to ask about"


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


def test_a_momentary_failure_is_tried_once_more(tmp_path, monkeypatch):
    replies = [{"is_error": True, "result": "Not logged in"},
               {"is_error": False, "structured_output": {"choice": 0}}]

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, json.dumps(replies.pop(0)), "")

    monkeypatch.setattr(matcher.subprocess, "run", fake_run)
    monkeypatch.setattr(ClaudeCodeDecider, "RETRY_AFTER_S", 0)
    assert ClaudeCodeDecider("sonnet", tmp_path)("s", "p", {}) == {"choice": 0}


def test_a_failed_call_is_an_error_and_is_not_cached(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, json.dumps(
            {"is_error": True, "result": "usage limit"}), "")

    monkeypatch.setattr(matcher.subprocess, "run", fake_run)
    monkeypatch.setattr(ClaudeCodeDecider, "RETRY_AFTER_S", 0)
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


def test_a_new_aldi_product_keeps_its_shelf_and_is_sorted_by_it():
    """ALDI's URLs carry no shelf; the crawl's category is recorded instead
    (2026-10-09), and the shelf files the product."""
    grated = {"source": "aldi süd", "name": "Gouda gerieben", "brand": "MILSANI",
              "pack_size": "0,25 kg", "article": "000000000000000001",
              "url": "https://www.aldi-sued.de/produkt/milsani-gouda-000000000000000001",
              "shelf": "Käse / Reibekäse", "product_id": None, "prices": [1.99]}
    product = new_product(grated, "matcher")
    assert product["provenance"]["shelf"] == "aldi:Käse / Reibekäse"
    assert product["category"] == "reibekaese"


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
    asked = propose(line("Reinex Kühlschr. Deo", 1.95), "Musterladen", PRODUCTS,
                    RESOLUTION, SHELF, INDEX, SHOPS, answering(1, "medium"))
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


# --- the model's guess ----------------------------------------------------------

PUDDING = {"article_number": "4000000000044", "name": "Vanille Pudding", "brand": "Muster",
           "pack_size": "500 g", "price": 1.49, "url": "https://musterladen.example/pudding"}
DEO, REINIGER = LISTINGS[0], LISTINGS[1]
BY_TEXT = {"Pud. V.": [DEO, REINIGER], "Vanille Pudding": [REINIGER, PUDDING]}
SEARCHED = {"musterladen": lambda text: BY_TEXT.get(text, [])}


def searched(guess=None):
    return gather("Pud. V.", "Musterladen", PRODUCTS, RESOLUTION, SHELF, INDEX, SEARCHED, guess)


def test_the_guess_finds_what_the_printed_text_misses():
    found = {c.name: c.found_by for c in searched("Vanille Pudding")}
    assert found["Vanille Pudding"] == ["guess"]


def test_nothing_the_printed_text_finds_drops_off_the_list():
    without = [c.name for c in searched()]
    assert [c.name for c in searched("Vanille Pudding")][:len(without)] == without


def test_a_product_both_searches_find_is_listed_once_with_both_marks():
    found = [c for c in searched("Vanille Pudding") if c.name == "Kühlschrank Reiniger"]
    assert [c.found_by for c in found] == [["printed", "guess"]]


def test_without_a_guess_everything_is_found_by_the_printed_text():
    assert all(c.found_by == ["printed"] for c in searched())


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_an_empty_guess_searches_nothing_more(empty):
    assert [c.name for c in searched(empty)] == [c.name for c in searched()]


def test_the_model_is_not_told_which_search_found_a_product():
    assert "guess" not in searched("Vanille Pudding")[-1].describe()


def test_the_guess_is_matched_loosely_not_word_for_word(tmp_path):
    """A misspelt guess in another word order still finds the product."""
    path = tmp_path / "crawl.json"
    write_crawl(path, [("Muster", "Schwarzer Pfeffer gemahlen"), ("Muster", "Rote Grütze"),
                       ("Muster", "Zimt gemahlen")])
    assert matcher.crawl_source(path)("Pfefer schwarz")[0]["name"] == "Schwarzer Pfeffer gemahlen"


def proposed(guess, listing_name):
    def decider(system, prompt, schema):
        number = next(i for i, row in enumerate(prompt.split("Products:\n")[1].splitlines(), 1)
                      if listing_name in row)
        return {"choice": number, "versions": [], "confidence": "high", "reason": "test"}

    return propose(line("Pud. V.", 1.49), "Musterladen", PRODUCTS, RESOLUTION, SHELF, INDEX,
                   SEARCHED, decider, guess)


def test_a_pick_only_the_guess_found_says_so():
    proposal = proposed("Vanille Pudding", "Vanille Pudding")
    assert (proposal["verdict"], proposal["only_by_guess"]) == ("accept", True)


def test_a_pick_the_printed_text_found_too_does_not():
    assert proposed("Vanille Pudding", "Kühlschrank Reiniger")["only_by_guess"] is False


def guessing(*rows):
    asked = []

    def decider(system, prompt, schema):
        asked.append(prompt)
        return {"guesses": [{"line": n, "name": name} for n, name in rows]}

    decider.asked = asked
    return decider


def test_each_line_gets_its_own_guess_in_one_call():
    decider = guessing((1, "Vanille Pudding"), (2, "Alpenmilch"))
    assert guess_names(["Pud. V.", "Alp.M."], "Musterladen", [], decider) == {
        "Pud. V.": "Vanille Pudding", "Alp.M.": "Alpenmilch"}
    assert len(decider.asked) == 1


def test_the_guess_sees_the_rest_of_the_receipt():
    decider = guessing((1, "Vanille Pudding"))
    guess_names(["Pud. V."], "Musterladen", ["Pud. V.", "Vollmilch"], decider)
    assert "Vollmilch" in decider.asked[0]


@pytest.mark.parametrize("number, name", [(0, "x"), (9, "x"), (1, ""), (1, "  ")])
def test_a_number_off_the_list_or_an_empty_name_is_no_guess(number, name):
    assert guess_names(["Pud. V."], None, [], guessing((number, name))) == {}


def test_a_printed_name_twice_on_the_receipt_is_guessed_once():
    decider = guessing((1, "Vanille Pudding"), (2, "wrong: no second line was asked"))
    assert guess_names(["Pud. V.", "Pud. V."], None, [], decider) == {"Pud. V.": "Vanille Pudding"}


def test_no_unknown_lines_means_no_call():
    decider = guessing()
    assert guess_names([], "Musterladen", ["Vollmilch"], decider) == {}
    assert decider.asked == []


@pytest.mark.parametrize("source, only", [("matcher v2 g1 guess", True),
                                          ("matcher v2 g1 printed", False),
                                          ("matcher v2", False), ("shopper-answer", False),
                                          (None, False)])
def test_the_source_tells_which_picks_only_the_guess_found(source, only):
    assert found_only_by_guess(source) is only
