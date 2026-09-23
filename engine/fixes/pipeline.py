"""End-to-end automatic fix: remove what is truly hidden (and, opted in, what is only a sliver of
a slit), correct any face wound backwards, then re-triangulate what is left, with a facade guard
at every removal step and a final guard of the WHOLE result against the pristine original -- so a
cumulative drift that no single step would have caught on its own still gets caught here.

Order: `analyse_topology` -> `compute_side_exposure`/`classify_exposure` -> candidates = hidden
faces AND degenerate ("zero-area") faces (plus slit faces, only when `profile.accept_slit`) ->
`guard_feedback` against the original, STRICT for pass 1 (the only automatic deletion, so it gets
the strictest guard) and, when slit faces are accepted, a SECOND colour-tolerant pass over the
state pass 1 leaves behind -> `remove_faces` -> `classify_orientation` +
`flip_faces` on the survivors, so a face whose only real exposure was on its BACK re-joins its
neighbours' region instead of being copied through alone -> `analyse_topology` on the flipped
result -> `merge_regions` -> a final guard of the merged mesh against the ORIGINAL. If the merge
did not converge, or the final guard fails, the result falls back to the flipped-but-unmerged
(removal-only) mesh and `passed` reflects the fallback's own guard instead -- while
`FixResult.guard_merge_attempt` keeps the merged mesh's own report, so the failure that caused
the rollback stays visible. Flipping never changes a double-sided render (see
`engine.fixes.orient`), so it never changes which guard passes.

A degenerate face is only RELATIVELY degenerate (`engine.topo.adjacency.degenerate_mask` allows
`area <= 1e-7 * longest**2`), so a 1,000 in sliver up to 0.0002 in wide is "zero-area" and yet a
real, hittable surface. Those are therefore ordinary pass-1 candidates, not an unconditional
delete: every BEFORE render casts against ALL faces, and a degenerate face the guard restores
stays in the mesh (`n_degenerate_restored` / `restored_degenerate`), so `n_zero_area_dropped` is
what was actually removed, not what was merely degenerate.

Vertices are never moved or invented anywhere in this module -- every mesh handed to a guard
render is welded through the SAME `weld_exact(mesh.positions, mesh.coord_decimals)` remap, because
`remove_faces`, `flip_faces` and `merge_regions` all leave `positions` untouched (see their own
modules).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.fixes.merge import merge_regions
from engine.fixes.orient import ORIENT_FLIP, ORIENT_THIN_SHEET, classify_orientation, flip_faces, one_sided_holes
from engine.fixes.remove import remove_faces
from engine.guard.compare import GuardReport, compare_views, face_planes, guard_feedback
from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.model import MeshData
from engine.pipeline import analyse_topology, flat_material_indices
from engine.rays.caster import ReusableCaster
from engine.topo.weld import weld_exact
from engine.vis.exposure import EXP_HIDDEN, EXP_SLIT, classify_exposure, compute_side_exposure

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
    #: How many `not ok` ("zero-area") faces the strict guard confirmed removable -- NOT how many
    #: there were: `degenerate_mask` is relative, so a long sliver counts as zero-area while
    #: still being visible, and those are kept (see `n_degenerate_restored`).
    n_zero_area_dropped: int
    n_degenerate_restored: int
    #: Bool, over ORIGINAL faces: degenerate faces the guard put back, which stay in the mesh.
    restored_degenerate: np.ndarray
    #: Bool, over ORIGINAL faces: survived removal and had its winding reversed (its only real
    #: exposure was on the BACK -- see `engine.fixes.orient.classify_orientation`).
    flipped: np.ndarray
    #: Bool, over ORIGINAL faces: both sides exposed, roughly equally -- reported, never touched.
    thin_sheets: np.ndarray
    #: `engine.fixes.orient.one_sided_holes` over the ORIGINAL mesh's non-degenerate faces, and
    #: again over the mesh actually shipped (`mesh`) -- pixels a one-sided renderer would still
    #: drop as a hole. `_after` is expected to be lower than `_before`.
    one_sided_holes_before: int
    one_sided_holes_after: int
    #: `{"hidden": history, "slit": history | None}` -- `guard_feedback`'s own per-round history
    #: from each pass; `"slit"` is `None` when no slit pass ran.
    feedback_history: dict
    guard_after_removal: GuardReport
    #: The MERGED mesh's guard against the reference -- the report that decided whether the merge
    #: was kept. `None` only when the merge did not converge, so there was no merged mesh to
    #: guard. It is kept even when the merge is ROLLED BACK, where `guard_final` describes the
    #: fallback that shipped instead: without it, the failure that caused the rollback leaves no
    #: trace at all. When nothing was rolled back it is the same report as `guard_final`.
    guard_merge_attempt: GuardReport | None
    guard_final: GuardReport
    merge_report: dict
    #: `engine.fixes.merge.MergeResult.rings`, valid against `mesh` (this result's own final
    #: mesh) exactly as documented there -- empty when the merge candidate was rolled back, since
    #: there is then no merged mesh for it to index into.
    rings: dict
    invariants: dict
    passed: bool


def _total_area(positions: np.ndarray, face_v: np.ndarray) -> float:
    p = positions[face_v]
    return float(0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1).sum())


def _render(positions_c: np.ndarray, faces: np.ndarray, size: tuple[int, int]):
    ids = np.arange(len(faces), dtype=np.int64)
    # ReusableCaster: one embree BVH build for this geometry, reused across all 26 views.
    caster_factory = ReusableCaster()
    return [(v, ortho_first_hit(positions_c, faces, ids, v, positions_c, size, caster_factory))
            for v in VIEWS_26]


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

    front, back = compute_side_exposure(positions_c, topo.face_w, topo.ok, n_dirs=profile.n_dirs)
    exposure = front + back
    exposure_class = classify_exposure(exposure, topo.ok, profile.slit_threshold)
    orientation = classify_orientation(front, back, topo.ok)
    flip_candidates_full = orientation == ORIENT_FLIP
    thin_sheets_full = orientation == ORIENT_THIN_SHEET

    one_sided_holes_before = one_sided_holes(
        positions_c, topo.face_w, np.arange(mesh.n_faces, dtype=np.int64), VIEWS_26, profile.guard_size)

    # Every render below -- the hidden pass's own BEFORE, the slit pass's, and both guards
    # against the original -- casts against the SAME face set: ALL of them. A "degenerate" face
    # is only relatively degenerate (`engine.topo.adjacency.degenerate_mask` allows an area of
    # `1e-7 * longest**2`), so a long sliver is real, hittable surface; rendering BEFORE without
    # it while deleting it in AFTER is what let 12 pixels of file B change material unchecked.
    # A truly zero-area triangle is never a first hit, so including it costs nothing.
    render_faces = topo.face_w
    render_material = mesh.face_material

    # ---- pass 1: hidden AND degenerate faces, one strict guard over the whole face set ------
    hidden_full = exposure_class == EXP_HIDDEN       # classify_exposure gives every `not ok` face
    degenerate_full = ~topo.ok                        # EXP_DEGENERATE, so these two are disjoint
    n_hidden_candidates = int(hidden_full.sum())
    removed_pass1, history_hidden = guard_feedback(
        hidden_full | degenerate_full, positions_c, render_faces, render_material, flat_materials,
        depth_tol, strict=True, size=profile.guard_size)
    removed_hidden_full = removed_pass1 & ~degenerate_full
    removed_degenerate_full = removed_pass1 & degenerate_full
    restored_degenerate_full = degenerate_full & ~removed_pass1
    n_removed_hidden = int(removed_hidden_full.sum())
    n_restored_by_guard = n_hidden_candidates - n_removed_hidden
    n_zero_area_dropped = int(removed_degenerate_full.sum())
    n_degenerate_restored = int(restored_degenerate_full.sum())

    # ---- pass 2: slit faces, colour-tolerant guard, over the state pass 1 leaves behind -----
    slit_full = exposure_class == EXP_SLIT
    removed_slit_full = np.zeros(mesh.n_faces, dtype=bool)
    history_slit = None
    if profile.accept_slit and slit_full.any():
        kept_after_pass1 = ~removed_pass1
        remaining_ids = np.nonzero(kept_after_pass1)[0]
        mask2, history_slit = guard_feedback(
            slit_full[kept_after_pass1], positions_c, render_faces[kept_after_pass1],
            render_material[kept_after_pass1], flat_materials, depth_tol, strict=False,
            size=profile.guard_size)
        removed_slit_full[remaining_ids[mask2]] = True
    n_removed_slit = int(removed_slit_full.sum())

    drop = removed_hidden_full | removed_slit_full | removed_degenerate_full
    mesh_removed, source_from_removal = remove_faces(mesh, drop)

    # ---- orientation: correct any survivor whose only real exposure was on its BACK ----------
    flip_removed = flip_candidates_full[source_from_removal]
    mesh_flipped = flip_faces(mesh_removed, flip_removed)
    flipped_full = np.zeros(mesh.n_faces, dtype=bool)
    flipped_full[source_from_removal[flip_removed]] = True

    topo2 = analyse_topology(mesh_flipped, flat_materials)
    merge_result = merge_regions(mesh_flipped, topo2, flat_materials)

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

    guard_after_removal = _guard_against_original(mesh_flipped, edge_flicker_cap=0.0)

    merge_report = dict(merge_result.report)
    rolled_back_reason = None
    guard_merge_attempt = None

    if not merge_report.get("converged", True):
        rolled_back_reason = "not_converged"   # no merged mesh exists, so there is none to guard
    else:
        guard_merge_attempt = _guard_against_original(merge_result.mesh, profile.edge_flicker_cap_final)
        if not guard_merge_attempt.passed:
            rolled_back_reason = "guard_failed"

    if rolled_back_reason is not None:
        merge_report["rolled_back"] = True
        merge_report["rolled_back_reason"] = rolled_back_reason
        final_mesh = mesh_flipped
        final_source_faces = [np.array([int(f)], dtype=np.int64) for f in source_from_removal]
        final_rings: dict = {}
        # `guard_final` describes what SHIPPED; `guard_merge_attempt` keeps the report that
        # caused the rollback, which is the only record of why the merge was thrown away.
        guard_final = _guard_against_original(final_mesh, profile.edge_flicker_cap_final)
    else:
        final_mesh = merge_result.mesh
        final_source_faces = [source_from_removal[s].astype(np.int64) for s in merge_result.source_faces]
        final_rings = merge_result.rings
        guard_final = guard_merge_attempt   # the merged mesh IS the shipped mesh

    one_sided_holes_after = one_sided_holes(
        positions_c, remap[final_mesh.face_v], np.arange(final_mesh.n_faces, dtype=np.int64),
        VIEWS_26, profile.guard_size)

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
        n_zero_area_dropped=n_zero_area_dropped, n_degenerate_restored=n_degenerate_restored,
        restored_degenerate=restored_degenerate_full,
        flipped=flipped_full, thin_sheets=thin_sheets_full,
        one_sided_holes_before=one_sided_holes_before, one_sided_holes_after=one_sided_holes_after,
        feedback_history={"hidden": history_hidden, "slit": history_slit},
        guard_after_removal=guard_after_removal, guard_merge_attempt=guard_merge_attempt,
        guard_final=guard_final,
        merge_report=merge_report, rings=final_rings, invariants=invariants, passed=passed)
