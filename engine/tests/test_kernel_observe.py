"""P1-K2: the observe-only repair kernel.

Item 1 -- `fix_object` is a loop over its seven stages, a pure refactor: running the stages by hand
gives the very same `FixResult` (compared through the report.json bytes `engine.cli` writes and the
shipped mesh's arrays).
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace

import numpy as np
import pytest

import engine.fixes.pipeline as fix_pipeline
from engine import cli
from engine.fixes.merge import MergeResult
from engine.fixes.pipeline import FixProfile, fix_object
from engine.repair.engines.legacy import STAGE_ENGINES, FaceView, observe
from engine.repair.kernel import repair_unit, write_edit_log
from engine.repair.types import RepairContext, UnitState, apply_edits, face_keys
from engine.tests.fixtures.build import (box_with_partition, box_with_partition_and_stitch, cube,
                                         gridded_box, open_box_with_cells, printed,
                                         slab_with_sawtooth_side,
                                         slab_with_strays, slab_with_three_skirts,
                                         slab_with_two_depths,
                                         stacked_duplicate_slab)

_FAST = FixProfile(guard_size=(120, 80), n_dirs=32)
#: the fragment tests' loosened cap (engine/tests/test_fragments.py): the fixture views are tiny
_STRAYS = FixProfile(guard_size=(120, 80), n_dirs=32, solidify=False, fragment_removed_cap=5e-3)


def _reversed_gridded_box():
    m = gridded_box(4, 2.5)
    m.face_v[10] = m.face_v[10][::-1]
    return m


#: (name, mesh builder, profile): between them every stage changes something
FIXTURES = [
    ("box_with_partition", box_with_partition, _FAST),          # hidden faces, merge
    ("reversed_gridded_box", _reversed_gridded_box, _FAST),      # a flip, merge
    ("stacked_duplicate_slab", lambda: stacked_duplicate_slab(nx=3, ny=3), _FAST),  # overlap
    ("slab_with_strays", lambda: printed(slab_with_strays()), _STRAYS),  # fragments, slivers
    ("slab_with_three_skirts", slab_with_three_skirts, _FAST),  # solidify adds a skirt and a bottom
    ("slab_with_sawtooth_side", slab_with_sawtooth_side, _FAST),  # ...and replaces broken side pieces
    ("slab_with_two_depths", slab_with_two_depths, _FAST),      # ...and invents points
    ("box_with_partition_and_stitch", box_with_partition_and_stitch, _FAST),  # E3 + E1 in pass 1
    # pass 2: the two deep-partition triangles are slit faces, removed under the colour-tolerant
    # guard and observed through pass 1's subset view
    ("open_box_with_cells_slit", open_box_with_cells,
     FixProfile(guard_size=(120, 80), n_dirs=32, accept_slit=True, solidify=False)),
    # the fragment pass switched off: the strays stay, the stage observes nothing
    ("slab_with_strays_kept", lambda: printed(slab_with_strays()),
     FixProfile(guard_size=(120, 80), n_dirs=32, solidify=False, fragment_removed_cap=5e-3,
                accept_fragments=False)),
    # the merge rolled back (`not_converged`, as in test_pipeline.py): the shipped mesh is the
    # unmerged one and the merge stage observes nothing
    ("gridded_box_merge_rolled_back", lambda: gridded_box(4, 2.5), _FAST),
]


def _not_converged_merge(monkeypatch):
    real_merge_regions = fix_pipeline.merge_regions

    def not_converged(mesh, topo, flat_materials=frozenset(), **kw):
        real = real_merge_regions(mesh, topo, flat_materials, **kw)
        report = dict(real.report)
        report["converged"] = False
        return MergeResult(mesh=real.mesh, source_faces=real.source_faces, report=report)

    monkeypatch.setattr(fix_pipeline, "merge_regions", not_converged)


def _prepare(name, monkeypatch):
    """Patches a FIXTURES case needs before it runs."""
    if name == "gridded_box_merge_rolled_back":
        _not_converged_merge(monkeypatch)


def _report_bytes(tmp_path, mesh, result, profile) -> bytes:
    from engine import cli
    obj = tmp_path / "input.obj"
    obj.write_bytes(b"same input for both")
    return json.dumps(cli._build_report(mesh.name, obj, mesh, result, profile), indent=2).encode()


def _same_mesh_arrays(a, b):
    for field in ("positions", "uvs", "normals", "face_v", "face_vt", "face_vn", "face_material",
                  "face_line"):
        assert np.array_equal(getattr(a, field), getattr(b, field)), field
    assert a.materials == b.materials


# ----------------------------------------------------------------------- item 1: the stages


def test_fix_object_is_the_seven_stages_in_order():
    assert [name for name, _ in fix_pipeline.FIX_STAGES] == [
        "solidify", "hidden", "slit", "fragments", "orientation", "overlap", "merge"]


@pytest.mark.parametrize("name, build, profile", FIXTURES, ids=[f[0] for f in FIXTURES])
def test_fix_stages_compose_into_fix_objects_result(tmp_path, monkeypatch, name, build, profile):
    """`FIX_STAGES`, `start_fix` and `finish_fix` compose: running them by hand gives
    `fix_object`'s result. `fix_object` IS this loop, so this is NOT the proof that splitting it
    changed nothing -- that proof is the unchanged engine suite and the golden units' sha256s."""
    _prepare(name, monkeypatch)
    mesh = build()
    expected = fix_object(mesh, {}, profile)

    state = fix_pipeline.start_fix(mesh, {}, profile)
    for _, stage in fix_pipeline.FIX_STAGES:
        state = stage(state)
    by_hand = fix_pipeline.finish_fix(state)

    assert _report_bytes(tmp_path, mesh, by_hand, profile) == _report_bytes(tmp_path, mesh, expected, profile)
    _same_mesh_arrays(by_hand.mesh, expected.mesh)
    _same_mesh_arrays(by_hand.reference_mesh, expected.reference_mesh)
    assert [s.tolist() for s in by_hand.source_faces] == [s.tolist() for s in expected.source_faces]


# --------------------------------------------- item 2: observed edits, legacy engines, kernel

def _keys(mesh):
    return face_keys(mesh, {})


def _view(mesh):
    return FaceView(mesh, None, {})


def _applied_keys(before_view, edits):
    applied, _ = apply_edits(before_view.as_mesh(), edits)
    return Counter(_keys(applied))


def _removed_added(edits):
    removed, added = Counter(), Counter()
    for e in edits:
        removed.update(e.evidence["removed_keys"])
        added.update(e.evidence["added_keys"])
    return removed, added


def _with_faces(mesh, face_v, face_material=None, positions=None):
    n = len(face_v)
    face_v = np.asarray(face_v, np.int64)
    return replace(
        mesh, positions=mesh.positions if positions is None else positions,
        face_v=face_v, face_vt=np.full((n, 3), -1, np.int64), face_vn=np.full((n, 3), -1, np.int64),
        face_material=(np.zeros(n, np.int64) if face_material is None
                       else np.asarray(face_material, np.int64)),
        face_line=np.arange(n, dtype=np.int64))


def test_observe_names_a_removal_a_flip_and_an_add():
    before = cube()
    fv = before.face_v.copy()
    new_face = [int(fv[0][0]), int(fv[2][1]), int(fv[5][2])]
    after_v = [fv[1][::-1], *fv[2:], new_face]                     # 0 gone, 1 flipped, one new
    after = _with_faces(before, after_v, face_material=before.face_material[[1, *range(2, 12), 0]])

    edits = observe(_view(before), _view(after), stage="test", site=0, engine="E1")

    kinds = {e.kind: e for e in edits}
    assert sorted(kinds) == ["add", "flip", "remove"]
    assert kinds["flip"].faces == (1,) and kinds["remove"].faces == (0,)
    assert kinds["add"].faces == () and kinds["add"].new_faces.tolist() == [new_face]
    assert all(e.engine == "E1" and e.new_points is None for e in edits)
    assert _applied_keys(_view(before), edits) == Counter(_keys(after))


def test_observe_counts_stacked_duplicates_as_a_multiset():
    base = cube()
    fv = base.face_v
    before = _with_faces(base, [fv[0], fv[0], fv[0], fv[1]])        # face 0 stacked three times
    after = _with_faces(base, [fv[0], fv[1]])

    edits = observe(_view(before), _view(after), stage="test", site=0, engine="E4")

    assert [(e.kind, len(e.faces)) for e in edits] == [("remove", 2)]
    assert set(edits[0].faces) <= {0, 1, 2}
    removed, added = _removed_added(edits)
    assert sum(removed.values()) == 2 and not added
    assert _applied_keys(_view(before), edits) == Counter(_keys(after))


def test_observe_a_solidify_add_carries_its_new_points_and_no_other_engine_may():
    before = cube()
    extra = np.array([[0.0, 0.0, -5.0], [10.0, 0.0, -5.0]])
    positions = np.vstack([before.positions, extra])
    n = len(before.positions)
    after = _with_faces(before, [*before.face_v, [0, n, n + 1]], positions=positions,
                        face_material=[*before.face_material, 0])

    edits = observe(_view(before), _view(after), stage="solidify", site=0, engine="E8")

    assert [(e.engine, e.kind) for e in edits] == [("E8", "add")]
    assert edits[0].new_points.tolist() == extra.tolist()
    assert edits[0].new_faces.tolist() == [[0, n, n + 1]]
    assert _applied_keys(_view(before), edits) == Counter(_keys(after))
    with pytest.raises(ValueError, match="new_points"):
        observe(_view(before), _view(after), stage="merge", site=6, engine="E7")


def test_observe_a_retriangulation_as_cut_edits_without_new_points():
    before = gridded_box(2, 2.5)
    # re-triangulate the first quad across its other diagonal
    a, b, c = (int(v) for v in before.face_v[0])
    d = next(int(v) for v in before.face_v[1] if v not in (a, b, c))
    after_v = [[a, b, d], [b, c, d], *before.face_v[2:]]
    after = _with_faces(before, after_v, face_material=before.face_material)

    edits = observe(_view(before), _view(after), stage="merge", site=6, engine="E7", mode="cut")

    assert edits and all(e.engine == "E7" and e.new_points is None for e in edits)
    assert {e.kind for e in edits} == {"cut"}
    assert _applied_keys(_view(before), edits) == Counter(_keys(after))


def test_a_subset_view_keys_and_materialises_only_its_faces():
    m = cube()
    view = FaceView(m, np.array([3, 1, 7]), {})
    assert view.n_faces == 3
    assert view.keys == [_keys(m)[i] for i in (3, 1, 7)]
    assert view.as_mesh().face_v.tolist() == m.face_v[[3, 1, 7]].tolist()


def _kernel(mesh, profile, **kw):
    unit = UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=profile, decider=None, validator=None)
    return repair_unit(unit, ctx, flatness={}, **kw), ctx


@pytest.mark.parametrize("name, build, profile", FIXTURES, ids=[f[0] for f in FIXTURES])
def test_the_kernel_gives_fix_objects_report_and_mesh(tmp_path, monkeypatch, name, build, profile):
    _prepare(name, monkeypatch)
    mesh = build()
    expected = fix_object(mesh, {}, profile)
    got, ctx = _kernel(build(), profile)

    assert _report_bytes(tmp_path, mesh, got.result, profile) == _report_bytes(tmp_path, mesh, expected, profile)
    _same_mesh_arrays(got.mesh, expected.mesh)
    assert got.mesh is got.result.mesh
    assert ctx.log == got.edits


@pytest.mark.parametrize("name, build, profile", FIXTURES, ids=[f[0] for f in FIXTURES])
def test_every_stage_accounts_for_every_face(monkeypatch, name, build, profile):
    _prepare(name, monkeypatch)
    mesh = build()
    got, _ = _kernel(mesh, profile)

    assert [st.stage for st in got.stages] == [n for n, _ in fix_pipeline.FIX_STAGES]
    for st in got.stages:
        removed, added = _removed_added(st.edits)
        n_removed, n_added = sum(removed.values()), sum(added.values())
        # input faces - removes + adds = output faces
        assert st.before.n_faces - n_removed + n_added == st.after.n_faces, st.stage
        # output key multiset = input - removed + added
        assert not (removed - Counter(st.before.keys)), st.stage
        assert Counter(st.before.keys) - removed + added == Counter(st.after.keys), st.stage
        # ...and the edits, applied, rebuild exactly that multiset
        assert _applied_keys(st.before, st.edits) == Counter(st.after.keys), st.stage
    for prev, nxt in zip(got.stages, got.stages[1:]):
        assert prev.after.keys == nxt.before.keys
    # in total, from the input to the shipped mesh, edit by edit (a key one stage adds, a later
    # one may remove: Counter subtraction clamps at zero, so the order matters)
    keys, n = Counter(_keys(mesh)), mesh.n_faces
    for edit in got.edits:
        removed, added = Counter(edit.evidence["removed_keys"]), Counter(edit.evidence["added_keys"])
        assert not (removed - keys)
        keys = keys - removed + added
        n += sum(added.values()) - sum(removed.values())
    assert keys == Counter(_keys(got.mesh)) and n == got.mesh.n_faces


#: solidify may also show a flip: on the real sidewalks and CHTM 5th a rebuilt side piece is
#: sometimes an input face with its winding reversed (1-2 faces per unit)
ALLOWED = {"solidify": ({"E8"}, {"add", "remove", "flip"}), "hidden": ({"E3", "E1"}, {"remove"}),
           "slit": ({"E3"}, {"remove"}), "fragments": ({"E1"}, {"remove"}),
           "orientation": ({"E2"}, {"flip"}), "overlap": ({"E4"}, {"remove"}),
           "merge": ({"E7"}, {"cut", "remove", "add"})}


@pytest.mark.parametrize("name, build, profile", FIXTURES, ids=[f[0] for f in FIXTURES])
def test_each_stage_logs_under_its_engine(monkeypatch, name, build, profile):
    _prepare(name, monkeypatch)
    got, _ = _kernel(build(), profile)
    assert dict(STAGE_ENGINES) == {"solidify": "E8", "hidden": "E3+E1", "slit": "E3",
                                   "fragments": "E1", "orientation": "E2", "overlap": "E4",
                                   "merge": "E7"}
    for site, st in enumerate(got.stages):
        engines, kinds = ALLOWED[st.stage]
        assert {e.engine for e in st.edits} <= engines, st.stage
        assert {e.kind for e in st.edits} <= kinds, st.stage
        assert all(e.site == site for e in st.edits)
        if st.stage != "solidify":
            assert all(e.new_points is None for e in st.edits), st.stage


def _stage(got, name):
    return next(st for st in got.stages if st.stage == name)


def _n(edits, engine=None, kind=None):
    return sum(len(e.evidence["removed_keys"]) for e in edits
               if (engine is None or e.engine == engine) and (kind is None or e.kind == kind))


def test_pass_one_labels_hidden_faces_e3_and_zero_area_faces_e1():
    got, _ = _kernel(box_with_partition_and_stitch(), _FAST)
    hidden = _stage(got, "hidden").edits
    assert _n(hidden, "E3", "remove") == got.result.n_removed_hidden == 2
    assert _n(hidden, "E1", "remove") == got.result.n_zero_area_dropped == 1


def test_the_flip_overlap_fragment_and_solidify_stages_show_what_they_did():
    flipped, _ = _kernel(_reversed_gridded_box(), _FAST)
    assert _n(_stage(flipped, "orientation").edits, "E2", "flip") == int(flipped.result.flipped.sum()) == 1

    stacked, _ = _kernel(stacked_duplicate_slab(nx=3, ny=3), _FAST)
    assert _n(_stage(stacked, "overlap").edits, "E4", "remove") == stacked.result.n_removed_overlap > 0

    strays, _ = _kernel(printed(slab_with_strays()), _STRAYS)
    assert (_n(_stage(strays, "fragments").edits, "E1", "remove")
            == int(strays.result.removed_fragments.sum()) == 2)

    for build in (slab_with_three_skirts, slab_with_sawtooth_side, slab_with_two_depths):
        slab, _ = _kernel(build(), _FAST)
        edits = _stage(slab, "solidify").edits
        adds = [e for e in edits if e.kind == "add"]
        replaced = int(slab.result.replaced_input.sum())
        assert adds and all(e.engine == "E8" for e in edits)
        assert _n(edits, "E8", "remove") == replaced
        assert (sum(len(e.new_faces) for e in adds)
                == slab.result.reference_mesh.n_faces - (build().n_faces - replaced))
        n_points = sum(0 if e.new_points is None else len(e.new_points) for e in adds)
        # only solidify invents points; the ones its kept faces use travel with those faces
        assert n_points <= slab.result.solidify_report["invented_vertices"]
        assert (n_points > 0) == (build is slab_with_two_depths)

        merged = _stage(slab, "merge").edits
        assert merged and {e.kind for e in merged} <= {"cut", "remove", "add"}
        assert all(e.engine == "E7" and e.new_points is None for e in merged)
        assert (replaced == 4) == (build is slab_with_sawtooth_side)  # its broken side pieces


def test_the_slit_stage_logs_e3_removes_named_in_pass_ones_subset_view():
    profile = FixProfile(guard_size=(120, 80), n_dirs=32, accept_slit=True, solidify=False)
    got, _ = _kernel(open_box_with_cells(), profile)
    slit = _stage(got, "slit")

    assert got.result.n_removed_slit == 2
    assert [(e.engine, e.kind) for e in slit.edits] == [("E3", "remove")]
    assert slit.before.ids is not None                        # pass 1's subset of the reference
    removed_reference = slit.before.mesh_ids(slit.edits[0].faces)
    assert sorted(removed_reference.tolist()) == np.flatnonzero(got.result.removed_slit).tolist()
    ref_keys = _keys(got.result.reference_mesh)
    assert Counter(slit.edits[0].evidence["removed_keys"]) == Counter(
        ref_keys[i] for i in np.flatnonzero(got.result.removed_slit))


def test_with_the_fragment_pass_off_the_fragment_stage_logs_nothing():
    profile = FixProfile(guard_size=(120, 80), n_dirs=32, solidify=False,
                         fragment_removed_cap=5e-3, accept_fragments=False)
    got, _ = _kernel(printed(slab_with_strays()), profile)
    assert not got.result.removed_fragments.any()
    assert _stage(got, "fragments").edits == []


def test_a_rolled_back_merge_logs_no_e7_edit(monkeypatch):
    _not_converged_merge(monkeypatch)
    m = gridded_box(4, 2.5)
    got, _ = _kernel(m, _FAST)
    assert got.result.merge_report["rolled_back_reason"] == "not_converged"
    assert _stage(got, "merge").edits == []
    assert got.mesh.n_faces == m.n_faces == 192


def test_the_edit_log_is_one_json_line_per_edit_with_no_path_or_timestamp(tmp_path):
    log = tmp_path / "edit_log.jsonl"
    got, _ = _kernel(slab_with_three_skirts(), _FAST, edit_log=log)

    text = log.read_text(encoding="utf-8")
    lines = [json.loads(line) for line in text.splitlines()]
    assert len(lines) == len(got.edits) > 0
    for line, edit in zip(lines, got.edits):
        assert set(line) == {"stage", "engine", "kind", "site", "reason", "faces", "removed",
                             "added", "n_removed", "n_added", "n_new_points", "material"}
        assert (line["engine"], line["kind"], line["site"], line["reason"]) == (
            edit.engine, edit.kind, edit.site, edit.reason)
        assert line["faces"] == list(edit.faces)
        assert line["n_removed"] == len(line["removed"]) and line["n_added"] == len(line["added"])
    assert str(tmp_path) not in text and str(tmp_path).replace("\\", "/") not in text
    assert "time" not in text


@pytest.mark.parametrize("name, build, profile", FIXTURES, ids=[f[0] for f in FIXTURES])
def test_the_edit_log_alone_accounts_for_the_unit(tmp_path, monkeypatch, name, build, profile):
    _prepare(name, monkeypatch)
    mesh = build()
    log = tmp_path / "edit_log.jsonl"
    got, _ = _kernel(mesh, profile, edit_log=log)

    keys = Counter(_keys(mesh))
    for line in map(json.loads, log.read_text(encoding="utf-8").splitlines()):
        removed, added = Counter(line["removed"]), Counter(line["added"])
        assert not (removed - keys)
        keys = keys - removed + added
    assert keys == Counter(_keys(got.mesh))


def test_the_edit_log_is_deterministic(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    _kernel(box_with_partition_and_stitch(), _FAST, edit_log=a)
    _kernel(box_with_partition_and_stitch(), _FAST, edit_log=b)
    assert a.read_bytes() == b.read_bytes()


def test_the_kernel_builds_the_report_dict_the_cli_writes(tmp_path):
    from engine import cli
    mesh = box_with_partition()
    obj = tmp_path / "input.obj"
    obj.write_bytes(b"x")
    got, _ = _kernel(mesh, _FAST, obj_path=obj)
    expected = cli._build_report(mesh.name, obj, mesh, fix_object(mesh, {}, _FAST), _FAST)
    assert json.dumps(got.report, indent=2) == json.dumps(expected, indent=2)


def test_write_edit_log_of_no_edits_is_an_empty_file(tmp_path):
    path = tmp_path / "edit_log.jsonl"
    write_edit_log(path, [])
    assert path.read_bytes() == b""


# ------------------------------------------------------------------- item 3: `fix --kernel`

_CLI = FixProfile(guard_size=(120, 80), n_dirs=32, qa_size=(160, 100))


def test_build_parser_fix_kernel_flag_defaults_off():
    assert cli.build_parser().parse_args(["fix", "somedir"]).kernel is False
    assert cli.build_parser().parse_args(["fix", "somedir", "--kernel"]).kernel is True


def test_main_passes_the_kernel_flag_to_cmd_fix(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "cmd_fix", lambda *a, kernel=False, **k: calls.append(kernel) or 0)
    assert cli.main(["fix", "snapdir"]) == 0
    assert cli.main(["fix", "snapdir", "--kernel"]) == 0
    assert calls == [False, True]


@pytest.mark.parametrize("build", [box_with_partition, slab_with_two_depths])
def test_cmd_fix_kernel_writes_the_same_report_and_obj_and_an_edit_log(tmp_path, build):
    from engine.tests.test_cli import _write_snapshot
    mesh = build()
    snap = _write_snapshot(tmp_path, mesh)
    plain_root, kernel_root = tmp_path / "plain", tmp_path / "kernel"

    code_plain = cli.cmd_fix(snap, plain_root, accept_slit=False, profile=_CLI, skp=False)
    code_kernel = cli.cmd_fix(snap, kernel_root, accept_slit=False, profile=_CLI, skp=False,
                              kernel=True)

    plain, kernel = plain_root / mesh.name, kernel_root / mesh.name
    assert code_plain == code_kernel
    assert (plain / "report.json").read_bytes() == (kernel / "report.json").read_bytes()
    for name in (f"{mesh.name}.fixed.obj", f"{mesh.name}.fixed.ngon.obj"):
        assert (plain / name).read_bytes() == (kernel / name).read_bytes()
    assert not (plain / "edit_log.jsonl").exists()
    lines = (kernel / "edit_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines and all(json.loads(line)["engine"] in {"E1", "E2", "E3", "E4", "E7", "E8"}
                         for line in lines)
    assert str(tmp_path) not in (kernel / "edit_log.jsonl").read_text(encoding="utf-8")
