# AGENTS.md — the rules every agent follows in UC MODEL FIXER

This is the single rules file for Claude, Hermes and every other agent working in this repo.
`CLAUDE.md` imports it; `HERMES.md`, `docs/superpowers/records/HANDOFF.md` and the skills link to it.
If anything elsewhere disagrees with this file, this file wins. Change it only with the owner's OK.

## 1. What this project is

- The UC campus was built in Minecraft with the **Little Tiles** mod, brought into SketchUp, and saved
  as **CHECKPOINT-17**, which the owner has checked.
- It is exported to OBJ per SketchUp group, and used in **Unity 6000.4.7f1 / URP 17.4.0**.
- Unity draws **both sides** of every face (`CampusDoubleSided.cs`, `_Cull = 0`). Players walk the floors.
- The engine here finds what is wrong with each floor, and repairs it without changing what anyone can see.

## 2. Where things are

| What | Where | Rule |
|---|---|---|
| Engine | `engine/`: detectors, fixes, guards, rays, I/O, `campus/`, `validate/` | Python 3.12 |
| Dashboard | `api/` (FastAPI) and `web/` (Vue 3 + three.js); live at http://localhost:5190 | containers `fixer-api`, `fixer-web`, `fixer-db` |
| Job queue | `tools/jobs.py`, kept as `data/jobs/queue.json` in the main checkout; rendered as `docs/superpowers/records/QUEUE.md` | every job is claimed here |
| Records | `docs/superpowers/records/` (HANDOFF, session record, briefs, `hermes/` reports, `campus/`); ledgers in `.superpowers/sdd/<plan>/progress.md` | update after every step |
| Specs and plans | `docs/superpowers/specs/`, `docs/superpowers/plans/` | the spec is the authority |
| CHECKPOINT-17 export | `D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\01-MODEL-EXPORT\CKPT17\` | **read only, and only through `engine/io/snapshot.py`** (stable copy plus sha256) |
| CHECKPOINT-17 backup | `MODEL FIXER ENGINE FILES\02-SKETCHUP-MODELS\CHECKPOINT-17-BACKUP\` | read only; the SDK opens only a verified copy under `data/campus/skp_copy/`, never saves |
| CHECKPOINT-17 master | `D:\PROJECTS\UC\02-SKETCHUP\current\…CHECKPOINT-17.skp` | **never** |
| The owner's folders | `MODEL FIXER ENGINE FILES\` (git-ignored) and `OBJ FIXED RESULT\` | only results built from COMMITTED code, published from `.claude/worktrees/verified` |
| Minecraft export | `D:\PROJECTS\UC\03-EXPORTS\NEW FIX IMPORT\` | old (the owner, 2026-10-03); not a reference |

## 3. Binding rules (each one cost time when broken)

- **Python**: always `.venv/Scripts/python.exe` from the repo root, run modules with `-m`
  (`-m pytest`, `-m engine.cli`). In a worktree use the main checkout's interpreter
  `"/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"` from the worktree root, and set
  `PYTHONPATH` to the worktree root for any plain `python script.py` (otherwise it imports the main
  checkout's engine).
- **Never touch**: any untracked file you did not create, the live export folder
  `D:\PROJECTS\UC ENVIRONMENT BUILDING\...`, the owner's campus model
  `D:\PROJECTS\UC\02-SKETCHUP\current\...skp`, and the running servers: the Docker containers
  `fixer-api` (8190), `fixer-web` (5190 and 5180, nginx) and `fixer-db` (Postgres 16, 5490).
  Rebuilding or restarting them, and any write to the live database `fixer`, is the owner's decision.
  The owner approved the 2026-09-25 rebuild (section 8).
- **API tests** (`pytest api`): since cba42a5 each session makes its own `fixer_test_<pid>_*` database
  and drops only its own (and ones left by dead processes), so runs of this code may overlap. A
  worktree or container on an older commit still drops the one shared `fixer_test`: never overlap two
  runs of such old code. Never touch the live database `fixer`.
- **Shared working tree**: other sessions edit this folder. Stage files by name, never `git add -A`
  or `git commit -a`. Big features go in their own worktree and branch; the controller merges.
  Foreign uncommitted edits get parked on a `wip/` branch, never discarded. Worktree `corllenium`
  (branch `corllenium/p1-ingest`) belongs to another session: leave it alone.
- **The owner's folder `OBJ FIXED RESULT/` holds only files built from COMMITTED code.** Every
  real-data run during work passes `--skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"`; after
  committing, refresh the owner's files from the clean worktree `.claude/worktrees/verified` (section 2).
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

(The references to "section 2" and "section 8" in this list point to `docs/superpowers/records/HANDOFF.md`.)

## 4. Blocked operations

Each of these once damaged this model. No agent does them, and no argument overrides that:

- **Weld above 0.1 mm** (tolerance welding).
- Blender **`select_interior_faces`** (it deleted 88 % of the geometry).
- **Fill Holes**, **Make Manifold**, **Decimate**, Poisson or voxel remeshing, any generic hole filling.
- Dissolve above 5°.
- Treating opposite-normal coincident pairs as duplicates. The only exception is brief 13 (same
  material, exactly coincident, under the strict guard).
- **whole-campus jobs**: the campus is never processed as one mesh; work runs per floor or element unit.

**Owner exceptions of 2026-10-03.** Each one is allowed only inside the engine that owns it, and is
named, measured and tested:
- **E5 flicker cut.** The losing face of a different-look overlap may be cut along the winning face's
  border. The new points lie only on that border.
- **E8 narrow flat fill.** A hole whose whole border lies in one plane that matches the neighbouring
  surface may be filled using existing points only. Each fill is shown in the floor review. The
  invariant "area never grows" allows exactly these fills.

## 5. Owner decisions (2026-10-03)

| Topic | Decision |
|---|---|
| Scope | Every building (BRS, CHTM, EDS, GYMNASIUM, MAIN, MAIN INFRASTRUCTURE, PE, SCIENCE A, ARCHITECTURE, plus site pieces), per floor or element |
| Source | CHECKPOINT-17 (its backup is the source of truth); the master is never touched |
| Reference for "visible" | CHECKPOINT-17 itself, before against after. The Minecraft export is old and not a reference |
| Visible rule | **Strict.** Nothing that can be seen is deleted or covered. Visible debris stays and is listed with a picture; a rebuilt side may cover only faces that are 0 % visible |
| Viewpoints | Outside, **and inside at eye height**, because players walk the floors |
| Back-to-back faces | They flicker in Unity (`_Cull = 0`). Keep the side facing a viewer and remove the inward copy. Where both sides are seen with different looks, the owner decides |
| Flicker, different looks | The loser is cut along the winner's border (E5). The winner, in order: a patch inside a bigger face of the same source group; the look and UV continuing the plane's neighbours; otherwise the owner |
| Holes | The narrow flat fill (E8); anything else goes to the per-floor "needs modelling" queue |
| Floors | Fixed separately (Unity shows them floor by floor); the floors above and below are read-only context |
| Outputs | `MODEL FIXER ENGINE FILES\05-FIXING\<BUILDING>\<BUILDING>-CKPT17-vs-FIXED.skp` (2 rows: CHECKPOINT-17, then engine-fixed, floors side by side), plus `\<Lnn>\` per floor |
| Review | Per floor, by the owner: accept or reject, plus "this spot is wrong" marks |
| ML | Rules first; a model learns from the owner's verdicts and never bypasses the rules |
| Hermes | Takes queued jobs (`hermes` or `either`) when the owner starts it; Claude reviews and merges |

## 6. The owner's validation rule

A floor is good only when the Validator (`engine/validate/`, run by an agent that did not build the fix)
shows all three:
1. **every facade texture is still there**: every visible sample keeps its surface, its look (texture
   plus colour) and its UV;
2. **the problems are solved**: `find_errors` after the fix meets the targets the owner signed;
3. **nothing visible to the eye was deleted or covered**: from outside, and from **eye height** inside
   every floor.

Then the owner confirms the floor. A log line or a self-report is not a pass. The pass is the
Validator's `validation.json` together with its evidence images.

## 7. How work flows

1. **Every job is in the queue.**
   - `"$PY" tools/jobs.py list` shows the jobs; `next --for <claude|hermes> --as <name>` claims the next
     eligible one; `done <id> --branch <b>` hands it in for review.
   - Never work a job you have not claimed; never take a job someone else holds.
2. **One job is one brief, one branch and one worktree.**
   - Claude: `claude/<id>` in `.claude/worktrees/<id>`. Hermes: `hermes/<id>` in `.hermes/worktrees/<id>`.
   - Branches are made from the phase's integration branch (P0: `feat/repair-p0`).
3. **Follow the brief item by item, test first.** Each item says when it is done and names its tests.
4. **The report carries real output.**
   - Hermes writes `docs/superpowers/records/hermes/<id>-report.md`; Claude writes its ledger.
   - Paste the actual output of every acceptance command. Never claim "fixed" or "passed" without that output.
5. **Review, then merge.**
   - Only the Claude controller merges, after a review (`hermes-reviewer` or `rules-reviewer`) and a
     re-run of the acceptance commands.
   - Changes that touch `engine/guard/**`, `FixProfile` thresholds or existing tests are rejected unless
     the brief asked for them.
6. **Records after every step:** the ledger, HANDOFF §2, the session record, `QUEUE.md`.

## 8. Commands

```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
# always from the worktree root, in a subshell, with PYTHONPATH set:
( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m pytest tools/tests -q -p no:cacheprovider )
"$PY" tools/jobs.py next --for hermes --as Hermes     # in the main checkout
```

- A bare `cd` in a shared terminal moves everyone's working directory: use subshells or `git -C`.
- Commit messages end with `Co-Authored-By: <model> <noreply@anthropic.com>` (Claude) or `Hermes-Job: <id>` (Hermes).
