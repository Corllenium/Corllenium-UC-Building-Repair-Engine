### Task 7: CLI, fixed OBJ, report, preview data

**Files:** Create `engine\cli.py`, `engine\tests\test_cli.py`. Modify `spike\12_export_preview.py` **no** - leave the
spike alone; add `preview-data` to the CLI instead.

**Interfaces — Produces:**
`python -m engine.cli fix <snapshot_dir> [--accept-slit] [--out data/output]` writes
`<out>\<name>\<name>.fixed.obj`, copies `materials.mtl` + `tex\`, `report.json` (every `FixResult` number, both
guard reports per view, profile, input sha256), `guard_<view>.png` triptychs for 6 views, exit code 0 when
`passed`, 2 when not. `python -m engine.cli preview-data <snapshot_dir> --out preview/data` writes the JSON the
existing `preview\index.html` reads, with AFTER = the real fixed mesh and the real guard numbers in `stats`.

- [ ] Tests: CLI on a fixture snapshot dir produces the files, `report.json` parses, exit code 0; a fixture that
  must fail the guard (patched profile forcing removal of an outer face) exits 2.
- [ ] **Real-data acceptance, both files**, paste `report.json` summaries:

| | expect |
|---|---|
| hidden removed after feedback | A **1,819**, B **2,381** |
| guard after removal | 0 holes, 0 material_changed, 0 moved_other, all 26 views |
| final guard after merge | **passed**, with `moved_same_flat` reported. The spike's rough merge failed this (0.42 % px), the real kernel must not |
| tris | A **<= 2,073** from 4,692, B **<= 2,499** from 7,227 |
| invariants | material count same, bbox same, area not grown |
| `--accept-slit` run | A removes 164 more, B 193 more. B's 260 px `material_changed` must make that run **fail** unless guard feedback restores the responsible faces, in which case report how many were restored |

- [ ] Open `http://localhost:5180` after `preview-data`, screenshot BEFORE / AFTER, confirm no console errors.
- [ ] Commit `feat(engine): fix CLI, report, guard images, preview data`.

---

## Phase 2E done when

- Full suite passes, real count pasted.
- Both real files produce a fixed OBJ with `passed: true` (hidden removal + merge), numbers within the table above.
- Fixed OBJ re-imports through `read_obj` with 0 zero-area faces and material count unchanged.
- Preview page shows the real fixed mesh.
- Any expectation that was not met is reported as not met, with the measured number. No expectation is edited to fit.
