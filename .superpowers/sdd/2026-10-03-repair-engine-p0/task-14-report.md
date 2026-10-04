# Task 14 (P0-14): the implementer's reports (handed back as text) and the controller's rulings

Branch `claude/P0-14`, worktree `.claude/worktrees/P0-14`, from 76d74bb.
Raw outputs and scripts: `<session scratchpad>/p0-14/`.

## Round 1: DONE_WITH_CONCERNS
**Commits:**
- ce5aa37 samples and UV;
- 9e4d3a6 viewpoints;
- 8f8ffee visibility (the brief's step-5 message);
- ecbcb30 argument guards.

**Files:** `engine/validate/{__init__,sampling,viewpoints,visibility}.py` and `engine/tests/test_validate_core.py` are new. `engine/tests/fixtures/build.py` gets +26 lines at the end (`closed_room`, a two-skin room: inner wound inward plus an outer skin 8 in out).

**Tests:** 40; engine 851 + 1 xfail. Red per item (collection errors), then green; mutation checks per rule.

**Interfaces** as the brief, plus:
- `interior_probes(..., caster=None)`;
- `VisibleSet` carries the viewpoints, with columns dirs | cams | probes, `seen` and `front` matrices, and properties `visible`, `front_seen`, `back_seen`, `seen_outside`, `seen_inside`;
- helpers `recentred`, `bbox_centre`, `used_bbox`, `check_frame` (|coord| ≤ 8192 in), `build_caster`, `check_caster`, `face_normals` (from the winding; zero or float-noise area gives no normal), `face_areas`.

**Semantics:**
- a direction is seen when the ray toward -dir escapes (`any_hit`);
- a camera or probe is seen when the first hit along the segment is beyond it (t ≥ reach − 0.02 in);
- the step-off is `EPS_ORIGIN` 0.02 in toward the viewer;
- edge-on (|cos| ≤ 1e-6) sees nothing;
- there is no field-of-view or range limit.

**Independence:** an AST test forbids `engine.guard`, `engine.fixes` and `engine.vis` imports in `engine/validate/`.

**Smoke (read-only):**
- sidewalk A: 7,227 faces, 838 probes, 1.25 M pairs/s;
- CHTM 5th: 20,599 faces, 1,577 probes.

**Concerns:**
1. probes inside walls: 181 of 1,577 on CHTM 5th;
2. roof probes;
3. both sides of a back-to-back pair count as seen (`_Cull = 0`);
4. the sign of dir;
5. the 0.02 in step-off;
6. edge-on viewpoints;
7. no field-of-view or range limit;
8. dense bool matrices, so cast in sample chunks;
9. the probe lattice is anchored to the mesh's bbox: compute it from BEFORE and reuse it for AFTER;
10. the `closed_room` face order is relied on;
11. normals come from the winding only;
12. line endings.

## Controller's rulings, then round 0 (fix before review)
- **Concern 1: FIX** with a majority back-face vote. 26 rays (`outside_directions(26)`) are cast from each candidate's eye point. A first hit seen from behind (dot(n, ray) > 0) counts as back; an escape, a front, or a face with no normal counts as air. Reject when back > 13. Tests (a)-(d) were given.
- **Concern 2: KEEP** (stricter is safe).
- **Concerns 3-12:** no change in P0-14; carried to P0-15:
  - the E5/E4 allowed-change class for the inward copy;
  - the best-conditioned viewpoint per sample;
  - chunked casting;
  - probes from BEFORE reused for AFTER.
- dir reading: the viewer is at -dir, matching the brief.

## Round 0 result: DONE
**Commit:** 2513c1e `fix(validate): interior_probes drops candidates that stand inside a solid, by a majority back-face vote`. Changes only `viewpoints.py` and the test file. The branch is purely additive against 76d74bb: 6 files, +1,455.

**Tests:** 49 in the file (+9); engine 860 + 1 xfail in 450 s.
- (a) a wall taller than the headroom, and its open-bottom twin: RED before (3 probes inside the wall), green after.
- (b), (c), (d) are over-rejection and determinism guards, green before and after, with red shown by mutation.
- Exactly 13 backs is kept (the boundary test).
- An independent brute-force vote count agrees where no ray hits a coincident pair.

**Mutants:**

| Mutant | Tests failed |
|---|---|
| no vote | 2 |
| any back rejects | 2 |
| half rejects | 1 |
| front counted as back | 11 |
| vote after the dedupe | 2 |
| vote from the surface | 3 |
| 10 votes | 3 |

**The vote runs before the dedupe**, so a cell whose lattice point lies in a wall still gets its open-floor centroid.

**Measured on CHTM 5th:** 1,577 probes became 1,397.
- 177 of the 181 flagged probes were dropped.
- 4 were kept with 12, 12, 13 and 13 backs. Three sit exactly on a coincident ±x pair (a two-sided zero-thickness wall).
- 10 unflagged probes were dropped, with 15-25 backs, in wall masses.
- All 1,386 probes with 0 backs were kept, and 1,390 old probes are unchanged.

**Other floors** (flagged probes, and how many were dropped):

| Floor | Flagged | Dropped | Unflagged dropped |
|---|---|---|---|
| sidewalk A | 0 | 0 | 0 |
| CHTM 2nd | 144 | 122 | 7 |
| BRS 10th | 135 | 121 | 0 |
| Science A plan 3 | 156 | 150 | 2 |
| CHTM 6th | 205 | 197 | 2 |

**Plan views:** `chtm5_probes_after_vote.png` and `chtm5_zoom_east.png`. The controller looked at the first: the open floor keeps a regular ~1 m lattice, the light wells have no probes, and the dropped probes sit on wall lines (the east wall most clearly). The yellow rings are flagged but kept: 3 lower left and 1 right edge.

**Optional idea, not done** (the ruling was explicit): drop a candidate whose eye point lies within 0.05 in of a face plane inside that face, to catch on-plane ties.
