# SketchUp export — brief (task K: the file the user checks after every run)

Repo `D:\PROJECTS\UC MODEL FIXER`, branch `feat-dashboard`. Bash, POSIX syntax, repo path
`/d/PROJECTS/UC MODEL FIXER`. Python ALWAYS `.venv/Scripts/python.exe`. Do not touch the running servers.
Prerequisite: merge-quality (`MergeResult.rings` with `outer` / `inners`) has landed.

## Requirement (user, 2026-09-23)
After every fix run, the latest SketchUp file of each model appears in `D:\PROJECTS\UC MODEL FIXER\OBJ FIXED RESULT`
so it can be opened in SketchUp 2026 and checked: hidden inside faces gone, no triangle edges on flat
surfaces, only the outline edges of the model, none inside a slab.

## Reference
Prototype bindings (untracked, from another session, read them, do not import them):
`create_skp.py`, `build_clean_skp.py`, `execute_full_internal_clean.py` in the repo root. They load
`C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUpAPI.dll` with ctypes and use SUInitialize,
SUModelCreate, SUModelGetEntities, SUGeometryInputCreate/AddVertex, SULoopInputCreate/AddVertexIndex,
SUGeometryInputAddFace, SUEntitiesFill, SUEntitiesGetEdges, SUEdgeGetFaces, SUFaceGetNormal, SUEdgeSetSoft,
SUEdgeSetSmooth, SUModelSaveToFile, SUModelRelease, SUTerminate. SketchUp's internal unit is the inch, the same
as the OBJ: pass coordinates through unchanged (world coordinates, so the object drops back into the campus model).

## K1 `feat(engine): SketchUp writer with polygon faces, inner loops, soft creases, materials`
- `engine/io/skp_writer.py`: `write_skp(mesh, rings, edge_class, edge_table, materials, path, dll_path=None)`.
  DLL path from the argument, else env `FIXER_SKETCHUP_DLL`, else the default above; raise a clear
  `SketchUpUnavailable` error when the DLL is missing. Faces: one polygon per merged region using
  `rings[r]["outer"]` with `SULoopInputAddVertexIndex`, and each `rings[r]["inners"]` added as an inner loop
  (`SUGeometryInputFaceAddInnerLoop` or the equivalent in this DLL version; verify the symbol exists with
  ctypes before use and fall back to triangles for that region if it does not, reporting the fallback);
  every face not in a merged region is written as its triangle. Edges classed `EDGE_SOFT` are set soft + smooth
  after `SUEntitiesFill` by matching edge endpoints to the SketchUp edges returned by `SUEntitiesGetEdges`
  (compare endpoint coordinates within 1e-6 in; report unmatched). Materials: one SketchUp material per OBJ
  material with its texture file (`SUTextureCreateFromFile`, `SUMaterialSetTexture`) when the texture exists,
  else the Kd colour; assign per face front side with UVs (`SUMaterialInput`, uv coords from the mesh's `vt` of
  that face's vertices; for polygon faces use the UV of each ring vertex from any of the region's triangles).
  If material assignment through `SUGeometryInput` proves unreliable in this DLL, write geometry first and
  assign materials with `SUFaceSetFrontMaterial` afterwards; say which path was used.
- Round-trip reader for tests: `read_skp_summary(path) -> {faces, edges, soft_edges, materials, loops_with_inners}`
  via `SUModelCreateFromFile` + entity queries (read only).
- Tests (skip cleanly with a reason when the DLL is absent): `grid_slab` merged -> 1 face, 4 edges, 0 soft;
  `slab_with_hole` -> 1 face with 1 inner loop (or the reported fallback); `cube` -> 6 faces 12 edges; a two-facet
  fixture with a 3-degree crease -> 2 faces, the shared edge soft; materials count equals the mesh's.
- Determinism: writing twice gives files whose `read_skp_summary` is identical (the binary may embed timestamps;
  compare summaries, not bytes).

## K2 `feat(engine): fix CLI writes the latest .skp for the user`
- `python -m engine.cli fix ...` writes `<run dir>/<name>.fixed.skp` and copies it to
  `OBJ FIXED RESULT/<name>.fixed.skp` (overwrite = the latest), creating the folder if needed; `--skp-dir` overrides
  the folder. Add `OBJ FIXED RESULT/` to `.gitignore`. `report.json` gains `skp` (path, faces, soft_edges,
  fallback_regions). Test with a fixture snapshot; skip when the DLL is absent.
- Real data: run both files, open each `.skp` summary with `read_skp_summary` and paste it. Then, with the
  SketchUp DLL, also read `OBJ FIXED RESULT/CHTM_SIDE_WALK_2nd_floor.fixed.skp` and report faces / edges /
  soft edges / materials.

Write `skp-export-report.md` next to this brief with `## Public signatures`. Commit messages as given,
trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Edit only files under `engine/` plus `.gitignore`.

## Guard follow-ups folded into this dispatch (from the guard-round review), do these FIRST
G1 `fix(engine): crack tolerance has a ceiling and a cap` — `FixProfile.depth_tol_max = 0.5` (inches): the
guard's `depth_tol` is `min(1.5 * max(axis quanta), depth_tol_max)`. `crack_closed` pixels are counted against a
per-view cap `FixProfile.crack_closed_cap` (default 1e-3 of the view's model pixels) exactly like flicker
pixels are counted against `edge_flicker_cap`; above the cap the pixels fall back to their base class and fail.
`zfight_tie` stays uncapped (a tie is provably not a change) and reported. Tests: a coarse-quantum fixture
would give depth_tol above the ceiling -> clamped; a run with more closed-crack pixels than the cap fails.
G2 `fix(engine): the removal guard classifies ties and cracks like the merge guard` — `guard_feedback`
passes the ring and tie machinery through with cap 0.0 (flicker still fails there; ties and closed cracks are
tolerated) so the two guards agree about the same pixel; correct the docstring that claims they already do.
Test: a hidden-face removal whose only changed pixel is a z-fight tie restores nothing.
G3 `test(engine): tie recovery rejects a coplanar triangle that does not contain the hit point` — a
vertex-sharing coplanar triangle beside the hit must not enter the tie set.
