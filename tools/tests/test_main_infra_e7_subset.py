from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from engine.io.snapshot import sha256_file
from tools.tests.test_main_infra_e7_serialization import fixture
from tools.main_infra_e3 import _source_digest


def api():
    from tools import main_infra_e7_subset
    return main_infra_e7_subset


@pytest.fixture
def donor(tmp_path):
    source, engine, before, ancestry, outcome, looks, inputs = fixture(tmp_path, mixed=True)
    component_root = tmp_path/'code'
    names = ('tools/main_infra_e7_1f_run.py', 'tools/main_infra_e7.py',
        'tools/main_infra_physical_validation.py', 'tools/main_infra_e3_binding.py',
        'engine/repair/engines/e7_thread.py', 'engine/repair/kernel.py',
        'engine/site_judge.py', 'engine/rays/caster.py')
    files = {}
    for name in names:
        path = component_root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
        files[name] = {'sha256': sha256_file(path), 'commit': 'fixture'}
    prep = tmp_path/'donor-preparation.json'
    paths = {k:v for k,v in inputs['paths'].items() if k != 'edit_log'}
    prep.write_text(json.dumps(dict(paths=paths,sha256={k:sha256_file(p) for k,p in paths.items()},
        components={'HEAD':'fixture','files':files},inputs={'before_digest':inputs['before_digest']})))
    worker = tmp_path/'donor-worker.json'
    worker.write_text(json.dumps(dict(preparation_sha256=sha256_file(prep),
        components={'HEAD':'fixture','files':files}, planned_cuts=2,kept_cuts=1,rolled_back_cuts=1,
        output_triangles=outcome.mesh.n_faces,checks=outcome.checks,state='failed')))
    donor_files = dict(preparation=str(prep),edit_log=inputs['paths']['edit_log'],worker=str(worker))
    expected = {k:sha256_file(p) for k,p in donor_files.items()}
    return before,looks,donor_files,expected,component_root,outcome


def select(donor):
    before,looks,paths,expected,root,_ = donor
    return api().verify_donor_subset(before,looks,paths=paths,expected_sha256=expected,
        component_root=root,expected_counts=(2,1))


def test_new_plan_selects_only_donor_kept_sites_in_original_order(donor):
    subset = select(donor)
    before,looks,_,_,_,old = donor
    assert [e.site for e in subset.edits] == [old.kept[0].site]
    assert all(e.site not in {r.site for r in old.rolled_back} for e in subset.edits)
    assert subset.proof['selected_donor_indices'] == [0]
    assert subset.proof['donor_planned'] == 2 and subset.proof['selected'] == 1
    assert subset.proof['old_verdict_is_not_reused'] is True
    got = api().run_checked_subset(before,looks,subset)
    assert got.kept == list(subset.edits) and got.rolled_back == []
    assert got.checks[0]['sites'] == 1 and got.checks[0]['first'] == 'PASS'
    assert got.checks[0] is not old.checks[0]
    assert got.records[-1] == {'check':got.checks[0]}


@pytest.mark.parametrize('name', ['preparation','edit_log','worker'])
def test_wrong_donor_hash_rejects_before_planner(donor,monkeypatch,name):
    _,_,_,expected,_,_ = donor
    expected[name] = '0'*64
    monkeypatch.setattr(api().E7Thread,'plan',lambda *_:pytest.fail('wrong donor reached planner'))
    with pytest.raises(ValueError,match='hash'):
        select(donor)


def test_changed_raw_and_component_are_rejected(donor):
    before,looks,paths,expected,root,_ = donor
    prep = json.loads(Path(paths['preparation']).read_text())
    raw = Path(prep['paths']['raw'])
    original = raw.read_bytes()
    raw.write_bytes(original+b'changed')
    with pytest.raises(ValueError,match='hash'):
        select(donor)
    raw.write_bytes(original)
    (root/'engine/repair/engines/e7_thread.py').write_text('changed code')
    with pytest.raises(ValueError,match='hash|component'):
        select(donor)


@pytest.mark.parametrize('change', ['site','face','kind','key','flag','missing','extra','order'])
def test_all_original_donor_records_are_bound(donor,change):
    _,_,paths,expected,_,_ = donor
    path = Path(paths['edit_log'])
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if change == 'site': rows[0]['site'] += 99
    if change == 'face': rows[0]['faces'] = [999]
    if change == 'kind': rows[0]['kind'] = 'remove'
    if change == 'key': rows[0]['added'][0] = '0'*64
    if change == 'flag': rows[0]['rolled_back'] = 'false'
    if change == 'missing': rows.pop(0)
    if change == 'extra': rows.insert(0,dict(rows[0]))
    if change == 'order': rows[:2] = rows[1::-1]
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    expected['edit_log'] = sha256_file(path)
    with pytest.raises(ValueError,match='donor|record|count|rollback'):
        select(donor)


def test_subset_input_and_typed_edits_cannot_change(donor):
    subset = select(donor)
    before,looks,*_ = donor
    changed = replace(before,positions=before.positions.copy())
    changed.positions[0,0] += .01
    with pytest.raises(ValueError,match='input|digest'):
        api().run_checked_subset(changed,looks,subset)
    subset.edits[0].evidence['changed'] = True
    with pytest.raises(ValueError,match='plan|seal'):
        api().run_checked_subset(before,looks,subset)


@pytest.mark.parametrize('charged',[True,False])
def test_fresh_default_failure_rolls_back_even_after_donor_pass(donor,monkeypatch,charged):
    from engine.site_judge import SiteJudge,FailingSamples,SiteVerdict
    subset = select(donor)
    before,looks,*_ = donor
    class WithFailure(SiteJudge):
        def check(self,after,focus):
            verdict = super().check(after,focus)
            s = verdict.samples
            face = subset.edits[0].faces[0] if charged else before.n_faces-1
            add = lambda a,row:np.concatenate([a,np.asarray(row,dtype=a.dtype)])
            samples = FailingSamples(face=add(s.face,[face]),index=add(s.index,[999]),
                point=np.vstack([s.point,[[1e6,1e6,1e6]]]),witness=np.vstack([s.witness,[[0,0,1.]]]),
                is_dir=add(s.is_dir,[True]),cluster=add(s.cluster,[len(s.clusters)]),
                clusters=s.clusters+[{'deleted':1}])
            return SiteVerdict(failing=verdict.failing|{(face,999)},summary=verdict.summary,
                               seconds=verdict.seconds,samples=samples)
    monkeypatch.setattr(api(),'SiteJudge',WithFailure)
    got = api().run_checked_subset(before,looks,subset)
    assert got.kept == [] and got.rolled_back == list(subset.edits)
    assert _source_digest(got.mesh) == _source_digest(before)
    assert got.checks[0]['first'] == 'FAIL'
    if not charged:
        assert got.checks[0]['stage_rolled_back']
