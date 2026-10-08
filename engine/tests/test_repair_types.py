"""K1: engine.repair.types -- FaceKey, Edit, apply_edits (the typed foundation of the repair engines)."""
from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

from engine.model import MeshData
from engine.repair.types import (Edit, RepairContext, RepairEngine, UnitState, apply_edits,
                                 face_keys)
from engine.tests.fixtures.build import cube, grid_slab


def _edit(engine="E1", kind="remove", faces=(0,), **kw):
    kw.setdefault("new_faces", None)
    kw.setdefault("new_points", None)
    kw.setdefault("site", 0)
    kw.setdefault("reason", "test")
    kw.setdefault("evidence", {})
    return Edit(engine=engine, kind=kind, faces=tuple(faces), **kw)


def _same_mesh(a: MeshData, b: MeshData):
    for field in ("positions", "uvs", "normals", "face_v", "face_vt", "face_vn", "face_material", "face_line"):
        assert np.array_equal(getattr(a, field), getattr(b, field)), field
    assert a.materials == b.materials and a.coord_decimals == b.coord_decimals


def _renumber_vertices(mesh: MeshData, rng, duplicate: bool) -> MeshData:
    """Same geometry, vertex array shuffled; with `duplicate`, some faces point at a copied row."""
    n = len(mesh.positions)
    order = rng.permutation(n)                 # new row r holds old vertex order[r]
    inverse = np.empty(n, np.int64)
    inverse[order] = np.arange(n)
    positions = mesh.positions[order]
    face_v = inverse[mesh.face_v]
    if duplicate:
        positions = np.vstack([positions, positions])          # row n + r copies row r
        use_copy = rng.random(face_v.shape) < 0.5
        face_v = np.where(use_copy, face_v + n, face_v)
    return replace(mesh, positions=positions, face_v=face_v)


def _permute_faces(mesh: MeshData, perm) -> MeshData:
    return replace(mesh, face_v=mesh.face_v[perm], face_vt=mesh.face_vt[perm], face_vn=mesh.face_vn[perm],
                   face_material=mesh.face_material[perm], face_line=mesh.face_line[perm])


# --- face_keys ---------------------------------------------------------------------------------

def test_face_keys_one_per_face_and_hex_sha256():
    mesh = cube()
    keys = face_keys(mesh, {0: "tex:a"})
    assert len(keys) == mesh.n_faces
    assert all(isinstance(k, str) and len(k) == 64 and int(k, 16) >= 0 for k in keys)
    assert len(set(keys)) == mesh.n_faces                      # distinct triangles, distinct keys


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_face_keys_stable_under_face_vertex_order_and_duplication(seed):
    rng = np.random.default_rng(seed)
    mesh = grid_slab(4, 3)
    looks = {0: "tex:a"}
    base = face_keys(mesh, looks)

    perm = rng.permutation(mesh.n_faces)
    assert face_keys(_permute_faces(mesh, perm), looks) == [base[i] for i in perm]

    for duplicate in (False, True):
        shuffled = _renumber_vertices(mesh, rng, duplicate)
        assert face_keys(shuffled, looks) == base

    # a face may start at any of its three vertices without changing its key
    rolled = replace(mesh, face_v=np.roll(mesh.face_v, int(rng.integers(1, 3)), axis=1))
    assert face_keys(rolled, looks) == base


def test_face_keys_snap_to_the_print_step():
    mesh = grid_slab(2, 2)
    step = 10.0 ** -mesh.coord_decimals
    base = face_keys(mesh, {0: "t"})
    assert face_keys(replace(mesh, positions=mesh.positions + step * 0.2), {0: "t"}) == base
    assert face_keys(replace(mesh, positions=mesh.positions + step * 3), {0: "t"}) != base


def test_face_keys_differ_for_look_and_for_flipped_winding():
    mesh = grid_slab(3, 3)
    base = face_keys(mesh, {0: "tex:a"})
    assert all(a != b for a, b in zip(base, face_keys(mesh, {0: "tex:b"})))
    flipped = replace(mesh, face_v=mesh.face_v[:, ::-1])
    assert all(a != b for a, b in zip(base, face_keys(flipped, {0: "tex:a"})))


def test_face_keys_unknown_material_falls_back_to_material_name():
    mesh = grid_slab(2, 2)
    assert face_keys(mesh, {}) == face_keys(mesh, {0: "material:m0"})
    assert face_keys(mesh, {}) != face_keys(mesh, {0: "tex:a"})


# --- Edit --------------------------------------------------------------------------------------

POINTS = np.array([[1.0, 2.0, 3.0]])


@pytest.mark.parametrize("engine", ["E1", "E2", "E3", "E4", "E6", "E7"])
def test_new_points_from_other_engines_raise(engine):
    with pytest.raises(ValueError, match="new_points"):
        _edit(engine=engine, kind="add", faces=(), new_faces=np.array([[0, 1, 2]]), new_points=POINTS)


@pytest.mark.parametrize("engine,kind", [("E5", "cut"), ("E8", "add")])
def test_new_points_from_e5_and_e8_accepted(engine, kind):
    faces = (0,) if kind == "cut" else ()
    edit = _edit(engine=engine, kind=kind, faces=faces, new_faces=np.array([[0, 1, 2]]), new_points=POINTS)
    assert edit.new_points.shape == (1, 3)


def test_edit_is_frozen_and_validates_vocabulary():
    edit = _edit()
    with pytest.raises(FrozenInstanceError):
        edit.engine = "E2"
    with pytest.raises(ValueError):
        _edit(engine="E9")
    with pytest.raises(ValueError):
        _edit(kind="weld")
    assert edit.decision is None
    assert edit.faces == (0,)


# --- apply_edits -------------------------------------------------------------------------------

def test_apply_edits_no_edits_is_identity():
    mesh = cube()
    out, new_to_old = apply_edits(mesh, [])
    _same_mesh(out, mesh)
    assert out is not mesh and out.face_v is not mesh.face_v           # a copy, never an alias
    assert np.array_equal(new_to_old, np.arange(mesh.n_faces))


def test_apply_edits_remove():
    mesh = grid_slab(3, 3)
    out, m = apply_edits(mesh, [_edit(faces=(1, 4)), _edit(engine="E2", faces=(7,))])
    keep = np.setdiff1d(np.arange(mesh.n_faces), [1, 4, 7])
    assert np.array_equal(m, keep)
    assert np.array_equal(out.face_v, mesh.face_v[keep])
    assert np.array_equal(out.face_vt, mesh.face_vt[keep])
    assert np.array_equal(out.face_material, mesh.face_material[keep])
    assert np.array_equal(out.positions, mesh.positions)


def test_apply_edits_flip_reverses_winding_and_uv_order():
    mesh = grid_slab(2, 2)
    out, m = apply_edits(mesh, [_edit(kind="flip", faces=(0, 3))])
    assert np.array_equal(m, np.arange(mesh.n_faces))
    for f in (0, 3):
        assert np.array_equal(out.face_v[f], mesh.face_v[f][::-1])
        assert np.array_equal(out.face_vt[f], mesh.face_vt[f][::-1])
        assert (out.face_vn[f] == -1).all()          # same rule as fixes.orient.flip_faces: no stale normal
    other = np.setdiff1d(np.arange(mesh.n_faces), [0, 3])
    assert np.array_equal(out.face_v[other], mesh.face_v[other])
    # flipping twice is the original
    twice, _ = apply_edits(out, [_edit(kind="flip", faces=(0, 3))])
    _same_mesh(twice, mesh)


def test_apply_edits_add_appends_faces_with_existing_ids_and_new_points():
    mesh = cube()
    n = len(mesh.positions)
    add = _edit(engine="E8", kind="add", faces=(), new_faces=np.array([[0, 1, 2], [0, 2, n]]),
                new_points=np.array([[5.0, 5.0, 5.0]]), evidence={"material": 0})
    out, m = apply_edits(mesh, [add])
    assert out.n_faces == mesh.n_faces + 2
    assert np.array_equal(m, np.concatenate([np.arange(mesh.n_faces), [-1, -1]]))
    assert np.array_equal(out.face_v[-2:], [[0, 1, 2], [0, 2, n]])
    assert np.array_equal(out.positions[n], [5.0, 5.0, 5.0]) and len(out.positions) == n + 1
    assert (out.face_vt[-2:] == -1).all() and (out.face_vn[-2:] == -1).all()
    assert (out.face_material[-2:] == 0).all()
    assert np.array_equal(out.face_v[:mesh.n_faces], mesh.face_v)


def test_apply_edits_add_without_material_raises():
    with pytest.raises(ValueError, match="material"):
        apply_edits(cube(), [_edit(engine="E8", kind="add", faces=(), new_faces=np.array([[0, 1, 2]]))])


def test_apply_edits_cut_replaces_input_faces_and_inherits_material():
    mesh = grid_slab(2, 2)
    mesh = replace(mesh, materials=["m0", "m1"], face_material=np.where(np.arange(mesh.n_faces) == 2, 1, 0))
    n = len(mesh.positions)
    cut = _edit(engine="E5", kind="cut", faces=(2,), new_faces=np.array([[0, 1, n], [1, 2, n]]),
                new_points=np.array([[1.0, 1.0, 0.0]]))
    out, m = apply_edits(mesh, [cut])
    keep = np.setdiff1d(np.arange(mesh.n_faces), [2])
    assert out.n_faces == len(keep) + 2
    assert np.array_equal(m, np.concatenate([keep, [-1, -1]]))
    assert np.array_equal(out.face_v[-2:], [[0, 1, n], [1, 2, n]])
    assert (out.face_material[-2:] == 1).all()
    assert len(out.positions) == n + 1


def test_apply_edits_new_point_ids_are_local_to_each_edit():
    mesh = grid_slab(2, 2)
    n = len(mesh.positions)
    a = _edit(engine="E5", kind="cut", faces=(0,), new_faces=np.array([[0, 1, n]]), new_points=np.array([[1.0, 1, 0]]))
    b = _edit(engine="E5", kind="cut", faces=(5,), new_faces=np.array([[2, 3, n]]), new_points=np.array([[2.0, 2, 0]]))
    out, _ = apply_edits(mesh, [a, b])
    assert len(out.positions) == n + 2
    assert np.array_equal(out.face_v[-2:], [[0, 1, n], [2, 3, n + 1]])


@pytest.mark.parametrize("first,second", [
    (dict(kind="remove", faces=(1,)), dict(kind="flip", faces=(1,))),
    (dict(kind="remove", faces=(1,)), dict(kind="remove", faces=(1,))),
    (dict(kind="flip", faces=(1, 2)), dict(kind="flip", faces=(2,))),
])
def test_apply_edits_conflicting_edits_raise(first, second):
    with pytest.raises(ValueError, match="conflict"):
        apply_edits(grid_slab(2, 2), [_edit(**first), _edit(engine="E2", **second)])


def test_apply_edits_rejects_bad_face_and_vertex_ids():
    mesh = grid_slab(2, 2)
    with pytest.raises(ValueError):
        apply_edits(mesh, [_edit(faces=(mesh.n_faces,))])
    bad = _edit(engine="E8", kind="add", faces=(), new_faces=np.array([[0, 1, len(mesh.positions)]]),
                evidence={"material": 0})
    with pytest.raises(ValueError):
        apply_edits(mesh, [bad])


def test_apply_edits_does_not_mutate_input_and_keys_follow_the_map():
    mesh = grid_slab(3, 3)
    before = mesh.face_v.copy()
    out, m = apply_edits(mesh, [_edit(faces=(0,)), _edit(engine="E2", faces=(5,))])
    assert np.array_equal(mesh.face_v, before)
    old_keys, new_keys = face_keys(mesh, {0: "t"}), face_keys(out, {0: "t"})
    assert new_keys == [old_keys[i] for i in m]


def test_protocol_and_state_types_exist():
    class Engine:
        name = "E1"

        def plan(self, unit, ctx):
            return []

    engine: RepairEngine = Engine()
    unit = UnitState(mesh=cube(), topo=None, looks={0: "t"}, viewpoints=None, neighbours=[])
    ctx = RepairContext(profile=None, decider=None, validator=None, log=[])
    assert engine.plan(unit, ctx) == []
