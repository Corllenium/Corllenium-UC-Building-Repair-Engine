"""The Validator, wired for the repair kernel's site checks (job P1-K3).

After each repair stage the kernel (`engine.repair.kernel.repair_unit(..., validate_sites=True)`) asks, for a few
of the stage's edits at a time, "did these break anything?". This module answers with the Validator itself
(`engine.validate.checks.validate` in its focus mode), so the kernel never judges its own work:

* `SiteJudge.begin(before)` takes a stage's input (the BEFORE of every check of that stage) once: its frame, the
  Validator's standard viewpoints (directions, the pedestrian ring and the eye-height probes) and the faces' boxes;
* `SiteJudge.focus(after, touched, new)` is the focus of a set of edits: in BEFORE, the faces they remove, flip or
  replace (`touched`), every face within their bounding box grown by `margin`, and the COVER CANDIDATES -- every
  face that could lie behind one of their new faces, or within the depth tolerance of one, from some standard
  viewpoint or probe (what the Validator's own "covered" and "overlaid" tests look at); in AFTER, the new faces
  (`new`: added, cut or flipped);
* `SiteJudge.check(after, focus)` runs the focus validation and returns a `SiteVerdict`: the failing samples
  (so a check can be compared with a baseline) and the Validator's reasons, for the edit log.

Why this module is here, outside both packages: the Validator must import nothing it judges (`engine.repair`,
`engine.fixes`, `engine.guard`), and the repair package computes its own measures and never imports the
Validator (K1-R2). The kernel gets a `SiteJudge` through `RepairContext.validator`, made by `engine.cli`.

THE COVER CANDIDATES ARE CONSERVATIVE BY CONSTRUCTION (P1-K3 fix round 1). They used to come from rays cast through
the new faces' sample lattice, which is 6 to 7.5 in apart, so a BEFORE face smaller than that gap, beyond the
margin, was missed (a 0.5 in face 40 in under a new 60 in plate: the full run said `covered`, the focus run PASS).
Now they are bounding-box shadows, with no sampling anywhere: a few boxes hold the new faces, each grown by the
depth tolerance, `EPS_ORIGIN` and a little slack; for each standard viewpoint, a BEFORE face is a candidate when its
own bounding box meets the box's shadow -- the box swept along the direction (a viewer far off at `-d` looks along
`+d`), or the cone from a camera or probe through the box and beyond. Each test is exact for the boxes, and the
boxes contain the faces, so a face some witness ray of the Validator could find covered or overlaid by a new face
is never left out (`_meets_shadow`). It over-approximates instead: the bottom of a box under a new plate is a
candidate though the box's top hides it. The ray peel this replaces (and its `_PEEL` cut-off) is gone.

WHAT THE COVER STEP LEAVES OUT, AND WHY THAT IS SAFE. It uses the standard viewpoints only, not the 1,024 extra
directions: the Validator casts those only for samples of SUSPECT faces (faces of BEFORE that AFTER no longer has),
and while AFTER is the stage input plus THIS site's edits, the suspect faces are exactly the site's touched faces,
which are in the focus already. When AFTER also carries other edits (another site's, kept earlier), their touched
faces are suspect too and are NOT in this focus: a cover of such a face is not looked at here.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from engine.model import MeshData
from engine.validate.checks import Focus, Looks, Settings, depth_tolerance, print_step, validate
from engine.validate.sampling import recentred, used_bbox
from engine.validate.viewpoints import interior_probes, outside_directions, pedestrian_ring
from engine.validate.visibility import EPS_ORIGIN, build_caster

#: Slack, in inches, on top of the depth tolerance and `EPS_ORIGIN` round the new faces' boxes.
_SLACK = 0.01
#: The new faces are held in at most this many boxes (a split along the longest axis at the median, twice).
_MAX_BOXES = 4
#: Viewpoints tested against every BEFORE face at once (memory: viewpoints x faces x 6 floats).
_VIEW_BLOCK = 32

#: No failing samples, judged nothing: the baseline of a check against an unchanged BEFORE.
NO_FAILURES: frozenset = frozenset()
#: (sample, new face) pairs tested at once when a failing sample's line of sight is checked against new faces.
_SEGMENT_PAIRS = 2_000_000


@dataclass
class FailingSamples:
    """Every failing sample of a focus run, one row each (P1-K3b). `face`: its BEFORE face; `index`: its index
    within the face (so `(face, index)` is a member of `SiteVerdict.failing`); `point`: where it is, in the
    model's own coordinates; `witness` and `is_dir`: the viewpoint whose line of sight judged it -- for a far-off
    direction (`is_dir`) the unit vector from the sample toward the viewer, else the camera or probe position, in
    model coordinates; `cluster`: which of the Validator's sites holds it, an index into `clusters`, the reasons of
    each of those sites (the Validator reports reasons per site, not per sample)."""
    face: np.ndarray
    index: np.ndarray
    point: np.ndarray
    witness: np.ndarray
    is_dir: np.ndarray
    cluster: np.ndarray
    clusters: list

    def __len__(self) -> int:
        return len(self.face)


def _no_samples() -> FailingSamples:
    empty = np.zeros(0, dtype=np.int64)
    return FailingSamples(face=empty, index=empty, point=np.zeros((0, 3)), witness=np.zeros((0, 3)),
                          is_dir=np.zeros(0, dtype=bool), cluster=empty, clusters=[])


@dataclass
class SiteVerdict:
    """What one focus validation found. `failing`: the failing samples, each `(BEFORE face, sample index within
    the face)`; `summary`: the Validator's counts, reasons and worst sites, for `edit_log.jsonl`; `samples`: the
    same failing samples with their points and judging viewpoints, for `SiteJudge.attribute`."""
    failing: frozenset
    summary: dict
    seconds: float = 0.0
    samples: FailingSamples = field(default_factory=_no_samples)

    @property
    def failed(self) -> bool:
        return bool(self.failing)


@dataclass
class SiteFocus:
    """The focus of one site, in parts (P1-K3b), so a failing sample can be charged to the site by the part that
    holds its face. In BEFORE: `touched` (the faces its edits remove, flip or replace), `near` (every face within
    its bounding box grown by the margin) and `cover` (its cover candidates); in AFTER: `new` (its added, cut or
    flipped faces), and `new_lo` / `new_hi`, the bounding box of each of those faces in model coordinates."""
    touched: np.ndarray
    near: np.ndarray
    cover: np.ndarray
    new: np.ndarray
    new_lo: np.ndarray
    new_hi: np.ndarray

    def focus(self) -> Focus:
        return Focus(before_faces=np.unique(np.concatenate([self.touched, self.near, self.cover])).astype(np.int64),
                     after_faces=self.new)


@dataclass
class Attribution:
    """Which sites could have caused which failing samples. `charged`: site -> indices (into `SiteVerdict.samples`)
    of the samples charged to it, only for sites with at least one; `how`: site -> how many of those were charged
    because the sample's face is one the site touched, lies within its grown box, or is a cover candidate with one
    of its new faces between the sample and its viewpoint (each sample counted once, by the first that holds);
    `unknown`: the samples charged to no site -- a legacy or unknown failure, reported, never dropped."""
    charged: dict
    how: dict
    unknown: np.ndarray


@dataclass
class _Stage:
    before: MeshData
    centre: np.ndarray
    viewpoints: np.ndarray        # (V, 3) model coordinates of the cameras and probes
    dirs: np.ndarray
    face_lo: np.ndarray
    face_hi: np.ndarray
    tol: float
    timings: dict = field(default_factory=dict)


class SiteJudge:
    """The Validator at the owner's settings, asked about sites. `looks` as `validate` takes them;
    `margin` (inches) grows a site's bounding box; `settings` must be the owner's defaults for a real run (a
    test may make them cheaper; `validate` says so in its notes)."""

    def __init__(self, looks: Looks, *, settings: Settings = Settings(), margin: float = 24.0):
        self.looks, self.settings, self.margin = looks, settings, float(margin)
        self._stage: _Stage | None = None
        self.calls = 0
        self.seconds = {"begin": 0.0, "focus": 0.0, "cover": 0.0, "check": 0.0}

    # -- per stage ---------------------------------------------------------------------------------------------
    def begin(self, before: MeshData) -> None:
        """Take `before` (a stage's input) as the BEFORE of every check until the next `begin`."""
        t0 = time.perf_counter()
        b, centre = recentred(before)
        caster = build_caster(b) if b.n_faces else None
        lo, hi = used_bbox(b)
        s = self.settings
        cams = pedestrian_ring((lo, hi), eye_z=lo[2] + s.eye, n=s.n_cameras, margin=s.camera_margin)
        probes = interior_probes(b, eye=s.eye, caster=caster) if b.n_faces else np.zeros((0, 3))
        tri = before.positions[before.face_v] if before.n_faces else np.zeros((0, 3, 3))
        self._stage = _Stage(before=before, centre=centre,
                             viewpoints=np.vstack([np.asarray(cams, float).reshape(-1, 3),
                                                   np.asarray(probes, float).reshape(-1, 3)]) + centre,
                             dirs=outside_directions(s.n_directions),
                             face_lo=tri.min(axis=1), face_hi=tri.max(axis=1),
                             tol=depth_tolerance(print_step(before)))
        self.seconds["begin"] += time.perf_counter() - t0

    @property
    def stage(self) -> _Stage:
        if self._stage is None:
            raise RuntimeError("SiteJudge.begin(before) must be called before a site is judged")
        return self._stage

    # -- the focus of a set of edits ---------------------------------------------------------------------------
    def cover_candidates(self, after: MeshData, new: np.ndarray) -> np.ndarray:
        """Sorted BEFORE face ids that could lie behind one of the AFTER faces `new`, or within the depth tolerance
        of one, from some standard direction, camera or probe: every face whose bounding box meets the shadow of a
        box holding new faces (see the module docstring). A superset of the faces those new faces can cover."""
        st = self.stage
        new = np.unique(np.asarray(new, dtype=np.int64))
        if not len(new) or not st.before.n_faces:
            return np.zeros(0, dtype=np.int64)
        t0 = time.perf_counter()
        grow = st.tol + EPS_ORIGIN + _SLACK
        found = np.zeros(st.before.n_faces, dtype=bool)
        for lo, hi in _boxes(after.positions[after.face_v[new]], _MAX_BOXES):
            lo, hi = lo - grow, hi + grow
            for k in range(0, len(st.dirs), _VIEW_BLOCK):
                found |= _meets_shadow(st.face_lo, st.face_hi, lo, hi, dirs=st.dirs[k:k + _VIEW_BLOCK])
            for k in range(0, len(st.viewpoints), _VIEW_BLOCK):
                found |= _meets_shadow(st.face_lo, st.face_hi, lo, hi, eyes=st.viewpoints[k:k + _VIEW_BLOCK])
        self.seconds["cover"] += time.perf_counter() - t0
        return np.flatnonzero(found).astype(np.int64)

    def focus(self, after: MeshData, touched: np.ndarray, new: np.ndarray) -> Focus:
        """The focus of a set of edits: BEFORE faces `touched` (removed, flipped or replaced), those within their
        bounding box (with the AFTER faces `new`) grown by `margin`, and the cover candidates of `new`; AFTER faces
        `new`."""
        return self.site_focus(after, touched, new).focus()

    def site_focus(self, after: MeshData, touched: np.ndarray, new: np.ndarray) -> SiteFocus:
        """`focus`, kept in its parts (see `SiteFocus`)."""
        st = self.stage
        t0 = time.perf_counter()
        touched = np.unique(np.asarray(touched, dtype=np.int64))
        new = np.unique(np.asarray(new, dtype=np.int64))
        tri = after.positions[after.face_v[new]] if len(new) else np.zeros((0, 3, 3))
        corners = np.concatenate([st.before.positions[st.before.face_v[touched]].reshape(-1, 3), tri.reshape(-1, 3)])
        near = np.zeros(0, dtype=np.int64)
        if len(corners):
            lo, hi = corners.min(axis=0) - self.margin, corners.max(axis=0) + self.margin
            near = np.flatnonzero(((st.face_lo <= hi) & (st.face_hi >= lo)).all(axis=1)).astype(np.int64)
        self.seconds["focus"] += time.perf_counter() - t0
        return SiteFocus(touched=touched, near=near, cover=self.cover_candidates(after, new), new=new,
                         new_lo=tri.min(axis=1), new_hi=tri.max(axis=1))

    @staticmethod
    def union(foci) -> Focus:
        """One focus for several sites: the union of their BEFORE faces and of their AFTER faces."""
        foci = [f.focus() for f in foci]
        empty = np.zeros(0, dtype=np.int64)
        return Focus(before_faces=np.unique(np.concatenate([empty, *[f.before_faces for f in foci]])),
                     after_faces=np.unique(np.concatenate([empty, *[f.after_faces for f in foci]])))

    # -- attribution -------------------------------------------------------------------------------------------
    def attribute(self, verdict: SiteVerdict, sites: dict) -> Attribution:
        """Charge each failing sample of `verdict` to every site of `sites` (id -> `SiteFocus`, built against the
        AFTER that was checked) that could have caused it: its face is one the site touched; or lies within the
        site's grown box; or is one of the site's cover candidates and one of the site's new faces lies between the
        sample and the viewpoint that judged it. "Between" is a box test, so it can only over-charge: the line of
        sight from the sample (from the depth tolerance behind it, for a layer on it) to the viewpoint (to infinity
        for a direction) meets the box of a new face grown by the depth tolerance, `EPS_ORIGIN` (the Validator's
        rays start that far off the face) and a little slack."""
        s = verdict.samples
        grow = self.stage.tol + EPS_ORIGIN + _SLACK
        charged, how = {}, {}
        hit_any = np.zeros(len(s), dtype=bool)
        for site in sorted(sites):
            f = sites[site]
            by_touch = np.isin(s.face, f.touched)
            by_box = ~by_touch & np.isin(s.face, f.near)
            by_cover = ~by_touch & ~by_box & np.isin(s.face, f.cover)
            if by_cover.any() and len(f.new_lo):
                rows = np.flatnonzero(by_cover)
                by_cover[rows] = _segments_meet_boxes(s.point[rows], s.witness[rows], s.is_dir[rows],
                                                      f.new_lo - grow, f.new_hi + grow, back=grow)
            else:
                by_cover[:] = False
            mine = by_touch | by_box | by_cover
            if mine.any():
                charged[site] = np.flatnonzero(mine)
                how[site] = {"touched": int(by_touch.sum()), "box": int(by_box.sum()), "cover": int(by_cover.sum())}
                hit_any |= mine
        return Attribution(charged=charged, how=how, unknown=np.flatnonzero(~hit_any))

    # -- the check ---------------------------------------------------------------------------------------------
    def check(self, after: MeshData, focus: Focus) -> SiteVerdict:
        """Run the Validator on `after` against the stage's BEFORE with `focus`."""
        st = self.stage
        t0 = time.perf_counter()
        settings = Settings(**{**self.settings.as_dict(), "max_sites": 1 << 30})   # every failing sample, grouped
        v = validate(st.before, after, self.looks, settings=settings, focus=focus)
        failing = set()
        first = {}
        for i, f in enumerate(v.samples.face.tolist()):
            first.setdefault(f, i)
        for members in v.members:
            for i in members.tolist():
                f = int(v.samples.face[i])
                failing.add((f, i - first[f]))
        r = v.report
        t, g = r["checks"]["textures"], r["checks"]["nothing_deleted"]
        summary = {"status": r["focus"]["status"], "before_faces": r["focus"]["before_faces"],
                   "after_faces": r["focus"]["after_faces"],
                   "textures": {"samples": t["samples"], "samples_failed": t["samples_failed"],
                                "reasons": t["reasons"]},
                   "nothing_deleted": {k: g[k] for k in ("samples", "samples_extra", "deleted", "replaced",
                                                         "covered", "overlaid")},
                   "sites": [{k: s[k] for k in ("centre", "size", "samples", "checks", "reasons", "faces")}
                             for s in r["sites"][:5]],
                   "sites_total": r["sites_total"]}
        seconds = time.perf_counter() - t0
        self.seconds["check"] += seconds
        self.calls += 1
        return SiteVerdict(failing=frozenset(failing), summary=summary, seconds=seconds,
                           samples=_failing_samples(v, first))


def _failing_samples(v, first: dict) -> FailingSamples:
    """The failing samples of the Validation `v` (all of them are in its sites: `max_sites` is unbounded), with the
    viewpoint that judged each (`Validation.wit_col`: a column of the standard directions, cameras and probes, or
    of the extra directions when `wit_extra`)."""
    if not v.members:
        return _no_samples()
    idx = np.concatenate([np.asarray(m, dtype=np.int64) for m in v.members])
    cluster = np.concatenate([np.full(len(m), k, dtype=np.int64) for k, m in enumerate(v.members)])
    face = v.samples.face[idx].astype(np.int64)
    index = idx - np.array([first[int(f)] for f in face.tolist()], dtype=np.int64)
    point = v.samples.points[idx] + v.centre
    col, extra = v.wit_col[idx].astype(np.int64), v.wit_extra[idx].astype(bool)
    vp = v.viewpoints
    dirs, extra_dirs = np.asarray(vp["dirs"], float).reshape(-1, 3), np.asarray(vp["extra_dirs"], float).reshape(-1, 3)
    eyes = np.vstack([np.asarray(vp["cams"], float).reshape(-1, 3), np.asarray(vp["probes"], float).reshape(-1, 3)])
    if (col < 0).any():
        raise RuntimeError("a failing sample without a judging viewpoint: the Validator tests every sample it fails")
    is_dir = extra | (col < len(dirs))
    witness = np.empty((len(idx), 3))
    witness[extra] = -extra_dirs[col[extra]]
    std = ~extra & is_dir
    witness[std] = -dirs[col[std]]
    eye = ~is_dir
    witness[eye] = eyes[col[eye] - len(dirs)] + v.centre
    clusters = [dict(s["reasons"]) for s in v.report["sites"]]
    return FailingSamples(face=face, index=index, point=point, witness=witness, is_dir=is_dir, cluster=cluster,
                          clusters=clusters)


def _segments_meet_boxes(points: np.ndarray, witness: np.ndarray, is_dir: np.ndarray, lo: np.ndarray,
                         hi: np.ndarray, *, back: float) -> np.ndarray:
    """(n,) bool: the line of sight of each sample meets some box `[lo, hi]` (k, 3). The line runs from `back`
    behind the sample (away from its viewer) to the viewer: for a direction (`is_dir`, `witness` the unit vector
    toward the viewer) without end, for a camera or probe (`witness` its position) up to it, plus `back`. A slab
    test per axis, exact for the boxes, with a relative slack so float rounding never drops a pair."""
    n, k = len(points), len(lo)
    out = np.zeros(n, dtype=bool)
    if not n or not k:
        return out
    u = np.where(is_dir[:, None], witness, witness - points)
    reach = np.where(is_dir, np.inf, np.linalg.norm(u, axis=1))
    u = u / np.maximum(np.linalg.norm(u, axis=1), 1e-12)[:, None]
    step = max(1, _SEGMENT_PAIRS // k)
    for a in range(0, n, step):
        p, d = points[a:a + step, None, :], u[a:a + step, None, :]               # (m, 1, 3)
        with np.errstate(divide="ignore", invalid="ignore"):
            t1, t2 = (lo[None] - p) / d, (hi[None] - p) / d                         # (m, k, 3)
        flat = d == 0.0
        inside = (p >= lo[None] - 1e-9) & (p <= hi[None] + 1e-9)
        t_in = np.where(flat, np.where(inside, -np.inf, np.inf), np.minimum(t1, t2)).max(axis=2)
        t_out = np.where(flat, np.where(inside, np.inf, -np.inf), np.maximum(t1, t2)).min(axis=2)
        slack = 1e-9 * (1.0 + np.abs(np.where(np.isfinite(t_in), t_in, 0.0)))
        start = np.maximum(t_in, -back)
        end = np.minimum(t_out, (reach[a:a + step] + back)[:, None])
        out[a:a + step] = (start <= end + slack).any(axis=1)
    return out


def _boxes(tri: np.ndarray, most: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """`(lo, hi)` boxes that together hold every triangle of `tri` (k, 3, 3): the faces split at the median of their
    centres along the longest axis of their spread, while there are at most `most` boxes and a box has more than
    one face. Each box is the bounding box of its own faces' corners, so every face lies wholly in one box."""
    groups = [np.arange(len(tri))]
    centre = tri.mean(axis=1)
    while len(groups) * 2 <= most:
        split = []
        for g in groups:
            if len(g) < 2:
                split.append(g)
                continue
            c = centre[g]
            axis = int(np.argmax(c.max(axis=0) - c.min(axis=0)))
            order = g[np.argsort(c[:, axis], kind="stable")]
            split += [order[: len(order) // 2], order[len(order) // 2:]]
        if len(split) == len(groups):
            break
        groups = split
    return [(tri[g].reshape(-1, 3).min(axis=0), tri[g].reshape(-1, 3).max(axis=0)) for g in groups if len(g)]


def _meets_shadow(face_lo: np.ndarray, face_hi: np.ndarray, lo: np.ndarray, hi: np.ndarray, *,
                  dirs: np.ndarray | None = None, eyes: np.ndarray | None = None) -> np.ndarray:
    """(F,) bool: the box `[face_lo, face_hi]` of each face meets the shadow of the box `[lo, hi]` for SOME viewpoint
    of the block -- exactly, as boxes.

    * A direction `d` (a viewer far off at `-d`, looking along `+d`): the box swept along `+d`, `{x + t d : x in box,
      t >= 0}`. A face box A meets it when `A - t d` meets the box for some `t >= 0`.
    * A camera or probe at `e`: the cone from `e` through the box and beyond, `{e + s (x - e) : x in box, s >= 1}`.
      A face box A meets it when the box `e + u (A - e)` meets the box for some `u` in `[0, 1]` (`u = 1 / s`; at
      `u = 0`, an eye inside the box, every face is a candidate).

    Either way each axis gives two linear conditions `c t <= r` on the one parameter, solved as an interval; a
    relative slack on `r` keeps float rounding from ever dropping a face."""
    n_faces = len(face_lo)
    if dirs is not None:
        v = np.asarray(dirs, dtype=np.float64)[:, None, :]                            # (V, 1, 3)
        shape = (v.shape[0], n_faces, 3)
        # A.lo - t d <= hi  ->  -d t <= hi - A.lo ;   A.hi - t d >= lo  ->  d t <= A.hi - lo
        c = np.concatenate([np.broadcast_to(-v, shape), np.broadcast_to(v, shape)], axis=2)
        r = np.concatenate([np.broadcast_to(hi - face_lo, shape), np.broadcast_to(face_hi - lo, shape)], axis=2)
        t_lo, t_hi = 0.0, np.inf
    else:
        e = np.asarray(eyes, dtype=np.float64)[:, None, :]                             # (V, 1, 3)
        shape = (e.shape[0], n_faces, 3)
        # e + u (A.lo - e) <= hi  ->  (A.lo - e) u <= hi - e ;   e + u (A.hi - e) >= lo  ->  -(A.hi - e) u <= e - lo
        c = np.concatenate([face_lo[None] - e, -(face_hi[None] - e)], axis=2)
        r = np.concatenate([np.broadcast_to(hi - e, shape), np.broadcast_to(e - lo, shape)], axis=2)
        t_lo, t_hi = 0.0, 1.0
    r = r + 1e-9 * (1.0 + np.abs(r))
    with np.errstate(divide="ignore", invalid="ignore"):
        bound = r / c
    upper = np.where(c > 0.0, bound, np.inf).min(axis=2)
    lower = np.where(c < 0.0, bound, -np.inf).max(axis=2)
    impossible = ((c == 0.0) & (r < 0.0)).any(axis=2)
    return (~impossible & (np.maximum(lower, t_lo) <= np.minimum(upper, t_hi))).any(axis=0)
