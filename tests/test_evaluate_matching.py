"""Tests for the matching score.

Like the extraction harness, a bug here is worse than a bug in the matcher: it
would report the wrong answer confidently. These tests pin what each outcome
means. Every name is invented (Musterladen).
"""

from __future__ import annotations

import json
import sys

from grocery_app.cli import main
from grocery_app.evaluate_matching import (
    article_index,
    evaluate_matching,
    format_matching_report,
    judge,
)


def product(name: str, eans: list[str] | None = None) -> dict:
    return {"name": name, "brand": "Muster", "category": "milch", "eans": eans or []}


PRODUCTS = {
    "p-0001": product("Milch 1,5%"),
    "p-0002": product("Milch 3,5%"),
    "p-0003": product("Kekse", eans=["4000000000003"]),
}

# (store key, printed name) -> product ids, the shape `load_resolution` returns.
RESOLUTION = {
    ("musterladen", "MU Milch 1,5%"): ["p-0001"],
    ("musterladen", "MU Milch"): ["p-0001", "p-0002"],
    ("musterladen", "MU Kakao"): ["p-0002"],
}


def line(name: str, net: float = 1.0) -> dict:
    return {"type": "product", "raw_name": name, "qty": 1, "gross": net,
            "discount": 0.0, "net": net, "tax_class": "A"}


READING = {
    "source_image": "IMG_1.jpeg", "store": "Musterladen", "date": "2026-01-05",
    "lines": [line("MU Milch 1,5%", 1.09), line("MU Milch", 1.19), line("MU Kakao", 2.0),
              line("MU Kekse", 1.5), line("Geheimnis", 3.0), line("Etwas Neues", 4.0),
              {"type": "deposit", "raw_name": "Pfand", "qty": 1, "gross": 0.25,
               "discount": 0.0, "net": 0.25, "tax_class": "B"}],
}


def truth(position: int, name: str, catalog_ids=(), article=None, product="x") -> dict:
    return {"source_image": "IMG_1.jpeg", "position": position, "store": "Musterladen",
            "date": "2026-01-05", "raw_name": name, "product": product,
            "article": article, "catalog_ids": list(catalog_ids), "known": "exact",
            "how": "confirmed", "note": None}


TRUTH = {"meta": {}, "lines": [
    truth(0, "MU Milch 1,5%", ["p-0001"]),       # right
    truth(1, "MU Milch", ["p-0002"]),            # right: a family that holds the answer
    truth(2, "MU Kakao", ["p-0001"]),            # wrong: answered another product
    truth(3, "MU Kekse", article="4000000000003"),  # missed: in the catalog by barcode
    truth(4, "Geheimnis", product="Kashk"),      # new: words only, not in the catalog
    truth(5, "Etwas Neues", article="999"),      # new: the shop lists it, we do not
]}


def score():
    return evaluate_matching(TRUTH, {"IMG_1.jpeg": READING}, RESOLUTION, PRODUCTS,
                             index=article_index(PRODUCTS, None))


def test_each_line_gets_the_outcome_its_answer_deserves():
    outcomes = [line["outcome"] for line in score()["lines"]]
    assert outcomes == ["right", "right", "wrong", "missed", "new", "new"]


def test_a_barcode_on_the_product_links_the_shops_number_to_the_catalog():
    assert article_index(PRODUCTS, None) == {"4000000000003": "p-0003"}


def test_a_banked_listing_links_the_shops_number_too(tmp_path):
    (tmp_path / "musterladen").mkdir()
    (tmp_path / "musterladen" / "listings.json").write_text(json.dumps(
        {"listings": {"123": {"product_id": "p-0002", "prices": []}}}), encoding="utf-8")
    assert article_index(PRODUCTS, tmp_path)["123"] == "p-0002"


def test_an_answer_the_key_can_only_describe_in_words_is_unchecked_not_wrong():
    record = {"resolution": "exact", "product_id": "p-0001"}
    assert judge(record, truth(4, "Geheimnis", product="Kashk"), {}) == "unchecked"


def test_a_produce_answer_is_scored_like_any_other_answer():
    record = {"resolution": "produce", "product_id": "p-0001", "candidate_ids": []}
    assert judge(record, truth(0, "Bananen lose", ["p-0001"]), {}) == "right"
    assert judge(record, truth(0, "Bananen lose", ["p-0002"]), {}) == "wrong"


def test_a_line_left_open_is_missed_only_when_the_catalog_had_it():
    open_line = {"resolution": "none", "product_id": None}
    assert judge(open_line, truth(0, "x", ["p-0001"]), {}) == "missed"
    assert judge(open_line, truth(0, "x"), {}) == "new"


def test_totals_count_lines_and_money_and_skip_deposits():
    totals = score()["totals"]
    assert totals["lines"] == 6, "the Pfand line is not a product and is not in the key"
    assert totals["count"] == {"right": 2, "wrong": 1, "unchecked": 0, "missed": 1, "new": 2}
    assert totals["euros"]["new"] == 7.0
    assert totals["total_euros"] == 12.78


def test_shopper_answers_for_these_lines_are_never_used():
    """The matcher is scored as it would run on an unseen receipt.

    `evaluate_matching` takes no line answers at all, so `Geheimnis` stays
    open here even though a shopper could place it. This pins that the
    signature keeps it that way.
    """
    geheimnis = score()["lines"][4]
    assert geheimnis["resolution"] == "none"


def test_a_key_line_that_no_longer_matches_the_reading_is_stale_not_scored():
    moved = {"meta": {}, "lines": [truth(0, "MU Milch 3,5%", ["p-0002"])]}
    report = evaluate_matching(moved, {"IMG_1.jpeg": READING}, RESOLUTION, PRODUCTS)
    assert report["lines"] == []
    assert len(report["stale"]) == 1

    missing = evaluate_matching(TRUTH, {}, RESOLUTION, PRODUCTS)
    assert missing["totals"]["lines"] == 0 and len(missing["stale"]) == 6


def test_the_report_names_what_went_wrong():
    text = format_matching_report(score())
    assert "right   2" in text
    assert "MU Kakao" in text.split("Wrong:")[1]
    assert "MU Kekse" in text.split("Missed:")[1]
    assert "answered by: exact 2  family 1" in text


def test_the_cli_scores_the_files_on_disk(tmp_path, monkeypatch, capsys):
    readings = tmp_path / "extracted"
    readings.mkdir()
    (readings / "IMG_1.json").write_text(json.dumps(READING), encoding="utf-8")
    (tmp_path / "truth.json").write_text(json.dumps(TRUTH), encoding="utf-8")
    (tmp_path / "products.json").write_text(json.dumps({"products": PRODUCTS}),
                                            encoding="utf-8")
    (tmp_path / "resolution.json").write_text(json.dumps({"entries": [
        {"store": s, "raw_name": n, "line_type": "product",
         "product_id": ids[0] if len(ids) == 1 else None,
         **({"product_ids": ids} if len(ids) > 1 else {})}
        for (s, n), ids in RESOLUTION.items()]}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "grocery-app", "eval-matching", "--truth", str(tmp_path / "truth.json"),
        "--readings", str(readings), "--products", str(tmp_path / "products.json"),
        "--resolution", str(tmp_path / "resolution.json"),
        "--products-dir", str(tmp_path / "none"), "--json"])
    main()
    report = json.loads(capsys.readouterr().out)
    assert report["totals"]["count"]["right"] == 2
