# Task S2 brief: one topology analysis per stage

**Plan** (docs/superpowers/plans/2026-10-03-repair-engine-p1-p2.md, Tasks S1-S3, row S2):
- **Change:** reuse one `analyse_topology` per pipeline stage.
- **Exit:**
  - byte-identical reports on A, B and CHTM 5th;
  - time measured.

The design spec measured that `analyse_topology` runs 4-5 times per fix (spec §"Measured facts").

## Facts

- P1-K2 split `engine/fixes/pipeline.py::fix_object` into seven stage functions over one `FixState` (`FIX_STAGES`,
  `start_fix`, `finish_fix`). The kernel wraps them; `engine.cli fix --kernel` and the plain `fix` both run them.
- `analyse_topology` is defined in `engine/pipeline.py` (line ~45).

## Design (binding)

1. **Measure first.** On CHTM 5th, count the `analyse_topology` calls per run and time each, per stage and in
   total, and note the inputs (mesh, flat-material set). Report the table before changing anything.
2. **Reuse, as a pure optimisation.**
   - Compute `analyse_topology` once for each distinct (mesh state, flat-materials) a stage needs.
   - Carry the result in `FixState` or a memo keyed by the mesh's identity and content (e.g. sha256 of
     positions + face_v + face_material, and the flat set), so a changed mesh is never served a stale topology.
   - No change to any computation, order, parameter, guard, tolerance or report key.
3. **The result must be bit-identical.** If two call sites pass different inputs (e.g. a different flat set or a
   modified mesh), they are different keys: never merge them.

## Exit (real output)

- **Call counts and times** before and after, per stage, on CHTM 5th, sidewalk A and sidewalk B.
- **Byte-identity** against the base: `report.json` (minus its skp path line), `.fixed.obj`, `.fixed.ngon.obj`, and
  with `--kernel` also `edit_log.jsonl`, on the three units (`data/snapshots/ce26e0392ab0`,
  `data/snapshots/0b290ec0bcb4`, `data/snapshots/c0c877002500-b7c2dc01` in the main checkout). Every run passes
  `--skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"` and writes only to a short temp folder.
- **A memo test:** a modified mesh is never served the old topology. Mutate one vertex and check that the memo
  recomputes.
- **The whole engine suite passes.** No existing test edited; nothing in `engine/guard/**`; no `FixProfile`
  threshold change.

If byte-identity fails, STOP and report the first differing key and stage.
