import json
import subprocess

from tools import publish_upper_status_live as live


def test_feed_stays_outside_every_public_folder():
    assert live.FEED == '~/corllenium/corllenium-data/building-repair-status.json'
    assert live.FEED not in live.REMOTE


def test_publish_reads_and_writes_the_feed_over_ssh_only(monkeypatch):
    doc = {'updated_at': '2026-10-31T00:00:00Z', 'step': 'x', 'heartbeat_at': 'y'}
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv[-1], kwargs.get('input')))
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({'state': 'kept'}).encode())

    monkeypatch.setattr(live, 'load_progress', lambda _: doc)
    monkeypatch.setattr(live, 'codex_document', lambda: None)
    monkeypatch.setattr(live.subprocess, 'run', fake_run)

    status, _ = live.publish_once('progress', 'key', 'hosts')

    assert status == 'uploaded'
    assert calls[0][0] == f'cat {live.FEED}'
    assert 'public' not in calls[1][0] and 'web/' not in calls[1][0]
    assert json.loads(calls[1][1]) == {'state': 'kept', 'freshMainInfraUpper': doc}
