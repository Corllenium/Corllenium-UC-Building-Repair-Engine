### Task 3: Guard

**Files:** Create `engine\guard\__init__.py`, `views.py`, `compare.py`, `render.py`, `engine\tests\test_guard.py`

**Interfaces — Produces:**
`VIEWS_26` (the 26 axis/diagonal directions, each nudged by `(0.013, 0.007, 0.011)`),
`ortho_first_hit(positions_c, faces, face_ids, view, frame_points, size=(900, 600), caster_factory=EmbreeCaster) -> tuple[depth (H,W) float64 inf=miss, tri (H,W) int64 -1=miss]` (`tri` holds `face_ids` values),
`@dataclass ViewVerdict(view, model_px, holes, moved_same_flat, moved_other, material_changed)`,
`@dataclass GuardReport(views: list[ViewVerdict], passed: bool, totals: dict)`,
`compare_views(before, after, face_material_before, face_material_after, flat_materials, depth_tol) -> GuardReport`,
`guard_feedback(candidates: bool (F,), render_after: Callable[[bool mask], list[(depth, tri)]], before, ...) -> tuple[bool mask, list[dict] history]`.

Pixel verdicts, in this order: **hole** = hit before, miss after. **material_changed** = both hit, material index
differs. **moved_same_flat** = both hit, same material, that material is flat, `|dt| > depth_tol`.
**moved_other** = both hit, same patterned material, `|dt| > depth_tol`. `passed` = holes + material_changed +
moved_other == 0. `moved_same_flat` is reported, never silently ignored, never a failure.
Default `depth_tol = 1.5 * max(axis_quanta)`.

`guard_feedback`: render, find failing pixels, every candidate face that is the BEFORE first hit at a failing pixel
is restored, repeat, stop at 0 failures or 8 rounds. Returns the surviving mask and per-round history.

`render.py`: `save_triptych(path, before, after, verdict_mask)` writes BEFORE | AFTER | DIFF (failures red,
`moved_same_flat` amber) as one PNG.

- [ ] **Step 1: failing mutation tests** on `box_with_partition()`:
  identity -> every count 0, `passed`; delete one outer face -> `holes > 0` or `moved_*` > 0, not passed;
  delete the 2 hidden inner tris -> all 0, passed; change one outer face's material to a second material ->
  `material_changed > 0`, not passed; flat vs patterned: on `open_box_with_cells()` deleting the near partition gives
  `moved_same_flat > 0` and passes when the material is flat, fails (`moved_other > 0`) when it is patterned.
  `guard_feedback`: candidates = hidden tris + one deliberately wrong outer face -> the outer face is restored in
  round 1, final mask keeps exactly the hidden tris.
- [ ] **Step 2:** implement. **Step 3:** tests pass.
- [ ] **Step 4: real-data check:** candidates = hidden faces of file A -> feedback ends with **1,819** removable,
  **34** restored, 0 failures over 26 views (spike numbers). Report the real history.
- [ ] **Step 5:** Commit `feat(engine): depth and colour aware facade guard with feedback`.

