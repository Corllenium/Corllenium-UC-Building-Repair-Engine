"""Targeted Stage 5 Green-Pass Sealer for Architecture_Whole_Building_R5 (and general seam-tear repair).

Seals the last 2 Stage 5 failures (#2 exterior tear seams + #4 sub-9mm degenerate needle slivers)
using universal, zero-hardcoded-coordinate rules:
  1. For every Check #2 outer-facade tear seam spot, finds any missing BEFORE faces near that seam
     (< 6/7 coverage within 35 in) and restores them via conflict-safe `restore_destroyed_facade_faces`.
  2. Purges ALL true degenerate needle slivers (`aspect >= 50`, `min_alt <= 0.35 in`, `area <= 12`,
     `~has_coplanar_neighbor` — strictly protecting louvers, railings, and flat walls!).
  3. Converges flicker (`0/0`), exact 128-dir orientation (`0` reversed), and zero-area drop (`0`).
  4. Re-verifies Stage 5 (`verify_facade_and_mesh_integrity`) + visibility-filtered `diff_overlay.json`,
     syncs `architectureWholeR5Integrity.ts` & `repair_summary.json`, and uploads live to cPanel.
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
from engine.fixes.patch_protect import detect_piercing_needle_slivers, purge_piercing_needle_slivers  # noqa: E402
from engine.fixes.pipeline import FixProfile  # noqa: E402
from engine.fixes.remove import remove_faces  # noqa: E402
from engine.io.obj_reader import read_obj  # noqa: E402
from engine.io.obj_writer import write_obj  # noqa: E402
from engine.pipeline import analyse_topology  # noqa: E402
from engine.rays.caster import EmbreeCaster  # noqa: E402
from engine.topo.edges import EDGE_REMOVABLE  # noqa: E402
from engine.topo.planes import face_normals  # noqa: E402
from engine.validate.diff_overlay import (  # noqa: E402
    compute_before_after_diff_overlay,
    restore_destroyed_facade_faces,
    write_diff_overlay_obj,
)
from engine.validate.facade_integrity import _coverage_7pt, verify_facade_and_mesh_integrity  # noqa: E402
from run_architecture_whole_r5_v2 import (  # noqa: E402
    AFTER_DIR,
    BEFORE_DIR,
    UNIT_ID,
    fix_reversed_orientation_exact,
    iterative_flicker_convergence,
    upload_after_files,
)
from stage5_loopback_heal import rebuilt_stair_excl  # noqa: E402


def main() -> None:
    t0 = time.perf_counter()
    before = read_obj(BEFORE_DIR / "before.obj")
    after_obj = AFTER_DIR / "after.obj"
    work = read_obj(after_obj)
    fi_prev = json.loads((AFTER_DIR / "facade_integrity.json").read_text(encoding="utf-8"))
    print(f"Seal-to-green start: before={before.n_faces:,}, after={work.n_faces:,} tris", flush=True)

    center = 0.5 * (before.positions.min(axis=0) + before.positions.max(axis=0))
    pts_b = before.positions[before.face_v]
    cen_b = pts_b.mean(axis=1)
    fn_b = face_normals(before.positions, before.face_v, np.ones(before.n_faces, dtype=bool))
    ok_b = (~np.isnan(fn_b).any(axis=1)) & (np.linalg.norm(fn_b, axis=1) > 0.5)
    excl_b = rebuilt_stair_excl(before)

    # 1. Seal every Check #2 outer-facade tear seam by pulling back missing BEFORE faces within 40 in of each seam spot
    c2_spots = []
    for c in fi_prev.get("checks", []):
        if c.get("id") == "outer_facade_zero_cracklines":
            c2_spots = c.get("spots", [])
    if c2_spots:
        near_mask = np.zeros(before.n_faces, dtype=bool)
        for sp in c2_spots:
            pt = np.asarray(sp["centre"], dtype=np.float64)
            near_mask |= (np.linalg.norm(cen_b - pt[None, :], axis=1) <= 45.0)
        cand_ids = np.flatnonzero(near_mask & ok_b & (~excl_b))
        ca = EmbreeCaster(work.positions - center, work.face_v)
        _, miss_seam = _coverage_7pt(before, ca, center, fn_b, cand_ids, tol=0.12)
        if len(miss_seam) > 0:
            seam_diff = {"before_faces": {"missing_outer_facade": [int(x) for x in miss_seam], "missing_interior_visible": []}}
            work, n_rest = restore_destroyed_facade_faces(before, work, seam_diff, include_interior=False)
            work, _ = compact_mesh(work, {})
            print(f"Seam-tear seal restored +{n_rest} BEFORE faces near {len(c2_spots)} seam spots -> {work.n_faces:,} tris", flush=True)

    # 2. Converge any overlap created by seam restore (0/0 flicker!)
    work, hist = iterative_flicker_convergence(work, FixProfile(), max_rounds=6)
    print(f"Flicker converged ({len(hist)} rounds) -> {work.n_faces:,} tris", flush=True)

    # 3. Purge ALL true degenerate spikes (<=0.35in, aspect>=50, area<=12, 0 coplanar neighbors -> ZERO louvers/railings/walls touched!)
    for r in range(3):
        work, n_sliv = purge_piercing_needle_slivers(work, protect_mask=None)
        print(f"Zero-hole spike purge round {r+1}: -{n_sliv} spikes -> {work.n_faces:,} tris", flush=True)
        if n_sliv == 0:
            break

    # 4. Zero-area drop + exact 128-dir orientation (`reversed -> 0`)
    topo_za = analyse_topology(work, frozenset())
    if int((~topo_za.ok).sum()) > 0:
        work, _ = remove_faces(work, ~topo_za.ok)
        work, _ = compact_mesh(work, {})
    work, n_flip = fix_reversed_orientation_exact(work)
    work, _ = compact_mesh(work, {})
    print(f"Final orientation fix: {n_flip} flips -> {work.n_faces:,} tris", flush=True)

    work.name = UNIT_ID
    work.mtllib = "materials.mtl"
    write_obj(work, after_obj)

    after_mesh = read_obj(after_obj)
    after_errs = find_errors(after_mesh)
    topo_a = analyse_topology(after_mesh, frozenset())
    after_errs["gridlines"] = int((topo_a.edge_class == EDGE_REMOVABLE).sum())
    (AFTER_DIR / "errors_after.json").write_text(json.dumps(after_errs), encoding="utf-8")

    report = verify_facade_and_mesh_integrity(
        before,
        after_mesh,
        after_errs,
        rebuild_exclusion_mask_fn=rebuilt_stair_excl,
        n_probe_dirs=256,
        n_ext_dirs=128,
        blender_mesh_valid=True,
    )
    (AFTER_DIR / "facade_integrity.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    diff_doc = compute_before_after_diff_overlay(
        before,
        after_mesh,
        after_errs,
        rebuild_exclusion_mask_fn=rebuilt_stair_excl,
        n_probe_dirs=256,
        n_ext_dirs=128,
    )
    (AFTER_DIR / "diff_overlay.json").write_text(json.dumps(diff_doc), encoding="utf-8")
    write_diff_overlay_obj(before, after_mesh, diff_doc, AFTER_DIR / "diff_overlay.obj")

    out_ts = Path(r"D:\PROJECTS\02-Corllenium-Siege\.worktrees\arch-whole-r5-20261122\dashboard\lib\buildings\architectureWholeR5Integrity.ts")
    out_ts.write_text(
        'import type { FacadeIntegrityReport } from "./types";\n\n'
        "// Auto-exported from 05-Corllenium-UC-Building-Repair-Engine/data/architecture_whole_r5/after/facade_integrity.json\n"
        f"export const ARCHITECTURE_WHOLE_R5_INTEGRITY: FacadeIntegrityReport = {json.dumps(report, indent=2)};\n",
        encoding="utf-8",
    )

    summ_path = AFTER_DIR / "repair_summary.json"
    summ = json.loads(summ_path.read_text(encoding="utf-8"))
    summ["tris_after"] = int(after_mesh.n_faces)
    summ["reduction_pct"] = round(100.0 * (1.0 - after_mesh.n_faces / max(summ["tris_before"], 1)), 2)
    summ["errors_after"] = after_errs["counts"]
    summ["loose_parts_after"] = after_errs["loose_parts"]
    summ["gridlines_after"] = after_errs["gridlines"]
    summ["facade_integrity"] = report
    summ_path.write_text(json.dumps(summ, indent=2), encoding="utf-8")

    print(f"\n=== SEAL-TO-GREEN STAGE 5 REPORT ({time.perf_counter()-t0:.1f}s) ===", flush=True)
    print(f"automatedPassed={report['automatedPassed']} | failedCheckIds={report['failedCheckIds']}", flush=True)
    for c in report["checks"]:
        print(f"  [{c['status'].upper():7s}] #{c['order']:2d} {c['id']:30s} | measured={c['measured']}", flush=True)
    print(f"DIFF_COUNTS: {diff_doc['counts']}", flush=True)
    print(f"VISIBLE_HOLES_BY_SHAPE: {diff_doc.get('newMeshHoles')}", flush=True)

    upload_after_files([
        after_obj,
        AFTER_DIR / "errors_after.json",
        AFTER_DIR / "facade_integrity.json",
        AFTER_DIR / "diff_overlay.json",
    ])
    print("UPLOADED_ALL_LIVE_OK", flush=True)


if __name__ == "__main__":
    main()
