# 3D Error Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the dashboard's 3D workspace, a "Find errors" button per version lights up each error kind of a building (flicker first), with a live filter, isolate, blink, click-for-details and a worst-spots fly-to list, on BEFORE and AFTER together.

**Architecture:**
- **Engine:** a read-only detector pass, `engine/detectors/errors.py::find_errors`, reuses the detectors the fix pipeline already trusts: exposure, orientation, double layers, T-junctions and degenerate faces. It returns one JSON-able dict per mesh.
- **API:** runs it per version and keeps the result in `data/errors/version-<id>.json`.
- **Web:** pure functions (`web/src/utils/errorLayers.ts`) turn that file plus the filter state into per-face colours, lines and points, which the existing `Viewport` draws.

**Tech Stack:** Python 3.12 (numpy, shapely, embree via the existing caster), FastAPI + SQLAlchemy (no migration), Vue 3 + three.js 0.170, vitest 5, pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-3d-error-filter-design.md`

## Global Constraints

- **Read-only:** `find_errors` never changes the mesh. Nothing is ever written in `D:\PROJECTS\UC ENVIRONMENT BUILDING\...`. There is no database migration and no table.
- **Face numbers:** `find_errors` numbers faces exactly as `mesh.face_v` does. `engine/transport/meshbuf.py` writes `tri_face_id = arange(n_faces)`, so these are the viewer's triangle numbers.
- **Coordinates:** the errors file holds world coordinates in inches. The viewer subtracts the meshbuf header's `origin_offset` (`web/src/three/meshbuf.ts::MeshbufHeader.origin_offset`).
- **Kinds, in priority order** (a face in several kinds is drawn in the first):

  | Kind | Label | Colour | Drawn as |
  |---|---|---|---|
  | `flicker_diff` | "Flicker: texture on texture" | `0xd8282f` red | faces |
  | `flicker_same` | "Flicker: same material" | `0xf08c00` orange | faces |
  | `reversed` | "Reversed / back faces" | `0x9650ff` purple | faces |
  | `hidden` | "Hidden inside faces" | `0x1f5bff` blue | faces |
  | `loose` | "Zero-area and stray bits" | `0xe0199b` magenta | faces |
  | `open_edges` | "Open edges" | `0x16a34a` green | lines |
  | `cracks` | "Cracks (T-junction points)" | `0x00b4d8` cyan | points |

- **Files:** stored at `settings.data_dir / "errors" / f"version-{id}.json"` (git-ignored `data/`).
- **Python and tests:**
  - Python is `.venv/Scripts/python.exe` from the repo root.
  - Engine tests: `.venv/Scripts/python.exe -m pytest engine/tests -q -p no:cacheprovider`.
  - API tests: `.venv/Scripts/python.exe -m pytest api/tests -q -p no:cacheprovider`. Each session gets its own `fixer_test_<pid>_*` database.
  - Web tests: `pnpm --dir web exec vitest run`.
- **Commits:** stage files by name; never `git add -A`. End every message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Fixtures:** new engine fixtures are appended at the END of `engine/tests/fixtures/build.py`.
- **Deploy:** only by HANDOFF.md section 8, from a commit, with the database backed up and old images tagged first.

## File structure

| File | Responsibility |
|---|---|
| `engine/fixes/overlap.py` (modify) | `double_layers` also returns every pair with its partner (`pair_list`), and gets faster on buildings |
| `engine/detectors/errors.py` (create) | `find_errors(mesh, profile) -> dict`: the per-face errors, lines, points, pairs and worst spots |
| `engine/cli.py` (modify) | `errors` subcommand: `python -m engine.cli errors <snapshot> --out <file>` |
| `engine/tests/fixtures/build.py` (append) | `two_sided_wall`: CHTM 5th floor's flicker in miniature |
| `engine/tests/test_errors.py` (create) | one test per kind, spots, JSON |
| `api/routers/errors.py` (create) | `POST` and `GET /api/versions/{id}/errors` |
| `api/main.py` (modify) | include the router |
| `api/routers/versions.py` (modify) | a fix run writes its AFTER version's errors file, isolated from the run's own outcome |
| `api/tests/test_errors.py` (create) | route tests |
| `web/src/utils/errorLayers.ts` (create) | types plus pure functions: kinds, overlay faces and colours, blink colours, lines, points, partners, spots |
| `web/src/utils/errorLayers.test.ts` (create) | vitest |
| `web/src/api/client.ts` (modify) | `fetchErrors`, `computeErrors` |
| `web/src/api/client.test.ts` (modify) | tests for both |
| `web/src/three/Viewport.ts` (modify) | draw the overlay faces, blink, lines, points, isolate, `flyTo` |
| `web/src/components/ErrorsPanel.vue` (create) | the legend, toggles, isolate, blink, Find errors buttons, worst spots |
| `web/src/views/WorkspaceView.vue` (modify) | wire the panel to both viewports and extend the click inspector |

---

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

### Task 2: `find_errors`, the read-only error finder

**Files:**
- Create: `engine/detectors/errors.py`
- Modify: `engine/tests/fixtures/build.py` (append `two_sided_wall` at the END)
- Test: `engine/tests/test_errors.py`

**Interfaces:**
- Consumes: Task 1's `double_layers(...)["pair_list"]`.
- Produces: `find_errors(mesh: MeshData, profile: FixProfile = FixProfile()) -> dict` with exactly these keys:
  - `"version": 1`, `"n_faces": int`;
  - `"counts": {kind: int}` for all 7 kinds;
  - `"faces": {"flicker_diff"|"flicker_same"|"reversed"|"hidden"|"loose": [face ids, ascending]}`;
  - `"open_edges": [[x1, y1, z1, x2, y2, z2], ...]` and `"cracks": [[x, y, z], ...]`, both in world inches;
  - `"flicker_pairs": [[i, j, shared, opposite], ...]`;
  - `"spots": {kind: [{"label": str, "centre": [x, y, z], "size": float, "value": float, "faces": [ids]}, ...]}`, at most 20 per kind, worst first.
- `KINDS = ("flicker_diff", "flicker_same", "reversed", "hidden", "loose", "open_edges", "cracks")`, exported.

- [ ] **Step 1: Append the fixture** at the END of `engine/tests/fixtures/build.py`:

```python
def two_sided_wall(size=40.0, uv_per_unit=0.05):
    """CHTM 5th floor's flicker in miniature: a zero-thickness wall at y = 0 written twice, once
    per side, in the SAME place -- faces 0-1 face -y in material 0 ("concrete"), faces 2-3 face
    +y in material 1 ("prismarine"), as the export writes a two-sided SketchUp face (OBJ lines
    13472 / 14606 on chtm_5ft_floor). Both sides are open to the air, so both layers are seen."""
    s = size
    P = [[0.0, 0.0, 0.0], [s, 0.0, 0.0], [s, 0.0, s], [0.0, 0.0, s]]
    fv = [[0, 1, 2], [0, 2, 3], [0, 2, 1], [0, 3, 2]]
    uvs = (np.asarray(P, float)[:, [0, 2]] * uv_per_unit).tolist()
    return _mesh("two_sided_wall", P, uvs, fv, fv, materials=("concrete", "prismarine"),
                 face_material=[0, 0, 1, 1])
```

- [ ] **Step 2: Write the failing tests** (`engine/tests/test_errors.py`)

```python
"""The 3D error filter's detector pass: one known answer per kind (spec 2026-09-26)."""
import json

import numpy as np
import pytest

from engine.detectors.errors import KINDS, find_errors
from engine.fixes.pipeline import FixProfile
from engine.tests.fixtures.build import (_mesh, box_with_partition, cube, t_junction_strip,
                                         two_sided_wall)

PROFILE = FixProfile(n_dirs=32)


def test_a_clean_closed_cube_has_no_errors():
    e = find_errors(cube(), PROFILE)
    assert e["n_faces"] == 12
    assert e["counts"] == {k: 0 for k in KINDS}


def test_a_two_sided_wall_is_red_flicker_with_its_partner():
    e = find_errors(two_sided_wall(), PROFILE)
    assert e["faces"]["flicker_diff"] == [0, 1, 2, 3]
    assert e["faces"]["flicker_same"] == []
    pairs = {(i, j) for i, j, _s, _o in e["flicker_pairs"]}
    assert pairs == {(0, 2), (1, 3)}
    assert all(o for *_rest, o in e["flicker_pairs"])
    spot = e["spots"]["flicker_diff"][0]
    assert spot["centre"] == pytest.approx([20.0, 0.0, 20.0], abs=1.0)
    assert spot["value"] > 0  # visible pixels


def test_a_face_sealed_inside_a_box_is_hidden():
    e = find_errors(box_with_partition(), PROFILE)
    assert e["faces"]["hidden"] == [12, 13]
    assert e["counts"]["hidden"] == 2


def test_a_face_turned_inside_out_is_reversed():
    m = cube()
    m.face_v[0] = m.face_v[0][[0, 2, 1]]
    m.face_vt[0] = m.face_vt[0][[0, 2, 1]]
    e = find_errors(m, PROFILE)
    assert e["faces"]["reversed"] == [0]


def test_a_flat_square_has_four_open_edges():
    P = [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]]
    m = _mesh("square", P, [[0, 0], [1, 0], [1, 1], [0, 1]], [[0, 1, 2], [0, 2, 3]], [[0, 1, 2], [0, 2, 3]])
    e = find_errors(m, PROFILE)
    assert e["counts"]["open_edges"] == 4
    lengths = sorted(round(float(np.linalg.norm(np.subtract(s[3:], s[:3]))), 3) for s in e["open_edges"])
    assert lengths == [10.0, 10.0, 10.0, 10.0]


def test_a_t_junction_is_a_crack_and_its_stitch_is_loose():
    e = find_errors(t_junction_strip(), PROFILE)
    assert [10.0, 10.0, 0.0] in [[round(v, 3) for v in p] for p in e["cracks"]]
    assert e["faces"]["loose"] == [6]  # the zero-area stitching triangle (3, 4, 2)


def test_the_result_is_plain_json():
    e = find_errors(two_sided_wall(), PROFILE)
    assert json.loads(json.dumps(e)) == e
```

- [ ] **Step 3: Run them and see them fail**

Run: `.venv/Scripts/python.exe -m pytest engine/tests/test_errors.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.detectors.errors'`

- [ ] **Step 4: Implement** `engine/detectors/errors.py`:

```python
"""What is wrong with a model, face by face, without changing it (spec 2026-09-26, the 3D error
filter). Every answer comes from a detector the fix pipeline already trusts; this module only
gathers them.

Face numbers are `mesh`'s own, which the meshbuf also uses (`tri_face_id = arange`), so the
viewer colours face `f` by looking it up here. Points and lines are world inches; the viewer
subtracts the meshbuf's `origin_offset`.
"""
from __future__ import annotations

import numpy as np

from engine.fixes.orient import ORIENT_FLIP, classify_orientation
from engine.fixes.overlap import double_layers
from engine.fixes.pipeline import FixProfile, guard_depth_tol
from engine.guard.views import VIEWS_26
from engine.model import MeshData
from engine.pipeline import analyse_topology
from engine.vis.exposure import EXP_HIDDEN, classify_exposure, compute_side_exposure

#: In drawing priority: a face in several kinds is drawn in the first.
KINDS = ("flicker_diff", "flicker_same", "reversed", "hidden", "loose", "open_edges", "cracks")
SPOTS_PER_KIND = 20


def _spot(label: str, points: np.ndarray, value: float, faces) -> dict:
    lo, hi = points.min(axis=0), points.max(axis=0)
    return {"label": label, "centre": [round(float(v), 2) for v in (lo + hi) / 2.0],
            "size": round(float(np.linalg.norm(hi - lo)), 2), "value": round(float(value), 2),
            "faces": [int(f) for f in faces]}


def _face_group_spots(kind: str, pos: np.ndarray, faces: np.ndarray, members: np.ndarray,
                      region: np.ndarray, area: np.ndarray) -> list[dict]:
    """Worst places for a face kind: its faces grouped by flat region, largest area first."""
    groups: dict[int, list[int]] = {}
    for f in members.tolist():
        key = int(region[f]) if region[f] >= 0 else -1 - f  # a face in no region stands alone
        groups.setdefault(key, []).append(f)
    ranked = sorted(groups.values(), key=lambda fs: (-float(area[fs].sum()), fs[0]))
    return [_spot(f"{kind} ({len(fs)} faces)", pos[faces[fs]].reshape(-1, 3), float(area[fs].sum()), fs)
            for fs in ranked[:SPOTS_PER_KIND]]


def find_errors(mesh: MeshData, profile: FixProfile = FixProfile()) -> dict:
    topo = analyse_topology(mesh, frozenset(), coplanar_angle=profile.coplanar_angle,
                            soft_angle=profile.soft_angle)
    pos, faces, ok = topo.positions_w, topo.face_w, topo.ok
    centre = (pos.min(axis=0) + pos.max(axis=0)) / 2.0
    positions_c = pos - centre
    tri = pos[faces]
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)

    # hidden and reversed: the pipeline's own exposure and orientation verdicts
    front, back = compute_side_exposure(positions_c, faces, ok, n_dirs=profile.n_dirs)
    hidden = np.nonzero((classify_exposure(front + back, ok, profile.slit_threshold) == EXP_HIDDEN) & ok)[0]
    reversed_ = np.nonzero((classify_orientation(front, back, ok) == ORIENT_FLIP) & ok)[0]
    loose = np.nonzero(~ok)[0]

    # flicker: two layers of one plane, split by whether the two materials differ
    depth_tol = guard_depth_tol(topo.quanta, profile)
    dl = double_layers(positions_c, faces, depth_tol, VIEWS_26, profile.guard_size, centre=centre)
    diff: set[int] = set()
    same: set[int] = set()
    for i, j, _s, _o in dl["pair_list"]:
        target = same if mesh.face_material[i] == mesh.face_material[j] else diff
        target.update((i, j))
    same -= diff

    # open edges and cracks from the same edge table the pipeline builds
    open_rows = np.nonzero(topo.table.counts == 1)[0]
    open_edges = pos[topo.table.edges[open_rows]].reshape(-1, 6)
    t_ids = sorted({int(v) for vs in topo.t_vertices.values() for v in np.atleast_1d(vs)})
    cracks = pos[t_ids] if t_ids else np.zeros((0, 3))

    flicker_spots = {"flicker_diff": [], "flicker_same": []}
    for plane in sorted(dl["planes"], key=lambda p: (-p["px"], -p["area"])):
        fs = [int(f) for f in plane["faces"]]
        kind = "flicker_diff" if any(f in diff for f in fs) else "flicker_same"
        if len(flicker_spots[kind]) < SPOTS_PER_KIND:
            flicker_spots[kind].append(_spot(f"{plane['pairs']} pairs, {plane['px']} px visible",
                                             pos[faces[fs]].reshape(-1, 3), plane["px"], fs))
    lengths = np.linalg.norm(open_edges[:, 3:] - open_edges[:, :3], axis=1)
    open_order = np.argsort(-lengths, kind="stable")[:SPOTS_PER_KIND]

    face_lists = {"flicker_diff": sorted(diff), "flicker_same": sorted(same),
                  "reversed": reversed_.tolist(), "hidden": hidden.tolist(), "loose": loose.tolist()}
    spots = dict(flicker_spots)
    for kind in ("reversed", "hidden", "loose"):
        spots[kind] = _face_group_spots(kind, pos, faces, np.asarray(face_lists[kind], dtype=np.int64),
                                        topo.face_region, area)
    spots["open_edges"] = [_spot(f"open edge {lengths[k]:.1f} in", open_edges[k].reshape(2, 3),
                                 lengths[k], []) for k in open_order.tolist()]
    spots["cracks"] = [_spot("T-junction point", cracks[k:k + 1], 0.0, [])
                       for k in range(min(SPOTS_PER_KIND, len(cracks)))]

    counts = {k: len(face_lists[k]) for k in face_lists}
    counts["open_edges"] = int(len(open_edges))
    counts["cracks"] = int(len(cracks))
    return {"version": 1, "n_faces": int(mesh.n_faces),
            "counts": {k: counts[k] for k in KINDS},
            "faces": {k: [int(f) for f in face_lists[k]] for k in face_lists},
            "open_edges": [[round(float(v), 3) for v in row] for row in open_edges],
            "cracks": [[round(float(v), 3) for v in row] for row in cracks],
            "flicker_pairs": dl["pair_list"],
            "spots": spots}
```

- [ ] **Step 5: Run the tests and see them pass**

Run: `.venv/Scripts/python.exe -m pytest engine/tests/test_errors.py -q -p no:cacheprovider`
Expected: 7 passed. If `test_a_face_turned_inside_out_is_reversed` fails because the cube's exposure calls the turned face a thin sheet, print `classify_orientation(front, back, ok)[0]` and the face's `front`/`back`. A closed cube's turned face sees only its back, so it must be `ORIENT_FLIP`. Fix the test's face choice rather than the verdict.

- [ ] **Step 6: Run the whole engine suite** (nothing else may change)

Run: `.venv/Scripts/python.exe -m pytest engine/tests -q -p no:cacheprovider`
Expected: all pass (610 + 1 xfailed + the new ones).

- [ ] **Step 7: Commit**

```bash
git add engine/detectors/errors.py engine/tests/test_errors.py engine/tests/fixtures/build.py
git commit -m "feat(engine): find_errors says what is wrong with each face, without changing the model" -m "The 3D error filter's detector pass: flicker pairs by material, hidden, reversed, zero-area, open edges, T-junction points, and the worst spots per kind, all from detectors the fix pipeline already uses." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

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

### Task 5: the API keeps one errors file per version

**Files:**
- Create: `api/routers/errors.py`
- Modify: `api/main.py` (include the router)
- Test: `api/tests/test_errors.py`

**Interfaces:**
- Consumes: `find_errors`; the `ModelVersion` and `VersionAsset` models; `get_db`; `Settings.data_dir`.
- Produces:
  - `POST /api/versions/{id}/errors` returns 200 with the errors dict (Task 2's keys).
  - `GET /api/versions/{id}/errors` returns 200 with the dict, or 404 with `{"detail": "not computed yet"}`.
  - Unknown version: 404 `{"detail": "Version not found"}`.
  - `errors_file(settings, version_id) -> Path` is importable by Task 6.

- [ ] **Step 1: Write the failing tests** (`api/tests/test_errors.py`)

```python
def test_errors_are_not_computed_before_the_button(client, imported_cube):
    vid = imported_cube["versions"][0]["id"]
    r = client.get(f"/api/versions/{vid}/errors")
    assert r.status_code == 404
    assert r.json()["detail"] == "not computed yet"


def test_find_errors_saves_the_file_and_serves_it(client, imported_cube):
    from api.routers.errors import errors_file
    from api.settings import get_settings
    vid = imported_cube["versions"][0]["id"]
    r = client.post(f"/api/versions/{vid}/errors")
    assert r.status_code == 200
    body = r.json()
    assert body["n_faces"] == 12
    assert set(body["counts"]) == {"flicker_diff", "flicker_same", "reversed", "hidden", "loose",
                                   "open_edges", "cracks"}
    assert errors_file(get_settings(), vid).exists()
    again = client.get(f"/api/versions/{vid}/errors")
    assert again.status_code == 200
    assert again.json() == body


def test_an_unknown_version_is_refused(client):
    r = client.post("/api/versions/999999/errors")
    assert r.status_code == 404
    assert r.json()["detail"] == "Version not found"
```

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/Scripts/python.exe -m pytest api/tests/test_errors.py -q -p no:cacheprovider`
Expected: FAIL (404 for the POST: no such route).

- [ ] **Step 3: Implement** `api/routers/errors.py`:

```python
"""The 3D error filter's files: one per version, `data/errors/version-<id>.json`."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import ModelVersion, VersionAsset
from api.settings import Settings, get_settings
from engine.detectors.errors import find_errors
from engine.fixes.pipeline import FixProfile
from engine.io.obj_reader import read_obj

router = APIRouter(prefix="/api/versions", tags=["errors"])


def errors_file(settings: Settings, version_id: int) -> Path:
    return settings.data_dir / "errors" / f"version-{version_id}.json"


def write_errors(settings: Settings, version_id: int, result: dict) -> None:
    path = errors_file(settings, version_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result), encoding="utf-8")
    tmp.replace(path)


@router.post("/{id}/errors")
def compute_errors(id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    version = db.scalar(select(ModelVersion).where(ModelVersion.id == id))
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    obj_asset = db.scalar(select(VersionAsset).where(VersionAsset.version_id == id, VersionAsset.kind == "obj"))
    if obj_asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OBJ asset not found")
    obj_path = settings.data_dir / obj_asset.path
    if not obj_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OBJ file missing on disk")
    result = find_errors(read_obj(obj_path), FixProfile())
    write_errors(settings, id, result)
    return JSONResponse(result)


@router.get("/{id}/errors")
def get_errors(id: int, settings: Settings = Depends(get_settings)):
    path = errors_file(settings, id)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not computed yet")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))
```

In `api/main.py`, add the import next to the other routers and include it:

```python
from api.routers.errors import router as errors_router
```

```python
    app.include_router(errors_router)
```

- [ ] **Step 4: Run them and see them pass**

Run: `.venv/Scripts/python.exe -m pytest api/tests/test_errors.py -q -p no:cacheprovider`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add api/routers/errors.py api/main.py api/tests/test_errors.py
git commit -m "feat(api): Find errors per version, kept as data/errors/version-<id>.json" -m "POST computes a version's errors file with find_errors; GET serves it or says not computed yet. No table, no migration." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

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

### Task 7: the web client can ask for errors

**Files:**
- Modify: `web/src/api/client.ts`
- Test: `web/src/api/client.test.ts` (append)

**Interfaces:**
- Consumes: the `ErrorsFile` type from Task 8. (Task 8 is written first when executing in order; if running 7 first, import the type from `../utils/errorLayers` after Task 8 lands.)
- Produces:
  - `fetchErrors(versionId: number): Promise<ErrorsFile | null>`: `null` on 404.
  - `computeErrors(versionId: number): Promise<ErrorsFile>`.

**Do Task 8 before Task 7**: Task 7 imports Task 8's type.

- [ ] **Step 1: Write the failing tests** (append inside the existing `describe` of `web/src/api/client.test.ts`)

```ts
  it('fetchErrors returns null when a version has no errors file yet', async () => {
    const { fetchErrors } = await import('./client')
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'not computed yet' }), { status: 404 })
    )
    expect(await fetchErrors(6)).toBeNull()
  })

  it('computeErrors posts to the version and returns the file', async () => {
    const { computeErrors } = await import('./client')
    const body = { version: 1, n_faces: 12, counts: {}, faces: {}, open_edges: [], cracks: [], flicker_pairs: [], spots: {} }
    const spy = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
    globalThis.fetch = spy
    expect(await computeErrors(6)).toEqual(body)
    expect(spy.mock.calls[0][0]).toContain('/versions/6/errors')
    expect(spy.mock.calls[0][1].method).toBe('POST')
  })
```

- [ ] **Step 2: Run and see them fail**

Run: `pnpm --dir web exec vitest run src/api/client.test.ts`
Expected: FAIL (`fetchErrors is not a function`).

- [ ] **Step 3: Implement** (append to `web/src/api/client.ts`)

```ts
import type { ErrorsFile } from '../utils/errorLayers'

export async function fetchErrors(versionId: number): Promise<ErrorsFile | null> {
  const res = await fetch(`${API_BASE}/versions/${versionId}/errors`)
  if (res.status === 404) return null
  await checkResponse(res, 'Failed to fetch errors')
  return res.json()
}

export async function computeErrors(versionId: number): Promise<ErrorsFile> {
  const res = await checkResponse(
    await fetch(`${API_BASE}/versions/${versionId}/errors`, { method: 'POST' }),
    'Failed to find errors'
  )
  return res.json()
}
```

Move the `import type` line to the top of the file with the other imports.

- [ ] **Step 4: Run and see them pass**

Run: `pnpm --dir web exec vitest run src/api/client.test.ts`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/client.ts web/src/api/client.test.ts
git commit -m "feat(web): client asks for a version's errors file or has it computed" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: the filter logic, as pure functions

**Files:**
- Create: `web/src/utils/errorLayers.ts`
- Test: `web/src/utils/errorLayers.test.ts`

**Interfaces:**
- Produces (exact names):

```ts
export type ErrorKind = 'flicker_diff' | 'flicker_same' | 'reversed' | 'hidden' | 'loose' | 'open_edges' | 'cracks' | 'facade'
export interface ErrorSpot { label: string; centre: [number, number, number]; size: number; value: number; faces: number[] }
export interface ErrorsFile {
  version: number; n_faces: number
  counts: Record<Exclude<ErrorKind, 'facade'>, number>
  faces: Record<'flicker_diff' | 'flicker_same' | 'reversed' | 'hidden' | 'loose', number[]>
  layers: { facade: number[] }; layer_counts: { facade: number }   // Task 14
  open_edges: number[][]; cracks: number[][]
  flicker_pairs: [number, number, number, boolean][]
  spots: Record<ErrorKind, ErrorSpot[]>
}
export interface ErrorFilter { enabled: Record<ErrorKind, boolean>; isolate: boolean; blink: boolean }
export const ERROR_KINDS: { kind: ErrorKind; label: string; color: number; draw: 'faces' | 'lines' | 'points' }[]
export const FACE_KINDS: ErrorKind[]  // the 'faces' ones, in priority order; 'facade' last
export function faceList(file: ErrorsFile, kind: FaceKind): number[]
export function countOf(file: ErrorsFile, kind: ErrorKind): number
export function defaultFilter(): ErrorFilter   // every kind on except 'facade'
export function overlayFaces(file: ErrorsFile, filter: ErrorFilter): { faces: number[]; colors: Float32Array }
export function blinkColors(file: ErrorsFile, faces: number[], triMaterial: ArrayLike<number>, phase: 0 | 1): Float32Array
export function partnersOf(file: ErrorsFile, face: number): { face: number; shared: number; opposite: boolean }[]
export function kindsOf(file: ErrorsFile, face: number): ErrorKind[]
export function openEdgeSegments(file: ErrorsFile, origin: number[]): Float32Array
export function crackPoints(file: ErrorsFile, origin: number[]): Float32Array
export function toViewer(p: number[], origin: number[]): [number, number, number]
export function materialColor(index: number): number
```

- [ ] **Step 1: Write the failing tests** (`web/src/utils/errorLayers.test.ts`)

```ts
import { describe, it, expect } from 'vitest'
import {
  ERROR_KINDS, FACE_KINDS, defaultFilter, overlayFaces, blinkColors, partnersOf, kindsOf,
  openEdgeSegments, crackPoints, toViewer, materialColor, countOf, type ErrorsFile,
} from './errorLayers'

const file: ErrorsFile = {
  version: 1, n_faces: 6,
  counts: { flicker_diff: 2, flicker_same: 0, reversed: 1, hidden: 2, loose: 0, open_edges: 1, cracks: 1 },
  faces: { flicker_diff: [0, 1], flicker_same: [], reversed: [1], hidden: [4, 5], loose: [] },
  layers: { facade: [0, 3] }, layer_counts: { facade: 2 },
  open_edges: [[10, 0, 0, 20, 0, 0]], cracks: [[15, 5, 0]],
  flicker_pairs: [[0, 1, 100, true]],
  spots: { flicker_diff: [], flicker_same: [], reversed: [], hidden: [], loose: [], open_edges: [], cracks: [], facade: [] },
}

describe('errorLayers', () => {
  it('lists the seven error kinds and the facade layer in priority order with the spec colours', () => {
    expect(ERROR_KINDS.map(k => k.kind)).toEqual(
      ['flicker_diff', 'flicker_same', 'reversed', 'hidden', 'loose', 'open_edges', 'cracks', 'facade'])
    expect(ERROR_KINDS[0].color).toBe(0xd8282f)
    expect(FACE_KINDS).toEqual(['flicker_diff', 'flicker_same', 'reversed', 'hidden', 'loose', 'facade'])
  })

  it('draws the facade in teal only when asked, and never over an error colour', () => {
    const f = defaultFilter()
    expect(f.enabled.facade).toBe(false)
    f.enabled.facade = true
    const { faces, colors } = overlayFaces(file, f)
    expect(faces).toEqual([0, 1, 3, 4, 5])
    // face 0 is flicker_diff AND facade: red wins; face 3 (slot 2) is facade only: teal
    expect(Array.from(colors.slice(0, 3)).map(v => Math.round(v * 255))).toEqual([0xd8, 0x28, 0x2f])
    expect(Array.from(colors.slice(18, 21)).map(v => Math.round(v * 255))).toEqual([0x0d, 0x94, 0x88])
  })

  it('counts errors from counts and the facade from layer_counts', () => {
    expect(countOf(file, 'reversed')).toBe(1)
    expect(countOf(file, 'facade')).toBe(2)
  })

  it('draws only the enabled kinds, a face in two kinds in the first one', () => {
    const f = defaultFilter()
    const { faces, colors } = overlayFaces(file, f)
    expect(faces).toEqual([0, 1, 4, 5])
    // face 1 is flicker_diff AND reversed: red wins
    expect(Array.from(colors.slice(9, 12)).map(v => Math.round(v * 255))).toEqual([0xd8, 0x28, 0x2f])
    f.enabled.flicker_diff = false
    expect(overlayFaces(file, f).faces).toEqual([1, 4, 5])
    expect(Array.from(overlayFaces(file, f).colors.slice(0, 3)).map(v => Math.round(v * 255))).toEqual([0x96, 0x50, 0xff])
  })

  it('blinks a flicker face between its own material and its partner s', () => {
    const tm = [3, 7, 0, 0, 0, 0]
    const a = blinkColors(file, [0, 1], tm, 0)
    const b = blinkColors(file, [0, 1], tm, 1)
    expect(Array.from(a.slice(0, 3))).toEqual(Array.from(b.slice(9, 12)))  // face 0 now = face 1 then
    expect(Array.from(a.slice(0, 3))).not.toEqual(Array.from(b.slice(0, 3)))
  })

  it('names a face s partners and kinds', () => {
    expect(partnersOf(file, 1)).toEqual([{ face: 0, shared: 100, opposite: true }])
    expect(kindsOf(file, 1)).toEqual(['flicker_diff', 'reversed'])
    expect(kindsOf(file, 2)).toEqual([])
    expect(kindsOf(file, 3)).toEqual(['facade'])
  })

  it('moves lines and points into the viewer s frame', () => {
    const origin = [10, 0, 0]
    expect(Array.from(openEdgeSegments(file, origin))).toEqual([0, 0, 0, 10, 0, 0])
    expect(Array.from(crackPoints(file, origin))).toEqual([5, 5, 0])
    expect(toViewer([11, 2, 3], origin)).toEqual([1, 2, 3])
  })

  it('gives different materials different colours', () => {
    expect(materialColor(0)).not.toBe(materialColor(1))
    expect(materialColor(12)).toBe(materialColor(0))
  })
})
```

- [ ] **Step 2: Run and see them fail**

Run: `pnpm --dir web exec vitest run src/utils/errorLayers.test.ts`
Expected: FAIL (cannot find module `./errorLayers`).

- [ ] **Step 3: Implement** `web/src/utils/errorLayers.ts`:

```ts
export type ErrorKind = 'flicker_diff' | 'flicker_same' | 'reversed' | 'hidden' | 'loose' | 'open_edges' | 'cracks' | 'facade'
type FaceKind = 'flicker_diff' | 'flicker_same' | 'reversed' | 'hidden' | 'loose' | 'facade'

export interface ErrorSpot { label: string; centre: [number, number, number]; size: number; value: number; faces: number[] }
export interface ErrorsFile {
  version: number
  n_faces: number
  counts: Record<Exclude<ErrorKind, 'facade'>, number>
  faces: Record<Exclude<FaceKind, 'facade'>, number[]>
  layers: { facade: number[] }          // Task 14: every face seen from outside -- not an error
  layer_counts: { facade: number }
  open_edges: number[][]
  cracks: number[][]
  flicker_pairs: [number, number, number, boolean][]
  spots: Record<ErrorKind, ErrorSpot[]>
}
export interface ErrorFilter { enabled: Record<ErrorKind, boolean>; isolate: boolean; blink: boolean }

export const ERROR_KINDS: { kind: ErrorKind; label: string; color: number; draw: 'faces' | 'lines' | 'points' }[] = [
  { kind: 'flicker_diff', label: 'Flicker: texture on texture', color: 0xd8282f, draw: 'faces' },
  { kind: 'flicker_same', label: 'Flicker: same material', color: 0xf08c00, draw: 'faces' },
  { kind: 'reversed', label: 'Reversed / back faces', color: 0x9650ff, draw: 'faces' },
  { kind: 'hidden', label: 'Hidden inside faces', color: 0x1f5bff, draw: 'faces' },
  { kind: 'loose', label: 'Zero-area and stray bits', color: 0xe0199b, draw: 'faces' },
  { kind: 'open_edges', label: 'Open edges', color: 0x16a34a, draw: 'lines' },
  { kind: 'cracks', label: 'Cracks (T-junction points)', color: 0x00b4d8, draw: 'points' },
  { kind: 'facade', label: 'Facade (seen from outside)', color: 0x0d9488, draw: 'faces' },
]
export const FACE_KINDS = ERROR_KINDS.filter(k => k.draw === 'faces').map(k => k.kind) as FaceKind[]

/** A face kind's faces: the errors' own lists, or the facade layer (Task 14). */
export function faceList(file: ErrorsFile, kind: FaceKind): number[] {
  return kind === 'facade' ? (file.layers?.facade ?? []) : file.faces[kind]
}

/** How many of a kind the file holds: faces, open edges, crack points or facade faces. */
export function countOf(file: ErrorsFile, kind: ErrorKind): number {
  return kind === 'facade' ? (file.layer_counts?.facade ?? 0) : file.counts[kind]
}

// 12 distinct hues for blinking materials against each other
const MATERIAL_PALETTE = [0xe6194b, 0x3cb44b, 0xffe119, 0x4363d8, 0xf58231, 0x911eb4,
  0x46f0f0, 0xf032e6, 0xbcf60c, 0xfabebe, 0x008080, 0x9a6324]

export function materialColor(index: number): number {
  return MATERIAL_PALETTE[((index % MATERIAL_PALETTE.length) + MATERIAL_PALETTE.length) % MATERIAL_PALETTE.length]
}

export function defaultFilter(): ErrorFilter {
  const enabled = Object.fromEntries(ERROR_KINDS.map(k => [k.kind, k.kind !== 'facade'])) as Record<ErrorKind, boolean>
  return { enabled, isolate: false, blink: false }
}

function rgb(color: number): [number, number, number] {
  return [((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255]
}

function fill(colors: Float32Array, slot: number, color: number) {
  const [r, g, b] = rgb(color)
  for (let v = 0; v < 3; v++) colors.set([r, g, b], slot * 9 + v * 3)
}

export function overlayFaces(file: ErrorsFile, filter: ErrorFilter): { faces: number[]; colors: Float32Array } {
  const colorOf = new Map<number, number>()
  for (const k of FACE_KINDS) {
    if (!filter.enabled[k]) continue
    const color = ERROR_KINDS.find(e => e.kind === k)!.color
    for (const f of faceList(file, k)) if (!colorOf.has(f)) colorOf.set(f, color)
  }
  const faces = [...colorOf.keys()].sort((a, b) => a - b)
  const colors = new Float32Array(faces.length * 9)
  faces.forEach((f, slot) => fill(colors, slot, colorOf.get(f)!))
  return { faces, colors }
}

export function partnersOf(file: ErrorsFile, face: number): { face: number; shared: number; opposite: boolean }[] {
  const out: { face: number; shared: number; opposite: boolean }[] = []
  for (const [i, j, shared, opposite] of file.flicker_pairs) {
    if (i === face) out.push({ face: j, shared, opposite })
    else if (j === face) out.push({ face: i, shared, opposite })
  }
  return out
}

export function blinkColors(file: ErrorsFile, faces: number[], triMaterial: ArrayLike<number>, phase: 0 | 1): Float32Array {
  const colors = new Float32Array(faces.length * 9)
  faces.forEach((f, slot) => {
    const partner = partnersOf(file, f)[0]
    const own = triMaterial[f]
    const other = partner ? triMaterial[partner.face] : own
    fill(colors, slot, materialColor(phase === 0 ? own : other))
  })
  return colors
}

export function kindsOf(file: ErrorsFile, face: number): ErrorKind[] {
  return FACE_KINDS.filter(k => faceList(file, k).includes(face))
}

export function toViewer(p: number[], origin: number[]): [number, number, number] {
  return [p[0] - origin[0], p[1] - origin[1], p[2] - origin[2]]
}

export function openEdgeSegments(file: ErrorsFile, origin: number[]): Float32Array {
  const out = new Float32Array(file.open_edges.length * 6)
  file.open_edges.forEach((s, k) => {
    out.set(toViewer(s.slice(0, 3), origin), k * 6)
    out.set(toViewer(s.slice(3, 6), origin), k * 6 + 3)
  })
  return out
}

export function crackPoints(file: ErrorsFile, origin: number[]): Float32Array {
  const out = new Float32Array(file.cracks.length * 3)
  file.cracks.forEach((p, k) => out.set(toViewer(p, origin), k * 3))
  return out
}
```

- [ ] **Step 4: Run and see them pass**

Run: `pnpm --dir web exec vitest run src/utils/errorLayers.test.ts`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add web/src/utils/errorLayers.ts web/src/utils/errorLayers.test.ts
git commit -m "feat(web): the error filter's logic -- kinds, colours, blink, partners, lines and points" -m "Pure functions over the errors file, so every rule is unit-tested and the viewport only draws what they return." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: the viewport draws the errors

**Files:**
- Modify: `web/src/three/Viewport.ts`

**Interfaces:**
- Produces (new public methods on `Viewport`):
  - `setErrorOverlay(faces: number[], colors: Float32Array, isolate: boolean): void`
  - `setErrorBlink(colorsA: Float32Array | null, colorsB: Float32Array | null): void` (`null` stops the blink)
  - `setErrorLines(segments: Float32Array, color: number): void` and `setErrorPoints(points: Float32Array, color: number): void` (an empty array removes them)
  - `flyTo(centre: [number, number, number], size: number): void` (viewer coordinates)
  - `originOffset(): [number, number, number]` (the loaded meshbuf's `header.origin_offset`)

There is no unit test: WebGL does not run under vitest. Task 11 checks it in the browser.

- [ ] **Step 1: Implement.** Add to the `parts` type:

```ts
    errors?: THREE.Mesh
    errorLines?: THREE.LineSegments
    errorPoints?: THREE.Points
```

Add these fields next to `private currentData?`:

```ts
  private xray = false
  private blinkA: Float32Array | null = null
  private blinkB: Float32Array | null = null
  private blinkPhase = -1
```

In `loop`, before `this.renderer.render(...)`:

```ts
    if (this.blinkA && this.blinkB && this.parts.errors) {
      const phase = Math.floor(performance.now() / 125) % 2   // 4 swaps a second
      if (phase !== this.blinkPhase) {
        const attr = this.parts.errors.geometry.getAttribute('color') as THREE.BufferAttribute
        attr.copyArray(phase === 0 ? this.blinkA : this.blinkB)
        attr.needsUpdate = true
        this.blinkPhase = phase
      }
    }
```

In `setXRay`, record the state at the top: `this.xray = xray`.

Add the methods:

```ts
  private removePart(name: 'errors' | 'errorLines' | 'errorPoints') {
    const part = this.parts[name]
    if (!part) return
    this.group.remove(part)
    part.geometry.dispose()
    ;(part.material as THREE.Material).dispose()
    delete this.parts[name]
  }

  setErrorOverlay(faces: number[], colors: Float32Array, isolate: boolean) {
    this.removePart('errors')
    if (this.parts.facade) {
      const m = this.parts.facade.material as THREE.MeshStandardMaterial
      m.transparent = isolate || this.xray
      m.opacity = isolate ? 0.08 : this.xray ? 0.25 : 1.0
      m.depthWrite = !(isolate || this.xray)
      m.needsUpdate = true
    }
    if (!this.lastPositions || faces.length === 0) return
    const pos = new Float32Array(faces.length * 9)
    faces.forEach((f, slot) => pos.set(this.lastPositions!.subarray(f * 9, f * 9 + 9), slot * 9))
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    geom.setAttribute('color', new THREE.BufferAttribute(colors.slice(), 3))
    const mat = new THREE.MeshBasicMaterial({
      vertexColors: true, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1,
    })
    this.parts.errors = new THREE.Mesh(geom, mat)
    this.group.add(this.parts.errors)
    this.blinkPhase = -1
  }

  setErrorBlink(colorsA: Float32Array | null, colorsB: Float32Array | null) {
    this.blinkA = colorsA
    this.blinkB = colorsB
    this.blinkPhase = -1
  }

  setErrorLines(segments: Float32Array, color: number) {
    this.removePart('errorLines')
    if (segments.length === 0) return
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(segments, 3))
    this.parts.errorLines = new THREE.LineSegments(geom, new THREE.LineBasicMaterial({ color, depthTest: false }))
    this.group.add(this.parts.errorLines)
  }

  setErrorPoints(points: Float32Array, color: number) {
    this.removePart('errorPoints')
    if (points.length === 0) return
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(points, 3))
    this.parts.errorPoints = new THREE.Points(geom, new THREE.PointsMaterial({ color, size: 6, sizeAttenuation: false, depthTest: false }))
    this.group.add(this.parts.errorPoints)
  }

  flyTo(centre: [number, number, number], size: number) {
    const target = new THREE.Vector3(...centre)
    const dir = this.camera.position.clone().sub(this.controls.target).normalize()
    this.controls.target.copy(target)
    this.camera.position.copy(target).add(dir.multiplyScalar(Math.max(size, 60) * 1.6))
    this.controls.update()
    this.controls.dispatchEvent({ type: 'change' } as any)   // lets syncViewports move the other panel
  }

  originOffset(): [number, number, number] {
    return (this.currentData?.header.origin_offset ?? [0, 0, 0]) as [number, number, number]
  }
```

In `clear()`, reset `this.blinkA = this.blinkB = null`.

- [ ] **Step 2: Type-check**

Run: `pnpm --dir web exec vue-tsc --noEmit`
Expected: the same 3 errors as before (`src/three/Viewport.ts:332,333,360`, which predate this plan; their line numbers may shift) and no new ones.

- [ ] **Step 3: Commit**

```bash
git add web/src/three/Viewport.ts
git commit -m "feat(web): the viewport draws error faces, blink, open edges, cracks, and flies to a spot" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: the Errors panel in the workspace

**Files:**
- Create: `web/src/components/ErrorsPanel.vue`
- Modify: `web/src/views/WorkspaceView.vue`

**Interfaces:**
- Consumes: Tasks 7, 8 and 9.
- `ErrorsPanel` props: `before: ErrorsFile | null`, `after: ErrorsFile | null`, `busyBefore: boolean`, `busyAfter: boolean`, `filter: ErrorFilter`, `hasAfter: boolean`.
- `ErrorsPanel` emits: `find` with payload `'before' | 'after'`, and `fly` with an `ErrorSpot` and its panel `'before' | 'after'`.

- [ ] **Step 1: Create** `web/src/components/ErrorsPanel.vue`:

```vue
<template>
  <section class="errors-panel">
    <header>
      <strong>Errors</strong>
      <button v-if="!before" class="btn" :disabled="busyBefore" @click="$emit('find', 'before')">
        {{ busyBefore ? 'Finding errors in BEFORE…' : 'Find errors (BEFORE)' }}
      </button>
      <button v-if="hasAfter && !after" class="btn" :disabled="busyAfter" @click="$emit('find', 'after')">
        {{ busyAfter ? 'Finding errors in AFTER…' : 'Find errors (AFTER)' }}
      </button>
    </header>
    <table v-if="before || after" class="legend">
      <thead><tr><th></th><th>Kind</th><th>BEFORE</th><th>AFTER</th></tr></thead>
      <tbody>
        <tr v-for="k in ERROR_KINDS" :key="k.kind">
          <td><input type="checkbox" v-model="filter.enabled[k.kind]" /></td>
          <td><span class="swatch" :style="{ background: hex(k.color) }"></span>{{ k.label }}</td>
          <td>{{ before ? countOf(before, k.kind).toLocaleString() : '—' }}</td>
          <td>{{ after ? countOf(after, k.kind).toLocaleString() : '—' }}</td>
        </tr>
      </tbody>
    </table>
    <div v-if="before || after" class="modes">
      <label><input type="checkbox" v-model="filter.isolate" /> Isolate errors</label>
      <label><input type="checkbox" v-model="filter.blink" /> Blink flicker</label>
    </div>
    <div v-if="before" class="spots">
      <strong>Worst spots (BEFORE)</strong>
      <select v-model="spotKind">
        <option v-for="k in ERROR_KINDS" :key="k.kind" :value="k.kind">{{ k.label }}</option>
      </select>
      <ol>
        <li v-for="(s, n) in before.spots[spotKind]" :key="n">
          {{ s.label }} <button class="btn-link" @click="$emit('fly', s, 'before')">fly to</button>
        </li>
      </ol>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ERROR_KINDS, countOf, type ErrorFilter, type ErrorKind, type ErrorsFile, type ErrorSpot } from '../utils/errorLayers'

defineProps<{ before: ErrorsFile | null; after: ErrorsFile | null; busyBefore: boolean; busyAfter: boolean;
  filter: ErrorFilter; hasAfter: boolean }>()
defineEmits<{ (e: 'find', panel: 'before' | 'after'): void; (e: 'fly', spot: ErrorSpot, panel: 'before' | 'after'): void }>()

const spotKind = ref<ErrorKind>('flicker_diff')
const hex = (c: number) => '#' + c.toString(16).padStart(6, '0')
</script>

<style scoped>
.errors-panel { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 10px 12px; font-size: 13px; }
.errors-panel header { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.legend { border-collapse: collapse; width: 100%; }
.legend td, .legend th { padding: 2px 6px; text-align: left; }
.swatch { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; }
.modes { display: flex; gap: 16px; margin: 8px 0; }
.spots ol { margin: 6px 0 0 18px; padding: 0; max-height: 180px; overflow: auto; }
.btn-link { background: none; border: none; color: #1f5bff; cursor: pointer; padding: 0 4px; }
</style>
```

- [ ] **Step 2: Wire it in** `web/src/views/WorkspaceView.vue`.
  - Add to the imports in `<script setup>`:

    ```ts
    import ErrorsPanel from '../components/ErrorsPanel.vue'
    import { fetchErrors, computeErrors } from '../api/client'
    import { defaultFilter, overlayFaces, blinkColors, openEdgeSegments, crackPoints, partnersOf, kindsOf,
      ERROR_KINDS, type ErrorsFile, type ErrorSpot } from '../utils/errorLayers'
    import { reactive, watch } from 'vue'   // merge with the existing vue import if there is one
    ```

  - Add the state:

    ```ts
    const errorFilter = reactive(defaultFilter())
    const errorsBefore = ref<ErrorsFile | null>(null)
    const errorsAfter = ref<ErrorsFile | null>(null)
    const busyBefore = ref(false)
    const busyAfter = ref(false)
    ```

  - Add the apply function and its watcher:

    ```ts
    function applyErrors(view: Viewport | null, file: ErrorsFile | null, triMaterial?: ArrayLike<number>) {
      if (!view) return
      if (!file) {
        view.setErrorOverlay([], new Float32Array(0), false)
        view.setErrorBlink(null, null)
        view.setErrorLines(new Float32Array(0), 0)
        view.setErrorPoints(new Float32Array(0), 0)
        return
      }
      const { faces, colors } = overlayFaces(file, errorFilter)
      view.setErrorOverlay(faces, colors, errorFilter.isolate)
      const flicker = faces.filter(f => file.faces.flicker_diff.includes(f) || file.faces.flicker_same.includes(f))
      if (errorFilter.blink && triMaterial && flicker.length) {
        const a = colors.slice(), b = colors.slice()
        const pa = blinkColors(file, faces, triMaterial, 0), pb = blinkColors(file, faces, triMaterial, 1)
        faces.forEach((f, slot) => {
          if (!flicker.includes(f)) return
          a.set(pa.subarray(slot * 9, slot * 9 + 9), slot * 9)
          b.set(pb.subarray(slot * 9, slot * 9 + 9), slot * 9)
        })
        view.setErrorBlink(a, b)
      } else {
        view.setErrorBlink(null, null)
      }
      const origin = view.originOffset()
      view.setErrorLines(errorFilter.enabled.open_edges ? openEdgeSegments(file, origin) : new Float32Array(0),
        ERROR_KINDS.find(k => k.kind === 'open_edges')!.color)
      view.setErrorPoints(errorFilter.enabled.cracks ? crackPoints(file, origin) : new Float32Array(0),
        ERROR_KINDS.find(k => k.kind === 'cracks')!.color)
    }

    watch([errorFilter, errorsBefore, errorsAfter], () => {
      applyErrors(viewA, errorsBefore.value, snapTriMaterial)
      applyErrors(viewB, errorsAfter.value, fixTriMaterial)
    }, { deep: true })
    ```

  - Keep the two decoded meshbufs' `triMaterial` arrays. Declare next to `viewA` / `viewB`:

    ```ts
    let snapTriMaterial: Uint16Array | undefined
    let fixTriMaterial: Uint16Array | undefined
    ```

  - In `reloadModel()` (about lines 446-453), replace the two `loadModel(decodeMeshbuf(...))` blocks
    with:

    ```ts
        if (snapshotVersion.value && viewA) {
          const snap = decodeMeshbuf(await fetchMeshbuf(snapshotVersion.value.id))
          snapTriMaterial = snap.triMaterial
          viewA.loadModel(snap)
          errorsBefore.value = await fetchErrors(snapshotVersion.value.id)
        }
        if (fixedVersion.value && viewB) {
          const fix = decodeMeshbuf(await fetchMeshbuf(fixedVersion.value.id))
          fixTriMaterial = fix.triMaterial
          viewB.loadModel(fix)
          errorsAfter.value = await fetchErrors(fixedVersion.value.id)
        }
    ```

    `loadModel` clears the viewport's parts, so the watcher below redraws the errors after every
    reload: the assignments to `errorsBefore` and `errorsAfter` trigger it.

  - Add the handlers:

    ```ts
    async function onFindErrors(panel: 'before' | 'after') {
      const version = panel === 'before' ? snapshotVersion.value : fixedVersion.value
      if (!version) return
      const busy = panel === 'before' ? busyBefore : busyAfter
      busy.value = true
      try {
        const file = await computeErrors(version.id)
        if (panel === 'before') errorsBefore.value = file
        else errorsAfter.value = file
      } finally {
        busy.value = false
      }
    }

    function onFly(spot: ErrorSpot, panel: 'before' | 'after') {
      const view = panel === 'before' ? viewA : viewB
      if (!view) return
      const o = view.originOffset()
      view.flyTo([spot.centre[0] - o[0], spot.centre[1] - o[1], spot.centre[2] - o[2]], spot.size)
    }
    ```

  - In the template, just below the existing layer toolbar, add:

    ```vue
    <ErrorsPanel :before="errorsBefore" :after="errorsAfter" :busy-before="busyBefore" :busy-after="busyAfter"
      :filter="errorFilter" :has-after="!!fixedVersion" @find="onFindErrors" @fly="onFly" />
    ```

  - **Click card:** in the existing inspector block (`<div v-if="pickedFace" class="picked-inspector">`,
    about line 182), add inside `.inspector-body`:

    ```vue
    <div v-if="pickedErrors.kinds.length">
      <strong>Errors:</strong> {{ pickedErrors.kinds.map(k => ERROR_KINDS.find(e => e.kind === k)!.label).join(', ') }}
      <div v-for="p in pickedErrors.partners" :key="p.face">
        fights face {{ p.face }} ({{ p.shared.toFixed(1) }} sq in shared{{ p.opposite ? ', back to back' : '' }})
        <button class="btn-link" @click="selectFace(p.face)">select</button>
      </div>
    </div>
    ```

    Add the computed value and the handler. `pickedFace` is already
    `{ viewKind: 'before' | 'after', faceId, point, loading, details?, error? }` (line 291; set in
    `viewA.onPick` / `viewB.onPick`, about lines 390 and 409):

    ```ts
    const pickedErrors = computed(() => {
      const face = pickedFace.value?.faceId
      const file = pickedFace.value?.viewKind === 'after' ? errorsAfter.value : errorsBefore.value
      if (face === undefined || !file) return { kinds: [], partners: [] }
      return { kinds: kindsOf(file, face), partners: partnersOf(file, face) }
    })

    function selectFace(face: number) {
      const current = pickedFace.value
      if (!current) return
      const view = current.viewKind === 'before' ? viewA : viewB
      view?.onPick?.(face, current.point)   // the same path as a click: loads that face's details
    }
    ```

    If `computed` is not yet imported from `vue` in this file, add it to the existing vue import.

- [ ] **Step 3: Type-check and run the web tests**

Run: `pnpm --dir web exec vue-tsc --noEmit` and `pnpm --dir web exec vitest run`
Expected: no new type errors (the same 3 predating ones), and all tests pass.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/ErrorsPanel.vue web/src/views/WorkspaceView.vue
git commit -m "feat(web): Errors panel in the workspace -- find, filter, isolate, blink, click, fly to" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: deploy and check it on CHTM 5th floor

**Files:** none new. This task follows HANDOFF.md section 8.

- [ ] **Step 1: Full suites on the commit.**
  - Engine: `.venv/Scripts/python.exe -m pytest engine/tests -q -p no:cacheprovider`
  - API: `.venv/Scripts/python.exe -m pytest api/tests -q -p no:cacheprovider`
  - Web: `pnpm --dir web exec vitest run`

  Expected: all pass. Write the three summary lines into the ledger.

- [ ] **Step 2: Rebuild the dashboard** from the commit, exactly as HANDOFF section 8 lists:
  1. `git -C .claude/worktrees/dk checkout --detach <commit>`
  2. Copy the four Docker files into `.claude/worktrees/dk`.
  3. `pnpm --dir .claude/worktrees/dk/web install --frozen-lockfile`, then `run build`.
  4. `pg_dump` backup to `data/backups/`.
  5. `docker tag` the current images as `:pre-<date>`.
  6. `docker build` api and web.
  7. `docker compose -p ucmodelfixer up -d --no-build api web`.

  In git bash, set `MSYS_NO_PATHCONV=1` for `docker exec`.

- [ ] **Step 3: Check in the browser** at `http://127.0.0.1:5190/workspace/2` (CHTM 5th floor, model 2):
  1. Press **Find errors (BEFORE)** and time it. The legend's counts must equal
     `data/errors/chtm5-raw.json` from Task 4 Step 5.
  2. Toggle each kind: the red faces follow the red checkbox, and so on.
  3. **Isolate**: the rest of the building fades.
  4. **Blink**: the flicker faces alternate.
  5. Pick **Worst spots → Flicker: texture on texture** and fly to #1. The camera goes to the diagonal
     wall at about (1893, 22949, 2194).
  6. Click a red face there. The card shows "Flicker: texture on texture" and "fights face N".

  Take a screenshot at each of 1, 3, 4 and 5, and send them to the owner.

- [ ] **Step 4: Records.** Update:
  - HANDOFF section 2: dashboard rebuilt from `<commit>`, with the 3D error filter;
  - the session record's history;
  - the ledger.

  Then commit:

```bash
git add docs/superpowers/records/HANDOFF.md docs/superpowers/records/2026-09-24-session-record.md
git add -f .superpowers/sdd/2026-09-21-phase2e-fix-pipeline/progress.md
git commit -m "docs(record): the 3D error filter is live in the dashboard" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: the meshbuf is built once per version (added 2026-09-26 after the owner saw an empty panel)

The owner opened CHTM 5th floor, and both panels stayed blank for about 19 s. `GET /api/versions/6/meshbuf`
takes 12.5 s (measured): `analyse_topology` over 20,599 faces and 26,856 edges on every request.
Versions never change, so the packed meshbuf is kept on disk the first time.

**Files:**
- Modify: `api/routers/versions.py` (`get_meshbuf`)
- Test: `api/tests/test_versions.py` (append)

- [ ] **Step 1: Write the failing test** (append to `api/tests/test_versions.py`)

```python
def test_meshbuf_is_built_once_per_version(client, imported_cube, monkeypatch):
    import api.routers.versions as versions_mod
    vid = imported_cube["versions"][0]["id"]
    first = client.get(f"/api/versions/{vid}/meshbuf")
    assert first.status_code == 200

    def packed_again(*a, **k):
        raise AssertionError("packed again")

    monkeypatch.setattr(versions_mod, "pack_meshbuf", packed_again)
    second = client.get(f"/api/versions/{vid}/meshbuf")
    assert second.status_code == 200
    assert second.content == first.content
    assert second.headers["x-tris-count"] == first.headers["x-tris-count"]
```

- [ ] **Step 2: Run it and see it fail** (the second call packs again and raises "packed again", which surfaces as a 500 or an AssertionError).

Run: `.venv/Scripts/python.exe -m pytest api/tests/test_versions.py::test_meshbuf_is_built_once_per_version -q -p no:cacheprovider`

- [ ] **Step 3: Implement.** In `api/routers/versions.py`, add near the top:

```python
import struct


def meshbuf_cache_file(settings: Settings, version_id: int) -> Path:
    return settings.data_dir / "meshbuf" / f"version-{version_id}.bin"


def _meshbuf_response(buf: bytes) -> Response:
    hlen = struct.unpack("<I", buf[8:12])[0]
    faces = json.loads(buf[12:12 + hlen].decode("utf-8").strip())["counts"]["faces"]
    return Response(content=buf, media_type="application/octet-stream",
                    headers={"X-Tris-Count": str(faces), "X-Face-Count": str(faces),
                             "Cache-Control": "public, max-age=3600"})
```

In `get_meshbuf`, right after the `version is None` check, add:

```python
    cached = meshbuf_cache_file(settings, id)
    if cached.exists():
        return _meshbuf_response(cached.read_bytes())
```

Replace its final `return Response(...)` with:

```python
    cached.parent.mkdir(parents=True, exist_ok=True)
    tmp = cached.with_suffix(".bin.tmp")
    tmp.write_bytes(buf)
    tmp.replace(cached)
    return _meshbuf_response(buf)
```

(`json`, `Path` and `Response` are already imported in this file; check with
`grep -n "^import json\|^from pathlib\|Response" api/routers/versions.py` and add any that are missing.)

- [ ] **Step 4: Run the versions tests and see them pass**

Run: `.venv/Scripts/python.exe -m pytest api/tests/test_versions.py -q -p no:cacheprovider`

- [ ] **Step 5: Commit**

```bash
git add api/routers/versions.py api/tests/test_versions.py
git commit -m "perf(api): a version's meshbuf is built once and kept, not on every open" -m "CHTM 5th floor's meshbuf took 12.5 s per request (20,599 faces); versions never change." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

**Also, in Task 10 (added with this task):** show a loading message in each panel while its meshbuf
loads.
- In `WorkspaceView.vue` add `const loadingA = ref(false)` and `const loadingB = ref(false)`.
- Set each to `true` before its `fetchMeshbuf(...)` in `reloadModel()`, and back to `false` in a
  `finally`.
- In each panel's viewport container add:

  ```vue
  <div v-if="loadingA" class="panel-loading">Loading model… a large building can take 20 s the first time</div>
  ```

  and the same with `loadingB`.
- Style `.panel-loading` as a centred overlay: `position: absolute; inset: 0; display: flex;
  align-items: center; justify-content: center; background: rgba(246,246,248,0.85); color: #555;
  font-size: 14px; z-index: 2;`
- Make sure the viewport container is `position: relative`.

### Task 13: real textures in the 3D viewer (added 2026-09-26, owner: "where's the texture, we need to show it in the model")

The viewer draws each material as a grey shade (`Viewport.loadModel`, vertex colours from
`triMaterial`). Everything needed for textures is already served:
- The meshbuf has UVs: CHTM 5th floor has 61,797 rows, 3 per face.
- Its header lists each material's texture: `{"name": "minecraft_quartz_block_side_-1", "texture": "tex/minecraft_quartz_block_side_-1.png"}`.
- `GET /api/versions/{id}/textures/{file name}` returns the PNG. It is looked up by FILE name:
  `…/textures/minecraft_quartz_block_side_-1.png` → 200, while the material name → 404 (measured).

With textures, coincident faces z-fight as they do in Unity, so the flicker is visible as it really
is. The error filter's colours then draw on top.

**Files:**
- Create: `web/src/utils/materialGroups.ts`, `web/src/utils/materialGroups.test.ts`
- Modify: `web/src/three/Viewport.ts`, `web/src/composables/useLayers.ts` (and its test), `web/src/views/WorkspaceView.vue`

**Interfaces:**
- `groupByMaterial(triMaterial: ArrayLike<number>): { order: Uint32Array; groups: { start: number; count: number; material: number }[] }`
  - `order[k]` is the face drawn at slot k: faces sorted by material, and by face number within a material.
  - `start` and `count` are in VERTICES (3 per face), as three.js `addGroup` wants for non-indexed geometry.
- `textureUrl(versionId: number, texture: string | null): string | null`
- `Viewport.loadModel(data, versionId?: number)` and `Viewport.setTextured(on: boolean)`.
- A new layer `textures`, default `true`, hotkey `u`.

- [ ] **Step 1: Write the failing tests** (`web/src/utils/materialGroups.test.ts`)

```ts
import { describe, it, expect } from 'vitest'
import { groupByMaterial, textureUrl } from './materialGroups'

describe('groupByMaterial', () => {
  it('sorts faces by material into one group per material, keeping face order within a material', () => {
    const { order, groups } = groupByMaterial([2, 0, 2, 1, 0])
    expect(Array.from(order)).toEqual([1, 4, 3, 0, 2])
    expect(groups).toEqual([
      { start: 0, count: 6, material: 0 },
      { start: 6, count: 3, material: 1 },
      { start: 9, count: 6, material: 2 },
    ])
  })

  it('handles an empty model', () => {
    const { order, groups } = groupByMaterial([])
    expect(order.length).toBe(0)
    expect(groups).toEqual([])
  })
})

describe('textureUrl', () => {
  it('asks the API for a texture by its file name', () => {
    expect(textureUrl(6, 'tex/minecraft_quartz_block_side_-1.png'))
      .toBe('/api/versions/6/textures/minecraft_quartz_block_side_-1.png')
    expect(textureUrl(6, null)).toBeNull()
  })
})
```

- [ ] **Step 2: Run them and see them fail**

Run: `pnpm --dir web exec vitest run src/utils/materialGroups.test.ts`
Expected: FAIL (cannot find module).

- [ ] **Step 3: Implement** `web/src/utils/materialGroups.ts`

```ts
export interface MaterialGroups {
  order: Uint32Array
  groups: { start: number; count: number; material: number }[]
}

/** Faces sorted by material so each material draws as one group; order[k] is the face drawn at slot k. */
export function groupByMaterial(triMaterial: ArrayLike<number>): MaterialGroups {
  const n = triMaterial.length
  const order = new Uint32Array(n)
  for (let i = 0; i < n; i++) order[i] = i
  order.sort((a, b) => triMaterial[a] - triMaterial[b] || a - b)
  const groups: MaterialGroups['groups'] = []
  let start = 0
  for (let k = 1; k <= n; k++) {
    if (k === n || triMaterial[order[k]] !== triMaterial[order[start]]) {
      groups.push({ start: start * 3, count: (k - start) * 3, material: triMaterial[order[start]] })
      start = k
    }
  }
  return { order, groups }
}

/** The API serves a version's textures by their FILE name, e.g. `…/textures/minecraft_quartz_block_side_-1.png`. */
export function textureUrl(versionId: number, texture: string | null): string | null {
  if (!texture) return null
  const name = texture.split('/').pop()!
  return `/api/versions/${versionId}/textures/${encodeURIComponent(name)}`
}
```

- [ ] **Step 4: Run and see them pass**

Run: `pnpm --dir web exec vitest run src/utils/materialGroups.test.ts`
Expected: 3 passed.

- [ ] **Step 5: The textured facade in `web/src/three/Viewport.ts`**
  - Add `textured?: THREE.Mesh` to the `parts` type, and the fields `private faceOrder?: Uint32Array` and
    `private texturedOn = true`.
  - Import `groupByMaterial, textureUrl` from `../utils/materialGroups`.
  - Change the signature to `loadModel(data: DecodedMeshbuf, versionId?: number)`. At the end of
    `loadModel` (before the camera fit), add:

```ts
    if (versionId !== undefined && data.header.materials.some(m => m.texture)) {
      const { order, groups } = groupByMaterial(data.triMaterial)
      const n = order.length
      const pos = new Float32Array(n * 9), nor = new Float32Array(n * 9), uv = new Float32Array(n * 6)
      for (let k = 0; k < n; k++) {
        const f = order[k]
        pos.set(data.positions.subarray(f * 9, f * 9 + 9), k * 9)
        nor.set(data.normals.subarray(f * 9, f * 9 + 9), k * 9)
        uv.set(data.uvs.subarray(f * 6, f * 6 + 6), k * 6)
      }
      const tgeom = new THREE.BufferGeometry()
      tgeom.setAttribute('position', new THREE.BufferAttribute(pos, 3))
      tgeom.setAttribute('normal', new THREE.BufferAttribute(nor, 3))
      tgeom.setAttribute('uv', new THREE.BufferAttribute(uv, 2))
      const nMat = data.header.materials.length
      const loader = new THREE.TextureLoader()
      const mats: THREE.Material[] = data.header.materials.map((m, i) => {
        const url = textureUrl(versionId, m.texture)
        const mat = new THREE.MeshStandardMaterial({
          side: THREE.DoubleSide, roughness: 0.9, metalness: 0.0,
          polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
          color: url ? 0xffffff : new THREE.Color().setScalar(0.8 + (i % 5) * 0.04),
        })
        if (url) {
          const tex = loader.load(url)
          tex.wrapS = tex.wrapT = THREE.RepeatWrapping
          tex.magFilter = THREE.NearestFilter          // block textures stay crisp
          tex.colorSpace = THREE.SRGBColorSpace
          mat.map = tex
        }
        return mat
      })
      mats.push(new THREE.MeshStandardMaterial({ side: THREE.DoubleSide, color: 0xcccccc }))  // faces with no material
      for (const g of groups) tgeom.addGroup(g.start, g.count, g.material < nMat ? g.material : nMat)
      this.parts.textured = new THREE.Mesh(tgeom, mats)
      this.faceOrder = order
      this.group.add(this.parts.textured)
      this.setTextured(this.texturedOn)
    }
```

  - Add the toggle and a helper that every look change goes through:

```ts
  setTextured(on: boolean) {
    this.texturedOn = on
    const hasTextured = !!this.parts.textured
    if (this.parts.textured) this.parts.textured.visible = on
    if (this.parts.facade) this.parts.facade.visible = !(on && hasTextured)
  }

  /** Every material the model's surface is drawn with, shaded and textured. */
  private surfaceMaterials(): THREE.MeshStandardMaterial[] {
    const out: THREE.MeshStandardMaterial[] = []
    for (const mesh of [this.parts.facade, this.parts.textured]) {
      if (!mesh) continue
      const m = mesh.material
      out.push(...((Array.isArray(m) ? m : [m]) as THREE.MeshStandardMaterial[]))
    }
    return out
  }
```

  - `setXRay`, `setOnesidedDiagnostic`, `setDoubleSided` and Task 9's `setErrorOverlay` (isolate) now
    loop over `this.surfaceMaterials()` instead of touching only `this.parts.facade.material`.
  - Picking (`setupPicking`) raycasts the visible surface and maps the slot back to the face number:

```ts
      const target = this.parts.textured?.visible ? this.parts.textured : this.parts.facade
      const hits = raycaster.intersectObject(target!)
      if (hits.length > 0 && hits[0].faceIndex !== undefined) {
        const slot = hits[0].faceIndex
        const faceId = target === this.parts.textured && this.faceOrder ? this.faceOrder[slot] : slot
        this.onPick(faceId, hits[0].point)
      }
```

  - In `clear()`: dispose each textured material's `map` too (`(m as any).map?.dispose()`), and reset
    `this.faceOrder = undefined`.

- [ ] **Step 6: The toggle.**
  - In `web/src/composables/useLayers.ts`, add `textures: boolean` to `LayerState`, `textures: true`
    to the defaults, and `u: 'textures'` to `HOTKEYS`. Update `useLayers.test.ts` where it lists the
    hotkeys or defaults, and run it.
  - In `WorkspaceView.vue`:
    - pass the version id: `viewA.loadModel(snap, snapshotVersion.value.id)` and
      `viewB.loadModel(fix, fixedVersion.value.id)`;
    - add a "Textures [U]" checkbox to the layer toolbar, copying the existing checkboxes' markup;
    - where the layers are applied to both views (about lines 482-496), add
      `viewA.setTextured(layers.textures)` and `viewB.setTextured(layers.textures)`.

- [ ] **Step 7: Type-check and run all web tests**

Run: `pnpm --dir web exec vue-tsc --noEmit` and `pnpm --dir web exec vitest run`
Expected: no new type errors; all tests pass.

- [ ] **Step 8: Commit**

```bash
git add web/src/utils/materialGroups.ts web/src/utils/materialGroups.test.ts web/src/three/Viewport.ts web/src/composables/useLayers.ts web/src/composables/useLayers.test.ts web/src/views/WorkspaceView.vue
git commit -m "feat(web): the 3D viewer shows the model's real textures, with a Textures toggle" -m "Textured, the export's coincident faces z-fight as they do in Unity, so the flicker is seen as it really is; the error filter's colours draw on top." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

Task 11's browser check adds:
- CHTM 5th floor shows its block textures;
- the diagonal wall at about (1893, 22949) visibly flickers as the camera moves;
- "Textures" off returns the grey shading.

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
