### Task 3: the flicker search is fast enough for a building

**Measured, 2026-09-26:** `double_layers` on a 10,057-face slice of the raw `chtm_5ft_floor` took
**342 s**. Of that, **323 s (94%)** went to counting pixels:
- `EmbreeCaster.all_hits` → `_coincident_with` (`engine/rays/caster.py:133`) tests every hit against
  every face (numpy `all` 145 s, `nonzero` 27 s).
- The pair search itself (shapely) took about 15 s.

So the fix is the pixel count, not the pair search. A pixel counts when its first hit is face `f` AND
its ray meets one of `f`'s own partners within `depth_tol`. That can be tested directly against the
partners (a Möller–Trumbore ray–triangle test, vectorized over (pixel, partner) rows), instead of
asking the caster for every surface along every ray.

**Files:**
- Modify: `engine/fixes/overlap.py` (`double_layers`, the pixel stage from `# the pixels:` to the
  `for view in views:` loop's end)
- Test: `engine/tests/test_overlap.py` (append)

**Interfaces:**
- `double_layers` keeps its exact signature and output keys; only its speed changes.
- The pixel count must equal the old method's on the fixtures.

- [ ] **Step 1: Write the failing test** (append to `engine/tests/test_overlap.py`): the new count against a reference copy of the old count.

```python
def _reference_px(positions_c, faces, result, depth_tol, views, size):
    """The visible-pixel total exactly as double_layers counted it before 2026-09-26: every surface
    along the ray, from the caster's all_hits."""
    from engine.guard.views import ortho_first_hit
    from engine.rays.caster import EmbreeCaster, ReusableCaster
    partners = {}
    for i, j, _s, _o in result["pair_list"]:
        partners.setdefault(i, set()).add(j)
        partners.setdefault(j, set()).add(i)
    watched = np.array(sorted(partners), dtype=np.int64)
    caster = EmbreeCaster(positions_c, faces)
    reusable = ReusableCaster(EmbreeCaster)
    ids_all = np.arange(len(faces), dtype=np.int64)
    total = 0
    for view in views:
        buf = ortho_first_hit(positions_c, faces, ids_all, view, positions_c, size, reusable)
        mask = (buf.tri >= 0) & np.isin(buf.tri, watched)
        if not mask.any():
            continue
        rows, cols = np.nonzero(mask)
        origins = buf.xs[cols][:, None] * buf.right + buf.ys[rows][:, None] * buf.up + buf.standoff
        ray, hit, t = caster.all_hits(origins, np.tile(np.asarray(buf.direction, float), (len(origins), 1)))
        first_f, first_t = buf.tri[rows, cols], buf.depth[rows, cols]
        near = np.abs(t - first_t[ray]) <= depth_tol
        met = {}
        for q, f in zip(ray[near].tolist(), hit[near].tolist()):
            met.setdefault(q, set()).add(f)
        total += sum(1 for q in range(len(rows)) if partners[int(first_f[q])] & met.get(q, set()))
    return total


@pytest.mark.parametrize("build", ["back_to_back_pair", "split_double_layer", "two_sided_wall"])
def test_double_layers_counts_the_same_pixels_as_every_surface_along_the_ray(build):
    from engine.fixes.overlap import double_layers
    from engine.guard.views import VIEWS_26
    from engine.tests.fixtures import build as fixtures
    m = getattr(fixtures, build)()
    pos = np.asarray(m.positions, float)
    centre = (pos.min(axis=0) + pos.max(axis=0)) / 2
    faces = np.asarray(m.face_v)
    d = double_layers(pos - centre, faces, 0.01, VIEWS_26, (300, 200), centre=centre)
    assert d["px"] > 0
    assert d["px"] == _reference_px(pos - centre, faces, d, 0.01, VIEWS_26, (300, 200))


def test_double_layers_no_longer_asks_the_caster_for_every_surface(monkeypatch):
    from engine.fixes import overlap
    from engine.rays.caster import EmbreeCaster
    from engine.tests.fixtures.build import two_sided_wall

    def forbidden(*a, **k):
        raise AssertionError("all_hits called")

    monkeypatch.setattr(EmbreeCaster, "all_hits", forbidden)
    m = two_sided_wall()
    pos = np.asarray(m.positions, float)
    overlap.double_layers(pos - pos.mean(axis=0), np.asarray(m.face_v), 0.01)
```

- [ ] **Step 2: Run them and see the right failure**

Run: `.venv/Scripts/python.exe -m pytest engine/tests/test_overlap.py -k "same_pixels or no_longer_asks" -q -p no:cacheprovider`
Expected:
- the three `same_pixels` tests PASS (the reference is the current method);
- `no_longer_asks` FAILS with `AssertionError: all_hits called`.

- [ ] **Step 3: Implement.** In `engine/fixes/overlap.py`, `double_layers`, replace everything from
  `ids_all = np.arange(len(faces), dtype=np.int64)` down to the end of the `for view in views:` loop
  (the block ending `px_plane[plane_index[f]] += 1`) with:

```python
    ids_all = np.arange(len(faces), dtype=np.int64)
    reusable = ReusableCaster(caster_factory)
    px_plane = np.zeros(len(planes), dtype=np.int64)
    # partners as CSR arrays over face ids, for a vectorized (pixel, partner) expansion
    ptr = np.zeros(len(faces) + 1, dtype=np.int64)
    for f, ps in partners.items():
        ptr[f + 1] = len(ps)
    ptr = np.cumsum(ptr)
    idx = np.zeros(int(ptr[-1]), dtype=np.int64)
    for f, ps in partners.items():
        idx[ptr[f]:ptr[f + 1]] = sorted(ps)
    plane_of_face = np.full(len(faces), -1, dtype=np.int64)
    for f, k in plane_index.items():
        plane_of_face[f] = k
    watched = np.array(sorted(partners), dtype=np.int64)
    for view in views:
        buf = ortho_first_hit(positions_c, faces, ids_all, view, positions_c, size, reusable)
        mask = (buf.tri >= 0) & np.isin(buf.tri, watched)
        if not mask.any():
            continue
        rows, cols = np.nonzero(mask)
        first_f = buf.tri[rows, cols].astype(np.int64)
        first_t = buf.depth[rows, cols]
        origins = buf.xs[cols][:, None] * buf.right + buf.ys[rows][:, None] * buf.up + buf.standoff
        direction = np.asarray(buf.direction, dtype=np.float64)
        # every (pixel, partner of its first face) row
        counts = ptr[first_f + 1] - ptr[first_f]
        pix = np.repeat(np.arange(len(first_f)), counts)
        starts = np.repeat(ptr[first_f] - np.concatenate(([0], np.cumsum(counts)[:-1])), counts)
        partner = idx[starts + np.arange(len(pix))]
        # Moller-Trumbore against that partner: does the ray meet it within depth_tol of the first hit?
        v0 = tri[partner, 0]
        e1 = tri[partner, 1] - v0
        e2 = tri[partner, 2] - v0
        pvec = np.cross(np.broadcast_to(direction, e2.shape), e2)
        det = np.einsum("ij,ij->i", e1, pvec)
        usable = np.abs(det) > 1e-12
        inv = np.where(usable, 1.0 / np.where(usable, det, 1.0), 0.0)
        s = origins[pix] - v0
        u = np.einsum("ij,ij->i", s, pvec) * inv
        qvec = np.cross(s, e1)
        v = (qvec @ direction) * inv
        t = np.einsum("ij,ij->i", e2, qvec) * inv
        eps = 1e-6
        met = usable & (u >= -eps) & (v >= -eps) & (u + v <= 1.0 + eps) & (np.abs(t - first_t[pix]) <= depth_tol)
        counted = np.unique(pix[met])
        np.add.at(px_plane, plane_of_face[first_f[counted]], 1)
    px_plane = px_plane.tolist()
```

Notes for this step:
- `tri` is already `positions_c[faces]` in `double_layers` (its first lines), so it is in the same
  frame as `buf`.
- The old lines that built `caster = caster_factory(positions_c, faces)` and called
  `caster.all_hits(...)` are gone.
- `px_plane` is still a list afterwards, for the output code below.

- [ ] **Step 4: Run the overlap tests and see them all pass**

Run: `.venv/Scripts/python.exe -m pytest engine/tests/test_overlap.py -q -p no:cacheprovider`
Expected: all pass, including the three `same_pixels` tests: the new count equals the reference
exactly.

- [ ] **Step 5: Measure on the same slice**

Run: `PYTHONPATH=. .venv/Scripts/python.exe <scratchpad>/profile_double_layers.py data/snapshots/c0c877002500-b7c2dc01`
Expected: `double_layers on the slice` well under 342 s (target under 20 s), with the same `6376 pairs`.
The px total is within a few pixels of `33934`: only faces touching exactly along a pixel's ray can
differ. Put both lines into the commit body.

- [ ] **Step 6: Whole engine suite**

Run: `.venv/Scripts/python.exe -m pytest engine/tests -q -p no:cacheprovider`
Expected: all pass. `double_layers` also runs in every fix, via `report.json`'s `double_layers`.

- [ ] **Step 7: Commit**

```bash
git add engine/fixes/overlap.py engine/tests/test_overlap.py
git commit -m "perf(engine): double_layers tests each pixel against its face's partners, not every surface" -m "<the two measured lines from Step 5: before 342.4 s on the 10,057-face slice, after N s; pairs 6376 both; px before/after>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

