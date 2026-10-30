"""Run ONE fresh MAIN INFRA floor through every stage by itself, heal on the measured failures, publish the Unity-ready
file when the bar is met, and write per-stage progress for the dashboard.

Owner words (2026-10-30): "the engine should run itself healing until it finishes; in the dashboard a realtime health bar
per stage and a live percentage of completeness".

  cd <E4-MERGE worktree>; set PYTHONPATH=<E4-MERGE worktree>
  python -B -u tools/run_floor_pipeline.py --floor 7F --worker claude [--max-rounds 3] [--dry-run]
      [--exclude-sites <root>/e5/exclusions/<file>] [--root R] [--claude-worktree CL] [--progress P] [--public ...]

Pipeline for floor F (run root R = the Claude worktree's data/main-infra-fresh/run-claude-4f-7f-20261023):
  e3       the checked E3 candidate R/e3/F (already done for every floor; the stage is reported done = 100)
  e5       R/e5/F reused when its stage-audit is finished, else `run_checked_e5_floor.py --from-e3 [--exclude-sites]`
  measure  `main_infra_external_validate` (identical guard + Validator, --allow coincident_backface_removed,
           --original-oracle on 4F/5F/6F) labelled <worker>-<stage>-<triangles>; the interior gate (Blender render of the
           qualified walking-height poses into R/independent-validator/<stage>-interior/<name>/renders, total changed px over
           the pairs <= 60); the 30-view native QA render + contact sheets into R/<stage>-native-qa/<name>
  heal     max --max-rounds rounds: a guard failure stops with "diagnosis needed" (the guard receipt carries per-view counts,
           not the BEFORE faces); a textures / nothing_deleted failure with a passing guard restores the Validator's
           `sites[].faces` (original ids) into R/e5/F-restoreN with `main_infra_restore_faces` and measures again
  e4       `run_checked_e4_floor.py --from-e5 --allow-growth` from the passing E5 candidate into R/e4/F-roundN, measured the
           same way; a failing round is explained with `main_infra_e4_replay.explain_failures` and the explained regions are
           excluded from the next round; when E4 does not meet the bar the E5 candidate stays the floor's result and the e4
           stage is marked failed with the numbers
  publish  bind the guard into the stage-audit, repackage the dashboard preview (the old folder moved to
           candidate-<stage>-<triangles>), publish the evidence, stage error kinds beside the candidate preview, archive to
           repo 04 and copy to repo 03 (Model-Floor_0N), mirror to Z, upload the floor's dashboard folders live, rebuild the
           Blender library, then set the floor to `unity_ready` ("LOCAL FIXED OBJ, Unity-ready: <03 path> ...") or to
           `validating` with the same text while the dashboard's progress helper does not know `unity_ready` yet.

Finished receipts, candidates and renders are reused (matched by the candidate's engine hash); a folder that exists is never
overwritten: an unfinished measurement whose process is still alive is waited for, a dead one is moved to
<name>-aborted-<stamp>. Every subprocess logs to R/logs/pipeline-<F>-<stage>.log, runs with OPENBLAS/OMP/MKL threads = 1, and
engine / Validator steps wait for >= --min-free-gb of free RAM. Every stage transition goes through the Claude worktree's
tools/main_infra_progress.py `set_stage` (falling back to writing the `stages` / `percent_complete` fields directly when the
helper predates it). All paths are D:/... (Windows Python cannot open /d/...).
"""
from __future__ import annotations

import argparse
import ctypes
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLAUDE_WORKTREE = Path('D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023')
DEFAULT_RUN_ROOT = DEFAULT_CLAUDE_WORKTREE / 'data/main-infra-fresh/run-claude-4f-7f-20261023'
DEFAULT_PROGRESS = DEFAULT_CLAUDE_WORKTREE / 'data/main-infra-fresh/current-upper.json'
DEFAULT_SIEGE = Path('D:/PROJECTS/05-Corllenium-UC-Building-Repair-Engine/.claude/worktrees/SIEGE-MAIN-INFRA-20261023/dashboard')
DEFAULT_PUBLIC = (DEFAULT_SIEGE / 'public', DEFAULT_SIEGE / 'out')
DEFAULT_REPO04 = Path('D:/PROJECTS/04-Corllenium-Building-Model-Repair')
DEFAULT_REPO03 = Path('D:/PROJECTS/03-Corllenium-UC-Game')
DEFAULT_Z_ROOT = Path('Z:/PC-4-STORAGE/UC MODELS/UPDATED MINECRAFT MODEL/MAIN INFRUSTRUCTURE - FIXED')
DEFAULT_BLENDER = Path('C:/Program Files/Blender Foundation/Blender 5.1/blender.exe')
JOB_ID = 'MAIN-INFRA-CLAUDE-4F-7F-20261023'
REVIEWER = 'Claude Code (independent external validation)'
CBR = 'coincident_backface_removed'
FLOORS = tuple(f'{n}F' for n in range(1, 8))
ORDINAL = {'1F': '1st', '2F': '2nd', '3F': '3rd', '4F': '4th', '5F': '5th', '6F': '6th', '7F': '7th'}
RAW_NAMES = {f: f'{ORDINAL[f]} floor main infra.obj' for f in FLOORS}
ORACLE_FLOORS = {'4F', '5F', '6F'}          # 6F: the Embree guard flags one depth-noise pixel there
INTERIOR_PX_MAX = 60
STAGE_OF_MODE = {'e3_remove_only': 'e3', 'e3_then_e5_cull': 'e5', 'e3_then_e5_then_e4_merge': 'e4'}
STAGE_ORDER = ('e3', 'e5', 'e4', 'measure', 'publish')
STAGE_LABELS = {'e3': 'Hidden faces', 'e5': 'Coincident layers', 'e4': 'Coplanar merge',
                'measure': 'Guard + textures + coverage + Validator', 'publish': 'Unity-ready file'}
STEP_NAMES = ('run_e5', 'run_e4', 'restore_faces', 'measure', 'render', 'contact_sheet', 'explain_e4', 'bind_guard',
              'package_preview', 'publish_evidence', 'stage_errors', 'archive', 'mirror_z', 'upload_live', 'rebuild_library')


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def stamp():
    return time.strftime('%m%d%H%M%S')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding='utf-8')


def sha256_file(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def free_physical_gb():
    """Free physical RAM in GB (Windows); None elsewhere. Same reading as tools/main_infra_external_validate.py."""
    if os.name != 'nt':
        return None

    class Status(ctypes.Structure):
        _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong), ('ullTotalPhys', ctypes.c_ulonglong),
                    ('ullAvailPhys', ctypes.c_ulonglong), ('ullTotalPageFile', ctypes.c_ulonglong),
                    ('ullAvailPageFile', ctypes.c_ulonglong), ('ullTotalVirtual', ctypes.c_ulonglong),
                    ('ullAvailVirtual', ctypes.c_ulonglong), ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
    status = Status()
    status.dwLength = ctypes.sizeof(Status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.ullAvailPhys / 2 ** 30


def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        out = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'], capture_output=True, text=True).stdout
        return f'"{pid}"' in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------------------------------------------------
# configuration


@dataclass
class Config:
    floor: str
    root: Path = DEFAULT_RUN_ROOT
    worker: str = 'claude'
    claude_worktree: Path = DEFAULT_CLAUDE_WORKTREE
    progress: Path = DEFAULT_PROGRESS
    public: list = field(default_factory=lambda: list(DEFAULT_PUBLIC))
    repo04: Path = DEFAULT_REPO04
    repo03: Path = DEFAULT_REPO03
    z_root: Path = DEFAULT_Z_ROOT
    blender: Path = DEFAULT_BLENDER
    python: str = sys.executable
    exclude_sites: Path | None = None
    max_rounds: int = 3
    min_free_gb: float = 5.0
    max_wait_s: float = 7200.0
    interior_px_max: int = INTERIOR_PX_MAX
    job_id: str = JOB_ID
    reviewer: str = REVIEWER
    oracle: bool | None = None
    dry_run: bool = False

    def __post_init__(self):
        if self.floor not in FLOORS:
            raise ValueError(f'unknown floor {self.floor}')
        for name in ('root', 'claude_worktree', 'progress', 'repo04', 'repo03', 'z_root', 'blender'):
            setattr(self, name, Path(getattr(self, name)))
        self.public = [Path(p) for p in self.public]
        if self.exclude_sites is not None:
            self.exclude_sites = Path(self.exclude_sites)
        if self.oracle is None:
            self.oracle = self.floor in ORACLE_FLOORS

    @property
    def raw_name(self):
        return RAW_NAMES[self.floor]

    @property
    def logs(self):
        return self.root / 'logs'

    @property
    def external(self):
        return self.root / 'independent-validator' / 'external'

    @property
    def helper(self):
        return self.claude_worktree / 'tools' / 'main_infra_candidate.py'

    @property
    def e3_dir(self):
        return self.root / 'e3' / self.floor

    @property
    def baseline_engine(self):
        return self.root / 'normalized' / self.floor / 'before.engine.obj'

    @property
    def poses(self):
        return self.root / 'independent-validator' / 'e3-interior' / self.floor / 'qualified-native-poses.json'

    @property
    def game_dir(self):
        return self.repo03 / 'Assets' / 'Models' / 'Campus' / 'Repaired' / 'Main-Infrastructure' / 'Floor' / f'Model-Floor_0{self.floor[0]}'

    @property
    def stem(self):
        return f'Main_Infrustructure_{ORDINAL[self.floor]}_floor'


# --------------------------------------------------------------------------------------------------------------------
# progress (the dashboard's per-stage health bars)


class ProgressWriter:
    """Writes stage health and floor state through the Claude worktree's tools/main_infra_progress.py, loaded by path.
    `set_stage(path, floor_id, stage_id, status, percent, note=None, label=None)` is used when the helper has it; otherwise
    the `stages` / `percent_complete` fields are written directly into the floor row."""

    def __init__(self, progress_path, helper_path):
        self.path, self.helper_path = Path(progress_path), Path(helper_path)
        self.module = None
        if self.helper_path.is_file():
            spec = importlib.util.spec_from_file_location('floor_pipeline_progress_helper', self.helper_path)
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)

    def supports_state(self, state):
        states = getattr(self.module, 'STATES', None)
        return state in states if states is not None else state == 'validating'

    def _load(self):
        return read_json(self.path)

    def _save(self, doc):
        directory = self.path.parent
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=directory, prefix=self.path.name + '.', suffix='.tmp', delete=False) as stream:
            json.dump(doc, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
            temporary = stream.name
        os.replace(temporary, self.path)

    def floor(self, floor):
        if self.module is not None and hasattr(self.module, 'load_progress'):
            return self.module.load_progress(self.path)['floors'][floor]
        return self._load()['floors'][floor]

    def set_stage(self, floor, stage_id, status, percent, note=None):
        if self.module is not None and hasattr(self.module, 'set_stage'):
            self.module.set_stage(self.path, floor, stage_id, status, percent, note=note, label=None)
            return
        doc = self._load()
        row = doc['floors'][floor]
        stages = list(row.get('stages') or [])
        existing = next((s for s in stages if s['id'] == stage_id), None)
        if existing is None:
            stages.append({'id': stage_id, 'label': STAGE_LABELS.get(stage_id, stage_id), 'status': status, 'percent': percent, 'note': note})
        else:
            existing.update(status=status, percent=percent, note=note)
        order = {s: i for i, s in enumerate(STAGE_ORDER)}
        stages.sort(key=lambda s: order.get(s['id'], len(STAGE_ORDER)))
        counted = [100 if s['status'] == 'done' else s['percent'] for s in stages if s['status'] != 'skipped']
        row['stages'] = stages
        row['percent_complete'] = round(sum(counted) / len(counted), 1) if counted else 0
        now = utc_now()
        row['last_work_event_at'] = doc['updated_at'] = doc['last_work_event_at'] = doc['heartbeat_at'] = now
        self._save(doc)

    def set_floor(self, floor, state, step, *, blocker=None, **measured):
        if self.module is None or not hasattr(self.module, 'update_floor'):
            raise RuntimeError(f'{self.helper_path} has no update_floor; the floor state cannot be set')
        self.module.update_floor(self.path, floor, state, step, blocker=blocker, **measured)


# --------------------------------------------------------------------------------------------------------------------
# subprocess runner and the default (real) steps


class Runner:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def env(self, pythonpath):
        env = dict(os.environ)
        env.update(PYTHONPATH=str(pythonpath), OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        tmp = self.cfg.claude_worktree / 'data' / 'tmp'
        if tmp.is_dir():
            env.update(TEMP=str(tmp), TMP=str(tmp))
        return env

    def run(self, argv, *, stage, cwd, pythonpath=None, timeout=None):
        argv = [str(a) for a in argv]
        self.cfg.logs.mkdir(parents=True, exist_ok=True)
        log = self.cfg.logs / f'pipeline-{self.cfg.floor}-{stage}.log'
        with log.open('a', encoding='utf-8') as stream:
            stream.write(f'\n=== {utc_now()} cwd={cwd}\n{subprocess.list2cmdline(argv)}\n')
            stream.flush()
            started = time.perf_counter()
            result = subprocess.run(argv, cwd=str(cwd), env=self.env(pythonpath or cwd), stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
            stream.write(f'=== exit {result.returncode} after {time.perf_counter() - started:.1f}s\n')
        return result.returncode


class Commands:
    """The exact command lines, shared by the real steps and --dry-run."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.py = [cfg.python, '-B', '-u']
        self.cl = cfg.claude_worktree

    def e5(self, out, exclude=None):
        argv = self.py + [ENGINE_ROOT / 'tools' / 'run_checked_e5_floor.py', '--root', self.cfg.root, '--floor', self.cfg.floor,
                          '--raw-name', self.cfg.raw_name, '--from-e3', '--out', out]
        if exclude is not None:
            argv += ['--exclude-sites', exclude]
        return argv

    def e4(self, e5_candidate, out, exclude=None):
        argv = self.py + [ENGINE_ROOT / 'tools' / 'run_checked_e4_floor.py', '--root', self.cfg.root, '--floor', self.cfg.floor,
                          '--raw-name', self.cfg.raw_name, '--from-e5', '--e5-candidate', e5_candidate, '--out', out, '--allow-growth']
        if exclude is not None:
            argv += ['--exclude-regions', exclude]
        return argv

    def restore(self, e5, faces, reason, out):
        return self.py + ['-m', 'tools.main_infra_restore_faces', '--root', self.cfg.root, '--floor', self.cfg.floor, '--e5', e5,
                          '--faces', ','.join(str(f) for f in faces), '--reason', reason, '--out', out]

    def measure(self, candidate, out, label, snapshot, oracle):
        argv = self.py + ['-m', 'tools.main_infra_external_validate', '--root', self.cfg.root, '--floor', self.cfg.floor,
                          '--raw-name', self.cfg.raw_name, '--snapshot', snapshot, '--candidate', candidate, '--out', out,
                          '--helper', self.cfg.helper, '--label', label, '--worker', self.cfg.worker, '--job-id', self.cfg.job_id,
                          '--reviewer', self.cfg.reviewer, '--allow', CBR, '--min-free-gb', self.cfg.min_free_gb]
        if oracle:
            argv.append('--original-oracle')
        return argv

    def render(self, before, after, out, poses=None):
        argv = [self.cfg.blender, '--background', '--factory-startup', '--python-exit-code', '13', '--python',
                self.cl / 'tools' / 'blender' / 'main_infra_render_pair.py', '--', '--before', before, '--after', after, '--out', out,
                '--before-frame', 'engine-inches', '--after-frame', 'engine-inches', '--size', '512']
        argv += ['--poses', poses] if poses is not None else ['--views', 'all']
        return argv

    def contact_sheet(self, out):
        return self.py + [self.cl / 'tools' / 'main_infra_contact_sheet.py', out]

    def preview(self, candidate, public, revision, run_id, with_progress):
        argv = self.py + [self.cl / 'tools' / 'main_infra_preview_stage2.py', '--baseline', self.cfg.root / 'normalized' / self.cfg.floor,
                          '--qualification', self.cfg.root / 'independent-validator' / 'import-audit' / f'qualification-{self.cfg.floor}.json',
                          '--public', public, '--revision', revision, '--run-id', run_id, '--floor', self.cfg.floor,
                          '--kind', 'candidate', '--candidate', candidate]
        if with_progress:
            argv += ['--progress', self.cfg.progress]
        return argv

    def evidence(self, candidate, validation, guard, interior, native_qa):
        argv = self.py + [self.cl / 'tools' / 'publish_upper_evidence.py', '--root', self.cfg.root, '--floor', self.cfg.floor,
                          '--candidate', candidate, '--validation', validation, '--guard-receipt', guard, '--interior', interior,
                          '--native-qa', native_qa, '--progress', self.cfg.progress]
        for public in self.cfg.public:
            argv += ['--public', public]
        return argv

    def stage_errors(self, e5, e4, before_out, after_out):
        argv = self.py + ['-m', 'tools.main_infra_stage_errors', '--e5', e5]
        if e4 is not None:
            argv += ['--e4', e4]
        return argv + ['--with-census', '--before-out', before_out, '--after-out', after_out]

    def archive(self, candidate, validation_dir, guard, interior, cleanup_mode, run_id):
        return self.py + [self.cl / 'tools' / 'archive_upper_floor.py', '--root', self.cfg.root, '--floor', self.cfg.floor,
                          '--candidate', candidate, '--validation-dir', validation_dir, '--repo04', self.cfg.repo04, '--repo03', self.cfg.repo03,
                          '--job-id', self.cfg.job_id, '--run-id', run_id, '--guard-receipt', guard, '--interior-gate', interior,
                          '--cleanup-mode', cleanup_mode]

    def library(self):
        export = self.cfg.repo04 / 'Exports' / 'Repaired-Buildings-20261023-fresh'
        output = self.cfg.repo04 / '02_STAGING_DEVELOPMENT' / 'BUILDINGS_AND_ENVIRONMENT' / 'libraries' / 'INFRA-FRESH-20261023.blend'
        return [self.cfg.blender, '--background', '--factory-startup', '--python-exit-code', '13', '--python',
                self.cl / 'tools' / 'blender' / 'main_infra_fresh_library.py', '--', '--export', export, '--output', output,
                '--floors', '7F,6F,5F,4F']


class DefaultSteps:
    """The real steps: subprocesses through Runner (engine tools from this worktree, publishing tools from the Claude worktree)
    and a few in-process file operations. Each is replaced by a fake in tests via `run_floor(steps={...})`."""

    def __init__(self, cfg: Config, runner: Runner):
        self.cfg, self.runner, self.cmd = cfg, runner, Commands(cfg)

    def run_e5(self, *, out, exclude, **_):
        return self.runner.run(self.cmd.e5(out, exclude), stage='e5', cwd=ENGINE_ROOT)

    def run_e4(self, *, e5_candidate, out, exclude, **_):
        return self.runner.run(self.cmd.e4(e5_candidate, out, exclude), stage='e4', cwd=ENGINE_ROOT)

    def restore_faces(self, *, e5, faces, reason, out, **_):
        return self.runner.run(self.cmd.restore(e5, faces, reason, out), stage='e5', cwd=ENGINE_ROOT)

    def measure(self, *, candidate, out, label, oracle, stage, **_):
        snapshot = read_json(self.cfg.e3_dir / 'stage-audit.json')['before_snapshot']
        return self.runner.run(self.cmd.measure(candidate, out, label, snapshot, oracle), stage=f'{stage}-measure', cwd=ENGINE_ROOT)

    def render(self, *, before, after, out, poses, stage, **_):
        return self.runner.run(self.cmd.render(before, after, out, poses), stage=f'{stage}-render', cwd=self.cfg.claude_worktree)

    def contact_sheet(self, *, out, stage, **_):
        return self.runner.run(self.cmd.contact_sheet(out), stage=f'{stage}-render', cwd=self.cfg.claude_worktree)

    def explain_e4(self, *, candidate, validation, **_):
        from tools.main_infra_e4_replay import explain_failures
        return explain_failures(candidate=Path(candidate), validation=Path(validation))

    def bind_guard(self, *, candidate, measurement, **_):
        return bind_guard_receipt(Path(candidate), measurement)

    def package_preview(self, *, candidate, public, revision, run_id, with_progress, **_):
        return self.runner.run(self.cmd.preview(candidate, public, revision, run_id, with_progress), stage='publish', cwd=self.cfg.claude_worktree)

    def publish_evidence(self, *, candidate, validation, guard, interior, native_qa, **_):
        return self.runner.run(self.cmd.evidence(candidate, validation, guard, interior, native_qa), stage='publish', cwd=self.cfg.claude_worktree)

    def stage_errors(self, *, e5, e4, before_out, after_out, **_):
        return self.runner.run(self.cmd.stage_errors(e5, e4, before_out, after_out), stage='publish', cwd=ENGINE_ROOT)

    def archive(self, *, candidate, validation_dir, guard, interior, cleanup_mode, run_id, **_):
        return self.runner.run(self.cmd.archive(candidate, validation_dir, guard, interior, cleanup_mode, run_id), stage='publish',
                               cwd=self.cfg.claude_worktree)

    def mirror_z(self, *, candidate, measurement, interior, native_qa, stage, triangles, readme, **_):
        return mirror_to_z(self.cfg, Path(candidate), measurement, Path(interior), Path(native_qa), stage, triangles, readme)

    def upload_live(self, *, public, revision, run_id, names, **_):
        return upload_floor_dirs(self.cfg, Path(public), revision, run_id, names)

    def rebuild_library(self, **_):
        return self.runner.run(self.cmd.library(), stage='publish', cwd=self.cfg.claude_worktree)


def bind_guard_receipt(candidate: Path, m: dict) -> int:
    """Bind the passing external guard (guard.json) and the external Validator pointer into the candidate's stage-audit.json,
    as scratchpad/bind_e5_guard2.py did for 7F / 6F; the previous audit is kept as stage-audit.pre-guard-bind-<stamp>.json."""
    audit_path = candidate / 'stage-audit.json'
    audit = read_json(audit_path)
    guard_path, receipt = Path(m['guard_path']), read_json(m['receipt'])
    guard_doc = read_json(guard_path)
    if guard_doc.get('passed') is not True:
        raise ValueError('guard did not pass; nothing is bound')
    engine_sha = sha256_file(candidate / 'candidate.engine.obj')
    if not (receipt['candidate_engine_sha256'] == audit['engine_candidate_sha256'] == engine_sha):
        raise ValueError('guard receipt is for another candidate')
    if audit.get('independent_guard_receipt', {}) and audit['independent_guard_receipt'].get('sha256') == sha256_file(guard_path):
        return 0                                                     # already bound to this receipt
    shutil.copyfile(audit_path, audit_path.with_name(f'stage-audit.pre-guard-bind-{stamp()}.json'))
    checks = receipt['validator']['checks']
    audit['guard'] = dict(guard_doc['report'], passed=True, state='independent_pass', caster=guard_doc.get('caster'),
                          depth_tol_inches=guard_doc.get('depth_tol_inches'))
    audit['independent_guard_receipt'] = dict(path=str(guard_path), sha256=sha256_file(guard_path), reviewer=receipt.get('reviewer'),
                                              finished_utc=guard_doc.get('finished_utc'),
                                              tool='tools/main_infra_external_validate.py (run by tools/run_floor_pipeline.py)')
    audit['independent_validation'] = dict(path=str(m['validation']), verdict=receipt['validator'].get('verdict'),
                                           textures=checks['textures']['status'], nothing_deleted=checks['nothing_deleted']['status'],
                                           problems=checks['problems'].get('status'),
                                           allowed_changes=receipt['validator'].get('allowed_changes_active'),
                                           external_guard=dict(passed=receipt['guard']['passed'], caster=receipt['guard'].get('caster'),
                                                               totals=receipt['guard'].get('totals')))
    write_json(audit_path, audit)
    return 0


def mirror_to_z(cfg: Config, candidate: Path, m: dict, interior: Path, native_qa: Path, stage: str, triangles: int, readme: str) -> int:
    """Z:\\...\\MAIN INFRUSTRUCTURE - FIXED\\<F>\\<STAGE>-candidate-<triangles>\\: the repo 03 copy (fixed.obj, MTL, textures) plus the
    engine-frame OBJ, the evidence and a README with the measured numbers. An existing folder is never overwritten."""
    if not cfg.z_root.is_dir():
        raise FileNotFoundError(f'Z mirror root unavailable: {cfg.z_root}')
    dest = cfg.z_root / cfg.floor / f'{stage.upper()}-candidate-{triangles}'
    if dest.exists():
        dest = dest.with_name(dest.name + '-' + stamp())
    staging = dest.with_name('.' + dest.name + '-incoming')
    staging.mkdir(parents=True)
    game = cfg.game_dir
    for name in os.listdir(game):
        src = game / name
        if src.is_dir():
            shutil.copytree(src, staging / name)
        elif name != 'RECEIPT.json':
            shutil.copyfile(src, staging / name)
    shutil.copyfile(candidate / 'candidate.engine.obj', staging / f'{cfg.stem}.fixed.engine.obj')
    evidence = staging / 'evidence'
    evidence.mkdir()
    for src, name in [(m['validation'], 'validation.json'), (m['guard_path'], 'guard.json'), (m['receipt'], 'external-validation.json'),
                      (candidate / 'stage-audit.json', 'stage-audit.json'), (candidate / 'edit-log.jsonl', 'edit-log.jsonl'),
                      (interior / 'renders' / 'comparison.json', 'interior-gate-comparison.json'),
                      (native_qa / 'paired-detail.png', 'paired-detail.png'), (native_qa / 'all-views.png', 'all-views.png')]:
        if Path(src).exists():
            shutil.copyfile(src, evidence / name)
    (staging / 'README.txt').write_text(readme, encoding='utf-8')
    os.rename(staging, dest)
    return 0


def upload_floor_dirs(cfg: Config, public: Path, revision: str, run_id: str, names: list) -> int:
    """Upload named dashboard subfolders of the floor to both live web roots (scratchpad upload_floor_dirs.py, in-process)."""
    live_path = cfg.claude_worktree / 'tools' / 'publish_upper_status_live.py'
    spec = importlib.util.spec_from_file_location('floor_pipeline_live', live_path)
    live = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(live)
    buffer = io.BytesIO()
    floor_dir = f'models/main-infra/{revision}/{cfg.floor}/{run_id}'
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for name in names:
            rel = Path(floor_dir) / name
            src = public / rel
            if os.name == 'nt':
                src = Path('\\\\?\\' + str(src.resolve()))
            if not src.exists():
                raise FileNotFoundError(f'missing {rel}')
            tar.add(str(src), arcname=rel.as_posix())
    app_public, web_root = os.path.dirname(live.REMOTE[0]), os.path.dirname(live.REMOTE[1])
    remote = (f"set -e; tar -xzf - -C {app_public}; mkdir -p {web_root}/{floor_dir}; "
              + '; '.join(f"rm -rf {web_root}/{floor_dir}/{n}; cp -r {app_public}/{floor_dir}/{n} {web_root}/{floor_dir}/{n}" for n in names)
              + f"; ls {web_root}/{floor_dir}")
    key = str(Path.home() / '.ssh' / 'corllenium_siege_ed25519')
    known = 'D:/PROJECTS/02-Corllenium-Siege/deploy/known_hosts'
    subprocess.run(live.ssh_args(key, known) + [remote], input=buffer.getvalue(), check=True, timeout=900)
    return 0


# --------------------------------------------------------------------------------------------------------------------
# the pipeline


class StageFailed(Exception):
    def __init__(self, stage, note):
        super().__init__(f'{stage}: {note}')
        self.stage, self.note = stage, note


def candidate_audit(candidate: Path) -> dict:
    return read_json(Path(candidate) / 'stage-audit.json')


def finished_receipt(path: Path) -> dict | None:
    """The receipt at <path>/external-validation.json when the measurement finished (Validator written)."""
    receipt = Path(path) / 'external-validation.json'
    if not receipt.is_file():
        return None
    try:
        doc = read_json(receipt)
    except (OSError, ValueError):
        return None
    return doc if doc.get('finished_utc') and isinstance(doc.get('validator'), dict) else None


def is_oracle(receipt: dict) -> bool:
    caster = str((receipt.get('guard') or {}).get('caster') or '')
    return 'BoundedBrute' in caster or 'oracle' in caster.lower()


def receipt_rank(receipt: dict):
    """Best first: guard passed, textures + nothing_deleted PASS, float64 oracle caster, newest."""
    checks = receipt['validator'].get('checks') or {}
    both = checks.get('textures', {}).get('status') == 'PASS' and checks.get('nothing_deleted', {}).get('status') == 'PASS'
    return (bool(receipt['guard'].get('passed')), both, is_oracle(receipt), str(receipt.get('finished_utc') or ''))


def measurement_summary(out: Path, candidate: Path, *, reused: bool) -> dict:
    receipt = finished_receipt(out)
    if receipt is None:
        raise StageFailed('measure', f'{out} holds no finished receipt')
    checks = receipt['validator']['checks']
    guard = receipt['guard']
    totals = guard.get('totals') or {}
    guard_px = sum(int(totals.get(k, 0) or 0) for k in ('holes', 'material_changed', 'moved_same_flat', 'moved_other'))
    validation = Path(receipt['validator'].get('path') or (out / 'validation' / 'validation.json'))
    if not validation.is_file():
        validation = out / 'validation' / 'validation.json'
    nd = checks['nothing_deleted']
    return dict(out=str(out), label=receipt.get('label'), receipt=str(out / 'external-validation.json'), guard_path=str(out / 'guard.json'),
                validation=str(validation), candidate=str(candidate), engine_sha=receipt['candidate_engine_sha256'], reused=reused,
                guard_passed=bool(guard.get('passed')), guard_px=guard_px, guard_totals=totals, caster=guard.get('caster'), oracle=is_oracle(receipt),
                textures=checks['textures']['status'], textures_failed=checks['textures'].get('samples_failed'),
                nothing_deleted=nd['status'], deleted=nd.get('deleted'), faces_unmet=nd.get('faces_unmet'), area_lost_in2=nd.get('area_lost_in2'),
                failed_by=nd.get('failed_by'),
                problems=checks.get('problems', {}).get('status'), verdict_validator=receipt['validator'].get('verdict'),
                kinds={k: dict(before=v.get('before'), after=v.get('after')) for k, v in (checks.get('problems', {}).get('kinds') or {}).items()
                       if isinstance(v, dict)})


class FloorPipeline:
    def __init__(self, cfg: Config, steps, progress, *, free_gb=free_physical_gb, sleep=time.sleep):
        self.cfg, self.steps, self.progress = cfg, steps, progress
        self.free_gb, self.sleep = free_gb, sleep
        self.notes = {s: [] for s in STAGE_ORDER}
        self.summary = dict(schema_version=1, floor=cfg.floor, worker=cfg.worker, root=str(cfg.root), started_utc=utc_now(), status='running',
                            e5_candidate=None, e4_candidate=None, final_candidate=None, final_stage=None, measurements=dict(e5=[], e4=[]),
                            stages={}, publish={})

    # ---- progress helpers
    def stage(self, stage_id, status, percent, note=None):
        text = note if note is not None else ' | '.join(self.notes[stage_id]) or None
        self.summary['stages'][stage_id] = dict(status=status, percent=percent, note=text)
        self.progress.set_stage(self.cfg.floor, stage_id, status, percent, note=text)

    def note(self, stage_id, text):
        self.notes[stage_id].append(text)

    def wait_ram(self, label):
        started = time.monotonic()
        while True:
            free = self.free_gb()
            if free is None or free >= self.cfg.min_free_gb:
                return free
            if time.monotonic() - started > self.cfg.max_wait_s:
                raise StageFailed('measure', f'{label}: free RAM {free:.1f} GB below the {self.cfg.min_free_gb} GB gate for {self.cfg.max_wait_s:.0f}s')
            self.sleep(30)

    # ---- stages
    def run(self) -> dict:
        cfg = self.cfg
        try:
            self.stage_e3()
            e5 = self.stage_e5()
            e4 = self.stage_e4(e5)
            final, final_stage = (e4, 'e4') if e4 is not None else (e5, 'e5')
            self.summary.update(final_candidate=str(final), final_stage=final_stage)
            self.stage_publish(final, final_stage)
            self.summary['status'] = 'published'
        except StageFailed as failure:
            self.note(failure.stage, failure.note)
            self.stage(failure.stage, 'failed', self.summary['stages'].get(failure.stage, {}).get('percent', 0))
            if failure.stage != 'measure':
                self.stage('measure', 'failed', self.summary['stages'].get('measure', {}).get('percent', 0),
                           note=f'{failure.stage}: {failure.note}')
            if 'publish' not in self.summary['stages']:
                self.stage('publish', 'pending', 0, note='waiting for a candidate that meets the bar')
            self.summary['status'] = f'{failure.stage}_failed'
            self.set_blocked(failure)
        self.summary['finished_utc'] = utc_now()
        cfg.logs.mkdir(parents=True, exist_ok=True)
        write_json(cfg.logs / f'pipeline-{cfg.floor}-summary.json', self.summary)
        return self.summary

    def stage_e3(self):
        audit_path = self.cfg.e3_dir / 'stage-audit.json'
        if not audit_path.is_file():
            raise StageFailed('e3', f'no checked E3 candidate at {self.cfg.e3_dir}')
        audit = read_json(audit_path)
        self.note('e3', f'checked E3 candidate {audit.get("output_triangles")} triangles (reused)')
        self.stage('e3', 'done', 100)

    def stage_e5(self) -> Path:
        cfg = self.cfg
        candidate = cfg.root / 'e5' / cfg.floor
        self.stage('e5', 'running', 10, note='starting')
        if (candidate / 'stage-audit.json').is_file():
            self.note('e5', f'reused {candidate.name}: {candidate_audit(candidate)["output_triangles"]} triangles')
        elif candidate.exists():
            raise StageFailed('e5', f'{candidate} exists without a finished stage-audit; move it aside or wait for its process')
        else:
            self.wait_ram('E5')
            if cfg.exclude_sites is not None:
                self.note('e5', f'exclusions {cfg.exclude_sites.name}')
            code = self.steps['run_e5'](root=cfg.root, floor=cfg.floor, raw_name=cfg.raw_name, exclude=cfg.exclude_sites, out=candidate, stage='e5')
            if code != 0 or not (candidate / 'stage-audit.json').is_file():
                raise StageFailed('e5', f'run_checked_e5_floor exit {code}; see logs/pipeline-{cfg.floor}-e5.log')
            audit = candidate_audit(candidate)
            self.note('e5', f'E5 {audit.get("input_triangles")} -> {audit.get("output_triangles")} triangles '
                            f'({audit.get("kept_edits")} kept, {audit.get("rolled_back_edits")} rolled back)')
        self.stage('e5', 'running', 60)
        passing = self.heal_loop('e5', candidate)
        self.summary['e5_candidate'] = str(passing)
        self.stage('e5', 'done', 100)
        return passing

    def heal_loop(self, stage: str, candidate: Path) -> Path:
        """Measure `candidate`; while it misses the bar and a heal exists, build the next candidate and measure it."""
        cfg = self.cfg
        excluded_regions: set[int] = set()
        for round_no in range(1, cfg.max_rounds + 1):
            m, interior_px, native_px = self.measure_candidate(stage, candidate)
            self.summary['measurements'][stage].append(dict(m, round=round_no, interior_px=interior_px, native_px=native_px))
            audit = candidate_audit(candidate)
            tag = f'round {round_no}: {m["label"]}'
            if stage == 'e4' and (excluded_regions or audit.get('excluded_regions')):
                tag += f' excluded regions {sorted(excluded_regions or set(audit["excluded_regions"]))}'
            line = (f'{tag} guard {"PASS" if m["guard_passed"] else "FAIL"} {m["guard_px"]} px; textures {m["textures"]}'
                    + (f' ({m["textures_failed"]} samples)' if m['textures'] != 'PASS' else '')
                    + f'; coverage {m["nothing_deleted"]}' + (f' ({m["deleted"]} deleted)' if m['nothing_deleted'] != 'PASS' else '')
                    + f'; interior {interior_px} px' + (f' over {cfg.interior_px_max}' if interior_px > cfg.interior_px_max else '')
                    + f'; native QA {native_px} px'
                    + (f' (reused receipt {m["label"]}, {"float64 oracle" if m["oracle"] else "Embree"})' if m['reused'] else ''))
            self.note(stage, line)
            bar = m['guard_passed'] and m['textures'] == 'PASS' and m['nothing_deleted'] == 'PASS' and interior_px <= cfg.interior_px_max
            if bar:
                self.summary['measurements'][stage][-1]['verdict'] = 'pass'
                kinds = ', '.join(f'{k} {v["before"]} to {v["after"]}' for k, v in m['kinds'].items() if v.get('after') is not None)
                self.note(stage, f'bar met by {candidate.name} ({audit["output_triangles"]} triangles); signed targets {m["problems"]}: {kinds}')
                self.stage(stage, 'running', 95)
                self.stage('measure', 'done', 100, note=f'{stage}: {line}')
                return candidate
            if not m['guard_passed']:
                self.summary['measurements'][stage][-1]['verdict'] = 'guard_failed'
                raise StageFailed(stage, f'guard FAIL {m["guard_px"]} px on {candidate.name}: the guard receipt names views, not BEFORE faces; '
                                         f'diagnosis needed (read-only re-render of the failing views) before any heal')
            if interior_px > cfg.interior_px_max and m['textures'] == 'PASS' and m['nothing_deleted'] == 'PASS':
                self.summary['measurements'][stage][-1]['verdict'] = 'interior_failed'
                raise StageFailed(stage, f'interior gate {interior_px} px over {cfg.interior_px_max} on {candidate.name}; no heal maps a '
                                         f'walking-height pose back to faces; diagnosis needed')
            self.summary['measurements'][stage][-1]['verdict'] = 'heal'
            if round_no == cfg.max_rounds:
                raise StageFailed(stage, f'rounds exhausted ({cfg.max_rounds}); last candidate {candidate.name} still fails the bar')
            self.stage(stage, 'running', 80)
            if stage == 'e5':
                candidate = self.heal_e5(candidate, m, round_no)
            else:
                candidate = self.heal_e4(candidate, m, round_no, excluded_regions)
        raise StageFailed(stage, 'rounds exhausted')

    def heal_e5(self, candidate: Path, m: dict, round_no: int) -> Path:
        cfg = self.cfg
        validation = read_json(m['validation'])
        faces = sorted({int(f) for site in validation.get('sites', []) for f in site.get('faces', [])})
        if m['textures'] == 'PASS' and m['nothing_deleted'] != 'PASS' and not m.get('faces_unmet') and not m.get('area_lost_in2'):
            raise StageFailed('e5', f'{m["label"]}: coverage FAIL by the floor pixel measure (failed_by {json.dumps(m.get("failed_by"))}; '
                                    f'faces_unmet 0, area_lost_in2 0): not healable by a face restore; diagnosis needed')
        if not faces:
            raise StageFailed('e5', f'{m["label"]} fails textures/coverage but validation.json names no site faces; diagnosis needed')
        n = 1
        while (cfg.root / 'e5' / f'{cfg.floor}-restore{n}').exists():
            existing = cfg.root / 'e5' / f'{cfg.floor}-restore{n}'
            if (existing / 'stage-audit.json').is_file():          # the same restore was already built (e.g. 4F-restore1): reuse it
                audit = candidate_audit(existing)
                source = Path((audit.get('restored_from') or {}).get('candidate', ''))
                restored = set(int(f) for f in (audit.get('restored_faces') or {}).get('faces_original', []))
                if str(source) and source.resolve() == candidate.resolve() and restored == set(faces):
                    self.note('e5', f'round {round_no + 1}: reused {existing.name} ({audit["output_triangles"]} triangles, the same '
                                    f'{len(faces)} faces restored)')
                    return existing
            n += 1
        out = cfg.root / 'e5' / f'{cfg.floor}-restore{n}'
        reason = f'Validator sites of {m["label"]} (round {round_no}): textures {m["textures"]}, nothing_deleted {m["nothing_deleted"]}'
        code = self.steps['restore_faces'](root=cfg.root, floor=cfg.floor, e5=candidate, faces=faces, reason=reason, out=out, stage='e5')
        if code != 0 or not (out / 'stage-audit.json').is_file():
            raise StageFailed('e5', f'main_infra_restore_faces exit {code} for faces {faces[:12]}; see logs/pipeline-{cfg.floor}-e5.log')
        self.note('e5', f'round {round_no + 1}: restored {len(faces)} faces into {out.name} ({candidate_audit(out)["output_triangles"]} triangles)')
        return out

    def heal_e4(self, candidate: Path, m: dict, round_no: int, excluded: set) -> Path:
        cfg = self.cfg
        validation = read_json(m['validation'])
        if 'e4_region_source_faces' not in (validation.get('physical_precision') or {}):
            row = self.summary['measurements']['e4'][-1]
            raise StageFailed('e4', f'{m["label"]} on {candidate.name}: guard {"PASS" if m["guard_passed"] else "FAIL"} {m["guard_px"]} px '
                                    f'(totals {json.dumps({k: v for k, v in (m.get("guard_totals") or {}).items() if v})}); '
                                    f'textures {m["textures"]} ({m["textures_failed"]} samples); coverage {m["nothing_deleted"]} ({m["deleted"]} deleted, '
                                    f'faces_unmet {m.get("faces_unmet")}, area_lost_in2 {m.get("area_lost_in2")}, failed_by {json.dumps(m.get("failed_by"))}); '
                                    f'interior {row["interior_px"]} px. E4 heal needs the E4-bound Validator receipt (tools/run_e4_replay_loop.py); '
                                    f'kept the E5 result')
        explained = self.steps['explain_e4'](candidate=candidate, validation=Path(m['validation']))
        write_json(cfg.root / 'e4' / f'{candidate.name}-explained.json', explained)
        if explained.get('unexplained'):
            raise StageFailed('e4', f'{len(explained["unexplained"])} failing faces unexplained by any merge region of {candidate.name}')
        new = set(int(r) for r in explained.get('e4_regions', [])) - excluded
        if explained.get('e5_sites'):
            raise StageFailed('e4', f'failures of {candidate.name} trace to E5 sites {sorted(explained["e5_sites"])[:8]}, not to merges; '
                                    f'the E5 candidate stays the floor result')
        if not new:
            raise StageFailed('e4', f'no new merge region explains the failures of {candidate.name}')
        excluded |= new
        e5_candidate = Path(candidate_audit(candidate)['e5_candidate']['candidate'])
        next_dir = self.next_e4_dir(e5_candidate, excluded)
        exclude = cfg.root / 'e4' / f'{next_dir.name}-exclude.json'
        if not next_dir.exists():
            write_json(exclude, dict(regions=sorted(excluded), reasons=explained.get('reasons', {}).get('e4_regions', {}), round=round_no + 1))
            self.note('e4', f'round {round_no + 1}: rerun without regions {sorted(new)}')
            return self.run_e4(e5_candidate, next_dir, exclude)
        self.note('e4', f'round {round_no + 1}: reused {next_dir.name}')
        return next_dir

    def measure_candidate(self, stage: str, candidate: Path):
        cfg = self.cfg
        audit = candidate_audit(candidate)
        engine_sha, triangles = audit['engine_candidate_sha256'], audit['output_triangles']
        self.stage('measure', 'running', 10, note=f'{stage}: measuring {candidate.name} ({triangles} triangles)')
        existing = self.find_receipt(engine_sha, stage)
        if existing is not None:
            m = measurement_summary(existing, candidate, reused=True)
        else:
            suffix = '' if candidate.name == cfg.floor else '-' + candidate.name.split('-', 1)[1]
            label = f'{cfg.worker}-{stage}{suffix}-{triangles}'          # claude-e5-19345, claude-e5-restore1-19348, claude-e4-round1-19641
            if finished_receipt(cfg.external / label) is not None:     # that label already holds a finished receipt (another caster): keep it
                label += '-oracle' if cfg.oracle else '-embree'
                while finished_receipt(cfg.external / label) is not None:
                    label += '-' + stamp()
            out = cfg.external / label
            self.wait_in_progress(engine_sha)                        # another process measuring this candidate finishes first
            self.make_room(out, engine_sha)
            existing = self.find_receipt(engine_sha)               # the waited-for process may have finished it
            if existing is not None:
                m = measurement_summary(existing, candidate, reused=True)
            else:
                self.wait_ram(label)
                code = self.steps['measure'](root=cfg.root, floor=cfg.floor, raw_name=cfg.raw_name, candidate=candidate, out=out, label=label,
                                             oracle=cfg.oracle, stage=stage)
                if finished_receipt(out) is None:
                    raise StageFailed('measure', f'main_infra_external_validate exit {code} without a finished receipt at {out}')
                m = measurement_summary(out, candidate, reused=False)
        self.stage('measure', 'running', 80, note=f'{stage}: guard and Validator done for {candidate.name}')
        self.stage(stage, 'running', 80)
        interior_px = self.interior_gate(stage, candidate, engine_sha)
        native_px = self.native_qa(stage, candidate, engine_sha)
        self.stage('measure', 'running', 100,
                   note=f'{stage}: {candidate.name} guard {"PASS" if m["guard_passed"] else "FAIL"} {m["guard_px"]} px; textures {m["textures"]}; '
                        f'coverage {m["nothing_deleted"]}; interior {interior_px} px; native QA {native_px} px')
        return m, interior_px, native_px

    def find_receipt(self, engine_sha: str, stage: str | None = None) -> Path | None:
        """The best finished receipt for the candidate hash (guard passed, textures + coverage PASS, oracle, newest). On a floor where
        the oracle is the default an Embree guard failure is never the answer: with no oracle receipt the candidate is measured again."""
        if not self.cfg.external.is_dir():
            return None
        rows = []
        for folder in sorted(self.cfg.external.iterdir()):
            receipt = finished_receipt(folder)
            if receipt is not None and receipt.get('candidate_engine_sha256') == engine_sha:
                rows.append((receipt_rank(receipt), folder, receipt))
        if not rows:
            return None
        rows.sort(key=lambda row: row[0], reverse=True)
        rank, folder, receipt = rows[0]
        if self.cfg.oracle and not receipt['guard'].get('passed') and not is_oracle(receipt):
            if stage:
                self.note(stage, f'{folder.name}: Embree guard FAIL {receipt["guard"].get("totals", {}).get("moved_other", "?")} px and no oracle '
                                 f'receipt; measuring again with the float64 oracle')
            return None
        if stage and len(rows) > 1:
            self.note(stage, f'chose receipt {folder.name} of {len(rows)} for this candidate ({", ".join(r[1].name for r in rows[1:])} ranked lower)')
        return folder

    @staticmethod
    def writer_pid(folder: Path):
        progress = folder / 'guard-progress.json'
        if not progress.is_file():
            return None
        try:
            pid = read_json(progress).get('pid')
        except (OSError, ValueError):
            return None
        return pid if isinstance(pid, int) else None

    def wait_folder(self, folder: Path):
        """Wait while the process named by <folder>/guard-progress.json is alive and the receipt is unfinished."""
        pid = self.writer_pid(folder)
        waited = 0.0
        while pid is not None and finished_receipt(folder) is None and pid_alive(pid):
            if waited > self.cfg.max_wait_s:
                raise StageFailed('measure', f'{folder} is still being written by pid {pid} after {waited:.0f}s')
            self.sleep(60)
            waited += 60
        if waited:
            self.note('measure', f'waited {waited:.0f}s for pid {pid} writing {folder.name}')

    def wait_in_progress(self, engine_sha: str):
        """An unfinished measurement of this very candidate under any label (e.g. the queue's claude-e4-round1-7F) is waited for,
        never duplicated; a dead one under another label is left untouched."""
        if not self.cfg.external.is_dir():
            return
        for folder in sorted(self.cfg.external.iterdir()):
            receipt = folder / 'external-validation.json'
            if finished_receipt(folder) is not None or not receipt.is_file():
                continue
            try:
                doc = read_json(receipt)
            except (OSError, ValueError):
                continue
            if doc.get('candidate_engine_sha256') == engine_sha:
                self.wait_folder(folder)

    def make_room(self, out: Path, engine_sha: str):
        """`out` must not exist when the measurement starts: wait for a live process writing it, move a dead attempt aside."""
        if not out.exists():
            return
        self.wait_folder(out)
        receipt = finished_receipt(out)
        if receipt is not None and receipt.get('candidate_engine_sha256') == engine_sha:
            return
        aside = out.with_name(f'{out.name}-aborted-{stamp()}')
        os.rename(out, aside)
        self.note('measure', f'moved unfinished {out.name} aside to {aside.name}')

    def render_dir(self, stage: str, candidate: Path, engine_sha: str, out: Path, poses, label: str) -> int:
        """Render (or reuse) a Blender before/after comparison of the candidate into `out`; returns the total changed pixels."""
        comparison = out / 'comparison.json'
        if comparison.is_file():
            doc = read_json(comparison)
            if doc.get('after_sha256') == engine_sha:
                return sum(int(v['different_pixels']) for v in doc['views'])
            os.rename(out, out.with_name(f'{out.name}-other-{stamp()}'))
        elif out.exists():
            os.rename(out, out.with_name(f'{out.name}-aborted-{stamp()}'))
        code = self.steps['render'](before=self.cfg.baseline_engine, after=candidate / 'candidate.engine.obj', out=out, poses=poses, stage=stage)
        if code != 0 or not comparison.is_file():
            raise StageFailed('measure', f'{label} render exit {code} for {candidate.name}; see logs/pipeline-{self.cfg.floor}-{stage}-render.log')
        doc = read_json(comparison)
        if poses is None:
            code = self.steps['contact_sheet'](out=out, stage=stage)
            if code != 0:
                raise StageFailed('measure', f'contact sheet exit {code} for {out}')
        return sum(int(v['different_pixels']) for v in doc['views'])

    def interior_gate(self, stage: str, candidate: Path, engine_sha: str) -> int:
        cfg = self.cfg
        gate_dir = cfg.root / 'independent-validator' / f'{stage}-interior' / candidate.name
        gate_dir.mkdir(parents=True, exist_ok=True)
        source = cfg.poses.parent
        for name in ('camera-qualification.json', 'qualified-native-poses.json'):
            if not (gate_dir / name).exists() and (source / name).is_file():
                shutil.copyfile(source / name, gate_dir / name)
        return self.render_dir(stage, candidate, engine_sha, gate_dir / 'renders', cfg.poses, 'interior gate')

    def native_qa(self, stage: str, candidate: Path, engine_sha: str) -> int:
        out = self.cfg.root / f'{stage}-native-qa' / candidate.name
        px = self.render_dir(stage, candidate, engine_sha, out, None, 'native QA')
        if not (out / 'paired-detail.png').is_file() or not (out / 'all-views.png').is_file():
            code = self.steps['contact_sheet'](out=out, stage=stage)
            if code != 0:
                raise StageFailed('measure', f'contact sheet exit {code} for {out}')
        return px

    # ---- E4
    def next_e4_dir(self, e5_candidate: Path, excluded: set) -> Path:
        """R/e4/<F>-round<k>: an existing round built from this E5 candidate with these exclusions is reused, otherwise the first
        free round number."""
        cfg = self.cfg
        e5_sha = candidate_audit(e5_candidate)['engine_candidate_sha256']
        k = 1
        while True:
            folder = cfg.root / 'e4' / f'{cfg.floor}-round{k}'
            if not folder.exists():
                return folder
            if (folder / 'stage-audit.json').is_file():
                audit = candidate_audit(folder)
                bound = (audit.get('e5_candidate') or {}).get('engine_candidate_sha256')
                if bound == e5_sha and set(int(r) for r in (audit.get('excluded_regions') or [])) == excluded:
                    return folder
            k += 1

    def run_e4(self, e5_candidate: Path, out: Path, exclude) -> Path:
        cfg = self.cfg
        self.wait_ram('E4')
        code = self.steps['run_e4'](root=cfg.root, floor=cfg.floor, raw_name=cfg.raw_name, e5_candidate=e5_candidate, out=out, exclude=exclude, stage='e4')
        if code != 0 or not (out / 'stage-audit.json').is_file():
            raise StageFailed('e4', f'run_checked_e4_floor exit {code} for {out.name}; see logs/pipeline-{cfg.floor}-e4.log')
        audit = candidate_audit(out)
        self.note('e4', f'E4 {out.name}: {audit.get("input_triangles")} -> {audit.get("output_triangles")} triangles '
                        f'({audit.get("kept_edits")} merges kept, {audit.get("rolled_back_edits")} rolled back)')
        self.stage('e4', 'running', 60)
        return out

    def stage_e4(self, e5_candidate: Path) -> Path | None:
        cfg = self.cfg
        self.stage('e4', 'running', 10, note='starting')
        try:
            folder = self.next_e4_dir(e5_candidate, set())
            if folder.exists():
                self.note('e4', f'reused {folder.name}: {candidate_audit(folder)["output_triangles"]} triangles')
                self.stage('e4', 'running', 60)
            else:
                folder = self.run_e4(e5_candidate, folder, None)
            passing = self.heal_loop('e4', folder)
        except StageFailed as failure:
            if failure.stage == 'measure':
                raise
            self.note('e4', failure.note)
            self.note('e4', f'E4 failed the bar; the E5 candidate {e5_candidate.name} stays the floor result')
            self.stage('e4', 'failed', self.summary['stages']['e4']['percent'])
            e5_rows = self.summary['measurements']['e5']
            self.stage('measure', 'done', 100, note=f'e5: {e5_candidate.name} is the floor result ({e5_rows[-1]["label"]}: guard PASS '
                                                    f'{e5_rows[-1]["guard_px"]} px, textures PASS, coverage PASS, interior {e5_rows[-1]["interior_px"]} px); '
                                                    f'e4 failed: {failure.note}')
            self.summary['e4_candidate'] = None
            return None
        self.summary['e4_candidate'] = str(passing)
        self.stage('e4', 'done', 100)
        return passing

    # ---- publish
    def stage_publish(self, candidate: Path, stage: str):
        cfg = self.cfg
        audit = candidate_audit(candidate)
        m = next(row for row in reversed(self.summary['measurements'][stage]) if row['candidate'] == str(candidate))
        triangles = audit['output_triangles']
        interior = cfg.root / 'independent-validator' / f'{stage}-interior' / candidate.name
        native_qa = cfg.root / f'{stage}-native-qa' / candidate.name
        doc = self.progress.floor(cfg.floor)
        head = read_json(cfg.progress) if cfg.progress.is_file() else {}
        revision, run_id = head.get('source_revision', ''), head.get('run_id', '')
        published = self.published_engine_sha(revision, run_id)
        if published == audit['engine_candidate_sha256']:
            self.note('publish', f'{candidate.name} ({triangles} triangles) is already published (the evidence stage-audit carries its engine hash); '
                                 f'only the stage health and the floor state are refreshed')
            self.summary['publish'].update(already_published=True, game_dir=str(cfg.game_dir))
            self.stage('publish', 'done', 100)
            self.set_final_state(candidate, stage, m, audit, triangles, doc)
            return
        self.summary['publish']['already_published'] = False
        self.stage('publish', 'running', 10, note=f'binding the guard into {candidate.name}')
        self.steps['bind_guard'](candidate=candidate, measurement=m)
        self.summary['publish']['bound'] = True
        # the dashboard preview: the previous candidate folder moved aside with its stage and triangle count
        moved = []
        for index, public in enumerate(cfg.public):
            floor_dir = public / 'models' / 'main-infra' / revision / cfg.floor / run_id
            if os.name == 'nt' and not str(floor_dir).startswith('\\\\?\\') and floor_dir.is_absolute():
                floor_dir = Path('\\\\?\\' + str(floor_dir.resolve()))
            moved += self.move_preview_aside(floor_dir)
            self.stage('publish', 'running', 20 + 5 * index, note=f'repackaging the dashboard preview in {public}')
            code = self.steps['package_preview'](candidate=candidate, public=public, revision=revision, run_id=run_id, with_progress=index == 0)
            if code != 0:
                raise StageFailed('publish', f'main_infra_preview_stage2 exit {code} for {public}; see logs/pipeline-{cfg.floor}-publish.log')
        self.summary['publish']['moved_aside'] = sorted(set(moved))
        self.stage('publish', 'running', 35, note='publishing the evidence')
        code = self.steps['publish_evidence'](candidate=candidate, validation=Path(m['validation']), guard=Path(m['guard_path']), interior=interior,
                                              native_qa=native_qa)
        if code != 0:
            raise StageFailed('publish', f'publish_upper_evidence exit {code}; see logs/pipeline-{cfg.floor}-publish.log')
        self.stage('publish', 'running', 45, note='stage error kinds beside the candidate preview')
        e5_dir = Path(self.summary['e5_candidate'])
        e4_dir = candidate if stage == 'e4' else None
        first = cfg.public[0] / 'models' / 'main-infra' / revision / cfg.floor / run_id / 'candidate' / 'errors.json'
        code = self.steps['stage_errors'](e5=e5_dir, e4=e4_dir, before_out=Path(m['out']) / 'errors-before.json', after_out=first)
        if code != 0:
            self.note('publish', f'stage errors exit {code} (overlay only; see logs/pipeline-{cfg.floor}-publish.log)')
        else:
            for public in cfg.public[1:]:
                target = public / 'models' / 'main-infra' / revision / cfg.floor / run_id / 'candidate' / 'errors.json'
                if first.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(first, target)
        self.stage('publish', 'running', 55, note='archiving to repo 04 and copying to repo 03')
        self.move_archive_aside(audit)
        code = self.steps['archive'](candidate=candidate, validation_dir=Path(m['validation']).parent, guard=Path(m['guard_path']), interior=interior,
                                     cleanup_mode=audit.get('cleanup_mode'), run_id=run_id)
        if code != 0:
            raise StageFailed('publish', f'archive_upper_floor exit {code}; see logs/pipeline-{cfg.floor}-publish.log')
        self.summary['publish']['game_dir'] = str(cfg.game_dir)
        readme = self.readme(candidate, stage, m, triangles, revision)
        for name, percent, kwargs in [
                ('mirror_z', 70, dict(candidate=candidate, measurement=m, interior=interior, native_qa=native_qa, stage=stage, triangles=triangles, readme=readme)),
                ('upload_live', 85, dict(public=cfg.public[0], revision=revision, run_id=run_id, names=['candidate', 'evidence'] + sorted(set(moved)))),
                ('rebuild_library', 95, dict())]:
            self.stage('publish', 'running', percent, note=name.replace('_', ' '))
            try:
                code = self.steps[name](**kwargs)
            except Exception as error:                         # noqa: BLE001 - recorded, the Unity-ready file is already in repo 03
                code = f'{type(error).__name__}: {error}'
            self.summary['publish'][name] = code
            if code != 0:
                self.note('publish', f'{name} failed: {code}')
        kinds = ', '.join(f'{k} {v["before"]} to {v["after"]}' for k, v in m['kinds'].items() if v.get('after') is not None)
        self.note('publish', f'{stage.upper()} {triangles:,} triangles published; guard PASS {m["guard_px"]} px, textures PASS, coverage PASS, '
                             f'interior {m.get("interior_px", self.summary["measurements"][stage][-1]["interior_px"])} px; signed targets {m["problems"]}: {kinds}')
        self.stage('publish', 'done', 100)
        self.set_final_state(candidate, stage, m, audit, triangles, doc)

    def set_final_state(self, candidate: Path, stage: str, m: dict, audit: dict, triangles: int, doc: dict):
        step = self.step_text(candidate, stage, m, triangles)
        state = 'unity_ready' if self.progress.supports_state('unity_ready') else 'validating'
        self.progress.set_floor(self.cfg.floor, state, step, blocker=doc.get('blocker'), input_triangles=int(audit.get('input_triangles', 0)),
                                output_triangles=int(triangles))
        self.summary['publish'].update(state=state, step=step)

    def published_engine_sha(self, revision: str, run_id: str):
        """The engine hash of the candidate whose evidence is published in the first dashboard root, or None."""
        if not self.cfg.public or not revision or not run_id:
            return None
        path = self.cfg.public[0] / 'models' / 'main-infra' / revision / self.cfg.floor / run_id / 'evidence' / 'stage-audit.json'
        if os.name == 'nt' and path.is_absolute():
            path = Path('\\\\?\\' + str(path.resolve()))
        try:
            return read_json(path).get('engine_candidate_sha256') if path.is_file() else None
        except (OSError, ValueError):
            return None

    def move_preview_aside(self, floor_dir: Path) -> list:
        """<floor_dir>/candidate -> candidate-<stage>-<triangles> (from the published evidence's stage-audit), same for evidence."""
        moved = []
        if not floor_dir.is_dir():
            return moved
        old_audit = floor_dir / 'evidence' / 'stage-audit.json'
        suffix = None
        if old_audit.is_file():
            try:
                audit = read_json(old_audit)
                suffix = f'{STAGE_OF_MODE.get(audit.get("cleanup_mode"), "prev")}-{audit.get("output_triangles")}'
            except (OSError, ValueError):
                suffix = None
        suffix = suffix or f'prev-{stamp()}'
        for name in ('candidate', 'evidence'):
            src = floor_dir / name
            if src.exists():
                dst = floor_dir / f'{name}-{suffix}'
                if dst.exists():
                    dst = floor_dir / f'{name}-{suffix}-{stamp()}'
                os.rename(src, dst)
                moved.append(dst.name)
        return moved

    def move_archive_aside(self, audit: dict):
        """repo 04 record upper-floors/<F> and export Model-Floor_0N of a previous candidate are kept under -<stage>-<triangles>."""
        cfg = self.cfg
        record_dir = cfg.repo04 / '03_REPAIR_RECORDS' / 'MAIN_INFRA_MINECRAFT_20261023' / 'upper-floors' / cfg.floor
        export_dir = cfg.repo04 / 'Exports' / 'Repaired-Buildings-20261023-fresh' / 'ByBuilding' / 'Main-Infrastructure' / f'Model-Floor_0{cfg.floor[0]}'
        record = record_dir / 'SOURCE_REPAIR_RECORD.json'
        if not record.is_file():
            return
        old = read_json(record)
        if old.get('candidate', {}).get('engine_candidate_sha256') == audit['engine_candidate_sha256']:
            return
        suffix = f'{STAGE_OF_MODE.get(old.get("cleanup_mode"), "prev")}-{old.get("candidate", {}).get("output_triangles")}'
        for src in (record_dir, export_dir):
            if src.exists():
                dst = src.with_name(f'{src.name}-{suffix}')
                if dst.exists():
                    dst = src.with_name(f'{src.name}-{suffix}-{stamp()}')
                os.rename(src, dst)
                self.note('publish', f'previous {src.name} kept as {dst.name}')

    def readme(self, candidate: Path, stage: str, m: dict, triangles: int, revision: str) -> str:
        cfg = self.cfg
        audit = candidate_audit(candidate)
        kinds = '; '.join(f'{k} {v["before"]}->{v["after"]}' for k, v in m['kinds'].items() if v.get('after') is not None)
        row = self.summary['measurements'][stage][-1]
        return (f'MAIN INFRASTRUCTURE {cfg.floor}, {stage.upper()} candidate ({audit.get("cleanup_mode")}), {time.strftime("%Y-%m-%d")}.\n'
                f'Source revision {revision}, 1 block = 1 m.\n'
                f'{audit.get("input_triangles")} -> {triangles} triangles. {cfg.stem}.fixed.obj = source frame (metres, Y-up); '
                f'.fixed.engine.obj = engine frame (inches).\n'
                f'Measured by the identical independent guard + Validator (--allow {CBR}{", float64 oracle" if cfg.oracle else ""}): '
                f'strict 26-view guard PASS {m["guard_px"]} px; textures PASS; visible coverage PASS; interior gate {row["interior_px"]} changed px; '
                f'native QA 30 views {row["native_px"]} px; signed targets {m["problems"]}: {kinds}.\n'
                f'Candidate, not accepted. Written by tools/run_floor_pipeline.py.\n')

    def step_text(self, candidate: Path, stage: str, m: dict, triangles: int) -> str:
        cfg = self.cfg
        row = self.summary['measurements'][stage][-1]
        kinds = ', '.join(f'{k} {v["before"]} to {v["after"]}' for k, v in m['kinds'].items() if v.get('after') is not None)
        text = (f'LOCAL FIXED OBJ, Unity-ready: {cfg.game_dir / (cfg.stem + ".fixed.obj")} = {stage.upper()} {triangles:,} triangles '
                f'(guard PASS {m["guard_px"]} px, textures and coverage PASS, interior gate {row["interior_px"]} px; signed targets {m["problems"]}: {kinds}).')
        if stage == 'e5' and self.summary['stages'].get('e4', {}).get('status') == 'failed':
            text += f' E4 failed the bar: {self.summary["stages"]["e4"]["note"]}'
        return text

    def set_blocked(self, failure: StageFailed):
        cfg = self.cfg
        try:
            doc = self.progress.floor(cfg.floor)
            state = doc.get('state') or 'blocked'
            if state in ('unity_ready', 'validating', 'blocked'):
                blocked = state if state != 'validating' else 'blocked'
                self.progress.set_floor(cfg.floor, blocked, doc.get('step') or f'{failure.stage} failed', blocker=doc.get('blocker'))
        except Exception as error:                               # noqa: BLE001 - the stage health already carries the failure
            self.summary['progress_error'] = f'{type(error).__name__}: {error}'


def run_floor(cfg: Config, *, steps=None, progress=None, free_gb=free_physical_gb, sleep=time.sleep) -> dict:
    runner = Runner(cfg)
    defaults = DefaultSteps(cfg, runner)
    table = {name: getattr(defaults, name) for name in STEP_NAMES}
    for name, step in (steps or {}).items():
        if name not in STEP_NAMES:
            raise ValueError(f'unknown step {name}')
        table[name] = step
    progress = progress or ProgressWriter(cfg.progress, cfg.claude_worktree / 'tools' / 'main_infra_progress.py')
    return FloorPipeline(cfg, table, progress, free_gb=free_gb, sleep=sleep).run()


# --------------------------------------------------------------------------------------------------------------------
# --dry-run: the plan with the command lines, decided from the current state of the run root


def describe_plan(cfg: Config) -> str:
    cmd, lines = Commands(cfg), []
    q = subprocess.list2cmdline

    def say(text):
        lines.append(text)

    e5_dir = cfg.root / 'e5' / cfg.floor
    say(f'floor {cfg.floor} ({cfg.raw_name}), worker {cfg.worker}, run root {cfg.root}')
    say(f'progress {cfg.progress} via {cfg.claude_worktree / "tools" / "main_infra_progress.py"} set_stage(...); '
        f'logs {cfg.logs}/pipeline-{cfg.floor}-<stage>.log; RAM gate >= {cfg.min_free_gb} GB before engine and Validator steps; '
        f'OPENBLAS/OMP/MKL threads = 1')
    say(f'e3: {"reuse " + str(cfg.e3_dir) if (cfg.e3_dir / "stage-audit.json").is_file() else "MISSING " + str(cfg.e3_dir) + " (stop)"}')
    if (e5_dir / 'stage-audit.json').is_file():
        say(f'e5: reuse {e5_dir} ({candidate_audit(e5_dir).get("output_triangles")} triangles)')
        e5_label = f'{cfg.worker}-e5-{candidate_audit(e5_dir).get("output_triangles")}'
    else:
        say('e5: run  ' + q([str(a) for a in cmd.e5(e5_dir, cfg.exclude_sites)]))
        e5_label = f'{cfg.worker}-e5-<triangles>'
    snapshot = read_json(cfg.e3_dir / 'stage-audit.json').get('before_snapshot', '<e3 before_snapshot>') if (cfg.e3_dir / 'stage-audit.json').is_file() else '<snapshot>'
    say('measure (reused when a finished receipt under independent-validator/external/* carries the candidate engine hash):')
    say('  ' + q([str(a) for a in cmd.measure(e5_dir, cfg.external / e5_label, e5_label, snapshot, cfg.oracle)]))
    interior = cfg.root / 'independent-validator' / f'e5-interior' / cfg.floor / 'renders'
    say(f'  interior gate (total changed px over the pairs <= {cfg.interior_px_max}): '
        + q([str(a) for a in cmd.render(cfg.baseline_engine, e5_dir / 'candidate.engine.obj', interior, cfg.poses)]))
    say('  native QA (30 views): ' + q([str(a) for a in cmd.render(cfg.baseline_engine, e5_dir / 'candidate.engine.obj', cfg.root / 'e5-native-qa' / cfg.floor)]))
    say('  contact sheets: ' + q([str(a) for a in cmd.contact_sheet(cfg.root / 'e5-native-qa' / cfg.floor)]))
    say(f'heal (max {cfg.max_rounds} rounds): guard FAIL -> stop, diagnosis needed; textures / nothing_deleted FAIL with guard PASS -> '
        + q([str(a) for a in cmd.restore(e5_dir, ['<validation.json sites[].faces>'], '<reason>', cfg.root / 'e5' / f'{cfg.floor}-restore1')])
        + ' then measure again')
    e4_dir = cfg.root / 'e4' / f'{cfg.floor}-round1'
    if (e4_dir / 'stage-audit.json').is_file():
        say(f'e4: reuse {e4_dir} when its stage-audit binds the passing E5 candidate, else the next free round: '
            + q([str(a) for a in cmd.e4(e5_dir, cfg.root / 'e4' / f'{cfg.floor}-round<N>', None)]))
    else:
        say('e4: run  ' + q([str(a) for a in cmd.e4(e5_dir, e4_dir, None)]))
    say(f'  measured as above (label {cfg.worker}-e4-round<N>-<triangles>, e4-interior/<F>-round<N>, e4-native-qa/<F>-round<N>); a failing round is '
        'explained by tools.main_infra_e4_replay.explain_failures and rerun with --exclude-regions; when E4 misses the bar the E5 candidate '
        'stays the floor result and e4 is marked failed with the numbers')
    head = read_json(cfg.progress) if cfg.progress.is_file() else {}
    revision, run_id = head.get('source_revision', '<revision>'), head.get('run_id', '<run_id>')
    say('publish (the best candidate that passes guard + textures + nothing_deleted + interior gate):')
    say('  bind the external guard.json and Validator pointer into <candidate>/stage-audit.json (backup stage-audit.pre-guard-bind-<stamp>.json)')
    for public in cfg.public:
        say(f'  move {public}/models/main-infra/{revision}/{cfg.floor}/{run_id}/candidate -> candidate-<stage>-<triangles> (evidence likewise), then '
            + q([str(a) for a in cmd.preview('<candidate>', public, revision, run_id, public == cfg.public[0])]))
    say('  ' + q([str(a) for a in cmd.evidence('<candidate>', '<ext>/validation/validation.json', '<ext>/guard.json', '<stage>-interior/<name>', '<stage>-native-qa/<name>')]))
    say('  ' + q([str(a) for a in cmd.stage_errors('<e5 candidate>', '<e4 candidate or omitted>', '<ext>/errors-before.json',
                                                      f'{cfg.public[0]}/models/main-infra/{revision}/{cfg.floor}/{run_id}/candidate/errors.json')]))
    say('  move repo 04 upper-floors/<F> and Model-Floor_0N of a previous candidate to -<stage>-<triangles>, then '
        + q([str(a) for a in cmd.archive('<candidate>', '<ext>/validation', '<ext>/guard.json', '<stage>-interior/<name>', '<cleanup_mode>', run_id)]))
    say(f'  mirror to {cfg.z_root / cfg.floor / "<STAGE>-candidate-<triangles>"} (fixed.obj, fixed.engine.obj, MTL, textures, evidence, README.txt)')
    say(f'  upload candidate, evidence and the moved-aside folders of {cfg.public[0]} live (tar over ssh, tools/publish_upper_status_live.REMOTE)')
    say('  ' + q([str(a) for a in cmd.library()]))
    say(f'  floor state unity_ready (or validating until the dashboard knows it): "LOCAL FIXED OBJ, Unity-ready: {cfg.game_dir / (cfg.stem + ".fixed.obj")} = ..."')
    return '\n'.join(lines)


# --------------------------------------------------------------------------------------------------------------------
# CLI


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--floor', required=True, choices=list(FLOORS))
    parser.add_argument('--worker', default='claude', choices=['claude', 'codex'])
    parser.add_argument('--root', type=Path, default=DEFAULT_RUN_ROOT, help='run root R (default: the Claude worktree run root)')
    parser.add_argument('--claude-worktree', type=Path, default=DEFAULT_CLAUDE_WORKTREE)
    parser.add_argument('--progress', type=Path, default=DEFAULT_PROGRESS, help='current-upper.json')
    parser.add_argument('--public', type=Path, action='append', default=None, help='dashboard public root (repeatable)')
    parser.add_argument('--repo04', type=Path, default=DEFAULT_REPO04)
    parser.add_argument('--repo03', type=Path, default=DEFAULT_REPO03)
    parser.add_argument('--z-root', type=Path, default=DEFAULT_Z_ROOT)
    parser.add_argument('--blender', type=Path, default=DEFAULT_BLENDER)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--exclude-sites', type=Path, default=None, help='R/e5/exclusions/<file> for a fresh E5 run')
    parser.add_argument('--max-rounds', type=int, default=3)
    parser.add_argument('--min-free-gb', type=float, default=5.0)
    parser.add_argument('--max-wait-s', type=float, default=7200.0)
    parser.add_argument('--interior-px-max', type=int, default=INTERIOR_PX_MAX)
    parser.add_argument('--original-oracle', dest='oracle', action=argparse.BooleanOptionalAction, default=None,
                        help='force the float64 oracle on/off (default: on for 4F/5F/6F)')
    parser.add_argument('--job-id', default=JOB_ID)
    parser.add_argument('--reviewer', default=REVIEWER)
    parser.add_argument('--dry-run', action='store_true', help='print the plan with the commands it would run')
    return parser


def config_from_args(args) -> Config:
    return Config(floor=args.floor, root=args.root, worker=args.worker, claude_worktree=args.claude_worktree, progress=args.progress,
                  public=list(args.public) if args.public else list(DEFAULT_PUBLIC), repo04=args.repo04, repo03=args.repo03,
                  z_root=args.z_root, blender=args.blender, python=args.python, exclude_sites=args.exclude_sites, max_rounds=args.max_rounds,
                  min_free_gb=args.min_free_gb, max_wait_s=args.max_wait_s, interior_px_max=args.interior_px_max, job_id=args.job_id,
                  reviewer=args.reviewer, oracle=args.oracle, dry_run=args.dry_run)


def main(argv=None):
    cfg = config_from_args(build_parser().parse_args(argv))
    if cfg.dry_run:
        print(describe_plan(cfg), flush=True)
        return 0
    summary = run_floor(cfg)
    print(json.dumps({k: summary[k] for k in ('status', 'final_stage', 'final_candidate', 'e5_candidate', 'e4_candidate')}), flush=True)
    return 0 if summary['status'] == 'published' else 2


if __name__ == '__main__':
    sys.exit(main())
