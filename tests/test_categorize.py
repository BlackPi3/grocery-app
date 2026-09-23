"""Proposing a category, and banking the answers.

Everything here runs on made-up products. The rule under test is the one the
module exists for: **a name alone is a question, two independent sources
agreeing is an answer.** So the tests are mostly about which rows come back
settled and which come back asking.
"""

from __future__ import annotations

import csv
import json

import pytest

from grocery_app import categories, categorize

# A shelf at the shop, as `listings.json` records it. Only the URL matters.
GLOBUS = "https://produkte.globus.de"


def listing(path: str, article: str = "4306188407508", slug: str = "x") -> dict:
    return {"url": f"{GLOBUS}/{path}/{article}/{slug}", "prices": []}


def product(**fields) -> dict:
    base = {"label": "x", "name": "", "brand": None, "product_line": None,
            "variant": None, "size": {"count": 1, "value": None, "unit": None},
            "category": None, "is_organic": None, "eans": [], "open_questions": [],
            "provenance": {"attributes": "test", "source": "test"}}
    return base | fields


def doc(**products) -> dict:
    return {"meta": {"schema": 1, "next_id": 99}, "products": dict(products)}


# --- what the evidence supports ----------------------------------------------


def test_the_shop_and_the_name_agreeing_needs_nobody():
    """Both say grated cheese, so there is nothing for a reviewer to add."""
    found = categorize.propose(
        "p-0001", product(name="Cheddar, gerieben", brand="Jeden Tag"),
        {"p-0001": listing("milchprodukte-eier/kaese/reibekaese")})

    assert (found.key, found.how, found.settled) == ("reibekaese", "agreed", True)


def test_the_shop_wins_nothing_when_the_name_disagrees():
    """`Eis, Schokolade` is ice cream on the shop's shelf and chocolate by its
    own words. One of the two is wrong and no rule here can say which, so the
    row keeps the shop's answer, keeps the name's as an alternative, and is not
    settled."""
    found = categorize.propose(
        "p-0002", product(name="Eis, Schokolade", brand="Jeden Tag"),
        {"p-0002": listing("tiefkuehlprodukte/eis/eis-grosspackungen")})

    assert (found.key, found.how, found.settled) == ("speiseeis", "conflict", False)
    assert "schokolade" in found.alternatives


def test_a_shelf_wider_than_a_category_lets_the_name_finish():
    """GLOBUS files pickled cucumbers under vegetable conserves; a jar of
    pickles and a tin of tomatoes are different lines on a shopping list. The
    shop narrows it to the section, the name picks the entry inside it."""
    found = categorize.propose(
        "p-0003", product(name="Salz-Dill-Gurken", brand="Kühne"),
        {"p-0003": listing("nudeln-reis-konserven/konserven-feinkost/gemuesekonserven")})

    assert (found.key, found.how, found.settled) == ("essiggemuese", "shop+name", True)


def test_a_name_pointing_at_two_categories_is_a_question():
    found = categorize.propose("p-0004", product(name="Mozzarella gerieben"))

    assert found.how == "name?"
    assert found.settled is False
    assert "reibekaese" in (found.key, *found.alternatives)


def test_a_name_pointing_at_one_category_is_still_a_question():
    """The printed name is wrong about one product in twenty-five, so it never
    settles a row on its own — it only proposes one."""
    found = categorize.propose("p-0005", product(name="Basmati Reis", brand="BON-RI"))

    assert (found.key, found.how, found.settled) == ("reis", "name", False)


def test_open_food_facts_agreeing_with_the_name_settles_it():
    """Two sources that cannot have copied each other. The chain is read
    backwards because its leaf is where `chia` and `cut` came from."""
    found = categorize.propose("p-0006", product(
        name="Bio 3 Korn Flocken", brand="Alnatura",
        enrichment={"categories": ["plant based foods", "breakfast cereals", "flakes",
                                   "muesli"]}))

    assert (found.key, found.how, found.settled) == ("muesli", "agreed", True)


def test_nothing_matching_proposes_nothing():
    found = categorize.propose("p-0007", product(name="Blitzstart Mix"))

    assert (found.key, found.how, found.settled) == (None, "", False)


# --- which words are read ----------------------------------------------------


def test_the_flavour_is_not_read():
    """`variant` says which one it was, not what it is. Reading it is how a bag
    of crisps in `Kräuterbutter` proposes butter."""
    chips = product(name="Potato chips", brand="Lay's", variant="Kräuterbutter")

    assert categorize.propose("p-0008", chips).key == "chips"


def test_the_longest_alias_wins_and_a_tie_goes_to_the_first_word():
    """German glues nouns together, so `Kartoffelchips` has to beat `chips`.
    Where two aliases are the same length the leftmost wins — not because that
    is clever, but so the same catalog proposes the same thing twice running."""
    assert categorize.name_hits(product(name="Kartoffelchips gesalzen"))[0] == "chips"
    assert categorize.name_hits(product(name="Börek Stange Spinat"))[0] == \
        "herzhaftes-gebaeck"


def test_a_short_alias_has_to_be_a_whole_word():
    """`eis` inside `Speisezwiebeln` is not ice cream; `Eis, Schokolade` is."""
    assert "speiseeis" not in categorize.name_hits(product(name="Speisezwiebeln"))
    assert categorize.name_hits(product(name="Eis am Stiel"))[0] == "speiseeis"


def test_every_mapped_shop_shelf_names_something_real():
    """The table maps their tree onto ours, so every value has to be a key or a
    section we actually have."""
    for shelf, key in categorize.SHOP_PATHS.items():
        if key.startswith("@"):
            assert key[1:] in categories.SECTIONS, shelf
        else:
            assert key in categories.CATEGORIES, shelf


# --- the CSV round trip -------------------------------------------------------


def test_a_product_already_carrying_a_vocabulary_key_is_done():
    rows = categorize.proposals(doc(
        **{"p-0001": product(name="Basmati Reis", category="reis"),
           "p-0002": product(name="Basmati Reis", category="Pantry / Rice")}))

    assert [row["product_id"] for row in rows] == ["p-0002"]


def test_the_rows_needing_a_person_come_first():
    rows = categorize.proposals(doc(
        **{"p-0001": product(name="Basmati Reis"),
           "p-0002": product(name="Blitzstart Mix"),
           "p-0003": product(name="Cheddar, gerieben"),
           }), {"p-0003": listing("milchprodukte-eier/kaese/reibekaese")})

    assert [row["how"] for row in rows] == ["", "name", "agreed"]
    assert [row["decision"] for row in rows] == ["", "", "y"]


def test_a_decision_survives_a_rerun_unless_the_proposal_moved():
    before = [{"product_id": "p-0001", "proposed": "reis", "decision": "n"},
              {"product_id": "p-0002", "proposed": "nudeln", "decision": "y"}]
    rows = categorize.proposals(doc(**{"p-0001": product(name="Basmati Reis"),
                                       "p-0002": product(name="Basmati Reis")}), None, before)
    decisions = {row["product_id"]: row["decision"] for row in rows}

    assert decisions["p-0001"] == "n"
    # The proposal changed under it, so the old answer is not carried over.
    assert decisions["p-0002"] == ""


def reviewed(tmp_path, rows):
    path = tmp_path / "categories.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=categorize.PROPOSAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture()
def catalog(tmp_path):
    path = tmp_path / "products.json"
    path.write_text(json.dumps(doc(**{
        "p-0001": product(name="Basmati Reis"),
        "p-0002": product(name="Basmati Reis"),
        "p-0003": product(name="Basmati Reis"),
        "p-0004": product(name="Basmati Reis"),
    }), ensure_ascii=False), encoding="utf-8")
    return path


def test_confirm_writes_y_takes_an_override_and_refuses_an_invention(catalog, tmp_path):
    rows = [{"decision": "y", "product_id": "p-0001", "proposed": "reis"},
            {"decision": "nudeln", "product_id": "p-0002", "proposed": "reis"},
            {"decision": "Rice", "product_id": "p-0003", "proposed": "reis"},
            {"decision": "", "product_id": "p-0004", "proposed": "reis"}]
    summary = categorize.confirm(reviewed(tmp_path, rows), catalog)
    written = json.loads(catalog.read_text(encoding="utf-8"))["products"]

    assert written["p-0001"]["category"] == "reis"
    assert written["p-0002"]["category"] == "nudeln"
    # A word the vocabulary has never heard of is a gap in `categories.py`, not
    # a forty-seventh free-text value. It is reported and not written.
    assert written["p-0003"]["category"] is None
    assert summary["unknown_categories"] == ["p-0003: Rice"]
    assert (summary["written"], summary["undecided"]) == (2, 1)


def test_saying_you_cannot_answer_is_written_down(catalog, tmp_path):
    """`n` is not a blank. A blank is work not done; `n` is the answer that
    there is no answer, and the catalog has to carry that as a question rather
    than look untouched — some of these are genuinely unrecoverable."""
    rows = [{"decision": "n", "product_id": "p-0001", "proposed": "reis"}]
    summary = categorize.confirm(reviewed(tmp_path, rows), catalog)
    written = json.loads(catalog.read_text(encoding="utf-8"))["products"]["p-0001"]

    assert summary["rejected"] == 1
    assert written["category"] is None
    assert written["open_questions"] == ["category unknown"]


def test_a_recorded_gap_is_not_asked_again(catalog, tmp_path):
    """The row still appears — a catalog match may close it later — but it
    comes back already answered `n`, so a re-run does not put a dead question
    in front of a person twice."""
    products = doc(**{"p-0001": product(name="Blitzstart Mix",
                                        open_questions=["category unknown"])})
    (row,) = categorize.proposals(products)

    assert (row["decision"], row["proposed"]) == ("n", "")
