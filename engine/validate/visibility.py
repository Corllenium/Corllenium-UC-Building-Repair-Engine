"""What each viewpoint sees of the samples.

A viewpoint is a direction (a viewer infinitely far away, looking along `dir`), a camera or a
probe (a point). A sample is SEEN by a viewpoint when nothing stands between them, and the viewer
is on the FRONT of the sample's face when it is on the side the winding normal points to, on its
BACK otherwise. Unity draws both sides of every face (`_Cull = 0`), so a face is seen from either
side: the back of a wall is as visible as its front, and the Validator reports which it was.

How the test is made, and why:

* The ray starts `EPS_ORIGIN` off the sample, along the normal, on the VIEWER's side of the
  face. So it never meets its own face or a coplanar neighbour, whichever side the viewer is on;
  and a face lying closer than `EPS_ORIGIN` in front does not hide the sample (two layers that
  close z-fight in Unity: both are drawn).
* A direction needs the ray from the sample toward `-dir` to ESCAPE (`any_hit` is false). A camera
  or probe needs a CLEAR SEGMENT: the first hit along the ray to it is beyond it, or none
  (`first_hit`). Surfaces behind the viewpoint do not matter.
* A viewpoint exactly edge-on to a face (`|cos| <= MIN_COS`) sees nothing of it, and a face with no
  area has no normal and is never seen.

Written for the Validator and independent of the code it judges (see `engine.validate`): rays go
through `engine.rays.caster.EmbreeCaster` and nothing else of the engine.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.model import MeshData
from engine.rays.caster import EmbreeCaster
from engine.validate.sampling import Samples, check_frame, face_normals

#: How far, in inches, a sample's ray starts off its face. Large against the float32 spacing in the
#: Validator's frame (about 0.001 in at the limit, `sampling.MAX_FRAME_COORD`), small against any
#: layer anyone could see apart.
EPS_ORIGIN = 0.02
#: A viewpoint whose line to the sample is within this cosine of the face's plane is edge-on.
MIN_COS = 1e-6
#: A camera or probe closer than this to a sample is the sample.
_MIN_DIST = 1e-9
#: (sample, viewpoint) pairs cast in one block, which bounds the arrays.
_BATCH = 1 << 20


def build_caster(mesh: MeshData) -> EmbreeCaster:
    """The ray caster for `mesh`, which must already be in the Validator's frame
    (`sampling.recentred`): Embree stores float32, so a mesh sitting near 24,000 in is refused
    with a `ValueError` instead of being silently rounded. `first_hit`'s `tri` indexes
    `mesh.face_v`, degenerate faces included (they are never hit)."""
    check_frame(mesh.positions, "mesh positions")
    return EmbreeCaster(mesh.positions, mesh.face_v)


def check_caster(mesh: MeshData, caster) -> None:
    """Raise `ValueError` unless `caster` has one face per face of `mesh`: it was built from some
    other mesh, and its `first_hit` indices would mean nothing here."""
    if len(caster.faces) != mesh.n_faces:
        raise ValueError(f"the caster has {len(caster.faces)} faces but the mesh has {mesh.n_faces}: "
                         "build it from this mesh with build_caster")


@dataclass(frozen=True, eq=False)
class VisibleSet:
    """Which viewpoints see which samples. The columns are the viewpoints in the order they were
    given: the `dirs`, then the `cams`, then the `probes` (`dir_cols`, `cam_cols`, `probe_cols`).
    The arrays are `(N, D + C + P)` for `N` samples; the viewpoints themselves are kept so a later
    pass can cast the same lines into another mesh."""
    dirs: np.ndarray      #: (D, 3) unit look directions, as normalised from the ones given
    cams: np.ndarray      #: (C, 3) camera positions
    probes: np.ndarray    #: (P, 3) probe positions
    seen: np.ndarray      #: bool: the viewpoint sees the sample, from either side
    front: np.ndarray     #: bool: it sees the sample's FRONT (implies `seen`); `seen & ~front` is its back

    @property
    def dir_cols(self) -> slice:
        return slice(0, len(self.dirs))

    @property
    def cam_cols(self) -> slice:
        return slice(len(self.dirs), len(self.dirs) + len(self.cams))

    @property
    def probe_cols(self) -> slice:
        return slice(len(self.dirs) + len(self.cams), self.seen.shape[1])

    @property
    def visible(self) -> np.ndarray:
        """(N,) some viewpoint sees the sample."""
        return self.seen.any(axis=1)

    @property
    def front_seen(self) -> np.ndarray:
        """(N,) some viewpoint sees the sample's front."""
        return self.front.any(axis=1)

    @property
    def back_seen(self) -> np.ndarray:
        """(N,) some viewpoint sees the sample's back."""
        return (self.seen & ~self.front).any(axis=1)

    @property
    def seen_outside(self) -> np.ndarray:
        """(N,) some direction or camera sees the sample."""
        return self.seen[:, :len(self.dirs) + len(self.cams)].any(axis=1)

    @property
    def seen_inside(self) -> np.ndarray:
        """(N,) some probe sees the sample."""
        return self.seen[:, self.probe_cols].any(axis=1)


def _rows(a, what: str) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    if a.size % 3:
        raise ValueError(f"{what} must be rows of 3 numbers, got shape {a.shape}")
    return a.reshape(-1, 3)


def _side(cos: np.ndarray) -> np.ndarray:
    """Which way a sample's ray steps off its face: `+EPS_ORIGIN` along the normal for a viewer on
    the front, `-EPS_ORIGIN` for one on the back."""
    return np.where(cos > 0.0, EPS_ORIGIN, -EPS_ORIGIN)


def _seen_by_directions(caster, points: np.ndarray, normals: np.ndarray, toward: np.ndarray):
    """`(rows, cols, is_front)` of the (sample, direction) pairs that see each other. `toward` is
    (D, 3): the unit vector from a sample to the viewer, `-dir`. The ray must escape."""
    cos = normals @ toward.T
    rows, cols = np.nonzero(np.abs(cos) > MIN_COS)
    c = cos[rows, cols]
    origin = points[rows] + _side(c)[:, None] * normals[rows]
    escaped = ~caster.any_hit(origin, toward[cols])
    return rows[escaped], cols[escaped], c[escaped] > 0.0


def _seen_by_points(caster, points: np.ndarray, normals: np.ndarray, viewpoints: np.ndarray):
    """`(rows, cols, is_front)` of the (sample, camera or probe) pairs that see each other: the
    segment from the sample to the viewpoint is clear. A hit within `EPS_ORIGIN` of the viewpoint
    itself does not block it."""
    v = viewpoints[None, :, :] - points[:, None, :]
    dist = np.linalg.norm(v, axis=2)
    with np.errstate(divide="ignore", invalid="ignore"):
        cos = np.einsum("nk,nqk->nq", normals, v) / dist
    rows, cols = np.nonzero((dist > _MIN_DIST) & (np.abs(cos) > MIN_COS))
    c = cos[rows, cols]
    origin = points[rows] + _side(c)[:, None] * normals[rows]
    to = viewpoints[cols] - origin
    reach = np.linalg.norm(to, axis=1)
    tri, t = caster.first_hit(origin, to / np.maximum(reach, _MIN_DIST)[:, None])
    clear = (tri < 0) | (t >= reach - EPS_ORIGIN)
    return rows[clear], cols[clear], c[clear] > 0.0


def visible_samples(mesh: MeshData, samples: Samples, dirs, cams, probes, caster) -> VisibleSet:
    """What every viewpoint sees of every sample of `mesh`, and which side of the face it sees.

    `dirs` (D, 3) are view directions: the sample is seen when the ray from it toward `-dir`
    escapes. `cams` (C, 3) and `probes` (P, 3) are points: seen when the segment to the point is
    clear. Each may be empty. `caster` must be built from this very mesh, in the Validator's frame
    (`build_caster(mesh)`, once for any number of calls); anything with `any_hit` and `first_hit`
    over the same `faces` works, which is how the tests check it against a brute-force oracle.

    The rows go through in blocks, so the rays in flight are bounded; the result is the dense
    `(N, D + C + P)` pair of boolean matrices, so for a floor of hundreds of thousands of samples
    cast it in chunks of samples."""
    dirs = _rows(dirs, "dirs")
    length = np.linalg.norm(dirs, axis=1)
    if (length <= 0.0).any():
        raise ValueError("a view direction has zero length")
    dirs = dirs / length[:, None]
    cams, probes = _rows(cams, "cams"), _rows(probes, "probes")
    check_caster(mesh, caster)
    for what, points in (("sample points", samples.points), ("cameras", cams), ("probes", probes)):
        check_frame(points, what)

    n, nd, nc = len(samples), len(dirs), len(cams)
    seen = np.zeros((n, nd + nc + len(probes)), dtype=bool)
    front = np.zeros_like(seen)
    normals = face_normals(mesh)[samples.face]
    step = max(1, _BATCH // max(nd, nc, len(probes), 1))
    for r0 in range(0, n, step):
        block = slice(r0, min(r0 + step, n))
        p, nrm = samples.points[block], normals[block]
        found = []
        if nd:
            found.append((0, _seen_by_directions(caster, p, nrm, -dirs)))
        if nc:
            found.append((nd, _seen_by_points(caster, p, nrm, cams)))
        if len(probes):
            found.append((nd + nc, _seen_by_points(caster, p, nrm, probes)))
        for col0, (rows, cols, is_front) in found:
            seen[r0 + rows, col0 + cols] = True
            front[r0 + rows[is_front], col0 + cols[is_front]] = True
    return VisibleSet(dirs=dirs, cams=cams, probes=probes, seen=seen, front=front)
