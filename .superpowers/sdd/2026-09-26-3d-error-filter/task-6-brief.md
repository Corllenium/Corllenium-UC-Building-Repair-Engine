### Task 6: a fix run writes its AFTER version's errors file

**Files:**
- Modify: `api/routers/versions.py` (in `run_fix_pipeline`, after the final commit block and before `return fix_run`)
- Test: `api/tests/test_errors.py` (append)

**Interfaces:**
- Consumes: `write_errors` from Task 5; `find_errors`; the fix run's `result.mesh`, its `profile` and `fix_run.fixed_version_id`.

- [ ] **Step 1: Write the failing test** (append)

```python
def test_a_fix_run_writes_its_after_errors_file(client, imported_cube):
    vid = imported_cube["versions"][0]["id"]
    run = client.post(f"/api/versions/{vid}/fix", json={"profile": {"n_dirs": 32}}).json()
    assert run["status"] == "completed"
    r = client.get(f"/api/versions/{run['fixed_version_id']}/errors")
    assert r.status_code == 200
    assert r.json()["n_faces"] > 0
```

- [ ] **Step 2: Run it and see it fail**

Run: `.venv/Scripts/python.exe -m pytest api/tests/test_errors.py::test_a_fix_run_writes_its_after_errors_file -q -p no:cacheprovider`
Expected: FAIL (`404 != 200`).

- [ ] **Step 3: Implement.** In `api/routers/versions.py`:
  - add near the other imports:

    ```python
    from api.routers.errors import write_errors
    from engine.detectors.errors import find_errors
    ```

  - and just before the success path's `return fix_run` in `run_fix_pipeline`. That is the
    `return fix_run` at about line 560, after the post-commit owner-copy block; NOT the one inside the
    `except` handler at about line 573:

    ```python
            # the 3D error filter's AFTER file; never allowed to change the run's own outcome
            try:
                write_errors(settings, fix_run.fixed_version_id, find_errors(result.mesh, profile))
            except Exception:
                logger.exception("errors file for fixed version %s failed", fix_run.fixed_version_id)
    ```

  The names already exist in the function:
  - `profile = FixProfile(...)`, about line 340;
  - `result = fix_object(mesh, flatness, profile)`, about line 358;
  - `settings`, and `logger` (module level, line 27).

- [ ] **Step 4: Run all API tests**

Run: `.venv/Scripts/python.exe -m pytest api/tests -q -p no:cacheprovider`
Expected: all pass (44 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add api/routers/versions.py api/tests/test_errors.py
git commit -m "feat(api): a fix run leaves its AFTER version's errors file behind" -m "So the AFTER panel's filter is ready without a second button; a failure there is logged and never changes the run's status." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

