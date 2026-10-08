# Task K3b brief: kernel site checks, attribute and confirm

**Why** (ruling K3-R2):
- K3 built the Validator's focus mode and `engine/site_judge.py` (conservative site focus with shadow-volume
  cover candidates). Both are merged on `feat/repair-p1p2`.
- Measured on CHTM 5th:
  - a conservative site focus is about the whole floor, so one focus run costs about one full Validator run
    (about 570 s);
  - spot-by-spot bisection costs 9-20× a plain fix before any bisection.
- The legacy stages are not rolled back spot by spot; the P2 engines replace them.

## Design (binding)

### 1. Attribute and confirm, instead of bisection by repeated runs

With `validate_sites=True`, per engine stage:
1. **Run once.** `after = apply_edits(stage_input, stage_edits)`. Run ONE focus validate whose focus is the union
   of every site's focus (`SiteJudge`). Collect its failing samples, each with its BEFORE face and its sample
   point.
2. **Attribute.** Charge each failing sample to every site that could have caused it:
   - the sample's face is one of the site's touched faces;
   - or the sample's face lies within the site's grown box;
   - or the sample's face is in the site's shadow-volume cover candidates AND one of the site's new faces lies
     between that sample and one of the viewpoints that saw the sample. Use a cheap exact or conservative ray or
     box test.

   A sample charged to no site is a **legacy or unknown failure**. Log it as such; it is never silently dropped.
3. **Roll back** every site with at least one charged failure: drop all its edits.
4. **Confirm.** Rebuild `after` from the kept edits and run ONE confirming focus validate on the union focus of the
   kept sites.
   - If it still fails on samples charged to kept sites, repeat steps 2-4, at most 3 rounds.
   - Then roll back every site that is still charged, and log `"rounds_exhausted": true`.
5. **Next stage.** The next stage runs on `apply_edits(stage_input, kept_edits)`.

### 2. Sites and logging

- **Sites come from the engines.** An `Edit.site` id groups edits.
  - The legacy engines give one site per stage, so a legacy stage either passes or is rolled back as a whole.
  - Under ruling K3-R2 a legacy stage is **NOT** rolled back by default. With `validate_sites=True` and a legacy
    engine, log the stage verdict (pass, or the failing count by reason) and keep the edits, unless the caller
    passes `rollback_legacy=True`. That flag exists only for tests.
- **The edit log gains, per checked stage:** `{"check": {...}}` records with the run times, the failing counts by
  reason, the sites rolled back (ids, charged sample counts, reasons) and the unknown failures.
  - A rolled-back edit gets `"rolled_back": true`.
  - No timestamps.

### 3. Carried from the K3 reviews

- **Cost and memory of the cover step:**
  - measure `SiteJudge` cover seconds and peak memory on CHTM 5th and on the largest unit (the Main
    Infrastructure split, about 142k triangles);
  - add a cheap cull before the per-viewpoint test: test against the union box's shadow first, or use a spatial
    grid;
  - make `_VIEW_BLOCK` bound the memory to ≤ 500 MB per block. Conservativeness must stay exact: the existing
    subset property tests must keep passing.
- Add a direct parametrised unit test of `_meets_shadow` edge cases: an eye inside or on the box, a direction
  parallel to an axis, a touching face.
- `site_judge` docstring: the candidate set is deliberately large; that is the price of being conservative.
- Finding 6: covers from other sites' faces are counted, overlays are not. Attribution resolves it, because a
  failure is charged only to the sites that could have caused it. Add a test with two sites where only one
  covers.

### 4. CLI

`engine.cli fix --kernel --validate-sites` runs this. Without `--validate-sites`, outputs stay byte-identical to
K2 and K1b.

## Exit (real output for each)

- **Fixture with two good sites and one bad site** (a remove of a visible face, or an add that covers one): only
  the bad site is rolled back after round 1; the confirming run passes; the log shows the charge.
- **Fixture where a failure is charged to no site:** logged as unknown, nothing rolled back, never dropped.
- **Each P0-16 mutation defect, as an engine site among good ones:** it is the one rolled back.
- **`validate_sites` off:** byte-identical to the base on A, B and CHTM 5th (`report.json` without its skp path
  line, `.fixed.obj`, `edit_log.jsonl`).
- **CHTM 5th with `--kernel --validate-sites`** (legacy, no rollback):
  - per-stage verdicts with failing counts by reason, and the total time;
  - this is the measured cost of a checked legacy run;
  - report it, and do not tune the Validator.
- **Cover-step measurements** before and after the cull, with memory, on CHTM 5th and the largest unit.
- **The whole engine suite passes.**

## Rules

- AGENTS.md §3-§7. Nothing in `engine/guard/**`; no `FixProfile` threshold change; no existing test edited.
- No change to the Validator's checks: focus mode as merged.
- Real runs read the snapshots only and write to temp or scratch folders, with
  `--skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"`.
- Test first; commit after each item.
- If the conservativeness property tests fail after the cull, STOP and report.
