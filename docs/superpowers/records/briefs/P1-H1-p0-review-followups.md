# Brief P1-H1: follow-ups from the end-of-P0 final review

**Job:** P1-H1 (either). **Branch:** from `feat/repair-p0` after the P0 phase merge, or from the P1 integration branch.
**Source:** the end-of-P0 whole-branch review (rules-reviewer, opus, 2026-10-08), which found the branch READY TO MERGE.
The fix round bb5a81e took the label finding and minors 3, 7, 9, 11, 14 and 15. The items below were parked with
rulings in the P0 ledger. None changes a result today. Each item is test-first and committed on its own.

## Items
1. **Flicker split by look (pin E4/E5 before the engines use it).** `find_errors` splits `flicker_diff` and
   `flicker_same` by material index. Decision-sheet answer 3 says same look = one material: identical-look flicker
   is E4, not E5. Add the look-based split, as `census.flicker_split` does from `materials.json`, to what the
   engines and the colour export consume. Keep `find_errors`' counts and file format unchanged unless a brief
   says otherwise.
   *Done when* E4 and E5 read one shared definition, with a test on two materials of one look.
2. **One output-path guard.** `refuse_protected(path)` in one module, used by every new writer:
   `error_export`, `skp_check`, `validate`, `census`, the `campus-*` commands and `decide-pilot`. It refuses the
   CHECKPOINT-17 export, master and backup folders on the resolved path (as `error_export._check_out` does
   since P0-18).
   *Done when* `campus-skp-check --out <export folder>` is refused, with a test.
3. **Defence in depth in the reader.** `engine/io/skp_reader.walk_skp` calls `refuse_master` itself.
4. **The verified copy follows `--out`.** `skp_check.require_verified_copy` takes the copy folder from
   `source.json` or the report, not only `data/campus/skp_copy/`.
5. **Band edges are the same in inventory and export.** Store `z_range` unrounded, or round the edges before
   the inventory splits, so that no face within 0.005 in of an edge can change floors between the two.
6. **double_layers memory on the largest units.** Measure the peak memory of the big-face pre-filter
   (K=200 × N boolean matrices) on the largest unit, then bound it, for example with a K that shrinks as N
   grows. P1-S3b measured only up to 91,714 faces.
7. **Defaults never overwrite tracked records.** `campus-inventory --md` and `census` write under `data/` by
   default; copying into `docs/superpowers/records/` is a deliberate step.
8. **The export checks its inputs.** `error_export` fails when a member's snapshot sha256 differs from
   `campus_map.json`, not only when `n_faces` differs.
9. **A unit's BEFORE and AFTER for the Validator.** The Validator takes one snapshot directory, but campus units
   are multi-member and band-split. Add a tool that builds a unit's BEFORE OBJ from its members (bands by
   face-centre z) for `validate --before`. Update `floor-validator.md` to use it.

10. **targets.json shape.** `load_targets` raises `ValueError` (the CLI's exit 2) when the file's JSON is not an
    object or its `kinds` is not an object; today a list raises `AttributeError` (re-review of bb5a81e).
11. **One missing-materials message.** `census.py`'s two "Materials map not found" messages both show the resolved
    path and say to pass `--materials`.

## Rules
AGENTS.md §3-§7. Nothing in `engine/guard/**` or the FixProfile thresholds. No existing test changes unless an
item names it.
