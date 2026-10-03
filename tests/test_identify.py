"""What a line is (`identify`) and how it is scored, with fake model answers.

No test calls a model. Every product name is invented or generic.
"""

from __future__ import annotations

from grocery_app.evaluate_identify import evaluate_identify, format_report
from grocery_app.identify import SCHEMA, SYSTEM_PROMPT, identify


def answering(**answer):
    base = {"parts": [{"printed": "Erdbeeren", "means": "strawberries (kind)"},
                      {"printed": "400g", "means": "size"}],
            "name": "Erdbeeren", "category": "beeren", "brand": None, "variant": None,
            "size": "400g", "can_tell": True, "reason": "the line says strawberries"}
    asked = []

    def decider(system, prompt, schema):
        asked.append((system, prompt, schema))
        return {**base, **answer}

    decider.asked = asked
    return decider


def test_a_line_is_read_into_the_fixed_format():
    decider = answering()
    identity = identify("Erdbeeren 400g", "Musterladen", decider)
    assert (identity.name, identity.category, identity.size, identity.can_tell) == \
        ("Erdbeeren", "beeren", "400g", True)
    system, prompt, schema = decider.asked[0]
    assert system == SYSTEM_PROMPT and schema == SCHEMA
    assert "Receipt line: `Erdbeeren 400g`" in prompt
    assert "beeren: Obst & Gemüse > Obst > Beeren" in system, "the categories are listed"


def test_a_category_outside_the_list_is_dropped_not_kept():
    assert identify("x", None, answering(category="strawberry-stuff")).category is None


def test_an_empty_name_is_not_an_answer():
    assert identify("x", None, answering(name="  ")).can_tell is False


def sheet(name, product, position=0):
    return {"source_image": "IMG_1.jpeg", "position": position, "store": "Musterladen",
            "raw_name": name, "product": product, "note": None}


def test_each_line_gets_the_outcome_the_judge_gives_or_asked():
    from grocery_app.identify import Identity

    said = {"Erdbeeren 400g": Identity("Erdbeeren", "beeren", None, None, "400g", True, "."),
            "MU Wraps": Identity("Tortilla Wraps", None, None, None, None, True, "."),
            "Kekse": Identity("Salzstangen", None, None, None, None, True, "."),
            "DESTAN": Identity("DESTAN", None, None, None, None, False, "a brand alone"),
            "Kartoffeln F.K.": Identity("Kartoffeln", None, None, "Frühkartoffeln", None,
                                        True, ".")}
    verdicts = {"Erdbeeren 400g": "right", "MU Wraps": "missing", "Kekse": "wrong",
                "Kartoffeln F.K.": "false_detail"}

    def judge(system, prompt, schema):
        name = prompt.split("`")[1]
        return {"verdict": verdicts[name], "reason": "test"}

    truth = {"lines": [sheet("Erdbeeren 400g", "strawberries 400 g", 0),
                       sheet("MU Wraps", "Muster tortilla wraps", 1),
                       sheet("Kekse", "biscuits", 2), sheet("DESTAN", "unknown", 3),
                       sheet("Kartoffeln F.K.", "waxy potatoes", 4)]}
    report = evaluate_identify(truth, lambda raw, store, others, paid, place=None: said[raw], judge)
    assert report["totals"] == {"right": 1, "missing": 1, "false_detail": 1, "wrong": 1,
                                "asked": 1}
    assert report["mistakes"] == 2, "a false detail is a mistake; a missing one is not"
    text = format_report(report)
    assert "mistakes (false_detail + wrong): 2" in text
    assert "Kekse" in text.split("Wrong:")[1].split("False detail:")[0]
    assert "Kartoffeln F.K." in text.split("False detail:")[1].split("Missing:")[0]
    assert "MU Wraps" in text.split("Missing:")[1] and "DESTAN" in text.split("Asked:")[1]


def test_the_judge_is_told_a_false_detail_is_not_a_missing_one():
    from grocery_app.evaluate_identify import JUDGE_PROMPT, JUDGE_SCHEMA

    assert JUDGE_SCHEMA["properties"]["verdict"]["enum"] == \
        ["right", "missing", "false_detail", "wrong"]
    assert "A true kind with one false detail is\nfalse_detail, not missing." in JUDGE_PROMPT


def test_the_shops_similar_products_are_context_without_prices():
    """They help read a cut word (`Kartoffelr.`); the price stays out."""
    decider = answering(name="Kartoffelringe")
    identify("Kartoffelr.,Dolphy", "Musterladen", decider,
             [{"name": "Kartoffelringe 100 g, Paprika", "brand": "MUSTER", "pack_size": "0,1 kg",
               "prices": [0.99]}])
    prompt = decider.asked[0][1]
    assert "- Kartoffelringe 100 g, Paprika | MUSTER | 0,1 kg" in prompt
    assert "0.99" not in prompt


def test_the_rest_of_the_receipt_is_context():
    """A café breakfast is told from a jar of compote by the receipt around it."""
    decider = answering(name="Frühstück", category="cafe-imbiss")
    identify("FRUEHSTUECKKOMP", "Musterladen", decider,
             receipt_lines=["CAFE CREME", "CAPPUCCINO", "FRUEHSTUECKKOMP"])
    prompt = decider.asked[0][1]
    assert "Other lines of the same receipt:\n- `CAFE CREME`\n- `CAPPUCCINO`" in prompt
    assert prompt.count("FRUEHSTUECKKOMP") == 1, "the line itself is not repeated"


def test_the_scorer_gives_each_line_its_receipt():
    seen = {}

    def identifier(raw, store, others, paid, place=None):
        from grocery_app.identify import Identity
        seen[raw] = others
        return Identity(raw, None, None, None, None, False, ".")

    truth = {"lines": [sheet("A", "a", 0), sheet("B", "b", 1)]}
    evaluate_identify(truth, identifier, lambda *a: {})
    assert seen == {"A": ["A", "B"], "B": ["A", "B"]}


# --- every printed part is accounted for -------------------------------------

def test_an_answer_that_leaves_a_printed_word_out_cannot_tell():
    """A till prints nothing by accident: `MU` dropped means the model took the
    first pad it saw instead of reading the brand."""
    identity = identify("MU Pads 36er", "Musterladen", answering(
        parts=[{"printed": "Pads", "means": "pads"}, {"printed": "36er", "means": "36"}],
        name="Wattepads", can_tell=True, reason="similar product"))
    assert identity.can_tell is False
    assert identity.reason.startswith("left out `MU`")


def test_every_word_accounted_for_keeps_the_answer():
    identity = identify("MU Pads 36er", "Musterladen", answering(
        parts=[{"printed": "MU", "means": "Muster (brand)"}, {"printed": "Pads", "means": "pads"},
               {"printed": "36er", "means": "36"}], name="Kaffeepads", can_tell=True))
    assert identity.can_tell is True
    assert identity.parts[0] == {"printed": "MU", "means": "Muster (brand)"}


def test_a_word_split_across_parts_or_punctuation_dropped_still_counts():
    from grocery_app.identify import left_out

    assert left_out("MUSTERKORNBRÖT. 2er", [{"printed": "MUSTERKORN"}, {"printed": "BRÖT."},
                                            {"printed": "2er"}]) == []
    assert left_out("Kekse,Muster / Ding W", [{"printed": "Kekse"}, {"printed": "Muster"},
                                              {"printed": "Ding W"}]) == []
    assert left_out("Kekse Muster", [{"printed": "Kekse"}]) == ["Muster"]


def test_the_model_is_told_to_read_every_part_first():
    assert "Leave nothing out" in SYSTEM_PROMPT
    assert SCHEMA["required"][0] == "parts"


def test_the_report_shows_the_parts_of_a_line_it_lists():
    from grocery_app.identify import Identity

    said = Identity("Wattepads", None, None, None, None, True, ".",
                    [{"printed": "MU", "means": None}, {"printed": "Pads", "means": "pads"}])
    report = evaluate_identify({"lines": [sheet("MU Pads", "Muster coffee pads")]},
                               lambda *_: said,
                               lambda *_: {"verdict": "wrong", "reason": "test"})
    assert "parts: MU = ?; Pads = pads" in format_report(report)


# --- what the paper says besides the name ------------------------------------

def test_an_abbreviation_is_learned_from_confirmed_names_whose_brand_it_can_stand_for():
    from grocery_app.identify import abbreviations

    products = {"p-1": {"brand": "Muster Tag"}, "p-2": {"brand": "Muster Tag"},
                "p-3": {"brand": "Musterladen"}, "p-4": {"brand": "Ding"},
                "p-5": {"brand": "Dr. Muster"}}
    resolution = {("musterladen", "MT Milch 1l"): ["p-1"],
                  ("musterladen", "MT Quark 500g"): ["p-2"],
                  ("musterladen", "MSTR.KEKSE 200G"): ["p-3"],
                  ("musterladen", "Avocados lose"): ["p-3"],  # a word, not the brand's letters
                  ("musterladen", "Ding Seife"): ["p-4"],  # the brand itself, nothing to learn
                  ("musterladen", "Dr. Muster Pudding"): ["p-5"],  # its first word: shared
                  ("musterladen", "MT Familie"): ["p-1", "p-2"]}  # a family says no one brand
    learned = abbreviations(resolution, products)["musterladen"]
    assert dict(learned) == {"MT": {"Muster Tag": 2}, "MSTR.": {"Musterladen": 1}}


def test_the_vat_rate_comes_from_whatever_the_receipt_prints():
    from grocery_app.identify import line_vat_rates

    def line(code, net):
        return {"raw_name": "x", "tax_class": code, "net": net}

    assert line_vat_rates({"store": "Lidl", "lines": [line("A", 1.0), line("B", 2.0)]}) == \
        [0.07, 0.19], "the store's class table"
    assert line_vat_rates({"store": "Woanders", "lines": [line("19%", 1.0), line("7%", 1.0)]}) \
        == [0.19, 0.07], "a rate read in place of the class"
    assert line_vat_rates({"store": "Woanders", "tax_buckets": {"19%": 3.0},
                           "lines": [line(None, 1.0), line(None, 2.0)]}) == [0.19, 0.19]
    assert line_vat_rates({"store": "Woanders", "tax_buckets": {"7%": 1.5, "19%": 2.0},
                           "lines": [line("1", 0.5), line("2", 2.0), line("1", 1.0)]}) == \
        [0.07, 0.19, 0.07], "each class adds up to one bucket's total"
    assert line_vat_rates({"store": "Woanders", "tax_buckets": {"7%": 9.0, "19%": 9.0},
                           "lines": [line("1", 1.0)]}) == [None], "nothing fits: unknown"


def test_what_was_paid_reads_like_the_receipt():
    from grocery_app.identify import paid

    assert paid({"qty": 1, "net": 5.49}, 0.07) == "Paid: 5,49 € for 1, VAT 7 %"
    assert paid({"qty": 2, "net": 1.3}, None) == "Paid: 1,30 € for 2 (0,65 € each)"
    assert paid({"qty": 1, "net": 2.1, "sold_by_weight": True, "weight_kg": 0.634,
                 "unit_price": 3.31, "unit_price_basis": "kg"}, 0.07) == \
        "Paid: 2,10 € for 0,634 kg at 3,31 €/kg, VAT 7 %"


def test_the_prompt_carries_the_price_and_only_the_abbreviations_on_the_line():
    from collections import Counter

    decider = answering(parts=[{"printed": "MT", "means": "Muster Tag"},
                               {"printed": "Pads", "means": "pads"}])
    learned = {"MT": Counter({"Muster Tag": 3}), "ZZ": Counter({"Zebra": 1})}
    identify("MT Pads", "Musterladen", decider, paid_text="Paid: 5,49 € for 1, VAT 7 %",
             learned=learned)
    prompt = decider.asked[0][1]
    assert "Receipt line: `MT Pads`\nPaid: 5,49 € for 1, VAT 7 %" in prompt
    assert "- `MT` = Muster Tag (3 confirmed names)" in prompt
    assert "Zebra" not in prompt
    assert "7 %: food" in SYSTEM_PROMPT


def test_the_scorer_gives_each_line_what_its_reading_says_was_paid():
    seen = {}

    def identifier(raw, store, others, paid, place=None):
        from grocery_app.identify import Identity
        seen[raw] = paid
        return Identity(raw, None, None, None, None, False, ".")

    truth = {"lines": [sheet("MT Pads", "pads", 0), sheet("Kekse", "biscuits", 1)]}
    reading = {"store": "Musterladen", "tax_buckets": {"7%": 6.48},
               "lines": [{"raw_name": "MT Pads", "qty": 1, "net": 5.49, "tax_class": None},
                         {"raw_name": "Kekse gross", "qty": 1, "net": 0.99}]}
    report = evaluate_identify(truth, identifier, lambda *a: {}, {"IMG_1.jpeg": reading})
    assert seen == {"MT Pads": "Paid: 5,49 € for 1, VAT 7 %", "Kekse": ""}, \
        "a position that no longer holds the same name gives no price"
    assert report["lines"][0]["paid"] == "Paid: 5,49 € for 1, VAT 7 %"


def test_the_scorer_hands_each_store_its_own_abbreviations():
    from collections import Counter

    from grocery_app.evaluate_identify import bound_identifier

    decider = answering(parts=[{"printed": "MT", "means": "x"}, {"printed": "Pads", "means": "x"}])
    learned = {"musterladen": {"MT": Counter({"Muster Tag": 2})},
               "woanders": {"MT": Counter({"Mehr Tee": 5})}}
    bound_identifier(decider, None, learned)("MT Pads", "MUSTERLADEN", [], "")
    assert "`MT` = Muster Tag" in decider.asked[0][1]
    assert "Mehr Tee" not in decider.asked[0][1]


def test_the_server_reads_a_line_with_the_evidence_it_is_scored_with():
    """`api.matching.line_identifier` hands identify the same evidence
    `eval-identify` measured: price and VAT, the other printed names, the
    shop's similar products and the abbreviations learned at this store."""
    from grocery_app.api.matching import line_identifier

    decider = answering(parts=[{"printed": "MT", "means": "x"}, {"printed": "Pads", "means": "x"},
                               {"printed": "6er", "means": "x"}])
    receipt = {"store": "Musterladen", "tax_buckets": {"7%": 6.48},
               "lines": [{"type": "product", "raw_name": "MT Pads 6er", "qty": 1, "net": 5.49},
                         {"type": "deposit", "raw_name": "Pfand", "qty": 1, "net": 0.0},
                         {"type": "product", "raw_name": "Kekse", "qty": 1, "net": 0.99}]}
    inputs = {"resolution": {("musterladen", "MT Kaffee 500g"): ["p-1"]},
              "products": {"p-1": {"brand": "Muster Tag"}}}
    proposal = {"candidates": [{"name": "Kaffeepads Crema", "brand": "Muster", "pack_size": None}]}
    line_identifier(decider)(0, receipt, proposal, inputs)
    prompt = decider.asked[0][1]
    assert "Paid: 5,49 € for 1, VAT 7 %" in prompt
    assert "- `MT` = Muster Tag (1 confirmed name)" in prompt
    assert "- `Kekse`" in prompt and "Pfand" not in prompt
    assert "- Kaffeepads Crema | Muster" in prompt



def test_the_shoppers_description_goes_in_the_lines_prompt_not_the_system_prompt():
    """The meaning is the shopper's, the format ours; and the scored system
    prompt, with its cached answers, stays as it was."""
    decider = answering(parts=[{"printed": "Pamir", "means": "brand"}])
    identify("Pamir", "FK Frisch Kauf GmbH", decider,
             description="salted pickled cucumbers, the Pamir ones")
    system, prompt, _ = decider.asked[0]
    assert "<<salted pickled cucumbers, the Pamir ones>>" in prompt
    assert "Never contradict them" in prompt
    assert system == SYSTEM_PROMPT
    identify("Pamir", "FK Frisch Kauf GmbH", decider)
    assert "<<" not in decider.asked[1][1], "no description, no such section"


# --- readers that can search ------------------------------------------------------

class Searching:
    """A fake searcher: answers `products` and says it searched `queries`."""

    def __init__(self, queries, titles=(), products=(), note="fits"):
        from grocery_app.matcher import Searched

        self.queries, self.titles = list(queries), list(titles)
        self.products, self.note = list(products), note
        self.asked = []
        self.last_search = Searched()

    def __call__(self, system, prompt, schema):
        from grocery_app.matcher import Searched

        self.asked.append((system, prompt, schema))
        self.last_search = Searched(list(self.queries), list(self.titles))
        return {"products": self.products, "note": self.note}


def test_every_line_is_searched_then_read_again_with_what_the_pages_said():
    from grocery_app.identify import SEARCH_SCHEMA, SEARCH_SYSTEM, read_line

    reader = answering(parts=[{"printed": "MU", "means": "Muster"},
                              {"printed": "Ult.Nacht", "means": "Ultra Nacht"},
                              {"printed": "12St", "means": "size"}],
                       name="Binden", category=None, can_tell=True)
    searcher = Searching(["MU Ult.Nacht 12St Musterladen", "Muster Ultimate Nacht Binden"],
                         titles=["Muster Ultimate Nacht Binden 12 Stück - Musterdrogerie"],
                         products=[{"product": "Ultimate Nacht Binden", "brand": "Muster",
                                    "size": "12 Stück", "price": "3,49 €",
                                    "seen_at": "musterdrogerie.de"}])
    identity = read_line("MU Ult.Nacht 12St", "Musterladen", reader, searcher,
                         paid_text="Paid: 3,41 € for 1, VAT 19 %",
                         place="Musterweg 1, 12345 Musterstadt")

    (system, prompt, schema), = searcher.asked
    assert (system, schema) == (SEARCH_SYSTEM, SEARCH_SCHEMA)
    assert prompt.startswith("Query to search first: MU Ult.Nacht 12St Musterladen"), \
        "the query is the whole printed line and the shop, built by the code"
    assert "The shop is at: Musterweg 1, 12345 Musterstadt, Germany" in prompt, \
        "the searcher is told where the shop is, so it searches in that country"
    first, second = reader.asked
    assert "web search" not in first[1], "the first reading has no findings"
    assert "Muster Ultimate Nacht Binden 12 Stück - Musterdrogerie" in second[1], \
        "the reader sees the page titles exactly as they came back"
    assert "Ultimate Nacht Binden | Muster | 12 Stück | 3,49 €" in second[1]
    assert identity.searched == ["MU Ult.Nacht 12St Musterladen",
                                 "Muster Ultimate Nacht Binden"]


def test_a_sure_first_reading_is_searched_all_the_same():
    from grocery_app.identify import read_line

    searcher = Searching(["Erdbeeren 400g Musterladen"])
    read_line("Erdbeeren 400g", "Musterladen", answering(can_tell=True), searcher)
    assert len(searcher.asked) == 1, "the model's confidence does not decide the search"


def test_a_line_that_is_not_groceries_is_neither_searched_nor_asked_about():
    from grocery_app.identify import read_line

    for printed, category in (("MILCHKAFFEE", "cafe-imbiss"), ("Muster Foto Sofort", "foto-karten"),
                              ("Tragetasche", "taschen-tueten")):
        reader = answering(parts=[{"printed": w, "means": "?"} for w in printed.split()],
                           name=printed.title(), category=category, can_tell=False,
                           choices=["one kind", "another kind"])
        searcher = Searching([f"{printed} Musterladen"])
        identity = read_line(printed, "Musterladen", reader, searcher)
        assert searcher.asked == [] and len(reader.asked) == 1, printed
        assert (identity.can_tell, identity.choices, identity.searched) == (True, [], []), \
            "which photo print it was does not matter: nothing to ask"


def test_groceries_and_lines_of_no_known_category_are_searched():
    from grocery_app.identify import read_line

    for category in ("beeren", None):
        searcher = Searching(["x"])
        read_line("Erdbeeren 400g", "Musterladen", answering(category=category), searcher)
        assert len(searcher.asked) == 1, category


def test_a_searcher_that_does_not_search_is_told_once_more_then_reported():
    from grocery_app.identify import read_line

    reader = answering()
    searcher = Searching([], products=[{"product": "what it already believed", "brand": None,
                                        "size": None, "price": None, "seen_at": None}])
    identity = read_line("Erdbeeren 400g", "Musterladen", reader, searcher)
    assert len(searcher.asked) == 2
    assert "You have not searched yet" in searcher.asked[1][1]
    assert identity.searched == [], "a line nobody searched is never passed off as searched"
    assert len(reader.asked) == 1, "and what the model already believed is not evidence"
    assert (identity.unsearched, identity.can_tell) == (True, False), \
        "an answer nobody checked is not saved"


def test_a_line_still_unclear_after_the_search_comes_with_the_choices_it_left():
    from grocery_app.identify import read_line

    reader = answering(parts=[{"printed": "MUSTRA", "means": "Mustra (brand)"}],
                       name="Mustra", category=None, can_tell=False,
                       choices=["Geflügelwurst, Mustra", "Schafskäse, Mustra"])
    identity = read_line("MUSTRA", "Musterladen", reader, Searching(["MUSTRA Musterladen"]))
    assert identity.can_tell is False
    assert identity.choices == ["Geflügelwurst, Mustra", "Schafskäse, Mustra"]
    sure = identify("Erdbeeren 400g", None, answering(choices=["something"]))
    assert sure.choices == [], "a line it can tell has no choices"


def test_the_shoppers_own_words_need_no_search():
    from grocery_app.identify import read_line

    searcher = Searching(["Pamir Musterladen"])
    read_line("Pamir", "Musterladen", answering(), searcher,
              description="salted pickled cucumbers")
    assert searcher.asked == []


def test_claude_with_search_may_search_the_web_and_nothing_else(monkeypatch, tmp_path):
    import subprocess

    from grocery_app.matcher import ClaudeCodeDecider

    ran = []

    def fake_run(command, **kwargs):
        ran.append(command)
        return subprocess.CompletedProcess(command, 0, '{"structured_output": {"a": 1}}', "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ClaudeCodeDecider("sonnet", tmp_path, version="t", search=True)("s", "p", {})
    ClaudeCodeDecider("sonnet", tmp_path, version="t")("s", "p", {})
    searching, plain = ran
    assert searching[searching.index("--output-format") + 1] == "stream-json"
    assert searching[searching.index("--tools") + 1] == "WebSearch"
    assert searching[searching.index("--allowedTools") + 1] == "WebSearch"
    assert plain[plain.index("--tools") + 1] == ""
    assert {p.parent.parent.name for p in tmp_path.rglob("*.json")} == \
        {"claude-code-sonnet-search", "claude-code-sonnet"}, "answers never cross setups"


def test_claude_search_records_what_it_searched_and_the_titles_that_came_back(
        monkeypatch, tmp_path):
    import json
    import subprocess

    from grocery_app.matcher import ClaudeCodeDecider

    links = [{"title": "Muster Ultimate Nacht 12 Stück", "url": "https://example.org/a"}]
    stream = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "WebSearch",
             "input": {"query": "MU Ult.Nacht 12St Musterladen"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "Web search results for query: x\n\n"
                                               f"Links: {json.dumps(links)}\n\nSummary."}]}},
        {"type": "result", "is_error": False, "structured_output": {"products": []}},
    ]
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0,
                                           "\n".join(json.dumps(e) for e in stream), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    searcher = ClaudeCodeDecider("sonnet", tmp_path, version="t", search=True)
    assert searcher("s", "p", {}) == {"products": []}
    assert searcher.last_search.queries == ["MU Ult.Nacht 12St Musterladen"]
    assert searcher.last_search.titles == ["Muster Ultimate Nacht 12 Stück"]

    again = ClaudeCodeDecider("sonnet", tmp_path, version="t", search=True)
    again("s", "p", {})
    assert len(calls) == 1 and again.last_search.queries == ["MU Ult.Nacht 12St Musterladen"], \
        "a cached answer still says what was searched"


class FakeGemini:
    """Stands in for Google's API: answers every call, searching `queries`."""

    def __init__(self, queries):
        self.queries = queries
        self.bodies = []

    def __call__(self, request, timeout=None):
        import io
        import json

        self.bodies.append(json.loads(request.data))
        payload = {"candidates": [{"content": {"parts": [{"text": '{"name": "Kaffeepads"}'}]},
                                   "groundingMetadata": {
                                       "webSearchQueries": self.queries,
                                       "groundingChunks": [{"web": {"title": "example.org"}}]}}],
                   "usageMetadata": {"totalTokenCount": 10}}
        response = io.BytesIO(json.dumps(payload).encode())
        response.__enter__ = lambda *a: response
        response.__exit__ = lambda *a: None
        return response


def test_gemini_searches_with_google_and_stops_at_its_search_budget(monkeypatch, tmp_path):
    import json
    import urllib.request

    import pytest

    from grocery_app.matcher import GeminiDecider, SearchBudgetExceeded

    fake = FakeGemini(["TC Pads 36er GLOBUS", "Tchibo Kaffeepads 36"])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    gemini = GeminiDecider("gemini-test", tmp_path, "t", max_searches=3, api_key="k")
    assert gemini.searches is True

    assert gemini("system", "line one", {"type": "object"}) == {"name": "Kaffeepads"}
    search, copy = fake.bodies
    assert search["tools"] == [{"google_search": {}}]
    assert "generationConfig" not in search, "asked for JSON, Gemini does not search"
    assert search["systemInstruction"]["parts"][0]["text"] == "system"
    assert "tools" not in copy and copy["generationConfig"]["responseJsonSchema"] == \
        {"type": "object"}, "a second call copies the free report into the format"
    assert copy["contents"][0]["parts"][0]["text"] == '{"name": "Kaffeepads"}'
    (cached,) = tmp_path.rglob("*.json")
    assert json.loads(cached.read_text())["searched"] == ["TC Pads 36er GLOBUS",
                                                         "Tchibo Kaffeepads 36"]
    assert gemini.last_search.titles == ["example.org"]

    assert gemini("system", "line one", {"type": "object"}) == {"name": "Kaffeepads"}
    assert len(fake.bodies) == 2, "a cached answer costs nothing"
    gemini("system", "line two", {"type": "object"})
    assert gemini.searched == 4
    with pytest.raises(SearchBudgetExceeded):
        gemini("system", "line three", {"type": "object"})
    assert len(fake.bodies) == 4, "no call once the budget is spent"


def test_a_run_with_a_searcher_lists_the_lines_it_did_not_search_before_any_number():
    from grocery_app.identify import Identity

    said = {"Erdbeeren 400g": Identity("Erdbeeren", "beeren", None, None, None, True, ".",
                                       searched=["Erdbeeren 400g Musterladen"]),
            "MU Wraps": Identity("Wraps", None, None, None, None, True, "."),
            "MILCHKAFFEE": Identity("Milchkaffee", "cafe-imbiss", None, None, None, True, ".")}
    truth = {"lines": [sheet("Erdbeeren 400g", "strawberries", 0),
                       sheet("MU Wraps", "wraps", 1), sheet("MILCHKAFFEE", "café", 2)]}
    report = evaluate_identify(truth, lambda raw, store, others, paid, place=None: said[raw],
                               lambda *a: {"verdict": "right", "reason": "."}, searching=True)
    assert report["search"] == {"due": 2, "searched": 1, "not_searched": ["MU Wraps"],
                                "not_groceries": 1}
    text = format_report(report)
    assert text.index("NOT SEARCHED") < text.index("mistakes"), "said before the numbers"
    assert "searched: Erdbeeren 400g Musterladen" not in text, "right lines are not listed"


def test_only_the_chosen_lines_are_scored_and_the_others_stay_evidence():
    from grocery_app.identify import Identity

    seen = []

    def identifier(raw, store, others, paid, place=None):
        seen.append((raw, others))
        return Identity(raw, None, None, None, None, True, ".")

    truth = {"lines": [sheet("Erdbeeren 400g", "strawberries", 0), sheet("MU Wraps", "wraps", 1)],
             "score_only": {"MU Wraps"}}
    report = evaluate_identify(truth, identifier, lambda *a: {"verdict": "right", "reason": "."})
    assert [line["raw_name"] for line in report["lines"]] == ["MU Wraps"]
    assert seen == [("MU Wraps", ["Erdbeeren 400g", "MU Wraps"])], \
        "the other lines of the receipt are still shown to the reader"


def test_gemini_without_search_is_held_to_the_schema_and_json_is_read_from_text(
        monkeypatch, tmp_path):
    import urllib.request

    from grocery_app.matcher import GeminiDecider, _json_in

    fake = FakeGemini([])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    GeminiDecider("gemini-test", tmp_path, "t", search=False, api_key="k")("s", "p", {"a": 1})
    assert fake.bodies[0]["generationConfig"]["responseJsonSchema"] == {"a": 1}
    assert "tools" not in fake.bodies[0]
    assert _json_in('Here it is:\n```json\n{"products": [], "note": "x"}\n```') == \
        {"products": [], "note": "x"}
    assert _json_in("no json at all") is None


def test_a_search_that_fails_is_no_search_and_the_line_waits():
    from grocery_app.identify import read_line
    from grocery_app.matcher import SearchBudgetExceeded

    def spent(system, prompt, schema):
        raise SearchBudgetExceeded("150 searches made; the limit is 150")

    identity = read_line("Erdbeeren 400g", "Musterladen", answering(), spent)
    assert (identity.unsearched, identity.can_tell) == (True, False)


def test_identify_reads_with_gemini_unless_told_otherwise_and_never_without_a_key(monkeypatch):
    import pytest

    from grocery_app.api.app import identify_decider, identify_searcher
    from grocery_app.matcher import ClaudeCodeDecider, GeminiDecider

    monkeypatch.delenv("GROCERY_IDENTIFY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="neither GEMINI_VERTEX_PROJECT nor GEMINI_API_KEY"):
        identify_decider()

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GROCERY_MAX_SEARCHES", "7")
    reader, searcher = identify_decider(), identify_searcher()
    assert isinstance(reader, GeminiDecider) and reader.searches is False
    assert isinstance(searcher, GeminiDecider) and searcher.searches is True
    assert searcher.max_searches == 7

    monkeypatch.setenv("GROCERY_IDENTIFY", "claude-code")
    assert isinstance(identify_searcher(), ClaudeCodeDecider)
    with pytest.raises(SystemExit, match="unknown identify reader"):
        identify_decider("gpt")


def test_the_matcher_asks_the_model_it_is_told_to_and_claude_stays_the_default(monkeypatch):
    import pytest

    from grocery_app import matcher as matching
    from grocery_app.api.app import matcher_decider
    from grocery_app.matcher import ClaudeCodeDecider, GeminiDecider

    monkeypatch.delenv("GROCERY_MATCHER", raising=False)
    assert isinstance(matcher_decider(), ClaudeCodeDecider)
    monkeypatch.setenv("GROCERY_MATCHER", "gemini")
    with pytest.raises(SystemExit, match="GEMINI_API_KEY"):
        matcher_decider()
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    decider = matcher_decider()
    assert isinstance(decider, GeminiDecider) and decider.searches is False
    assert decider.cache.parts[-2:] == ("gemini-gemini-3.8-flash", matching.PROMPT_VERSION)
    with pytest.raises(SystemExit, match="unknown matcher"):
        matcher_decider("gpt")
