"""The checked E4 run, its region mapping, the saved pair and its readback (MAIN-INFRA-E4-MERGE-20261023)."""
import json
from dataclasses import replace

import numpy as np
import pytest

from engine.io.minecraft_floor import Frame, parse_floor
from engine.io.obj_reader import read_obj
from engine.repair.kernel import KernelResult
from engine.repair.types import Edit, apply_edits
from engine.tests.test_validate_checks import _looks

FRAME = Frame(1000 / 25.4, 'owner metre/block; Y-up')
#: "glass" is textured (std above the flat threshold); "facade" has no texture.
FLATNESS = {'glass': 50.0}

# a 2 x 1 (source units) flat glass panel in the y = 0 plane (source Y-up: engine z), cut into 4 slivers
# with two T-vertices on its diagonal, plus one far-off facade triangle that must survive untouched
FLOOR = '''mtllib materials.mtl
v 0 0 0
v 2 0 0
v 2 0 1
v 0 0 1
v 0.6666666666666666 0 0.3333333333333333
v 1.3333333333333333 0 0.6666666666666666
v 10 0 0
v 11 0 0
v 10 0 1
vt 0 0
vt 1 0
vt 1 0.5
vt 0 0.5
vt 0.3333333333333333 0.16666666666666666
vt 0.6666666666666666 0.3333333333333333
vn 0 1 0
o panel
g glass_panel
usemtl glass
f 1/1/1 2/2/1 3/3/1
f 1/1/1 5/5/1 4/4/1
f 5/5/1 6/6/1 4/4/1
f 6/6/1 3/3/1 4/4/1
o far
g facade_bit
usemtl facade
f 7/1/1 8/2/1 9/4/1
'''


def floor():
    return parse_floor(FLOOR, name='fixture')


def pair():
    source = floor()
    engine = source.in_frame(FRAME)
    return engine, source


def looks():
    return _looks('glass', 'facade')


def _areas(mesh):
    tri = mesh.positions[mesh.face_v]
    return 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)


def test_checked_e4_merges_the_panel_keeps_the_facade_and_maps_the_region():
    from tools.main_infra_e4 import run_checked_e4
    engine, _source = pair()
    before = engine.mesh
    outcome, mapping = run_checked_e4(before, looks(), FLATNESS)
    (check,) = outcome.checks
    assert check['stage'] == 'E4' and check['engine'] == 'E4' and check['final'] == 'PASS'
    assert outcome.mesh.n_faces == 3 and len(outcome.kept) == 1 and outcome.rolled_back == []
    np.testing.assert_array_equal(outcome.mesh.positions, before.positions)
    assert mapping['mode'] == 'e4_coplanar_merge' and mapping['input_triangles'] == 5 and mapping['output_triangles'] == 3
    assert mapping['kept_source_faces'] == [4]
    (region,) = mapping['regions']
    assert region['source_faces'] == [0, 1, 2, 3] and region['new_triangles'] == [1, 2]
    assert region['material'] == 'glass' and region['area_before'] == pytest.approx(region['area_after'], rel=1e-9)
    assert region['area_before'] == pytest.approx(_areas(before)[:4].sum())
    assert len(mapping['appended_uvs']) == len(outcome.mesh.uvs) - len(before.uvs)
    assert all(v < len(before.positions) for tri in region['face_v'] for v in tri)


def _outcome(before, kept, rolled=(), *, final='PASS'):
    after, _ = apply_edits(before, list(kept))
    return KernelResult(mesh=after, result=None, edits=list(kept) + list(rolled), stages=[], report=None,
                        kept=list(kept), rolled_back=list(rolled),
                        checks=[dict(stage='E4', engine='E4', legacy=False, rollback=True, final=final)], records=[])


def _cut(before, faces=(0, 1, 2, 3), **changes):
    tri = before.face_v[list(faces)]
    uv = before.uvs[before.face_vt[list(faces)]]
    edit = Edit('E4', 'cut', tuple(faces), tri, None, 0, 'merge', {'region': 0}, new_face_uv=uv)
    return replace(edit, **changes)


def test_merged_mapping_refuses_any_other_engine_kind_new_point_or_unconfirmed_site():
    from tools.main_infra_e4 import merged_mapping
    before = pair()[0].mesh
    with pytest.raises(ValueError, match='E4'):
        merged_mapping(before, _outcome(before, [_cut(before, engine='E7')]))
    with pytest.raises(ValueError, match='E4'):
        merged_mapping(before, _outcome(before, [replace(_cut(before), kind='remove', new_faces=None, new_face_uv=None)]))
    with pytest.raises(ValueError, match='legacy|E4'):
        merged_mapping(before, _outcome(before, [_cut(before, legacy=True)]))
    with pytest.raises(ValueError, match='unconfirmed|PASS'):
        merged_mapping(before, _outcome(before, [_cut(before)], final='FAIL'))
    outcome = _outcome(before, [_cut(before)])
    outcome.mesh = replace(outcome.mesh, positions=outcome.mesh.positions + 1e-6)
    with pytest.raises(ValueError, match='positions'):
        merged_mapping(before, outcome)


def test_a_rolled_back_region_is_copied_through_and_listed_as_kept_source_faces():
    from tools.main_infra_e4 import merged_mapping
    before = pair()[0].mesh
    mapping = merged_mapping(before, _outcome(before, [], [_cut(before)], final='NOTHING KEPT'))
    assert mapping['kept_source_faces'] == [0, 1, 2, 3, 4] and mapping['regions'] == []


def test_save_merged_pair_round_trips_both_frames_and_refuses_existing_output(tmp_path):
    from tools.main_infra_e4 import run_checked_e4, save_merged_pair, verify_merged_mesh
    engine, source = pair()
    outcome, mapping = run_checked_e4(engine.mesh, looks(), FLATNESS)
    out = tmp_path / 'e4' / '7F'
    eng_path, src_path, map_path = save_merged_pair(engine, source, mapping, out)
    assert eng_path.name == 'candidate.engine.obj' and src_path.name == 'candidate.source.obj'
    assert map_path.name == 'region-map.json' and json.loads(map_path.read_text()) == mapping
    eng_after, src_after = read_obj(eng_path), read_obj(src_path)
    verify_merged_mesh(engine.mesh, eng_after, mapping)
    verify_merged_mesh(source.mesh, src_after, mapping, rotation=FRAME.rotation)
    for name in ('face_v', 'face_vt', 'face_vn'):
        np.testing.assert_array_equal(getattr(eng_after, name), getattr(outcome.mesh, name))
    # read_obj numbers materials by first use, so compare names: the kept facade first, then the merged glass
    assert [eng_after.materials[m] for m in eng_after.face_material] == ['facade', 'glass', 'glass']
    assert [outcome.mesh.materials[m] for m in outcome.mesh.face_material] == ['facade', 'glass', 'glass']
    np.testing.assert_array_equal(eng_after.uvs, outcome.mesh.uvs)
    np.testing.assert_array_equal(src_after.positions, source.mesh.positions)
    # the source candidate's new triangles lie in the panel plane (y = 0) and inside the panel
    new = src_after.positions[src_after.face_v[1:]]
    assert np.abs(new[:, :, 1]).max() == 0.0
    assert new[:, :, 0].min() >= 0 and new[:, :, 0].max() <= 2 and new[:, :, 2].min() >= 0 and new[:, :, 2].max() <= 1
    text = src_path.read_text()
    assert text.count('o panel') == 1 and text.count('g glass_panel') == 1 and 'usemtl facade' in text
    with pytest.raises(ValueError, match='exists'):
        save_merged_pair(engine, source, mapping, out)


def test_verify_merged_mesh_refuses_a_triangle_outside_its_region_or_a_changed_kept_face(tmp_path):
    from tools.main_infra_e4 import merged_mesh, run_checked_e4, verify_merged_mesh
    engine, _source = pair()
    before = engine.mesh
    _outcome_, mapping = run_checked_e4(before, looks(), FLATNESS)
    good = merged_mesh(before, mapping)
    verify_merged_mesh(before, good, mapping)
    outside = json.loads(json.dumps(mapping))
    outside['regions'][0]['face_v'][0][0] = 6                  # a facade vertex, off the panel's footprint
    with pytest.raises(ValueError, match='footprint|plane'):
        verify_merged_mesh(before, merged_mesh(before, outside), outside)
    moved = replace(good, face_v=np.vstack([good.face_v[:1][:, ::-1], good.face_v[1:]]))
    with pytest.raises(ValueError, match='kept'):
        verify_merged_mesh(before, moved, mapping)
    grown = replace(good, positions=np.vstack([good.positions, [[0.0, 0.0, 0.0]]]))
    with pytest.raises(ValueError, match='positions'):
        verify_merged_mesh(before, grown, mapping)


def test_floor_from_candidate_keeps_groups_and_objects_per_face(tmp_path):
    from tools.main_infra_e4 import floor_from_candidate
    path = tmp_path / 'candidate.source.obj'
    path.write_text(FLOOR, encoding='utf-8')
    got = floor_from_candidate(path)
    assert got.frame is None and got.mesh.n_faces == 5
    assert [(p.object_name, p.group) for p in got.polygons] == [('panel', 'glass_panel')] * 4 + [('far', 'facade_bit')]
    np.testing.assert_array_equal(got.triangle_polygon, np.arange(5))


def test_the_floor_runner_refuses_an_existing_output_before_reading_anything(tmp_path):
    from tools.run_checked_e4_floor import main
    (tmp_path / 'e4' / '7F').mkdir(parents=True)
    with pytest.raises(ValueError, match='existing'):
        main(['--root', str(tmp_path), '--floor', '7F', '--raw-name', '7th floor main infra.obj'])
