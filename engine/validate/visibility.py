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

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from engine.model import MeshData
from engine.rays.caster import EmbreeCaster
from engine.validate.sampling import Samples, _lattice, check_frame, face_normals

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


#: A batch of at least this many rays is split over threads (job P2-V2: the floor's dense lattice and pixel renders).
THREAD_MIN_RAYS = 1 << 16
_POOL = None


def _pool():
    global _POOL
    if _POOL is None:
        _POOL = ThreadPoolExecutor(max_workers=max(1, min(16, os.cpu_count() or 1)), thread_name_prefix="validator-cast")
    return _POOL


class ThreadedCaster:
    """An `EmbreeCaster` whose big batches (`THREAD_MIN_RAYS` rays or more) are cast in slices on a thread pool.
    Embree answers each ray on its own and releases the interpreter while it casts, so the answers are exactly the
    one-thread answers (`tri`, `t`, `any_hit`), only sooner. `faces` and `all_hits` are the wrapped caster's."""

    def __init__(self, caster: EmbreeCaster):
        self._caster = caster
        self.faces = caster.faces
        self.threads = _pool()._max_workers
        if len(self.faces):                       # trimesh fills its caches on the first cast: do it on one thread
            caster.first_hit(np.zeros((1, 3)), np.array([[0.0, 0.0, 1.0]]))
        rmi = getattr(caster, "_rmi", None)
        if len(self.faces) and rmi is not None:
            self._wrap = rmi._scene
            self._po = np.ascontiguousarray(rmi.mesh.triangles[:, 0, :], dtype=np.float64)
            self._pn = np.ascontiguousarray(rmi.mesh.face_normals, dtype=np.float64)
            self._pd_tri = np.ascontiguousarray(np.einsum("ij,ij->i", self._po, self._pn), dtype=np.float64)
        else:
            self._wrap = None

    def _split(self, fn, origins, directions):
        origins, directions = np.asarray(origins, dtype=np.float64), np.asarray(directions, dtype=np.float64)
        n = len(origins)
        if n < THREAD_MIN_RAYS or self.threads <= 1:
            return fn(origins, directions)
        parts = np.array_split(np.arange(n), min(self.threads, -(-n // (THREAD_MIN_RAYS // 4))))
        return list(_pool().map(lambda p: fn(origins[p[0]:p[-1] + 1], directions[p[0]:p[-1] + 1]), parts))

    def any_hit(self, origins, directions) -> np.ndarray:
        if self._wrap is None:
            out = self._split(self._caster.any_hit, origins, directions)
            return np.concatenate(out) if isinstance(out, list) else out
        origins = np.asarray(origins, dtype=np.float64)
        directions = np.asarray(directions, dtype=np.float64)
        n = len(origins)
        if not n:
            return np.zeros(0, dtype=np.bool_)
        wrap = self._wrap
        w_origin, w_scale, scene = wrap.origin, float(wrap.scale), wrap.scene

        def _any_slice(s: slice) -> np.ndarray:
            o, d = origins[s], directions[s]
            norm_d = np.sqrt(np.einsum("ij,ij->i", d, d))
            ud = (d / np.maximum(norm_d, 1e-12)[:, None]).astype(np.float32)
            sc_o = ((o - w_origin) * w_scale).astype(np.float32)
            return np.asarray(scene.run(sc_o, ud) != -1, dtype=np.bool_)

        if n < THREAD_MIN_RAYS or self.threads <= 1:
            return _any_slice(slice(0, n))
        parts = np.array_split(np.arange(n), min(self.threads, -(-n // (THREAD_MIN_RAYS // 4))))
        slices = [slice(int(p[0]), int(p[-1]) + 1) for p in parts if len(p)]
        return np.concatenate(list(_pool().map(_any_slice, slices)))

    def first_hit(self, origins, directions) -> tuple[np.ndarray, np.ndarray]:
        if self._wrap is None:
            out = self._split(self._caster.first_hit, origins, directions)
            if isinstance(out, list):
                return np.concatenate([o[0] for o in out]), np.concatenate([o[1] for o in out])
            return out
        origins = np.asarray(origins, dtype=np.float64)
        directions = np.asarray(directions, dtype=np.float64)
        n = len(origins)
        if not n:
            return np.full(0, -1, dtype=np.int64), np.full(0, np.inf, dtype=np.float64)
        wrap = self._wrap
        w_origin, w_scale, scene = wrap.origin, float(wrap.scale), wrap.scene
        pn, pd_tri = self._pn, self._pd_tri

        def _first_slice(s: slice) -> tuple[np.ndarray, np.ndarray]:
            o, d = origins[s], directions[s]
            m = len(o)
            tri_s = np.full(m, -1, dtype=np.int64)
            t_s = np.full(m, np.inf, dtype=np.float64)
            norm_d = np.sqrt(np.einsum("ij,ij->i", d, d))
            ud = d / np.maximum(norm_d, 1e-12)[:, None]
            sc_o = ((o - w_origin) * w_scale).astype(np.float32)
            q = scene.run(sc_o, ud.astype(np.float32))
            hit = np.flatnonzero(q != -1)
            if len(hit):
                ht = q[hit].astype(np.int64)
                proj_ori = pd_tri[ht] - np.einsum("ij,ij->i", o[hit], pn[ht])
                proj_dir = np.einsum("ij,ij->i", ud[hit], pn[ht])
                valid = np.abs(proj_dir) > 1e-5
                ok_r = hit[valid]
                ok_t = ht[valid]
                dist = proj_ori[valid] / proj_dir[valid]
                tri_s[ok_r] = ok_t
                t_s[ok_r] = dist * norm_d[ok_r]
            return tri_s, t_s

        if n < THREAD_MIN_RAYS or self.threads <= 1:
            return _first_slice(slice(0, n))
        parts = np.array_split(np.arange(n), min(self.threads, -(-n // (THREAD_MIN_RAYS // 4))))
        slices = [slice(int(p[0]), int(p[-1]) + 1) for p in parts if len(p)]
        res = list(_pool().map(_first_slice, slices))
        return np.concatenate([r[0] for r in res]), np.concatenate([r[1] for r in res])

    def all_hits(self, origins, directions):
        return self._caster.all_hits(origins, directions)


def build_caster(mesh: MeshData) -> ThreadedCaster:
    """The ray caster for `mesh`, which must already be in the Validator's frame
    (`sampling.recentred`): Embree stores float32, so a mesh sitting near 24,000 in is refused
    with a `ValueError` instead of being silently rounded. `first_hit`'s `tri` indexes
    `mesh.face_v`, degenerate faces included (they are never hit). Big batches go on threads
    (`ThreadedCaster`), with the answers of one thread."""
    check_frame(mesh.positions, "mesh positions")
    return ThreadedCaster(EmbreeCaster(mesh.positions, mesh.face_v))


def check_caster(mesh: MeshData, caster) -> None:
    """Raise `ValueError` unless `caster` was built from the faces of `mesh`: as many of them, with
    the same vertex indices in the same order. Otherwise it came from some other mesh, and its
    `first_hit` indices would mean nothing here. (The vertex POSITIONS cannot be compared: a caster
    does not give them back, so one built from the same faces over moved vertices is not caught.)"""
    if len(caster.faces) != mesh.n_faces:
        raise ValueError(f"the caster has {len(caster.faces)} faces but the mesh has {mesh.n_faces}: "
                         "build it from this mesh with build_caster")
    if not np.array_equal(caster.faces, mesh.face_v):
        raise ValueError("the caster has as many faces as the mesh but not the same ones (other vertex "
                         "indices or another order): build it from this mesh with build_caster")


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
    """`a` as (k, 3) float64. Only that shape, or nothing at all (an empty list or array, which
    means k = 0), is accepted: an array of six numbers is not reshaped into two points."""
    a = np.asarray(a, dtype=np.float64)
    if a.size == 0 and a.ndim <= 1:
        return np.zeros((0, 3))
    if a.ndim != 2 or a.shape[1] != 3:
        raise ValueError(f"{what} must be rows of 3 numbers, shape (k, 3), got shape {a.shape}")
    return a


def _side(cos: np.ndarray) -> np.ndarray:
    """Which way a sample's ray steps off its face: `+EPS_ORIGIN` along the normal for a viewer on
    the front, `-EPS_ORIGIN` for one on the back."""
    return np.where(cos > 0.0, EPS_ORIGIN, -EPS_ORIGIN)


def _seen_by_directions(caster, points: np.ndarray, normals: np.ndarray, toward: np.ndarray):
    """`(rows, cols, is_front)` of the (sample, direction) pairs that see each other. `toward` is
    (D, 3): the unit vector from a sample to the viewer, `-dir`. The ray must escape."""
    wrap = getattr(caster, "_wrap", None)
    n_pts, n_dirs = len(points), len(toward)
    if wrap is None or n_pts * n_dirs < THREAD_MIN_RAYS or getattr(caster, "threads", 1) <= 1:
        cos = normals @ toward.T
        rows, cols = np.nonzero(np.abs(cos) > MIN_COS)
        c = cos[rows, cols]
        origin = points[rows] + _side(c)[:, None] * normals[rows]
        escaped = ~caster.any_hit(origin, toward[cols])
        return rows[escaped], cols[escaped], c[escaped] > 0.0

    w_origin, w_scale, scene = wrap.origin, float(wrap.scale), wrap.scene
    tw_f32 = np.ascontiguousarray(toward, dtype=np.float32)

    def _dir_worker(s: slice):
        loc_r, loc_c, loc_f = [], [], []
        for i0 in range(s.start, s.stop, 256):
            i1 = min(i0 + 256, s.stop)
            p_sub, n_sub = points[i0:i1], normals[i0:i1]
            cos = n_sub @ toward.T
            rp, cd = np.nonzero(np.abs(cos) > MIN_COS)
            if not len(rp):
                continue
            c = cos[rp, cd]
            is_fr = c > 0.0
            orig = p_sub[rp] + np.where(is_fr, EPS_ORIGIN, -EPS_ORIGIN)[:, None] * n_sub[rp]
            sc_o = ((orig - w_origin) * w_scale).astype(np.float32)
            hit = scene.run(sc_o, tw_f32[cd])
            esc = np.flatnonzero(hit == -1)
            if len(esc):
                loc_r.append(i0 + rp[esc])
                loc_c.append(cd[esc])
                loc_f.append(is_fr[esc])
        if not loc_r:
            return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, bool)
        return np.concatenate(loc_r), np.concatenate(loc_c), np.concatenate(loc_f)

    parts = np.array_split(np.arange(n_pts), min(max(1, -(-n_pts // 64)), caster.threads * 2))
    slices = [slice(int(p[0]), int(p[-1]) + 1) for p in parts if len(p)]
    res = list(_pool().map(_dir_worker, slices))
    return (np.concatenate([x[0] for x in res]),
            np.concatenate([x[1] for x in res]),
            np.concatenate([x[2] for x in res]))


def _seen_by_points(caster, points: np.ndarray, normals: np.ndarray, viewpoints: np.ndarray):
    """`(rows, cols, is_front)` of the (sample, camera or probe) pairs that see each other: the
    segment from the sample to the viewpoint is clear. A hit within `EPS_ORIGIN` of the viewpoint
    itself does not block it."""
    wrap = getattr(caster, "_wrap", None)
    n_pts, n_vp = len(points), len(viewpoints)
    if wrap is None or n_pts * n_vp < THREAD_MIN_RAYS or getattr(caster, "threads", 1) <= 1:
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

    w_origin, w_scale, scene = wrap.origin, float(wrap.scale), wrap.scene
    pn, pd_tri = caster._pn, caster._pd_tri

    def _pt_worker(s: slice):
        loc_r, loc_c, loc_f = [], [], []
        for i0 in range(s.start, s.stop, 256):
            i1 = min(i0 + 256, s.stop)
            p_sub, n_sub = points[i0:i1], normals[i0:i1]
            v = viewpoints[None, :, :] - p_sub[:, None, :]
            dist2 = np.einsum("nqk,nqk->nq", v, v)
            dot = np.einsum("nk,nqk->nq", n_sub, v)
            rp, cv = np.nonzero((dist2 > _MIN_DIST * _MIN_DIST) & (dot * dot > (MIN_COS * MIN_COS) * dist2))
            if not len(rp):
                continue
            d_val = dot[rp, cv]
            is_fr = d_val > 0.0
            orig = p_sub[rp] + np.where(is_fr, EPS_ORIGIN, -EPS_ORIGIN)[:, None] * n_sub[rp]
            to = viewpoints[cv] - orig
            reach = np.sqrt(np.einsum("ij,ij->i", to, to))
            ud = to / np.maximum(reach, _MIN_DIST)[:, None]
            sc_o = ((orig - w_origin) * w_scale).astype(np.float32)
            q = scene.run(sc_o, ud.astype(np.float32))
            miss = q == -1
            hit_idx = np.flatnonzero(~miss)
            if len(hit_idx):
                ht = q[hit_idx].astype(np.int64)
                proj_dir = np.einsum("ij,ij->i", ud[hit_idx], pn[ht])
                valid = np.abs(proj_dir) > 1e-5
                miss[hit_idx[~valid]] = True
                v_idx = hit_idx[valid]
                if len(v_idx):
                    ht_v = ht[valid]
                    proj_ori = pd_tri[ht_v] - np.einsum("ij,ij->i", orig[v_idx], pn[ht_v])
                    t_v = proj_ori / proj_dir[valid]
                    miss[v_idx[t_v >= reach[v_idx] - EPS_ORIGIN]] = True
            clr = np.flatnonzero(miss)
            if len(clr):
                loc_r.append(i0 + rp[clr])
                loc_c.append(cv[clr])
                loc_f.append(is_fr[clr])
        if not loc_r:
            return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, bool)
        return np.concatenate(loc_r), np.concatenate(loc_c), np.concatenate(loc_f)

    parts = np.array_split(np.arange(n_pts), min(max(1, -(-n_pts // 64)), caster.threads * 2))
    slices = [slice(int(p[0]), int(p[-1]) + 1) for p in parts if len(p)]
    res = list(_pool().map(_pt_worker, slices))
    return (np.concatenate([x[0] for x in res]),
            np.concatenate([x[1] for x in res]),
            np.concatenate([x[2] for x in res]))


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


_SUB4_MATS = np.array([
    [[1.0, 0.0, 0.0], [0.5, 0.5, 0.0], [0.5, 0.0, 0.5]],
    [[0.5, 0.5, 0.0], [0.0, 1.0, 0.0], [0.0, 0.5, 0.5]],
    [[0.5, 0.0, 0.5], [0.0, 0.5, 0.5], [0.0, 0.0, 1.0]],
    [[0.0, 0.5, 0.5], [0.5, 0.0, 0.5], [0.5, 0.5, 0.0]],
], dtype=np.float64)


@lru_cache(maxsize=None)
def _lattice_c64_ids(n: int) -> np.ndarray:
    """For `_lattice(n)` (n*n, 3), return the 64th-triangle cell index `0..63` (`(q * 4 + s) * 4 + t`) of each point."""
    b = _lattice(n)

    def _step(coords):
        idx = np.full(len(coords), 3, dtype=np.int64)
        idx[coords[:, 0] > 0.5] = 0
        idx[coords[:, 1] > 0.5] = 1
        idx[coords[:, 2] > 0.5] = 2
        loc = np.empty_like(coords)
        m0, m1, m2, m3 = idx == 0, idx == 1, idx == 2, idx == 3
        loc[m0] = np.stack([2 * coords[m0, 0] - 1, 2 * coords[m0, 1], 2 * coords[m0, 2]], axis=1)
        loc[m1] = np.stack([2 * coords[m1, 0], 2 * coords[m1, 1] - 1, 2 * coords[m1, 2]], axis=1)
        loc[m2] = np.stack([2 * coords[m2, 0], 2 * coords[m2, 1], 2 * coords[m2, 2] - 1], axis=1)
        loc[m3] = np.stack([1 - 2 * coords[m3, 0], 1 - 2 * coords[m3, 1], 1 - 2 * coords[m3, 2]], axis=1)
        return idx, loc

    q, loc1 = _step(b)
    s, loc2 = _step(loc1)
    t, _ = _step(loc2)
    return (q * 4 + s) * 4 + t


def snapped_point_keys(face: np.ndarray, points: np.ndarray, step: float) -> np.ndarray:
    """1D void-32 keys of `(face_id, round(x / step), round(y / step), round(z / step))` for sample-lattice reuse."""
    if not len(face) or not step > 0.0:
        return np.zeros(0, dtype=np.dtype((np.void, 32)))
    ijk = np.rint(points / step).astype(np.int64)
    rows = np.ascontiguousarray(np.column_stack([np.asarray(face, dtype=np.int64), ijk]))
    return rows.view(np.dtype((np.void, 32))).reshape(-1)


def visible_floor_lattice(
    mesh: MeshData,
    lattice: Samples,
    faces: np.ndarray,
    normals_b: np.ndarray,
    dirs,
    cams,
    probes,
    caster,
    *,
    lattice_min: int = 36,
    lattice_per_sq_in: float = 1.0,
    lattice_cap: int = 4096,
    unseen_keys: np.ndarray | None = None,
    snap_step: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(rows, cols, is_front)` of visible `(lattice_row, view_col, is_front)` across `lattice` on `faces` (job P2-V3).

    Uses exact 3-level midpoint triangle-quadtree shadow-frustum culling (`D0 -> D1 -> D2`, 64 cells per face) so
    viewpoint-cell pairs provably occluded by a blocker triangle are skipped before point-level casting, and reuses
    unseen sample answers (`unseen_keys` snapped at `snap_step`) where a lattice point coincides with an already-cast
    sample point. Every verdict and count is identical to casting `visible_samples` across the full lattice.
    """
    if not len(lattice):
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, bool)

    dirs = _rows(dirs, "dirs")
    if len(dirs):
        length = np.linalg.norm(dirs, axis=1)
        if (length <= 0.0).any():
            raise ValueError("a view direction has zero length")
        dirs = dirs / length[:, None]
    toward = -dirs
    toward_f32 = np.ascontiguousarray(toward, dtype=np.float32)
    cams, probes = _rows(cams, "cams"), _rows(probes, "probes")
    eyes = np.vstack([cams, probes]) if (len(cams) or len(probes)) else np.zeros((0, 3))
    n_dirs, n_eyes = len(toward), len(eyes)

    wrap = getattr(caster, "_wrap", None)
    if wrap is None:
        vs = visible_samples(mesh, lattice, dirs, cams, probes, caster)
        r, col = np.nonzero(vs.seen)
        return r, col, vs.front[r, col]

    w_origin, w_scale, scene = wrap.origin, float(wrap.scale), wrap.scene
    pn, pd_tri = caster._pn, caster._pd_tri
    tri_verts = mesh.positions[mesh.face_v]

    # Identify triangles whose trimesh normal is zero (`pn == 0`) while their float32 Embree cross product is non-zero:
    # Embree can report a hit on these collinear slivers that trimesh's plane_line then discards (`|proj_dir| <= 1e-5`).
    pn_zero = np.flatnonzero(np.linalg.norm(pn, axis=1) == 0.0)
    if len(pn_zero):
        v_f32 = ((mesh.positions - w_origin) * w_scale).astype(np.float32)
        tv32 = v_f32[mesh.face_v[pn_zero]]
        cr32 = np.cross(tv32[:, 1] - tv32[:, 0], tv32[:, 2] - tv32[:, 0])
        ghost_ids = pn_zero[np.linalg.norm(cr32, axis=1) > 0.0]
        ghost_verts = tri_verts[ghost_ids]
        d01 = np.linalg.norm(ghost_verts[:, 1] - ghost_verts[:, 0], axis=1)
        d12 = np.linalg.norm(ghost_verts[:, 2] - ghost_verts[:, 1], axis=1)
        d20 = np.linalg.norm(ghost_verts[:, 0] - ghost_verts[:, 2], axis=1)
        ghost_A = np.where((d01 >= d12)[:, None] & (d01 >= d20)[:, None], ghost_verts[:, 0],
                  np.where((d12 >= d20)[:, None], ghost_verts[:, 1], ghost_verts[:, 2]))
        ghost_B = np.where((d01 >= d12)[:, None] & (d01 >= d20)[:, None], ghost_verts[:, 1],
                  np.where((d12 >= d20)[:, None], ghost_verts[:, 2], ghost_verts[:, 0]))
    else:
        ghost_A = np.zeros((0, 3))
        ghost_B = np.zeros((0, 3))

    def _ghost_eye_mask(O_corners: np.ndarray, P_eyes: np.ndarray) -> np.ndarray:
        if not len(ghost_A) or not len(P_eyes):
            return np.zeros(len(P_eyes), dtype=bool)
        uA = ghost_A[None, :, :] - P_eyes[:, None, :]
        uB = ghost_B[None, :, :] - P_eyes[:, None, :]
        n_g = np.cross(uA, uB)
        n_g /= np.maximum(np.linalg.norm(n_g, axis=2, keepdims=True), 1e-12)
        W = O_corners - P_eyes[:, None, :]
        h = np.einsum("kci,kgi->kcg", W, n_g)
        return ((h.min(axis=1) <= 0.05) & (h.max(axis=1) >= -0.05)).any(axis=1)

    def _peel_eyes_batch(O_corners: np.ndarray, P_eyes: np.ndarray, n_peels: int = 2):
        K = len(P_eyes)
        whole_dec = np.zeros(K, dtype=bool)
        sub4_dec = np.zeros((K, 4), dtype=bool)
        if not K:
            return whole_dec, sub4_dec
        o_cent = O_corners.mean(axis=1)
        to_p = P_eyes - o_cent
        reach = np.sqrt(np.einsum("ij,ij->i", to_p, to_p))
        dir_p = -to_p / np.maximum(reach, _MIN_DIST)[:, None]
        c_pos = P_eyes + EPS_ORIGIN * dir_p
        c_dist = np.full(K, EPS_ORIGIN)
        act = np.flatnonzero(~_ghost_eye_mask(O_corners, P_eyes))
        for _ in range(n_peels):
            if not len(act):
                break
            ht, t = caster.first_hit(c_pos[act], dir_p[act])
            tot = c_dist[act] + t
            blk = (ht >= 0) & (tot < reach[act] - EPS_ORIGIN)
            if not blk.any():
                break
            act_b = act[blk]
            ht_b = ht[blk]
            P = P_eyes[act_b]
            O = O_corners[act_b]
            B = tri_verts[ht_b]
            u0, u1, u2 = B[:, 0] - P, B[:, 1] - P, B[:, 2] - P
            m0, m1, m2 = np.cross(u0, u1), np.cross(u1, u2), np.cross(u2, u0)
            det_sign = np.where(np.einsum("ij,ij->i", u0, m1) >= 0.0, 1.0, -1.0)[:, None]
            m0 *= det_sign / np.maximum(np.linalg.norm(m0, axis=1, keepdims=True), 1e-12)
            m1 *= det_sign / np.maximum(np.linalg.norm(m1, axis=1, keepdims=True), 1e-12)
            m2 *= det_sign / np.maximum(np.linalg.norm(m2, axis=1, keepdims=True), 1e-12)
            nB = normals_b[ht_b].copy()
            wc = o_cent[act_b] - P
            nB *= np.where(np.einsum("ij,ij->i", wc, nB) >= 0.0, 1.0, -1.0)[:, None]
            p_in_front = np.einsum("kj,kj->k", B[:, 0] - P, nB) > (EPS_ORIGIN + 0.05)
            if p_in_front.any():
                pf_idx = np.flatnonzero(p_in_front)
                W_d = O[pf_idx] - P[pf_idx, None, :]
                M_planes = np.stack([m0[pf_idx], m1[pf_idx], m2[pf_idx]], axis=2)
                D_cone = np.einsum("kci,kie->kce", W_d, M_planes) - 1e-3
                D_depth = (np.einsum("kci,ki->kc", O[pf_idx] - B[pf_idx, 0:1, :], nB[pf_idx]) - 0.05)[:, :, None]
                D = np.concatenate([D_cone, D_depth], axis=2)
                w_ok = (D > 0.0).all(axis=(1, 2))
                whole_rows = act_b[pf_idx[w_ok]]
                whole_dec[whole_rows] = True
                sub4_dec[whole_rows] = True
                part = np.flatnonzero(~w_ok)
                if len(part):
                    D_sub4 = np.einsum("qca,kae->kqce", _SUB4_MATS, D[part])
                    q_ok = (D_sub4 > 0.0).all(axis=(2, 3))
                    part_rows = act_b[pf_idx[part]]
                    sub4_dec[part_rows] |= q_ok
                    all4 = sub4_dec[part_rows].all(axis=1)
                    whole_dec[part_rows[all4]] = True
            still = act_b[~whole_dec[act_b]]
            t_still = t[blk][~whole_dec[act_b]]
            c_pos[still] = c_pos[still] + (t_still + 0.05)[:, None] * dir_p[still]
            c_dist[still] = c_dist[still] + t_still + 0.05
            act = still
        return whole_dec, sub4_dec

    def _peel_dirs_batch(O_corners: np.ndarray, toward_dirs: np.ndarray, sky_dist: float = 5000.0, n_peels: int = 2):
        K = len(toward_dirs)
        whole_dec = np.zeros(K, dtype=bool)
        sub4_dec = np.zeros((K, 4), dtype=bool)
        if not K:
            return whole_dec, sub4_dec
        o_cent = O_corners.mean(axis=1)

        def _eval(act_b: np.ndarray, ht_b: np.ndarray):
            O = O_corners[act_b]
            tw = toward_dirs[act_b]
            B = tri_verts[ht_b]
            e0, e1, e2 = B[:, 1] - B[:, 0], B[:, 2] - B[:, 1], B[:, 0] - B[:, 2]
            m0, m1, m2 = np.cross(e0, tw), np.cross(e1, tw), np.cross(e2, tw)
            nB = normals_b[ht_b]
            ds = np.where(np.einsum("ij,ij->i", tw, nB) <= 0.0, 1.0, -1.0)[:, None]
            m0 *= ds / np.maximum(np.linalg.norm(m0, axis=1, keepdims=True), 1e-12)
            m1 *= ds / np.maximum(np.linalg.norm(m1, axis=1, keepdims=True), 1e-12)
            m2 *= ds / np.maximum(np.linalg.norm(m2, axis=1, keepdims=True), 1e-12)
            denom = np.einsum("ij,ij->i", tw, nB)[:, None]
            num = np.einsum("kij,kj->ki", B[:, 0:1, :] - O, nB)
            tc = np.where(np.abs(denom) > 1e-9, num / np.where(np.abs(denom) > 1e-9, denom, 1.0), -1.0)
            d0 = np.einsum("kci,ki->kc", O - B[:, 0:1, :], m0) - 1e-3
            d1 = np.einsum("kci,ki->kc", O - B[:, 1:2, :], m1) - 1e-3
            d2 = np.einsum("kci,ki->kc", O - B[:, 2:3, :], m2) - 1e-3
            D = np.stack([d0, d1, d2, tc - 0.05], axis=2)
            w_ok = (D > 0.0).all(axis=(1, 2))
            whole_rows = act_b[w_ok]
            whole_dec[whole_rows] = True
            sub4_dec[whole_rows] = True
            part = np.flatnonzero(~w_ok)
            if len(part):
                D_sub4 = np.einsum("qca,kae->kqce", _SUB4_MATS, D[part])
                q_ok = (D_sub4 > 0.0).all(axis=(2, 3))
                part_rows = act_b[part]
                sub4_dec[part_rows] |= q_ok
                all4 = sub4_dec[part_rows].all(axis=1)
                whole_dec[part_rows[all4]] = True

        c_pos = o_cent + sky_dist * toward_dirs
        c_dist = np.zeros(K, dtype=np.float64)
        act = np.arange(K)
        for _ in range(n_peels):
            if not len(act):
                break
            ht, t = caster.first_hit(c_pos[act], -toward_dirs[act])
            tot = c_dist[act] + t
            blk = (ht >= 0) & (tot < sky_dist - EPS_ORIGIN)
            if not blk.any():
                break
            act_b = act[blk]
            _eval(act_b, ht[blk])
            still = act_b[~whole_dec[act_b]]
            t_still = t[blk][~whole_dec[act_b]]
            c_pos[still] = c_pos[still] - (t_still + 0.05)[:, None] * toward_dirs[still]
            c_dist[still] = c_dist[still] + t_still + 0.05
            act = still
        rem = np.flatnonzero(~whole_dec)
        if len(rem):
            ht, _ = caster.first_hit(o_cent[rem], toward_dirs[rem])
            blk = ht >= 0
            if blk.any():
                _eval(rem[blk], ht[blk])
        return whole_dec, sub4_dec

    ids = np.asarray(faces, dtype=np.int64).reshape(-1)
    M = len(ids)
    f_verts = tri_verts[ids]
    f_cents = f_verts.mean(axis=1)
    f_norms = normals_b[ids]
    plane_d = np.einsum("ij,ij->i", f_norms, f_verts[:, 0, :])
    area = 0.5 * np.linalg.norm(np.cross(f_verts[:, 1] - f_verts[:, 0], f_verts[:, 2] - f_verts[:, 0]), axis=1)
    wanted = np.minimum(lattice_min + np.ceil(area * lattice_per_sq_in), lattice_cap)
    sides = np.minimum(np.ceil(np.sqrt(wanted)), int(np.floor(np.sqrt(lattice_cap)))).astype(np.int64)
    counts = sides * sides
    starts = np.cumsum(counts) - counts

    n_workers = getattr(caster, "threads", 8)
    out_r_all, out_col_all, out_fr_all = [], [], []

    for f0 in range(0, M, 256):
        f1 = min(f0 + 256, M)
        Mb = f1 - f0
        fv_b = f_verts[f0:f1]
        fc_b = f_cents[f0:f1]
        fn_b = f_norms[f0:f1]
        pd_b = plane_d[f0:f1]
        sd_b = sides[f0:f1]
        ct_b = counts[f0:f1]
        ids_b = ids[f0:f1]
        p_start = int(starts[f0])
        p_end = int(starts[f1 - 1] + counts[f1 - 1])
        pts_batch = lattice.points[p_start:p_end]
        n_pts_b = len(pts_batch)

        f_loc = np.repeat(np.arange(Mb, dtype=np.int64), ct_b)
        c64_loc = np.concatenate([_lattice_c64_ids(int(s)) for s in sd_b])
        if unseen_keys is not None and len(unseen_keys) > 0 and snap_step > 0.0:
            pt_keys = snapped_point_keys(ids_b[f_loc], pts_batch, snap_step)
            skip_pt = np.isin(pt_keys, unseen_keys)
        else:
            skip_pt = None

        dir_active = np.zeros((Mb, 64, n_dirs), dtype=bool)
        dot_fd = fn_b @ toward.T
        if n_dirs:
            rf_d, cd_d = np.nonzero(np.abs(dot_fd) > MIN_COS)
            if len(rf_d):
                side_d = np.where(dot_fd[rf_d, cd_d] > 0.0, EPS_ORIGIN, -EPS_ORIGIN)
                O_d0 = fv_b[rf_d] + side_d[:, None, None] * fn_b[rf_d][:, None, :]
                _, sub4_d0 = _peel_dirs_batch(O_d0, toward[cd_d], n_peels=2)
                r_id0, q_id0 = np.nonzero(~sub4_d0)
                if len(r_id0):
                    rf_dq = rf_d[r_id0]
                    cd_dq = cd_d[r_id0]
                    big_d1 = sd_b[rf_dq] > 12
                    sm_rf, sm_cd, sm_q = rf_dq[~big_d1], cd_dq[~big_d1], q_id0[~big_d1]
                    for st_i in range(16):
                        dir_active[sm_rf, sm_q * 16 + st_i, sm_cd] = True
                    if big_d1.any():
                        rb1, qb1 = r_id0[big_d1], q_id0[big_d1]
                        O_d1 = np.einsum("kij,kjd->kid", _SUB4_MATS[qb1], O_d0[rb1])
                        _, sub4_d1 = _peel_dirs_batch(O_d1, toward[cd_d[rb1]], n_peels=1)
                        r_id1, s_id1 = np.nonzero(~sub4_d1)
                        if len(r_id1):
                            rf_ds = rf_d[rb1[r_id1]]
                            cd_ds = cd_d[rb1[r_id1]]
                            c16_d = qb1[r_id1] * 4 + s_id1
                            big_d2 = sd_b[rf_ds] > 28
                            md_rf, md_cd, md_c16 = rf_ds[~big_d2], cd_ds[~big_d2], c16_d[~big_d2]
                            for t_i in range(4):
                                dir_active[md_rf, md_c16 * 4 + t_i, md_cd] = True
                            if big_d2.any():
                                rb2, sb2 = r_id1[big_d2], s_id1[big_d2]
                                O_d2 = np.einsum("kij,kjd->kid", _SUB4_MATS[sb2], O_d1[rb2])
                                _, sub4_d2 = _peel_dirs_batch(O_d2, toward[cd_ds[big_d2]], n_peels=1)
                                r_id2, t_id2 = np.nonzero(~sub4_d2)
                                if len(r_id2):
                                    dir_active[rf_ds[big_d2][r_id2], c16_d[big_d2][r_id2] * 4 + t_id2, cd_ds[big_d2][r_id2]] = True

        eye_active = np.zeros((Mb, 64, n_eyes), dtype=bool)
        dot_fe = fn_b @ eyes.T - pd_b[:, None] if n_eyes else np.zeros((Mb, 0))
        if n_eyes:
            f_rad = np.linalg.norm(fv_b - fc_b[:, None, :], axis=2).max(axis=1)
            dist_ce = np.linalg.norm(eyes[None, :, :] - fc_b[:, None, :], axis=2)
            rf_e, ce_e = np.nonzero(np.abs(dot_fe) > MIN_COS * np.maximum(dist_ce - f_rad[:, None], _MIN_DIST))
            if len(rf_e):
                side_e = np.where(dot_fe[rf_e, ce_e] > 0.0, EPS_ORIGIN, -EPS_ORIGIN)
                O_e0 = fv_b[rf_e] + side_e[:, None, None] * fn_b[rf_e][:, None, :]
                _, sub4_e0 = _peel_eyes_batch(O_e0, eyes[ce_e], n_peels=2)
                r_ie0, q_ie0 = np.nonzero(~sub4_e0)
                if len(r_ie0):
                    rf_eq = rf_e[r_ie0]
                    ce_eq = ce_e[r_ie0]
                    big_e1 = sd_b[rf_eq] > 12
                    sm_rf, sm_ce, sm_q = rf_eq[~big_e1], ce_eq[~big_e1], q_ie0[~big_e1]
                    for st_i in range(16):
                        eye_active[sm_rf, sm_q * 16 + st_i, sm_ce] = True
                    if big_e1.any():
                        rb1, qb1 = r_ie0[big_e1], q_ie0[big_e1]
                        O_e1 = np.einsum("kij,kjd->kid", _SUB4_MATS[qb1], O_e0[rb1])
                        _, sub4_e1 = _peel_eyes_batch(O_e1, eyes[ce_e[rb1]], n_peels=1)
                        r_ie1, s_ie1 = np.nonzero(~sub4_e1)
                        if len(r_ie1):
                            rf_es = rf_e[rb1[r_ie1]]
                            ce_es = ce_e[rb1[r_ie1]]
                            c16_e = qb1[r_ie1] * 4 + s_ie1
                            big_e2 = sd_b[rf_es] > 28
                            md_rf, md_ce, md_c16 = rf_es[~big_e2], ce_es[~big_e2], c16_e[~big_e2]
                            for t_i in range(4):
                                eye_active[md_rf, md_c16 * 4 + t_i, md_ce] = True
                            if big_e2.any():
                                rb2, sb2 = r_ie1[big_e2], s_ie1[big_e2]
                                O_e2 = np.einsum("kij,kjd->kid", _SUB4_MATS[sb2], O_e1[rb2])
                                _, sub4_e2 = _peel_eyes_batch(O_e2, eyes[ce_es[big_e2]], n_peels=1)
                                r_ie2, t_ie2 = np.nonzero(~sub4_e2)
                                if len(r_ie2):
                                    eye_active[rf_es[big_e2][r_ie2], c16_e[big_e2][r_ie2] * 4 + t_ie2, ce_es[big_e2][r_ie2]] = True

        def _worker_pts(s_slice: slice):
            loc_r, loc_c, loc_f = [], [], []
            for i0 in range(s_slice.start, s_slice.stop, 256):
                i1 = min(i0 + 256, s_slice.stop)
                if skip_pt is not None:
                    keep = np.flatnonzero(~skip_pt[i0:i1])
                    if not len(keep):
                        continue
                    p_sub = pts_batch[i0:i1][keep]
                    fl_sub = f_loc[i0:i1][keep]
                    c64_sub = c64_loc[i0:i1][keep]
                    row_map = (p_start + i0) + keep
                else:
                    p_sub = pts_batch[i0:i1]
                    fl_sub = f_loc[i0:i1]
                    c64_sub = c64_loc[i0:i1]
                    row_map = None
                n_sub = fn_b[fl_sub]

                if n_dirs:
                    rp, cd = np.nonzero(dir_active[fl_sub, c64_sub])
                    if len(rp):
                        c_val = dot_fd[fl_sub[rp], cd]
                        is_fr = c_val > 0.0
                        orig = p_sub[rp] + np.where(is_fr, EPS_ORIGIN, -EPS_ORIGIN)[:, None] * n_sub[rp]
                        sc_o = ((orig - w_origin) * w_scale).astype(np.float32)
                        hit = scene.run(sc_o, toward_f32[cd])
                        esc = np.flatnonzero(hit == -1)
                        if len(esc):
                            r_esc = rp[esc]
                            loc_r.append((p_start + i0 + r_esc) if row_map is None else row_map[r_esc])
                            loc_c.append(cd[esc])
                            loc_f.append(is_fr[esc])

                if n_eyes:
                    rp, ce = np.nonzero(eye_active[fl_sub, c64_sub])
                    if len(rp):
                        d_val = dot_fe[fl_sub[rp], ce]
                        v = eyes[ce] - p_sub[rp]
                        dist2 = np.einsum("ij,ij->i", v, v)
                        ok_ang = (dist2 > _MIN_DIST * _MIN_DIST) & (d_val * d_val > (MIN_COS * MIN_COS) * dist2)
                        if ok_ang.any():
                            ia = np.flatnonzero(ok_ang)
                            rp, ce, d_val = rp[ia], ce[ia], d_val[ia]
                            is_fr = d_val > 0.0
                            orig = p_sub[rp] + np.where(is_fr, EPS_ORIGIN, -EPS_ORIGIN)[:, None] * n_sub[rp]
                            to = eyes[ce] - orig
                            reach = np.sqrt(np.einsum("ij,ij->i", to, to))
                            ud = to / np.maximum(reach, _MIN_DIST)[:, None]
                            sc_o = ((orig - w_origin) * w_scale).astype(np.float32)
                            q = scene.run(sc_o, ud.astype(np.float32))
                            miss = q == -1
                            hit_idx = np.flatnonzero(~miss)
                            if len(hit_idx):
                                ht = q[hit_idx].astype(np.int64)
                                proj_dir = np.einsum("ij,ij->i", ud[hit_idx], pn[ht])
                                valid = np.abs(proj_dir) > 1e-5
                                miss[hit_idx[~valid]] = True
                                v_idx = hit_idx[valid]
                                if len(v_idx):
                                    ht_v = ht[valid]
                                    proj_ori = pd_tri[ht_v] - np.einsum("ij,ij->i", orig[v_idx], pn[ht_v])
                                    t_v = proj_ori / proj_dir[valid]
                                    miss[v_idx[t_v >= reach[v_idx] - EPS_ORIGIN]] = True
                            clr = np.flatnonzero(miss)
                            if len(clr):
                                r_clr = rp[clr]
                                loc_r.append((p_start + i0 + r_clr) if row_map is None else row_map[r_clr])
                                loc_c.append(n_dirs + ce[clr])
                                loc_f.append(is_fr[clr])
            if not loc_r:
                return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, bool)
            return np.concatenate(loc_r), np.concatenate(loc_c), np.concatenate(loc_f)

        parts = np.array_split(np.arange(n_pts_b), min(max(1, n_pts_b // 256), n_workers * 4))
        slices = [slice(int(p[0]), int(p[-1]) + 1) for p in parts if len(p)]
        res = list(_pool().map(_worker_pts, slices))
        for r_s, c_s, f_s in res:
            if len(r_s):
                out_r_all.append(r_s)
                out_col_all.append(c_s)
                out_fr_all.append(f_s)

    if not out_r_all:
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, bool)
    r_cat = np.concatenate(out_r_all)
    c_cat = np.concatenate(out_col_all)
    f_cat = np.concatenate(out_fr_all)
    order = np.lexsort((c_cat, r_cat))
    return r_cat[order], c_cat[order], f_cat[order]
