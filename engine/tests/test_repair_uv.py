"""K1b: an `Edit` carries the UVs and normals of its new faces; `apply_edits` writes them and the
legacy observer fills them from the stage OUTPUT, so applying the edits reproduces the output's
per-corner UV and normal VALUES (not only its face keys)."""
from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from engine.repair.types import Edit, apply_edits, face_keys
from engine.tests.fixtures.build import cube, grid_slab


def _edit(engine="E7", kind="cut", faces=(0,), **kw):
    kw.setdefault("new_faces", np.array([[0, 1, 2]]))
    kw.setdefault("new_points", None)
    kw.setdefault("site", 0)
    kw.setdefault("reason", "test")
    kw.setdefault("evidence", {"material": 0})
    return Edit(engine=engine, kind=kind, faces=tuple(faces), **kw)


UV = np.array([[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]])
NORMAL = np.array([[[0.0, 0.0, 1.0]] * 3])


def _corner_values(mesh, uv=True):
    """Per face key: the sorted per-corner (position, value) tuples, so a rotated corner order does
    not matter but a value moved to another corner does. A corner without an index reads None."""
    keys = face_keys(mesh, {})
    table = mesh.uvs if uv else mesh.normals
    index = mesh.face_vt if uv else mesh.face_vn
    out = []
    for f in range(mesh.n_faces):
        corners = []
        for c in range(3):
            i = int(index[f, c])
            value = None if i < 0 else tuple(float(x) for x in table[i])
            corners.append((tuple(float(x) for x in mesh.positions[mesh.face_v[f, c]]), value))
        out.append((keys[f], tuple(sorted(corners, key=repr))))
    return Counter(out)


# --- Edit ----------------------------------------------------------------------------------------

def test_edit_without_uv_or_normal_keeps_none():
    edit = _edit()
    assert edit.new_face_uv is None and edit.new_face_normal is None


def test_edit_copies_uv_and_normal_and_makes_them_read_only():
    uv, normal = UV.copy(), NORMAL.copy()
    edit = _edit(new_face_uv=uv, new_face_normal=normal)
    uv[0, 0, 0] = 99.0
    normal[0, 0, 0] = 99.0
    assert edit.new_face_uv[0, 0, 0] == 0.0 and edit.new_face_normal[0, 0, 0] == 0.0
    assert edit.new_face_uv.shape == (1, 3, 2) and edit.new_face_normal.shape == (1, 3, 3)
    assert edit.new_face_uv.dtype == np.float64 and edit.new_face_normal.dtype == np.float64
    for array in (edit.new_face_uv, edit.new_face_normal):
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array[0, 0, 0] = 1.0


@pytest.mark.parametrize("field,bad", [
    ("new_face_uv", np.zeros((2, 3, 2))),        # k differs from new_faces
    ("new_face_uv", np.zeros((1, 3, 3))),        # not 2 coordinates
    ("new_face_uv", np.zeros((1, 2, 2))),        # not 3 corners
    ("new_face_uv", np.zeros((3, 2))),           # not 3-D
    ("new_face_normal", np.zeros((2, 3, 3))),
    ("new_face_normal", np.zeros((1, 3, 2))),
    ("new_face_normal", np.zeros((1, 3))),
])
def test_edit_wrong_shapes_raise(field, bad):
    with pytest.raises(ValueError, match=field):
        _edit(**{field: bad})


@pytest.mark.parametrize("field,shape", [("new_face_uv", (1, 3, 2)), ("new_face_normal", (1, 3, 3))])
@pytest.mark.parametrize("bad", [np.inf, -np.inf, np.nan])
def test_edit_non_finite_values_raise(field, shape, bad):
    array = np.zeros(shape)
    array[0, 1, 0] = bad                       # one corner only: not the whole-face placeholder
    with pytest.raises(ValueError, match="finite"):
        _edit(**{field: array})


@pytest.mark.parametrize("field,shape", [("new_face_uv", (1, 3, 2)), ("new_face_normal", (1, 3, 3))])
def test_edit_a_whole_face_of_nan_is_the_documented_placeholder(field, shape):
    edit = _edit(new_faces=np.array([[0, 1, 2], [0, 2, 3]]), **{field: np.array([np.zeros(shape[1:]),
                                                                                  np.full(shape[1:], np.nan)])})
    assert np.isnan(getattr(edit, field)[1]).all() and np.isfinite(getattr(edit, field)[0]).all()


def test_edit_uv_needs_new_faces():
    with pytest.raises(ValueError, match="new_face_uv"):
        Edit(engine="E1", kind="remove", faces=(0,), new_faces=None, new_points=None, site=0,
             reason="t", evidence={}, new_face_uv=UV)
    with pytest.raises(ValueError, match="new_face_normal"):
        Edit(engine="E1", kind="flip", faces=(0,), new_faces=None, new_points=None, site=0,
             reason="t", evidence={}, new_face_normal=NORMAL)


# --- apply_edits ---------------------------------------------------------------------------------

def test_apply_edits_add_writes_the_uvs_and_normals_of_the_new_faces():
    mesh = cube()
    n_uv, n_vn = len(mesh.uvs), len(mesh.normals)
    uv = np.array([[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]], [[0.7, 0.8], [0.9, 1.0], [0.1, 0.2]]])
    normal = np.array([[[0, 0, 1.0]] * 3, [[0, 1.0, 0]] * 3])
    add = _edit(engine="E8", kind="add", faces=(), new_faces=np.array([[0, 1, 2], [0, 2, 3]]),
                new_face_uv=uv, new_face_normal=normal)
    out, _ = apply_edits(mesh, [add])
    assert np.array_equal(out.face_vt[:mesh.n_faces], mesh.face_vt)       # existing faces untouched
    assert np.array_equal(out.face_vn[:mesh.n_faces], mesh.face_vn)
    assert np.array_equal(out.uvs[:n_uv], mesh.uvs) and np.array_equal(out.normals[:n_vn], mesh.normals)
    assert np.array_equal(out.uvs[out.face_vt[-2:]], uv)
    assert np.array_equal(out.normals[out.face_vn[-2:]], normal)
    assert (out.face_vt[-2:] >= n_uv).all() and (out.face_vn[-2:] >= n_vn).all()


def test_apply_edits_without_uv_or_normal_keeps_minus_one_and_the_tables():
    mesh = cube()
    add = _edit(engine="E8", kind="add", faces=(), new_faces=np.array([[0, 1, 2]]))
    out, _ = apply_edits(mesh, [add])
    assert (out.face_vt[-1] == -1).all() and (out.face_vn[-1] == -1).all()
    assert np.array_equal(out.uvs, mesh.uvs) and np.array_equal(out.normals, mesh.normals)


def test_apply_edits_only_uv_given_leaves_the_normals_minus_one():
    mesh = cube()
    out, _ = apply_edits(mesh, [_edit(engine="E8", kind="add", faces=(), new_face_uv=UV)])
    assert np.array_equal(out.uvs[out.face_vt[-1]], UV[0])
    assert (out.face_vn[-1] == -1).all() and np.array_equal(out.normals, mesh.normals)


def test_apply_edits_cut_pieces_carry_their_uvs_and_normals():
    mesh = grid_slab(2, 2)
    uv = np.array([[[0.0, 0.0], [0.5, 0.0], [0.5, 0.5]], [[0.0, 0.0], [0.5, 0.5], [0.0, 0.5]]])
    normal = np.array([[[0, 0, 1.0]] * 3] * 2)
    cut = _edit(engine="E7", kind="cut", faces=(2,), new_faces=np.array([[0, 1, 2], [0, 2, 3]]),
                new_face_uv=uv, new_face_normal=normal)
    out, new_to_old = apply_edits(mesh, [cut])
    assert (new_to_old[-2:] == -1).all()
    assert np.array_equal(out.uvs[out.face_vt[-2:]], uv)
    assert np.array_equal(out.normals[out.face_vn[-2:]], normal)
    keep = np.setdiff1d(np.arange(mesh.n_faces), [2])
    assert np.array_equal(out.face_vt[:len(keep)], mesh.face_vt[keep])     # survivors keep their ids


def test_apply_edits_a_nan_face_stays_minus_one_while_its_neighbour_gets_values():
    mesh = cube()
    uv = np.array([UV[0], np.full((3, 2), np.nan)])
    normal = np.array([np.full((3, 3), np.nan), NORMAL[0]])
    add = _edit(engine="E8", kind="add", faces=(), new_faces=np.array([[0, 1, 2], [0, 2, 3]]),
                new_face_uv=uv, new_face_normal=normal)
    out, _ = apply_edits(mesh, [add])
    assert np.array_equal(out.uvs[out.face_vt[-2]], UV[0]) and (out.face_vt[-1] == -1).all()
    assert (out.face_vn[-2] == -1).all() and np.array_equal(out.normals[out.face_vn[-1]], NORMAL[0])
    assert np.isfinite(out.uvs).all() and np.isfinite(out.normals).all()   # no NaN ever reaches the mesh


def test_apply_edits_identical_rows_share_one_index_and_the_result_is_deterministic():
    mesh = cube()
    uv = np.array([[[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]], [[0.1, 0.1], [0.3, 0.3], [0.4, 0.4]]])
    add = _edit(engine="E8", kind="add", faces=(), new_faces=np.array([[0, 1, 2], [0, 2, 3]]), new_face_uv=uv)
    out, _ = apply_edits(mesh, [add])
    assert len(out.uvs) == len(mesh.uvs) + 4                  # 6 corners, 4 distinct rows
    assert out.face_vt[-2, 0] == out.face_vt[-1, 0] and out.face_vt[-2, 2] == out.face_vt[-1, 1]
    again, _ = apply_edits(mesh, [add])
    assert np.array_equal(out.uvs, again.uvs) and np.array_equal(out.face_vt, again.face_vt)


def test_apply_edits_does_not_modify_the_input_mesh():
    mesh = cube()
    before = (mesh.uvs.copy(), mesh.normals.copy(), mesh.face_vt.copy(), mesh.face_vn.copy())
    apply_edits(mesh, [_edit(engine="E8", kind="add", faces=(), new_face_uv=UV, new_face_normal=NORMAL)])
    for a, b in zip(before, (mesh.uvs, mesh.normals, mesh.face_vt, mesh.face_vn)):
        assert np.array_equal(a, b)


def test_apply_edits_flip_is_unchanged_it_reverses_vt_and_blanks_vn():
    mesh = grid_slab(2, 2)
    out, _ = apply_edits(mesh, [Edit(engine="E2", kind="flip", faces=(0,), new_faces=None, new_points=None,
                                     site=0, reason="t", evidence={})])
    assert np.array_equal(out.face_vt[0], mesh.face_vt[0][::-1]) and (out.face_vn[0] == -1).all()
    assert np.array_equal(out.uvs, mesh.uvs)
