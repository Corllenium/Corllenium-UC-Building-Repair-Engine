"""Merged BEFORE+AFTER 3D Ghost-Facade Diff Overlay Generator (`engine.validate.diff_overlay`).

Compares ANY `before_mesh` and `after_mesh` (single floor or whole building, zero hardcoded
coordinates) using Embree 7-point barycentric coverage + exterior exposure classification and
partitions every difference into 4 visual inspection layers for the Siege 3D Diff Viewport
and Blender QA:

  1. `missing_outer_facade`     (BRIGHT RED GHOST)     — EXP_OUTSIDE faces in BEFORE missing in AFTER (D03/D04/D06/D07)
  2. `missing_interior_visible` (ORANGE-RED GHOST)     — Room-visible interior faces in BEFORE missing in AFTER (D04/D07/D12/D14)
  3. `cleaned_hidden_trash`     (TRANSLUCENT CYAN)     — Non-visible / internal cavity / flicker faces intentionally cleaned (D11/D13/D15)
  4. `remaining_after_errors`   (MAGENTA / AMBER)      — Residual defects still present on AFTER (D02 slivers, flicker, reversed, open seams)

Output `diff_overlay.json` stores compact face-index arrays referencing `before.obj` and
`after.obj` (zero duplicated vertex downloads in the web dashboard) plus exact counts and
`[x, y, z]` 3D hotspot coordinates. `write_diff_overlay_obj(...)` optionally emits a standalone
multi-material `.obj` for direct import into Blender.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import numpy as np

from engine.detectors.errors import find_errors
from engine.fixes.patch_protect import detect_piercing_needle_slivers
from engine.model import MeshData
from engine.pipeline import analyse_topology
from engine.rays.caster import EmbreeCaster
from engine.topo.planes import face_normals
from engine.validate import sampling, viewpoints, visibility
from engine.validate.facade_integrity import BARY7, _coverage_7pt
from engine.validate.hole_detector import detect_new_mesh_holes
from engine.vis.exposure import EXP_OUTSIDE, classify_exposure, compute_side_exposure


def _top_spots(mesh: MeshData, face_ids: np.ndarray, label_prefix: str, limit: int = 16) -> list[dict]:
    if len(face_ids) == 0:
        return []
    pts = mesh.positions[mesh.face_v[face_ids]]
    areas = 0.5 * np.linalg.norm(np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]), axis=1)
    order = np.argsort(-areas)[:limit]
    spots: list[dict] = []
    for idx in order:
        f = int(face_ids[idx])
        cen = pts[idx].mean(axis=0)
        spots.append({
            "label": f"{label_prefix} (face #{f}, area={areas[idx]:.1f} sq in)",
            "centre": [round(float(v), 2) for v in cen],
            "size": round(float(np.sqrt(max(areas[idx], 1.0))), 2),
            "faceId": f,
        })
    return spots


def compute_before_after_diff_overlay(
    before_mesh: MeshData,
    after_mesh: MeshData,
    after_errs: dict | None = None,
    *,
    rebuild_exclusion_mask_fn: Callable[[MeshData], np.ndarray] | None = None,
    n_probe_dirs: int = 128,
    n_ext_dirs: int = 64,
) -> dict:
    """Compute the 4-layer Merged BEFORE+AFTER Ghost-Facade Diff payload for any building/floor."""
    center = 0.5 * (before_mesh.positions.min(axis=0) + before_mesh.positions.max(axis=0))
    pts_b = before_mesh.positions[before_mesh.face_v]
    fn_b = face_normals(before_mesh.positions, before_mesh.face_v, np.ones(before_mesh.n_faces, dtype=bool))
    ok_b = (~np.isnan(fn_b).any(axis=1)) & (np.linalg.norm(fn_b, axis=1) > 0.5)
    areas_b = 0.5 * np.linalg.norm(np.cross(pts_b[:, 1] - pts_b[:, 0], pts_b[:, 2] - pts_b[:, 0]), axis=1)

    excl_b = (
        np.asarray(rebuild_exclusion_mask_fn(before_mesh), dtype=bool)
        if rebuild_exclusion_mask_fn is not None
        else np.zeros(before_mesh.n_faces, dtype=bool)
    )

    # 1. Classify BEFORE outer facade (`EXP_OUTSIDE`) & interior room-visible faces
    ef_b, eb_b = compute_side_exposure(before_mesh.positions - center, before_mesh.face_v, ok_b, n_dirs=n_ext_dirs)
    exp_b = classify_exposure(ef_b + eb_b, ok_b)
    outer_b_mask = ok_b & (exp_b == EXP_OUTSIDE) & (areas_b >= 0.05) & (~excl_b)

    m_r, _ = sampling.recentred(before_mesh)
    caster_v = visibility.build_caster(m_r)
    probes_eye = viewpoints.interior_probes(m_r, eye=63.0, headroom=80.0, grid=39.37, caster=caster_v)
    room_hits_b = np.zeros(before_mesh.n_faces, dtype=np.int64)
    if len(probes_eye) > 0:
        probes_all = np.vstack([
            probes_eye,
            probes_eye + np.array([0.0, 0.0, -36.0]),
            probes_eye + np.array([0.0, 0.0, +30.0]),
        ])
        dirs_probe = viewpoints.outside_directions(n_probe_dirs)
        cb_r = EmbreeCaster(m_r.positions, m_r.face_v)
        batch = 1500
        for i in range(0, len(probes_all), batch):
            pb = probes_all[i : i + batch]
            orig = np.repeat(pb, len(dirs_probe), axis=0)
            d_rep = np.tile(dirs_probe, (len(pb), 1))
            hit_f, _ = cb_r.first_hit(orig, d_rep)
            valid = hit_f[hit_f >= 0]
            if len(valid):
                np.add.at(room_hits_b, valid, 1)
    interior_vis_b_mask = ok_b & (room_hits_b > 0) & (~outer_b_mask) & (areas_b >= 0.05) & (~excl_b)

    # 2. Check 7-point Embree coverage of EVERY valid BEFORE face against AFTER
    after_caster = EmbreeCaster(after_mesh.positions - center, after_mesh.face_v)
    all_valid_b = np.flatnonzero(ok_b & (~excl_b))
    _, missing_all_b = _coverage_7pt(before_mesh, after_caster, center, fn_b, all_valid_b, tol=0.12)

    missing_b_mask = np.zeros(before_mesh.n_faces, dtype=bool)
    missing_b_mask[missing_all_b] = True

    missing_outer_ids = np.flatnonzero(missing_b_mask & outer_b_mask)
    missing_interior_ids = np.flatnonzero(missing_b_mask & interior_vis_b_mask)
    cleaned_trash_ids = np.flatnonzero(missing_b_mask & (~outer_b_mask) & (~interior_vis_b_mask))

    # 3. Collect remaining AFTER error faces (D02 needle slivers + flicker + reversed + zero-area)
    if after_errs is None:
        after_errs = find_errors(after_mesh)
    err_faces_dict = after_errs.get("faces", {}) if isinstance(after_errs, dict) else {}
    after_err_set: set[int] = set()
    for key in ("flicker_diff", "flicker_same", "reversed", "zero_area"):
        for fid in err_faces_dict.get(key, ()):
            if 0 <= int(fid) < after_mesh.n_faces:
                after_err_set.add(int(fid))

    sliver_mask, sliver_spots = detect_piercing_needle_slivers(after_mesh)
    for fid in np.flatnonzero(sliver_mask):
        after_err_set.add(int(fid))

    # 4. Detect ANY-shape new void-leaking mesh holes (triangles, edge slits, notches, irregular polygons)
    hole_report = detect_new_mesh_holes(before_mesh, after_mesh)
    for fid in hole_report["holeFaceIds"]:
        if 0 <= int(fid) < after_mesh.n_faces:
            after_err_set.add(int(fid))
    remaining_after_ids = np.array(sorted(after_err_set), dtype=np.int64)

    return {
        "version": "1.1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "beforeFacesTotal": int(before_mesh.n_faces),
        "afterFacesTotal": int(after_mesh.n_faces),
        "counts": {
            "missing_outer_facade": int(len(missing_outer_ids)),
            "missing_interior_visible": int(len(missing_interior_ids)),
            "cleaned_hidden_trash": int(len(cleaned_trash_ids)),
            "remaining_after_errors": int(len(remaining_after_ids)),
            "new_mesh_holes": int(hole_report["holeCount"]),
            "new_hole_void_edges": int(hole_report["voidLeakEdgeCount"]),
        },
        "newMeshHoles": {
            "holeCount": hole_report["holeCount"],
            "voidLeakEdgeCount": hole_report["voidLeakEdgeCount"],
            "byShape": hole_report["byShape"],
        },
        "before_faces": {
            "missing_outer_facade": [int(x) for x in missing_outer_ids],
            "missing_interior_visible": [int(x) for x in missing_interior_ids],
            "cleaned_hidden_trash": [int(x) for x in cleaned_trash_ids],
        },
        "after_faces": {
            "remaining_after_errors": [int(x) for x in remaining_after_ids],
            "new_hole_boundary_faces": hole_report["holeFaceIds"],
        },
        "spots": {
            "missing_outer_facade": _top_spots(before_mesh, missing_outer_ids, "Missing outer facade"),
            "missing_interior_visible": _top_spots(before_mesh, missing_interior_ids, "Missing visible interior"),
            "remaining_after_errors": sliver_spots[:16],
            "new_mesh_holes": hole_report["spots"],
        },
    }


def write_diff_overlay_obj(
    before_mesh: MeshData,
    after_mesh: MeshData,
    diff_doc: dict,
    out_obj_path: Path,
) -> Path:
    """Write a standalone 4-group `.obj` + `.mtl` of the diff overlay for direct Blender QA import."""
    mtl_path = out_obj_path.with_suffix(".mtl")
    mtl_path.write_text(
        "newmtl DIFF_MISSING_OUTER\nKd 0.96 0.14 0.22\nd 0.88\n\n"
        "newmtl DIFF_MISSING_INTERIOR\nKd 0.98 0.52 0.12\nd 0.80\n\n"
        "newmtl DIFF_CLEANED_TRASH\nKd 0.08 0.80 0.95\nd 0.35\n\n"
        "newmtl DIFF_AFTER_ERRORS\nKd 0.92 0.18 0.86\nd 0.90\n",
        encoding="utf-8",
    )

    lines: list[str] = [f"mtllib {mtl_path.name}"]
    v_offset = 1

    def _emit_group(name: str, mat: str, src: MeshData, fids: list[int]) -> None:
        nonlocal v_offset
        if not fids:
            return
        idx_arr = np.asarray(fids, dtype=np.int64)
        fv = src.face_v[idx_arr]
        uniq_v, inv = np.unique(fv.ravel(), return_inverse=True)
        pts = src.positions[uniq_v]
        lines.append(f"o {name}")
        lines.append(f"usemtl {mat}")
        for x, y, z in pts:
            lines.append(f"v {x:.4f} {y:.4f} {z:.4f}")
        remapped = inv.reshape(-1, 3) + v_offset
        for a, b, c in remapped:
            lines.append(f"f {int(a)} {int(b)} {int(c)}")
        v_offset += len(uniq_v)

    bf = diff_doc.get("before_faces", {})
    af = diff_doc.get("after_faces", {})
    _emit_group("DIFF_MISSING_OUTER", "DIFF_MISSING_OUTER", before_mesh, bf.get("missing_outer_facade", []))
    _emit_group("DIFF_MISSING_INTERIOR", "DIFF_MISSING_INTERIOR", before_mesh, bf.get("missing_interior_visible", []))
    _emit_group("DIFF_CLEANED_TRASH", "DIFF_CLEANED_TRASH", before_mesh, bf.get("cleaned_hidden_trash", []))
    _emit_group("DIFF_AFTER_ERRORS", "DIFF_AFTER_ERRORS", after_mesh, af.get("remaining_after_errors", []))

    out_obj_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_obj_path


def restore_destroyed_facade_faces(
    before_mesh: MeshData,
    after_mesh: MeshData,
    diff_doc: dict,
    *,
    include_interior: bool = True,
) -> tuple[MeshData, int]:
    """Mandatory in-run self-heal: pull accidentally destroyed visible BEFORE faces back into AFTER.

    Prevents the repair engine from shipping a model with missing outer facades (`D03`/`D04`/`D06`/`D07`)
    or missing room-visible walls/baseboards/columns (`D12`/`D14`). Preserves UVs, materials, and normals.
    """
    bf = diff_doc.get("before_faces", {})
    ids: list[int] = list(bf.get("missing_outer_facade", []))
    if include_interior:
        ids.extend(bf.get("missing_interior_visible", []))
    if not ids:
        return after_mesh, 0

    sel = np.unique(np.asarray(ids, dtype=np.int64))
    sel = sel[(sel >= 0) & (sel < before_mesh.n_faces)]
    if len(sel) == 0:
        return after_mesh, 0

    import copy
    out = copy.deepcopy(after_mesh)

    # Clear any buried/conflicting coplanar faces in `out` that lie on the exact same plane & overlap
    # a restored visible BEFORE face, so subsequent flicker convergence NEVER re-deletes the visible facade!
    if out.n_faces > 0:
        from shapely.geometry import Polygon
        from engine.topo.planes import plane_basis

        fn_b = face_normals(before_mesh.positions, before_mesh.face_v, np.ones(before_mesh.n_faces, dtype=bool))
        fn_a = face_normals(out.positions, out.face_v, np.ones(out.n_faces, dtype=bool))
        pts_b_sel = before_mesh.positions[before_mesh.face_v[sel]]
        pts_a = out.positions[out.face_v]
        # Bounding-box + plane prefilter for fast conflict detection
        bmin_a = pts_a.min(axis=1)
        bmax_a = pts_a.max(axis=1)
        drop_conflict = np.zeros(out.n_faces, dtype=bool)
        for idx_k, bf_id in enumerate(sel):
            nb = fn_b[bf_id]
            if np.isnan(nb).any() or np.linalg.norm(nb) < 0.5:
                continue
            tb = pts_b_sel[idx_k]
            bb_min = tb.min(axis=0) - 0.15
            bb_max = tb.max(axis=0) + 0.15
            cand = np.flatnonzero(
                (~drop_conflict)
                & (bmax_a[:, 0] >= bb_min[0]) & (bmin_a[:, 0] <= bb_max[0])
                & (bmax_a[:, 1] >= bb_min[1]) & (bmin_a[:, 1] <= bb_max[1])
                & (bmax_a[:, 2] >= bb_min[2]) & (bmin_a[:, 2] <= bb_max[2])
            )
            if len(cand) == 0:
                continue
            dots = np.abs(fn_a[cand] @ nb)
            cand = cand[dots >= 0.995]
            if len(cand) == 0:
                continue
            d_plane = float(tb[0] @ nb)
            c_pts = pts_a[cand].mean(axis=1)
            cand = cand[np.abs((c_pts @ nb) - d_plane) <= 0.12]
            if len(cand) == 0:
                continue
            u_ax, v_ax = plane_basis(nb)
            pb = Polygon(np.stack([tb @ u_ax, tb @ v_ax], axis=-1))
            if not pb.is_valid or pb.area <= 0.05:
                continue
            for af in cand:
                pa = Polygon(np.stack([pts_a[af] @ u_ax, pts_a[af] @ v_ax], axis=-1))
                if pa.is_valid and pa.area > 0.05:
                    ovl = float(pa.intersection(pb).area)
                    if ovl >= 0.70 * float(pa.area):
                        drop_conflict[af] = True
        if drop_conflict.any():
            from engine.fixes.remove import remove_faces
            out, _ = remove_faces(out, drop_conflict)

    mat_map: dict[str, int] = {m: i for i, m in enumerate(out.materials)}
    for m in before_mesh.materials:
        if m not in mat_map:
            mat_map[m] = len(out.materials)
            out.materials.append(m)

    v_off = len(out.positions)
    out.positions = np.vstack([out.positions, before_mesh.positions[before_mesh.face_v[sel]].reshape(-1, 3)])
    new_fv = np.arange(v_off, v_off + 3 * len(sel), dtype=np.int64).reshape(-1, 3)
    out.face_v = np.vstack([out.face_v, new_fv])

    if out.uvs is not None and before_mesh.uvs is not None and before_mesh.face_vt is not None and out.face_vt is not None:
        sub_vt = before_mesh.face_vt[sel]
        valid_vt = sub_vt >= 0
        if valid_vt.any() and len(before_mesh.uvs) > 0:
            vt_off = len(out.uvs)
            safe_vt = np.where(valid_vt, sub_vt, 0)
            out.uvs = np.vstack([out.uvs, before_mesh.uvs[safe_vt].reshape(-1, 2)])
            new_fvt = np.arange(vt_off, vt_off + 3 * len(sel), dtype=np.int64).reshape(-1, 3)
            new_fvt = np.where(valid_vt, new_fvt, -1)
        else:
            new_fvt = np.full((len(sel), 3), -1, dtype=np.int64)
        out.face_vt = np.vstack([out.face_vt, new_fvt])
    elif out.face_vt is not None:
        out.face_vt = np.vstack([out.face_vt, np.full((len(sel), 3), -1, dtype=np.int64)])

    if out.face_vn is not None:
        out.face_vn = np.vstack([out.face_vn, np.full((len(sel), 3), -1, dtype=np.int64)])

    new_fm = np.array([mat_map[before_mesh.materials[int(m)]] for m in before_mesh.face_material[sel]], dtype=np.int64)
    out.face_material = np.concatenate([out.face_material, new_fm])
    out.face_line = np.concatenate([out.face_line, np.zeros(len(sel), dtype=np.int64)])
    return out, int(len(sel))

