# Task P2-E8b brief: the narrow flat fill (owner exception)

**Owner exception (AGENTS.md §4, 2026-10-03).** A hole whose whole border lies in one plane matching the
neighbouring surface may be filled, using existing points only. Each fill is shown in the floor review. The
invariant "area never grows" allows exactly these fills.

**Plan** (E8): the border is planar and matches a neighbour plane; triangulate with earcut or constrained Delaunay
on existing points only; show each fill in the review. Every other hole goes to E8c (`needs_modelling.json`).

**Base:** `feat/repair-p1p2` after the P2-E8a merge. Interfaces from there:
- `E8Solidify`;
- `engine.cli repair-unit (--unit | --snapshot) --engines ... --out`, with exit codes 0/1/2/3;
- the kernel rules from P2-K0 (only E8 adds; a non-PASS non-legacy stage is rolled back whole; `validate_sites=True`
  on every P2 command-line path).

## Controller rulings

- **E8b-R1, which holes.** A candidate is one closed loop of open edges:
  - every vertex on it has exactly two open edges of that loop;
  - it is simple (it does not cross itself) after projection to its plane;
  - it has no inner loop; a hole inside a hole goes to E8c.
- **E8b-R2, "flat" and "matches the neighbour", measured, never argued.** Every loop point lies within
  `plane_tol = 2 × print_step` of the least-squares plane through the loop. Every face that shares a loop edge has
  its normal within **1°** of that plane's normal, up to sign, and lies in that plane within `plane_tol`. A
  neighbour face that is not coplanar (a wall meeting a floor at the hole's border) disqualifies the loop:
  E8c.
- **E8b-R3, "narrow".**
  - The hole's largest inscribed circle diameter is at most **39.37 in** (one Minecraft block, 1 m), measured in
    the plane.
  - Anything larger goes to E8c.
  - The report gives the diameter histogram on the three golden units, so the owner can tune the cap. The cap is a
    named constant, not a FixProfile field.
- **E8b-R4, look and UV.**
  - Every neighbour face of the loop has one look key (`face_keys` look; `material:<none>` counts as a look);
    otherwise E8c.
  - The fill's UV is the neighbours' UV continued: fit one affine map (plane xy → uv) to all neighbour face
    corners with `engine.topo.planes.fit_uv`. If the largest residual is above `1e-3` (UV units), the neighbours
    do not continue one map: E8c.
  - The fill's winding faces the same side as its neighbours.
- **E8b-R5, existing points only.**
  - Fill triangles index the loop's own vertices: `new_points=None` and `kind="add"`, labelled `engine="E8"`, with
    `evidence["material"]`, `new_face_uv` and `new_face_normal`.
  - Triangulate with an ear-clipping implementation written in the repo, or merge.py's own triangulation if it
    takes a loop. **No new dependency.** No Steiner points.
  - The triangle count must equal `n - 2` for an `n`-vertex loop. Each fill's area equals the polygon's area
    within 1e-6 relative.
- **E8b-R6, the Validator's named class for fill sites.** This is the owner's exception made measurable; it is the
  analogue of E5's z-fight class.
  - A fill closes a hole people could see through, so the Validator would call what lay behind it "covered". That
    is the purpose of the fill, not a loss.
  - Add to `engine/validate` ONE named class, `fill_site`: a BEFORE sample counts as `covered_by_fill`, not
    `covered`, only if:
    - every viewpoint line that saw it in BEFORE now ends on a face the edit log marks as an E8 flat fill;
    - and the hit point lies inside that fill's own loop polygon.
  - Such samples are counted, listed per fill with a crop, and do not fail check 3. Everything else is unchanged.
  - Tests first, including mutations that must still FAIL:
    - a fill polygon one cell larger than its loop (covering a visible face beside the hole);
    - a "fill" not marked in the edit log;
    - a fill in another look than its neighbours.
  - This is the only change allowed in `engine/validate/**`. Nothing in `engine/guard/**`. No FixProfile change.
- **E8b-R7, ordering.**
  - `repair-unit --engines E8` runs E8a (solidify) and then E8b (fill) as two kernel stages; `--engines E8a` or
    `E8b` runs one.
  - Each fill is its own site.
  - A fill that the site check charges (anything other than `covered_by_fill` samples) is rolled back, and its loop
    goes to E8c.
- **E8b-R8, the review list.** `report.json` gets `fills`: one row per kept fill, with:
  - site, loop vertex count, area (in²), inscribed diameter, look, centroid, normal;
  - a crop path: BEFORE | AFTER, from a viewpoint that saw through the hole.

  It also gets `not_filled`: every candidate loop refused, with the rule that refused it. E8c reads that list.

## Failing tests first (`engine/tests/test_e8_flat_fill.py` and `engine/tests/test_validate_fill_site.py`)

1. A flat slab with a square hole whose neighbours are one look and one UV map. One fill, `n - 2` triangles, no new
   points, the neighbours' UV continued, and the slab's open edges go to 0.
2. Each refusal leaves its loop unfilled and listed with the reason:
   - a non-planar border (one corner raised 3 print steps);
   - a hole with a wall at its border (a neighbour at 90°);
   - two looks around the hole;
   - a UV seam around the hole (residual above 1e-3);
   - a 1.5 m wide hole;
   - a hole with an inner hole.
3. The Validator class:
   - a hole in a floor that shows a room below. With the fill, check 3 PASSes, with `covered_by_fill > 0` and
     `covered == 0`.
   - Each of the three mutations in E8b-R6 FAILs check 3.
4. The kernel and the CLI:
   - `repair-unit --engines E8` on a fixture with one fillable hole and one refused hole gives one kept fill, one
     `not_filled` row, and exit 0;
   - the edit log has the fill as an `add` with no `new_points`.

## Exit (real output)

- The tests above, red then green; the full engine and tools suites pass.
- **On CHTM 5th, sidewalk A and sidewalk B with `--engines E8`:**
  - candidate loops, fills kept and rolled back, `not_filled` by reason;
  - the inscribed-diameter histogram;
  - open edges and cracks: BEFORE, after E8a alone, and after E8a plus E8b (P2-E8a: CHTM-L05 open edges 346 →
    373, cracks 3,884 → 3,898);
  - time.
- **Visual pass:** BEFORE | AFTER crops of at least six kept fills across the three units, looked at and described.

## Rules

- AGENTS.md §3-§7.
- New faces use existing points only. Fill only inside E8, and only for loops that meet R1-R5.
- Test first; commit after each item. Real runs write only to temp folders, with
  `--skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"` if a `.skp` is written.
- Stop only your own processes, by PID.
