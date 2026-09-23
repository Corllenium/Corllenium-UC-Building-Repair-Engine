import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

import engine.cli as cli
import engine.fixes.pipeline as fix_pipeline
from engine.fixes.pipeline import FixProfile
from engine.guard.compare import GuardReport
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


def test_cmd_preview_data_classifies_triangulation_diagonals_by_region(tmp_path):
    """R1b: `fix_object` rebuilds `source_faces` with `.astype`, so `_after_edges`' old
    `src[a] is src[b]` identity test could never hold and EVERY triangulation diagonal was drawn
    as a real shape edge. Classified by region id instead, the real edges of the merged cube are
    exactly the edges of its regions' rings, and the 6 quad diagonals are diagonals."""
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_dir = tmp_path / "preview_out"

    cli.cmd_preview_data(snap_dir, out_dir, profile=_FAST)

    data = json.loads((out_dir / f"{m.name}.json").read_text(encoding="utf-8"))
    assert len(data["edges"]["tri_after"]) > 0
    assert data["stats"]["unavoidable_diagonals_after"] > 0

    _obj, mesh, flatness, _mtl = cli._load_snapshot(snap_dir)
    result = fix_pipeline.fix_object(mesh, flatness, _FAST)
    assert (result.face_region_final >= 0).any()
    ring_edges = set()
    for loops in {id(v): v for v in result.rings.values()}.values():
        outer = [int(v) for v in loops["outer"]]
        for a, b in zip(outer, outer[1:] + outer[:1]):
            ring_edges.add((min(a, b), max(a, b)))
    assert data["stats"]["outline_edges_after"] == len(ring_edges)


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


# ---------------------------------------------------------------------------------------------
# M0b: `guard_fail_<index>.png` is for views that actually FAIL. A non-strict run tolerates
# `moved_same_flat` by construction, and writing a triptych for each such view buried the real
# failures under 13-18 pictures of pixels nobody was going to act on.
# ---------------------------------------------------------------------------------------------

def _run_with_tolerated_moves(tmp_path, monkeypatch, *, strict, per_view=7):
    """Run `cmd_fix` on a clean fixture whose guards report `moved_same_flat` pixels and nothing
    else, at the given final strictness."""
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_root = tmp_path / "out"
    real = fix_pipeline.fix_object

    def with_tolerated_moves(mesh, flatness, profile):
        result = real(mesh, flatness, profile)
        views = [replace(v, moved_same_flat=per_view, edge_flicker=0, holes=0,
                         material_changed=0, moved_other=0) for v in result.guard_final.views]
        totals = dict(result.guard_final.totals)
        totals.update(moved_same_flat=per_view * len(views), edge_flicker=0, holes=0,
                      material_changed=0, moved_other=0)
        report = GuardReport(views=views, passed=not strict, totals=totals)
        return replace(result, strict_final=strict, guard_final=report,
                       guard_merge_attempt=report, guard_after_removal=report)

    monkeypatch.setattr(cli, "fix_object", with_tolerated_moves)
    cli.cmd_fix(snap_dir, out_root, accept_slit=True, profile=_FAST)
    return out_root / m.name


def test_tolerated_moved_same_flat_pixels_write_no_failing_view_image(tmp_path, monkeypatch):
    out_dir = _run_with_tolerated_moves(tmp_path, monkeypatch, strict=False)
    assert list(out_dir.glob("guard_fail_*.png")) == []
    assert len(list(out_dir.glob("guard_*.png"))) == 6      # the six axis views, as always


def test_the_same_pixels_do_write_failing_view_images_when_the_run_is_strict(tmp_path, monkeypatch):
    """The counterpart: `moved_same_flat` is a failure under a strict run, so every view that has
    one gets its picture. Only the strictness differs between the two tests."""
    out_dir = _run_with_tolerated_moves(tmp_path, monkeypatch, strict=True)
    assert len(list(out_dir.glob("guard_fail_*.png"))) == len(cli.VIEWS_26)


def _run_with_flicker(tmp_path, monkeypatch, *, per_view, model_px, cap):
    """`cmd_fix` where the two FINAL guards report `per_view` flicker pixels in a `model_px` view
    and the post-removal guard is clean, so only the final cap decides."""
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_root = tmp_path / "out"
    real = fix_pipeline.fix_object
    profile = replace(_FAST, edge_flicker_cap_final=cap)
    zeroed = dict(holes=0, material_changed=0, moved_other=0, moved_same_flat=0)

    def with_flicker(mesh, flatness, profile_in):
        result = real(mesh, flatness, profile_in)
        clean = GuardReport(
            views=[replace(v, edge_flicker=0, **zeroed) for v in result.guard_after_removal.views],
            passed=True, totals=dict(result.guard_after_removal.totals))
        flickering = GuardReport(
            views=[replace(v, edge_flicker=per_view, model_px=model_px, **zeroed)
                   for v in result.guard_final.views],
            passed=True, totals=dict(result.guard_final.totals))
        return replace(result, strict_final=True, guard_after_removal=clean,
                       guard_merge_attempt=flickering, guard_final=flickering)

    monkeypatch.setattr(cli, "fix_object", with_flicker)
    cli.cmd_fix(snap_dir, out_root, accept_slit=False, profile=profile)
    return out_root / m.name


def test_flicker_under_the_final_cap_writes_no_failing_view_image(tmp_path, monkeypatch):
    """Flicker fails only when it is counted against that view's cap, and each guard has its own:
    the post-removal guard always runs at 0.0, the merge attempt and the final guard at
    `edge_flicker_cap_final`. 1 pixel in 10,000 is under a 1e-2 cap (100 px)."""
    out_dir = _run_with_flicker(tmp_path, monkeypatch, per_view=1, model_px=10_000, cap=1e-2)
    assert list(out_dir.glob("guard_fail_*.png")) == []


def test_flicker_over_the_final_cap_does_write_failing_view_images(tmp_path, monkeypatch):
    """The counterpart, differing only in how much flicker there is: 500 pixels in 10,000 is over
    the same 1e-2 cap, so every view is worth a look."""
    out_dir = _run_with_flicker(tmp_path, monkeypatch, per_view=500, model_px=10_000, cap=1e-2)
    assert len(list(out_dir.glob("guard_fail_*.png"))) == len(cli.VIEWS_26)


# ---------------------------------------------------------------------------------------------
# R1c: the preview page reads `stats` and `edges` BY NAME. A key preview-data does not write
# renders as `undefined` -- which is how the page came to carry a hardcoded "guard 0 damaged px"
# instead of the number the guard actually produced. This test reads the page and checks.
# ---------------------------------------------------------------------------------------------

_PREVIEW_PAGE = Path(__file__).resolve().parents[2] / "preview" / "index.html"


def test_preview_data_writes_every_stat_and_edge_list_the_page_reads(tmp_path):
    if not _PREVIEW_PAGE.exists():
        pytest.skip("preview/index.html is not shipped with the engine package")
    source = _PREVIEW_PAGE.read_text(encoding="utf-8")
    # every stat the page shows is interpolated as ${s.<name>}; every edge list it draws is
    # read as d.edges.<name>. A key preview-data does not write renders as `undefined`.
    wanted_stats = set(re.findall(r"\$\{s\.([A-Za-z_][A-Za-z0-9_]*)", source))
    wanted_edges = set(re.findall(r"\bd\.edges\.([A-Za-z_][A-Za-z0-9_]*)", source))
    assert wanted_stats, "the page stopped interpolating stats -- update this test"
    assert wanted_edges, "the page stopped reading d.edges -- update this test"

    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_dir = tmp_path / "preview_out"
    cli.cmd_preview_data(snap_dir, out_dir, profile=_FAST)
    data = json.loads((out_dir / f"{m.name}.json").read_text(encoding="utf-8"))

    assert wanted_stats <= set(data["stats"]), sorted(wanted_stats - set(data["stats"]))
    assert wanted_edges <= set(data["edges"]), sorted(wanted_edges - set(data["edges"]))


def test_preview_page_shows_no_hardcoded_guard_number(tmp_path):
    """The two sentences R1c removes: a literal "guard 0 damaged px", and the claim that the
    region rebuild is a rough preview that flattens vertices. Neither was ever true of the real
    kernel -- `engine.fixes.merge` never moves a vertex -- and the first was not even read from
    the data."""
    if not _PREVIEW_PAGE.exists():
        pytest.skip("preview/index.html is not shipped with the engine package")
    source = _PREVIEW_PAGE.read_text(encoding="utf-8")
    assert "guard 0 damaged px" not in source
    assert "flattens vertices" not in source
    assert "rough preview" not in source
