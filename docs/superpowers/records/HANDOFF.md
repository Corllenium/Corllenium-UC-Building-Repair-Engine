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

## 2. Current state (2026-09-24 19:00, written by the Claude controller)

Branch `feat-dashboard`, HEAD after `437e4ef`. Engine suite **417 passed**. `docker-compose.yml`
shows as modified: it belongs to another session, never touch it.

Latest outputs (written 18:4x by the code at 03df53d; they are what is in `OBJ FIXED RESULT/`):

| | A | B |
|---|---|---|
| Triangles in -> out | 4,692 -> 1,013 | 7,227 -> 601 |
| Passed (all invariants, final guard), merge rolled back | yes, no | yes, no |
| T-vertices before -> after the merge | 353 -> 0 | 363 -> 0 |
| `.skp` faces | 567 | 241 |
| Lines SketchUp draws inside flat surfaces (audit) | 7 + 2 T-junction lines | 3 + 24 (15 of them material seams) |

The lines left are double layers (one surface's edge lying over a second copy of it), which the side
rebuild or the overlap removal must handle, and material seams, which are real edges.

Jobs:

1. **T1 — T-junction repair**: DONE (28d63df, 03df53d, report 437e4ef).
2. **SR — side rebuild** (brief `briefs/02-SR-side-rebuild.md`), worktree
   `.claude/worktrees/side-rebuild`, branch `feat/side-rebuild`, held by a Claude subagent since
   18:34. SR0 committed (`ff4a0ec`); SR2 written but not committed when last measured; with it: back
   faces seen from outside A 119,610 -> 29,225 px, B 21,959 -> 5,258 px, both passed, but file A's
   merge rolls back (2,668 triangles instead of about 900). The owner's "sawtooth" broken side is on
   file B, under the slope between the upper landing and the lower slab.
3. Next: `briefs/03-reconcile-and-verify.md` once SR is done.

**If you take over one of these** (for example because Claude hit its usage limit): follow the
lapse rule at the top of `WORK-CLAIMS.md`, take the claim over in writing, run `git status` and
`git log` in that tree, and continue from the brief's remaining items. Uncommitted work in a tree is
work in progress: finish it, test it, commit it; never discard it.

## 3. The queue (do in this order)

| # | Brief | What | Where |
|---|---|---|---|
| 1 | `briefs/01-T1-tjunction-repair.md` | finish T1 | main checkout |
| 2 | `briefs/02-SR-side-rebuild.md` | finish SR2, SR3 (side rebuild, faces outward), fix A's rollback | worktree side-rebuild |
| 3 | `briefs/03-reconcile-and-verify.md` | merge feat/side-rebuild into feat-dashboard, rerun both files, audit the `.skp`, renders, update records | main checkout |
| 4 | `briefs/04-review.md` | independent review of everything since b2134e9 | read-only |
| 5 | `briefs/05-dashboard-fix-wave.md` | dashboard fixes D1-D12 | main checkout |
| 6 | `briefs/06-leftovers.md` | smaller engine leftovers found on the way | main checkout |

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
