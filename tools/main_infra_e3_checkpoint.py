"""Capture only actual checked E3 removals before survivor serialization."""
from dataclasses import fields
import json
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from engine.io.protected import refuse_protected
from engine.io.snapshot import sha256_file
from engine.model import MeshData
from engine.repair.kernel import KernelResult,stage_records,write_records
from engine.repair.types import Edit,apply_edits
from tools.main_infra_e3 import _source_digest,source_survivors
from tools.main_infra_e3_binding import _hash
from tools.main_infra_e7_checkpoint import MESH_ARRAYS,EDIT_ARRAYS,_digest,_partition,_inputs,typed_edits
from tools.main_infra_e7_serialization import _dump,_read

FILES={'arrays.npz','result.json','edit-log.jsonl'}


def _pack(outcome):
    if outcome.result is not None or outcome.report is not None or outcome.stages or len(outcome.checks)!=1:
        raise ValueError('one nonlegacy E3 outcome required')
    if any(outcome.checks[0].get(k)!=v for k,v in dict(stage='E3',engine='E3',legacy=False,rollback=True).items()):
        raise ValueError('default checked E3 stage required')
    if any(e.engine!='E3' or e.kind!='remove' or e.legacy or any(getattr(e,k) is not None for k in EDIT_ARRAYS)
            for e in outcome.edits):
        raise ValueError('only original-face E3 removals without new arrays required')
    kept,rolled=_partition(outcome);rows,arrays=typed_edits(outcome.edits)
    if arrays:raise ValueError('E3 may not carry new arrays')
    arrays={'mesh_'+name:getattr(outcome.mesh,name) for name in MESH_ARRAYS}
    data=dict(schema_version=1,mesh={f.name:getattr(outcome.mesh,f.name) for f in fields(MeshData) if f.name not in MESH_ARRAYS},
        edits=rows,kept=kept,rolled_back=rolled,checks=outcome.checks,records=outcome.records,result=None,report=None,stages=[])
    return data,arrays


def _verify(before,outcome,looks):
    _pack(outcome);source_survivors(before,outcome)
    expected,_=apply_edits(before,outcome.kept)
    if _source_digest(expected)!=_source_digest(outcome.mesh) or expected.name!=outcome.mesh.name:
        raise ValueError('actual E3 outcome is not bit-exact kept edits')
    check=outcome.checks[0]
    if {r['site'] for r in check.get('rolled_back',[])}!={e.site for e in outcome.rolled_back}:
        raise ValueError('actual E3 rollback partition differs')
    if outcome.kept and (check.get('final')!='PASS' or check.get('stage_rolled_back') is not None
            or check.get('rounds_exhausted',False) or not check.get('runs')
            or check['runs'][-1].get('status')!='PASS' or check['runs'][-1].get('failing')!=0
            or check['runs'][-1].get('unknown',0)!=0):
        raise ValueError('fresh confirmed E3 outcome required')
    records=stage_records(before,outcome.edits,{i:looks.key_of(n) for i,n in enumerate(before.materials)},'E3')
    rolled={id(e) for e in outcome.rolled_back}
    for e,row in zip(outcome.edits,records):
        if id(e) in rolled:row['rolled_back']=True
    if records+[{'check':check}]!=outcome.records:raise ValueError('actual E3 records differ')


def save_e3_checkpoint(before,outcome,looks,out,*,binding):
    out=Path(out);refuse_protected(out)
    if out.exists():raise ValueError('E3 checkpoint exists; refusing overwrite')
    data,arrays=_pack(outcome);out.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix=out.name+'.incomplete-',dir=out.parent))
    np.savez(staging/'arrays.npz',**arrays)
    (staging/'result.json').write_text(_dump(data),encoding='utf-8')
    write_records(staging/'edit-log.jsonl',outcome.records)
    receipt=dict(schema_version=1,mode='actual_checked_e3_checkpoint',capture_only=True,binding=binding,
        files={name:sha256_file(staging/name) for name in sorted(FILES)},arrays={name:_digest(v) for name,v in arrays.items()},
        before_digest=_source_digest(before).hex(),after_digest=_source_digest(outcome.mesh).hex(),
        fresh_check=outcome.checks[0],planned=len(outcome.edits),kept=len(outcome.kept),rolled_back=len(outcome.rolled_back),
        output_triangles=outcome.mesh.n_faces)
    (staging/'checkpoint-receipt.json').write_text(_dump(receipt),encoding='utf-8');staging.rename(out)
    receipt_sha=sha256_file(out/'checkpoint-receipt.json')
    loaded=restore_e3_checkpoint(before,looks,out,binding=binding,expected_receipt_sha256=receipt_sha)
    actual_data,actual_arrays=_pack(loaded)
    if _dump(actual_data)!=_dump(data) or {k:_digest(v) for k,v in actual_arrays.items()}!=receipt['arrays']:
        raise ValueError('actual E3 capture readback differs')
    return {**receipt,'receipt_sha256':receipt_sha}


def restore_e3_checkpoint(before,looks,out,*,binding,expected_receipt_sha256):
    out=Path(out);_hash(out/'checkpoint-receipt.json',expected_receipt_sha256)
    receipt=_read(out/'checkpoint-receipt.json')
    if (receipt.get('schema_version')!=1 or receipt.get('mode')!='actual_checked_e3_checkpoint'
            or receipt.get('capture_only') is not True or receipt.get('binding')!=json.loads(_dump(binding))
            or set(receipt.get('files',{}))!=FILES):raise ValueError('E3 checkpoint binding differs')
    _inputs(before,binding)
    for name,digest in receipt['files'].items():_hash(out/name,digest)
    data=_read(out/'result.json');references={'mesh_'+name for name in MESH_ARRAYS}
    if set(receipt['arrays'])!=references:raise ValueError('E3 checkpoint array inventory differs')
    for row in data['edits']:
        if set(row)!={f.name for f in fields(Edit)} or any(row[k] is not None for k in EDIT_ARRAYS):
            raise ValueError('E3 typed edit fields/new arrays differ')
    with zipfile.ZipFile(out/'arrays.npz') as zipped:
        names=zipped.namelist()
        if len(names)!=len(set(names)) or set(names)!={key+'.npy' for key in references}:
            raise ValueError('unknown or duplicate E3 archive member')
    with np.load(out/'arrays.npz',allow_pickle=False) as archive:arrays={name:archive[name] for name in references}
    if any(v.dtype.hasobject or _digest(v)!=receipt['arrays'][k] for k,v in arrays.items()):
        raise ValueError('E3 checkpoint array digest differs')
    mesh=MeshData(**data['mesh'],**{k:arrays['mesh_'+k] for k in MESH_ARRAYS});edits=[Edit(**row) for row in data['edits']]
    partition=data['kept']+data['rolled_back']
    if (any(type(i) is not int or not 0<=i<len(edits) for i in partition) or len(partition)!=len(set(partition))
            or set(partition)!=set(range(len(edits)))):raise ValueError('invalid E3 capture partition')
    outcome=KernelResult(mesh,data['result'],edits,data['stages'],data['report'],[edits[i] for i in data['kept']],
        [edits[i] for i in data['rolled_back']],data['checks'],data['records'])
    _verify(before,outcome,looks)
    log=[json.loads(line) for line in (out/'edit-log.jsonl').read_text().splitlines()]
    if (data.get('schema_version')!=1 or log!=outcome.records or receipt['before_digest']!=_source_digest(before).hex()
            or receipt['after_digest']!=_source_digest(mesh).hex() or receipt['fresh_check']!=outcome.checks[0]
            or [receipt[k] for k in ('planned','kept','rolled_back','output_triangles')]
                !=[len(edits),len(outcome.kept),len(outcome.rolled_back),mesh.n_faces]):
        raise ValueError('E3 actual capture digest differs')
    return outcome
