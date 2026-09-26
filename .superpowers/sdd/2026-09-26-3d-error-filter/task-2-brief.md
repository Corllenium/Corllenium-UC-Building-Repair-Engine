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

