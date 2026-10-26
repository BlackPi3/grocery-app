"""What a person's history counts beside groceries (owner, 2026-10-26): only
groceries by default; the kinds close to groceries (alcohol, supplements,
household, ...) when the person switches them on, each person their own."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from grocery_app.api.app import create_app
from grocery_app.api.repository import InMemoryRepository
from tests.conftest import DATABASE_URL

db = pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set")
OWNER = {"Authorization": "Bearer owner-secret"}


def line(pid, day, net, category):
    return {"date": day, "store": "Musterladen", "source_image": day, "type": "product",
            "raw_name": pid, "product_id": pid, "resolved": True, "resolution": "exact",
            "qty": 1.0, "gross": net, "discount": 0.0, "net_paid": net, "product": pid,
            "category": category}


DOC = {"meta": {}, "purchases": [line("p-wine", "2026-09-03", 6.0, "rotwein"),
                                 line("p-milk", "2026-09-03", 1.0, "milch")]}


class Counting(InMemoryRepository):
    def __init__(self, doc, kinds):
        super().__init__(doc)
        self.kinds = frozenset(kinds)

    def counted_kinds(self):
        return self.kinds


def test_the_insights_count_the_kinds_the_person_counts():
    plain = TestClient(create_app(Counting(DOC, []))).get("/v1/insights").json()
    assert plain["months"][0]["spend"] == 1.0, "wine is not groceries"
    counted = TestClient(create_app(Counting(DOC, ["vices"]))).get("/v1/insights").json()
    assert counted["months"][0]["spend"] == 7.0


def test_the_choices_are_read_without_a_database_but_not_written():
    client = TestClient(create_app(InMemoryRepository(DOC)))
    answer = client.get("/v1/counted").json()
    assert answer["kinds"] == [] and answer["choices"]["vices"] == "Alcohol & tobacco"
    assert client.put("/v1/counted", json={"kinds": ["vices"]}).status_code == 503


@pytest.fixture
def two_people(engine, session):
    from grocery_app.api.repository import PostgresRepository
    from grocery_app.db.session import make_session_factory

    repository = PostgresRepository(make_session_factory(engine))
    return repository, repository.create_user("Sara")


@db
def test_each_person_counts_their_own_kinds(two_people):
    repository, sara = two_people
    client = TestClient(create_app(repository, token="owner-secret"))
    hers = {"Authorization": f"Bearer {sara['password']}"}

    put = client.put("/v1/counted", headers=OWNER, json={"kinds": ["vices", "household"]})
    assert put.status_code == 200 and put.json()["kinds"] == ["household", "vices"]
    assert client.get("/v1/counted", headers=hers).json()["kinds"] == [], "not Sara's"

    client.put("/v1/counted", headers=hers, json={"kinds": ["pets"]})
    client.put("/v1/counted", headers=OWNER, json={"kinds": ["household"]})
    assert client.get("/v1/counted", headers=OWNER).json()["kinds"] == ["household"], \
        "a kind switched off is gone"
    assert client.get("/v1/counted", headers=hers).json()["kinds"] == ["pets"]


@db
def test_an_unknown_kind_is_refused_and_nothing_changes(two_people):
    repository, _ = two_people
    client = TestClient(create_app(repository, token="owner-secret"))
    client.put("/v1/counted", headers=OWNER, json={"kinds": ["vices"]})
    answer = client.put("/v1/counted", headers=OWNER, json={"kinds": ["household", "clothes"]})
    assert answer.status_code == 422
    assert repository.counted_kinds() == {"vices"}


@db
def test_a_deleted_account_takes_its_choices_with_it(two_people, session):
    from grocery_app.db.models import CountedKind

    repository, sara = two_people
    as_sara = repository.as_user({"id": sara["id"], "name": "Sara"})
    as_sara.set_counted_kinds(frozenset({"pets"}))
    repository.set_counted_kinds(frozenset({"vices"}))
    as_sara.remove_account()
    assert [(k.user_id, k.kind) for k in session.query(CountedKind)] == [(None, "vices")]
