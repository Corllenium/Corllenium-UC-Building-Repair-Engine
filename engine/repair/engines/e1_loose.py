"""E1, loose faces (job P2-E1): zero-area faces, stray fragments, slivers, folds.

Removes debris only when unseen from any viewpoint under the Validator floor rule (<= 4 px at 0.02 in/px).
Visible debris stays and is listed with a picture for review.
"""
from __future__ import annotations

import collections
import dataclasses
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from engine.detectors.folds import detect_folds
from engine.detectors.fragments import detect_fragments
from engine.fill_review import SpotCropper
from engine.fixes.pipeline import _fold_members, sliver_width_bound
from engine.model import MeshData
from engine.pipeline import analyse_topology
from engine.repair.engines.e3_hidden import _components, split_group
from engine.repair.types import Edit, RepairContext, UnitState, print_step
from engine.validate.checks import Looks, Settings
from engine.validate.floor import FLOOR_IN_PER_PX, VISIBLE_FLOOR_PX, Viewpoint, face_pixels, face_visible_pixels, floor_lattice
from engine.validate.sampling import recentred, used_bbox
from engine.validate.viewpoints import above_horizon_directions, interior_probes, pedestrian_ring
from engine.validate.visibility import build_caster, visible_samples

MAX_SITE_FACES = 512
MAX_ZERO_AREA_SITE = 64


def _face_visible_exceeds(mesh: MeshData, face: int, viewpoint: Viewpoint, caster, limit: float = VISIBLE_FLOOR_PX) -> float:
    """Early-exit visibility measurement: stops as soon as `limit` pixels are exceeded."""
    total = 0.0
    for block in face_pixels(mesh, face, viewpoint, caster, px=FLOOR_IN_PER_PX):
        total += block.count
        if total > limit:
            return total
    return total


def _build_default_viewpoints(mesh: MeshData, settings: Settings = Settings()) -> tuple[MeshData, list[Viewpoint]]:
    """Recentred mesh and viewpoints in its frame (directions, ring cameras, eye-height probes)."""
    b, centre = recentred(mesh)
    dirs = above_horizon_directions(settings.n_directions)
    lo, hi = used_bbox(b)
    cams = pedestrian_ring((lo, hi), eye_z=lo[2] + settings.eye, n=settings.n_cameras, margin=settings.camera_margin)
    caster = build_caster(b) if b.n_faces else None
    probes = interior_probes(b, eye=settings.eye, caster=caster) if b.n_faces else np.zeros((0, 3))

    views: list[Viewpoint] = [Viewpoint.direction(d) for d in dirs]
    views.extend([Viewpoint.point(p) for p in cams])
    views.extend([Viewpoint.point(p) for p in probes])
    return b, views


@dataclass
class E1Loose:
    """The repair engine E1 for loose faces.

    Removes zero-area faces, fragments, slivers and folds only when no viewpoint sees them.
    Visible debris is never removed: it stays in the mesh and is reported with crops.
    """
    name: str = "E1"
    legacy: bool = False
    flatness: dict = field(default_factory=dict)
    solidify: Any = None
    out_dir: Path | str | None = None
    viewpoints: list[Viewpoint] | None = None
    report: dict | None = field(default=None, repr=False)

    def _get_viewpoints(self, mesh: MeshData, ctx: RepairContext) -> tuple[MeshData, list[Viewpoint]]:
        b, centre = recentred(mesh)
        if self.viewpoints is not None:
            return b, self.viewpoints
        if ctx.validator is not None and getattr(ctx.validator, "_stage", None) is not None:
            st = ctx.validator.stage
            views = [Viewpoint.direction(d) for d in st.dirs]
            # convert stored stage viewpoints to centered frame
            pts = st.viewpoints - st.centre
            views.extend([Viewpoint.point(p) for p in pts])
            return b, views
        settings = getattr(ctx.validator, "settings", Settings())
        return _build_default_viewpoints(mesh, settings)

    def plan(self, unit: UnitState, ctx: RepairContext) -> list[Edit]:
        mesh = unit.mesh
        profile = ctx.profile
        t0 = time.perf_counter()

        topo = analyse_topology(mesh)
        ok = np.asarray(topo.ok, bool)
        zero_area_all = np.flatnonzero(~ok)

        # Faces solidify invented (face_line < 0) are never debris (E1-R5)
        invented = np.asarray(mesh.face_line) < 0

        contact_tol = 1.5 * float(topo.quanta.max())
        max_width = sliver_width_bound(topo.quanta, profile)

        # Detect fragments and slivers on welded topology
        positions_w = topo.positions_w
        face_w = topo.face_w

        det = detect_fragments(positions_w, face_w, profile,
                               contact_tol=contact_tol, max_width=max_width,
                               protected=invented)
        frag_mask = np.asarray(det.fragments, bool) & ok & ~invented
        sliver_mask = np.asarray(det.slivers, bool) & ok & ~invented

        # Detect folds
        folds = detect_folds(positions_w, face_w, mesh.face_material,
                             contact_tol=contact_tol, protected=invented)
        empty_exposure = np.zeros((mesh.n_faces, 2), dtype=bool)
        chosen, alone = _fold_members(folds, face_w, np.arange(mesh.n_faces),
                                      positions_w, face_w, side_exposure=empty_exposure,
                                      drop=np.zeros(mesh.n_faces, bool), profile=profile)
        fold_pairs: dict[int, int] = {}
        for k, m in chosen.items():
            if m is not None and not invented[m]:
                partner = int(sum(folds.folds[k]["faces"]) - m)
                fold_pairs[int(m)] = partner

        fold_mask = np.zeros(mesh.n_faces, bool)
        fold_mask[list(fold_pairs.keys())] = True
        fold_mask &= ~(frag_mask | sliver_mask) & ok

        # Zero-area faces
        zero_area_mask = np.zeros(mesh.n_faces, bool)
        zero_area_mask[zero_area_all] = True
        zero_area_mask &= ~invented

        # Determine piece groupings (E1-R2)
        pieces: list[dict] = []

        # 1. Fold pieces: chosen member and partner form one site
        for chosen_face, partner_face in fold_pairs.items():
            pieces.append({
                "faces": np.array([chosen_face], dtype=np.int64),
                "kind": "fold",
                "partner": partner_face,
            })

        # 2. Fragment and sliver components
        frag_sliver_ids = np.flatnonzero((frag_mask | sliver_mask) & ~fold_mask)
        if len(frag_sliver_ids):
            groups = _components(topo.face_w, frag_sliver_ids)
            centroid = mesh.positions[mesh.face_v].mean(axis=1)
            for grp in groups:
                for sub in split_group(grp, centroid, cap=MAX_SITE_FACES):
                    sub_frag = (frag_mask[sub]).sum()
                    sub_sliver = (sliver_mask[sub]).sum()
                    kind = "fragment" if sub_frag >= sub_sliver else "sliver"
                    pieces.append({
                        "faces": np.asarray(sub, dtype=np.int64),
                        "kind": kind,
                    })

        # 3. Zero-area faces
        # If a zero-area face shares an edge with a fragment/sliver piece, it joins it.
        # Otherwise, group by shared face with the rest of the mesh, up to 64 per site.
        claimed_faces = set()
        for p in pieces:
            claimed_faces.update(p["faces"].tolist())

        edge_table: dict[tuple[int, int], list[int]] = {}
        for f, tri in enumerate(topo.face_w):
            for i in range(3):
                v0, v1 = int(tri[i]), int(tri[(i + 1) % 3])
                if v0 != v1:
                    e = (min(v0, v1), max(v0, v1))
                    edge_table.setdefault(e, []).append(f)

        isolated_zero_area: list[int] = []
        for za in zero_area_all:
            za = int(za)
            if za in claimed_faces:
                continue
            joined = False
            for i in range(3):
                v0, v1 = int(topo.face_w[za, i]), int(topo.face_w[za, (i + 1) % 3])
                if v0 != v1:
                    e = (min(v0, v1), max(v0, v1))
                    for neighbour in edge_table.get(e, []):
                        if neighbour != za and neighbour in claimed_faces:
                            # join that piece
                            for p in pieces:
                                if neighbour in p["faces"]:
                                    p["faces"] = np.sort(np.append(p["faces"], za))
                                    claimed_faces.add(za)
                                    joined = True
                                    break
                        if joined:
                            break
                if joined:
                    break
            if not joined:
                isolated_zero_area.append(za)

        # Group remaining isolated zero-area faces by their neighbouring mesh face
        if isolated_zero_area:
            za_groups: dict[int, list[int]] = {}
            for za in isolated_zero_area:
                base_neighbour = -1
                for i in range(3):
                    v0, v1 = int(topo.face_w[za, i]), int(topo.face_w[za, (i + 1) % 3])
                    if v0 != v1:
                        e = (min(v0, v1), max(v0, v1))
                        for neighbour in edge_table.get(e, []):
                            if neighbour != za and neighbour not in zero_area_all:
                                base_neighbour = neighbour
                                break
                    if base_neighbour >= 0:
                        break
                za_groups.setdefault(base_neighbour, []).append(za)

            for base_f, zas in za_groups.items():
                zas_arr = np.array(zas, dtype=np.int64)
                for chunk_idx in range(0, len(zas_arr), MAX_ZERO_AREA_SITE):
                    chunk = zas_arr[chunk_idx:chunk_idx + MAX_ZERO_AREA_SITE]
                    pieces.append({
                        "faces": chunk,
                        "kind": "zero_area",
                        "base_neighbour": base_f,
                    })

        # Pre-filter: measure visibility from every Validator viewpoint (E1-R3)
        cand_faces_list = [f for p in pieces for f in p["faces"] if ok[f]]
        needs_casting = len(cand_faces_list) > 0 and (self.viewpoints is None or len(self.viewpoints) > 0)
        b_mesh, _ = recentred(mesh)
        caster = build_caster(b_mesh) if (b_mesh.n_faces and needs_casting) else None

        looks = unit.looks if isinstance(unit.looks, Looks) else Looks(unit.looks or {})
        cropper: SpotCropper | None = None
        crop_dir: Path | None = None
        if self.out_dir is not None:
            crop_dir = Path(self.out_dir) / "visible_debris"
            cropper = SpotCropper(mesh, looks)

        edits: list[Edit] = []
        visible_debris: list[dict] = []
        site_id = 0

        # Determine visibility
        is_visible_piece = [False] * len(pieces)
        worst_vps: list[Viewpoint | None] = [None] * len(pieces)
        worst_faces = [-1] * len(pieces)
        worst_pixels = [0.0] * len(pieces)

        if self.viewpoints is not None:
            # Custom viewpoints passed in (e.g. unit tests)
            for p_idx, piece in enumerate(pieces):
                p_faces = piece["faces"]
                max_px = 0.0
                worst_vp: Viewpoint | None = None
                worst_face: int = -1
                for vp in self.viewpoints:
                    for f in p_faces:
                        if not ok[f]:
                            continue
                        px = _face_visible_exceeds(b_mesh, int(f), vp, caster=caster, limit=VISIBLE_FLOOR_PX)
                        if px > max_px:
                            max_px = px
                            worst_vp = vp
                            worst_face = int(f)
                        if max_px > VISIBLE_FLOOR_PX:
                            break
                    if max_px > VISIBLE_FLOOR_PX:
                        break
                if max_px > VISIBLE_FLOOR_PX:
                    is_visible_piece[p_idx] = True
                    worst_vps[p_idx] = worst_vp
                    worst_faces[p_idx] = worst_face
                    worst_pixels[p_idx] = max_px
        else:
            # Standard Validator viewpoints: use lattice and visible_samples to find candidate viewpoints
            s = getattr(ctx.validator, "settings", Settings())
            lo, hi = used_bbox(b_mesh)
            dirs = above_horizon_directions(s.n_directions)
            cams = pedestrian_ring((lo, hi), eye_z=lo[2] + s.eye, n=s.n_cameras, margin=s.camera_margin)
            probes = interior_probes(b_mesh, eye=s.eye, caster=caster) if b_mesh.n_faces else np.zeros((0, 3))
            views = ([Viewpoint.direction(d) for d in dirs] +
                     [Viewpoint.point(p) for p in cams] +
                     [Viewpoint.point(p) for p in probes])

            cand_faces_list = [f for p in pieces for f in p["faces"] if ok[f]]
            cand_faces_arr = np.array(cand_faces_list, dtype=np.int64)
            lattice = floor_lattice(b_mesh, cand_faces_arr) if len(cand_faces_arr) else None
            vs = visible_samples(b_mesh, lattice, dirs, cams, probes, caster) if lattice and len(lattice) else None

            for p_idx, piece in enumerate(pieces):
                p_faces = piece["faces"]
                max_px = 0.0
                worst_vp: Viewpoint | None = None
                worst_face: int = -1

                if vs is not None and lattice is not None:
                    for f in p_faces:
                        if not ok[f]:
                            continue
                        f_mask = lattice.face == f
                        seen_f = vs.seen[f_mask]
                        cols = np.flatnonzero(seen_f.any(axis=0))
                        for col in cols:
                            vp = views[col]
                            px = _face_visible_exceeds(b_mesh, int(f), vp, caster=caster, limit=VISIBLE_FLOOR_PX)
                            if px > max_px:
                                max_px = px
                                worst_vp = vp
                                worst_face = int(f)
                            if max_px > VISIBLE_FLOOR_PX:
                                break
                        if max_px > VISIBLE_FLOOR_PX:
                            break

                if max_px > VISIBLE_FLOOR_PX:
                    is_visible_piece[p_idx] = True
                    worst_vps[p_idx] = worst_vp
                    worst_faces[p_idx] = worst_face
                    worst_pixels[p_idx] = max_px

        for p_idx, piece in enumerate(pieces):
            p_faces = piece["faces"]
            if is_visible_piece[p_idx]:
                worst_face = worst_faces[p_idx]
                worst_vp = worst_vps[p_idx]
                max_px = worst_pixels[p_idx]
                # Visible debris: remains in mesh, listed with crop (E1-R3)
                crop_path = None
                if cropper is not None and crop_dir is not None and worst_face >= 0 and worst_vp is not None:
                    crop_file = crop_dir / f"piece_{p_idx}.png"
                    pts = mesh.positions[mesh.face_v[worst_face]]
                    centroid = pts.mean(axis=0)
                    if worst_vp.kind == "direction":
                        eye = centroid - 240.0 * worst_vp.at
                    else:
                        eye = worst_vp.at
                    view_dict = {"eye": eye, "target": centroid}
                    crop_path = str(cropper.write(pts, ordered=True, view=view_dict, path=crop_file))

                vp_label = "none" if worst_vp is None else f"{worst_vp.kind}:{worst_vp.at.round(3).tolist()}"
                visible_debris.append({
                    "piece": p_idx,
                    "faces": p_faces.tolist(),
                    "kind": piece["kind"],
                    "pixels": round(float(max_px), 2),
                    "viewpoint": vp_label,
                    "crop": crop_path,
                })
            else:
                # Invisible debris: propose as remove edit (E1-R1)
                P_f = mesh.positions[mesh.face_v[p_faces]]
                face_area = 0.5 * np.linalg.norm(np.cross(P_f[:, 1] - P_f[:, 0], P_f[:, 2] - P_f[:, 0]), axis=1)
                total_area = float(face_area.sum())
                centroid = P_f.reshape(-1, 3).mean(axis=0).tolist()
                bbox = [P_f.reshape(-1, 3).min(axis=0).tolist(), P_f.reshape(-1, 3).max(axis=0).tolist()]

                evidence = {
                    "rule": piece["kind"],
                    "faces": p_faces.tolist(),
                    "area": round(total_area, 4),
                    "centroid": centroid,
                    "bbox": bbox,
                    "legacy_rays": False,
                    "legacy_guard": False,
                }
                if "partner" in piece:
                    evidence["partner"] = piece["partner"]

                edits.append(Edit(
                    engine=self.name,
                    kind="remove",
                    faces=tuple(int(f) for f in p_faces),
                    new_faces=None,
                    new_points=None,
                    site=site_id,
                    reason=piece["kind"],
                    evidence=evidence,
                ))
                site_id += 1

        # Populate report numbers
        cand_counts = {
            "fragment": int(frag_mask.sum()),
            "sliver": int(sliver_mask.sum()),
            "fold": int(fold_mask.sum()),
            "zero_area": int(zero_area_mask.sum()),
            "total": int((frag_mask | sliver_mask | fold_mask | zero_area_mask).sum()),
        }
        self.report = {
            "candidates": cand_counts,
            "sites": site_id,
            "visible_debris": visible_debris,
            "visible_debris_count": len(visible_debris),
            "seconds": round(time.perf_counter() - t0, 3),
        }
        return edits
