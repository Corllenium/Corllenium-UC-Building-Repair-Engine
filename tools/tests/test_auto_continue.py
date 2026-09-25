"""The runner that hands a Claude job to Hermes while Claude is at its usage limit.

Every test here runs without Gemini: the end-to-end tests launch a fake Hermes (a small Python
script) in a throwaway git repository.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools import auto_continue as ac

TZ = dt.timezone(dt.timedelta(hours=8))


def at(h, m=0, day=25):
    return dt.datetime(2026, 9, day, h, m, tzinfo=TZ)


CLAIMS = (
    "# WORK CLAIMS\r\n"
    "\r\n"
    "| Job | Brief | Tree / branch | Holder | Since | Status |\r\n"
    "|---|---|---|---|---|---|\r\n"
    "| Review of brief 10 | read-only | committed state dc24e9a | - | 2026-09-25 18:40 | DONE: review |\r\n"
    "| Re-review round 3 | read-only | committed state da8ba85 | Claude subagent (re-review 3) | 2026-09-25 18:50 | running |\r\n"
    "| Remaining visual defects | briefs/11-remaining.md | main checkout / feat-dashboard | Claude subagent (brief 11) | 2026-09-25 17:45 | running |\r\n"
    "| Leftovers | briefs/06-leftovers.md | main checkout | - | queued | any time a slot is free |\r\n"
)


def rows():
    return ac.parse_claims(CLAIMS)


def row_of(text, job):
    return next(r for r in ac.parse_claims(text) if r.job == job)


# --- the claims table -------------------------------------------------------------------------


def test_parse_claims_reads_every_job_row_and_skips_the_header():
    got = rows()
    assert [r.job for r in got] == ["Review of brief 10", "Re-review round 3",
                                    "Remaining visual defects", "Leftovers"]
    r = got[2]
    assert (r.brief, r.tree, r.holder, r.status) == (
        "briefs/11-remaining.md", "main checkout / feat-dashboard", "Claude subagent (brief 11)", "running")
    assert r.claude_running and not r.hermes_running
    assert not got[0].claude_running


def test_update_claim_rewrites_only_that_row_and_keeps_crlf():
    out = ac.update_claim(CLAIMS, "Remaining visual defects", holder="Hermes (auto-continue)",
                          since="2026-09-25 23:10", status="running (auto-continue run x)")
    old, new = CLAIMS.split("\r\n"), out.split("\r\n")
    assert len(old) == len(new)
    assert [i for i, (a, b) in enumerate(zip(old, new)) if a != b] == [6]
    assert new[6] == ("| Remaining visual defects | briefs/11-remaining.md | main checkout / feat-dashboard"
                      " | Hermes (auto-continue) | 2026-09-25 23:10 | running (auto-continue run x) |")


def test_update_claim_keeps_the_table_intact_when_a_value_holds_a_pipe():
    out = ac.update_claim(CLAIMS, "Leftovers", holder="-", since="x", status="a | b")
    assert len(ac.parse_claims(out)) == 4
    assert row_of(out, "Leftovers").status == "a / b"


def test_update_claim_of_an_unknown_job_raises():
    with pytest.raises(KeyError):
        ac.update_claim(CLAIMS, "No such job", holder="-", since="x", status="y")


# --- reading Claude's state from its transcripts ------------------------------------------------


@pytest.mark.parametrize("when, hit, expected", [
    ("8:40pm (Asia/Singapore)", at(18, 52), at(20, 40)),
    ("10:40am (Asia/Singapore)", at(21, 5), at(10, 40, day=26)),
    ("11:30pm", at(13, 40), at(23, 30)),
    ("3pm", at(9, 0), at(15, 0)),
    ("12:10am", at(22, 0), at(0, 10, day=26)),
    ("Oct 1, 9am (Asia/Singapore)", at(21, 0), dt.datetime(2026, 10, 1, 9, 0, tzinfo=TZ)),
])
def test_parse_reset_reads_the_time_in_the_limit_message(when, hit, expected):
    assert ac.parse_reset(when, hit) == expected


def test_parse_reset_gives_none_for_text_it_cannot_read():
    assert ac.parse_reset("soon", at(9)) is None


def entry(kind, when, text="", **extra):
    stamp = when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    d = {"type": kind, "timestamp": stamp,
         "message": {"role": kind, "content": [{"type": "text", "text": text}]}}
    d.update(extra)
    return json.dumps(d)


def limit_entry(when, resets="1:40am"):
    return entry("assistant", when, f"You've hit your session limit \u00b7 resets {resets} (Asia/Singapore)",
                 isApiErrorMessage=True, error="rate_limit")


def write_transcript(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_scan_entries_finds_the_newest_limit_hit_and_the_newest_real_activity():
    lines = [
        entry("user", at(22, 0), "tool result"),
        entry("assistant", at(22, 5), "working"),
        entry("assistant", at(22, 6), "API Error: stream timeout", isApiErrorMessage=True, error="unknown"),
        limit_entry(at(22, 10)),
        "not json",
    ]
    limit, activity = ac.scan_entries(lines, TZ)
    assert activity == at(22, 5)
    assert limit.at == at(22, 10)
    assert limit.kind == "session"
    assert limit.resets_at == at(1, 40, day=26)


def test_read_claude_state_takes_the_newest_signals_across_session_and_agent_transcripts(tmp_path):
    proj = tmp_path / "projects"
    write_transcript(proj / "s1.jsonl", [entry("assistant", at(22, 0), "x"), limit_entry(at(22, 10))])
    write_transcript(proj / "s1" / "subagents" / "agent-a.jsonl",
                     [entry("user", at(22, 8), "r"), limit_entry(at(22, 11))])
    st = ac.read_claude_state(proj, TZ)
    assert st.limit.at == at(22, 11)
    assert st.last_activity == at(22, 8)
    assert st.at_limit(at(22, 40))
    assert not st.at_limit(at(1, 41, day=26))  # the window has reset


def test_activity_after_the_limit_hit_means_claude_is_back(tmp_path):
    proj = tmp_path / "projects"
    write_transcript(proj / "s1.jsonl", [limit_entry(at(22, 10)), entry("user", at(1, 45, day=26), "continue"),
                                         entry("assistant", at(1, 46, day=26), "ok")])
    st = ac.read_claude_state(proj, TZ)
    assert not st.at_limit(at(1, 50, day=26))


# --- deciding -----------------------------------------------------------------------------------

CFG = ac.Config()


def eligible(r):
    return r.brief.startswith("briefs/")


def state(limit_at=None, resets_at=None, activity=None):
    lim = ac.LimitHit(at=limit_at, kind="session", resets_at=resets_at) if limit_at else None
    return ac.ClaudeState(limit=lim, last_activity=activity)


CUT = state(at(22, 10), at(1, 40, day=26), at(22, 9))


def test_no_transcript_at_all_means_no_action():
    # a wrong projects folder must never read as "Claude silent for ever"
    d = ac.decide(rows(), state(), at(22, 25), 0.0, CFG, eligible)
    assert d.action == "none" and "transcript" in d.reason


def test_nothing_happens_while_claude_is_working():
    d = ac.decide(rows(), state(activity=at(22, 30)), at(22, 35), 0.0, CFG, eligible)
    assert d.action == "none" and "active" in d.reason


def test_waits_a_grace_period_after_the_limit_hit():
    d = ac.decide(rows(), CUT, at(22, 15), 0.0, CFG, eligible)
    assert d.action == "none" and "grace" in d.reason


def test_leaves_the_job_to_claude_when_the_reset_is_near():
    cut = state(at(0, 50, day=26), at(1, 40, day=26), at(0, 49, day=26))
    d = ac.decide(rows(), cut, at(1, 5, day=26), 0.0, CFG, eligible)
    assert d.action == "none" and "back in 35 min" in d.reason


def test_takes_over_the_running_implementation_job_when_claude_is_out():
    d = ac.decide(rows(), CUT, at(22, 25), 0.0, CFG, eligible)
    assert d.action == "takeover" and d.row.job == "Remaining visual defects"


def test_never_hands_a_review_to_hermes():
    only_review = [r for r in rows() if r.job != "Remaining visual defects"]
    d = ac.decide(only_review, CUT, at(22, 25), 0.0, CFG, eligible)
    assert d.action == "none" and "Re-review round 3" in d.reason


def test_a_job_hermes_holds_by_hand_neither_blocks_the_takeover_nor_is_taken():
    # a hand-started Hermes row stays "running" until Claude releases it, which a cut Claude cannot do
    text = ac.update_claim(CLAIMS, "Leftovers", holder="Hermes", since="x", status="running (pass 5, by hand)")
    d = ac.decide(ac.parse_claims(text), CUT, at(22, 25), 0.0, CFG, eligible)
    assert d.action == "takeover" and d.row.job == "Remaining visual defects"
    text = CLAIMS.replace("| Claude subagent (brief 11) | 2026-09-25 17:45 | running |", "| - | 2026-09-25 17:45 | DONE |")
    text = ac.update_claim(text, "Leftovers", holder="Hermes", since="x", status="running (auto-ok)")
    assert ac.decide(ac.parse_claims(text), CUT, at(22, 25), 0.0, CFG, eligible).action == "none"


def test_the_daily_cap_stops_new_runs():
    d = ac.decide(rows(), CUT, at(22, 25), CFG.daily_cap_usd, CFG, eligible)
    assert d.action == "none" and "cap" in d.reason


def test_long_silence_without_a_limit_message_also_lapses_the_claim():
    assert ac.decide(rows(), state(activity=at(20, 0)), at(21, 31), 0.0, CFG, eligible).action == "takeover"
    assert ac.decide(rows(), state(activity=at(20, 0)), at(21, 29), 0.0, CFG, eligible).action == "none"


def test_a_queued_job_starts_only_when_marked_auto_ok():
    text = CLAIMS.replace("| Claude subagent (brief 11) | 2026-09-25 17:45 | running |", "| - | 2026-09-25 17:45 | DONE |")
    assert ac.decide(ac.parse_claims(text), CUT, at(22, 25), 0.0, CFG, eligible).action == "none"
    text = text.replace("any time a slot is free", "any time a slot is free (auto-ok)")
    d = ac.decide(ac.parse_claims(text), CUT, at(22, 25), 0.0, CFG, eligible)
    assert d.action == "start" and d.row.job == "Leftovers"


def test_the_stop_file_blocks_every_new_run():
    d = ac.decide(rows(), CUT, at(22, 25), 0.0, CFG, eligible, stopped=True)
    assert d.action == "none" and "STOP" in d.reason


def test_job_paths_resolve_the_brief_and_the_tree(tmp_path):
    repo = tmp_path / "repo"
    (repo / "docs/superpowers/records/briefs").mkdir(parents=True)
    (repo / "docs/superpowers/records/briefs/11-remaining.md").write_text("b")
    (repo / ".claude/worktrees/side").mkdir(parents=True)
    cfg = ac.Config(repo=repo)
    got = rows()
    assert ac.job_paths(cfg, got[2]) == (repo / "docs/superpowers/records/briefs/11-remaining.md", repo)
    assert ac.job_paths(cfg, got[1]) is None  # a read-only review
    assert ac.job_paths(cfg, got[3]) is None  # its brief file does not exist
    moved = dataclasses.replace(got[2], tree=".claude/worktrees/side / feat/side")
    assert ac.job_paths(cfg, moved)[1] == repo / ".claude/worktrees/side"


def test_a_job_whose_final_report_is_written_counts_as_done(tmp_path):
    # a finished agent's claim still reads "running" when Claude was cut before releasing it
    repo = tmp_path / "repo"
    (repo / "docs/superpowers/records/briefs").mkdir(parents=True)
    (repo / "docs/superpowers/records/briefs/11-remaining.md").write_text(
        "Source: brief 10's report `.superpowers/sdd/x/old-report.md`.\n\n"
        "## Finish\n\nSuite; both runs. Report\n`.superpowers/sdd/x/remaining-report.md`.\n")
    (repo / ".superpowers/sdd/x").mkdir(parents=True)
    (repo / ".superpowers/sdd/x/old-report.md").write_text("an earlier brief's report")
    cfg = ac.Config(repo=repo)
    job = rows()[2]
    assert not ac.job_done(cfg, job)  # only the brief's LAST named report is its own
    (repo / ".superpowers/sdd/x/remaining-report.md").write_text("done")
    assert ac.job_done(cfg, job)


def test_a_report_named_without_its_folder_is_looked_for_in_the_ledger_folders(tmp_path):
    repo = tmp_path / "repo"
    (repo / "docs/superpowers/records/briefs").mkdir(parents=True)
    (repo / "docs/superpowers/records/briefs/11-remaining.md").write_text("Finish as before, report\n`side-report.md`.\n")
    cfg = ac.Config(repo=repo)
    assert not ac.job_done(cfg, rows()[2])
    (repo / ".superpowers/sdd/2026-09-21-x").mkdir(parents=True)
    (repo / ".superpowers/sdd/2026-09-21-x/side-report.md").write_text("done")
    assert ac.job_done(cfg, rows()[2])


def test_spent_on_adds_each_runs_cost_and_assumes_one_when_the_usage_file_is_missing(tmp_path):
    runs = tmp_path / "runs"
    for rid, started, cost in [("a", at(9), 2.5), ("b", at(23), None), ("c", at(1, day=26), 4.0)]:
        (runs / rid).mkdir(parents=True)
        (runs / rid / "run.json").write_text(json.dumps({"started": started.isoformat()}))
        if cost is not None:
            (runs / rid / "usage.json").write_text(json.dumps(
                {"estimated_cost_usd": cost - 0.1, "total_including_auxiliary": {"estimated_cost_usd": cost}}))
    assert ac.spent_on(dt.date(2026, 9, 25), runs, assumed=6.0) == pytest.approx(8.5)


def test_the_prompt_carries_the_rules_that_protect_the_owner():
    p = ac.build_prompt(job="Remaining visual defects", brief="docs/superpowers/records/briefs/11-remaining.md",
                        run_id="0925-2225-b11", wt=Path("D:/r/.hermes/worktrees/auto-0925-2225-b11"),
                        branch="hermes/auto-0925-2225-b11", base="4019987abc",
                        carried=["engine/fixes/solidify.py"], why="Claude at its session limit",
                        max_minutes=150, out_dir=Path("D:/r/data/auto_continue/0925-2225-b11/out"))
    for must in ["hermes/auto-0925-2225-b11", "engine/fixes/solidify.py", "11-remaining.md",
                 '--skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"', "api tests", "OBJ FIXED RESULT",
                 "WORK-CLAIMS", "Hermes-Auto-Run: 0925-2225-b11", "hermes-auto/0925-2225-b11-report.md",
                 "git add -A"]:
        assert must in p, must


# --- end to end, with a fake Hermes -------------------------------------------------------------

FAKE_HERMES = r'''
import json, os, pathlib, subprocess, sys, time
args = sys.argv[1:]
prompt = args[args.index("-z") + 1]
wt = pathlib.Path(args[args.index("--in") + 1])
usage = pathlib.Path(args[args.index("--usage-file") + 1])
(usage.parent / "prompt_seen.txt").write_text(prompt, encoding="utf-8")
(usage.parent / "pythonpath_seen.txt").write_text(os.environ.get("PYTHONPATH", ""), encoding="utf-8")
if os.environ.get("FAKE_MODE") == "sleep":
    time.sleep(120)
(wt / "engine" / "done.py").write_text("x = 1\n")
subprocess.run(["git", "-C", str(wt), "add", "engine/done.py"], check=True)
subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", "fake item"], check=True)
usage.write_text(json.dumps({"completed": True, "failed": False,
                             "total_including_auxiliary": {"estimated_cost_usd": 1.25}}))
'''


def git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.delenv("FAKE_MODE", raising=False)
    repo = tmp_path / "repo"
    (repo / "docs/superpowers/records/briefs").mkdir(parents=True)
    (repo / "engine").mkdir()
    git(tmp_path, "init", "-q", "-b", "feat-dashboard", str(repo))
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    (repo / ac.CLAIMS).write_bytes(CLAIMS.encode("utf-8"))
    (repo / "docs/superpowers/records/briefs/11-remaining.md").write_text("# Brief 11\n")
    (repo / "engine/solidify.py").write_text("a = 1\n")
    (repo / "docker-compose.yml").write_text("v: 1\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    # the cut agent's work in progress, and another session's edit that must stay where it is
    (repo / "engine/solidify.py").write_text("a = 2  # wip\n")
    (repo / "engine/new_test.py").write_text("def test_x():\n    pass\n")
    (repo / "docker-compose.yml").write_text("v: 2\n")
    proj = tmp_path / "projects"
    write_transcript(proj / "s.jsonl", [entry("assistant", at(22, 9), "working"), limit_entry(at(22, 10))])
    fake = tmp_path / "fake_hermes.py"
    fake.write_text(FAKE_HERMES)
    return ac.Config(repo=repo, projects_dir=proj, hermes=[sys.executable, str(fake)],
                     runs_dir=tmp_path / "runs", tz=TZ)


def wait_for_exit(cfg, run, timeout=60.0):
    t0 = time.time()
    while ac.run_alive(run) and time.time() - t0 < timeout:
        time.sleep(0.2)


def test_takeover_runs_hermes_in_its_own_worktree_then_releases_the_claim(world):
    cfg = world
    repo = cfg.repo
    msg = ac.tick(cfg, now=at(22, 25))
    assert msg.startswith("takeover"), msg
    row = row_of((repo / ac.CLAIMS).read_text(encoding="utf-8"), "Remaining visual defects")
    assert row.holder == "Hermes (auto-continue)" and row.status.startswith("running")
    run = ac.load_active(cfg)
    wt = Path(run["wt"])
    # the job's work in progress went with it; the other session's edit did not
    assert (wt / "engine/solidify.py").read_text() == "a = 2  # wip\n"
    assert (wt / "engine/new_test.py").exists()
    assert (wt / "docker-compose.yml").read_text() == "v: 1\n"
    # the shared checkout's files are untouched
    assert (repo / "engine/solidify.py").read_text() == "a = 2  # wip\n"
    assert (repo / "docker-compose.yml").read_text() == "v: 2\n"
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "feat-dashboard"

    wait_for_exit(cfg, run)
    run_dir = Path(run["dir"])
    assert (run_dir / "prompt_seen.txt").read_text(encoding="utf-8") == (run_dir / "prompt.md").read_text(encoding="utf-8")
    assert (run_dir / "pythonpath_seen.txt").read_text(encoding="utf-8") == str(wt)

    msg = ac.tick(cfg, now=at(22, 35))
    assert msg.startswith("finished"), msg
    row = row_of((repo / ac.CLAIMS).read_text(encoding="utf-8"), "Remaining visual defects")
    assert row.holder == "-" and row.status.startswith("HERMES-AUTO DONE")
    assert run["branch"] in row.status and "1 commit" in row.status
    assert ac.load_active(cfg) is None
    assert ac.spent_on(dt.date(2026, 9, 25), cfg.runs_dir, 6.0) == pytest.approx(1.25)
    assert (repo / ac.LOG_MD).read_text(encoding="utf-8").count(run["run_id"]) >= 2
    assert "fake item" in git(repo, "log", "--format=%s", run["branch"])
    # the released job is not taken again while Claude is still out
    assert ac.tick(cfg, now=at(22, 40)).startswith("none")


def test_a_run_past_its_time_limit_is_ended_and_reported(world, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "sleep")
    cfg = world
    assert ac.tick(cfg, now=at(22, 25)).startswith("takeover")
    run = ac.load_active(cfg)
    assert ac.run_alive(run)
    msg = ac.tick(cfg, now=at(22, 25) + dt.timedelta(minutes=cfg.max_run_min + 1))
    assert msg.startswith("finished"), msg
    assert not ac.run_alive(run)
    row = row_of((cfg.repo / ac.CLAIMS).read_text(encoding="utf-8"), "Remaining visual defects")
    assert row.holder == "-" and row.status.startswith("HERMES-AUTO TIMEOUT")


def test_a_restarted_runner_still_knows_the_run_by_its_pid(world, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "sleep")
    cfg = world
    assert ac.tick(cfg, now=at(22, 25)).startswith("takeover")
    run = ac.load_active(cfg)
    ac._PROCS.clear()  # a new runner process knows the run only from run.json
    assert ac.run_alive(run)
    assert not ac.run_alive({**run, "image": "notepad.exe"})  # a reused pid is not our run
    assert ac.stop(cfg, kill=True, now=at(22, 30)).startswith("finished")
    t0 = time.time()
    while ac.run_alive(run) and time.time() - t0 < 10:
        time.sleep(0.2)
    assert not ac.run_alive(run)


def test_stop_with_kill_ends_the_run_and_blocks_new_ones(world, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "sleep")
    cfg = world
    assert ac.tick(cfg, now=at(22, 25)).startswith("takeover")
    run = ac.load_active(cfg)
    ac.stop(cfg, kill=True, now=at(22, 40))
    assert not ac.run_alive(run)
    row = row_of((cfg.repo / ac.CLAIMS).read_text(encoding="utf-8"), "Remaining visual defects")
    assert row.holder == "-" and row.status.startswith("HERMES-AUTO STOPPED")
    assert ac.tick(cfg, now=at(22, 45)).startswith("none")
