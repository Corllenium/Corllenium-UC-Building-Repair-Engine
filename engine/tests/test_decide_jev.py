"""The Jev helper (engine/decide/jev.py): no network, no real key, no real .env.

Every test uses a fake client or a fake key in a tmp_path file. An autouse fixture points the default
`.env` path at a file that does not exist, so no test can open the repo's real one.
"""
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.decide import jev
from engine.decide.jev import (ChoiceQ, Decision, JevDecider, NoulQ, ScoreQ, classify_group_names,
                               classify_materials)

FAKE_KEY = "ts-FAKE-KEY-0123456789-do-not-leak"


@pytest.fixture(autouse=True)
def _no_real_env(tmp_path_factory, monkeypatch):
    monkeypatch.setattr(jev, "DEFAULT_ENV_FILE", tmp_path_factory.mktemp("noenv") / "absent.env")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


def _noul(p):
    return SimpleNamespace(type="noul", noul=p)


def _choice(label, conf, probs=None):
    return SimpleNamespace(type="choice", choice=label, confidence=conf, probabilities=probs or {label: conf})


def _score(value, conf, probs=None):
    return SimpleNamespace(type="score", score=value, confidence=conf, probabilities=probs or {round(value): conf})


class FakeClient:
    """Answers every question through `answer(id, spec)`; records each call."""

    def __init__(self, answer=None, fail_on_call=None, error=None):
        self.answer = answer or self._default
        self.fail_on_call = fail_on_call
        self.error = error
        self.calls = []

    @staticmethod
    def _default(qid, spec):
        if isinstance(spec, NoulQ):
            return _noul(0.9)
        if isinstance(spec, ChoiceQ):
            return _choice(next(iter(spec.criteria)), 0.95)
        return _score(3.0, 0.9)

    def system_one(self, state, questions):
        self.calls.append({"state": state, "questions": dict(questions)})
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            raise (self.error or RuntimeError("boom"))
        answers = {qid: self.answer(qid, spec) for qid, spec in questions.items()}
        return SimpleNamespace(answers=answers, model="jev-fake",
                               usage=SimpleNamespace(input_tokens=100, output_tokens=7))


def _decider(client, tmp_path, **kw):
    return JevDecider(client=client, env_file=tmp_path / "none.env", **kw)


# ---------------------------------------------------------------------------------------- mapping


def test_ask_maps_a_canned_response_into_decisions(tmp_path):
    answers = {
        "n": _noul(0.95),
        "c": _choice("glass", 0.91, {"glass": 0.91, "metal": 0.09}),
        "s": _score(2.4, 0.83, {2: 0.6, 3: 0.4}),
    }
    client = FakeClient(answer=lambda qid, spec: answers[qid])
    out = _decider(client, tmp_path).ask("some text", {
        "n": NoulQ("is it?"), "c": ChoiceQ("which?", {"glass": None, "metal": None}), "s": ScoreQ("how much?", ["a", "b"])})
    assert out["n"] == Decision(True, 0.95, {"yes": 0.95, "no": pytest.approx(0.05)}, "jev", True)
    assert out["c"].answer == "glass" and out["c"].confidence == 0.91
    assert out["c"].probabilities == {"glass": 0.91, "metal": 0.09} and out["c"].source == "jev"
    assert out["s"].answer == 2.4 and out["s"].probabilities == {2: 0.6, 3: 0.4}
    assert out["s"].confidence == 0.83


def test_a_noul_has_no_confidence_so_it_is_derived_from_p_yes(tmp_path):
    client = FakeClient(answer=lambda qid, spec: _noul(0.3))
    d = _decider(client, tmp_path).ask("t", {"q": NoulQ("x")})["q"]
    assert d.answer is False
    assert d.confidence == pytest.approx(0.7)
    assert d.probabilities == {"yes": 0.3, "no": pytest.approx(0.7)}
    assert d.accepted is False  # 0.7 < 0.8


def test_accepted_follows_min_confidence(tmp_path):
    client = FakeClient(answer=lambda qid, spec: _choice("a", {"hi": 0.85, "lo": 0.79, "edge": 0.8}[qid]))
    qs = {k: ChoiceQ("?", {"a": None}) for k in ("hi", "lo", "edge")}
    out = _decider(client, tmp_path).ask("t", qs)
    assert (out["hi"].accepted, out["lo"].accepted, out["edge"].accepted) == (True, False, True)
    strict = _decider(client, tmp_path, min_confidence=0.9).ask("t", qs)
    assert not any(d.accepted for d in strict.values())


def test_a_string_state_is_sent_as_text_and_a_dict_as_it_is(tmp_path):
    client = FakeClient()
    dec = _decider(client, tmp_path)
    dec.ask("hello", {"q": NoulQ("x")})
    dec.ask({"a": 1}, {"q": NoulQ("x")})
    assert client.calls[0]["state"] == {"text": "hello"}
    assert client.calls[1]["state"] == {"a": 1}


def test_a_question_the_response_leaves_out_is_an_error(tmp_path):
    client = FakeClient()
    client.system_one = lambda state, questions: SimpleNamespace(
        answers={}, model="m", usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    d = _decider(client, tmp_path).ask("t", {"q": NoulQ("x")})["q"]
    assert d.source == "error" and d.accepted is False and d.answer is None


# ---------------------------------------------------------------------------------------- batching


def test_45_questions_with_batch_20_make_3_calls(tmp_path):
    client = FakeClient()
    dec = _decider(client, tmp_path, batch=20)
    out = dec.ask("t", {f"q{i}": NoulQ("x") for i in range(45)})
    assert [len(c["questions"]) for c in client.calls] == [20, 20, 5]
    assert len(out) == 45 and all(d.source == "jev" for d in out.values())
    assert len(dec.calls) == 3
    assert dec.calls[0]["input_tokens"] == 100 and dec.calls[0]["output_tokens"] == 7
    assert dec.calls[0]["latency_s"] >= 0 and dec.calls[0]["model"] == "jev-fake"


def test_an_sdk_exception_fails_only_its_batch(tmp_path):
    client = FakeClient(fail_on_call=2)
    out = _decider(client, tmp_path, batch=20).ask("t", {f"q{i}": NoulQ("x") for i in range(45)})
    sources = [out[f"q{i}"].source for i in range(45)]
    assert sources[:20] == ["jev"] * 20
    assert sources[20:40] == ["error"] * 20
    assert sources[40:] == ["jev"] * 5
    assert not any(out[f"q{i}"].accepted for i in range(20, 40))
    assert out["q25"].answer is None and out["q25"].confidence == 0.0


# ---------------------------------------------------------------------------- availability and key


def test_without_a_key_nothing_is_available_and_no_client_is_made(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a client was made without a key")
    monkeypatch.setattr(jev, "_make_sdk_client", boom)
    dec = JevDecider(env_file=tmp_path / "missing.env")
    assert dec.available is False
    out = dec.ask("t", {"a": NoulQ("x"), "b": ChoiceQ("y", {"k": None})})
    assert all(d.source == "none" and d.accepted is False and d.answer is None for d in out.values())
    assert dec.calls == []


def test_without_the_sdk_nothing_is_available_even_with_a_key(tmp_path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", FAKE_KEY)
    monkeypatch.setattr(jev, "sdk_importable", lambda: False)
    dec = JevDecider(env_file=tmp_path / "missing.env")
    assert dec.available is False
    assert dec.ask("t", {"a": NoulQ("x")})["a"].source == "none"


def test_an_injected_client_is_available_without_a_key(tmp_path):
    assert _decider(FakeClient(), tmp_path).available is True


def test_the_environment_key_wins_over_the_env_file(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(jev, "sdk_importable", lambda: True)
    monkeypatch.setattr(jev, "_make_sdk_client", lambda key, model: seen.append(key) or FakeClient())
    env = tmp_path / ".env"
    env.write_text("TYPESAFE_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", "from-env")
    dec = JevDecider(env_file=env)
    assert dec.available
    dec.ask("t", {"a": NoulQ("x")})
    assert seen == ["from-env"]


def test_the_env_file_yields_only_the_key_and_never_enters_os_environ(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(jev, "sdk_importable", lambda: True)
    monkeypatch.setattr(jev, "_make_sdk_client", lambda key, model: seen.append(key) or FakeClient())
    env = tmp_path / ".env"
    env.write_text("# a comment\nOTHER_SECRET=zzz\nSUPABASE_URL=https://x\n"
                   f'  export TYPESAFE_API_KEY = "{FAKE_KEY}"  \nTRAILING=1\n', encoding="utf-8")
    dec = JevDecider(env_file=env)
    assert dec.available
    dec.ask("t", {"a": NoulQ("x")})
    assert seen == [FAKE_KEY]
    assert "TYPESAFE_API_KEY" not in os.environ
    assert "OTHER_SECRET" not in os.environ and "SUPABASE_URL" not in os.environ
    assert FAKE_KEY not in repr(dec) and "zzz" not in repr(dec)


def test_a_single_quoted_or_bare_key_and_an_empty_one(tmp_path):
    p = tmp_path / ".env"
    p.write_text("TYPESAFE_API_KEY='abc123'\n", encoding="utf-8")
    assert jev.read_env_key(p) == "abc123"
    p.write_text("TYPESAFE_API_KEY=abc123 # note\n", encoding="utf-8")
    assert jev.read_env_key(p) == "abc123"
    p.write_text("TYPESAFE_API_KEY=\nOTHER=1\n", encoding="utf-8")
    assert jev.read_env_key(p) is None
    assert jev.read_env_key(tmp_path / "nope.env") is None


def test_no_env_and_no_env_file_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(jev, "sdk_importable", lambda: True)
    assert JevDecider(env_file=tmp_path / "absent.env").available is False


def test_the_default_env_file_is_the_repo_root_one():
    real = Path(jev.__file__).resolve().parents[2] / ".env"
    # only the path is compared; the file is never opened by this test
    assert jev._repo_root_env() == real
    assert (real.parent / "pyproject.toml").is_file()


def test_the_key_appears_in_no_repr_log_or_exception_text(tmp_path, monkeypatch, caplog, capsys):
    monkeypatch.setattr(jev, "sdk_importable", lambda: True)
    leaky = RuntimeError(f"401 for key {FAKE_KEY} at https://x/?key={FAKE_KEY}")
    monkeypatch.setattr(jev, "_make_sdk_client", lambda key, model: FakeClient(fail_on_call=1, error=leaky))
    env = tmp_path / ".env"
    env.write_text(f"TYPESAFE_API_KEY={FAKE_KEY}\n", encoding="utf-8")
    dec = JevDecider(env_file=env)
    with caplog.at_level(logging.DEBUG):
        out = dec.ask("t", {"a": NoulQ("x")})
    assert out["a"].source == "error"
    captured = capsys.readouterr()
    texts = [repr(dec), str(dec), repr(out), caplog.text, repr(dec.calls), repr(vars(dec).get("_client")),
             captured.out, captured.err, repr(out["a"].error)]
    assert not any(FAKE_KEY in t for t in texts)
    # a failure while MAKING the client must not leak either
    def bad_make(key, model):
        raise RuntimeError(f"bad key {key}")
    monkeypatch.setattr(jev, "_make_sdk_client", bad_make)
    dec2 = JevDecider(env_file=env)
    with caplog.at_level(logging.DEBUG):
        out2 = dec2.ask("t", {"a": NoulQ("x")})
    assert out2["a"].source == "error"
    assert FAKE_KEY not in caplog.text and FAKE_KEY not in repr(out2)


def test_a_log_line_names_the_question_source_confidence_and_no_long_state(tmp_path, caplog):
    client = FakeClient()
    with caplog.at_level(logging.DEBUG, logger="engine.decide.jev"):
        _decider(client, tmp_path).ask("x" * 500, {"qid1": NoulQ("x")})
    assert "qid1" in caplog.text and "jev" in caplog.text
    assert "x" * 201 not in caplog.text


# ---------------------------------------------------------------------------------- SDK adapter


def test_the_sdk_adapter_converts_questions_and_passes_the_key_explicitly(monkeypatch):
    pytest.importorskip("typesafe_sdk")
    import typesafe_sdk
    made = {}

    class StubClient:
        def __init__(self, **kw):
            made.update(kw)

        def system_one(self, state, questions):
            made["state"], made["questions"] = state, questions
            return "resp"

    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", StubClient)
    client = jev._make_sdk_client(FAKE_KEY, "jev-latest")
    assert made == {"api_key": FAKE_KEY, "model": "jev-latest"}
    assert "TYPESAFE_API_KEY" not in os.environ
    resp = client.system_one(state={"a": 1}, questions={
        "n": NoulQ("is it?"), "c": ChoiceQ("pick", {"x": "the x", "y": None}), "s": ScoreQ("rate", ["lo", "hi"])})
    assert resp == "resp" and made["state"] == {"a": 1}
    q = made["questions"]
    assert isinstance(q["n"], typesafe_sdk.Noul) and q["n"].instructions == "is it?"
    assert isinstance(q["c"], typesafe_sdk.Choice) and dict(q["c"].criteria) == {"x": "the x", "y": None}
    assert isinstance(q["s"], typesafe_sdk.Score) and list(q["s"].criteria) == ["lo", "hi"]


# ------------------------------------------------------------------------------------ classifiers

ROWS = [
    {"name": "Main_Infrustructure_Building", "tris": 142234, "z_min": 0.0, "z_max": 900.0, "footprint_building": None},
    {"name": "CHTM_5th_floor", "tris": 8000, "z_min": 600.0, "z_max": 740.0, "footprint_building": "CHTM"},
]


def _group_answers(qid, spec):
    label = qid.split(":")[-1]
    if label == "building":
        return _choice("MAIN INFRASTRUCTURE", 0.97) if qid.startswith("0:") else _choice("CHTM", 0.6)
    if label == "type":
        return _choice("floor", 0.9)
    if label == "floor":
        return _score(4.8, 0.85, {5: 0.85, 4: 0.15})
    return _noul(0.1)


def test_classify_group_names_asks_four_typed_questions_per_row(tmp_path):
    client = FakeClient(answer=_group_answers)
    out = classify_group_names(ROWS, _decider(client, tmp_path))
    qs = client.calls[0]["questions"]
    assert len(qs) == 8 and sum(len(c["questions"]) for c in client.calls) == 8
    b = qs["0:building"]
    assert isinstance(b, ChoiceQ) and "MAIN INFRASTRUCTURE" in b.criteria and "SITE" in b.criteria
    assert set(qs["0:type"].criteria) == {"floor", "stair", "roof", "shell", "road", "landscape", "bridge", "other"}
    assert isinstance(qs["0:floor"], ScoreQ) and len(qs["0:floor"].criteria) == 16
    assert isinstance(qs["0:duplicate"], NoulQ)
    assert "Main_Infrustructure_Building" in b.instructions  # self-contained: ids are not sent to the model
    assert out[0]["name"] == "Main_Infrustructure_Building"
    assert out[0]["building"].answer == "MAIN_INFRA" and out[0]["building"].accepted
    assert out[1]["building"].answer == "CHTM" and out[1]["building"].accepted is False
    assert out[0]["type"].answer == "floor" and out[0]["floor"].answer == 4.8
    assert out[0]["duplicate"].answer is False


def test_classify_group_names_without_a_key_is_all_none(tmp_path):
    out = classify_group_names(ROWS, JevDecider(env_file=tmp_path / "absent.env"))
    assert len(out) == 2
    for row in out:
        for k in ("building", "type", "floor", "duplicate"):
            assert row[k].source == "none" and row[k].accepted is False


def test_classify_materials_sends_text_only_and_maps_categories(tmp_path):
    def ans(qid, spec):
        return _choice("glass", 0.92) if qid.endswith(":category") else _noul(0.97)
    client = FakeClient(answer=ans)
    out = classify_materials(["M00_Soft_Cloud", {"name": "Glass_01", "texture": "Glass_01_1K.png", "kd": [0.1, 0.2, 0.3]}],
                             _decider(client, tmp_path))
    qs = client.calls[0]["questions"]
    assert set(qs["0:category"].criteria) == {"glass", "concrete", "metal", "wood", "stone", "plant", "fabric", "paint", "other"}
    assert isinstance(qs["0:trim"], NoulQ)
    assert "Glass_01_1K.png" in qs["1:category"].instructions and "M00_Soft_Cloud" in qs["0:category"].instructions
    assert out[0]["name"] == "M00_Soft_Cloud" and out[1]["name"] == "Glass_01"
    assert out[1]["category"].answer == "glass" and out[1]["trim"].answer is True


def test_classify_materials_without_a_key_is_all_none(tmp_path):
    out = classify_materials(["a", "b"], JevDecider(env_file=tmp_path / "absent.env"))
    assert [r["category"].source for r in out] == ["none", "none"]
    assert [r["trim"].accepted for r in out] == [False, False]


# ------------------------------------------------------------------------------- review fix round


def test_the_footprint_hint_is_shown_with_the_option_label_not_the_inventory_key(tmp_path):
    client = FakeClient()
    rows = [{"name": "G", "tris": 1, "z_min": 0.0, "z_max": 1.0, "footprint_building": "MAIN_INFRA"},
            {"name": "H", "tris": 1, "z_min": 0.0, "z_max": 1.0, "footprint_building": "SCIENCE_A"},
            {"name": "I", "tris": 1, "z_min": 0.0, "z_max": 1.0, "footprint_building": "CHTM"}]
    classify_group_names(rows, _decider(client, tmp_path))
    qs = client.calls[0]["questions"]
    assert "MAIN INFRASTRUCTURE" in qs["0:building"].instructions and "MAIN_INFRA" not in qs["0:building"].instructions
    assert "SCIENCE A" in qs["1:building"].instructions and "SCIENCE_A" not in qs["1:building"].instructions
    assert "footprint of CHTM" in qs["2:building"].instructions


def test_a_client_that_cannot_be_made_fails_every_batch_at_once_after_one_attempt(tmp_path, monkeypatch, caplog):
    made = []
    monkeypatch.setattr(jev, "sdk_importable", lambda: True)

    def bad_make(key, model):
        made.append(1)
        raise RuntimeError(f"bad key {key}")
    monkeypatch.setattr(jev, "_make_sdk_client", bad_make)
    env = tmp_path / ".env"
    env.write_text(f"TYPESAFE_API_KEY={FAKE_KEY}\n", encoding="utf-8")
    dec = JevDecider(env_file=env, batch=5)
    with caplog.at_level(logging.DEBUG):
        out = dec.ask("t", {f"q{i}": NoulQ("x") for i in range(45)})
    assert len(made) == 1
    assert all(d.source == "error" and not d.accepted for d in out.values())
    assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) == 1
    assert FAKE_KEY not in caplog.text and FAKE_KEY not in repr(out)
    out2 = dec.ask("t", {"again": NoulQ("x")})          # still remembered
    assert len(made) == 1 and out2["again"].source == "error"


def test_with_several_key_lines_the_last_one_wins(tmp_path):
    p = tmp_path / ".env"
    p.write_text("TYPESAFE_API_KEY=first\nOTHER=1\nTYPESAFE_API_KEY=second\n", encoding="utf-8")
    assert jev.read_env_key(p) == "second"
    p.write_text("TYPESAFE_API_KEY=first\nTYPESAFE_API_KEY=\n", encoding="utf-8")
    assert jev.read_env_key(p) is None


# ------------------------------------------------------------------ API limits, checked before any call


def test_the_adapter_refuses_a_score_over_ten_levels_before_calling_the_client():
    client = FakeClient()
    adapter = jev._SdkAdapter(client)
    assert jev.MAX_SCORE_LEVELS == 10 and jev.MAX_CHOICE_OPTIONS == 255
    with pytest.raises(ValueError, match="10"):
        adapter.system_one(state={}, questions={"s": ScoreQ("rate", [f"l{i}" for i in range(11)])})
    assert client.calls == []


def test_the_adapter_refuses_a_choice_over_255_options_before_calling_the_client():
    client = FakeClient()
    adapter = jev._SdkAdapter(client)
    with pytest.raises(ValueError, match="255"):
        adapter.system_one(state={}, questions={
            "ok": NoulQ("fine?"), "c": ChoiceQ("pick", {f"o{i}": None for i in range(256)})})
    assert client.calls == []


def test_the_adapter_lets_ten_levels_and_255_options_through():
    pytest.importorskip("typesafe_sdk")
    client = FakeClient()
    jev._SdkAdapter(client).system_one(state={}, questions={
        "s": ScoreQ("rate", [f"l{i}" for i in range(10)]),
        "c": ChoiceQ("pick", {f"o{i}": None for i in range(255)})})
    assert len(client.calls) == 1
