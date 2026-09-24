### Task 4: Remove faces with provenance

**Files:** Create `engine\fixes\__init__.py`, `engine\fixes\remove.py`, `engine\tests\test_remove.py`

**Interfaces — Produces:** `remove_faces(mesh: MeshData, drop: np.ndarray[bool]) -> tuple[MeshData, np.ndarray[int64]]`
returning the new mesh and `source_face` (new face index -> original face index). Positions, UVs, normals arrays are
kept unchanged (no re-indexing, no compaction) so vertex ids stay comparable across versions. `face_line` carries over.

- [ ] Tests: dropping nothing is identity; dropping faces keeps order of survivors; `source_face` maps back exactly;
  round trip through `write_obj` / `read_obj` preserves face count. Implement, pass, commit
  `feat(engine): face removal with provenance`.

