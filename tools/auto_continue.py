"""Keep the queued work moving with Hermes while Claude is at its usage limit.

Claude's agents stop when the account hits its usage limit. This runner reads Claude's transcripts
and the claims table; when Claude is out it hands the running implementation job to Hermes (Gemini)
in a worktree of its own, with the job's uncommitted work carried over, and releases the job when
Hermes stops. Claude reviews Hermes's branch before anything merges it.

Run from the repo root (standard library only):
    python tools/auto_continue.py status          what it sees and would do; changes nothing
    python tools/auto_continue.py watch           check every 5 minutes, act, supervise the run
    python tools/auto_continue.py tick            one check (for Task Scheduler)
    python tools/auto_continue.py stop [--kill]   no new runs; --kill also ends the running one
    python tools/auto_continue.py resume          allow new runs again

The rules are written in docs/superpowers/records/WORK-CLAIMS.md (automatic continuation) and
HANDOFF.md section 7.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Iterable

REPO = Path(__file__).resolve().parents[1]
CLAIMS = "docs/superpowers/records/WORK-CLAIMS.md"
LOG_MD = "docs/superpowers/records/AUTO-CONTINUE-LOG.md"
BRIEFS = "docs/superpowers/records/briefs"
REPORTS = "docs/superpowers/records/hermes-auto"
HOLDER = "Hermes (auto-continue)"
# Paths quoted in Hermes's prompt: the real-data snapshots and the scratch folder live only in the
# main checkout (data/ is not in git), and the owner's folder must never be written by a test run.
MAIN = "D:/PROJECTS/UC MODEL FIXER"
PY = f'"{MAIN}/.venv/Scripts/python.exe"'


@dataclasses.dataclass
class Config:
    repo: Path = REPO
    projects_dir: Path = Path.home() / ".claude" / "projects" / "D--PROJECTS-UC-MODEL-FIXER"
    hermes: list[str] = dataclasses.field(
        default_factory=lambda: [str(Path.home() / "AppData" / "Local" / "hermes" / "bin" / "hermes.exe")])
    runs_dir: Path = REPO / "data" / "auto_continue"
    tz: dt.tzinfo | None = None  # None: this machine's zone, the one the limit message is written in
    grace_min: float = 10  # after a limit hit, wait this long before acting
    silent_min: float = 90  # with no limit message, a Claude claim lapses after this much silence
    min_to_reset_min: float = 45  # the job stays with Claude when its limit resets sooner than this
    daily_cap_usd: float = 12.0  # Hermes spend per local day, all automatic runs together
    assumed_run_usd: float = 6.0  # counted for a run whose usage file is missing (it was killed)
    max_run_min: float = 150  # a run is ended after this long
    carry: tuple[str, ...] = ("engine", "docs/superpowers/records/scripts")  # work in progress moved along


# --- the claims table -------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Row:
    job: str
    brief: str
    tree: str
    holder: str
    since: str
    status: str

    @property
    def claude_running(self) -> bool:
        return self.holder.lower().startswith("claude") and self.status.lower().startswith("running")

    @property
    def hermes_running(self) -> bool:
        return self.holder.lower().startswith("hermes") and self.status.lower().startswith("running")


def _cells(line: str) -> list[str] | None:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return None
    return [c.strip() for c in s[1:-1].split("|")]


def parse_claims(text: str) -> list[Row]:
    rows = []
    for line in text.splitlines():
        cells = _cells(line)
        if not cells or len(cells) != 6 or cells[0] == "Job" or set(cells[0]) <= set("-: "):
            continue
        rows.append(Row(*cells))
    return rows


def update_claim(text: str, job: str, *, holder: str, since: str, status: str) -> str:
    """Rewrite one job's row; every other byte of the file stays as it was."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        cells = _cells(line)
        if cells and len(cells) == 6 and cells[0] == job:
            values = [cells[0], cells[1], cells[2], holder, since, status]
            values = [re.sub(r"[\r\n]+", " ", v).replace("|", "/") for v in values]
            lines[i] = "| " + " | ".join(values) + " |" + ("\r" if line.endswith("\r") else "")
            return "\n".join(lines)
    raise KeyError(job)


def job_paths(cfg: Config, row: Row) -> tuple[Path, Path] | None:
    """(brief file, job tree) of a job Hermes may take; None for reviews and paths that do not exist."""
    if "read-only" in f"{row.brief} {row.tree}".lower():
        return None
    m = re.search(r"briefs/(\d\d-[\w.-]+\.md)", row.brief)
    if not m:
        return None
    brief = cfg.repo / BRIEFS / m[1]
    where = row.tree.split(" / ")[0].strip()
    tree = cfg.repo if where.lower().startswith("main checkout") else cfg.repo / where
    if not brief.is_file() or not tree.is_dir():
        return None
    return brief, tree


_REPORT_RE = re.compile(r"\b[Rr]eport\s+`([^`]+\.md)`")


def job_done(cfg: Config, row: Row) -> bool:
    """True when the brief's own final report (the last report it names) exists in the job's tree.

    A finished agent's claim still reads "running" when Claude was cut before releasing it."""
    paths = job_paths(cfg, row)
    names = _REPORT_RE.findall(paths[0].read_text(encoding="utf-8", errors="replace")) if paths else []
    if not names:
        return False
    tree, name = paths[1], names[-1]
    if "/" in name:
        return (tree / name).is_file()
    ledgers = tree / ".superpowers" / "sdd"
    return ledgers.is_dir() and any(ledgers.rglob(name))


def may_take(cfg: Config, row: Row) -> bool:
    return job_paths(cfg, row) is not None and not job_done(cfg, row)


# --- Claude's state, read from its transcripts ---------------------------------------------------

_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_RESET_RE = re.compile(
    r"\s*(?:(?P<mon>[A-Za-z]{3})[A-Za-z]*\.?\s+(?P<day>\d{1,2}),?\s+(?:at\s+)?)?"
    r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>am|pm)\b", re.I)
_LIMIT_RE = re.compile(r"hit your (?P<kind>[\w -]*?)\s*limit\b.*?resets\s+(?P<when>.+)", re.I | re.S)


def parse_reset(when: str, hit: dt.datetime) -> dt.datetime | None:
    """The reset moment in a limit message ("8:40pm", "Oct 1, 9am"), read in the zone of `hit`."""
    m = _RESET_RE.match(when)
    if not m:
        return None
    hour = int(m["h"]) % 12 + (12 if m["ap"].lower() == "pm" else 0)
    minute = int(m["m"] or 0)
    if m["mon"]:
        mon = m["mon"][:3].lower()
        if mon not in _MONTHS:
            return None
        moment = hit.replace(month=_MONTHS.index(mon) + 1, day=int(m["day"]), hour=hour, minute=minute,
                             second=0, microsecond=0)
        return moment.replace(year=moment.year + 1) if moment < hit - dt.timedelta(days=1) else moment
    moment = hit.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return moment + dt.timedelta(days=1) if moment <= hit else moment


@dataclasses.dataclass
class LimitHit:
    at: dt.datetime
    kind: str
    resets_at: dt.datetime | None


@dataclasses.dataclass
class ClaudeState:
    limit: LimitHit | None  # the newest limit message in any transcript
    last_activity: dt.datetime | None  # the newest real entry (not an API error) in any transcript

    def at_limit(self, now: dt.datetime) -> bool:
        if self.limit is None:
            return False
        if self.last_activity is not None and self.last_activity > self.limit.at:
            return False
        return self.limit.resets_at is None or now < self.limit.resets_at


def _text(d: dict) -> str:
    msg = d.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return d["content"] if isinstance(d.get("content"), str) else ""


def _stamp(value) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def scan_entries(lines: Iterable[str], tz: dt.tzinfo) -> tuple[LimitHit | None, dt.datetime | None]:
    limit, activity = None, None
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        t = _stamp(d.get("timestamp")) if isinstance(d, dict) else None
        if t is None:
            continue
        t = t.astimezone(tz)
        if d.get("isApiErrorMessage") or d.get("error"):
            m = _LIMIT_RE.search(_text(d))
            if m and (limit is None or t >= limit.at):
                limit = LimitHit(at=t, kind=m["kind"].strip().lower() or "usage", resets_at=parse_reset(m["when"], t))
            continue  # other API errors (timeouts) are neither a limit nor activity
        if d.get("type") in ("user", "assistant") and (activity is None or t > activity):
            activity = t
    return limit, activity


def _tail_lines(path: Path, max_bytes: int) -> list[str]:
    with path.open("rb") as f:
        size = f.seek(0, os.SEEK_END)
        f.seek(max(0, size - max_bytes))
        lines = f.read().decode("utf-8", errors="replace").splitlines()
    return lines[1:] if size > max_bytes else lines  # the first line of a tail is cut


def read_claude_state(projects_dir: Path, tz: dt.tzinfo | None = None, newest: int = 12) -> ClaudeState:
    tz = tz or _local_tz()
    found = []
    for p in projects_dir.rglob("*.jsonl") if projects_dir.is_dir() else []:
        try:
            found.append((p.stat().st_mtime, p))
        except OSError:
            continue
    limit, activity = None, None
    for _, p in sorted(found, reverse=True)[:newest]:
        try:
            lim, act = scan_entries(_tail_lines(p, 2 << 20), tz)
            if lim is None and act is None:  # one huge entry filled the tail: look further back
                lim, act = scan_entries(_tail_lines(p, 16 << 20), tz)
        except OSError:
            continue
        if lim and (limit is None or lim.at > limit.at):
            limit = lim
        if act and (activity is None or act > activity):
            activity = act
    return ClaudeState(limit=limit, last_activity=activity)


# --- deciding -----------------------------------------------------------------------------------


@dataclasses.dataclass
class Decision:
    action: str  # none | wait | takeover | start
    reason: str
    row: Row | None = None


def _minutes(delta: dt.timedelta) -> float:
    return delta.total_seconds() / 60


def decide(rows: list[Row], state: ClaudeState, now: dt.datetime, spent_today: float, cfg: Config,
           eligible: Callable[[Row], bool], stopped: bool = False) -> Decision:
    # One automatic run at a time is kept by tick() (active.json). A Hermes job started by hand does
    # not hold the takeover back: its row stays "running" until Claude releases it, and a Claude cut
    # by its limit cannot.
    if stopped:
        return Decision("none", "stopped: the STOP file is present (python tools/auto_continue.py resume)")
    if state.limit is None and state.last_activity is None:
        return Decision("none", "no Claude transcript found, so Claude's state is unknown")
    if state.at_limit(now):
        since = _minutes(now - state.limit.at)
        if since < cfg.grace_min:
            return Decision("none", f"limit hit {since:.0f} min ago; grace period {cfg.grace_min:.0f} min")
        resets = state.limit.resets_at
        if resets is not None and _minutes(resets - now) < cfg.min_to_reset_min:
            return Decision("none", f"Claude is back in {_minutes(resets - now):.0f} min "
                                    f"(limit resets {resets:%H:%M}); the job stays with Claude")
        why = (f"Claude at its {state.limit.kind} limit since {state.limit.at:%H:%M}, "
               + (f"resets {resets:%Y-%m-%d %H:%M}" if resets else "reset time unknown"))
    else:
        silent = _minutes(now - state.last_activity) if state.last_activity else float("inf")
        if silent < cfg.silent_min:
            return Decision("none", f"Claude active {silent:.0f} min ago")
        why = f"no Claude activity for {silent:.0f} min"
    if spent_today >= cfg.daily_cap_usd:
        return Decision("none", f"{why}; today's Hermes spend {spent_today:.2f} USD has reached the "
                                f"daily cap of {cfg.daily_cap_usd:.2f} USD")
    claude = [r for r in rows if r.claude_running]
    for r in claude:
        if eligible(r):
            return Decision("takeover", why, r)
    for r in rows:
        if r.holder in ("", "-") and "auto-ok" in f"{r.since} {r.status}".lower() and eligible(r):
            return Decision("start", why, r)
    kept = ", ".join(r.job for r in claude) or "none running"
    return Decision("none", f"{why}; no job Hermes may take (reviews and read-only jobs stay with Claude): {kept}")


# --- Hermes's spend -----------------------------------------------------------------------------


def _usage_cost(path: Path) -> float | None:
    try:
        usage = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cost = (usage.get("total_including_auxiliary") or {}).get("estimated_cost_usd")
    cost = usage.get("estimated_cost_usd") if cost is None else cost
    return None if cost is None else float(cost)


def spent_on(day: dt.date, runs_dir: Path, assumed: float) -> float:
    """What the automatic runs started on `day` cost; a run without a usage file counts `assumed`."""
    total = 0.0
    for info_file in runs_dir.glob("*/run.json"):
        try:
            started = dt.datetime.fromisoformat(json.loads(info_file.read_text(encoding="utf-8"))["started"])
        except (OSError, ValueError, KeyError):
            continue
        if started.date() == day:
            cost = _usage_cost(info_file.parent / "usage.json")
            total += assumed if cost is None else cost
    return total


# --- the prompt ---------------------------------------------------------------------------------


def build_prompt(*, job: str, brief: str, run_id: str, wt: Path, branch: str, base: str, carried: list[str],
                 why: str, max_minutes: float, out_dir: Path) -> str:
    carried_text = "\n".join(f"    {c}" for c in carried) if carried else "    (none)"
    out = out_dir.as_posix()
    scratch = f'--skp-dir "{MAIN}/data/skp_scratch"'
    return f"""You are Hermes. You are continuing a job that a Claude agent started; {why}.
This run is automatic (run {run_id}) and nobody watches it live: follow these rules exactly, and
stop rather than guess.

WHERE YOU WORK
- Only in this git worktree: {wt.as_posix()} (branch {branch}, made from commit {base[:10]},
  the job's HEAD). Commit there. Never switch branches, merge, rebase, reset or push.
- The main checkout "{MAIN}" is shared by other sessions: never edit, stage or commit anything
  in it. You may READ its files and its data/ folder (the snapshots).
- The Claude agent's uncommitted work was copied into this worktree as staged changes:
{carried_text}
  It is work in progress: run the tests, finish it, commit it. Never discard it.

THE JOB: "{job}"
- Brief: {brief}. Read it completely.
- Also read HERMES.md section 0, docs/superpowers/records/HANDOFF.md sections 4 and 5, and the last
  80 lines of .superpowers/sdd/2026-09-21-phase2e-fix-pipeline/progress.md (what is done already).
- Run git log --oneline -15 to see the job's commits so far. Do only the brief's REMAINING items,
  in the brief's order.

HOW
- Python is {PY}, run from the worktree root, modules with -m. PYTHONPATH is already set to
  this worktree; keep it.
- Test-first for every item: write the failing test, run it and see it fail, implement, run it and
  see it pass. Tests: {PY} -m pytest engine/tests -q -p no:cacheprovider
  Never run the api tests: they drop a database other sessions use.
- One commit per item. The message says what changed and why and ends with the line
  Hermes-Auto-Run: {run_id}
  Stage files by name; never use git add -A, git add . or git commit -a.
- Real-data runs, only exactly like this (the owner's folder must never be written):
  {PY} -m engine.cli fix "{MAIN}/data/snapshots/ce26e0392ab0" --out "{out}" {scratch}
  {PY} -m engine.cli fix "{MAIN}/data/snapshots/0b290ec0bcb4" --out "{out}" {scratch}
  Then read each report.json: passed, invariants, merge_report.rolled_back, guard_final.totals.

NEVER
- Loosen a guard, tolerance, cap or threshold to make a test or a run pass, or change what the guard
  tolerates without naming and measuring it. Never delete side meshes. Never use a blocked
  operation: weld above 0.1 mm, select_interior_faces, hole fill / Make Manifold / Decimate /
  remeshing, treating opposite-normal coincident faces as duplicates.
- Touch OBJ FIXED RESULT/, docker-compose.yml or any Docker file, containers or servers (ports
  5190, 5180, 8190, 5490), the database "fixer", D:/PROJECTS/UC ENVIRONMENT BUILDING, the campus
  model .skp, or any .env, auth or key file.
- Edit WORK-CLAIMS.md or HANDOFF.md: the runner and Claude keep those.
- Install packages or change any tool's configuration.

STOP (commit only what is clean and tested, then write the report) when an item needs a blocked
operation or a looser guard, when the same test still fails after three honest attempts, when a real
run fails its guard and you cannot say why, or after about {max(30, int(max_minutes) - 20)} minutes of work.

FINISH
- Write {REPORTS}/{run_id}-report.md: a table of brief item -> commit -> the test that pins it; the
  test summary line exactly as printed; for each file from report.json: triangles, passed, back
  faces final, guard totals; what is left and why. Commit it.
- Final answer, 5 to 10 lines: the commits, the test line, whether both runs passed, what is left.
"""


# --- side effects: git, the Hermes process, the records -----------------------------------------

_PROCS: dict[str, subprocess.Popen] = {}
_NO_WINDOW = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0


def _local_tz() -> dt.tzinfo:
    return dt.datetime.now().astimezone().tzinfo


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()}")
    return r.stdout


def carry_wip(tree: Path, wt: Path, paths: Iterable[str], patch_file: Path) -> list[str]:
    """Copy the tree's uncommitted work under `paths` into the new worktree, staged. The tree keeps it."""
    paths = [p for p in paths if (tree / p).exists()]
    if not paths:
        return []
    patch = subprocess.run(["git", "-C", str(tree), "diff", "--binary", "HEAD", "--", *paths],
                           capture_output=True, check=True).stdout
    changed = [p for p in _git(tree, "diff", "--name-only", "-z", "HEAD", "--", *paths).split("\0") if p]
    new = [p for p in _git(tree, "ls-files", "--others", "--exclude-standard", "-z", "--", *paths).split("\0") if p]
    if patch.strip():
        patch_file.write_bytes(patch)
        _git(wt, "apply", "--index", "--binary", "--whitespace=nowarn", str(patch_file))
    for rel in new:
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tree / rel, wt / rel)
    if new:
        _git(wt, "add", "--", *new)
    return sorted(set(changed) | set(new))


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_active(cfg: Config) -> dict | None:
    active = _read_json(cfg.runs_dir / "active.json")
    return _read_json(cfg.runs_dir / active["run_id"] / "run.json") if active else None


def _pid_image(pid: int) -> str | None:
    """The image name of a live process, or None when there is no such process."""
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return None
        return ""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                               ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        code = wintypes.DWORD()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
            return None
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if not k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return Path(buf.value).name.lower()
    finally:
        k32.CloseHandle(handle)


def run_alive(run: dict) -> bool:
    proc = _PROCS.get(run["run_id"])
    if proc is not None:
        return proc.poll() is None
    image = _pid_image(int(run.get("pid") or 0)) if run.get("pid") else None
    # a reused pid belongs to another program: only the image the run started counts
    return image is not None and (image == "" or image == run.get("image", image))


def _kill(run: dict) -> None:
    if run_alive(run):
        subprocess.run(["taskkill", "/PID", str(run["pid"]), "/T", "/F"], capture_output=True)
    proc = _PROCS.get(run["run_id"])
    if proc is not None:
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass


def _log(cfg: Config, now: dt.datetime, text: str) -> None:
    md = cfg.repo / LOG_MD
    if not md.exists():
        md.write_text(
            "# Automatic continuation log\n\n"
            "Written by `tools/auto_continue.py` (HANDOFF.md section 7): one line per Hermes run started\n"
            "while Claude was at its usage limit, and one when it finished. Claude reviews every branch\n"
            "named here before anything merges it.\n\n", encoding="utf-8")
    with md.open("a", encoding="utf-8") as f:
        f.write(f"- {now:%Y-%m-%d %H:%M} {text}\n")


def _set_claim(cfg: Config, job: str, now: dt.datetime, holder: str, status: str) -> None:
    path = cfg.repo / CLAIMS
    text = path.read_bytes().decode("utf-8")
    path.write_bytes(update_claim(text, job, holder=holder, since=f"{now:%Y-%m-%d %H:%M}", status=status)
                     .encode("utf-8"))


def launch(cfg: Config, d: Decision, now: dt.datetime) -> str:
    paths = job_paths(cfg, d.row)
    if paths is None:
        raise RuntimeError(f"job {d.row.job!r} has no brief or tree to run")
    brief, tree = paths
    run_id = f"{now:%m%d-%H%M}-b{brief.name[:2]}"
    run_dir = cfg.runs_dir / run_id
    run_dir.mkdir(parents=True)
    branch = f"hermes/auto-{run_id}"
    wt = cfg.repo / ".hermes" / "worktrees" / f"auto-{run_id}"
    base = _git(tree, "rev-parse", "HEAD").strip()
    _git(cfg.repo, "worktree", "add", "-q", "-b", branch, str(wt), base)
    carried = carry_wip(tree, wt, cfg.carry, run_dir / "wip.patch")
    prompt = build_prompt(job=d.row.job, brief=brief.relative_to(cfg.repo).as_posix(), run_id=run_id, wt=wt,
                          branch=branch, base=base, carried=carried, why=d.reason, max_minutes=cfg.max_run_min,
                          out_dir=run_dir / "out")
    (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    usage = run_dir / "usage.json"
    with open(run_dir / "hermes.out", "wb") as out, open(run_dir / "hermes.err", "wb") as err:
        proc = subprocess.Popen([*cfg.hermes, "-z", prompt, "--in", str(wt), "--usage-file", str(usage)],
                                cwd=str(wt), stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                env={**os.environ, "PYTHONPATH": str(wt)}, creationflags=_NO_WINDOW)
    _PROCS[run_id] = proc
    run = {"run_id": run_id, "job": d.row.job, "brief": str(brief), "tree": str(tree), "wt": str(wt),
           "branch": branch, "base": base, "carried": carried, "why": d.reason, "started": now.isoformat(),
           "dir": str(run_dir), "usage": str(usage), "pid": proc.pid, "image": Path(cfg.hermes[0]).name.lower()}
    _write_json(run_dir / "run.json", run)
    _write_json(cfg.runs_dir / "active.json", {"run_id": run_id})
    _set_claim(cfg, d.row.job, now, HOLDER, f"running (auto-continue run {run_id}: worktree "
               f".hermes/worktrees/auto-{run_id}, branch {branch}; {d.reason})")
    _log(cfg, now, f"STARTED run {run_id}: Hermes took over {d.row.job!r} ({d.reason}); branch {branch} "
                   f"from {base[:10]}; carried {len(carried)} files of work in progress")
    return f"{d.action}: {d.reason}; run {run_id} started on branch {branch}"


def finish(cfg: Config, run: dict, now: dt.datetime, forced: str | None = None) -> str:
    usage = _read_json(Path(run["usage"])) or {}
    cost = _usage_cost(Path(run["usage"]))
    commits = [c for c in _git(cfg.repo, "log", "--format=%h %s", f"{run['base']}..{run['branch']}",
                               check=False).splitlines() if c.strip()]
    dirty = [c for c in _git(Path(run["wt"]), "status", "--porcelain", check=False).splitlines() if c.strip()]
    has_report = (Path(run["wt"]) / REPORTS / f"{run['run_id']}-report.md").is_file()
    outcome = forced or ("DONE" if usage.get("completed") and not usage.get("failed") and commits else "STOPPED")
    n = len(commits)
    shas = f" {commits[-1].split()[0]}..{commits[0].split()[0]}" if n > 1 else (f" {commits[0].split()[0]}" if n else "")
    status = (f"HERMES-AUTO {outcome} {now:%Y-%m-%d %H:%M}: branch {run['branch']}, {n} commit{'' if n == 1 else 's'}"
              f"{shas}, {'cost unknown' if cost is None else f'{cost:.2f} USD'}, {len(dirty)} files uncommitted, "
              f"report {'in the branch' if has_report else 'missing'}; Claude reviews the branch before any merge")
    try:
        _set_claim(cfg, run["job"], now, "-", status)
    except KeyError:
        status += " (claims row not found; not updated)"
    run.update(finished=now.isoformat(), outcome=outcome, commits=commits, cost=cost, uncommitted=len(dirty))
    _write_json(Path(run["dir"]) / "run.json", run)
    (cfg.runs_dir / "active.json").unlink(missing_ok=True)
    _PROCS.pop(run["run_id"], None)
    _log(cfg, now, f"{outcome} run {run['run_id']} on {run['job']!r}: {status}")
    return f"finished: run {run['run_id']} {outcome}; {status}"


def supervise(cfg: Config, run: dict, now: dt.datetime) -> str:
    ran = _minutes(now - dt.datetime.fromisoformat(run["started"]))
    if run_alive(run):
        if ran <= cfg.max_run_min:
            return f"wait: Hermes run {run['run_id']} on {run['job']!r} running for {ran:.0f} min"
        _kill(run)
        return finish(cfg, run, now, "TIMEOUT")
    return finish(cfg, run, now)


def tick(cfg: Config, now: dt.datetime | None = None, act: bool = True) -> str:
    tz = cfg.tz or _local_tz()
    now = now or dt.datetime.now(tz)
    run = load_active(cfg)
    if run is not None:
        return supervise(cfg, run, now) if act else f"wait: Hermes run {run['run_id']} is active"
    rows = parse_claims((cfg.repo / CLAIMS).read_text(encoding="utf-8"))
    state = read_claude_state(cfg.projects_dir, tz)
    spent = spent_on(now.date(), cfg.runs_dir, cfg.assumed_run_usd)
    d = decide(rows, state, now, spent, cfg, lambda r: may_take(cfg, r), stopped=(cfg.runs_dir / "STOP").exists())
    if d.action in ("takeover", "start") and act:
        return launch(cfg, d, now)
    return f"{d.action}: {d.reason}" + (f" (would take {d.row.job!r})" if d.row else "")


def stop(cfg: Config, kill: bool = False, now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(cfg.tz or _local_tz())
    cfg.runs_dir.mkdir(parents=True, exist_ok=True)
    (cfg.runs_dir / "STOP").write_text(f"stopped {now.isoformat()}\n", encoding="utf-8")
    run = load_active(cfg)
    if run is not None and kill:
        _kill(run)
        return finish(cfg, run, now, "STOPPED")
    return "stopped: no new runs" + (f"; run {run['run_id']} keeps going (--kill ends it)" if run else "")


def status(cfg: Config) -> str:
    tz = cfg.tz or _local_tz()
    now = dt.datetime.now(tz)
    st = read_claude_state(cfg.projects_dir, tz)
    rows = parse_claims((cfg.repo / CLAIMS).read_text(encoding="utf-8"))
    lim = st.limit
    lines = [
        f"now {now:%Y-%m-%d %H:%M}",
        "Claude: last activity " + (f"{st.last_activity:%H:%M} ({_minutes(now - st.last_activity):.0f} min ago)"
                                    if st.last_activity else "none found"),
        "Claude: newest limit message " + (f"{lim.at:%m-%d %H:%M} ({lim.kind}, resets "
                                           f"{lim.resets_at:%m-%d %H:%M})" if lim and lim.resets_at else
                                           (f"{lim.at:%m-%d %H:%M}" if lim else "none")) +
        f"; at the limit now: {'yes' if st.at_limit(now) else 'no'}",
    ]
    for r in rows:
        if r.claude_running or r.hermes_running:
            who = ("Hermes may take it" if may_take(cfg, r) else
                   "its report is written, so it counts as finished" if job_paths(cfg, r) else "stays with Claude")
            lines.append(f"claim: {r.job!r} held by {r.holder} ({who if r.claude_running else 'Hermes'})")
    lines.append(f"Hermes spend today {spent_on(now.date(), cfg.runs_dir, cfg.assumed_run_usd):.2f} of "
                 f"{cfg.daily_cap_usd:.2f} USD")
    lines.append("decision: " + tick(cfg, now, act=False))
    return "\n".join(lines)


def watch(cfg: Config, every_s: float) -> int:
    cfg.runs_dir.mkdir(parents=True, exist_ok=True)
    pid_file = cfg.runs_dir / "watch.pid"
    try:
        other = int(pid_file.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        other = 0
    if other and other != os.getpid() and (_pid_image(other) or "").startswith("python"):
        print(f"another watcher runs as pid {other}; not starting a second one")
        return 1
    pid_file.write_text(f"{os.getpid()}\n")
    print(f"watching every {every_s:.0f} s; runs in {cfg.runs_dir}; daily cap {cfg.daily_cap_usd:.2f} USD, "
          f"{cfg.max_run_min:.0f} min per run", flush=True)
    while True:
        try:
            msg = tick(cfg)
        except Exception as e:  # keep watching; the error is in the log
            msg = f"error: {e!r}"
        line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
        print(line, flush=True)
        with (cfg.runs_dir / "runner.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        time.sleep(every_s)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Hand Claude's running job to Hermes while Claude is at its limit.")
    p.add_argument("command", choices=["status", "tick", "watch", "stop", "resume"])
    p.add_argument("--kill", action="store_true", help="stop: also end the running Hermes run")
    p.add_argument("--every", type=float, default=300, help="watch: seconds between checks")
    p.add_argument("--daily-cap", type=float, default=Config.daily_cap_usd, help="USD of Hermes spend per day")
    p.add_argument("--max-run-min", type=float, default=Config.max_run_min, help="minutes before a run is ended")
    a = p.parse_args(argv)
    cfg = Config(daily_cap_usd=a.daily_cap, max_run_min=a.max_run_min)
    if a.command == "status":
        print(status(cfg))
    elif a.command == "tick":
        print(tick(cfg))
    elif a.command == "watch":
        return watch(cfg, a.every)
    elif a.command == "stop":
        print(stop(cfg, kill=a.kill))
    else:
        (cfg.runs_dir / "STOP").unlink(missing_ok=True)
        print("resumed: new runs allowed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
