# Task P2-E3 brief: hidden faces, interior-aware, as a repair engine

**Plan** (E3): faces unseen from outside AND from every interior probe, and not on a side mesh, may be removed.
**Spec** §4 table, E3: unseen from **outside and from interior probes**, floor alone; never side meshes; never room
surfaces. **Owner (AGENTS.md §5):** the strict visible rule. Viewpoints are outside, **and inside at eye height**.

**Measured need (P1, legacy hidden stage, CHTM 5th):** the legacy stage FAILs its per-stage check, deleting about
22,000 visible samples (ledger, "FIRST PER-STAGE VERDICTS").

**Base:** `feat/repair-p1p2` = 9cae2d2 (E8 complete). Interfaces:
- `E8Solidify` (`engine/repair/engines/e8_solidify.py`) is the model to follow: a non-legacy engine wrapping a legacy
  stage, one site per piece, judged by `validate_sites=True`;
- `engine.cli repair-unit (--unit | --snapshot) --engines ... --out`, exit codes 0/1/2/3;
- the P2-K0 kernel rules.

## Controller rulings

- **E3-R1, engine shape.** `engine/repair/engines/e3_hidden.py`: `E3Hidden`, non-legacy, name "E3".
  - `plan()` computes the hidden candidates exactly as the legacy hidden stage does today: `stage_hidden` in
    `engine/fixes/pipeline.py`, with `compute_side_exposure`, `classify_exposure` and the guard feedback. Read
    them; do not change them.
  - It returns `remove` edits labelled `E3`.
  - **One site per connected group of candidate faces**: faces sharing an edge, within the candidate set. A
    group larger than **512 faces** is split by a spatial grid, so one visible face cannot roll back a whole
    storey's interior.
  - Evidence: face count, area, exposure numbers, and which legacy rule made each face a candidate.
- **E3-R2, the judge is the Validator.**
  - Every site is checked with `validate_sites=True`. A group whose removal deletes any sample seen from any
    viewpoint (outside directions, ring cameras, **eye-height probes**) is rolled back.
  - The guard's own thresholds stay untouched (nothing in `engine/guard/**`, no FixProfile change).
  - Report how the Validator's `deleted` check judges a sample: one witness ray, or every line? Compare
    P2-E8a concern 3, where `covered` uses one witness. Say whether removal could hide that gap. Do not change
    `engine/validate/**`. If you find a gap, report it with a measured example.
- **E3-R3, never side meshes.** Faces that the legacy pipeline marks as a slab side, or that solidify built or
  kept as a side, are never candidates.
  - Find how the pipeline marks them (search `side` in `engine/fixes/pipeline.py`, `solidify.py` and
    `orient.py`), and name the rule you used.
  - **Test:** a closed slab whose side face is unseen from every viewpoint is still not removed.
- **E3-R4, never room surfaces.** Any face that an eye-height probe sees from either side is not a candidate,
  before the judge runs. This is the cheap pre-filter; the judge is the safety net.
  - **Test:** a closed room (floor, four walls, ceiling) inside a building shell, seen only from its probe: none of
    its faces is removed.
- **E3-R5, no winding-number second opinion now.** The plan's libigl second opinion needs the owner's OK to install,
  so it is not in this job. Record where exposure and probes disagree (a candidate the exposure calls hidden that
  a probe sees) as `disagreements` in report.json, so a later job can use them.
- **E3-R6, ordering.**
  - `--engines` accepts a comma list, run in order, for example `--engines E8a,E3`. E3 works best after solidify
    has closed the slabs.
  - `E8` keeps meaning E8a then E8b.
  - Unknown names exit 2.

## The failing tests first (`engine/tests/test_e3_hidden.py`, plus a CLI test)

1. **Engine shape.** On a closed box with an internal partition (an existing fixture with hidden interior faces,
   for example `box_with_partition`):
   - E3 edits are non-legacy `remove` edits labelled E3, one site per connected group;
   - `apply_edits` reproduces the legacy hidden stage's own removal (the same face-key multiset) when nothing is
     rolled back.
2. **Strict rule.** A fixture whose hidden-candidate group includes one face seen only from an eye-height probe:
   - that group is rolled back;
   - the other groups are kept;
   - the log reason is `deleted`.
3. **E3-R3:** a side face unseen from every viewpoint is never a candidate.
4. **E3-R4:** a closed room seen only from its probe keeps every face.
5. **Group splitting:** a 2,000-face candidate group becomes at least 4 sites, and every site has at most 512 faces.
6. **CLI:**
   - `repair-unit --engines E8a,E3` runs two stages in order and writes both check lines;
   - `--engines E3,bogus` exits 2.

## Exit (real output)

- The tests red, then green; the full engine and tools suites pass; no existing test edited.
- **On CHTM 5th, sidewalk A and sidewalk B with `--engines E8a,E3`:**
  - candidate faces and groups;
  - sites kept and rolled back, by reason;
  - faces removed;
  - the Validator's deleted count after rollback (must be 0; the legacy hidden stage deleted about 22,000 samples
    on CHTM 5th);
  - `find_errors` hidden count: BEFORE, after E8a, after E8a+E3;
  - disagreements;
  - time.
- **Visual pass:** BEFORE | AFTER crops of at least six kept groups (inside views from a probe and from outside),
  looked at and described.

## Rules

- AGENTS.md §3-§7. Nothing in `engine/guard/**` or `engine/validate/**`; no FixProfile change.
- Removal only; no new faces, no new points.
- Test first; commit after each item. Real runs write only to temp folders.
- Stop only your own processes, by PID.
