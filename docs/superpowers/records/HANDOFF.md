# HANDOFF — how any agent (Hermes, Claude, a person) continues this work

Read this whole page before touching anything. It is kept current by whoever works last; the
"Current state" section carries a timestamp. If it is older than the newest commit on
`feat-dashboard`, trust `git log` and the ledger tail over it.

Companion files:
- `docs/superpowers/records/2026-09-24-session-record.md` — the goal, the map of which engine file
  handles which error, the full history with measured results. Read section 1 and 3 first.
- `docs/superpowers/records/WORK-CLAIMS.md` — who is working on what right now. **Claim before you
  start, release when you stop.**
- `docs/superpowers/records/briefs/` — complete, self-contained task briefs, numbered in queue order.
- `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/progress.md` — the ledger: every ruling and
  measurement in order. Append to it after every step.

## 1. What the owner wants (one paragraph)

Clean the SketchUp OBJ exports of the CHTM sidewalk (file A `CHTM_SIDE_WALK_2nd_floor`, snapshot
`data/snapshots/ce26e0392ab0`; file B `CHTM_2nd_to_3rd_building_sidewalk_outside`, snapshot
`data/snapshots/0b290ec0bcb4`) into clean solid slabs for Unity: remove (not hide) hidden inside
faces, triangle edges on flat surfaces, stacked duplicate layers and stray fragments; never delete a
side mesh, rebuild broken or missing sides; only the model's outline edges may be visible. After every
run the latest `.skp` of each file must be in `OBJ FIXED RESULT/` for the owner to check in SketchUp
2026. Work visually: every round ends with renders that are looked at, not only numbers.

## 2. Current state (2026-09-25 10:55, written by the brief 03 Claude subagent)

Branch `feat-dashboard`. The side rebuild is MERGED: 68f6d15 (merge), a89f771, 82adc60 and ca463c2
(follow-ups), f8e72bb (report `reconcile-side-rebuild-report.md`), then these record files. Engine
suite **542 passed** at ca463c2. `docker-compose.yml` shows as modified: it belongs to another
session, never touch it.

Latest owner files (A 08:52, B 08:50, engine ca463c2). Both passed, with no merge rollback:
- file A: 1,044 triangles, back faces from outside 20,945 px;
- file B: 530 triangles, 5,993 px;
- the owner's ramp (B region 309) in the written `.skp`: one clean wall, close-up 948 back px
  (input 43,696);
- two runs of A give a byte-identical `report.json`.

Against the side rebuild alone (876 / 486), the extra triangles are feat-dashboard's T-junction
threading (A 143, B 49, measured with it switched off) and its debris and fold pass.

Jobs:

1. Next: review part 2 (the side rebuild), then brief 10 (side rebuild follow-ups).
2. Found in brief 03, for brief 10 or the leftovers:
   - A ships a coincident double layer with opposite windings at z 1612.2 on its lower landing
     (session record section 6 item 8);
   - 3 of A's 6 longest lines inside a surface lie along x = 2673.2;
   - a new sliver, A face 3491, is removed and confirmed by the rays, but why it became a
     candidate was not traced.

**If you take over one of these** (for example because Claude hit its usage limit): follow the
lapse rule at the top of `WORK-CLAIMS.md`, take the claim over in writing, run `git status` and
`git log` in that tree, and continue from the brief's remaining items. Uncommitted work in a tree is
work in progress: finish it, test it, commit it; never discard it.

## 3. The queue (do in this order)

| # | Brief | What | Status |
|---|---|---|---|
| 1 | `briefs/01-T1-tjunction-repair.md` | T-junction repair | DONE (28d63df, 03df53d, report 437e4ef) |
| 2 | `briefs/02-SR-side-rebuild.md` | side rebuild SR0-SR6 | DONE on feat/side-rebuild (fafd4d6), merged by brief 03 |
| 3 | `briefs/03-reconcile-and-verify.md` | merge the side rebuild, rerun, verify | DONE (68f6d15 + a89f771, 82adc60, ca463c2; report f8e72bb); 542 passed; A 1,044 / B 530 passed |
| 4 | `briefs/04-review.md` | review part 1 DONE (review-since-b2134e9.md); review 2a of Hermes's commits DONE (review-hermes-fixes.md); **part 2 (the side rebuild and the merge) NEXT** | read-only |
| 5 | `briefs/05-dashboard-fix-wave.md` | dashboard fixes D1-D12 | queued |
| 6 | `briefs/06-leftovers.md` | smaller leftovers | any time a slot is free |
| 7 | `briefs/07-review-fixes.md` | fixes from review part 1 | DONE by Hermes (merge 19f97cc) |
| 8 | `briefs/08-review2a-fixes.md` | fixes from review 2a | DONE (536fca7..d570927, report 64023ad) |
| 9 | `briefs/09-sliver-ray-confirmation.md` | rays through each debris piece, folds | DONE (3386c4f..d9673c1) |
| 10 | `briefs/10-side-rebuild-followups.md` | side rebuild gaps + the render findings after the merge | **NEXT** (main checkout) |

## 4. Rules (each one cost time when broken)

- **Python**: always `.venv/Scripts/python.exe` from the repo root, run modules with `-m`
  (`-m pytest`, `-m engine.cli`). In a worktree use the main checkout's interpreter
  `"/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"` from the worktree root, and set
  `PYTHONPATH` to the worktree root for any plain `python script.py` (otherwise it imports the main
  checkout's engine).
- **Never touch**: `docker-compose.yml` and the Docker files at the root (another session's), any
  untracked file you did not create, the live export folder `D:\PROJECTS\UC ENVIRONMENT BUILDING\...`,
  the owner's campus model `D:\PROJECTS\UC\02-SKETCHUP\current\...skp`, and the running servers
  (uvicorn 8190, vite 5190, http.server 5180, Postgres 5490).
- **API tests** (`pytest api`) drop and recreate the shared test database; never run them while any
  other process runs them.
- **Shared working tree**: other sessions edit this folder. Stage files by name, never `git add -A`
  or `git commit -a`. Big features go in their own worktree and branch; the controller merges.
  Foreign uncommitted edits get parked on a `wip/` branch, never discarded. Worktree `corllenium`
  (branch `corllenium/p1-ingest`) belongs to another session: leave it alone.
- **Test-first**: write the failing test, see it fail, implement, see it pass. Commit after every
  item so a cut loses nothing.
- **Guards are never loosened by argument.** A change to what the guard tolerates must name the
  change and MEASURE it (example: border shifts are tolerated only up to the merge's own 0.15 in,
  measured per pixel). Only `engine/fixes/solidify.py` may invent vertices; the merge never moves or
  invents one.
- **Visual pass every round**: read `data/output/<name>/qa/*.png` and render the `.skp` with
  `docs/superpowers/records/scripts/render_skp.py`, audit it with `skp_edge_audit.py`, and say what
  you see. A log line is not evidence.
- **Records**: after every step append to the ledger, update section 2 of this page and the session
  record's history, and commit them (`git add -f` for files under `.superpowers/sdd/`).

## 5. How to verify a round (copy these)

```bash
.venv/Scripts/python.exe -m pytest engine/tests -q -p no:cacheprovider
.venv/Scripts/python.exe -m engine.cli fix data/snapshots/ce26e0392ab0 --out data/output
.venv/Scripts/python.exe -m engine.cli fix data/snapshots/0b290ec0bcb4 --out data/output
.venv/Scripts/python.exe -m engine.cli preview-data data/snapshots/ce26e0392ab0 --out preview/data
.venv/Scripts/python.exe -m engine.cli preview-data data/snapshots/0b290ec0bcb4 --out preview/data
PYTHONPATH="$PWD" .venv/Scripts/python.exe docs/superpowers/records/scripts/skp_edge_audit.py "OBJ FIXED RESULT/CHTM_SIDE_WALK_2nd_floor.fixed.skp"
PYTHONPATH="$PWD" .venv/Scripts/python.exe docs/superpowers/records/scripts/render_skp.py "OBJ FIXED RESULT/CHTM_SIDE_WALK_2nd_floor.fixed.skp" data/skp_render/A
```

Read in `data/output/<name>/report.json`: `tris_after`, `passed`, `invariants` (all true),
`merge_report.rolled_back` (must be false), `guard_final.totals` (holes, material_changed,
moved_same_flat, moved_other must be 0; edge_flicker within its cap; border_shift, zfight_tie,
crack_closed, fragment_removed are tolerated classes), `solidify_report.cap_guard_passed`.

## 6. Handing back

When you stop (limit reached, owner says Claude is back, or the job is done): commit at a clean point,
release your claim in `WORK-CLAIMS.md`, update section 2 here with what is done and what is left,
append to the ledger, commit those three files.
