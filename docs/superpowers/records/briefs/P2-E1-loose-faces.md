# Brief P2-E1: loose faces (zero-area, stray fragments, slivers, folds) as a strict repair engine

Rules: [`AGENTS.md`](../../../../AGENTS.md); they always apply.

## Goal

A new repair engine **E1** removes zero-area faces, stray fragments, slivers and fold members **only when no
viewpoint can see them**. Visible debris is never removed: it is listed with a picture for the owner's floor review
(AGENTS.md §5, Visible rule: "visible debris stays and is listed with a picture"). The measure is the Validator's
floor (§5 "Visible rule, measured": no removed face may show more than 4 px at 0.02 in/px from any viewpoint at or
above the horizon, the ring cameras or the eye-height probes). Plan: `docs/superpowers/plans/
2026-10-03-repair-engine-p1-p2.md`, Tasks E1-E8, E1.

## Base and branch

- Base: `feat/repair-p1p2` (0795710 or later: E8a/b/c, E3 and the floor Validator are merged).
- Branch `hermes/P2-E1`, worktree `.hermes/worktrees/P2-E1`. The controller merges.

## Files

- Create: `engine/repair/engines/e1_loose.py`, `engine/tests/test_e1_loose.py`, a CLI test (a new file, or new
  functions in a new file `engine/tests/test_cli_repair_unit_e1.py`).
- Modify: `engine/cli.py` (register E1 in `repair_stages` and the `e1` section of `report.json`; nothing else),
  `engine/tests/fixtures/build.py` only to ADD fixtures.
- Read only (models to follow): `engine/repair/engines/e3_hidden.py` (a non-legacy engine around a legacy stage's
  candidates, one site per edge-connected group, `split_group`), `engine/repair/engines/e8_solidify.py`.
- Read only (the candidate detectors, unchanged): `engine/fixes/pipeline.py` (`stage_fragments`, about line 866,
  and `_fold_members`), `engine/fixes/fragments.py` (`detect_fragments`), `engine/fixes/folds.py` (`detect_folds`),
  `engine/detectors/errors.py` (`loose.zero_area`).
- Read only (the judge): `engine/validate/floor.py` (`face_visible_pixels`, `VISIBLE_FLOOR_PX`, `FLOOR_IN_PER_PX`),
  `engine/validate/viewpoints.py` (`above_horizon_directions`), `engine/site_judge.py`, `engine/repair/kernel.py`.
- Read only (crops): `engine/fill_review.py` (`SpotCropper`).

## Interfaces

- Consumes: `RepairEngine` protocol (`engine/repair/types.py`: `name`, `plan(unit, ctx) -> list[Edit]`); `Edit`
  (non-legacy `remove` edits carry `faces`, `site`, `reason`, `evidence`); `split_group` from `e3_hidden.py`;
  the kernel's `validate_sites=True` path.
- Produces: `E1Loose` (name `"E1"`); `report.json` section `e1` with `candidates` (by kind: `fragment`, `sliver`,
  `fold`, `zero_area`), `sites`, `kept`, `rolled_back` (with reasons), `visible_debris` (one row per piece: faces,
  kind, pixels, viewpoint, crop path); `--engines E8a,E3,E1` runs three stages in that order.

## Rulings (binding)

- **E1-R1, candidates.** Exactly what the legacy `stage_fragments` proposes today (`detect_fragments`'s fragments
  and slivers, and the fold members `_fold_members` chooses), **plus the zero-area faces**. Run those detectors
  unchanged on the stage input. The legacy stage's own guards (`fragment_feedback`, `piece_ray_check`) are NOT the
  judge; record what they would have said per site in the evidence (`legacy_rays`, `legacy_guard`), for comparison.
- **E1-R2, sites.** One site per edge-connected group of candidate faces (welded `topo.face_w`), split above 512
  faces with E3's `split_group` (import it). A fold's chosen member and its partner are one site. Zero-area faces
  that touch no other candidate are grouped by the face they share an edge with, up to 64 per site.
- **E1-R3, the pre-filter is the floor measure.** Before the judge, measure every candidate piece with
  `face_visible_pixels` from every Validator viewpoint (above-horizon directions, ring cameras, eye-height probes).
  A piece any face of which shows more than `VISIBLE_FLOOR_PX` from any viewpoint is **visible debris**: not a
  candidate, listed in `e1.visible_debris` with a crop (`SpotCropper`). Import the constants; never redefine them.
- **E1-R4, the judge.** `validate_sites=True`, as E3. A charged site is rolled back and listed with its reason.
- **E1-R5, solidify's faces are never debris.** Faces E8a built (and any component holding one) are excluded; E1
  runs after E8a, and finds E8a's faces from the stage input's edit-log keys as E3 does for `seen_through_shell`.
- **E1-R6.** No change to `engine/guard/**`, `engine/validate/**`, `engine/fixes/**`, `FixProfile` or existing
  tests.

## Items (test first; one green commit per item)

### Item 1: engine shape
- **Tests first:** on a fixture with a stray one-face fragment, an attached sliver and two zero-area faces (add it
  to `fixtures/build.py`): E1 edits are non-legacy removes labelled E1; one site per group; `apply_edits` reproduces
  the legacy fragments stage's removal plus the zero-area faces (same face-key multiset) when nothing is rolled back.
- **Done when:** `test_e1_loose.py` item-1 tests pass.

### Item 2: visible debris stays and is listed
- **Test first:** a stray fragment 10 × 10 in standing in the open on a slab, seen from above: not a candidate;
  present in `e1.visible_debris` with pixels, viewpoint and a crop path; the floor Validator on the output shows it
  still there.

### Item 3: invisible debris goes
- **Test first:** the same fragment inside a closed box: removed; check 3 PASS and the floor PASS.

### Item 4: zero-area faces
- **Test first:** zero-area faces on a slab are removed, labelled E1 with rule `zero_area`.

### Item 5: solidify's faces are never candidates
- **Test first:** a fixture where E8a's new bottom would otherwise read as a stray; it stays.

### Item 6: the CLI
- **Test first:** `repair-unit --engines E8a,E3,E1` runs three stages in order with three check lines; `e1` in
  `report.json` has `candidates`, `kept`, `rolled_back`, `visible_debris`.

## Acceptance commands

```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
W="D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P2-E1"
M="D:/PROJECTS/UC MODEL FIXER/data/campus/materials.json"
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_e1_loose.py engine/tests/test_cli_repair_unit_e1.py -q -p no:cacheprovider )
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest tools/tests -q -p no:cacheprovider )
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m engine.cli repair-unit --snapshot "D:/PROJECTS/UC MODEL FIXER/data/snapshots/ce26e0392ab0" --engines E8a,E3,E1 --out C:/Temp/e1/swA --materials "$M" )
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m engine.cli repair-unit --snapshot "D:/PROJECTS/UC MODEL FIXER/data/snapshots/0b290ec0bcb4" --engines E8a,E3,E1 --out C:/Temp/e1/swB --materials "$M" )
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m engine.cli repair-unit --unit CHTM-L05 --engines E8a,E3,E1 --out C:/Temp/e1/chtm5 --materials "$M" --map "D:/PROJECTS/UC MODEL FIXER/data/campus/campus_map.json" --source "D:/PROJECTS/UC MODEL FIXER/data/campus/source.json" )
```

Then `engine.cli validate --edit-log <out>/edit_log.jsonl ...` on each output (read `validate --help`; the BEFORE for
a snapshot run is the snapshot, for CHTM it is `<out>/before/`).

Expected:
- the new tests pass; the engine suite keeps only its existing 1 xfailed (about 25-40 minutes); the tools suite
  passes;
- per unit: candidates by kind, sites, kept, rolled back by reason, visible-debris count; `find_errors` loose
  BEFORE, after E8a+E3, after E8a+E3+E1; validate checks 1 and 3 and the floor PASS (check 2 fails on flicker_same,
  reversed and cracks until their engines exist; say so);
- six crops of visible debris and six of removed pieces (BEFORE | AFTER), looked at and described.
- **Times:** the sidewalks take 5-20 minutes each. CHTM-L05 takes an hour or more and needs several GB free; if
  the machine has under 4 GB free (`wmic OS get FreePhysicalMemory`), skip CHTM, say so, and hand in the sidewalks.

## Rules for this job

- Change only the files under Files. Never change `engine/guard/**`, `engine/validate/**`, `engine/fixes/**`,
  `FixProfile` or existing tests. No new dependency.
- Removal only: no new faces, no new points.
- Never use a bare `cd`. Stop only processes you started, by PID (never by image name). Write outputs only to
  `C:/Temp/e1/`. Never touch the owner's folders, the live export folder, the master `.skp`, the containers or the
  live database.
- Secrets: never open, print, log, write or commit `.env*` or any key file.
- Stop conditions: a test that cannot pass without loosening it, or an acceptance number that cannot be met: stop at
  that item, hand in what is committed, and list it under "Unsure about".

## Report

- `docs/superpowers/records/hermes/P2-E1-report.md`, in the format of `docs/superpowers/records/hermes/README.md`,
  with the real output of each acceptance command.
- Hand in with `tools/jobs.py done P2-E1 --branch hermes/P2-E1`.
