# Task 5 Report: API Errors Endpoint

## Status
✓ COMPLETE: 3-test suite passed. Full API suite passed (47 tests, 17:34).

## RED - Tests Fail (As Expected)

Initial test run before implementation showed 3 failures:
```
FAILED api/tests/test_errors.py::test_errors_are_not_computed_before_the_button
FAILED api/tests/test_errors.py::test_find_errors_saves_the_file_and_serves_it
FAILED api/tests/test_errors.py::test_an_unknown_version_is_refused
```

Expected: routes not yet implemented, module `api.routers.errors` doesn't exist.

## GREEN - Tests Pass

After implementing `api/routers/errors.py` and modifying `api/main.py`:

```
3 passed, 4 warnings in 1.54s
```

All three tests passed:
1. `test_errors_are_not_computed_before_the_button` - GET before POST returns 404 "not computed yet" ✓
2. `test_find_errors_saves_the_file_and_serves_it` - POST runs find_errors, saves file, GET returns it ✓
3. `test_an_unknown_version_is_refused` - POST to unknown version returns 404 "Version not found" ✓

## Implementation

### Files Created/Modified

**Created:**
- `api/routers/errors.py` (53 lines)
  - `errors_file(settings, version_id) -> Path`: computes `data/errors/version-<id>.json` path
  - `write_errors(settings, version_id, result)`: atomic write with .tmp temp file
  - `POST /{id}/errors`: runs `find_errors`, saves to file, returns dict
  - `GET /{id}/errors`: serves file or 404 "not computed yet"

- `api/tests/test_errors.py` (27 lines)
  - All three tests as specified in brief

**Modified:**
- `api/main.py`: added import + include_router for errors_router

### Commit

```
Commit: 4a998da
feat(api): Find errors per version, kept as data/errors/version-<id>.json

POST computes a version's errors file with find_errors; GET serves it or says not computed yet. No table, no migration.

Files: 3 changed, 82 insertions(+)
  api/main.py              |  2 ++
  api/routers/errors.py    | 53 ++++++++++++++++++++++++++++++++++++++++++++++++
  api/tests/test_errors.py | 27 ++++++++++++++++++++++++
```

## API Test Suite

Full suite run PASSED:
```bash
cd "/D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/error-filter"
PYTHONPATH="$PWD" "/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest api/tests/ -q -p no:cacheprovider
```

Result: **47 passed in 1054.38s (17:34)** ✓
- No failures
- No xfails  
- All existing tests still passing with new errors endpoint integrated

## Self-Review

✓ Implementation matches brief exactly  
✓ Tests verify all 3 required behaviors  
✓ Error messages match spec ("not computed yet", "Version not found")  
✓ `errors_file()` is importable for Task 6  
✓ Atomic write with .tmp prevents partial corrupts  
✓ Commit message includes Co-Authored-By attribution  

## Concerns

None. Implementation is straightforward and follows brief verbatim.

---
Task 5 complete. Ready for Task 6.
