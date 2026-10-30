"""Keep the MAIN INFRA floor queue and its publishers running with no agent session (owner request 2026-10-30).

Started by the Windows task `Corllenium-Main-Infra-Supervisor` at logon and every 5 minutes; a file lock keeps one
instance. Every tick it:

- adopts or starts the services: both status publishers and the local dashboard preview on port 4192;
- works the floor queue `<state>/queue.json` ({"floors": [{"floor": "4F"}, ...]}) one floor at a time with
  `tools/run_floor_pipeline.py`, which reuses finished receipts, so a restart resumes instead of starting over.

A pipeline already running (started by anyone) is adopted, never duplicated. Exit 0 or a published summary = done.
Exit 2 = measured failure: the floor is blocked with a note and the queue goes on; a rerun would measure the same.
A crash or a killed run restarts, at most MAX_CRASHES times, then the floor is blocked. To pause, create `<state>/STOP`:
nothing new starts and running work is left alone. Status: `<state>/status.json`, log: `<state>/supervisor.log`.

The task needs a signed-in Windows user (interactive token): it survives closing Claude, not signing out.
"""
from __future__ import annotations

import argparse
import json
import msvcrt
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
WORKTREES = ENGINE.parent
CLAUDE = WORKTREES / 'MAIN-INFRA-CLAUDE-4F-7F-20261023'
DASHBOARD_OUT = WORKTREES / 'SIEGE-MAIN-INFRA-20261023' / 'dashboard' / 'out'
RUN_ROOT = CLAUDE / 'data' / 'main-infra-fresh' / 'run-claude-4f-7f-20261023'
STATE_DIR = CLAUDE / 'data' / 'main-infra-fresh' / 'supervisor'
PYTHON = WORKTREES.parent.parent / '.venv' / 'Scripts' / 'python.exe'
FLOORS = tuple(f'{n}F' for n in range(1, 8))
MAX_CRASHES = 3
TICK_S = 30
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, doc) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(doc, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def load_queue(path: Path) -> dict:
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    for entry in doc.get('floors', []):
        if entry.get('floor') not in FLOORS:
            raise ValueError(f'unknown floor in queue: {entry.get("floor")}')
    return doc


def acquire_lock(path: Path):
    """An open, locked file, or None when another instance holds it. Windows frees it when the process dies."""
    stream = open(path, 'a+b')
    try:
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        stream.close()
        return None
    return stream


def list_python_processes() -> list[str]:
    script = "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | ForEach-Object { $_.CommandLine }"
    result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script], capture_output=True, text=True,
                            timeout=60, creationflags=NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError('process listing failed: ' + result.stderr[:200])
    return [line for line in result.stdout.splitlines() if line.strip()]


def port_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(('127.0.0.1', port)) == 0


def start_detached(cmd, cwd, log):
    environment = dict(os.environ, PYTHONPATH=str(cwd), OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                       TEMP=str(CLAUDE / 'data' / 'tmp'), TMP=str(CLAUDE / 'data' / 'tmp'))
    with open(log, 'ab') as stream:
        return subprocess.Popen([str(part) for part in cmd], cwd=cwd, env=environment, stdin=subprocess.DEVNULL, stdout=stream,
                                stderr=subprocess.STDOUT, creationflags=NO_WINDOW)


@dataclass
class Service:
    name: str
    marker: str | None            # text in a running command line; None = judged by `port` alone
    cmd: list
    cwd: Path
    port: int | None = None


@dataclass
class Supervisor:
    state_dir: Path
    run_root: Path
    services: list = field(default_factory=list)
    list_processes: object = list_python_processes
    port_open: object = port_open
    start: object = start_detached
    pipeline_command: object = None
    child: tuple | None = None    # (floor, process) of a pipeline this instance started

    @property
    def queue_path(self) -> Path:
        return self.state_dir / 'queue.json'

    def log(self, text: str) -> None:
        with (self.state_dir / 'supervisor.log').open('a', encoding='utf-8') as stream:
            stream.write(f'{now()} {text}\n')

    def tend_services(self, processes) -> dict:
        report = {}
        for service in self.services:
            alive = self.port_open(service.port) if service.port else any(service.marker in line for line in processes)
            if not alive:
                self.start(service.cmd, service.cwd, self.state_dir / f'{service.name}.log')
                self.log(f'started service {service.name}')
            report[service.name] = 'adopted' if alive else 'started'
        return report

    def summary_status(self, floor: str):
        path = self.run_root / 'logs' / f'pipeline-{floor}-summary.json'
        return json.loads(path.read_text(encoding='utf-8')).get('status') if path.is_file() else None

    def finish(self, entry: dict, code: int | None) -> None:
        floor = entry['floor']
        status = self.summary_status(floor)
        if code is None and status not in (None, 'published'):
            code = 2              # an adopted run has no exit code; its summary says it ended on a measured failure
        if code == 0 or status == 'published':
            entry.update(state='done', note='published', finished_utc=now())
        elif code == 2:
            entry.update(state='blocked', note=f'measured failure; see logs/pipeline-{floor}-summary.json', finished_utc=now())
        else:
            entry['crashes'] = entry.get('crashes', 0) + 1
            blocked = entry['crashes'] >= MAX_CRASHES
            entry.update(state='blocked' if blocked else 'pending', note=f'run ended unexpectedly (exit {code}), crash {entry["crashes"]}')
        self.log(f'{floor}: {entry["state"]} ({entry["note"]})')

    def tend_queue(self, processes) -> None:
        queue = load_queue(self.queue_path)
        floors = queue.get('floors', [])
        active = next((e for e in floors if e.get('state') in ('running', 'adopted')), None)
        if self.child is not None:
            floor, process = self.child
            code = process.poll()
            if code is None:
                write_json(self.queue_path, queue)
                return
            self.child = None
            entry = next(e for e in floors if e['floor'] == floor)
            self.finish(entry, code)
            active = None
        pipeline = next((e for e in floors if any('run_floor_pipeline' in line and f'--floor {e["floor"]}' in line for line in processes)), None)
        if pipeline is not None:
            if pipeline.get('state') != 'adopted':
                pipeline.update(state='adopted', note='already running')
                self.log(f'{pipeline["floor"]}: adopted running pipeline')
        else:
            if active is not None:
                self.finish(active, None)
            if not (self.state_dir / 'STOP').exists():
                entry = next((e for e in floors if e.get('state', 'pending') == 'pending'), None)
                if entry is not None and self.summary_status(entry['floor']) == 'published' and entry.get('crashes', 0) == 0 and not entry.get('rerun'):
                    entry.update(state='done', note='already published')
                    entry = next((e for e in floors if e.get('state', 'pending') == 'pending'), None)
                if entry is not None:
                    process = self.start(self.pipeline_command(entry['floor']), ENGINE, self.run_root / 'logs' / f'pipeline-{entry["floor"]}.log')
                    self.child = (entry['floor'], process)
                    entry.update(state='running', started_utc=now())
                    self.log(f'{entry["floor"]}: started pipeline')
        write_json(self.queue_path, queue)

    def tick(self) -> None:
        processes = self.list_processes()
        services = self.tend_services(processes)
        self.tend_queue(processes)
        write_json(self.state_dir / 'status.json', dict(pid=os.getpid(), parent_pid=os.getppid(), heartbeat_utc=now(), services=services,
                                                        queue=load_queue(self.queue_path), stop_file=(self.state_dir / 'STOP').exists()))


def default_services() -> list:
    progress = 'data/main-infra-fresh/current-upper.json'
    public = WORKTREES / 'SIEGE-MAIN-INFRA-20261023' / 'dashboard'
    return [Service('publisher-live', 'tools.publish_upper_status_live',
                    [PYTHON, '-B', '-u', '-m', 'tools.publish_upper_status_live', '--progress', progress, '--interval', '30'], CLAUDE),
            Service('publisher-local', 'tools.publish_upper_status --',
                    [PYTHON, '-B', '-u', '-m', 'tools.publish_upper_status', '--progress', progress, '--feed', public / 'public' / 'building-repair-status.json',
                     '--feed', public / 'out' / 'building-repair-status.json', '--interval', '5'], CLAUDE),
            Service('preview-4192', None, [PYTHON, '-B', '-m', 'http.server', '4192', '--bind', '127.0.0.1'], DASHBOARD_OUT, port=4192)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--state-dir', type=Path, default=STATE_DIR)
    parser.add_argument('--once', action='store_true', help='one tick, then exit')
    args = parser.parse_args(argv)
    args.state_dir.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock(args.state_dir / 'supervisor.lock')
    if lock is None:
        return 0                  # another instance is running; the scheduler's 5-minute start lands here
    supervisor = Supervisor(state_dir=args.state_dir, run_root=RUN_ROOT, services=default_services(),
                            pipeline_command=lambda floor: [PYTHON, '-B', '-u', 'tools/run_floor_pipeline.py', '--floor', floor, '--worker', 'claude', '--max-rounds', '3'])
    supervisor.log(f'supervisor start pid {os.getpid()} parent {os.getppid()}')
    while True:
        try:
            supervisor.tick()
        except Exception as error:   # a failed tick must not end the watch; the next tick retries
            supervisor.log(f'tick failed: {error!r}')
        if args.once:
            return 0
        time.sleep(TICK_S)


if __name__ == '__main__':
    sys.exit(main())
