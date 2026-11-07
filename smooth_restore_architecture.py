"""Restore all 8 Architecture floors from STAGE11_BACKUP, remove synthetic bridging soffit
triangles across stairwells/openings, restore all missing visible stair treads, stair risers,
ceiling beams, wall pockets, louvers, and original textures from BEFORE, purge ONLY strictly
enclosed sub-floor and double-wall vertical cavity ribs, smoothly dissolve coplanar same-material
planes so flat floors and walls have zero internal green slit lines, and split 7th Floor Roof/Ceiling.
"""
from __future__ import annotations

from collections import defaultdict
import copy
import json
from pathlib import Path
from typing import Any
import numpy as np
import shapely
from shapely.geometry import MultiPoint, Polygon
from shapely.ops import unary_union

from engine.campus.blender_staging import apply_repaired_building_to_blender_staging
from engine.campus.checkpoint_push import convert_unity_to_ckpt17_coords
from engine.fixes.building_repair import (
    _triangulate_clipped_face,
    cluster_coplanar_faces,
    compact_mesh,
    prepare_building_materials,
)
from engine.fixes.remove import remove_faces
from engine.io.mtl import parse_mtl
from engine.io.obj_reader import read_obj
from engine.model import MeshData
from engine.rays.caster import EmbreeCaster
from engine.topo.planes import face_normals, plane_basis

REPAIR_REPO = Path("D:/PROJECTS/04-Corllenium-Building-Model-Repair")
UC_GAME_ARCHI = Path("D:/PROJECTS/03-Corllenium-UC-Game/Assets/Models/Campus/Repaired/Architecture")
ORIG_ARCHI = REPAIR_REPO / "Exports/Unity-Buildings-20261014/ByBuilding/Architecture"
EXP_ARCHI = REPAIR_REPO / "Exports/Repaired-Buildings-20261015/ByBuilding/Architecture"
SIEGE_WTS = [
    Path("D:/PROJECTS/02-Corllenium-Siege/.worktrees/merge-main-infra-and-pipelines-20261106"),
    Path("D:/PROJECTS/02-Corllenium-Siege/.worktrees/pipeline-foundry-floorplans"),
    Path("D:/PROJECTS/02-Corllenium-Siege/.worktrees/campus-webgl-v0.2.1"),
    Path("D:/PROJECTS/02-Corllenium-Siege"),
]
PRIMARY_SIEGE = SIEGE_WTS[0]

ARCHI_UNITS = [
    ("Architecture_1st_floor", "Model-Floor_01"),
    ("Architecture_dep_2nd_Floor_obj", "Model-Floor_02"),
    ("Architecture_dep_3rd_Floor_obj", "Model-Floor_03"),
    ("Architecture_dep_4th_Floor_obj", "Model-Floor_04"),
    ("Architecture_dep_5th_Floor_obj", "Model-Floor_05"),
    ("Architecture_dep_6th_Floor_obj", "Model-Floor_06"),
    ("Architecture_dep_7th_Floor_obj", "Model-Floor_07"),
    ("Architecture_emergency_stairs", "Shared-Stairs"),
]

EXPORT_FLOOR_FOLDER = {
    "Architecture_1st_floor": "Model-Floor_01",
    "Architecture_dep_2nd_Floor_obj": "Model-Floor_02",
    "Architecture_dep_3rd_Floor_obj": "Model-Floor_03",
    "Architecture_dep_4th_Floor_obj": "Model-Floor_04",
    "Architecture_dep_5th_Floor_obj": "Model-Floor_05",
    "Architecture_dep_6th_Floor_obj": "Model-Floor_06",
    "Architecture_dep_7th_Floor_obj": "Model-Floor_07",
    "Architecture_dep_7th_Floor_Roof_Ceiling": "Model-Floor_07-Roof",
    "Architecture_emergency_stairs": "Shared-Stairs",
}


def _iter_polys(geom: Any) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if hasattr(geom, "geoms"):
        out: list[Polygon] = []
        for g in geom.geoms:
            out.extend(_iter_polys(g))
        return out
    return []


def compute_visible_before_mask(
    b_mesh: MeshData, mtl_dict: dict[str, Any] | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    pts = b_mesh.positions[b_mesh.face_v]
    fn = face_normals(b_mesh.positions, b_mesh.face_v, np.ones(b_mesh.n_faces, dtype=bool))
    ok = (~np.isnan(fn).any(axis=1)) & (np.linalg.norm(fn, axis=1) > 0.5)
    cent = pts.mean(axis=1)
    z0 = pts[:, :, 2].min(axis=1)
    z1 = pts[:, :, 2].max(axis=1)
    dz = z1 - z0
    z_min_b = float(b_mesh.positions[:, 2].min())

    caster = EmbreeCaster(b_mesh.positions, b_mesh.face_v[ok])
    BARY4 = np.array([[1 / 3, 1 / 3, 1 / 3], [0.65, 0.175, 0.175], [0.175, 0.65, 0.175], [0.175, 0.175, 0.65]])
    samp = np.einsum("sb,fbk->fsk", BARY4, pts)
    dirs_fn = np.repeat(fn[:, None, :], 4, axis=1).reshape(-1, 3)
    _, tf_s = caster.first_hit((samp + 0.15 * fn[:, None, :]).reshape(-1, 3), dirs_fn)
    _, tb_s = caster.first_hit((samp - 0.15 * fn[:, None, :]).reshape(-1, 3), -dirs_fn)
    tf = tf_s.reshape(b_mesh.n_faces, 4).max(axis=1)
    tb = tb_s.reshape(b_mesh.n_faces, 4).max(axis=1)

    pf_s = (samp + 2.0 * fn[:, None, :]).reshape(-1, 3)
    pb_s = (samp - 2.0 * fn[:, None, :]).reshape(-1, 3)
    N4 = len(pf_s)
    up_v4 = np.tile([0.0, 0.0, 1.0], (N4, 1))
    dn_v4 = np.tile([0.0, 0.0, -1.0], (N4, 1))
    _, pf_tup_s = caster.first_hit(pf_s, up_v4)
    _, pf_tdn_s = caster.first_hit(pf_s, dn_v4)
    _, pb_tup_s = caster.first_hit(pb_s, up_v4)
    _, pb_tdn_s = caster.first_hit(pb_s, dn_v4)
    pf_z_top = (pf_s[:, 2] + pf_tup_s).reshape(b_mesh.n_faces, 4).max(axis=1)
    pf_z_bot = (pf_s[:, 2] - pf_tdn_s).reshape(b_mesh.n_faces, 4).min(axis=1)
    pb_z_top = (pb_s[:, 2] + pb_tup_s).reshape(b_mesh.n_faces, 4).max(axis=1)
    pb_z_bot = (pb_s[:, 2] - pb_tdn_s).reshape(b_mesh.n_faces, 4).min(axis=1)

    vert = ok & (np.abs(fn[:, 2]) < 0.25)

    # Detect hidden back-faces on vertical walls (e.g. bf=32527 grey inner wall behind bf=39010 dark green wainscot)
    is_hidden_backface = np.zeros(b_mesh.n_faces, dtype=bool)
    gx_v = np.round(cent[:, 0] / 3.0).astype(int)
    gy_v = np.round(cent[:, 1] / 3.0).astype(int)
    gz_v = np.round(cent[:, 2] / 3.0).astype(int)
    vert_grid: dict[tuple[int, int, int], list[int]] = {}
    for i in np.flatnonzero(vert):
        k = (int(gx_v[i]), int(gy_v[i]), int(gz_v[i]))
        vert_grid.setdefault(k, []).append(int(i))
    for i in np.flatnonzero(vert):
        if tf[i] < 10.0:
            k0, k1, k2 = int(gx_v[i]), int(gy_v[i]), int(gz_v[i])
            found_open_twin = False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz_k in (-1, 0, 1):
                        for j in vert_grid.get((k0 + dx, k1 + dy, k2 + dz_k), ()):
                            if float(np.dot(fn[i], fn[j])) < -0.90 and tf[j] > 18.0:
                                found_open_twin = True
                                break
                        if found_open_twin:
                            break
                    if found_open_twin:
                        break
                if found_open_twin:
                    break
            if found_open_twin:
                is_hidden_backface[i] = True

    f_span = pf_z_top - pf_z_bot
    b_span = pb_z_top - pb_z_bot
    f_escapes_up = (tf > 4.0) & (pf_z_top > (z1 + 4.0))
    f_escapes_dn = (tf > 2.5) & (pf_z_bot < (z0 - 4.0))
    b_escapes_up = (tb > 4.0) & (pb_z_top > (z1 + 4.0))
    b_escapes_dn = (tb > 2.5) & (pb_z_bot < (z0 - 4.0))

    # A vertical face is visible if its front or back faces open space AND either spans > 28 in,
    # stands in a space > 28 in tall, or escapes above/below a slab
    f_open = (tf > 4.0) & ((tf > 12.0) | (tf >= 0.45 * tb)) & (
        (dz > 28.0) | (f_span > 28.0) | f_escapes_up | f_escapes_dn
    )
    b_open = (tb > 4.0) & ((tb > 12.0) | (tb >= 0.45 * tf)) & (
        (dz > 28.0) | (b_span > 28.0) | b_escapes_up | b_escapes_dn
    )
    enclosed_slab_part = (dz <= 28.0) & (f_span <= 28.0) & (b_span <= 28.0) & (~f_escapes_up) & (~f_escapes_dn) & (~b_escapes_up) & (~b_escapes_dn)
    vert_vis = vert & (~is_hidden_backface) & (f_open | b_open) & (~enclosed_slab_part)

    horiz = ok & (np.abs(fn[:, 2]) >= 0.25)
    areas = 0.5 * np.linalg.norm(np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]), axis=1)
    zh = np.round(cent[:, 2], 1)
    major_zs = []
    major_polys = {}
    for zv in sorted(set(zh[horiz].tolist())):
        if zv > z_min_b + 149.0:
            continue
        sel = np.flatnonzero(horiz & (np.abs(zh - zv) < 0.35))
        if areas[sel].sum() > 350_000.0:
            u = unary_union([Polygon(pts[f, :, :2]).buffer(0.1) for f in sel])
            if u.area > 180_000.0:
                major_zs.append(zv)
                major_polys[zv] = u

    buried_slab_xy: dict[float, Any] = {}
    for i, zv in enumerate(major_zs):
        higher = [major_polys[z2] for z2 in major_zs[i + 1 :] if (z2 - zv) <= 85.0]
        if higher:
            u_hi = unary_union(higher).buffer(-2.0)
            ovl = major_polys[zv].intersection(u_hi)
            if not ovl.is_empty and ovl.area > 50_000.0:
                buried_slab_xy[zv] = ovl

    _, tup_s = caster.first_hit((samp + np.array([0.0, 0.0, 2.0])).reshape(-1, 3), up_v4)
    _, tdn_s = caster.first_hit((samp - np.array([0.0, 0.0, 2.0])).reshape(-1, 3), dn_v4)
    tup_z = tup_s.reshape(b_mesh.n_faces, 4).max(axis=1)
    tdn_z = tdn_s.reshape(b_mesh.n_faces, 4).max(axis=1)

    # Identify back-to-back coplanar +Z faces so -Z internal slab faces (ltstone/quartz_block_bottom) never overwrite +Z floor tops
    pos_z_cells: set[tuple[int, int, int]] = set()
    gx_h = np.round(cent[:, 0] / 2.5).astype(int)
    gy_h = np.round(cent[:, 1] / 2.5).astype(int)
    gz_h = np.round(cent[:, 2] / 1.0).astype(int)
    for i in np.flatnonzero(horiz & (fn[:, 2] >= 0.85) & (tup_z > 6.0)):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                pos_z_cells.add((int(gx_h[i]) + dx, int(gy_h[i]) + dy, int(gz_h[i])))
    has_pos_twin = np.zeros(b_mesh.n_faces, dtype=bool)
    for i in np.flatnonzero(horiz & (fn[:, 2] <= -0.85)):
        if (int(gx_h[i]), int(gy_h[i]), int(gz_h[i])) in pos_z_cells:
            has_pos_twin[i] = True

    not_hollow_step = ~((tup_z <= 6.5) & (tdn_z <= 6.5))
    is_green_wall_cap = np.array(
        ["-00-" in b_mesh.materials[int(m)] for m in b_mesh.face_material], dtype=bool
    ) & (cent[:, 2] <= z_min_b + 150.0)

    # Allow stair steps under landings (tup_z > 6.5 and tdn_z > 6.5, like bf=23023..23030 at z=1415.3)
    horiz_up_vis = (
        horiz
        & (~has_pos_twin)
        & ((tup_z > 22.0) | ((tup_z > 6.5) & (tdn_z > 6.5) & (fn[:, 2] >= 0.25)))
        & not_hollow_step
        & (~is_green_wall_cap)
        & ((tdn_z < 22.0) | (tup_z >= 0.25 * np.minimum(tdn_z, 120.0)))
    )
    horiz_dn_vis = (
        horiz
        & (tdn_z > 18.0)
        & (~has_pos_twin)
        & not_hollow_step
        & (~is_green_wall_cap)
        & ((tup_z < 22.0) | (tdn_z >= 0.30 * np.minimum(tup_z, 120.0)))
    )

    for zv, b_poly in buried_slab_xy.items():
        on_z = horiz & (np.abs(cent[:, 2] - zv) < 0.5) & (tup_z <= 42.0)
        fids_z = np.flatnonzero(on_z)
        if len(fids_z) > 0:
            in_b = shapely.contains_xy(b_poly, cent[fids_z, 0], cent[fids_z, 1])
            buried_fids = fids_z[in_b]
            horiz_up_vis[buried_fids] = False
            horiz_dn_vis[buried_fids] = False

    # Always preserve white exterior slanted louver blades & horizontal corner louver slats (littletiles_ltcolored0_-1)
    louver_vis = np.zeros(b_mesh.n_faces, dtype=bool)
    if mtl_dict:
        white_louver_mids = {
            mid
            for mid, mname in enumerate(b_mesh.materials)
            if mname in mtl_dict and "ltcolored0" in (mtl_dict[mname].map_kd or "").lower()
        }
        if white_louver_mids:
            is_white_louver = np.isin(b_mesh.face_material, list(white_louver_mids))
            louver_vis = (
                ok
                & is_white_louver
                & (dz <= 15.0)
                & ((tf > 2.0) | (tb > 2.0) | (tup_z > 2.0) | (tdn_z > 2.0))
            )

    # Priority materials: only on stairs / non-major floor slabs (never let ltstone overwrite main quartz_block_top floors!)
    priority_mids = set()
    for mid, mname in enumerate(b_mesh.materials):
        tex_l = (mtl_dict[mname].map_kd or "").lower() if (mtl_dict and mname in mtl_dict) else mname.lower()
        if "Architecture_1st_floor" in mname and any(k in mname for k in ("-01-", "-02-", "-03-", "-04-", "-05-", "-07-", "-08-")):
            priority_mids.add(mid)
        elif any(k in mname.lower() or k in tex_l for k in ("ltstone", "sandstone", "quartz_block_top")):
            priority_mids.add(mid)

    on_major_floor_slab = np.zeros(b_mesh.n_faces, dtype=bool)
    for zv in major_zs:
        on_major_floor_slab |= horiz & (np.abs(cent[:, 2] - zv) < 1.0)

    vis_mask = vert_vis | horiz_up_vis | horiz_dn_vis | louver_vis
    prio_mask = np.isin(b_mesh.face_material, list(priority_mids)) & vis_mask & (~on_major_floor_slab)
    return vis_mask, prio_mask, tf, tb


def purge_strictly_enclosed_ribs_and_dissolve(
    mesh: MeshData, uid: str, mtl_dict: dict[str, Any] | None = None
) -> MeshData:
    fn = face_normals(mesh.positions, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    pts = mesh.positions[mesh.face_v]
    cent = pts.mean(axis=1)
    ok_m = (~np.isnan(fn).any(axis=1)) & (np.linalg.norm(fn, axis=1) > 0.5)
    horiz_mask = ok_m & (np.abs(fn[:, 2]) > 0.95)
    vert_mask = ok_m & (np.abs(fn[:, 2]) < 0.25)

    valid_m_fids = np.flatnonzero(ok_m)
    caster_m = EmbreeCaster(mesh.positions, mesh.face_v[valid_m_fids])
    BARY4 = np.array([[1 / 3, 1 / 3, 1 / 3], [0.6, 0.2, 0.2], [0.2, 0.6, 0.2], [0.2, 0.2, 0.6]])
    samp_m = np.einsum("sb,fbk->fsk", BARY4, pts)
    dirs_m = np.repeat(fn[:, None, :], 4, axis=1).reshape(-1, 3)
    _, tf_m_s = caster_m.first_hit((samp_m + 0.15 * fn[:, None, :]).reshape(-1, 3), dirs_m)
    _, tb_m_s = caster_m.first_hit((samp_m - 0.15 * fn[:, None, :]).reshape(-1, 3), -dirs_m)
    tf_m = tf_m_s.reshape(mesh.n_faces, 4).max(axis=1)
    tb_m = tb_m_s.reshape(mesh.n_faces, 4).max(axis=1)

    pf_m_s = (samp_m + 1.8 * fn[:, None, :]).reshape(-1, 3)
    pb_m_s = (samp_m - 1.8 * fn[:, None, :]).reshape(-1, 3)
    M4 = len(pf_m_s)
    up_m4 = np.tile([0.0, 0.0, 1.0], (M4, 1))
    dn_m4 = np.tile([0.0, 0.0, -1.0], (M4, 1))
    _, pfm_tup = caster_m.first_hit(pf_m_s, up_m4)
    _, pfm_tdn = caster_m.first_hit(pf_m_s, dn_m4)
    _, pbm_tup = caster_m.first_hit(pb_m_s, up_m4)
    _, pbm_tdn = caster_m.first_hit(pb_m_s, dn_m4)
    pfm_ztop = np.median((pf_m_s[:, 2] + pfm_tup).reshape(mesh.n_faces, 4), axis=1)
    pfm_zbot = np.median((pf_m_s[:, 2] - pfm_tdn).reshape(mesh.n_faces, 4), axis=1)
    pbm_ztop = np.median((pb_m_s[:, 2] + pbm_tup).reshape(mesh.n_faces, 4), axis=1)
    pbm_zbot = np.median((pb_m_s[:, 2] - pbm_tdn).reshape(mesh.n_faces, 4), axis=1)
    zm0 = pts[:, :, 2].min(axis=1)
    zm1 = pts[:, :, 2].max(axis=1)
    strictly_enclosed_vert = (
        ((zm1 - zm0) <= 32.0)
        & ((pfm_ztop - pfm_zbot) <= 32.0)
        & ((pbm_ztop - pbm_zbot) <= 32.0)
    )

    h_fids = np.flatnonzero(horiz_mask)
    h_zs = pts[h_fids, :, 2].mean(axis=1)
    h_polys = [Polygon(pts[f, :, :2]).buffer(0.25) for f in h_fids]

    slab_at_z: dict[float, Any] = {}
    for z_val in np.unique(np.round(h_zs, 0)):
        sel = [h_polys[i] for i in range(len(h_fids)) if abs(h_zs[i] - z_val) <= 1.0]
        if sel:
            u_raw = unary_union(sel)
            big_geoms = [g.buffer(6.0).buffer(-7.5) for g in _iter_polys(u_raw) if g.area >= 8000.0]
            if big_geoms:
                slab_at_z[float(z_val)] = unary_union(big_geoms)

    # IMPORTANT: Never drop vertical faces globally! Only drop < 4 in double-wall cavity liners,
    # or vertical ribs that lie inside u_enclosed (between top & bottom horizontal floor slabs) below.
    drop_mask = vert_mask & (tf_m < 4.0) & (tb_m < 4.0)
    v_fids = np.flatnonzero(vert_mask)
    v_zmin = pts[v_fids, :, 2].min(axis=1)
    v_zmax = pts[v_fids, :, 2].max(axis=1)
    v_dz = v_zmax - v_zmin
    z_tops = np.round(v_zmax, 0)

    pf_x = cent[v_fids, 0] + 2.5 * fn[v_fids, 0]
    pf_y = cent[v_fids, 1] + 2.5 * fn[v_fids, 1]
    pb_x = cent[v_fids, 0] - 2.5 * fn[v_fids, 0]
    pb_y = cent[v_fids, 1] - 2.5 * fn[v_fids, 1]

    stair_mids = {
        mid for mid, mn in enumerate(mesh.materials)
        if any(k in mn.lower() for k in ("ltstone", "sandstone"))
        or ("Architecture_1st_floor" in mn and any(k in mn for k in ("-01-", "-02-", "-03-", "-04-", "-05-", "-07-", "-08-")))
    }
    louver_mids = {
        mid
        for mid, mn in enumerate(mesh.materials)
        if (mtl_dict and mn in mtl_dict and "ltcolored0" in (mtl_dict[mn].map_kd or "").lower())
        or "ltcolored0" in mn.lower()
    }

    for zt, u_top in slab_at_z.items():
        if u_top is None or u_top.is_empty:
            continue
        lower_slabs = [slab_at_z[zb] for zb in slab_at_z if (zt - 32.0) <= zb <= (zt - 6.0)]
        if not lower_slabs:
            continue
        u_bot = unary_union(lower_slabs)
        if u_bot is None or u_bot.is_empty:
            continue
        u_enclosed = u_top.intersection(u_bot)
        if u_enclosed.is_empty or u_enclosed.area < 4000.0:
            continue
        sel_idx = np.flatnonzero((np.abs(z_tops - zt) <= 1.0) & (v_dz <= 32.0))
        if len(sel_idx) == 0:
            continue
        in_f = shapely.contains_xy(u_enclosed, pf_x[sel_idx], pf_y[sel_idx])
        in_b = shapely.contains_xy(u_enclosed, pb_x[sel_idx], pb_y[sel_idx])
        for idx_sub in sel_idx[in_f & in_b]:
            gf = int(v_fids[idx_sub])
            if int(mesh.face_material[gf]) not in stair_mids and strictly_enclosed_vert[gf]:
                drop_mask[gf] = True

    v_clusters = cluster_coplanar_faces(mesh.positions, mesh.face_v, fn, vert_mask & (~drop_mask))
    major_walls = []
    for cn, fids in v_clusters:
        if len(fids) < 6:
            continue
        h_dir = np.array([-cn[1], cn[0], 0.0])
        hn = float(np.linalg.norm(h_dir))
        if hn < 1e-6:
            continue
        h_dir /= hn
        z_dir = np.array([0.0, 0.0, 1.0])
        d_val = float((pts[fids, :, :] @ cn).mean())
        polys = [Polygon(np.stack([pts[f] @ h_dir, pts[f] @ z_dir], axis=-1)).buffer(0.5) for f in fids]
        u_w = unary_union([p for p in polys if p.is_valid and p.area > 1.0]).buffer(-0.4)
        if u_w.area > 2000.0:
            major_walls.append((cn, h_dir, d_val, u_w, set(fids)))

    for i in range(len(major_walls)):
        cn_i, h_i, d_i, uw_i, fset_i = major_walls[i]
        for j in range(i + 1, len(major_walls)):
            cn_j, h_j, d_j, uw_j, fset_j = major_walls[j]
            if float(np.dot(cn_i, cn_j)) > 0.995 and 2.0 <= abs(d_i - d_j) <= 16.0:
                ovl_2d = uw_i.intersection(uw_j).buffer(-1.0)
                if not ovl_2d.is_empty and ovl_2d.area > 1000.0:
                    d_min, d_max = min(d_i, d_j), max(d_i, d_j)
                    d_faces = pts @ cn_i
                    f_dmin = d_faces.min(axis=1)
                    f_dmax = d_faces.max(axis=1)
                    dots = np.abs(fn @ cn_i)
                    cand_mask = (
                        vert_mask
                        & (~drop_mask)
                        & (f_dmin >= d_min - 0.35)
                        & (f_dmax <= d_max + 0.35)
                        & (dots <= 0.4)
                        & (tf_m <= 8.0)
                        & (tb_m <= 8.0)
                    )
                    for fo in fset_i | fset_j:
                        cand_mask[fo] = False
                    cand_ids = np.flatnonzero(cand_mask)
                    if len(cand_ids) > 0:
                        h_c = cent[cand_ids] @ h_i
                        z_c = cent[cand_ids, 2]
                        inside_ovl = shapely.contains_xy(ovl_2d, h_c, z_c)
                        for gf in cand_ids[inside_ovl]:
                            if int(mesh.face_material[gf]) not in stair_mids and strictly_enclosed_vert[gf]:
                                drop_mask[gf] = True

    m1, _ = remove_faces(mesh, drop_mask)
    if uid == "Architecture_emergency_stairs":
        return m1

    fn1 = face_normals(m1.positions, m1.face_v, np.ones(m1.n_faces, dtype=bool))
    pts1 = m1.positions[m1.face_v]
    clusters1 = cluster_coplanar_faces(
        m1.positions, m1.face_v, fn1, np.ones(m1.n_faces, dtype=bool), normal_dot_tol=0.992, dist_tol=0.65
    )
    z_min_mesh = float(m1.positions[:, 2].min())

    # Identify quartz_block_top material ID and minor floor stone/bottom/side material IDs on any floor
    q_top_mid = None
    floor_absorb_mids: set[int] = set()
    for mid, mname in enumerate(m1.materials):
        tex_l = (mtl_dict[mname].map_kd or "").lower() if (mtl_dict and mname in mtl_dict) else mname.lower()
        if "quartz_block_top" in tex_l or (uid == "Architecture_dep_2nd_Floor_obj" and "-01-TwoSided" in mname):
            q_top_mid = mid
        elif any(k in tex_l for k in ("ltstone", "quartz_block_bottom", "quartz_block_side")) or (
            uid == "Architecture_dep_2nd_Floor_obj" and "-06-TwoSided" in mname
        ):
            floor_absorb_mids.add(mid)

    new_pos_list: list[np.ndarray] = []
    new_uv_list: list[np.ndarray] = []
    new_fv_list: list[list[int]] = []
    new_fvt_list: list[list[int]] = []
    new_fmat_list: list[int] = []
    v_cache: dict[tuple[int, int, int], int] = {}

    def get_v_idx(p3: np.ndarray) -> int:
        key = (
            int(round(float(p3[0]) * 12.0)),
            int(round(float(p3[1]) * 12.0)),
            int(round(float(p3[2]) * 12.0)),
        )
        if key in v_cache:
            return v_cache[key]
        idx = len(new_pos_list)
        new_pos_list.append(np.round(p3, 3))
        v_cache[key] = idx
        return idx

    for cn, fids in clusters1:
        u_ax, v_ax = plane_basis(cn)
        p0_plane = pts1[fids[0], 0]
        d_plane = float(np.median((pts1[fids].reshape(-1, 3) - p0_plane) @ cn))
        origin_3d = p0_plane + d_plane * cn
        is_h = abs(float(cn[2])) > 0.95
        z_plane = float(pts1[fids, :, 2].mean())

        mat_areas: dict[int, float] = defaultdict(float)
        f_polys: dict[int, Polygon] = {}
        f_p2: dict[int, np.ndarray] = {}
        for f in fids:
            p2 = np.stack([(pts1[f] - origin_3d) @ u_ax, (pts1[f] - origin_3d) @ v_ax], axis=-1)
            p = Polygon(p2)
            if p.is_valid and p.area > 0.05:
                f_polys[f] = p
                f_p2[f] = p2
                mat_areas[int(m1.face_material[f])] += float(p.area)
        if not f_polys:
            continue

        tot_plane_area = sum(mat_areas.values())
        mat_uv_sol: dict[int, np.ndarray] = {}
        mat_norm_sign: dict[int, float] = {}
        for mid in mat_areas:
            mfids = sorted([f for f in f_polys if int(m1.face_material[f]) == mid], key=lambda x: -f_polys[x].area)
            signs = [1.0 if float(np.dot(fn1[f], cn)) >= 0 else -1.0 for f in mfids]
            mat_norm_sign[mid] = (
                1.0
                if sum(signs[i] * float(f_polys[mfids[i]].area) for i in range(len(mfids))) >= 0
                else -1.0
            )
            for rf in mfids[:10]:
                vt_ids = m1.face_vt[rf]
                if (vt_ids >= 0).all() and m1.uvs is not None and len(m1.uvs) > 0:
                    rp2 = f_p2[rf]
                    if np.linalg.matrix_rank(rp2[1:] - rp2[0]) == 2:
                        A = np.column_stack([rp2, np.ones(3)])
                        try:
                            mat_uv_sol[mid] = np.linalg.solve(A, m1.uvs[vt_ids])
                            break
                        except Exception:
                            pass

        by_mat: dict[int, list[Polygon]] = defaultdict(list)
        for f, p in f_polys.items():
            mid = int(m1.face_material[f])
            # On horizontal floor planes dominated by quartz_block_top, absorb any coplanar ltstone / quartz_block_bottom / side triangles into quartz_block_top
            if (
                is_h
                and q_top_mid is not None
                and mid in floor_absorb_mids
                and mat_areas.get(q_top_mid, 0.0) >= max(5000.0, 0.50 * tot_plane_area)
            ):
                mid = q_top_mid
            by_mat[mid].append(p)

        cleaned_by_mat: dict[int, Any] = {}
        for mid, plist in by_mat.items():
            is_delicate = (mid in stair_mids and not is_h) or (mid in louver_mids)
            buf_r = 0.03 if is_delicate else 0.25
            simp_r = 0.02 if is_delicate else (0.08 if is_h else 0.06)
            u_m = (
                unary_union([p.buffer(buf_r, join_style="mitre") for p in plist])
                .buffer(-buf_r, join_style="mitre")
                .simplify(simp_r, preserve_topology=True)
                .buffer(0)
            )
            cleaned = []
            for g in _iter_polys(u_m):
                if g.area < 0.5 if is_delicate else g.area < 2.0:
                    continue
                holes = []
                for r in g.interiors:
                    hp = Polygon(r)
                    # Remove small holes (< 64 sq in) and narrow slits (< 3.6 in wide everywhere)
                    if hp.area < 64.0 or hp.buffer(-1.8).is_empty:
                        continue
                    holes.append(r)
                cp = Polygon(g.exterior, holes).simplify(simp_r, preserve_topology=True)
                cleaned.append(cp)
            if cleaned:
                cleaned_by_mat[mid] = unary_union(cleaned).buffer(0)

        non_ovl_by_mat: dict[int, Any] = {}
        all_ring_pts: list[tuple[float, float]] = []
        cov_plane = Polygon()
        sorted_mids = sorted(
            cleaned_by_mat.keys(),
            key=lambda k: (
                0 if (is_h and k == q_top_mid) else (1 if k in stair_mids else 2),
                -mat_areas.get(k, 0.0),
            ),
        )
        for mid in sorted_mids:
            u_clean = cleaned_by_mat[mid]
            if not cov_plane.is_empty:
                u_clean = u_clean.difference(cov_plane).buffer(0)
            if u_clean.is_empty or (u_clean.area < 0.5 if mid in louver_mids else u_clean.area < 2.0):
                continue
            cov_plane = cov_plane.union(u_clean) if not cov_plane.is_empty else u_clean
            non_ovl_by_mat[mid] = u_clean
            for g in _iter_polys(u_clean):
                all_ring_pts.extend((float(x), float(y)) for x, y in g.exterior.coords)
                for h_r in g.interiors:
                    all_ring_pts.extend((float(x), float(y)) for x, y in h_r.coords)

        snap_mp = MultiPoint(all_ring_pts) if (len(non_ovl_by_mat) > 1 and len(all_ring_pts) <= 800) else None
        for mid, u_clean in non_ovl_by_mat.items():
            u_orig = u_clean
            if snap_mp is not None:
                snapped = shapely.snap(u_clean, snap_mp, 0.25)
                u_clean = snapped if snapped.is_valid else snapped.buffer(0)
            try:
                cdt = shapely.constrained_delaunay_triangles(u_clean)
            except Exception:
                try:
                    cdt = shapely.constrained_delaunay_triangles(u_orig.buffer(0.01).buffer(-0.01))
                except Exception:
                    dt_raw = shapely.delaunay_triangles(u_orig)
                    cdt = unary_union([p.intersection(u_orig) for p in _iter_polys(dt_raw)])
            t_list = [p for p in _iter_polys(cdt) if p.is_valid and p.area > 0.2]
            target_n = cn * mat_norm_sign.get(mid, 1.0)
            if is_h and z_plane <= z_min_mesh + 140.0 and float(target_n[2]) < 0:
                target_n = -target_n
            sol = mat_uv_sol.get(mid)
            for tp in t_list:
                coords2d = np.asarray(tp.exterior.coords[:3], dtype=np.float64)
                if len(coords2d) < 3:
                    continue
                p3_tri = [origin_3d + c2[0] * u_ax + c2[1] * v_ax for c2 in coords2d]
                v_ids = [get_v_idx(p3) for p3 in p3_tri]
                if len(set(v_ids)) < 3:
                    continue
                cr = np.cross(
                    new_pos_list[v_ids[1]] - new_pos_list[v_ids[0]],
                    new_pos_list[v_ids[2]] - new_pos_list[v_ids[0]],
                )
                if float(np.linalg.norm(cr)) < 1e-4:
                    continue
                if float(np.dot(cr, target_n)) < 0:
                    v_ids = [v_ids[0], v_ids[2], v_ids[1]]
                    coords2d = coords2d[[0, 2, 1]]
                if sol is not None:
                    uv_tri = np.column_stack([coords2d, np.ones(3)]) @ sol
                else:
                    uv_tri = coords2d * 0.01
                vt_base = len(new_uv_list)
                new_uv_list.extend(uv_tri)
                new_fv_list.append(v_ids)
                new_fvt_list.append([vt_base, vt_base + 1, vt_base + 2])
                new_fmat_list.append(mid)

    out = copy.deepcopy(m1)
    out.positions = np.asarray(new_pos_list, dtype=np.float64)
    out.uvs = np.asarray(new_uv_list, dtype=np.float64)
    out.face_v = np.asarray(new_fv_list, dtype=np.int64)
    out.face_vt = np.asarray(new_fvt_list, dtype=np.int64)
    out.face_material = np.asarray(new_fmat_list, dtype=np.int64)
    fn_out = face_normals(out.positions, out.face_v, np.ones(out.n_faces, dtype=bool))
    out.normals = np.round(fn_out, 4)
    out.face_vn = np.repeat(np.arange(out.n_faces, dtype=np.int64)[:, None], 3, axis=1)
    out.face_line = np.zeros(out.n_faces, dtype=np.int64)
    return out


def restore_and_clean_unit(uid: str, s11_folder: str) -> MeshData:
    orig_dir = ORIG_ARCHI / s11_folder
    if not orig_dir.exists():
        orig_dir = ORIG_ARCHI / "Model-Floor_ER-Stairs"
    b_raw = read_obj(orig_dir / f"{uid}.obj")
    b_raw.positions = np.round(convert_unity_to_ckpt17_coords(b_raw.positions), 4)
    mtl_dict = parse_mtl(orig_dir / f"{uid}.mtl")
    b_mesh = prepare_building_materials(b_raw, mtl_dict)

    s11_path = UC_GAME_ARCHI / s11_folder / f"{uid}.fixed.obj"
    s11 = read_obj(s11_path)
    s11.positions = np.round(convert_unity_to_ckpt17_coords(s11.positions), 4)

    mat_remap = [b_mesh.materials.index(m) if m in b_mesh.materials else 0 for m in s11.materials]
    s11.materials = list(b_mesh.materials)
    s11.face_material = np.asarray([mat_remap[int(m)] for m in s11.face_material], dtype=np.int64)

    pts_b = b_mesh.positions[b_mesh.face_v]
    fn_b = face_normals(b_mesh.positions, b_mesh.face_v, np.ones(b_mesh.n_faces, dtype=bool))
    ok_b = (~np.isnan(fn_b).any(axis=1)) & (np.linalg.norm(fn_b, axis=1) > 0.5)
    pts_u = s11.positions[s11.face_v]
    fn_u = face_normals(s11.positions, s11.face_v, np.ones(s11.n_faces, dtype=bool))

    b_valid_fids = np.flatnonzero(ok_b)
    caster_b = EmbreeCaster(b_mesh.positions, b_mesh.face_v[b_valid_fids])
    BARY4 = np.array([[1 / 3, 1 / 3, 1 / 3], [0.6, 0.2, 0.2], [0.2, 0.6, 0.2], [0.2, 0.2, 0.6]])
    samp_u = np.einsum("sb,fbk->fsk", BARY4, pts_u)
    dirs4 = np.repeat(fn_u[:, None, :], 4, axis=1).reshape(-1, 3)
    h1, t1 = caster_b.first_hit((samp_u - 0.6 * fn_u[:, None, :]).reshape(-1, 3), dirs4)
    h2, t2 = caster_b.first_hit((samp_u + 0.6 * fn_u[:, None, :]).reshape(-1, 3), -dirs4)

    use_1 = t1 <= t2
    t_best = np.where(use_1, t1, t2).reshape(s11.n_faces, 4)
    h_best = np.where(use_1, h1, h2).reshape(s11.n_faces, 4)
    hit_fn = fn_b[b_valid_fids[np.maximum(h_best, 0)]]
    dot_parallel = np.abs(np.einsum("fsk,fk->fs", hit_fn, fn_u))
    sample_on_b = (h_best >= 0) & (t_best <= 1.25) & (dot_parallel > 0.94)
    drop_u = ~sample_on_b.all(axis=1)

    cent_u = pts_u.mean(axis=1)
    up_u_vec = np.tile([0.0, 0.0, 1.0], (s11.n_faces, 1))
    dn_u_vec = np.tile([0.0, 0.0, -1.0], (s11.n_faces, 1))
    _, tup_u = caster_b.first_hit(cent_u + np.array([0.0, 0.0, 3.0]), up_u_vec)
    _, tdn_u = caster_b.first_hit(cent_u - np.array([0.0, 0.0, 3.0]), dn_u_vec)

    U4 = s11.n_faces * 4
    up_u4 = np.tile([0.0, 0.0, 1.0], (U4, 1))
    dn_u4 = np.tile([0.0, 0.0, -1.0], (U4, 1))
    _, tup_u_s = caster_b.first_hit((samp_u + np.array([0.0, 0.0, 2.0])).reshape(-1, 3), up_u4)
    _, tdn_u_s = caster_b.first_hit((samp_u - np.array([0.0, 0.0, 2.0])).reshape(-1, 3), dn_u4)
    tup_u_max = tup_u_s.reshape(s11.n_faces, 4).max(axis=1)
    tdn_u_max = tdn_u_s.reshape(s11.n_faces, 4).max(axis=1)
    horiz_u = np.abs(fn_u[:, 2]) >= 0.25
    vert_u = np.abs(fn_u[:, 2]) < 0.25
    # Only drop horizontal faces in s11 if buried inside a thin hollow step/slab (tup <= 6.5 and tdn <= 6.5)
    drop_u |= horiz_u & (tup_u_max <= 6.5) & (tdn_u_max <= 6.5)

    _, tf_u_s = caster_b.first_hit((samp_u + 0.15 * fn_u[:, None, :]).reshape(-1, 3), dirs4)
    _, tb_u_s = caster_b.first_hit((samp_u - 0.15 * fn_u[:, None, :]).reshape(-1, 3), -dirs4)
    tf_u = tf_u_s.reshape(s11.n_faces, 4).max(axis=1)
    tb_u = tb_u_s.reshape(s11.n_faces, 4).max(axis=1)
    # Only drop < 4 in double-wall cavity liners in s11 (never drop real vertical walls!)
    drop_u |= vert_u & (tf_u < 4.0) & (tb_u < 4.0)

    up_b_fids = np.flatnonzero(ok_b & (fn_b[:, 2] > 0.9))
    dn_b_fids = np.flatnonzero(ok_b & (fn_b[:, 2] < -0.9))
    is_floor_top = (tup_u > 42.0) & ((np.isinf(tup_u) & ~np.isinf(tdn_u)) | (tup_u > tdn_u + 15.0) | (np.isinf(tup_u) & np.isinf(tdn_u)))
    is_ceil_bot = (tdn_u > 42.0) & ((np.isinf(tdn_u) & ~np.isinf(tup_u)) | (tdn_u > tup_u + 15.0))

    if len(up_b_fids) > 0:
        caster_up_b = EmbreeCaster(b_mesh.positions, b_mesh.face_v[up_b_fids])
        hu_up, tu_up = caster_up_b.first_hit(cent_u + np.array([0.0, 0.0, 0.6]), dn_u_vec)
        for f in np.flatnonzero((~drop_u) & (np.abs(fn_u[:, 2]) > 0.9) & is_floor_top):
            if hu_up[f] >= 0 and tu_up[f] <= 1.2:
                bf_up = int(up_b_fids[hu_up[f]])
                s11.face_material[f] = b_mesh.face_material[bf_up]
                if fn_u[f, 2] < 0:
                    s11.face_v[f] = s11.face_v[f, [0, 2, 1]]
                    s11.face_vt[f] = s11.face_vt[f, [0, 2, 1]]
                    fn_u[f] = -fn_u[f]
    if len(dn_b_fids) > 0:
        caster_dn_b = EmbreeCaster(b_mesh.positions, b_mesh.face_v[dn_b_fids])
        hu_dn, tu_dn = caster_dn_b.first_hit(cent_u - np.array([0.0, 0.0, 0.6]), up_u_vec)
        for f in np.flatnonzero((~drop_u) & (np.abs(fn_u[:, 2]) > 0.9) & is_ceil_bot):
            if hu_dn[f] >= 0 and tu_dn[f] <= 1.2:
                bf_dn = int(dn_b_fids[hu_dn[f]])
                s11.face_material[f] = b_mesh.face_material[bf_dn]
                if fn_u[f, 2] > 0:
                    s11.face_v[f] = s11.face_v[f, [0, 2, 1]]
                    s11.face_vt[f] = s11.face_vt[f, [0, 2, 1]]
                    fn_u[f] = -fn_u[f]

    s11_clean, _ = remove_faces(s11, drop_u)

    vis_b_mask, prio_b_mask, tf_b, tb_b = compute_visible_before_mask(b_mesh, mtl_dict)
    pts_a = s11_clean.positions[s11_clean.face_v]
    fn_a = face_normals(s11_clean.positions, s11_clean.face_v, np.ones(s11_clean.n_faces, dtype=bool))

    all_pos = np.vstack([b_mesh.positions, s11_clean.positions])
    all_fv = np.vstack([b_mesh.face_v, s11_clean.face_v + len(b_mesh.positions)])
    all_fn = np.vstack([fn_b, fn_a])
    valid_all = np.concatenate([vis_b_mask, np.ones(s11_clean.n_faces, dtype=bool)])
    clusters = cluster_coplanar_faces(
        all_pos, all_fv, all_fn, valid_all, normal_dot_tol=0.992, dist_tol=0.65
    )

    drop_a_mask = np.zeros(s11_clean.n_faces, dtype=bool)
    new_pos_list: list[np.ndarray] = []
    new_uv_list: list[np.ndarray] = []
    new_fv_list: list[list[int]] = []
    new_fvt_list: list[list[int]] = []
    new_fmat_list: list[int] = []
    next_v_idx = len(s11_clean.positions)
    next_vt_idx = len(s11_clean.uvs) if s11_clean.uvs is not None else 0

    for cn, fids in clusters:
        bfids = [f for f in fids if f < b_mesh.n_faces and vis_b_mask[f]]
        afids = [f - b_mesh.n_faces for f in fids if f >= b_mesh.n_faces]
        if not bfids:
            continue
        u_ax, v_ax = plane_basis(cn)

        prio_bfids = [f for f in bfids if prio_b_mask[f]]
        prio_cov = Polygon()
        if prio_bfids:
            for pf_id in prio_bfids:
                p2 = np.stack([pts_b[pf_id] @ u_ax, pts_b[pf_id] @ v_ax], axis=-1)
                pl = Polygon(p2)
                if not pl.is_valid or pl.area < 0.5:
                    continue
                if not prio_cov.is_empty and pl.intersection(prio_cov).area > 0.75 * pl.area:
                    continue
                prio_cov = prio_cov.union(pl) if not prio_cov.is_empty else pl
                orig_fvt = b_mesh.face_vt[pf_id]
                uvs_f = b_mesh.uvs[orig_fvt] if (orig_fvt >= 0).all() else None
                target_fn_p = fn_b[pf_id].copy()
                if abs(float(target_fn_p[2])) > 0.85 and float(target_fn_p[2]) < 0:
                    target_fn_p = -target_fn_p
                npos, nuv, nfv, nfvt, nfmat, next_v_idx, next_vt_idx = _triangulate_clipped_face(
                    pts_b[pf_id], p2, np.array([-1, -1, -1], dtype=np.int64), np.array([-1, -1, -1], dtype=np.int64),
                    uvs_f, target_fn_p, int(b_mesh.face_material[pf_id]), pl, next_v_idx, next_vt_idx,
                )
                if nfv:
                    new_pos_list.extend(npos)
                    new_uv_list.extend(nuv)
                    new_fv_list.extend(nfv)
                    new_fvt_list.extend(nfvt)
                    new_fmat_list.extend(nfmat)

            if not prio_cov.is_empty:
                prio_buf = prio_cov.buffer(0.02)
                for af in afids:
                    ap2 = np.stack([pts_a[af] @ u_ax, pts_a[af] @ v_ax], axis=-1)
                    apl = Polygon(ap2)
                    if not apl.is_valid or apl.area < 0.5:
                        continue
                    ovl_a = apl.intersection(prio_buf).area
                    if ovl_a > 1.0:
                        drop_a_mask[af] = True
                        rem_a = apl.difference(prio_buf).buffer(0)
                        if not rem_a.is_empty and rem_a.area >= 6.0:
                            orig_fvt = s11_clean.face_vt[af]
                            uvs_f = s11_clean.uvs[orig_fvt] if (orig_fvt >= 0).all() else None
                            npos, nuv, nfv, nfvt, nfmat, next_v_idx, next_vt_idx = _triangulate_clipped_face(
                                pts_a[af], ap2, np.array([-1, -1, -1], dtype=np.int64), np.array([-1, -1, -1], dtype=np.int64),
                                uvs_f, fn_a[af], int(s11_clean.face_material[af]), rem_a, next_v_idx, next_vt_idx,
                            )
                            if nfv:
                                new_pos_list.extend(npos)
                                new_uv_list.extend(nuv)
                                new_fv_list.extend(nfv)
                                new_fvt_list.extend(nfvt)
                                new_fmat_list.extend(nfmat)

        kept_a_polys = [
            Polygon(np.stack([pts_a[af] @ u_ax, pts_a[af] @ v_ax], axis=-1))
            for af in afids
            if not drop_a_mask[af]
        ]
        a_u = unary_union([p for p in kept_a_polys if p.is_valid and p.area > 0.25]) if kept_a_polys else Polygon()
        if not prio_cov.is_empty:
            a_u = a_u.union(prio_cov) if not a_u.is_empty else prio_cov
        # Use 0.02 in buffer (no 0.25 in moat!) so restored wall/floor faces meet s11 faces seamlessly
        a_u_buf = a_u.buffer(0.02) if not a_u.is_empty else Polygon()

        # Sort bfids so front-facing faces (tf_b > tb_b) and faces matching s11 materials on this plane go first
        a_mids_on_plane = {int(s11_clean.face_material[af]) for af in afids if not drop_a_mask[af]}
        bfids_sorted = sorted(
            bfids,
            key=lambda bf: (
                0 if int(b_mesh.face_material[bf]) in a_mids_on_plane else 1,
                0 if float(tf_b[bf]) >= float(tb_b[bf]) else 1,
                -float(tf_b[bf]),
            ),
        )

        restored_on_plane = Polygon()
        for bf in bfids_sorted:
            if prio_b_mask[bf]:
                continue
            bp2 = np.stack([pts_b[bf] @ u_ax, pts_b[bf] @ v_ax], axis=-1)
            bpl = Polygon(bp2)
            if not bpl.is_valid or bpl.area < 0.5:
                continue
            rem_b = bpl.difference(a_u_buf).buffer(0) if not a_u_buf.is_empty else bpl
            if not restored_on_plane.is_empty and not rem_b.is_empty:
                rem_b = rem_b.difference(restored_on_plane).buffer(0)
            if rem_b.is_empty or rem_b.area < 0.5 or rem_b.area < 0.12 * bpl.area:
                continue
            orig_fvt = b_mesh.face_vt[bf]
            uvs_f = b_mesh.uvs[orig_fvt] if (orig_fvt >= 0).all() else None
            target_fn_b = fn_b[bf].copy()
            if abs(float(target_fn_b[2])) > 0.85 and float(target_fn_b[2]) < 0 and float(tf_b[bf]) < float(tb_b[bf]):
                target_fn_b = -target_fn_b
            npos, nuv, nfv, nfvt, nfmat, next_v_idx, next_vt_idx = _triangulate_clipped_face(
                pts_b[bf], bp2, np.array([-1, -1, -1], dtype=np.int64), np.array([-1, -1, -1], dtype=np.int64),
                uvs_f, target_fn_b, int(b_mesh.face_material[bf]), rem_b, next_v_idx, next_vt_idx,
            )
            if nfv:
                new_pos_list.extend(npos)
                new_uv_list.extend(nuv)
                new_fv_list.extend(nfv)
                new_fvt_list.extend(nfvt)
                new_fmat_list.extend(nfmat)
                restored_on_plane = restored_on_plane.union(bpl) if not restored_on_plane.is_empty else bpl

    out, _ = remove_faces(s11_clean, drop_a_mask)
    if new_fv_list:
        if new_pos_list:
            out.positions = np.vstack([out.positions, np.asarray(new_pos_list, dtype=np.float64)])
        if new_uv_list:
            out.uvs = np.vstack([out.uvs, np.asarray(new_uv_list, dtype=np.float64)])
        out.face_v = np.vstack([out.face_v, np.asarray(new_fv_list, dtype=np.int64)])
        out.face_vt = np.vstack([out.face_vt, np.asarray(new_fvt_list, dtype=np.int64)])
        out.face_vn = np.vstack([out.face_vn, np.full((len(new_fv_list), 3), -1, dtype=np.int64)])
        out.face_material = np.concatenate([out.face_material, np.asarray(new_fmat_list, dtype=np.int64)])
        out.face_line = np.concatenate([out.face_line, np.zeros(len(new_fv_list), dtype=np.int64)])

    out_smooth = purge_strictly_enclosed_ribs_and_dissolve(out, uid, mtl_dict)
    out_smooth, _ = compact_mesh(out_smooth, {})
    fn_out = face_normals(out_smooth.positions, out_smooth.face_v, np.ones(out_smooth.n_faces, dtype=bool))
    out_smooth.normals = np.round(fn_out, 4)
    out_smooth.face_vn = np.repeat(np.arange(out_smooth.n_faces, dtype=np.int64)[:, None], 3, axis=1)
    print(f"[{uid}] STAGE11={s11.n_faces:,} -> Restored={out.n_faces:,} -> Smooth-dissolved={out_smooth.n_faces:,} tris", flush=True)
    return out_smooth


def compact_obj_bytes(m: MeshData) -> bytes:
    uv_pos, inv_pos = np.unique(np.round(m.positions, 3), axis=0, return_inverse=True)
    fv = inv_pos[m.face_v] + 1
    if m.uvs is not None and len(m.uvs) > 0 and (m.face_vt >= 0).all():
        uv_vt, inv_vt = np.unique(np.round(m.uvs, 4), axis=0, return_inverse=True)
        fvt = inv_vt[m.face_vt] + 1
    else:
        uv_vt = np.zeros((1, 2), dtype=np.float64)
        fvt = np.ones((m.n_faces, 3), dtype=np.int64)
    lines = ["mtllib materials.mtl"]
    for x, y, z in uv_pos:
        lines.append(f"v {x:.3f} {y:.3f} {z:.3f}")
    for u, v in uv_vt:
        lines.append(f"vt {u:.4f} {v:.4f}")
    cur_m = -1
    for f in range(m.n_faces):
        mid = int(m.face_material[f])
        if mid != cur_m:
            cur_m = mid
            lines.append(f"usemtl {m.materials[mid]}")
        a, b, c = fv[f]
        ta, tb, tc = fvt[f]
        lines.append(f"f {a}/{ta} {b}/{tb} {c}/{tc}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def run_all_architecture() -> None:
    import shutil
    from merge_flying_and_regroup_buildings import append_faces_from_source, save_updated_unit
    from organize_dashboard_seed import main as regen_seed

    meshes: dict[str, MeshData] = {}
    for uid, s11_folder in ARCHI_UNITS:
        meshes[uid] = restore_and_clean_unit(uid, s11_folder)

    # 1. Move ONLY the 16-triangle V-bay grey trapezoid at Z=1385.83 from 3rd Floor -> 2nd Floor
    m3 = meshes["Architecture_dep_3rd_Floor_obj"]
    pts3 = m3.positions[m3.face_v]
    cent3 = pts3.mean(axis=1)
    vbay_trap_mask = (
        (cent3[:, 0] >= -6000.0)
        & (cent3[:, 0] <= -5650.0)
        & (cent3[:, 1] >= 20700.0)
        & (cent3[:, 1] <= 21100.0)
        & (np.abs(cent3[:, 2] - 1385.83) < 2.0)
    )
    trap_fids = np.flatnonzero(vbay_trap_mask).tolist()
    if trap_fids:
        meshes["Architecture_dep_2nd_Floor_obj"] = append_faces_from_source(
            meshes["Architecture_dep_2nd_Floor_obj"],
            "Architecture_dep_2nd_Floor_obj",
            m3,
            "Architecture_dep_3rd_Floor_obj",
            trap_fids,
        )
        meshes["Architecture_dep_3rd_Floor_obj"], _ = remove_faces(m3, vbay_trap_mask)
        print(f"Moved {len(trap_fids)} V-bay trapezoid tris (Z=1385.83) from 3rd Floor -> 2nd Floor", flush=True)

    # 2. Split 7th Floor Roof & Ceiling (zmin >= 2556.8) into Architecture_dep_7th_Floor_Roof_Ceiling
    m7 = meshes["Architecture_dep_7th_Floor_obj"]
    pts7 = m7.positions[m7.face_v]
    zmin7 = pts7[:, :, 2].min(axis=1)
    roof_mask = zmin7 >= 2556.8
    m7_body, _ = remove_faces(m7, roof_mask)
    m7_roof, _ = remove_faces(m7, ~roof_mask)
    m7_body, _ = compact_mesh(m7_body, {})
    m7_roof, _ = compact_mesh(m7_roof, {})
    meshes["Architecture_dep_7th_Floor_obj"] = m7_body
    meshes["Architecture_dep_7th_Floor_Roof_Ceiling"] = m7_roof
    print(f"Split 7th Floor: body={m7_body.n_faces:,} tris, roof_ceiling={m7_roof.n_faces:,} tris", flush=True)

    # 3. Save all Architecture units to Exports/Repaired-Buildings-20261015 and Siege checkouts (compacted)
    all_save_units = [u for u, _ in ARCHI_UNITS] + ["Architecture_dep_7th_Floor_Roof_Ceiling"]
    for uid in all_save_units:
        fcode = EXPORT_FLOOR_FOLDER[uid]
        m = meshes[uid]
        if uid == "Architecture_dep_7th_Floor_Roof_Ceiling":
            # Ensure export folder & Siege model folder have materials.mtl + textures from 7th floor
            r_dir = EXP_ARCHI / fcode
            r_dir.mkdir(parents=True, exist_ok=True)
            src7_exp = EXP_ARCHI / "Model-Floor_07"
            if src7_exp.is_dir():
                for f_item in src7_exp.iterdir():
                    if f_item.suffix.lower() in (".mtl", ".png", ".jpg"):
                        shutil.copy2(f_item, r_dir / f_item.name)
            comp_bytes = compact_obj_bytes(m)
            (r_dir / f"{uid}.fixed.obj").write_bytes(comp_bytes)
            rep_p = r_dir / f"{uid}.report.json"
            rep_p.write_text(
                json.dumps({"unit": uid, "building": "ARCHITECTURE", "tris_before": 1239, "tris_after": m.n_faces}, indent=2),
                encoding="utf-8",
            )
            for wt in SIEGE_WTS:
                for base in ("dashboard/public/models", "dashboard/deploy-build/public/models"):
                    src_m7 = wt / base / "Architecture_dep_7th_Floor_obj"
                    dst_mr = wt / base / uid
                    if src_m7.is_dir():
                        dst_mr.mkdir(parents=True, exist_ok=True)
                        for f_item in src_m7.iterdir():
                            if f_item.is_file() and f_item.name not in ("before.obj", "after.obj"):
                                shutil.copy2(f_item, dst_mr / f_item.name)
                        (dst_mr / "before.obj").write_bytes(comp_bytes)
                        (dst_mr / "after.obj").write_bytes(comp_bytes)
        else:
            save_updated_unit(uid, m, "Architecture", fcode, uid)
            comp_bytes = compact_obj_bytes(m)
            for wt in SIEGE_WTS:
                for base in ("dashboard/public/models", "dashboard/deploy-build/public/models"):
                    tp = wt / base / uid / "after.obj"
                    if tp.parent.exists():
                        tp.write_bytes(comp_bytes)
        print(f"Saved & compacted {uid}: {m.n_faces:,} tris ({len(comp_bytes):,} bytes)", flush=True)

    # 4. Stage ARCHITECTURE into Blender 5.1 (02_STAGING_DEVELOPMENT) and regenerate seedData.ts + status JSON
    r = apply_repaired_building_to_blender_staging(repair_repo_root=REPAIR_REPO, building="ARCHITECTURE")
    print(f"Staged ARCHITECTURE into Blender 5.1 -> ARCHI_LOD0 = {r['lod0_triangles']:,} tris", flush=True)
    regen_seed()


if __name__ == "__main__":
    run_all_architecture()
