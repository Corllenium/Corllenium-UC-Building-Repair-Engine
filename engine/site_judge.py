"""The Validator, wired for the repair kernel's site checks (job P1-K3).

After each repair stage the kernel (`engine.repair.kernel.repair_unit(..., validate_sites=True)`) asks "did these
sites break anything, and which?". This module answers with the Validator itself (`engine.validate.checks.validate`
in its focus mode), so the kernel never judges its own work:

* `SiteJudge.begin(before)` takes a stage's input (the BEFORE of every check of that stage) once: its frame, the
  Validator's standard viewpoints (directions, the pedestrian ring and the eye-height probes) and the faces' boxes;
* `SiteJudge.focus(after, touched, new)` is the focus of a set of edits: in BEFORE, the faces they remove, flip or
  replace (`touched`), every face within their bounding box grown by `margin`, and the COVER CANDIDATES -- every
  face that could lie behind one of their new faces, or within the depth tolerance of one, from some standard
  viewpoint or probe (what the Validator's own "covered" and "overlaid" tests look at); in AFTER, the new faces
  (`new`: added, cut or flipped). `site_focus` keeps those parts apart (a `SiteFocus`), `union` joins sites;
* `SiteJudge.check(after, focus)` runs the focus validation and returns a `SiteVerdict`: the failing samples
  (so a check can be compared with a baseline), each with its point and the viewpoint that judged it, and the
  Validator's reasons, for the edit log;
* `SiteJudge.attribute(verdict, sites)` (P1-K3b) charges each failing sample to the sites that could have caused
  it; one charged to none is unknown. The kernel runs ONE focus run per stage on the union of its sites, rolls the
  charged sites back and confirms, instead of bisecting by repeated runs (ruling K3-R2).

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

THE CANDIDATE SET IS DELIBERATELY LARGE: that is the price of being conservative. From 128 directions and a ring of
cameras, and from every eye-height probe inside the floor, the shadows of even a few small boxes reach most of a
floor (on CHTM 5th a 10-face site has all 20,599 faces as candidates). A focus run is then about as costly as a full
run, and that is accepted (ruling K3-R2); what keeps a failure from being blamed on the wrong site is not this set
but `SiteJudge.attribute`, which charges a cover candidate to a site only when one of the site's new faces lies on
the line from the sample to the viewpoint that judged it.

THE CULL (P1-K3b). The per-viewpoint test is exact and cheap per pair, but every BEFORE face against every
viewpoint is a lot of pairs (about 700 s and 900 MB on the largest unit, 142k faces and 3,953 viewpoints). Two
culls cut it without changing the result: BEFORE's faces are sorted into a grid of cells, each cell's box the union
of its faces' boxes (grown a hair), and a face is tested against a viewpoint only when its cell's box meets that
viewpoint's shadow (a cell box holds its faces' boxes, so a face whose box meets the shadow is in a cell whose box
does); and a face already found is never tested again. Every block of work is sized to `_BLOCK_BYTES`.

WHAT THE COVER STEP LEAVES OUT, AND WHY THAT IS SAFE. It uses the standard viewpoints only, not the 1,024 extra
directions: the Validator casts those only for samples of SUSPECT faces (faces of BEFORE that AFTER no longer has),
and while AFTER is the stage input plus THIS site's edits, the suspect faces are exactly the site's touched faces,
which are in the focus already. When AFTER also carries other edits (another site's, kept earlier), their touched
faces are suspect too and are NOT in this focus: a cover of such a face is not looked at here. The kernel's union
focus (P1-K3b) holds every site's touched faces, and a failing sample of one is charged to the site that touched it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from engine.model import MeshData
from engine.validate.checks import FillSite, Focus, Looks, Settings, depth_tolerance, print_step, validate
from engine.validate.sampling import Samples, face_samples, recentred, used_bbox
from engine.validate.viewpoints import interior_probes, outside_directions, pedestrian_ring
from engine.validate.visibility import EPS_ORIGIN, build_caster, visible_samples

#: Slack, in inches, on top of the depth tolerance and `EPS_ORIGIN` round the new faces' boxes.
_SLACK = 0.01
#: The new faces are held in at most this many boxes (a split along the longest axis at the median, twice).
_MAX_BOXES = 4
#: Memory one block of the cover step may take, in bytes (P1-K3b: at most 500 MB per block).
_BLOCK_BYTES = 256 * 2**20
#: Arrays of a block's (pairs x 6) float64 size alive at once in `_shadow_core`, for sizing the blocks.
_LIVE = 8
#: The cull's grid holds about this many BEFORE faces per cell.
_PER_CELL = 32
#: Each cell's box is grown by this much (inches) so float rounding can never cull a face the exact test keeps.
_CELL_GROW = 1e-6

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
    grid: "_Grid | None" = None
    timings: dict = field(default_factory=dict)


@dataclass
class _Grid:
    """BEFORE's faces sorted into cells: `order[start[c]:start[c] + count[c]]` are cell `c`'s faces, `cell[f]` is
    face `f`'s cell, and `[lo[c], hi[c]]` holds the boxes of all of them (grown by `_CELL_GROW`)."""
    order: np.ndarray
    start: np.ndarray
    count: np.ndarray
    cell: np.ndarray
    lo: np.ndarray
    hi: np.ndarray


def _face_grid(face_lo: np.ndarray, face_hi: np.ndarray) -> _Grid:
    """About `_PER_CELL` faces per cell, the cells as near cubes over the spread of the faces' centres."""
    n = len(face_lo)
    centre = (face_lo + face_hi) / 2.0
    low, span = centre.min(axis=0), np.ptp(centre, axis=0)
    size = (np.prod(np.maximum(span, 1e-9)) / max(n / _PER_CELL, 1.0)) ** (1.0 / 3.0)
    dims = np.clip(np.ceil(span / max(size, 1e-9)), 1, 256).astype(np.int64)
    ijk = np.minimum(((centre - low) / np.maximum(span, 1e-12) * dims).astype(np.int64), dims - 1)
    key = (ijk[:, 0] * dims[1] + ijk[:, 1]) * dims[2] + ijk[:, 2]
    _, cell = np.unique(key, return_inverse=True)
    cell = cell.reshape(-1).astype(np.int64)
    count = np.bincount(cell)
    order = np.argsort(cell, kind="stable").astype(np.int64)
    start = np.concatenate([[0], np.cumsum(count)[:-1]]).astype(np.int64)
    lo = np.full((len(count), 3), np.inf)
    hi = np.full((len(count), 3), -np.inf)
    np.minimum.at(lo, cell, face_lo)
    np.maximum.at(hi, cell, face_hi)
    return _Grid(order=order, start=start, count=count, cell=cell, lo=lo - _CELL_GROW, hi=hi + _CELL_GROW)


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
        if before.n_faces:
            self._stage.grid = _face_grid(self._stage.face_lo, self._stage.face_hi)
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
        box holding new faces (see the module docstring). A superset of the faces those new faces can cover --
        deliberately a large one, the price of being conservative (most of a floor, as a rule)."""
        st = self.stage
        new = np.unique(np.asarray(new, dtype=np.int64))
        if not len(new) or not st.before.n_faces:
            return np.zeros(0, dtype=np.int64)
        t0 = time.perf_counter()
        grow = st.tol + EPS_ORIGIN + _SLACK
        found = np.zeros(st.before.n_faces, dtype=bool)
        for lo, hi in _boxes(after.positions[after.face_v[new]], _MAX_BOXES):
            for which, views in (("dirs", st.dirs), ("eyes", st.viewpoints)):
                _cover_pass(st, found, lo - grow, hi + grow, which, np.asarray(views, dtype=np.float64))
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
        rays start that far off the face) and a little slack.

        REMOVE-ONLY SITES (ruling E3-R8, job P2-E3). A site with no new faces (every edit of it a `remove`: an add,
        cut or flip always brings new faces) can delete only its own faces' samples, so a `deleted` sample is charged
        to it only when the sample lies on a face it touched -- never through its grown box. The Validator gives its
        reasons per cluster of failing samples (`FailingSamples.clusters`), not per sample, so a sample counts as
        `deleted` when every reason of its cluster is `deleted`; a sample of a mixed cluster, and every other kind
        (covered, look, uv, ...), keeps the conservative attribution above."""
        s = verdict.samples
        grow = self.stage.tol + EPS_ORIGIN + _SLACK
        charged, how = {}, {}
        hit_any = np.zeros(len(s), dtype=bool)
        only_deleted = np.array([bool(c) and set(c) <= {"deleted"} for c in s.clusters], dtype=bool)
        deleted = only_deleted[s.cluster] if len(s) else np.zeros(0, dtype=bool)
        for site in sorted(sites):
            f = sites[site]
            by_touch = np.isin(s.face, f.touched)
            by_box = ~by_touch & np.isin(s.face, f.near)
            if not len(f.new):
                by_box &= ~deleted                    # ruling E3-R8: a removal deletes only its own faces' samples
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

    # -- what the eye-height probes see (P2-E3) -----------------------------------------------------------------
    def probe_seen(self, mesh: MeshData, faces) -> np.ndarray:
        """Per face of `faces` (ids of `mesh`): how many of its samples some eye-height probe sees, from its front or
        its back. The hidden-face engine E3's pre-filter (ruling E3-R4: never room surfaces), with the Validator's own
        means: the probes placed on `mesh` exactly as `begin` places them on a BEFORE (`interior_probes` at this
        judge's settings), the samples at the Validator's density (`face_samples`), and "sees" as the Validator casts
        it (`visible_samples`: the segment from the sample, stepped off its face toward the probe, is clear). It
        changes nothing in the judge's state and never stands in for a check: the site checks still judge E3."""
        faces = np.asarray(faces, dtype=np.int64)
        out = np.zeros(len(faces), dtype=np.int64)
        if not len(faces) or not mesh.n_faces:
            return out
        s = self.settings
        b, _ = recentred(mesh)
        caster = build_caster(b)
        probes = interior_probes(b, eye=s.eye, caster=caster)
        if not len(probes):
            return out
        samples = face_samples(b, faces=np.unique(faces), min_per_face=s.min_per_face,
                               area_per_sample=s.area_per_sample)
        none = np.zeros((0, 3))
        seen = np.zeros(len(samples), dtype=bool)
        chunk = max(1, int(s.chunk))
        for start in range(0, len(samples), chunk):
            part = slice(start, min(start + chunk, len(samples)))
            sub = Samples(points=samples.points[part], face=samples.face[part], bary=samples.bary[part])
            seen[part] = visible_samples(b, sub, none, none, probes, caster).seen.any(axis=1)
        return np.bincount(samples.face[seen], minlength=mesh.n_faces)[faces].astype(np.int64)

    def lattice_seen(self, mesh: MeshData, faces, points_per_face: int) -> dict:
        """Per face of `faces` (ids of `mesh`): how many points of a DENSE lattice on it some viewpoint of the
        Validator's sees, from its front or its back -- `"outside"` (the standard directions, the extra directions
        and the ring of cameras), `"probes"` (the eye-height probes) and `"any"`. The hidden-face engine E3's dense
        pre-filter (ruling E3-R7): the Validator samples a face at about one point per `area_per_sample` (at least
        `min_per_face`), and a part of a face seen through an opening between those samples passes its check unseen
        (measured on CHTM 5th, face 8480). The lattice is the Validator's own equal-area one (`face_samples`) with
        `points_per_face` points on every face whatever its size (a square: 36 is the 6 x 6 lattice), so the points
        are spread evenly over each face's area; the viewpoints are placed on `mesh` exactly as `begin` places them,
        plus the extra directions the Validator casts for faces that are gone. Changes nothing in the judge's state."""
        faces = np.asarray(faces, dtype=np.int64)
        out = {k: np.zeros(len(faces), dtype=np.int64) for k in ("outside", "probes", "any")}
        if not len(faces) or not mesh.n_faces:
            return out
        side = int(round(float(points_per_face) ** 0.5))
        if side < 1 or side * side != int(points_per_face):
            raise ValueError(f"points_per_face must be a square (the n x n lattice), got {points_per_face}")
        s = self.settings
        b, _ = recentred(mesh)
        caster = build_caster(b)
        lo, hi = used_bbox(b)
        cams = pedestrian_ring((lo, hi), eye_z=lo[2] + s.eye, n=s.n_cameras, margin=s.camera_margin)
        probes = interior_probes(b, eye=s.eye, caster=caster)
        dirs = np.vstack([outside_directions(s.n_directions), outside_directions(s.n_extra_directions)])
        ids = np.unique(faces)
        # the smallest n x n lattice reaching `points_per_face` on every face: no area term (an infinite area per sample)
        samples = face_samples(b, faces=ids, min_per_face=int(points_per_face), area_per_sample=float("inf"))
        n_out = len(dirs) + len(cams)
        seen = {k: np.zeros(len(samples), dtype=bool) for k in ("outside", "probes")}
        chunk = max(1, int(s.chunk))
        for start in range(0, len(samples), chunk):
            part = slice(start, min(start + chunk, len(samples)))
            sub = Samples(points=samples.points[part], face=samples.face[part], bary=samples.bary[part])
            vs = visible_samples(b, sub, dirs, cams, probes, caster)
            seen["outside"][part] = vs.seen[:, :n_out].any(axis=1)
            seen["probes"][part] = vs.seen[:, n_out:].any(axis=1)
        seen["any"] = seen["outside"] | seen["probes"]
        return {k: np.bincount(samples.face[v], minlength=mesh.n_faces)[faces].astype(np.int64)
                for k, v in seen.items()}

    # -- the check ---------------------------------------------------------------------------------------------
    def check(self, after: MeshData, focus: Focus, fills=None) -> SiteVerdict:
        """Run the Validator on `after` against the stage's BEFORE with `focus`. `fills` (P2-E8b): the flat fills
        the edit log marks, `{"faces": AFTER face ids, "loop": (n, 3) points}` each, for the `fill_site` class."""
        st = self.stage
        t0 = time.perf_counter()
        settings = Settings(**{**self.settings.as_dict(), "max_sites": 1 << 30})   # every failing sample, grouped
        marks = [FillSite(faces=f["faces"], loop=f["loop"]) for f in fills] if fills else None
        v = validate(st.before, after, self.looks, settings=settings, focus=focus, fills=marks)
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
                                                         "covered", "overlaid", "covered_by_fill") if k in g},
                   "sites": [{k: s[k] for k in ("centre", "size", "samples", "checks", "reasons", "faces")}
                             for s in r["sites"][:5]],
                   "sites_total": r["sites_total"], "fill_sites": r.get("fill_sites", [])}
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


def _cover_pass(st: _Stage, found: np.ndarray, lo: np.ndarray, hi: np.ndarray, which: str, views: np.ndarray) -> None:
    """`found |=` every BEFORE face whose box meets the shadow of `[lo, hi]` from some viewpoint of `views`
    (`which`: "dirs" or "eyes"), testing a (viewpoint, face) pair only when the face is not found yet and its
    cell's box meets that viewpoint's shadow. Exactly `_meets_shadow` over every face and viewpoint."""
    g = st.grid
    if not len(views) or g is None:
        return
    pair_bytes = 6 * 8 * _LIVE
    per_block = max(1, _BLOCK_BYTES // (pair_bytes * len(g.count)))       # viewpoints x cells in one cell pass
    chunk = max(1, _BLOCK_BYTES // (pair_bytes + 8 * 6))                   # (viewpoint, face) pairs in one test
    for k in range(0, len(views), per_block):
        cells = np.flatnonzero(np.bincount(g.cell[~found], minlength=len(g.count)) > 0)
        if not len(cells):
            return
        block = views[k:k + per_block]
        meet = _shadow_matrix(g.lo[cells], g.hi[cells], lo, hi, **{which: block})          # (views, cells)
        v_of, c_of = np.nonzero(meet)
        c_of = cells[c_of]
        sizes = g.count[c_of]
        ends = np.cumsum(sizes)
        first = 0
        while first < len(c_of):
            last = max(first + 1, int(np.searchsorted(ends, (ends[first - 1] if first else 0) + chunk, side="right")))
            v, c, n = v_of[first:last], c_of[first:last], sizes[first:last]
            offset = np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n)
            faces = g.order[np.repeat(g.start[c], n) + offset]
            views_of = np.repeat(v, n)
            todo = ~found[faces]
            faces, views_of = faces[todo], views_of[todo]
            if len(faces):
                hit = _shadow_pairs(st.face_lo[faces], st.face_hi[faces], lo, hi, which, block[views_of])
                found[faces[hit]] = True
            first = last


def _shadow_core(c: np.ndarray, r: np.ndarray, t_lo: float, t_hi: float) -> np.ndarray:
    """The interval test over the last axis (six linear conditions `c t <= r` on one parameter `t` in
    `[t_lo, t_hi]`), with a relative slack on `r` so float rounding never drops a face."""
    r = r + 1e-9 * (1.0 + np.abs(r))
    with np.errstate(divide="ignore", invalid="ignore"):
        bound = r / c
    upper = np.where(c > 0.0, bound, np.inf).min(axis=-1)
    lower = np.where(c < 0.0, bound, -np.inf).max(axis=-1)
    impossible = ((c == 0.0) & (r < 0.0)).any(axis=-1)
    return ~impossible & (np.maximum(lower, t_lo) <= np.minimum(upper, t_hi))


def _shadow_pairs(face_lo: np.ndarray, face_hi: np.ndarray, lo: np.ndarray, hi: np.ndarray, which: str,
                  views: np.ndarray) -> np.ndarray:
    """(P,) bool: face box `[face_lo[i], face_hi[i]]` meets the shadow of `[lo, hi]` from viewpoint `views[i]`; the
    same conditions as `_shadow_matrix`, one pair per row."""
    if which == "dirs":
        c = np.concatenate([-views, views], axis=1)
        r = np.concatenate([hi - face_lo, face_hi - lo], axis=1)
        return _shadow_core(c, r, 0.0, np.inf)
    c = np.concatenate([face_lo - views, -(face_hi - views)], axis=1)
    r = np.concatenate([hi - views, views - lo], axis=1)
    return _shadow_core(c, r, 0.0, 1.0)


def _shadow_matrix(face_lo: np.ndarray, face_hi: np.ndarray, lo: np.ndarray, hi: np.ndarray, *,
                   dirs: np.ndarray | None = None, eyes: np.ndarray | None = None) -> np.ndarray:
    """(V, F) bool: `_meets_shadow` for each viewpoint of the block separately."""
    n_faces = len(face_lo)
    if dirs is not None:
        v = np.asarray(dirs, dtype=np.float64)[:, None, :]                            # (V, 1, 3)
        shape = (v.shape[0], n_faces, 3)
        c = np.concatenate([np.broadcast_to(-v, shape), np.broadcast_to(v, shape)], axis=2)
        r = np.concatenate([np.broadcast_to(hi - face_lo, shape), np.broadcast_to(face_hi - lo, shape)], axis=2)
        return _shadow_core(c, r, 0.0, np.inf)
    e = np.asarray(eyes, dtype=np.float64)[:, None, :]                                 # (V, 1, 3)
    shape = (e.shape[0], n_faces, 3)
    c = np.concatenate([face_lo[None] - e, -(face_hi[None] - e)], axis=2)
    r = np.concatenate([np.broadcast_to(hi - e, shape), np.broadcast_to(e - lo, shape)], axis=2)
    return _shadow_core(c, r, 0.0, 1.0)


def _meets_shadow(face_lo: np.ndarray, face_hi: np.ndarray, lo: np.ndarray, hi: np.ndarray, *,
                  dirs: np.ndarray | None = None, eyes: np.ndarray | None = None) -> np.ndarray:
    """(F,) bool: the box `[face_lo, face_hi]` of each face meets the shadow of the box `[lo, hi]` for SOME viewpoint
    of the block -- exactly, as boxes.

    * A direction `d` (a viewer far off at `-d`, looking along `+d`): the box swept along `+d`, `{x + t d : x in box,
      t >= 0}`. A face box A meets it when `A - t d` meets the box for some `t >= 0`.
    * A camera or probe at `e`: the cone from `e` through the box and beyond, `{e + s (x - e) : x in box, s >= 1}`.
      A face box A meets it when the box `e + u (A - e)` meets the box for some `u` in `[0, 1]` (`u = 1 / s`; at
      `u = 0`, an eye inside the box, every face is a candidate).

    Either way each axis gives two linear conditions `c t <= r` on the one parameter, solved as an interval
    (`_shadow_core`); a relative slack on `r` keeps float rounding from ever dropping a face.

    Directions: `A.lo - t d <= hi` -> `-d t <= hi - A.lo`; `A.hi - t d >= lo` -> `d t <= A.hi - lo`.
    Eyes: `e + u (A.lo - e) <= hi` -> `(A.lo - e) u <= hi - e`; `e + u (A.hi - e) >= lo` -> `-(A.hi - e) u <= e - lo`.
    """
    return _shadow_matrix(face_lo, face_hi, lo, hi, dirs=dirs, eyes=eyes).any(axis=0)
