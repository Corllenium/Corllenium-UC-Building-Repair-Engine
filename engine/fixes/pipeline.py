"""End-to-end automatic fix: remove what is truly hidden (and, opted in, what is only a sliver of
a slit), then re-triangulate what is left, with a facade guard at every removal step and a final
guard of the WHOLE result against the pristine original -- so a cumulative drift that no single
step would have caught on its own still gets caught here.

Order: `analyse_topology` -> `compute_exposure`/`classify_exposure` -> candidates = hidden faces
(plus slit faces, only when `profile.accept_slit`) -> `guard_feedback` against the original,
STRICT for hidden (the only automatic deletion, so it gets the strictest guard) and, when slit
faces are accepted, a SECOND colour-tolerant pass over the state the hidden pass leaves behind ->
`remove_faces` (which also drops every zero-area face) -> `analyse_topology` on the result ->
`merge_regions` -> a final guard of the merged mesh against the ORIGINAL. If the merge did not
converge, or the final guard fails, the result falls back to the un-merged (removal-only) mesh and
`passed` reflects the fallback's own guard instead.

Vertices are never moved or invented anywhere in this module -- every mesh handed to a guard
render is welded through the SAME `weld_exact(mesh.positions, mesh.coord_decimals)` remap, because
`remove_faces` and `merge_regions` both leave `positions` untouched (see their own modules).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.fixes.merge import merge_regions
from engine.fixes.remove import remove_faces
from engine.guard.compare import GuardReport, compare_views, face_planes, guard_feedback
from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.model import MeshData
from engine.pipeline import analyse_topology, flat_material_indices
from engine.topo.weld import weld_exact
from engine.vis.exposure import EXP_HIDDEN, EXP_SLIT, classify_exposure, compute_exposure

#: Relative slack on the whole-mesh area check, matching `engine.fixes.merge`'s own per-region
#: tolerance -- merging can shift area by float noise, never grow it on purpose.
_AREA_REL_TOL = 1e-6


@dataclass
class FixProfile:
    n_dirs: int = 128
    slit_threshold: float = 0.05
    accept_slit: bool = False
    flat_texture_std: float = 8.0
    guard_size: tuple[int, int] = (900, 600)
    #: `edge_flicker_cap` for the FINAL guard only (merged vs original): merging never deletes a
    #: face, so a silhouette pixel may flicker by less than a pixel of sub-pixel coverage without
    #: that being real damage. The removal guards (inside `guard_feedback`) always use 0.0.
    edge_flicker_cap_final: float = 1e-4


@dataclass
class FixResult:
    mesh: MeshData
    #: One int64 array per face of `mesh`, listing which faces of the ORIGINAL input mesh (to
    #: `fix_object`, not any intermediate) it came from -- a whole region when merged, a single
    #: face otherwise.
    source_faces: list[np.ndarray]
    #: Per ORIGINAL face, one of `engine.vis.exposure`'s `EXP_*` codes.
    exposure_class: np.ndarray
    #: Bool, over ORIGINAL faces: the hidden/slit faces `guard_feedback` confirmed removable.
    removed_hidden: np.ndarray
    removed_slit: np.ndarray
    n_hidden_candidates: int
    n_restored_by_guard: int
    n_removed_hidden: int
    n_removed_slit: int
    n_zero_area_dropped: int
    #: `{"hidden": history, "slit": history | None}` -- `guard_feedback`'s own per-round history
    #: from each pass; `"slit"` is `None` when no slit pass ran.
    feedback_history: dict
    guard_after_removal: GuardReport
    guard_final: GuardReport
    merge_report: dict
    invariants: dict
    passed: bool


def _total_area(positions: np.ndarray, face_v: np.ndarray) -> float:
    p = positions[face_v]
    return float(0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1).sum())


def _render(positions_c: np.ndarray, faces: np.ndarray, size: tuple[int, int]):
    ids = np.arange(len(faces), dtype=np.int64)
    return [(v, ortho_first_hit(positions_c, faces, ids, v, positions_c, size)) for v in VIEWS_26]


def fix_object(mesh: MeshData, flatness: dict[str, float], profile: FixProfile = FixProfile()) -> FixResult:
    flat_materials = flat_material_indices(mesh, flatness, profile.flat_texture_std)
    topo = analyse_topology(mesh, flat_materials)
    depth_tol = 1.5 * float(topo.quanta.max())
    # Recentre once, to the ORIGINAL mesh's bbox centre; the same recentred frame renders every
    # side, before and after, at every stage -- vertices never move, so one frame is always correct.
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
    positions_c = topo.positions_w - centre
    _, remap = weld_exact(mesh.positions, mesh.coord_decimals)  # same weld space as topo, reusable
    # for any mesh whose `positions` is the SAME array (remove_faces/merge_regions never touch it).

    exposure = compute_exposure(positions_c, topo.face_w, topo.ok, n_dirs=profile.n_dirs)
    exposure_class = classify_exposure(exposure, topo.ok, profile.slit_threshold)

    ok_ids = np.nonzero(topo.ok)[0]
    render_faces = topo.face_w[topo.ok]
    render_material = mesh.face_material[topo.ok]

    # ---- pass 1: hidden faces, strict guard (the only automatic deletion) -------------------
    hidden_ok = exposure_class[topo.ok] == EXP_HIDDEN
    n_hidden_candidates = int(hidden_ok.sum())
    removed_hidden_ok, history_hidden = guard_feedback(
        hidden_ok, positions_c, render_faces, render_material, flat_materials, depth_tol,
        strict=True, size=profile.guard_size)
    n_removed_hidden = int(removed_hidden_ok.sum())
    n_restored_by_guard = n_hidden_candidates - n_removed_hidden

    # ---- pass 2: slit faces, colour-tolerant guard, over the state pass 1 leaves behind -----
    slit_ok = exposure_class[topo.ok] == EXP_SLIT
    removed_slit_ok = np.zeros(len(render_faces), dtype=bool)
    history_slit = None
    if profile.accept_slit and slit_ok.any():
        kept_after_hidden = ~removed_hidden_ok
        remaining_ids = np.nonzero(kept_after_hidden)[0]
        mask2, history_slit = guard_feedback(
            slit_ok[kept_after_hidden], positions_c, render_faces[kept_after_hidden],
            render_material[kept_after_hidden], flat_materials, depth_tol, strict=False,
            size=profile.guard_size)
        removed_slit_ok[remaining_ids[mask2]] = True
    n_removed_slit = int(removed_slit_ok.sum())

    removed_hidden_full = np.zeros(mesh.n_faces, dtype=bool)
    removed_hidden_full[ok_ids[removed_hidden_ok]] = True
    removed_slit_full = np.zeros(mesh.n_faces, dtype=bool)
    removed_slit_full[ok_ids[removed_slit_ok]] = True
    zero_area_full = ~topo.ok
    n_zero_area_dropped = int(zero_area_full.sum())

    drop = removed_hidden_full | removed_slit_full | zero_area_full
    mesh_removed, source_from_removal = remove_faces(mesh, drop)

    topo2 = analyse_topology(mesh_removed, flat_materials)
    merge_result = merge_regions(mesh_removed, topo2, flat_materials)

    # A slit-tolerant removal is a person-accepted, colour-tolerant change: both guard checks
    # below use the same strictness the removal itself used.
    strict_final = not (profile.accept_slit and n_removed_slit > 0)

    face_w_original = topo.face_w
    material_original = mesh.face_material
    planes_original = face_planes(positions_c, face_w_original)
    before_original = _render(positions_c, face_w_original, profile.guard_size)

    def _guard_against_original(final_mesh: MeshData, edge_flicker_cap: float) -> GuardReport:
        face_w_final = remap[final_mesh.face_v]
        after = _render(positions_c, face_w_final, profile.guard_size)
        return compare_views(
            before_original, after, material_original, final_mesh.face_material, flat_materials,
            depth_tol, strict=strict_final, plane_before=planes_original,
            plane_after=face_planes(positions_c, face_w_final), edge_flicker_cap=edge_flicker_cap,
            geometry_before=(positions_c, face_w_original), geometry_after=(positions_c, face_w_final))

    guard_after_removal = _guard_against_original(mesh_removed, edge_flicker_cap=0.0)

    merge_report = dict(merge_result.report)
    rolled_back_reason = None

    if not merge_report.get("converged", True):
        rolled_back_reason = "not_converged"
    else:
        guard_final = _guard_against_original(merge_result.mesh, profile.edge_flicker_cap_final)
        if not guard_final.passed:
            rolled_back_reason = "guard_failed"

    if rolled_back_reason is not None:
        merge_report["rolled_back"] = True
        merge_report["rolled_back_reason"] = rolled_back_reason
        final_mesh = mesh_removed
        final_source_faces = [np.array([int(f)], dtype=np.int64) for f in source_from_removal]
        guard_final = _guard_against_original(final_mesh, profile.edge_flicker_cap_final)
    else:
        final_mesh = merge_result.mesh
        final_source_faces = [source_from_removal[s].astype(np.int64) for s in merge_result.source_faces]

    invariants = {
        "material_count_same": len(final_mesh.materials) == len(mesh.materials),
        "bbox_same": bool(np.array_equal(final_mesh.positions.min(axis=0), mesh.positions.min(axis=0))
                          and np.array_equal(final_mesh.positions.max(axis=0), mesh.positions.max(axis=0))),
        "area_not_grown": bool(_total_area(final_mesh.positions, final_mesh.face_v)
                               <= _total_area(mesh.positions, mesh.face_v) * (1.0 + _AREA_REL_TOL)),
        "guard_passed": guard_final.passed,
    }
    passed = all(invariants.values())

    return FixResult(
        mesh=final_mesh, source_faces=final_source_faces, exposure_class=exposure_class,
        removed_hidden=removed_hidden_full, removed_slit=removed_slit_full,
        n_hidden_candidates=n_hidden_candidates, n_restored_by_guard=n_restored_by_guard,
        n_removed_hidden=n_removed_hidden, n_removed_slit=n_removed_slit,
        n_zero_area_dropped=n_zero_area_dropped,
        feedback_history={"hidden": history_hidden, "slit": history_slit},
        guard_after_removal=guard_after_removal, guard_final=guard_final,
        merge_report=merge_report, invariants=invariants, passed=passed)
