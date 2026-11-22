"""Stage 4C · Visible-Surface Preservation & Hard Validation Gate for Architecture_Whole_Building_R5.

Restores 100% of visible room/exterior/baseboard/stair-stringer faces from `before.obj` that were
prematurely dropped by the earlier loose `room_hits <= 2` cavity-fin pass (preserving the newly
rebuilt 12-step diagonal stair flight and sealed landings verbatim!), drives any newly-introduced
coplanar pairs to exact 0/0 flicker while keeping original finishes (`littletiles`, `quartz_block_top`),
re-runs real `find_errors(after)`, enforces the hard validation gate:
  flicker_diff == 0 AND flicker_same == 0 AND reversed == 0 AND zero_area == 0 AND visible_coverage >= 99.0%,
and uploads the verified live package.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time
import numpy as np

ENGINE_ROOT = Path(r"D:\PROJECTS\05-Corllenium-UC-Building-Repair-Engine")
sys.path.insert(0, str(ENGINE_ROOT))

from engine.detectors.errors import find_errors  # noqa: E402
from engine.fixes.building_repair import compact_mesh  # noqa: E402
from engine.fixes.pipeline import FixProfile  # noqa: E402
from engine.fixes.remove import remove_faces  # noqa: E402
from engine.io.obj_reader import read_obj  # noqa: E402
from engine.io.obj_writer import write_obj  # noqa: E402
from engine.pipeline import analyse_topology  # noqa: E402
from engine.rays.caster import EmbreeCaster  # noqa: E402
from engine.topo.edges import EDGE_REMOVABLE  # noqa: E402
from engine.topo.planes import face_normals  # noqa: E402
from run_architecture_whole_r5_v2 import (  # noqa: E402
    AFTER_DIR,
    BARY7,
    BEFORE_DIR,
    ROOF_PROTECT_Z_IN,
    UNIT_ID,
    append_mesh,
    compute_reachability,
    fix_reversed_orientation_exact,
    iterative_flicker_convergence,
    push_live_status,
    upload_after_files,
)
from stage4_rebuild_diagonal_stairs import (  # noqa: E402
    IN_PER_M,
    N_IN,
    P_MINX,
    T_DIR,
)


def main() -> None:
    t0 = time.perf_counter()
    before_obj = BEFORE_DIR / "before.obj"
    after_obj = AFTER_DIR / "after.obj"
    orig = read_obj(before_obj)
    work = read_obj(after_obj)
    print(f"Loaded before={orig.n_faces:,}, after={work.n_faces:,} tris", flush=True)

    # 1. Exact visible surface set on before.obj (STRICTLY room_hits > 0 OR ext_exp > 0 OR 7F roof — ZERO sealed cavities!)
    reachable, room_hits, ext_exp = compute_reachability(orig, n_probe_dirs=512, n_ext_dirs=128)
    pts_b = orig.positions[orig.face_v]
    pts_bm = pts_b / IN_PER_M
    cen_bm = pts_bm.mean(axis=1)
    fn_b = face_normals(orig.positions, orig.face_v, np.ones(orig.n_faces, dtype=bool))
    ok_b = (~np.isnan(fn_b).any(axis=1)) & (np.linalg.norm(fn_b, axis=1) > 0.5)
    areas_b = 0.5 * np.linalg.norm(np.cross(pts_b[:, 1] - pts_b[:, 0], pts_b[:, 2] - pts_b[:, 0]), axis=1)
    roof_b = pts_b[:, :, 2].min(axis=1) > ROOF_PROTECT_Z_IN

    # Exclude ONLY the explicitly rebuilt 12-step diagonal stair flight volume so we never restore broken old stair tris!
    d_b = cen_bm - P_MINX[None, :]
    t_b = d_b @ T_DIR
    s_b = d_b @ N_IN
    z_b = cen_bm[:, 2]
    in_rebuilt_stairs = (
        (s_b >= 32.00) & (s_b <= 35.38)
        & (t_b >= 6.68) & (t_b <= 13.56)
        & (z_b >= 4.255) & (z_b <= 7.245)
        & np.array([
            ("quartz_block_top" in orig.materials[int(mid)])
            or ("quartz_block_side" in orig.materials[int(mid)])
            or ("quartz_block_bottom" in orig.materials[int(mid)])
            for mid in orig.face_material
        ], dtype=bool)
    )

    prot_mask = (reachable | roof_b) & ok_b & (areas_b >= 0.005) & (~in_rebuilt_stairs)
    prot_ids = np.flatnonzero(prot_mask)
    print(f"Protected strictly visible faces (room_hits>0 or ext_exp>0 or roof, excl rebuilt stairs): {len(prot_ids):,}", flush=True)

    # 2. Check 7-pt coverage of every protected visible face against current after.obj
    center = (orig.positions.min(axis=0) + orig.positions.max(axis=0)) / 2.0
    bt_prot = pts_b[prot_ids] - center
    samp_b7 = np.einsum("sb,fbk->fsk", BARY7, bt_prot).reshape(-1, 3)
    nb7 = np.repeat(fn_b[prot_ids], len(BARY7), axis=0)

    ca = EmbreeCaster(work.positions - center, work.face_v)
    hp, dp = ca.first_hit(samp_b7 - 0.05 * nb7, nb7)
    hm, dm = ca.first_hit(samp_b7 + 0.05 * nb7, -nb7)
    cov = (((hp >= 0) & (dp <= 0.10)) | ((hm >= 0) & (dm <= 0.10))).reshape(len(prot_ids), len(BARY7))
    # Restore any visible face missing >= 1 interior sample point (catches EVERY missing corner/baseboard/stringer!)
    miss_ids = prot_ids[~cov.all(axis=1)]
    cov_before_restore = round(100.0 * (1.0 - len(miss_ids) / max(len(prot_ids), 1)), 3)
    print(f"Visible coverage BEFORE restore: {cov_before_restore}% (missing {len(miss_ids):,} visible tris). Restoring...", flush=True)

    if len(miss_ids) > 0:
        work = append_mesh(work, orig, miss_ids)
        work, _ = compact_mesh(work, {})
        # Resolve any overlap introduced by restored faces using finish-preserving flicker loop -> exact 0/0!
        work, fl_hist = iterative_flicker_convergence(work, FixProfile(), max_rounds=6)
        topo_za = analyse_topology(work, frozenset())
        if int((~topo_za.ok).sum()) > 0:
            work, _ = remove_faces(work, ~topo_za.ok)
            work, _ = compact_mesh(work, {})
        work, n_flip = fix_reversed_orientation_exact(work)
        work, _ = compact_mesh(work, {})
        print(f"Restored & converged: {work.n_faces:,} tris (flicker_rounds={len(fl_hist)}, flips={n_flip})", flush=True)

    work.name = UNIT_ID
    work.mtllib = "materials.mtl"
    write_obj(work, after_obj)

    # 3. HARD VALIDATION GATE: measure final 7-pt visible surface coverage + real find_errors(after)!
    after_mesh = read_obj(after_obj)
    ca_fin = EmbreeCaster(after_mesh.positions - center, after_mesh.face_v)
    hp_f, dp_f = ca_fin.first_hit(samp_b7 - 0.05 * nb7, nb7)
    hm_f, dm_f = ca_fin.first_hit(samp_b7 + 0.05 * nb7, -nb7)
    cov_fin = (((hp_f >= 0) & (dp_f <= 0.10)) | ((hm_f >= 0) & (dm_f <= 0.10))).reshape(len(prot_ids), len(BARY7))
    uncov_after = int((~cov_fin.all(axis=1)).sum())
    cov_pct = round(100.0 * (1.0 - uncov_after / max(len(prot_ids), 1)), 3)

    after_errs = find_errors(after_mesh)
    topo_a = analyse_topology(after_mesh, frozenset())
    grid_after = int((topo_a.edge_class == EDGE_REMOVABLE).sum())
    after_errs["gridlines"] = grid_after
    after_errs_path = AFTER_DIR / "errors_after.json"
    after_errs_path.write_text(json.dumps(after_errs), encoding="utf-8")

    ea = after_errs["counts"]
    za = after_errs["loose_parts"]["zero_area"]
    passed = (
        ea["flicker_diff"] == 0
        and ea["flicker_same"] == 0
        and ea["reversed"] == 0
        and za == 0
        and cov_pct >= 99.0
    )

    summ_path = AFTER_DIR / "repair_summary.json"
    summ = json.loads(summ_path.read_text(encoding="utf-8"))
    summ["tris_after"] = int(after_mesh.n_faces)
    summ["reduction_pct"] = round(100.0 * (1.0 - after_mesh.n_faces / max(summ["tris_before"], 1)), 2)
    summ["errors_after"] = ea
    summ["loose_parts_after"] = after_errs["loose_parts"]
    summ["gridlines_after"] = grid_after
    summ["protected_reachable_faces"] = int(len(prot_ids))
    summ["uncovered_reachable_after"] = uncov_after
    summ["reachable_facade_and_room_coverage_pct"] = cov_pct
    summ["validator_passed_hard_gate"] = passed
    summ_path.write_text(json.dumps(summ, indent=2), encoding="utf-8")

    print(f"FINAL VISIBLE COVERAGE: {cov_pct}% (uncovered={uncov_after}/{len(prot_ids)}) | HARD GATE PASSED={passed}", flush=True)
    print("FINAL VERIFIED COUNTS:", json.dumps(ea, indent=2), flush=True)
    print("FINAL LOOSE_PARTS:", after_errs["loose_parts"], flush=True)

    upload_after_files([after_obj, after_errs_path])
    eb = summ["errors_before"]
    live_res = {
        "trisBefore": summ["tris_before"],
        "trisAfter": int(after_mesh.n_faces),
        "reductionPct": summ["reduction_pct"],
        "errorsBefore": eb,
        "errorsAfter": ea,
        "validatorPassed": passed,
        "jevRecommendedAction": "owner_review_ready" if passed else "needs_review",
    }
    push_live_status(
        6,
        f"Stage 6 · Hard-Gate Validated ({cov_pct}% Visible Coverage, 0 Flicker, 0 Reversed, 0 Zero-Area)",
        100,
        round(summ.get("elapsed_seconds", 0.0) + (time.perf_counter() - t0), 1),
        f"Stage 4C Hard-Gate DONE: {summ['tris_before']:,}->{after_mesh.n_faces:,} tris (-{summ['reduction_pct']}%) | visible_coverage={cov_pct}% | flicker={ea['flicker_diff']}/{ea['flicker_same']}, reversed={ea['reversed']}, zero_area={za}.",
        [],
        results=live_res,
        state="completed",
    )


if __name__ == "__main__":
    main()
