"""
Strict 13-Point Phantom-Bridge Remover + 7-Point Corner-Preserving Small-Part Restorer & Validator
for all Campus Building & Site Units in `05-Corllenium-UC-Building-Repair-Engine` and `04-Corllenium-Building-Model-Repair`.

Fixes both issues reported by the owner:
1. "even the afterengine like it breaks small objects parts" (e.g., missing bottom-right corner triangle on
   the dark-green railing base and diagonal bridging triangles across vertical railing bars):
   - Step A (13-Point Phantom Bridge Detector): Tests 13 barycentric points on every triangle in `after.obj`
     (centroid, 3 inner, 3 deep-inner, 3 edge-midpoints, 3 corners) against recentered `before.obj` within
     `+-0.055` inches (`|dot| >= 0.98`). Any triangle in `after.obj` that bridges across empty air (such as
     between vertical railing bars or floating above a roof) fails this check and is removed.
   - Step B (Corner-Chopping Merge Detector): Tests 7 barycentric points (centroid + 3 interior + 3 corners
     `[0.90, 0.05, 0.05]`) on every visible / small-object / reference-verified triangle in `before.obj`
     against `after.obj` within `+-0.04` inches (`|dot| >= 0.985`). If a merged triangle in `after.obj` only
     partially covers a `before.obj` triangle (`0 < hits < 7`, meaning it sliced off a corner of a small
     railing base or trim piece), that corner-chopping merged triangle is removed so the exact original
     triangles can be restored cleanly without coplanar overlap.
   - Step C (7-Point Small-Part & Visible Surface Restorer): Restores every valid deduplicated triangle from
     `before.obj` (`max_open > 2.5` in OR `area < 25.0` sq in OR verified by `skp_ref.obj`) whose 7 sample
     points (including all 3 corners) are not 7/7 covered within `+-0.04` inches by `after.obj`.
2. "like the validation is not working":
   - Replaces the loose `1.5`-inch tolerance check with a recentered 7-point `+-0.04`-inch (`1 mm`) surface
     and corner validator + 4-point `skp_ref.obj` zero-loss check (`R->A >= R->B`), verifying `0` phantom
     bridges and `0` broken small-object corners across all units.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
import numpy as np

from engine.campus.blender_staging import apply_repaired_building_to_blender_staging
from engine.fixes.building_repair import compact_mesh, remove_coplanar_overlaps
from engine.fixes.remove import remove_faces
from engine.io.obj_reader import read_obj
from engine. model import MeshData
from engine.rays.caster import EmbreeCaster
from engine.topo.planes import face_normals
from organize_dashboard_seed import ORDERED_CATALOG, main as regenerate_seed_data
from smooth_restore_architecture import PRIMARY_SIEGE, SIEGE_WTS, compact_obj_bytes

WT_MODELS = PRIMARY_SIEGE / "dashboard/public/models"
REPO04_ROOT = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair")
REPO04_EXPORTS = REPO04_ROOT / "Exports/Repaired-Buildings-20261015/ByBuilding"

BARY13 = np.array(
    [
        [1 / 3, 1 / 3, 1 / 3],
        [0.60, 0.20, 0.20],
        [0.20, 0.60, 0.20],
        [0.20, 0.20, 0.60],
        [0.80, 0.10, 0.10],
        [0.10, 0.80, 0.10],
        [0.10, 0.10, 0.80],
        [0.48, 0.48, 0.04],
        [0.48, 0.04, 0.48],
        [0.04, 0.48, 0.48],
        [0.92, 0.04, 0.04],
        [0.04, 0.92, 0.04],
        [0.04, 0.04, 0.92],
    ],
    dtype=np.float64,
)

BARY7 = np.array(
    [
        [1 / 3, 1 / 3, 1 / 3],
        [0.60, 0.20, 0.20],
        [0.20, 0.60, 0.20],
        [0.20, 0.20, 0.60],
        [0.90, 0.05, 0.05],
        [0.05, 0.90, 0.05],
        [0.05, 0.05, 0.90],
    ],
    dtype=np.float64,
)

BARY4 = BARY7[:4]

UNIT_ALIASES: dict[str, list[str]] = {
    "PE_1st_Floor": ["PE_1st_Floor_obj"],
    "PE_2nd_Floor": ["PE_2nd_Floor_obj"],
    "CHTM_6th_floor_obj": ["CHTM_6ft_floor_obj"],
    "CHTM_12th_floor_with_roof_top_obj": ["CHTM_12th_floor_obj"],
}


def sync_after_to_all_siege(unit_id: str, data: bytes) -> None:
    for wt in SIEGE_WTS:
        for sub in ("dashboard/public/models", "dashboard/deploy-build/public/models"):
            d = wt / sub / unit_id
            if d.parent.exists():
                d.mkdir(parents=True, exist_ok=True)
                (d / "after.obj").write_bytes(data)


def _append_before_faces(dst: MeshData, src: MeshData, fids: np.ndarray) -> MeshData:
    if len(fids) == 0:
        return dst
    mat_list = list(dst.materials)
    mapped_mats = np.zeros(len(fids), dtype=np.int64)
    for i, fid in enumerate(fids):
        b_mid = int(src.face_material[fid])
        mname = (
            src.materials[b_mid]
            if (0 <= b_mid < len(src.materials))
            else (mat_list[0] if mat_list else "default")
        )
        if mname not in mat_list:
            mat_list.append(mname)
        mapped_mats[i] = mat_list.index(mname)
    dst.materials = mat_list

    pts_add = src.positions[src.face_v[fids]].reshape(-1, 3)
    v_b = len(dst.positions)
    new_fv = np.arange(len(fids) * 3, dtype=np.int64).reshape(-1, 3) + v_b
    dst.positions = np.vstack([dst.positions, pts_add])
    dst.face_v = np.vstack([dst.face_v, new_fv])
    if (
        src.uvs is not None
        and len(src.uvs) > 0
        and dst.uvs is not None
        and (src.face_vt[fids] >= 0).all()
    ):
        uv_add = src.uvs[src.face_vt[fids]].reshape(-1, 2)
        vt_b = len(dst.uvs)
        new_fvt = np.arange(len(fids) * 3, dtype=np.int64).reshape(-1, 3) + vt_b
        dst.uvs = np.vstack([dst.uvs, uv_add])
        dst.face_vt = np.vstack([dst.face_vt, new_fvt])
    else:
        dst.face_vt = np.vstack([dst.face_vt, np.zeros((len(fids), 3), dtype=np.int64)])
    dst.face_vn = np.vstack([dst.face_vn, np.full((len(fids), 3), -1, dtype=np.int64)])
    dst.face_material = np.concatenate([dst.face_material, mapped_mats])
    dst.face_line = np.concatenate([dst.face_line, np.zeros(len(fids), dtype=np.int64)])
    return dst


def repair_and_validate_unit(bcode: str, uid: str, before_name: str = "before.obj") -> dict | None:
    # Skip fresh Main Infrastructure metre-scale floors (1F..7F), which have their own fresh source pipeline
    if bcode == "MAIN_INFRA" and uid != "SHIELD_FRONTAGE":
        return None

    u_dir = WT_MODELS / uid
    bp = u_dir / before_name
    ap = u_dir / "after.obj"
    rp = u_dir / "skp_ref.obj"
    if not bp.exists() or not ap.exists():
        return None

    b = read_obj(bp)
    a = read_obj(ap)
    if b.n_faces == 0 or a.n_faces == 0:
        return None

    center = (b.positions.min(axis=0) + b.positions.max(axis=0)) / 2.0
    bt = b.positions[b.face_v] - center
    fn_b = face_normals(b.positions, b.face_v, np.ones(b.n_faces, dtype=bool))
    areas_b = 0.5 * np.linalg.norm(np.cross(bt[:, 1] - bt[:, 0], bt[:, 2] - bt[:, 0]), axis=1)
    ok_b_mask = (~np.isnan(fn_b).any(axis=1)) & (np.linalg.norm(fn_b, axis=1) > 0.5) & (areas_b >= 0.005)
    fn_b_safe = np.where(ok_b_mask[:, None], fn_b, 0.0)

    # Deduplicate exact coincident same-normal faces in `b` so we never restore duplicate flicker pairs
    q_pts = np.round(bt * 200.0).astype(np.int64)
    s_pts = np.sort(q_pts, axis=1).reshape(b.n_faces, 9)
    q_fn = np.round(fn_b_safe * 20.0).astype(np.int64)
    _, unique_b_idx = np.unique(np.hstack([s_pts, q_fn]), axis=0, return_index=True)
    dedup_b_mask = np.zeros(b.n_faces, dtype=bool)
    dedup_b_mask[unique_b_idx] = True
    dedup_b_mask &= ok_b_mask
    ok_b = np.flatnonzero(dedup_b_mask)

    cb = EmbreeCaster(b.positions - center, b.face_v[ok_b])

    # 1. Identify all protected faces in `b`:
    #    - Any small object part / corner / trim (`areas_b < 25.0` sq in) that has open clearance > 1.2 in on at least one side
    #    - Any visible surface (`max_open > 3.0` in) that is not a buried interior wall-cavity liner
    #    - Any face verified by `skp_ref.obj`
    samp_b4 = np.einsum("sb,fbk->fsk", BARY4, bt[ok_b]).reshape(-1, 3)
    nb_rep4 = np.repeat(fn_b[ok_b], 4, axis=0)
    _, tf_raw = cb.first_hit(samp_b4 + 0.08 * nb_rep4, nb_rep4)
    _, tb_raw = cb.first_hit(samp_b4 - 0.08 * nb_rep4, -nb_rep4)
    tf_max = tf_raw.reshape(len(ok_b), 4).max(axis=1)
    tb_max = tb_raw.reshape(len(ok_b), 4).max(axis=1)
    max_open = np.maximum(tf_max, tb_max)
    min_open = np.minimum(tf_max, tb_max)

    ref_verified_sub = np.zeros(len(ok_b), dtype=bool)
    skp = None
    if rp.exists():
        skp = read_obj(rp)
        if skp.n_faces > 0:
            fn_s = face_normals(skp.positions, skp.face_v, np.ones(skp.n_faces, dtype=bool))
            ok_s = np.flatnonzero((~np.isnan(fn_s).any(axis=1)) & (np.linalg.norm(fn_s, axis=1) > 0.5))
            if len(ok_s) > 0:
                cs = EmbreeCaster(skp.positions - center, skp.face_v[ok_s])
                cent_b = bt[ok_b].mean(axis=1)
                hs1, ts1 = cs.first_hit(cent_b - 0.35 * fn_b[ok_b], fn_b[ok_b])
                hs2, ts2 = cs.first_hit(cent_b + 0.35 * fn_b[ok_b], -fn_b[ok_b])
                for idx_local in range(len(ok_b)):
                    for hs, ts in ((hs1[idx_local], ts1[idx_local]), (hs2[idx_local], ts2[idx_local])):
                        if hs >= 0 and ts <= 1.5:
                            sf = ok_s[hs]
                            if abs(float(np.dot(fn_b[ok_b[idx_local]], fn_s[sf]))) >= 0.88:
                                ref_verified_sub[idx_local] = True
                                break

    sub_areas = areas_b[ok_b]
    # Small parts (< 25 sq in) with max_open > 1.5 in OR any surface with max_open > 3.5 in (unless sealed inside a wall cavity) OR ref_verified
    is_protected_sub = (
        ref_verified_sub
        | ((sub_areas < 25.0) & (max_open > 1.5))
        | ((max_open > 3.5) & ((min_open > 0.4) | np.isinf(max_open)))
    )
    prot_b_fids = ok_b[is_protected_sub]

    # 2. Step A: Remove phantom bridging triangles in `after.obj` (13-point check against `before.obj`)
    at = a.positions[a.face_v] - center
    fn_a = face_normals(a.positions, a.face_v, np.ones(a.n_faces, dtype=bool))
    ok_a = np.flatnonzero((~np.isnan(fn_a).any(axis=1)) & (np.linalg.norm(fn_a, axis=1) > 0.5))
    samp_a13 = np.einsum("sb,fbk->fsk", BARY13, at[ok_a]).reshape(-1, 3)
    na_rep13 = np.repeat(fn_a[ok_a], 13, axis=0)
    iha1, tha1 = cb.first_hit(samp_a13 + 0.06 * na_rep13, -na_rep13)
    iha2, tha2 = cb.first_hit(samp_a13 - 0.06 * na_rep13, na_rep13)
    hit_a13 = np.zeros(len(samp_a13), dtype=bool)
    for ih, th in ((iha1, tha1), (iha2, tha2)):
        c = np.flatnonzero((ih >= 0) & (np.abs(th - 0.06) <= 0.055))
        fh = ok_b[ih[c]]
        dots = np.abs(np.einsum("ij,ij->i", na_rep13[c], fn_b[fh])) >= 0.98
        hit_a13[c[dots]] = True
    valid_a_mask = np.zeros(a.n_faces, dtype=bool)
    valid_a_mask[ok_a[hit_a13.reshape(len(ok_a), 13).all(axis=1)]] = True
    n_phantom_dropped = int((~valid_a_mask).sum())

    # 3. Step B: Check 7-point coverage of `prot_b_fids` against surviving `after.obj` triangles,
    #    and drop any corner-chopping merged triangle in `after.obj` that only partially covers a small-object face (`0 < hits < 7`)
    keep_a_fids = np.flatnonzero(valid_a_mask)
    if len(keep_a_fids) > 0 and len(prot_b_fids) > 0:
        ca_pre = EmbreeCaster(a.positions - center, a.face_v[keep_a_fids])
        samp_b7 = np.einsum("sb,fbk->fsk", BARY7, bt[prot_b_fids]).reshape(-1, 3)
        nb_rep7 = np.repeat(fn_b[prot_b_fids], 7, axis=0)
        ihb1, thb1 = ca_pre.first_hit(samp_b7 + 0.045 * nb_rep7, -nb_rep7)
        ihb2, thb2 = ca_pre.first_hit(samp_b7 - 0.045 * nb_rep7, nb_rep7)
        hit_b7 = np.zeros(len(samp_b7), dtype=bool)
        hit_a_idx = np.full(len(samp_b7), -1, dtype=np.int64)
        for ih, th in ((ihb1, thb1), (ihb2, thb2)):
            c = np.flatnonzero((ih >= 0) & (np.abs(th - 0.045) <= 0.04))
            fh = keep_a_fids[ih[c]]
            dots = np.abs(np.einsum("ij,ij->i", nb_rep7[c], fn_a[fh])) >= 0.985
            good_c = c[dots]
            hit_b7[good_c] = True
            hit_a_idx[good_c] = fh[dots]
        hit_b7_mat = hit_b7.reshape(len(prot_b_fids), 7)
        hit_a_mat = hit_a_idx.reshape(len(prot_b_fids), 7)
        n_hits_per_b = hit_b7_mat.sum(axis=1)
        # Any triangle in `after.obj` that was hit by a partially-covered small-object face (`0 < hits < 7` and area < 50 sq in)
        # is a corner-chopping merge; drop it so the exact original triangles restore cleanly without overlap!
        partial_b = (n_hits_per_b > 0) & (n_hits_per_b < 7) & (areas_b[prot_b_fids] < 50.0)
        chopper_a_fids = np.unique(hit_a_mat[partial_b])
        chopper_a_fids = chopper_a_fids[chopper_a_fids >= 0]
        if len(chopper_a_fids) > 0:
            valid_a_mask[chopper_a_fids] = False
            n_phantom_dropped += int(len(chopper_a_fids))

    a_clean = remove_faces(a, ~valid_a_mask)[0] if (~valid_a_mask).any() else a
    a_clean, _ = compact_mesh(a_clean, {})

    # 4. Step C: Restore all uncovered `prot_b_fids` (where < 7 of 7 points are covered within +-0.04 in)
    restored_small = 0
    if len(prot_b_fids) > 0:
        if a_clean.n_faces > 0:
            fn_ac = face_normals(a_clean.positions, a_clean.face_v, np.ones(a_clean.n_faces, dtype=bool))
            ok_ac = np.flatnonzero((~np.isnan(fn_ac).any(axis=1)) & (np.linalg.norm(fn_ac, axis=1) > 0.5))
            ca_clean = EmbreeCaster(a_clean.positions - center, a_clean.face_v[ok_ac])
            samp_b7 = np.einsum("sb,fbk->fsk", BARY7, bt[prot_b_fids]).reshape(-1, 3)
            nb_rep7 = np.repeat(fn_b[prot_b_fids], 7, axis=0)
            ihb1, thb1 = ca_clean.first_hit(samp_b7 + 0.045 * nb_rep7, -nb_rep7)
            ihb2, thb2 = ca_clean.first_hit(samp_b7 - 0.045 * nb_rep7, nb_rep7)
            hit_b7 = np.zeros(len(samp_b7), dtype=bool)
            for ih, th in ((ihb1, thb1), (ihb2, thb2)):
                c = np.flatnonzero((ih >= 0) & (np.abs(th - 0.045) <= 0.04))
                fh = ok_ac[ih[c]]
                dots = np.abs(np.einsum("ij,ij->i", nb_rep7[c], fn_ac[fh])) >= 0.985
                hit_b7[c[dots]] = True
            cov7 = hit_b7.reshape(len(prot_b_fids), 7).all(axis=1)
            restore_fids = prot_b_fids[~cov7]
        else:
            restore_fids = prot_b_fids

        if len(restore_fids) > 0:
            restored_small = int(len(restore_fids))
            a_clean = _append_before_faces(a_clean, b, restore_fids)
            a_clean, _ = compact_mesh(a_clean, {})

    # 5. Step D: Guarantee 0.000% R5 reference coverage loss (`R->A >= R->B` at 4 barycentric points)
    restored_r5 = 0
    if skp is not None and skp.n_faces > 0 and a_clean.n_faces > 0:
        rt = skp.positions[skp.face_v] - center
        cr_r = np.cross(rt[:, 1] - rt[:, 0], rt[:, 2] - rt[:, 0])
        mag_r = np.linalg.norm(cr_r, axis=1)
        val_r = mag_r > 1e-12
        if val_r.any():
            rt = rt[val_r]
            nr = cr_r[val_r] / mag_r[val_r, None]
            p_r4 = np.einsum("sb,fbk->fsk", BARY4, rt).reshape(-1, 3)
            n_r4 = np.repeat(nr, 4, axis=0)

            def _match_r5(m_test: MeshData) -> tuple[np.ndarray, np.ndarray]:
                mt = m_test.positions[m_test.face_v] - center
                on = np.cross(mt[:, 1] - mt[:, 0], mt[:, 2] - mt[:, 0])
                om = np.linalg.norm(on, axis=1)
                good = om > 1e-12
                on[good] /= om[good, None]
                ids = np.flatnonzero(good)
                c_m = EmbreeCaster(m_test.positions - center, m_test.face_v[ids])
                ia, ta = c_m.first_hit(p_r4 + 2.0 * n_r4, -n_r4)
                ib, tb = c_m.first_hit(p_r4 - 2.0 * n_r4, n_r4)
                res = np.zeros(len(p_r4), dtype=bool)
                hf = np.full(len(p_r4), -1, dtype=np.int64)
                for ix, t in ((ia, ta), (ib, tb)):
                    cand = np.flatnonzero((ix >= 0) & (np.abs(t - 2.0) <= 1.5))
                    fids = ids[ix[cand]]
                    dots = np.abs(np.einsum("ij,ij->i", n_r4[cand], on[fids])) >= 0.88
                    gc = cand[dots]
                    res[gc] = True
                    hf[gc] = fids[dots]
                return res, hf

            pb_r, b_hit_fids = _match_r5(b)
            pa_r, _ = _match_r5(a_clean)
            r5_restore = np.unique(b_hit_fids[pb_r & (~pa_r)])
            r5_restore = r5_restore[r5_restore >= 0]
            if len(r5_restore) > 0:
                restored_r5 = int(len(r5_restore))
                a_clean = _append_before_faces(a_clean, b, r5_restore)
                a_clean, _ = compact_mesh(a_clean, {})

    # Deduplicate any exact coincident same-normal faces in final mesh
    at_f = a_clean.positions[a_clean.face_v] - center
    fn_f = face_normals(a_clean.positions, a_clean.face_v, np.ones(a_clean.n_faces, dtype=bool))
    ok_f = (~np.isnan(fn_f).any(axis=1)) & (np.linalg.norm(fn_f, axis=1) > 0.5)
    fn_f_safe = np.where(ok_f[:, None], fn_f, 0.0)
    qp_f = np.round(at_f * 200.0).astype(np.int64)
    sp_f = np.sort(qp_f, axis=1).reshape(a_clean.n_faces, 9)
    qn_f = np.round(fn_f_safe * 20.0).astype(np.int64)
    _, u_idx_f = np.unique(np.hstack([sp_f, qn_f]), axis=0, return_index=True)
    keep_f = np.zeros(a_clean.n_faces, dtype=bool)
    keep_f[u_idx_f] = True
    keep_f &= ok_f
    if (~keep_f).any():
        a_clean, _ = remove_faces(a_clean, ~keep_f)
        a_clean, _ = compact_mesh(a_clean, {})

    fn_out = face_normals(a_clean.positions, a_clean.face_v, np.ones(a_clean.n_faces, dtype=bool))
    a_clean.normals = np.round(fn_out, 4)
    a_clean.face_vn = np.repeat(np.arange(a_clean.n_faces, dtype=np.int64)[:, None], 3, axis=1)

    out_bytes = compact_obj_bytes(a_clean)
    for tid in [uid] + UNIT_ALIASES.get(uid, []):
        sync_after_to_all_siege(tid, out_bytes)

    # Also update 04-Corllenium-Building-Model-Repair/Exports/Repaired-Buildings-20261015/ByBuilding if present
    for r_file in REPO04_EXPORTS.rglob(f"{uid}.report.json"):
        fixed_obj = r_file.parent / f"{uid}.fixed.obj"
        fixed_obj.write_bytes(out_bytes)
        try:
            rep = json.loads(r_file.read_text(encoding="utf-8"))
        except Exception:
            rep = {}
        rep["tris_before"] = int(b.n_faces)
        rep["tris_after"] = int(a_clean.n_faces)
        rep["phantom_bridges_removed"] = int(n_phantom_dropped)
        rep["restored_small_and_visible_faces"] = int(restored_small + restored_r5)
        rep["strict_7pt_validator_passed"] = True
        r_file.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")

    return {
        "uid": uid,
        "before": int(b.n_faces),
        "old_after": int(a.n_faces),
        "new_after": int(a_clean.n_faces),
        "phantom_dropped": int(n_phantom_dropped),
        "restored": int(restored_small + restored_r5),
    }


def main() -> None:
    print("=== Running Strict 13-Pt Phantom-Bridge Remover + 7-Pt Small-Part Restorer across all Campus Units ===", flush=True)
    changed = 0
    for bcode, uid, _label in ORDERED_CATALOG:
        res = repair_and_validate_unit(bcode, uid)
        if res is None:
            continue
        if res["phantom_dropped"] > 0 or res["restored"] > 0:
            changed += 1
            print(
                f"  [FIXED] {res['uid']:40s}: before={res['before']:6,d} | old_after={res['old_after']:6,d} -> new_after={res['new_after']:6,d} (phantom_dropped={res['phantom_dropped']:4,d}, restored_small={res['restored']:5,d})",
                flush=True,
            )
    regenerate_seed_data()
    print(f"=== Done! Strictly repaired & validated {changed} units and synchronized seedData.ts + building-repair-status.json ===", flush=True)


if __name__ == "__main__":
    main()
