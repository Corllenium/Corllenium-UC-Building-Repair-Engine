"""E3, hidden faces, interior-aware (job P2-E3): the legacy hidden stage as a strict repair engine.

THE CANDIDATES ARE THE LEGACY ONES (ruling E3-R1). `E3Hidden.plan` runs `engine.fixes.pipeline.stage_hidden`
UNCHANGED on its stage input, taken as the reference mesh (the input when solidify does not run: `stage_solidify`
with `solidify=False`; E8a, run before E3, has already closed what it could). Pass 1 of that stage is the legacy
candidate set: every face `compute_side_exposure` / `classify_exposure` call HIDDEN (exposure 0 on both sides from
every outside direction) and every zero-area face (`~topo.ok`), confirmed by the strict `guard_feedback` against the
input; the faces it gives back stay. When E8a ran first (`solidify`), the input faces its cap guard let a new face
cover only through rule 6 (`SolidifyResult.seen_through_shell`) are left out too, by K1 face key, as the legacy
stage leaves them out of the solidified reference.

THEN THESE RULES TAKE FACES OUT, before the judge runs:
- E3-R9, NEVER ZERO-AREA FACES (fix round 1). A zero-area face (`~topo.ok`) belongs to E1 (debris and zero-area): the
  legacy pass 1 removes it with the hidden ones, E3 leaves it (`report["excluded"]["zero_area"]`).
- E3-R3, NEVER SIDE MESHES. A face is a slab side when solidify, run on the stage input as a measurement only (its
  output is thrown away), takes it as one (`SolidifyResult.side_faces`: an own side of a top it plans -- a side face,
  `|n_z| <= top_min_nz`, with an edge along the top's outline -- or a piece it finds in the side band under one of
  that top's outline edges, whole side or broken), or when no OBJ row holds it (`face_line < 0`: solidify's own mark
  for a face it invented, which every E8 add carries -- a wall or bottom E8a built, or an E8b fill).
- E3-R4, NEVER ROOM SURFACES. A face some eye-height probe sees, from its front or its back, is no candidate
  (`probe_view`; by default the site judge's `SiteJudge.probe_seen`, the Validator's own probes and visibility, so
  this package still imports nothing of `engine/validate`). The cheap pre-filter: the judge is the safety net.
- E3-R7, THE DENSE PRE-FILTER (fix round 1). The judge samples a face at about one point per 36 sq in (at least 4),
  and a part of a face seen through an opening between those samples passes it unseen (measured on CHTM 5th: face
  8480, 290.87 sq in, 9 samples none of them seen, yet about 4.8 sq in of it seen from outside). So every face still a
  candidate is tested on a lattice of `DENSE_POINTS_PER_FACE` (36) points spread evenly over its area against EVERY
  viewpoint of the Validator's -- the standard and the extra outside directions, the ring cameras and the eye-height
  probes, from either side (`dense_view`; by default the site judge's `SiteJudge.lattice_seen`). A face any point of
  which is seen is no candidate; `report["dense_excluded"]` names each.

ONE SITE PER EDGE-CONNECTED GROUP of what is left (faces sharing an edge of the welded topology, within the
candidate set). A group over `MAX_SITE_FACES` (512) faces is split by a spatial grid over its faces' centroids
(`split_group`), so one visible face cannot roll back a whole storey's interior. Each site is one `remove` edit,
labelled E3, judged by the kernel's site checks (`validate_sites=True`):
a site whose removal deletes any sample some viewpoint sees -- outside directions, ring cameras, eye-height probes,
and the 1,024 extra directions the Validator casts for faces that are gone -- is rolled back (ruling E3-R2).

NO SECOND OPINION (E3-R5). Where exposure calls a face hidden and a probe sees it, `report["disagreements"]` lists
it, for a later job (a winding-number test needs the owner's OK to install).

`evidence` of an edit: `group` (its connected group), `cell` (its grid cell, None when the group was not split),
`group_faces`, `faces`, `area` (sq in), `exposure` (`front_max`, `back_max` over its faces, from
`compute_side_exposure`), `rules` (per face, in `faces` order, the legacy rule that made it a candidate: "hidden",
the only one E3 takes since ruling E3-R9), `centroid` and `bbox` (model coordinates). `report` (the last run): the legacy counts, what each rule took
out, the candidates, groups and sites, the probe numbers and the disagreements.
"""
from __future__ import annotations

import dataclasses
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from engine.fixes.pipeline import stage_hidden, stage_solidify, start_fix
from engine.fixes.solidify import solidify
from engine.repair.types import Edit, RepairContext, UnitState, face_keys
from engine.vis.exposure import EXP_HIDDEN

#: The most faces one E3 site holds (ruling E3-R1): a bigger connected group is split by a spatial grid.
MAX_SITE_FACES = 512
DENSE_POINTS_PER_FACE = 36
#: How many disagreeing faces `report["disagreements"]["list"]` names (all are counted).
DISAGREEMENTS_LISTED = 1000
#: The slab-side rule, in words, for the report (ruling E3-R3).
SIDE_RULE = ("SolidifyResult.side_faces on the stage input (an own side of a top solidify plans, or a piece in the "
             "side band under one of its outline edges), or face_line < 0 (a face solidify invented)")


def _components(face_w: np.ndarray, ids: np.ndarray) -> list[np.ndarray]:
    """The edge-connected groups of the faces `ids` (sorted ascending): two faces are joined when they share an edge
    of the welded topology (`face_w`). Each group sorted, the groups ordered by their first face."""
    k = len(ids)
    if not k:
        return []
    tri = face_w[ids]
    edges = np.concatenate([np.sort(tri[:, [0, 1]], axis=1), np.sort(tri[:, [1, 2]], axis=1),
                            np.sort(tri[:, [2, 0]], axis=1)])
    owner = np.concatenate([np.arange(k)] * 3)
    real = edges[:, 0] != edges[:, 1]
    edges, owner = edges[real], owner[real]
    order = np.lexsort((edges[:, 1], edges[:, 0]))
    edges, owner = edges[order], owner[order]
    same = (edges[1:] == edges[:-1]).all(axis=1)
    parent = list(range(k))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in zip(owner[:-1][same].tolist(), owner[1:][same].tolist()):
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    roots = np.array([root(i) for i in range(k)])
    groups: dict[int, list[int]] = {}
    for i, r in enumerate(roots.tolist()):
        groups.setdefault(r, []).append(i)
    return [ids[np.array(g)] for _, g in sorted(groups.items())]


def split_group(ids: np.ndarray, centroid: np.ndarray, cap: int = MAX_SITE_FACES) -> list[np.ndarray]:
    """`ids` (face ids) in pieces of at most `cap` faces, by a spatial grid over their centroids (`centroid`, indexed
    by face id): about `ceil(len / cap)` cells of equal size over the axes the faces spread along, each cell still
    over `cap` split again the same way. Faces whose centroids do not spread (a stack in one spot) are cut in order.
    Deterministic: cells in ascending grid order, each cell's faces ascending."""
    ids = np.sort(np.asarray(ids, np.int64))
    if len(ids) <= cap:
        return [ids]
    pts = centroid[ids]
    lo, span = pts.min(axis=0), np.ptp(pts, axis=0)
    axes = span > 1e-9
    if not axes.any():
        return [ids[i:i + cap] for i in range(0, len(ids), cap)]
    cells = math.ceil(len(ids) / cap)
    size = (float(np.prod(span[axes])) / cells) ** (1.0 / int(axes.sum()))
    ijk = np.where(axes, np.floor((pts - lo) / max(size, 1e-12)), 0.0).astype(np.int64)
    keys, which = np.unique(ijk, axis=0, return_inverse=True)
    which = which.reshape(-1)
    if len(keys) == 1:
        # the grid did not separate them: cut along the longest axis, in order
        along = ids[np.argsort(pts[:, int(np.argmax(span))], kind="stable")]
        return [np.sort(along[i:i + cap]) for i in range(0, len(along), cap)]
    out: list[np.ndarray] = []
    for c in range(len(keys)):
        out.extend(split_group(ids[which == c], centroid, cap))
    return out


@dataclass
class E3Hidden:
    """The repair engine E3 (see the module docstring). `flatness` is the per-material texture std the pipeline reads
    its flat materials from; `solidify` the `E8Solidify` engine run before this one, if any (its `seen_through`
    record); `probe_view(mesh, faces)` gives per face how many of its samples an eye-height probe sees (None: the
    site judge's `probe_seen`, from `ctx.validator`); `dense_view(mesh, faces)` gives per face how many points of its
    `DENSE_POINTS_PER_FACE` lattice some viewpoint sees, as an array or as `{"any", "outside", "probes"}` arrays (None:
    the site judge's `lattice_seen`); `report` holds the last run's numbers."""
    flatness: dict = field(default_factory=dict)
    solidify: Any = None
    probe_view: Callable[[Any, np.ndarray], np.ndarray] | None = None
    dense_view: Callable[[Any, np.ndarray], Any] | None = None
    max_site_faces: int = MAX_SITE_FACES
    name: str = "E3"
    legacy: bool = False
    report: dict | None = field(default=None, repr=False)

    def _probe_view(self, ctx: RepairContext):
        if self.probe_view is not None:
            return self.probe_view
        view = getattr(ctx.validator, "probe_seen", None)
        if view is None:
            raise ValueError("E3 needs the eye-height probes (ruling E3-R4): give it a probe_view, or the site judge "
                             "in ctx.validator")
        return view

    def _dense_view(self, ctx: RepairContext):
        if self.dense_view is not None:
            return self.dense_view
        lattice = getattr(ctx.validator, "lattice_seen", None)
        if lattice is None:
            raise ValueError("E3 needs the dense pre-filter (ruling E3-R7): give it a dense_view, or the site judge in "
                             "ctx.validator")
        return lambda mesh, faces: lattice(mesh, faces, DENSE_POINTS_PER_FACE)

    def _through_shell(self, mesh, looks: dict) -> np.ndarray:
        """Bool over `mesh`'s faces: the faces E8a's cap guard let a new face cover only through rule 6, by key."""
        out = np.zeros(mesh.n_faces, bool)
        record = getattr(self.solidify, "seen_through", None)
        if record is None:
            return out
        source, mask = record
        if not np.asarray(mask, bool).any():
            return out
        flagged = {k for k, m in zip(face_keys(source, looks), np.asarray(mask, bool).tolist()) if m}
        return np.array([k in flagged for k in face_keys(mesh, looks)], dtype=bool)

    def plan(self, unit: UnitState, ctx: RepairContext) -> list[Edit]:
        started = time.perf_counter()
        mesh, profile = unit.mesh, ctx.profile
        view = self._probe_view(ctx)
        dense_view = self._dense_view(ctx)
        seconds: dict[str, float] = {}

        # ---- the legacy candidates: stage_hidden, unchanged, on the stage input as the reference
        t0 = time.perf_counter()
        state = stage_hidden(stage_solidify(start_fix(mesh, self.flatness,
                                                      dataclasses.replace(profile, solidify=False))))
        seconds["legacy_hidden"] = time.perf_counter() - t0
        if state.mesh is not mesh or state.mesh.n_faces != mesh.n_faces:
            raise ValueError("E3: the hidden stage's reference is not the stage input")
        topo = state.topo
        removed = np.asarray(state.removed_pass1, bool)
        ok = np.asarray(topo.ok, bool)
        exposure_hidden = np.asarray(state.exposure_class) == EXP_HIDDEN

        # ---- E3-R3: never side meshes (solidify's own side record, measured on the input; and invented faces)
        t0 = time.perf_counter()
        invented = np.asarray(mesh.face_line) < 0
        measured = solidify(mesh, state.topo_input, profile)
        side = np.zeros(mesh.n_faces, bool)
        if measured.side_faces is not None:
            side |= np.asarray(measured.side_faces, bool)
        through = self._through_shell(mesh, unit.looks)
        seconds["sides"] = time.perf_counter() - t0

        # ---- E3-R4: never room surfaces (what the eye-height probes see), and where they disagree with exposure
        t0 = time.perf_counter()
        looked = np.flatnonzero(removed | exposure_hidden)
        probe_samples = np.zeros(mesh.n_faces, np.int64)
        if len(looked):
            counts = np.asarray(view(mesh, looked), np.int64)
            if counts.shape != looked.shape:
                raise ValueError(f"E3: probe_view gave {counts.shape} values for {looked.shape} faces")
            probe_samples[looked] = counts
        seen = probe_samples > 0
        seconds["probes"] = time.perf_counter() - t0

        # E3-R9 (fix round 1): a zero-area face is E1's (debris and zero-area), never an E3 candidate
        excluded = {"zero_area": 0, "invented": 0, "side": 0, "seen_through_shell": 0, "probe": 0}
        left = removed.copy()
        for name, mask in (("zero_area", ~ok), ("invented", invented), ("side", side), ("seen_through_shell", through),
                           ("probe", seen)):
            hit = left & mask
            excluded[name] = int(hit.sum())
            left &= ~mask

        # ---- E3-R7: the dense pre-filter -- a point of a DENSE lattice on the face that any viewpoint of the
        # Validator's sees (outside directions, extra directions, ring cameras, eye-height probes, either side)
        t0 = time.perf_counter()
        tested = np.flatnonzero(left)
        dense = {k: np.zeros(mesh.n_faces, np.int64) for k in ("any", "outside", "probes")}
        if len(tested):
            got = dense_view(mesh, tested)
            got = got if isinstance(got, dict) else {"any": got}
            for k, values in got.items():
                values = np.asarray(values, np.int64)
                if values.shape != tested.shape:
                    raise ValueError(f"E3: dense_view gave {values.shape} values for {tested.shape} faces")
                dense[k][tested] = values
        dense_seen = left & (dense["any"] > 0)
        excluded["dense"] = int(dense_seen.sum())
        left &= ~dense_seen
        seconds["dense"] = time.perf_counter() - t0
        candidates = np.flatnonzero(left)

        # ---- sites: edge-connected groups, a big one split by a spatial grid
        positions = topo.positions_w
        tri = positions[topo.face_w]
        centroid = tri.mean(axis=1)
        area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
        front, back = np.asarray(state.front, float), np.asarray(state.back, float)
        groups = _components(topo.face_w, candidates)
        edits: list[Edit] = []
        split = 0
        for g, members in enumerate(groups):
            pieces = split_group(members, centroid, self.max_site_faces)
            split += int(len(pieces) > 1)
            for c, faces in enumerate(pieces):
                corners = mesh.positions[mesh.face_v[faces]].reshape(-1, 3)
                rules = ["hidden" if ok[f] else "zero_area" for f in faces.tolist()]
                evidence = {"group": g, "cell": c if len(pieces) > 1 else None, "group_faces": int(len(members)),
                            "faces": int(len(faces)), "area": round(float(area[faces].sum()), 4),
                            "exposure": {"front_max": float(front[faces].max()), "back_max": float(back[faces].max())},
                            "rules": rules,
                            "centroid": [round(float(v), 4) for v in mesh.positions[mesh.face_v[faces]]
                                         .reshape(-1, 3).mean(axis=0)],
                            "bbox": [[round(float(v), 4) for v in corners.min(axis=0)],
                                     [round(float(v), 4) for v in corners.max(axis=0)]]}
                edits.append(Edit(
                    engine="E3", kind="remove", faces=tuple(faces.tolist()), new_faces=None, new_points=None,
                    site=len(edits),
                    reason=(f"E3 hidden: {len(faces)} face(s) of connected group {g} ({len(members)} faces) that the "
                            f"legacy pass 1 removes (exposure 0 from every outside direction, confirmed by its strict "
                            f"guard); none of zero area (E1's), none a slab side, none "
                            f"seen by an eye-height probe, none seen at any point of its {DENSE_POINTS_PER_FACE}-point "
                            f"lattice"),
                    evidence=evidence))

        dis = np.flatnonzero(exposure_hidden & seen)
        self.report = {
            "legacy_candidates": int(removed.sum()),
            "legacy_removed": np.flatnonzero(removed).tolist(),
            "by_rule": {"hidden": int((removed & ok).sum()), "zero_area": int((removed & ~ok).sum())},
            "legacy": {"exposure_hidden": int(exposure_hidden.sum()),
                       "n_hidden_candidates": int(state.n_hidden_candidates),
                       "n_removed_hidden": int(state.n_removed_hidden),
                       "n_restored_by_guard": int(state.n_restored_by_guard),
                       "n_zero_area_dropped": int(state.n_zero_area_dropped),
                       "n_degenerate_restored": int(state.n_degenerate_restored)},
            "excluded": excluded,
            "side_rule": SIDE_RULE,
            "side_faces_measured": int(side.sum()),
            "candidates": int(len(candidates)),
            "groups": len(groups),
            "groups_split": split,
            "largest_group": max((len(g) for g in groups), default=0),
            "sites": len(edits),
            "probes": {"faces_looked_at": int(len(looked)), "faces_seen": int(seen[looked].sum())},
            "dense_lattice": DENSE_POINTS_PER_FACE,
            "dense_tested": int(len(tested)),
            "dense_excluded": [{"face": int(f), "points_seen": int(dense["any"][f]),
                                "outside": int(dense["outside"][f]), "probes": int(dense["probes"][f]),
                                "area": round(float(area[f]), 4),
                                "centroid": [round(float(v), 3) for v in mesh.positions[mesh.face_v[f]].mean(axis=0)]}
                               for f in np.flatnonzero(dense_seen).tolist()],
            "disagreements": {
                "faces": int(len(dis)),
                "removed_by_legacy": int(removed[dis].sum()),
                "rule": "exposure 0 from every outside direction (classify_exposure: hidden), yet an eye-height "
                        "probe sees a sample of the face",
                "list": [{"face": int(f), "probe_samples": int(probe_samples[f]),
                          "removed_by_legacy": bool(removed[f]),
                          "centroid": [round(float(v), 3) for v in
                                       mesh.positions[mesh.face_v[f]].mean(axis=0)]}
                         for f in dis[:DISAGREEMENTS_LISTED].tolist()]},
            "seconds": {**{k: round(v, 2) for k, v in seconds.items()},
                        "total": round(time.perf_counter() - started, 2)},
        }
        return edits
