# Final-review fix wave — brief

Repo `D:\PROJECTS\UC MODEL FIXER`, branch `phase1a-engine`, Windows. Bash tool with POSIX syntax, repo path in
bash is `/d/PROJECTS/UC MODEL FIXER`. ALWAYS use `.venv/Scripts/python.exe`. 35 tests pass before you start.

## Rules

- TDD for every item: failing test FIRST, run it, see it fail, then implement, see it pass.
- One commit per item, message as given, trailer on every commit:
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`
- Existing tests stay unmodified unless an item says otherwise.
- `engine/` imports nothing from `api`, `spike`, fastapi, sqlalchemy.
- Vertices are never moved, weld stays exact.
- Do not touch `spike/`, `preview/`, `docs/`, `data/` (reading is fine). No refactors beyond the items.
- Never dispatch subagents.
- Check `git log --oneline 0dc2d1f..HEAD` first: if some items are already committed (an earlier run was
  interrupted), skip those and continue with the next one.

## Baseline (do this before changing anything)

Script under `C:\Users\Future26\AppData\Local\Temp\claude\D--PROJECTS-UC-MODEL-FIXER\5472478e-978d-426b-bab2-e7cf21699a70\scratchpad`:
`analyse_topology(read_obj(Path('data/snapshots/ce26e0392ab0/CHTM_SIDE_WALK_2nd_floor.obj')), flat_materials=frozenset({0}))`,
print `topology_stats` and runtime. Known baseline: regions 986, real 1097, removable 2524, open 326,
nonmanifold 1738, t_junction 316, edges_with_t_vertices 164.

## Items, in this order

### F1 `fix(engine): meshbuf header accepts Path texture values`
`engine/transport/meshbuf.py`: `textures` values may be `str | Path | None`. `SnapshotResult.textures` is
`dict[str, Path]` and `json.dumps` raises `TypeError: Object of type WindowsPath is not JSON serializable`.
Serialize as a forward-slash string (`Path(v).as_posix()`), `None` stays `null`. Test with a `Path` value and
with a backslash Windows-style string.

### F2 `fix(engine): flat-material adapter from flatness-by-name to indices`
`engine/pipeline.py`: add constant `FLAT_TEXTURE_STD = 8.0` and
`flat_material_indices(mesh, flatness: dict[str, float], threshold: float = FLAT_TEXTURE_STD) -> frozenset[int]`
returning indices into `mesh.materials` whose flatness is below threshold. A material with NO entry in
`flatness` (no texture, plain colour) counts as flat. `analyse_topology` raises `TypeError` with a clear
message if any element of `flat_materials` is not an `int` (names used to fail silently, `in` always False).
Tests: names -> indices, untextured material is flat, patterned one is not, TypeError on a str.

### F3+F4 `fix(engine): T-junctions from zero-area hints and on every edge`
Spec: "Zero-area triangles are the stitching across T-junctions: use them as hints, drop them after adjacency
is built." Today `find_t_vertices` searches only `counts == 1` edges with candidates limited to open-edge
endpoints, and zero-area faces are discarded before adjacency.

- `find_t_vertices(positions_w, table, tol, face_w=None, degenerate=None)`. Geometric search runs on EVERY
  edge in the table (count >= 1). Candidates are all welded vertices referenced by faces included in the
  table. Keep it vectorized per edge.
- Hints: for each degenerate face in `face_w[degenerate]` with three DISTINCT vertex ids, the vertex whose
  parameter lies strictly between the other two on their common line is a T-vertex of the edge formed by the
  other two, if that edge exists in the table. Merge hints with geometric hits, de-duplicate, keep order from
  `edges[e][0]` to `edges[e][1]`.
- `analyse_topology` passes `face_w` and `~ok`.
- `engine/topo/edges.py` `classify_edges`: for an edge `e` with T-vertices, gather faces of `e` and of all
  its sub-edges. If every sub-edge exists and all those faces share one region (not -1): `e` becomes
  `EDGE_REMOVABLE`, and each sub-edge with `counts == 1` becomes `EDGE_REMOVABLE`. Otherwise: only if
  `counts[e] == 1` does `e` become `EDGE_TJUNCTION` (and its `counts == 1` sub-edges too). An edge with
  `counts >= 2` keeps the class the count rules gave it. `build_regions` keeps joining faces across the chain
  exactly as now.
- Tests: (a) existing `t_junction_strip` tests pass unmodified. (b) new fixture in
  `engine/tests/fixtures/build.py`, `t_junction_shared_strip()`: same as `t_junction_strip()` plus one
  vertical wall triangle that also uses the long edge (0,10,0)-(20,10,0), vertices
  (0,10,0),(20,10,0),(10,10,-10), so that edge has `counts == 2`. Assert its T-vertex (10,10,0) is found via
  the hint, and in a second test with the zero-area face removed from the fixture, via geometry alone.
  (c) a degenerate face with a repeated vertex id yields no hint and no crash.
- After this item re-run the real-model script. Paste BEFORE and AFTER `topology_stats` and runtimes in the
  report. If runtime exceeds 5 s say so plainly.

### F6 `fix(engine): per-call incoming dir for concurrent snapshots`
`engine/io/snapshot.py`: replace the per-OBJ `.incoming-<stem>` temp dir with
`tempfile.mkdtemp(prefix=".incoming-", dir=dst_root)`. If `final` already exists when about to rename
(another call won the race), discard tmp and load the existing `final`. The existing "no `.incoming-*` left
behind" test must still pass. Add a test: two sequential calls into the same `dst_root` both succeed, and a
stale pre-existing `.incoming-walk` directory from a crashed run is neither deleted by name collision nor
breaks the call.

### F7b `fix(engine): OS errors during verified copy mean the source is unstable`
`_copy_verified` and `read_manifest_stable`: wrap `OSError` (includes `PermissionError` from a Windows file
lock and `FileNotFoundError` when the file vanishes mid-copy) into `SourceUnstable` with the original
message, `raise ... from exc`. Test by monkeypatching `shutil.copyfile` to raise `PermissionError`.

### F8 `fix(engine): refuse texture basename collisions instead of overwriting`
Textures are flattened to their basename under `tex/`. If two DIFFERENT source rel-paths used by the object
share a basename, raise `ValueError` naming both paths, before copying anything. Put the check where the
wanted texture set is known (`_copy_assets`). Test with `a/stone.png` and `b/stone.png`.

### M1 `fix(engine): reject exponent-form coordinates`
`engine/io/obj_reader.py`: a `v` token containing `e` or `E` (e.g. `1e-05`) breaks printed-decimal and
significant-digit detection and therefore the exact weld. Raise `ObjFormatError` with the line number. Test.

### T8 `test(engine): meshbuf sentinels for degenerate faces and missing material`
Meshbuf test using `t_junction_strip()` with one face's `face_material` set to -1: assert `tri_region == -1`
exactly for the zero-area face, `tri_material == 65535` for the unassigned face, all normals finite and unit
length (degenerate face gets (0,0,1)), `tri_face_id == arange`.

## Finish

Whole suite `.venv/Scripts/python.exe -m pytest -q`, state the REAL count. Real-model script once more.

Write the full report (per item: test added, RED output, GREEN output; real-model BEFORE/AFTER stats and
runtimes; concerns) to `final-fix-report.md` next to this brief. Append to it after EACH item, so an
interruption loses nothing.

Return ONLY: status, commit hashes in order, full-suite summary line, BEFORE and AFTER real-model
`topology_stats` with runtimes, concerns.
