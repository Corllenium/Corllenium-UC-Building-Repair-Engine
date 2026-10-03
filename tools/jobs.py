"""The shared job queue: one list of work that Claude sessions and Hermes both take jobs from.

The queue is a JSON file in the main checkout, ``data/jobs/queue.json`` (tests point ``UC_JOBS_ROOT``
somewhere else). Every command holds ``data/jobs/queue.lock`` while it reads or writes, so two agents
can never take the same job, and every write goes to a temp file that then replaces the queue
(``os.replace``), so nothing ever sees half a file. Readers take the lock too: on Windows ``os.replace``
fails while another process has the file open. Standard library only.

    python tools/jobs.py list [--status S] [--for claude|hermes]
    python tools/jobs.py next --for claude|hermes --as NAME    claims the first eligible job and prints
                                                                <id> TAB <brief> TAB <branch>; exit 3 if none
    python tools/jobs.py claim ID --as NAME [--for claude|hermes]
    python tools/jobs.py done ID [--branch B]
    python tools/jobs.py release ID
    python tools/jobs.py review ID (--pass | --changes NOTE)
    python tools/jobs.py block ID NOTE
    python tools/jobs.py unblock ID
    python tools/jobs.py add ID --title T --brief B --type T --who W [--depends a,b]
    python tools/jobs.py render                                 writes docs/superpowers/records/QUEUE.md

Exit codes: 0 done, 1 the request was refused (the reason is on stderr), 2 bad usage, 3 `next` found no job.

Statuses and the only moves between them (anything else raises ``JobError``):

    ready --(next, claim)--> claimed
    claimed, changes-requested --(done)--> awaiting-review
    claimed, changes-requested --(release)--> ready
    awaiting-review --(review --pass)--> merged          awaiting-review --(review --changes)--> changes-requested
    any --(block)--> blocked --(unblock)--> ready

``next`` takes a job that is ``ready``, whose ``who`` is the caller or ``either``, and whose dependencies
are all ``merged``; it takes them in queue order. ``claim`` is the manual override: it names the job and
checks only that it is ``ready``.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent

VERSION = 1
TYPES = ("build", "run", "validate", "research", "docs")
WHO = ("claude", "hermes", "either")
TAKERS = ("claude", "hermes")  # who can take a job; "either" marks a job, it is never a caller
STATUSES = ("ready", "claimed", "awaiting-review", "changes-requested", "merged", "blocked")

LOCK_WAIT_S = 10.0    # a command waits this long for the lock, then gives up
LOCK_STALE_S = 120.0  # a lock older than this was left by a process that died: it is broken
EXIT_NO_JOB = 3       # `next`: nothing is eligible

QUEUE_NAME = "queue.json"
LOCK_NAME = "queue.lock"
QUEUE_MD = Path("docs") / "superpowers" / "records" / "QUEUE.md"

# action -> (statuses it may start from, the status it ends in)
TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "claim": (("ready",), "claimed"),
    "done": (("claimed", "changes-requested"), "awaiting-review"),
    "release": (("claimed", "changes-requested"), "ready"),
    "pass": (("awaiting-review",), "merged"),
    "changes": (("awaiting-review",), "changes-requested"),
    "block": (STATUSES, "blocked"),
    "unblock": (("blocked",), "ready"),
}
_VERB = {"claim": "claimed", "done": "marked done", "release": "released", "pass": "passed",
         "changes": "sent back with changes", "block": "blocked", "unblock": "unblocked"}

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_NEW_FIELDS = ("id", "title", "brief", "type", "who", "depends_on")


class JobError(Exception):
    """A request the queue cannot honour: a move it does not allow, a bad field, a lock that never freed."""


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="minutes")


# ------------------------------------------------------------------ where the queue lives

def main_root() -> Path:
    """The main checkout, which owns ``data/``: found through git so a worktree reaches the same queue."""
    env = os.environ.get("UC_JOBS_ROOT")
    if env:
        return Path(env)
    try:
        out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=HERE,
                             capture_output=True, text=True, check=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        detail = (getattr(e, "stderr", None) or str(e)).strip()
        raise JobError(f"cannot find the main checkout through git ({detail}); "
                       "set UC_JOBS_ROOT to its folder") from e
    if not out:
        raise JobError("git did not name a common directory; set UC_JOBS_ROOT to the main checkout")
    return Path(out).parent


def queue_path(root: Path | str) -> Path:
    return Path(root) / "data" / "jobs" / QUEUE_NAME


def lock_path(root: Path | str) -> Path:
    return Path(root) / "data" / "jobs" / LOCK_NAME


# ------------------------------------------------------------------ file helpers

def _retry_busy(op: Callable[..., Any], *args: Any, attempts: int = 40, pause: float = 0.025) -> Any:
    """Run a file operation, trying again while Windows says the file is in use (a scanner, an indexer)."""
    for attempt in range(attempts):
        try:
            return op(*args)
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(pause)


def _unlink_quietly(path: Path) -> None:
    try:
        _retry_busy(os.unlink, path)
    except OSError:
        pass


def _write_atomic(path: Path, text: str) -> None:
    """Write ``text`` so that a reader, or a crash, sees the old file or the new one and never half of one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        _retry_busy(os.replace, tmp, path)
    except BaseException:
        _unlink_quietly(tmp)
        raise


# ------------------------------------------------------------------ the lock

class Locked:
    """``with Locked(root):`` holds ``data/jobs/queue.lock`` for the block.

    The lock is a file made with ``O_CREAT | O_EXCL``: exactly one process can make it. A process that
    finds it taken tries again until ``LOCK_WAIT_S`` is up, then raises ``JobError``. A lock older than
    ``LOCK_STALE_S`` belongs to a process that died, and is broken. The lock holds a token that only its
    owner recognises, so a process never removes a lock that someone else has since taken over. It is not
    re-entrant: taking it twice in one process waits, then gives up.
    """

    def __init__(self, root: Path | str, wait: float | None = None, stale: float | None = None):
        self.path = lock_path(root)
        self.wait = LOCK_WAIT_S if wait is None else wait
        self.stale = LOCK_STALE_S if stale is None else stale
        self._token = ""

    def __enter__(self) -> "Locked":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        token = f"{os.getpid()}-{uuid.uuid4().hex}"
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
        deadline = time.monotonic() + self.wait
        last: OSError | None = None
        while True:
            try:
                fd = os.open(self.path, flags)
            except (FileExistsError, PermissionError) as e:
                # PermissionError too: on Windows a lock file that is being deleted refuses O_EXCL this way.
                last = e
                if self._break_if_stale():
                    continue
                if time.monotonic() >= deadline:
                    raise JobError(self._gave_up(last)) from None
                time.sleep(random.uniform(0.01, 0.04))
                continue
            try:
                os.write(fd, token.encode("ascii"))
            except BaseException:
                os.close(fd)
                _unlink_quietly(self.path)  # never leave an empty lock that nobody owns
                raise
            os.close(fd)
            self._token = token
            return self

    def __exit__(self, *exc: Any) -> None:
        try:
            if self.path.read_bytes() == self._token.encode("ascii"):  # still ours?
                _retry_busy(os.unlink, self.path)
        except FileNotFoundError:
            pass  # broken as stale and not yet retaken: nothing of ours is left to remove
        except OSError as e:
            # The work is saved; do not turn that into a failure. The lock clears itself once it is stale.
            print(f"jobs: could not remove {self.path} ({e}); it will be broken after "
                  f"{self.stale:g} s", file=sys.stderr)

    def _break_if_stale(self) -> bool:
        """Remove the lock if it is stale. True means the lock file is gone, so try to take it again at once."""
        try:
            first = os.stat(self.path)
        except FileNotFoundError:
            return True  # released between our attempt and now
        except OSError:
            return False
        if time.time() - first.st_mtime <= self.stale:
            return False
        # Look again: if the file changed, someone else broke it and made a fresh one, which is not ours
        # to remove. (Two waiters can still judge one dead lock at the same moment; this shrinks that window
        # to microseconds, and it can only ever matter after a holder has crashed.)
        try:
            again = os.stat(self.path)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        if (again.st_mtime_ns, again.st_ino) != (first.st_mtime_ns, first.st_ino):
            return True
        try:
            _retry_busy(os.unlink, self.path)
        except FileNotFoundError:
            pass  # someone else broke it first
        except OSError:
            return False
        return True

    def _gave_up(self, last: OSError | None) -> str:
        who = ""
        try:
            age = time.time() - os.stat(self.path).st_mtime
            holder = self.path.read_bytes().decode("ascii", "replace").split("-")[0]
            who = f" (held for {age:.0f} s by process {holder})"
        except OSError:
            pass
        why = f"; last error: {last}" if last is not None and not isinstance(last, FileExistsError) else ""
        return (f"could not lock the job queue within {self.wait:g} s: {self.path} is taken{who}{why}. "
                f"A lock older than {self.stale:g} s is broken automatically; if no jobs.py is running, "
                "delete the file.")


# ------------------------------------------------------------------ load and save

def load(root: Path | str) -> dict:
    """The queue as ``{"version": 1, "jobs": [...]}``; an empty queue if the file does not exist yet."""
    path = queue_path(root)
    try:
        text = path.read_text(encoding="utf-8-sig")  # -sig: an editor may have added a byte-order mark
    except FileNotFoundError:
        return {"version": VERSION, "jobs": []}
    try:
        data = json.loads(text)
    except ValueError as e:
        raise JobError(f"{path} is not valid JSON ({e}); restore it or fix it by hand") from e
    if not (isinstance(data, dict) and data.get("version") == VERSION and isinstance(data.get("jobs"), list)):
        raise JobError(f"{path} is not a version {VERSION} job queue")
    return data


def save(root: Path | str, data: dict) -> None:
    """Replace the queue file atomically. Call it while holding the lock."""
    _write_atomic(queue_path(root), json.dumps(data, indent=2) + "\n")


# ------------------------------------------------------------------ jobs

def _text(job: dict, key: str) -> str:
    value = job[key]
    if not isinstance(value, str) or not value.strip():
        raise JobError(f"{key} must be a non-empty string")
    if any(ord(c) < 32 for c in value):
        raise JobError(f"{key} must be on one line, with no tabs or other control characters")
    return value.strip()


def _new_job(job: Any) -> dict:
    """Check a job someone wants to add, and build the record the queue stores (always ``ready``, unheld)."""
    if not isinstance(job, dict):
        raise JobError("a job must be a dict")
    missing = [k for k in _NEW_FIELDS[:-1] if k not in job]
    if missing:
        raise JobError(f"missing field(s): {', '.join(missing)}")
    extra = sorted(set(job) - set(_NEW_FIELDS))
    if extra:
        raise JobError(f"unknown field(s): {', '.join(extra)}; a new job takes only {', '.join(_NEW_FIELDS)}")
    jid, title, brief = _text(job, "id"), _text(job, "title"), _text(job, "brief")
    if not _ID.match(jid):
        raise JobError(f"id {jid!r} must be letters, digits, '.', '_' or '-', starting with a letter or digit")
    if job["type"] not in TYPES:
        raise JobError(f"type must be one of {', '.join(TYPES)} (got {job['type']!r})")
    if job["who"] not in WHO:
        raise JobError(f"who must be one of {', '.join(WHO)} (got {job['who']!r})")
    deps = job.get("depends_on", [])
    if not isinstance(deps, (list, tuple)) or not all(isinstance(d, str) and d.strip() for d in deps):
        raise JobError("depends_on must be a list of job ids")
    deps = list(dict.fromkeys(d.strip() for d in deps))
    if jid in deps:
        raise JobError(f"job {jid} cannot depend on itself")
    return {"id": jid, "title": title, "brief": brief, "type": job["type"], "who": job["who"],
            "depends_on": deps, "status": "ready", "holder": None, "branch": None, "since": _now(),
            "notes": []}


def _find(data: dict, jid: str) -> dict:
    for job in data["jobs"]:
        if job["id"] == jid:
            return job
    raise JobError(f"no job {jid!r} in the queue")


def _move(job: dict, action: str) -> None:
    """Apply a transition, or raise ``JobError`` naming the status the job is actually in."""
    sources, target = TRANSITIONS[action]
    if job["status"] not in sources:
        by = f" (holder: {job['holder']})" if job.get("holder") else ""
        raise JobError(f"job {job['id']} is {job['status']}{by}, so it cannot be {_VERB[action]}; "
                       f"that needs {' or '.join(sources)}")
    job["status"] = target
    job["since"] = _now()


def _note(job: dict, text: str) -> None:
    job["notes"].append(f"{_now()} {text}")


def _holder_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise JobError("a holder name is required (--as NAME)")
    return name


def _check_taker(who: str) -> None:
    if who not in TAKERS:
        raise JobError(f"the caller must be one of {', '.join(TAKERS)} (got {who!r})")


def _who_is_taking(job: dict, name: str, told: str | None) -> str:
    """The prefix of the branch a claim names: the caller if it said, else what the name says, else the job's."""
    if told:
        return told
    lowered = name.lower()
    for who in TAKERS:
        if lowered.startswith(who):
            return who
    return job["who"] if job["who"] in TAKERS else "claude"


def _take(job: dict, name: str, taking: str) -> None:
    _move(job, "claim")
    job["holder"] = name
    job["branch"] = f"{taking}/{job['id']}"


def add(root: Path | str, job: dict) -> dict:
    """Put a new job in the queue as ``ready``. Returns the stored job."""
    new = _new_job(job)
    with Locked(root):
        data = load(root)
        if any(j["id"] == new["id"] for j in data["jobs"]):
            raise JobError(f"job {new['id']} is already in the queue")
        data["jobs"].append(new)
        save(root, data)
    return new


def get(root: Path | str, jid: str) -> dict:
    with Locked(root):
        return _find(load(root), jid)


def list_jobs(root: Path | str, status: str | None = None, who: str | None = None) -> list[dict]:
    """The jobs in queue order, optionally only one status, and only those ``who`` may take."""
    if status is not None and status not in STATUSES:
        raise JobError(f"status must be one of {', '.join(STATUSES)} (got {status!r})")
    if who is not None:
        _check_taker(who)
    with Locked(root):
        rows = load(root)["jobs"]
    return [j for j in rows
            if (status is None or j["status"] == status) and (who is None or j["who"] in (who, "either"))]


def next_job(root: Path | str, who: str, name: str) -> dict | None:
    """Claim the first job ``who`` may take whose dependencies are merged, for ``name``. None if there is none.

    Finding the job and claiming it happen under one hold of the lock, so two callers never get the same one.
    A dependency that is not in the queue counts as not merged.
    """
    _check_taker(who)
    name = _holder_name(name)
    with Locked(root):
        data = load(root)
        state = {j["id"]: j["status"] for j in data["jobs"]}
        for job in data["jobs"]:
            if job["status"] != "ready" or job["who"] not in (who, "either"):
                continue
            if any(state.get(dep) != "merged" for dep in job["depends_on"]):
                continue
            _take(job, name, who)
            save(root, data)
            return job
    return None


def claim(root: Path | str, jid: str, name: str, who_taking: str | None = None) -> dict:
    """Claim one named job for ``name``. Only checks that it is ``ready``: it is the override of ``next``."""
    name = _holder_name(name)
    if who_taking is not None:
        _check_taker(who_taking)
    with Locked(root):
        data = load(root)
        job = _find(data, jid)
        _take(job, name, _who_is_taking(job, name, who_taking))
        save(root, data)
    return job


def done(root: Path | str, jid: str, branch: str | None = None) -> dict:
    """The holder has finished: the job waits for review. ``branch`` records where the work is."""
    with Locked(root):
        data = load(root)
        job = _find(data, jid)
        _move(job, "done")
        if branch and branch.strip():
            job["branch"] = branch.strip()
        save(root, data)
    return job


def release(root: Path | str, jid: str) -> dict:
    """The holder gives the job back: it is ``ready`` again for anyone. A note keeps who had it."""
    with Locked(root):
        data = load(root)
        job = _find(data, jid)
        _move(job, "release")
        _note(job, f"released by {job['holder']} (branch {job['branch']})")
        job["holder"] = None
        job["branch"] = None
        save(root, data)
    return job


def review(root: Path | str, jid: str, passed: bool, note: str = "") -> dict:
    """Claude's verdict on a finished job: merged, or sent back with a note saying what to change."""
    note = (note or "").strip()
    if not passed and not note:
        raise JobError("sending a job back needs a note saying what to change")
    with Locked(root):
        data = load(root)
        job = _find(data, jid)
        _move(job, "pass" if passed else "changes")
        if not passed:
            _note(job, f"changes requested: {note}")
        elif note:
            _note(job, f"review passed: {note}")
        save(root, data)
    return job


def block(root: Path | str, jid: str, note: str) -> dict:
    """Park a job, whatever its status, with the reason. A blocked job is not handed out."""
    note = (note or "").strip()
    if not note:
        raise JobError("blocking a job needs a note saying why")
    with Locked(root):
        data = load(root)
        job = _find(data, jid)
        _move(job, "block")
        _note(job, f"blocked: {note}")
        save(root, data)
    return job


def unblock(root: Path | str, jid: str) -> dict:
    """A blocked job goes back to ``ready``, with no holder. A note keeps who had it."""
    with Locked(root):
        data = load(root)
        job = _find(data, jid)
        _move(job, "unblock")
        _note(job, "unblocked" + (f" (was held by {job['holder']}, branch {job['branch']})"
                                  if job["holder"] else ""))
        job["holder"] = None
        job["branch"] = None
        save(root, data)
    return job


# ------------------------------------------------------------------ QUEUE.md

def _cell(value: Any) -> str:
    return " ".join(str(value).split()).replace("|", "\\|") if value else ""


def _render_md(rows: list[dict]) -> str:
    known = {j["id"] for j in rows}
    lines = [
        "# Job queue",
        "",
        f"Generated by `python tools/jobs.py render` at {_now()} from `data/jobs/queue.json`. "
        "Do not edit this file by hand: the next render overwrites it.",
        "",
        "| id | title | who | status | holder | branch | depends on | brief |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for j in rows:
        deps = ", ".join(d if d in known else f"{d} (not in queue)" for d in j["depends_on"])
        cells = [j["id"], j["title"], j["who"], j["status"], j["holder"], j["branch"], deps, j["brief"]]
        lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    return "\n".join(lines) + "\n"


def render(root: Path | str) -> str:
    """Write the queue for people to ``docs/superpowers/records/QUEUE.md`` under ``root``; returns the text."""
    root = Path(root)
    with Locked(root):
        md = _render_md(load(root)["jobs"])
        _write_atomic(root / QUEUE_MD, md)
    return md


# ------------------------------------------------------------------ command line

def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="jobs.py", description="The job queue shared by Claude and Hermes.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="show the jobs, one per line")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--for", dest="who", choices=TAKERS, help="only the jobs this agent may take")

    p = sub.add_parser("next", help="claim the first eligible job; exit 3 if there is none")
    p.add_argument("--for", dest="who", required=True, choices=TAKERS)
    p.add_argument("--as", dest="name", required=True, help="who is taking it, e.g. Hermes")

    p = sub.add_parser("claim", help="claim one named job (it must be ready)")
    p.add_argument("id")
    p.add_argument("--as", dest="name", required=True)
    p.add_argument("--for", dest="who", choices=TAKERS, help="names the branch; default: from the name or job")

    p = sub.add_parser("done", help="finished: wait for review")
    p.add_argument("id")
    p.add_argument("--branch", help="where the work is, e.g. hermes/P0-08")

    p = sub.add_parser("release", help="give the job back")
    p.add_argument("id")

    p = sub.add_parser("review", help="pass a finished job, or send it back")
    p.add_argument("id")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pass", dest="passed", action="store_true")
    g.add_argument("--changes", metavar="NOTE")

    p = sub.add_parser("block", help="park a job with a reason")
    p.add_argument("id")
    p.add_argument("note")

    p = sub.add_parser("unblock", help="make a blocked job ready again")
    p.add_argument("id")

    p = sub.add_parser("add", help="put a new job in the queue")
    p.add_argument("id")
    p.add_argument("--title", required=True)
    p.add_argument("--brief", required=True, help="path to the brief, may end #task-N")
    p.add_argument("--type", required=True, choices=TYPES)
    p.add_argument("--who", required=True, choices=WHO)
    p.add_argument("--depends", default="", help="comma-separated ids that must be merged first")

    sub.add_parser("render", help="write docs/superpowers/records/QUEUE.md")
    return ap


def _taken(job: dict) -> str:
    return f"{job['id']}\t{job['brief']}\t{job['branch']}"


def _state(job: dict) -> str:
    return f"{job['id']}\t{job['status']}"


def _run(a: argparse.Namespace) -> int:
    root = main_root()
    if a.cmd == "list":
        for j in list_jobs(root, a.status, a.who):
            print("\t".join([j["id"], j["status"], j["who"], j["holder"] or "-", j["title"]]))
    elif a.cmd == "next":
        job = next_job(root, a.who, a.name)
        if job is None:
            print(f"jobs: no job is eligible for {a.who}", file=sys.stderr)
            return EXIT_NO_JOB
        print(_taken(job))
    elif a.cmd == "claim":
        print(_taken(claim(root, a.id, a.name, a.who)))
    elif a.cmd == "done":
        print(_state(done(root, a.id, a.branch)))
    elif a.cmd == "release":
        print(_state(release(root, a.id)))
    elif a.cmd == "review":
        print(_state(review(root, a.id, bool(a.passed), a.changes or "")))
    elif a.cmd == "block":
        print(_state(block(root, a.id, a.note)))
    elif a.cmd == "unblock":
        print(_state(unblock(root, a.id)))
    elif a.cmd == "add":
        depends = [d.strip() for d in a.depends.split(",") if d.strip()]
        print(_state(add(root, {"id": a.id, "title": a.title, "brief": a.brief, "type": a.type,
                                "who": a.who, "depends_on": depends})))
    elif a.cmd == "render":
        render(root)
        print(root / QUEUE_MD)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:  # argparse has printed the usage error or the help; give the code back
        return e.code if isinstance(e.code, int) else 2
    try:
        return _run(args)
    except (JobError, OSError) as e:
        print(f"jobs: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:  # a title with a character this console cannot show must not crash a command
            _stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
