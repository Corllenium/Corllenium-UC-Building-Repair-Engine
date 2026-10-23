"""Publish Claude's 4F-7F progress file into the dashboard feed under its own key, never touching Codex's.

Codex's publisher owns ``freshMainInfra`` and the legacy keys of ``building-repair-status.json``.
This writer only sets ``freshMainInfraUpper`` to the validated contents of ``current-upper.json`` and
re-reads the feed immediately before each atomic replace, retrying when another writer changed it in
between, so neither side loses the other's update. ``--once`` publishes a single time; otherwise it loops.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import time

from tools.main_infra_progress import load_progress

KEY = 'freshMainInfraUpper'


def _read_feed(path):
    path = Path(path)
    if not path.exists():
        return {}, None
    stat = path.stat()
    doc = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(doc, dict):
        raise ValueError('Dashboard feed must be an object')
    return doc, (stat.st_mtime_ns, stat.st_size)


def _stamp(path):
    path = Path(path)
    return (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None


def publish_once(progress_path, feed_paths, *, attempts=5):
    """Write the validated progress doc under KEY into every feed; returns the doc. Never edits other keys."""
    doc = load_progress(progress_path)
    for feed in feed_paths:
        feed = Path(feed)
        for attempt in range(attempts):
            published, seen = _read_feed(feed)
            published[KEY] = doc
            feed.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=feed.parent, prefix=feed.name + '.upper.',
                                                 suffix='.tmp', delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump(published, stream, indent=2, ensure_ascii=False)
                    stream.write('\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                if _stamp(feed) != seen:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                os.replace(temporary, feed)
                temporary = None
                break
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        else:
            raise RuntimeError(f'Feed {feed} kept changing; upper status not published')
    return doc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--progress', type=Path, required=True)
    parser.add_argument('--feed', type=Path, action='append', required=True, help='building-repair-status.json (repeatable)')
    parser.add_argument('--interval', type=float, default=5.0)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args(argv)
    last = None
    while True:
        try:
            doc = publish_once(args.progress, args.feed)
            marker = (doc['updated_at'], doc['heartbeat_at'])
            if marker != last:
                print(f"published {KEY} {doc['run_id']} updated_at={doc['updated_at']} step={doc['step']}", flush=True)
                last = marker
        except (OSError, ValueError, RuntimeError) as exc:
            print(f'publish failed: {exc}', flush=True)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == '__main__':
    raise SystemExit(main())
