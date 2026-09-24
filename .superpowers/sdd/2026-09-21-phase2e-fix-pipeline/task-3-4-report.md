# Task 3 & 4 implementation report

## Task 3: Guard

### What I implemented

- `engine/guard/__init__.py` (empty, package marker).
- `engine/guard/views.py`:
  - `VIEWS_26`: tuple of 26 `(x, y, z)` float tuples -- every nonzero combination of `(-1, 0, 1)`
    on each axis, each nudged by `(0.013, 0.007, 0.011)`. Ported from `spike/11_guard_feedback.py`'s
    `VIEWS`.
  - `ortho_first_hit(positions_c, faces, face_ids, view, frame_points, size=(900, 600),
    caster_factory=EmbreeCaster) -> (depth, tri)`: orthographic camera framed from `frame_points`
    (not from `faces`/`positions_c` directly), so a BEFORE/AFTER pair rendered with the same
    `frame_points` always has pixel-aligned buffers even when `faces` differs between the two
    calls. Ported from `first_hit` in `spike/11_guard_feedback.py` (camera math shared with
    `depth_image` in `spike/10_ds_visibility.py`), generalised to a configurable `size` and
    `caster_factory` instead of hard-coding `RayMeshIntersector`. Empty `faces` returns an
    all-miss buffer without constructing a caster.
- `engine/guard/compare.py`:
  - `PX_OK/PX_HOLE/PX_MATERIAL_CHANGED/PX_MOVED_SAME_FLAT/PX_MOVED_OTHER` -- per-pixel verdict
    codes.
  - `classify_pixels(before_depth, before_tri, after_depth, after_tri, material_before,
    material_after, flat_materials, depth_tol) -> codes (uint8, same shape)`: the shared,
    pixel-level classifier used by both `compare_views` and `guard_feedback`, in the brief's exact
    priority order (hole > material_changed > moved_same_flat/moved_other > ok).
  - `@dataclass ViewVerdict(view, model_px, holes, moved_same_flat, moved_other, material_changed)`.
  - `@dataclass GuardReport(views, passed, totals)`.
  - `compare_views(before, after, face_material_before, face_material_after, flat_materials,
    depth_tol, strict=False) -> GuardReport`: `before`/`after` are `Sequence[(view, depth, tri)]`
    (i.e. already-rendered `ortho_first_hit` outputs, paired by position), so this module never
    needs its own `views` parameter. `strict=True` folds `moved_same_flat` into the failure count.
  - `guard_feedback(candidates, positions_c, faces, face_material, flat_materials, depth_tol,
    strict, views=VIEWS_26, size=(900, 600), caster_factory=EmbreeCaster, max_rounds=8) -> (mask,
    history)`: the brief's signature ended in `...`; fixed per the controller ruling (full
    parameter list in "Public signatures" below). Renders BEFORE once against every face in
    `faces` (the caller's already-filtered renderable set -- e.g. non-degenerate only; `candidates`
    and the returned mask are indexed against this same array, not necessarily the mesh's full
    `face_w`), tentatively removes every candidate, then each round renders AFTER with the current
    kept faces and restores every candidate that is the BEFORE first-hit face at a failing pixel.
    Stops at 0 failing pixels or nothing left to restore, or after `max_rounds` (default 8)
    rounds. `positions_c` doubles as `frame_points` for every render (vertices never move).
- `engine/guard/render.py`:
  - `save_triptych(path, before, after, verdict_mask)`: `before`/`after` are `(depth, tri)` pairs
    for ONE view; `verdict_mask` is that view's `classify_pixels` code array. Writes one PNG,
    three `(H, W)` panels side by side (BEFORE silhouette | AFTER silhouette | DIFF), flat grey
    "hit" vs white background (no per-face lighting -- `ortho_first_hit` doesn't hand this module
    normals; `spike/06_render_classes.py`'s shading needs them directly). DIFF overlays
    `PX_HOLE`/`PX_MATERIAL_CHANGED`/`PX_MOVED_OTHER` in red and `PX_MOVED_SAME_FLAT` in amber onto
    the BEFORE silhouette.
- `engine/tests/test_guard.py`: 13 tests (see below).

### Design decisions not spelled out in the brief

- File split: `views.py` owns camera/rendering (`VIEWS_26`, `ortho_first_hit`); `compare.py` owns
  all pixel-level and feedback-loop logic (`classify_pixels`, `ViewVerdict`, `GuardReport`,
  `compare_views`, `guard_feedback`); `render.py` owns PNG output only.
- `guard_feedback`'s `faces`/`candidates` are NOT assumed to be the mesh's full `face_w` -- they
  are whatever array the caller passes (the real-data check passes only `ok`-filtered faces, then
  maps the returned mask back to original face indices itself via `ok_ids[mask]`). This keeps
  `guard_feedback` agnostic to the "degenerate face" concept, which belongs to `engine.vis.exposure`
  / `engine.pipeline`, not the guard.
- `compare_views`'s `strict` defaults to `False` (general-purpose, non-destructive comparison);
  `guard_feedback`'s `strict` has NO default -- it is deliberately required, since the controller
  ruling ties the correct value to which caller context is calling it (auto-removal vs
  person-accepted), and a silent default risks picking the wrong one.
- `classify_pixels` is exposed as a public function (not `_`-prefixed) because both `compare_views`
  and `guard_feedback` need the same per-pixel codes -- `compare_views` to aggregate counts,
  `guard_feedback` to find failing pixels and read off their BEFORE `tri` for restoration -- and
  `save_triptych` consumes the same code array for its DIFF panel.

### TDD evidence

RED -- before `engine/guard/` existed:
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_guard.py -q
ImportError while importing test module 'D:\PROJECTS\UC MODEL FIXER\engine\tests\test_guard.py'.
engine\tests\test_guard.py:5: in <module>
    from engine.guard.compare import (PX_HOLE, PX_MATERIAL_CHANGED, PX_MOVED_OTHER, PX_MOVED_SAME_FLAT, PX_OK,
E   ModuleNotFoundError: No module named 'engine.guard'
1 error in 0.20s
```
Failure was expected: the package did not exist yet.

One test needed a fix after the first implementation pass, not the implementation itself:
`test_ortho_first_hit_matches_cube_silhouette_and_miss_background` originally passed
`frame_points = positions_c` (the cube's own extent) and asserted both hit and miss pixels existed;
`ortho_first_hit` frames tightly to `frame_points` (only ~4% overscan), so at 20x20 resolution
every pixel landed inside the cube's silhouette -- correct behaviour, wrong test. Fixed by passing
`frame_points = positions_c * 2.0` so the cube visibly sits inside a larger frame with real
background at the edges.

GREEN -- after implementation (and the one test fix):
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_guard.py -q
.............                                                            [100%]
13 passed in 1.33s
```

Full suite after Task 3:
```
$ .venv/Scripts/python.exe -m pytest -q
........................................................................ [ 92%]
......                                                                   [100%]
78 passed in 1.62s
```
(65 pre-existing + 13 new; re-ran with `-W error::DeprecationWarning`, still 78 passed, no
warnings.)

### Tests written (`engine/tests/test_guard.py`)

1. `test_views_26_are_the_26_nudged_axis_and_diagonal_directions` -- exactly 26 views, each equal
   to some `{-1,0,1}^3 \ {0}` combination plus the exact nudge, every combination present once.
2. `test_ortho_first_hit_matches_cube_silhouette_and_miss_background` -- straight-down render of a
   cube inside a wider frame: hit pixels finite depth + valid `face_ids`, miss pixels `inf`/`-1`.
3. `test_ortho_first_hit_empty_faces_is_all_miss` -- zero faces never touches the caster, returns
   an all-miss buffer of the right shape.
4. `test_classify_pixels_priority_order` -- one synthetic pixel per code (`HOLE`,
   `MATERIAL_CHANGED`, `MOVED_SAME_FLAT`, `MOVED_OTHER`, two `OK`s), verifying the exact priority
   order against hand-picked before/after tri/depth/material arrays (no rendering).
5. `test_classify_pixels_empty_flat_materials_treats_everything_as_patterned` -- empty
   `flat_materials` -> a depth move on that face is `MOVED_OTHER`, never `MOVED_SAME_FLAT`.
6. `test_identity_all_counts_zero_and_passed` -- `box_with_partition()`, before==after render
   (26 views): every count 0, `passed` even under `strict=True`.
7. `test_delete_one_outer_face_fails` -- dropping one outer cube triangle: `not passed`, with
   `holes`/`moved_same_flat`/`moved_other` covering the possible outcomes (the removed triangle
   exposes the sealed inner partition to some views, which is a depth move, not necessarily a pure
   hole -- confirmed by inspecting the actual run: `moved_other` fires, not `holes`, because the
   fixture's inner partition backstops the hole and both faces share material 0, not in
   `flat_materials=frozenset()`).
8. `test_delete_hidden_inner_tris_all_zero_and_passed` -- dropping the two sealed partition tris
   (12, 13): all four counts 0, `passed` even under `strict=True`.
9. `test_material_change_on_visible_face_detected` -- same render for before/after, only
   `face_material_after[0]` changed: `material_changed > 0`, `not passed`, no holes/moves.
10. `test_open_box_flat_vs_patterned_removal_of_near_partition` -- `open_box_with_cells()`,
    dropping the near partition (10, 11): `flat_materials={0}` -> `moved_same_flat > 0`, `passed`;
    `flat_materials=frozenset()` -> `moved_other > 0`, `not passed`. Confirmed no holes occur in
    either case (the box's only true opening is the front face; removing the near partition always
    exposes either the deep partition or a fully solid wall).
11. `test_guard_feedback_restores_wrong_face_keeps_only_hidden_tris` -- candidates = `{12, 13,
    0}` (hidden tris plus one deliberately wrong visible outer face): round 0 restores exactly the
    outer face (`restored == 1`), final mask is exactly `{12, 13}`, last round has 0 failing
    pixels.
12. `test_guard_feedback_no_candidates_is_a_noop` -- empty candidate mask: mask stays empty,
    history has exactly one round with 0 failing pixels (loop exits immediately).
13. `test_save_triptych_writes_three_panel_png` -- writes a real PNG, checks it exists and its
    shape is `(H, W*3, 3)`.

### Real-data check

Script: `C:\Users\Future26\AppData\Local\Temp\claude\D--PROJECTS-UC-MODEL-FIXER\5472478e-978d-426b-bab2-e7cf21699a70\scratchpad\task3_real_data_check.py`
(not part of the repo).

Loaded `data/snapshots/ce26e0392ab0/CHTM_SIDE_WALK_2nd_floor.obj` with `read_obj`, ran
`analyse_topology`, recentred `positions_w` to its bbox centre, ran `compute_exposure`/
`classify_exposure` with defaults. Candidates = faces classed `EXP_HIDDEN` (restricted to the
`ok`-face subset, as `guard_feedback` expects). `flat_materials = {0}`, `depth_tol = 0.15`
(matching the spike's `TOL` exactly, for numeric comparison -- NOT the `1.5 * max(axis_quanta)`
production default), `strict=True`, `views=VIEWS_26`, `size=(900, 600)`.

Result -- **exact match on the first run, no divergence to investigate**:
```
candidates (EXP_HIDDEN, over all faces): 1853
ok faces: 4475 candidates within ok faces: 1853

history:
  {'round': 0, 'candidates_remaining': 1853, 'failing_pixels': 223, 'restored': 34}
  {'round': 1, 'candidates_remaining': 1819, 'failing_pixels': 0, 'restored': 0}

final removable: 1819
restored: 34

expected: {'candidates': 1853, 'round0_restored': 34, 'final_removable': 1819}
MATCH
```
Timing: `read=0.017s analyse_topology=0.492s compute_exposure=0.463s guard_feedback=11.851s
total=12.824s`. `guard_feedback` dominates because it constructs a fresh `EmbreeCaster` per
`ortho_first_hit` call (26 views x 2 rounds = 52 renders at 900x600 = ~540k rays each), matching
the spike's own approach (it also rebuilds `RayMeshIntersector` on every call) rather than reusing
one caster across rounds.

Since the numbers matched exactly, there was no port-vs-spike difference to diagnose.

Triptych saved to `data/output/_guardcheck/CHTM_SIDE_WALK_2nd_floor__top_oblique.png` (git-ignored,
`data/` is in `.gitignore`), view `(0.45, 0.55, -0.70)`, size `(900, 600)`, before = all `ok` faces,
after = `ok` faces minus the final 1819 removable faces. Verified: `2700x600` RGB (3 panels of
900x600), and only 2 distinct colours present (background white, model grey) -- consistent with
the reported 0 failing pixels in the final state (no red/amber anywhere in the DIFF panel).

### Files changed

- `engine/guard/__init__.py` (new)
- `engine/guard/views.py` (new)
- `engine/guard/compare.py` (new)
- `engine/guard/render.py` (new)
- `engine/tests/test_guard.py` (new)

### Self-review

- `trimesh`/`embreex` are not imported directly anywhere in `engine/guard/` -- verified with
  `grep -n "^import\|^from" engine/guard/*.py`; the only mentions of `trimesh`/`embreex` are in a
  docstring in `views.py`. Rendering goes through `engine.rays.caster.EmbreeCaster`.
- No `import` of `api`, `spike`, `fastapi`, or `sqlalchemy` anywhere in `engine/guard/`.
- No random numbers anywhere in `engine/guard/` or `engine/tests/test_guard.py`.
- No vertex positions are ever mutated; `guard_feedback` only ever changes which faces are
  included in a render, never `positions_c`.
- `moved_same_flat` is always reported in `totals` and every `ViewVerdict`, and is never a failure
  unless `strict=True` -- covered by tests 6, 8, 10, and by the real-data check (`strict=True`
  throughout).

### Concerns

- `guard_feedback` rebuilds an `EmbreeCaster` (and thus an Embree BVH) once per view per round
  rather than reusing one across rounds for the AFTER renders (BEFORE is computed once). This
  matches the spike's own behaviour and produced the exact expected numbers, but it is the reason
  the real-data run takes ~12s; a future performance pass could cache/rebuild the caster only when
  the kept-face set actually shrinks between rounds. Not changed here since the spike does the
  same thing and matching its numbers exactly was the acceptance bar.

Commit: `4d22c3a feat(engine): depth and colour aware facade guard with feedback`

## Task 4: Remove faces with provenance

### What I implemented

- `engine/fixes/__init__.py` (empty, package marker).
- `engine/fixes/remove.py`:
  - `remove_faces(mesh: MeshData, drop: np.ndarray) -> tuple[MeshData, np.ndarray]`: `drop`
    (bool, `(mesh.n_faces,)`) marks faces to remove. Builds `keep = ~drop`, `source_face =
    np.nonzero(keep)[0].astype(np.int64)` (new face index -> original face index, preserving
    relative order), and returns `dataclasses.replace(mesh, face_v=mesh.face_v[keep],
    face_vt=mesh.face_vt[keep], face_vn=mesh.face_vn[keep],
    face_material=mesh.face_material[keep], face_line=mesh.face_line[keep])` alongside
    `source_face`. `positions`, `uvs`, `normals`, and `materials` are passed through unchanged (the
    same arrays/list as the input `mesh`, via `dataclasses.replace` only overriding the five
    per-face fields) -- no re-indexing, no compaction, so vertex/UV/normal ids stay comparable to
    the original mesh across versions. Raises `ValueError` if `drop`'s shape doesn't match
    `(mesh.n_faces,)`.
- `engine/tests/test_remove.py`: 4 tests (see below).

### TDD evidence

RED -- before `engine/fixes/` existed:
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_remove.py -q
ImportError while importing test module 'D:\PROJECTS\UC MODEL FIXER\engine\tests\test_remove.py'.
engine\tests\test_remove.py:3: in <module>
    from engine.fixes.remove import remove_faces
E   ModuleNotFoundError: No module named 'engine.fixes.remove'
1 error in 0.20s
```
Failure was expected: the package did not exist yet.

GREEN -- after implementation:
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_remove.py -q
....                                                                     [100%]
4 passed in 0.11s
```

Full suite after Task 4:
```
$ .venv/Scripts/python.exe -m pytest -q -W error::DeprecationWarning
........................................................................ [ 87%]
..........                                                               [100%]
82 passed in 1.65s
```
(78 pre-existing (after Task 3) + 4 new, no warnings.)

### Tests written (`engine/tests/test_remove.py`)

1. `test_dropping_nothing_is_identity` -- an all-`False` `drop` on `cube()` (12 faces): every
   per-face array equal to the original, `positions`/`uvs`/`normals`/`materials` untouched,
   `source_face == arange(12)`.
2. `test_dropping_faces_keeps_order_of_survivors` -- dropping faces `{3, 7}`:
   `source_face == [0,1,2,4,5,6,8,9,10,11]` (relative order preserved), `n_faces == 10`,
   `positions` still untouched.
3. `test_source_face_maps_back_exactly` -- dropping `{1, 5, 9}`: `new.face_v == m.face_v
   [source_face]` and likewise for `face_vt`/`face_vn`/`face_material`/`face_line`.
4. `test_round_trip_through_write_and_read_preserves_face_count` -- dropping `{0, 2, 4}`, then
   `write_obj` + `read_obj`: reloaded `n_faces == new.n_faces == 9`.

### Files changed

- `engine/fixes/__init__.py` (new)
- `engine/fixes/remove.py` (new)
- `engine/tests/test_remove.py` (new)

### Self-review

- No imports of `api`, `spike`, `fastapi`, `sqlalchemy`, `trimesh`, or `embreex` anywhere in
  `engine/fixes/` -- verified by grep; `remove.py` only imports `dataclasses.replace`, `numpy`,
  and `engine.model.MeshData`.
- No random numbers anywhere in `engine/fixes/` or `engine/tests/test_remove.py`.
- No vertex positions are ever moved or re-indexed -- `positions`/`uvs`/`normals` are the exact
  same array objects as the input `mesh` (verified in `test_dropping_nothing_is_identity` and
  `test_dropping_faces_keeps_order_of_survivors` via `np.array_equal`, and by inspection: `replace`
  only overrides the five per-face fields).
- `face_line` carries over unchanged (subset only, values not renumbered) per the brief.

### Concerns

None.

Commit: `34d3f00 feat(engine): face removal with provenance`

## Public signatures
(appended by controller from the implementer's final message, verbatim)

engine/guard/views.py
  VIEWS_26: tuple of 26 (x,y,z) view directions
  ortho_first_hit(positions_c, faces, face_ids, view, frame_points, size=(900, 600), caster_factory=EmbreeCaster) -> (depth (H,W) float64 inf=miss, tri (H,W) int64 -1=miss, values drawn from face_ids)
engine/guard/compare.py
  PX_OK=0, PX_HOLE=1, PX_MATERIAL_CHANGED=2, PX_MOVED_SAME_FLAT=3, PX_MOVED_OTHER=4
  classify_pixels(before_depth, before_tri, after_depth, after_tri, material_before, material_after, flat_materials, depth_tol) -> uint8 codes
  ViewVerdict(view, model_px, holes, moved_same_flat, moved_other, material_changed); GuardReport(views, passed, totals)
  compare_views(before, after, face_material_before, face_material_after, flat_materials, depth_tol, strict=False) -> GuardReport   # before/after: sequences of (view, depth, tri)
  guard_feedback(candidates, positions_c, faces, face_material, flat_materials, depth_tol, strict, views=VIEWS_26, size=(900, 600), caster_factory=EmbreeCaster, max_rounds=8) -> (surviving mask, history list[dict])
engine/guard/render.py
  save_triptych(path, before=(depth, tri), after=(depth, tri), verdict_mask) -> None
engine/fixes/remove.py
  remove_faces(mesh, drop) -> (new_mesh, source_face int64: new index -> original face index)
