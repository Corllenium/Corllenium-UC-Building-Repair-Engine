"""The Validator, wired for the repair kernel's site checks (job P1-K3).

After each repair stage the kernel (`engine.repair.kernel.repair_unit(..., validate_sites=True)`) asks, for a few
of the stage's edits at a time, "did these break anything?". This module answers with the Validator itself
(`engine.validate.checks.validate` in its focus mode), so the kernel never judges its own work:

* `SiteJudge.begin(before)` takes a stage's input (the BEFORE of every check of that stage) once: its frame, the
  Validator's standard viewpoints (directions, the pedestrian ring and the eye-height probes) and a ray caster;
* `SiteJudge.focus(after, touched, new)` is the focus of a set of edits: in BEFORE, the faces they remove, flip or
  replace (`touched`), every face within their bounding box grown by `margin`, and the COVER CANDIDATES -- the
  faces that lie behind one of their new faces from some standard viewpoint or probe, found by casting from
  each viewpoint through the new faces' sample points into BEFORE (what the Validator's own "covered" and
  "overlaid" tests look at); in AFTER, the new faces (`new`: added, cut or flipped);
* `SiteJudge.check(after, focus)` runs the focus validation and returns a `SiteVerdict`: the failing samples
  (so a check can be compared with a baseline) and the Validator's reasons, for the edit log.

Why this module is here, outside both packages: the Validator must import nothing it judges (`engine.repair`,
`engine.fixes`, `engine.guard`), and the repair package computes its own measures and never imports the
Validator (K1-R2). The kernel gets a `SiteJudge` through `RepairContext.validator`, made by `engine.cli`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from engine.model import MeshData
from engine.validate.checks import Focus, Looks, Settings, depth_tolerance, print_step, validate
from engine.validate.sampling import face_samples, recentred, used_bbox
from engine.validate.viewpoints import interior_probes, outside_directions, pedestrian_ring
from engine.validate.visibility import build_caster

#: Layers a cover-candidate ray looks through: every face within the depth tolerance of a new face's point
#: (coincident layers, which the overlay pass judges) and the first one beyond it (which the cover test judges).
_PEEL = 6
_PEEL_STEP = 1e-3

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
    caster: object
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
                             dirs=outside_directions(s.n_directions), caster=caster,
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
        """Sorted BEFORE face ids that lie behind (or on, within the depth tolerance) one of the AFTER faces `new`
        as some standard viewpoint or probe looks through it: the faces those new faces could cover."""
        st = self.stage
        new = np.asarray(new, dtype=np.int64)
        if not len(new) or st.caster is None:
            return np.zeros(0, dtype=np.int64)
        t0 = time.perf_counter()
        s = self.settings
        pts = face_samples(after, faces=new, min_per_face=s.min_per_face, area_per_sample=s.area_per_sample).points
        pts = pts - st.centre
        views = st.viewpoints - st.centre
        found = []
        back = st.tol + 2.0 * _PEEL_STEP
        for d in st.dirs:                                   # a viewer far off at -d, looking along +d
            found.append(self._peel(np.broadcast_to(d, pts.shape), pts, back))
        for v in views:
            ray = pts - v
            length = np.linalg.norm(ray, axis=1)
            ok = length > 1e-9
            if ok.any():
                found.append(self._peel(ray[ok] / length[ok, None], pts[ok], back))
        out = np.unique(np.concatenate(found)) if found else np.zeros(0, dtype=np.int64)
        self.seconds["cover"] += time.perf_counter() - t0
        return out[out >= 0]

    def _peel(self, dirn: np.ndarray, pts: np.ndarray, back: float) -> np.ndarray:
        """Faces hit along `pts + x dirn` from `x = -back` on: every layer up to `back` past the point, and the
        first one beyond."""
        st = self.stage
        dirn = np.ascontiguousarray(dirn, dtype=np.float64)
        cur = pts - back * dirn
        travelled = np.full(len(pts), -back)
        active = np.arange(len(pts))
        hits = []
        for _ in range(_PEEL):
            if not len(active):
                break
            tri, t = st.caster.first_hit(cur[active], dirn[active])
            hit = tri >= 0
            hits.append(tri[hit])
            depth = travelled[active] + np.where(hit, t, 0.0)
            again = hit & (depth <= back)                  # still within the new face's own layer: look past it
            nxt = active[again]
            cur[nxt] = cur[nxt] + (t[again] + _PEEL_STEP)[:, None] * dirn[nxt]
            travelled[nxt] = depth[again] + _PEEL_STEP
            active = nxt
        return np.concatenate(hits) if hits else np.zeros(0, dtype=np.int64)

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
