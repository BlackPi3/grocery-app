"""The drill-down (2026-10-12): from an insight to a product's purchases, to
the receipt line, to the receipt's photo. Each step shows the asker's own
receipts only; in the demo, where every guest is the owner, the photos shown
are the made-up receipts' only. All on made-up receipts (Musterladen)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from grocery_app.api.app import create_app
from grocery_app.api.images import DiskImageStore, sha256_of
from grocery_app.api.repository import PostgresRepository
from grocery_app.db.models import Receipt
from grocery_app.db.session import make_session_factory
from tests.conftest import DATABASE_URL as URL
from tests.test_accounts import add_receipt, photo
from tests.test_upload import A_PDF, RECEIPT, FakeExtractor

pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_URL not set")

OWNER = {"Authorization": "Bearer owner-secret"}


class EveryPhotoANewPaper(FakeExtractor):
    """Each photo reads as another minute at the till, so none is taken for a
    second photo of the same paper (`jobs.same_paper`)."""

    def __call__(self, path):
        self.receipt = {**RECEIPT, "time": f"11:{len(self.calls):02d}"}
        return super().__call__(path)


@pytest.fixture
def history(engine, session, data, tmp_path):
    """The fixture's two receipts as the owner's, and a server with accounts."""
    from grocery_app.db.io import import_data

    import_data(session, data / "receipts" / "truth", data / "products" / "products.json",
                data / "products" / "resolution.json", data / "absent.json",
                data / "products")
    session.commit()
    repository = PostgresRepository(make_session_factory(engine))
    sara = repository.create_user("Sara")
    client = TestClient(create_app(repository, DiskImageStore(tmp_path / "uploads"),
                                   EveryPhotoANewPaper(), token="owner-secret"))
    ids = {r.source_image: r.id for r in session.scalars(select(Receipt))}
    return client, ids, sara, {"Authorization": f"Bearer {sara['password']}"}


def test_a_products_purchases_are_its_lines_on_the_askers_receipts(history, session):
    client, ids, sara, her = history
    # Sara bought the same milk; the memory is shared, her receipts are not.
    hers = add_receipt(session, "IMG_9.jpeg", ["MU Milch 1,5%"], sara["id"])
    # The owner says the unreadable `Geheimnis` was the milk too.
    client.put(f"/v1/receipts/{ids['IMG_2.jpeg']}/lines/2/resolution", headers=OWNER,
               json={"product_id": "p-0001"})

    got = client.get("/v1/products/p-0001/purchases", headers=OWNER)
    assert got.status_code == 200
    body = got.json()
    assert (body["product"], body["brand"]) == ("Milch 1,5%", "Muster")
    assert body["category_path"] == ["Molkereiprodukte & Eier", "Milch & Joghurt", "Milch"]
    assert [(p["receipt_id"], p["position"], p["date"], p["net_paid"], p["said_by"])
            for p in body["purchases"]] == [
        (ids["IMG_1.jpeg"], 0, "2026-01-05", 1.09, "you"),
        (ids["IMG_2.jpeg"], 0, "2026-02-05", 1.19, "you"),
        (ids["IMG_2.jpeg"], 2, "2026-02-05", 0.25, "you"),
    ], "oldest first, the answered line included, nobody else's"
    assert body["purchases"][0]["unit_price"] == {"amount": 1.09, "per": "l"}
    assert body["purchases"][2]["raw_name"] == "Geheimnis"

    # Each one opens the line it names, placed as that product.
    for p in body["purchases"]:
        receipt = client.get(f"/v1/receipts/{p['receipt_id']}", headers=OWNER).json()
        assert receipt["lines"][p["position"]]["product_id"] == "p-0001"

    (only,) = client.get("/v1/products/p-0001/purchases", headers=her).json()["purchases"]
    assert (only["receipt_id"], only["position"]) == (hers, 0)
    assert client.get("/v1/products/p-0002/purchases", headers=her).json()["purchases"] == []
    assert client.get("/v1/products/p-9999/purchases", headers=OWNER).status_code == 404


def test_a_receipts_photo_is_shown_to_whoever_may_see_the_receipt_only(history):
    client, ids, _, her = history
    mine = client.post("/v1/receipts", headers=OWNER,
                       files={"file": ("a.jpg", photo("red"), "image/jpeg")}).json()
    theirs = client.post("/v1/receipts", headers=her,
                         files={"file": ("b.jpg", photo("blue"), "image/jpeg")}).json()
    pdf = client.post("/v1/receipts", headers=OWNER,
                      files={"file": ("order.pdf", A_PDF, "application/pdf")}).json()
    mine, theirs, pdf = (client.get(f"/v1/jobs/{j['job_id']}", headers=h).json()["receipt_id"]
                         for j, h in ((mine, OWNER), (theirs, her), (pdf, OWNER)))

    got = client.get(f"/v1/receipts/{mine}/photo", headers=OWNER)
    assert got.status_code == 200 and got.content == photo("red")
    assert got.headers["content-type"] == "image/jpeg"
    got = client.get(f"/v1/receipts/{pdf}/photo", headers=OWNER)
    assert got.content == A_PDF and got.headers["content-type"] == "application/pdf"
    assert client.get(f"/v1/receipts/{theirs}/photo", headers=her).content == photo("blue")

    # Another person's receipt has no photo, as it has no lines, for either of them.
    assert client.get(f"/v1/receipts/{theirs}/photo", headers=OWNER).status_code == 404
    assert client.get(f"/v1/receipts/{mine}/photo", headers=her).status_code == 404
    assert client.get(f"/v1/receipts/{mine}/photo").status_code == 401
    # A receipt typed in on the laptop was never a photo here.
    typed = ids["IMG_1.jpeg"]
    assert client.get(f"/v1/receipts/{typed}/photo", headers=OWNER).status_code == 404

    listed = {r["receipt_id"]: r["photo"]
              for r in client.get("/v1/receipts", headers=OWNER).json()}
    assert listed == {mine: True, pdf: True, typed: False, ids["IMG_2.jpeg"]: False}


def test_the_demo_shows_its_made_up_receipts_photos_and_no_guests(
        engine, session, tmp_path, monkeypatch):
    """Every guest is the owner in the demo, so the receipt list is shared;
    a photo a guest sent must still stay theirs. Only the photos the seed's
    receipts were read from are shown (`demo.seeded_photos`)."""
    from grocery_app import demo

    seeded = photo("green")
    seed = tmp_path / "seed.sql"
    seed.write_text("INSERT INTO public.jobs VALUES ('x', 'done', "
                    f"'{sha256_of(photo('blue'))}');\n"
                    f"INSERT INTO public.receipts VALUES (1, '{sha256_of(seeded)}', 'made-up', "
                    f"'Musterladen', NULL, '{sha256_of(seeded)}', NULL);\n")
    monkeypatch.setattr(demo, "SEED", seed)
    client = TestClient(create_app(PostgresRepository(make_session_factory(engine)),
                                   DiskImageStore(tmp_path / "uploads"), EveryPhotoANewPaper(),
                                   demo=True))
    receipts = {}
    for name, image in (("seeded", seeded), ("guest", photo("blue"))):
        job = client.post("/v1/receipts", files={"file": (name, image, "image/jpeg")}).json()
        receipts[name] = client.get(f"/v1/jobs/{job['job_id']}").json()["receipt_id"]

    assert client.get(f"/v1/receipts/{receipts['seeded']}/photo").content == seeded
    assert client.get(f"/v1/receipts/{receipts['guest']}/photo").status_code == 403
    listed = {r["receipt_id"]: r["photo"] for r in client.get("/v1/receipts").json()}
    assert listed == {receipts["seeded"]: True, receipts["guest"]: False}
