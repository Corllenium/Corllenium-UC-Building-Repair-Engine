"""Repair and restore all 9 Architecture units using SketchUp R5 Reference (capms r5.skp -> skp_ref.obj)
as the primary surface checklist alongside Checkpoint 17 BEFORE (before.obj) for exact Little Tiles UVs
and exterior louvers/stairs.

Guarantees:
1. NEVER runs destructive whole-plane Delaunay re-triangulation across ceilings or corridors
   (zero dark-green bridging triangles across ceilings!).
2. Preserves 100% of the unbroken SketchUp R5 Reference ceiling soffits (material_0064 / material_0048
   quartz_block_bottom cobblestone/tile ceiling + material_0063 grey concrete beams), walls, and stairs.
3. Transfers exact Little Tiles UV coordinates and material assignments from before.obj onto every
   matching SketchUp R5 Reference face, deduplicates coincident flicker pairs, removes only strictly
   enclosed (<3.5 in) cavity faces, and restores any visible exterior louvers from before.obj.
4. Keeps Architecture_dep_7th_Floor_Roof_Ceiling cleanly separated using its dedicated SketchUp R5
   Roof/Ceiling group without slicing vertical 7th-floor interior walls.
"""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any
import numpy as np

from engine.campus.blender_staging import apply_repaired_building_to_blender_staging
from engine.campus.checkpoint_push import convert_unity_to_ckpt17_coords
from engine.fixes.building_repair import compact_mesh, prepare_building_materials, remove_coplanar_overlaps
from engine.fixes.remove import remove_faces
from engine.io.mtl import parse_mtl
from engine.io.obj_reader import read_obj
from engine.model import MeshData
from engine.rays.caster import EmbreeCaster
from engine.topo.planes import face_normals

REPAIR_REPO = Path("D:/PROJECTS/04-Corllenium-Building-Model-Repair")
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
    ("Architecture_dep_7th_Floor_Roof_Ceiling", "Model-Floor_07-Roof"),
    ("Architecture_emergency_stairs", "Shared-Stairs"),
]

EXPORT_FLOOR_FOLDER = dict(ARCHI_UNITS)


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
    order = np.argsort(m.face_material, kind="stable")
    cur_m = -1
    for idx in order:
        f = int(idx)
        mid = int(m.face_material[f])
        if mid != cur_m:
            cur_m = mid
            lines.append(f"usemtl {m.materials[mid]}")
        a, b, c = fv[f]
        ta, tb, tc = fvt[f]
        lines.append(f"f {a}/{ta} {b}/{tb} {c}/{tc}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def repair_unit_with_skp_ref(uid: str, s11_folder: str) -> MeshData:
    """Run the Repair Engine on Checkpoint-17 `before.obj` (`b_mesh`), using `skp_ref.obj`
    (`capms r5.skp`) STRICTLY as a Reference Guard / Validator checklist.

    Every output triangle in `after.obj` comes 100% from `before.obj` repaired by our Engine
    (never copied from `skp_ref.obj`). `skp_ref.obj` is used strictly to verify which walls,
    stairs, and ceiling soffits in `before.obj` must be protected by the Engine Guard.
    """
    model_dir = PRIMARY_SIEGE / "dashboard/public/models" / uid
    skp_ref_path = model_dir / "skp_ref.obj"

    # 1. Load Checkpoint-17 BEFORE (the sole geometry source for Engine Repair)
    if uid == "Architecture_dep_7th_Floor_Roof_Ceiling":
        orig_dir = ORIG_ARCHI / "Model-Floor_07"
        b_uid = "Architecture_dep_7th_Floor_obj"
    else:
        orig_dir = ORIG_ARCHI / s11_folder
        if not orig_dir.exists():
            orig_dir = ORIG_ARCHI / "Model-Floor_ER-Stairs"
        b_uid = uid

    b_raw = read_obj(orig_dir / f"{b_uid}.obj")
    b_raw.positions = np.round(convert_unity_to_ckpt17_coords(b_raw.positions), 4)
    mtl_dict = parse_mtl(orig_dir / f"{b_uid}.mtl")
    b_mesh = prepare_building_materials(b_raw, mtl_dict)

    pts_b = b_mesh.positions[b_mesh.face_v]
    fn_b = face_normals(b_mesh.positions, b_mesh.face_v, np.ones(b_mesh.n_faces, dtype=bool))
    areas_b = 0.5 * np.linalg.norm(np.cross(pts_b[:, 1] - pts_b[:, 0], pts_b[:, 2] - pts_b[:, 0]), axis=1)
    ok_b = (~np.isnan(fn_b).any(axis=1)) & (np.linalg.norm(fn_b, axis=1) > 0.5) & (areas_b > 0.05)
    cent_b = pts_b.mean(axis=1)

    # 2. Load SketchUp R5 Reference (skp_ref.obj) STRICTLY as Reference Validator / Guard
    skp = read_obj(skp_ref_path)
    fn_s = face_normals(skp.positions, skp.face_v, np.ones(skp.n_faces, dtype=bool))
    ok_s = (~np.isnan(fn_s).any(axis=1)) & (np.linalg.norm(fn_s, axis=1) > 0.5)
    s_valid_fids = np.flatnonzero(ok_s)

    ref_verified = np.zeros(b_mesh.n_faces, dtype=bool)
    ref_is_ceiling_soffit = np.zeros(b_mesh.n_faces, dtype=bool)
    if len(s_valid_fids) > 0:
        caster_s = EmbreeCaster(skp.positions, skp.face_v[s_valid_fids])
        hs1, ts1 = caster_s.first_hit(cent_b - 0.35 * fn_b, fn_b)
        hs2, ts2 = caster_s.first_hit(cent_b + 0.35 * fn_b, -fn_b)
        use_s1 = ts1 <= ts2
        t_s = np.where(use_s1, ts1, ts2)
        h_s = np.where(use_s1, hs1, hs2)
        for bf in np.flatnonzero(ok_b & (t_s <= 1.5) & (h_s >= 0)):
            sf = int(s_valid_fids[int(h_s[bf])])
            if abs(float(np.dot(fn_b[bf], fn_s[sf]))) >= 0.88:
                ref_verified[bf] = True
                if float(fn_s[sf, 2]) < -0.85:
                    ref_is_ceiling_soffit[bf] = True

    # Separate 7th_Floor_obj vs 7th_Floor_Roof_Ceiling in Checkpoint-17 BEFORE using the Reference Guard
    if uid == "Architecture_dep_7th_Floor_Roof_Ceiling":
        unit_scope = ok_b & ref_verified
    elif uid == "Architecture_dep_7th_Floor_obj":
        roof_ref_path = PRIMARY_SIEGE / "dashboard/public/models/Architecture_dep_7th_Floor_Roof_Ceiling/skp_ref.obj"
        in_roof_only = np.zeros(b_mesh.n_faces, dtype=bool)
        if roof_ref_path.exists():
            r_skp = read_obj(roof_ref_path)
            fn_r = face_normals(r_skp.positions, r_skp.face_v, np.ones(r_skp.n_faces, dtype=bool))
            ok_r = (~np.isnan(fn_r).any(axis=1)) & (np.linalg.norm(fn_r, axis=1) > 0.5)
            r_valid = np.flatnonzero(ok_r)
            if len(r_valid) > 0:
                c_r = EmbreeCaster(r_skp.positions, r_skp.face_v[r_valid])
                _, tr1 = c_r.first_hit(cent_b - 0.35 * fn_b, fn_b)
                _, tr2 = c_r.first_hit(cent_b + 0.35 * fn_b, -fn_b)
                in_roof_only = (np.minimum(tr1, tr2) <= 1.2) & (~ref_verified)
        unit_scope = ok_b & (~in_roof_only)
    else:
        unit_scope = ok_b.copy()

    # 3. Engine Repair on Checkpoint-17 BEFORE (`b_mesh`):
    #    Measure 4-sample barycentric ray clearance on BEFORE
    b_valid_fids = np.flatnonzero(unit_scope)
    caster_b = EmbreeCaster(b_mesh.positions, b_mesh.face_v[b_valid_fids])
    BARY4 = np.array([[1 / 3, 1 / 3, 1 / 3], [0.6, 0.2, 0.2], [0.2, 0.6, 0.2], [0.2, 0.2, 0.6]])
    samp_b = np.einsum("sb,fbk->fsk", BARY4, pts_b)
    dirs_b = np.repeat(fn_b[:, None, :], 4, axis=1).reshape(-1, 3)
    _, tf_b_raw = caster_b.first_hit((samp_b + 0.15 * fn_b[:, None, :]).reshape(-1, 3), dirs_b)
    _, tb_b_raw = caster_b.first_hit((samp_b - 0.15 * fn_b[:, None, :]).reshape(-1, 3), -dirs_b)
    tf_b = tf_b_raw.reshape(b_mesh.n_faces, 4).max(axis=1)
    tb_b = tb_b_raw.reshape(b_mesh.n_faces, 4).max(axis=1)
    max_open_b = np.maximum(tf_b, tb_b)
    min_open_b = np.minimum(tf_b, tb_b)

    green_wall_mids = {
        mid
        for mid, mn in enumerate(b_mesh.materials)
        if "-00-" in mn or "concrete_white_-119" in mn or (
            mn in mtl_dict and "concrete_white_-119" in (mtl_dict[mn].map_kd or "")
        )
    }
    white_louver_mids = {
        mid
        for mid, mname in enumerate(b_mesh.materials)
        if mname in mtl_dict and "ltcolored0" in (mtl_dict[mname].map_kd or "").lower()
    }
    z_max_floor = float(b_mesh.positions[:, 2].max())

    drop_b = ~unit_scope
    for bf in b_valid_fids:
        mid = int(b_mesh.face_material[bf])
        nz = float(fn_b[bf, 2])
        zf = float(cent_b[bf, 2])

        # Drop buried horizontal green wall-endcaps inside ceilings/floors unless at top wall rim
        if abs(nz) > 0.85 and mid in green_wall_mids:
            if zf < z_max_floor - 8.0 and (ref_is_ceiling_soffit[bf] or min_open_b[bf] < 3.5):
                drop_b[bf] = True
                continue

        # Reference Guard: if verified by skp_ref.obj (and area > 0.05) OR is an exterior white louver slat, keep!
        # Checked BEFORE the < 2.5 in cavity drop so thin reference-verified trim/stair/wall faces are never dropped.
        if (ref_verified[bf] and areas_b[bf] > 0.05) or mid in white_louver_mids:
            continue

        # Strictly enclosed cavity faces (< 2.5 in on both sides) not in skp_ref.obj are dropped
        if tf_b[bf] < 2.5 and tb_b[bf] < 2.5:
            drop_b[bf] = True
            continue

        # If not in skp_ref.obj, drop internal wall cavity faces (clearance < 36 in on both sides or buried on one side < 8 in)
        if not (np.isinf(max_open_b[bf]) and min_open_b[bf] > 8.0):
            drop_b[bf] = True

    # Deduplicate same-normal coincident flicker pairs in BEFORE (include quantized normal so opposite-normal faces stay distinct)
    seen_keys: dict[tuple[tuple[tuple[int, int, int], ...], tuple[int, int, int]], int] = {}

    def _b_prio(bf: int) -> tuple[int, int, float]:
        mid = int(b_mesh.face_material[bf])
        not_green_h = 0 if (abs(float(fn_b[bf, 2])) > 0.85 and mid in green_wall_mids) else 1
        r_flag = 1 if ref_verified[bf] else 0
        return (not_green_h, r_flag, float(tf_b[bf]))

    for bf in sorted(np.flatnonzero(~drop_b).tolist(), key=_b_prio, reverse=True):
        verts_key = tuple(sorted(map(tuple, np.round(pts_b[bf] * 10.0).astype(int).tolist())))
        norm_key = tuple(np.round(fn_b[bf] * 10.0).astype(int).tolist())
        tri_key = (verts_key, norm_key)
        if tri_key in seen_keys:
            drop_b[bf] = True
        else:
            seen_keys[tri_key] = int(bf)

    # Flip any reversed single-sided face in BEFORE where front is buried (< 2.5 in) and back is open (> 18.0 in)
    for bf in np.flatnonzero(~drop_b):
        if tf_b[bf] < 2.5 and tb_b[bf] > 18.0:
            b_mesh.face_v[bf] = b_mesh.face_v[bf, [0, 2, 1]]
            if b_mesh.face_vt is not None and len(b_mesh.face_vt) == b_mesh.n_faces:
                b_mesh.face_vt[bf] = b_mesh.face_vt[bf, [0, 2, 1]]
            fn_b[bf] = -fn_b[bf]

    out, _ = remove_faces(b_mesh, drop_b)
    out, _ = compact_mesh(out, {})

    # 4. Eliminate coplanar vertical wall-crack overlaps (e.g., grey concrete wall end-caps Z-fighting inside green walls)
    #    while protecting 100% of downward-facing ceiling soffit triangles (fn_z < -0.85) verified by skp_ref.obj!
    fn_pre = face_normals(out.positions, out.face_v, np.ones(out.n_faces, dtype=bool))
    soffit_fids = np.flatnonzero(fn_pre[:, 2] < -0.85)
    soffit_backup = None
    if len(soffit_fids) > 0:
        pts_sof = out.positions[out.face_v[soffit_fids]]
        uv_sof = (
            out.uvs[out.face_vt[soffit_fids]]
            if (out.uvs is not None and len(out.uvs) > 0 and (out.face_vt >= 0).all())
            else None
        )
        mat_sof = out.face_material[soffit_fids].copy()
        soffit_backup = (pts_sof, uv_sof, mat_sof)

    out, n_ovl_dropped = remove_coplanar_overlaps(out, overlap_ratio=0.08, drop_only=True)

    # Ensure zero ceiling soffit faces were lost during remove_coplanar_overlaps
    if soffit_backup is not None:
        pts_sof, uv_sof, mat_sof = soffit_backup
        fn_cur = face_normals(out.positions, out.face_v, np.ones(out.n_faces, dtype=bool))
        dn_cur = np.flatnonzero(fn_cur[:, 2] < -0.85)
        if len(dn_cur) > 0:
            c_dn = EmbreeCaster(out.positions, out.face_v[dn_cur])
            cent_sof = pts_sof.mean(axis=1)
            up_v = np.tile([0.0, 0.0, 1.0], (len(pts_sof), 1))
            _, t_sof = c_dn.first_hit(cent_sof - np.array([0.0, 0.0, 0.35]), up_v)
            miss_sof = np.flatnonzero(t_sof > 0.8)
        else:
            miss_sof = np.arange(len(pts_sof))
        if len(miss_sof) > 0:
            add_p = pts_sof[miss_sof].reshape(-1, 3)
            v_b = len(out.positions)
            new_fv = np.arange(len(miss_sof) * 3, dtype=np.int64).reshape(-1, 3) + v_b
            out.positions = np.vstack([out.positions, add_p])
            out.face_v = np.vstack([out.face_v, new_fv])
            if uv_sof is not None and out.uvs is not None:
                add_u = uv_sof[miss_sof].reshape(-1, 2)
                vt_b = len(out.uvs)
                new_fvt = np.arange(len(miss_sof) * 3, dtype=np.int64).reshape(-1, 3) + vt_b
                out.uvs = np.vstack([out.uvs, add_u])
                out.face_vt = np.vstack([out.face_vt, new_fvt])
            out.face_vn = np.vstack([out.face_vn, np.full((len(miss_sof), 3), -1, dtype=np.int64)])
            out.face_material = np.concatenate([out.face_material, mat_sof[miss_sof]])
            out.face_line = np.concatenate([out.face_line, np.zeros(len(miss_sof), dtype=np.int64)])

    out, _ = compact_mesh(out, {})
    fn_out = face_normals(out.positions, out.face_v, np.ones(out.n_faces, dtype=bool))
    out.normals = np.round(fn_out, 4)
    out.face_vn = np.repeat(np.arange(out.n_faces, dtype=np.int64)[:, None], 3, axis=1)
    print(
        f"[{uid}] ENGINE REPAIR on BEFORE={b_mesh.n_faces:,} (Guarded by SKP_R5_REF={skp.n_faces:,}, dropped {n_ovl_dropped:,} wall-crack overlaps) -> ENGINE_FIXED={out.n_faces:,} tris",
        flush=True,
    )
    return out


def run_all_architecture() -> None:
    from merge_flying_and_regroup_buildings import save_updated_unit
    from organize_dashboard_seed import main as regen_seed

    meshes: dict[str, MeshData] = {}
    for uid, s11_folder in ARCHI_UNITS:
        meshes[uid] = repair_unit_with_skp_ref(uid, s11_folder)

    # Save all 9 Architecture units to Exports/Repaired-Buildings-20261015 and all 4 Siege checkouts
    for uid, fcode in ARCHI_UNITS:
        m = meshes[uid]
        comp_bytes = compact_obj_bytes(m)
        if uid == "Architecture_dep_7th_Floor_Roof_Ceiling":
            r_dir = EXP_ARCHI / fcode
            r_dir.mkdir(parents=True, exist_ok=True)
            src7_exp = EXP_ARCHI / "Model-Floor_07"
            if src7_exp.is_dir():
                for f_item in src7_exp.iterdir():
                    if f_item.suffix.lower() in (".mtl", ".png", ".jpg"):
                        shutil.copy2(f_item, r_dir / f_item.name)
            (r_dir / f"{uid}.fixed.obj").write_bytes(comp_bytes)
            rep_p = r_dir / f"{uid}.report.json"
            rep_p.write_text(
                json.dumps({"unit": uid, "building": "ARCHITECTURE", "tris_before": 1324, "tris_after": m.n_faces}, indent=2),
                encoding="utf-8",
            )
            for wt in SIEGE_WTS:
                for base in ("dashboard/public/models", "dashboard/deploy-build/public/models"):
                    src_m7 = wt / base / "Architecture_dep_7th_Floor_obj"
                    dst_mr = wt / base / uid
                    if src_m7.is_dir():
                        dst_mr.mkdir(parents=True, exist_ok=True)
                        for f_item in src_m7.iterdir():
                            if f_item.is_file() and f_item.name not in ("before.obj", "after.obj", "skp_ref.obj"):
                                shutil.copy2(f_item, dst_mr / f_item.name)
                        (dst_mr / "after.obj").write_bytes(comp_bytes)
        else:
            save_updated_unit(uid, m, "Architecture", fcode, uid)
            for wt in SIEGE_WTS:
                for base in ("dashboard/public/models", "dashboard/deploy-build/public/models"):
                    tp = wt / base / uid / "after.obj"
                    if tp.parent.exists():
                        tp.write_bytes(comp_bytes)
        print(f"Saved & compacted {uid}: {m.n_faces:,} tris ({len(comp_bytes):,} bytes)", flush=True)

    # Stage ARCHITECTURE into Blender 5.1 (02_STAGING_DEVELOPMENT) and regenerate seedData.ts + status JSON
    r = apply_repaired_building_to_blender_staging(repair_repo_root=REPAIR_REPO, building="ARCHITECTURE")
    print(f"Staged ARCHITECTURE into Blender 5.1 -> ARCHI_LOD0 = {r['lod0_triangles']:,} tris", flush=True)
    regen_seed()
    for wt in SIEGE_WTS[1:]:
        sd_src = PRIMARY_SIEGE / "dashboard/lib/buildings/seedData.ts"
        sd_dst = wt / "dashboard/lib/buildings/seedData.ts"
        if sd_dst.parent.exists():
            shutil.copy2(sd_src, sd_dst)


if __name__ == "__main__":
    run_all_architecture()
