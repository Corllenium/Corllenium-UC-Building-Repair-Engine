"""Exact source/engine pairs for hash-bound checked E7 existing-vertex cuts."""
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np

from engine.fixes.pipeline import FixProfile
from engine.io.minecraft_floor import FloorInput, SourcePolygon, parse_floor, write_floor
from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file
from engine.repair.engines.e7_thread import E7Thread, _attributes, _source_weights
from engine.repair.kernel import KernelResult, stage_records
from engine.repair.types import Edit, RepairContext, UnitState, apply_edits
from tools.main_infra_e3 import _source_digest, _survivor_indices
from tools.main_infra_e3_binding import _hash


ARRAYS = ('positions', 'uvs', 'normals', 'face_v', 'face_vt', 'face_vn')
INPUTS = {'raw', 'reference', 'qualification', 'provenance', 'baseline_source', 'baseline_engine',
          'source_input', 'engine_input', 'lineage', 'edit_log'}
FILES = {'candidate.source.obj', 'candidate.engine.obj', 'cut-lineage.json', 'checked-edits.json', 'edit-log.jsonl'}


def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _array(actual, expected, label):
    if (actual.shape != expected.shape or actual.dtype != expected.dtype
            or actual.tobytes() != expected.tobytes()):
        raise ValueError(f'exact cut table differs: {label}')


def _names(mesh):
    if ((mesh.face_material < -1) | (mesh.face_material >= len(mesh.materials))).any():
        raise ValueError('invalid cut material')
    return [None if i < 0 else mesh.materials[int(i)] for i in mesh.face_material]


def _tables(actual, expected):
    for name in ARRAYS:
        _array(getattr(actual, name), getattr(expected, name), name)
    if _names(actual) != _names(expected) or actual.mtllib != expected.mtllib:
        raise ValueError('cut material names or library differ')


def _inputs(source, engine, before, ancestry, binding):
    paths, hashes = binding['paths'], binding['sha256']
    if not INPUTS.issubset(paths) or set(paths) != set(hashes):
        raise ValueError('trusted cut input inventory required')
    for name in paths:
        _hash(Path(paths[name]), hashes[name])
    if binding.get('before_digest') != _source_digest(before).hex():
        raise ValueError('qualified BEFORE digest differs')
    reference, qualification = _read(paths['reference']), _read(paths['qualification'])
    provenance = _read(paths['provenance'])
    if (source.frame is not None or engine.frame is None
            or engine.frame.inches_per_unit != 1000 / 25.4
            or qualification.get('qualified') is not True
            or qualification.get('source_obj_sha256') != hashes['raw']
            or qualification.get('native_reference_sha256') != hashes['reference']
            or not qualification.get('floor_id') or not qualification.get('source_revision')
            or qualification.get('source_triangles_sha256') != hashes['baseline_source']
            or qualification.get('engine_obj_sha256') != hashes['baseline_engine']
            or reference.get('source_sha256') != hashes['raw']
            or provenance.get('source_sha256') != hashes['raw']
            or provenance.get('reference_sha256') != hashes['reference']
            or provenance.get('source_triangles_sha256') != hashes['baseline_source']
            or provenance.get('engine_obj_sha256') != hashes['baseline_engine']
            or provenance.get('source_to_engine') != engine.frame.matrix.tolist()):
        raise ValueError('qualified source frame binding differs')
    parsed = parse_floor(Path(paths['raw']).read_text(encoding='utf-8'),
        triangulations={int(k): v for k, v in reference['polygons'].items()})
    if (_source_digest(parsed.mesh) != _source_digest(source.mesh) or parsed.polygons != source.polygons):
        raise ValueError('original source differs from frozen raw')
    for name in ('triangle_polygon', 'triangle_corners'):
        _array(getattr(parsed, name), getattr(source, name), name)
    if _source_digest(source.in_frame(engine.frame).mesh) != _source_digest(engine.mesh):
        raise ValueError('engine original differs from qualified forward frame')
    _tables(read_obj(paths['baseline_source']), source.mesh)
    _tables(read_obj(paths['baseline_engine']), engine.mesh)
    ids = _survivor_indices(ancestry, source.mesh.n_faces)
    mapping = _read(paths['lineage'])
    if mapping != dict(schema_version=1, mode='original_source_survivors',
        input_triangles=source.mesh.n_faces, output_triangles=len(ids), source_faces=ids.tolist()):
        raise ValueError('E3 source ancestry differs')
    def selected(mesh):
        return replace(mesh, **{name: getattr(mesh, name)[ids] for name in
            ('face_v', 'face_vt', 'face_vn', 'face_material', 'face_line')})
    source_before, engine_before = selected(source.mesh), selected(engine.mesh)
    _tables(read_obj(paths['source_input']), source_before)
    _tables(read_obj(paths['engine_input']), engine_before)
    _tables(before, engine_before)
    _array(before.face_line, read_obj(paths['engine_input']).face_line, 'input physical OBJ lines')
    if before.physical_quanta != engine.mesh.physical_quanta or before.units != engine.mesh.units:
        raise ValueError('BEFORE physical precision differs')
    source_before = replace(source_before, materials=before.materials.copy(),
                            face_material=before.face_material.copy())
    return source_before, ids


def _encode(edit):
    return dict(engine=edit.engine, kind=edit.kind, faces=list(edit.faces), site=edit.site,
        reason=edit.reason, evidence=edit.evidence, legacy=edit.legacy,
        new_points=None if edit.new_points is None else edit.new_points.tolist(),
        **{name: None if getattr(edit, name) is None else getattr(edit, name).tolist()
           for name in ('new_faces', 'new_face_uv', 'new_face_normal')})


def _decode(row):
    return Edit(**{**row, 'faces': tuple(row['faces'])})


def _checked(before, outcome, looks, binding):
    if outcome.result is not None or outcome.stages or len(outcome.checks) != 1:
        raise ValueError('one checked nonlegacy E7 stage required')
    edits, kept, rolled = outcome.edits, outcome.kept, outcome.rolled_back
    planned_ids, kept_ids, rolled_ids = map(lambda items: [id(item) for item in items], (edits, kept, rolled))
    if (len(set(planned_ids)) != len(edits) or set(kept_ids) & set(rolled_ids)
            or set(planned_ids) != set(kept_ids) | set(rolled_ids)
            or kept_ids != [i for i in planned_ids if i in kept_ids]
            or rolled_ids != [i for i in planned_ids if i in rolled_ids]):
        raise ValueError('actual kept/rolled partition required')
    faces, sites = set(), set()
    for edit in edits:
        if (edit.engine != 'E7' or edit.kind != 'cut' or edit.legacy or len(edit.faces) != 1
                or edit.new_points is not None or not 0 <= edit.faces[0] < before.n_faces
                or edit.faces[0] in faces or edit.site in sites or edit.site != edit.faces[0]
                or (edit.new_faces < 0).any() or (edit.new_faces >= len(before.positions)).any()):
            raise ValueError('only disjoint original-index E7 cuts required')
        faces.update(edit.faces); sites.add(edit.site)
    check = outcome.checks[0]
    if (check.get('stage') != 'E7' or check.get('engine') != 'E7' or check.get('legacy') is not False
            or check.get('rollback') is not True
            or {row['site'] for row in check.get('rolled_back', [])} != {e.site for e in rolled}):
        raise ValueError('E7 rollback check differs')
    runs = check.get('runs') or []
    if kept and (check.get('final') != 'PASS' or check.get('stage_rolled_back') is not None
            or check.get('rounds_exhausted', False) is not False or not runs
            or runs[-1].get('status') != 'PASS' or runs[-1].get('failing') != 0
            or runs[-1].get('unknown', 0) != 0):
        raise ValueError('fresh confirmed E7 PASS required')
    if not kept and check.get('final') not in ('PASS', 'NOTHING KEPT'):
        raise ValueError('unconfirmed E7 no-op')
    look_ids = {i: looks.key_of(name) for i, name in enumerate(before.materials)}
    records = stage_records(before, edits, look_ids, 'E7')
    for edit, row in zip(edits, records):
        if id(edit) in rolled_ids:
            row['rolled_back'] = True
    records.append({'check': check})
    actual_log = [json.loads(line) for line in Path(binding['paths']['edit_log']).read_text().splitlines()]
    if records != outcome.records or records != actual_log:
        raise ValueError('checked cut log differs')
    expected, _ = apply_edits(before, kept)
    if _source_digest(expected) != _source_digest(outcome.mesh):
        raise ValueError('checked outcome differs from actual kept cuts')
    allowed = {edit.site: edit for edit in E7Thread().plan(UnitState(before, None, look_ids, None),
        RepairContext(FixProfile(), None, None))}
    for edit in kept:
        if edit.site not in allowed or _dump(_encode(edit)) != _dump(_encode(allowed[edit.site])):
            raise ValueError('kept cut differs from strict source triangle proof')
    rank = {identity: index for index, identity in enumerate(planned_ids)}
    return dict(schema_version=1, input_triangles=before.n_faces, before_digest=_source_digest(before).hex(),
        input_sha256=binding['sha256'], edits=[_encode(e) for e in edits],
        kept=[rank[i] for i in kept_ids], rolled_back=[rank[i] for i in rolled_ids],
        check=check, engine_digest=_source_digest(expected).hex()), records


@dataclass(frozen=True)
class CutPair:
    source: FloorInput
    engine: FloorInput
    lineage: dict
    checked: dict
    records: list
    binding: dict
    seal: str


def _seal(source, engine, lineage, checked):
    return hashlib.sha256(_source_digest(source.mesh) + _source_digest(engine.mesh)
        + _dump(lineage).encode() + _dump(checked).encode()).hexdigest()


def prepare_cut_pair(source_floor, engine_floor, before, input_lineage, outcome, looks, *, binding):
    source_before, ancestry = _inputs(source_floor, engine_floor, before, input_lineage, binding)
    checked, records = _checked(before, outcome, looks, binding)
    checked['original_source_triangles'] = source_floor.mesh.n_faces
    source_edits = []
    for edit in outcome.kept:
        source = edit.faces[0]
        _source_weights(source_before, source, edit.new_faces)
        _faces, weights, _area, _after = _source_weights(before, source, edit.new_faces)
        source_edits.append(replace(edit, new_face_uv=_attributes(source_before, source, weights, 'face_vt', 'uvs'),
            new_face_normal=_attributes(source_before, source, weights, 'face_vn', 'normals')))
    source_after, _ = apply_edits(source_before, source_edits)
    engine_after = outcome.mesh
    _array(source_after.uvs, engine_after.uvs, 'frame-invariant UV table')
    _array(source_after.normals @ engine_floor.frame.rotation.T, engine_after.normals, 'forward normal table')
    for name in ('face_v', 'face_vt', 'face_vn'):
        _array(getattr(source_after, name), getattr(engine_after, name), 'paired ' + name)
    touched = {e.faces[0] for e in outcome.kept}
    origins = [(face, None, None) for face in range(before.n_faces) if face not in touched]
    plan_index = {id(edit): index for index, edit in enumerate(outcome.edits)}
    for edit in outcome.kept:
        index = plan_index[id(edit)]
        origins.extend((edit.faces[0], index, child) for child in range(len(edit.new_faces)))
    rows, polygons = [], []
    material_names = _names(source_after)
    for output, (face, edit_index, child) in enumerate(origins):
        original = int(ancestry[face]); poly = source_floor.polygons[source_floor.triangle_polygon[original]]
        rows.append(dict(output_face=output, stage_input_face=face, original_source_triangle=original,
            source_polygon_line=poly.line, group=poly.group, object_name=poly.object_name,
            material=material_names[output], kind='unchanged' if child is None else 'cut_child',
            edit_index=edit_index, site=None if child is None else outcome.edits[edit_index].site,
            child=child, vertex_ids=source_after.face_v[output].tolist(),
            source_uv=source_after.face_vt[output].tolist(), source_normal=source_after.face_vn[output].tolist(),
            engine_uv=engine_after.face_vt[output].tolist(), engine_normal=engine_after.face_vn[output].tolist()))
        polygons.append(poly)
    def floor(mesh, frame):
        polys = tuple(SourcePolygon(poly.line, tuple(zip(mesh.face_v[i], mesh.face_vt[i], mesh.face_vn[i])),
            int(mesh.face_material[i]), poly.group, poly.object_name) for i, poly in enumerate(polygons))
        return FloorInput(mesh, polys, np.arange(mesh.n_faces), np.tile([0, 1, 2], (mesh.n_faces, 1)), frame)
    source, engine = floor(source_after, None), floor(engine_after, engine_floor.frame)
    lineage = dict(schema_version=1, mode='original_source_existing_vertex_cuts', input_sha256=binding['sha256'], faces=rows)
    return CutPair(source, engine, lineage, checked, records, binding, _seal(source, engine, lineage, checked))


def _readback(path, expected):
    actual = read_obj(path); _tables(actual, expected.mesh)
    parsed = parse_floor(path.read_text(encoding='utf-8'))
    if [(p.group, p.object_name) for p in parsed.polygons] != [(p.group, p.object_name) for p in expected.polygons]:
        raise ValueError('saved cut object/group state differs')
    return replace(actual, units=expected.mesh.units, physical_quanta=expected.mesh.physical_quanta,
                   coord_decimals=expected.mesh.coord_decimals, sig_digits=expected.mesh.sig_digits)


def _digests(mesh):
    return {name: dict(dtype=getattr(mesh, name).dtype.str, shape=list(getattr(mesh, name).shape),
        sha256=hashlib.sha256(getattr(mesh, name).tobytes()).hexdigest()) for name in ARRAYS}


def save_cut_pair(pair, out):
    out = Path(out)
    if out.exists():
        raise ValueError('cut output exists; refusing overwrite')
    if pair.seal != _seal(pair.source, pair.engine, pair.lineage, pair.checked):
        raise ValueError('prepared cut pair changed')
    for name, path in pair.binding['paths'].items():
        _hash(Path(path), pair.binding['sha256'][name])
    staging = Path(tempfile.mkdtemp(prefix=out.name + '.incomplete-', dir=out.parent))
    write_floor(pair.source, staging/'candidate.source.obj')
    write_floor(pair.engine, staging/'candidate.engine.obj')
    source = _readback(staging/'candidate.source.obj', pair.source)
    engine = _readback(staging/'candidate.engine.obj', pair.engine)
    (staging/'checked-edits.json').write_text(_dump(pair.checked), encoding='utf-8')
    (staging/'cut-lineage.json').write_text(_dump(pair.lineage), encoding='utf-8')
    (staging/'edit-log.jsonl').write_bytes(Path(pair.binding['paths']['edit_log']).read_bytes())
    receipt = dict(schema_version=1, mode='e7_existing_vertex_cuts', candidate_only=True,
        binding=pair.binding, files={name: sha256_file(staging/name) for name in sorted(FILES)},
        source_tables=_digests(source), engine_tables=_digests(engine), exact_readback=True,
        positions_unchanged=True, original_source_triangles=pair.checked['original_source_triangles'],
        stage_input_triangles=pair.checked['input_triangles'],
        output_triangles=engine.n_faces, kept_cuts=len(pair.checked['kept']))
    (staging/'cut-receipt.json').write_text(_dump(receipt), encoding='utf-8')
    staging.rename(out)
    return {**receipt, 'receipt_sha256': sha256_file(out/'cut-receipt.json')}


def bind_saved_cut_pair(source_floor, engine_floor, before, input_lineage, looks, candidate, *, binding,
                        expected_receipt_sha256):
    candidate = Path(candidate); _hash(candidate/'cut-receipt.json', expected_receipt_sha256)
    receipt = _read(candidate/'cut-receipt.json')
    if (receipt.get('schema_version') != 1 or receipt.get('mode') != 'e7_existing_vertex_cuts'
            or receipt.get('binding') != binding or set(receipt.get('files', {})) != FILES
            or receipt.get('candidate_only') is not True or receipt.get('exact_readback') is not True
            or receipt.get('positions_unchanged') is not True):
        raise ValueError('trusted cut receipt contract differs')
    for name, expected in receipt['files'].items():
        _hash(candidate/name, expected)
    payload = _read(candidate/'checked-edits.json'); edits = [_decode(row) for row in payload['edits']]
    kept, rolled = [edits[i] for i in payload['kept']], [edits[i] for i in payload['rolled_back']]
    mesh, _ = apply_edits(before, kept)
    records = [json.loads(line) for line in (candidate/'edit-log.jsonl').read_text().splitlines()]
    outcome = KernelResult(mesh, None, edits, [], None, kept, rolled, [payload['check']], records)
    pair = prepare_cut_pair(source_floor, engine_floor, before, input_lineage, outcome, looks, binding=binding)
    if _dump(pair.checked) != _dump(payload) or _dump(pair.lineage) != _dump(_read(candidate/'cut-lineage.json')):
        raise ValueError('saved cut payload or lineage differs')
    source = _readback(candidate/'candidate.source.obj', pair.source)
    engine = _readback(candidate/'candidate.engine.obj', pair.engine)
    if receipt['source_tables'] != _digests(source) or receipt['engine_tables'] != _digests(engine):
        raise ValueError('saved cut table digests differ')
    if (receipt['original_source_triangles'] != source_floor.mesh.n_faces
            or receipt['stage_input_triangles'] != before.n_faces or receipt['output_triangles'] != engine.n_faces
            or receipt['kept_cuts'] != len(kept)):
        raise ValueError('saved cut counts differ')
    return source, engine, receipt
