"""`tools/strict_guard_allowed.py`: the exemption set of `coincident_backface_removed` for the strict guard
(`backface_twin_pairs`, real geometry on a small cube), the replicated render loop forwarding `allowed_pairs`
(`strict_guard_allowed`, fake renderer and comparer), `run_strict_guard`'s two paths and `parse_allow`."""
from types import SimpleNamespace

import numpy as np
import pytest

from engine.tests.fixtures.build import cube
from engine.validate.checks import CBR
from tools import strict_guard_allowed as sga

TOL = 0.15


def cube_with_backface_twin(reverse=True):
    """A closed 10 in cube (faces 0-11, outward) plus a copy of its TOP quad (faces 12, 13): reversed winding
    (normal -z, its front pointing into the solid cube) by default, same-facing with `reverse=False`.
    `(positions_c, face_v, kept_faces, after_face_v)` with the copy removed."""
    mesh = cube()
    top = mesh.face_v[[2, 3]]
    extra = top[:, ::-1] if reverse else top
    face_v = np.vstack([mesh.face_v, extra])
    positions = mesh.positions - (mesh.positions.min(axis=0) + mesh.positions.max(axis=0)) / 2
    kept = np.arange(12)
    return positions, face_v, kept, face_v[kept]


def test_backface_twin_pairs_lists_the_kept_exposed_twin_of_a_hidden_front_removed_face():
    positions, face_v, kept, after = cube_with_backface_twin()
    pairs, report = sga.backface_twin_pairs(positions, face_v, kept, after, TOL)
    assert len(pairs) >= 2
    assert set(np.unique(pairs[:, 0]).tolist()) == {12, 13}, 'both triangles of the removed back-face are excused'
    assert set(np.unique(pairs[:, 1]).tolist()) <= {2, 3}, 'their twins are the top quad, by AFTER id'
    assert report['excused_faces'] == 2 and report['pairs'] == len(pairs) and report['rule'] == CBR
    assert report['removed_faces'] == 2 and report['removed_hidden_front'] == 2
    assert report['kept_front_exposed'] == 12 and report['guard_class'] == 'allowed_backface_twin'
    assert report['exposure_n_dirs'] == 128 and report['depth_tol_inches'] == TOL


def test_a_same_facing_duplicate_is_not_a_backface_twin():
    positions, face_v, kept, after = cube_with_backface_twin(reverse=False)
    pairs, report = sga.backface_twin_pairs(positions, face_v, kept, after, TOL)
    assert len(pairs) == 0 and report['pairs'] == 0 and report['excused_faces'] == 0
    assert report['removed_hidden_front'] == 0, 'a same-facing copy of the top is front-exposed like the top'


def test_a_removed_face_whose_front_is_exposed_is_never_excused():
    positions, face_v, _kept, _after = cube_with_backface_twin()
    kept = np.array([0, 1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13])          # the TOP is removed, its back-face kept
    pairs, report = sga.backface_twin_pairs(positions, face_v, kept, face_v[kept], TOL)
    assert len(pairs) == 0
    assert report['removed_faces'] == 2 and report['removed_hidden_front'] == 0


def test_a_listed_twin_beyond_the_tolerance_is_not_coincident():
    positions, face_v, kept, after = cube_with_backface_twin()
    # the copy shares the cube's vertices, so give it its own, 1 in below the top (inside the cube)
    extra_pts = positions[face_v[12:].ravel()] + np.array([0.0, 0.0, -1.0])
    positions2 = np.vstack([positions, extra_pts])
    face_v2 = face_v.copy()
    face_v2[12:] = np.arange(len(positions), len(positions) + 6).reshape(2, 3)
    pairs, report = sga.backface_twin_pairs(positions2, face_v2, kept, face_v2[kept], TOL)
    assert report['removed_hidden_front'] == 2, 'still hidden inside the cube'
    assert len(pairs) == 0, '1 in off the top plane is not within the 0.15 in tolerance'


def test_after_index_of_kept_handles_both_layouts():
    before = np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11]])
    e5_after = before[[0, 2]]
    assert sga.after_index_of_kept(before, e5_after, [0, 2]).tolist() == [0, -1, 1, -1]
    e4_after = np.vstack([before[[2]], [[20, 21, 22]], before[[0]]])
    assert sga.after_index_of_kept(before, e4_after, [0, 2]).tolist() == [2, -1, 0, -1]
    with pytest.raises(ValueError, match='not in AFTER'):
        sga.after_index_of_kept(before, e5_after, [0, 1])


def _mesh(face_v, n_materials=1):
    positions, _ = cube_with_backface_twin()[:2]
    return SimpleNamespace(positions=positions + 1000.0, face_v=np.asarray(face_v), n_faces=len(face_v),
                           face_material=np.zeros(len(face_v), np.int64), sig_digits=6)


def test_strict_guard_allowed_replicates_the_render_loop_and_forwards_the_pairs():
    _p, face_v, kept, after_v = cube_with_backface_twin()
    before, after, source = _mesh(face_v), _mesh(after_v), _mesh(face_v)
    provenance = {'source_to_engine': np.eye(4).tolist()}
    renders, views_seen, compared = [], [], {}

    def fake_render(positions, faces, ids, view, frame, size, factory):
        renders.append((len(faces), tuple(view), size))
        assert np.array_equal(frame, positions) and len(ids) == len(faces)
        return SimpleNamespace(tri=np.full((2, 3), -1), depth=np.full((2, 3), np.inf))

    def fake_compare(before_views, after_views, mat_b, mat_a, flat, depth_tol, **kw):
        compared.update(kw, n_before=len(before_views), n_after=len(after_views), depth_tol=depth_tol, flat=flat)
        return SimpleNamespace(passed=True, totals={'allowed_backface_twin': 3})

    pairs = np.array([[12, 2], [13, 3]])
    report, tol = sga.strict_guard_allowed(before, after, source, provenance, allowed_pairs=pairs,
                                           on_view=lambda label, i: views_seen.append((label, i)),
                                           render=fake_render, compare=fake_compare)
    assert report.totals['allowed_backface_twin'] == 3
    assert len(renders) == 52 and {r[2] for r in renders} == {(900, 600)}
    assert [r[0] for r in renders] == [14] * 26 + [12] * 26
    assert views_seen[0] == ('Before', 1) and views_seen[25] == ('Before', 26) and views_seen[-1] == ('After', 26)
    assert compared['n_before'] == compared['n_after'] == 26 and compared['strict'] is True
    assert compared['crack_closed_cap'] == 0.0 and compared['fragment_removed_cap'] == 0.0 and compared['flat'] == ()
    assert np.array_equal(compared['allowed_pairs'], pairs)
    assert compared['depth_tol'] == tol == sga.guard_frame(before, source, provenance)[1]
    assert compared['plane_before'].shape == (14, 4) and compared['geometry_after'][1].shape == (12, 3)


def test_run_strict_guard_uses_the_helper_without_allowances_and_the_class_with(monkeypatch):
    _p, face_v, kept, after_v = cube_with_backface_twin()
    before, after, source = _mesh(face_v), _mesh(after_v), _mesh(face_v)
    provenance = {'source_to_engine': np.eye(4).tolist()}
    helper_calls = []

    def helper_guard(b, a, s, p, *, caster_factory=None, on_view=None):
        helper_calls.append(caster_factory)
        return SimpleNamespace(passed=False, totals={'material_changed': 2}), 0.15

    helper = SimpleNamespace(strict_guard=helper_guard)
    report, tol, fields = sga.run_strict_guard(helper, before, after, source, provenance, kept_faces=kept, allowed_changes=[])
    assert helper_calls == [None] and report.passed is False and tol == 0.15
    assert fields == dict(guard_caller='unchanged helper strict_guard', allowed_changes=[], guard_class=None,
                          allowed_pairs=None, excused_px=0, raw_totals=None, failed_by=None)

    seen = {}

    def fake_pairs(positions, fv, kept_faces, after_fv, depth_tol, *, caster_factory, n_dirs):
        seen.update(n_dirs=n_dirs, kept=list(kept_faces), exposure_caster=caster_factory.__name__)
        return np.array([[12, 2]]), {'pairs': 1, 'excused_faces': 1}

    def fake_allowed(b, a, s, p, *, allowed_pairs, caster_factory=None, on_view=None):
        seen.update(pairs=allowed_pairs.tolist(), render_caster=caster_factory)
        return SimpleNamespace(passed=True, totals={'allowed_backface_twin': 9, 'material_changed': 0},
                               raw_totals={'allowed_backface_twin': 0, 'material_changed': 9}, failed_by={}), 0.15

    monkeypatch.setattr(sga, 'backface_twin_pairs', fake_pairs)
    monkeypatch.setattr(sga, 'strict_guard_allowed', fake_allowed)

    class Oracle:
        pass

    report, tol, fields = sga.run_strict_guard(helper, before, after, source, provenance, kept_faces=kept,
                                               allowed_changes=[CBR], audit={'engine_report': {'exposure_n_dirs': 64}},
                                               caster_factory=Oracle)
    assert helper_calls == [None], 'the helper strict_guard is not the caller under the class'
    assert report.passed is True
    assert seen == dict(n_dirs=64, kept=list(range(12)), exposure_caster='EmbreeCaster', pairs=[[12, 2]], render_caster=Oracle)
    assert fields['allowed_changes'] == [CBR] and fields['guard_class'] == 'allowed_backface_twin'
    assert fields['allowed_pairs'] == {'pairs': 1, 'excused_faces': 1} and fields['excused_px'] == 9
    assert fields['raw_totals'] == {'allowed_backface_twin': 0, 'material_changed': 9} and fields['failed_by'] == {}
    assert 'strict_guard_allowed' in fields['guard_caller'] and 'Oracle' in fields['guard_caller']


def test_parse_allow_knows_only_the_validator_class_names():
    assert sga.parse_allow([]) == [] and sga.parse_allow(None) == []
    assert sga.parse_allow([CBR, CBR]) == [CBR]
    with pytest.raises(ValueError, match='unknown allowed-change class'):
        sga.parse_allow(['growth'])
