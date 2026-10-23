"""Read-only positive for the actual failed cohort; never loads model geometry."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.io.snapshot import sha256_file
from tools.main_infra_e7_native_policy import _read_policy, _native_sites, _signed_sites

ROOT=Path(__file__).resolve().parents[2]
POLICY=ROOT/'docs/superpowers/records/MAIN-INFRA-E7-NATIVE-SAFE-ATTEMPT4-20261024/policy.json'
POLICY_SHA='ff44af745864e72500a2ab48aaa9d735cd7f72659118f0688ddbd194049fe3eb'
PREPARATION=Path('D:/LLM_BACKUP/Codex session/main-infra-e7-attempt3-20261023/05-Corllenium-UC-Building-Repair-Engine/data/main-infra-e7/run-20261023-attempt3/preparation-1F.json')


def test_actual_failed_native_and_signed_cohort_derives_101_sites_without_geometry():
    if not PREPARATION.exists():pytest.skip('local immutable evidence not available')
    assert sha256_file(PREPARATION)=='e5af36dde9a242388985200cd6502b370dba87aba92ef152bec9e91b0f681e2a'
    original=json.loads(PREPARATION.read_text())
    subset=SimpleNamespace(proof=original['selection'],seal=original['selection_seal'],
        edits=[SimpleNamespace(site=site) for site in original['selection']['selected_sites']])
    policy,evidence=_read_policy(dict(path=str(POLICY),sha256=POLICY_SHA))
    native,pixels=_native_sites(policy,evidence,subset)
    signed=_signed_sites(policy,evidence,subset)
    assert pixels==335 and len(native)==92 and len(signed)==11
    assert native&signed=={2902,8451}
    assert len(native|signed)==101 and len(set(subset.proof['selected_sites'])-(native|signed))==172
    assert policy['excluded_sites']==sorted(native|signed)
    assert not {3409,5524,7143}&(native|signed)
