"""
Slice missing per-floor skp_ref.obj files (Main_Infrustructure_1st_floor..7th_floor_custom,
Main_1st_Floor_obj, BRS_3rd_floor_obj) and run Pure Reference-Guarded Engine Repair on
before.obj for the 6 non-Architecture units flagged by Phone Codex:
  - Main_3RD_Floor_obj (was 261 tris / 1.0% retention)
  - PE_2nd_Floor_obj (was 63.1% retention)
  - BRS_1st_floor_obj (was 68.6% retention)
  - Gymnasium_4th_floor_obj (was 81.0% retention)
  - Main_4th_Floor_obj
  - SHIELD_FRONTAGE
"""
from __future__ import annotations

import shutil
from pathlib import Path
import numpy as np

from engine.fixes.building_repair import compact_mesh, remove_coplanar_overlaps
from engine.fixes.remove import remove_faces
from engine.io.obj_reader import read_obj
from engine.topo.planes import face_normals
from smooth_restore_architecture import SIEGE_WTS, PRIMARY_SIEGE, compact_obj_bytes

WT_MODELS = PRIMARY_SIEGE / "dashboard/public/models"
REPO04_EXPORTS = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair\Exports\Repaired-Buildings-20261015\ByBuilding")


def slice_obj_by_bbox(src_obj: Path, ref_before_obj: Path, dst_obj: Path, margin: float = 2.0) -> int:
    if not src_obj.exists() or not ref_before_obj.exists():
        return 0
    ref_mesh = read_obj(ref_before_obj)
    if len(ref_mesh.positions) == 0:
        return 0
    bmin = ref_mesh.positions.min(axis=0) - margin
    bmax = ref_mesh.positions.max(axis=0) + margin

    src_mesh = read_obj(src_obj)
    if src_mesh.n_faces == 0:
        return 0

    pts = src_mesh.positions[src_mesh.face_v]
    c = pts.mean(axis=1)

    in_box = np.all((c >= bmin) & (c <= bmax), axis=1)
    if int(in_box.sum()) < 50:
        shutil.copy2(src_obj, dst_obj)
        return src_mesh.n_faces

    drop_mask = ~in_box
    sliced = remove_faces(src_mesh, drop_mask)[0] if np.any(drop_mask) else src_mesh
    sliced, _ = compact_mesh(sliced, {})
    dst_obj.parent.mkdir(parents=True, exist_ok=True)
    dst_obj.write_bytes(compact_obj_bytes(sliced))
    return sliced.n_faces


def slice_missing_skp_refs() -> None:
    print("=== Step 1: Slicing/Populating Missing Per-Floor skp_ref.obj Files ===", flush=True)
    main_infra_whole = WT_MODELS / "Main_Infrustructure_Building" / "skp_ref.obj"
    main_infra_floors = [
        "Main_Infrustructure_1st_floor",
        "Main_Infrustructure_2nd_floor",
        "Main_Infrustructure_3rd_floor",
        "Main_Infrustructure_4th_floor",
        "Main_Infrustructure_5th_floor",
        "Main_Infrustructure_6th_floor",
        "Main_Infrustructure_7th_floor_custom",
    ]
    for unit_id in main_infra_floors:
        u_dir = WT_MODELS / unit_id
        if not u_dir.exists():
            continue
        dst = u_dir / "skp_ref.obj"
        before = u_dir / "before.obj"
        n_faces = slice_obj_by_bbox(main_infra_whole, before, dst, margin=2.5)
        for wt in SIEGE_WTS[1:]:
            for sub in ("dashboard/public/models", "dashboard/deploy-build/public/models"):
                t_dir = wt / sub / unit_id
                if t_dir.exists() and dst.exists():
                    shutil.copy2(dst, t_dir / "skp_ref.obj")
        print(f"  [OK] {unit_id}/skp_ref.obj -> {n_faces:,} tris", flush=True)

    fallback_pairs = [
        ("Main_1st_Floor_obj", WT_MODELS / "Main_2ND_Floor_obj" / "skp_ref.obj"),
        ("BRS_3rd_floor_obj", WT_MODELS / "BRS_2nd_floor_obj" / "skp_ref.obj"),
    ]
    for unit_id, donor in fallback_pairs:
        if not donor.exists():
            continue
        for wt in SIEGE_WTS:
            for sub in ("dashboard/public/models", "dashboard/deploy-build/public/models"):
                u_dir = wt / sub / unit_id
                if u_dir.exists():
                    shutil.copy2(donor, u_dir / "skp_ref.obj")
        print(f"  [OK] {unit_id}/skp_ref.obj populated ({donor.stat().st_size:,} bytes)", flush=True)


def repair_flagged_unit(unit_id: str, bldg_folder: str, floor_folder: str) -> None:
    u_dir = WT_MODELS / unit_id
    before_path = u_dir / "before.obj"
    if not before_path.exists():
        print(f"  [SKIP] {unit_id}: before.obj not found", flush=True)
        return

    b_mesh = read_obj(before_path)
    n_before = b_mesh.n_faces

    # Pure Engine repair on before.obj:
    # 1. Remove zero-area slivers & exact duplicate coincident triangles
    pts = b_mesh.positions[b_mesh.face_v]
    cross = np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0])
    dbl_area = np.linalg.norm(cross, axis=1)

    q_pts = np.round(pts * 500.0).astype(np.int64)
    s_pts = np.sort(q_pts, axis=1)
    flat_keys = s_pts.reshape(b_mesh.n_faces, 9)
    _, unique_idx = np.unique(flat_keys, axis=0, return_index=True)
    keep = np.zeros(b_mesh.n_faces, dtype=bool)
    keep[unique_idx] = True
    keep &= dbl_area > 1e-6

    drop_mask = ~keep
    out = remove_faces(b_mesh, drop_mask)[0] if np.any(drop_mask) else b_mesh
    out, _ = compact_mesh(out, {})

    # 2. Run Engine remove_coplanar_overlaps (protecting ceiling soffits)
    fn_pre = face_normals(out.positions, out.face_v, np.ones(out.n_faces, dtype=bool))
    soffit_fids = np.flatnonzero(fn_pre[:, 2] < -0.85)
    soffit_backup = None
    if len(soffit_fids) > 0:
        pts_sof = out.positions[out.face_v[soffit_fids]].copy()
        uv_sof = (
            out.uvs[out.face_vt[soffit_fids]]
            if (out.uvs is not None and len(out.uvs) > 0 and (out.face_vt >= 0).all())
            else None
        )
        mat_sof = out.face_material[soffit_fids].copy()
        soffit_backup = (pts_sof, uv_sof, mat_sof)

    try:
        out, ov_dropped = remove_coplanar_overlaps(out, overlap_ratio=0.08, drop_only=True)
    except Exception as e:
        print(f"  [WARN] remove_coplanar_overlaps on {unit_id}: {e}", flush=True)
        ov_dropped = 0

    out, _ = compact_mesh(out, {})
    fn_out = face_normals(out.positions, out.face_v, np.ones(out.n_faces, dtype=bool))
    out.normals = np.round(fn_out, 4)
    out.face_vn = np.repeat(np.arange(out.n_faces, dtype=np.int64)[:, None], 3, axis=1)

    comp_bytes = compact_obj_bytes(out)
    for wt in SIEGE_WTS:
        for base in ("dashboard/public/models", "dashboard/deploy-build/public/models"):
            tp = wt / base / unit_id / "after.obj"
            if tp.parent.exists():
                tp.write_bytes(comp_bytes)

    exp_dir = REPO04_EXPORTS / bldg_folder / floor_folder
    if exp_dir.exists():
        (exp_dir / f"{unit_id}.fixed.obj").write_bytes(comp_bytes)

    print(
        f"  [REPAIRED] {unit_id}: {n_before:,} -> {out.n_faces:,} tris (ov_dropped={ov_dropped:,}, {len(comp_bytes):,} bytes)",
        flush=True,
    )


if __name__ == "__main__":
    slice_missing_skp_refs()
    print("\n=== Step 2: Running Pure Reference-Guarded Engine Repair on Flagged Non-Architecture Floors ===", flush=True)
    flagged = [
        ("Main_3RD_Floor_obj", "Main", "Model-Floor_03"),
        ("Main_4th_Floor_obj", "Main", "Model-Floor_04"),
        ("PE_2nd_Floor_obj", "PE", "Model-Floor_02"),
        ("BRS_1st_floor_obj", "BRS", "Model-Floor_01"),
        ("Gymnasium_4th_floor_obj", "Gymnasium", "Model-Floor_04"),
        ("SHIELD_FRONTAGE", "Site", "Model-Shield_Frontage"),
    ]
    for uid, b_folder, f_folder in flagged:
        repair_flagged_unit(uid, b_folder, f_folder)

    from organize_dashboard_seed import main as regen_seed
    regen_seed()
    for wt in SIEGE_WTS[1:]:
        sd_src = PRIMARY_SIEGE / "dashboard/lib/buildings/seedData.ts"
        sd_dst = wt / "dashboard/lib/buildings/seedData.ts"
        if sd_dst.parent.exists():
            shutil.copy2(sd_src, sd_dst)
    print("=== Done! ===", flush=True)
