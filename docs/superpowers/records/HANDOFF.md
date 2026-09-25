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

## 2. Current state (2026-09-25 23:55, written by the Claude controller)

Branch `feat-dashboard`, engine suite **566 passed** at brief 10's end (17:32). Brief 11's item 1 is
committed (4019987); its next items are the brief-11 agent's uncommitted work in progress in the main
checkout (measured 21:15: `engine/fixes/solidify.py`, `engine/tests/fixtures/build.py`,
`engine/tests/test_solidify.py`, 614 lines added, 93 removed). Brief 11 has since committed 0a81860
(item 2) and 281a569 (R10-C1).

The owner's decisions of 21:45 are carried out:
- **Live database backed up** to `data/backups/fixer-20260925-2150.dump`.
- **The 6 `version_assets` rows** with backslash paths were rewritten to forward slashes (`UPDATE 6`).
- **The dashboard was rebuilt** from committed 281a569 (section 8):
  - nginx now has `proxy_read_timeout` / `proxy_send_timeout` of 600 s.
  - `fixer-api` and `fixer-web` were recreated at 21:55, and the API migrated the live database from
    0001 to 0002_flat_materials when it started.
  - The live model now loads in the container: every version's meshbuf returns 200 through nginx.
  - The old images are kept as `ucmodelfixer-api:pre-20260925` and `ucmodelfixer-web:pre-20260925`.
  - The container writes no `.skp` (there is no SketchUp DLL on Linux), so the owner's files still
    come from native runs.
- **One copy of each stacked, opposite-wound, same-material surface may be removed**: brief 13.

Owner files (refreshed 23:53 and 23:54 into `data/output_verified`) are built from the COMMITTED head
ab22ff3, which is brief 11's end, in the clean worktree `.claude/worktrees/verified`:
- File A: 881 triangles, back faces from outside 18,348 px, `.skp` sha256 31d4440c4270…
- File B: 513 triangles, 2,869 px, sha256 bd874b3573c7…
- Both passed, with all invariants true.
- The numbers equal brief 11's own runs. To refresh them from committed code again: in
that worktree `git checkout --detach <commit>`, then run `engine.cli fix` with
`--out "D:/PROJECTS/UC MODEL FIXER/data/output_verified" --skp-dir "D:/PROJECTS/UC MODEL FIXER/OBJ FIXED RESULT"`
for both snapshots (the file must not be open in SketchUp).

Jobs:

State at 23:55:
1. **Brief 11 is DONE_WITH_CONCERNS**: 15 commits, 4019987..ab22ff3.
   - Suite: 607 passed, 1 xfailed (M2).
   - A: 881 triangles, 18,348 back px. B: 513 triangles, 2,869 back px. Both passed.
   - Its concerns are in `remaining-visual-defects-report.md`. The biggest: R10-I1 costs A two 2 in
     walls at x 2680, a knife edge again; R10-I2 adds 112 back px on B.
   - A read-only review of briefs 11 and 13 together is next, in the fresh window after 01:40.
2. **Brief 15** (one wall per side plane, for no flicker) is running: the brief-11 agent continues in
   the main checkout.
3. **Brief 13's branch `feat/coincident-pairs`** is not merged: it waits for that review. Its rule works
   but removes nothing today. Brief 14's measurements are on the same branch.
4. **The owner's files** were refreshed from committed ab22ff3 (23:53 and 23:54): A 881, B 513, both passed.
5. **Merged:** the dashboard wave (cba42a5) and brief 12 (f885fd9, Hermes pass 5, reviewed).
6. **Automatic continuation is ON** (section 7): if the limit cuts brief 15, Hermes continues it on its
   own branch.

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
| 5 | `briefs/05-dashboard-fix-wave.md` | dashboard fixes D1-D12 | DONE by Hermes (passes 1-4, three reviews); merged as cba42a5 |
| 6 | `briefs/06-leftovers.md` | smaller leftovers | any time a slot is free |
| 7 | `briefs/07-review-fixes.md` | fixes from review part 1 | DONE by Hermes (merge 19f97cc) |
| 8 | `briefs/08-review2a-fixes.md` | fixes from review 2a | DONE (536fca7..d570927, report 64023ad) |
| 9 | `briefs/09-sliver-ray-confirmation.md` | rays through each debris piece, folds | DONE (3386c4f..d9673c1) |
| 10 | `briefs/10-side-rebuild-followups.md` | side rebuild gaps + review part 2 findings | DONE (9f64ae9..f7e27d1, report daeb84c) |
| 11 | `briefs/11-remaining-visual-defects.md` | margin-strip winding, broken undersides, B region 107, B4, B8 | DONE_WITH_CONCERNS (4019987..ab22ff3); review next |
| 12 | `briefs/12-dashboard-followups.md` | re-review 3 follow-ups M1-M4 and nits (API owner-copy block, tests) | DONE by Hermes pass 5; reviewed (engine 573, API 44, web 47, 5 of 5 mutation checks); merged as f885fd9 |
| 13 | `briefs/13-coincident-pairs.md` | one copy of each exactly stacked, opposite-wound, same-material surface (owner's decision 09-25 21:45) | DONE_WITH_CONCERNS on `feat/coincident-pairs` (not merged; review together with brief 11): the rule works but removes nothing at 281a569, where A's landing is already one layer |
| 14 | `briefs/14-zfight-sources.md` | what still z-fights on A: riser pair x 1305.14, same-wound duplicate z 1779.53 | DONE, measured and not fixed (9f39e7f): A 28 double layers (3,723.5 sq in, 141 px), B 2; all are export sides drawn twice; the fix is brief 15 |
| 15 | `briefs/15-one-wall-per-side-plane.md` | one wall per side plane where the export drew a side twice; `double_layers` in every report | **running**: the brief-11 agent, main checkout |

## 4. Rules (each one cost time when broken)

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

## 5. How to verify a round (copy these)

```bash
.venv/Scripts/python.exe -m pytest engine/tests -q -p no:cacheprovider
.venv/Scripts/python.exe -m engine.cli fix data/snapshots/ce26e0392ab0 --out data/output --skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"
.venv/Scripts/python.exe -m engine.cli fix data/snapshots/0b290ec0bcb4 --out data/output --skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"
.venv/Scripts/python.exe -m engine.cli preview-data data/snapshots/ce26e0392ab0 --out preview/data
.venv/Scripts/python.exe -m engine.cli preview-data data/snapshots/0b290ec0bcb4 --out preview/data
PYTHONPATH="$PWD" .venv/Scripts/python.exe docs/superpowers/records/scripts/skp_edge_audit.py "data/skp_scratch/CHTM_SIDE_WALK_2nd_floor.fixed.skp"
PYTHONPATH="$PWD" .venv/Scripts/python.exe docs/superpowers/records/scripts/render_skp.py "data/skp_scratch/CHTM_SIDE_WALK_2nd_floor.fixed.skp" data/skp_render/A
```

Without `--skp-dir` the run writes the owner's `OBJ FIXED RESULT/`, which must hold only files built
from committed code (section 4).

Read in `data/output/<name>/report.json`: `tris_after`, `passed`, `invariants` (all true),
`merge_report.rolled_back` (must be false), `guard_final.totals` (holes, material_changed,
moved_same_flat, moved_other must be 0; edge_flicker within its cap; border_shift, zfight_tie,
crack_closed, fragment_removed are tolerated classes), `solidify_report.cap_guard_passed`.

## 6. Handing back

When you stop (limit reached, owner says Claude is back, or the job is done): commit at a clean point,
release your claim in `WORK-CLAIMS.md`, update section 2 here with what is done and what is left,
append to the ledger, commit those three files.

## 7. Automatic continuation while Claude is at its usage limit

`tools/auto_continue.py` runs outside Claude, so it keeps working when Claude's usage limit stops every
Claude agent. The Claude controller starts it in the background after every restart of the app:

```bash
.venv/Scripts/python.exe tools/auto_continue.py watch    # checks every 5 minutes, acts, supervises
.venv/Scripts/python.exe tools/auto_continue.py status   # what it sees and would do now; changes nothing
```

The rule it follows is written in `WORK-CLAIMS.md` (automatic continuation). In short, when Claude is
cut with the reset at least 45 minutes away, the running brief job goes to Hermes on branch
`hermes/auto-<run>` in `.hermes/worktrees/auto-<run>`, with the job tree's uncommitted work copied in
and a prompt that carries section 4's rules. Reviews stay with Claude. Everything a run did is in
`data/auto_continue/<run>/` (`prompt.md`, `hermes.out`, `usage.json`, `wip.patch`, `run.json`), one line
per event in `AUTO-CONTINUE-LOG.md`, and Hermes's report in the branch at
`docs/superpowers/records/hermes-auto/<run>-report.md`.

When Claude comes back:
1. Run `status`, read `WORK-CLAIMS.md` and `AUTO-CONTINUE-LOG.md`. Do not resume a job Hermes holds.
   To take it back early: `tools/auto_continue.py stop --kill` (the row is released as STOPPED with
   Hermes's commits so far), then `tools/auto_continue.py resume` so later cuts are covered again.
2. Review the branch `hermes/auto-<run>` like any worker's (a read-only reviewer with probes).
3. Merging it into `feat-dashboard`: the job's work in progress is STILL uncommitted in the job's tree;
   the runner copied it and did not move it (`data/auto_continue/<run>/wip.patch` is the copy). Park it
   first (`git stash push -- <those files>`), merge, check that nothing in the parked copy is missing
   from the merged files, and only then drop the stash.
4. Then continue the brief (claim the row again) and refresh the owner's files from the new commit.

Tested by `tools/tests/test_auto_continue.py` (a fake Hermes in a throwaway repository); run
`.venv/Scripts/python.exe -m pytest tools/tests -q -p no:cacheprovider`.

## 8. Rebuilding the Docker dashboard (only with the owner's OK)

The compose file builds from `.`, the main checkout's working tree. That tree holds other agents'
uncommitted work, so build the images from a clean worktree of a COMMIT instead. In git bash, set
`MSYS_NO_PATHCONV=1` for any `docker exec` that passes a container path.

```bash
git -C .claude/worktrees/dk checkout --detach <commit>
cp Dockerfile.api Dockerfile.web nginx.conf .dockerignore .claude/worktrees/dk/
pnpm --dir .claude/worktrees/dk/web install --frozen-lockfile
pnpm --dir .claude/worktrees/dk/web run build
docker exec fixer-db pg_dump -U fixer -d fixer -Fc -f /tmp/fixer.dump
docker cp fixer-db:/tmp/fixer.dump data/backups/fixer-<date>.dump
docker tag ucmodelfixer-api ucmodelfixer-api:pre-<date>
docker tag ucmodelfixer-web ucmodelfixer-web:pre-<date>
docker build -t ucmodelfixer-api -f .claude/worktrees/dk/Dockerfile.api .claude/worktrees/dk
docker build -t ucmodelfixer-web -f .claude/worktrees/dk/Dockerfile.web .claude/worktrees/dk
docker compose -p ucmodelfixer up -d --no-build api web
```

- `pg_dump` and `docker cp` make the backup, before anything else touches the database.
- The two `docker tag` commands keep the old images, so a rollback is one command.
- The API runs `alembic upgrade head` on the live database when it starts.
- Check `docker logs fixer-api`, then that `/api/versions/<id>/meshbuf` returns 200 through port 5190.
