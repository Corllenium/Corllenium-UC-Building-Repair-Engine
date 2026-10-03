"""What tools/jobs.py promises beyond the nine tests in test_jobs.py.

The brief's nine tests cover the happy paths. These cover the rest of what the brief specifies and
what Hermes will depend on: the CLI's output (UTF-8, LF) and exit codes, block/unblock, the lock's two
time limits (10 s wait, 120 s stale) and what it does when the OS refuses it, atomic writes and the
Windows retries around them, input validation, and no lost update under real contention. Every test
works in tmp_path through UC_JOBS_ROOT; none touches the real queue.
"""
import codecs
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from tools import jobs


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("UC_JOBS_ROOT", str(tmp_path))
    return tmp_path


def _add(root, jid, who="either", deps=(), title=None):
    jobs.add(root, {"id": jid, "title": title or jid, "brief": f"b/{jid}.md", "type": "build",
                    "who": who, "depends_on": list(deps)})


def _lock(root):
    return root / "data" / "jobs" / "queue.lock"


def _queue(root):
    return root / "data" / "jobs" / "queue.json"


# ---------------------------------------------------------------- the CLI contract

def test_cli_next_prints_id_brief_branch_separated_by_tabs(root, capsys):
    _add(root, "P0-08", who="hermes")
    assert jobs.main(["next", "--for", "hermes", "--as", "Hermes"]) == 0
    assert capsys.readouterr().out == "P0-08\tb/P0-08.md\thermes/P0-08\n"


def test_cli_every_command_works_end_to_end(root, capsys):
    m = jobs.main
    assert m(["add", "A", "--title", "First", "--brief", "plan.md#task-1", "--type", "build",
              "--who", "claude"]) == 0
    assert m(["add", "B", "--title", "Second", "--brief", "plan.md#task-2", "--type", "docs",
              "--who", "either", "--depends", "A"]) == 0
    capsys.readouterr()

    assert m(["list"]) == 0
    assert [ln.split("\t")[:2] for ln in capsys.readouterr().out.splitlines()] == \
        [["A", "ready"], ["B", "ready"]]
    assert m(["list", "--status", "ready", "--for", "hermes"]) == 0       # A is claude-only
    assert [ln.split("\t")[0] for ln in capsys.readouterr().out.splitlines()] == ["B"]

    assert m(["claim", "A", "--as", "Claude"]) == 0
    assert jobs.get(root, "A")["holder"] == "Claude" and jobs.get(root, "A")["branch"] == "claude/A"
    assert m(["done", "A", "--branch", "claude/A-final"]) == 0
    assert jobs.get(root, "A")["status"] == "awaiting-review"
    assert jobs.get(root, "A")["branch"] == "claude/A-final"
    assert m(["review", "A", "--changes", "rename it"]) == 0
    assert jobs.get(root, "A")["status"] == "changes-requested"
    assert m(["done", "A"]) == 0                                          # --branch is optional
    assert jobs.get(root, "A")["branch"] == "claude/A-final"
    assert m(["review", "A", "--pass"]) == 0
    assert jobs.get(root, "A")["status"] == "merged"

    assert m(["next", "--for", "claude", "--as", "Claude"]) == 0          # B: dependency now merged
    assert jobs.get(root, "B")["holder"] == "Claude"
    assert m(["block", "B", "waiting for the owner"]) == 0
    assert jobs.get(root, "B")["status"] == "blocked"
    assert m(["unblock", "B"]) == 0
    assert jobs.get(root, "B")["status"] == "ready"
    assert m(["claim", "B", "--as", "Hermes"]) == 0
    assert jobs.get(root, "B")["branch"] == "hermes/B"
    assert m(["release", "B"]) == 0
    assert jobs.get(root, "B")["status"] == "ready" and jobs.get(root, "B")["holder"] is None

    capsys.readouterr()
    assert m(["render"]) == 0
    assert (root / "docs" / "superpowers" / "records" / "QUEUE.md").is_file()


def test_cli_job_error_exits_1_and_says_why(root, capsys):
    assert jobs.main(["done", "NOPE"]) == 1
    assert "NOPE" in capsys.readouterr().err
    _add(root, "A")
    assert jobs.main(["done", "A"]) == 1                                  # ready, not claimed
    assert "ready" in capsys.readouterr().err                             # the message names the status


def test_the_script_writes_utf8_with_lf_endings_whatever_the_console_default(root):
    """Hermes reads a piped `next`: a CR on the branch, or a '?' in a path, would break it. Windows gives a
    pipe the ANSI code page and turns each LF into CRLF, so this checks bytes, under a hostile default."""
    env = {**os.environ, "UC_JOBS_ROOT": str(root), "PYTHONIOENCODING": "ascii"}
    env.pop("PYTHONUTF8", None)
    arrow, tick, e_acute = chr(0x2192), chr(0x2713), chr(0xE9)
    title, brief = f"Fix {arrow} {tick}", f"docs/caf{e_acute}/{tick}-plan.md"
    script = [sys.executable, str(Path(jobs.__file__))]
    cr = bytes([13])

    def run(*args):
        return subprocess.run(script + list(args), env=env, capture_output=True)   # bytes: nothing translates

    empty = run("next", "--for", "hermes", "--as", "H")
    assert empty.returncode == 3 and empty.stdout == b""
    assert empty.stderr.endswith(b"\n") and cr not in empty.stderr
    added = run("add", "A", "--title", title, "--brief", brief, "--type", "build", "--who", "hermes")
    assert added.returncode == 0 and added.stdout == b"A\tready\n"
    listed = run("list")
    assert listed.stdout == f"A\tready\thermes\t-\t{title}\n".encode("utf-8")
    taken = run("next", "--for", "hermes", "--as", "H")
    assert taken.returncode == 0
    assert taken.stdout == f"A\t{brief}\thermes/A\n".encode("utf-8")      # LF only; accent and tick intact
    refused = run("done", "NOPE")
    assert refused.returncode == 1 and refused.stderr.endswith(b"\n") and cr not in refused.stderr


def test_main_sets_up_its_streams_only_when_it_is_the_command(root, monkeypatch):
    """main() with no argv is the command (script, -m, entry point): it makes stdout and stderr UTF-8 with
    LF. A caller that passes argv, such as a test or another tool, keeps the streams it has."""
    calls = []

    class Stream(io.StringIO):
        def reconfigure(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(sys, "stdout", Stream())
    monkeypatch.setattr(sys, "stderr", Stream())
    assert jobs.main(["list"]) == 0
    assert calls == []
    monkeypatch.setattr(sys, "argv", ["jobs.py", "list"])
    assert jobs.main() == 0
    assert calls == [{"encoding": "utf-8", "errors": "replace", "newline": "\n"}] * 2   # stdout, stderr


def test_main_copes_with_a_stream_that_cannot_be_reconfigured(root, monkeypatch):
    class Plain:                                   # no reconfigure(), like a file-like wrapper
        def __init__(self):
            self.text = []

        def write(self, s):
            self.text.append(s)

        def flush(self):
            pass

    monkeypatch.setattr(sys, "stderr", Plain())
    monkeypatch.setattr(sys, "argv", ["jobs.py", "list"])
    assert jobs.main() == 0


# ---------------------------------------------------------------- block / unblock / release

def test_block_from_any_status_and_unblock_only_from_blocked(root):
    _add(root, "A")
    with pytest.raises(jobs.JobError):
        jobs.unblock(root, "A")                                           # ready is not blocked
    with pytest.raises(jobs.JobError):
        jobs.block(root, "A", "  ")                                       # a reason is required
    jobs.block(root, "A", "waiting for the owner")
    assert jobs.get(root, "A")["status"] == "blocked"
    assert "waiting for the owner" in jobs.get(root, "A")["notes"][-1]
    jobs.unblock(root, "A")
    assert jobs.get(root, "A")["status"] == "ready"

    jobs.claim(root, "A", "Claude")
    jobs.block(root, "A", "needs a decision")                             # claimed -> blocked
    assert jobs.get(root, "A")["holder"] == "Claude"                      # the work is still theirs
    jobs.unblock(root, "A")
    after = jobs.get(root, "A")
    assert after["status"] == "ready" and after["holder"] is None and after["branch"] is None

    jobs.claim(root, "A", "Claude"); jobs.done(root, "A", "claude/A"); jobs.review(root, "A", True, "")
    jobs.block(root, "A", "merge found broken")                           # "any -> blocked"
    assert jobs.get(root, "A")["status"] == "blocked"


def test_a_blocked_job_is_not_handed_out_and_holds_back_its_dependants(root):
    _add(root, "A", who="hermes"); _add(root, "B", who="hermes", deps=["A"])
    jobs.block(root, "A", "needs the owner")
    assert jobs.next_job(root, "hermes", "H") is None                     # A blocked; B waits on A
    jobs.unblock(root, "A")
    assert jobs.next_job(root, "hermes", "H")["id"] == "A"


def test_release_returns_the_job_and_keeps_a_note_of_who_had_it(root):
    _add(root, "A")
    jobs.claim(root, "A", "Hermes")
    job = jobs.release(root, "A")
    assert job["status"] == "ready" and job["holder"] is None and job["branch"] is None
    assert "Hermes" in job["notes"][-1] and "hermes/A" in job["notes"][-1]

    jobs.claim(root, "A", "Claude"); jobs.done(root, "A", "claude/A")
    jobs.review(root, "A", False, "tests missing")
    assert jobs.release(root, "A")["status"] == "ready"                   # changes-requested -> ready


def test_claim_names_the_branch_after_who_is_taking_the_job(root):
    for jid, who in [("A", "either"), ("B", "either"), ("C", "hermes"), ("D", "either"), ("E", "hermes")]:
        _add(root, jid, who=who)
    assert jobs.claim(root, "A", "Hermes (auto-continue)")["branch"] == "hermes/A"   # the name says
    assert jobs.claim(root, "B", "H123", who_taking="hermes")["branch"] == "hermes/B"  # told outright
    assert jobs.claim(root, "C", "Claude")["branch"] == "claude/C"        # the name beats the job's who
    assert jobs.claim(root, "D", "worker-7")["branch"] == "claude/D"      # nothing to go on
    assert jobs.claim(root, "E", "worker-7")["branch"] == "hermes/E"      # the job's who decides


def test_claim_refuses_a_job_that_is_already_taken(root):
    _add(root, "A")
    jobs.claim(root, "A", "Claude")
    with pytest.raises(jobs.JobError, match="claimed"):
        jobs.claim(root, "A", "Hermes")


# ---------------------------------------------------------------- the lock

def test_lock_wait_gives_up_instead_of_hanging(root, monkeypatch):
    monkeypatch.setattr(jobs, "LOCK_WAIT_S", 0.3)
    with jobs.Locked(root):
        t0 = time.monotonic()
        with pytest.raises(jobs.JobError, match="lock"):
            _add(root, "A")                       # same process: the lock is not re-entrant
        assert 0.25 <= time.monotonic() - t0 < 5
    _add(root, "A")                               # released on exit, so this works now


def test_a_lock_the_os_keeps_refusing_to_make_ends_in_a_job_error_and_does_not_spin(root, monkeypatch):
    """Regression. os.open refusing with PermissionError while no lock file exists used to loop at once, with
    no deadline check and no pause: full CPU, forever, instead of a JobError after the wait."""
    monkeypatch.setattr(jobs, "LOCK_WAIT_S", 0.3)
    real_open, attempts = os.open, []

    def refuse(path, flags, *args, **kwargs):
        if str(path).endswith("queue.lock"):
            attempts.append(1)
            if len(attempts) > 2000:               # a loop that never pauses gets here within milliseconds
                raise RuntimeError(f"spinning: {len(attempts)} attempts without a pause")
            raise PermissionError(13, "simulated: access is denied")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", refuse)
    t0 = time.monotonic()
    with pytest.raises(jobs.JobError, match="simulated: access is denied") as why:   # names the last OS error
        _add(root, "A")
    assert 0.25 <= time.monotonic() - t0 < 2       # the wait was 0.3 s: not a spin, and not a hang
    assert len(attempts) < 200                     # it paused between tries: 0.3 s at 10-40 ms is 10-30 tries
    assert "delete the file" not in str(why.value)  # there is no lock file, so do not tell anyone to delete one
    monkeypatch.undo()
    assert not _lock(root).exists() and jobs.list_jobs(root) == []


def test_a_refusal_that_clears_up_is_waited_out(root, monkeypatch):
    """A lock file that is mid-delete refuses O_EXCL with PermissionError on Windows for a moment."""
    real_open, attempts = os.open, []

    def refuse_three_times(path, flags, *args, **kwargs):
        if str(path).endswith("queue.lock"):
            attempts.append(1)
            if len(attempts) <= 3:
                raise PermissionError(13, "simulated: access is denied")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", refuse_three_times)
    _add(root, "A")
    assert len(attempts) == 4                      # three refusals, then the lock was made
    monkeypatch.undo()
    assert jobs.get(root, "A")["status"] == "ready"


def test_a_fresh_lock_is_never_broken_and_a_stale_one_always_is(root, monkeypatch):
    monkeypatch.setattr(jobs, "LOCK_WAIT_S", 0.3)
    lock = _lock(root)
    lock.parent.mkdir(parents=True); lock.write_text("1234")
    for age in (0, 100):                          # younger than the 120 s limit
        old = time.time() - age; os.utime(lock, (old, old))
        with pytest.raises(jobs.JobError):
            _add(root, "A")
        assert lock.read_text() == "1234"         # untouched
    old = time.time() - 130; os.utime(lock, (old, old))
    _add(root, "A")                               # older than 120 s: broken, no timeout
    assert jobs.get(root, "A")["status"] == "ready" and not lock.exists()


def test_the_lock_is_released_after_success_and_after_an_error(root):
    _add(root, "A")
    assert not _lock(root).exists()
    with pytest.raises(jobs.JobError):
        jobs.done(root, "A", "x")
    assert not _lock(root).exists()
    with pytest.raises(jobs.JobError):
        _add(root, "A")                           # duplicate
    assert not _lock(root).exists()


def test_a_lock_someone_else_took_over_is_not_deleted_by_us(root):
    with jobs.Locked(root):
        _lock(root).write_text("someone else")    # a waiter judged us stale and replaced the lock
    assert _lock(root).read_text() == "someone else"


def test_no_update_is_lost_when_threads_write_at_once(root):
    errors = []

    def worker(n):
        try:
            for i in range(8):
                _add(root, f"T{n}-{i}")
        except Exception as e:                    # noqa: BLE001 - reported below
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
    for t in threads: t.start()
    for t in threads: t.join(120)
    assert not errors
    ids = [j["id"] for j in jobs.list_jobs(root)]
    assert len(ids) == 48 and len(set(ids)) == 48


# ---------------------------------------------------------------- the file

def test_save_is_atomic_and_leaves_nothing_but_the_queue(root):
    for i in range(5):
        _add(root, f"J{i}")
    assert sorted(p.name for p in _queue(root).parent.iterdir()) == ["queue.json"]
    data = json.loads(_queue(root).read_text(encoding="utf-8"))
    assert data["version"] == 1 and [j["id"] for j in data["jobs"]] == [f"J{i}" for i in range(5)]


def test_a_failed_save_keeps_the_old_queue_and_cleans_up(root, monkeypatch):
    _add(root, "A")
    before = _queue(root).read_bytes()

    def boom(src, dst):
        raise OSError("disk gone")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        _add(root, "B")
    monkeypatch.undo()
    assert _queue(root).read_bytes() == before
    assert sorted(p.name for p in _queue(root).parent.iterdir()) == ["queue.json"]   # no .tmp, no .lock


def test_a_corrupt_queue_file_is_a_job_error_and_is_never_overwritten(root):
    _queue(root).parent.mkdir(parents=True)
    _queue(root).write_text("{not json", encoding="utf-8")
    with pytest.raises(jobs.JobError, match="queue.json"):
        _add(root, "A")
    assert _queue(root).read_text(encoding="utf-8") == "{not json"
    assert not _lock(root).exists()


def test_save_waits_out_windows_saying_the_file_is_in_use(root, monkeypatch):
    _add(root, "A")
    real_replace, calls = os.replace, []

    def busy_twice(src, dst):
        calls.append(1)
        if len(calls) <= 2:
            raise PermissionError(32, "simulated: the file is in use by another process")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", busy_twice)
    _add(root, "B")                                # two refusals, then the replace goes through
    assert len(calls) == 3
    monkeypatch.undo()
    assert [j["id"] for j in jobs.list_jobs(root)] == ["A", "B"]
    assert sorted(p.name for p in _queue(root).parent.iterdir()) == ["queue.json"]


def test_save_gives_up_when_the_file_stays_in_use_and_keeps_the_old_queue(root, monkeypatch):
    _add(root, "A")
    before = _queue(root).read_bytes()
    monkeypatch.setattr(jobs.time, "sleep", lambda seconds: None)    # do not really wait out the retries
    calls = []

    def always_busy(src, dst):
        calls.append(1)
        raise PermissionError(32, "simulated: the file is in use by another process")

    monkeypatch.setattr(os, "replace", always_busy)
    with pytest.raises(PermissionError, match="simulated"):
        _add(root, "B")
    monkeypatch.undo()
    assert 1 < len(calls) < 1000                   # it retried, and it stopped
    assert _queue(root).read_bytes() == before
    assert sorted(p.name for p in _queue(root).parent.iterdir()) == ["queue.json"]   # no .tmp, no .lock


def test_the_lock_release_retries_when_the_file_is_in_use(root, monkeypatch):
    real_unlink, calls = os.unlink, []

    def busy_twice(path, *args, **kwargs):
        if str(path).endswith("queue.lock"):
            calls.append(1)
            if len(calls) <= 2:
                raise PermissionError(32, "simulated: the file is in use by another process")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", busy_twice)
    _add(root, "A")
    assert len(calls) == 3 and not _lock(root).exists()


def test_a_lock_that_cannot_be_removed_is_reported_and_does_not_fail_the_work(root, monkeypatch, capsys):
    real_unlink = os.unlink

    def stuck(path, *args, **kwargs):
        if str(path).endswith("queue.lock"):
            raise PermissionError(32, "simulated: the file is in use by another process")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(jobs.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(os, "unlink", stuck)
    _add(root, "A")                                # the job is saved: no exception
    err = capsys.readouterr().err
    monkeypatch.undo()
    assert "could not remove" in err and "queue.lock" in err and "simulated" in err
    assert _lock(root).exists()                    # left behind; it is broken once it is 120 s old
    _lock(root).unlink()
    assert jobs.get(root, "A")["status"] == "ready"


def test_a_queue_file_with_a_byte_order_mark_still_loads(root):
    _add(root, "A")
    _queue(root).write_bytes(codecs.BOM_UTF8 + _queue(root).read_bytes())   # what Notepad adds on save
    assert jobs.get(root, "A")["status"] == "ready"
    _add(root, "B")                                # the next write is fine, and carries no mark
    assert not _queue(root).read_bytes().startswith(codecs.BOM_UTF8)
    assert [j["id"] for j in jobs.list_jobs(root)] == ["A", "B"]


# ---------------------------------------------------------------- the jobs themselves

def test_a_new_job_starts_ready_and_empty(root):
    _add(root, "A", deps=["Z"])
    job = jobs.get(root, "A")
    assert set(job) == {"id", "title", "brief", "type", "who", "depends_on", "status", "holder",
                        "branch", "since", "notes"}
    assert job["status"] == "ready" and job["holder"] is None and job["branch"] is None
    assert job["notes"] == [] and job["depends_on"] == ["Z"] and job["since"]
    with pytest.raises(jobs.JobError, match="NOPE"):
        jobs.get(root, "NOPE")


GOOD = {"id": "A", "title": "T", "brief": "b.md", "type": "build", "who": "either", "depends_on": []}


@pytest.mark.parametrize("bad", [
    {"id": ""}, {"id": "has space"}, {"id": "a|b"}, {"id": "../x"}, {"id": "-lead"},
    {"who": "nobody"}, {"type": "nonsense"},
    {"title": ""}, {"title": "two\nlines"}, {"brief": ""}, {"brief": "tab\there"},
    {"depends_on": "A"}, {"depends_on": [3]}, {"depends_on": ["A"]},       # a string, a number, itself
    {"status": "merged"}, {"holder": "me"},                                # not settable on add
])
def test_add_rejects_malformed_jobs_and_writes_nothing(root, bad):
    with pytest.raises(jobs.JobError):
        jobs.add(root, {**GOOD, **bad})
    assert jobs.list_jobs(root) == []


def test_add_rejects_a_missing_field(root):
    for key in ("id", "title", "brief", "type", "who"):
        with pytest.raises(jobs.JobError, match=key):
            jobs.add(root, {k: v for k, v in GOOD.items() if k != key})
    jobs.add(root, {k: v for k, v in GOOD.items() if k != "depends_on"})   # depends_on is optional
    assert jobs.get(root, "A")["depends_on"] == []


def test_a_dependency_not_in_the_queue_is_accepted_but_never_clears_until_it_is_merged(root):
    _add(root, "B", who="hermes", deps=["A"])                             # A is not in the queue yet
    assert jobs.next_job(root, "hermes", "H") is None
    _add(root, "A", who="claude")                                         # adding it later is fine
    assert jobs.next_job(root, "hermes", "H") is None                     # B still waits for A's merge


def test_next_checks_who_and_the_caller_name(root):
    _add(root, "A")
    with pytest.raises(jobs.JobError):
        jobs.next_job(root, "either", "X")                                # the caller is one of two
    with pytest.raises(jobs.JobError):
        jobs.next_job(root, "hermes", "  ")                               # a holder name is required


@pytest.mark.parametrize("name", ["a\tb", "a\nb", "tab\t", "a" + chr(13) + "b", "x" + chr(0)])
def test_a_holder_name_must_be_one_line(root, name, capsys):
    """--as NAME is stored, and printed in lines that other tools split on tabs."""
    _add(root, "A", who="hermes")
    with pytest.raises(jobs.JobError, match="holder name"):
        jobs.next_job(root, "hermes", name)
    with pytest.raises(jobs.JobError, match="holder name"):
        jobs.claim(root, "A", name)
    assert jobs.main(["next", "--for", "hermes", "--as", name]) == 1
    assert "holder name" in capsys.readouterr().err
    assert jobs.get(root, "A")["status"] == "ready" and jobs.get(root, "A")["holder"] is None


# ---------------------------------------------------------------- render, main_root

def test_render_escapes_cells_and_flags_a_dependency_that_is_not_in_the_queue(root):
    _add(root, "A", title="has | pipe", deps=["GHOST"])
    md = jobs.render(root)
    assert "has \\| pipe" in md and "GHOST (not in queue)" in md
    assert "| id | title | who | status | holder | branch | depends on | brief |" in md
    assert "generated" in md.lower()


def test_main_root_prefers_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("UC_JOBS_ROOT", str(tmp_path))
    assert jobs.main_root() == tmp_path


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
                   cwd=cwd, check=True, capture_output=True)


def test_main_root_from_a_linked_worktree_is_the_main_checkout_not_the_worktree(tmp_path, monkeypatch):
    """The queue must be one file for every worktree, so asked from inside a linked worktree main_root has
    to name the MAIN checkout. A wrong answer (--show-toplevel, or the folder of the worktree's own git
    directory) is still right when asked from the main checkout, so it needs a real linked worktree."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    for name in [k for k in os.environ if k.startswith("GIT_")]:     # a git hook's variables redirect git
        monkeypatch.delenv(name)
    monkeypatch.delenv("UC_JOBS_ROOT", raising=False)
    nothing = tmp_path / "empty-gitconfig"                          # keep the machine's git settings out
    nothing.write_text("")                                          # of the fixture: signing, hooks, ...
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(nothing))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    main = tmp_path / "main checkout"                               # with a space, like the real folder
    main.mkdir()
    _git(main, "init", "-q")
    _git(main, "commit", "-q", "--allow-empty", "-m", "first")
    linked = tmp_path / "linked worktree"
    _git(main, "worktree", "add", "-q", "--detach", str(linked))
    (linked / "tools").mkdir()

    monkeypatch.setattr(jobs, "HERE", linked / "tools")             # as if jobs.py lived in the worktree
    assert jobs.main_root().samefile(main)
    assert not jobs.main_root().samefile(linked)
    monkeypatch.setattr(jobs, "HERE", main)                         # and in the main checkout itself
    assert jobs.main_root().samefile(main)
