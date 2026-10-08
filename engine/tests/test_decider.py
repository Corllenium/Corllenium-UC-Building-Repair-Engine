"""The Decider (engine/decide/decider.py): owner answer, then rules, then suggestion providers, otherwise the
owner's queue. Fake providers only: no key, no network, nothing written outside tmp_path."""
import hashlib
import json

import pytest

from engine.decide.decider import (
    Answer,
    Decider,
    Question,
    QuestionType,
    RuleProvider,
    question_key,
)

BUILDINGS = (
    ("BRS", "Building BRS"),
    ("CHTM", "Building CHTM"),
    ("MAIN", "Main building"),
)

T_BUILDING = QuestionType(
    "inv.building", "choice", "Which building does this group belong to?", BUILDINGS
)
T_DUP = QuestionType("inv.duplicate", "noul", "Is this group a duplicate of another?", ())
T_PRIORITY = QuestionType("review.priority", "score", "How urgent is this unit?", ("low", "mid", "high"))


def _q(subject="CHTM_5th_floor", **state):
    return Question("inv.building", subject, state or {"name": subject})


def _digest(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------- question_key (convention with the Jev session)


def test_question_key_choice_matches_convention():
    q = _q("G1", name="G1", n=3)
    expected = _digest(
        {
            "state": {"name": "G1", "n": 3},
            "kind": "choice",
            "instructions": "Which building does this group belong to?",
            "criteria": [["BRS", "Building BRS"], ["CHTM", "Building CHTM"], ["MAIN", "Main building"]],
        }
    )
    assert question_key(T_BUILDING, q) == expected


def test_question_key_choice_is_order_sensitive():
    reordered = QuestionType(
        "inv.building", "choice", T_BUILDING.instructions, tuple(reversed(BUILDINGS))
    )
    q = _q("G1")
    assert question_key(T_BUILDING, q) != question_key(reordered, q)


def test_question_key_ignores_qtype_subject_and_state_order():
    other_type = QuestionType("inv.type", "choice", T_BUILDING.instructions, BUILDINGS)
    a = Question("inv.building", "G1", {"a": 1, "b": 2})
    b = Question("inv.type", "G2", {"b": 2, "a": 1})
    assert question_key(T_BUILDING, a) == question_key(other_type, b)


def test_question_key_noul_and_score_criteria():
    assert question_key(T_DUP, Question("inv.duplicate", "G", {"x": 1})) == _digest(
        {"state": {"x": 1}, "kind": "noul", "instructions": T_DUP.instructions, "criteria": None}
    )
    assert question_key(T_PRIORITY, Question("review.priority", "U", {})) == _digest(
        {"state": {}, "kind": "score", "instructions": T_PRIORITY.instructions,
         "criteria": ["low", "mid", "high"]}
    )


def test_question_type_validation():
    with pytest.raises(ValueError):
        QuestionType("Building", "choice", "x", (("a", "b"),))  # not <area>.<question> lowercase
    with pytest.raises(ValueError):
        QuestionType("inv.thing", "choice", "x", tuple((str(i), "d") for i in range(256)))
    QuestionType("inv.thing", "choice", "x", tuple((str(i), "d") for i in range(255)))
    with pytest.raises(ValueError):
        QuestionType("inv.thing", "score", "x", tuple(str(i) for i in range(11)))
    with pytest.raises(ValueError):
        QuestionType("inv.thing", "maybe", "x", ())
