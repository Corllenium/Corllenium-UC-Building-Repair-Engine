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
_FAST = FixProfile(guard_size=(120, 80), n_dirs=32, qa_size=(160, 100))


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
                                   "edge_flicker", "grown")):
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
    monkeypatch.setattr(cli, "cmd_fix",
                        lambda snap, out, accept_slit, solidify=True, fragments=True, **_skp:
                        calls.append((snap, out, accept_slit, solidify, fragments)) or 0)
    code = cli.main(["fix", "snapdir", "--out", "outdir", "--accept-slit"])
    assert code == 0
    assert calls == [(Path("snapdir"), Path("outdir"), True, True, True)]

    calls.clear()
    assert cli.main(["fix", "snapdir", "--no-solidify"]) == 0
    assert calls == [(Path("snapdir"), Path("data/output"), False, False, True)]

    calls.clear()
    assert cli.main(["fix", "snapdir", "--keep-fragments"]) == 0
    assert calls == [(Path("snapdir"), Path("data/output"), False, True, False)]


def test_main_dispatches_to_cmd_preview_data(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "cmd_preview_data",
                        lambda snap, out, solidify=True: calls.append((snap, out, solidify)) or 0)
    code = cli.main(["preview-data", "snapdir", "--out", "outdir"])
    assert code == 0
    assert calls == [(Path("snapdir"), Path("outdir"), True)]

    calls.clear()
    assert cli.main(["preview-data", "snapdir", "--no-solidify"]) == 0
    assert calls == [(Path("snapdir"), Path("preview/data"), False)]


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


# ---------------------------------------------------------------------------------------------
# MQ4: the page says what the data says. Three sentences it used to say on its own authority --
# what the AFTER pane contains, what the soft-crease thresholds are, and that every reported
# pixel is damage -- are now read from `stats`.
# ---------------------------------------------------------------------------------------------

def test_preview_page_names_its_soft_crease_thresholds_from_the_data():
    if not _PREVIEW_PAGE.exists():
        pytest.skip("preview/index.html is not shipped with the engine package")
    source = _PREVIEW_PAGE.read_text(encoding="utf-8")
    assert "1-5" not in source                      # the old hard-coded label
    assert "${s.coplanar_angle}" in source and "${s.soft_angle}" in source


def test_preview_page_heading_is_written_from_the_rollback_flag():
    """The static heading used to promise "flat regions rebuilt" even on a run whose merge was
    thrown away and whose AFTER pane is the removal-only fallback."""
    if not _PREVIEW_PAGE.exists():
        pytest.skip("preview/index.html is not shipped with the engine package")
    source = _PREVIEW_PAGE.read_text(encoding="utf-8")
    assert "<h2>AFTER" not in source
    heading = source.split("$('hb').innerHTML")[1].split("$('sa')")[0]
    assert "s.merge_rolled_back" in heading and "merge rolled back" in heading


def test_preview_page_calls_tolerated_flicker_what_it_is():
    if not _PREVIEW_PAGE.exists():
        pytest.skip("preview/index.html is not shipped with the engine package")
    source = _PREVIEW_PAGE.read_text(encoding="utf-8")
    assert "flicker px tolerated" in source
    assert "${s.guard_flicker_px" in source


def test_preview_data_keeps_tolerated_flicker_out_of_the_damaged_count(tmp_path, monkeypatch):
    """`edge_flicker` is what `compare_views` promotes a pixel INTO when the two pictures differ
    only by a boundary that moved less than the tolerance, and the final guard tolerates it up to
    its cap -- so counting it as damage made the page report the opposite of the guard's own
    verdict. 7 flicker pixels per view, nothing else: damaged 0, flicker 7 * 26."""
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    real = fix_pipeline.fix_object
    zeroed = dict(holes=0, material_changed=0, moved_other=0, moved_same_flat=0)

    def with_flicker(mesh, flatness, profile_in):
        result = real(mesh, flatness, profile_in)
        views = [replace(v, edge_flicker=7, **zeroed) for v in result.guard_final.views]
        totals = dict(result.guard_final.totals)
        totals.update(zeroed, edge_flicker=7 * len(views))
        flickering = GuardReport(views=views, passed=True, totals=totals)
        return replace(result, guard_final=flickering)

    monkeypatch.setattr(cli, "fix_object", with_flicker)
    out_dir = tmp_path / "preview_out"
    cli.cmd_preview_data(snap_dir, out_dir, profile=_FAST)
    stats = json.loads((out_dir / f"{m.name}.json").read_text(encoding="utf-8"))["stats"]

    assert stats["guard_flicker_px"] == 7 * len(cli.VIEWS_26)
    assert stats["guard_damaged_px"] == 0
    assert stats["guard_passed"] is True


def _with_border_shift(monkeypatch, count):
    """Make `fix_object` hand the CLI a final guard that measured `count` border-shift pixels."""
    real = fix_pipeline.fix_object

    def patched(mesh, flatness, profile_in):
        result = real(mesh, flatness, profile_in)
        totals = dict(result.guard_final.totals, border_shift=count)
        return replace(result, guard_final=GuardReport(views=result.guard_final.views,
                                                       passed=result.guard_final.passed,
                                                       totals=totals))

    monkeypatch.setattr(cli, "fix_object", patched)


def test_cmd_fix_prints_the_final_guards_border_shift_count(tmp_path, monkeypatch, capsys):
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    _with_border_shift(monkeypatch, 17)

    cli.cmd_fix(snap_dir, tmp_path / "out", accept_slit=False, profile=_FAST)

    guard_line = [line for line in capsys.readouterr().out.splitlines() if "passed=" in line]
    assert len(guard_line) == 1 and "border_shift=17" in guard_line[0]
    report = json.loads((tmp_path / "out" / m.name / "report.json").read_text(encoding="utf-8"))
    assert report["guard_final"]["totals"]["border_shift"] == 17


def test_preview_data_reports_the_final_guards_border_shift(tmp_path, monkeypatch):
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    _with_border_shift(monkeypatch, 17)
    out_dir = tmp_path / "preview_out"

    cli.cmd_preview_data(snap_dir, out_dir, profile=_FAST)

    stats = json.loads((out_dir / f"{m.name}.json").read_text(encoding="utf-8"))["stats"]
    assert stats["guard_border_shift_px"] == 17
    assert stats["guard_damaged_px"] == 0 and stats["guard_flicker_px"] == 0


def test_preview_page_shows_tolerated_border_shift_next_to_the_flicker_count():
    if not _PREVIEW_PAGE.exists():
        pytest.skip("preview/index.html is not shipped with the engine package")
    honest = _PREVIEW_PAGE.read_text(encoding="utf-8").split("$('honest').innerHTML")[1]
    flicker = honest.index("${s.guard_flicker_px")
    shift = honest.index("${s.guard_border_shift_px")
    assert flicker < shift < honest.index("${s.zfight_tie")      # right after the flicker count
    assert "tolerated sub-tolerance border movement" in honest[shift:shift + 200]


def test_preview_data_reports_what_closing_the_slab_added(tmp_path, monkeypatch):
    """The BEFORE pane is the REFERENCE mesh -- the export plus whatever `solidify` added -- so
    the page has to be able to name both counts and what the difference cost."""
    from engine.tests.fixtures.build import slab_with_three_skirts
    m = slab_with_three_skirts()
    snap_dir = _write_snapshot(tmp_path, m)
    out_dir = tmp_path / "preview_out"
    cli.cmd_preview_data(snap_dir, out_dir, profile=_FAST)
    stats = json.loads((out_dir / f"{m.name}.json").read_text(encoding="utf-8"))["stats"]

    assert stats["tris_input"] == m.n_faces
    assert stats["tris_total"] == m.n_faces + 4        # one skirt quad and one bottom quad
    assert stats["skirts_added"] == 1 and stats["bottoms_added"] == 1
    assert stats["invented_vertices"] == 0
    assert stats["n_removed_overlap"] == 0 and stats["n_overlap_pairs_same"] == 0


# ---------------------------------------------------------------------------------------------
# S-M: the BEFORE pane is the ORIGINAL EXPORT again. It was switched to the reference mesh when
# solidify landed, which made a pane labelled "as exported" show geometry the export never had.
# ---------------------------------------------------------------------------------------------

def test_preview_data_before_pane_is_the_original_export_not_the_reference(tmp_path):
    from engine.tests.fixtures.build import slab_with_three_skirts
    m = slab_with_three_skirts()
    snap_dir = _write_snapshot(tmp_path, m)
    out_dir = tmp_path / "preview_out"
    cli.cmd_preview_data(snap_dir, out_dir, profile=_FAST)
    data = json.loads((out_dir / f"{m.name}.json").read_text(encoding="utf-8"))

    assert data["stats"]["tris_input"] == 8
    assert data["stats"]["tris_total"] == 12
    # the export as it arrived: 8 triangles, not the 12 the guards compared against
    assert len(data["before"]["mat"]) == 8
    assert len(data["before"]["pos"]) == 8 * 9
    assert len(data["before"]["hidden"]) == 8
    # ...and what solidify added is its own block, so the page can draw it AS added
    assert len(data["reference"]["mat"]) == 4
    assert len(data["reference"]["pos"]) == 4 * 9
    # the BEFORE pane's own hidden count is the one it draws: over the export's faces only.
    # (`hidden` stays the reference-wide count; on file A the two differ by 96 invented faces.)
    assert data["stats"]["hidden_in_export"] == sum(data["before"]["hidden"])


def test_preview_page_measures_its_reduction_from_the_export_it_shows():
    """The BEFORE pane leads with `tris_input`, so "N % fewer" beside the AFTER count must be
    measured from that number, not from the larger reference the pane no longer draws."""
    if not _PREVIEW_PAGE.exists():
        pytest.skip("preview/index.html is not shipped with the engine package")
    source = _PREVIEW_PAGE.read_text(encoding="utf-8")
    assert "pct(s.after_merged, s.tris_input)" in source
    assert "${s.hidden_in_export" in source


def test_preview_data_before_edges_belong_to_the_original_export(tmp_path):
    """Drawn from the INPUT mesh's own topology: an outline edge of a skirt the export never had
    would otherwise float in the BEFORE pane with no surface under it."""
    from engine.tests.fixtures.build import slab_with_three_skirts
    m = slab_with_three_skirts()
    snap_dir = _write_snapshot(tmp_path, m)
    out_dir = tmp_path / "preview_out"
    cli.cmd_preview_data(snap_dir, out_dir, profile=_FAST)
    edges = json.loads((out_dir / f"{m.name}.json").read_text(encoding="utf-8"))["edges"]

    from engine.pipeline import analyse_topology
    # one segment per edge of the INPUT mesh (15), not of the reference (18): `_before_edges`
    # emits every edge that still has a visible face, and nothing here is removed
    drawn = sum(len(edges[name]) // 6 for name in ("grid", "tri_before", "outline_before"))
    assert drawn == len(analyse_topology(m).table.edges) == 15


def test_preview_page_says_its_before_pane_is_the_original_export():
    if not _PREVIEW_PAGE.exists():
        pytest.skip("preview/index.html is not shipped with the engine package")
    source = _PREVIEW_PAGE.read_text(encoding="utf-8")
    assert "BEFORE &middot; the original export" in source or "BEFORE · the original export" in source
    # and it draws what solidify added as its own, separately labelled thing
    assert "d.reference.pos" in source


# ---------------------------------------------------------------------------------------------
# F2: every `fix` run writes the visual QA sheet under `<run dir>/qa/`.
# ---------------------------------------------------------------------------------------------

def test_cmd_fix_writes_the_21_file_qa_sheet(tmp_path):
    from engine.guard.qa_render import qa_file_names
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_root = tmp_path / "out"

    assert cli.cmd_fix(snap_dir, out_root, accept_slit=False, profile=_FAST) == 0

    qa = out_root / m.name / "qa"
    assert sorted(p.name for p in qa.iterdir()) == sorted(qa_file_names())
    assert len(qa_file_names()) == 21
    for p in qa.iterdir():
        assert p.stat().st_size > 0


# ---------------------------------------------------------------------------------------------
# K2: every `fix` run writes `<run dir>/<name>.fixed.skp` and copies it, as the LATEST, into the
# folder the owner opens in SketchUp (`<repo root>/OBJ FIXED RESULT/` unless `--skp-dir`).
# ---------------------------------------------------------------------------------------------

def _sketchup_or_skip():
    from engine.io.skp_writer import SketchUpUnavailable, load_api
    try:
        load_api()
    except SketchUpUnavailable as exc:
        pytest.skip(f"SketchUp C API unavailable: {exc}")


def _skp_report(out_root, name):
    return json.loads((out_root / name / "report.json").read_text(encoding="utf-8"))["skp"]


def test_build_parser_fix_writes_a_skp_by_default():
    args = cli.build_parser().parse_args(["fix", "somedir"])
    assert args.skp is True and args.skp_dir is None


def test_build_parser_fix_no_skp_and_skp_dir():
    args = cli.build_parser().parse_args(["fix", "somedir", "--no-skp", "--skp-dir", "x/y"])
    assert args.skp is False and args.skp_dir == "x/y"


def test_default_skp_dir_is_obj_fixed_result_next_to_the_engine_package():
    import engine
    assert cli.default_skp_dir() == (Path(engine.__file__).resolve().parent.parent
                                     / "OBJ FIXED RESULT")


def test_main_passes_the_skp_folder_to_cmd_fix(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "cmd_fix", lambda *a, skp=True, skp_dir=None, **k:
                        calls.append((skp, skp_dir)) or 0)
    assert cli.main(["fix", "snapdir"]) == 0
    assert cli.main(["fix", "snapdir", "--skp-dir", "elsewhere"]) == 0
    assert cli.main(["fix", "snapdir", "--no-skp"]) == 0
    assert calls == [(True, cli.default_skp_dir()), (True, Path("elsewhere")),
                     (False, cli.default_skp_dir())]


def test_cmd_fix_writes_the_skp_and_copies_it_into_a_new_skp_folder(tmp_path):
    _sketchup_or_skip()
    from engine.io.skp_writer import read_skp_summary
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_root = tmp_path / "out"
    skp_dir = tmp_path / "owner" / "OBJ FIXED RESULT"       # does not exist yet

    assert cli.cmd_fix(snap_dir, out_root, accept_slit=False, profile=_FAST, skp_dir=skp_dir) == 0

    run_skp = out_root / m.name / f"{m.name}.fixed.skp"
    copy = skp_dir / f"{m.name}.fixed.skp"
    assert run_skp.exists() and copy.read_bytes() == run_skp.read_bytes()
    skp = _skp_report(out_root, m.name)
    assert skp["written"] is True
    assert (skp["path"], skp["copied_to"]) == (str(run_skp), str(copy))
    summary = read_skp_summary(copy)
    # the fixed box: 12 triangles merged into 6 quads -> 6 faces, 12 hard edges
    assert (skp["faces"], skp["edges"], skp["soft_edges"]) == (
        summary["faces"], summary["edges"], summary["soft_edges"]) == (6, 12, 0)
    assert (skp["gridline_edges_softened"], skp["fallback_regions"], skp["reversed_faces"],
            skp["uv_residual_regions"], skp["material_path"]) == (0, [], 0, [], "geometry_input")
    assert skp["sketchup_check_changed"] is False


def test_cmd_fix_replaces_the_previous_skp_in_the_skp_folder(tmp_path):
    _sketchup_or_skip()
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_root = tmp_path / "out"
    skp_dir = tmp_path / "OBJ FIXED RESULT"
    skp_dir.mkdir()
    (skp_dir / f"{m.name}.fixed.skp").write_bytes(b"an older run")

    assert cli.cmd_fix(snap_dir, out_root, accept_slit=False, profile=_FAST, skp_dir=skp_dir) == 0

    run_skp = out_root / m.name / f"{m.name}.fixed.skp"
    assert (skp_dir / run_skp.name).read_bytes() == run_skp.read_bytes()


def test_cmd_fix_failed_run_does_not_replace_previous_skp_in_skp_folder(tmp_path, monkeypatch):
    _sketchup_or_skip()
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_root = tmp_path / "out"
    skp_dir = tmp_path / "OBJ FIXED RESULT"
    skp_dir.mkdir()
    previous = b"the last PASSING run file"
    owner_copy = skp_dir / f"{m.name}.fixed.skp"
    owner_copy.write_bytes(previous)

    # force a failing run by making the guard drop face 0
    import engine.fixes.pipeline as fix_pipeline

    def bad_guard_feedback(candidates, positions_c, faces, face_material, flat_materials,
                           depth_tol, strict, **kw):
        removed = candidates.copy()
        removed[0] = True
        return removed, [{"round": 0, "candidates_remaining": int(removed.sum()),
                          "failing_pixels": 0, "restored": 0}]

    monkeypatch.setattr(fix_pipeline, "guard_feedback", bad_guard_feedback)
    assert cli.cmd_fix(snap_dir, out_root, accept_slit=False, profile=_FAST, skp_dir=skp_dir) == 2

    # owner's copy is kept untouched, and a .fixed.FAILED.skp is written beside it
    assert owner_copy.read_bytes() == previous
    failed_copy = skp_dir / f"{m.name}.fixed.FAILED.skp"
    assert failed_copy.exists()
    skp = _skp_report(out_root, m.name)
    assert skp["copied_to"] == str(failed_copy)


def test_cmd_fix_without_sketchup_still_succeeds_and_says_why(tmp_path, monkeypatch):
    missing = tmp_path / "no_sketchup" / "SketchUpAPI.dll"
    monkeypatch.setenv("FIXER_SKETCHUP_DLL", str(missing))
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_root = tmp_path / "out"
    skp_dir = tmp_path / "OBJ FIXED RESULT"

    assert cli.cmd_fix(snap_dir, out_root, accept_slit=False, profile=_FAST, skp_dir=skp_dir) == 0

    skp = _skp_report(out_root, m.name)
    assert skp["written"] is False and str(missing) in skp["reason"]
    assert not (out_root / m.name / f"{m.name}.fixed.skp").exists()
    assert not skp_dir.exists()


def test_cmd_fix_no_skp_writes_no_skp(tmp_path):
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_root = tmp_path / "out"
    skp_dir = tmp_path / "OBJ FIXED RESULT"

    assert cli.cmd_fix(snap_dir, out_root, accept_slit=False, profile=_FAST, skp=False,
                       skp_dir=skp_dir) == 0

    assert _skp_report(out_root, m.name) == {"written": False, "reason": "disabled by --no-skp"}
    assert not (out_root / m.name / f"{m.name}.fixed.skp").exists()
    assert not skp_dir.exists()


def test_cmd_fix_reports_the_lines_the_skp_hides_and_the_edges_it_shows(tmp_path, capsys):
    _sketchup_or_skip()
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    out_root = tmp_path / "out"

    assert cli.cmd_fix(snap_dir, out_root, accept_slit=False, profile=_FAST) == 0

    [line] = [ln for ln in capsys.readouterr().out.splitlines() if ".fixed.skp:" in ln]
    assert "6 faces, 0 edges hidden, 0 lines left inside surfaces, copied to nowhere" in line
    skp = _skp_report(out_root, m.name)
    assert (skp["coplanar_edges_softened"], skp["tjunction_lines_softened"],
            skp["soft_only_edges"]) == (0, 0, 0)
    # the fixed box: 6 quads, and every one of its 12 edges is where two of them meet at 90 deg
    assert {k: skp[k] for k in ("visible_border_edges", "visible_angled_edges",
                                "visible_shape_edges", "visible_material_borders",
                                "visible_nonmanifold_edges", "visible_lines_inside_surfaces")} == {
        "visible_border_edges": 0, "visible_angled_edges": 0, "visible_shape_edges": 12,
        "visible_material_borders": 0, "visible_nonmanifold_edges": 0,
        "visible_lines_inside_surfaces": 0}


# ---------------------------------------------------------------------------------------------
# Review 2a Minor 1: the guard images and the preview know the guard's newer rules -- a removed
# fragment's pixel is excused only where AFTER shows what was already outside (`exposed_after`),
# per view up to `fragment_removed_cap`, and a pixel where surface APPEARED (`PX_GROWN`) fails.
# ---------------------------------------------------------------------------------------------

def _guard_image_codes(tmp_path, monkeypatch, result, profile):
    """Run `_write_guard_images` for `result` and return `{png name: codes}` it drew."""
    from engine.pipeline import flat_material_indices
    captured = {}
    monkeypatch.setattr(cli, "save_triptych",
                        lambda path, before, after, codes, **kw: captured.update({path.name: codes}))
    ref = result.reference_mesh
    flat = flat_material_indices(ref, {}, profile.flat_texture_std)
    topo = cli.analyse_topology(ref, flat)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
    cli._write_guard_images(ref, result, profile, flat, topo, topo.positions_w - centre, tmp_path)
    return captured


def test_guard_images_excuse_exactly_the_fragment_pixels_the_final_guard_excuses(tmp_path,
                                                                                 monkeypatch):
    """Experiment E-img: the run passes and its final guard excuses the stray's pixels, because
    AFTER shows the slab's top there -- an outside surface on the reference. The images were drawn
    without `exposed_after`, where only the sky excuses a debris pixel, so `guard_-z.png` painted
    those same pixels as damage."""
    from engine.guard.compare import PX_FRAGMENT_REMOVED
    from engine.tests.fixtures.build import slab_with_strays
    profile = replace(_FAST, solidify=False)
    r = fix_pipeline.fix_object(slab_with_strays(), {}, profile)
    assert r.passed and r.guard_final.totals["fragment_removed"] > 0
    codes = _guard_image_codes(tmp_path, monkeypatch, r, profile)
    top = cli.VIEWS_26.index(next(v for v in cli._AXIS_VIEWS if cli._axis_name(v) == "-z"))
    assert r.guard_final.views[top].fragment_removed > 0         # the premise: seen from above
    for view in cli._AXIS_VIEWS:
        drawn = codes[f"guard_{cli._axis_name(view)}.png"]
        assert (int((drawn == PX_FRAGMENT_REMOVED).sum())
                == r.guard_final.views[cli.VIEWS_26.index(view)].fragment_removed)


def test_guard_images_apply_the_per_view_fragment_cap(tmp_path, monkeypatch):
    """Over `fragment_removed_cap` the real guard judges a view's debris pixels as what they are,
    so the image must too, or it shows as excused exactly what made the view fail."""
    from engine.guard.compare import PX_FRAGMENT_REMOVED, PX_MOVED_SAME_FLAT
    from engine.tests.fixtures.build import slab_with_strays
    profile = replace(_FAST, solidify=False)
    r = fix_pipeline.fix_object(slab_with_strays(), {}, profile)
    loose = _guard_image_codes(tmp_path, monkeypatch, r, profile)["guard_-z.png"]
    capped = _guard_image_codes(tmp_path, monkeypatch, r,
                                replace(profile, fragment_removed_cap=0.0))["guard_-z.png"]
    excused = loose == PX_FRAGMENT_REMOVED
    assert excused.any() and not (capped == PX_FRAGMENT_REMOVED).any()
    assert (capped[excused] == PX_MOVED_SAME_FLAT).all()          # the slab's top, 20 in below


def _with_growth(monkeypatch, view, count):
    """Make `fix_object` hand the CLI final and merge guards that counted `count` GROWN pixels in
    `view` and nothing else wrong anywhere."""
    real = fix_pipeline.fix_object

    def grown(mesh, flatness, profile_in):
        result = real(mesh, flatness, profile_in)
        views = [replace(v, grown=count if i == view else 0) for i, v in
                 enumerate(result.guard_final.views)]
        report = GuardReport(views=views, passed=False,
                             totals=dict(result.guard_final.totals, grown=count))
        return replace(result, guard_final=report, guard_merge_attempt=report)

    monkeypatch.setattr(cli, "fix_object", grown)


def test_a_view_failing_only_on_growth_gets_its_failing_view_image(tmp_path, monkeypatch):
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    _with_growth(monkeypatch, view=7, count=3)
    cli.cmd_fix(snap_dir, tmp_path / "out", accept_slit=False, profile=_FAST, skp=False)
    out_dir = tmp_path / "out" / m.name
    assert sorted(p.name for p in out_dir.glob("guard_fail_*.png")) == ["guard_fail_7.png"]
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert report["guard_final"]["views"][7]["grown"] == 3        # ...and report.json says why
    assert report["guard_final"]["views"][7]["edge_flicker_grown"] == 0
    assert "border_shift" in report["guard_final"]["views"][7]


def test_preview_data_counts_grown_pixels_as_damage(tmp_path, monkeypatch):
    """Growth fails the guard like a hole, so the page's damaged count has to include it -- or it
    shows FAILED next to 0 damaged px."""
    m = box_with_partition()
    snap_dir = _write_snapshot(tmp_path, m)
    _with_growth(monkeypatch, view=7, count=5)
    out_dir = tmp_path / "preview_out"
    cli.cmd_preview_data(snap_dir, out_dir, profile=_FAST)
    stats = json.loads((out_dir / f"{m.name}.json").read_text(encoding="utf-8"))["stats"]
    assert stats["guard_passed"] is False
    assert stats["guard_damaged_px"] == 5
