"""Keep the live site's status file carrying Claude's `freshMainInfraUpper` key (owner request 2026-10-24).

Every interval: heartbeat the local progress file, download the live building-repair-status.json, set only the
`freshMainInfraUpper` key to the validated local document, and upload it to both web roots over the same SSH
path deploy.sh uses. Codex's uploader rewrites the whole file without this key; this loop re-adds it within one
interval. Nothing else in the live file is changed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from tools.main_infra_progress import heartbeat_progress, load_progress

LIVE = 'https://corllenium.ai.dev-environment.site/building-repair-status.json'
REMOTE = ('~/corllenium/app/public/building-repair-status.json', '~/corllenium/web/building-repair-status.json')


def ssh_args(key, known_hosts):
    return ['ssh', '-i', key, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', f'UserKnownHostsFile={known_hosts}', '-o', 'LogLevel=ERROR', '-o', 'ConnectTimeout=30', '-p', '27015',
            'devenvir@dev-environment.site']


LOCAL_FEED = Path(__file__).resolve().parents[2] / 'SIEGE-MAIN-INFRA-20261023' / 'dashboard' / 'public' / 'building-repair-status.json'
BROKEN_DIR = Path(__file__).resolve().parents[1] / 'data' / 'main-infra-fresh' / 'live-broken'


def salvage_live(raw: bytes) -> dict:
    """Parse the live feed; when it is truncated (an interrupted upload), keep every complete top-level key.

    The legacy keys come first and the fresh blocks last, so a cut inside `freshMainInfra` still leaves the
    other buildings' `completedUnits` intact. Missing fresh blocks are filled from the local SIEGE feed.
    """
    text = raw.decode('utf-8', errors='replace')
    try:
        live = json.loads(text)
        if not isinstance(live, dict):
            raise ValueError('live status is not an object')
        return live
    except ValueError:
        pass
    BROKEN_DIR.mkdir(parents=True, exist_ok=True)
    (BROKEN_DIR / time.strftime('live-%Y%m%d-%H%M%S.json')).write_bytes(raw)
    salvaged = None
    for key_name in ('freshMainInfraUpper', 'freshMainInfra'):
        cut = text.rfind(f'"{key_name}"')
        if cut > 0:
            prefix = text[:cut].rstrip().rstrip(',')
            try:
                salvaged = json.loads(prefix + '}')
                break
            except ValueError:
                continue
    if not isinstance(salvaged, dict):
        raise ValueError('live status unparsable and not salvageable')
    local = json.loads(LOCAL_FEED.read_text(encoding='utf-8')) if LOCAL_FEED.exists() else {}
    for key_name in ('freshMainInfra',):
        if key_name not in salvaged and key_name in local:
            salvaged[key_name] = local[key_name]
    salvaged['_salvaged_from_truncated_upload_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    return salvaged


def publish_once(progress, key, known_hosts):
    doc = load_progress(progress)
    live = salvage_live(urllib.request.urlopen(LIVE, timeout=30).read())
    current = live.get('freshMainInfraUpper')
    if current == doc and '_salvaged_from_truncated_upload_utc' not in live:
        return 'unchanged', doc
    live['freshMainInfraUpper'] = doc
    payload = json.dumps(live, indent=2, ensure_ascii=False).encode('utf-8')
    json.loads(payload)
    remote = f"cat > {REMOTE[0]}.tmp && mv -f {REMOTE[0]}.tmp {REMOTE[0]} && cp -f {REMOTE[0]} {REMOTE[1]}"
    subprocess.run(ssh_args(key, known_hosts) + [remote], input=payload, check=True, timeout=120)
    return 'uploaded', doc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--progress', type=Path, required=True)
    parser.add_argument('--key', default=str(Path.home() / '.ssh' / 'corllenium_siege_ed25519'))
    parser.add_argument('--known-hosts', default='D:/PROJECTS/02-Corllenium-Siege/deploy/known_hosts')
    parser.add_argument('--interval', type=float, default=30.0)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args(argv)
    while True:
        try:
            heartbeat_progress(args.progress)
            status, doc = publish_once(args.progress, args.key, args.known_hosts)
            print(time.strftime('%H:%M:%S'), status, doc['heartbeat_at'], doc['step'][:90], flush=True)
        except Exception as exc:  # keep the loop alive; the next tick retries
            print(time.strftime('%H:%M:%S'), 'live publish failed:', exc, flush=True)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == '__main__':
    raise SystemExit(main())
