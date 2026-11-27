"""Batch runner and 6-gate QA harness for Engine v2 (`solid_cutaway_rebuild`)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Any

import numpy as np
from shapely.geometry import LineString, Polygon, box as shapely_box
from shapely.ops import polygonize, unary_union
import trimesh

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.fixes.solid_cutaway_rebuild import (  # noqa: E402
    _clean_shapely,
    _count_non_ortho_edges,
    _extract_exterior_facade_meshes,
    _extract_solid_slice,
    _extract_structural_slices,
    _is_clean_angled_tread,
    _iter_polygons,
    load_raw_floor_obj,
    run_solid_rebuild,
)

DEFAULT_SRC_ROOT = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair\Exports\Repaired-Buildings-20261015\ByBuilding")
DEFAULT_OUT_ROOT = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair\02_STAGING_DEVELOPMENT\SolidRebuild")
DEFAULT_RAW_SRC_ROOT = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair\Exports\Unity-Buildings-20261014\ByBuilding")
DEFAULT_MAIN_INFRA_RAW_ROOT = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair\01_ORIGINAL_BACKUPS\MAIN_INFRA_MINECRAFT_20261023")
DEFAULT_RAW_OUT_ROOT = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair\02_STAGING_DEVELOPMENT\SolidRebuild-RAW")


def resolve_raw_ref_obj(
    src_obj: Path,
    bname: str,
    floor_name: str,
    raw_src_root: Path | None = DEFAULT_RAW_SRC_ROOT,
    main_infra_raw_root: Path | None = DEFAULT_MAIN_INFRA_RAW_ROOT,
) -> Path | None:
    """Resolve the matching untouched RAW .obj baseline for a floor unit."""
    if bname == "Main-Infrastructure" and main_infra_raw_root is not None and main_infra_raw_root.is_dir():
        m = re.search(r"Model-Floor_0(\d)", floor_name)
        if m:
            n = int(m.group(1))
            sfx = {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")
            cand = main_infra_raw_root / f"{sfx} floor main infra.obj"
            if cand.is_file():
                return cand
    if raw_src_root is None or not raw_src_root.is_dir():
        return None
    fdir = raw_src_root / bname / floor_name
    if not fdir.is_dir():
        return None
    base_name = src_obj.name[:-len(".fixed.obj")] + ".obj" if src_obj.name.lower().endswith(".fixed.obj") else src_obj.name
    cands = [
        p for p in sorted(fdir.glob("*.obj"))
        if not p.name.lower().endswith(".fixed.obj")
        and "skp_ref" not in p.name.lower()
        and ".solid_rebuild" not in p.name.lower()
    ]
    if not cands:
        return None
    exact = [p for p in cands if p.name.lower() == base_name.lower()]
    if exact:
        return exact[0]
    return max(cands, key=lambda p: (0 if p.stem.lower().endswith("1") else 1, p.stat().st_size, p.name))


def _discover_source_objs(
    b_src: Path,
    bname: str,
    floors: list[str] | None,
    include_basements: bool,
    source_mode: str,
) -> list[tuple[str, Path]]:
    """Discover (floor_name, obj_path) pairs for Engine v1 (.fixed.obj) or raw (.obj) batch runs."""
    if source_mode == "v1":
        fixed_objs = sorted(b_src.rglob("*.fixed.obj"))
        if floors:
            want = set(floors)
            fixed_objs = [p for p in fixed_objs if p.parent.name in want]
        else:
            fixed_objs = [
                p for p in fixed_objs
                if not _is_non_interior_folder(p.parent.name, include_basements=include_basements)
            ]
        if not fixed_objs:
            raise FileNotFoundError(f"No *.fixed.obj files found under {b_src} for floors={floors}")
        by_dir: dict[Path, list[Path]] = {}
        for p in fixed_objs:
            by_dir.setdefault(p.parent, []).append(p)
        return [
            (
                parent.name,
                max(
                    cands,
                    key=lambda p: (
                        0 if p.name.lower().endswith("1.fixed.obj") else 1,
                        p.stat().st_size if p.is_file() else 0,
                        p.name,
                    ),
                ),
            )
            for parent, cands in sorted(by_dir.items())
        ]

    if source_mode != "raw":
        raise ValueError(f"Unsupported source_mode: {source_mode!r}")

    # Support flat Main-Infrastructure raw layout ("1st floor main infra.obj" .. "7th floor main infra.obj")
    flat_mi: list[tuple[str, Path]] = []
    for p in sorted(b_src.glob("*.obj")):
        m = re.match(r"^(\d+)(?:st|nd|rd|th)\s+floor\s+main\s+infra\.obj$", p.name, flags=re.IGNORECASE)
        if m:
            fl_name = f"Model-Floor_0{m.group(1)}"
            if not floors or fl_name in floors:
                flat_mi.append((fl_name, p))
    if flat_mi:
        return sorted(flat_mi, key=lambda item: item[0])

    raw_objs = [
        p for p in sorted(b_src.rglob("*.obj"))
        if not p.name.lower().endswith(".fixed.obj")
        and "skp_ref" not in p.name.lower()
        and ".solid_rebuild" not in p.name.lower()
    ]
    if floors:
        want = set(floors)
        raw_objs = [p for p in raw_objs if p.parent.name in want]
    else:
        raw_objs = [
            p for p in raw_objs
            if not _is_non_interior_folder(p.parent.name, include_basements=include_basements)
        ]
    if not raw_objs:
        raise FileNotFoundError(f"No raw *.obj files found under {b_src} ({bname}) for floors={floors}")
    by_dir_raw: dict[Path, list[Path]] = {}
    for p in raw_objs:
        by_dir_raw.setdefault(p.parent, []).append(p)
    return [
        (
            parent.name,
            max(
                cands,
                key=lambda p: (
                    0 if p.stem.lower().endswith("1") else 1,
                    p.stat().st_size if p.is_file() else 0,
                    p.name,
                ),
            ),
        )
        for parent, cands in sorted(by_dir_raw.items())
    ]


def _is_non_interior_folder(name: str, include_basements: bool = False) -> bool:
    """Return True for rooftops, sidewalks, shared shells, debug subdirs, and basements."""
    low = name.strip().lower()
    if (
        low == "floor_rf"
        or low.endswith("_rf")
        or (low.endswith("-roof") and "and-roof" not in low)
        or low.startswith("roof")
        or low.startswith("sidewalk")
        or low.startswith("shared-")
        or "redwing_stack" in low
        or re.search(r"-e[35]-\d+", low) is not None
    ):
        return True
    if not include_basements and re.match(r"^(floor_)?\d+b$", low):
        return True
    return False


def audit_rebuilt_glb(
    glb_path: Path,
    src_obj: Path,
    out_dir: Path,
    report_audit: dict[str, Any],
    passed_flag: bool,
    raw_ref_obj: Path | None = None,
    raw_ref_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run all 10 automated Engine v2 QA gates against a rebuilt floor package."""
    sc = trimesh.load(glb_path, force="scene")
    manifest_recovery: dict[str, Any] = {}
    manifest_file = out_dir / "rebuild_manifest.json"
    if manifest_file.is_file():
        try:
            manifest_recovery = json.loads(manifest_file.read_text(encoding="utf-8")).get("raw_recovery", {})
        except Exception:
            manifest_recovery = {}
    ref_cache_entry = (
        raw_ref_cache.get(str(raw_ref_obj)) if (raw_ref_cache is not None and raw_ref_obj is not None) else None
    )
    raw_ref_loaded = (
        ref_cache_entry["ref_raw"]
        if ref_cache_entry is not None
        else (load_raw_floor_obj(raw_ref_obj) if (raw_ref_obj is not None and raw_ref_obj.is_file()) else None)
    )
    if manifest_recovery.get("used_raw_structural_fallback") and raw_ref_loaded is not None:
        raw = raw_ref_loaded
    else:
        raw = load_raw_floor_obj(src_obj)

    # Gate 1: Watertight & manifold topology
    watertight_ok = bool(
        passed_flag
        and report_audit.get("all_watertight")
        and int(report_audit.get("total_open_edges", 1)) == 0
        and int(report_audit.get("total_nonmanifold_edges", 1)) == 0
        and int(report_audit.get("narrow_wall_gaps", 1)) == 0
    )

    # Gate 2: Zero prematurely stepped/chopped __Upper walls & columns
    stepped_upper: list[dict[str, Any]] = []
    for n, g in sorted(sc.geometry.items()):
        if not ((n.startswith("Wall_") or n.startswith("Column_")) and "__Upper" in n):
            continue
        fn = g.face_normals
        fc = g.vertices[g.faces].mean(axis=1)
        up = fn[:, 1] > 0.9
        if not up.any():
            continue
        max_y = float(g.bounds[1][1])
        mid_m = up & (fc[:, 1] < max_y - 0.3)
        if mid_m.any():
            a_mid = float(g.area_faces[mid_m].sum())
            if a_mid > 0.25:
                stepped_upper.append({"node": n, "a_mid": round(a_mid, 3)})

    # Gate 3: Zero non-orthogonal notched single-step stair treads
    non_ortho_steps: list[dict[str, Any]] = []
    stair_geoms = [g for n, g in sc.geometry.items() if n.startswith("Stairs_") and "Parapet" not in n]
    if stair_geoms:
        st_all = trimesh.util.concatenate(stair_geoms) if len(stair_geoms) > 1 else stair_geoms[0]
        fc = st_all.vertices[st_all.faces].mean(axis=1)
        fn = st_all.face_normals
        by_y: dict[float, list[Polygon]] = {}
        for f, yv in zip(st_all.faces[fn[:, 1] > 0.95], fc[fn[:, 1] > 0.95, 1]):
            yr = round(round(float(yv) / 0.05) * 0.05, 3)
            p = Polygon(st_all.vertices[f][:, [0, 2]]).buffer(0)
            if p.area > 1e-4:
                by_y.setdefault(yr, []).append(p)
        for yr, plist in sorted(by_y.items()):
            for g in _iter_polygons(_clean_shapely(unary_union(plist), 0.004)):
                min_dim = min(g.bounds[2] - g.bounds[0], g.bounds[3] - g.bounds[1])
                if g.area <= 4.5 and min_dim <= 1.25:
                    no = 0 if _is_clean_angled_tread(g) else _count_non_ortho_edges(g)
                    if no > 0:
                        non_ortho_steps.append({"y": yr, "non_ortho_edges": no})

    # Gate 4: Zero same-direction Parapet vs Wall/Column/Overhead Z-fighting overlaps
    parapet_meshes = [g for n, g in sc.geometry.items() if "Parapet" in n]
    other_meshes = [
        g for n, g in sc.geometry.items()
        if n.startswith("Wall_") or n.startswith("Column_") or n.startswith("OverheadBeams_")
    ]
    parapet_zfight = 0
    if parapet_meshes and other_meshes:
        pm = trimesh.util.concatenate(parapet_meshes) if len(parapet_meshes) > 1 else parapet_meshes[0]
        om = trimesh.util.concatenate(other_meshes) if len(other_meshes) > 1 else other_meshes[0]
        pfc = pm.vertices[pm.faces].mean(axis=1)
        ofc = om.vertices[om.faces].mean(axis=1)
        pfn = pm.face_normals
        ofn = om.face_normals
        for i in range(0, len(pfc), 500):
            d = np.linalg.norm(pfc[i : i + 500, None, :] - ofc[None, :, :], axis=2)
            dot = np.einsum("ik,jk->ij", pfn[i : i + 500], ofn)
            parapet_zfight += int(((d < 0.045) & (dot > 0.95)).sum())

    # Gate 5: Overhead lintels bounded (zero huge roof slab leakage)
    ov_gs = [g for n, g in sc.geometry.items() if n.startswith("OverheadBeams_")]
    overhead_top_area = 0.0
    if ov_gs:
        ovm = trimesh.util.concatenate(ov_gs) if len(ov_gs) > 1 else ov_gs[0]
        overhead_top_area = round(float(ovm.area_faces[ovm.face_normals[:, 1] > 0.9].sum()), 2)
    overhead_ok = overhead_top_area <= 65.0

    # Gate 6: Required Unity & manifest outputs exist and are non-empty
    stem = src_obj.stem
    req_files = [
        out_dir / f"{stem}.solid_rebuild.unity.obj",
        out_dir / "materials.mtl",
        out_dir / "rebuild_manifest.json",
        out_dir / "watertight_audit.json",
    ]
    unity_outputs_ok = all(p.is_file() and p.stat().st_size > 0 for p in req_files)

    # Gate 7: Slanted stair quartz_15574983 balustrades must stay bounded (zero ceiling soffit wedges / protrusions)
    parapet_anomalies: list[dict[str, Any]] = []
    stair_all_geoms = [
        g for n, g in sc.geometry.items()
        if (n.startswith("Stairs_") or n.startswith("Stairs_Upper_")) and "Parapet" not in n
    ]
    if stair_all_geoms:
        st_bounds = trimesh.util.concatenate(stair_all_geoms).bounds if len(stair_all_geoms) > 1 else stair_all_geoms[0].bounds
        sx0, sz0 = float(st_bounds[0][0]), float(st_bounds[0][2])
        sx1, sz1 = float(st_bounds[1][0]), float(st_bounds[1][2])
    else:
        sx0 = sz0 = sx1 = sz1 = 0.0

    for n, g in sorted(sc.geometry.items()):
        if "Parapet" not in n or "cut_cap" in n or "15574983" not in n:
            continue
        b = g.bounds
        ext = b[1] - b[0]
        if stair_all_geoms:
            if float(b[0][0]) < sx0 - 0.50 or float(b[1][0]) > sx1 + 0.50 or float(b[0][2]) < sz0 - 0.50 or float(b[1][2]) > sz1 + 0.50:
                parapet_anomalies.append({
                    "node": n,
                    "reason": "protrudes_beyond_stairs",
                    "bounds": [round(float(v), 2) for v in (*b[0], *b[1])],
                })
                continue
        ax_i, u_i = (0, 2) if ext[0] < ext[2] else (2, 0)
        fn = g.face_normals
        fc_m = g.vertices[g.faces].mean(axis=1)
        ax_mask = np.abs(fn[:, ax_i]) > 0.85
        if not ax_mask.any():
            continue
        # Evaluate each 0.25m parallel slab separately so adjacent stepped balustrades don't flatten together
        slab_bins: dict[float, list[Polygon]] = {}
        for f, center_ax in zip(g.faces[ax_mask], fc_m[ax_mask, ax_i]):
            p = Polygon(g.vertices[f][:, [u_i, 1]]).buffer(0)
            if p.area > 1e-4:
                kr = round(float(center_ax) * 4.0) / 4.0
                slab_bins.setdefault(kr, []).append(p)
        for kr, polys in slab_bins.items():
            u_poly = _clean_shapely(unary_union(polys), 0.005)
            if u_poly.is_empty:
                continue
            u0, y0, u1, y1 = u_poly.bounds
            if not (np.isfinite(u0) and np.isfinite(u1) and u1 > u0):
                continue
            max_h = 0.0
            ceil_hang_span = 0.0
            for u in np.arange(u0 + 0.12, u1, 0.25):
                inter = u_poly.intersection(LineString([(u, y0 - 1.0), (u, y1 + 1.0)]))
                if inter.is_empty:
                    continue
                ib = inter.bounds
                h = float(ib[3] - ib[1])
                if h > max_h:
                    max_h = h
                if ib[3] >= float(raw.ceil_y) - 0.08 and ib[1] >= float(raw.floor_y) + 0.50:
                    ceil_hang_span += 0.25
            if max_h > 1.75 or ceil_hang_span >= 1.50:
                parapet_anomalies.append({
                    "node": n,
                    "slab_bin": kr,
                    "reason": "excess_vertical_depth_or_ceil_hang",
                    "max_h": round(max_h, 2),
                    "ceil_hang_span": round(ceil_hang_span, 2),
                })

    # Gate 7b: Lower cutaway parapets must rest over Floor_Slab or lower Stairs_* (zero floating tails over empty pits)
    # and Floor_Slab upward faces must never receive iron_block/metal_block railings
    lower_sup_polys: list[Polygon] = []
    floor_slab_iron_nodes = [
        n for n in sc.geometry
        if n.startswith("Floor_Slab") and ("iron_block" in n.lower() or "metal_block" in n.lower())
    ]
    for n, g in sc.geometry.items():
        if n.startswith("Floor_Slab"):
            fn = g.face_normals
            fc_y = g.vertices[g.faces].mean(axis=1)[:, 1]
            m = (fn[:, 1] > 0.85) & (fc_y >= float(raw.floor_y) - 0.15)
            for f in g.faces[m]:
                p = Polygon(g.vertices[f][:, [0, 2]]).buffer(0)
                if p.area > 1e-4:
                    lower_sup_polys.append(p)
        elif n.startswith("Stairs_") and "Upper" not in n and "Parapet" not in n:
            fn = g.face_normals
            for f in g.faces[fn[:, 1] > 0.85]:
                p = Polygon(g.vertices[f][:, [0, 2]]).buffer(0)
                if p.area > 1e-4:
                    lower_sup_polys.append(p)
    lower_support_xz = (
        _clean_shapely(unary_union(lower_sup_polys).buffer(0.45, join_style=2), 0.005)
        if lower_sup_polys
        else Polygon()
    )
    if not lower_support_xz.is_empty:
        for n, g in sorted(sc.geometry.items()):
            if "Parapet" not in n or "__Lower" not in n or "cut_cap" in n:
                continue
            face_xz = [Polygon(g.vertices[f][:, [0, 2]]).buffer(0) for f in g.faces]
            parapet_xz = _clean_shapely(unary_union([p for p in face_xz if p.area > 1e-5]), 0.005)
            overhang = float(parapet_xz.difference(lower_support_xz).area) if not parapet_xz.is_empty else 0.0
            if overhang > 0.05:
                b = g.bounds
                parapet_anomalies.append({
                    "node": n,
                    "reason": "floating_lower_parapet_tail",
                    "overhang_m2": round(overhang, 3),
                    "bounds": [round(float(v), 2) for v in (*b[0], *b[1])],
                })
    for fn_iron in floor_slab_iron_nodes:
        parapet_anomalies.append({"node": fn_iron, "reason": "floor_slab_iron_bleed"})

    # Gate 8: Genuine raw doorway pockets beneath lintels must remain unblocked in Wall_*__Lower
    def _find_blocked_doorways(ref_mesh: Any, wc_lo_poly: Any, stair_geoms_list: list[Any]) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        pos_r, fa_r, mats_r, fmats_r = ref_mesh.positions, ref_mesh.faces, ref_mesh.materials, ref_mesh.face_mats
        keep_w = np.array([mats_r[m].category in ("structural", "baseboard", "exterior_accent") for m in fmats_r])
        if not keep_w.any():
            return found
        wall_tm_r = trimesh.Trimesh(vertices=pos_r, faces=fa_r[keep_w], process=False)
        p0_r, p1_r, p2_r = pos_r[fa_r[:, 0]], pos_r[fa_r[:, 1]], pos_r[fa_r[:, 2]]
        cr_r = np.cross(p1_r - p0_r, p2_r - p0_r)
        un_r = cr_r / np.maximum(np.linalg.norm(cr_r, axis=1)[:, None], 1e-12)
        yc_r = pos_r[fa_r].mean(axis=1)[:, 1]
        y_chk = float(ref_mesh.floor_y) + 0.60

        def _raw_caps(ymin: float) -> Any:
            ps = [
                Polygon(pos_r[f][:, [0, 2]]).buffer(0)
                for f, ok in zip(fa_r, keep_w & (un_r[:, 1] > 0.85) & (yc_r >= ymin))
                if ok
            ]
            ps = [p for p in ps if p.area > 1e-5]
            return _clean_shapely(unary_union(ps), 0.005) if ps else Polygon()

        any_cap_r = _raw_caps(float(ref_mesh.floor_y) + 0.45)
        caps_hi_r = _raw_caps(y_chk - 0.02)
        base_no_cap = _extract_solid_slice(wall_tm_r, y_chk, any_cap_r, caps_above_y=None)
        segs_r = trimesh.intersections.mesh_plane(wall_tm_r, [0.0, 1.0, 0.0], [0.0, y_chk, 0.0])
        if len(segs_r) > 0 and not caps_hi_r.is_empty:
            lines_r = [
                LineString([(round(float(s[0, 0]), 3), round(float(s[0, 2]), 3)), (round(float(s[1, 0]), 3), round(float(s[1, 2]), 3))])
                for s in segs_r
                if (round(float(s[0, 0]), 3), round(float(s[0, 2]), 3)) != (round(float(s[1, 0]), 3), round(float(s[1, 2]), 3))
            ]
            noded_r = unary_union(lines_r)
            wide_c = caps_hi_r.buffer(-1.30, join_style=2)
            narrow_c = caps_hi_r.difference(wide_c.buffer(1.40, join_style=2)) if not wide_c.is_empty else caps_hi_r
            miss_c = _clean_shapely(narrow_c.difference(base_no_cap.buffer(0.02, join_style=2)), 0.008)
            if not miss_c.is_empty:
                cap_lr = [g.exterior for g in _iter_polygons(miss_c)]
                for g in _iter_polygons(miss_c):
                    cap_lr.extend(list(g.interiors))
                fresh_r_noded = noded_r.difference(base_no_cap.buffer(0.06, join_style=2)) if not base_no_cap.is_empty else noded_r
                fresh_r_buf = fresh_r_noded.buffer(0.08, join_style=2) if not fresh_r_noded.is_empty else Polygon()
                st_xz = (
                    unary_union([
                        Polygon(g.vertices[f][:, [0, 2]]).buffer(0)
                        for g in stair_geoms_list
                        for f in g.faces[g.face_normals[:, 1] > 0.85]
                    ]).buffer(0.10)
                    if stair_geoms_list
                    else Polygon()
                )
                for p in polygonize(unary_union(lines_r + cap_lr)):
                    if not (0.25 <= p.area <= 2.50):
                        continue
                    if not st_xz.is_empty and p.intersects(st_xz):
                        continue
                    if p.intersection(miss_c).area / max(p.area, 1e-9) < 0.70:
                        continue
                    fresh_ratio = (
                        p.boundary.intersection(fresh_r_buf).length / max(p.boundary.length, 1e-9)
                        if not fresh_r_buf.is_empty
                        else 0.0
                    )
                    if fresh_ratio < 0.15 and p.intersection(wc_lo_poly).area / max(p.area, 1e-9) >= 0.70:
                        found.append({
                            "area": round(float(p.area), 2),
                            "bounds": [round(float(v), 2) for v in p.bounds],
                        })
        return found

    blocked_doorways: list[dict[str, Any]] = []
    wc_lo_polys = [
        Polygon(g.vertices[f][:, [0, 2]]).buffer(0)
        for n, g in sc.geometry.items()
        if (n.startswith("Wall_") or n.startswith("Column_")) and "__Lower" in n
        for f in g.faces[g.face_normals[:, 1] > 0.9]
    ]
    wc_lo_polys = [p for p in wc_lo_polys if p.area > 1e-4]

    if wc_lo_polys:
        wc_lo = _clean_shapely(unary_union(wc_lo_polys), 0.005)
        if manifest_recovery.get("used_raw_structural_fallback") and raw_ref_loaded is not None:
            blocked_doorways = _find_blocked_doorways(raw_ref_loaded, wc_lo, stair_all_geoms)
        elif float(manifest_recovery.get("recovered_wall_m2", 0.0) or 0.0) >= 0.80 and raw_ref_loaded is not None:
            b_v1 = _find_blocked_doorways(raw, wc_lo, stair_all_geoms)
            b_raw = _find_blocked_doorways(raw_ref_loaded, wc_lo, stair_all_geoms)
            raw_boxes = [shapely_box(*it["bounds"]) for it in b_raw]
            blocked_doorways = [
                it for it in b_v1
                if any(shapely_box(*it["bounds"]).buffer(0.05).intersects(rb) for rb in raw_boxes)
            ]
        else:
            blocked_doorways = _find_blocked_doorways(raw, wc_lo, stair_all_geoms)

    # Gate 9: Zero inverted-volume structural nodes or acute sliver triangles
    neg_volume_nodes: list[str] = []
    sliver_tris = 0
    min_structural_alt_mm = 9999.0
    for n, g in sorted(sc.geometry.items()):
        if not (n.startswith("Wall_") or n.startswith("Column_") or n.startswith("Floor_Slab")):
            continue
        if g.is_watertight and float(g.volume) < -1e-6:
            neg_volume_nodes.append(n)
        if len(g.faces) == 0:
            continue
        verts = g.vertices[g.faces]
        e0 = np.linalg.norm(verts[:, 1] - verts[:, 0], axis=1)
        e1 = np.linalg.norm(verts[:, 2] - verts[:, 1], axis=1)
        e2 = np.linalg.norm(verts[:, 0] - verts[:, 2], axis=1)
        longest = np.maximum(np.maximum(e0, e1), e2)
        alt_mm = (2.0 * g.area_faces / np.maximum(longest, 1e-12)) * 1000.0
        aspect = longest / np.maximum(alt_mm / 1000.0, 1e-12)
        min_structural_alt_mm = min(min_structural_alt_mm, float(alt_mm.min()))
        sliver_tris += int(((alt_mm < 0.5) & (aspect > 80.0)).sum())
    if min_structural_alt_mm == 9999.0:
        min_structural_alt_mm = 0.0

    # Gate 10: Completeness vs untouched RAW baseline (floor area, standing walls, facades, stairs)
    raw_comp: dict[str, Any] = {
        "checked_against_raw": False,
        "floor_coverage_pct": 100.0,
        "wall_coverage_pct": 100.0,
        "facade_coverage_ok": True,
        "stair_coverage_ok": True,
        "rebuilt_facade_tris": 0,
    }
    rebuilt_facade_tris = sum(len(g.faces) for n, g in sc.geometry.items() if n.startswith("Facade_"))
    rebuilt_stair_tris = sum(len(g.faces) for g in stair_all_geoms)
    raw_comp["rebuilt_facade_tris"] = int(rebuilt_facade_tris)
    raw_completeness_ok = True
    if raw_ref_obj is not None and raw_ref_obj.is_file():
        if ref_cache_entry is None:
            ref_raw = raw_ref_loaded if raw_ref_loaded is not None else load_raw_floor_obj(raw_ref_obj)
            ref_sl = _extract_structural_slices(ref_raw)
            ref_cache_entry = {"ref_raw": ref_raw, "ref_sl": ref_sl}
            if raw_ref_cache is not None:
                raw_ref_cache[str(raw_ref_obj)] = ref_cache_entry
        else:
            ref_raw = ref_cache_entry["ref_raw"]
            ref_sl = ref_cache_entry["ref_sl"]
        ref_floor_a = float(ref_sl["floor_fp"].area) if not ref_sl["floor_fp"].is_empty else 0.0
        ref_wall_a = float(ref_sl["S_base"].area) if not ref_sl["S_base"].is_empty else 0.0
        rebuilt_floor_a = sum(
            float(g.area_faces[g.face_normals[:, 1] > 0.9].sum())
            for n, g in sc.geometry.items()
            if n.startswith("Floor_Slab")
        )
        rebuilt_wall_a = sum(
            float(g.area_faces[g.face_normals[:, 1] > 0.9].sum())
            for n, g in sc.geometry.items()
            if (n.startswith("Wall_") or n.startswith("Column_")) and "__Lower" in n
        )
        floor_cov = round(min(100.0, (100.0 * rebuilt_floor_a / ref_floor_a)), 1) if ref_floor_a >= 10.0 else 100.0
        wall_cov = round(min(100.0, (100.0 * rebuilt_wall_a / ref_wall_a)), 1) if ref_wall_a >= 2.0 else 100.0
        if "ref_fac" not in ref_cache_entry:
            ref_cache_entry["ref_fac"] = _extract_exterior_facade_meshes(ref_raw, ref_sl["S_base"], ref_sl["floor_fp"])
        ref_fac = ref_cache_entry["ref_fac"]
        ref_has_facade = any(len(tm_f.faces) > 0 for _, _, tm_f in ref_fac)
        ref_has_stairs = len(ref_sl["stair_clusters"]) > 0
        facade_ok = (not ref_has_facade) or (rebuilt_facade_tris > 0)
        stair_ok = (not ref_has_stairs) or (rebuilt_stair_tris > 0)
        raw_completeness_ok = (floor_cov >= 85.0) and (wall_cov >= 85.0) and facade_ok and stair_ok
        raw_comp.update({
            "checked_against_raw": True,
            "raw_ref_obj": str(raw_ref_obj),
            "floor_coverage_pct": floor_cov,
            "wall_coverage_pct": wall_cov,
            "ref_has_facade": ref_has_facade,
            "facade_coverage_ok": facade_ok,
            "ref_has_stairs": ref_has_stairs,
            "stair_coverage_ok": stair_ok,
        })

    gates = {
        "watertight": watertight_ok,
        "stepped_upper": len(stepped_upper) == 0,
        "non_ortho_steps": len(non_ortho_steps) == 0,
        "parapet_zfight": parapet_zfight == 0,
        "overhead_bounds": overhead_ok,
        "unity_outputs": unity_outputs_ok,
        "parapet_bounds_clean": len(parapet_anomalies) == 0,
        "doorways_unblocked": len(blocked_doorways) == 0,
        "no_sliver_artifacts": len(neg_volume_nodes) == 0 and sliver_tris == 0,
        "raw_completeness": raw_completeness_ok,
    }
    return {
        "all_passed": all(gates.values()),
        "gates": gates,
        "metrics": {
            "floor_y": round(float(raw.floor_y), 3),
            "ceil_y": round(float(raw.ceil_y), 3),
            "nodes": len(report_audit.get("nodes", [])),
            "open_edges": int(report_audit.get("total_open_edges", 0)),
            "nonmanifold_edges": int(report_audit.get("total_nonmanifold_edges", 0)),
            "narrow_wall_gaps": int(report_audit.get("narrow_wall_gaps", 0)),
            "stepped_upper": stepped_upper,
            "non_ortho_steps": non_ortho_steps,
            "parapet_zfight": parapet_zfight,
            "parapet_anomalies": parapet_anomalies,
            "blocked_doorways": blocked_doorways,
            "neg_volume_nodes": neg_volume_nodes,
            "sliver_tris": sliver_tris,
            "min_structural_alt_mm": round(min_structural_alt_mm, 3),
            "raw_completeness": raw_comp,
            "overhead_top_area": overhead_top_area,
            "floor_raised_nodes": [n for n in sc.geometry if "Raised" in n],
        },
    }


def _floor_elevation_key(floor_name: str, floor_y: float) -> tuple[int, float, str]:
    """Order basements separately from upper floors using suffix (B vs F/M) and floor_y."""
    up = floor_name.strip().upper()
    band = 0 if up.endswith("B") else 1
    return (band, float(floor_y), floor_name)


def audit_stacked_continuity(floor_glbs: list[tuple[str, float, Path]]) -> dict[str, Any]:
    """Cross-check stacked floors in XZ so missing middle-floor walls or columns are flagged."""
    fps: dict[str, Any] = {}
    ordered: list[tuple[int, float, str]] = []
    for floor_name, floor_y, glb_path in floor_glbs:
        sc = trimesh.load(glb_path, force="scene")
        wc_polys: list[Polygon] = []
        for n, g in sc.geometry.items():
            if (n.startswith("Wall_") or n.startswith("Column_")) and "__Lower" in n:
                fn = g.face_normals
                for f_idx in g.faces[fn[:, 1] > 0.9]:
                    p = Polygon(g.vertices[f_idx][:, [0, 2]]).buffer(0)
                    if p.area > 1e-4:
                        wc_polys.append(p)
        fps[floor_name] = _clean_shapely(unary_union(wc_polys), 0.01) if wc_polys else Polygon()
        ordered.append(_floor_elevation_key(floor_name, floor_y))

    by_band: dict[int, list[str]] = {0: [], 1: []}
    for band, _, fname in sorted(ordered):
        by_band[band].append(fname)

    flagged: list[dict[str, Any]] = []
    per_floor: dict[str, dict[str, Any]] = {}
    for band_list in by_band.values():
        for idx, fl in enumerate(band_list):
            if idx == 0 or idx == len(band_list) - 1:
                per_floor[fl] = {"missing_m2": 0.0, "clusters": []}
                continue
            prev_fl, next_fl = band_list[idx - 1], band_list[idx + 1]
            both_adj = _clean_shapely(fps[prev_fl].intersection(fps[next_fl]), 0.02)
            miss = _clean_shapely(both_adj.difference(fps[fl].buffer(0.15, join_style=2)), 0.02)
            clusters = [
                {
                    "area_m2": round(float(p.area), 2),
                    "bounds": [round(float(v), 2) for v in p.bounds],
                }
                for p in _iter_polygons(miss)
                if p.area >= 0.50
            ]
            miss_area = round(sum(c["area_m2"] for c in clusters), 2)
            per_floor[fl] = {
                "compared_between": [prev_fl, next_fl],
                "missing_m2": miss_area,
                "clusters": clusters,
            }
            if miss_area > 0.0:
                flagged.append({"floor": fl, **per_floor[fl]})

    return {
        "has_large_gaps": len(flagged) > 0,
        "flagged_floors": flagged,
        "per_floor": per_floor,
    }


def _stage_to_dashboard(src_obj: Path, out_dir: Path, glb_path: Path | None, obj_path: Path | None, dash_dir: Path) -> None:
    dash_dir.mkdir(parents=True, exist_ok=True)
    base = src_obj.name[:-len(".fixed.obj")] if src_obj.name.endswith(".fixed.obj") else src_obj.stem
    if glb_path and glb_path.is_file():
        shutil.copy2(glb_path, dash_dir / f"{base}.solid_rebuild.glb")
    if obj_path and obj_path.is_file():
        shutil.copy2(obj_path, dash_dir / f"{base}.solid_rebuild.unity.obj")
    for name in ("materials.mtl", "rebuild_manifest.json", "watertight_audit.json"):
        fp = out_dir / name
        if fp.is_file():
            shutil.copy2(fp, dash_dir / name)
    tex_src = out_dir / "textures"
    if tex_src.is_dir():
        tex_dst = dash_dir / "textures"
        tex_dst.mkdir(parents=True, exist_ok=True)
        for tf in tex_src.iterdir():
            if tf.is_file():
                shutil.copy2(tf, tex_dst / tf.name)


def run_batch_rebuild(
    src_root: Path,
    out_root: Path,
    building: str,
    floors: list[str] | None = None,
    stage_dashboard_dir: Path | None = None,
    include_basements: bool = False,
    source_mode: str = "v1",
    raw_ref_root: Path | None = DEFAULT_RAW_SRC_ROOT,
    main_infra_raw_root: Path | None = DEFAULT_MAIN_INFRA_RAW_ROOT,
) -> dict[str, Any]:
    """Rebuild and QA-audit every selected building/floor package."""
    buildings = sorted(p.name for p in src_root.iterdir() if p.is_dir()) if building.upper() == "ALL" else [building]
    overall: dict[str, Any] = {"all_passed": True, "source_mode": source_mode, "buildings": {}}

    for bname in buildings:
        b_src = src_root / bname
        if not b_src.is_dir():
            if source_mode == "raw" and src_root.is_dir() and any(src_root.glob("*.obj")):
                b_src = src_root
            else:
                raise FileNotFoundError(f"Building source folder not found: {b_src}")
        src_entries = _discover_source_objs(b_src, bname, floors, include_basements, source_mode)

        b_out = out_root / bname
        b_out.mkdir(parents=True, exist_ok=True)
        floor_results: list[dict[str, Any]] = []
        floor_glbs: list[tuple[str, float, Path]] = []
        b_passed = True

        for floor_name, src_obj in src_entries:
            floor_out = b_out / floor_name
            raw_ref = (
                resolve_raw_ref_obj(src_obj, bname, floor_name, raw_ref_root, main_infra_raw_root)
                if source_mode == "v1"
                else src_obj
            )
            floor_cache: dict[str, Any] = {}
            rep = run_solid_rebuild(
                src_obj,
                floor_out,
                raw_ref_obj=(raw_ref if source_mode == "v1" else None),
                raw_ref_cache=floor_cache,
                low_cut_m=1.25,
                plinth_m=0.04,
                export_glb=True,
            )
            assert rep.glb_path is not None
            qa = audit_rebuilt_glb(
                rep.glb_path, src_obj, floor_out, rep.audit, rep.passed, raw_ref_obj=raw_ref, raw_ref_cache=floor_cache
            )
            if not qa["all_passed"]:
                b_passed = False
            if stage_dashboard_dir is not None:
                _stage_to_dashboard(src_obj, floor_out, rep.glb_path, rep.obj_path, stage_dashboard_dir / bname)
            floor_glbs.append((floor_name, float(qa["metrics"]["floor_y"]), rep.glb_path))
            floor_results.append({
                "floor": floor_name,
                "source_mode": source_mode,
                "source_obj": str(src_obj),
                "source_obj_name": src_obj.name,
                "raw_ref_obj": str(raw_ref) if raw_ref is not None else None,
                "raw_recovery": rep.manifest.get("raw_recovery", {}),
                "out_dir": str(floor_out),
                **qa,
            })

        stacked_continuity = audit_stacked_continuity(floor_glbs)
        b_report = {
            "building": bname,
            "source_mode": source_mode,
            "all_passed": b_passed,
            "floor_count": len(floor_results),
            "stacked_continuity": stacked_continuity,
            "floors": floor_results,
        }
        (b_out / "batch_qa_report.json").write_text(json.dumps(b_report, indent=2) + "\n", encoding="utf-8")
        overall["buildings"][bname] = b_report
        if not b_passed:
            overall["all_passed"] = False

    return overall


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Batch Engine v2 solid rebuild & 10-gate QA harness")
    parser.add_argument("--building", required=True, help="Building folder name (e.g. CHTM) or ALL")
    parser.add_argument("--floors", nargs="*", default=None, help="Optional floor subfolder names (e.g. Floor_4F Floor_5F)")
    parser.add_argument("--include-basements", action="store_true", help="Include basement Floor_*B folders (excluded by default for Interior Studio)")
    parser.add_argument("--source-mode", choices=("v1", "raw"), default="v1", help="Select Engine v1 (.fixed.obj) or raw (.obj) inputs")
    parser.add_argument("--no-raw-ref", action="store_true", help="Disable automatic RAW completeness guard and missing-geometry recovery")
    parser.add_argument("--src-root", type=Path, default=None)
    parser.add_argument("--out-root", type=Path, default=None)
    parser.add_argument("--stage-dashboard-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    src_root = args.src_root or (DEFAULT_RAW_SRC_ROOT if args.source_mode == "raw" else DEFAULT_SRC_ROOT)
    out_root = args.out_root or (DEFAULT_RAW_OUT_ROOT if args.source_mode == "raw" else DEFAULT_OUT_ROOT)

    summary = run_batch_rebuild(
        src_root=src_root,
        out_root=out_root,
        building=args.building,
        floors=args.floors,
        stage_dashboard_dir=args.stage_dashboard_dir,
        include_basements=args.include_basements,
        source_mode=args.source_mode,
        raw_ref_root=(None if args.no_raw_ref else DEFAULT_RAW_SRC_ROOT),
        main_infra_raw_root=(None if args.no_raw_ref else DEFAULT_MAIN_INFRA_RAW_ROOT),
    )
    for bname, brep in summary["buildings"].items():
        print(f"[{bname}] all_passed={brep['all_passed']} floors={brep['floor_count']}")
        cont = brep.get("stacked_continuity", {})
        per_fl = cont.get("per_floor", {})
        for fl in brep["floors"]:
            miss_m2 = per_fl.get(fl["floor"], {}).get("missing_m2", 0.0)
            print(
                f"  - {fl['floor']}: passed={fl['all_passed']} gates={fl['gates']} "
                f"open={fl['metrics']['open_edges']} stepped={len(fl['metrics']['stepped_upper'])} "
                f"non_ortho={len(fl['metrics']['non_ortho_steps'])} zfight={fl['metrics']['parapet_zfight']} "
                f"stacked_gap_m2={miss_m2}"
            )
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
