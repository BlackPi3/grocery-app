"""What a chain's download writes to the database, on made-up products.

The owner, 2026-11-08: a new download records only what changed, so the table
grows with changes, not with downloads, and a failed page never makes a shelf
look discontinued.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from grocery_app.chain_products import OlderDownload, load_download, seen_on_of
from grocery_app.db.models import ChainPrice, ChainProduct
from tests.conftest import DATABASE_URL as URL

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")

MON = date(2026, 3, 2)
TUE = date(2026, 3, 3)
WED = date(2026, 3, 4)


def row(article="1", name="Vanille Pudding", price=1.49, **extra):
    return {"article_number": article, "name": name, "brand": "Muster", "ean": None,
            "pack_size": "500 g", "category": "desserts", "url": f"https://muster.example/{article}",
            "price": price, "fetched_at": "2026-03-02T10:00:00Z", **extra}


def rows(*listings):
    return {listing["article_number"]: listing for listing in listings}


def product(session, article="1", chain="musterladen"):
    session.expire_all()
    return session.scalars(select(ChainProduct).where(
        ChainProduct.chain == chain, ChainProduct.article_number == article)).one()


def prices(session, article="1"):
    return [(p.seen_on, p.price) for p in session.scalars(
        select(ChainPrice).where(ChainPrice.chain_product_id == product(session, article).id)
        .order_by(ChainPrice.seen_on))]


def five():
    return [row(str(i)) for i in range(1, 6)]


def test_a_new_product_gets_a_row_and_its_first_price(session):
    counts = load_download(session, "Musterladen", rows(row()), MON)
    found = product(session)
    assert (counts["new"], found.name, found.first_seen, found.last_seen, found.gone_since) == (
        1, "Vanille Pudding", MON, MON, None)
    assert prices(session) == [(MON, Decimal("1.49"))]


def test_the_chain_is_kept_as_one_spelling(session):
    load_download(session, "MUSTERLADEN ", rows(row()), MON)
    assert product(session).chain == "musterladen"


def test_an_unchanged_product_writes_only_the_day_it_was_seen(session):
    load_download(session, "Musterladen", rows(row()), MON)
    counts = load_download(session, "Musterladen", rows(row()), TUE)
    assert counts == {"new": 0, "prices": 0, "changed": 0, "gone": 0, "back": 0, "unchanged": 1}
    assert product(session).last_seen == TUE
    assert prices(session) == [(MON, Decimal("1.49"))], "no price row for an unchanged price"


def test_a_changed_price_is_a_dated_entry_and_the_old_one_stays(session):
    load_download(session, "Musterladen", rows(row()), MON)
    counts = load_download(session, "Musterladen", rows(row(price=1.69)), TUE)
    assert counts["prices"] == 1
    assert prices(session) == [(MON, Decimal("1.49")), (TUE, Decimal("1.69"))]


def test_a_price_that_goes_back_is_recorded_again(session):
    load_download(session, "Musterladen", rows(row()), MON)
    load_download(session, "Musterladen", rows(row(price=1.69)), TUE)
    load_download(session, "Musterladen", rows(row()), WED)
    assert [p for _, p in prices(session)] == [
        Decimal("1.49"), Decimal("1.69"), Decimal("1.49")]


def test_a_changed_name_is_updated(session):
    load_download(session, "Musterladen", rows(row()), MON)
    counts = load_download(session, "Musterladen", rows(row(name="Pudding Vanille")), TUE)
    assert (counts["changed"], product(session).name) == (1, "Pudding Vanille")
    assert product(session).first_seen == MON


def test_a_listing_without_a_price_gets_a_row_and_no_price(session):
    load_download(session, "Musterladen", rows(row(price=None)), MON)
    assert prices(session) == []


def test_loading_the_same_download_twice_changes_nothing(session):
    load_download(session, "Musterladen", rows(row()), MON)
    counts = load_download(session, "Musterladen", rows(row()), MON)
    assert counts["unchanged"] == 1
    assert session.scalar(select(func.count()).select_from(ChainPrice)) == 1


def test_what_chains_do_not_share_is_kept_apart(session):
    load_download(session, "Musterladen", rows(row(unit_price="2,98 €/1 kg")), MON)
    assert product(session).extra == {"unit_price": "2,98 €/1 kg"}


def test_chains_may_use_the_same_article_number(session):
    load_download(session, "Musterladen", rows(row(name="Erstens")), MON)
    load_download(session, "Beispielmarkt", rows(row(name="Zweitens")), MON)
    assert product(session).name == "Erstens"
    assert product(session, chain="beispielmarkt").name == "Zweitens"


def test_a_listing_with_no_name_is_skipped(session):
    assert load_download(session, "Musterladen", rows(row(name="")), MON)["skipped"] == 1
    assert session.scalar(select(func.count()).select_from(ChainProduct)) == 0


def test_a_partial_download_never_marks_a_product_gone(session):
    load_download(session, "Musterladen", rows(*five()), MON)
    counts = load_download(session, "Musterladen", rows(*five()[:4]), TUE)
    assert counts["gone"] == 0
    assert product(session, "5").gone_since is None
    assert product(session, "5").last_seen == MON, "not seen in this one"


def test_a_complete_download_marks_what_it_lacks_gone(session):
    load_download(session, "Musterladen", rows(*five()), MON)
    counts = load_download(session, "Musterladen", rows(*five()[:4]), TUE, complete=True)
    assert counts["gone"] == 1
    assert product(session, "5").gone_since == TUE
    assert product(session, "4").gone_since is None


def test_a_gone_product_is_never_deleted_and_comes_back(session):
    load_download(session, "Musterladen", rows(*five()), MON)
    load_download(session, "Musterladen", rows(*five()[:4]), TUE, complete=True)
    counts = load_download(session, "Musterladen", rows(*five()), WED, complete=True)
    assert counts["back"] == 1
    assert (product(session, "5").gone_since, product(session, "5").last_seen) == (None, WED)
    assert session.scalar(select(func.count()).select_from(ChainProduct)) == 5


def test_too_much_missing_at_once_marks_nothing_and_fires_the_trap(session, caplog):
    load_download(session, "Musterladen", rows(*five()), MON)
    counts = load_download(session, "Musterladen", rows(*five()[:3]), TUE, complete=True)
    assert (counts["gone"], counts["refused_gone"]) == (0, 2)
    assert product(session, "5").gone_since is None
    assert "GROCERY_TRAP chain-download-shrank chain=musterladen missing=2 held=5" in caplog.text


def test_the_trap_names_no_product(session, caplog):
    load_download(session, "Musterladen", rows(*five()), MON)
    load_download(session, "Musterladen", rows(*five()[:3]), TUE, complete=True)
    assert "Vanille" not in caplog.text


def test_an_older_download_is_refused(session):
    load_download(session, "Musterladen", rows(row()), TUE)
    with pytest.raises(OlderDownload):
        load_download(session, "Musterladen", rows(row(price=9.99)), MON)


def test_the_day_of_a_download_is_its_newest_row():
    listings = [row(fetched_at="2026-03-01T23:00:00Z"), row(fetched_at="2026-03-02T01:00:00Z")]
    assert seen_on_of(listings) == date(2026, 3, 2)
    assert seen_on_of([{"name": "x"}]) is None
