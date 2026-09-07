"""Tests for the extraction evaluation harness.

The harness is what tells us whether a parser change helped, so a bug here is
worse than a bug in the parser: it would report the wrong answer confidently.
These tests pin the behaviours the accuracy numbers depend on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from grocery_app.evaluate import evaluate, match_lines, score_receipt


def line(name: str, net: float, qty: int = 1, tax: str | None = "A") -> dict:
    return {"type": "product", "raw_name": name, "qty": qty, "net": net, "tax_class": tax}


def receipt(image: str = "IMG_1.jpeg", store: str = "Lidl", lines: list | None = None) -> dict:
    return {
        "source_image": image,
        "store": store,
        "date": "2026-06-26",
        "printed_total": 3.0,
        "lines": lines if lines is not None else [line("Gurken", 1.0), line("Porree", 2.0)],
    }


def write(directory: Path, *receipts: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for data in receipts:
        (directory / f"{data['source_image'].split('.')[0]}.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
    return directory


def test_identical_input_scores_perfectly():
    result = score_receipt(receipt(), receipt())
    assert result["exact"] is True
    assert result["errors"] == []
    assert result["missed"] == result["spurious"] == 0


def test_price_misread_is_reported_but_line_still_matches():
    truth = receipt()
    pred = receipt(lines=[line("Gurken", 1.0), line("Porree", 2.5)])
    result = score_receipt(truth, pred)

    assert result["exact"] is False
    assert result["matched"] == 2, "a wrong price must not turn into a missed line"
    assert result["fields"]["net"] == [1, 2]
    assert any("net" in error for error in result["errors"])


def test_dropped_line_is_missed_not_a_cascade():
    """A dropped line must not misalign every line after it."""
    truth = receipt(lines=[line("A", 1.0), line("B", 2.0), line("C", 3.0)])
    pred = receipt(lines=[line("A", 1.0), line("C", 3.0)])
    result = score_receipt(truth, pred)

    assert result["missed"] == 1
    assert result["spurious"] == 0
    assert result["matched"] == 2
    assert result["fields"]["net"] == [2, 2], "surviving lines must still score correct"


def test_invented_line_is_spurious():
    """The Sofortstorno failure mode: transcribing items that were reversed."""
    truth = receipt(lines=[line("A", 1.0)])
    pred = receipt(lines=[line("A", 1.0), line("Coca-Cola 1.25Lx6", 5.94)])
    result = score_receipt(truth, pred)

    assert result["spurious"] == 1
    assert result["missed"] == 0
    assert any("spurious" in error for error in result["errors"])


def test_repaired_umlaut_counts_as_wrong():
    """Globus prints '?' for umlauts; 'fixing' it is a misread, not an improvement."""
    truth = receipt(lines=[line("SAATENBR?TCHEN 3+1", 1.65)])
    pred = receipt(lines=[line("SAATENBRÖTCHEN 3+1", 1.65)])
    result = score_receipt(truth, pred)

    assert result["exact"] is False
    assert result["fields"]["raw_name"] == [0, 1]


def test_guessed_tax_class_counts_as_wrong():
    truth = receipt(lines=[line("Pamir", 14.95, tax=None)])
    pred = receipt(lines=[line("Pamir", 14.95, tax="7%")])
    assert score_receipt(truth, pred)["fields"]["tax_class"] == [0, 1]


def test_store_name_case_does_not_count_as_an_error():
    truth = receipt(store="ALDI SÜD")
    pred = receipt(store="Aldi Süd")
    result = score_receipt(truth, pred)
    assert result["header"]["store"] is True
    assert result["exact"] is True


def test_missing_prediction_scores_zero_not_crash():
    result = score_receipt(receipt(), None)
    assert result["produced"] is False
    assert result["missed"] == 2
    assert result["exact"] is False


def test_duplicate_names_pair_with_their_own_price_first():
    """Receipts repeat items (three 'Pfand' lines). Exact pairs must win."""
    truth = [line("Pfand", 0.25), line("Pfand", 0.25), line("Pfand", 0.15)]
    pred = [line("Pfand", 0.15), line("Pfand", 0.25), line("Pfand", 0.25)]
    pairs, missed, spurious = match_lines(truth, pred)

    assert not missed and not spurious
    assert all(t["net"] == p["net"] for t, p in pairs)


def test_stores_are_grouped_case_insensitively(tmp_path):
    truth = write(
        tmp_path / "truth",
        receipt("IMG_1.jpeg", store="ALDI SÜD"),
        receipt("IMG_2.jpeg", store="Aldi Süd"),
    )
    report = evaluate(truth, truth)

    assert len(report["by_store"]) == 1, "one chain must not split into two rows"
    assert report["store_name_variants"], "the inconsistency should still be surfaced"


def test_excluded_store_leaves_the_totals(tmp_path):
    truth = write(
        tmp_path / "truth",
        receipt("IMG_1.jpeg", store="Lidl"),
        receipt("IMG_2.jpeg", store="SVG Autohof"),
    )
    report = evaluate(truth, truth, exclude_stores=("SVG Autohof",))

    assert report["totals"]["receipts"] == 1
    assert "SVG Autohof" not in report["by_store"]
    assert len(report["results"]) == 2, "excluded receipts are still scored, just not totalled"
