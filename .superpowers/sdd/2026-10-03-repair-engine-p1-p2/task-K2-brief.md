# Task K2 brief: the observe-only kernel

The plan text (docs/superpowers/plans/2026-10-03-repair-engine-p1-p2.md, Task K2):
- **Files:** create `engine/repair/kernel.py`, `engine/repair/engines/legacy.py` and
  `engine/tests/test_kernel_observe.py`.
- **What:** `repair_unit(unit, ctx)` runs today's `fix_object` stages through thin engine wrappers, in the same
  order and with the same parameters, and writes `edit_log.jsonl`.
- **Exit:**
  - `report.json` is byte-identical to today's `engine.cli fix` on sidewalk A, sidewalk B and CHTM 5th;
  - the edit log accounts for every face removed or added.

## The controller's design (binding)

1. **Split `fix_object` into stages: a pure refactor.**
   - `engine/fixes/pipeline.py::fix_object` (line 621 on) is one function holding seven stages, in this order:
     solidify; pass 1 (hidden and degenerate); pass 2 (slit); fragments and slivers; orientation; covered
     same-material duplicate layers (overlap); the region merge with its rollback.
   - Move each into a stage function in the same module that takes and returns one explicit state object: the
     mesh, the reference ids, the accumulated report dict, and whatever later stages read.
   - `fix_object(mesh, flatness, profile)` keeps its signature and `FixResult`. It becomes a loop over that stage
     list.
   - No change to any computation, order, parameter, random seed, guard, tolerance or report key.
   - `engine/guard/**` and the `FixProfile` thresholds are untouched.
2. **The legacy engines.** `engine/repair/engines/legacy.py` wraps each stage as a `RepairEngine` (the K1
   protocol in `engine/repair/types.py`). Engine names:

   | Stage | Engine |
   |---|---|
   | solidify | E8 |
   | pass 1 | E3 (hidden) plus E1 (degenerate) |
   | pass 2 | E3 |
   | fragments and slivers | E1 |
   | orientation | E2 |
   | overlap | E4 |
   | merge | E7 |

   Pass 1 removes hidden and zero-area faces together under one guard. Its wrapper may label the edits per face
   from the report's own lists, or log them as one engine; say which.
3. **Edits come from observation, not from a re-implementation.**
   - Each wrapper runs its stage, then derives its `Edit`s by comparing K1 `face_keys` before and after the
     stage:
     - a key that disappears is a remove;
     - a face whose key returns with reversed winding is a flip;
     - a new key is an add.
   - Solidify adds new points, so it is an E8 add carrying `new_points`.
   - The merge replaces each region's triangles with a new triangulation of the same region and existing points
     only. Log it as E7 cut edits with no `new_points`.
   - The kernel must not alter the stage's output mesh. The edits are a record. K3 will start applying them.
   - **Duplicated faces.** Stacked exact duplicates are common in this data, so a key can occur more than once.
     Treat keys as a multiset and count occurrences.
4. **The kernel.** `repair_unit(unit: UnitState, ctx: RepairContext)`:
   - runs the legacy engines in the stage order;
   - returns the final mesh and the same `report.json` dict that `fix_object` + `cmd_fix` produce;
   - writes `edit_log.jsonl`, one JSON line per `Edit`. Each line holds engine, kind, the face keys removed and
     added, the counts, the site (one site per stage is fine for now) and the reason. Arrays are written as
     lists; there is no path or timestamp in the log.
5. **The CLI.** `engine.cli fix` gains a flag `--kernel`. Without the flag it is unchanged. With it, the same
   run goes through `repair_unit` and also writes `edit_log.jsonl` next to `report.json`. Every real-data run
   passes `--skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"`.

## Exit (each with real output in your report)

- **The three golden units.** The snapshots are in the main checkout: `data/snapshots/ce26e0392ab0` (sidewalk A,
  `CHTM_SIDE_WALK_2nd_floor`), `data/snapshots/0b290ec0bcb4` (sidewalk B), `data/snapshots/c0c877002500-b7c2dc01`
  (CHTM 5th, about 6 minutes).
  - First run `engine.cli fix` at the BASE commit (the K2 worktree before your changes, or a scratch checkout of
    the base) into a short temp folder.
  - Then run your branch with and without `--kernel`.
  - In both cases the `report.json` bytes must be identical to the base (compare the sha256), and so must the
    `.fixed.obj`.
- **The edit log accounts for every face.**
  - A test asserts: input faces − removes + adds = output faces, per stage and in total.
  - A test asserts the multiset of output keys equals the multiset of input keys − removed + added.
  - Run the same check on the three units' real logs.
- **The stage refactor is proven equivalent:** the whole existing engine suite passes unchanged. No existing
  test is edited.
- **Determinism:** two `--kernel` runs on sidewalk A give byte-identical `report.json` and `edit_log.jsonl`.

## Rules

- AGENTS.md §3-§7.
- Python as AGENTS.md §8, in a subshell with PYTHONPATH set to the worktree. Never a bare `cd`.
- Real-data runs read the snapshots only and write to temp or scratch folders. Never write to the owner's folders
  or the export folder.
- Test first. Commit after each item, and stage files by name.
- If byte-identity fails, stop and report the first differing key. Never adjust a report key to make it match.
