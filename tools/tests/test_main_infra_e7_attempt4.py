import json
from pathlib import Path

import pytest

from engine.io.snapshot import sha256_file
from tools.tests.test_main_infra_e7_attempt3 import prepared
from tools.tests.test_main_infra_e7_subset import donor


def test_attempt4_namespace_refuses_before_input_loading(tmp_path):
    from tools import main_infra_e7_attempt3 as run
    with pytest.raises(ValueError,match='namespace'):
        run.prepare({}, {}, {}, tmp_path/'preparation.json',tmp_path/'wrong/1F',
            native_policy={'path':'unused','sha256':'0'*64})


def test_attempt4_execute_refuses_policy_mismatch_before_kernel(prepared,monkeypatch):
    run,plan,out,*_=prepared
    value=json.loads(plan.read_text())
    value['native_policy']={'path':'untrusted','sha256':'0'*64}
    value['run_id']='MAIN-INFRA-E7-1F-attempt4-20261024'
    plan.write_text(json.dumps(value))
    monkeypatch.setattr(run,'run_checked_subset',lambda *_:pytest.fail('policy mismatch reached kernel'))
    with pytest.raises(ValueError,match='policy'):
        run.execute(plan,sha256_file(plan),native_policy={'path':'trusted','sha256':'1'*64})
    assert not out.exists() and not (out.parent/'execution-1F').exists()
