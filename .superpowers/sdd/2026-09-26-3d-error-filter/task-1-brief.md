### Task 1: `double_layers` returns every pair with its partner

**Files:**
- Modify: `engine/fixes/overlap.py` (the `return` at the end of `double_layers`, about line 540)
- Test: `engine/tests/test_overlap.py` (append)

**Interfaces:**
- Produces: `double_layers(...)["pair_list"]`, a list of `[i, j, shared_area: float, opposite: bool]` with `i < j` indexing the `faces` passed in, sorted by `(-shared_area, i, j)`. Every other key is unchanged.

- [ ] **Step 1: Write the failing test** (append to `engine/tests/test_overlap.py`)

```python
def test_double_layers_lists_every_pair_with_its_partner():
    from engine.fixes.overlap import double_layers
    from engine.tests.fixtures.build import back_to_back_pair
    m = back_to_back_pair()
    pos = np.asarray(m.positions, float)
    centre = (pos.min(axis=0) + pos.max(axis=0)) / 2
    d = double_layers(pos - centre, np.asarray(m.face_v), depth_tol=0.01, centre=centre)
    assert d["count"] == 1
    [(i, j, shared, opposite)] = d["pair_list"]
    assert (i, j) == (0, 1)
    assert opposite is True
    assert shared == pytest.approx(d["area"])
```

- [ ] **Step 2: Run it and see it fail**

Run: `.venv/Scripts/python.exe -m pytest engine/tests/test_overlap.py::test_double_layers_lists_every_pair_with_its_partner -q -p no:cacheprovider`
Expected: FAIL with `KeyError: 'pair_list'`

- [ ] **Step 3: Implement.** In `double_layers`, replace the final `return {...}` with:

```python
    pair_list = sorted(([int(i), int(j), round(float(s), 3), bool(o)] for i, j, s, o in pairs),
                       key=lambda p: (-p[2], p[0], p[1]))
    return {"count": len(pairs), "area": round(sum(s for _i, _j, s, _o in pairs), 3),
            "px": int(sum(px_plane)), "planes": out_planes, "pair_list": pair_list}
```

Also add `"pair_list": []` to the `empty` dict near the top of the function:

```python
    empty = {"count": 0, "area": 0.0, "px": 0, "planes": [], "pair_list": []}
```

- [ ] **Step 4: Run the overlap tests and see them pass**

Run: `.venv/Scripts/python.exe -m pytest engine/tests/test_overlap.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add engine/fixes/overlap.py engine/tests/test_overlap.py
git commit -m "feat(engine): double_layers lists every flicker pair with its partner" -m "The 3D error filter's click card names the face a face fights with; the planes alone only gave counts." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

