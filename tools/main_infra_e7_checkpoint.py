"""Capture actual E7 results before source serialization, with exact typed readback."""
from dataclasses import fields
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from engine.io.protected import refuse_protected
from engine.io.snapshot import sha256_file
from engine.model import MeshData
from engine.repair.kernel import KernelResult, stage_records, write_records
from engine.repair.types import Edit, apply_edits
from tools.main_infra_e3 import _source_digest
from tools.main_infra_e3_binding import _hash
from tools.main_infra_e7_serialization import _dump, _read

MESH_ARRAYS = ('positions', 'uvs', 'normals', 'face_v', 'face_vt', 'face_vn', 'face_material', 'face_line')
EDIT_ARRAYS = ('new_faces', 'new_points', 'new_face_uv', 'new_face_normal')
FILES = {'arrays.npz', 'result.json', 'edit-log.jsonl'}


def _digest(array):
    return dict(dtype=array.dtype.str, shape=list(array.shape),
                sha256=hashlib.sha256(array.tobytes()).hexdigest())


def _partition(outcome):
    planned = [id(e) for e in outcome.edits]
    kept, rolled = [id(e) for e in outcome.kept], [id(e) for e in outcome.rolled_back]
    if (len(set(planned)) != len(planned) or len(set(kept)) != len(kept) or len(set(rolled)) != len(rolled)
            or set(kept) & set(rolled) or set(planned) != set(kept) | set(rolled)
            or kept != [i for i in planned if i in kept] or rolled != [i for i in planned if i in rolled]):
        raise ValueError('actual E7 identity partition required')
    rank = {identity: i for i, identity in enumerate(planned)}
    return [rank[i] for i in kept], [rank[i] for i in rolled]


def typed_edits(edits):
    rows, arrays = [], {}
    for i, edit in enumerate(edits):
        row = {f.name: getattr(edit, f.name) for f in fields(Edit) if f.name not in EDIT_ARRAYS}
        row['faces'] = list(edit.faces)
        for name in EDIT_ARRAYS:
            value = getattr(edit, name)
            key = f'edit_{i}_{name}'
            row[name] = None if value is None else key
            if value is not None:
                arrays[key] = value
        rows.append(row)
    return rows, arrays


def typed_plan_digest(edits):
    rows, arrays = typed_edits(edits)
    return hashlib.sha256((_dump(rows) + _dump({k: _digest(v) for k, v in arrays.items()})).encode()).hexdigest()


def _pack(outcome):
    if outcome.result is not None or outcome.report is not None or outcome.stages or len(outcome.checks) != 1:
        raise ValueError('one nonlegacy E7 outcome required')
    check = outcome.checks[0]
    if any(check.get(k) != v for k, v in dict(stage='E7', engine='E7', legacy=False, rollback=True).items()):
        raise ValueError('default nonlegacy E7 check required')
    if any(e.engine != 'E7' or e.kind != 'cut' or e.legacy or e.new_points is not None for e in outcome.edits):
        raise ValueError('only existing-vertex E7 cuts required')
    kept, rolled = _partition(outcome)
    rows, arrays = typed_edits(outcome.edits)
    arrays.update({'mesh_' + name: getattr(outcome.mesh, name) for name in MESH_ARRAYS})
    data = dict(schema_version=1, mesh={f.name: getattr(outcome.mesh, f.name) for f in fields(MeshData)
        if f.name not in MESH_ARRAYS}, edits=rows, kept=kept, rolled_back=rolled,
        checks=outcome.checks, records=outcome.records, result=None, report=None, stages=[])
    return data, arrays


def _inputs(before, binding):
    if (binding.get('before_digest') != _source_digest(before).hex()
            or not binding.get('run_id') or set(binding['paths']) != set(binding['sha256'])):
        raise ValueError('checkpoint input binding differs')
    for name, path in binding['paths'].items():
        _hash(Path(path), binding['sha256'][name])


def _verify(before, outcome, looks):
    _pack(outcome)
    check = outcome.checks[0]
    if {row['site'] for row in check.get('rolled_back', [])} != {e.site for e in outcome.rolled_back}:
        raise ValueError('E7 actual rollback partition differs')
    if outcome.kept and (check.get('final') != 'PASS' or check.get('stage_rolled_back') is not None
            or check.get('rounds_exhausted', False) or not check.get('runs')
            or check['runs'][-1].get('status') != 'PASS' or check['runs'][-1].get('failing') != 0
            or check['runs'][-1].get('unknown', 0) != 0):
        raise ValueError('fresh checked E7 outcome required')
    expected, _ = apply_edits(before, outcome.kept)
    if _source_digest(expected) != _source_digest(outcome.mesh) or expected.name != outcome.mesh.name:
        raise ValueError('actual E7 outcome differs from kept edits')
    look_ids = {i: looks.key_of(name) for i, name in enumerate(before.materials)}
    records = stage_records(before, outcome.edits, look_ids, 'E7')
    rolled = {id(e) for e in outcome.rolled_back}
    for edit, row in zip(outcome.edits, records):
        if id(edit) in rolled:
            row['rolled_back'] = True
    if records + [{'check': check}] != outcome.records:
        raise ValueError('actual E7 records differ')


def save_e7_checkpoint(before, outcome, looks, out, *, binding):
    out = Path(out)
    refuse_protected(out)
    if out.exists():
        raise ValueError('E7 checkpoint exists; refusing overwrite')
    _inputs(before, binding)
    data, arrays = _pack(outcome)
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=out.name + '.incomplete-', dir=out.parent))
    np.savez(staging/'arrays.npz', **arrays)
    (staging/'result.json').write_text(_dump(data), encoding='utf-8')
    write_records(staging/'edit-log.jsonl', outcome.records)
    receipt = dict(schema_version=1, mode='actual_checked_e7_checkpoint', binding=binding,
        files={name: sha256_file(staging/name) for name in sorted(FILES)},
        arrays={name: _digest(value) for name, value in arrays.items()},
        before_digest=_source_digest(before).hex(), after_digest=_source_digest(outcome.mesh).hex(),
        fresh_check=outcome.checks[0], planned=len(outcome.edits), kept=len(outcome.kept),
        rolled_back=len(outcome.rolled_back), output_triangles=outcome.mesh.n_faces)
    (staging/'checkpoint-receipt.json').write_text(_dump(receipt), encoding='utf-8')
    staging.rename(out)
    receipt_sha = sha256_file(out/'checkpoint-receipt.json')
    loaded = restore_e7_checkpoint(before, looks, out, binding=binding, expected_receipt_sha256=receipt_sha)
    actual_data, actual_arrays = _pack(loaded)
    if (_dump(actual_data) != _dump(data)
            or {k: _digest(v) for k, v in actual_arrays.items()} != receipt['arrays']):
        raise ValueError('actual E7 checkpoint readback differs')
    return {**receipt, 'receipt_sha256': receipt_sha}


def restore_e7_checkpoint(before, looks, out, *, binding, expected_receipt_sha256):
    out = Path(out)
    _hash(out/'checkpoint-receipt.json', expected_receipt_sha256)
    receipt = _read(out/'checkpoint-receipt.json')
    if (receipt.get('schema_version') != 1 or receipt.get('mode') != 'actual_checked_e7_checkpoint'
            or receipt.get('binding') != json.loads(_dump(binding)) or set(receipt.get('files', {})) != FILES):
        raise ValueError('E7 checkpoint binding differs')
    _inputs(before, binding)
    for name, expected in receipt['files'].items():
        _hash(out/name, expected)
    data = _read(out/'result.json')
    references = {'mesh_' + name for name in MESH_ARRAYS}
    for i, row in enumerate(data['edits']):
        if set(row) != {f.name for f in fields(Edit)}:
            raise ValueError('E7 checkpoint edit fields differ')
        for name in EDIT_ARRAYS:
            key = row[name]
            if key is not None:
                if key != f'edit_{i}_{name}':
                    raise ValueError('invalid E7 checkpoint array reference')
                references.add(key)
    if set(receipt['arrays']) != references:
        raise ValueError('E7 checkpoint array references differ')
    with zipfile.ZipFile(out/'arrays.npz') as zipped:
        names = zipped.namelist()
        if len(names) != len(set(names)) or set(names) != {key + '.npy' for key in references}:
            raise ValueError('unknown or duplicate E7 checkpoint archive member')
    with np.load(out/'arrays.npz', allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in references}
    if any(a.dtype.hasobject or _digest(a) != receipt['arrays'][name] for name, a in arrays.items()):
        raise ValueError('E7 checkpoint array digest differs')
    mesh = MeshData(**data['mesh'], **{name: arrays['mesh_' + name] for name in MESH_ARRAYS})
    edits = [Edit(**{**row, **{name: None if row[name] is None else arrays[row[name]]
        for name in EDIT_ARRAYS}}) for row in data['edits']]
    partition = data['kept'] + data['rolled_back']
    if (any(type(i) is not int or not 0 <= i < len(edits) for i in partition)
            or len(partition) != len(set(partition)) or set(partition) != set(range(len(edits)))):
        raise ValueError('invalid E7 checkpoint partition')
    outcome = KernelResult(mesh, data['result'], edits, data['stages'], data['report'],
        [edits[i] for i in data['kept']], [edits[i] for i in data['rolled_back']], data['checks'], data['records'])
    _verify(before, outcome, looks)
    log = [json.loads(line) for line in (out/'edit-log.jsonl').read_text().splitlines()]
    if (data.get('schema_version') != 1 or log != outcome.records
            or receipt['before_digest'] != _source_digest(before).hex()
            or receipt['after_digest'] != _source_digest(mesh).hex()
            or receipt['fresh_check'] != outcome.checks[0]
            or [receipt[k] for k in ('planned', 'kept', 'rolled_back', 'output_triangles')]
                != [len(edits), len(outcome.kept), len(outcome.rolled_back), mesh.n_faces]):
        raise ValueError('E7 checkpoint actual result digest differs')
    return outcome
