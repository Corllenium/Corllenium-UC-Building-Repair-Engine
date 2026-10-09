"""Job P1-K3b item 2: the kernel's site checks -- attribute and confirm, instead of bisection by repeated runs.

With `validate_sites=True`, after each engine stage: ONE focus run on the union of the sites' focus; each failing
sample charged to the sites that could have caused it (`SiteJudge.attribute`); every charged site rolled back; ONE
confirming run on the kept sites (at most 3 rounds, then what is still charged is rolled back with
`rounds_exhausted`); the next stage runs on `apply_edits(stage_input, kept_edits)`. A failure charged to no site is
logged as unknown and never dropped. Legacy stages (one site each) are not rolled back unless `rollback_legacy`.

The fixtures: BEFORE is a P0-16 mutation fixture (the two-look cube, or the closed room) with two far-off pieces
appended after its faces, so its own face ids do not move: a slab whose faces are all stacked twice, and a slab the
good engine re-triangulates along the other diagonal. The good sites: remove the stacked duplicate copies, and that
re-triangulation (a cut carrying the very UVs of the corners). The bad site: one P0-16 defect, as an edit.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass

import numpy as np
import pytest

import engine.repair.engines.legacy as legacy
from engine.fixes.pipeline import FixProfile
from engine.repair.kernel import edit_record, repair_unit
from engine.repair.types import Edit, RepairContext, UnitState, apply_edits
from engine.site_judge import SiteJudge
from engine.tests.fixtures.build import box_with_partition, closed_room, grid_slab
from engine.tests.test_validate_checks import _looks, _moved, _with_plate
from engine.tests.test_validate_mutations import LOOKS, ROOM_LOOKS, SIZE, two_look_cube

GOOD_DUP, GOOD_CUT, BAD = 11, 12, 13
_FAST = FixProfile(guard_size=(120, 80), n_dirs=32)


def _slab(at):
    """A 2 x 2 slab of 10 in cells at `at`, facing +z, in material 0."""
    return _moved(grid_slab(2, 2, cell=10.0), at)


def _scene(base, far=600.0):
    """`(before, dup_ids, cut_ids)`: `base` with a doubled slab and a plain slab appended, `far` in off along y."""
    n = base.n_faces
    slab = _slab([0.0, far, 0.0])
    before = _with_plate(_with_plate(base, slab), slab)                     # the same 8 faces twice
    before = _with_plate(before, _slab([40.0, far, 0.0]))
    return before, np.arange(n + 8, n + 16), np.arange(n + 16, n + 24)


def _ev(stage="fixture", **kw):
    return {"stage": stage, "removed_keys": [], "added_keys": [], **kw}


def _good_edits(before, dup_ids, cut_ids):
    """The two good sites: the duplicate copies removed; the plain slab cut along its other diagonals."""
    remove = Edit(engine="E4", kind="remove", faces=tuple(dup_ids.tolist()), new_faces=None, new_points=None,
                  site=GOOD_DUP, reason="stacked duplicate copies", evidence=_ev())
    new_v, new_uv = [], []
    for a, b in zip(cut_ids[0::2], cut_ids[1::2]):             # each cell: [v0 v1 v2] and [v0 v2 v3]
        (v0, v1, v2), (_, _, v3) = before.face_v[a], before.face_v[b]
        (t0, t1, t2), (_, _, t3) = before.face_vt[a], before.face_vt[b]
        new_v += [[v0, v1, v3], [v1, v2, v3]]
        new_uv += [before.uvs[[t0, t1, t3]], before.uvs[[t1, t2, t3]]]
    cut = Edit(engine="E7", kind="cut", faces=tuple(cut_ids.tolist()), new_faces=np.array(new_v), new_points=None,
               site=GOOD_CUT, reason="re-triangulated", evidence=_ev(), new_face_uv=np.array(new_uv))
    return [remove, cut]


def _bad(kind, before):
    """The P0-16 mutation `kind` as the edits of site BAD."""
    uv = lambda f: before.uvs[before.face_vt[f]][None]
    tri = lambda f: before.face_v[f][None]
    if kind in ("1 delete a visible face", "6 delete an inner wall only a probe sees"):
        faces = (8,) if kind.startswith("1") else (4, 5)
        return [Edit(engine="E3", kind="remove", faces=faces, new_faces=None, new_points=None, site=BAD,
                     reason="bad", evidence=_ev())]
    if kind == "2 a visible face in another look":
        return [Edit(engine="E5", kind="remove", faces=(8,), new_faces=None, new_points=None, site=BAD,
                     reason="bad", evidence=_ev()),
                Edit(engine="E8", kind="add", faces=(), new_faces=tri(8), new_points=None, site=BAD, reason="bad",
                     evidence=_ev(material=1), new_face_uv=uv(8))]
    if kind == "3 UVs shifted by half":
        return [Edit(engine="E7", kind="cut", faces=(2,), new_faces=tri(2), new_points=None, site=BAD,
                     reason="bad", evidence=_ev(), new_face_uv=uv(2) + 0.5)]
    if kind == "4 a flipped visible face":
        return [Edit(engine="E2", kind="flip", faces=(2,), new_faces=None, new_points=None, site=BAD,
                     reason="bad", evidence=_ev())]
    if kind == "5 a face one inch in front of a visible face":
        n = len(before.positions)
        plate = _moved(grid_slab(1, 1, cell=SIZE), [0.0, 0.0, SIZE + 1.0])
        return [Edit(engine="E8", kind="add", faces=(), new_faces=plate.face_v + n, new_points=plate.positions,
                     site=BAD, reason="bad", evidence=_ev(material=0), new_face_uv=plate.uvs[plate.face_vt])]
    raise KeyError(kind)


MUTATIONS = ["1 delete a visible face", "2 a visible face in another look", "3 UVs shifted by half",
             "4 a flipped visible face", "5 a face one inch in front of a visible face",
             "6 delete an inner wall only a probe sees"]


@dataclass
class _Planned:
    """A test engine: plans the edits it was given (against the stage input it was built for)."""
    name: str
    edits: list

    def plan(self, unit, ctx):
        return list(self.edits)


def _run(before, looks, engines, *, judge=None, **kw):
    judge = judge or SiteJudge(looks, margin=2.0)
    unit = UnitState(mesh=before, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=FixProfile(), decider=None, validator=judge)
    return repair_unit(unit, ctx, engines=engines, validate_sites=True, **kw), ctx


def _same(a, b):
    for name in ("positions", "uvs", "face_v", "face_vt", "face_material"):
        assert np.array_equal(getattr(a, name), getattr(b, name)), name


def _cube_scene():
    return _scene(two_look_cube())


def test_two_good_sites_and_one_bad_only_the_bad_site_is_rolled_back_and_the_confirming_run_passes():
    before, dup, cut = _cube_scene()
    good = _good_edits(before, dup, cut)
    bad = _bad("1 delete a visible face", before)
    got, ctx = _run(before, LOOKS, [_Planned("fixture", [good[0], *bad, good[1]])])

    (check,) = got.checks
    assert check["first"] == "FAIL" and check["final"] == "PASS"
    assert [r["kind"] for r in check["runs"]] == ["first", "confirm"]
    assert check["runs"][0]["failing"] == 4 and check["runs"][0]["nothing_deleted"]["deleted"] == 4
    assert check["runs"][1]["failing"] == 0 and check["runs"][1]["status"] == "PASS"
    (rolled,) = check["rolled_back"]
    assert rolled["site"] == BAD and rolled["charged"] == 4 and rolled["round"] == 1
    assert rolled["how"] == {"touched": 4, "box": 0, "cover": 0} and rolled["edits"] == 1
    assert rolled["reasons"] == {"deleted": 4}
    assert check["rounds"] == 1 and check["rounds_exhausted"] is False and check["unknown"]["samples"] == 0
    assert got.rolled_back == bad and got.kept == [good[0], good[1]]
    _same(got.mesh, apply_edits(before, good)[0])
    assert ctx.log == [good[0], *bad, good[1]], "every planned edit is in the context's log, kept or not"


@pytest.mark.parametrize("kind", MUTATIONS)
def test_each_p0_16_mutation_as_a_site_among_good_ones_is_the_one_rolled_back(kind):
    base, looks = (closed_room(), ROOM_LOOKS) if kind.startswith("6") else (two_look_cube(), LOOKS)
    before, dup, cut = _scene(base)
    good = _good_edits(before, dup, cut)
    got, _ = _run(before, looks, [_Planned("fixture", [*good, *_bad(kind, before)])])
    (check,) = got.checks
    assert check["first"] == "FAIL", kind
    assert [r["site"] for r in check["rolled_back"]] == [BAD], (kind, check["rolled_back"])
    assert check["final"] == "PASS" and check["runs"][-1]["kind"] == "confirm"
    _same(got.mesh, apply_edits(before, good)[0])


class _NoisyJudge(SiteJudge):
    """The Validator, plus one failing sample no edit could have caused (a stand-in for Validator noise, or a
    change no edit names): a sample of BEFORE face 0, the cube's bottom, which no site touches or covers."""

    def check(self, after, focus):
        from engine.site_judge import FailingSamples, SiteVerdict
        v = super().check(after, focus)
        s = v.samples
        add = lambda a, row: np.concatenate([a, np.asarray(row, dtype=a.dtype)])
        samples = FailingSamples(face=add(s.face, [0]), index=add(s.index, [0]), point=np.vstack([s.point, [[5, 5, 0]]]),
                                 witness=np.vstack([s.witness, [[0, 0, -1.0]]]), is_dir=add(s.is_dir, [True]),
                                 cluster=add(s.cluster, [len(s.clusters)]), clusters=s.clusters + [{"deleted": 1}])
        return SiteVerdict(failing=v.failing | {(0, 0)}, summary=v.summary, seconds=v.seconds, samples=samples)


def test_a_failure_charged_to_no_site_is_logged_as_unknown_and_no_site_is_charged_but_the_stage_is_rolled_back():
    # P2-K0 item 1: the stage no longer ships its edits after a failure no site explains (it used to keep them all).
    before, dup, cut = _cube_scene()
    good = _good_edits(before, dup, cut)
    got, _ = _run(before, LOOKS, [_Planned("fixture", good)], judge=_NoisyJudge(LOOKS, margin=2.0))
    (check,) = got.checks
    assert check["first"] == "FAIL" and got.kept == [] and got.rolled_back == good
    assert all(r["stage_rolled_back"] and r["charged"] == 0 for r in check["rolled_back"])
    assert check["unknown"] == {"samples": 1, "faces": [0], "reasons": {"deleted": 1}}
    assert check["runs"][0]["unknown"] == 1 and check["runs"][0]["charged"] == 0
    assert [r["kind"] for r in check["runs"]] == ["first"], "no site was charged: no confirming run is needed"
    _same(got.mesh, before)


def _covered_then_unmasked():
    """Site A (BAD) lays a plate 1 in over the cube's top (it covers it) AND puts back an exact copy of one face of
    the far slab; site B (GOOD_DUP) removes that face. Round 1: only A is charged (the cover); A rolled back, the
    confirming run shows the face B removed is gone: B is charged in round 2."""
    before, dup, _ = _cube_scene()
    gone = int(dup[0]) - 8                                       # the first copy of the doubled slab's first face
    plate = _bad("5 a face one inch in front of a visible face", before)
    copy = Edit(engine="E8", kind="add", faces=(), new_faces=before.face_v[gone][None], new_points=None, site=BAD,
                reason="copy", evidence=_ev(material=0), new_face_uv=before.uvs[before.face_vt[gone]][None])
    remove = Edit(engine="E4", kind="remove", faces=(gone, gone + 8), new_faces=None, new_points=None, site=GOOD_DUP,
                  reason="both copies", evidence=_ev())
    return before, [*plate, copy, remove]


def test_a_failure_unmasked_by_a_rollback_is_charged_in_the_next_round():
    before, edits = _covered_then_unmasked()
    got, _ = _run(before, LOOKS, [_Planned("fixture", edits)])
    (check,) = got.checks
    assert [(r["site"], r["round"]) for r in check["rolled_back"]] == [(BAD, 1), (GOOD_DUP, 2)]
    assert check["rounds"] == 2 and check["rounds_exhausted"] is False
    assert [r["kind"] for r in check["runs"]] == ["first", "confirm"], "nothing kept after round 2: no third run"
    assert got.kept == [] and check["final"] == "NOTHING KEPT"
    _same(got.mesh, before)


def test_when_the_rounds_run_out_what_is_still_charged_is_rolled_back_and_says_so():
    before, edits = _covered_then_unmasked()
    got, _ = _run(before, LOOKS, [_Planned("fixture", edits)], max_rounds=1)
    (check,) = got.checks
    assert [(r["site"], r["round"]) for r in check["rolled_back"]] == [(BAD, 1), (GOOD_DUP, 2)]
    assert check["rolled_back"][1]["rounds_exhausted"] is True and check["rounds_exhausted"] is True
    assert check["rounds"] == 1 and got.kept == []


@pytest.mark.parametrize("validate_sites", [True, False])
def test_a_non_legacy_engine_planning_a_legacy_marked_edit_is_refused(validate_sites):
    # P2-K0 fix round 1: the legacy marker lifts the add refusal, so only the legacy observer may set it.
    before, _, _ = _cube_scene()
    sneaky = Edit(engine="E8", kind="add", faces=(), new_faces=before.face_v[0][None], new_points=None, site=BAD,
                  reason="legacy marker from a P2 engine", evidence=_ev(material=0),
                  new_face_uv=before.uvs[before.face_vt[0]][None], legacy=True)
    unit = UnitState(mesh=before, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=FixProfile(), decider=None, validator=SiteJudge(LOOKS, margin=2.0))
    with pytest.raises(ValueError, match="legacy"):
        repair_unit(unit, ctx, engines=[_Planned("fixture", [sneaky])], validate_sites=validate_sites)


def test_the_next_stage_runs_on_the_kept_result():
    before, dup, cut = _cube_scene()
    good = _good_edits(before, dup, cut)
    seen = []

    @dataclass
    class _Second:
        name: str = "second"

        def plan(self, unit, ctx):
            seen.append(unit.mesh)
            return []

    got, _ = _run(before, LOOKS, [_Planned("first", [*good, *_bad("1 delete a visible face", before)]), _Second()])
    _same(seen[0], apply_edits(before, good)[0])
    assert got.checks[1]["edits"] == 0 and got.checks[1]["runs"] == [] and got.checks[1]["first"] == "PASS"


def test_the_edit_log_has_a_check_record_per_stage_and_marks_rolled_back_edits(tmp_path):
    before, dup, cut = _cube_scene()
    good = _good_edits(before, dup, cut)
    log = tmp_path / "edit_log.jsonl"
    _run(before, LOOKS, [_Planned("fixture", [*good, *_bad("1 delete a visible face", before)])], edit_log=log)
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [("check" in line, line.get("rolled_back", False)) for line in lines] == [
        (False, False), (False, False), (False, True), (True, False)]
    check = lines[-1]["check"]
    assert check["stage"] == "fixture" and check["rolled_back"][0]["site"] == BAD
    assert {"seconds", "focus_seconds", "cover_seconds"} <= set(check["runs"][0])
    text = log.read_text(encoding="utf-8")
    assert "timestamp" not in text and "created" not in text and str(tmp_path) not in text


# ---------------------------------------------------------------------------------------------------------------
# The legacy engines: one site per stage, not rolled back by default (ruling K3-R2)
# ---------------------------------------------------------------------------------------------------------------

def _overlap_drops_a_visible_face(monkeypatch):
    """The overlap stage, then the first face of what it hands on dropped: a visible face of the box deleted."""
    stages = dict(legacy.FIX_STAGES)
    real = stages["overlap"]

    def overlap(s):
        s = real(s)
        m = s.mesh_overlapped
        keep = np.arange(1, m.n_faces)
        s.mesh_overlapped = dataclasses.replace(m, face_v=m.face_v[keep], face_vt=m.face_vt[keep],
                                                face_vn=m.face_vn[keep], face_material=m.face_material[keep],
                                                face_line=m.face_line[keep])
        s.source_from_overlap = s.source_from_overlap[keep]
        return s

    monkeypatch.setattr(legacy, "FIX_STAGES", tuple((n, overlap if n == "overlap" else f)
                                                     for n, f in legacy.FIX_STAGES))


def _legacy(mesh, **kw):
    unit = UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=_FAST, decider=None, validator=SiteJudge(_looks(*mesh.materials)))
    return repair_unit(unit, ctx, flatness={}, validate_sites=True, **kw)


def test_a_legacy_stage_that_fails_its_check_is_logged_and_kept(monkeypatch):
    _overlap_drops_a_visible_face(monkeypatch)
    plain = repair_unit(UnitState(mesh=box_with_partition(), topo=None, looks={}, viewpoints=None),
                        RepairContext(profile=_FAST, decider=None, validator=None), flatness={})
    got = _legacy(box_with_partition())
    assert [c["stage"] for c in got.checks] == [s for s, _ in legacy.STAGE_ENGINES]
    overlap = next(c for c in got.checks if c["stage"] == "overlap")
    assert overlap["first"] == "FAIL" and overlap["legacy"] is True and overlap["rolled_back"] == []
    assert overlap["final"] == "FAIL (legacy stage kept, ruling K3-R2)"
    assert overlap["runs"][0]["nothing_deleted"]["deleted"] > 0
    assert overlap["unknown"]["samples"] == 0, "one site per stage: every failure is the stage's"
    assert all(c["first"] == "PASS" for c in got.checks if c["stage"] != "overlap" and c["edits"])
    _same(got.mesh, plain.mesh)
    assert got.result is not None and got.rolled_back == []
    assert [edit_record(e) for e in got.kept] == [edit_record(e) for e in plain.edits]


def test_with_rollback_legacy_a_failing_legacy_stage_is_rolled_back_and_the_later_ones_do_not_run(monkeypatch):
    _overlap_drops_a_visible_face(monkeypatch)
    got = _legacy(box_with_partition(), rollback_legacy=True)
    overlap = next(c for c in got.checks if c["stage"] == "overlap")
    assert [r["site"] for r in overlap["rolled_back"]] == [5] and overlap["final"] == "NOTHING KEPT"
    merge = next(c for c in got.checks if c["stage"] == "merge")
    assert merge["skipped"].startswith("an earlier legacy stage was rolled back")
    orientation = got.stages[4]
    _same(got.mesh, orientation.after.as_mesh())
    assert got.result is None and got.report is None
