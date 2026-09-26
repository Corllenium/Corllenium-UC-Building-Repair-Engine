# Task 2 Report: `find_errors(mesh, profile)`

## Summary

Implemented `find_errors`, the 3D error filter's detector pass that identifies all errors in a mesh without modifying it. The function analyzes 7 error kinds (flicker_diff, flicker_same, reversed, hidden, loose, open_edges, cracks) using existing pipeline detectors, and returns structured error data with face IDs, locations, and worst spots per kind.

## Implementation Details

### Files Changed
- **`engine/detectors/errors.py`** (new, 123 lines): Complete implementation with helpers `_spot()` and `_face_group_spots()`.
- **`engine/tests/test_errors.py`** (new, 70 lines): 7 test cases covering all error kinds.
- **`engine/tests/fixtures/build.py`** (modified): Appended `two_sided_wall()` fixture at END.

### TDD Evidence

**RED Phase:** Tests fail with `ModuleNotFoundError: No module named 'engine.detectors.errors'`
```bash
cd 'D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/error-filter' && PYTHONPATH="$PWD" '/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' -m pytest engine/tests/test_errors.py -q -p no:cacheprovider
```
Output: 1 error during collection ✗

**GREEN Phase:** All 7 tests pass
```bash
cd 'D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/error-filter' && PYTHONPATH="$PWD" '/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' -m pytest engine/tests/test_errors.py -q -p no:cacheprovider
```
Output: 7 passed in 33.01s ✓

### Full Engine Suite
```bash
cd 'D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/error-filter' && PYTHONPATH="$PWD" '/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' -m pytest engine/tests -q -p no:cacheprovider
```
Result: **619 passed, 1 xfailed in 436.82s** (no new failures) ✓

## Interface

The function signature and output keys match the brief exactly:
- Consumes: Task 1's `double_layers(...)["pair_list"]` (list of `[i, j, shared_area, opposite]`)
- Produces: Dictionary with 8 keys: `version`, `n_faces`, `counts`, `faces`, `open_edges`, `cracks`, `flicker_pairs`, `spots`
- Exports: `KINDS = ("flicker_diff", "flicker_same", "reversed", "hidden", "loose", "open_edges", "cracks")`

All 7 error kinds are detected using existing pipeline components:
- **flicker_diff/same**: Via `double_layers()` output, split by material equality
- **reversed**: Via `classify_orientation()` from `engine.fixes.orient`
- **hidden**: Via `classify_exposure()` from `engine.vis.exposure`
- **loose**: Zero-area faces (ok=False from topology analysis)
- **open_edges**: Edges with count==1 from topology edge table
- **cracks**: T-junction vertices from topology analysis

## Test Coverage

1. **Clean cube** (0 errors): Baseline
2. **Two-sided wall** (flicker_diff): Material-different layers detected; spot location and visibility pixels verified
3. **Box with partition** (hidden faces): Interior faces correctly classified
4. **Flipped cube face** (reversed): Orientation flip detected
5. **Open square** (open edges): All 4 edges identified with correct lengths
6. **T-junction strip** (loose + cracks): Zero-area stitch and junction point both found
7. **JSON serialization**: Output is plain JSON-serializable

## Self-Review

- ✓ All 7 tests pass without modification to assertions
- ✓ No existing tests broken (619 passed, same xfail)
- ✓ Implementation uses exact code from brief, no deviations
- ✓ Fixture appended at END of build.py as required
- ✓ PYTHONPATH correctly set to worktree root
- ✓ Commit message follows format with Co-Authored-By
- ✓ Output structure matches brief spec (counts for all 7 kinds, face lists, coordinates in inches, rounded to 2-3 decimals)

## Concerns

None. All tests pass, full suite clean, implementation faithful to brief specification.

## Commit

- **SHA**: b24da59
- **Subject**: feat(engine): find_errors says what is wrong with each face, without changing the model
- **Files**: engine/detectors/errors.py (new), engine/tests/test_errors.py (new), engine/tests/fixtures/build.py (modified)
