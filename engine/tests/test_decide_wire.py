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
