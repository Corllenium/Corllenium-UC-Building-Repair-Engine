import json
from pathlib import Path

import numpy as np
import pytest

from engine.guard.compare import (PX_HOLE, PX_MATERIAL_CHANGED, PX_MOVED_OTHER, PX_OK,
                                 _displacement, classify_pixels, compare_views, face_planes)
from engine.guard.views import ortho_first_hit
from engine.tests.fixtures.build import cube


def actual_witnesses():
    return json.loads((Path(__file__).parent/'fixtures/guard_2f_f64_witnesses.json').read_text())


def classify_one(plane_before, plane_after, *, depth_before=1.0, depth_after=1.0,
                 direction=(0.0, 0.0, 1.0), origin=(0.0, 0.0, 0.0), tolerance=0.15):
    return classify_pixels(np.array([depth_before]), np.array([0]), np.array([depth_after]),
                           np.array([0]), np.array([0]), np.array([0]), frozenset(), tolerance,
                           origins=np.array([origin]), direction=np.array(direction),
                           plane_before=np.array([plane_before]), plane_after=np.array([plane_after]))[0]


def test_actual_2f_unchanged_planes_do_not_move_at_the_original_tolerance():
    data=actual_witnesses();rows=data['witnesses'];count=len(rows)
    before=np.array([r['before_depth_inches'] for r in rows]);after=np.array([r['after_depth_inches'] for r in rows])
    origins=np.array([r['origin_inches'] for r in rows]);pb=np.array([r['before_plane'] for r in rows]);pa=np.array([r['after_plane'] for r in rows])
    assert count==24 and all(r['original_before_face']==r['after_original_face'] for r in rows)
    np.testing.assert_array_equal(pb,pa)
    assert min(r['old_plane_residual_inches'] for r in rows)>data['guard_depth_tol_inches']
    moved=_displacement(before,np.arange(count),after,np.arange(count),np.ones(count,bool),origins,np.array(data['direction']),pb,pa)
    np.testing.assert_array_equal(moved,np.zeros(count))
    codes=classify_pixels(before,np.arange(count),after,np.arange(count),np.zeros(count,int),np.zeros(count,int),frozenset(),data['guard_depth_tol_inches'],origins=origins,direction=np.array(data['direction']),plane_before=pb,plane_after=pa)
    np.testing.assert_array_equal(codes,np.zeros(count,np.uint8))


def test_genuine_float32_render_of_unchanged_cube_is_not_surface_movement():
    m=cube(1417.3228346456694);positions=m.positions-708.6614173228347;ids=np.arange(len(m.face_v));view=(-.987,.007,-.989)
    b=ortho_first_hit(positions,m.face_v,ids,view,positions,(18,12));planes=face_planes(positions,m.face_v)
    report=compare_views([(view,b)],[(view,b)],m.face_material,m.face_material,frozenset(),5.905511811023622e-6,strict=True,plane_before=planes,plane_after=planes)
    assert report.totals['model_px']>0
    assert report.totals['moved_other']==0 and report.passed


@pytest.mark.parametrize('scale',[1e-5,1.0,1e5])
@pytest.mark.parametrize('multiple,want',[(.5,PX_OK),(2.0,PX_MOVED_OTHER),(-.5,PX_OK),(-2.0,PX_MOVED_OTHER)])
def test_true_parallel_plane_translation_uses_the_same_quantum_tolerance(scale,multiple,want):
    tolerance=1.5e-6*scale;z=3.0*scale
    assert classify_one([0,0,1,-z],[0,0,1,-(z+multiple*tolerance)],depth_before=float(np.float32(z)),depth_after=float(np.float32(z+multiple*tolerance)),tolerance=tolerance)==want


@pytest.mark.parametrize('multiple,want',[(.5,PX_OK),(2.0,PX_MOVED_OTHER)])
def test_grazing_original_planes_measure_normal_translation_not_ray_depth(multiple,want):
    tolerance=1.5e-6;direction=np.array([1.0,0.0,-1e-9]);direction/=np.linalg.norm(direction)
    assert classify_one([0,0,1,-1],[0,0,1,-(1+multiple*tolerance)],direction=direction,origin=(0,0,2),depth_before=1e9,depth_after=1e9,tolerance=tolerance)==want


def test_same_reported_depth_does_not_hide_a_changed_supporting_plane():
    assert classify_one([0,0,1,-1],[0,0,1,-1.3],depth_before=1,depth_after=1)==PX_MOVED_OTHER


def test_rotated_plane_displacement_is_measured_on_both_supporting_planes():
    assert classify_one([0,0,1,-1],[.6,0,.8,-1.04],origin=(1,0,0),depth_before=1,depth_after=.55)==PX_MOVED_OTHER


def test_zero_area_fallback_keeps_real_depth_translation():
    assert classify_one([0,0,0,0],[0,0,0,0],depth_before=1,depth_after=1.3)==PX_MOVED_OTHER


@pytest.mark.parametrize('plane,origin,direction',[
    ([0,0,1,-1],(0,0,1),(1,0,0)),
    ([0,0,1,-1],(np.nan,0,0),(0,0,1)),
    ([np.nan,0,1,-1],(0,0,0),(0,0,1)),
])
def test_unreconstructable_original_plane_cannot_silently_pass(plane,origin,direction):
    assert classify_one(plane,plane,origin=origin,direction=direction)==PX_MOVED_OTHER


def test_material_swap_and_hole_still_fail_at_unchanged_witness_depths():
    d=actual_witnesses();w=d['witnesses'][0];origin=np.array([w['origin_inches']]*2);planes=np.array([w['before_plane']]);depth=w['before_depth_inches']
    codes=classify_pixels(np.array([depth,depth]),np.array([0,0]),np.array([depth,np.inf]),np.array([0,-1]),np.array([0]),np.array([1]),frozenset(),d['guard_depth_tol_inches'],origins=origin,direction=np.array(d['direction']),plane_before=planes,plane_after=planes)
    assert codes.tolist()==[PX_MATERIAL_CHANGED,PX_HOLE]