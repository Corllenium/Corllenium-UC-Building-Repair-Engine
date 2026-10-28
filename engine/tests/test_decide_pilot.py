"""The Jev pilot (engine/decide/pilot.py) and the `decide-pilot` CLI: tiny tmp_path campus, fake decider,
no key, no network, nothing written under data/."""
import json
from types import SimpleNamespace

import pytest

from engine import cli
from engine.decide import jev, pilot
from engine.decide.jev import ChoiceQ, JevDecider, NoulQ, ScoreQ


@pytest.fixture(autouse=True)
def _no_real_env(tmp_path_factory, monkeypatch):
    monkeypatch.setattr(jev, "DEFAULT_ENV_FILE", tmp_path_factory.mktemp("noenv") / "absent.env")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


def _square(z0, z1, x0=0.0):
    pts = [(x0, 0, z0), (x0 + 10, 0, z0), (x0 + 10, 10, z1), (x0, 10, z1)]
    return "".join(f"v {x} {y} {z}\n" for x, y, z in pts) + "f 1 2 3\nf 1 3 4\n"


GROUPS = {
    # name: (obj text, tris)
    "CHTM_5th_floor": _square(500, 520),
    "CHTM_6th_floor": _square(600, 620),
    "Main_Infrustructure_Building": _square(0, 900, x0=100.0),
    "CHTM_stairs": _square(0, 300),
    "ROAD_front": _square(0, 1, x0=500.0),
    "Group137": _square(0, 1, x0=900.0),
}


def _campus(tmp_path):
    snaps = []
    for name, text in GROUPS.items():
        d = tmp_path / "snap" / name
        d.mkdir(parents=True)
        (d / f"{name}.obj").write_text(text, encoding="utf-8")
        snaps.append({"group": name, "file": f"{name}.obj", "dir": str(d), "tris": 2, "sha256": "s" * 64})
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"manifest": [{"group": n, "file": f"{n}.obj", "tris": 2} for n in GROUPS],
                                  "snapshots": snaps}), encoding="utf-8")
    cmap = tmp_path / "campus_map.json"
    cmap.write_text(json.dumps({
        "buildings": {"CHTM": {"groups": ["CHTM_5th_floor", "CHTM_6th_floor", "CHTM_stairs"]},
                      "MAIN_INFRA": {"groups": ["Main_Infrustructure_Building"]}},
        "units": [
            {"unit": "CHTM-L05", "building": "CHTM", "level": "L05", "type": "floor", "members": [{"group": "CHTM_5th_floor"}]},
            {"unit": "CHTM-L06", "building": "CHTM", "level": "L06", "type": "floor", "members": [{"group": "CHTM_6th_floor"}]},
            {"unit": "CHTM-E-stairs", "building": "CHTM", "level": None, "type": "element", "members": [{"group": "CHTM_stairs"}]},
            {"unit": "MAIN_INFRA-L02", "building": "MAIN_INFRA", "level": "L02", "type": "floor",
             "members": [{"group": "Main_Infrustructure_Building"}]},
            {"unit": "MAIN_INFRA-L03", "building": "MAIN_INFRA", "level": "L03", "type": "floor",
             "members": [{"group": "Main_Infrustructure_Building"}]},
            {"unit": "SITE-ROAD_front", "building": "SITE", "level": None, "type": "site", "members": [{"group": "ROAD_front"}]},
        ],
        "excluded": [{"group": "Group137", "reason": "duplicate copy"}]}), encoding="utf-8")
    mats = tmp_path / "materials.json"
    mats.write_text(json.dumps({"materials": {
        f"Mat_{i:02d}": {"map_kd": f"SRC-TEX/Tex_{i}.png" if i % 2 else None, "kd": [0.5, 0.5, 0.5], "look": "x"}
        for i in range(40)}}), encoding="utf-8")
    return source, cmap, mats


def test_truth_comes_from_the_campus_map(tmp_path):
    source, cmap, _ = _campus(tmp_path)
    truth = pilot.load_truth(json.loads(cmap.read_text()), list(GROUPS))
    assert truth["CHTM_5th_floor"] == {"building": "CHTM", "type": "floor", "floor": 5, "duplicate": False}
    assert truth["Main_Infrustructure_Building"]["building"] == "MAIN_INFRA"
    # two units: no single type or floor, so both are unknown (None), the building still known
    assert truth["Main_Infrustructure_Building"]["type"] is None and truth["Main_Infrustructure_Building"]["floor"] is None
    assert truth["CHTM_stairs"]["type"] == "element" and truth["CHTM_stairs"]["floor"] is None
    assert truth["ROAD_front"] == {"building": "SITE", "type": "site", "floor": None, "duplicate": False}
    # in no building and in no unit: SITE, type unknown; the excluded one is the duplicate copy
    assert truth["Group137"] == {"building": "SITE", "type": None, "floor": None, "duplicate": True}


def test_rows_carry_height_and_footprint_building(tmp_path):
    source, cmap, _ = _campus(tmp_path)
    rows = pilot.group_rows(json.loads(source.read_text()))
    by = {r["name"]: r for r in rows}
    assert set(by) == set(GROUPS)
    assert by["CHTM_5th_floor"]["z_min"] == 500 and by["CHTM_5th_floor"]["z_max"] == 520
    assert by["CHTM_5th_floor"]["tris"] == 2
    # CHTM_5th_floor sits inside CHTM_6th_floor's and CHTM_stairs' box (same XY): footprint is CHTM
    assert by["CHTM_5th_floor"]["footprint_building"] == "CHTM"
    assert by["ROAD_front"]["footprint_building"] is None


def test_type_classes_are_compared_in_three_coarse_groups():
    assert pilot.type_matches("floor", "floor") and not pilot.type_matches("floor", "stair")
    assert pilot.type_matches("element", "stair") and pilot.type_matches("site", "road")
    assert not pilot.type_matches("site", "floor")


def test_score_reports_accuracy_coverage_and_accuracy_within_coverage():
    d = lambda a, c, acc=None: SimpleNamespace(answer=a, confidence=c, source="jev", accepted=c >= 0.8 if acc is None else acc)
    pairs = [(d("A", 0.9), "A"), (d("B", 0.9), "A"), (d("A", 0.5), "A"), (d("B", 0.5), "A"), (d("A", 0.9), None)]
    s = pilot.score(pairs, lambda a, t: a == t)
    assert s["n_truth"] == 4 and s["unknown_truth"] == 1 and s["answered"] == 4
    assert s["accuracy"] == 0.5          # 2 of 4 right
    assert s["coverage"] == 0.5          # 2 of 4 accepted
    assert s["accuracy_within_coverage"] == 0.5   # of the 2 accepted, 1 right
    none = lambda: SimpleNamespace(answer=None, confidence=0.0, source="none", accepted=False)
    empty = pilot.score([(none(), "A")], lambda a, t: a == t)
    assert empty["accuracy"] is None and empty["coverage"] == 0.0 and empty["accuracy_within_coverage"] is None


def test_the_pilot_runs_end_to_end_without_a_key_and_writes_none_counts(tmp_path):
    source, cmap, mats = _campus(tmp_path)
    out = tmp_path / "out" / "jev_pilot.json"
    decider = JevDecider(env_file=tmp_path / "absent.env")
    report = pilot.run_pilot(source, mats, cmap, out, decider)
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["available"] is False
    assert on_disk["groups"]["n"] == 6 and on_disk["groups"]["sources"] == {"none": 24}
    assert on_disk["materials"]["n"] == 40 and on_disk["materials"]["sources"] == {"none": 80}
    assert on_disk["groups"]["building"]["accuracy"] is None and on_disk["groups"]["building"]["coverage"] == 0.0
    assert on_disk["groups"]["type"]["unknown_truth"] == 2
    assert on_disk["calls"]["n"] == 0
    assert len(on_disk["materials"]["spot_check"]) == 30
    assert report == on_disk
    assert "TYPESAFE" not in json.dumps(on_disk)


def test_the_pilot_sends_the_texture_file_name_and_kd_never_pixels(tmp_path):
    source, cmap, mats = _campus(tmp_path)
    client = SimpleNamespace(calls=[])

    def system_one(state, questions):
        client.calls.append(questions)
        answers = {}
        for qid, q in questions.items():
            if isinstance(q, NoulQ):
                answers[qid] = SimpleNamespace(noul=0.1)
            elif isinstance(q, ChoiceQ):
                answers[qid] = SimpleNamespace(choice=next(iter(q.criteria)), confidence=0.9,
                                               probabilities={next(iter(q.criteria)): 0.9})
            else:
                answers[qid] = SimpleNamespace(score=5.0, confidence=0.9, probabilities={5: 0.9})
        return SimpleNamespace(answers=answers, model="jev-fake",
                               usage=SimpleNamespace(input_tokens=10, output_tokens=2))
    client.system_one = system_one
    decider = JevDecider(client=client, env_file=tmp_path / "absent.env")
    report = pilot.run_pilot(source, mats, cmap, tmp_path / "o.json", decider)
    sent = json.dumps([[getattr(q, "instructions", "") for q in qs.values()] for qs in client.calls])
    assert "Tex_1.png" in sent and "SRC-TEX" not in sent
    assert report["materials"]["sources"] == {"jev": 80}
    assert report["materials"]["histogram"] == {"glass": 40}
    assert report["calls"]["n"] == len(decider.calls) > 0
    assert report["calls"]["input_tokens"] == 10 * report["calls"]["n"]
    assert report["groups"]["building"]["coverage"] == 1.0


def test_the_cli_runs_without_a_key_and_writes_the_report(tmp_path, capsys):
    source, cmap, mats = _campus(tmp_path)
    out = tmp_path / "jev_pilot.json"
    code = cli.main(["decide-pilot", "--source", str(source), "--materials", str(mats), "--map", str(cmap),
                     "--out", str(out), "--env-file", str(tmp_path / "absent.env")])
    assert code == 0
    printed = capsys.readouterr().out
    assert "no key" in printed.lower() or "not available" in printed.lower()
    assert json.loads(out.read_text(encoding="utf-8"))["groups"]["sources"] == {"none": 24}


# ------------------------------------------------------------------------------- review fix round


def _answering_client(type_label, building_label="CHTM"):
    """A fake client that answers every building with `building_label` and every type with `type_label`."""
    def system_one(state, questions):
        answers = {}
        for qid, q in questions.items():
            if isinstance(q, NoulQ):
                answers[qid] = SimpleNamespace(noul=0.1)
            elif isinstance(q, ChoiceQ):
                label = ("5" if qid.endswith(":floor")           # the floor question is a Choice keyed "0".."15"
                         else building_label if qid.endswith(":building") else type_label)
                answers[qid] = SimpleNamespace(choice=label, confidence=0.9, probabilities={label: 0.9})
            else:
                answers[qid] = SimpleNamespace(score=5.0, confidence=0.9, probabilities={5: 0.9})
        return SimpleNamespace(answers=answers, model="m", usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    return SimpleNamespace(system_one=system_one)


def test_a_strict_floor_vs_non_floor_accuracy_sits_next_to_the_lenient_one(tmp_path):
    source, cmap, mats = _campus(tmp_path)
    # "other" is right for element and site (lenient) but wrong for a floor; stairs/site truth are 4 groups
    decider = JevDecider(client=_answering_client("other"), env_file=tmp_path / "absent.env")
    g = pilot.run_pilot(source, mats, cmap, tmp_path / "o.json", decider)["groups"]
    assert g["type"]["n_truth"] == 4                       # 2 floors, 1 element, 1 site (Main_Infra has two units)
    assert g["type"]["correct"] == 2                       # lenient: "other" counts for element and site
    assert g["type_strict"]["n_truth"] == 4
    assert g["type_strict"]["correct"] == 2                # "other" is non-floor: right for the 2 non-floors
    only_floor = JevDecider(client=_answering_client("floor"), env_file=tmp_path / "absent.env")
    g2 = pilot.run_pilot(source, mats, cmap, tmp_path / "o2.json", only_floor)["groups"]
    assert g2["type"]["correct"] == 2 and g2["type_strict"]["correct"] == 2   # the 2 floors
    stair = JevDecider(client=_answering_client("stair"), env_file=tmp_path / "absent.env")
    g3 = pilot.run_pilot(source, mats, cmap, tmp_path / "o3.json", stair)["groups"]
    assert g3["type"]["correct"] == 1 and g3["type_strict"]["correct"] == 2   # stair is right for element only
    assert "other" in g["type_note"] and "lenient" in g["type_note"]


def test_the_floor_choice_answer_scores_as_an_int_against_the_unit_level(tmp_path):
    source, cmap, mats = _campus(tmp_path)
    decider = JevDecider(client=_answering_client("floor"), env_file=tmp_path / "absent.env")
    g = pilot.run_pilot(source, mats, cmap, tmp_path / "o.json", decider)["groups"]
    assert g["floor"]["n_truth"] == 2                     # CHTM_5th_floor (L05) and CHTM_6th_floor (L06)
    assert g["floor"]["correct"] == 1                     # every floor is answered "5": right for L05 only
    assert g["floor"]["coverage"] == 1.0
    assert g["sources"] == {"jev": 24}                    # no floor answer fell out as an error


def test_each_row_carries_its_footprint_hint_and_agreement_is_counted(tmp_path):
    source, cmap, mats = _campus(tmp_path)
    decider = JevDecider(client=_answering_client("floor", building_label="CHTM"), env_file=tmp_path / "absent.env")
    g = pilot.run_pilot(source, mats, cmap, tmp_path / "o.json", decider)["groups"]
    rows = {r["name"]: r for r in g["rows"]}
    assert rows["CHTM_5th_floor"]["footprint_building"] == "CHTM"
    assert rows["ROAD_front"]["footprint_building"] is None
    h = g["building_hint"]
    assert h["with_hint"] == 3                       # the three CHTM groups share one XY box
    assert h["jev_agrees"] == 3 and h["hint_correct"] == 3
    assert "hint" in h["note"]


def test_the_cli_never_leaks_a_key_through_a_failing_client(tmp_path, monkeypatch, capsys, caplog):
    import logging
    fake_key = "ts-FAKE-CLI-KEY-9876543210-do-not-leak"
    source, cmap, mats = _campus(tmp_path)
    env = tmp_path / ".env"
    env.write_text(f"OTHER=1\nTYPESAFE_API_KEY={fake_key}\n", encoding="utf-8")
    monkeypatch.setattr(jev, "sdk_importable", lambda: True)

    class LeakyClient:
        def system_one(self, state, questions):
            raise RuntimeError(f"401 for key {fake_key} at https://x/?key={fake_key}")
    monkeypatch.setattr(jev, "_make_sdk_client", lambda key, model: LeakyClient())
    out = tmp_path / "jev_pilot.json"
    with caplog.at_level(logging.DEBUG):
        code = cli.main(["decide-pilot", "--source", str(source), "--materials", str(mats), "--map", str(cmap),
                         "--out", str(out), "--env-file", str(env)])
    captured = capsys.readouterr()
    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["groups"]["sources"] == {"error": 24} and report["calls"]["failed"] > 0
    for text in (captured.out, captured.err, out.read_text(encoding="utf-8"), caplog.text):
        assert fake_key not in text
