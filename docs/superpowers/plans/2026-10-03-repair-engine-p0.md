# UC Repair Engine — P0 Foundations Implementation Plan

> **For agentic workers:**
> - **Claude:** REQUIRED SUB-SKILL superpowers:subagent-driven-development.
> - **Hermes:** start at `HERMES.md`; it tells you which task of this plan is your job.
> - Steps use checkbox (`- [ ]`) syntax.

**Goal:** Lay the foundations the repair engine is built on:
- **rules and queue:** one rules source and a job queue that Claude and Hermes share;
- **source:** the CHECKPOINT-17 export frozen, indexed and inventoried into floor and element units;
- **census:** every unit measured, with timings;
- **Validator v0:** it enforces the owner's rule (textures there, problems solved, nothing visible deleted or covered).

**Architecture:**
- `tools/jobs.py` runs the shared queue, kept in the main checkout as `data/jobs/queue.json`.
- `AGENTS.md` is the single rules file; `HERMES.md` is Hermes's entry point.
- Skills and sub-agents live in `.claude/`.
- `engine/campus/` holds the source freeze, the group-path index, material look keys, the inventory, the SDK cross-check and the census.
- `engine/validate/` holds Validator v0.

Nothing in P0 changes how any model is fixed.

**Tech stack:** Python 3.12, numpy, shapely, trimesh + embreex (rays), Pillow, the SketchUp 2026 C SDK through ctypes, and pytest. psutil and scikit-learn are not installed; peak memory is read through the Windows API.

**Spec:** `docs/superpowers/specs/2026-10-03-uc-repair-engine-design.md` (approved 2026-10-03).

## Global Constraints

- **Rules.** `AGENTS.md` (Task 1) binds every agent. Until it is merged, `docs/superpowers/records/HANDOFF.md` §4 does.
- **Branches.**
  - Integration branch: `feat/repair-p0`, in the worktree `.claude/worktrees/repair-p0`, made from `feat-dashboard`.
  - Each job gets its own branch made from `feat/repair-p0`:
    - Claude: `claude/<job-id>` in `.claude/worktrees/<job-id>`;
    - Hermes: `hermes/<job-id>` in `.hermes/worktrees/<job-id>`.
  - Only the Claude controller merges a job branch, after review. `feat/repair-p0` merges into `feat-dashboard` at the end of P0.
- **Sources are read-only.**
  - **CKPT17 export,** `D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\01-MODEL-EXPORT\CKPT17\`: read ONLY through `engine/io/snapshot.py` (stable copy plus sha256). No `grep`, `head` or editor on it.
  - **The backup,** `D:\PROJECTS\UC MODEL FIXER\MODEL FIXER ENGINE FILES\02-SKETCHUP-MODELS\CHECKPOINT-17-BACKUP\`: hash it in place. The SDK opens only a verified COPY under `data/campus/skp_copy/` and never saves it.
  - **The master** `D:\PROJECTS\UC\02-SKETCHUP\current\…`: never.
- **Outputs.** P0 writes only `data/campus/`, `data/snapshots/` and `data/jobs/` (all git-ignored), plus the tracked docs this plan names. Nothing is written into `MODEL FIXER ENGINE FILES\` or `OBJ FIXED RESULT\`.
- **Python.** Use `PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"`, run from the worktree root in a subshell with `PYTHONPATH` set: `(cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m pytest <tests> -q -p no:cacheprovider)`.
- **Test suites.**
  - Engine: `engine/tests`.
  - Tools: `tools/tests`.
  - SketchUp tests skip when `SketchUpAPI.dll` is missing.
- **Test-first.** Write the test, run it and see it fail for the right reason, implement, see it pass, commit.
- **Commits.** Stage files by name; never `git add -A`. Every Claude message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (or the implementing model). Every Hermes message ends with `Hermes-Job: <job-id>`.
- **Never:** write to the live database `fixer`; stop, start or rebuild a container; use a blocked operation; write a file outside your worktree, except `data/` and your report.
- **Reports.**
  - Hermes: `docs/superpowers/records/hermes/<job-id>-report.md`, including the acceptance commands' real output.
  - Claude: the SDD ledger `.superpowers/sdd/2026-10-03-repair-engine-p0/progress.md`.

## File structure

| File | Responsibility | Task |
|---|---|---|
| `AGENTS.md` (create) | the single rules file: rules, blocked operations, owner decisions, validation rule, workflow | 1 |
| `CLAUDE.md` (create) | imports `AGENTS.md`, plus Claude-only working notes | 1 |
| `tools/jobs.py`, `tools/tests/test_jobs.py` (create) | the shared job queue and its tests | 2 |
| `.claude/skills/*/SKILL.md`, `.claude/agents/*.md` (create) | skills and sub-agents | 3, 16 |
| `HERMES.md` (modify), `docs/superpowers/records/briefs/TEMPLATE.md`, `docs/superpowers/records/hermes/README.md` (create) | Hermes entry point, brief template, report format | 4 |
| `docs/superpowers/records/QUEUE.md` (generated) | the queue, rendered for people | 2, 6 |
| `engine/io/snapshot.py` (modify) | public `copy_verified` wrapper | 7 |
| `engine/campus/source.py` | freeze the export and hash the backup → `data/campus/source.json` | 7 |
| `engine/campus/groups.py` | face → SketchUp group-path index from `CKPT17-CLEAN.obj` | 8 |
| `engine/campus/materials.py` | look keys (texture sha256 + Kd + d) → `data/campus/materials.json` | 9 |
| `engine/campus/inventory.py` | level tables, units, duplicates → `data/campus/campus_map.draft.json` | 10 |
| `engine/io/skp_reader.py`, `engine/campus/skp_check.py` | read-only SDK walk of the backup copy; compare it with the export | 11 |
| `engine/campus/census.py` | `find_errors` per unit, with timings and memory → `data/campus/census.json` | 12 |
| `engine/validate/{sampling,viewpoints,visibility,checks,evidence}.py` | Validator v0 | 14-16 |
| `engine/cli.py` (modify) | `campus-freeze`, `campus-index`, `campus-materials`, `campus-inventory`, `campus-skp-check`, `census`, `validate` | 7-16 |

## Jobs: who may take each task

| Task | Job id | Who | Depends on |
|---|---|---|---|
| 1 Rules source | P0-01 | claude | — |
| 2 Job queue | P0-02 | claude | — |
| 3 Skills + agents | P0-03 | claude | P0-01 |
| 4 Hermes entry + brief template | P0-04 | claude | P0-01, P0-02 |
| 5 Worktree hygiene | P0-05 | claude | — |
| 6 Queue the jobs; first Hermes session | P0-06 | claude + owner | P0-02, P0-04 |
| 7 Source freeze | P0-07 | either | P0-06 |
| 8 Group-path index | P0-08 | **hermes** | P0-07 |
| 9 Material look keys | P0-09 | **hermes** | P0-07 |
| 10 Inventory | P0-10 | claude | P0-08, P0-09 |
| 11 SDK cross-check | P0-11 | claude | P0-07 |
| 12 Census | P0-12 | either | P0-09 |
| 13 Owner decision sheet | P0-13 | claude | P0-10, P0-11, P0-12 |
| 14 Validator core | P0-14 | claude | P0-09 |
| 15 Validator checks + CLI | P0-15 | claude | P0-14 |
| 16 Mutation proof, real verdicts, agent | P0-16 | claude | P0-15 |

**Order:** 1, 2 and 5 → 3 and 4 → 6 → 7 → (8 ∥ 9 ∥ 11) → (10 ∥ 12 ∥ 14) → 13 and 15 → 16.

---

### Task 1: one rules source — `AGENTS.md` and `CLAUDE.md` (claude)

**Files:**
- Create: `AGENTS.md`, `CLAUDE.md`, `tools/tests/test_agents_md.py`.
- Modify: `docs/superpowers/records/HANDOFF.md` §4 (the rules list becomes a link), `HERMES.md` §2 (the blocked operations become a link).

**`AGENTS.md` sections** (plain markdown; every agent reads it):
1. **What this project is.** 3 lines: Little Tiles → SketchUp CHECKPOINT-17 → OBJ → Unity (double-sided, `_Cull = 0`).
2. **Where things are.** The repo layout, `data/`, the export (read-only), the backup (read-only), the master (never), `MODEL FIXER ENGINE FILES\` (the owner's), `OBJ FIXED RESULT\` (committed code only).
3. **Binding rules.** HANDOFF §4's list, moved here VERBATIM; HANDOFF §4 then links here.
4. **Blocked operations.** Weld above 0.1 mm, `select_interior_faces`, Fill Holes, Make Manifold, Decimate or remeshing, dissolve above 5°, opposite-normal coincident pairs as duplicates (brief 13 is the only exception), whole-campus jobs. Plus the 2026-10-03 owner exceptions: the E5 cut along the winner's border, and the narrow E8 flat fill.
5. **Owner decisions of 2026-10-03.** The spec's decisions table, verbatim.
6. **The owner's validation rule.** The three checks, the viewpoints (outside, and eye height inside), the strict visible rule.
7. **How work flows.**
   - The queue: `tools/jobs.py`.
   - Briefs, with acceptance commands.
   - One branch and worktree per job.
   - Reports with real test output.
   - Only Claude merges, after review.
   - Records.
8. **Commands.** Python and the test suites (from Global Constraints).

- [ ] **Step 1: Write the failing test** (`tools/tests/test_agents_md.py`):

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MUST = [
    "Weld above 0.1 mm", "select_interior_faces", "Fill Holes", "Make Manifold", "Decimate",
    "whole-campus jobs", "every facade texture is still there", "the problems are solved",
    "nothing visible to the eye was deleted or covered", "eye height", "_Cull = 0",
    "Only `engine/fixes/solidify.py` may invent vertices", "tools/jobs.py",
]


def test_agents_md_holds_every_binding_rule():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    missing = [m for m in MUST if m not in text]
    assert not missing, missing


def test_claude_md_imports_agents_md():
    assert "@AGENTS.md" in (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def test_handoff_rules_point_to_agents_md():
    text = (ROOT / "docs/superpowers/records/HANDOFF.md").read_text(encoding="utf-8")
    assert "AGENTS.md" in text
```

- [ ] **Step 2: Run it** (`-m pytest tools/tests/test_agents_md.py`). Expected: 3 failures (missing files).
- [ ] **Step 3: Write `AGENTS.md`, `CLAUDE.md` and the two links.** `CLAUDE.md` holds:
  - `@AGENTS.md` on its first line;
  - subagent-driven development: ledgers under `.superpowers/sdd/<plan>/`, force-added;
  - the records to update after each step.
- [ ] **Step 4: Run it again.** Expected: 3 passed.
- [ ] **Step 5: Commit.** `docs(rules): AGENTS.md is the single rules source for Claude, Hermes and every agent`.

### Task 2: the shared job queue — `tools/jobs.py` (claude)

**Files:** Create `tools/jobs.py` and `tools/tests/test_jobs.py`.

**Interfaces (produced, used by Tasks 4 and 6 and by Hermes):**
- **Queue file.** `<main checkout>/data/jobs/queue.json`, found through `git rev-parse --path-format=absolute --git-common-dir`. The environment variable `UC_JOBS_ROOT` overrides it in tests.
- **Schema.** `{"version": 1, "jobs": [Job]}`, where each Job is:
  - `id`, `title`, `brief` (path, may end `#task-N`);
  - `type` ∈ build | run | validate | research | docs;
  - `who` ∈ claude | hermes | either;
  - `depends_on` (list of ids);
  - `status` ∈ ready | claimed | awaiting-review | changes-requested | merged | blocked;
  - `holder`, `branch`, `since`, `notes` (list of strings).
- **Transitions** (anything else raises `JobError`):
  - ready → claimed (`next`, `claim`);
  - claimed or changes-requested → awaiting-review (`done`);
  - claimed or changes-requested → ready (`release`);
  - awaiting-review → merged (`review --pass`) or changes-requested (`review --changes NOTE`);
  - any → blocked (`block NOTE`); blocked → ready (`unblock`).
- **CLI:**
  - `list [--status S] [--for W]`;
  - `next --for {claude,hermes} --as NAME`, which prints `<id>\t<brief>\t<branch>`, or exits 3 when no job is eligible;
  - `claim ID --as NAME`;
  - `done ID [--branch B]`, `release ID`;
  - `review ID (--pass | --changes NOTE)`;
  - `block ID NOTE`, `unblock ID`;
  - `add ID --title T --brief B --type T --who W [--depends a,b]`;
  - `render`, which writes `docs/superpowers/records/QUEUE.md` in the main checkout.
- **Eligibility for `next`:** status `ready`; `who` equal to the caller or `either`; every dependency `merged`. Jobs are taken in queue order.
- **Lock:**
  - `data/jobs/queue.lock` is created with `O_CREAT | O_EXCL`;
  - the wait gives up after 10 s;
  - a lock older than 120 s is stale and is broken;
  - writes are atomic (a temp file, then `os.replace`).

- [ ] **Step 1: Write the failing tests** (`tools/tests/test_jobs.py`):

```python
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
```

- [ ] **Step 2: Run it** (`-m pytest tools/tests/test_jobs.py`). Expected: ImportError, because `tools/jobs.py` is missing.
- [ ] **Step 3: Implement `tools/jobs.py`.**
  - Functions: `main_root`, `Locked` (context manager), `load`, `save` (atomic), `add`, `get`, `next_job`, `claim`, `done`, `release`, `review`, `block`, `unblock`, `render`, `main(argv)`.
  - Each mutating function: take the lock, load, check the transition (raise `JobError` with the current status in the message), change, save.
  - Times: `datetime.now().astimezone().isoformat(timespec="minutes")`.
  - The branch name is `f"{who_taking}/{id}"`, where `who_taking` is the `--for` value.
  - `render` writes a markdown table: `| id | title | who | status | holder | branch | depends on | brief |`, with a header giving the time and saying the file is generated.
- [ ] **Step 4: Run it again.** Expected: 9 passed. Then run the whole `tools/tests` suite: nothing else breaks.
- [ ] **Step 5: Commit.** `feat(tools): a shared job queue that Claude and Hermes both claim from, under a file lock`.

### Task 3: skills and sub-agents (claude)

**Files:**
- Create the skills:
  - `.claude/skills/uc-repair-rules/SKILL.md`;
  - `.claude/skills/uc-handoff/SKILL.md`;
  - `.claude/skills/uc-run-unit/SKILL.md`.
- Create the sub-agents in `.claude/agents/`:
  - `engine-builder.md`, `unit-runner.md`;
  - `rules-reviewer.md`, `hermes-reviewer.md`;
  - `census-analyst.md`.
- `uc-validate-floor` and `floor-validator` come in Task 16; `uc-comparison-skp` and `skp-builder` come in P3.

**Skill format:** frontmatter with `name` and `description` (when to use it), then a short body that points to `AGENTS.md` sections, never copies them, plus checklists.
- `uc-repair-rules`: the pre-flight checklist before any engine change (the blocked operations, which guard a change touches, test-first, the strict visible rule).
- `uc-handoff`: how to take a job (`tools/jobs.py next`), make the worktree, write the report, hand back (`done`), and how Claude reviews.
- `uc-run-unit`: the CLI commands that exist after P0 (`campus-freeze`, `census`, `validate`) and where outputs go.

**Agent format:** Claude Code frontmatter (`name`, `description`, `tools`, `model`), then the role prompt. Every role prompt says:
- read `AGENTS.md` first;
- work only in your job's worktree;
- never dispatch sub-agents;
- report with real command output.

| Agent | Model | Tools | Job |
|---|---|---|---|
| engine-builder | sonnet | all but Agent | TDD on one brief |
| unit-runner | haiku | Bash, Read | runs CLI commands from a brief, never edits code |
| rules-reviewer | sonnet | Read, Grep, Bash (read-only git) | reviews a diff against `AGENTS.md` §3-6 |
| hermes-reviewer | sonnet | same as rules-reviewer | additionally re-runs the brief's acceptance commands; flags any change to `engine/guard/**`, `FixProfile` thresholds or existing tests |
| census-analyst | haiku | Read, Bash | summarises `census.json` |

- [ ] **Step 1: Write the failing test** (`tools/tests/test_claude_assets.py`). For each listed file: it exists; its frontmatter parses (split on the `---` lines; keys `name` and `description` exist; agents also have `model`); its body contains `AGENTS.md`.
- [ ] **Step 2: Run it.** It fails. **Step 3:** write the files. **Step 4:** it passes. **Step 5:** commit `docs(agents): project skills and sub-agent roles for the repair engine`.

### Task 4: Hermes entry point, brief template, report format (claude)

**Files:**
- Modify: `HERMES.md` §0.
- Create: `docs/superpowers/records/briefs/TEMPLATE.md`, `docs/superpowers/records/hermes/README.md`.
- Modify: `docs/superpowers/records/WORK-CLAIMS.md` header (new jobs live in `tools/jobs.py`; WORK-CLAIMS stays for the automatic runner until P5).

**New `HERMES.md` §0, "When the owner says: Read HERMES.md and do the next job":**
1. Read `AGENTS.md` completely.
2. From the main checkout: `"$PY" tools/jobs.py next --for hermes --as Hermes`. Exit code 3 means no job for you: say so and stop.
3. Make your worktree from the integration branch: `git worktree add -b hermes/<id> .hermes/worktrees/<id> feat/repair-p0`.
4. Open the brief the queue printed. Do each item in order, test first. Each item has "done when" lines with named tests.
5. Run every acceptance command of the brief and paste the real output into `docs/superpowers/records/hermes/<id>-report.md` (format: `hermes/README.md`).
6. Commit by name, with `Hermes-Job: <id>` at the end of each message.
7. `"$PY" tools/jobs.py done <id> --branch hermes/<id>`, then stop.
8. Never: merge; push; edit `engine/guard/**`, `FixProfile` thresholds or any existing test; touch the live database, the containers, the export (except through the snapshot functions) or the master; use a blocked operation. `delegate_task` children may only read.

**`briefs/TEMPLATE.md`:**
- Goal, why, and the job id.
- Files (create or modify), with the exact paths.
- Interfaces it consumes and produces.
- Items, each with: steps, tests to write (names and assertions), and "done when".
- Acceptance commands (copy-pasteable).
- Rules reminder: link `AGENTS.md`.
- Report path.

**`hermes/README.md`, the report format:**
- job id, branch, commits;
- per item: done or not, the tests added, and the real output;
- the acceptance command outputs;
- anything unsure, said plainly.

- [ ] **Step 1: Write the failing test** (`tools/tests/test_handover_docs.py`):
  - `HERMES.md` contains `tools/jobs.py next --for hermes` and `jobs.py done`;
  - `TEMPLATE.md` contains the headings `## Items` and `## Acceptance commands`;
  - `hermes/README.md` contains `## Acceptance command outputs`.
- [ ] **Steps 2-5:** see it fail, write the docs, see it pass, commit `docs(hermes): the entry point for an owner-started Hermes session, the brief template and the report format`.

### Task 5: worktree hygiene (claude)

- [ ] **Step 1:** `git worktree list --porcelain`. Note which entries say `prunable`.
- [ ] **Step 2:** `git worktree prune -v`. It removes only the admin records of worktree folders that no longer exist.
- [ ] **Step 3:** create the integration worktree: `git worktree add -b feat/repair-p0 .claude/worktrees/repair-p0 feat-dashboard`.
- [ ] **Step 4:** create the publishing worktree named in HANDOFF: `git worktree add --detach .claude/worktrees/verified feat-dashboard`. Run its engine suite once, from its root.
- [ ] **Step 5:** add both worktrees to HANDOFF §2 and the ledger. Commit (records only).

### Task 6: queue the P0 jobs and run the first Hermes session (claude + owner)

- [ ] **Step 1:** for every task 7-16, `tools/jobs.py add P0-<NN> --title … --brief docs/superpowers/plans/2026-10-03-repair-engine-p0.md#task-<N> --type … --who … --depends …`, exactly as in the Jobs table.
- [ ] **Step 2:** `tools/jobs.py render`, then commit `QUEUE.md`.
- [ ] **Step 3:** Claude takes P0-07 itself (`next --for claude`) and runs it (Task 7). P0-08 and P0-09 become eligible for Hermes when P0-07 is merged.
- [ ] **Step 4: Owner action.** Open Hermes desktop on `D:\PROJECTS\UC MODEL FIXER` and say: **"Read HERMES.md and do the next job."**
- [ ] **Step 5:** when Hermes runs `done`:
  - dispatch `hermes-reviewer` on `git diff feat/repair-p0...hermes/<id>` together with the report;
  - re-run the acceptance commands from the main checkout;
  - then `review --pass` and merge into `feat/repair-p0`, or `review --changes NOTE` with a fix brief.

  **Done when:** one Hermes branch has been reviewed and merged.

### Task 7: source freeze (either)

**Files:**
- Modify: `engine/io/snapshot.py`, adding a public `copy_verified(src, dst, interval_s=1.0, sleep=time.sleep)` that wraps `_copy_verified`.
- Create: `engine/campus/__init__.py`, `engine/campus/source.py`, `engine/tests/test_campus_source.py`.
- Modify: `engine/cli.py`, adding `campus-freeze`.

**Interface:**
```python
@dataclass
class SourceFreeze:
    json_path: Path
    snapshots: list[dict]      # {"file","group","tris","dir","sha256"} per split OBJ, manifest order
    clean_obj: Path            # frozen copy of CKPT17-CLEAN.obj
    clean_mtl: Path            # frozen copy of the shared MTL

def freeze_source(export_dir: Path, backup_dir: Path, out_root: Path, snapshots_root: Path,
                  interval_s: float = 1.0, sleep=time.sleep) -> SourceFreeze
```

**Behaviour:**
1. `rows = read_manifest_stable(export_dir / "split" / "_MANIFEST.txt", interval_s, sleep)`.
2. For each row in order: `snapshot_object(export_dir/"split"/row.file, snapshots_root, expected_tris=row.tris, …)`.
3. Copy `CKPT17-CLEAN.obj` and its MTL (the `.mtl` with the same stem) with `copy_verified` into `out_root/"source"/<sha256 of the OBJ copy, 12 characters>/`.
4. Copy every file of `SRC-TEX` with `copy_verified` into `…/SRC-TEX/` and hash the copies.
5. Hash `*.skp` and `*.skb` in `backup_dir` in place (sha256, size, mtime).
6. Write `out_root/"source.json"`: `created`, `export_dir`, `manifest` (rows), `snapshots`, `clean_obj {path, sha256}`, `clean_mtl {path, sha256}`, `textures {name: sha256}`, `backup {name: {sha256, size, mtime}}`, and `totals {files, tris}`.

The function never writes under `export_dir` or `backup_dir`.

- [ ] **Step 1: Write the failing tests** (`engine/tests/test_campus_source.py`):

```python
import json
import time
from pathlib import Path

import pytest

from engine.campus.source import freeze_source
from engine.io.snapshot import ManifestMismatch

OBJ = "mtllib ../X.mtl\no {name}\nv 0 0 0\nv 10 0 0\nv 0 10 0\nvt 0 0\nvt 1 0\nvt 0 1\nusemtl m0\nf 1/1 2/2 3/3\n"


def _export(tmp: Path, alpha_tris=1):
    exp = tmp / "CKPT17"; split = exp / "split"; tex = exp / "SRC-TEX"
    split.mkdir(parents=True); tex.mkdir()
    (exp / "X.mtl").write_text("newmtl m0\nKd 1 1 1\nmap_Kd SRC-TEX/a.png\n")
    (tex / "a.png").write_bytes(b"png-a")
    for name in ("Alpha", "Beta"):
        (split / f"{name}.obj").write_text(OBJ.format(name=name))
    (split / "_MANIFEST.txt").write_text(
        "file  tris  sketchup group\n" f"Alpha.obj  {alpha_tris}  Alpha\n" "Beta.obj  1  Beta\n")
    (exp / "CKPT17-CLEAN.obj").write_text("mtllib CKPT17-CLEAN.mtl\n" + OBJ.format(name="all"))
    (exp / "CKPT17-CLEAN.mtl").write_text("newmtl m0\nKd 1 1 1\nmap_Kd SRC-TEX/a.png\n")
    backup = tmp / "BACKUP"; backup.mkdir()
    (backup / "M.skp").write_bytes(b"skp"); (backup / "M.skb").write_bytes(b"skb")
    return exp, backup


def _listing(d: Path):
    return sorted((str(p.relative_to(d)), p.stat().st_size, p.stat().st_mtime_ns) for p in d.rglob("*"))


def test_freeze_writes_source_json_and_snapshots(tmp_path):
    exp, backup = _export(tmp_path)
    before = _listing(exp), _listing(backup)
    res = freeze_source(exp, backup, tmp_path / "campus", tmp_path / "snaps", interval_s=0, sleep=lambda s: None)
    data = json.loads(res.json_path.read_text())
    assert [s["file"] for s in data["snapshots"]] == ["Alpha.obj", "Beta.obj"]
    assert data["totals"] == {"files": 2, "tris": 2}
    assert data["textures"]["a.png"] and set(data["backup"]) == {"M.skp", "M.skb"}
    assert res.clean_obj.exists() and res.clean_obj.read_bytes() == (exp / "CKPT17-CLEAN.obj").read_bytes()
    assert (_listing(exp), _listing(backup)) == before          # sources untouched


def test_manifest_mismatch_raises(tmp_path):
    exp, backup = _export(tmp_path, alpha_tris=2)
    with pytest.raises(ManifestMismatch):
        freeze_source(exp, backup, tmp_path / "campus", tmp_path / "snaps", interval_s=0, sleep=lambda s: None)


def test_rerun_reuses_content_addressed_snapshots(tmp_path):
    exp, backup = _export(tmp_path)
    a = freeze_source(exp, backup, tmp_path / "campus", tmp_path / "snaps", interval_s=0, sleep=lambda s: None)
    b = freeze_source(exp, backup, tmp_path / "campus", tmp_path / "snaps", interval_s=0, sleep=lambda s: None)
    assert [s["dir"] for s in a.snapshots] == [s["dir"] for s in b.snapshots]
```

- [ ] **Step 2: Run it.** Expected: ImportError.
- [ ] **Step 3: Implement** `copy_verified`, `engine/campus/source.py` and the CLI `campus-freeze --export DIR --backup DIR --out data/campus --snapshots data/snapshots`.
- [ ] **Step 4: Run it.** The 3 tests pass, and the whole engine suite stays green.
- [ ] **Step 5: Real run** (read-only on the sources):

  ```
  "$PY" -m engine.cli campus-freeze --export "D:/PROJECTS/UC ENVIRONMENT BUILDING/REQUIREMENTS/01-MODEL-EXPORT/CKPT17" --backup "D:/PROJECTS/UC MODEL FIXER/MODEL FIXER ENGINE FILES/02-SKETCHUP-MODELS/CHECKPOINT-17-BACKUP" --out data/campus --snapshots data/snapshots
  ```

  **Done when:** `source.json` says `files` 85 and `tris` 1766906, and every snapshot's triangle count equals the manifest.
- [ ] **Step 6: Commit.** `feat(campus): freeze the CHECKPOINT-17 export and hash the backup into data/campus/source.json`.

### Task 8: face → group-path index (hermes)

**Files:** Create `engine/campus/groups.py` and `engine/tests/test_campus_groups.py`, plus the fixture `engine/tests/fixtures/campus/clean_sample.obj`. Add the CLI `campus-index`.

- [ ] **Step 1: Pin the format.**
  - Print the first 30 `g` lines and the 5 lines around the first `usemtl` of the FROZEN copy: `source.json` → `clean_obj.path`.
  - Write `clean_sample.obj` with 3 groups (one nested 3 deep, one automatic name such as `Group124`, one floor name with a space and a dot, such as `Eds 2nd Floor.obj`), copying the exact `g`-line syntax you printed.
  - Write the format, with 3 real example lines, at the top of `groups.py` as a comment.
- [ ] **Step 2: Port the naming rule.** It reproduced the split exactly (85/85 names and triangle counts). The owner's script is `C:\Users\Future26\AppData\Local\Temp\claude\D--PROJECTS-UC-Projects-feature-system-FEATURE-SYSTEM-MODEL-BUIILD\696b59e4-*\scratchpad\split_named.py` (read it; if it is gone, use this description):
  - ignore automatic names (`Group###`, `Mesh###`, `minecraft_*`, `littletiles_*` and the like);
  - take the outermost group whose name contains floor, side_walk, stair, bridge, roof, pathway or ground; if there is none, take the outermost named group;
  - the file name is the group name with spaces and dots replaced by `_`.
- [ ] **Step 3: Write the failing tests:**
  - `parse_group_paths(sample)` returns, per face in file order, the path tuple; check the nested group gives a 3-tuple;
  - `split_name(path)` follows the rule: the automatic name is skipped, `Eds 2nd Floor.obj` becomes `Eds_2nd_Floor_obj`;
  - `index_by_split(index)` groups the faces by split name and counts them;
  - a face before any `g` line gets the path `()` and the split name `unnamed`.
- [ ] **Step 4:** implement; the tests pass.
- [ ] **Step 5: Real run:** `campus-index --source data/campus/source.json --out data/campus/group_index.json`. **Done when:** for all 85 manifest files, the face count per split name equals the manifest's tris. Paste the comparison table (name, index count, manifest count) into the report.
- [ ] **Step 6: Commit.** `feat(campus): index every face of CKPT17-CLEAN.obj by its SketchUp group path`.

**Output format, `data/campus/group_index.json`:**
- `paths`: the list of path tuples;
- `faces`: a run-length list of `[path_id, first_face, count]` in clean-OBJ face order;
- `split`: `{split_name: {"tris": n, "paths": [path_id, …]}}`.

### Task 9: material look keys (hermes)

**Files:** Create `engine/campus/materials.py`, `engine/tests/test_campus_materials.py`. Add the CLI `campus-materials`.

**Interface:**
```python
def parse_kd_d(mat: MtlMaterial) -> tuple[tuple[float, float, float], float]   # defaults (1,1,1), 1.0
def look_key(tex_sha256: str | None, kd, d) -> str     # sha256(f"{tex or 'none'}|{kd rounded 4}|{d rounded 4}")[:16]
def build_materials(mtl_path: Path, tex_dir: Path) -> dict
```

`build_materials` returns:
- `materials`: `{name: {"map_kd": file or None, "tex_sha256": …, "kd": [..], "d": .., "look": key, "missing_texture": bool}}`;
- `looks`: `{key: [material names]}`;
- `stats`: `{"materials": n, "textured": n, "images": distinct tex_sha256, "looks": n}`.

- [ ] **Step 1: Write the failing tests:**
  - two materials with different names whose textures are the same bytes and whose Kd is equal → the same `look`;
  - Kd differs → a different look;
  - a missing texture file → `missing_texture: True`, and the look uses `"missing:<file>"` as its texture part;
  - `d` defaults to 1.0 when absent;
  - `stats` counts are right for a 4-material fixture.
- [ ] **Step 2:** see them fail. **Step 3:** implement, reusing `engine/io/mtl.py::parse_mtl` and parsing `Kd` and `d` from `mat.lines`. **Step 4:** they pass, and the engine suite is green.
- [ ] **Step 5: Real run:** `campus-materials --source data/campus/source.json --out data/campus/materials.json`, using the frozen MTL and SRC-TEX copies. **Done when:** the report shows `materials` 391 and `images` 86, prints `looks`, and lists the 10 largest look groups (names).
- [ ] **Step 6: Commit.** `feat(campus): material look keys, so visual checks compare texture + colour, not material numbers`.

### Task 10: inventory — levels, units, duplicates (claude)

**Files:** Create `engine/campus/inventory.py`, `engine/tests/test_campus_inventory.py`. Add the CLI `campus-inventory`.

**Algorithm:**
1. **Buildings.** Normalise the split names with a prefix table:

   | Prefix | Building |
   |---|---|
   | `CHTM`, `Chtm`, `chtm` | CHTM |
   | `EDS`, `Eds` | EDS |
   | `BRS` | BRS |
   | `Gymnasium` | GYMNASIUM |
   | `Main_Infrustructure` | MAIN_INFRA |
   | `MAIN`, `Main` | MAIN |
   | `PE` | PE |
   | `Sciene_A` | SCIENCE_A |
   | `Architecture`, `ARCHITECTURE` | ARCHITECTURE |
   | anything else | SITE |

   Check each group's footprint (XY bounding box) against its building's union. Flag any group whose footprint lies mostly in another building, such as `Main_Infrustructure_1st_floor`.
2. **Level table per building.**
   - Build a histogram of upward-facing area (`n_z > 0.9`) over z, in 1 in bins.
   - Peaks of at least 15 % of the building's largest peak are slab tops; merge peaks within 20 in.
   - `base` = the slab bottom: the nearest downward-facing area peak below, within 24 in.
3. **Units.**
   - A group whose faces' centre z falls inside one level band becomes a floor unit `Lnn`, numbered from the lowest band (L01).
   - A group spanning several bands gets a proposed split by face centre (no triangle is cut), recorded as `members: [{"group", "faces": "band k"}]`.
   - Groups whose names hold stair, bridge, roof, zone, shell, ground, pathway or road, and which span more than one band, become `element` or `site` units.
4. **Duplicates.**
   - Face fingerprint = the vertices snapped to the print step (from `coord_decimals`), sorted, plus the look key.
   - Take the Jaccard similarity between groups of the same building. Flag at least 0.25 with the percentage.
5. **Misnamed.** Compare the floor number parsed from the name (`1st`, `5ft`, `3RD`, `Floor 4`, `plan 2`) with the assigned `Lnn`, and flag differences.
6. **Missing.** A gap in a building's level sequence. Expected: SCIENCE_A L01.

**Output:**
- `data/campus/campus_map.draft.json`, per unit:
  - `unit`, `building`, `level`, `type`;
  - `members` (group, path ids, sha256 of the snapshot);
  - `tris`, `base`, `top`, `slab`;
  - `neighbours` (the unit ids just above and below);
  - `flags`;
  - `confirmed_by_owner: false`.
- `docs/superpowers/records/campus/campus-map-draft.md`: an owner-readable table plus the flag list.

- [ ] **Step 1: Write the failing tests**, on synthetic meshes:
  - 3 stacked slabs at z = 0, 200 and 400 in → 3 levels with the right bases;
  - one group holding 2 slabs → a split proposal with face counts per band;
  - two groups sharing 90 % of their faces → a duplicate flag of about 0.9;
  - a group named `X_9th_floor` assigned to the 8th band → a misnamed flag;
  - a missing middle level → a missing flag.
- [ ] **Steps 2-4:** see them fail, implement, see them pass.
- [ ] **Step 5: Real run.** **Done when:** every split file is in exactly one unit or proposal, and the known cases appear as flags: BRS_9th_obj1 → L08, the Science A duplicates of about 90 %, MAIN_BUILDING split into 2, Main_Infrustructure_Building split into 7, Science A L01 missing.
- [ ] **Step 6: Commit.** `feat(campus): inventory -- level tables, floor and element units, duplicates and misnamed levels for the owner to confirm`.

### Task 11: SDK cross-check, export against backup (claude)

**Files:** Create `engine/io/skp_reader.py`, `engine/campus/skp_check.py`, `engine/tests/test_skp_reader.py` (skipped without the DLL). Add the CLI `campus-skp-check`.

**Read-only SDK bindings** (copy the ctypes conventions of `engine/io/skp_writer.py`):
- model and entities: `SUModelCreateFromFile`, `SUModelGetEntities`;
- groups: `SUEntitiesGetNumGroups`, `SUEntitiesGetGroups`, `SUGroupGetName`, `SUGroupGetTransform`, `SUGroupGetEntities`;
- component instances: `SUEntitiesGetNumInstances`, `SUEntitiesGetInstances`, `SUComponentInstanceGetName`, `SUComponentInstanceGetTransform`, `SUComponentInstanceGetDefinition`, `SUComponentDefinitionGetName`, `SUComponentDefinitionGetEntities`;
- faces and vertices: `SUEntitiesGetNumFaces`, `SUEntitiesGetFaces`, `SUFaceGetArea`, `SUFaceGetNumVertices`, `SUFaceGetVertices`, `SUVertexGetPosition`;
- visibility: `SUDrawingElementGetHidden`;
- release: `SUModelRelease`, `SUStringCreate`, `SUStringGetUTF8`, `SUStringRelease`.

There is no save call in this module, and a test asserts that.

**Behaviour:**
- Copy the backup `.skp` to `data/campus/skp_copy/` with `copy_verified`, and check its sha256 equals `source.json`'s.
- In a subprocess (30 min timeout), walk the entities recursively, composing transforms. For every named group or instance, collect: world bounding box (from the transformed vertices), face area (scaled by the transform), face count and hidden flag.
- Compare with the export per split name, through Task 8's index:
  - bounding box within 2 × the print step;
  - area within 0.5 %.
- Write `data/campus/skp_check.json` (matches and mismatches) and a short markdown summary.

- [ ] **Step 1: Write the failing tests** (skipped without the DLL):
  - a model written by `skp_writer.write_skp` with 2 triangles reads back with the right face count and area;
  - `skp_reader` defines no function whose name contains `Save`;
  - the copy step refuses a sha256 mismatch.
- [ ] **Steps 2-4:** see them fail, implement, see them pass.
- [ ] **Step 5: Real run.** **Done when:** a mismatch list exists (possibly empty), with the reason for each mismatch.
- [ ] **Step 6: Commit.** `feat(campus): read-only SDK check that the export matches the CHECKPOINT-17 backup`.

### Task 12: census with timings (either)

**Files:**
- Create `engine/campus/census.py`, `engine/tests/test_campus_census.py`.
- Modify `engine/detectors/errors.py`: an optional `timings: dict | None = None` argument that records `perf_counter` per stage (topology, exposure, double_layers, fragments, assemble). The output is unchanged when it is None.
- Add the CLI `census`.

**Behaviour:**
- `census(units, out_json, jobs=4, timeout_s=1800)`. A unit here is a split snapshot until `campus_map` is confirmed.
- Each unit runs in a spawned process with `OMP_NUM_THREADS = MKL_NUM_THREADS = OPENBLAS_NUM_THREADS = 1`. It records:
  - `find_errors` counts;
  - stage timings;
  - peak memory (Windows `GetProcessMemoryInfo` → `PeakWorkingSetSize` through ctypes);
  - machine load at start and end: the count of other `python.exe` and `msedge.exe` processes, and the system CPU times through `GetSystemTimes`.
- Flicker split: pairs × {same look, different look} × {opposite, same facing}, using `materials.json`.
- A timeout writes `{"status": "timeout"}` for that unit.
- Outputs: `data/campus/census.json` and `docs/superpowers/records/campus/census.md` (a table: building, unit, triangles, each kind, seconds, peak MB).

- [ ] **Step 1: Write the failing tests:**
  - `find_errors(..., timings=t)` fills 5 stage keys and gives the same result as without it (on `two_sided_wall`);
  - the flicker split on `two_sided_wall` sums to the total pair count;
  - `census` on two fixture units writes both rows with `seconds` and `peak_mb`, and a `timeout_s` of 0.001 marks a unit as timeout.
- [ ] **Steps 2-4:** see them fail, implement, see them pass, and the engine suite stays green.
- [ ] **Step 5: Real run** on all 85 snapshots, `--jobs 4`. Record the machine load. **Done when:** every unit has counts or `timeout`, and the report names the 5 slowest units and the 5 with the highest peak memory.
- [ ] **Step 6: Commit.** `feat(campus): census of every unit with stage timings, peak memory and flicker split by look and winding`.

### Task 13: owner decision sheet (claude)

- [ ] Compile `docs/superpowers/records/campus/decision-sheet-p0.md`:
  - the level table per building;
  - multi-floor splits;
  - duplicates (which copy to keep);
  - misnamed and missing levels;
  - tint groups: materials with identical looks (from `materials.json`), and whether they count as one material for E4;
  - check-2 numeric targets per kind (proposal: flicker 0, reversed 0, hidden 0 except protected, zero-area 0, visible debris listed, cracks 0, open edges listed);
  - SDK cross-check mismatches.
- [ ] Ask the owner with AskUserQuestion, at most 4 questions per round. Write the answers into `data/campus/campus_map.json` (`confirmed_by_owner: true`) and `engine/validate/targets.json`. Commit the sheet with the answers.

### Task 14: Validator core — samples, viewpoints, visibility (claude)

**Files:** Create `engine/validate/__init__.py`, `sampling.py`, `viewpoints.py`, `visibility.py`, and `engine/tests/test_validate_core.py`.

**Interfaces:**
```python
def face_samples(mesh, faces=None, min_per_face=4, area_per_sample=36.0) -> Samples
#   Samples: points (N,3) float64, face (N,), bary (N,3); deterministic barycentric lattice
def uv_at(mesh, face: np.ndarray, bary: np.ndarray) -> np.ndarray          # (N,2), from uvs[face_vt]
def outside_directions(n=128) -> np.ndarray                                # Fibonacci, unit
def pedestrian_ring(bbox, eye_z, n=24, margin=240.0) -> np.ndarray         # camera positions
def interior_probes(mesh, eye=63.0, headroom=83.0, grid=39.37) -> np.ndarray
#   above every upward face (n_z > 0.9) whose upward ray from 0.5 in above meets nothing within `headroom`
def visible_samples(mesh, samples, dirs, cams, probes, caster) -> VisibleSet
#   for each sample: which viewpoints see it (escape toward -dir; clear segment to a camera or probe),
#   and whether that viewpoint sees the FRONT of the face (dot(normal, view) > 0)
```

Rays use `EmbreeCaster` on positions re-centred on the bounding-box centre (float32-safe). Depth and UV comparisons are float64.

- [ ] **Step 1: Write the failing tests:**
  - `face_samples` gives at least 4 samples per face, inside their triangles, and identical on a second call;
  - `uv_at` at a corner's barycentric weight returns that corner's UV;
  - on `cube()`, every outside face is visible from some direction, and the inside of a closed box with no opening is seen by no outside viewpoint;
  - **a closed room** (floor, 4 walls, ceiling; a new fixture appended at the END of `engine/tests/fixtures/build.py`) has interior probes, and they see all 4 inner wall faces;
  - a wall face whose front points away from every viewpoint is marked `back_seen`.
- [ ] **Steps 2-4:** see them fail, implement, see them pass. **Step 5:** commit `feat(validate): samples, viewpoints outside and at eye height inside, and visibility for the Validator`.

### Task 15: Validator checks 1-3, CLI, evidence (claude)

**Files:** Create `engine/validate/checks.py`, `engine/validate/evidence.py`, `engine/tests/test_validate_checks.py`. Add the CLI `validate`.

**Checks:**
- **Check 1, textures there.** For every visible BEFORE sample, cast from one of its viewpoints into AFTER. It passes when:
  - the hit depth is within `max(2 × print step, 0.05 in)`;
  - the look key is the same;
  - the UV is the same mod 1, within 1 texel of that texture (size read from the PNG header);
  - the front is seen wherever BEFORE's front was seen.
- **Check 2, problems solved.** `find_errors` BEFORE and AFTER, compared with `targets.json`. Until the owner signs the targets, every kind reports `"target": "unsigned"`, the counts and the residual locations, and check 2 is `REPORT_ONLY`.
- **Check 3, nothing visible deleted or covered.**
  - Every BEFORE face with any visible sample must still be met: same depth, same look.
  - Faces whose fingerprint is absent from AFTER get 1,024 extra directions plus every probe.
  - A covered face means AFTER's first hit is closer than BEFORE's at a visible sample.
  - v0 has no allowed-change classes.
- **Evidence.** Failing samples are clustered (6 in grid). For each of the 20 worst clusters, two 256 px orthographic crops (BEFORE and AFTER), coloured by look (the mean texture colour), written as PNG with Pillow.

**CLI:** `validate --before <snapshot_dir> --after <obj> --materials data/campus/materials.json --out <dir>` writes:
- `validation.json`: `{"checks": {"textures": {...}, "problems": {...}, "nothing_deleted": {...}}, "verdict": "PASS|FAIL", "sites": [...]}`;
- `evidence\*.png`.

- [ ] **Step 1: Write the failing tests:** identity (AFTER = BEFORE) passes every check, on `cube()`, `two_sided_wall()` and the closed room. Each Task 16 mutation is still to come.
- [ ] **Steps 2-4:** see them fail, implement, see them pass. **Step 5:** commit `feat(validate): the owner's three checks with evidence crops and a validate command`.

### Task 16: mutation proof, real verdicts, the validator agent (claude)

**Files:**
- Create `engine/tests/test_validate_mutations.py`.
- Create `.claude/agents/floor-validator.md` and `.claude/skills/uc-validate-floor/SKILL.md`, the latter describing the workflow claim → snapshot → repair → validate → evidence → review → publish.

- [ ] **Step 1: Write the failing mutation tests.** Each takes BEFORE as a textured fixture (`cube()` with 2 materials, plus the closed room), builds AFTER with ONE defect, and asserts the named check FAILS with a site at the defect:

  | Mutation | Expected failure |
  |---|---|
  | delete one visible face | check 3 |
  | change one visible face's material to a different look | check 1 |
  | shift its UVs by 0.5 | check 1 |
  | flip one visible face's winding | check 1 (`back_seen`) |
  | add a face 1 in in front of a visible face | check 3 (covered) |
  | delete one inner wall of the closed room (seen only by an interior probe) | check 3 |
  | AFTER = BEFORE | all PASS |

- [ ] **Steps 2-4:** see them fail, fix the Validator until all 7 behave, and run the engine suite.
- [ ] **Step 5: Real verdicts**, recorded in the ledger and in `docs/superpowers/records/campus/validator-v0-verdicts.md`:
  - CHTM 5th: BEFORE = its snapshot, AFTER = `data/out_chtm5/chtm_5ft_floor/*.obj`;
  - sidewalks A and B: their snapshots against `data/output_verified/*`.

  These show where today's engine breaks the owner's strict rule. They are expected failures, and they feed P2.
- [ ] **Step 6:** write the agent and the skill. The `floor-validator` agent:
  - runs `validate`;
  - reads `validation.json` and every evidence PNG;
  - writes PASS or FAIL with reasons;
  - never edits code or outputs;
  - never validates work it built.
- [ ] **Step 7: Commit.** `test(validate): mutations prove the Validator catches every break of the owner's rule; v0 verdicts on CHTM 5th, A and B`.

---

## After P0

- Merge `feat/repair-p0` into `feat-dashboard` after a final whole-branch review (opus).
- Update HANDOFF §2, the session record and the ledger.
- Then write the P1 plan (observe-only kernel plus speed) from the census timings.
