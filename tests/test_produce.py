"""The produce vocabulary: kinds, not SKUs, and one entry per shop-independent thing.

All names here are made up in the same style real tills print — truncated,
glued, abbreviated — because that is the whole difficulty. Nothing in this file
comes from a real receipt.
"""

from __future__ import annotations

import csv
import json

import pytest

from grocery_app import categories
from grocery_app.produce import (
    KIND_CATEGORIES,
    VOCABULARY,
    confirm,
    is_organic,
    match,
    near_misses,
    normalise,
    propose,
    resolve,
    write_proposals,
)


@pytest.mark.parametrize("printed, kind", [
    ("Gurke Stk", "Salatgurken"),
    ("Salatgurken St", "Salatgurken"),
    ("Mini Gurken 750g", "Mini-Gurken"),
    ("Rispentomaten lose", "Rispentomaten"),
    ("Datteltomaten 500g", "Datteltomaten"),
    ("Paprika rot kg", "Paprika rot"),
    ("Karotten", "Karotten"),
    ("Zwiebeln gelb1.5kg", "Zwiebeln"),
    ("Lauchzwiebeln Bund", "Lauchzwiebeln"),
])
def test_one_kind_takes_the_many_names_tills_print_for_it(printed, kind):
    found = match(printed)
    assert found is not None and found.kind == kind


def test_the_same_vegetable_at_two_stores_reaches_one_kind():
    """The point of the whole module: catalogue work fixes one name at one
    shop, a vocabulary entry fixes the word everywhere."""
    assert match("Paprika rot lose").kind == match("Paprika rot kg").kind
    assert match("Gurke Stk").kind == match("Salatgurken St").kind
    assert match("Snack Gurken").kind == match("Mini Gurken 750g").kind


def test_quantity_and_packaging_are_not_identity():
    assert normalise("Rispentomaten 650g") == normalise("Rispentomaten lose")
    assert normalise("Nektarinen 1 kg") == normalise("Nektarinen 1kg")
    assert normalise("Kiwi grün Stück") == "kiwi gruen"


def test_organic_is_read_from_the_name_however_it_is_glued():
    for printed in ("Bananen Bio", "Bio-Mini Möh. 200g", "KBio Babyspinat",
                    "Limette BioFT 4Stk"):
        assert is_organic(printed), printed
    assert not is_organic("Bananen")
    assert match("Bananen Bio").product_name == "Bananen Bio"
    assert match("Bananen").product_name == "Bananen"


def test_organic_and_conventional_are_different_products():
    """Deliberate: the price gap between them is the thing worth measuring, so
    merging them would quietly corrupt any inflation figure."""
    assert match("Bananen Bio").product_name != match("Bananen").product_name


def test_a_truncated_or_qualified_name_still_finds_its_kind():
    """Tills cut names off and glue qualifiers on."""
    assert match("Johannisbeer kg").kind == "Johannisbeeren"
    assert match("Speisezwiebeln rot").kind == "Zwiebeln"
    assert match("Minze, geschnit").kind == "Minze"


def test_a_variety_is_its_own_kind_when_the_price_follows_it():
    """Rispen at about a euro a kilo and Dattel at nearly four are not one
    product: lumping them would read a change of variety as inflation, which
    is a false number rather than a missing one."""
    assert match("Rispentomaten lose").kind != match("Datteltomaten 500g").kind
    assert match("Paprika rot kg").kind != match("Paprika grün lose").kind
    assert match("Gurke Stk").kind != match("Snack Gurken").kind


def test_a_generic_name_resolves_to_the_family_it_could_be():
    """`Tomaten` on a till roll cannot say which tomato, and neither can this
    module. The shopper can, so the name resolves to all of them — the same
    shape the catalog already uses for a product line the till cannot split."""
    found = match("Tomaten")
    assert found.is_family and found.how == "family"
    assert "Rispentomaten" in found.kinds and "Datteltomaten" in found.kinds
    assert match("Gurken").kinds == ("Salatgurken", "Mini-Gurken")
    with pytest.raises(ValueError, match="family"):
        _ = found.kind


def test_a_processed_fruit_is_not_the_fruit():
    """The failure mode prefix matching invites, and the reason for the veto:
    juice is not an orange, and jam is not a cherry."""
    assert match("Orangendirektsaft") is None
    assert match("Sauerkirschkonfituere") is None
    assert match("Himbeerjoghurt 500g") is None


def test_a_name_the_vocabulary_has_never_seen_matches_nothing():
    assert match("Choviva Kekstaler") is None
    assert match("Lenor WSP Basis 71") is None
    assert match("") is None


def test_each_prefix_match_says_what_shape_it_had():
    """Three shapes, not equally safe, so the match reports which it was."""
    assert match("Trauben dunk. 500g").how == "word"
    assert match("BioBabyWasserme").how == "truncated"
    assert match("Kartoffelpuffer 6er").how == "glued"


def test_a_vegetable_glued_to_a_longer_word_is_not_sure():
    """`Kartoffel` glued to the front of a word is as often a dish as the
    vegetable. It can still be proposed for review; it is never used unasked."""
    assert match("Kartoffelpuffer 6er").kind == "Kartoffeln"
    assert resolve("Kartoffelpuffer 6er", KINDS) is None


KINDS = {
    "p-0001": {"name": "Rispentomaten", "category": "tomaten"},
    "p-0002": {"name": "Trauben", "category": "trauben"},
    "p-0003": {"name": "Kartoffeln", "category": "kartoffeln"},
    "p-0004": {"name": "Bananen Bio", "category": "bananen"},
    "p-0005": {"name": "Salatgurken", "category": "gurken"},
    "p-0006": {"name": "Mini-Gurken", "category": "gurken"},
    # Same word, not produce: a name alone must not reach it.
    "p-0007": {"name": "Zitronen", "category": "backzutaten"},
}


@pytest.mark.parametrize("printed, product_id", [
    ("Rispentomaten lose", "p-0001"),   # alias
    ("Trauben dunk. 500g", "p-0002"),   # word
    ("Kartoffeln f.k. lose", "p-0003"),  # word
    ("Bio Bananen", "p-0004"),          # organic finds the organic product
])
def test_a_sure_match_resolves_to_the_kind_the_catalog_holds(printed, product_id):
    assert resolve(printed, KINDS) == product_id


@pytest.mark.parametrize("printed, why", [
    ("Gurken", "a family is a question, not an answer"),
    ("Bananen", "the catalog holds only the organic ones"),
    ("Datteltomaten 500g", "the catalog has no such kind yet"),
    ("Zitronen Stück", "the only product with that name is not produce"),
    ("Choviva Kekstaler", "not produce at all"),
])
def test_anything_less_than_sure_resolves_to_nothing(printed, why):
    assert resolve(printed, KINDS) is None, why


def test_near_misses_are_offered_when_nothing_matched():
    """A misspelling or an unknown word still points the reviewer somewhere."""
    assert match("Tomatten") is None
    assert "Rispentomaten" in near_misses("Tomatten")
    assert near_misses("Lenor WSP Basis 71") == []


PURCHASES = {
    "contract_version": 3,
    "meta": {"receipts": 2},
    "purchases": [
        {"type": "product", "store": "Musterladen", "raw_name": "Gurke Stk",
         "resolved": False, "net_paid": 0.89},
        {"type": "product", "store": "Woanders", "raw_name": "Salatgurken St",
         "resolved": False, "net_paid": 1.19},
        {"type": "product", "store": "Musterladen", "raw_name": "Gurke Stk",
         "resolved": False, "net_paid": 0.99},
        {"type": "product", "store": "Musterladen", "raw_name": "Choviva Kekstaler",
         "resolved": False, "net_paid": 2.49},
        {"type": "product", "store": "Musterladen", "raw_name": "MU Milch 1,5%",
         "resolved": True, "net_paid": 1.09},
        {"type": "deposit", "store": "Musterladen", "raw_name": "Pfand",
         "resolved": False, "net_paid": 0.25},
    ],
}


def test_proposals_cover_unresolved_product_lines_and_nothing_else():
    rows = propose(PURCHASES)
    names = {row["raw_name"] for row in rows}

    assert names == {"Gurke Stk", "Salatgurken St", "Choviva Kekstaler"}
    assert "MU Milch 1,5%" not in names, "already resolved"
    assert "Pfand" not in names, "a deposit is not a product"


def test_a_proposal_carries_the_weight_of_the_name_and_the_best_guess():
    rows = {row["raw_name"]: row for row in propose(PURCHASES)}

    assert rows["Gurke Stk"]["lines"] == 2
    assert rows["Gurke Stk"]["spend"] == "1.88"
    assert rows["Gurke Stk"]["kind"] == "Salatgurken"
    assert rows["Gurke Stk"]["confidence"] == "alias"
    assert rows["Choviva Kekstaler"]["kind"] == "", "no guess is an honest answer"


def test_guesses_come_first_and_then_the_expensive_names():
    rows = propose(PURCHASES)
    assert [row["raw_name"] for row in rows[:2]] == ["Salatgurken St", "Gurke Stk"] or \
        [row["raw_name"] for row in rows[:2]] == ["Gurke Stk", "Salatgurken St"]
    assert rows[-1]["raw_name"] == "Choviva Kekstaler", "unguessed rows sink to the bottom"


@pytest.fixture
def catalog(tmp_path):
    products = tmp_path / "products.json"
    resolution = tmp_path / "resolution.json"
    products.write_text(json.dumps({"meta": {"next_id": 1}, "products": {}}), encoding="utf-8")
    resolution.write_text(json.dumps({"meta": {"schema": 1}, "entries": []}), encoding="utf-8")
    return products, resolution


def reviewed(tmp_path, rows):
    path = tmp_path / "reviewed.csv"
    write_proposals(rows, path)
    return path


def test_one_kind_earns_one_id_and_every_store_resolves_to_it(catalog, tmp_path):
    """The payoff. Two shops, two printed names, one product — which is what
    makes a cross-store price comparison possible at all."""
    products, resolution = catalog
    rows = [dict(row, decision="y") for row in propose(PURCHASES) if row["kind"]]
    summary = confirm(reviewed(tmp_path, rows), products, resolution)

    assert summary["products"] == 1, "Salatgurken, once"
    assert summary["entries"] == 2, "one per store that prints a name for it"

    catalog_doc = json.loads(products.read_text(encoding="utf-8"))
    (product_id, product), = catalog_doc["products"].items()
    assert product["name"] == "Salatgurken"
    assert (product["brand"], product["eans"], product["category"]) == (None, [], "gurken")

    entries = json.loads(resolution.read_text(encoding="utf-8"))["entries"]
    assert {e["store"] for e in entries} == {"Musterladen", "Woanders"}
    assert {e["product_id"] for e in entries} == {product_id}


def test_an_unmarked_row_writes_nothing(catalog, tmp_path):
    products, resolution = catalog
    summary = confirm(reviewed(tmp_path, propose(PURCHASES)), products, resolution)

    assert (summary["products"], summary["entries"]) == (0, 0)
    assert summary["undecided"] == 3
    assert json.loads(products.read_text(encoding="utf-8"))["products"] == {}


def test_a_rejected_row_writes_nothing_either(catalog, tmp_path):
    products, resolution = catalog
    rows = [dict(row, decision="n") for row in propose(PURCHASES)]
    summary = confirm(reviewed(tmp_path, rows), products, resolution)

    assert (summary["products"], summary["entries"], summary["rejected"]) == (0, 0, 3)


def test_typing_a_kind_overrides_a_wrong_guess(catalog, tmp_path):
    """The fastest correction there is: write the right answer over the guess."""
    products, resolution = catalog
    rows = [dict(row, decision="Kartoffeln") for row in propose(PURCHASES)
            if row["raw_name"] == "Gurke Stk"]
    confirm(reviewed(tmp_path, rows), products, resolution)

    (product,) = json.loads(products.read_text(encoding="utf-8"))["products"].values()
    assert product["name"] == "Kartoffeln"


def test_a_kind_the_vocabulary_lacks_is_reported_and_not_written(catalog, tmp_path):
    """A reviewer typing an unknown kind has found a vocabulary gap, not made a
    mistake — but the answer cannot be banked until the gap is closed.

    A produce product is brandless on purpose, and the only thing that tells
    that apart from a brand nobody read is its category. Minting `Pastinaken`
    with no category would write a record the store's own invariant rejects.
    So the row is reported and left in the CSV, where re-running `confirm`
    after two lines in `produce.py` banks it unchanged.
    """
    products, resolution = catalog
    rows = [dict(row, decision="Pastinaken") for row in propose(PURCHASES)
            if row["raw_name"] == "Choviva Kekstaler"]
    summary = confirm(reviewed(tmp_path, rows), products, resolution)

    assert summary["new_kinds"] == ["Pastinaken"]
    assert summary["uncategorised"] == ["Pastinaken"]
    assert (summary["products"], summary["entries"]) == (0, 0)
    assert "Pastinaken" not in VOCABULARY


def test_confirming_twice_adds_nothing_the_second_time(catalog, tmp_path):
    products, resolution = catalog
    rows = [dict(row, decision="y") for row in propose(PURCHASES) if row["kind"]]
    path = reviewed(tmp_path, rows)
    confirm(path, products, resolution)
    again = confirm(path, products, resolution)

    assert (again["products"], again["entries"]) == (0, 0)
    assert again["skipped"] == 2


def test_an_organic_row_becomes_its_own_product(catalog, tmp_path):
    products, resolution = catalog
    doc = {"purchases": [{"type": "product", "store": "Musterladen", "resolved": False,
                          "raw_name": name, "net_paid": 1.0}
                         for name in ("Bananen", "Bananen Bio")]}
    rows = [dict(row, decision="y") for row in propose(doc)]
    confirm(reviewed(tmp_path, rows), products, resolution)

    catalog_doc = json.loads(products.read_text(encoding="utf-8"))["products"]
    by_name = {p["name"]: p for p in catalog_doc.values()}
    assert set(by_name) == {"Bananen", "Bananen Bio"}
    assert by_name["Bananen Bio"]["is_organic"] is True
    assert by_name["Bananen"]["is_organic"] is False


def test_the_written_csv_is_what_confirm_reads_back(tmp_path):
    """The two halves must agree about the file, or a review is lost."""
    path = tmp_path / "p.csv"
    rows = propose(PURCHASES)
    write_proposals(rows, path)
    with path.open(encoding="utf-8", newline="") as handle:
        read_back = list(csv.DictReader(handle))
    assert [r["raw_name"] for r in read_back] == [r["raw_name"] for r in rows]
    assert read_back[0]["decision"] == ""


def test_the_cli_runs_the_whole_loop(tmp_path, monkeypatch, capsys):
    """propose writes a CSV, a human marks it, confirm writes the catalog."""
    import sys

    from grocery_app.cli import main

    purchases = tmp_path / "purchases.json"
    purchases.write_text(json.dumps(PURCHASES), encoding="utf-8")
    out = tmp_path / "produce.csv"
    products = tmp_path / "products.json"
    resolution = tmp_path / "resolution.json"
    products.write_text(json.dumps({"meta": {"next_id": 1}, "products": {}}), encoding="utf-8")
    resolution.write_text(json.dumps({"meta": {"schema": 1}, "entries": []}), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["grocery-app", "produce", "propose",
                                      "--purchases", str(purchases), "--out", str(out)])
    main()
    assert "the vocabulary has a guess for: 2 names" in capsys.readouterr().out

    with out.open(encoding="utf-8", newline="") as handle:
        rows = [dict(row, decision="y" if row["kind"] else "n")
                for row in csv.DictReader(handle)]
    write_proposals(rows, out)

    monkeypatch.setattr(sys, "argv", ["grocery-app", "produce", "confirm",
                                      "--reviewed", str(out), "--products", str(products),
                                      "--resolution", str(resolution)])
    main()
    printed = capsys.readouterr().out
    assert "new produce kinds:      1" in printed
    assert "new resolution entries: 2" in printed


def test_confirm_writes_a_family_the_shopper_can_settle(catalog, tmp_path):
    """Two kinds on one row is not a merge: each earns its own id and the name
    resolves to both, which is what makes the correction flow ask the question."""
    products, resolution = catalog
    doc = {"purchases": [{"type": "product", "store": "Musterladen", "resolved": False,
                          "raw_name": "Gurken", "net_paid": 1.77}]}
    rows = [dict(row, decision="y") for row in propose(doc)]
    assert rows[0]["kind"] == "Salatgurken | Mini-Gurken"
    summary = confirm(reviewed(tmp_path, rows), products, resolution)

    assert (summary["products"], summary["entries"], summary["families"]) == (2, 1, 1)
    (entry,) = json.loads(resolution.read_text(encoding="utf-8"))["entries"]
    assert entry["product_id"] is None
    assert len(entry["product_ids"]) == 2
    assert entry["status"] == "ambiguous_on_receipt"


def test_a_reviewer_can_narrow_a_family_to_one_kind(catalog, tmp_path):
    products, resolution = catalog
    doc = {"purchases": [{"type": "product", "store": "Musterladen", "resolved": False,
                          "raw_name": "Gurken", "net_paid": 1.77}]}
    rows = [dict(row, decision="Salatgurken") for row in propose(doc)]
    summary = confirm(reviewed(tmp_path, rows), products, resolution)

    assert (summary["products"], summary["families"]) == (1, 0)
    (entry,) = json.loads(resolution.read_text(encoding="utf-8"))["entries"]
    assert entry["product_id"] is not None and "product_ids" not in entry


def test_a_review_survives_the_vocabulary_improving():
    """Re-proposing must not throw away an afternoon of marking."""
    before = propose(PURCHASES)
    marked = [dict(row, decision="y") for row in before]
    again = propose(PURCHASES, marked)
    assert all(row["decision"] == "y" for row in again)


def test_a_decision_is_cleared_when_the_guess_it_was_made_against_changes():
    """The reviewer agreed to something that is no longer on offer, so they
    have to look at it again."""
    marked = [dict(row, decision="y",
                   kind="Something Else" if row["raw_name"] == "Gurke Stk" else row["kind"])
              for row in propose(PURCHASES)]
    again = {row["raw_name"]: row for row in propose(PURCHASES, marked)}

    assert again["Gurke Stk"]["decision"] == "", "the guess moved; look again"
    assert again["Salatgurken St"]["decision"] == "y", "that guess did not move"
    assert again["Choviva Kekstaler"]["decision"] == "y", "no guess either time, kept"


def test_every_kind_knows_what_kind_of_thing_it_is():
    """`VOCABULARY` says what a produce kind is called and `KIND_CATEGORIES`
    says what it is. A kind in one and not the other cannot be minted, so the
    two are kept level here rather than discovered by a reviewer."""
    assert set(KIND_CATEGORIES) == set(VOCABULARY)
    for kind, key in KIND_CATEGORIES.items():
        assert categories.is_produce(key), kind
