# Task K1b brief: edits carry the UVs and normals of new faces

**Why** (K3 measured this on CHTM 5th, ruling K3-R2):
- `apply_edits` gives every added or cut face `face_vt = -1` and `face_vn = -1` (ruling K1-R4).
- The Validator's check 1 (every texture still there, same look and UV) therefore fails every merge site on UV
  alone.
- Any engine that adds faces (E5 cut, E7 merge, E8 solidify, E8 flat fill) needs its new faces to keep a correct
  UV.

## Design (binding)

1. **`Edit` gains optional per-corner attributes for its `new_faces`:**
   - `new_face_uv: ndarray | None`, shape (k, 3, 2), the UV at each corner;
   - `new_face_normal: ndarray | None`, shape (k, 3, 3).
   - Both are copied on construction, read-only and finite, with shape checked against `new_faces`.
   - `None` keeps today's behaviour: -1 indices.
2. **`apply_edits`** appends these UVs and normals to `mesh.uvs` and `mesh.normals`, sets the new faces'
   `face_vt` and `face_vn` to them, and leaves every existing face's indices untouched.
   - De-duplicating identical UV or normal rows is allowed if it stays deterministic.
   - It must not change any existing face.
3. **The K2 legacy observer** (`engine/repair/engines/legacy.py::observe`) fills `new_face_uv` and
   `new_face_normal` from the stage's OUTPUT mesh for every add and cut it logs (E7 merge, E8 solidify).
   - `apply_edits(stage_input, stage_edits)` then reproduces the stage output's per-corner UV and normal VALUES,
     not only its face keys.
   - A face whose output has `face_vt = -1` stays `None` for that face.
   - Use NaN rows only if the shape requires a placeholder, and document it.
4. **Flips:** they already reverse `face_vt`. Leave `face_vn` as -1 (ruling K1-R3).
5. **The edit log** gains nothing; `edit_log.jsonl` stays as K2 left it.

## Exit (real output)

- **Tests:**
  - round-trip of UV and normal values for add and cut on fixtures;
  - None keeps -1;
  - wrong shapes raise;
  - non-finite raises;
  - the arrays are read-only.
- **On sidewalk A, sidewalk B and CHTM 5th:** for every stage, `apply_edits(stage_input, edits)` gives the same
  per-corner UV values as the stage output, within 1e-9, keyed by face key.
- **Byte-identity:** `engine.cli fix` with and without `--kernel` is still byte-identical to the base for
  `report.json` and `.fixed.obj` on the three units, because the observer only reads.
- **Suite:** the whole engine suite passes. Existing tests are unedited, except a K1 or K2 test that asserted
  -1 for a face that now carries a UV; name each such edit and why.

## Rules

- AGENTS.md §3-§7. Nothing in `engine/guard/**` or `engine/validate/**`; no `FixProfile` threshold change.
- Test first; commit after each item.
