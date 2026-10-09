# Task P2-E8a brief: strict solidify as a repair engine

**Plan** (Tasks E1-E8, E8): solidify covers only 0 %-visible faces (the owner's strict rule, AGENTS.md §5: "a
rebuilt side may cover only faces that are 0 % visible"). The plan's text says "solidify's `cover_max_exposure`
becomes 0". **Spec** §4 table, E8: solidify covers only 0 %-visible faces.

## Measured fact and ruling E8-R1 (controller)

- `engine/guard/compare.py` (about :1500-1511) documents why `cover_max_exposure` is a threshold (0.10), not 0. A
  face seen only through a small opening never measures exactly 0 by ray sampling, and with 0 the skirt that
  closes `open_box_with_cells` is refused.
- **Ruling:** the strict rule is enforced by the **Validator**, not by changing the guard's threshold.
  - Each solidify piece is its own site, checked by the K3b kernel (`validate_sites`). The check covers every
    sample any viewpoint sees: outside directions, cameras, and the eye-height probes inside.
  - A piece that covers ANY such sample is rolled back. That is "0 % visible", judged by the owner's own Validator.
  - The guard's 0.10 stays as a cheap pre-filter. `FixProfile.cover_max_exposure` is not changed, and nothing in
    `engine/guard/**` changes.
  - Pieces rolled back this way leave the hole open. Those holes go to E8b (narrow flat fill) or E8c (the
    needs-modelling queue).

## Design (binding)

1. **`engine/repair/engines/e8_solidify.py`: `E8Solidify`, a `RepairEngine`** (name "E8", `legacy=False`).
   - `plan(unit, ctx)` runs `engine.fixes.solidify.solidify` on the unit's mesh (no change to solidify's
     geometry).
   - It returns `Edit`s, **one site per built piece**: a side wall run or a bottom. If solidify does not expose
     its pieces today, add a read-only way to group its new faces into pieces, without changing what it builds.
   - Edits:
     - an add, carrying `new_points`, `new_face_uv` and `new_face_normal` (K1b);
     - or a cut for a replaced broken piece;
     - each with `reason` and `evidence` (piece kind, edge run, thickness, the solidify report row).
2. **The kernel runs it with `validate_sites=True`.** Charged pieces are rolled back. The stage verdict must be
   PASS after rollback, or the whole stage is rolled back (P2-K0 item 1).
3. **A floor-level command:**
   - `engine.cli repair-unit --unit <UNIT> --engines E8 --out <dir>` builds the unit's BEFORE with
     `campus-unit-before`, runs the kernel with E8 only, and writes `<unit>.fixed.obj`, `edit_log.jsonl` and
     `report.json` (sites kept and rolled back, by reason).
   - Every real run passes `--skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"` if it writes a `.skp`, and
     writes only to a temp or scratch folder.
4. **Carried from P2-K0:** `engine/campus/unit_before.py:112` must treat a negative material index as
   "material:<none>", matching `face_keys` and `material_name`.

## The failing tests (write them first, commit, see them fail)

- **Engine shape** (`engine/tests/test_e8_solidify.py`): `E8Solidify().plan()` on `slab_with_three_skirts` (and the
  other solidify fixtures in `engine/tests/fixtures/build.py`) returns E8 edits:
  - non-legacy;
  - one distinct site per piece;
  - `apply_edits(input, edits)` reproduces solidify's own output mesh (same face keys and UVs) when nothing is
    rolled back.
- **Strict rule, covering a visible sample:** a fixture where a rebuilt piece covers a face that only an
  eye-height probe sees, for example `compartment_with_deep_wall` or a room seen through a gap. With
  `validate_sites=True` that piece is rolled back, the other pieces are kept, and the log names the reason
  (covered).
- **Strict rule, covering nothing visible:** a fixture where every piece covers only unseen faces. All pieces are
  kept and the stage passes.
- **No-material face:** a fixture face with material -1 in `unit_before` gets "material:<none>".

## Exit (real output)

- The tests above: red, then green.
- **On CHTM 5th, sidewalk A and sidewalk B (real units, E8 only):**
  - pieces built, kept and rolled back, with reasons;
  - the Validator's covered count for the stage after rollback, which must be 0, against the legacy solidify's
    13,350 covered samples on CHTM 5th;
  - time.
- **The full engine and tools suites pass.** No existing test edited; nothing in `engine/guard/**`; no
  `FixProfile` change.

## Rules

- AGENTS.md §3-§7. Only `engine/fixes/solidify.py` invents vertices (E8 is its engine).
- Test first; commit after each item.
- Stop only your own processes, by PID.
