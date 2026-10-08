# Task K3 brief: site validation and rollback

The plan text (docs/superpowers/plans/2026-10-03-repair-engine-p1-p2.md, Task K3):
- **What:** after each engine, run the Validator (P0) in fast mode on the touched sites only. A failing site is
  bisected down to the smallest failing set of edits; those are rolled back and logged with the Validator's
  evidence.
- **Exit:**
  - a deliberately bad edit mixed into good ones is the only one rolled back (fixture);
  - the time per site is within the budget measured on CHTM 5th.

## Facts the controller measured

- `engine/validate/checks.py::validate(before, after, looks, ...)` samples EVERY face of BEFORE. On CHTM 5th the
  whole run takes about 570 s (P0-15). `engine/validate/sampling.py::face_samples(mesh, faces=None, ...)` already
  accepts a face subset.
- The K2 kernel (`engine/repair/kernel.py`, `engine/repair/engines/legacy.py`) observes each stage's edits.
  `apply_edits(stage_input, stage_edits)` reproduces each stage's output (K2 measured this on A, B and CHTM 5th).
  K2 documented its limits for you:
  - `LegacyEngine.plan()` runs the stage as a side effect;
  - flipping both members of a coincident pair is invisible to the multiset;
  - solidify may log E8 flips;
  - new points are numbered per edit, so a vertex shared by two adds is carried twice; de-duplicate when
    applying;
  - merge cuts are grouped by material, one site per stage.

## The controller's design (binding)

### 1. A focus mode in the Validator (the judge), additive and proven equal

- `validate(..., focus=None)`. `focus` is a `Focus(before_faces: ndarray, after_faces: ndarray)` of face ids to
  sample.
  - With focus, checks 1 and 3 sample only those faces. The viewpoints, tolerances and the rest are unchanged.
  - Check 2 (`find_errors`) is skipped and reported as `"skipped (focus)"`. A focus run never gives a floor
    verdict; it only answers "did these sites break anything?".
- **Proof:** a test shows that `focus` = all faces gives a report equal to `focus=None` in checks 1 and 3 (same
  counts, reasons and sites) on two fixtures.
- **Independence:** the validator still imports nothing from `engine/repair`, `engine/fixes` or `engine/guard`.
  The existing independence tests must keep passing unchanged.
- Nothing else in `engine/validate` changes. Existing tests stay unedited.

### 2. The focus set of a site

The site is the faces whose result could change. In BEFORE (the stage's input):
- the faces the site's edits remove, flip or replace;
- every face within the site's bounding box grown by `SITE_MARGIN_IN` (start at 24 in; measure);
- the **cover candidates**: faces that, from any standard viewpoint or eye-height probe, lie behind a face the
  site adds. Find them by casting from each viewpoint through the new faces' sample points into BEFORE. This is
  what the Validator's own "covered" test needs.

In AFTER: the faces the site adds.

### 3. Site checks and rollback in the kernel

- `repair_unit(..., validate_sites=False)`. With it off, everything is exactly K2 (byte-identical outputs).
- With it on, after each engine:
  - group the stage's edits into sites. Legacy stages give one site per stage; a site of more than
    `SITE_MAX_FACES` touched faces is split spatially, by a grid over face centres;
  - for each site, build `after = apply_edits(stage_input, kept_edits)` and run `validate(stage_input, after,
    focus=site_focus)`;
  - a failing site is **bisected**: split its edits in half, re-check each half, and recurse to the smallest
    failing subsets. Edits that pass are kept.
  - **Rolled-back edits** are written to `edit_log.jsonl` with `"rolled_back": true`, the Validator's failing
    sites, reasons and sample counts. Evidence crops come only when asked, to keep this fast.
  - **The next stage runs on the kept result,** `apply_edits(stage_input, kept_edits)`, not on the legacy stage's
    raw output. This is the one place K3 changes behaviour, and only with `validate_sites` on.
- `engine.cli fix --kernel --validate-sites` turns it on.

### 4. Budget

- Item 1 of your work: measure the focus run's cost per site on CHTM 5th, at sites of 50, 500 and 5,000 touched
  faces, and the cover-candidate step separately. Report the numbers before tuning anything.
- Then set `SITE_MAX_FACES` and the budget: the whole `--validate-sites` run on CHTM 5th takes at most 3× the
  plain `fix` run. If that is not reachable, STOP and report the measured costs. The controller decides.

## Exit (real output for each)

- **Fixture:** good edits plus one deliberately bad edit (it removes a visible face, or adds a face that covers a
  visible one). Only the bad edit is rolled back; the log says why; the good ones stay.
- **Mutation:** each of the P0-16 mutation-table defects, when introduced as an edit, is caught and rolled back
  by the site check.
- **Proofs:**
  - the focus-equals-full proof (item 1);
  - `validate_sites=False` stays byte-identical to K2 on A, B and CHTM 5th (`report.json` and `.fixed.obj`
    sha256).
- **CHTM 5th with `--validate-sites`:** the time, the sites checked, the sites failed, the edits rolled back
  (with their engines), and the final face count.
  - The Validator judged the legacy output FAIL (P0-16: about 21,000 visible samples deleted), so rollbacks ARE
    expected. Report them as the first measured result of the kernel's rule.
- **The whole engine suite passes.**

## Rules

- AGENTS.md §3-§7.
- Nothing in `engine/guard/**`; no `FixProfile` threshold changes; no existing test edited.
- Real runs read the snapshots and write to temp or scratch folders only, with
  `--skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"`.
- Test first; commit after each item; stage files by name.
- If the focus-equals-full proof fails, STOP and report. Never relax a Validator check to make it pass.
