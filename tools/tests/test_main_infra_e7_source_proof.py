"""Exact source coverage admits the measured partition and refuses real damage."""
from dataclasses import replace
import json

import numpy as np
import pytest

from engine.io.minecraft_floor import Frame, parse_floor, write_floor
from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file
from engine.repair.kernel import write_records
from engine.validate.checks import Looks
from tools.main_infra_e3 import _source_digest
from tools.main_infra_e7 import run_checked_e7
from tools import main_infra_e7_serialization as serializer


PARENT = [0, 1, 2]
LITERAL = [[4, 4.75, 27.25], [4.25, 4.75, 28], [4.25, 4.75, 27.25], [4.25, 4.75, 27.75]]
CHILDREN = [[1, 3, 0], [3, 2, 0]]


def mesh(points, parent=PARENT):
    base = parse_floor('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n').mesh
    return replace(base, positions=np.array(points, dtype=np.float64), face_v=np.array([parent], dtype=np.int64))


def prove(points, children, parent=PARENT):
    proof = getattr(serializer, '_prove_exact_source_coverage', None)
    assert callable(proof), 'Exact source coverage proof is missing'
    original = mesh(points, parent)
    before = original.positions.tobytes()
    proof(original, 0, np.array(children, dtype=np.int64))
    assert original.positions.tobytes() == before


def literal_pair(tmp_path):
    points = LITERAL + [[4.5, 4.75, 27.75]]
    text = ['o literal-source', 'g parent'] + ['v ' + ' '.join(map(str, row)) for row in points]
    text += ['vt .0009995269 .74950075', 'vt .25049976 .001000464', 'vt .25049976 .74950075',
             'usemtl wall', 'f 1/1 2/2 3/3', 'g trim', 'usemtl trim', 'f 4/1 2/2 5/3']
    raw=tmp_path/'raw.obj';raw.write_text('\n'.join(text)+'\n')
    source=parse_floor(raw.read_text());engine=source.in_frame(Frame(1000/25.4,'literal metres Y-up'))
    paths=dict(raw=raw,reference=tmp_path/'reference.json',qualification=tmp_path/'qualification.json',
        provenance=tmp_path/'geometry-provenance.json',baseline_source=tmp_path/'before.source.obj',
        baseline_engine=tmp_path/'before.engine.obj',source_input=tmp_path/'input.source.obj',
        engine_input=tmp_path/'input.engine.obj',lineage=tmp_path/'source-faces.json',edit_log=tmp_path/'edit-log.jsonl')
    for field,floor in [('baseline_source',source),('baseline_engine',engine),('source_input',source),('engine_input',engine)]:
        write_floor(floor,paths[field])
    before=replace(read_obj(paths['engine_input']),units=engine.mesh.units,physical_quanta=engine.mesh.physical_quanta)
    looks=Looks(key={'wall':'wall','trim':'trim'},texel={'wall':(1024,1024)},flat=frozenset({'trim'}))
    outcome=run_checked_e7(before,looks)
    assert len(outcome.kept)==1 and not outcome.rolled_back
    write_records(paths['edit_log'],outcome.records)
    paths['reference'].write_text(json.dumps(dict(source_sha256=sha256_file(raw),
        polygons={str(poly.line):[[0,1,2]] for poly in source.polygons})))
    paths['qualification'].write_text(json.dumps(dict(qualified=True,floor_id='1F',source_revision='a'*64,
        source_obj_sha256=sha256_file(raw),native_reference_sha256=sha256_file(paths['reference']),
        source_triangles_sha256=sha256_file(paths['baseline_source']),engine_obj_sha256=sha256_file(paths['baseline_engine']))))
    paths['provenance'].write_text(json.dumps(dict(source_sha256=sha256_file(raw),reference_sha256=sha256_file(paths['reference']),
        source_triangles_sha256=sha256_file(paths['baseline_source']),engine_obj_sha256=sha256_file(paths['baseline_engine']),
        source_to_engine=engine.frame.matrix.tolist())))
    paths['lineage'].write_text(json.dumps(dict(schema_version=1,mode='original_source_survivors',
        input_triangles=2,output_triangles=2,source_faces=[0,1])))
    binding=dict(paths={key:str(path) for key,path in paths.items()},sha256={key:sha256_file(path) for key,path in paths.items()},
        before_digest=_source_digest(before).hex())
    return source,engine,before,outcome,looks,binding


def test_literal_source_partition_serializes_without_changing_engine_attributes(tmp_path):
    source,engine,before,outcome,looks,binding=literal_pair(tmp_path)
    pair=serializer.prepare_cut_pair(source,engine,before,[0,1],outcome,looks,binding=binding)
    assert pair.engine.mesh.uvs.tobytes()==outcome.mesh.uvs.tobytes()
    assert pair.engine.mesh.face_v.tobytes()==outcome.mesh.face_v.tobytes()
    assert pair.source.mesh.uvs.tobytes()==outcome.mesh.uvs.tobytes()
    assert pair.source.mesh.positions.tobytes()==source.mesh.positions.tobytes()
    assert pair.engine.mesh.positions.tobytes()==engine.mesh.positions.tobytes()
    serializer.save_cut_pair(pair,tmp_path/'saved')


def test_measured_literal_and_reordered_children_have_exact_coverage():
    prove(LITERAL,CHILDREN)
    prove(LITERAL,list(reversed(CHILDREN)))
    prove(LITERAL,[[3,0,1],[2,0,3]])


def test_partial_collinear_subdivision_and_geometric_vertex_alias_are_noded():
    points=[[0,0,0],[1,0,0],[0,1,0],[.5,.5,0],[.25,.25,0],[.5,.5,0]]
    prove(points,[[1,3,0],[5,2,4],[4,2,0]])


@pytest.mark.parametrize('children', [[[1,3,0]],[[1,3,0],[3,2,0],[1,3,0]],[[1,0,3],[3,2,0]],[[1,3,3],[3,2,0]]])
def test_gap_duplicate_reverse_and_zero_area_children_are_refused(children):
    with pytest.raises(ValueError):prove(LITERAL,children)


def test_contained_positive_equal_area_overlap_plus_gap_is_refused():
    points=[[0,0,0],[1,0,0],[0,1,0],[0,.5,0],[.5,0,0]]
    with pytest.raises(ValueError):prove(points,[[0,1,3],[0,4,2]])


def test_crossing_equal_area_children_are_refused():
    points=[[0,0,0],[1,0,0],[0,1,0],[.75,.25,0],[.25,.75,0]]
    with pytest.raises(ValueError):prove(points,[[0,1,4],[0,3,2]])


def test_one_ulp_gap_is_not_rounded_closed():
    points=[[0,0,0],[1,0,0],[0,1,0],[0,.5,0],[0,np.nextafter(.5,1),0]]
    with pytest.raises(ValueError):prove(points,[[0,1,3],[4,1,2]])


@pytest.mark.parametrize('kind',['off_plane','outside'])
def test_min_subnormal_source_displacement_is_refused(kind):
    tiny=np.nextafter(0.0,1.0)
    point=[0,.5,tiny] if kind=='off_plane' else [-tiny,.5,0]
    points=[[0,0,0],[1,0,0],[0,1,0],point]
    with pytest.raises(ValueError):prove(points,[[0,1,3],[3,1,2]])


@pytest.mark.parametrize('value',[float('nan'),float('inf'),float('-inf')])
def test_nonfinite_referenced_source_point_is_refused(value):
    points=[list(row) for row in LITERAL];points[3][0]=value
    with pytest.raises(ValueError):prove(points,CHILDREN)


def test_parent_winding_and_non_axis_plane_remain_supported():
    prove([[0,0,0],[0,1,1],[1,0,1],[.5,.5,1]],CHILDREN)
