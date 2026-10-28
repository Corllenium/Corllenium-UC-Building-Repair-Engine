# HERMES Agent — Project Memory: UC MODEL FIXER

## 0. START HERE (updated 2026-10-03)

This file is the entry point. The work is shared between Claude sessions and you, Hermes.
- Claude lays the foundation: the rules, the plan, a brief per job, the failing tests for build jobs.
- You execute queued jobs.
- Claude reviews every branch you hand in and merges it, or sends it back with notes.
- You never merge.

### When the owner says: "Read HERMES.md and do the next job"

1. **Read [`AGENTS.md`](AGENTS.md) completely.** It holds the rules, the blocked operations, the owner's
   decisions and the owner's validation rule, and it wins over anything else.
2. **Claim your job** from the MAIN checkout (`D:\PROJECTS\UC MODEL FIXER`):
   ```bash
   "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" tools/jobs.py next --for hermes --as Hermes
   ```
   - It prints `<id>  <brief>  hermes/<id>`.
   - Exit code 3 means no job is ready for you now: tell the owner, and stop.
   - **If the owner names a job** ("do job H1"), claim that one instead:
     `"D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" tools/jobs.py claim <id> --as Hermes`. It is refused
     unless the job is `ready`. Then make the worktree from the branch the job's brief names; if it names
     none, use `feat-dashboard` for a records-only job and `feat/repair-p0` for code.
   - `tools/jobs.py list` shows the whole queue; `docs/superpowers/records/QUEUE.md` is the same,
     rendered.
3. **Make your worktree** from the job's base: the branch its brief names; if it names none, the
   phase's integration branch for code (P0: `feat/repair-p0`) and `feat-dashboard` for a records-only job:
   ```bash
   git -C "D:/PROJECTS/UC MODEL FIXER" worktree add -b hermes/<id> ".hermes/worktrees/<id>" <base>
   ```
   Work only inside `D:\PROJECTS\UC MODEL FIXER\.hermes\worktrees\<id>`.
4. **Open the brief the queue printed.**
   - A path ending `#task-N` means that task of the plan.
   - Do the items in order, **test first**: write the named test, run it and see it fail, implement,
     see it pass.
   - Each item says when it is done.
   - Run Python from the worktree root, as `AGENTS.md` §8 shows.
5. **Run every acceptance command of the brief** and paste the **real output** into
   `docs/superpowers/records/hermes/<id>-report.md` (format: `docs/superpowers/records/hermes/README.md`).
   - Never write "fixed" or "passed" without that output.
   - If something did not work, say so plainly in the report.
6. **Commit** in your worktree, staging files by name, never `git add -A`. End every message with the
   line `Hermes-Job: <id>`. Never amend or rebase: make a new commit. In the report, copy commit hashes
   from `git log --oneline` after your last code commit. An amended commit's old hash no longer exists,
   and two reports cited such hashes.
7. **Hand in:**
   ```bash
   "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" tools/jobs.py done <id> --branch hermes/<id>
   ```
   Then tell the owner the job is waiting for Claude's review, and stop. If Claude asks for changes,
   the job shows `changes-requested` with notes; the next session continues on the same branch.
8. **Never:**
   - merge or push;
   - edit `engine/guard/**`, `FixProfile` thresholds or any existing test (unless the brief says so);
   - touch the live database, the containers, the export folder (except through the snapshot
     functions), the CHECKPOINT-17 master or backup (except as the brief says);
   - use a blocked operation (`AGENTS.md` §4);
   - write outside your worktree, except `data/` and your report.

   `delegate_task` children may only read: they never edit files or run commits.

### Background

- History and the map of which engine file handles which error:
  `docs/superpowers/records/2026-09-24-session-record.md`.
- The current state: `docs/superpowers/records/HANDOFF.md` §2.
- If you were started by `tools/auto_continue.py` (your prompt says "This run is automatic"), that
  prompt's rules come first. That runner is switched off until phase P5 of the repair engine.

**Project Directory:** `D:\PROJECTS\UC MODEL FIXER`
**Source model:** `UC-campus-FIXED-v2026-07-11 - CHECKPOINT-17.skp`; the engine works on its OBJ
exports, test files `CHTM_SIDE_WALK_2nd_floor` (snapshot `data/snapshots/ce26e0392ab0`) and
`CHTM_2nd_to_3rd_building_sidewalk_outside` (snapshot `data/snapshots/0b290ec0bcb4`).
**Deliverable the owner checks:** `OBJ FIXED RESULT/<name>.fixed.skp`. It holds only files built from
COMMITTED code: every run during work passes
`--skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"` (without it, `engine.cli fix` writes the
owner's folder).
**Target Engine:** Unity 6000.4.7f1 / URP 17.4.0 (`CampusDoubleSided.cs`, `_Cull = 0`)

---

## 1. Dedicated Machine Ports & Host Rules
Never use default ports (5173, 8000, 5432) — other services run on this machine:
- **Web Dashboard:** `http://localhost:5190` (Vite `strictPort: true`)
- **API Server:** `http://127.0.0.1:8190` (FastAPI / Uvicorn)
- **PostgreSQL 16:** `127.0.0.1:5490` (Docker container `fixer-db`, container port 5432)
- **Preview page:** `http://127.0.0.1:5180` (static, `preview/index.html`)
- *Host Services:* `uc-dashboard` on `127.0.0.1:8200`, `ui-tars-model` on `8090`.
- Do not stop or restart the running servers without asking the owner.

---

## 2. Hard Invariants & Guardrails
**The binding rules, the blocked operations (with the owner's E5 and E8 exceptions), the owner's decisions
and the owner's validation rule are in [`AGENTS.md`](AGENTS.md) §3-6, and only there; this file does not
repeat them. Read them before any work. The notes below are engine background.**
- **Double-sided rendering by default**: Match SketchUp & Unity campus shaders. Single-sided is only a diagnostic canvas toggle.
- **Invariants after every fix** (all in `report.json` `invariants`):
  - Region surface area must never grow (cannot bridge openings).
  - Material count unchanged.
  - Bounding box identical.
  - Cap guard (solidify) passed.
  - Final guard passed across 26 orthographic views: 0 holes, 0 changed materials, 0 moved surfaces. Tolerated only by name and measurement: z-fight ties, closed cracks (capped), removed debris, border shifts up to the merge's own 0.15 in.

---

## 3. Project Structure
```
engine/       Pure computational geometry (no SQL/HTTP imports). Tests: pytest engine/tests -q (run it; the
              count grows with every job).
              - rays/: Embree ray caster & numpy Moller-Trumbore oracle.
              - vis/: 128-direction exposure (hidden / slit / outside).
              - guard/: 26-view orthographic guard, pixel classes, feedback loops; qa_render.py writes 21 renders per run.
              - fixes/: pipeline.py (fix_object, the order of every step), solidify.py (walls, bottoms),
                remove.py, orient.py (flip), overlap.py (duplicate layers), merge.py (planar merge, T-junction threading).
              - detectors/: errors.py (find_errors, the error map), fragments.py (stray fragments, slivers).
              - io/: exact f-line OBJ reader/writer, snapshot manager, skp_writer.py / skp_reader.py (the SketchUp C API).
              - campus/: the CHECKPOINT-17 source freeze, group index, material looks, inventory, census.
              - cli.py: `python -m engine.cli fix <snapshot> --out data/output` (writes OBJ, polygon OBJ, report.json, qa/, .skp).
tools/        jobs.py (the job queue), auto_continue.py (off until P5).
api/          FastAPI + SQLAlchemy 2 + Alembic + Docker Postgres on port 5490.
web/          Vue 3 + Vite + TypeScript + Three.js on port 5190.
docs/superpowers/records/   Session record, HANDOFF, QUEUE.md, briefs/, hermes/ reports, diagnostic scripts/.
```

---

## 4. Current Progress
The live state is `docs/superpowers/records/HANDOFF.md` §2 and the job queue (`tools/jobs.py list`,
rendered as `docs/superpowers/records/QUEUE.md`).
