# Task P1-H1b brief: P0-review follow-ups, part 2

The base list is items 3-8 of `docs/superpowers/records/briefs/P1-H1-p0-review-followups.md` (read them there),
plus four items from the P1-H1 review and prompt audit. Each item is test-first and committed on its own.

## From the P1-H1 brief
- **3. Defence in depth in the reader:** `engine/io/skp_reader.walk_skp` calls `refuse_master` itself.
- **4. The verified copy follows `--out`:** `skp_check.require_verified_copy` takes the copy folder from
  `source.json` or the report, not only `data/campus/skp_copy/`.
- **5. One set of band edges for inventory and export:** store `z_range` unrounded, or round the edges before the
  inventory splits, so no face within 0.005 in of an edge can change floors between the two. A test pins it.
- **6. double_layers memory:**
  - measure the peak memory of the big-face pre-filter (K=200 × N boolean matrices) on the largest unit
    (Main_Infrustructure_Building, 142,234 faces; snapshot via `data/campus/source.json`);
  - bound it, for example with a K that shrinks as N grows;
  - results must stay identical to `double_layers_reference` (the existing speed tests).
- **7. Defaults never overwrite tracked records:** `campus-inventory --md` and `census` default to outputs under
  `data/`. Copying into `docs/superpowers/records/` becomes a deliberate step.
- **8. The export checks its inputs:** `error_export` fails when a member's snapshot sha256 differs from
  `campus_map.json`, not only when `n_faces` differs.

## From the P1-H1 review and prompt audit
- **9. The colour export uses the shared look split:**
  - `engine/campus/error_export.py` colours flicker with `engine/campus/materials.flicker_faces_by_look` (P1-H1);
  - the labels become FLICKER DIFFERENT LOOK / FLICKER SAME LOOK again, now true;
  - E4 and E5 will read the same function.
  - The colour export's existing tests may need their label expectations changed: name each such edit and why.
- **10. A public name:** rename `materials._material_name` (imported privately by `census.py`) to a public
  `material_name`.
- **11. `unit_before` must refuse a `source.json` row without `sha256`.** Today `if frozen and actual != frozen`
  skips the check.
- **12. The protected-path pre-check covers the older commands:** `engine.cli fix`, `errors` and `preview-data`
  get the same pre-check as the commands P1-H1 covered (`--out`, `--skp-dir`).

## Rules
- AGENTS.md §3-§7. Nothing in `engine/guard/**`; no `FixProfile` threshold change.
- Existing tests unedited, except where an item names the change.
- Real runs read only and write to temp folders.
- Run the full engine and tools suites once at the end.
