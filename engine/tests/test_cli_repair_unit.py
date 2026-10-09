"""Job P2-E8a item 3: `engine.cli repair-unit --unit <UNIT> --engines E8 --out <dir>`.

It builds the unit's BEFORE as `campus-unit-before` does, runs the repair kernel with E8 only and the site judge on
(`validate_sites=True`), and writes `<unit>.fixed.obj`, `edit_log.jsonl` and `report.json` (sites kept and rolled
back, by reason). `--snapshot <dir>` takes a snapshot folder as the BEFORE instead of a campus unit.
"""
from __future__ import annotations

import json

import pytest

from engine import cli
from engine.fixes.pipeline import FixProfile
from engine.io.obj_reader import read_obj
from engine.io.obj_writer import write_obj
from engine.io.snapshot import sha256_file
from engine.tests.fixtures.build import compartment_with_deep_wall, slab_with_three_skirts

_FAST = FixProfile(guard_size=(120, 80), n_dirs=32)


def _campus(tmp_path, mesh, unit="T-L01"):
    """A one-member campus: `mesh` as a frozen snapshot, and its campus map and source.json written to files."""
    snap = tmp_path / "snaps" / mesh.name
    snap.mkdir(parents=True)
    obj = snap / f"{mesh.name}.obj"
    write_obj(mesh, obj)
    (snap / "materials.mtl").write_text("".join(f"newmtl {m}\nKd 0.8 0.8 0.8\n\n" for m in mesh.materials),
                                        encoding="utf-8")
    row = {"file": obj.name, "group": mesh.name, "dir": str(snap), "sha256": sha256_file(obj)}
    cmap = {"units": [{"unit": unit, "members": [{"group": mesh.name, "file": obj.name, "sha256": row["sha256"],
                                                   "tris": mesh.n_faces, "faces": "all"}]}]}
    paths = {}
    for name, data in (("map", cmap), ("source", {"snapshots": [row]}), ("materials", {"materials": {}})):
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(data), encoding="utf-8")
    return paths, snap


def _run(tmp_path, mesh, **kw):
    paths, snap = _campus(tmp_path, mesh)
    out = tmp_path / "out"
    code = cli.cmd_repair_unit(out, unit="T-L01", engines=["E8"], campus_map=paths["map"], source=paths["source"],
                               materials=paths["materials"], profile=_FAST, **kw)
    return code, out


def test_the_parser_takes_a_unit_or_a_snapshot_and_the_engines():
    args = cli.build_parser().parse_args(["repair-unit", "--unit", "CHTM-L05", "--engines", "E8", "--out", "o"])
    assert args.unit == "CHTM-L05" and args.engines == ["E8"] and str(args.out) == "o" and args.snapshot is None
    assert str(args.materials).replace("\\", "/") == "data/campus/materials.json"
    assert str(args.map).replace("\\", "/") == "data/campus/campus_map.json"
    args = cli.build_parser().parse_args(["repair-unit", "--snapshot", "snapdir", "--engines", "E8", "--out", "o"])
    assert str(args.snapshot) == "snapdir" and args.unit is None
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["repair-unit", "--unit", "U", "--snapshot", "s", "--engines", "E8",
                                       "--out", "o"])


def test_an_engine_that_is_not_e8_is_refused(capsys):
    assert cli.main(["repair-unit", "--unit", "U", "--engines", "E3", "--out", "o"]) == 2
    assert "E3" in capsys.readouterr().err


def test_repair_unit_refuses_a_protected_output(tmp_path, capsys):
    """Review finding 4: an --out in the live export folder is refused by main (exit 2) and by cmd_repair_unit
    (ValueError), before anything is read or written."""
    from pathlib import Path
    protected = Path("D:/PROJECTS/UC ENVIRONMENT BUILDING/x")
    existed = protected.exists()
    assert cli.main(["repair-unit", "--unit", "U", "--engines", "E8", "--out", str(protected),
                     "--map", str(tmp_path / "no_map.json")]) == 2
    assert "protected" in capsys.readouterr().err
    with pytest.raises(ValueError, match="protected"):
        cli.cmd_repair_unit(protected, unit="U", engines=["E8"], campus_map=tmp_path / "no_map.json",
                            source=tmp_path / "no_source.json", materials=tmp_path / "no_materials.json")
    assert protected.exists() == existed, "nothing was created there"


def test_repair_unit_writes_the_fixed_obj_the_edit_log_and_the_report(tmp_path):
    mesh = slab_with_three_skirts()
    code, out = _run(tmp_path, mesh)
    assert code == 0
    fixed = read_obj(out / "T-L01.fixed.obj")
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["unit"] == "T-L01" and report["engines"] == ["E8"]
    assert report["sites"]["built"] == 2 and report["sites"]["kept"] == 2 and report["sites"]["rolled_back"] == 0
    assert report["sites"]["rolled_back_by_reason"] == {}
    assert report["stages"][0]["final"] == "PASS" and report["covered_after_rollback"] == 0
    assert report["before"]["faces"] == mesh.n_faces and report["after"]["faces"] == fixed.n_faces > mesh.n_faces
    assert {p["piece"] for p in report["pieces"]} == {"wall", "bottom"} and all(p["kept"] for p in report["pieces"])
    lines = [json.loads(line) for line in (out / "edit_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sum("check" in line for line in lines) == 2, "one check line per stage: E8 runs E8a then E8b (R10)"
    assert {line["site"] for line in lines if "check" not in line} == {p["site"] for p in report["pieces"]}
    assert (out / "before" / "T-L01.obj").is_file()


def test_repair_unit_reports_a_rolled_back_piece_by_reason(tmp_path):
    mesh = compartment_with_deep_wall()
    code, out = _run(tmp_path, mesh)
    assert code == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["sites"]["built"] == 1 and report["sites"]["kept"] == 0 and report["sites"]["rolled_back"] == 1
    assert report["sites"]["rolled_back_by_reason"] == {"covered": 1}
    (piece,) = report["pieces"]
    assert piece["kept"] is False and set(piece["reasons"]) == {"covered"}
    assert report["covered_after_rollback"] == 0
    assert read_obj(out / "T-L01.fixed.obj").n_faces == mesh.n_faces, "nothing was kept: the BEFORE ships"


def test_repair_unit_takes_a_snapshot_folder_as_the_before(tmp_path):
    mesh = slab_with_three_skirts()
    paths, snap = _campus(tmp_path, mesh)
    out = tmp_path / "out_snap"
    code = cli.cmd_repair_unit(out, snapshot=snap, engines=["E8"], materials=paths["materials"], profile=_FAST)
    assert code == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["snapshot"] == str(snap) and report["sites"]["kept"] == 2
    assert (out / f"{mesh.name}.fixed.obj").is_file()


# ------------------------------------------------------------------------------- review fix round 1

LIVE_EXPORT = "D:/PROJECTS/UC ENVIRONMENT BUILDING/REQUIREMENTS/01-MODEL-EXPORT/CKPT17"


def test_a_snapshot_in_the_live_export_folder_is_refused_and_nothing_is_read(tmp_path, monkeypatch, capsys):
    """Finding 1: the live export folder is read only through engine/io/snapshot.py (AGENTS.md section 3)."""
    reads = []
    monkeypatch.setattr(cli, "_load_snapshot", lambda d: reads.append(d) or (_ for _ in ()).throw(AssertionError))
    materials = tmp_path / "materials.json"
    materials.write_text(json.dumps({"materials": {}}), encoding="utf-8")
    out = tmp_path / "out"
    code = cli.main(["repair-unit", "--snapshot", LIVE_EXPORT, "--engines", "E8", "--out", str(out),
                     "--materials", str(materials)])
    assert code == 2 and reads == [] and not out.exists()
    assert "engine/io/snapshot.py" in capsys.readouterr().err
    with pytest.raises(ValueError, match="protected"):
        cli.cmd_repair_unit(out, snapshot=LIVE_EXPORT, engines=["E8"], materials=materials, profile=_FAST)
    assert reads == []


def test_a_unit_whose_before_differs_from_the_campus_map_stops_with_exit_1(tmp_path, capsys):
    """Finding 2: as campus-unit-before does, a BEFORE whose face count is not the campus map's stops the run."""
    mesh = slab_with_three_skirts()
    paths, _snap = _campus(tmp_path, mesh)
    cmap = json.loads(paths["map"].read_text(encoding="utf-8"))
    cmap["units"][0]["members"][0]["tris"] = mesh.n_faces + 1
    paths["map"].write_text(json.dumps(cmap), encoding="utf-8")
    out = tmp_path / "out"
    code = cli.main(["repair-unit", "--unit", "T-L01", "--engines", "E8", "--out", str(out), "--map", str(paths["map"]),
                     "--source", str(paths["source"]), "--materials", str(paths["materials"])])
    assert code == 1
    assert "DIFFERS from the campus map" in capsys.readouterr().err
    assert not (out / "report.json").exists() and not (out / "T-L01.fixed.obj").exists()
    assert not (out / "edit_log.jsonl").exists(), "the kernel never ran"


from engine.site_judge import SiteJudge as _RealSiteJudge  # noqa: E402  (the class itself, before any patch)

NO_SITES_FACE = 999_999   # a face id in no site's focus


class _FarNoiseJudge:
    """Made in place of `SiteJudge`: the Validator, plus one failing sample no site can be charged with (its face id
    names no face any site touched, boxed or covered, and it lies far off), so the stage's failure is charged to no
    site and the stage is rolled back whole."""

    def __new__(cls, looks, **kw):
        import numpy as np
        from engine.site_judge import FailingSamples, SiteVerdict

        class Noisy(_RealSiteJudge):
            def check(self, after, focus):
                v = super().check(after, focus)
                s = v.samples
                add = lambda a, row: np.concatenate([a, np.asarray(row, dtype=a.dtype)])
                far = FailingSamples(face=add(s.face, [NO_SITES_FACE]), index=add(s.index, [0]),
                                     point=np.vstack([s.point, [[1.0e4, 1.0e4, 1.0e4]]]),
                                     witness=np.vstack([s.witness, [[0.0, 0.0, -1.0]]]), is_dir=add(s.is_dir, [True]),
                                     cluster=add(s.cluster, [len(s.clusters)]), clusters=s.clusters + [{"deleted": 1}])
                return SiteVerdict(failing=v.failing | {(NO_SITES_FACE, 0)}, summary=v.summary, seconds=v.seconds, samples=far)
        return Noisy(looks, **kw)


def test_the_exit_code_is_0_when_the_stage_passed(tmp_path):
    """Finding 3: 0 when E8's stage passed (here every piece kept; NOTHING KEPT, each piece rolled back on its own
    charge, is a passing stage too: `test_repair_unit_reports_a_rolled_back_piece_by_reason`)."""
    code, out = _run(tmp_path, slab_with_three_skirts())
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert code == 0 and report["stages"][0]["final"] == "PASS" and report["exit_code"] == 0


def test_the_exit_code_is_3_when_the_stage_was_rolled_back_whole_and_the_outputs_are_still_written(tmp_path,
                                                                                                    monkeypatch):
    """Finding 3: 3 when the stage was rolled back whole (or ended FAIL); the BEFORE ships, and every file is written."""
    import engine.site_judge
    monkeypatch.setattr(engine.site_judge, "SiteJudge", _FarNoiseJudge)
    mesh = slab_with_three_skirts()
    code, out = _run(tmp_path, mesh)
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    stage = report["stages"][0]
    assert stage["stage_rolled_back"] and stage["unknown"]["samples"] == 1
    assert code == 3 and report["exit_code"] == 3
    assert report["sites"]["kept"] == 0 and read_obj(out / "T-L01.fixed.obj").n_faces == mesh.n_faces
    assert (out / "edit_log.jsonl").is_file()


def test_the_help_documents_the_exit_codes():
    import argparse
    sub = next(a for a in cli.build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    text = " ".join(sub.choices["repair-unit"].format_help().split())
    assert "exit 0: every E8 stage passed" in text
    assert "1: the unit's BEFORE differs from the campus map" in text
    assert "2: a refused input" in text
    assert "3: the stage was rolled back whole" in text
