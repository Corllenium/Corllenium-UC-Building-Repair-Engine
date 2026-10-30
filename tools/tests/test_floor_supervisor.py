"""tools/floor_supervisor.py: the queue decisions, adoption of running work and restart limits, with no real processes."""
import json

import pytest

from tools.floor_supervisor import MAX_CRASHES, Service, Supervisor, acquire_lock, load_queue


def make(tmp_path, floors=('4F',), processes=None, ports=()):
    run_root = tmp_path / 'run'
    (run_root / 'logs').mkdir(parents=True)
    state = tmp_path / 'sup'
    state.mkdir()
    (state / 'queue.json').write_text(json.dumps({'floors': [{'floor': f} for f in floors]}), encoding='utf-8')
    started = []
    box = {'processes': list(processes or [])}

    def start(cmd, cwd, log):
        started.append(cmd)
        return FakeProcess()

    sup = Supervisor(state_dir=state, run_root=run_root, services=[], list_processes=lambda: box['processes'],
                     port_open=lambda port: port in ports, start=start, pipeline_command=lambda floor: ['driver', floor])
    return sup, started, box


class FakeProcess:
    def __init__(self, code=None):
        self.code = code

    def poll(self):
        return self.code


def test_runs_the_first_pending_floor_only(tmp_path):
    sup, started, _ = make(tmp_path, floors=('4F', '3F'))
    sup.tick()
    sup.tick()
    assert started == [['driver', '4F']]
    assert load_queue(sup.queue_path)['floors'][0]['state'] == 'running'
    assert load_queue(sup.queue_path)['floors'][1].get('state', 'pending') == 'pending'


def test_adopts_a_pipeline_that_is_already_running(tmp_path):
    sup, started, _ = make(tmp_path, processes=['python -B -u tools/run_floor_pipeline.py --floor 4F --worker claude'])
    sup.tick()
    assert started == []
    assert load_queue(sup.queue_path)['floors'][0]['state'] == 'adopted'


def test_published_summary_finishes_the_floor_and_moves_on(tmp_path):
    sup, started, box = make(tmp_path, floors=('4F', '3F'), processes=['tools/run_floor_pipeline.py --floor 4F'])
    sup.tick()
    box['processes'] = []
    (sup.run_root / 'logs' / 'pipeline-4F-summary.json').write_text(json.dumps({'status': 'published'}), encoding='utf-8')
    sup.tick()
    floors = load_queue(sup.queue_path)['floors']
    assert floors[0]['state'] == 'done'
    assert started == [['driver', '3F']]


def test_a_killed_pipeline_restarts_then_stops_at_the_limit(tmp_path):
    sup, started, _ = make(tmp_path)
    for _ in range(MAX_CRASHES + 3):
        sup.tick()
        if sup.child is not None:
            sup.child[1].code = 1
    assert len(started) == MAX_CRASHES
    entry = load_queue(sup.queue_path)['floors'][0]
    assert entry['state'] == 'blocked' and entry['crashes'] == MAX_CRASHES


def test_a_failed_floor_is_blocked_at_once_and_the_queue_continues(tmp_path):
    sup, started, _ = make(tmp_path, floors=('4F', '3F'))
    sup.tick()
    sup.child[1].code = 2
    sup.tick()
    floors = load_queue(sup.queue_path)['floors']
    assert floors[0]['state'] == 'blocked' and 'measured failure' in floors[0]['note']
    assert started[-1] == ['driver', '3F']


def test_an_adopted_run_with_a_failed_summary_is_blocked_not_rerun(tmp_path):
    sup, started, box = make(tmp_path, processes=['tools/run_floor_pipeline.py --floor 4F'])
    sup.tick()
    box['processes'] = []
    (sup.run_root / 'logs' / 'pipeline-4F-summary.json').write_text(json.dumps({'status': 'e5_failed'}), encoding='utf-8')
    sup.tick()
    assert load_queue(sup.queue_path)['floors'][0]['state'] == 'blocked' and started == []


def test_stop_file_starts_nothing_new(tmp_path):
    sup, started, _ = make(tmp_path)
    (sup.state_dir / 'STOP').write_text('', encoding='utf-8')
    sup.tick()
    assert started == []


def test_services_are_adopted_or_started(tmp_path):
    sup, started, _ = make(tmp_path, processes=['-m tools.publish_upper_status_live --progress x'], ports=(4192,))
    sup.services = [Service('live', 'tools.publish_upper_status_live', ['live'], tmp_path),
                    Service('local', 'tools.publish_upper_status ', ['local'], tmp_path),
                    Service('preview', None, ['preview'], tmp_path, port=4192)]
    sup.tick()
    assert ['local'] in started and ['live'] not in started and ['preview'] not in started


def test_second_lock_is_refused(tmp_path):
    first = acquire_lock(tmp_path / 'lock')
    assert first is not None
    assert acquire_lock(tmp_path / 'lock') is None
    first.close()
    assert acquire_lock(tmp_path / 'lock') is not None


def test_bad_queue_is_refused(tmp_path):
    path = tmp_path / 'queue.json'
    path.write_text(json.dumps({'floors': [{'floor': '9F'}]}), encoding='utf-8')
    with pytest.raises(ValueError):
        load_queue(path)
