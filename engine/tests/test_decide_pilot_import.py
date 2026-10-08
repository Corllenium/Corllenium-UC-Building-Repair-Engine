"""decide-import-pilot (engine/decide/pilot_import.py): the paid Jev pilot answers become pending suggestions on
the VPS service. A tiny tmp_path campus, a local fake server, no real network, nothing read from data/."""
import copy
import json

import pytest

from engine import cli
from engine.decide import jev, pilot, pilot_import, wire
from engine.decide.jev import classify_group_names, classify_materials
from engine.tests.test_decide_remote import AUTH, PW, Server


@pytest.fixture(autouse=True)
def _no_real_env(tmp_path_factory, monkeypatch):
    monkeypatch.setattr(jev, "DEFAULT_ENV_FILE", tmp_path_factory.mktemp("noenv") / "absent.env")
    monkeypatch.delenv("UC_DECIDE_PASSWORD", raising=False)
    monkeypatch.delenv("UC_DECIDE_URL", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


@pytest.fixture
def serve():
    servers = []

    def make(reply):
        s = Server(reply)
        servers.append(s)
        return s
    yield make
    for s in servers:
        s.close()


def _square(z0, z1, x0=0.0):
    pts = [(x0, 0, z0), (x0 + 10, 0, z0), (x0 + 10, 10, z1), (x0, 10, z1)]
    return "".join(f"v {x} {y} {z}\n" for x, y, z in pts) + "f 1 2 3\nf 1 3 4\n"


GROUPS = {
    "CHTM_5th_floor": _square(500, 520),
    "CHTM_6th_floor": _square(600, 620),
    "Main_Infrustructure_Building": _square(0, 900, x0=100.0),
    "ROAD_front": _square(0, 1, x0=500.0),
}


def _dec(answer, confidence=0.9, source="jev"):
    return {"answer": answer, "confidence": confidence, "source": source, "accepted": confidence >= 0.8}


def _row(name, building, type_, floor, duplicate, footprint=None):
    return {"name": name, "footprint_building": footprint, "truth": {},
            "building": _dec(building, 0.89), "type": _dec(type_, 0.57), "floor": _dec(floor, 1.0),
            "duplicate": _dec(duplicate, 0.95)}


def _inputs(tmp_path):
    snaps = []
    for name, text in GROUPS.items():
        d = tmp_path / "snap" / name
        d.mkdir(parents=True)
        (d / f"{name}.obj").write_text(text, encoding="utf-8")
        snaps.append({"group": name, "file": f"{name}.obj", "dir": str(d), "tris": 2, "sha256": "s" * 64})
    source = {"manifest": [{"group": n, "file": f"{n}.obj", "tris": 2} for n in GROUPS], "snapshots": snaps}
    materials = {"materials": {
        f"Mat_{i:02d}": {"map_kd": f"SRC-TEX/Tex_{i}.png" if i % 2 else None, "kd": [0.5, 0.25, 0.125], "look": "x"}
        for i in range(6)}}
    rows = [
        _row("CHTM_5th_floor", "CHTM", "floor", 5, False, footprint="CHTM"),
        _row("CHTM_6th_floor", "CHTM", "floor", 6, False, footprint="CHTM"),
        _row("Main_Infrustructure_Building", "MAIN_INFRA", "other", 0, False),
        _row("ROAD_front", "SITE", "road", 0, True),
    ]
    spot = [{"name": "Mat_01", "texture": "Tex_1.png", "kd": [0.5, 0.25, 0.125], "category": "glass",
             "confidence": 0.71, "accepted": False, "trim": False},
            {"name": "Mat_02", "texture": None, "kd": [0.5, 0.25, 0.125], "category": "concrete",
             "confidence": 0.93, "accepted": True, "trim": True}]
    pil = {"model": "jev-latest", "calls": {"models": ["jev-1.13.0"]},
           "groups": {"rows": rows}, "materials": {"spot_check": spot}}
    return source, materials, pil


def _items(tmp_path, mutate=None):
    source, materials, pil = _inputs(tmp_path)
    if mutate:
        mutate(pil)
    return pilot_import.build_import_items(source, materials, pil), (source, materials, pil)


def _by(items, qtype):
    return {it["question"]["subject"]: it for it in items if it["question"]["qtype"] == qtype}


# ------------------------------------------------------------------------------------- the items


def test_each_group_gets_four_items_with_the_answer_mapped_back_to_its_option(tmp_path):
    items, _ = _items(tmp_path)
    groups = [it for it in items if it["question"]["qtype"].startswith("inv.")]
    assert len(groups) == 4 * 4
    assert {it["question"]["subject"] for it in groups} == set(GROUPS)
    assert _by(groups, "inv.building")["Main_Infrustructure_Building"]["answer"] == "MAIN INFRASTRUCTURE"
    assert _by(groups, "inv.building")["CHTM_5th_floor"]["answer"] == "CHTM"
    assert _by(groups, "inv.floor")["CHTM_5th_floor"]["answer"] == "5"
    assert _by(groups, "inv.floor")["ROAD_front"]["answer"] == "0"
    assert _by(groups, "inv.type")["ROAD_front"]["answer"] == "road"
    dup = _by(groups, "inv.duplicate")["ROAD_front"]["answer"]
    assert dup is True and _by(groups, "inv.duplicate")["CHTM_5th_floor"]["answer"] is False
    for it in groups:
        assert set(it) == {"state", "question", "answer", "confidence", "probabilities", "model"}
        assert it["probabilities"] == {} and it["model"] == "jev-1.13.0"
    assert _by(groups, "inv.building")["CHTM_5th_floor"]["confidence"] == 0.89
    # the item is exactly what the service takes: the wire form of the question
    json.dumps(items)
    assert wire.question_from_json(groups[0]["question"]).subject == groups[0]["question"]["subject"]


def test_every_answer_is_one_of_its_questions_options(tmp_path):
    items, _ = _items(tmp_path)
    for it in items:
        assert it["answer"] in wire.options_of(wire.question_from_json(it["question"]))


def test_materials_import_only_the_spot_check_names_and_only_the_category(tmp_path):
    items, _ = _items(tmp_path)
    mats = [it for it in items if it["question"]["qtype"].startswith("mat.")]
    assert {it["question"]["qtype"] for it in mats} == {"mat.category"}
    assert sorted(it["question"]["subject"] for it in mats) == ["Mat_01", "Mat_02"]
    by = _by(mats, "mat.category")
    assert by["Mat_01"]["answer"] == "glass" and by["Mat_01"]["confidence"] == 0.71
    assert by["Mat_02"]["answer"] == "concrete" and by["Mat_02"]["confidence"] == 0.93


def test_a_decision_that_is_not_from_jev_or_has_no_answer_is_skipped(tmp_path):
    def mutate(pil):
        rows = pil["groups"]["rows"]
        rows[0]["type"] = _dec(None, 0.0, source="none")                 # no answer, source none
        rows[1]["floor"]["source"] = "error"                              # an answer, but not from jev
        rows[2]["duplicate"]["answer"] = None
        pil["materials"]["spot_check"][1]["category"] = None
    items, _ = _items(tmp_path, mutate)
    groups = [it for it in items if it["question"]["qtype"].startswith("inv.")]
    assert len(groups) == 16 - 3
    assert "CHTM_5th_floor" not in _by(groups, "inv.type")
    assert "CHTM_6th_floor" not in _by(groups, "inv.floor")
    assert "Main_Infrustructure_Building" not in _by(groups, "inv.duplicate")
    assert sorted(_by(items, "mat.category")) == ["Mat_01"]


def test_a_group_that_is_not_in_the_pilot_gives_no_items(tmp_path):
    items, _ = _items(tmp_path, lambda pil: pil["groups"]["rows"].pop())
    assert "ROAD_front" not in {it["question"]["subject"] for it in items}
    assert len(items) == 12 + 2


def test_an_answer_that_is_not_an_option_is_skipped(tmp_path):
    items, _ = _items(tmp_path, lambda pil: pil["groups"]["rows"][0]["building"].update(answer="ATLANTIS"))
    assert "CHTM_5th_floor" not in _by(items, "inv.building")


def test_the_model_falls_back_to_the_pilot_model_name(tmp_path):
    def mutate(pil):
        pil["calls"]["models"] = []
    items, _ = _items(tmp_path, mutate)
    assert {it["model"] for it in items} == {"jev-latest"}


# ------------------------------------------------------------------------------------- the key


class _Recorder:
    """A decider that records what the classifiers ask and answers none."""

    def __init__(self):
        self.keys = {}

    def ask(self, state, questions):
        for qid, q in questions.items():
            self.keys[(q.qtype, q.subject)] = wire.question_key(state, q)
        return {qid: jev._none() for qid in questions}


def test_each_item_key_equals_the_key_of_a_live_call_through_the_classifiers(tmp_path):
    items, (source, materials, pil) = _items(tmp_path)
    live = _Recorder()
    classify_group_names(pilot.group_rows(source), live)
    spot = pil["materials"]["spot_check"]
    classify_materials([{"name": s["name"], "texture": s["texture"], "kd": s["kd"]} for s in spot], live)
    assert items
    for it in items:
        q = wire.question_from_json(it["question"])
        assert wire.question_key(it["state"], q) == live.keys[(q.qtype, q.subject)]


def test_a_material_key_matches_the_live_ask_the_pilot_makes_from_materials_json(tmp_path):
    """run_pilot asks from materials.json (texture = file name of map_kd, kd), not from the spot-check copy."""
    items, (source, materials, pil) = _items(tmp_path)
    live = _Recorder()
    names = sorted(materials["materials"])
    classify_materials([{"name": n, "texture": (None if not materials["materials"][n]["map_kd"]
                                                  else materials["materials"][n]["map_kd"].split("/")[-1]),
                         "kd": materials["materials"][n]["kd"]} for n in names], live)
    for it in _by(items, "mat.category").values():
        q = wire.question_from_json(it["question"])
        assert wire.question_key(it["state"], q) == live.keys[("mat.category", q.subject)]


def test_the_inputs_are_not_changed(tmp_path):
    source, materials, pil = _inputs(tmp_path)
    before = copy.deepcopy((source, materials, pil))
    pilot_import.build_import_items(source, materials, pil)
    assert (source, materials, pil) == before


# ------------------------------------------------------------------------------------- the CLI


def _files(tmp_path):
    source, materials, pil = _inputs(tmp_path)
    paths = {}
    for name, data in (("source", source), ("materials", materials), ("pilot", pil)):
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        paths[name] = str(p)
    return paths


def _argv(paths, *extra):
    return ["decide-import-pilot", "--source", paths["source"], "--materials", paths["materials"],
            "--pilot", paths["pilot"], *extra]


def test_dry_run_prints_the_counts_and_sends_nothing(serve, tmp_path, monkeypatch, capsys):
    s = serve(lambda req: (200, {"added": 0, "skipped": 0, "invalid": 0}))
    monkeypatch.setenv("UC_DECIDE_PASSWORD", PW)
    paths = _files(tmp_path)
    assert cli.main(_argv(paths, "--url", s.url, "--dry-run")) == 0
    out = capsys.readouterr().out
    assert "groups: 16 items (4 x 4)" in out and "materials: 2 items" in out
    assert s.requests == []
    assert PW not in out


def test_dry_run_needs_neither_a_password_nor_an_https_url(tmp_path, capsys):
    paths = _files(tmp_path)
    assert cli.main(_argv(paths, "--url", "http://unused", "--dry-run")) == 0
    assert "materials: 2 items" in capsys.readouterr().out


def test_the_run_posts_chunks_of_200_with_the_engine_login_and_sums_the_counts(serve, tmp_path, monkeypatch, capsys):
    s = serve(lambda req: (200, {"added": len(req["body"]["items"]) - 1, "skipped": 1, "invalid": 0}))
    monkeypatch.setenv("UC_DECIDE_PASSWORD", PW)
    paths = _files(tmp_path)
    monkeypatch.setattr(pilot_import, "CHUNK", 8)           # 18 items -> 8 + 8 + 2
    assert cli.main(_argv(paths, "--url", s.url)) == 0
    assert [len(r["body"]["items"]) for r in s.requests] == [8, 8, 2]
    for r in s.requests:
        assert r["method"] == "POST" and r["path"] == "/api/decide/import"
        assert r["headers"]["Authorization"] == AUTH
        assert set(r["body"]) == {"items"}
    out = capsys.readouterr().out
    assert "added 15, skipped 3, invalid 0" in out
    assert PW not in out


def test_the_default_chunk_is_200():
    assert pilot_import.CHUNK == 200


def test_the_url_falls_back_to_uc_decide_url_and_else_errors(serve, tmp_path, monkeypatch, capsys):
    s = serve(lambda req: (200, {"added": 18, "skipped": 0, "invalid": 0}))
    monkeypatch.setenv("UC_DECIDE_PASSWORD", PW)
    paths = _files(tmp_path)
    assert cli.main(_argv(paths)) == 2
    assert "UC_DECIDE_URL" in capsys.readouterr().err
    monkeypatch.setenv("UC_DECIDE_URL", s.url)
    assert cli.main(_argv(paths)) == 0
    assert len(s.requests) == 1


def test_the_password_comes_from_the_one_env_file_line(serve, tmp_path, monkeypatch):
    s = serve(lambda req: (200, {"added": 18, "skipped": 0, "invalid": 0}))
    env = tmp_path / "x.env"
    env.write_text(f"OTHER=1\nUC_DECIDE_PASSWORD={PW}\n", encoding="utf-8")
    paths = _files(tmp_path)
    assert cli.main(_argv(paths, "--url", s.url, "--env-file", str(env))) == 0
    assert s.requests[0]["headers"]["Authorization"] == AUTH


def test_no_password_stops_before_any_request(serve, tmp_path, capsys):
    s = serve(lambda req: (200, {"added": 18, "skipped": 0, "invalid": 0}))
    assert cli.main(_argv(_files(tmp_path), "--url", s.url)) == 2
    assert s.requests == []
    assert "UC_DECIDE_PASSWORD" in capsys.readouterr().err


def test_a_remote_http_url_is_refused_without_a_request(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("UC_DECIDE_PASSWORD", PW)
    assert cli.main(_argv(_files(tmp_path), "--url", "http://example.com")) == 2
    err = capsys.readouterr().err
    assert "https" in err and PW not in err


def test_a_422_stops_the_run_with_the_status_only(serve, tmp_path, monkeypatch, capsys):
    s = serve(lambda req: (422, {"detail": f"echo {PW}"}))
    monkeypatch.setenv("UC_DECIDE_PASSWORD", PW)
    monkeypatch.setattr(pilot_import, "CHUNK", 8)
    assert cli.main(_argv(_files(tmp_path), "--url", s.url)) == 2
    cap = capsys.readouterr()
    assert "HTTP 422" in cap.err and PW not in cap.out + cap.err
    assert len(s.requests) == 1                                     # the first failed chunk ends the run


def test_a_malformed_reply_is_an_error_not_a_count(serve, tmp_path, monkeypatch, capsys):
    s = serve(lambda req: (200, {"unexpected": True}))
    monkeypatch.setenv("UC_DECIDE_PASSWORD", PW)
    assert cli.main(_argv(_files(tmp_path), "--url", s.url)) == 2
    assert "BadReply" in capsys.readouterr().err
