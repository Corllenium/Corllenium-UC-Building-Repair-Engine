"""K1b item 2: the legacy observer fills `new_face_uv` / `new_face_normal` from the stage OUTPUT, so
`apply_edits(stage_input, stage_edits)` reproduces the output's per-corner UV and normal VALUES."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace

import numpy as np

from engine.repair.engines.legacy import FaceView, observe
from engine.repair.types import apply_edits
from engine.tests.fixtures.build import cube, gridded_box
from engine.tests.test_repair_uv import _corner_values


def _with_uvs(mesh, face_v, uv_rows, normal_rows=None, material=None):
    """`mesh` with the faces `face_v`, each carrying its own new UV (and normal) rows."""
    n = len(face_v)
    uvs = np.vstack([mesh.uvs, np.asarray(uv_rows, float).reshape(-1, 2)])
    vt = np.arange(n * 3).reshape(n, 3) + len(mesh.uvs)
    normals, vn = mesh.normals, np.full((n, 3), -1, np.int64)
    if normal_rows is not None:
        normals = np.vstack([mesh.normals, np.asarray(normal_rows, float).reshape(-1, 3)])
        vn = np.arange(n * 3).reshape(n, 3) + len(mesh.normals)
    return replace(mesh, uvs=uvs, normals=normals, face_v=np.asarray(face_v, np.int64), face_vt=vt,
                   face_vn=vn, face_material=np.zeros(n, np.int64) if material is None else material,
                   face_line=np.arange(n, dtype=np.int64))


def _rows(n, seed):
    return np.random.default_rng(seed).random((n * 3, 2)) * 5 - 2


def test_observed_cut_edits_reproduce_the_outputs_uv_and_normal_values():
    before = gridded_box(2, 2.5)
    a, b, c = (int(v) for v in before.face_v[0])
    d = next(int(v) for v in before.face_v[1] if v not in (a, b, c))
    face_v = [[a, b, d], [b, c, d], *before.face_v[2:]]
    n = len(face_v)
    after = _with_uvs(before, face_v, _rows(n, 1), np.random.default_rng(2).random((n * 3, 3)),
                      before.face_material)
    # the surviving faces keep the look they had: only the two new pieces are being tested
    edits = observe(FaceView(before, None, {}), FaceView(after, None, {}), stage="merge", site=6,
                    engine="E7", mode="cut")
    cuts = [e for e in edits if e.kind == "cut"]
    assert cuts and all(e.new_face_uv is not None and e.new_face_normal is not None for e in cuts)
    applied, _ = apply_edits(before, edits)
    new = Counter()
    for e in cuts:
        new.update(e.evidence["added_keys"])
    got, want = _corner_values(applied), _corner_values(after)
    added = set(new)
    assert {k: v for k, v in got.items() if k[0] in added} == {k: v for k, v in want.items() if k[0] in added}
    got_n, want_n = _corner_values(applied, uv=False), _corner_values(after, uv=False)
    assert {k: v for k, v in got_n.items() if k[0] in added} == {k: v for k, v in want_n.items() if k[0] in added}


def test_observed_solidify_add_reproduces_the_outputs_uvs():
    before = cube()
    n = len(before.positions)
    positions = np.vstack([before.positions, [[0.0, 0.0, -5.0], [10.0, 0.0, -5.0]]])
    face_v = [*before.face_v, [0, n, n + 1], [0, n + 1, 1]]
    rows = _rows(len(face_v), 3)
    after = _with_uvs(replace(before, positions=positions), face_v, rows,
                      material=np.zeros(len(face_v), np.int64))
    edits = observe(FaceView(before, None, {}), FaceView(after, None, {}), stage="solidify", site=0,
                    engine="E8")
    add = next(e for e in edits if e.kind == "add")
    assert add.new_face_uv.shape == (2, 3, 2) and add.new_face_normal is None
    assert np.array_equal(add.new_face_uv.reshape(-1, 2), rows[-6:])
    applied, _ = apply_edits(before, edits)
    got, want = _corner_values(applied), _corner_values(after)
    new = set(add.evidence["added_keys"])
    assert {k: v for k, v in got.items() if k[0] in new} == {k: v for k, v in want.items() if k[0] in new}


def test_observed_face_without_a_uv_in_the_output_stays_without_one():
    before = cube()
    n = len(before.positions)
    positions = np.vstack([before.positions, [[0.0, 0.0, -5.0], [10.0, 0.0, -5.0]]])
    face_v = [*before.face_v, [0, n, n + 1], [0, n + 1, 1]]
    rows = _rows(len(face_v), 4)
    after = _with_uvs(replace(before, positions=positions), face_v, rows,
                      material=np.zeros(len(face_v), np.int64))
    vt = after.face_vt.copy()
    vt[-2] = -1                                                 # the first new face has no UV
    after = replace(after, face_vt=vt)
    edits = observe(FaceView(before, None, {}), FaceView(after, None, {}), stage="solidify", site=0,
                    engine="E8")
    add = next(e for e in edits if e.kind == "add")
    applied, _ = apply_edits(before, edits)
    assert (applied.face_vt[-2] == -1).all() and (applied.face_vt[-1] >= 0).all()
    assert np.isfinite(applied.uvs).all()


def test_observed_adds_with_no_uv_in_the_output_pass_none():
    before = cube()
    n = len(before.positions)
    positions = np.vstack([before.positions, [[0.0, 0.0, -5.0], [10.0, 0.0, -5.0]]])
    face_v = np.array([*before.face_v, [0, n, n + 1]])
    m = len(face_v)
    after = replace(before, positions=positions, face_v=face_v,
                    face_vt=np.vstack([before.face_vt, [[-1, -1, -1]]]),
                    face_vn=np.vstack([before.face_vn, [[-1, -1, -1]]]),
                    face_material=np.zeros(m, np.int64), face_line=np.arange(m, dtype=np.int64))
    edits = observe(FaceView(before, None, {}), FaceView(after, None, {}), stage="solidify", site=0,
                    engine="E8")
    add = next(e for e in edits if e.kind == "add")
    assert add.new_face_uv is None and add.new_face_normal is None
    applied, _ = apply_edits(before, edits)
    assert (applied.face_vt[-1] == -1).all()
