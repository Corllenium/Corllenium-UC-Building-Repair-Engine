### Task 14: the facade layer (added 2026-09-26, owner: highlight "the face-out walls that represent the facade of the model, not the hidden faces")

`find_errors` already classifies every face's exposure: 128 ray directions from 4 points per face,
the pipeline's own `classify_exposure`. Faces a ray from outside reaches (`EXP_OUTSIDE`) are the
facade. The facade is not an error, so it lives beside the errors: `"layers"` and `"layer_counts"`.
A clean model still has `counts` all zero.

**Files:**
- Modify: `engine/detectors/errors.py`
- Test: `engine/tests/test_errors.py` (append)

**Interfaces:**
- Produces three new keys in `find_errors`' output:
  - `"layers": {"facade": [face ids, ascending]}`
  - `"layer_counts": {"facade": int}`
  - `"spots"["facade"]`: the largest facade regions, same shape as the other spots
- `counts`, `faces` and `KINDS` are unchanged.

- [ ] **Step 1: Write the failing tests** (append to `engine/tests/test_errors.py`)

```python
def test_the_facade_layer_is_every_face_seen_from_outside():
    e = find_errors(box_with_partition(), PROFILE)
    assert e["layers"]["facade"] == list(range(12))   # the 12 outer faces, not the sealed partition
    assert e["layer_counts"]["facade"] == 12
    assert e["counts"]["hidden"] == 2
    assert e["spots"]["facade"][0]["value"] > 0


def test_a_clean_cube_is_all_facade_and_still_has_no_errors():
    e = find_errors(cube(), PROFILE)
    assert e["layers"]["facade"] == list(range(12))
    assert e["counts"] == {k: 0 for k in KINDS}
```

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/Scripts/python.exe -m pytest engine/tests/test_errors.py -q -p no:cacheprovider`
Expected: the two new tests FAIL with `KeyError: 'layers'`.

- [ ] **Step 3: Implement.** In `engine/detectors/errors.py`:
  - import `EXP_OUTSIDE` next to `EXP_HIDDEN`;
  - compute the exposure class once and derive both lists from it:

```python
    exposure_class = classify_exposure(front + back, ok, profile.slit_threshold)
    hidden = np.nonzero((exposure_class == EXP_HIDDEN) & ok)[0]
    facade = np.nonzero((exposure_class == EXP_OUTSIDE) & ok)[0]
```

  - after the loop that fills `spots` for `("reversed", "hidden", "loose")`, add:

```python
    spots["facade"] = _face_group_spots("facade", pos, faces, facade, topo.face_region, area)
```

  - in the returned dict, add:

```python
            "layers": {"facade": [int(f) for f in facade]},
            "layer_counts": {"facade": int(len(facade))},
```

- [ ] **Step 4: Run and see them pass**, then the CLI and errors tests

Run: `.venv/Scripts/python.exe -m pytest engine/tests/test_errors.py engine/tests/test_cli.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add engine/detectors/errors.py engine/tests/test_errors.py
git commit -m "feat(engine): find_errors also lists the facade -- every face seen from outside" -m "The owner wants the outward-facing walls highlighted, as opposed to the hidden inside faces; the facade sits beside the errors, so a clean model still reports none." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

**Web side (in Task 8 and Task 10, below):** a `facade` kind in teal (`0x0d9488`):
- off by default, labelled "Facade (seen from outside)";
- drawn with the lowest priority, so any error on a facade face keeps the error's colour;
- read from `file.layers.facade`, and counted from `file.layer_counts.facade`.

## Order

Tasks run in this order: **1, 2, 3, 4, 5, 6, 12, 14, 8, 7, 9, 10, 13, 11**.
- Task 8 comes before Task 7, because Task 7 imports Task 8's `ErrorsFile` type.
- Task 3 comes before Task 4 Step 5, which measures the whole building.

The profiling script used in Task 3 Step 5 is
`C:/Users/Future26/AppData/Local/Temp/claude/D--PROJECTS-UC-MODEL-FIXER/5472478e-978d-426b-bab2-e7cf21699a70/scratchpad/profile_double_layers.py`.
Copy it into `docs/superpowers/records/scripts/profile_double_layers.py` in Task 3 so the
measurement can be repeated.
