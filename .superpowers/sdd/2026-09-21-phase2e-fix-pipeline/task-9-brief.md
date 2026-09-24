### Task 9: Polygon export + honest viewer data

The user wants the AFTER object to show only its real shape edges. OBJ for Unity must contain triangles, but each
merged flat region without holes can also be written as ONE polygon face.

**Files:** Modify `engine\fixes\merge.py` (keep each region's kept outer ring of vertex ids in `MergeResult.rings`),
`engine\io\obj_writer.py` (`write_obj_polygons(mesh, rings, path)`), `engine\cli.py`.

- `fix` additionally writes `<name>.fixed.ngon.obj`: one `f` line per hole-free merged region (any vertex count),
  triangles for regions with holes and for copied-through faces. The triangulated `<name>.fixed.obj` stays the Unity file.
- `preview-data` marks AFTER edges as: `outline` (real), `tri` (triangulation diagonals that exist only because OBJ
  needs triangles), and provides counts for both so the page can state "0 gridlines, N outline edges, M unavoidable diagonals".
- [ ] Tests: `grid_slab` -> ngon file has exactly 1 face with 4 vertices; `slab_with_hole` -> stays triangles (8);
  ngon file re-read fails loudly with `ObjFormatError` in `read_obj` (triangles only by design), which is asserted, and a
  tiny polygon-aware counter in the test confirms the face count.
- [ ] Commit `feat(engine): polygon export and viewer edge classes for the fixed mesh`.

---

## Phase 2E done when

- Full suite passes, real count pasted.
- Both real files produce a fixed OBJ with `passed: true` (hidden removal + merge), numbers within the table above.
- Fixed OBJ re-imports through `read_obj` with 0 zero-area faces and material count unchanged.
- Preview page shows the real fixed mesh.
- Any expectation that was not met is reported as not met, with the measured number. No expectation is edited to fit.
