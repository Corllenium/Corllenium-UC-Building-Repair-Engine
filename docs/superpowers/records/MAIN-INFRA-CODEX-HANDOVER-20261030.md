# MAIN INFRA handover for Codex (2026-10-30)

Read this first. It explains how the fresh MAIN INFRASTRUCTURE repair is set up now, where everything is, and how to run it.
Source revision `7b2f7451b5723f724a1e074fdedc07dbcf7291d330ae550066f4926886136511`, 1 block = 1 m.
Source export (read only): `Z:\PC-4-STORAGE\UC MODELS\UPDATED MINECRAFT MODEL\MAIN INFRUSTRUCTURE`.

## 1. What runs by itself

Windows task `Corllenium-Main-Infra-Supervisor` starts `tools/floor_supervisor.py` at logon and every 5 minutes. It needs a
signed-in Windows user, and does not need Claude or Codex open. It keeps these alive:

- the floor queue, one floor at a time, through `tools/run_floor_pipeline.py`
- `tools.publish_upper_status` and `tools.publish_upper_status_live` (dashboard feeds)
- the local preview on `http://127.0.0.1:4192/local-repair-preview/`

Supervisor state: `<CLAUDE>\data\main-infra-fresh\supervisor\` (`queue.json`, `status.json`, `supervisor.log`, `STOP`).
Do not start a second copy of a floor. The supervisor adopts a running pipeline, but check `status.json` first.

- **Add a floor:** add `{"floor": "3F"}` to `floors` in `queue.json`. See section 6 before adding 1F-3F.
- **Pause:** create an empty `STOP` file. Nothing new starts; running work continues.
- **Re-run a floor marked done or blocked:** set its entry back to `{"floor": "4F", "rerun": true}`.

## 2. Where things are

`ENG = D:\PROJECTS\05-Corllenium-UC-Building-Repair-Engine`, `W = ENG\.claude\worktrees`. Remote name: `corllenium`.

| What | Path | Branch |
|---|---|---|
| Engine stages, driver, supervisor, shared measurement | `W\MAIN-INFRA-E4-MERGE-20261023` (call it E4) | `claude/MAIN-INFRA-E4-MERGE-20261023` |
| Run data, progress tools, publishers | `W\MAIN-INFRA-CLAUDE-4F-7F-20261023` (CLAUDE) | `claude/MAIN-INFRA-CLAUDE-4F-7F-20261023` |
| Strict guard allowed-change class | `W\MAIN-INFRA-GUARD-CLASS-20261029` | `claude/MAIN-INFRA-GUARD-CLASS-20261029` |
| E5 exposure fix, draft PR 1, stacked on the guard branch | `W\MAIN-INFRA-E5-GUARDDIR-20261029` | `claude/MAIN-INFRA-E5-GUARDDIR-20261029` |
| Dashboard source, local preview | `W\SIEGE-MAIN-INFRA-20261023\dashboard` | `claude/main-infra-fresh-upper-20261023` |
| Live dashboard build | `D:\PROJECTS\02-Corllenium-Siege\.worktrees\claude-main-infra-live` | `claude/main-infra-fresh-live-20261023` |

Run root `R = CLAUDE\data\main-infra-fresh\run-claude-4f-7f-20261023` (git-ignored, on disk only): `raw`, `reference`, `normalized`,
`e3`, `e5`, `e4`, `independent-validator`, `logs`. Progress file: `CLAUDE\data\main-infra-fresh\current-upper.json`.
Your own progress file stays `ENG\data\main-infra-fresh\current.json`; the live publisher mirrors it unchanged when it is newer.

Do not delete or move folders in `R`. Your v4/v5/v6 phase plans pin files there. Superseded E5 output is kept beside the
current one: for example your pinned `e5/6F` files are now in `e5/6F-fixed1-10292108/`, hashes unchanged.

## 3. The stages for one floor

`run_floor_pipeline.py` does this and reuses any finished receipt by candidate hash, so re-running is safe.

1. **E3** hidden-face removal.
2. **E5** coincident-layer cull (`--exclude-sites` drops named sites).
3. **Measure** with `tools/main_infra_external_validate.py`: strict 26-view guard, textures, visible coverage, signed Validator,
   with `--allow coincident_backface_removed`, plus 16 walking-height interior pairs (limit 60 px). Uses the float64 oracle on 4F, 5F, 6F.
4. **Heal:** faces the Validator still sees are re-kept with `tools/main_infra_restore_faces.py` (at most 3 rounds).
5. **E4** coplanar merge, measured the same way.
6. **Publish** the best candidate that meets the bar: dashboard, repo 04, repo 03, Z mirror, Blender library, then state `unity_ready`.

Manual run, from E4 with `PYTHONPATH` = E4. Add `--dry-run` to print the plan:

```
D:\PROJECTS\05-Corllenium-UC-Building-Repair-Engine\.venv\Scripts\python.exe -B -u tools\run_floor_pipeline.py --floor 4F --worker claude --max-rounds 3
```

**The bar for Unity:** guard PASS, textures PASS, coverage PASS, interior gate at most 60 px. Signed flicker and crack targets are
reported, not blocking. `unity_ready` means saved locally and passed that bar. It does not mean the owner accepted the floor.

## 4. State on 30 Oct

| Floor | Fixed file in repo 03 | Stage 3 (E4 merge) |
|---|---|---|
| 7F | E5, 19,345 | failed: coverage floor measure, interior 457 px |
| 6F | E5, 25,063 | failed: interior 1,623 px |
| 5F | E5, 35,068 | crashed: "a region triangle lies outside the footprint of its source faces" |
| 4F | E5 guard-direction fix plus 13 restored faces, 47,956 (31 Oct, replaced 48,245) | failed on 48,245; not run on 47,956 |

Files: `D:\PROJECTS\03-Corllenium-UC-Game\Assets\Models\Campus\Repaired\Main-Infrastructure\Floor\Model-Floor_0N\`.
Live results: `R\logs\pipeline-<F>-summary.json`. Comparison of every candidate from both workers: `R\independent-validator\external\comparison.md`.

## 5. What we learned

- **Interior-twin slivers:** E5 rule (d) removed back-to-back faces that the guard's below-oblique views can see. 4F (20 sites) and
  5F (4 sites) needed `e5/exclusions/*.json`. The proper fix is PR 1 (draft, not merged): test exposure along the 26 guard directions. 4F needed no
  exclusion list with it. 5F, 6F and 7F have not been rerun with it, and the full test suites have not been run on it.
- **Your candidates under the same measurement:** 7F 19,671, 5F 34,977 and 35,343, 4F 58,064 and 58,169 fail textures and coverage.
  6F 26,290 passes both with higher residuals than Claude's 25,063. See `comparison.md`.
- **Embree on 6F:** one depth-noise pixel. Use the oracle.

## 6. Open work

1. **E4 merge has passed on no floor.** It is the smooth-wall step the owner wants. Fix the 5F footprint crash and the interior
   changes first. E4 failures on 7F and 6F have no automatic heal: the external receipt lacks `e4_region_source_faces`, so
   `explain_failures` cannot run on it.
2. **1F-3F are yours.** The driver accepts `--floor 1F..3F` and `--worker codex` but has never run on them. Its defaults point at the
   Claude run root, which holds no references or normalized floors for 1F-3F. Pass your own `--root`, `--progress` and `--public`
   and use `--dry-run` first. The supervisor always launches `--worker claude` with the defaults, so do not queue 1F-3F there
   until that is changed.
3. **Merge PR 1**, then rerun E5 on 5F, 6F and 7F without exclusion lists.
4. **Merge the branches.** The four engine branches are separate and none is merged to main.
5. **Owner decisions still open:** accepting any floor; rollback attribution by bounding box or covering face.

## 7. Dashboard deploys: read before deploying

Live runs `38b8754` from branch `claude/main-infra-fresh-live-20261023` in `D:\PROJECTS\02-Corllenium-Siege\.worktrees\claude-main-infra-live`.
That branch is the only one holding all of these: the engine-worker Agent Monitor (`5242c88`), the fresh-floor workspace, the Unity-ready
state, the stage bars and the texture fix. Deploying any other branch removes the missing parts from production: on 30 Oct a deploy
without `5242c88` removed the engine-worker monitor. Merge your work into this branch first, for example
`codex/main-infra-dashboard-status-fix`, then build and deploy from there.

The local preview on port 4192 uses `tools/serve_dashboard.py`, because `python -m http.server` returns 404 for paths over 260 characters.
