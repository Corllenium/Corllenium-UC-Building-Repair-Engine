"""Claude's upper-floor publisher writes only its own feed key and keeps every other key byte for byte."""
import json
from pathlib import Path

import pytest


def upper_progress(tmp_path):
    from tools.main_infra_progress import FLOORS, utc_now, write_progress
    now = utc_now()
    doc = {'schema_version': 1, 'building_id': 'MAIN_INFRA', 'source_revision': 'a' * 64, 'run_id': 'upper-run',
           'source_label': 'Fresh Minecraft export', 'source_state': 'frozen', 'scale_metres_per_block': 1,
           'state': 'running', 'step': '7F: rendering', 'updated_at': now, 'last_work_event_at': now, 'heartbeat_at': now,
           'floors': {f: {'floor_id': f'MAIN_INFRA_{f}', 'state': 'cancelled' if f in ('1F', '2F', '3F') else 'queued',
                          'step': 'x', 'blocker': None, 'source_preview': None, 'candidate_preview': None, 'accepted_preview': None,
                          'evidence_refs': [], 'validator_ref': None, 'owner_decision_ref': None} for f in FLOORS}}
    path = tmp_path / 'current-upper.json'
    write_progress(path, doc)
    return path


def test_publisher_adds_only_its_key_and_preserves_codex_and_legacy_keys(tmp_path):
    from tools.publish_upper_status import KEY, publish_once
    progress = upper_progress(tmp_path)
    feed = tmp_path / 'public' / 'building-repair-status.json'
    feed.parent.mkdir()
    legacy = {'activeUnit': 'CHTM_sidewalk_zone', 'completedUnits': {'x': {'trisAfter': 1}}, 'freshMainInfra': {'run_id': 'codex'}}
    feed.write_text(json.dumps(legacy))
    second = tmp_path / 'out' / 'building-repair-status.json'
    doc = publish_once(progress, [feed, second])
    for path in (feed, second):
        saved = json.loads(path.read_text())
        assert saved[KEY] == doc and saved[KEY]['run_id'] == 'upper-run'
    saved = json.loads(feed.read_text())
    assert {k: v for k, v in saved.items() if k != KEY} == legacy
    assert json.loads(second.read_text()) == {KEY: doc}


def test_publisher_refuses_invalid_progress_and_leaves_feed_untouched(tmp_path):
    from tools.publish_upper_status import publish_once
    progress = tmp_path / 'bad.json'
    progress.write_text(json.dumps({'schema_version': 2}))
    feed = tmp_path / 'feed.json'
    feed.write_text('{"freshMainInfra": 1}')
    with pytest.raises(ValueError):
        publish_once(progress, [feed])
    assert feed.read_text() == '{"freshMainInfra": 1}'
    assert not list(tmp_path.glob('feed.json.upper.*'))
