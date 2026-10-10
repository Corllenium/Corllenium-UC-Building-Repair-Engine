# Task P2-E1 brief: loose faces (zero-area, stray fragments, slivers, folds) as a repair engine

**Plan** (E1): a debris piece is removed only if the Validator's viewpoints (outside plus interior probes) see none
of its samples. Every visible piece goes to the floor review with a crop. **Spec** §4, E1: degenerate removal;
components through T-junctions and contact; ray-confirmed; **only invisible debris**; visible debris is listed.
**Owner (AGENTS.md §5):** visible debris stays and is listed with a picture. **Measured rule:** the Validator's floor
(§5 "Visible rule, measured"): no removed face may show more than 4 px at 0.02 in/px from any viewpoint at or above
the horizon, the ring cameras or the eye-height probes.

**Base:** `feat/repair-p1p2` = 0795710 (E8a/b/c, E3 and the floor Validator merged). Models to follow:
`engine/repair/engines/e3_hidden.py` (a non-legacy engine wrapping a legacy stage's candidates unchanged, one site
per edge-connected group, a dense pre-filter) and `e8_solidify.py`.

## Controller rulings

- **E1-R1, engine shape.** `engine/repair/engines/e1_loose.py`: `E1Loose`, non-legacy, name "E1", `remove` edits.
  - Candidates are exactly what the legacy `stage_fragments` (`engine/fixes/pipeline.py:866`) proposes today:
    `detect_fragments` (fragments and slivers), the fold members `_fold_members` chooses, **plus the zero-area
    faces** (`find_errors`'s `loose.zero_area`; ruling E3-R9 moved them here). Run those detectors unchanged, on
    the stage input; do not change `fragments.py`, `folds.py` or `pipeline.py`.
  - The legacy stage's own guards (`fragment_feedback`, `piece_ray_check`) are NOT used as the judge; the kernel's
    site check is. Record what the legacy guard would have said per site in the evidence (`legacy_rays`,
    `legacy_guard`), for comparison only.
- **E1-R2, sites.** One site per edge-connected group of candidate faces (welded `topo.face_w`), split above 512
  faces with E3's `split_group` (import it; do not copy it). A fold's chosen member and its partner are one site.
  Zero-area faces that touch no other candidate are grouped by the face they share an edge with, up to 64 per site.
- **E1-R3, the pre-filter is the floor measure.** Before the judge, every candidate piece is measured with the
  Validator's own `face_visible_pixels` (`engine/validate/floor.py`) from every Validator viewpoint (above-horizon
  directions, ring cameras, eye-height probes). A piece any face of which shows more than `VISIBLE_FLOOR_PX` from
  any viewpoint is not a candidate: it is **visible debris** and goes to `report.json` `e1.visible_debris` with a
  crop (reuse `fill_review.SpotCropper`). Import the constants; never redefine them.
- **E1-R4, the judge.** `validate_sites=True` as for E3. A charged site is rolled back and listed in
  `e1.rolled_back` with its reason.
- **E1-R5, solidify's faces are never debris** (the legacy rule): faces `SolidifyResult.new_faces` built, and any
  component holding one, are excluded. E1 runs after E8a (`--engines E8a,E3,E1`), and reads which faces are E8a's
  from the stage input's edit log keys as E3 does for `seen_through_shell`.
- **E1-R6, no change** to `engine/guard/**`, `engine/validate/**`, `engine/fixes/**`, `FixProfile`, or existing
  tests (name any exception and why).

## Failing tests first (`engine/tests/test_e1_loose.py`, plus a CLI test)

1. **Engine shape.** On a fixture with a stray one-face fragment, an attached sliver and two zero-area faces
   (build from `engine/tests/fixtures/build.py` helpers): E1 edits are non-legacy removes labelled E1; one site per
   group; `apply_edits` reproduces the legacy fragments stage's removal plus the zero-area faces (same face-key
   multiset) when nothing is rolled back.
2. **Visible debris stays and is listed.** A stray fragment 10 × 10 in standing in the open on a slab, seen from
   above: not a candidate; present in `e1.visible_debris` with pixels, viewpoint and a crop path; and the floor
   Validator on the output shows it still there.
3. **Invisible debris goes.** The same fragment inside a closed box: removed; the Validator's check 3 PASS with
   the floor PASS.
4. **Zero-area faces** on a slab are removed and labelled E1 with rule `zero_area`.
5. **A solidify face is never a candidate** (a fixture where E8a's new bottom would otherwise read as a stray).
6. **CLI:** `repair-unit --engines E8a,E3,E1` runs three stages in order, with three check lines; `e1` in
   `report.json` has `candidates`, `kept`, `rolled_back`, `visible_debris`.

## Exit (real output)

- Tests red, then green; the full engine and tools suites pass.
- **`repair-unit --engines E8a,E3,E1` on sidewalk A, sidewalk B and CHTM-L05** (the main checkout's data; pass
  `--materials`, and `--map "D:/PROJECTS/UC MODEL FIXER/data/campus/campus_map.json"` for CHTM; outputs to
  `C:/Temp/e1/`):
  - candidates by kind (fragment, sliver, fold, zero_area), sites, kept, rolled back by reason, visible debris
    count;
  - `find_errors` loose: BEFORE, after E8a+E3, after E8a+E3+E1;
  - `engine.cli validate --edit-log` on each output: checks 1 and 3 and the floor must PASS;
  - time, with the machine load.
- **Visual pass:** six crops of visible debris and six of removed pieces (BEFORE | AFTER), looked at and described.

## Rules

- AGENTS.md §3-§7. Removal only; no new faces, no new points.
- Test first; commit after each item, every commit green. Real runs write only to `C:/Temp/e1/`.
- Stop only your own processes, by PID. Never use a bare `cd`.
