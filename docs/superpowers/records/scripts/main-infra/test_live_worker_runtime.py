import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path('D:/PROJECTS/UC MODEL FIXER')
SCRIPT = Path(__file__).with_name('live-worker-status-runtime.ps1')


class LiveWorkerRuntime(unittest.TestCase):
    def test_retry_uses_actual_worker_path_and_reports_serializer_failure(self):
        code = SCRIPT.read_text(encoding='utf-8').split("$taskPython=@'\n", 1)[1].split("\n'@", 1)[0]
        original = json.loads((ROOT / 'data/main-infra-fresh/current.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory(prefix='live-worker-runtime-', dir=ROOT / 'data/tmp') as folder:
            fixture = Path(folder)
            def save(path, value):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value), encoding='utf-8')
            save(fixture / 'data/main-infra-fresh/current.json', original)
            old = fixture / '.claude/worktrees/MAIN-INFRA-E3-20261023/data/main-infra-e3/run-20261023'
            for floor in ('2F', '3F'):
                save(old / f'worker-{floor}.json', dict(pid=22 if floor == '2F' else 33, state='failed', error='old allocation failure'))
            newer = fixture / 'retry/worker-2F.json'
            save(newer, dict(pid=222, state='running_checked_E3'))
            one = fixture / 'retry/worker-1F.json'
            save(one, dict(pid=111, state='failed', error='ValueError: source boundary'))
            upper = dict(source_revision=original['source_revision'], job_id='MAIN-INFRA-CLAUDE-4F-7F-20261023', run_id='fixture-upper', updated_at=original['updated_at'], floors={f:original['floors'][f] for f in ('4F','5F','6F','7F')})
            upper['floors']['6F'].update(state='blocked', step='Signed targets still fail', blocker='Signed targets still fail')
            save(fixture / '.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/data/main-infra-fresh/current-upper.json', upper)
            save(fixture / '.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/data/main-infra-fresh/run-claude-4f-7f-20261023/e3/worker-6F.json', dict(pid=66, state='candidate_saved', output_triangles=42))
            observations = {'1F':dict(alive=False,worker_path=str(one)), '2F':dict(alive=True,cpu=1,start='2026-10-23T13:00:00Z',worker_path=str(newer)), '3F':dict(alive=False,worker_path=str(old / 'worker-3F.json'))}
            code = code.replace("root=Path('D:/PROJECTS/UC MODEL FIXER')", f'root=Path({str(fixture)!r})')
            saved = os.environ.get('UC_MODEL_WORKER_OBSERVATIONS')
            try:
                os.environ['UC_MODEL_WORKER_OBSERVATIONS'] = json.dumps(observations)
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(code, str(SCRIPT), 'exec'), {})
                result = json.loads((fixture / 'data/main-infra-fresh/current.json').read_text())
                self.assertEqual(result['floors']['2F']['state'], 'cleaning')
                self.assertEqual(result['floors']['2F']['worker_pid'], 222)
                self.assertIn('source boundary', result['floors']['1F']['blocker'])
                self.assertEqual(result['floors']['6F']['state'], 'blocked')
                self.assertEqual(result['floors']['6F']['blocker'], 'Signed targets still fail')
                self.assertEqual(result['floors']['6F']['output_triangles'], 42)
                observations['2F']['alive'] = False
                save(newer, dict(pid=222,state='failed',error='test stopped'))
                os.environ['UC_MODEL_WORKER_OBSERVATIONS'] = json.dumps(observations)
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(code, str(SCRIPT), 'exec'), {})
                result = json.loads((fixture / 'data/main-infra-fresh/current.json').read_text())
                self.assertNotIn('investigating shared memory allocation failure', result['step'])
                self.assertIn('source boundary', result['step'])
                observations.pop('3F')
                result['floors']['3F'].update(state='queued', step='Serial retry prepared', blocker=None)
                save(fixture / 'data/main-infra-fresh/current.json', result)
                os.environ['UC_MODEL_WORKER_OBSERVATIONS'] = json.dumps(observations)
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        exec(compile(code, str(SCRIPT), 'exec'), {})
                except KeyError:
                    self.fail('Deferred floor still requires an obsolete worker')
                result = json.loads((fixture / 'data/main-infra-fresh/current.json').read_text())
                self.assertEqual(result['floors']['3F']['state'], 'queued')
                save(one, dict(pid=111, state='checked_checkpoint_saved', checkpoint_status='verified'))
                observations['1F']['alive'] = True
                os.environ['UC_MODEL_WORKER_OBSERVATIONS'] = json.dumps(observations)
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(code, str(SCRIPT), 'exec'), {})
                result = json.loads((fixture / 'data/main-infra-fresh/current.json').read_text())
                self.assertEqual(result['floors']['1F']['state'], 'cleaning')
                self.assertIsNone(result['floors']['1F']['blocker'])
                self.assertIn('checkpoint', result['floors']['1F']['step'])
            finally:
                if saved is None:
                    os.environ.pop('UC_MODEL_WORKER_OBSERVATIONS', None)
                else:
                    os.environ['UC_MODEL_WORKER_OBSERVATIONS'] = saved


if __name__ == '__main__':
    unittest.main()
