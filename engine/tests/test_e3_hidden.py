"""Job P2-E3: hidden faces, interior-aware, as the repair engine E3 (`engine.repair.engines.e3_hidden.E3Hidden`).

E3 computes its candidates exactly as the legacy hidden stage does (`engine.fixes.pipeline.stage_hidden`, pass 1:
exposure 0 from every outside direction, or zero area, confirmed by the strict guard), then drops every slab side
(ruling E3-R3) and every face an eye-height probe sees from either side (ruling E3-R4), and hands back one `remove`
site per edge-connected group of what is left (a group over 512 faces split by a spatial grid). The kernel's site
checks (`validate_sites=True`) judge every site, so a group that deletes any sample some viewpoint sees -- an
eye-height probe included -- is rolled back (ruling E3-R2).
"""
from __future__ import annotations

import json
from collections import Counter

import numpy as np

from engine import cli
from engine.fixes.pipeline import FixProfile
from engine.repair.engines.e3_hidden import MAX_SITE_FACES, E3Hidden
from engine.repair.engines.legacy import LegacyRun, legacy_engines
from engine.repair.kernel import repair_unit
from engine.repair.types import RepairContext, UnitState, apply_edits, face_keys
from engine.site_judge import SiteJudge
from engine.tests.fixtures import build as B
from engine.tests.fixtures.build import _closed_box, _mesh, _quads
from engine.tests.test_cli_repair_unit import _campus
from engine.tests.test_validate_checks import _looks, _moved, _with_plate
from engine.validate.checks import Settings
from engine.validate.sampling import face_samples, recentred, used_bbox
from engine.validate.viewpoints import interior_probes, outside_directions, pedestrian_ring
from engine.validate.visibility import build_caster, visible_samples

_FAST = FixProfile(guard_size=(120, 80), n_dirs=32)


def _blind(mesh, faces):
    """A probe view that sees nothing: the R4 pre-filter switched off, so only the judge stands guard."""
    return np.zeros(len(faces), np.int64)


def _plan(mesh, *, probe_view=None, judge=None):
    engine = E3Hidden(probe_view=probe_view)
    unit = UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None)
    edits = engine.plan(unit, RepairContext(profile=_FAST, decider=None, validator=judge))
    return engine, edits


def _judge(mesh):
    return SiteJudge(_looks(*mesh.materials), margin=2.0)


def _checked(mesh, engine, *, edit_log=None):
    unit = UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=_FAST, decider=None, validator=_judge(mesh))
    return repair_unit(unit, ctx, engines=[engine], validate_sites=True, edit_log=edit_log)


def _two_boxes():
    """Two sealed `box_with_partition`s far apart: two hidden partitions (faces 12-13 and 26-27), two groups."""
    return _with_plate(B.box_with_partition(), _moved(B.box_with_partition(), [100.0, 0.0, 0.0]))


def _legacy_hidden_output(mesh):
    """The face-key multiset the legacy hidden stage hands on (solidify, then pass 1), observed as the kernel does."""
    run = LegacyRun(mesh, {}, _FAST, {})
    unit = UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=_FAST, decider=None, validator=None)
    for engine in legacy_engines(run)[:2]:
        engine.plan(unit, ctx)
    return Counter(run.output("hidden").keys)


def _seen(mesh):
    """Per face: samples seen from outside (directions and ring cameras) and from the eye-height probes, with the
    Validator's own viewpoints and settings."""
    s = Settings()
    b, _ = recentred(mesh)
    caster = build_caster(b)
    lo, hi = used_bbox(b)
    cams = pedestrian_ring((lo, hi), eye_z=lo[2] + s.eye, n=s.n_cameras, margin=s.camera_margin)
    probes = interior_probes(b, eye=s.eye, caster=caster)
    samples = face_samples(b, faces=None, min_per_face=s.min_per_face, area_per_sample=s.area_per_sample)
    vs = visible_samples(b, samples, outside_directions(s.n_directions), cams, probes, caster)
    n_out = len(vs.dirs) + len(vs.cams)
    outside = np.bincount(samples.face[vs.seen[:, :n_out].any(axis=1)], minlength=b.n_faces)
    inside = np.bincount(samples.face[vs.seen[:, n_out:].any(axis=1)], minlength=b.n_faces)
    return outside, inside


# ------------------------------------------------------------------------------------------- engine shape

def test_e3_is_a_non_legacy_engine_named_e3():
    engine = E3Hidden()
    assert engine.name == "E3" and engine.legacy is False and MAX_SITE_FACES == 512


def test_plan_gives_non_legacy_e3_removes_one_site_per_connected_group():
    mesh = _two_boxes()
    engine, edits = _plan(mesh, judge=_judge(mesh))
    assert edits and all(e.engine == "E3" and e.kind == "remove" and e.legacy is False for e in edits)
    assert all(e.new_faces is None and e.new_points is None for e in edits)
    assert sorted(sorted(e.faces) for e in edits) == [[12, 13], [26, 27]]
    assert len({e.site for e in edits}) == len(edits) == 2, "one site per edge-connected group"
    for e in edits:
        assert e.reason and {"faces", "area", "exposure", "rules", "group"} <= set(e.evidence)
        assert e.evidence["faces"] == 2 and e.evidence["rules"] == ["hidden", "hidden"]
        assert e.evidence["exposure"]["front_max"] == 0.0 and e.evidence["exposure"]["back_max"] == 0.0
    assert engine.report["legacy_candidates"] == 4 and engine.report["candidates"] == 4
    assert engine.report["groups"] == 2 and engine.report["sites"] == 2


def test_apply_edits_reproduces_the_legacy_hidden_stage_when_nothing_is_rolled_back():
    for mesh in (B.box_with_partition(), _two_boxes()):
        _engine, edits = _plan(mesh, judge=_judge(mesh))
        after, _ = apply_edits(mesh, edits)
        assert Counter(face_keys(after, {})) == _legacy_hidden_output(mesh)
        checked = _checked(mesh, E3Hidden())
        assert not checked.rolled_back and checked.checks[0]["final"] == "PASS"
        assert Counter(face_keys(checked.mesh, {})) == _legacy_hidden_output(mesh)


def test_plan_leaves_the_unit_mesh_alone():
    mesh = B.box_with_partition()
    before = (mesh.positions.copy(), mesh.face_v.copy())
    unit = UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None)
    E3Hidden(probe_view=_blind).plan(unit, RepairContext(profile=_FAST, decider=None, validator=None))
    assert unit.mesh is mesh and np.array_equal(mesh.positions, before[0]) and np.array_equal(mesh.face_v, before[1])


# --------------------------------------------------------------- the strict rule: the judge is the safety net

PLATE_LOW = (24, 25)    # in `_room_scene`: the plate's half inside the floor's cavity, hidden from everything
PLATE_HIGH = (26, 27)   # ...and its half standing in the room, seen ONLY by the eye-height probes
PARTITIONS = (40, 41, 54, 55)


def _room_scene():
    """`closed_room` (faces 0-23: its inner skin is seen only from its own probes) with a plate standing in it at
    x = 100: its lower half (24-25) in the floor's sealed cavity, z = -6..0, its upper half (26-27) in the room,
    z = 0..30, the two sharing the edge at z = 0 (one connected group). Far off, two sealed `box_with_partition`s
    (28-41 and 42-55), whose partitions (40-41, 54-55) nothing sees."""
    P = [[100.0, 40.0, -6.0], [100.0, 120.0, -6.0], [100.0, 120.0, 0.0], [100.0, 40.0, 0.0],
         [100.0, 120.0, 30.0], [100.0, 40.0, 30.0]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3), (3, 2, 4, 5)])
    scene = _with_plate(B.closed_room(), _mesh("plate", P, uvs, fv, fvt, face_material=fm))
    scene = _with_plate(scene, _moved(B.box_with_partition(), [400.0, 0.0, 0.0]))
    return _with_plate(scene, _moved(B.box_with_partition(), [0.0, 400.0, 0.0]))


def test_the_room_scene_plate_is_seen_only_from_eye_height():
    outside, inside = _seen(_room_scene())
    assert (outside[list(PLATE_HIGH)] == 0).all() and (inside[list(PLATE_HIGH)] > 0).all()
    assert (outside[list(PLATE_LOW) + list(PARTITIONS)] == 0).all()
    assert (inside[list(PLATE_LOW) + list(PARTITIONS)] == 0).all()


def test_a_group_holding_a_face_only_a_probe_sees_is_rolled_back_for_deleted(tmp_path):
    """The pre-filter is told the plate's upper half is unseen (a miss it could make), so the plate's group is
    planned: the judge sees the probe's samples deleted and rolls the group back; the partitions are kept."""
    mesh = _room_scene()

    def missing_the_plate(m, faces):
        seen = SiteJudge(_looks(*m.materials)).probe_seen(m, faces)
        return np.where(np.isin(faces, PLATE_HIGH), 0, seen)

    log = tmp_path / "edit_log.jsonl"
    engine = E3Hidden(probe_view=missing_the_plate)
    result = _checked(mesh, engine, edit_log=log)
    by_site = {e.site: sorted(e.faces) for e in result.edits}
    plate_site = next(s for s, faces in by_site.items() if set(PLATE_HIGH) <= set(faces))
    assert set(PLATE_LOW) <= set(by_site[plate_site]), "the plate's two halves are one group"
    (check,) = result.checks
    rolled = {row["site"]: row for row in check["rolled_back"]}
    assert set(rolled) == {plate_site}, "only the plate's group is rolled back"
    assert "deleted" in rolled[plate_site]["reasons"]
    kept = sorted(f for e in result.kept for f in e.faces)
    assert kept == list(PARTITIONS), "every other group is kept"
    assert check["final"] == "PASS"
    keys = Counter(face_keys(result.mesh, {}))
    for f in PLATE_LOW + PLATE_HIGH + tuple(range(12)):
        assert keys[face_keys(mesh, {})[f]] >= 1, f"face {f} must still be there"
    assert result.mesh.n_faces == mesh.n_faces - len(PARTITIONS)
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert any(line.get("rolled_back") and line["site"] == plate_site for line in lines if "check" not in line)


# ---------------------------------------------------------------------------------- E3-R3: never side meshes

SIDE = (6, 7)           # in `_slab_against_a_block`: slab A's x = 40 side, pressed against block B
SLAB_PARTITION = (24, 25)


def _slab_against_a_block():
    """A closed slab A (0..40 x 0..40, z -8..0, faces 0-11, wound outward) whose x = 40 side (faces 6-7) lies on the
    face of a taller closed block B (40..80 x -20..60, z -30..30, faces 12-23): that side is hidden from every
    viewpoint, yet it is the slab's own side. A partition inside A at z = -4 (faces 24-25) is the inside."""
    P, uvs, fv, fvt, fm = [], [], [], [], []
    _closed_box(P, uvs, fv, fvt, fm, 0.0, 40.0, 0.0, 40.0, -8.0, 0.0)
    _closed_box(P, uvs, fv, fvt, fm, 40.0, 80.0, -20.0, 60.0, -30.0, 30.0)
    b = len(P)
    P += [[0.0, 0.0, -4.0], [40.0, 0.0, -4.0], [40.0, 40.0, -4.0], [0.0, 40.0, -4.0]]
    _quads(P, uvs, fv, fvt, fm, [(b, b + 1, b + 2, b + 3)])
    return _mesh("slab_against_a_block", P, uvs, fv, fvt, face_material=fm)


def test_a_slab_side_unseen_from_every_viewpoint_is_never_a_candidate():
    mesh = _slab_against_a_block()
    outside, inside = _seen(mesh)
    assert (outside[list(SIDE)] == 0).all() and (inside[list(SIDE)] == 0).all(), "no viewpoint sees the side"
    engine, edits = _plan(mesh, probe_view=_blind)
    assert set(SIDE) <= set(engine.report["legacy_removed"]), "the legacy hidden stage would delete it"
    planned = sorted(f for e in edits for f in e.faces)
    assert planned == list(SLAB_PARTITION), "the inside goes, the side stays"
    assert engine.report["excluded"]["side"] >= len(SIDE)
    result = _checked(mesh, E3Hidden(probe_view=_blind))
    keys = Counter(face_keys(result.mesh, {}))
    assert all(keys[face_keys(mesh, {})[f]] == 1 for f in SIDE)


def test_a_face_solidify_invented_is_never_a_candidate():
    """A face no OBJ row holds (`face_line` -1, solidify's own mark for a face it invented, which an E8 add carries)
    is a built side or bottom: never a candidate, even when hidden."""
    import dataclasses
    plain = B.box_with_partition()
    line = plain.face_line.copy()
    line[[12, 13]] = -1
    engine, edits = _plan(dataclasses.replace(plain, face_line=line), probe_view=_blind)
    assert edits == [] and engine.report["excluded"]["invented"] == 2


# ------------------------------------------------------------------------------- E3-R4: never room surfaces

def test_a_closed_room_seen_only_from_its_probe_keeps_every_face():
    mesh = B.closed_room()
    outside, inside = _seen(mesh)
    assert (outside[:12] == 0).all() and (inside[:12] > 0).all(), "the room is seen only from its probes"
    engine, edits = _plan(mesh, judge=_judge(mesh))
    assert set(range(12)) <= set(engine.report["legacy_removed"]), "the legacy hidden stage would delete the room"
    assert not any(f < 12 for e in edits for f in e.faces)
    assert engine.report["excluded"]["probe"] == 12
    assert engine.report["disagreements"]["faces"] == 12, "exposure calls them hidden, a probe sees them"
    result = _checked(mesh, E3Hidden())
    assert result.mesh.n_faces == mesh.n_faces


# --------------------------------------------------------------------------------------- group splitting

def _box_with_a_fine_partition(n=32, size=100.0):
    """`cube(size)` (faces 0-11) with a partition at mid-height cut into an `n` x `n` grid of quads: 2 n^2
    triangles, every one sharing an edge with its neighbours, all hidden (one connected group of 2,048)."""
    m = B.cube(size)
    P = [list(p) for p in m.positions]
    uvs = [list(t) for t in m.uvs]
    fv = [list(f) for f in m.face_v]
    fvt = [list(f) for f in m.face_vt]
    fm = [0] * len(fv)
    base = len(P)
    step = size / n
    for j in range(n + 1):
        for i in range(n + 1):
            P.append([i * step, j * step, size / 2.0])
    quads = [(base + j * (n + 1) + i, base + j * (n + 1) + i + 1, base + (j + 1) * (n + 1) + i + 1,
              base + (j + 1) * (n + 1) + i) for j in range(n) for i in range(n)]
    _quads(P, uvs, fv, fvt, fm, quads)
    return _mesh("box_with_a_fine_partition", P, uvs, fv, fvt, face_material=fm)


def test_a_group_over_512_faces_is_split_by_a_spatial_grid():
    mesh = _box_with_a_fine_partition()
    engine, edits = _plan(mesh, probe_view=_blind)
    partition = set(range(12, mesh.n_faces))
    assert len(partition) == 2048 and engine.report["groups"] == 1
    sizes = Counter()
    for e in edits:
        sizes[e.site] += len(e.faces)
    assert len(sizes) >= 4 and max(sizes.values()) <= MAX_SITE_FACES
    assert sorted(f for e in edits for f in e.faces) == sorted(partition), "every face in exactly one site"
    assert all(e.evidence["group_faces"] == 2048 for e in edits)


# ---------------------------------------------------------------------------------------------- the CLI

def _cli_scene():
    """E8a has a wall and a bottom to build (`slab_with_three_skirts`), E3 a hidden partition, far off."""
    return _with_plate(B.slab_with_three_skirts(), _moved(B.box_with_partition(size=10.0), [500.0, 0.0, 0.0]))


def test_repair_unit_runs_e8a_then_e3_in_the_given_order(tmp_path):
    paths, _snap = _campus(tmp_path, _cli_scene())
    out = tmp_path / "out"
    code = cli.main(["repair-unit", "--unit", "T-L01", "--engines", "E8a,E3", "--out", str(out),
                     "--map", str(paths["map"]), "--source", str(paths["source"]),
                     "--materials", str(paths["materials"])])
    assert code == 0
    lines = [json.loads(line) for line in (out / "edit_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [line["check"]["stage"] for line in lines if "check" in line] == ["E8", "E3"]
    stages = [line["stage"] for line in lines if "check" not in line]
    assert stages == sorted(stages, key=["E8", "E3"].index), "E8's edits first, then E3's"
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    e3 = report["e3"]
    assert e3["sites"]["kept"] >= 1 and e3["faces_removed"] >= 2 and e3["deleted_after_rollback"] == 0
    assert {"legacy_candidates", "candidates", "groups", "excluded", "disagreements"} <= set(e3)


def test_repair_unit_refuses_an_unknown_engine_in_a_comma_list(capsys):
    assert cli.main(["repair-unit", "--unit", "U", "--engines", "E3,bogus", "--out", "o"]) == 2
    assert "bogus" in capsys.readouterr().err
