# Task P2-K0 brief: kernel prep for the P2 engines

**Why:** the end-of-P1 whole-branch review (opus) found four places that only a P2 (non-legacy) engine will
reach. They must be closed before E8 or any other new engine runs (ledger ruling P1-R1).

## Items

Each item is test-first, with a minimal non-legacy engine fixture: a small `RepairEngine` whose `plan()` returns
`Edit`s without running a legacy stage.

1. **A failed stage must not ship** (`engine/repair/kernel.py`, about :225-258).
   - **Today:** a stage whose failures are all charged to no site ends `FAIL` with every edit kept, and a stage
     that runs out of rounds ships kept sites never re-checked after the last rollback (`UNCONFIRMED`).
   - **Fix:** for a non-legacy engine, any final stage verdict other than PASS rolls the whole stage back (every
     edit dropped and logged with the reason), and the unit continues from the stage input.
   - Legacy stages keep today's behaviour (ruling K3-R2).
   - **Tests:**
     - all-unknown failures lead to a stage rollback;
     - exhausted rounds lead to a stage rollback;
     - a PASS stage keeps its edits.
2. **The edit log works for any engine** (`kernel.py` `edit_record`, about :57-65, used at :299).
   - **Today:** it needs `evidence["stage"]`, `["removed_keys"]` and `["added_keys"]`, which only legacy edits
     carry, so a P2 engine's `Edit` raises KeyError.
   - **Fix:** the kernel computes the removed and added face keys itself from the stage input and `apply_edits`,
     and takes the stage name from the engine.
   - **Test:** the minimal engine writes a valid `edit_log.jsonl`, with and without `--validate-sites`.
3. **Only E8 may add faces** (`engine/repair/types.py` about :79-93; AGENTS.md §4: generic hole filling is
   blocked, E8's narrow flat fill is the only exception).
   - **Fix:** for a non-legacy engine, an `add` edit is refused unless the engine is E8. A `cut` (replacing its
     own input faces) stays allowed as today.
   - The legacy observer still needs E7 adds: keep them behind an explicit, documented legacy marker (for example
     `Edit.legacy=True`, set only by `engines/legacy.py`).
   - **Tests:**
     - an E1-E7 non-legacy add raises;
     - E8 add accepted;
     - the legacy marker keeps the K2/K1b tests green unchanged.
4. **No material is its own look** (`types.py` :196-199 and `engine/campus/materials.py` :154-155).
   - **Today:** material index -1 (a face before any `usemtl`) resolves to `mesh.materials[-1]`, the LAST
     material.
   - **Fix:** a negative index is its own look, `"material:<none>"`, in `face_keys` and `material_name`.
   - **Test:** a two-face mesh with one face before `usemtl` gives distinct keys and the name `<none>`.

## Exit

- Each item red first, then green.
- `fix --kernel` and `fix --kernel --validate-sites` stay byte-identical to the base on sidewalk A, sidewalk B and
  CHTM 5th (`report.json` minus its skp path line, `.fixed.obj`, and `edit_log.jsonl` minus check lines), because
  the legacy path is unchanged.
- The full engine and tools suites pass. No existing test is edited, except to add the legacy marker where the
  observer builds edits (name each).

## Rules

- AGENTS.md §3-§7. Nothing in `engine/guard/**` or `engine/validate/**`; no `FixProfile` change.
- Real runs read the snapshots and write to temp folders, with
  `--skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"`.
- Stop only processes you started, by PID.
