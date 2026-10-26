"""The HTTP layer over made-up data.

The routes must return the documents the CLI writes, unchanged: the demo and
the future iOS app read the same contract whether it came from a file or a
server. So these tests compare the wire format with the pipeline's own output
rather than asserting hand-written JSON.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from grocery_app.api.app import create_app, default_app
from grocery_app.api.repository import InMemoryRepository, JsonRepository
from grocery_app.api.schemas import Purchase
from grocery_app.insights import build_insights
from grocery_app.normalizer import save_json

PURCHASES = {
    "contract_version": 10,
    "meta": {
        "receipts": 2, "date_range": ["2026-01-05", "2026-02-05"], "product_lines": 3,
        "total_net_paid": 4.03, "unresolved_items": ["Geheimnis"], "ambiguous_items": [],
    },
    "purchases": [
        {"date": "2026-01-05", "store": "Musterladen", "source_image": "IMG_1.jpeg",
         "type": "product", "raw_name": "MU Milch 1,5%", "product_id": "p-0001",
         "resolved": True, "resolution": "exact", "said_by": "you", "candidate_ids": [],
         "qty": 1,
         "gross": 1.09, "discount": 0.0, "net_paid": 1.09, "tax_class": "A", "tax_rate": 0.07,
         "product": "Milch 1,5%", "brand": "Muster", "details": [],
         "category": "milch",
         "category_path": ["Molkereiprodukte & Eier", "Milch & Joghurt", "Milch"],
         "is_budget_brand": True, "is_organic": False,
         "unit_price": {"amount": 1.09, "per": "l"}},
        {"date": "2026-02-05", "store": "Musterladen", "source_image": "IMG_2.jpeg",
         "type": "product", "raw_name": "MU Milch 1,5%", "product_id": "p-0001",
         "resolved": True, "resolution": "exact", "said_by": "you", "candidate_ids": [],
         "qty": 1,
         "gross": 1.19, "discount": 0.0, "net_paid": 1.19, "tax_class": "A", "tax_rate": 0.07,
         "product": "Milch 1,5%", "brand": "Muster", "details": [],
         "category": "milch",
         "category_path": ["Molkereiprodukte & Eier", "Milch & Joghurt", "Milch"],
         "is_budget_brand": True, "is_organic": False,
         "unit_price": {"amount": 1.19, "per": "l"}},
        {"date": "2026-02-05", "store": "Musterladen", "source_image": "IMG_2.jpeg",
         "type": "product", "raw_name": "Geheimnis", "product_id": None,
         "resolved": False, "resolution": "none", "said_by": None, "candidate_ids": [],
         "qty": 1,
         "gross": 1.75, "discount": 0.0, "net_paid": 1.75, "tax_class": "A", "tax_rate": 0.07,
         "unit_price": None},
    ],
}


@pytest.fixture
def client():
    return TestClient(create_app(InMemoryRepository(PURCHASES)))


def test_health_reports_contract_versions_and_receipts(client):
    body = client.get("/health").json()
    assert body == {"status": "ok", "purchases_contract_version": 10,
                    "insights_contract_version": 12, "receipts": 2,
                    "uploads": False, "writes": False}
    assert (body["uploads"], body["writes"]) == (False, False), \
        "a file-backed server can do neither, and says so rather than 404ing later"


def test_purchases_is_the_contract_unchanged(client):
    """The wire format is the document, key for key.

    Comparing against a copy re-normalized by the same schema would prove
    nothing: it would hide exactly the kind of field the schema adds or drops
    on the way out. So this compares with the document as written.
    """
    r = client.get("/v1/purchases")
    assert r.status_code == 200
    assert r.json() == PURCHASES


def test_an_unresolved_line_gains_no_attributes_on_the_wire(client):
    """The normalizer omits the product attributes it does not know; so does
    the server. A client must not see `brand: null` where there is no brand
    field at all, or it will report a product with no brand."""
    served = next(p for p in client.get("/v1/purchases").json()["purchases"]
                  if not p["resolved"])
    for field in ("product", "brand", "details", "category",
                  "category_path", "is_budget_brand", "is_organic"):
        assert field not in served
    # A null the document does carry is still sent.
    assert served["unit_price"] is None
    assert served["product_id"] is None


def test_a_resolved_line_keeps_its_attributes_on_the_wire(client):
    served = next(p for p in client.get("/v1/purchases").json()["purchases"]
                  if p["resolved"])
    assert served["product"] == "Milch 1,5%"
    assert served["brand"] == "Muster"
    assert served["is_budget_brand"] is True
    # The key is the identity; the path is what a reader is shown.
    assert served["category"] == "milch"
    assert served["category_path"][-1] == "Milch"
    assert served["details"] == [], "a known-empty attribute is still sent"


def test_insights_are_computed_from_the_served_history(client):
    r = client.get("/v1/insights")
    assert r.status_code == 200
    assert r.json() == build_insights(PURCHASES)


def test_insights_as_of_is_honoured(client):
    body = client.get("/v1/insights", params={"as_of": "2026-03-01"}).json()
    assert body["as_of"] == "2026-03-01"
    assert body == build_insights(PURCHASES, as_of=date(2026, 3, 1))


def test_insights_rejects_a_non_date(client):
    r = client.get("/v1/insights", params={"as_of": "yesterday"})
    assert r.status_code == 422
    assert "as_of" in r.json()["detail"]


def test_schema_rejects_a_field_the_contract_does_not_know():
    record = dict(PURCHASES["purchases"][0], surprise=1)
    with pytest.raises(ValueError):
        Purchase.model_validate(record)


def test_json_repository_rereads_the_file(tmp_path):
    path = tmp_path / "purchases.json"
    save_json(PURCHASES, path)
    client = TestClient(create_app(JsonRepository(path)))
    assert client.get("/health").json()["receipts"] == 2
    updated = dict(PURCHASES, meta=dict(PURCHASES["meta"], receipts=3))
    save_json(updated, path)
    assert client.get("/health").json()["receipts"] == 3


def test_default_app_reads_the_path_from_the_environment(tmp_path, monkeypatch):
    """A 200 would prove nothing here: the default path answers too.

    So the file at the configured path carries a receipt count no other file
    has, and the response has to show it.
    """
    path = tmp_path / "elsewhere.json"
    save_json(dict(PURCHASES, meta=dict(PURCHASES["meta"], receipts=99)), path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("GROCERY_PURCHASES", str(path))
    assert TestClient(default_app()).get("/health").json()["receipts"] == 99


def test_the_server_applies_the_migrations_as_it_starts(monkeypatch):
    """No separate `db upgrade` step before the server: every start is a wait
    for whoever opened the page, and two Python starts took longer than one.
    The migrations still run before anything else, so no request can meet an
    old schema."""
    import grocery_app.db.migrate as migrate

    class Upgraded(Exception):
        pass

    def upgrade(url):
        raise Upgraded(url)

    monkeypatch.setattr(migrate, "upgrade", upgrade)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg:///nowhere")
    with pytest.raises(Upgraded, match="nowhere"):
        default_app()


def test_the_page_worker_is_served_for_the_page_to_register(client):
    """The phone keeps its own copy of the page, so a reload does not wait for
    a server that is starting up. The worker is never cached itself, or a
    fix to it would not reach the phone."""
    worker = client.get("/sw.js")
    assert worker.status_code == 200
    assert worker.headers["content-type"].startswith("application/javascript")
    assert worker.headers["cache-control"] == "no-cache"
    assert '"navigate"' in worker.text, "it answers for the page only, never for /v1"
    assert 'register("/sw.js")' in client.get("/").text
    assert '"page-updated"' in worker.text and '"page-updated"' in client.get("/").text, \
        "a page shown from the phone's copy is replaced once the server's newer one arrives"



def run_page_function(page, name, script):
    """Runs functions of the phone page in Node (`name`: their names, spaces
    between), with `script` after them. Its console.log lines come back."""
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.fail("node is needed to run the page's code")
    found = []
    for each in name.split():
        match = re.search(rf"^(?:async )?function {each}\(.*?^}}$", page, re.S | re.M)
        assert match, f"the page has {each}()"
        found.append(match.group(0))
    done = subprocess.run([node, "-e", "\n".join(found) + "\n" + script],
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return done.stdout.splitlines()


@pytest.mark.parametrize("online, said", [
    (False, "no internet connection"),
    (True, "the server could not be reached; check your connection"),
])
def test_a_request_that_never_left_the_phone_says_so(client, online, said):
    """Offline, the page said "Cannot load: Load failed", the browser's words,
    as if the app had broken (the owner, 2026-10-14)."""
    page = client.get("/").text
    out = run_page_function(page, "reach", f"""
        Object.defineProperty(globalThis, "navigator",
                              {{ value: {{ onLine: {str(online).lower()} }} }});
        globalThis.fetch = async () => {{ throw new TypeError("Load failed"); }};
        reach("/v1/receipts").catch(error => console.log(error.message));
    """)
    assert out == [said]
    assert page.count("await fetch(path, opts)") == 1 and "await reach(path, opts)" in page, \
        "every request of the page goes through it"
    assert 'addEventListener("online", () => load())' in page, "and loads again once back"


def test_a_newcomer_s_home_fills_a_bar_to_ten_receipts_and_each_stop_opens_its_card(client):
    """The owner, 2026-10-14: a newcomer saw one lone number. Until 10
    receipts, Home is a bar with stops at 1, 5 and 10, each a promise."""
    page = client.get("/").text
    start = page[page.index("const START_GOAL"):page.index("function gettingStarted")]
    out = run_page_function(page, "gettingStarted", start + """
        for (const n of [0, 1, 4, 5, 9, 10, 31]) {
          const s = gettingStarted(n);
          console.log(n, s ? s.goal + " " + s.stops.map(x => x.at + (x.reached ? "+" : "-"))
            .join(" ") : "none");
        }
    """)
    assert out == ["0 10 1- 5- 10-", "1 10 1+ 5- 10-", "4 10 1+ 5- 10-", "5 10 1+ 5+ 10-",
                   "9 10 1+ 5+ 10-", "10 none", "31 none"]
    assert "reached(START_GOAL) ? priceCard(d) : null" in page, "price moves open at 10"
    assert "reached(5) ? regularsCard(d) : null" in page, "your regular opens at 5"


def test_a_receipt_line_is_its_product_and_brand_and_nothing_more(client):
    """The owner, 2026-10-15: "you're writing everything". A line is one row,
    the product and its brand; who said it, the size and the printed text are
    off the screen. A line nothing placed shows its guess, else the paper's
    text, marked as a guess."""
    page = client.get("/").text
    out = run_page_function(page, "lineWords", """
        const show = line => console.log(JSON.stringify(lineWords(line)));
        show({ product: "Bio Müsli", brand: "Kornfeld", said_by: "app", raw_name: "BIO MUESLI",
               sold_as: { form: "pack", size: { value: 500, unit: "g" } } });
        show({ product: "Bananen", brand: null, said_by: "you", raw_name: "BANANEN" });
        show({ product: null, first_guess: { name: "Haferdrink" }, raw_name: "HAFER DR" });
        show({ product: null, first_guess: null, raw_name: "ART 4711" });
    """)
    assert out == ['{"name":"Bio Müsli","brand":"Kornfeld","guess":false}',
                   '{"name":"Bananen","brand":null,"guess":false}',
                   '{"name":"Haferdrink","brand":null,"guess":true}',
                   '{"name":"ART 4711","brand":null,"guess":true}']
    drawn = page[page.index("function lineText("):page.index("function isOwner(")]
    assert "lineWords(line)" in drawn
    assert "said_by" not in drawn and "printed" not in drawn and "sold_as" not in drawn, \
        "no you/app mark, printed text or size under a receipt line"


def test_a_receipt_row_says_its_day_and_items_and_only_a_misread_besides(client):
    """The owner, 2026-10-15: "10 items: 8 you, 2 app" was noise. The row says
    the day and the items; a receipt that does not add up still says so."""
    page = client.get("/").text
    out = run_page_function(page, "receiptMeta shortDate day plural misread", """
        const row = (extra) => console.log(receiptMeta({ date: "2026-10-03", product_lines: 7,
          said_by_you: 5, said_by_app: 2, not_counted: 1, unplaced: 1, printed_total: 12.5,
          lines_total: 12.5, ...extra }));
        row({});
        row({ product_lines: 1 });
        row({ lines_total: 12.0 });
    """)
    assert out == ["3 Oct · 7 items", "3 Oct · 1 item", "3 Oct · 7 items · doesn't add up"]


def test_empty_screens_say_they_are_empty_and_how_to_fill_them(client):
    page = client.get("/").text
    assert '"No receipts yet. Tap + " +' in page
    assert '"No insights yet: they come " +' in page
    for question in ("Prices that moved", "Due again soon", "Same item, other shops"):
        assert f'closedCard("{question}",' in page, f"{question}: closed, saying what opens it"


def test_a_receipt_still_being_read_is_not_asked_for_when_none_is_open(client):
    """A queued job has no receipt id yet; with no receipt open the page took
    null for null and asked for /v1/receipts/null every 3 s (2026-10-14)."""
    page = client.get("/").text
    out = run_page_function(page, "inProgress openBeingRead", """
        const queued = { status: "queued", receipt_id: null };
        const reading = { status: "running", receipt_id: 7 };
        for (const [open, jobs] of [[null, [queued]], [undefined, [queued]], [7, [queued]],
                                    [7, [reading]], [8, [reading]]]) {
          globalThis.state = { open, jobs };
          console.log(String(open), openBeingRead());
        }
    """)
    assert out == ["null false", "undefined false", "7 false", "7 true", "8 false"]
    assert 'if (openBeingRead() && state.tab === "receipts")' in page, \
        "the refresh asks openBeingRead()"


def test_a_removed_receipt_is_removed_when_the_page_is_left_before_undo_runs_out(client):
    """2026-10-14: the removal waited 8 s for Undo and a reload dropped it, so
    removed receipts came back. Leaving the page now sends it; Undo still
    sends nothing, and the receipt's questions go with it at once."""
    page = client.get("/").text
    start = "const UNDO_MS = 8000;\n" + \
        page[page.index("const removals"):page.index("function removeReceipt")]
    out = run_page_function(page, "asks removeReceipt sendRemoval sendRemovalsNow", start + """
        const sent = [];
        let undo = null;
        globalThis.api = async (path, opts) => {
          sent.push(opts.method + " " + path + (opts.keepalive ? " keepalive" : ""));
        };
        globalThis.toast = (text, onUndo) => { undo = onUndo; };
        globalThis.render = () => {};
        globalThis.load = async () => {};
        globalThis.state = { removing: new Set(), open: 5,
          checks: { checks: [{ receipt_id: 5, app_product: "Feigen" },
                             { receipt_id: 6, app_product: "Milch" }] },
          questions: { questions: [] } };
        removeReceipt(5);
        console.log(asks().map(a => a.item.app_product).join(","), state.open);
        sendRemovalsNow();
        removeReceipt(6);
        undo();
        sendRemovalsNow();
        setTimeout(() => { console.log(sent.join(" | ")); process.exit(0); }, 10);
    """)
    assert out == ["Milch null", "DELETE /v1/receipts/5 keepalive"]
    assert 'addEventListener("pagehide", sendRemovalsNow)' in page


def test_a_question_thanks_the_shopper(client):
    page = client.get("/").text
    assert "Thank you: your answer helps the app learn." in page
    assert "Each answer helps the app learn what you buy" in page


def test_undo_shows_a_ring_that_empties_in_the_time_left_to_undo(client):
    """The owner, 2026-10-14: the time to undo, shown as a clock-like ring."""
    page = client.get("/").text
    assert "const UNDO_MS = 8000;" in page
    assert "function toast(text, undo, ms = UNDO_MS)" in page
    assert "animation-duration:${ms}ms" in page, "the ring runs as long as the Undo"
    assert "undo ? ms : 3500" in page and "sendRemoval(receiptId), UNDO_MS)" in page, \
        "the message and the removal end with the ring"

def test_the_repository_is_chosen_by_the_environment(tmp_path, monkeypatch):
    """Which store production reads from. Without a URL it is the file; with
    one it is PostgreSQL, and no connection is made to decide that."""
    from grocery_app.api.repository import JsonRepository as _Json
    from grocery_app.api.repository import PostgresRepository, default_repository

    path = tmp_path / "purchases.json"
    save_json(PURCHASES, path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("GROCERY_PURCHASES", str(path))
    chosen = default_repository()
    assert isinstance(chosen, _Json) and chosen.purchases_path == path

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://nobody@localhost:1/nothing")
    assert isinstance(default_repository(), PostgresRepository)


# --- the password -------------------------------------------------------------

def test_a_token_locks_every_v1_route_and_nothing_else():
    locked = TestClient(create_app(InMemoryRepository(PURCHASES), token="s3cret"))

    for path in ("/v1/purchases", "/v1/insights", "/v1/receipts", "/v1/questions"):
        response = locked.get(path)
        assert response.status_code == 401, path
        assert response.json() == {"detail": "wrong or no token"}
    assert locked.get("/v1/purchases",
                      headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert locked.post("/v1/receipts", files={"file": ("r.jpg", b"x")}).status_code == 401, \
        "an upload is refused before anything is read or stored"

    allowed = locked.get("/v1/purchases", headers={"Authorization": "Bearer s3cret"})
    assert allowed.status_code == 200
    assert allowed.json()["meta"]["receipts"] == 2

    # The page, the health check and the schema hold no history.
    assert locked.get("/").status_code == 200
    assert locked.get("/sw.js").status_code == 200
    assert locked.get("/health").json()["receipts"] == 2
    assert locked.get("/openapi.json").status_code == 200


def test_without_a_token_the_routes_stay_open(client):
    assert client.get("/v1/purchases").status_code == 200
