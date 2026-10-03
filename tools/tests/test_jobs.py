import json
import multiprocessing as mp
import os
import time

import pytest

from tools import jobs


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("UC_JOBS_ROOT", str(tmp_path))
    return tmp_path


def _add(root, jid, who="either", deps=()):
    jobs.add(root, {"id": jid, "title": jid, "brief": f"b/{jid}.md", "type": "build", "who": who,
                    "depends_on": list(deps)})


def test_next_respects_who_and_order(root):
    _add(root, "A", who="claude"); _add(root, "B", who="hermes"); _add(root, "C")
    assert jobs.next_job(root, "hermes", "Hermes")["id"] == "B"
    assert jobs.next_job(root, "hermes", "Hermes")["id"] == "C"
    assert jobs.next_job(root, "hermes", "Hermes") is None
    assert jobs.next_job(root, "claude", "Claude")["id"] == "A"


def test_next_waits_for_merged_dependencies(root):
    _add(root, "A", who="claude"); _add(root, "B", who="hermes", deps=["A"])
    assert jobs.next_job(root, "hermes", "Hermes") is None
    jobs.claim(root, "A", "Claude"); jobs.done(root, "A", "claude/A"); jobs.review(root, "A", True, "")
    assert jobs.next_job(root, "hermes", "Hermes")["id"] == "B"


def test_claim_sets_holder_branch_and_time(root):
    _add(root, "A", who="hermes")
    job = jobs.next_job(root, "hermes", "Hermes")
    assert job["status"] == "claimed" and job["holder"] == "Hermes"
    assert job["branch"] == "hermes/A" and job["since"]


def test_transitions_and_errors(root):
    _add(root, "A")
    with pytest.raises(jobs.JobError):
        jobs.done(root, "A", "x")                      # not claimed
    jobs.claim(root, "A", "Claude")
    jobs.done(root, "A", "claude/A")
    jobs.review(root, "A", False, "fix the test name")
    assert jobs.get(root, "A")["status"] == "changes-requested"
    assert "fix the test name" in jobs.get(root, "A")["notes"][-1]
    jobs.done(root, "A", "claude/A")
    jobs.review(root, "A", True, "")
    assert jobs.get(root, "A")["status"] == "merged"
    with pytest.raises(jobs.JobError):
        jobs.release(root, "A")                        # merged is final


def test_duplicate_id_and_bad_fields_rejected(root):
    _add(root, "A")
    with pytest.raises(jobs.JobError):
        _add(root, "A")
    with pytest.raises(jobs.JobError):
        jobs.add(root, {"id": "B", "title": "B", "brief": "b", "type": "nonsense", "who": "either",
                        "depends_on": []})


def _grab(root_str, out_q):
    os.environ["UC_JOBS_ROOT"] = root_str
    from pathlib import Path
    job = jobs.next_job(Path(root_str), "hermes", f"H{os.getpid()}")
    out_q.put(job["id"] if job else None)


def test_two_processes_never_claim_the_same_job(root):
    for i in range(6):
        _add(root, f"J{i}", who="hermes")
    ctx = mp.get_context("spawn"); q = ctx.Queue()
    procs = [ctx.Process(target=_grab, args=(str(root), q)) for _ in range(6)]
    for p in procs: p.start()
    for p in procs: p.join(30)
    got = [q.get(timeout=5) for _ in procs]
    assert sorted(got) == [f"J{i}" for i in range(6)]


def test_stale_lock_is_broken(root, monkeypatch):
    lock = root / "data" / "jobs" / "queue.lock"
    lock.parent.mkdir(parents=True, exist_ok=True); lock.write_text("999999")
    old = time.time() - 3600; os.utime(lock, (old, old))
    _add(root, "A")                                    # must not time out
    assert jobs.get(root, "A")["status"] == "ready"


def test_render_writes_a_row_per_job(root):
    _add(root, "A", who="claude"); _add(root, "B", who="hermes", deps=["A"])
    md = jobs.render(root)
    assert "| A |" in md and "| B |" in md and "hermes" in md and "A" in md
    assert (root / "docs" / "superpowers" / "records" / "QUEUE.md").read_text(encoding="utf-8") == md


def test_cli_next_exit_code_3_when_empty(root, capsys):
    assert jobs.main(["next", "--for", "hermes", "--as", "Hermes"]) == 3
