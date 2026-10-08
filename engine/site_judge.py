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


@dataclass
class SiteVerdict:
    """What one focus validation found. `failing`: the failing samples, each `(BEFORE face, sample index within
    the face)`; `summary`: the Validator's counts, reasons and worst sites, for `edit_log.jsonl`."""
    failing: frozenset
    summary: dict
    seconds: float = 0.0

    @property
    def failed(self) -> bool:
        return bool(self.failing)


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
        st = self.stage
        t0 = time.perf_counter()
        touched = np.unique(np.asarray(touched, dtype=np.int64))
        new = np.unique(np.asarray(new, dtype=np.int64))
        corners = [st.before.positions[st.before.face_v[touched]].reshape(-1, 3),
                   after.positions[after.face_v[new]].reshape(-1, 3)]
        corners = np.concatenate(corners)
        parts = [touched]
        if len(corners):
            lo, hi = corners.min(axis=0) - self.margin, corners.max(axis=0) + self.margin
            near = ((st.face_lo <= hi) & (st.face_hi >= lo)).all(axis=1)
            parts.append(np.flatnonzero(near))
        self.seconds["focus"] += time.perf_counter() - t0
        parts.append(self.cover_candidates(after, new))
        return Focus(before_faces=np.unique(np.concatenate(parts)).astype(np.int64), after_faces=new)

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
        return SiteVerdict(failing=frozenset(failing), summary=summary, seconds=seconds)


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
