"""What tools/jobs.py promises beyond the nine tests in test_jobs.py.

The brief's nine tests cover the happy paths. These cover the rest of what the brief specifies and
what Hermes will depend on: the CLI's output and exit codes, block/unblock, the lock's two time
limits (10 s wait, 120 s stale), atomic writes, input validation, and no lost update under real
contention. Every test works in tmp_path through UC_JOBS_ROOT; none touches the real queue.
"""
import json
import os
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


def test_cli_runs_as_a_script_and_survives_a_console_that_cannot_encode_a_title(root):
    env = {**os.environ, "UC_JOBS_ROOT": str(root), "PYTHONIOENCODING": "ascii"}
    script = [sys.executable, str(Path(jobs.__file__)), ]
    empty = subprocess.run(script + ["next", "--for", "hermes", "--as", "H"], env=env,
                           capture_output=True, text=True)
    assert empty.returncode == 3 and empty.stdout == ""
    _add(root, "A", who="hermes", title="Fix → ✓ café")
    listed = subprocess.run(script + ["list"], env=env, capture_output=True, text=True)
    assert listed.returncode == 0 and listed.stdout.startswith("A\tready\thermes\t")
    taken = subprocess.run(script + ["next", "--for", "hermes", "--as", "H"], env=env,
                           capture_output=True, text=True)
    assert taken.returncode == 0 and taken.stdout == "A\tb/A.md\thermes/A\n"


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


# ---------------------------------------------------------------- render, main_root

def test_render_escapes_cells_and_flags_a_dependency_that_is_not_in_the_queue(root):
    _add(root, "A", title="has | pipe", deps=["GHOST"])
    md = jobs.render(root)
    assert "has \\| pipe" in md and "GHOST (not in queue)" in md
    assert "| id | title | who | status | holder | branch | depends on | brief |" in md
    assert "generated" in md.lower()


def test_main_root_prefers_the_environment_then_asks_git_for_the_main_checkout(monkeypatch, tmp_path):
    monkeypatch.setenv("UC_JOBS_ROOT", str(tmp_path))
    assert jobs.main_root() == tmp_path
    monkeypatch.delenv("UC_JOBS_ROOT")
    try:
        top = jobs.main_root()
    except jobs.JobError:
        pytest.skip("not inside a git checkout")
    assert (top / ".git").is_dir()               # the main checkout, even when run from a worktree
