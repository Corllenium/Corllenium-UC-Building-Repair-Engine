"""Stray fragments and attached slivers: geometry that is not part of anything.

WHAT THIS IS FOR. A SketchUp export carries debris the rest of the pipeline cannot touch. The
hidden-face pass only ever removes what nobody can see, and a stray is usually plainly VISIBLE --
a triangle left where something was deleted, a scrap of a component that was moved away, a needle
too thin to be a surface. The merge cannot dissolve it either, because it is its own region.

So this step is different in kind from every other one here: it deletes geometry a person can
see, on the strength of a size argument, and its guard therefore has to be different too. The
removal runs under a FRAGMENT-mode guard (`engine.guard.compare.fragment_feedback`) whose only
permitted change is a pixel whose BEFORE first hit was one of these very faces. Any other failing
pixel a candidate was involved in -- one the BEFORE ray met in front of what AFTER now shows --
puts that candidate back.

TWO SHAPES OF DEBRIS, and they are found differently.

A FRAGMENT is a whole connected component -- components are taken over SHARED WELDED EDGES, so
two faces that merely touch at a vertex, or cross without sharing an edge, are separate. A
component is a candidate when any one of these holds:

  * its total area is below `FixProfile.fragment_max_area` (4 in^2), or
  * it is a single face, or
  * its longest bounding-box extent is below `FixProfile.fragment_max_extent` (6 in),

and NEVER when it contains a face bigger than `fragment_max_area` on its own. That last rule is
not a refinement, it is what makes the other three safe: a 5 x 4 in panel is under the extent
threshold on every axis, and a rule without it would delete a real panel for being small. A
component that survives all of this is reported with its size, so the thresholds can be argued
with against real numbers rather than asserted.

A SLIVER is a single face inside a component that is NOT a fragment candidate -- so, attached to
something real -- whose polygon quality `4 * pi * area / perimeter^2` is below
`FixProfile.sliver_q` (0.02) AND whose own area is at most `fragment_max_area`. That quality is 1
for a circle and about 0.6 for an equilateral triangle; 0.02 is a needle roughly 1:150. It is
reported separately from fragments because it is a different claim: a fragment is debris, a
sliver is a real surface's ragged edge.

THE AREA BOUND IS NOT AN EXTRA THRESHOLD, it is the same one the component rule already applies
("never a component holding a face bigger than `fragment_max_area` on its own"), and leaving it
off was a defect. The quality ratio is SCALE-FREE: a 630 x 4 in strip of real sidewalk scores
0.006, deeper into "needle" than a 1 in whisker, because it is long rather than because it is
thin. Measured on file A's solidified reference: 285 faces score under 0.02 and the largest of
them are 391 to 793 sq in -- surfaces nobody would call debris. And the fragment guard cannot
save them: it tolerates a candidate's OWN pixels by construction, which is what lets it delete
visible debris at all, so it would have removed a 793 sq in strip without a murmur. A detector
whose guard cannot second-guess it has to be the conservative one.

Deterministic: components are numbered in ascending face order, every loop is over a sorted list,
and no random number is drawn.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.topo.adjacency import build_edge_table, edge_face_lists

#: How many of the components the size rules did NOT catch are listed in the report, smallest
#: first. Bounded so `report.json` stays a fixed size on a model with thousands of components,
#: and smallest-first because those are the ones near the threshold.
_KEPT_REPORTED = 10


@dataclass
class FragmentResult:
    #: Bool over the faces handed in: this face's whole component is a fragment candidate.
    fragments: np.ndarray
    #: Bool over the faces handed in: an attached sliver candidate. Disjoint from `fragments` --
    #: a face in a fragment component is never also reported as a sliver.
    slivers: np.ndarray
    #: Per face, its connected-component id (always >= 0; every face is in some component).
    component: np.ndarray
    report: dict


def _components(face_w: np.ndarray) -> np.ndarray:
    """Connected components of `face_w` under SHARED WELDED EDGE adjacency, numbered from 0 in
    ascending order of their lowest face id -- so the numbering is a property of the mesh, not of
    the order a union-find happened to visit things in."""
    n = len(face_w)
    parent = np.arange(n)

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    if n:
        table = build_edge_table(face_w, np.ones(n, dtype=bool))
        for group in edge_face_lists(table):
            members = [int(f) for f in group]
            for f in members[1:]:
                parent[find(f)] = find(members[0])

    out = np.full(n, -1, np.int64)
    labels: dict[int, int] = {}
    for f in range(n):
        out[f] = labels.setdefault(find(f), len(labels))
    return out


def _face_area(positions_w: np.ndarray, face_w: np.ndarray) -> np.ndarray:
    tri = positions_w[face_w]
    return 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)


def _face_quality(positions_w: np.ndarray, face_w: np.ndarray) -> np.ndarray:
    """`4 * pi * area / perimeter**2` per face: 1 for a circle, ~0.6 for an equilateral triangle,
    towards 0 for a needle. A face with no perimeter at all (every vertex welded together) gets
    0.0, which is the honest answer -- it has no shape."""
    tri = positions_w[face_w]
    area = _face_area(positions_w, face_w)
    perimeter = np.linalg.norm(tri - np.roll(tri, -1, axis=1), axis=2).sum(axis=1)
    out = np.zeros(len(face_w), dtype=np.float64)
    good = perimeter > 0.0
    out[good] = 4.0 * np.pi * area[good] / perimeter[good] ** 2
    return out


def detect_fragments(positions_w: np.ndarray, face_w: np.ndarray, profile) -> FragmentResult:
    """Find every stray-fragment and attached-sliver candidate in `face_w` (welded triangles into
    `positions_w`). See the module docstring for both rules.

    `profile` is an `engine.fixes.pipeline.FixProfile`, duck-typed like every other consumer in
    `engine.fixes`, so this package imports nothing from it. Nothing is removed here: the caller
    puts the candidates through `engine.guard.compare.fragment_feedback` first."""
    positions_w = np.asarray(positions_w, dtype=np.float64)
    face_w = np.asarray(face_w, dtype=np.int64)
    max_area = float(getattr(profile, "fragment_max_area", 4.0))
    max_extent = float(getattr(profile, "fragment_max_extent", 6.0))
    min_q = float(getattr(profile, "sliver_q", 0.02))

    n = len(face_w)
    fragments = np.zeros(n, dtype=bool)
    slivers = np.zeros(n, dtype=bool)
    if not n:
        return FragmentResult(fragments, slivers, np.zeros(0, np.int64),
                              {"n_components": 0, "n_candidate_components": 0,
                               "n_above_threshold_components": 0, "n_fragment_faces": 0,
                               "n_sliver_faces": 0, "smallest_kept_components": []})

    component = _components(face_w)
    area = _face_area(positions_w, face_w)
    n_components = int(component.max()) + 1

    kept: list[dict] = []
    n_candidates = 0
    for c in range(n_components):
        members = np.nonzero(component == c)[0]
        total = float(area[members].sum())
        corners = positions_w[face_w[members]].reshape(-1, 3)
        extent = float((corners.max(axis=0) - corners.min(axis=0)).max())
        biggest = float(area[members].max())

        candidate = (biggest <= max_area
                     and (total < max_area or len(members) == 1 or extent < max_extent))
        if candidate:
            fragments[members] = True
            n_candidates += 1
        else:
            kept.append({"faces": int(len(members)), "area": round(total, 4),
                          "extent": round(extent, 4), "largest_face": round(biggest, 4)})

    # Slivers are looked for only OUTSIDE the fragment components: inside one the whole thing is
    # going anyway, and reporting the same face under two headings would double-count it. The
    # area bound is the module docstring's subject -- without it this catches long real strips.
    quality = _face_quality(positions_w, face_w)
    slivers[~fragments & (quality < min_q) & (area <= max_area)] = True

    kept.sort(key=lambda k: (k["area"], k["faces"], k["extent"]))
    report = {
        "n_components": n_components,
        "n_candidate_components": n_candidates,
        "n_above_threshold_components": n_components - n_candidates,
        "n_fragment_faces": int(fragments.sum()),
        "n_sliver_faces": int(slivers.sum()),
        #: The smallest components the size rules did NOT catch -- the evidence for where the
        #: thresholds sit relative to this model, and the first place to look if something real
        #: went missing or something stray survived.
        "smallest_kept_components": kept[:_KEPT_REPORTED],
    }
    return FragmentResult(fragments=fragments, slivers=slivers, component=component,
                          report=report)
