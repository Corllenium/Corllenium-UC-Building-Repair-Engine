# engine/tests/test_cli_repair_unit_e1.py
import json
from pathlib import Path

from engine import cli
from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import printed, slab_with_debris


def test_cli_repair_unit_e1(tmp_path):
    m = printed(slab_with_debris())
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir()
    write_obj(m, snap_dir / "snap.obj")
    (snap_dir / "materials.mtl").write_text("newmtl m0\n")

    mat_json = tmp_path / "materials.json"
    mat_json.write_text(json.dumps({"looks": {}, "materials": {}}))

    out_dir = tmp_path / "out"
    exit_code = cli.main([
        "repair-unit",
        "--snapshot", str(snap_dir),
        "--engines", "E8a,E3,E1",
        "--out", str(out_dir),
        "--materials", str(mat_json),
    ])
    assert exit_code == 0
    report_file = out_dir / "report.json"
    assert report_file.is_file()
    rep = json.loads(report_file.read_text(encoding="utf-8"))

    assert rep["stages_run"] == ["E8a", "E3", "E1"]
    assert "e1" in rep
    e1 = rep["e1"]
    assert "candidates" in e1
    assert "kept" in e1
    assert "rolled_back" in e1
    assert "visible_debris" in e1
