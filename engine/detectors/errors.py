"""What is wrong with a model, face by face, without changing it (spec 2026-09-26, the 3D error
filter). Every answer comes from a detector the fix pipeline already trusts; this module only
gathers them.

Face numbers are `mesh`'s own, which the meshbuf also uses (`tri_face_id = arange`), so the
viewer colours face `f` by looking it up here. Points and lines are world inches; the viewer
subtracts the meshbuf's `origin_offset`.

"Zero-area and stray bits" (`loose`) is the zero-area faces plus the stray-fragment and
attached-sliver CANDIDATES `engine.detectors.fragments.detect_fragments` names, at the tolerances
`engine.fixes.pipeline.fix_object` gives it; `loose_parts` counts each. They are candidates, not
verdicts: the pipeline also passes every one through `engine.guard.compare.fragment_feedback`
(and the rays through it) before removing any, and puts back those whose removal would show
something it must not.
"""
from __future__ import annotations

import numpy as np

from engine.detectors.fragments import detect_fragments
from engine.fixes.orient import ORIENT_FLIP, classify_orientation
from engine.fixes.overlap import double_layers
from engine.fixes.pipeline import FixProfile, guard_depth_tol, sliver_width_bound
from engine.guard.views import VIEWS_26
from engine.model import MeshData
from engine.pipeline import analyse_topology
from engine.topo.edges import EDGE_OPEN
from engine.vis.exposure import EXP_HIDDEN, EXP_OUTSIDE, classify_exposure, compute_side_exposure

#: The file's schema version, written as its `"version"`. Bumped whenever what the file MEANS
#: changes, and the API serves no file of another version (review M2): 2 since the facade layer
#: (Task 14), T-junction edges no longer read as open (Task 15) and `loose` holding the fragment
#: and sliver candidates (review I4).
ERRORS_VERSION = 2

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
    exposure_class = classify_exposure(front + back, ok, profile.slit_threshold)
    hidden = np.nonzero((exposure_class == EXP_HIDDEN) & ok)[0]
    facade = np.nonzero((exposure_class == EXP_OUTSIDE) & ok)[0]
    reversed_ = np.nonzero((classify_orientation(front, back, ok) == ORIENT_FLIP) & ok)[0]

    # loose: the zero-area faces, and the stray-fragment and sliver candidates among the rest, at
    # the tolerances fix_object uses (contact within its T-junction tolerance, no sliver wider
    # than the merge's own border tolerance)
    ok_ids = np.nonzero(ok)[0]
    fr = detect_fragments(positions_c, faces[ok_ids], profile,
                          contact_tol=1.5 * float(topo.quanta.max()),
                          max_width=sliver_width_bound(topo.quanta, profile))
    zero_area = np.nonzero(~ok)[0]
    loose = np.union1d(zero_area, ok_ids[fr.fragments | fr.slivers])
    loose_parts = {"zero_area": int(len(zero_area)), "fragments": int(fr.fragments.sum()),
                   "slivers": int(fr.slivers.sum())}

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
    open_rows = np.nonzero(np.asarray(topo.edge_class) == EDGE_OPEN)[0]
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
    spots["facade"] = _face_group_spots("facade", pos, faces, facade, topo.face_region, area)
    spots["open_edges"] = [_spot(f"open edge {lengths[k]:.1f} in", open_edges[k].reshape(2, 3),
                                 lengths[k], []) for k in open_order.tolist()]
    spots["cracks"] = [_spot("T-junction point", cracks[k:k + 1], 0.0, [])
                       for k in range(min(SPOTS_PER_KIND, len(cracks)))]

    counts = {k: len(face_lists[k]) for k in face_lists}
    counts["open_edges"] = int(len(open_edges))
    counts["cracks"] = int(len(cracks))
    return {"version": ERRORS_VERSION, "n_faces": int(mesh.n_faces),
            "counts": {k: counts[k] for k in KINDS},
            "loose_parts": loose_parts,
            "faces": {k: [int(f) for f in face_lists[k]] for k in face_lists},
            "layers": {"facade": [int(f) for f in facade]},
            "layer_counts": {"facade": int(len(facade))},
            "open_edges": [[round(float(v), 3) for v in row] for row in open_edges],
            "cracks": [[round(float(v), 3) for v in row] for row in cracks],
            "flicker_pairs": dl["pair_list"],
            "spots": spots}
