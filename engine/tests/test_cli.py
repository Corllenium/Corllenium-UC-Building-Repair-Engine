import json
from pathlib import Path

import engine.cli as cli
import engine.fixes.pipeline as fix_pipeline
from engine.fixes.pipeline import FixProfile
from engine.io.obj_reader import read_obj
from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import box_with_partition

#: Small render settings: only correctness is under test here, not image fidelity (matches the
#: convention in test_pipeline.py / test_guard.py / test_exposure.py). The default FixProfile's
#: 900x600 x 26-view renders are real-file settings, not something a unit test should pay for.
_FAST = FixProfile(guard_size=(120, 80), n_dirs=32)


def _write_snapshot(tmp_path, mesh):
    """A minimal snapshot directory: <name>.obj + materials.mtl (no textures -- every material
    then counts as flat with no flatness entry, matching engine.pipeline.flat_material_indices)."""
    snap_dir = tmp_path / "snap"
    snap_dir.mkdir()
    write_obj(mesh, snap_dir / f"{mesh.name}.obj")
    lines = []
    for m in mesh.materials:
        lines += [f"newmtl {m}", "Kd 0.8 0.8 0.8", ""]
    (snap_dir / "materials.mtl").write_text("\n".join(lines), encoding="utf-8")
    return snap_dir


def test_load_snapshot_reads_mesh_and_flatness(tmp_path):
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    obj_path, mesh, flatness, mtl_materials = cli._load_snapshot(snap_dir)
    assert obj_path.name == f"{m.name}.obj"
    assert mesh.n_faces == m.n_faces
    assert flatness == {}  # no texture -> no flatness entries (untextured = flat by convention)
    assert set(mtl_materials.keys()) == set(m.materials)


def test_cmd_fix_writes_expected_files_and_exits_zero(tmp_path):
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_root = tmp_path / "out"

    code = cli.cmd_fix(snap_dir, out_root, accept_slit=False, profile=_FAST)

    assert code == 0
    out_dir = out_root / m.name
    fixed = out_dir / f"{m.name}.fixed.obj"
    ngon = out_dir / f"{m.name}.fixed.ngon.obj"
    report_path = out_dir / "report.json"
    assert fixed.exists() and ngon.exists() and report_path.exists()
    assert (out_dir / "materials.mtl").exists()
    for view in cli._AXIS_VIEWS:
        assert (out_dir / f"guard_{cli._axis_name(view)}.png").exists()
    assert len(list(out_dir.glob("guard_*.png"))) == 6

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["tris_before"] == m.n_faces
    assert report["tris_after"] == 12
    assert report["n_removed_hidden"] == 2
    assert len(report["input_sha256"]) == 64
    assert report["guard_final"]["passed"] is True
    assert len(report["guard_final"]["views"]) == 26
    assert report["profile"]["accept_slit"] is False
    assert report["profile"]["guard_size"] == [120, 80]

    back = read_obj(fixed)
    assert back.n_faces == 12


def test_cmd_fix_accept_slit_flag_reaches_the_profile(tmp_path):
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_root = tmp_path / "out"

    code = cli.cmd_fix(snap_dir, out_root, accept_slit=True, profile=_FAST)

    assert code == 0
    report = json.loads((out_root / m.name / "report.json").read_text(encoding="utf-8"))
    assert report["profile"]["accept_slit"] is True


def test_cmd_fix_exits_two_when_a_visible_face_is_wrongly_removed(tmp_path, monkeypatch):
    """A fixture that must fail the guard: guard_feedback is patched to also confirm-remove a
    real, visible outer face (bypassing its own restoration safety net) -- the INDEPENDENT final
    guard (unpatched, comparing the merged result to the pristine original) must still catch the
    resulting hole and fail, and the CLI must exit 2."""

    def bad_guard_feedback(candidates, positions_c, faces, face_material, flat_materials,
                            depth_tol, strict, **kw):
        removed = candidates.copy()
        removed[0] = True  # face 0: a real, visible outer cube face -- not a real candidate
        return removed, [{"round": 0, "candidates_remaining": int(removed.sum()),
                          "failing_pixels": 0, "restored": 0}]

    monkeypatch.setattr(fix_pipeline, "guard_feedback", bad_guard_feedback)

    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_root = tmp_path / "out"

    code = cli.cmd_fix(snap_dir, out_root, accept_slit=False, profile=_FAST)

    assert code == 2
    out_dir = out_root / m.name
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert report["invariants"]["guard_passed"] is False

    # M0: a failing run says WHICH views failed, in pictures as well as numbers -- the six axis
    # views are rarely the ones that catch it.
    fail_pngs = sorted(out_dir.glob("guard_fail_*.png"))
    assert fail_pngs, "a failing run wrote no guard_fail_<index>.png"
    indices = {int(p.stem.split("_")[-1]) for p in fail_pngs}
    assert all(0 <= i < len(cli.VIEWS_26) for i in indices)

    # exactly the views report.json itself calls bad, from any of the three guards
    expected = set()
    for key in ("guard_merge_attempt", "guard_after_removal", "guard_final"):
        guard = report[key]
        if guard is None:
            continue
        for i, v in enumerate(guard["views"]):
            if any(v[k] for k in ("holes", "material_changed", "moved_other", "moved_same_flat",
                                   "edge_flicker")):
                expected.add(i)
    assert indices == expected and expected


def test_cmd_fix_writes_no_failing_view_images_when_the_run_is_clean(tmp_path):
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_root = tmp_path / "out"

    assert cli.cmd_fix(snap_dir, out_root, accept_slit=False, profile=_FAST) == 0

    out_dir = out_root / m.name
    assert list(out_dir.glob("guard_fail_*.png")) == []
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert report["guard_merge_attempt"] is not None
    assert report["guard_merge_attempt"]["passed"] is True
    assert len(report["guard_merge_attempt"]["views"]) == 26


def test_cmd_preview_data_writes_expected_shape(tmp_path):
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_dir = tmp_path / "preview_out"

    code = cli.cmd_preview_data(snap_dir, out_dir, profile=_FAST)

    assert code == 0
    data = json.loads((out_dir / f"{m.name}.json").read_text(encoding="utf-8"))
    for key in ("name", "stats", "materials", "before", "after", "edges"):
        assert key in data
    for key in ("flipped", "thin_sheets", "one_sided_holes_before", "one_sided_holes_after",
                "outline_edges_after", "unavoidable_diagonals_after", "guard_passed",
                "tris_total", "hidden", "after_merged", "regions", "guard_views",
                "guard_model_px", "guard_damaged_px", "gridline_edges",
                "soft_edges", "coplanar_region_borders"):
        assert key in data["stats"]

    assert data["stats"]["hidden"] == 2
    assert data["stats"]["after_merged"] == 12
    assert len(data["before"]["pos"]) == len(data["before"]["mat"]) * 9
    assert len(data["before"]["hidden"]) == len(data["before"]["mat"])
    assert len(data["after"]["pos"]) == len(data["after"]["mat"]) * 9
    assert data["stats"]["outline_edges_after"] > 0
    for edge_key in ("grid", "tri_before", "outline_before", "outline_after", "tri_after",
                     "soft_after"):
        assert edge_key in data["edges"]

    index = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
    assert {"file": f"{m.name}.json", "name": m.name} in index


def test_cmd_preview_data_writes_soft_creases_of_the_shipped_mesh(tmp_path):
    """M2: `edges.soft_after` is the EDGE_SOFT list of the mesh that actually ships, and
    `stats.soft_edges` counts exactly those segments -- 6 floats each (two xyz endpoints)."""
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_dir = tmp_path / "preview_out"

    cli.cmd_preview_data(snap_dir, out_dir, profile=_FAST)

    data = json.loads((out_dir / f"{m.name}.json").read_text(encoding="utf-8"))
    assert len(data["edges"]["soft_after"]) == data["stats"]["soft_edges"] * 6
    assert data["stats"]["coplanar_region_borders"] >= 0


def test_cmd_preview_data_index_replaces_stale_entry_for_the_same_name(tmp_path):
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_dir = tmp_path / "preview_out"

    cli.cmd_preview_data(snap_dir, out_dir, profile=_FAST)
    cli.cmd_preview_data(snap_dir, out_dir, profile=_FAST)  # re-running must not duplicate the entry

    index = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
    assert index.count({"file": f"{m.name}.json", "name": m.name}) == 1


# ---------------------------------------------------------------------------------------------
# main() / argparse -- dispatch only. cmd_fix/cmd_preview_data's own behaviour is covered above;
# the default FixProfile (900x600 x 26 views) is real-file-sized and not something a unit test
# should pay for, so main()'s dispatch is tested by stubbing the commands it calls out to.
# ---------------------------------------------------------------------------------------------

def test_build_parser_fix_defaults():
    args = cli.build_parser().parse_args(["fix", "somedir"])
    assert args.command == "fix"
    assert args.snapshot_dir == "somedir"
    assert args.accept_slit is False
    assert args.out == "data/output"


def test_build_parser_fix_accept_slit_and_out():
    args = cli.build_parser().parse_args(["fix", "somedir", "--accept-slit", "--out", "x/y"])
    assert args.accept_slit is True
    assert args.out == "x/y"


def test_build_parser_preview_data_defaults():
    args = cli.build_parser().parse_args(["preview-data", "somedir"])
    assert args.command == "preview-data"
    assert args.snapshot_dir == "somedir"
    assert args.out == "preview/data"


def test_main_dispatches_to_cmd_fix(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "cmd_fix", lambda snap, out, accept_slit: calls.append((snap, out, accept_slit)) or 0)
    code = cli.main(["fix", "snapdir", "--out", "outdir", "--accept-slit"])
    assert code == 0
    assert calls == [(Path("snapdir"), Path("outdir"), True)]


def test_main_dispatches_to_cmd_preview_data(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "cmd_preview_data", lambda snap, out: calls.append((snap, out)) or 0)
    code = cli.main(["preview-data", "snapdir", "--out", "outdir"])
    assert code == 0
    assert calls == [(Path("snapdir"), Path("outdir"))]


def test_main_returns_the_command_exit_code(monkeypatch):
    monkeypatch.setattr(cli, "cmd_fix", lambda *a, **k: 2)
    assert cli.main(["fix", "snapdir"]) == 2
