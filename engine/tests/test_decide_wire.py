import json
from engine.decide.jev import ChoiceQ, Decision, NoulQ, ScoreQ, classify_group_names, classify_materials
from engine.decide import wire


def test_question_round_trip_keeps_kind_criteria_and_metadata():
    for q in (NoulQ("is it?", qtype="inv.duplicate", subject="CHTM_5th"),
              ChoiceQ("which?", {"a": None, "b": "bee"}, qtype="mat.category", subject="M1"),
              ScoreQ("how?", ["low", "high"])):
        back = wire.question_from_json(json.loads(json.dumps(wire.question_to_json(q))))
        assert back == q


def test_question_key_ignores_metadata_but_not_text_or_state():
    a = ChoiceQ("which?", {"a": None}, qtype="t1", subject="s1")
    b = ChoiceQ("which?", {"a": None}, qtype="t2", subject="s2")
    assert wire.question_key({"x": 1}, a) == wire.question_key({"x": 1}, b)
    assert wire.question_key({"x": 1}, a) != wire.question_key({"x": 2}, a)
    assert wire.question_key({"x": 1}, a) != wire.question_key({"x": 1}, ChoiceQ("which?!", {"a": None}))
    assert len(wire.question_key({}, a)) == 64


def test_decision_round_trip():
    d = Decision("stone", 0.92, {"stone": 0.92, "metal": 0.08}, "jev", True)
    j = wire.decision_to_json(d, suggestion_id=7)
    assert j["suggestion_id"] == 7
    assert wire.decision_from_json(j) == d


def test_options_of():
    assert wire.options_of(NoulQ("q")) == [True, False]
    assert wire.options_of(ChoiceQ("q", {"a": None, "b": None})) == ["a", "b"]
    assert wire.options_of(ScoreQ("q", ["x", "y", "z"])) == [0, 1, 2]


class _Capture:
    def __init__(self):
        self.questions = {}

    def ask(self, state, questions):
        self.questions.update(questions)
        return {qid: Decision(None, 0.0, {}, "none", False) for qid in questions}


def test_classifiers_tag_every_question_with_qtype_and_subject():
    cap = _Capture()
    classify_group_names([{"name": "CHTM_5th", "tris": 1, "z_min": 0, "z_max": 1, "footprint_building": "CHTM"}], cap)
    classify_materials([{"name": "M1", "texture": "m1.png", "kd": [1, 1, 1]}], cap)
    tags = {(q.qtype, q.subject) for q in cap.questions.values()}
    assert tags == {("inv.building", "CHTM_5th"), ("inv.type", "CHTM_5th"), ("inv.floor", "CHTM_5th"),
                    ("inv.duplicate", "CHTM_5th"), ("mat.category", "M1"), ("mat.trim", "M1")}


def test_key_depends_on_choice_criteria_order():
    ab = ChoiceQ("which?", {"a": None, "b": None})
    ba = ChoiceQ("which?", {"b": None, "a": None})
    assert wire.question_key({}, ab) != wire.question_key({}, ba)


def test_key_is_stable_across_the_question_round_trip():
    for q in (NoulQ("is it?"), ChoiceQ("which?", {"b": "bee", "a": None}, qtype="t", subject="s"),
              ScoreQ("how?", ["low", "high"])):
        back = wire.question_from_json(json.loads(json.dumps(wire.question_to_json(q))))
        assert wire.question_key({"x": 1}, back) == wire.question_key({"x": 1}, q)


def test_key_is_pinned():
    q = ChoiceQ("which?", {"b": "bee", "a": None})
    assert wire.question_key({"x": 1}, q) == "c9f3ffef7452aa75463de0ec3e9077e50ccdf02557ebcbcc39baee8fd472de99"


def test_key_differs_between_kinds_with_the_same_text():
    assert wire.question_key({}, NoulQ("same?")) != wire.question_key({}, ChoiceQ("same?", {"a": None}))


def test_probabilities_are_string_keyed_on_the_wire():
    d = Decision(2, 0.9, {0: 0.1, 2: 0.9}, "jev", True)
    back = wire.decision_from_json(json.loads(json.dumps(wire.decision_to_json(d))))
    assert back.probabilities == {"0": 0.1, "2": 0.9}


def test_unsupported_question_type_raises_type_error():
    import pytest
    with pytest.raises(TypeError, match="unsupported question type str"):
        wire.question_to_json("not a question")


def test_bool_answer_stays_a_bool():
    d = Decision(True, 0.8, {"True": 0.8}, "jev", True)
    back = wire.decision_from_json(json.loads(json.dumps(wire.decision_to_json(d))))
    assert back.answer is True


def test_choice_criteria_order_survives_the_round_trip():
    q = ChoiceQ("which?", {"b": None, "a": "x"})
    back = wire.question_from_json(json.loads(json.dumps(wire.question_to_json(q))))
    assert list(back.criteria) == ["b", "a"]


def test_unknown_question_kind_raises_value_error():
    import pytest
    with pytest.raises(ValueError):
        wire.question_from_json({"kind": "x", "instructions": "q", "criteria": None})


def test_classifier_questions_have_the_right_count_and_kinds():
    cap = _Capture()
    classify_group_names([{"name": "CHTM_5th", "tris": 1, "z_min": 0, "z_max": 1, "footprint_building": "CHTM"}], cap)
    classify_materials([{"name": "M1", "texture": "m1.png", "kd": [1, 1, 1]}], cap)
    assert len(cap.questions) == 6
    for q in cap.questions.values():
        want = NoulQ if q.qtype in ("inv.duplicate", "mat.trim") else ChoiceQ
        assert type(q) is want, q.qtype
