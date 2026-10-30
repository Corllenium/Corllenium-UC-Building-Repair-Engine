"""tools/run_floor_pipeline.py: one fresh MAIN INFRA floor through E3 -> E5 -> measure -> heal -> E4 -> publish, with every
engine, Validator, Blender and publishing step injected (no engine runs, one process). The fakes write the same files the
real tools write (stage-audit.json, external-validation.json, guard.json, validation/validation.json, comparison.json) so the
driver is exercised on what it actually reads."""
import hashlib
import json
from pathlib import Path

import pytest

from tools import run_floor_pipeline as rfp
from tools.run_floor_pipeline import finished_receipt

FLOOR = '7F'


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding='utf-8')
    return path


def make_candidate(path, *, triangles, cleanup_mode, text, input_triangles=20625, extra=None):
    """A candidate dir as the E5 / E4 runners save it: engine OBJ + stage-audit with the OBJ's hash."""
    path.mkdir(parents=True)
    (path / 'candidate.engine.obj').write_text(text, encoding='utf-8')
    (path / 'candidate.source.obj').write_text('source ' + text, encoding='utf-8')
    (path / '7th floor main infra.mtl').write_text('newmtl a\n', encoding='utf-8')
    (path / 'textures').mkdir()
    (path / 'edit-log.jsonl').write_text('', encoding='utf-8')
    audit = dict(cleanup_mode=cleanup_mode, input_triangles=input_triangles, output_triangles=triangles,
                 engine_candidate_sha256=sha(text), source_candidate_sha256=sha('source ' + text),
                 guard=dict(passed=False, state='pending'), independent_validation='pending', **(extra or {}))
    write_json(path / 'stage-audit.json', audit)
    return path


def make_root(tmp_path, floor=FLOOR):
    root = tmp_path / 'run'
    e3 = make_candidate(root / 'e3' / floor, triangles=20625, cleanup_mode='e3_remove_only', text='e3', input_triangles=26152,
                        extra=dict(before_snapshot=str(tmp_path / 'snap')))
    (tmp_path / 'snap').mkdir()
    (root / 'normalized' / floor).mkdir(parents=True)
    (root / 'normalized' / floor / 'before.engine.obj').write_text('before', encoding='utf-8')
    interior = root / 'independent-validator' / 'e3-interior' / floor
    write_json(interior / 'camera-qualification.json', dict(qualified=True))
    write_json(interior / 'qualified-native-poses.json', dict(poses=[dict(name=f'eye_{i}') for i in range(16)]))
    write_json(interior / 'renders' / 'comparison.json', dict(after_sha256=sha('e3'), views=[dict(name='eye_0', different_pixels=0)]))
    (root / 'logs').mkdir()
    return root, e3


class FakeProgress:
    """Records set_stage / set_floor calls; `floor()` is what the publisher reads back."""

    def __init__(self, unity_ready=True):
        self.calls, self.stages, self.state, self.unity_ready = [], {}, None, unity_ready
        self.blocker = 'measured before'

    def set_stage(self, floor, stage_id, status, percent, note=None):
        self.calls.append(('stage', floor, stage_id, status, percent, note))
        self.stages[stage_id] = dict(status=status, percent=percent, note=note)

    def set_floor(self, floor, state, step, *, blocker=None, **measured):
        self.calls.append(('floor', floor, state, step, blocker, measured))
        self.state = dict(state=state, step=step, blocker=blocker, **measured)

    def supports_state(self, state):
        return state != 'unity_ready' or self.unity_ready

    def floor(self, floor):
        return dict(blocker=self.blocker, state='blocked')


class Fakes:
    """Scripted verdicts per candidate engine hash; every step records its call."""

    def __init__(self, root, verdicts):
        self.root, self.verdicts, self.calls = root, verdicts, []
        self.e4_text = 'e4-merge'
        self.restore_text = 'restored'

    def record(self, name, **kw):
        self.calls.append((name, kw))
        return 0

    def run_e5(self, *, out, exclude, **kw):
        self.record('run_e5', out=out, exclude=exclude)
        make_candidate(Path(out), triangles=19345, cleanup_mode='e3_then_e5_cull', text='e5')
        return 0

    def run_e4(self, *, e5_candidate, out, exclude, **kw):
        self.record('run_e4', e5_candidate=e5_candidate, out=out, exclude=exclude)
        text = self.e4_text + (f'-x{Path(exclude).name}' if exclude else '')
        make_candidate(Path(out), triangles=19641, cleanup_mode='e3_then_e5_then_e4_merge', text=text, input_triangles=19345,
                       extra=dict(e5_candidate=dict(candidate=str(e5_candidate), engine_candidate_sha256=json.loads(
                           (Path(e5_candidate) / 'stage-audit.json').read_text())['engine_candidate_sha256'])))
        return 0

    def restore_faces(self, *, e5, faces, out, reason, **kw):
        self.record('restore_faces', e5=e5, faces=faces, out=out, reason=reason)
        make_candidate(Path(out), triangles=19345 + len(faces), cleanup_mode='e3_then_e5_cull', text=self.restore_text)
        return 0

    def measure(self, *, candidate, out, label, oracle, **kw):
        self.record('measure', candidate=candidate, out=out, label=label, oracle=oracle)
        candidate, out = Path(candidate), Path(out)
        engine_sha = json.loads((candidate / 'stage-audit.json').read_text())['engine_candidate_sha256']
        v = dict(self.verdicts[engine_sha])
        deleted = v.get('deleted', 0)
        checks = dict(textures=dict(status=v.get('textures', 'PASS'), samples_failed=v.get('samples_failed', 0)),
                      nothing_deleted=dict(status=v.get('nothing_deleted', 'PASS'), deleted=deleted, faces_unmet=v.get('faces_unmet', deleted),
                                           area_lost_in2=v.get('area_lost_in2', 1.5 if deleted else 0.0), failed_by=v.get('failed_by')),
                      problems=dict(status='FAIL', kinds=dict(flicker_diff=dict(before=4518, after=1199, target=100),
                                                                cracks=dict(before=5429, after=4631, target=100))))
        caster = 'BoundedBruteCaster (original float64 oracle)' if (oracle or v.get('caster') == 'oracle') else 'EmbreeCaster default'
        finished = v.get('finished_utc', '2026-10-30T00:00:00Z')
        out.mkdir(parents=True)
        write_json(out / 'guard.json', dict(passed=v.get('guard', True), totals=dict(moved_other=v.get('moved', 0)),
                                             report=dict(views=[]), caster=caster, depth_tol_inches=5.9e-05, finished_utc=finished))
        validation = dict(verdict='FAIL', checks=checks, sites=v.get('sites', []), inputs=dict(after_sha256=engine_sha))
        if v.get('e4_bound'):
            validation['physical_precision'] = dict(before='before.engine.obj', e4_region_source_faces={})
        write_json(out / 'validation' / 'validation.json', validation)
        write_json(out / 'external-validation.json', dict(
            label=label, worker='claude', reviewer='test', candidate_engine_sha256=engine_sha, output_triangles=1,
            guard=dict(passed=v.get('guard', True), totals=dict(moved_other=v.get('moved', 0)), caster=caster),
            validator=dict(verdict='FAIL', checks=checks, allowed_changes_active=['coincident_backface_removed'],
                           path=str(out / 'validation' / 'validation.json')),
            finished_utc=finished))
        return 0 if v.get('guard', True) and checks['textures']['status'] == 'PASS' else 2

    def render(self, *, before, after, out, poses=None, **kw):
        self.record('render', before=before, after=after, out=out, poses=poses)
        after = Path(after)
        px = self.verdicts[sha(after.read_text())].get('interior_px' if poses else 'native_px', 0)
        n = 16 if poses else 30
        write_json(Path(out) / 'comparison.json', dict(after_sha256=sha(after.read_text()), after=str(after),
                                                       views=[dict(name=f'v{i}', different_pixels=px if i == 0 else 0) for i in range(n)]))
        return 0

    def contact_sheet(self, *, out, **kw):
        self.record('contact_sheet', out=out)
        (Path(out) / 'all-views.png').write_bytes(b'png')
        (Path(out) / 'paired-detail.png').write_bytes(b'png')
        return 0

    def explain_e4(self, *, candidate, validation, **kw):
        self.record('explain_e4', candidate=candidate, validation=validation)
        return self.verdicts.get('explain', dict(e4_regions=[], e5_sites=[], unexplained=[], reasons=dict(e4_regions={}, e5_sites={})))

    # publishing
    def bind_guard(self, **kw):
        return self.record('bind_guard', **kw)

    def package_preview(self, **kw):
        return self.record('package_preview', **kw)

    def publish_evidence(self, **kw):
        return self.record('publish_evidence', **kw)

    def stage_errors(self, **kw):
        return self.record('stage_errors', **kw)

    def archive(self, **kw):
        return self.record('archive', **kw)

    def mirror_z(self, **kw):
        return self.record('mirror_z', **kw)

    def upload_live(self, **kw):
        return self.record('upload_live', **kw)

    def rebuild_library(self, **kw):
        return self.record('rebuild_library', **kw)

    def names(self):
        return [name for name, _ in self.calls]

    def steps(self):
        return {name: getattr(self, name) for name in rfp.STEP_NAMES}


def config_for(root, tmp_path, floor=FLOOR, **kw):
    return rfp.Config(floor=floor, root=root, worker='claude', claude_worktree=tmp_path / 'cl', progress=tmp_path / 'progress.json',
                      public=[tmp_path / 'pub1', tmp_path / 'pub2'], repo04=tmp_path / 'r04', repo03=tmp_path / 'r03',
                      z_root=tmp_path / 'z', blender=tmp_path / 'blender.exe', **{**dict(max_rounds=3, min_free_gb=5.0), **kw})


def run(root, tmp_path, fakes, progress=None, **kw):
    progress = progress or FakeProgress()
    summary = rfp.run_floor(config_for(root, tmp_path, **kw), steps=fakes.steps(), progress=progress,
                            free_gb=lambda: 32.0, sleep=lambda s: None)
    return summary, progress


PASS = dict(guard=True, textures='PASS', nothing_deleted='PASS', interior_px=45, native_px=294151)


def test_the_happy_path_runs_e5_e4_and_publishes_the_e4_candidate(tmp_path):
    root, _ = make_root(tmp_path)
    fakes = Fakes(root, {sha('e5'): PASS, sha('e4-merge'): dict(PASS, interior_px=12)})
    summary, progress = run(root, tmp_path, fakes)
    assert summary['status'] == 'published'
    assert fakes.names()[:2] == ['run_e5', 'measure']
    assert fakes.calls[0][1]['out'] == root / 'e5' / FLOOR
    e5_measure = fakes.calls[1][1]
    assert e5_measure['label'] == 'claude-e5-19345' and e5_measure['oracle'] is False
    assert e5_measure['out'] == root / 'independent-validator' / 'external' / 'claude-e5-19345'
    # the interior gate renders the qualified poses into <stage>-interior/<F>/renders, the native QA into <stage>-native-qa/<F>
    renders = [c for n, c in fakes.calls if n == 'render']
    assert renders[0]['out'] == root / 'independent-validator' / 'e5-interior' / FLOOR / 'renders'
    assert renders[0]['poses'] == root / 'independent-validator' / 'e3-interior' / FLOOR / 'qualified-native-poses.json'
    assert renders[1]['out'] == root / 'e5-native-qa' / FLOOR and renders[1]['poses'] is None
    assert (root / 'independent-validator' / 'e5-interior' / FLOOR / 'camera-qualification.json').exists()
    e4 = next(c for n, c in fakes.calls if n == 'run_e4')
    assert e4['e5_candidate'] == root / 'e5' / FLOOR and e4['out'] == root / 'e4' / f'{FLOOR}-round1' and e4['exclude'] is None
    e4_measure = [c for n, c in fakes.calls if n == 'measure'][1]
    assert e4_measure['label'] == 'claude-e4-round1-19641'
    assert summary['final_candidate'] == str(root / 'e4' / f'{FLOOR}-round1') and summary['final_stage'] == 'e4'
    published = {n: c for n, c in fakes.calls if n in ('bind_guard', 'package_preview', 'publish_evidence', 'stage_errors',
                                                          'archive', 'mirror_z', 'upload_live', 'rebuild_library')}
    assert set(published) == {'bind_guard', 'package_preview', 'publish_evidence', 'stage_errors', 'archive', 'mirror_z',
                              'upload_live', 'rebuild_library'}
    assert published['archive']['candidate'] == root / 'e4' / f'{FLOOR}-round1'
    assert published['stage_errors']['e5'] == root / 'e5' / FLOOR and published['stage_errors']['e4'] == root / 'e4' / f'{FLOOR}-round1'
    assert progress.state['state'] == 'unity_ready'
    assert progress.state['step'].startswith('LOCAL FIXED OBJ, Unity-ready: ' + str(
        tmp_path / 'r03' / 'Assets' / 'Models' / 'Campus' / 'Repaired' / 'Main-Infrastructure' / 'Floor' / 'Model-Floor_07'))
    assert progress.state['blocker'] == 'measured before'          # the Validator's measured text is kept
    assert progress.state['output_triangles'] == 19641
    assert {k: v['status'] for k, v in progress.stages.items()} == {s: 'done' for s in ('e3', 'e5', 'e4', 'measure', 'publish')}
    assert all(v['percent'] == 100 for v in progress.stages.values())
    # the running percent markers were posted on the way
    e5_marks = [c[4] for c in progress.calls if c[0] == 'stage' and c[2] == 'e5']
    assert e5_marks[0] == 10 and 60 in e5_marks and 80 in e5_marks and e5_marks[-1] == 100
    assert 'claude-e5-19345' in progress.stages['e5']['note'] and 'interior 45 px' in progress.stages['e5']['note']


def test_finished_candidates_and_receipts_are_reused_and_never_overwritten(tmp_path):
    root, _ = make_root(tmp_path)
    make_candidate(root / 'e5' / FLOOR, triangles=19345, cleanup_mode='e3_then_e5_cull', text='e5')
    fakes = Fakes(root, {sha('e5'): PASS, sha('e4-merge'): dict(PASS, interior_px=12)})
    # a finished receipt under another label (the queue's) for the E5 candidate ...
    done = root / 'independent-validator' / 'external' / 'claude-e5-fresh'
    fakes.measure(candidate=root / 'e5' / FLOOR, out=done, label='claude-e5-fresh', oracle=False)
    fakes.calls.clear()
    # ... a finished interior gate and native QA for it ...
    fakes.render(before='b', after=root / 'e5' / FLOOR / 'candidate.engine.obj', out=root / 'independent-validator' / 'e5-interior' / FLOOR / 'renders', poses='p')
    fakes.render(before='b', after=root / 'e5' / FLOOR / 'candidate.engine.obj', out=root / 'e5-native-qa' / FLOOR)
    (root / 'e5-native-qa' / FLOOR / 'all-views.png').write_bytes(b'png')
    (root / 'e5-native-qa' / FLOOR / 'paired-detail.png').write_bytes(b'png')
    fakes.calls.clear()
    # ... an E4 round-1 candidate from that E5 whose measurement never finished: the queue's folder (another label, dead pid)
    # and an earlier attempt under the driver's own label (dead pid)
    fakes.run_e4(e5_candidate=root / 'e5' / FLOOR, out=root / 'e4' / f'{FLOOR}-round1', exclude=None)
    fakes.calls.clear()
    queue = root / 'independent-validator' / 'external' / 'claude-e4-round1-7F'
    write_json(queue / 'external-validation.json', dict(candidate_engine_sha256=sha('e4-merge'), guard=dict(passed=True)))
    write_json(queue / 'guard-progress.json', dict(pid=999999999))
    own = root / 'independent-validator' / 'external' / 'claude-e4-round1-19641'
    write_json(own / 'external-validation.json', dict(candidate_engine_sha256=sha('e4-merge')))
    write_json(own / 'guard-progress.json', dict(pid=999999998))
    summary, progress = run(root, tmp_path, fakes)
    assert summary['status'] == 'published'
    assert 'run_e5' not in fakes.names() and 'run_e4' not in fakes.names()
    measures = [c for n, c in fakes.calls if n == 'measure']
    assert len(measures) == 1 and measures[0]['candidate'] == root / 'e4' / f'{FLOOR}-round1'
    assert measures[0]['out'] == own                              # the driver's label; the dead attempt moved aside first
    assert (queue / 'guard-progress.json').exists() and not finished_receipt(queue)   # another label: never touched
    aborted = [p for p in own.parent.iterdir() if p.name.startswith('claude-e4-round1-19641-aborted-')]
    assert len(aborted) == 1 and (aborted[0] / 'guard-progress.json').exists()
    renders = [c for n, c in fakes.calls if n == 'render']
    assert [r['out'].parent.name if r['poses'] else r['out'].parent.name for r in renders] == ['7F-round1', 'e4-native-qa']
    assert summary['measurements']['e5'][0]['receipt'] == str(done / 'external-validation.json')
    assert summary['measurements']['e5'][0]['reused'] is True
    assert 'claude-e5-fresh' in progress.stages['e5']['note']


def test_an_unfinished_measurement_with_a_live_process_is_waited_for(tmp_path, monkeypatch):
    root, _ = make_root(tmp_path)
    make_candidate(root / 'e5' / FLOOR, triangles=19345, cleanup_mode='e3_then_e5_cull', text='e5')
    fakes = Fakes(root, {sha('e5'): PASS, sha('e4-merge'): PASS})
    out = root / 'independent-validator' / 'external' / 'claude-e5-19345'
    write_json(out / 'external-validation.json', dict(candidate_engine_sha256=sha('e5'), guard=dict(passed=True)))
    write_json(out / 'guard-progress.json', dict(pid=4242))
    polls = []

    def alive(pid):
        polls.append(pid)
        if len(polls) == 2:           # the "other process" finishes its receipt while we wait
            fakes.measure(candidate=root / 'e5' / FLOOR, out=out.with_name('tmp-finished'), label='claude-e5-19345', oracle=False)
            fakes.calls.pop()         # the other process's work is not a driver call
            for name in ('external-validation.json', 'guard.json'):
                (out / name).write_bytes((out.with_name('tmp-finished') / name).read_bytes())
            (out / 'validation').mkdir()
            (out / 'validation' / 'validation.json').write_bytes((out.with_name('tmp-finished') / 'validation' / 'validation.json').read_bytes())
            return False
        return True

    monkeypatch.setattr(rfp, 'pid_alive', alive)
    fakes.calls.clear()
    summary, _ = run(root, tmp_path, fakes)
    assert summary['status'] == 'published'
    assert polls == [4242, 4242]
    assert [c['candidate'] for n, c in fakes.calls if n == 'measure'] == [root / 'e4' / f'{FLOOR}-round1']
    assert summary['measurements']['e5'][0]['reused'] is True


def test_validator_faces_are_restored_and_measured_again_until_the_bar_is_met(tmp_path):
    root, _ = make_root(tmp_path)
    fail = dict(guard=True, textures='FAIL', nothing_deleted='FAIL', samples_failed=79, deleted=46,
                sites=[dict(id=1, faces=[21504, 34754], checks=['textures', 'nothing_deleted']), dict(id=2, faces=[34754, 36508])])
    fakes = Fakes(root, {sha('e5'): fail, sha('restored'): PASS, sha('e4-merge'): PASS})
    summary, progress = run(root, tmp_path, fakes)
    assert summary['status'] == 'published'
    restore = next(c for n, c in fakes.calls if n == 'restore_faces')
    assert restore['e5'] == root / 'e5' / FLOOR and restore['faces'] == [21504, 34754, 36508]
    assert restore['out'] == root / 'e5' / f'{FLOOR}-restore1'
    assert 'claude-e5-19345' in restore['reason']
    labels = [c['label'] for n, c in fakes.calls if n == 'measure']
    assert labels == ['claude-e5-19345', 'claude-e5-restore1-19348', 'claude-e4-round1-19641']
    assert summary['e5_candidate'] == str(root / 'e5' / f'{FLOOR}-restore1')
    e4 = next(c for n, c in fakes.calls if n == 'run_e4')
    assert e4['e5_candidate'] == root / 'e5' / f'{FLOOR}-restore1'
    note = progress.stages['e5']['note']
    assert 'round 1' in note and 'textures FAIL (79 samples)' in note and 'coverage FAIL (46 deleted)' in note
    assert 'round 2' in note and 'restored 3 faces' in note
    assert summary['measurements']['e5'][0]['verdict'] == 'heal' and summary['measurements']['e5'][1]['verdict'] == 'pass'


def test_an_existing_restore_of_the_same_faces_is_reused(tmp_path):
    root, _ = make_root(tmp_path)
    make_candidate(root / 'e5' / FLOOR, triangles=19345, cleanup_mode='e3_then_e5_cull', text='e5')
    make_candidate(root / 'e5' / f'{FLOOR}-restore1', triangles=19347, cleanup_mode='e3_then_e5_cull', text='restored',
                   extra=dict(restored_from=dict(candidate=str(root / 'e5' / FLOOR)), restored_faces=dict(faces_original=[5, 9])))
    fail = dict(guard=True, textures='FAIL', sites=[dict(id=1, faces=[9, 5])])
    fakes = Fakes(root, {sha('e5'): fail, sha('restored'): PASS, sha('e4-merge'): PASS})
    summary, progress = run(root, tmp_path, fakes)
    assert summary['status'] == 'published' and 'restore_faces' not in fakes.names()
    assert summary['e5_candidate'] == str(root / 'e5' / f'{FLOOR}-restore1')
    assert 'reused 7F-restore1' in progress.stages['e5']['note']


def test_a_guard_failure_stops_with_a_diagnosis_needed_note(tmp_path):
    root, _ = make_root(tmp_path)
    fakes = Fakes(root, {sha('e5'): dict(guard=False, moved=328)})
    summary, progress = run(root, tmp_path, fakes)
    assert summary['status'] == 'e5_failed'
    assert 'restore_faces' not in fakes.names() and 'run_e4' not in fakes.names() and 'archive' not in fakes.names()
    assert progress.stages['e5']['status'] == 'failed'
    assert 'guard FAIL 328 px' in progress.stages['e5']['note'] and 'diagnosis needed' in progress.stages['e5']['note']
    assert progress.stages['measure']['status'] == 'failed'
    assert progress.stages['publish']['status'] == 'pending'
    assert progress.state['state'] == 'blocked'


def test_heal_rounds_are_bounded(tmp_path):
    root, _ = make_root(tmp_path)
    fail = dict(guard=True, textures='FAIL', sites=[dict(id=1, faces=[1])])
    fakes = Fakes(root, {sha('e5'): fail, sha('restored'): fail})
    fakes.restore_text = 'restored'
    summary, progress = run(root, tmp_path, fakes, max_rounds=2)
    assert summary['status'] == 'e5_failed'
    assert [c['out'].name for n, c in fakes.calls if n == 'restore_faces'] == ['7F-restore1']
    assert 'rounds exhausted' in progress.stages['e5']['note']


def test_an_e4_failure_keeps_the_e5_result_and_publishes_it(tmp_path):
    root, _ = make_root(tmp_path)
    verdicts = {sha('e5'): PASS, sha('e4-merge'): dict(guard=True, textures='FAIL', samples_failed=12, sites=[dict(id=1, faces=[7])], e4_bound=True),
                'explain': dict(e4_regions=[], e5_sites=[], unexplained=[dict(face=7)], reasons=dict(e4_regions={}, e5_sites={}))}
    fakes = Fakes(root, verdicts)
    summary, progress = run(root, tmp_path, fakes)
    assert summary['status'] == 'published' and summary['final_stage'] == 'e5'
    assert summary['final_candidate'] == str(root / 'e5' / FLOOR)
    assert progress.stages['e4']['status'] == 'failed'
    assert 'textures FAIL (12 samples)' in progress.stages['e4']['note'] and 'unexplained' in progress.stages['e4']['note']
    assert progress.stages['publish']['status'] == 'done'
    archive = next(c for n, c in fakes.calls if n == 'archive')
    assert archive['candidate'] == root / 'e5' / FLOOR
    stage_errors = next(c for n, c in fakes.calls if n == 'stage_errors')
    assert stage_errors['e4'] is None
    assert progress.state['step'].startswith('LOCAL FIXED OBJ, Unity-ready: ')
    assert 'E5 19,345' in progress.state['step'] and 'E4 failed' in progress.state['step']


def test_e4_reruns_without_the_explained_regions(tmp_path):
    root, _ = make_root(tmp_path)
    verdicts = {sha('e5'): PASS,
                sha('e4-merge'): dict(guard=True, nothing_deleted='FAIL', deleted=3, sites=[dict(id=1, faces=[7])], e4_bound=True),
                sha('e4-merge-x7F-round2-exclude.json'): PASS,
                'explain': dict(e4_regions=[12], e5_sites=[], unexplained=[], reasons=dict(e4_regions={'12': [dict(face=7)]}, e5_sites={}))}
    fakes = Fakes(root, verdicts)
    summary, progress = run(root, tmp_path, fakes)
    assert summary['status'] == 'published' and summary['final_stage'] == 'e4'
    e4_runs = [c for n, c in fakes.calls if n == 'run_e4']
    assert [r['out'].name for r in e4_runs] == ['7F-round1', '7F-round2']
    assert e4_runs[1]['exclude'] == root / 'e4' / '7F-round2-exclude.json'
    assert json.loads(e4_runs[1]['exclude'].read_text())['regions'] == [12]
    assert summary['final_candidate'] == str(root / 'e4' / '7F-round2')
    assert 'round 2' in progress.stages['e4']['note'] and 'excluded regions [12]' in progress.stages['e4']['note']


def test_e4_heal_without_the_e4_bound_receipt_keeps_the_e5_result(tmp_path):
    root, _ = make_root(tmp_path)
    fail = dict(guard=True, textures='FAIL', samples_failed=12, nothing_deleted='FAIL', deleted=5, faces_unmet=2, area_lost_in2=40.5,
                failed_by=dict(measure='floor_pixels', threshold=0.001), sites=[dict(id=1, faces=[7])], interior_px=9)
    fakes = Fakes(root, {sha('e5'): PASS, sha('e4-merge'): fail})      # the external receipt: no physical_precision block
    summary, progress = run(root, tmp_path, fakes)
    assert summary['status'] == 'published' and summary['final_stage'] == 'e5'
    assert 'explain_e4' not in fakes.names() and 'restore_faces' not in fakes.names()
    note = progress.stages['e4']['note']
    assert 'E4 heal needs the E4-bound Validator receipt (tools/run_e4_replay_loop.py); kept the E5 result' in note
    assert 'guard PASS 0 px' in note and 'textures FAIL (12 samples)' in note and 'coverage FAIL (5 deleted' in note
    assert 'faces_unmet 2' in note and 'area_lost_in2 40.5' in note and 'floor_pixels' in note and 'interior 9 px' in note
    assert progress.stages['e4']['status'] == 'failed' and progress.stages['publish']['status'] == 'done'
    assert next(c for n, c in fakes.calls if n == 'archive')['candidate'] == root / 'e5' / FLOOR


def test_publishing_the_already_published_e5_only_refreshes_the_state(tmp_path):
    root, _ = make_root(tmp_path)
    make_candidate(root / 'e5' / FLOOR, triangles=19345, cleanup_mode='e3_then_e5_cull', text='e5')
    write_json(tmp_path / 'progress.json', dict(source_revision='r' * 64, run_id='run-x', floors={}))
    for pub in ('pub1', 'pub2'):
        write_json(tmp_path / pub / 'models' / 'main-infra' / ('r' * 64) / FLOOR / 'run-x' / 'evidence' / 'stage-audit.json',
                   dict(engine_candidate_sha256=sha('e5'), cleanup_mode='e3_then_e5_cull', output_triangles=19345))
    fail = dict(guard=True, textures='FAIL', samples_failed=3, sites=[dict(id=1, faces=[7])])
    fakes = Fakes(root, {sha('e5'): PASS, sha('e4-merge'): fail})
    summary, progress = run(root, tmp_path, fakes)
    assert summary['status'] == 'published' and summary['final_stage'] == 'e5' and summary['publish']['already_published'] is True
    assert not {'bind_guard', 'package_preview', 'publish_evidence', 'stage_errors', 'archive', 'mirror_z', 'upload_live', 'rebuild_library'} & set(fakes.names())
    assert progress.stages['publish']['status'] == 'done' and progress.stages['publish']['percent'] == 100
    assert 'already published' in progress.stages['publish']['note']
    assert progress.state['state'] == 'unity_ready' and progress.state['step'].startswith('LOCAL FIXED OBJ, Unity-ready: ')
    assert {k: v['status'] for k, v in progress.stages.items()} == dict(e3='done', e5='done', e4='failed', measure='done', publish='done')


def test_a_floor_pixel_coverage_failure_is_not_healed_by_a_face_restore(tmp_path):
    root, _ = make_root(tmp_path)
    fail = dict(guard=True, textures='PASS', nothing_deleted='FAIL', deleted=0, faces_unmet=0, area_lost_in2=0.0,
                failed_by=dict(measure='floor_pixels', changed=412), sites=[dict(id=1, faces=[7, 8])])
    fakes = Fakes(root, {sha('e5'): fail})
    summary, progress = run(root, tmp_path, fakes)
    assert summary['status'] == 'e5_failed' and 'restore_faces' not in fakes.names()
    note = progress.stages['e5']['note']
    assert 'floor pixel measure' in note and 'floor_pixels' in note and 'faces_unmet 0' in note and 'not healable by a face restore' in note


def test_the_best_finished_receipt_is_chosen_for_a_candidate_hash(tmp_path):
    root, _ = make_root(tmp_path, floor='6F')
    make_candidate(root / 'e5' / '6F', triangles=25063, cleanup_mode='e3_then_e5_cull', text='e5')
    fakes = Fakes(root, {sha('e5'): dict(guard=False, moved=1, caster='embree', finished_utc='2026-10-30T02:00:00Z'), sha('e4-merge'): PASS})
    fakes.measure(candidate=root / 'e5' / '6F', out=root / 'independent-validator' / 'external' / 'claude-e5-25063', label='claude-e5-25063', oracle=False)
    fakes.verdicts[sha('e5')] = dict(PASS, caster='oracle', finished_utc='2026-10-30T01:00:00Z')      # older, but oracle and passing
    fakes.measure(candidate=root / 'e5' / '6F', out=root / 'independent-validator' / 'external' / 'claude-e5-25063-oracle', label='claude-e5-25063-oracle', oracle=True)
    fakes.calls.clear()
    summary, progress = run(root, tmp_path, fakes, floor='6F')
    assert summary['status'] == 'published'
    assert [c['candidate'] for n, c in fakes.calls if n == 'measure'] == [root / 'e4' / '6F-round1']
    assert summary['measurements']['e5'][0]['label'] == 'claude-e5-25063-oracle'
    assert 'claude-e5-25063-oracle' in progress.stages['e5']['note'] and 'float64 oracle' in progress.stages['e5']['note']
    assert [c['oracle'] for n, c in fakes.calls if n == 'measure'] == [True]


def test_an_embree_failed_receipt_on_an_oracle_floor_is_remeasured_with_the_oracle(tmp_path):
    root, _ = make_root(tmp_path, floor='6F')
    make_candidate(root / 'e5' / '6F', triangles=25063, cleanup_mode='e3_then_e5_cull', text='e5')
    fakes = Fakes(root, {sha('e5'): dict(guard=False, moved=1, caster='embree'), sha('e4-merge'): PASS})
    embree = root / 'independent-validator' / 'external' / 'claude-e5-25063'
    fakes.measure(candidate=root / 'e5' / '6F', out=embree, label='claude-e5-25063', oracle=False)
    fakes.calls.clear()
    fakes.verdicts[sha('e5')] = PASS
    summary, progress = run(root, tmp_path, fakes, floor='6F')
    assert summary['status'] == 'published'
    measures = [c for n, c in fakes.calls if n == 'measure']
    assert measures[0]['candidate'] == root / 'e5' / '6F' and measures[0]['oracle'] is True
    assert measures[0]['out'] == embree.with_name('claude-e5-25063-oracle') and measures[0]['label'] == 'claude-e5-25063-oracle'
    assert finished_receipt(embree) is not None                   # the Embree receipt stays where it was
    assert 'Embree guard FAIL' in progress.stages['e5']['note'] and 'claude-e5-25063-oracle' in progress.stages['e5']['note']


def test_the_interior_gate_over_threshold_fails_the_candidate(tmp_path):
    root, _ = make_root(tmp_path)
    fakes = Fakes(root, {sha('e5'): dict(PASS, interior_px=61)})
    summary, progress = run(root, tmp_path, fakes)
    assert summary['status'] == 'e5_failed'
    assert 'interior 61 px' in progress.stages['e5']['note'] and 'over 60' in progress.stages['e5']['note']


def test_without_unity_ready_in_the_dashboard_the_floor_is_validating_with_the_same_text(tmp_path):
    root, _ = make_root(tmp_path)
    fakes = Fakes(root, {sha('e5'): PASS, sha('e4-merge'): PASS})
    summary, progress = run(root, tmp_path, fakes, progress=FakeProgress(unity_ready=False))
    assert progress.state['state'] == 'validating'
    assert progress.state['step'].startswith('LOCAL FIXED OBJ, Unity-ready: ')


def test_the_ram_gate_waits_before_engine_and_validator_steps(tmp_path):
    root, _ = make_root(tmp_path)
    fakes = Fakes(root, {sha('e5'): PASS, sha('e4-merge'): PASS})
    readings = iter([2.0, 3.0, 9.0] + [9.0] * 20)
    waited = []
    rfp.run_floor(config_for(root, tmp_path), steps=fakes.steps(), progress=FakeProgress(), free_gb=lambda: next(readings),
                  sleep=waited.append)
    assert len(waited) == 2 and fakes.names()[0] == 'run_e5'


def test_a_running_e5_folder_without_a_finished_audit_is_not_touched(tmp_path):
    root, _ = make_root(tmp_path)
    (root / 'e5' / FLOOR).mkdir(parents=True)
    (root / 'e5' / FLOOR / 'candidate.engine.obj').write_text('partial', encoding='utf-8')
    fakes = Fakes(root, {})
    summary, progress = run(root, tmp_path, fakes)
    assert summary['status'] == 'e5_failed' and fakes.calls == []
    assert 'exists without a finished stage-audit' in progress.stages['e5']['note']


def test_dry_run_prints_the_commands_without_running_anything(tmp_path, capsys):
    root, _ = make_root(tmp_path)
    make_candidate(root / 'e5' / FLOOR, triangles=19345, cleanup_mode='e3_then_e5_cull', text='e5')
    fakes = Fakes(root, {})
    code = rfp.main(['--floor', FLOOR, '--worker', 'claude', '--dry-run', '--root', str(root), '--claude-worktree', str(tmp_path / 'cl'),
                     '--progress', str(tmp_path / 'p.json'), '--public', str(tmp_path / 'pub'), '--repo04', str(tmp_path / 'r04'),
                     '--repo03', str(tmp_path / 'r03'), '--z-root', str(tmp_path / 'z'), '--blender', str(tmp_path / 'blender.exe')])
    out = capsys.readouterr().out
    assert code == 0 and fakes.calls == []
    assert 'e3: reuse' in out and 'e5: reuse' in out
    assert 'main_infra_external_validate' in out and '--label claude-e5-19345' in out
    assert '--original-oracle' not in out                      # 7F runs the Embree guard
    assert 'main_infra_render_pair.py' in out and 'qualified-native-poses.json' in out
    assert 'run_checked_e4_floor.py' in out and '7F-round1' in out
    assert 'archive_upper_floor.py' in out and 'main_infra_fresh_library.py' in out
    assert 'heal' in out and 'max 3 rounds' in out
    assert not list((root / 'logs').glob('pipeline-*'))


def test_dry_run_on_4f_uses_the_oracle_and_fresh_e5(tmp_path, capsys):
    root, _ = make_root(tmp_path)
    (root / 'e3' / '4F').mkdir()
    write_json(root / 'e3' / '4F' / 'stage-audit.json', dict(cleanup_mode='e3_remove_only', before_snapshot='s', output_triangles=52865))
    code = rfp.main(['--floor', '4F', '--worker', 'claude', '--dry-run', '--root', str(root), '--claude-worktree', str(tmp_path / 'cl'),
                     '--progress', str(tmp_path / 'p.json'), '--exclude-sites', str(root / 'e5' / 'exclusions' / '4F.json')])
    out = capsys.readouterr().out
    assert code == 0
    assert 'run_checked_e5_floor.py' in out and '--from-e3' in out and '--exclude-sites' in out and '--original-oracle' in out


def test_the_cli_parses_its_arguments():
    args = rfp.build_parser().parse_args(['--floor', '7F', '--worker', 'claude', '--max-rounds', '3'])
    assert args.floor == '7F' and args.worker == 'claude' and args.max_rounds == 3 and args.dry_run is False
    cfg = rfp.config_from_args(args)
    assert cfg.root == rfp.DEFAULT_RUN_ROOT and cfg.progress == rfp.DEFAULT_PROGRESS and cfg.raw_name == '7th floor main infra.obj'
    assert cfg.oracle is False and rfp.config_from_args(rfp.build_parser().parse_args(['--floor', '6F'])).oracle is True
    assert str(cfg.root).startswith('D:')
    with pytest.raises(SystemExit):
        rfp.build_parser().parse_args(['--floor', '9F'])


def test_the_progress_writer_falls_back_to_writing_the_stage_fields_directly(tmp_path):
    helper = tmp_path / 'old_progress.py'
    helper.write_text('STATES = {"validating", "blocked"}\n'
                      'import json\n'
                      'def update_floor(path, floor_id, state, step, *, blocker=None, **measured):\n'
                      '    doc = json.loads(open(path).read()); doc["floors"][floor_id].update(state=state, step=step, blocker=blocker, **measured)\n'
                      '    open(path, "w").write(json.dumps(doc))\n', encoding='utf-8')
    progress_path = tmp_path / 'current-upper.json'
    write_json(progress_path, dict(floors={'7F': dict(state='blocked', step='x', blocker='b')}, updated_at='2026-10-30T00:00:00Z'))
    writer = rfp.ProgressWriter(progress_path, helper)
    assert writer.supports_state('unity_ready') is False and writer.supports_state('validating') is True
    writer.set_stage('7F', 'e3', 'done', 100)
    writer.set_stage('7F', 'e5', 'running', 60, note='engine finished')
    doc = json.loads(progress_path.read_text())
    stages = doc['floors']['7F']['stages']
    assert [(s['id'], s['status'], s['percent']) for s in stages] == [('e3', 'done', 100), ('e5', 'running', 60)]
    assert stages[1]['note'] == 'engine finished' and stages[1]['label'] == 'Coincident layers'
    assert doc['floors']['7F']['percent_complete'] == 80
    assert doc['updated_at'] != '2026-10-30T00:00:00Z'
    writer.set_stage('7F', 'e5', 'done', 100, note='bar met')
    assert json.loads(progress_path.read_text())['floors']['7F']['percent_complete'] == 100
    writer.set_floor('7F', 'validating', 'LOCAL FIXED OBJ, Unity-ready: x', blocker='kept', output_triangles=1)
    assert json.loads(progress_path.read_text())['floors']['7F']['state'] == 'validating'
    assert writer.floor('7F')['blocker'] == 'kept'


def test_the_progress_writer_uses_set_stage_when_the_helper_has_it(tmp_path):
    helper = tmp_path / 'new_progress.py'
    helper.write_text('STATES = {"unity_ready"}\nCALLS = []\n'
                      'def set_stage(path, floor_id, stage_id, status, percent, note=None, label=None, **kw):\n'
                      '    CALLS.append((str(path), floor_id, stage_id, status, percent, note, label))\n'
                      'def update_floor(path, floor_id, state, step, *, blocker=None, **measured):\n'
                      '    CALLS.append(("floor", floor_id, state, step, blocker, measured))\n'
                      'def load_progress(path):\n'
                      '    return {"floors": {"7F": {"blocker": "live"}}}\n', encoding='utf-8')
    writer = rfp.ProgressWriter(tmp_path / 'p.json', helper)
    writer.set_stage('7F', 'measure', 'running', 10, note='n')
    writer.set_floor('7F', 'unity_ready', 'step', blocker=None, input_triangles=2)
    calls = writer.module.CALLS
    assert calls[0] == (str(tmp_path / 'p.json'), '7F', 'measure', 'running', 10, 'n', None)
    assert calls[1] == ('floor', '7F', 'unity_ready', 'step', None, dict(input_triangles=2))
    assert writer.supports_state('unity_ready') and writer.floor('7F') == {'blocker': 'live'}
