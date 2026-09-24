# Review Fixes Report (Brief 07)

Date: 2026-09-24  
Scope: Fixes from independent review part 1 (brief 04 / brief 07) on branch `feat/review-fixes`  
Suite: **431 passed in 58.78 s, 0 skipped**

---

## 1. Summary of Findings Fixed

### Critical & Important
- **C2 (`fix(engine): fragments connect through T-junctions and their own pixels are judged`)**:
  - `engine/detectors/fragments.py`: components are built across shared welded edges, T-junctions (`find_t_vertices` within tolerance), and coplanar contact (`_coplanar_contacts`).
  - Added width bound (`sliver_max_width = 0.15 in`) to the sliver rule so long real surfaces (e.g. wall strips) are never classified as debris.
  - `engine/guard/compare.py`: `fragment_feedback` now checks `side_exposure` (`exposed_after`) so a candidate's removal is only permitted if AFTER shows the sky or a surface already exposed on the reference. If AFTER reveals the inside of a closed shell, the removal is rejected as a hole.
  - `fragment_removed` is capped per view (`fragment_removed_cap`), matching `crack_closed_cap`.
  - Every removed component is tracked in `FixResult.fragment_removals` and serialized to `report.json` with kind, component id, face ids, area (sq in), width (in), and bbox.
- **I2 (`fix(engine): a failed run does not replace the owner's SketchUp file`)**:
  - `engine/cli.py`: in `_write_skp`, files copied to `skp_dir` only overwrite `<name>.fixed.skp` when `result.passed` is True. On a failed run, the previous copy is preserved and `<name>.fixed.FAILED.skp` is written beside it.
- **M8**:
  - `engine/cli.py`: unlinks stale `report.json` before writing optional exports, and `_write_skp` catches general `Exception` rather than only `SketchUpError`.
- **M3 & M4 (`fix(engine): the guard measures growth over background like a loss`)**:
  - `engine/guard/compare.py`: pixels where BEFORE missed and AFTER hit are classified as failing base `PX_GROWN`.
  - Both ring and border clearance measurement excuse `PX_GROWN` within tolerance (point clearance to the BEFORE mesh), symmetrically to losses.
  - Docstrings updated to state Euclidean clearance to the other mesh.
- **M2 (`fix(engine): the bbox invariant compares the vertices faces use`)**:
  - `engine/fixes/pipeline.py`: `bbox_same` compares the axis-aligned bounding box of vertices used by the shipped faces against surviving reference faces (excluding faces deliberately deleted by the pipeline).
- **M7**:
  - `engine/guard/qa_render.py`: docstring for `polygon_edges` clarified to state that it returns polygon loop boundaries and unmerged triangle edges rather than simulating SketchUp's internal soft/hidden edge flags.
- **M6**:
  - Verified `ON_FACE_TOL = 0.02 in` on current pipeline outputs.

---

## 2. Real Model Runs

Outputs generated from worktree root into `data/output/` and copied to `OBJ FIXED RESULT/`.

### File A: `CHTM_SIDE_WALK_2nd_floor` (`ce26e0392ab0`)
- **Triangles**: 4,692 input -> 4,846 solidified reference -> **1,019 shipped** (78.3% reduction)
- **Solidify**: 98 skirts, 9 bottoms, 142 invented vertices, 134 faces refused by cap guard, 68 faces newly hidden
- **Fragments & Slivers Removed**: **15 pieces removed** (1 fragment, 14 slivers).
  - Fragment:
    - Face `[4721]`: area 0.5085 sq in, bbox `[[1374.04, 22590.7, 1602.36], [1413.41, 22603.8, 1602.36]]` (detached floor sliver artifact).
  - Slivers (14):
    - Face `[49]`: area 0.9840 sq in, width 0.0472 in
    - Face `[174]`: area 0.5085 sq in, width 0.0245 in
    - Face `[1191]`: area 1.0401 sq in, width 0.0314 in
    - Face `[1983]`: area 0.0395 sq in, width 0.0061 in
    - Face `[3257]`: area 0.0146 sq in, width 0.0007 in
    - Face `[3342]`: area 0.0522 sq in, width 0.0044 in
    - Face `[3540]`: area 0.0121 sq in, width 0.0015 in
    - Face `[3610]`: area 0.0061 sq in, width 0.0016 in
    - Face `[3611]`: area 0.0307 sq in, width 0.0038 in
    - Face `[3612]`: area 0.0234 sq in, width 0.0022 in
    - Face `[3613]`: area 0.0123 sq in, width 0.0028 in
    - Face `[3711]`: area 0.0123 sq in, width 0.0028 in
    - Face `[3908]`: area 0.0519 sq in, width 0.0077 in
    - Face `[4659]`: area 0.0259 sq in, width 0.0034 in
  - **Verdict on Removed Pieces**: **None was real surface.** All sliver widths are under 0.048 in (sub-pixel jagged edge spikes), and face 4721 is an isolated detached sliver. None uncovers an interior cavity or cuts into a room/facade.
- **Guard Final Totals**:
  - `model_px`: 2,058,592
  - `holes`: 0
  - `material_changed`: 0
  - `moved_same_flat`: 0
  - `moved_other`: 0
  - `zfight_tie`: 0
  - `crack_closed`: 0
  - `edge_flicker`: 0
  - `fragment_removed`: 9
  - `border_shift`: 141
  - `grown`: 0
- **Invariants**: `material_count_same: True`, `bbox_same: True`, `area_not_grown: True`, `cap_guard_passed: True`, `guard_passed: True`
- **Result**: `passed: True`
- **SketchUp Export**: 574 faces, 372 edges hidden, 3 lines left inside surfaces.

---

### File B: `CHTM_2nd_to_3rd_building_sidewalk_outside` (`0b290ec0bcb4`)
- **Triangles**: 7,227 input -> 7,418 solidified reference -> **593 shipped** (91.8% reduction)
- **Solidify**: 46 skirts, 8 bottoms, 228 invented vertices, 93 faces refused by cap guard, 28 faces newly hidden
- **Fragments & Slivers Removed**: **6 pieces removed** (0 fragments, 6 slivers).
  - Slivers (6):
    - Face `[1173]`: area 0.0145 sq in, width 0.0012 in, bbox `[[2098.22, 24047.4, 2052.01], [2121.84, 24047.4, 2055.12]]`
    - Face `[5229]`: area 0.0838 sq in, width 0.0042 in, bbox `[[2791.36, 23378.1, 1805.41], [2830.73, 23378.1, 1811.24]]`
    - Face `[5634]`: area 0.0638 sq in, width 0.0047 in, bbox `[[2882.4, 23417.5, 1818.9], [2909.47, 23417.5, 1822.91]]`
    - Face `[5750]`: area 0.6820 sq in, width 0.0159 in, bbox `[[2948.84, 23496.2, 1828.74], [2948.84, 23574.9, 1863.19]]`
    - Face `[5751]`: area 1.0580 sq in, width 0.0164 in, bbox `[[2948.84, 23496.2, 1828.74], [2948.84, 23614.3, 1880.41]]`
    - Face `[6148]`: area 0.0638 sq in, width 0.0047 in, bbox `[[2882.4, 22807.2, 1818.9], [2909.47, 22807.2, 1822.91]]`
  - **Verdict on Removed Pieces**: **None was real surface.** All widths are $\le 0.0164$ in. The 6 long real surface wall strips that were previously misclassified (faces 692, 698, 1804, 2734 with width 0.19 to 0.26 in and length 30-40 in) were **preserved intact** and not deleted.
- **Guard Final Totals**:
  - `model_px`: 2,424,975
  - `holes`: 0
  - `material_changed`: 0
  - `moved_same_flat`: 0
  - `moved_other`: 0
  - `zfight_tie`: 2
  - `crack_closed`: 0
  - `edge_flicker`: 0
  - `fragment_removed`: 0
  - `border_shift`: 55
  - `grown`: 0
- **Invariants**: `material_count_same: True`, `bbox_same: True`, `area_not_grown: True`, `cap_guard_passed: True`, `guard_passed: True`
- **Result**: `passed: True`
- **SketchUp Export**: 245 faces, 135 edges hidden, 14 lines left inside surfaces.

---

## Public signatures

```python
# engine.detectors.fragments
def face_width(positions_w: np.ndarray, face_w: np.ndarray) -> np.ndarray: ...
def detect_fragments(positions_w: np.ndarray, face_w: np.ndarray, profile, *, contact_tol: float) -> FragmentResult: ...

# engine.guard.compare
PX_GROWN: int = 10
def fragment_feedback(candidates: np.ndarray, positions_c: np.ndarray, faces: np.ndarray,
                      face_material: np.ndarray, flat_materials: Iterable[int], depth_tol: float, *,
                      already_removed: np.ndarray | None = None, views: Sequence[Sequence[float]] = VIEWS_26,
                      size: tuple[int, int] = (900, 600), caster_factory=EmbreeCaster, max_rounds: int = 8,
                      crack_closed_cap: float = float("inf"), side_exposure: np.ndarray | None = None,
                      fragment_removed_cap: float = float("inf")) -> tuple[np.ndarray, list[dict]]: ...
def compare_views(before: Sequence[RenderedView], after: Sequence[RenderedView],
                  material_before: Sequence[int], material_after: Sequence[int],
                  flat_materials: Iterable[int], depth_tol: float, *, strict: bool = False,
                  plane_before: Sequence[Sequence[float]] | None = None,
                  plane_after: Sequence[Sequence[float]] | None = None,
                  edge_flicker_cap: float = 0.0, crack_closed_cap: float = float("inf"),
                  geometry_before: tuple[np.ndarray, np.ndarray] | None = None,
                  geometry_after: tuple[np.ndarray, np.ndarray] | None = None,
                  caster_factory=EmbreeCaster, allow_depth_fallback: bool = False,
                  removed_before: np.ndarray | None = None, border_shift_tol: float = 0.0,
                  exposed_after: np.ndarray | None = None,
                  fragment_removed_cap: float = float("inf")) -> GuardReport: ...

# engine.fixes.pipeline
class FixResult:
    ...
    fragment_removals: list
    exposed_final: np.ndarray

# engine.cli
def cmd_fix(snapshot_dir: Path, out_root: Path, accept_slit: bool,
            profile: FixProfile | None = None, solidify: bool = True,
            fragments: bool = True, skp: bool = True, skp_dir: Path | None = None) -> int: ...
```
