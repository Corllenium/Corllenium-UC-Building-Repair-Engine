### Task 4: `python -m engine.cli errors`

**Files:**
- Modify: `engine/cli.py` (a new `cmd_errors` and subparser next to `preview-data`, about line 830)
- Test: `engine/tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `find_errors`, and `_load_snapshot(snapshot_dir) -> (obj_path, mesh, flatness, mtl_materials)` from `engine/cli.py`.
- Produces: `cmd_errors(snapshot_dir: Path, out_file: Path, profile: FixProfile | None = None) -> dict`, which writes the JSON and returns the dict.

- [ ] **Step 1: Write the failing test** (append to `engine/tests/test_cli.py`)

```python
def test_cmd_errors_writes_the_errors_file(tmp_path):
    import json
    from engine.cli import cmd_errors
    from engine.fixes.pipeline import FixProfile
    from engine.io.obj_writer import write_obj
    from engine.tests.fixtures.build import two_sided_wall
    snap = tmp_path / "snap"
    snap.mkdir()
    write_obj(two_sided_wall(), snap / "two_sided_wall.obj")
    out = tmp_path / "errors.json"
    result = cmd_errors(snap, out, FixProfile(n_dirs=32))
    assert json.loads(out.read_text(encoding="utf-8")) == result
    assert result["counts"]["flicker_diff"] == 4
```

- [ ] **Step 2: Run it and see it fail**

Run: `.venv/Scripts/python.exe -m pytest engine/tests/test_cli.py::test_cmd_errors_writes_the_errors_file -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'cmd_errors'`

- [ ] **Step 3: Implement.** In `engine/cli.py`, add after `cmd_preview_data`:

```python
def cmd_errors(snapshot_dir: Path, out_file: Path, profile: FixProfile | None = None) -> dict:
    """What is wrong with the snapshot's model, face by face (the 3D error filter's file);
    the model is not changed."""
    from engine.detectors.errors import find_errors
    _obj_path, mesh, _flatness, _mtl = _load_snapshot(Path(snapshot_dir))
    result = find_errors(mesh, profile or FixProfile())
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(result), encoding="utf-8")
    print(f"{mesh.name}: " + ", ".join(f"{k} {v}" for k, v in result["counts"].items()))
    return result
```

In `main()`, next to the `preview_p = sub.add_parser("preview-data", ...)` block, add:

```python
    errors_p = sub.add_parser("errors", help="find what is wrong with each face, without fixing it")
    errors_p.add_argument("snapshot", type=Path)
    errors_p.add_argument("--out", type=Path, required=True)
```

In the dispatch part of `main()`, next to the `preview-data` branch, add:

```python
    elif args.command == "errors":
        cmd_errors(args.snapshot, args.out)
```

If `json` is not imported at the top of `engine/cli.py`, add `import json` (check with `grep -n "^import json" engine/cli.py`).

- [ ] **Step 4: Run it and see it pass**, then the CLI tests

Run: `.venv/Scripts/python.exe -m pytest engine/tests/test_cli.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Measure on the real building**

Run: `.venv/Scripts/python.exe -m engine.cli errors data/snapshots/c0c877002500-b7c2dc01 --out data/errors/chtm5-raw.json`

Expected:
- a line starting `chtm_5ft_floor:` with `hidden` near 13,290 and `cracks` near 2,241;
- flicker faces from the scan's 13,947 pairs.

Write the wall time into the commit body.

- [ ] **Step 6: Commit**

```bash
git add engine/cli.py engine/tests/test_cli.py
git commit -m "feat(engine): engine.cli errors writes a model's errors file" -m "<the measured counts and wall time on chtm_5ft_floor from Step 5>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

