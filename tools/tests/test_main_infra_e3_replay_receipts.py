"""The two committed E3 producers bind the same BEFORE through different receipt keys."""
import json
from pathlib import Path

import pytest

from engine.io.snapshot import sha256_file
from tools.main_infra_e3_replay import load_replay_plan
from tools.tests.test_main_infra_e3_replay import fixture


ACTUAL_AUDIT=Path('D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/MAIN-INFRA-E3-20261023/data/main-infra-e3/run-20261023-attempt2/3F/stage-audit.json')
ACTUAL_AUDIT_SHA='56ab090d861106c2801b2dab057ba5e9df6109ac69d87faaf29b718c87389512'


def qualified_receipt(tmp_path, floor='3F'):
    before,looks,candidate,_old_hash=fixture(tmp_path)
    path=candidate/'stage-audit.json'
    audit=json.loads(path.read_text())
    receipt=audit['input_receipt']
    assert receipt.pop('before_sha256')==receipt['engine_obj_sha256']
    receipt['floor_id']=floor
    path.write_text(json.dumps(audit))
    return before,looks,candidate,path


def test_retained_producer_receipt_uses_engine_pin_without_before_alias():
    assert sha256_file(ACTUAL_AUDIT)==ACTUAL_AUDIT_SHA
    actual=json.loads(ACTUAL_AUDIT.read_text())['input_receipt']
    assert 'before_sha256' not in actual and actual['floor_id']=='3F'
    assert actual['engine_obj_sha256']=='740103bb4197a1270e4c00e38abe9971e12f5c80ebe14502e4acd75148afbc82'
    assert actual['qualification_sha256']=='5e1880c494bb4fa532a1d50bce5515d20cc02e532d82c5e55db69e59a83a7424'


@pytest.mark.parametrize('floor',['2F','3F'])
def test_qualified_producer_schema_replays_original_exact_tiny_edit(tmp_path,floor):
    before,looks,candidate,path=qualified_receipt(tmp_path,floor)
    edits,proof=load_replay_plan(before,looks,candidate,expected_audit_sha256=sha256_file(path),restore_sites=())
    assert len(edits)==1 and edits[0].site==0 and edits[0].faces==(1,)
    assert proof['original_before_sha256']==json.loads(path.read_text())['input_receipt']['engine_obj_sha256']


@pytest.mark.parametrize('change',['present_none','present_wrong','engine_none','engine_missing','engine_wrong','floor_1F','floor_missing','floor_unknown'])
def test_receipt_adapter_never_ignores_present_mismatch_or_unknown_schema(tmp_path,change):
    before,looks,candidate,path=qualified_receipt(tmp_path)
    audit=json.loads(path.read_text());receipt=audit['input_receipt']
    if change=='present_none':receipt['before_sha256']=None
    elif change=='present_wrong':receipt['before_sha256']='0'*64
    elif change=='engine_none':receipt['engine_obj_sha256']=None
    elif change=='engine_missing':del receipt['engine_obj_sha256']
    elif change=='engine_wrong':receipt['engine_obj_sha256']='0'*64
    elif change=='floor_1F':receipt['floor_id']='1F'
    elif change=='floor_missing':del receipt['floor_id']
    elif change=='floor_unknown':receipt['floor_id']='4F'
    path.write_text(json.dumps(audit))
    with pytest.raises(ValueError,match='hash|qualification'):
        load_replay_plan(before,looks,candidate,expected_audit_sha256=sha256_file(path),restore_sites=())
