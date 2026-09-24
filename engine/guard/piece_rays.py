"""Rays through the piece itself: how a debris removal is confirmed when no guard pixel meets it.

WHY NOT PIXELS. The fragment guard (`engine.guard.compare.fragment_feedback`) and the final guard
judge the pixels a removal changed. At the real files' guard size a pixel spans 1.5 to 3.5 in,
and debris is 0.001 to 0.05 in wide: a strip that thin is met by a guard ray now and then, and
mostly never. Brief 08 re-judged the 21 pieces the fragment pass had removed at 670ad50: 10 were
real surface -- thin risers, a rim band of needles, a fold pair closing the top of a ramp's side
wall -- and each shipped a hairline crack onto the inside of the model while every guard passed.
The open-border sliver rule keeps those now, but two slivers it names still opened sub-pixel
slots onto the inside (file A, faces 3540 and 4659). A pixel cannot judge a sub-pixel piece;
lines through the piece can.

THE RULE. A candidate UNIT -- a fragment component, or one sliver -- is sampled on every one of its
faces (`strata_points`). For each point p and each exposure direction w (the directions
`engine.vis.exposure` measures exposure along), (p, w) is a LINE of the unit when a viewer out in
direction w sees the unit at p on the reference: nothing of the reference lies on the ray from p
toward w. A face level with p -- within `TIE` along the ray, a double layer or a fold -- does not
hide it: both are seen there, and the line counts. Each line is then followed on from the
viewer's side through p, in AFTER: the reference without the faces earlier passes removed
(`already_removed`) and without EVERY unit still marked for removal. What it meets first there is
what that viewer sees once the removal is done -- the sky, a face side the reference already
exposed, or a face side the reference never exposed (`side_exposure`, the per-side exposure the
fragment guard and the final guard read). A unit any of whose lines ends on a side of that last
kind -- the inside of a shell -- is REFUSED, and put back. A face met LEVEL with p (within `TIE`)
is the one exception, because the line itself is the measurement: that line met the same face
at the same place on the reference, tied with the piece, so its side was seen whatever the
exposure's sampling found. Measured on the real references: file A's fold member 3059 and file
B's 2254 were seen along 684 and 29 lines, every one of which met the fold's other member (3082,
2253) level with it on a side the exposure's 4 points x 128 directions had never found -- B's
2253 samples 0.0 on both sides. Units are refused ONE PER ROUND, and every unit still marked is
judged again with it in place, because putting a piece back can cover what the others' lines
saw: first a unit that fails even judged alone (it can never go), else the lowest -- so of two
pieces failing only because each covers the other, one stays and the other goes. A refused unit
is never proposed again, so this ends. This is review 2a's alternative fix 2 for C1, and the
pixel rule of `engine.guard.compare.classify_pixels` (`removed_before` / `exposed_after`) applied
to lines through the piece instead of pixels on a grid.

EVERY MARKED UNIT GONE AT ONCE, never one at a time: at 670ad50 file B's faces 5750 and 5751 were
removed together, each covering most of the other, and together they had closed an 86 in crack at
the top of a ramp's side wall. Judged one at a time, each is covered by the other.

UNITS THAT MUST STAY COVERED. A fold's redundant member (`engine.detectors.folds`) is no debris:
its removal is meant to change nothing at all, so it is judged `covered` -- refused unless EVERY
one of its lines still meets a face level with it, where the rest of the model covers it exactly.
Debris may uncover the sky or an outside surface; a fold member may not. `judge_alone` gives each
unit's verdict with only itself gone, which is how the pipeline picks the member to propose.

HOW MANY POINTS. `N_POINTS` (256) per face, one per equal-area stratum (see `strata_points`): a
needle is cut into 64 slices along its length and 4 bands across it, so file A's 16.2 in lip 3540
is sampled every 0.25 in. Measured with this module on brief 08's captured references and the
exposure's 128 directions, each piece judged alone: 3540 opens a slot onto the inside along 219
of its 15,360 lines at 256 points, and along none of its 3,840 at 64 (16 slices x 4 bands: the
slot lies between the slices) -- so 64 is too few for a needle, and 256 is the least count tried
that finds it. Every other piece brief 08 judged real surface is refused at both counts, by 229
lines or more (B 5750 alone at 64 points; the risers by all of theirs), and none of the pieces it
judged harmless is. A face costs under 0.1 s.

FLOAT64 NEAR THE PIECE. `EmbreeCaster` stores vertices as float32, and on file B its hits strayed
6e-5 in outside a 129 in face's edge and leaked through another 1.1e-4 in inside its edge -- a
sizeable part of a strip 0.0015 in wide. So every ray is cast in float64 (Moller-Trumbore, as
`BruteCaster` does, over only the faces near its own point) for its first `REACH` inches from the
piece, and by embree, recentred on the unit, beyond that. Brief 08's own scratch check
(`own_rays.py`) cast everything in float32 from 1e-5 in off the piece, and read A 1983 and B 5229
as reached by no line at all: each one's coincident twin (1982, 5233) was met 1e-5 to 4e-5 in
BEHIND the ray's own start. Both are seen from thousands of lines here, and both would be refused.

Deterministic: fixed points, fixed directions, units in the order given, sorted lists, no random
number anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.rays.caster import EmbreeCaster

#: Equal-area strata, and so sample points, per face of a unit (see the module docstring for the
#: measurement behind it).
N_POINTS = 256
#: Bands across a face, at least: without them a needle's strata are one row along its length, at
#: one height, and a slot under the other part of its width is never sampled.
MIN_BANDS = 4
#: How far from the piece, in inches, rays are cast in float64 before embree takes over.
REACH = 1.0
#: Along a ray, how close to the piece (in inches) another face counts as level with it -- a
#: double layer or a fold, seen together with it -- rather than in front of it.
TIE = 1e-6
#: Barycentric slack of the float64 hit test, so a ray through the edge two faces share meets
#: one of them instead of slipping between them.
_BARY_TOL = 1e-9
#: How many (ray, face) pairs one float64 block tests at once.
_PAIR_BLOCK = 1_000_000


def strata_points(tri: np.ndarray, n: int = N_POINTS, min_bands: int = MIN_BANDS) -> np.ndarray:
    """About `n` points on the triangle `tri` (`(3, 3)`), one per EQUAL-AREA stratum.

    The strata are `slices` fans from the apex over equal parts of the LONGEST edge, each cut into
    `bands` equal-area bands from that edge toward the apex -- band `j` ends `1 - sqrt(1 - j/bands)`
    of the way up, because a triangle's area grows as the square of the distance from its apex.
    Every stratum therefore holds `area / (slices * bands)`. `bands` makes the strata as square
    as the face allows (`sqrt(n * height / longest)`), and is never below `min_bands`; `slices` is
    `n / bands`. Each point is the middle, by area, of its stratum: halfway along its slice, and
    at `1 - sqrt(1 - (j + 1/2)/bands)` of the way up."""
    tri = np.asarray(tri, dtype=np.float64).reshape(3, 3)
    lengths = np.linalg.norm(tri - np.roll(tri, -1, axis=0), axis=1)
    k = int(np.argmax(lengths))
    a, b, c = tri[k], tri[(k + 1) % 3], tri[(k + 2) % 3]
    longest = float(lengths[k])
    if longest <= 0.0:
        return tri[:1].copy()                     # all three corners in one place
    height = float(np.linalg.norm(np.cross(b - a, c - a))) / longest
    bands = max(int(min_bands), int(round(np.sqrt(n * height / longest))))
    slices = max(1, int(round(n / bands)))
    u = (np.arange(slices) + 0.5) / slices
    h = 1.0 - np.sqrt(1.0 - (np.arange(bands) + 0.5) / bands)
    base = a[None, :] + u[:, None] * (b - a)[None, :]
    return (base[:, None, :] + h[None, :, None] * (c[None, None, :] - base[:, None, :])).reshape(-1, 3)


@dataclass
class PieceRayCheck:
    #: Bool per unit: still marked for removal after the check.
    confirmed: np.ndarray
    #: Per unit, the verdict of the last round that judged it -- `{"faces", "points", "lines",
    #: "lines_level", "lines_inside", "inside_faces", "refused"}` -- or `None` for a unit handed
    #: in unmarked. `lines_level` counts the lines that met a face level with the unit (the rest of
    #: the model covering it right there), `lines_inside` those that met a side never exposed, and
    #: `inside_faces` lists (up to 5, ascending) the faces whose never-exposed side was met.
    verdicts: list
    #: One entry per round: `{"round", "units", "lines", "lines_inside", "refused"}`.
    history: list


def _unit_normals(tri: np.ndarray) -> np.ndarray:
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normal, axis=1)
    out = np.zeros_like(normal)
    good = length > 0.0
    out[good] = normal[good] / length[good, None]
    return out


def _near_first_hits(tri: np.ndarray, face_ids: np.ndarray, near: np.ndarray, points: np.ndarray,
                     ray_point: np.ndarray, ray_dir: np.ndarray, t_lo: float, t_hi: float):
    """In float64: for each ray `points[ray_point[r]] + t * ray_dir[r]`, the first of the
    triangles `tri` (`(M, 3, 3)`, ids `face_ids`) it meets with `t_lo < t <= t_hi`, testing only
    the triangles `near[ray_point[r]]` marks (`(P, M)` bool). Returns `(face id or -1, t)`."""
    n_rays = len(ray_point)
    face = np.full(n_rays, -1, np.int64)
    best = np.full(n_rays, np.inf)
    if not n_rays or not len(tri):
        return face, best
    v0, e1, e2 = tri[:, 0], tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    order = np.argsort(ray_point, kind="stable")
    starts = np.searchsorted(ray_point[order], np.arange(len(points) + 1))
    for p in range(len(points)):
        rays = order[starts[p]:starts[p + 1]]
        cols = np.nonzero(near[p])[0]
        if not len(rays) or not len(cols):
            continue
        for lo in range(0, len(rays), max(1, _PAIR_BLOCK // len(cols))):
            r = rays[lo:lo + max(1, _PAIR_BLOCK // len(cols))]
            d = ray_dir[r]                                               # (R, 3)
            s = points[p][None, :] - v0[cols]                           # (C, 3)
            q = np.cross(s, e1[cols])                                    # (C, 3)
            h = np.cross(d[:, None, :], e2[cols][None, :, :])            # (R, C, 3)
            det = np.einsum("ck,rck->rc", e1[cols], h)
            ok = det != 0.0
            inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
            u = np.einsum("ck,rck->rc", s, h) * inv
            v = (d @ q.T) * inv
            t = np.einsum("ck,ck->c", q, e2[cols])[None, :] * inv
            hit = (ok & (u >= -_BARY_TOL) & (v >= -_BARY_TOL) & (u + v <= 1.0 + _BARY_TOL)
                   & (t > t_lo) & (t <= t_hi))
            t = np.where(hit, t, np.inf)
            k = np.argmin(t, axis=1)
            tk = t[np.arange(len(r)), k]
            better = tk < best[r]
            face[r[better]] = face_ids[cols[k[better]]]
            best[r[better]] = tk[better]
    return face, best


class _Unit:
    """One unit's points, its lines on the reference, and what it needs to follow them on."""

    def __init__(self, faces_ref: np.ndarray, positions_c: np.ndarray, faces: np.ndarray,
                 directions: np.ndarray, n_points: int, caster_factory):
        self.faces = np.asarray(faces_ref, dtype=np.int64)
        self.points = np.concatenate([strata_points(positions_c[faces[f]], n_points)
                                      for f in self.faces.tolist()])
        corners = positions_c[faces[self.faces]].reshape(-1, 3)
        self.origin = corners.mean(axis=0)            # recentred here for embree (float32)
        reach = REACH + TIE + 1e-9
        tri = positions_c[faces]
        lo, hi = tri.min(axis=1), tri.max(axis=1)
        around = ((hi >= corners.min(axis=0) - reach) & (lo <= corners.max(axis=0) + reach)).all(axis=1)
        self.near_ids = np.nonzero(around)[0]
        self.near_tri = tri[self.near_ids]
        near_lo, near_hi = lo[self.near_ids], hi[self.near_ids]
        self.near = ((near_hi[None] >= self.points[:, None] - reach)
                     & (near_lo[None] <= self.points[:, None] + reach)).all(axis=2)
        self.caster_factory = caster_factory
        self.positions_c = positions_c
        self.faces_all = faces

        # (p, w): the viewer out in direction w sees the unit at p when no face of the reference
        # lies on the ray from p toward w -- past `TIE`, so a face level with p does not hide it
        n_dirs = len(directions)
        self.ray_point = np.repeat(np.arange(len(self.points)), n_dirs)
        self.ray_dir = np.tile(np.asarray(directions, dtype=np.float64), (len(self.points), 1))
        hit, _t = _near_first_hits(self.near_tri, self.near_ids, self.near, self.points,
                                   self.ray_point, self.ray_dir, TIE, REACH)
        clear = hit < 0
        if clear.any():
            far = caster_factory(positions_c - self.origin, faces)
            start = self.points[self.ray_point[clear]] + REACH * self.ray_dir[clear] - self.origin
            clear[np.nonzero(clear)[0][far.any_hit(start, self.ray_dir[clear])]] = False
        self.line = clear

    def follow(self, keep: np.ndarray, normals: np.ndarray, side_exposure: np.ndarray,
               covered: bool = False) -> dict:
        """Follow every line on, from the viewer through p, in the faces `keep` marks (bool over
        the reference): what each meets first, whether that side was exposed, and whether it lies
        level with p. `covered`: the unit must stay covered, so it is refused unless every line
        meets a face level with it."""
        rp, rd = self.ray_point[self.line], -self.ray_dir[self.line]
        if not len(rp):
            return {"faces": self.faces.tolist(), "points": int(len(self.points)), "lines": 0,
                    "lines_level": 0, "lines_inside": 0, "inside_faces": [], "refused": False}
        near_keep = keep[self.near_ids]
        face, t = _near_first_hits(self.near_tri, self.near_ids, self.near & near_keep[None, :],
                                   self.points, rp, rd, -TIE, REACH)
        rest = np.nonzero(face < 0)[0]
        after_ids = np.nonzero(keep)[0]
        if len(rest) and len(after_ids):
            far = self.caster_factory(self.positions_c - self.origin, self.faces_all[after_ids])
            start = self.points[rp[rest]] + REACH * rd[rest] - self.origin
            tri, _tt = far.first_hit(start, rd[rest])
            met = tri >= 0
            face[rest[met]] = after_ids[tri[met]]
        hit = face >= 0
        g = np.where(hit, face, 0)
        facing = np.einsum("ij,ij->i", normals[g], rd)
        seen_side = np.where(facing > 0.0, side_exposure[g, 1], side_exposure[g, 0])
        # a face with no plane has no side a line could be said to meet
        seen_side &= np.linalg.norm(normals[g], axis=1) > 0.0
        # a face LEVEL with the piece (a tie, within `TIE` of p) was met by this very line on
        # the reference, tied with the piece: seen, whatever the sampled exposure says
        level = hit & (t <= TIE)
        inside = hit & ~(seen_side | level)
        n_inside, n_level = int(inside.sum()), int(level.sum())
        return {"faces": self.faces.tolist(), "points": int(len(self.points)),
                "lines": int(len(rp)), "lines_level": n_level, "lines_inside": n_inside,
                "inside_faces": sorted(set(g[inside].tolist()))[:5],
                "refused": (n_level < len(rp)) if covered else n_inside > 0}


def judge_alone(units, positions_c: np.ndarray, faces: np.ndarray, side_exposure: np.ndarray,
                *, directions: np.ndarray, already_removed: np.ndarray | None = None,
                n_points: int = N_POINTS, caster_factory=EmbreeCaster) -> list[dict]:
    """Each unit's verdict with ONLY that unit and `already_removed` gone -- everything else in
    place -- as `piece_ray_check` words it (with `lines_level`, the lines that still meet a face
    level with the unit: where the rest of the model covers it exactly). Nothing is refused or
    put back: this is how `engine.fixes.pipeline` decides which member of a fold is the one the
    rest of the model covers, and so may be proposed at all."""
    faces = np.asarray(faces, dtype=np.int64)
    positions_c = np.asarray(positions_c, dtype=np.float64)
    exposure = np.asarray(side_exposure, dtype=bool).reshape(len(faces), 2)
    gone_before = (np.zeros(len(faces), dtype=bool) if already_removed is None
                   else np.asarray(already_removed, dtype=bool))
    normals = _unit_normals(positions_c[faces])
    out = []
    for ids in units:
        unit = _Unit(ids, positions_c, faces, directions, n_points, caster_factory)
        keep = ~gone_before
        keep[unit.faces] = False
        out.append(unit.follow(keep, normals, exposure))
    return out


def piece_ray_check(units, positions_c: np.ndarray, faces: np.ndarray, side_exposure: np.ndarray,
                    *, directions: np.ndarray, already_removed: np.ndarray | None = None,
                    marked: np.ndarray | None = None, covered=None, n_points: int = N_POINTS,
                    caster_factory=EmbreeCaster) -> PieceRayCheck:
    """Judge each candidate unit (`units[i]`, reference face ids) by the lines through it -- see
    the module docstring -- and refuse, one per round, units one of whose lines, with every marked
    unit and `already_removed` gone, meets a side `side_exposure` (`(F, 2)` bool: FRONT, BACK
    exposed on the reference) says was never exposed. A unit `covered` marks (bool per unit, none
    by default) MUST STAY COVERED -- a fold's redundant member, whose removal is meant to change
    nothing -- and is refused unless every one of its lines meets a face level with it.

    `positions_c` / `faces` are the recentred reference the pipeline renders (the WHOLE reference:
    a line is judged against what a person saw), `directions` the exposure's unit directions
    (`engine.vis.exposure.fib_dirs(profile.n_dirs)`), and `marked` (bool per unit, all by default)
    the units still proposed; an unmarked unit is left out of the rounds and gets no verdict."""
    faces = np.asarray(faces, dtype=np.int64)
    positions_c = np.asarray(positions_c, dtype=np.float64)
    exposure = np.asarray(side_exposure, dtype=bool).reshape(len(faces), 2)
    gone_before = (np.zeros(len(faces), dtype=bool) if already_removed is None
                   else np.asarray(already_removed, dtype=bool))
    marked = (np.ones(len(units), dtype=bool) if marked is None
              else np.asarray(marked, dtype=bool).copy())
    covered = (np.zeros(len(units), dtype=bool) if covered is None
               else np.asarray(covered, dtype=bool).reshape(len(units)))
    normals = _unit_normals(positions_c[faces])
    judged = {i: _Unit(units[i], positions_c, faces, directions, n_points, caster_factory)
              for i in np.nonzero(marked)[0].tolist()}
    verdicts: list = [None] * len(units)
    history: list[dict] = []
    fails_alone: dict[int, bool] = {}             # judged with only itself gone, when it failed
    for rnd in range(len(units) + 1):             # every round but the last refuses a unit
        keep = ~gone_before
        for i in np.nonzero(marked)[0].tolist():
            keep[judged[i].faces] = False
        failing = []
        for i in np.nonzero(marked)[0].tolist():
            verdicts[i] = judged[i].follow(keep, normals, exposure, covered=bool(covered[i]))
            if verdicts[i]["refused"]:
                if i not in fails_alone:
                    solo = ~gone_before
                    solo[judged[i].faces] = False
                    fails_alone[i] = judged[i].follow(solo, normals, exposure,
                                                      covered=bool(covered[i]))["refused"]
                failing.append((not fails_alone[i], i))
        history.append({"round": rnd, "units": int(marked.sum()),
                        "lines": sum(verdicts[i]["lines"] for i in np.nonzero(marked)[0]),
                        "lines_inside": sum(verdicts[i]["lines_inside"] for i in np.nonzero(marked)[0]),
                        "refused": int(bool(failing))})
        if not failing:
            break
        # ONE per round, because putting a piece back may cover what the others' lines saw: first
        # a unit that fails even judged alone (it can never go), else -- pieces failing only
        # because they cover each other -- the lowest; of two pieces covering each other, one
        # stays and the other, judged again, goes
        marked[min(failing)[1]] = False
    return PieceRayCheck(confirmed=marked, verdicts=verdicts, history=history)
