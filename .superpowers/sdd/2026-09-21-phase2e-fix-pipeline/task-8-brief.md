### Task 8: Outward orientation + one-sided completeness

Added 2026-09-21 after the user asked that the fixed object also be correct with one-sided rendering.
Measured on the real files (double-sided occlusion, each side of a face tested separately): file A has **727**
visible faces (18.1 % of visible area) whose only exposed side is the BACK, file B **800** (15.8 %). Another
330 / 561 faces have both sides exposed, of which only 82 / 107 are roughly equal-sided true thin sheets.

**Files:** Modify `engine\vis\exposure.py`, `engine\fixes\pipeline.py`, `engine\cli.py`. Create `engine\fixes\orient.py`,
`engine\tests\test_orient.py`.

**Interfaces — Produces:**
`compute_side_exposure(positions_c, face_w, ok, caster_factory=EmbreeCaster, n_dirs=128) -> tuple[np.ndarray, np.ndarray]`
(front, back fractions, each escaping rays / (`n_dirs` * 4); `compute_exposure` becomes their sum and keeps returning
exactly the same values as today, pinned by a test),
`ORIENT_OK=0, ORIENT_FLIP=1, ORIENT_THIN_SHEET=2`,
`classify_orientation(front, back, ok, sheet_ratio=0.5) -> np.ndarray[uint8]`: `FLIP` when `back > front`;
`THIN_SHEET` when both > 0 and `min/max >= sheet_ratio`; else `OK`. Hidden faces are `OK` (they get removed anyway).
`flip_faces(mesh, flip: bool mask) -> MeshData`: reverses vertex order of `face_v`, `face_vt`, `face_vn` for those faces
and negates nothing else. Vertices are not moved. Source `vn` of a flipped face is dropped (`-1`), so no normal points backwards.
`one_sided_holes(positions_c, faces, face_ids, views, size) -> int`: pixels that hit in a double-sided render but
whose first hit is back-facing to the camera. Reported BEFORE and AFTER.

Pipeline order becomes: exposure -> hidden removal under strict guard -> (accepted slit removal) -> **orientation flip** ->
merge -> final guard. Flipping never changes a double-sided render, so the guard verdict must be identical with and
without the flip step: that is a test. `FixResult` gains `flipped`, `thin_sheets`, `one_sided_holes_before`,
`one_sided_holes_after`. Thin sheets are reported, not changed: completing them one-sided means adding a second face,
which is new geometry and stays a reviewed, later fix.

- [ ] Tests: `compute_exposure` unchanged (exact array equality before/after this task on `box_with_partition`);
  a cube with 3 faces deliberately reversed -> exactly those 3 classed `FLIP`, after `flip_faces` all outward and
  `one_sided_holes == 0`; a single free-standing quad -> `THIN_SHEET`, untouched; guard report equal with and without flips.
- [ ] Real data: file A must class **727** faces `FLIP` (same sampling as the measurement above) and report
  `one_sided_holes` before and after over the 26 views. After must be lower than before. Paste both numbers.
- [ ] Commit `feat(engine): outward orientation and one-sided completeness`.

