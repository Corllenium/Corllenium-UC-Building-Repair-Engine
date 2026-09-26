# Task 6 Report: Fix Run Writes AFTER Version's Errors File

## Changes Made

### 1. `api/routers/versions.py` - Lines 15, 17
Added two new imports:
- Line 15: `from api.routers.errors import write_errors`
- Line 17: `from engine.detectors.errors import find_errors`

### 2. `api/routers/versions.py` - Lines 562-566 (before the success `return fix_run`)
Inserted the error file writing block in the success path:
```python
        # the 3D error filter's AFTER file; never allowed to change the run's own outcome
        try:
            write_errors(settings, fix_run.fixed_version_id, find_errors(result.mesh, profile))
        except Exception:
            logger.exception("errors file for fixed version %s", fix_run.fixed_version_id)
```

### 3. `api/tests/test_errors.py` - Lines 31-37
Appended new test:
```python
def test_a_fix_run_writes_its_after_errors_file(client, imported_cube):
    vid = imported_cube["versions"][0]["id"]
    run = client.post(f"/api/versions/{vid}/fix", json={"profile": {"n_dirs": 32}}).json()
    assert run["status"] == "completed"
    r = client.get(f"/api/versions/{run['fixed_version_id']}/errors")
    assert r.status_code == 200
    assert r.json()["n_faces"] > 0
```

## Test Results

### Before Implementation (Red)
```
FAILED api/tests/test_errors.py::test_a_fix_run_writes_its_after_errors_file
E       assert 404 == 200
```

### After Implementation (Green)
```
1 passed, 4 warnings in 40.32s
```

### Full Test Suites Passing
- `api/tests/test_errors.py`: 4 passed (3 existing + 1 new)
- `api/tests/test_versions.py`: 6 passed (all existing, no regressions)

## Commit

**SHA:** e66122446fa83724892ca1318e455ba6938f0547

**Message:**
```
feat(api): a fix run leaves its AFTER version's errors file behind

So the AFTER panel's filter is ready without a second button; a failure there is logged and never changes the run's status.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

## Concerns

None. The implementation:
- Follows the brief exactly (imports, code block, placement, test)
- Uses try/except to never change the fix run's outcome on error
- Properly logs exceptions
- All existing tests continue to pass
- New test validates the feature works end-to-end
