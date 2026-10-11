# engine/tests/test_e1_loose.py
import pytest
import numpy as np

from engine.tests.fixtures.build import slab_with_debris, printed
from engine.repair.engines.e1_loose import E1Loose
from engine.repair.types import UnitState, RepairContext, apply_edits, face_keys
from engine.fixes.pipeline import FixProfile


def test_e1_engine_shape():
    m = printed(slab_with_debris())
    engine = E1Loose(viewpoints=[])
    unit = UnitState(mesh=m, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=FixProfile(accept_fragments=True), decider=None, validator=None)

    edits = engine.plan(unit, ctx)
    assert len(edits) > 0
    assert all(e.engine == "E1" and e.kind == "remove" for e in edits)

    # each site has its own edit
    sites = [e.site for e in edits]
    assert len(sites) == len(set(sites))

    # removed faces include the 4 debris faces: 32, 33, 34, 35
    removed_faces = set(f for e in edits for f in e.faces)
    assert {32, 33, 34, 35}.issubset(removed_faces)

    # apply_edits removes all 4 debris faces, keeping exactly the 32 slab faces
    after_mesh, _ = apply_edits(m, edits)
    assert after_mesh.n_faces == 32

    # verify removed face keys match exactly the 4 debris faces
    all_keys = face_keys(m, {})
    debris_keys = sorted(all_keys[f] for f in (32, 33, 34, 35))
    edits_keys = sorted(all_keys[f] for e in edits for f in e.faces)
    assert debris_keys == edits_keys


def test_visible_debris_stays_and_is_listed(tmp_path):
    from pathlib import Path
    from engine.tests.fixtures.build import _grid, _mesh
    P, uvs, fv, fvt, fm = _grid(4, 4, 10.0, 0.05)
    base = len(P)
    P += [[10.0, 10.0, 20.0], [20.0, 10.0, 20.0], [10.0, 20.0, 20.0]]
    fv.append([base, base + 1, base + 2])
    fvt.append([0, 1, 2])
    fm.append(0)
    m = _mesh("open_slab_with_visible_fragment", P, uvs, fv, fvt, face_material=fm)
    frag_face = m.n_faces - 1

    engine = E1Loose(out_dir=tmp_path)
    unit = UnitState(mesh=m, topo=None, looks={}, viewpoints=None)
    profile = FixProfile(accept_fragments=True, fragment_max_area=100.0)
    ctx = RepairContext(profile=profile, decider=None, validator=None)

    edits = engine.plan(unit, ctx)

    # Fragment must NOT be removed
    removed_faces = set(f for e in edits for f in e.faces)
    assert frag_face not in removed_faces

    # Must be present in e1.visible_debris with pixels, viewpoint and crop path
    vd = engine.report["visible_debris"]
    assert len(vd) == 1
    item = vd[0]
    assert frag_face in item["faces"]
    assert item["pixels"] > 4.0
    assert "direction" in item["viewpoint"] or "camera" in item["viewpoint"] or "point" in item["viewpoint"]
    assert item["crop"] is not None and Path(item["crop"]).is_file()

    # The fragment is still present in output
    after_mesh, _ = apply_edits(m, edits)
    assert after_mesh.n_faces == m.n_faces


def test_invisible_debris_goes_check3_floor_pass():
    from engine.tests.fixtures.build import _mesh, _closed_box
    from engine.validate.checks import validate, Settings, Looks
    from engine.validate.floor import Viewpoint
    P, uvs, fv, fvt, fm = [], [], [], [], []
    _closed_box(P, uvs, fv, fvt, fm, 0.0, 40.0, 0.0, 40.0, 0.0, 40.0, material=0)
    base = len(P)
    P += [[10.0, 10.0, 20.0], [20.0, 10.0, 20.0], [10.0, 20.0, 20.0]]
    fv.append([base, base + 1, base + 2])
    fvt.append([0, 1, 2])
    fm.append(0)
    m = _mesh("closed_box_with_fragment", P, uvs, fv, fvt, face_material=fm)
    frag_face = m.n_faces - 1

    vp_above = Viewpoint.direction([0.0, 0.0, -1.0])
    engine = E1Loose(viewpoints=[vp_above])
    unit = UnitState(mesh=m, topo=None, looks={}, viewpoints=None)
    profile = FixProfile(accept_fragments=True, fragment_max_area=100.0)
    ctx = RepairContext(profile=profile, decider=None, validator=None)
    edits = engine.plan(unit, ctx)

    # Fragment inside box is invisible, so it IS removed
    removed_faces = set(f for e in edits for f in e.faces)
    assert frag_face in removed_faces

    after_mesh, _ = apply_edits(m, edits)
    assert after_mesh.n_faces == m.n_faces - 1

    # Check 3 and Floor PASS
    res = validate(m, after_mesh, Looks({}), settings=Settings(n_directions=64, n_extra_directions=64, n_cameras=8))
    c3 = res.report["checks"]["nothing_deleted"]
    assert c3["status"] == "PASS"
    assert c3["floor"]["status"] == "PASS"


def test_zero_area_faces_removed_labelled_e1_rule_zero_area():
    from engine.tests.fixtures.build import _grid, _mesh
    P, uvs, fv, fvt, fm = _grid(4, 4, 10.0, 0.05)
    base = len(P)
    P += [[10.0, 10.0, 0.0], [20.0, 10.0, 0.0], [30.0, 10.0, 0.0]]
    ub = len(uvs)
    uvs.extend([[0.5, 0.5], [1.0, 0.5], [1.5, 0.5]])
    fv.append([base, base + 1, base + 2])
    fvt.append([ub, ub + 1, ub + 2])
    fm.append(0)
    ub = len(uvs)
    uvs.extend([[0.0, 0.0], [0.0, 0.0], [0.5, 0.0]])
    fv.append([0, 0, 1])
    fvt.append([ub, ub + 1, ub + 2])
    fm.append(0)
    m = _mesh("slab_with_zero_area", P, uvs, fv, fvt, face_material=fm)
    za_faces = {32, 33}

    engine = E1Loose()
    unit = UnitState(mesh=m, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=FixProfile(accept_fragments=True), decider=None, validator=None)
    edits = engine.plan(unit, ctx)

    # All zero-area faces must be removed and labelled E1 with reason/rule "zero_area"
    za_edits = [e for e in edits if any(f in za_faces for f in e.faces)]
    assert len(za_edits) > 0
    for e in za_edits:
        assert e.engine == "E1"
        assert e.kind == "remove"
        assert e.reason == "zero_area"
        assert e.evidence["rule"] == "zero_area"

    after_mesh, _ = apply_edits(m, edits)
    assert after_mesh.n_faces == 32


def test_solidifys_faces_are_never_candidates():
    import dataclasses
    from engine.tests.fixtures.build import _grid, _mesh
    P, uvs, fv, fvt, fm = _grid(4, 4, 10.0, 0.05)
    base = len(P)
    # A 2 sq in triangle that has face_line = -1 (invented by solidify)
    P += [[0.0, 0.0, 20.0], [2.0, 0.0, 20.0], [0.0, 2.0, 20.0]]
    fv.append([base, base + 1, base + 2])
    fvt.append([0, 1, 2])
    fm.append(0)
    lines = [1] * 32 + [-1]
    m = _mesh("slab_with_invented_bottom", P, uvs, fv, fvt, face_material=fm)
    m = dataclasses.replace(m, face_line=np.array(lines, dtype=np.int64))

    engine = E1Loose(viewpoints=[])
    unit = UnitState(mesh=m, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=FixProfile(accept_fragments=True), decider=None, validator=None)
    edits = engine.plan(unit, ctx)

    # Face 32 must NOT be in edits
    removed_faces = set(f for e in edits for f in e.faces)
    assert 32 not in removed_faces

    after_mesh, _ = apply_edits(m, edits)
    assert after_mesh.n_faces == m.n_faces
