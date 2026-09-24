"""Folds: two faces sharing an edge, folded onto the same side of it in one plane.

WHAT A FOLD IS. Two triangles that share one edge normally lie on OPPOSITE sides of it -- the
surface continues across the edge. When both lie on the SAME side, in one plane, the surface has
folded back over itself there: the area next to the edge is covered twice. File B carries one at
the top of a ramp's side wall (faces 5750 and 5751, two needles 86 and 129 in long at
x = 2948.84), which SketchUp draws as two lines inside the surface, 85.9 and 43.0 in; and its
merge region 79 is two original triangles folded over their shared edge, 47.7 sq in covered twice
(OBJ lines 10834 and 11402). Folds come wound both ways: 5750 and 5751 face opposite ways (the
surface turned back on itself), region 79's pair the same way. Measured on the solidified
references after the hidden pass: 43 folds on file A and 31 on file B.

WHICH MEMBER MAY GO is not decided here, and not by the fold alone: `engine.fixes.pipeline` asks
the rays through each member (`engine.guard.piece_rays.judge_alone`) whether the rest of the model
still covers it exactly -- every line along which it was seen, with it gone, meets a face level
with it -- and proposes one member that is (the smaller, then the higher face id). "Lies within
the other" is not the test, and file B's own fold shows why: 5750 lies within 5751 but for a
sliver 0.0018 in wide, and that sliver is all that closes the top of the wall under the ramp's
edge; 5751 does not lie within 5750, yet 5750 and the wall face 5753 cover all of it between them.
When neither member is covered by the rest, each covers area nothing else does: removing either
would uncover it, and resolving the fold would need a vertex where their edges cross, which
nothing here may invent. That fold is left, and reported.

WHAT IS NEVER PROPOSED, and is reported with the reason instead: a fold between two materials
(which colour a person wants is not a question geometry can answer -- the duplicate-layer rule of
`engine.fixes.overlap`), and a fold holding a face `protected` marks (one solidify invented:
whether it should lie over an original face is the cap guard's question). Two copies of one
triangle share all three edges: that is a duplicate layer, `engine.fixes.overlap`'s to remove,
counted here and never a fold.

Nothing is removed here. Deterministic: edges in the edge table's order, pairs in ascending face
order, no randomness.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely

from engine.topo.adjacency import build_edge_table, edge_face_lists


@dataclass
class FoldResult:
    #: One entry per fold, in ascending order of its faces: `{"faces": [f, g]` (f < g), `"edge":
    #: [u, v]` (the shared edge's vertices), `"overlap_area"` (sq in covered twice), `"reason"`
    #: (why neither member may be proposed -- "different materials" or "protected" -- or `None`)
    #: `}`. Face and vertex ids index what was handed in.
    folds: list
    report: dict


def _unit(v: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(v))
    return v / length if length > 0.0 else v * 0.0


def detect_folds(positions_w: np.ndarray, face_w: np.ndarray, face_material: np.ndarray, *,
                 contact_tol: float, protected: np.ndarray | None = None) -> FoldResult:
    """Every fold in `face_w` (welded triangles into `positions_w`, with `face_material`): two
    faces with three distinct corners each, sharing exactly one edge, both with area, each one's
    third corner within `contact_tol` of the other's plane (one plane: the T-junction tolerance
    `engine.detectors.fragments` calls coplanar contact with), and both third corners on the same
    side of the shared edge. `protected` (bool over the faces, `None` protects nothing) marks the
    faces solidify invented. See the module docstring for what happens to a fold next."""
    positions_w = np.asarray(positions_w, dtype=np.float64)
    face_w = np.asarray(face_w, dtype=np.int64)
    material = np.asarray(face_material)
    n = len(face_w)
    protected = (np.zeros(n, dtype=bool) if protected is None
                 else np.asarray(protected, dtype=bool).reshape(n))
    folds: list[dict] = []
    n_duplicates = 0
    if n:
        tri = positions_w[face_w]
        area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
        table = build_edge_table(face_w, np.ones(n, dtype=bool))
        corner_sets = [frozenset(f) for f in face_w.tolist()]
        for (u, v), group in zip(table.edges.tolist(), edge_face_lists(table)):
            members = sorted(int(f) for f in group)
            for i, f in enumerate(members):
                for g in members[i + 1:]:
                    if len(corner_sets[f]) < 3 or len(corner_sets[g]) < 3:
                        continue                    # a repeated corner: no triangle at all
                    if corner_sets[f] == corner_sets[g]:
                        n_duplicates += 1           # counted once per shared edge: see below
                        continue
                    if area[f] <= 0.0 or area[g] <= 0.0:
                        continue
                    overlap = _folded(positions_w, face_w, f, g, u, v, contact_tol)
                    if overlap is None:
                        continue
                    reason = ("different materials" if material[f] != material[g]
                              else "protected" if protected[f] or protected[g] else None)
                    folds.append({"faces": [f, g], "edge": sorted([u, v]),
                                  "overlap_area": round(overlap, 4), "reason": reason})
        n_duplicates //= 3                          # a copy shares all three of its edges
    folds.sort(key=lambda d: tuple(d["faces"]))
    report = {"contact_tol": float(contact_tol), "n_folds": len(folds),
              "n_never_proposed": sum(d["reason"] is not None for d in folds),
              "n_duplicate_pairs": n_duplicates}
    return FoldResult(folds=folds, report=report)


def _folded(positions_w, face_w, f: int, g: int, u: int, v: int, contact_tol: float) -> float | None:
    """The area `f` and `g` cover twice when they are folded across their shared edge `u`-`v` --
    in one plane, on the same side of it -- or `None` when they are not."""
    pu, pv = positions_w[u], positions_w[v]
    cf = positions_w[[x for x in face_w[f].tolist() if x not in (u, v)][0]]
    cg = positions_w[[x for x in face_w[g].tolist() if x not in (u, v)][0]]
    along = _unit(pv - pu)
    off_f = (cf - pu) - float((cf - pu) @ along) * along       # each apex, square off the edge
    off_g = (cg - pu) - float((cg - pu) @ along) * along
    if float(off_f @ off_g) <= 0.0:
        return None                                            # opposite sides: no fold
    normal_f = _unit(np.cross(along, off_f))
    normal_g = _unit(np.cross(along, off_g))
    if abs(float((cg - pu) @ normal_f)) > contact_tol or abs(float((cf - pu) @ normal_g)) > contact_tol:
        return None                                            # not one plane
    across = _unit(off_f)

    def flat(points):
        rel = np.asarray(points, dtype=np.float64) - pu
        return np.stack([rel @ along, rel @ across], axis=-1)

    return float(shapely.area(shapely.intersection(shapely.Polygon(flat(positions_w[face_w[f]])),
                                                   shapely.Polygon(flat(positions_w[face_w[g]])))))
