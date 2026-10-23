from dataclasses import replace
import json
from pathlib import Path
import zipfile

import pytest
from engine.io.snapshot import sha256_file
from tools.main_infra_e3 import _source_digest
from engine.repair.kernel import KernelResult,stage_records
from engine.repair.types import Edit
from tools.tests.test_main_infra_e3_replay import fixture


def api():
    from tools import main_infra_e3_checkpoint
    return main_infra_e3_checkpoint


@pytest.fixture
def captured(tmp_path):
    before,looks,candidate,audit=fixture(tmp_path)
    edit=Edit('E3','remove',(1,),None,None,0,'captured rollback fixture',{})
    check=dict(stage='E3',engine='E3',legacy=False,rollback=True,first='FAIL',final='NOTHING KEPT',
        rolled_back=[{'site':0}],runs=[dict(status='FAIL',failing=1,unknown=0)])
    records=stage_records(before,[edit],{i:looks.key_of(n) for i,n in enumerate(before.materials)},'E3')
    records[0]['rolled_back']=True
    outcome=KernelResult(before,None,[edit],[],None,[],[edit],[check],records+[{'check':check}])
    binding=dict(run_id='e3-visible-fixture',before_digest=_source_digest(before).hex(),
        paths=dict(audit=str(candidate/'stage-audit.json')),sha256=dict(audit=audit),
        preparation_sha256='a'*64,selection_digest='b'*64,components={'HEAD':'fixture'})
    return before,outcome,looks,binding


def save(tmp_path,captured):
    before,outcome,looks,binding=captured;out=tmp_path/'checked-outcome'
    receipt=api().save_e3_checkpoint(before,outcome,looks,out,binding=binding)
    return out,receipt


def restore(captured,out,receipt):
    before,_outcome,looks,binding=captured
    return api().restore_e3_checkpoint(before,looks,out,binding=binding,expected_receipt_sha256=receipt['receipt_sha256'])


def test_checked_rollback_fixture_survives_downstream_failure_exactly(tmp_path,captured):
    before,actual,_looks,_binding=captured
    assert actual.checks[0]['first']=='FAIL' and len(actual.rolled_back)==1 and actual.kept==[]
    out,receipt=save(tmp_path,captured)
    with pytest.raises(RuntimeError):raise RuntimeError('serializer failed after checkpoint')
    got=restore(captured,out,receipt)
    assert _source_digest(got.mesh)==_source_digest(actual.mesh)
    assert got.checks==actual.checks and got.records==actual.records
    assert got.rolled_back[0] is got.edits[0] and got.kept==[]
    assert got.edits[0].site==actual.edits[0].site and got.edits[0].evidence==actual.edits[0].evidence
    assert got.edits[0].reason==actual.edits[0].reason and got.edits[0].decision==actual.edits[0].decision
    assert receipt['mode']=='actual_checked_e3_checkpoint' and receipt['capture_only'] is True
    assert not (tmp_path/'serialized-candidate').exists()


@pytest.mark.parametrize('file',['arrays.npz','result.json','edit-log.jsonl','checkpoint-receipt.json'])
def test_capture_byte_tamper_refuses(tmp_path,captured,file):
    out,receipt=save(tmp_path,captured)
    with (out/file).open('ab') as stream:stream.write(b'changed')
    with pytest.raises(ValueError,match='hash'):restore(captured,out,receipt)


def reseal(out):
    path=out/'checkpoint-receipt.json';r=json.loads(path.read_text())
    r['files']={key:sha256_file(out/key) for key in r['files']};path.write_text(json.dumps(r))
    return dict(receipt_sha256=sha256_file(path))


@pytest.mark.parametrize('entry',['unknown.npy','mesh_positions.npy'])
def test_unknown_or_duplicate_archive_member_refuses(tmp_path,captured,entry):
    out,_receipt=save(tmp_path,captured)
    with zipfile.ZipFile(out/'arrays.npz','a') as archive:
        with pytest.warns(UserWarning) if entry=='mesh_positions.npy' else __import__('contextlib').nullcontext():
            archive.writestr(entry,b'invalid')
    with pytest.raises(ValueError,match='archive'):restore(captured,out,reseal(out))


def test_e3_remove_checkpoint_cannot_reference_new_arrays(tmp_path,captured):
    out,_receipt=save(tmp_path,captured);path=out/'result.json';data=json.loads(path.read_text())
    data['edits'][0]['new_faces']='../outside.npy';path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='E3|array'):restore(captured,out,reseal(out))


def test_external_binding_and_receipt_pin_required(tmp_path,captured):
    out,receipt=save(tmp_path,captured)
    with pytest.raises(ValueError,match='hash'):restore(captured,out,dict(receipt,receipt_sha256='0'*64))
    before,_outcome,looks,binding=captured
    with pytest.raises(ValueError,match='binding'):
        api().restore_e3_checkpoint(before,looks,out,binding=dict(binding,run_id='wrong'),expected_receipt_sha256=receipt['receipt_sha256'])


def test_actual_outcome_and_identity_partition_cannot_be_substituted(tmp_path,captured):
    before,actual,looks,binding=captured
    for index,bad in enumerate((replace(actual,result='legacy'),replace(actual,report={'fake':True}),
            replace(actual,stages=['legacy']),replace(actual,rolled_back=[replace(actual.edits[0])]))):
        with pytest.raises(ValueError,match='E3|partition'):
            api().save_e3_checkpoint(before,bad,looks,tmp_path/f'bad-{index}',binding=binding)
    moved=replace(actual,mesh=replace(actual.mesh,positions=actual.mesh.positions.copy()))
    moved.mesh.positions[0,0]+=.25
    with pytest.raises(ValueError,match='survivor|outcome|changed'):
        api().save_e3_checkpoint(before,moved,looks,tmp_path/'moved',binding=binding)


def test_drifted_input_retains_capture_but_prevents_verified_restore(tmp_path,captured):
    before,outcome,looks,binding=captured;Path(binding['paths']['audit']).write_text('changed during kernel')
    out=tmp_path/'diagnostic'
    with pytest.raises(ValueError,match='hash'):api().save_e3_checkpoint(before,outcome,looks,out,binding=binding)
    receipt=json.loads((out/'checkpoint-receipt.json').read_text())
    assert receipt['capture_only'] is True and receipt['binding']==binding
    with pytest.raises(ValueError,match='hash'):restore(captured,out,dict(receipt_sha256=sha256_file(out/'checkpoint-receipt.json')))


def test_actual_capture_is_exclusive(tmp_path,captured):
    out,_receipt=save(tmp_path,captured);before,outcome,looks,binding=captured
    with pytest.raises(ValueError,match='exists'):api().save_e3_checkpoint(before,outcome,looks,out,binding=binding)


def test_survivor_position_tables_are_bit_exact_including_signed_zero(tmp_path,captured):
    import numpy as np
    before,outcome,looks,binding=captured
    changed=replace(outcome,mesh=replace(outcome.mesh,positions=outcome.mesh.positions.copy()))
    zero=tuple(np.argwhere(changed.mesh.positions==0)[0]);changed.mesh.positions[zero]=-0.0
    assert changed.mesh.positions.tobytes()!=outcome.mesh.positions.tobytes()
    with pytest.raises(ValueError,match='outcome|exact'):
        api().save_e3_checkpoint(before,changed,looks,tmp_path/'signed-zero',binding=binding)
