"""The pipeline end to end on made-up data: receipts -> purchases.json -> insights.json.

The unit tests pin each stage; this one pins the seams between them and the
CLI that developers actually run, so a change to one stage that silently
breaks the next cannot merge. Every file here is invented (Musterladen).
"""

import json
import sys

from grocery_app.cli import main
from grocery_app.insights import build_insights
from grocery_app.normalizer import build_purchases


def test_receipts_become_purchases_become_insights(data):
    purchases = build_purchases(data / "receipts" / "truth",
                                data / "products" / "products.json",
                                data / "products" / "resolution.json",
                                None, data / "products")
    assert purchases["contract_version"] == 6
    assert purchases["meta"]["receipts"] == 2
    assert purchases["meta"]["product_lines"] == 5
    assert purchases["meta"]["unresolved_items"] == ["Geheimnis"]
    milk = [p for p in purchases["purchases"] if p["product_id"] == "p-0001"]
    assert [p["resolution"] for p in milk] == ["exact", "exact"], \
        "store spelled two ways still resolves"
    assert [p["said_by"] for p in milk] == ["you", "you"], \
        "the fixture's memory entries were confirmed by a person"
    assert milk[0]["unit_price"] == {"amount": 1.09, "per": "l"}
    assert milk[0]["sold_as"] == {"form": "pack",
                                  "size": {"count": 1, "value": 1.0, "unit": "l"}}
    # The catalog stores the vocabulary key and nothing else; the three labels
    # a reader sees are derived here, once, on the way into the contract.
    assert milk[0]["category"] == "milch"
    assert milk[0]["category_path"] == ["Molkereiprodukte & Eier",
                                        "Milch & Joghurt", "Milch"]
    unresolved = next(p for p in purchases["purchases"] if not p["product_id"])
    assert "category_path" not in unresolved, \
        "a line with no product gains no attributes, this one included"

    insights = build_insights(purchases)
    assert insights["contract_version"] == 4
    assert insights["as_of"] == "2026-02-05"
    assert insights["coverage"]["resolved_lines"] == 4
    (change,) = [c for c in insights["price_changes"] if c["product_id"] == "p-0001"]
    assert change["change_pct"] == 9.2
    assert [r["product_id"] for r in insights["repurchase"]] == ["p-0001", "p-0002"]
    assert insights["basket_index"]["series"][0]["index"] is None, \
        "two overlapping products is too thin for an index, and it says so"
    (label,) = insights["budget_brand"]["by_store"]
    assert label.casefold() == "musterladen", "two spellings, one store"
    assert insights["budget_brand"]["by_store"][label] == insights["budget_brand"]["overall"]
    assert insights["cross_store"]["products"] == []


def test_the_cli_runs_the_same_path(data, monkeypatch, capsys):
    out_purchases = data / "purchases.json"
    out_insights = data / "insights.json"
    monkeypatch.setattr(sys, "argv", [
        "grocery-app", "purchases",
        "--receipts-dir", str(data / "receipts" / "truth"),
        "--products", str(data / "products" / "products.json"),
        "--resolution", str(data / "products" / "resolution.json"),
        "--line-resolutions", str(data / "absent.json"),
        "--products-dir", str(data / "products"),
        "--output", str(out_purchases),
    ])
    main()
    assert "UNRESOLVED:     ['Geheimnis']" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", [
        "grocery-app", "insights", "--purchases", str(out_purchases),
        "--output", str(out_insights),
    ])
    main()
    printed = capsys.readouterr().out
    assert "repurchase:     2 products bought more than once" in printed
    written = json.loads(out_insights.read_text(encoding="utf-8"))
    assert set(written) == {"contract_version", "as_of", "coverage", "repurchase",
                            "price_changes", "basket_index", "budget_brand", "cross_store"}


def test_the_server_serves_what_the_normalizer_built(data):
    """The seam between the pipeline and the HTTP layer.

    The schema is strict, so a field added to `normalize_line` without a
    matching line in `api/schemas.py` fails here, not on a client.
    """
    from fastapi.testclient import TestClient

    from grocery_app.api.app import create_app
    from grocery_app.api.repository import InMemoryRepository
    from grocery_app.api.schemas import PurchasesDocument

    purchases = build_purchases(data / "receipts" / "truth",
                                data / "products" / "products.json",
                                data / "products" / "resolution.json",
                                None, data / "products")
    PurchasesDocument.model_validate(purchases)

    client = TestClient(create_app(InMemoryRepository(purchases)))
    # The whole document, not a summary of it: comparing only `meta` and the
    # names let the server add null attributes to unresolved lines unnoticed.
    assert client.get("/v1/purchases").json() == purchases
    assert client.get("/v1/insights").json() == build_insights(purchases)


def test_budget_brand_is_derived_at_the_seam_and_not_stored_in_the_catalog(data):
    """The catalog holds no own-brand answer; purchases.json holds one per line.

    This is the seam the change is about. Products are permanent and shared
    across shops, so a value frozen onto one could only ever be right in the
    shop it was minted in. Deriving it as purchases are built means a correction
    to the brand tables reaches every line ever written, with no migration.
    """
    catalog = json.loads((data / "products" / "products.json").read_text())["products"]
    assert catalog, "fixture has products"
    for product_id, product in catalog.items():
        assert "is_budget_brand" not in product, \
            f"{product_id}: the catalog must not freeze a per-shop fact onto a product"

    purchases = build_purchases(data / "receipts" / "truth",
                                data / "products" / "products.json",
                                data / "products" / "resolution.json",
                                None, data / "products")
    resolved = [p for p in purchases["purchases"] if p.get("product_id")]
    assert resolved, "fixture resolves something"
    assert all("is_budget_brand" in p for p in resolved), \
        "every resolved line answers the question the catalog no longer stores"
    # A line nothing could place invents nothing, this field included.
    for line in purchases["purchases"]:
        if line["type"] == "product" and not line.get("product_id"):
            assert "is_budget_brand" not in line


def test_the_matching_score_reads_what_the_normalizer_reads_but_not_the_answers(data):
    """The score runs the normalizer on the same files, minus the shopper's answers.

    `Geheimnis` on IMG_2 has an answer in `line_resolutions.json`, so
    purchases.json places it. The score must not: a line the shopper answered
    is exactly the line the matcher is being tested on.
    """
    from grocery_app.evaluate_matching import article_index, evaluate_matching, load_readings
    from grocery_app.normalizer import load_products, load_resolution

    products = load_products(data / "products" / "products.json")
    key = {"meta": {}, "lines": [
        {"source_image": "IMG_2.jpeg", "position": 0, "store": "musterladen",
         "raw_name": "MU Milch 1,5%", "product": "Muster Milch", "article": "4000000000001",
         "catalog_ids": [], "known": "exact"},
        {"source_image": "IMG_2.jpeg", "position": 2, "store": "musterladen",
         "raw_name": "Geheimnis", "product": "Muster Milch", "article": None,
         "catalog_ids": ["p-0001"], "known": "exact"},
    ]}
    report = evaluate_matching(
        key, load_readings(data / "receipts" / "truth", {"IMG_2.jpeg"}),
        load_resolution(data / "products" / "resolution.json"), products,
        index=article_index(products, data / "products"))
    assert [line["outcome"] for line in report["lines"]] == ["right", "missed"], \
        "the listing links the shop's number to p-0001; the answer file is not read"


def test_produce_known_at_one_store_resolves_at_another_through_the_seam(data):
    """A second shop prints its own name for the same bananas. The memory has
    nothing there; the vocabulary answers, and the answer survives the trip
    through purchases.json and the server's strict schema, labelled as the
    vocabulary's so a reader can tell it from a remembered one."""
    from grocery_app.api.schemas import PurchasesDocument

    elsewhere = {
        "source_image": "IMG_3.jpeg", "transcribed_by": "hand", "store": "Woanders",
        "date": "2026-02-10", "time": "10:00", "currency": "EUR", "printed_total": 1.49,
        "lines": [{"type": "product", "raw_name": "Bananen lose", "qty": 1,
                   "gross": 1.49, "discount": 0.0, "net": 1.49, "tax_class": "A"}],
    }
    (data / "receipts" / "truth" / "IMG_3.json").write_text(json.dumps(elsewhere),
                                                            encoding="utf-8")
    purchases = build_purchases(data / "receipts" / "truth",
                                data / "products" / "products.json",
                                data / "products" / "resolution.json",
                                None, data / "products")
    PurchasesDocument.model_validate(purchases)
    (banana,) = [p for p in purchases["purchases"] if p["store"] == "Woanders"]
    assert (banana["resolution"], banana["product_id"]) == ("produce", "p-0002")
    assert "Bananen lose" not in purchases["meta"]["unresolved_items"]


def test_a_line_that_is_not_a_grocery_stays_in_the_history_and_out_of_the_insights(data):
    """The category decides it, and the category is set on the product, so the
    exclusion has to survive two seams: catalog -> purchases.json, where the
    line keeps its money and its category, and purchases.json -> insights,
    where it counts under `not_grocery` and nowhere else."""
    products = json.loads((data / "products" / "products.json").read_text())
    products["products"]["p-0003"] = {
        "label": "fruehstueck", "name": "Frühstück", "brand": None, "product_line": None,
        "variant": None, "size": None, "category": "cafe-imbiss", "is_organic": False,
        "eans": [], "open_questions": [], "provenance": {"attributes": "test", "source": "test"}}
    (data / "products" / "products.json").write_text(json.dumps(products), encoding="utf-8")
    resolution = json.loads((data / "products" / "resolution.json").read_text())
    resolution["entries"].append(
        {"store": "Musterladen", "raw_name": "Fruehstueck", "line_type": "product",
         "product_id": "p-0003", "confirmed_by": "test", "confirmed_at": "2026-01-01",
         "source": "test"})
    (data / "products" / "resolution.json").write_text(json.dumps(resolution), encoding="utf-8")
    cafe = {"source_image": "IMG_4.jpeg", "transcribed_by": "hand", "store": "Musterladen",
            "date": "2026-02-07", "time": "09:00", "currency": "EUR", "printed_total": 7.5,
            "lines": [{"type": "product", "raw_name": "Fruehstueck", "qty": 1,
                       "gross": 7.5, "discount": 0.0, "net": 7.5, "tax_class": "B"}]}
    (data / "receipts" / "truth" / "IMG_4.json").write_text(json.dumps(cafe), encoding="utf-8")

    purchases = build_purchases(data / "receipts" / "truth",
                                data / "products" / "products.json",
                                data / "products" / "resolution.json",
                                None, data / "products")
    (line,) = [p for p in purchases["purchases"] if p["source_image"] == "IMG_4.jpeg"]
    assert (line["product_id"], line["category"], line["net_paid"]) == \
        ("p-0003", "cafe-imbiss", 7.5), "the history keeps it"

    insights = build_insights(purchases)
    assert insights["as_of"] == "2026-02-07", "the last receipt is still the last receipt"
    assert insights["coverage"]["not_grocery"] == {
        "lines": 1, "spend": 7.5, "by_category": {"Café & Imbiss": 7.5}}
    assert insights["coverage"]["product_lines"] == 5, "the five grocery lines only"
    assert "p-0003" not in json.dumps({k: v for k, v in insights.items() if k != "coverage"})

    from fastapi.testclient import TestClient

    from grocery_app.api.app import create_app
    from grocery_app.api.repository import InMemoryRepository

    client = TestClient(create_app(InMemoryRepository(purchases)))
    assert client.get("/v1/insights").json() == insights


def test_a_readings_first_guesses_stay_out_of_the_receipt_and_the_history():
    """The seam between reading a photo and storing it as a receipt.

    The reading carries a plain name and a category per line (prompt v3), for
    the phone to show while the lines are placed. The receipt that is stored
    and normalized must not carry them: the import refuses keys it has no
    column for, and the normalizer must not see a guess as an answer.
    """
    import json as json_

    from grocery_app.api.jobs import DERIVED_KEYS
    from grocery_app.db.io import receipt_from_dict, receipt_to_dict
    from grocery_app.extract import parse_model_output
    from grocery_app.normalizer import normalize_receipt

    text = json_.dumps({
        "store": "Musterladen", "store_location": "Musterstadt", "date": "2026-03-05",
        "time": "10:00", "currency": "EUR", "printed_total": 3.0, "printed_savings": None,
        "tax_buckets": None,
        "lines": [{"type": "product", "raw_name": "MU BLUETENHONIG", "qty": 1,
                   "sold_by_weight": False, "weight_kg": None, "unit_price": None,
                   "unit_price_basis": None, "unit_gross": None, "gross": 3.0,
                   "discount": 0.0, "net": 3.0, "tax_class": "A",
                   "guess_name": "Blütenhonig", "guess_category": "honig"}],
    })
    reading = parse_model_output(text, "IMG_1.jpeg")
    assert reading["first_guesses"] == [{"name": "Blütenhonig", "category": "honig"}]

    stored = receipt_to_dict(receipt_from_dict(
        {k: v for k, v in reading.items() if k not in DERIVED_KEYS}))
    assert "first_guesses" not in stored
    (record,) = normalize_receipt(stored, {}, {})
    assert record["resolution"] == "none" and record.get("category_path") is None
