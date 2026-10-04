"""Face samples for the Validator: where on a face to look, and what texture is there.

A sample is a point on a face with its barycentric weights. The lattice that places them is
deterministic (no randomness anywhere) and gives every sample of one face the same area, so a
count of samples is a measure of area: "40 % of the samples are visible" means 40 % of the face.

Written for the Validator and independent of the code it judges (see `engine.validate`).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from engine.model import MeshData

#: A face whose doubled area is below this fraction of its longest edge squared has no area worth
#: a normal: three points that are collinear up to float noise give a cross product of random
#: direction, and a visible face with a random normal would be nonsense. The noise on recentred
#: coordinates is about 1e-13 relative; a real sliver is thousands of times wider than this.
_NO_AREA = 1e-9


@dataclass(frozen=True)
class Samples:
    """Points on faces. Row `i` is the point `bary[i] @ corners(face[i])`."""
    points: np.ndarray   #: (N, 3) float64, on the faces, in the mesh's own frame
    face: np.ndarray     #: (N,) int64, index into `mesh.face_v`
    bary: np.ndarray     #: (N, 3) float64, weights of the face's corners 0, 1, 2; every row sums to 1

    def __len__(self) -> int:
        return int(self.face.shape[0])


def _cross_and_longest_edge2(mesh: MeshData, ids: np.ndarray | None = None):
    """`cross(b - a, c - a)` per face (twice the area's vector) and the longest edge squared."""
    fv = mesh.face_v if ids is None else mesh.face_v[ids]
    P = mesh.positions
    a, b, c = P[fv[:, 0]], P[fv[:, 1]], P[fv[:, 2]]
    ab, ac, bc = b - a, c - a, c - b
    longest2 = np.maximum(np.maximum((ab * ab).sum(axis=1), (ac * ac).sum(axis=1)),
                          (bc * bc).sum(axis=1))
    return np.cross(ab, ac), longest2


def face_areas(mesh: MeshData) -> np.ndarray:
    """(F,) float64 area of every face."""
    cross, _ = _cross_and_longest_edge2(mesh)
    return 0.5 * np.linalg.norm(cross, axis=1)


def face_normals(mesh: MeshData) -> np.ndarray:
    """(F, 3) float64 unit normal of every face from its winding, `cross(b - a, c - a)`; the zero
    vector for a face with no area. The Validator ignores the OBJ's `vn`: a face is front-facing
    to whoever sees it counter-clockwise."""
    cross, longest2 = _cross_and_longest_edge2(mesh)
    length = np.linalg.norm(cross, axis=1)
    normals = np.zeros_like(cross)
    good = length > _NO_AREA * longest2
    normals[good] = cross[good] / length[good, None]
    return normals


@lru_cache(maxsize=None)
def _lattice(n: int) -> np.ndarray:
    """(n * n, 3) barycentric weights of the centres of the n * n congruent cells that cut a
    triangle by lines parallel to its sides, `n` to a side: n (n + 1) / 2 cells pointing the same
    way as the triangle, then n (n - 1) / 2 pointing the other way. Every cell has the same area
    (a nth squared of the triangle's), and every centre has all three weights above zero, so a
    sample is never on an edge. Read-only: the array is cached."""
    i, j = np.nonzero(np.add.outer(np.arange(n), np.arange(n)) <= n - 1)           # same way up
    k, m = np.nonzero(np.add.outer(np.arange(n), np.arange(n)) <= n - 2)           # the other way
    b = np.concatenate([(3 * i + 1) / (3.0 * n), (3 * k + 2) / (3.0 * n)])
    c = np.concatenate([(3 * j + 1) / (3.0 * n), (3 * m + 2) / (3.0 * n)])
    lattice = np.stack([1.0 - b - c, b, c], axis=1)
    lattice.setflags(write=False)
    return lattice


def face_samples(mesh: MeshData, faces=None, min_per_face: int = 4,
                 area_per_sample: float = 36.0) -> Samples:
    """Samples on `faces` (all of them by default; an index array in the order wanted, or a
    boolean mask): at least `min_per_face` on every face and about one per `area_per_sample` sq
    in, as the smallest `n * n` lattice (see `_lattice`) that reaches that count. So a 10 in
    triangle gets 4 and a 120 in one gets 225.

    Faces with no area still get their samples (all on the degenerate triangle), so the count per
    face is uniform; they have no normal and the visibility pass never sees them.

    Rows come in the order of `faces`, each face's samples in lattice order."""
    if not area_per_sample > 0.0:
        raise ValueError(f"area_per_sample must be positive, got {area_per_sample!r}")
    if faces is None:
        ids = np.arange(mesh.n_faces, dtype=np.int64)
    else:
        faces = np.asarray(faces)
        if faces.dtype == np.bool_:
            if faces.shape != (mesh.n_faces,):
                raise ValueError("a boolean `faces` mask needs one entry per face")
            ids = np.flatnonzero(faces).astype(np.int64)
        else:
            ids = faces.astype(np.int64).reshape(-1)

    cross, _ = _cross_and_longest_edge2(mesh, ids)
    area = 0.5 * np.linalg.norm(cross, axis=1)
    wanted = np.maximum(int(min_per_face), np.ceil(area / area_per_sample)).astype(np.int64)
    order = np.ceil(np.sqrt(wanted)).astype(np.int64)                  # lattice size, n * n samples
    counts = order * order
    starts = np.cumsum(counts) - counts

    face = np.repeat(ids, counts)
    bary = np.empty((int(counts.sum()), 3), dtype=np.float64)
    for n in np.unique(order):                                          # ascending: deterministic
        if n == 0:
            continue
        which = np.flatnonzero(order == n)
        at = (starts[which][:, None] + np.arange(n * n)[None, :]).reshape(-1)
        bary[at] = np.tile(_lattice(int(n)), (len(which), 1))

    P, fv = mesh.positions, mesh.face_v[face]
    points = (bary[:, 0, None] * P[fv[:, 0]] + bary[:, 1, None] * P[fv[:, 1]]
              + bary[:, 2, None] * P[fv[:, 2]])
    return Samples(points=points, face=face, bary=bary)


def uv_at(mesh: MeshData, face: np.ndarray, bary: np.ndarray) -> np.ndarray:
    """(N, 2) float64 texture coordinate at barycentric weights `bary` (N, 3) of faces `face` (N,),
    interpolated from `uvs[face_vt]`. NaN for a face with no texture coordinates (the OBJ reader
    marks them -1, which a bare index would turn into the LAST uv). The result is NOT reduced mod
    1: whether the texture repeats is the caller's question."""
    face = np.asarray(face, dtype=np.int64).reshape(-1)
    bary = np.asarray(bary, dtype=np.float64).reshape(-1, 3)
    vt = mesh.face_vt[face]
    has_uv = (vt >= 0).all(axis=1) & (vt < len(mesh.uvs)).all(axis=1)
    uv = np.full((len(face), 2), np.nan, dtype=np.float64)
    if has_uv.any():
        uv[has_uv] = np.einsum("nk,nkc->nc", bary[has_uv], mesh.uvs[vt[has_uv]])
    return uv


def bbox_centre(mesh: MeshData) -> np.ndarray:
    """(3,) centre of the bounding box of the vertices some face uses (a stray vertex nobody
    uses does not move it)."""
    used = np.zeros(len(mesh.positions), dtype=bool)
    used[mesh.face_v.reshape(-1)] = True
    P = mesh.positions[used] if used.any() else mesh.positions
    if not len(P):
        return np.zeros(3)
    return (P.min(axis=0) + P.max(axis=0)) / 2.0


def recentred(mesh: MeshData, centre: np.ndarray | None = None) -> tuple[MeshData, np.ndarray]:
    """`(mesh shifted so `centre` is the origin, centre)`; the bounding-box centre by default.
    Only `positions` changes (every other array is shared, not copied). Embree stores float32,
    and the real models sit near 24,000 in, so the Validator casts rays only in this frame.

    Put BEFORE and AFTER in ONE frame: recentre BEFORE, then pass its `centre` back for AFTER."""
    c = bbox_centre(mesh) if centre is None else np.asarray(centre, dtype=np.float64).reshape(3)
    return dataclasses.replace(mesh, positions=mesh.positions - c), c
