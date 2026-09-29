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
            "DESTAN": Identity("DESTAN", None, None, None, None, False, "a brand alone")}
    verdicts = {"Erdbeeren 400g": "right", "MU Wraps": "close", "Kekse": "wrong"}

    def judge(system, prompt, schema):
        name = prompt.split("`")[1]
        return {"verdict": verdicts[name], "reason": "test"}

    truth = {"lines": [sheet("Erdbeeren 400g", "strawberries 400 g", 0),
                       sheet("MU Wraps", "Muster tortilla wraps", 1),
                       sheet("Kekse", "biscuits", 2), sheet("DESTAN", "unknown", 3)]}
    report = evaluate_identify(truth, lambda raw, store, others: said[raw], judge)
    assert report["totals"] == {"right": 1, "close": 1, "wrong": 1, "asked": 1}
    text = format_report(report)
    assert "Kekse" in text.split("Wrong:")[1] and "DESTAN" in text.split("Asked:")[1]


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

    def identifier(raw, store, others):
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

