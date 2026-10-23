from dataclasses import replace

import numpy as np
import pytest

from engine.fixes.pipeline import FixProfile
from engine.repair.types import RepairContext, UnitState, apply_edits
from engine.tests.fixtures.build import _mesh


def seam():
    mesh = _mesh('seam', [[0, 0, 0], [4, 0, 0], [0, 4, 0], [2, 0, 0], [2, -2, 0]],
        [[.2, .1], [2.2, .1], [.2, 2.1], [9, 9], [8, 9], [9, 8]],
        [[0, 1, 2], [3, 0, 4]], [[0, 1, 2], [3, 4, 5]],
        materials=('wall', 'trim'), face_material=[0, 1], coord_decimals=12)
    mesh.physical_quanta = (.01, .01, .01)
    mesh.normals = np.array([[0, 0, 1], [0, .6, .8], [.6, 0, .8], [0, 0, -1]], float)
    mesh.face_vn = np.array([[0, 1, 2], [3, 3, 3]])
    return mesh


def planned(mesh):
    from engine.repair.engines.e7_thread import E7Thread
    engine = E7Thread()
    edits = engine.plan(UnitState(mesh, None, {0: 'wall', 1: 'trim'}, None),
                        RepairContext(FixProfile(), None, None))
    return edits, engine.report


def test_existing_edge_is_split_at_used_vertex_without_rebuilding_neighbour():
    mesh = seam()
    before = {key: value.copy() for key, value in vars(mesh).items() if isinstance(value, np.ndarray)}
    edits, report = planned(mesh)
    assert len(edits) == 1 and report['proposed'] == 1
    edit = edits[0]
    assert (edit.engine, edit.kind, edit.faces, edit.site, edit.legacy) == ('E7', 'cut', (0,), 0, False)
    assert edit.new_points is None
    np.testing.assert_array_equal(edit.new_faces, [[0, 3, 2], [3, 1, 2]])
    after, _ = apply_edits(mesh, edits)
    np.testing.assert_array_equal(after.positions, mesh.positions)
    assert after.face_material.tolist() == [1, 0, 0]
    np.testing.assert_array_equal(after.face_v[0], [3, 0, 4])
    for key, value in before.items():
        np.testing.assert_array_equal(getattr(mesh, key), value)


def test_uv_and_normals_interpolate_source_triangle_and_keep_shared_seam():
    mesh = seam()
    edits, _ = planned(mesh)
    np.testing.assert_allclose(edits[0].new_face_uv,
        [[[.2, .1], [1.2, .1], [.2, 2.1]], [[1.2, .1], [2.2, .1], [.2, 2.1]]])
    np.testing.assert_allclose(edits[0].new_face_normal,
        [[[0, 0, 1], [0, .3, .9], [.6, 0, .8]], [[0, .3, .9], [0, .6, .8], [.6, 0, .8]]])
    after, _ = apply_edits(mesh, edits)
    np.testing.assert_array_equal(after.uvs[after.face_vt[0]], [[9, 9], [8, 9], [9, 8]])
    np.testing.assert_array_equal(after.normals[after.face_vn[0]], [[0, 0, -1]] * 3)


def test_reverse_winding_is_preserved():
    mesh = seam()
    mesh.face_v[0] = mesh.face_v[0, ::-1]
    mesh.face_vt[0] = mesh.face_vt[0, ::-1]
    mesh.face_vn[0] = mesh.face_vn[0, ::-1]
    edits, _ = planned(mesh)
    tri = mesh.positions[edits[0].new_faces]
    assert (np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])[:, 2] < 0).all()


def test_absent_source_corner_attributes_stay_absent():
    mesh = seam()
    mesh.face_vt[:] = -1
    mesh.face_vn[:] = -1
    edits, _ = planned(mesh)
    assert edits[0].new_face_uv is None and edits[0].new_face_normal is None
    after, _ = apply_edits(mesh, edits)
    assert (after.face_vt == -1).all() and (after.face_vn == -1).all()


@pytest.mark.parametrize('offset', [.01, 5e-10])
def test_off_edge_point_cannot_move_original_cut_boundary(offset):
    mesh = seam()
    mesh.positions[3, 1] = -offset
    edits, _ = planned(mesh)
    assert edits == []


def test_off_plane_point_inside_thread_search_tolerance_is_refused():
    mesh = seam()
    mesh.positions[3, 2] = 5e-10
    assert planned(mesh)[0] == []


def test_overlapped_source_triangles_are_refused():
    mesh = seam()
    for key in ('face_v', 'face_vt', 'face_vn'):
        setattr(mesh, key, np.vstack([getattr(mesh, key), getattr(mesh, key)[0]]))
    mesh.face_material = np.array([0, 1, 0])
    mesh.face_line = np.array([1, 2, 3])
    edits, report = planned(mesh)
    assert edits == [] and report['refused'].get('overlap') == 2


@pytest.mark.parametrize('degenerate', [False, True])
def test_unused_or_degenerate_only_vertex_does_not_create_a_cut(degenerate):
    mesh = seam()
    if degenerate:
        mesh.face_v[1] = [0, 3, 1]
    else:
        for key in ('face_v', 'face_vt', 'face_vn', 'face_material', 'face_line'):
            setattr(mesh, key, getattr(mesh, key)[:1])
    assert planned(mesh)[0] == []


@pytest.mark.parametrize('pieces', [
    [[0, 3, 2]],
    [[0, 2, 3], [3, 1, 2]],
    [[0, 3, 2], [3, 1, 2], [0, 3, 2]],
])
def test_malformed_thread_result_cannot_change_boundary_winding_or_area(monkeypatch, pieces):
    import engine.repair.engines.e7_thread as module
    monkeypatch.setattr(module, '_thread_output', lambda *args: ([], {0: pieces}, set()))
    assert planned(seam())[0] == []


@pytest.mark.parametrize('field', ['face_vt', 'face_vn'])
def test_partial_source_corner_attribute_is_refused(field):
    mesh = seam()
    getattr(mesh, field)[0, 0] = -1
    assert planned(mesh)[0] == []


def test_default_checked_wrapper_preserves_visible_textured_triangle():
    from engine.validate.checks import Looks
    from tools.main_infra_e7 import run_checked_e7
    mesh = seam()
    looks = Looks(key={'wall': 'wall', 'trim': 'trim'}, texel={'wall': (256, 256)}, flat=frozenset({'trim'}))
    result = run_checked_e7(mesh, looks)
    assert len(result.kept) == 1 and result.rolled_back == []
    assert result.checks[0]['legacy'] is False and result.checks[0]['rollback'] is True
    assert result.checks[0]['final'] == 'PASS'
    assert result.mesh.n_faces == 3
    np.testing.assert_array_equal(result.mesh.positions, mesh.positions)


def test_default_checked_wrapper_rolls_back_faulty_visible_uv_cut(monkeypatch):
    from engine.repair.engines.e7_thread import E7Thread
    from engine.validate.checks import Looks
    from tools.main_infra_e7 import run_checked_e7
    original = E7Thread.plan
    def wrong_uv(self, unit, ctx):
        return [replace(edit, new_face_uv=edit.new_face_uv + .25) for edit in original(self, unit, ctx)]
    monkeypatch.setattr(E7Thread, 'plan', wrong_uv)
    mesh = seam()
    looks = Looks(key={'wall': 'wall', 'trim': 'trim'}, texel={'wall': (256, 256)}, flat=frozenset({'trim'}))
    result = run_checked_e7(mesh, looks)
    assert result.kept == [] and len(result.rolled_back) == 1
    assert result.checks[0]['first'] == 'FAIL'
    assert result.checks[0]['final'] == 'NOTHING KEPT'
    np.testing.assert_array_equal(result.mesh.face_v, mesh.face_v)
    np.testing.assert_array_equal(result.mesh.face_vt, mesh.face_vt)
