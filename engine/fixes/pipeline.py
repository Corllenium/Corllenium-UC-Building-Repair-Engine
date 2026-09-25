"""End-to-end automatic fix: remove what is truly hidden (and, opted in, what is only a sliver of
a slit), correct any face wound backwards, then re-triangulate what is left, with a facade guard
at every removal step and a final guard of the WHOLE result against the pristine original -- so a
cumulative drift that no single step would have caught on its own still gets caught here.

Order: `analyse_topology` -> `engine.fixes.solidify` (which APPENDS faces, so from here on the
reference mesh is longer than the input and every per-face array in `FixResult` is sized over the
reference, not the input) -> `compute_side_exposure`/`classify_exposure` -> candidates = hidden
faces AND degenerate ("zero-area") faces (plus slit faces, only when `profile.accept_slit`) ->
`guard_feedback` against the original, STRICT for pass 1 (the only automatic deletion, so it gets
the strictest guard) and, when slit faces are accepted, a SECOND colour-tolerant pass over the
state pass 1 leaves behind -> `remove_faces` -> `engine.detectors.fragments` (stray fragments
and attached slivers, removed when `profile.accept_fragments` and only when both the rays through
each piece (`engine.guard.piece_rays`: no line along which it was seen may then meet a side the
reference never exposed) and `fragment_feedback` -- the one guard that lets a pass change the
picture, only at those faces' own pixels -- confirm it; in the same pass, `engine.detectors.folds`
and the member of each fold the rest of the model still covers along every line) ->
`classify_orientation` +
`flip_faces` on the survivors, so a face whose only real exposure was on its BACK re-joins its
neighbours' region instead of being copied through alone (and, brief 11, `orient_sheets`: a THIN
survivor is wound like the connected near-coplanar sheet it belongs to, where that measures no
more back pixels) -> `analyse_topology` on the flipped
result -> `engine.fixes.overlap.remove_overlaps`, which drops a duplicate layer the rest of its
own region already covers, under the SAME strict guard (the merge can do nothing with a region
that overlaps itself: rule 3 excludes the triangles and a region whose union still overlaps is
skipped outright) -> `analyse_topology` again -> `merge_regions` -> a final guard of the merged
mesh against the ORIGINAL. If the merge
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

from engine.detectors.folds import detect_folds
from engine.detectors.fragments import detect_fragments, face_width
from engine.fixes.merge import default_collinear_tol, merge_regions
from engine.fixes.orient import (ORIENT_FLIP, ORIENT_THIN_SHEET, backface_counts, backface_pixels,
                                 classify_orientation, flip_faces, orient_sheets)
from engine.fixes.overlap import remove_overlaps
from engine.fixes.remove import remove_faces
from engine.fixes.solidify import solidify
from engine.guard.compare import (GuardReport, compare_views, face_planes, fragment_feedback,
                                   guard_feedback)
from engine.guard.piece_rays import judge_alone, piece_ray_check
from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.model import MeshData
from engine.pipeline import analyse_topology, flat_material_indices
from engine.topo.edges import COPLANAR_ANGLE, SOFT_ANGLE
from engine.rays.caster import ReusableCaster
from engine.topo.weld import weld_exact
from engine.vis.exposure import (EXP_HIDDEN, EXP_SLIT, classify_exposure, compute_side_exposure,
                                 fib_dirs)

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
    #: Dihedral thresholds, in degrees, for `engine.topo.edges.classify_edges`: at or below
    #: `coplanar_angle` two faces are flat to within what the export could print, and above it
    #: up to `soft_angle` a same-material border between two regions is an EDGE_SOFT crease.
    coplanar_angle: float = COPLANAR_ANGLE
    soft_angle: float = SOFT_ANGLE
    #: `edge_flicker_cap` for the FINAL guard only (merged vs original): merging never deletes a
    #: face, so a silhouette pixel may flicker by less than a pixel of sub-pixel coverage without
    #: that being real damage. The removal guards (inside `guard_feedback`) always use 0.0.
    edge_flicker_cap_final: float = 1e-4
    #: Ceiling, in inches, on the guard's depth tolerance (see `guard_depth_tol`). The tolerance
    #: is derived from the mesh's own print precision, which is right near 24,000 in (0.15 in)
    #: and wrong for a model exported in survey coordinates near 240,000 in, where the same
    #: formula gives 1.5 in -- and the crack test's ring radius IS that tolerance, so anything
    #: thinner than it would read as a crack the fix closed.
    depth_tol_max: float = 0.5
    #: Per-view cap on `PX_CRACK_CLOSED` pixels, as a fraction of that view's model pixels; over
    #: it they fall back to their base class and fail (see `engine.guard.compare.compare_views`).
    crack_closed_cap: float = 1e-3
    #: Close each slab before anything else runs -- skirts on its open outline edges and a bottom
    #: under it, so its interior stops being visible (`engine.fixes.solidify`). The CLI turns it
    #: off with `--no-solidify`. It is the only step in the engine that invents a vertex.
    solidify: bool = True
    #: `|n_z|` above which a region is horizontal enough to be a top surface (it must also see
    #: sky -- see `engine.fixes.solidify`), and at or below which a face is a SIDE face, the
    #: kind a skirt's thickness is measured from.
    top_min_nz: float = 0.7
    #: How much of a candidate region must see sky straight up for it to be a top surface.
    top_sky_fraction: float = 0.5
    #: UNUSED since SR5 (review I1), kept so profiles and report.json keep their shape: an edge's
    #: height comes only from the slab's own sides, never from side faces found within this many
    #: inches of its midpoint.
    skirt_search_radius: float = 60.0
    #: A measured region thickness is clamped into these bounds, in inches. On file A a real
    #: skirt varies from 1.3 to 49 in, so one uniform thickness leaks; these only bound it.
    min_thickness: float = 2.0
    #: THE CEILING on a slab's thickness (brief 10 item 2), set from the measured distribution of
    #: OWN-side depths -- how far each side hanging from a top's outline reaches below it, weighted
    #: by the length it runs -- on both files: A 21,761 in of own side over 138 regions, B 28,019
    #: in over 88. They come in LittleTiles steps of 9.84 in (25 cm): A 84.8 % at 9.84 in, 9.9 %
    #: at 29.52, 0.4 % at 39.37, 4.4 % at 49.21; B 72.0 % to 10 in, 13.0 % at 36.26-39.37. The
    #: deepest slab is A's region 852, 49.21 in (1.25 m) by all 816.9 in of its own side, and no
    #: side face of file A stands taller. The one own side deeper -- B region 820, 51.67 in over
    #: 39.4 of its 157.6 in, representative depth 22.14 -- is not a slab's depth and is clamped. It
    #: was 36 in, which clamped B's upper landing (region 92) and four more 39.37 in regions, and
    #: A's regions 852 and 857, their walls and bottoms stopping short of their own sides' feet.
    max_thickness: float = 50.0
    #: Fraction of a region's faces that must find something within `h + bottom_search_extra`
    #: straight down for it to count as already having a bottom.
    bottom_exists_fraction: float = 0.9
    #: How far PAST the region's bottom depth that downward search reaches, in inches. The
    #: bottom depth is the region's SHALLOWEST measured skirt height, and a slab thicker in the
    #: middle than at its rim already has an underside deeper than that: without this slack a
    #: second bottom is invented ABOVE the real one, boxing it in. Bounded, because "anything
    #: at all below me" is not a bottom.
    bottom_search_extra: float = 24.0
    #: The CAP GUARD's cover threshold (`engine.guard.compare.solidify_feedback`, rule 3): an
    #: invented face may cover a pixel whose BEFORE hit is an original face only while that
    #: face's exposure ON THE ORIGINAL MESH, on WHICHEVER side the ray met it (SR4; it read the
    #: front side only before), is below this -- a surface seen only through an opening. Not
    #: `== 0`, because ray sampling never gives exactly 0 for a wall seen through a small hole:
    #: the far wall of `compartment_with_deep_wall` measures a fraction of a percent through a
    #: 10 x 10 in opening 45 in away.
    cover_max_exposure: float = 0.10
    #: SR2. Half-width, in inches, of the band around a new wall's (or bottom's) plane in which an
    #: original face parallel to it is a PIECE of that broken side: replaced by the new face,
    #: removed together with its acceptance. From SR1's measurement of every face the old cap
    #: guard refused to cover near and parallel to a new face: 99 % of those pixels lie within
    #: 1.98 in (file A) and 2.35 in (file B). Capped at `engine.fixes.solidify.SIDE_BAND_MAX`
    #: (3 in), past which the band reaches things standing NEXT to the slab.
    side_band: float = 2.5
    #: Rounds the cap guard may spend removing invented faces before it gives up. It always
    #: verifies the state it hands back, so giving up is VISIBLE: `cap_guard_passed` goes False
    #: and with it the whole run's `passed`.
    cap_guard_max_rounds: int = 8
    #: Remove stray fragments and attached slivers (`engine.detectors.fragments`), between the
    #: hidden-face removal and the flip. The CLI turns it off with `--keep-fragments`. Unlike
    #: every other removal here it deletes geometry a person CAN see, so it runs under a guard
    #: of its own -- see `engine.guard.compare.fragment_feedback`.
    accept_fragments: bool = True
    #: A connected component whose total area is under this many square inches is debris, and no
    #: component holding a face bigger than this on its own is ever debris.
    fragment_max_area: float = 4.0
    #: ...and so is one whose longest bounding-box extent is under this many inches.
    fragment_max_extent: float = 6.0
    #: Polygon quality `4*pi*area/perimeter**2` below which a face ATTACHED to something real is
    #: a sliver: 1 is a circle, ~0.6 an equilateral triangle, 0.02 a needle about 1:150. How WIDE
    #: a sliver may be is not a setting: it is the merge's own border tolerance, derived from the
    #: mesh's print step (`sliver_width_bound`) -- and it is a sliver only on an open border
    #: (`engine.detectors.fragments`).
    sliver_q: float = 0.02
    #: Per-view cap on `PX_FRAGMENT_REMOVED` pixels, as a fraction of that view's model pixels,
    #: in the fragment guard and the final guard alike; over it they are judged as what they
    #: really are (see `engine.guard.compare.compare_views`). SIZED FROM THE REAL FILES at the
    #: 900 x 600 guard size: the largest share of a view ever recorded for them is 1.2e-4 (file
    #: B, brief 07; A 6.2e-5); re-measured at 670ad50 it is 4.8e-5 on A (7 px of a 145,828 px
    #: view) and 0 on B, and with the open-border sliver rule 0 on both. 1.2e-4 is about 9 px of
    #: A's average 79,000 px view. It was 5e-3, sized for `slab_with_strays`' 2 sq in stray at
    #: the tests' 120 x 80 (1.7e-3 of a view), which on the real files tripped only above about
    #: 400 px of debris per view -- so the tests that need that stray removed loosen it.
    fragment_removed_cap: float = 1.2e-4
    #: Pixel size of every image in the visual QA sheet the CLI writes under `<run dir>/qa/`
    #: (`engine.guard.qa_render.write_qa_sheet`). Not used by `fix_object` itself.
    qa_size: tuple[int, int] = (1600, 1000)


@dataclass
class FixResult:
    mesh: MeshData
    #: One int64 array per face of `mesh`, listing which faces of the REFERENCE mesh it came
    #: from -- a whole region when merged, a single face otherwise. The reference, not the input:
    #: when solidify runs it appends faces, and a face of `mesh` may have come from one of those.
    #: The input's own faces are rows `0 .. input.n_faces - 1` of the reference, so an id below
    #: that bound does mean the input face with the same id.
    source_faces: list[np.ndarray]
    #: Per REFERENCE-mesh face, one of `engine.vis.exposure`'s `EXP_*` codes. See
    #: `reference_mesh`: every per-face array in this dataclass is sized over that mesh, because
    #: that is the mesh the rest of the pipeline was handed.
    exposure_class: np.ndarray
    #: Bool, over REFERENCE-mesh faces: the hidden/slit faces `guard_feedback` confirmed
    #: removable.
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
    #: Bool, over REFERENCE-mesh faces: degenerate faces the guard put back, which stay in the
    #: mesh.
    restored_degenerate: np.ndarray
    #: Bool, over REFERENCE-mesh faces: survived removal and had its winding reversed -- its only
    #: real exposure was on the BACK (`engine.fixes.orient.classify_orientation`), or it is a
    #: thin face wound like its sheet (`sheet_flipped`).
    flipped: np.ndarray
    #: Bool, over REFERENCE-mesh faces: both sides exposed, roughly equally -- reported, and never
    #: flipped on its own evidence (`engine.fixes.orient.classify_orientation`); only the sheet
    #: rule may re-wind one, with the sheet it belongs to (`sheet_flipped`).
    thin_sheets: np.ndarray
    #: Brief 11 item 1. Bool, over REFERENCE-mesh faces: THIN faces re-wound like the connected
    #: near-coplanar sheet they belong to (`engine.fixes.orient.orient_sheets`); also in
    #: `flipped`.
    sheet_flipped: np.ndarray
    #: `engine.fixes.orient.orient_sheets`' report: the sheets whose windings disagreed, what was
    #: re-wound, what was refused, and the back pixels over the guard views before and after.
    sheet_report: dict
    #: Bool, over REFERENCE-mesh faces: debris -- a whole stray component, or an attached
    #: sliver -- confirmed removable by the FRAGMENT-mode guard (see
    #: `engine.detectors.fragments` and `engine.guard.compare.fragment_feedback`). Empty when
    #: `profile.accept_fragments` is False.
    removed_fragments: np.ndarray
    #: Connected components the detector found at all, debris or not. 0 when the pass is off.
    n_fragment_components: int
    n_removed_fragments: int
    n_removed_slivers: int
    #: Candidates put back -- by the rays through them or by the fragment guard -- so still in
    #: the mesh.
    n_restored_fragments: int
    #: ...of which refused by the rays through them (`engine.guard.piece_rays`): faces of
    #: candidates one of whose lines, with every removal done, met a side the reference never
    #: exposed.
    n_refused_by_rays: int
    #: `engine.detectors.fragments.FragmentResult.report` -- component counts and the smallest
    #: components the size rules did NOT catch. Empty when the pass is off.
    fragment_report: dict
    #: EVERY face the fragment pass removed, so each one can be found and checked: one entry per
    #: fragment component (`{"kind": "fragment", "component", "faces", "component_faces",
    #: "area", "bbox", "lines", "lines_inside"}` -- `faces` the REFERENCE ids removed,
    #: `component_faces` how many faces the component had, so a partly restored one shows) and
    #: one per sliver (`{"kind": "sliver", "component", "faces", "area", "width", "bbox",
    #: "lines", "lines_inside"}`), sorted by first face id. `area` in sq in, `width` in in, `bbox`
    #: `[[min x, y, z], [max x, y, z]]` in the input's own coordinates; `lines` and
    #: `lines_inside` are the piece's ray verdict (`fragment_ray_check`). Empty when the pass is
    #: off or removed nothing.
    fragment_removals: list
    #: The rays-through-the-piece verdict of EVERY candidate the pass proposed, removed or not:
    #: one entry per unit -- a fragment component, a sliver, or a fold's redundant member --
    #: `{"kind", "faces", "points", "lines", "lines_level", "lines_inside", "inside_faces",
    #: "refused", "removed"}` (see `engine.guard.piece_rays`): `lines` the (point, exposure
    #: direction) lines along which the piece was seen from outside on the reference,
    #: `lines_level` how many of them, once the removal was done, still met a face level with it,
    #: `lines_inside` how many met a side the reference never exposed, `inside_faces` up to five
    #: of the faces met there. A fold member is refused unless `lines_level == lines`; debris
    #: unless `lines_inside == 0`. Sorted by first face id; empty when the pass is off or
    #: proposed nothing.
    fragment_ray_check: list
    #: Faces removed as a FOLD's redundant member (`engine.detectors.folds`): two faces sharing
    #: an edge, folded onto the same side of it in one plane, and this one covered by the rest of
    #: the model along every line through it. Also in `removed_fragments`.
    n_removed_folds: int
    #: `engine.detectors.folds.FoldResult.report` plus every fold, resolved or left: `{...,
    #: "n_resolved", "n_left", "folds": [{"faces", "edge", "overlap_area", "members",
    #: "redundant", "verdict", "reason", "lines", "lines_level", "lines_inside"}]}` in REFERENCE
    #: ids. `edge` is the shared edge's two ends in the input's own coordinates; `members` each
    #: member's ray verdict judged ALONE (`{"face", "lines", "lines_level", "lines_inside"}`, empty
    #: for a fold never proposed); `redundant` the member proposed -- one the rest of the model
    #: covered along every line -- or `None`; `verdict` "resolved" (it was removed) or "left";
    #: `reason` why a fold was left ("different materials", "protected", "neither is covered by
    #: the rest", "refused by the rays", "put back by the fragment guard"); and `lines`,
    #: `lines_level`, `lines_inside` the proposed member's verdict with every removal done (else
    #: `None`). Empty when the fragment pass is off.
    fold_report: dict
    #: Bool, over REFERENCE-mesh faces: a duplicate layer the rest of its own region already
    #: covered, confirmed removable by the strict guard (see `engine.fixes.overlap`).
    removed_overlap: np.ndarray
    #: Bool, over REFERENCE-mesh faces: proposed as a covered duplicate and put back by the
    #: guard, so still in the mesh.
    restored_overlap: np.ndarray
    n_overlap_pairs_same: int
    n_overlap_pairs_diff: int
    n_removed_overlap: int
    n_restored_overlap: int
    #: Every DIFFERENT-material overlapping pair, as
    #: `{"faces": [i, j], "materials": [m_i, m_j], "area": sq in}` with REFERENCE face ids. Never
    #: removed -- which of two colours a person wants is not a question geometry can answer --
    #: only reported, as the input to a later preference-driven resolution.
    overlap_pairs_diff_material: list
    #: `engine.fixes.orient.one_sided_holes` over the ORIGINAL mesh's non-degenerate faces, and
    #: again over the mesh actually shipped (`mesh`) -- pixels a one-sided renderer would still
    #: drop as a hole. `_after` is expected to be lower than `_before`.
    one_sided_holes_before: int
    one_sided_holes_after: int
    #: SR0. Pixels whose FIRST hit is a face met on its BACK side -- SketchUp's blue-purple --
    #: over the 26 guard views, for the INPUT, the solidified REFERENCE and the FINAL mesh:
    #: `{"input" | "reference" | "final": {"total": int, "per_view": [26 ints, VIEWS_26 order]}}`.
    #: All three are framed on the reference, so they count the same pixels. `"input"`'s total
    #: is `one_sided_holes_before` and `"final"`'s is `one_sided_holes_after`; the reference is
    #: counted from the guard's own renders of it (`engine.fixes.orient.backface_counts`).
    backface_px: dict
    #: `{"hidden": ..., "slit": ..., "fragments": ..., "fragment_rays": ..., "overlap": ...}` --
    #: each pass's own per-round history; `"slit"` is `None` when no slit pass ran, and
    #: `"fragments"` (the fragment guard's rounds, numbered on across its calls) and
    #: `"fragment_rays"` (`engine.guard.piece_rays`' rounds) are `None` when the fragment pass
    #: did not run or had no candidate.
    feedback_history: dict
    guard_after_removal: GuardReport
    #: The MERGED mesh's guard against the reference -- the report that decided whether the merge
    #: was kept. `None` only when the merge did not converge, so there was no merged mesh to
    #: guard. It is kept even when the merge is ROLLED BACK, where `guard_final` describes the
    #: fallback that shipped instead: without it, the failure that caused the rollback leaves no
    #: trace at all. When nothing was rolled back it is the same report as `guard_final`.
    guard_merge_attempt: GuardReport | None
    guard_final: GuardReport
    #: The strictness all three of those guards were run at: False when a person opted into a
    #: colour-tolerant slit removal AND slit faces were actually removed, so `moved_same_flat`
    #: pixels are tolerated by construction. A reader of the reports needs it to know which of
    #: their counts are failures -- see `engine.guard.compare._fail_mask`.
    strict_final: bool
    #: `(F, 2)` bool per FINAL face: whether its FRONT / BACK side was already an outside surface
    #: on the reference -- some face it came from had exposure above 0 on that side. What the
    #: final guard lets a removed fragment uncover (`engine.guard.compare.classify_pixels`).
    exposed_final: np.ndarray
    #: Per FINAL face, the merged region it belongs to, or -1 when it was copied through (and
    #: -1 everywhere when the merge was rolled back). Two final faces sharing a region id >= 0
    #: are two triangles of ONE rebuilt polygon, so the edge between them is a triangulation
    #: diagonal, not a shape edge. `source_faces` cannot answer that: `fix_object` rebuilds it
    #: with `.astype`, so the array IDENTITY `engine.fixes.merge` sets up does not survive here.
    face_region_final: np.ndarray
    merge_report: dict
    #: `engine.fixes.solidify.SolidifyResult.report` -- skirts and bottoms added, the thickness
    #: each region was given, how many vertices were invented, what the cap guard removed, and
    #: how many faces the step moved to exposure 0. Empty when `profile.solidify` is False.
    solidify_report: dict
    #: `engine.guard.compare.solidify_feedback`'s per-round history -- the CAP GUARD's verdict,
    #: and the only comparison in the run still made against the PRISTINE input. `None` when
    #: `profile.solidify` is False.
    guard_solidify: list | None
    #: The mesh every guard in this run compares AGAINST: the solidified mesh, or the input when
    #: `profile.solidify` is False. EVERY per-face array above -- `exposure_class`,
    #: `removed_hidden`, `removed_slit`, `restored_degenerate`, `flipped`, `thin_sheets`,
    #: `removed_overlap`, `restored_overlap`, `removed_fragments`, `source_faces` and the face
    #: ids in `overlap_pairs_diff_material` -- is indexed against THIS mesh's faces, not the
    #: input's, because that is the mesh the rest of the pipeline was given. Its first rows are
    #: the input's faces MINUS `replaced_input`, in their original order, and every face
    #: solidify invented follows: input face `i` (not replaced) is reference row
    #: `cumsum(~replaced_input)[i] - 1`.
    reference_mesh: MeshData
    #: SR2. Bool over the INPUT's faces: pieces of a broken side or bottom that solidify replaced
    #: with a new wall or bottom -- not in the reference mesh at all. All False without solidify.
    replaced_input: np.ndarray
    #: `engine.fixes.merge.MergeResult.rings` -- `{output face: {"outer": ids, "inners": [...]}}`
    #: -- valid against `mesh` (this result's own final mesh) exactly as documented there. Empty
    #: when the merge candidate was rolled back, since there is then no merged mesh to index into.
    rings: dict
    invariants: dict
    passed: bool


def guard_depth_tol(quanta: np.ndarray, profile: FixProfile) -> float:
    """The depth tolerance every guard in this run works to: `1.5 * max(axis quanta)`, the mesh's
    own print precision, CLAMPED to `profile.depth_tol_max`.

    Unclamped the formula tracks the export: a model near 24,000 in prints Y to 0.1 in and gets
    0.15 in. A model exported in survey coordinates near 240,000 in prints to 1.0 in and would get
    1.5 in -- and `depth_tol` is not only the "did the surface move" bound, it is also the RADIUS
    of the crack and flicker rings, so at 1.5 in any genuinely lost sliver thinner than that reads
    as a crack the fix closed (`engine.guard.compare.classify_pixels` states that limit). The
    ceiling keeps the tolerance a property of what a person can see, not of where the model sits."""
    return min(1.5 * float(np.asarray(quanta).max()), profile.depth_tol_max)


def sliver_width_bound(quanta: np.ndarray, profile: FixProfile) -> float:
    """The widest an attached sliver may be (`engine.detectors.fragments`), in inches: the merge's
    own border tolerance, `default_collinear_tol(quanta)`, clamped to `profile.depth_tol_max` --
    the same derivation as the border-shift tolerance `fix_object` gives the guards that judge a
    merged mesh. Removing a sliver through its open border moves that border by at most its
    width, so the bound is exactly the border movement the rest of the engine already names,
    measures and excuses: 0.15 in on both real files' 0.1 in print step, 1.5e-4 in on a model
    printed to 1e-4 in, and never above `depth_tol_max` on a survey-coordinate export. It used to
    be the constant 0.15 whatever the print step (review 2a C1)."""
    return min(default_collinear_tol(quanta), profile.depth_tol_max)


def _total_area(positions: np.ndarray, face_v: np.ndarray) -> float:
    p = positions[face_v]
    return float(0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1).sum())


def _render(positions_c: np.ndarray, faces: np.ndarray, size: tuple[int, int]):
    ids = np.arange(len(faces), dtype=np.int64)
    # ReusableCaster: one embree BVH build for this geometry, reused across all 26 views.
    caster_factory = ReusableCaster()
    return [(v, ortho_first_hit(positions_c, faces, ids, v, positions_c, size, caster_factory))
            for v in VIEWS_26]


def _exposed_sides(positions_c: np.ndarray, face_w: np.ndarray, sources: list,
                   normal_reference: np.ndarray, side_exposure: np.ndarray) -> np.ndarray:
    """`(F, 2)` bool over the faces `face_w`: is each one's FRONT / BACK side a side the
    REFERENCE already showed -- does some reference face it came from (`sources[k]`, reference
    ids) have exposure above 0 on the side that now faces the same way? A face wound against its
    source (flipped, or a merged triangle facing the other way) reads that source's sides
    swapped. `side_exposure` is `(F_reference, 2)` bool, FRONT then BACK."""
    out = np.zeros((len(face_w), 2), dtype=bool)
    if not len(face_w):
        return out
    flat = [np.asarray(s, dtype=np.int64).reshape(-1) for s in sources]
    k = np.repeat(np.arange(len(flat)), [len(s) for s in flat])
    src = np.concatenate(flat)
    normal = face_planes(positions_c, face_w)[:, :3]
    same = np.einsum("ij,ij->i", normal_reference[src], normal[k]) >= 0.0
    np.logical_or.at(out, (k, 0), np.where(same, side_exposure[src, 0], side_exposure[src, 1]))
    np.logical_or.at(out, (k, 1), np.where(same, side_exposure[src, 1], side_exposure[src, 0]))
    return out


def _fragment_removals(detected, confirmed: np.ndarray, reference_ids: np.ndarray,
                       positions_c: np.ndarray, centre: np.ndarray,
                       face_w: np.ndarray, ray_check: list, covered_by: dict) -> list[dict]:
    """`FixResult.fragment_removals`: every face the fragment pass removed, grouped the way it
    was named -- a fragment component, a sliver, or a fold's redundant member (`covered_by`:
    `{member: its fold partner}`, REFERENCE ids, for the members proposed as folds alone) -- each
    with its ray verdict from `ray_check` (`FixResult.fragment_ray_check`). `reference_ids[i]` is
    the reference id of the detector's face `i`."""
    tri = positions_c[face_w]
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    verdict_of = {f: v for v in ray_check for f in v["faces"]}

    def entry(kind: str, component: int, ids: np.ndarray, **extra) -> dict:
        corners = positions_c[face_w[ids]].reshape(-1, 3) + centre
        verdict = verdict_of[int(ids[0])]
        return {"kind": kind, "component": int(component), "faces": [int(f) for f in ids],
                **extra, "area": round(float(area[ids].sum()), 4),
                "bbox": [np.round(corners.min(axis=0), 4).tolist(),
                         np.round(corners.max(axis=0), 4).tolist()],
                "lines": verdict["lines"], "lines_inside": verdict["lines_inside"]}

    out = []
    for c in np.unique(detected.component[detected.fragments]).tolist():
        members = reference_ids[detected.component == c]
        gone = members[confirmed[members]]
        if len(gone):
            out.append(entry("fragment", c, gone, component_faces=int(len(members))))
    widths = face_width(positions_c, face_w)
    for i in np.nonzero(detected.slivers)[0].tolist():
        f = int(reference_ids[i])
        if confirmed[f]:
            out.append(entry("sliver", detected.component[i], np.array([f]),
                             width=round(float(widths[f]), 4)))
    local_of = {int(r): i for i, r in enumerate(reference_ids.tolist())}
    for f, partner in sorted(covered_by.items()):
        if confirmed[f]:
            out.append(entry("fold", detected.component[local_of[f]], np.array([f]),
                             covered_by=int(partner)))
    return sorted(out, key=lambda e: e["faces"][0])


def _debris_units(detected, reference_ids: np.ndarray,
                  fold_members: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """The pass's candidates as the units the rays judge -- each fragment component whole, each
    sliver alone, each fold's redundant member (`fold_members`, bool over the detector's faces,
    none of them a fragment or a sliver) alone -- as `(kind, REFERENCE face ids)`, sorted by first
    face id."""
    units = [("fragment", reference_ids[(detected.component == c) & detected.fragments])
             for c in np.unique(detected.component[detected.fragments]).tolist()]
    units += [("sliver", reference_ids[[i]]) for i in np.nonzero(detected.slivers)[0].tolist()]
    units += [("fold", reference_ids[[i]]) for i in np.nonzero(fold_members)[0].tolist()]
    return sorted(units, key=lambda u: int(u[1].min()))


def _fold_members(folds, face_w_local: np.ndarray, reference_ids: np.ndarray,
                  positions_c: np.ndarray, render_faces: np.ndarray, side_exposure: np.ndarray,
                  drop: np.ndarray, profile: FixProfile) -> tuple[dict, dict]:
    """Which member of each fold may be proposed: one the rest of the model still covers exactly
    when it ALONE is gone -- every line along which it was seen then meets a face level with it
    (`engine.guard.piece_rays.judge_alone`) -- the smaller when both are, then the higher face id;
    none when neither is. Returns `(chosen, alone)`: `{fold index: detector face id or None}` for
    every fold with no reason against it, and `{detector face id: its verdict alone}`."""
    eligible = [k for k, fold in enumerate(folds.folds) if fold["reason"] is None]
    members = sorted({m for k in eligible for m in folds.folds[k]["faces"]})
    verdicts = judge_alone([reference_ids[[m]] for m in members], positions_c, render_faces,
                           side_exposure, directions=fib_dirs(profile.n_dirs), already_removed=drop)
    alone = dict(zip(members, verdicts))
    tri = positions_c[face_w_local]
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    chosen = {}
    for k in eligible:
        covered = [m for m in folds.folds[k]["faces"]
                   if alone[m]["lines_level"] == alone[m]["lines"]]
        chosen[k] = min(covered, key=lambda m: (float(area[m]), -m)) if covered else None
    return chosen, alone


def _fold_report(folds, chosen: dict, alone: dict, reference_ids: np.ndarray, removed: np.ndarray,
                 ray_check: list, positions_c: np.ndarray, centre: np.ndarray) -> dict:
    """`FixResult.fold_report`: the fold detector's report, and every fold with its verdict, in
    REFERENCE ids -- its shared edge's two ends in the input's own coordinates, and each member's
    verdict judged alone. A fold whose member was proposed is "resolved" when that member was
    removed, and otherwise "left": "refused by the rays" when, with every removal done, its lines
    no longer all met a level face (or one met a side never exposed), "put back by the fragment
    guard" when its pixels did not pass."""
    verdict_of = {f: v for v in ray_check for f in v["faces"]}
    out = []
    for k, fold in enumerate(folds.folds):
        f, g = (int(reference_ids[x]) for x in fold["faces"])
        reason = fold["reason"]
        member = chosen.get(k)
        redundant = None if member is None else int(reference_ids[member])
        ray = verdict_of.get(redundant) if redundant is not None else None
        if redundant is not None and removed[redundant]:
            verdict = "resolved"
        else:
            verdict = "left"
            if reason is None and redundant is None:
                reason = "neither is covered by the rest"
            elif reason is None:
                reason = "refused by the rays" if ray["refused"] else "put back by the fragment guard"
        members = ([] if fold["reason"] is not None else
                   [{"face": int(reference_ids[m]),
                     **{key: alone[m][key] for key in ("lines", "lines_level", "lines_inside")}}
                    for m in fold["faces"]])
        out.append({"faces": [f, g], "edge": np.round(positions_c[fold["edge"]] + centre, 2).tolist(),
                    "overlap_area": fold["overlap_area"], "members": members,
                    "redundant": redundant, "verdict": verdict, "reason": reason,
                    **{key: None if ray is None else ray.get(key, None)
                       for key in ("lines", "lines_level", "lines_inside")}})
    out.sort(key=lambda d: tuple(d["faces"]))
    resolved = sum(d["verdict"] == "resolved" for d in out)
    return {**folds.report, "n_resolved": resolved, "n_left": len(out) - resolved, "folds": out}


def _confirm_debris(units: list[tuple[str, np.ndarray]], positions_c: np.ndarray,
                    render_faces: np.ndarray, render_material: np.ndarray, flat_materials,
                    depth_tol: float, drop: np.ndarray, side_exposure: np.ndarray,
                    profile: FixProfile):
    """Which faces of `units` may go: every unit must pass the rays through it
    (`engine.guard.piece_rays`) AND the fragment guard (`fragment_feedback`) -- each judging with
    all the others' removals done.

    The rays go first: they are exact where the guard's pixels never reach. The fragment guard
    then judges the survivors, and when it puts faces back those faces are present again for the
    rays -- so the rays judge once more, and the guard again, until neither puts anything back.
    Both only ever put back, so this ends. Returns `(removed, ray_check, n_refused_by_rays,
    fragment_history, ray_history)` with `removed` bool over the reference faces and `ray_check`
    `FixResult.fragment_ray_check`."""
    n_faces = len(render_faces)
    faces_of = [np.asarray(ids, dtype=np.int64) for _kind, ids in units]
    alive = np.ones(len(units), dtype=bool)
    verdicts: list = [None] * len(units)
    refused_by_rays = np.zeros(n_faces, dtype=bool)
    removed = np.zeros(n_faces, dtype=bool)
    fragment_history: list = []
    ray_history: list = []
    directions = fib_dirs(profile.n_dirs)
    # a fold's member must stay covered: its removal is meant to change nothing at all
    covered = np.array([kind == "fold" for kind, _ids in units], dtype=bool)
    while alive.any():
        check = piece_ray_check(faces_of, positions_c, render_faces, side_exposure,
                                directions=directions, already_removed=drop, marked=alive,
                                covered=covered)
        for i, verdict in enumerate(check.verdicts):
            if verdict is not None:
                verdicts[i] = verdict
        for i in np.nonzero(alive & ~check.confirmed)[0].tolist():
            refused_by_rays[faces_of[i]] = True
        ray_history += [dict(h, round=len(ray_history) + k) for k, h in enumerate(check.history)]
        alive = check.confirmed
        candidates = np.zeros(n_faces, dtype=bool)
        for i in np.nonzero(alive)[0].tolist():
            candidates[faces_of[i]] = True
        if not candidates.any():
            break
        # `already_removed=drop`, so the guard's BEFORE is the WHOLE reference -- the same
        # picture the final guard renders -- while its AFTER drops the candidates as well as
        # everything earlier passes took out. See `fragment_feedback`.
        confirmed, history = fragment_feedback(
            candidates, positions_c, render_faces, render_material, flat_materials,
            depth_tol, already_removed=drop, size=profile.guard_size,
            crack_closed_cap=profile.crack_closed_cap, side_exposure=side_exposure,
            fragment_removed_cap=profile.fragment_removed_cap)
        fragment_history += [dict(h, round=len(fragment_history) + k) for k, h in enumerate(history)]
        removed = confirmed & candidates
        if not (candidates & ~confirmed).any():
            break
        # the guard put faces back: a unit is now what it still confirms, and the rays judge
        # again with those faces present
        for i in np.nonzero(alive)[0].tolist():
            faces_of[i] = faces_of[i][confirmed[faces_of[i]]]
            alive[i] = len(faces_of[i]) > 0
        removed = np.zeros(n_faces, dtype=bool)

    ray_check = []
    for (kind, ids), verdict in zip(units, verdicts):
        ray_check.append({"kind": kind, "faces": [int(f) for f in ids],
                          **{k: verdict[k] for k in ("points", "lines", "lines_level",
                                                     "lines_inside", "inside_faces", "refused")},
                          "removed": bool(removed[ids].any())})
    return removed, ray_check, int(refused_by_rays.sum()), fragment_history, ray_history


def fix_object(mesh: MeshData, flatness: dict[str, float], profile: FixProfile = FixProfile()) -> FixResult:
    flat_materials = flat_material_indices(mesh, flatness, profile.flat_texture_std)
    angles = {"coplanar_angle": profile.coplanar_angle, "soft_angle": profile.soft_angle}
    input_mesh = mesh
    topo_input = analyse_topology(mesh, flat_materials, **angles)

    # ---- solidify: close each slab, so its interior can become hidden at all ------------------
    # The only step that invents a vertex, and everything after it works on the SOLIDIFIED mesh:
    # exposure, both removal guards and the final guard all take it as the reference, because it
    # is the mesh a person accepted when they asked for the sides to be built. The cap guard's
    # own report against the pristine input is kept as `guard_solidify`.
    solidify_report: dict = {}
    replaced_input = np.zeros(mesh.n_faces, dtype=bool)
    if profile.solidify:
        result = solidify(mesh, topo_input, profile)
        mesh, solidify_report, replaced_input = result.mesh, result.report, result.replaced

    topo = analyse_topology(mesh, flat_materials, **angles)
    depth_tol = guard_depth_tol(topo.quanta, profile)
    # Recentre once, to the REFERENCE mesh's bbox centre; the same recentred frame renders every
    # side, before and after, at every stage -- vertices never move after this point, so one
    # frame is always correct. The input mesh's own faces index the same rows (solidify only
    # APPENDS positions), so they can be rendered in this frame too.
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
    positions_c = topo.positions_w - centre
    _, remap = weld_exact(mesh.positions, mesh.coord_decimals)  # same weld space as topo, reusable
    # for any mesh whose `positions` is the SAME array (remove_faces/merge_regions never touch it).

    front, back = compute_side_exposure(positions_c, topo.face_w, topo.ok, n_dirs=profile.n_dirs)
    exposure = front + back
    # which side of each reference face a person could already see -- what a removed fragment
    # may uncover and nothing else (`engine.guard.compare.classify_pixels`)
    side_exposure = np.stack([front > 0.0, back > 0.0], axis=1)
    normal_reference = face_planes(positions_c, topo.face_w)[:, :3]
    exposure_class = classify_exposure(exposure, topo.ok, profile.slit_threshold)
    orientation = classify_orientation(front, back, topo.ok)
    flip_candidates_full = orientation == ORIENT_FLIP
    thin_sheets_full = orientation == ORIENT_THIN_SHEET

    # ...on the INPUT mesh's own faces, not the reference's: the point of the number is what the
    # export arrived with. They index `positions_c` too, since solidify only appends.
    face_w_input = remap[input_mesh.face_v]
    backface_input = backface_pixels(
        positions_c, face_w_input, np.arange(input_mesh.n_faces, dtype=np.int64), VIEWS_26,
        profile.guard_size)
    one_sided_holes_before = int(sum(backface_input))

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
        depth_tol, strict=True, size=profile.guard_size,
        crack_closed_cap=profile.crack_closed_cap)
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
            size=profile.guard_size, crack_closed_cap=profile.crack_closed_cap)
        removed_slit_full[remaining_ids[mask2]] = True
    n_removed_slit = int(removed_slit_full.sum())

    drop = removed_hidden_full | removed_slit_full | removed_degenerate_full
    mesh_removed, source_from_removal = remove_faces(mesh, drop)

    # ---- stray fragments and attached slivers, under a guard of their OWN --------------------
    # After the hidden pass, because a stray only stands out once what is genuinely invisible is
    # gone, and before the flip, because a face about to be deleted is not worth re-winding. The
    # guard here is `fragment_feedback`, not `guard_feedback`: this is the one removal in the
    # engine that deliberately changes the picture, so the rule is "nothing OTHER than these
    # faces' own pixels changed" rather than "nothing changed".
    removed_fragments_full = np.zeros(mesh.n_faces, dtype=bool)
    fragment_report: dict = {}
    fold_report: dict = {}
    fragment_removals: list = []
    fragment_ray_check: list = []
    fragment_history = ray_history = None
    n_removed_fragments = n_removed_slivers = n_removed_folds = 0
    n_restored_fragments = n_refused_by_rays = 0
    mesh_fragments, source_from_fragments = mesh_removed, np.arange(mesh_removed.n_faces, dtype=np.int64)
    if profile.accept_fragments:
        kept = ~drop
        # The faces solidify invented are the shell it is closing, never debris: protected, so
        # neither they nor a component holding one is ever a candidate (file A's face 4721, an
        # invented bottom triangle, was removed as a one-face stray). `result` is solidify's.
        invented = (np.asarray(result.new_faces, dtype=bool) if profile.solidify
                    else np.zeros(mesh.n_faces, dtype=bool))
        # contact within the tolerance `analyse_topology` finds T-junctions with, and no sliver
        # wider than the merge's own border tolerance
        contact_tol = 1.5 * float(topo.quanta.max())
        max_width = sliver_width_bound(topo.quanta, profile)
        detected = detect_fragments(positions_c, render_faces[kept], profile,
                                    contact_tol=contact_tol, max_width=max_width,
                                    protected=invented[kept])
        fragment_report = detected.report
        # ...and FOLDS: two faces folded onto the same side of their shared edge, the area
        # covered twice. The member proposed is one the rest of the model still covers exactly
        # when it alone is gone -- judged by the rays through it, not by the fold's own shape
        # (`engine.detectors.folds`) -- and it goes only if it stays covered with every other
        # removal done too, and the fragment guard agrees.
        folds = detect_folds(positions_c, render_faces[kept], render_material[kept],
                             contact_tol=contact_tol, protected=invented[kept])
        chosen, alone = _fold_members(folds, render_faces[kept], source_from_removal,
                                      positions_c, render_faces, side_exposure, drop, profile)
        fold_members = np.zeros(int(kept.sum()), dtype=bool)
        fold_members[[m for m in chosen.values() if m is not None]] = True
        fold_members &= ~(detected.fragments | detected.slivers)
        covered_by = {int(source_from_removal[chosen[k]]):
                      int(source_from_removal[sum(folds.folds[k]["faces"]) - chosen[k]])
                      for k in sorted(chosen, reverse=True)
                      if chosen[k] is not None and fold_members[chosen[k]]}
        candidates = np.zeros(mesh.n_faces, dtype=bool)      # lifted back to REFERENCE ids
        candidates[source_from_removal[detected.fragments | detected.slivers | fold_members]] = True
        confirmed = np.zeros(mesh.n_faces, dtype=bool)
        if candidates.any():
            # every candidate is judged by the rays through it AND by the fragment guard's
            # pixels, each with all the others' removals done -- the rays because no guard pixel
            # meets a sub-pixel piece (brief 08: 10 real-surface pieces went that way)
            (confirmed, fragment_ray_check, n_refused_by_rays, fragment_history,
             ray_history) = _confirm_debris(
                _debris_units(detected, source_from_removal, fold_members), positions_c,
                render_faces, render_material, flat_materials, depth_tol, drop, side_exposure,
                profile)
            kind = np.zeros(mesh.n_faces, dtype=np.int8)       # 1 fragment, 2 sliver, 3 fold
            kind[source_from_removal[detected.fragments]] = 1
            kind[source_from_removal[detected.slivers]] = 2
            kind[source_from_removal[fold_members]] = 3
            n_removed_fragments = int((confirmed & (kind == 1)).sum())
            n_removed_slivers = int((confirmed & (kind == 2)).sum())
            n_removed_folds = int((confirmed & (kind == 3)).sum())
            n_restored_fragments = int((candidates & ~confirmed).sum())
            removed_fragments_full = confirmed
            fragment_removals = _fragment_removals(detected, confirmed, source_from_removal,
                                                   positions_c, centre, render_faces,
                                                   fragment_ray_check, covered_by)
            mesh_fragments, source_from_fragments = remove_faces(mesh_removed, confirmed[kept])
        fold_report = _fold_report(folds, chosen, alone, source_from_removal, confirmed,
                                   fragment_ray_check, positions_c, centre)
    source_after_fragments = source_from_removal[source_from_fragments]

    # ---- orientation: correct any survivor whose only real exposure was on its BACK ----------
    flip_removed = flip_candidates_full[source_after_fragments]
    # ...and wind a THIN survivor like the connected near-coplanar sheet it belongs to, where
    # that sheet's windings disagree and the change measures no more back pixels over the guard
    # views (brief 11 item 1, `engine.fixes.orient.orient_sheets`). Judged on the survivors,
    # framed on the reference like every other render here; a flip changes no double-sided
    # render, so no guard can see it.
    sheets = orient_sheets(
        positions_c, remap[mesh_fragments.face_v], front[source_after_fragments],
        back[source_after_fragments], flip_removed, thin_sheets_full[source_after_fragments],
        topo.ok[source_after_fragments], tol=depth_tol, angle_deg=profile.coplanar_angle,
        size=profile.guard_size, centre=centre)
    sheet_flipped_full = np.zeros(mesh.n_faces, dtype=bool)
    sheet_flipped_full[source_after_fragments[sheets.flip]] = True
    flip_removed = flip_removed | sheets.flip
    mesh_flipped = flip_faces(mesh_fragments, flip_removed)
    flipped_full = np.zeros(mesh.n_faces, dtype=bool)
    flipped_full[source_after_fragments[flip_removed]] = True

    # ---- covered same-material duplicate layers, under the same strict guard -----------------
    # Before the merge and after the flip: the merge cannot do anything with a region that
    # overlaps itself (rule 3 excludes the triangles, and a region whose union still overlaps is
    # skipped outright), and flipping first means a face is judged in the winding it will ship in.
    topo2 = analyse_topology(mesh_flipped, flat_materials, **angles)
    overlap_result = remove_overlaps(
        mesh_flipped, topo2, positions_c, flat_materials, depth_tol,
        guard_size=profile.guard_size, crack_closed_cap=profile.crack_closed_cap)
    mesh_overlapped = overlap_result.mesh
    source_from_overlap = source_after_fragments[overlap_result.source_faces]

    removed_overlap_full = np.zeros(mesh.n_faces, dtype=bool)
    removed_overlap_full[source_after_fragments[overlap_result.removed]] = True
    restored_overlap_full = np.zeros(mesh.n_faces, dtype=bool)
    restored_overlap_full[source_after_fragments[overlap_result.restored]] = True
    # every face id leaving this function indexes the REFERENCE mesh
    overlap_pairs_diff_material = [
        {"faces": [int(source_after_fragments[e["faces"][0]]),
                    int(source_after_fragments[e["faces"][1]])],
         "materials": e["materials"], "area": e["area"]}
        for e in overlap_result.report["overlap_pairs_diff_material"]]

    topo3 = analyse_topology(mesh_overlapped, flat_materials, **angles)
    merge_result = merge_regions(mesh_overlapped, topo3, flat_materials)
    # How far the merge may move a border: its corner pass drops a border vertex while the whole
    # original polyline stays within `collinear_tol` of the chord that replaces it, so a merged
    # border can sit up to that far from the original. The guards that judge a merged mesh MEASURE
    # each flicker pixel's real displacement and excuse up to exactly that (`border_shift_tol`,
    # see `engine.guard.compare.classify_pixels`) -- clamped to `depth_tol_max`, so a coarse-
    # precision export cannot excuse a wide shift. The same derivation `merge_regions` just used.
    border_shift_tol = min(default_collinear_tol(topo3.quanta), profile.depth_tol_max)

    # A slit-tolerant removal is a person-accepted, colour-tolerant change: both guard checks
    # below use the same strictness the removal itself used.
    strict_final = not (profile.accept_slit and n_removed_slit > 0)

    # THE FINAL GUARD TOLERATES THE FRAGMENT PIXELS, and nothing else. Removing visible debris
    # is a change, and the guard's question -- "is the picture the same" -- answers no, correctly,
    # for exactly the pixels the fragment pass was authorised to change by its own guard. So
    # those pixels are excused BY NAME: `removed_before` marks the faces, and a pixel whose
    # BEFORE first hit is one of them is `PX_FRAGMENT_REMOVED` (see `classify_pixels`) -- but
    # only where the shipped mesh shows the sky there or a side the reference already showed
    # (`exposed_after`, mapped onto each final face through the faces it came from), and only
    # up to `fragment_removed_cap` of a view. A removed face that uncovers the inside of a shell
    # is a hole, judged as one. It used to be excused whatever it uncovered (review C2).
    #
    # Not by leaving those faces out of the BEFORE render, which is a different thing and is
    # wrong. The hidden pass ran FIRST and its guard judged the picture WITH the debris in it, so
    # a face it deleted may have been invisible only because a sliver covered it -- and a BEFORE
    # render without that sliver puts the deleted face back on screen. Measured on file A: 749
    # `moved_same_flat` pixels of damage that never existed, and a rolled-back merge.
    face_w_original = topo.face_w
    material_original = mesh.face_material
    planes_original = face_planes(positions_c, face_w_original)
    before_original = _render(positions_c, face_w_original, profile.guard_size)
    # the reference's back faces, counted from the renders the final guard needs anyway
    backface_reference = backface_counts(before_original, planes_original[:, :3])

    def _guard_against_original(final_mesh: MeshData, sources: list, edge_flicker_cap: float,
                                border_shift_tol: float) -> GuardReport:
        face_w_final = remap[final_mesh.face_v]
        after = _render(positions_c, face_w_final, profile.guard_size)
        return compare_views(
            before_original, after, material_original, final_mesh.face_material, flat_materials,
            depth_tol, strict=strict_final, plane_before=planes_original,
            plane_after=face_planes(positions_c, face_w_final), edge_flicker_cap=edge_flicker_cap,
            crack_closed_cap=profile.crack_closed_cap,
            geometry_before=(positions_c, face_w_original),
            geometry_after=(positions_c, face_w_final),
            removed_before=removed_fragments_full, border_shift_tol=border_shift_tol,
            exposed_after=_exposed_sides(positions_c, face_w_final, sources, normal_reference,
                                         side_exposure),
            fragment_removed_cap=profile.fragment_removed_cap)

    # the mesh the merge was attempted on, which is also what ships if it is rolled back. Nothing
    # here moved a border -- faces were only removed -- so this guard excuses no border shift.
    sources_unmerged = [np.array([int(f)], dtype=np.int64) for f in source_from_overlap]
    guard_after_removal = _guard_against_original(mesh_overlapped, sources_unmerged,
                                                  edge_flicker_cap=0.0, border_shift_tol=0.0)

    merge_report = dict(merge_result.report)
    rolled_back_reason = None
    guard_merge_attempt = None

    merged_source_faces: list = []
    if not merge_report.get("converged", True):
        rolled_back_reason = "not_converged"   # no merged mesh exists, so there is none to guard
    else:
        merged_source_faces = [source_from_overlap[s].astype(np.int64)
                               for s in merge_result.source_faces]
        guard_merge_attempt = _guard_against_original(
            merge_result.mesh, merged_source_faces, profile.edge_flicker_cap_final,
            border_shift_tol)
        if not guard_merge_attempt.passed:
            rolled_back_reason = "guard_failed"

    if rolled_back_reason is not None:
        merge_report["rolled_back"] = True
        merge_report["rolled_back_reason"] = rolled_back_reason
        final_mesh = mesh_overlapped
        final_source_faces = sources_unmerged
        final_rings: dict = {}
        final_face_region = np.full(mesh_overlapped.n_faces, -1, np.int64)
        # `guard_final` describes what SHIPPED; `guard_merge_attempt` keeps the report that
        # caused the rollback, which is the only record of why the merge was thrown away.
        guard_final = _guard_against_original(final_mesh, final_source_faces,
                                              profile.edge_flicker_cap_final, border_shift_tol)
    else:
        final_mesh = merge_result.mesh
        final_source_faces = merged_source_faces
        final_rings = merge_result.rings
        final_face_region = merge_result.face_region
        guard_final = guard_merge_attempt   # the merged mesh IS the shipped mesh
    exposed_final = _exposed_sides(positions_c, remap[final_mesh.face_v], final_source_faces,
                                   normal_reference, side_exposure)

    backface_final = backface_pixels(
        positions_c, remap[final_mesh.face_v], np.arange(final_mesh.n_faces, dtype=np.int64),
        VIEWS_26, profile.guard_size)
    one_sided_holes_after = int(sum(backface_final))
    backface_px = {name: {"total": int(sum(counts)), "per_view": [int(c) for c in counts]}
                   for name, counts in (("input", backface_input),
                                        ("reference", backface_reference),
                                        ("final", backface_final))}

    # Against the REFERENCE mesh, not the pristine input: solidify deliberately grows both the
    # bounding box (downwards, by a skirt) and the area (by the faces it invents), and it is the
    # mesh every guard in this run compares against. The cap guard is what bounds what solidify
    # may do; `guard_solidify` carries its verdict.
    # Review M2: compare the bbox of vertices that faces actually use, evaluated against the
    # surviving reference faces (excluding faces deliberately deleted by the pipeline passes).
    # WHY DELETED FACES ARE LEFT OUT, and to the guards: what a removal did to the picture is
    # exactly what its own guard judged (strict for hidden and overlap faces, the fragment guard
    # for debris), and the bbox cannot tell a legitimate removal from damage. 0b4b8e9 compared
    # against every reference face and left the suite red -- deleting `slab_with_strays`' stray
    # at the model's top shrank the used bbox -- so f285ef3 compares only what survived them.
    # WHY WITHIN `border_shift_tol` and not exactly: the merge's corner pass may drop a border
    # vertex while the original polyline stays within that tolerance of the chord replacing it,
    # so a merged border may sit that far inside the original one -- the movement the final
    # guard measures and excuses. Compared exactly, review 2a's E4 plate (its unique max-x
    # vertex 0.1 in off a straight edge, dropped) failed a run whose guard passed.
    deleted = drop | removed_fragments_full | removed_overlap_full
    surviving_face_v = mesh.face_v[~deleted] if len(mesh.face_v) else mesh.face_v
    ref_used = np.unique(surviving_face_v) if len(surviving_face_v) else []
    final_used = np.unique(final_mesh.face_v) if len(final_mesh.face_v) else []
    ref_bbox = ((mesh.positions[ref_used].min(axis=0), mesh.positions[ref_used].max(axis=0))
                if len(ref_used) else (np.zeros(3), np.zeros(3)))
    final_bbox = ((final_mesh.positions[final_used].min(axis=0), final_mesh.positions[final_used].max(axis=0))
                  if len(final_used) else (np.zeros(3), np.zeros(3)))

    invariants = {
        "material_count_same": len(final_mesh.materials) == len(mesh.materials),
        "bbox_same": bool((np.abs(final_bbox[0] - ref_bbox[0]) <= border_shift_tol).all()
                          and (np.abs(final_bbox[1] - ref_bbox[1]) <= border_shift_tol).all()),
        "area_not_grown": bool(_total_area(final_mesh.positions, final_mesh.face_v)
                               <= _total_area(mesh.positions, mesh.face_v) * (1.0 + _AREA_REL_TOL)),
        # The CAP GUARD's own verdict, re-verified against the mesh solidify handed back (see
        # `engine.guard.compare.solidify_feedback`). It is an invariant and not merely a report,
        # because every other guard in this run compares against the solidified mesh: if the cap
        # guard never converged, the reference itself is covering something a person can see, and
        # no later guard would ever notice. True vacuously when solidify did not run.
        "cap_guard_passed": bool(solidify_report.get("cap_guard_passed", True)),
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
        sheet_flipped=sheet_flipped_full, sheet_report=sheets.report,
        removed_fragments=removed_fragments_full,
        n_fragment_components=int(fragment_report.get("n_components", 0)),
        n_removed_fragments=n_removed_fragments, n_removed_slivers=n_removed_slivers,
        n_restored_fragments=n_restored_fragments, n_refused_by_rays=n_refused_by_rays,
        fragment_report=fragment_report, fragment_removals=fragment_removals,
        fragment_ray_check=fragment_ray_check, n_removed_folds=n_removed_folds,
        fold_report=fold_report,
        removed_overlap=removed_overlap_full, restored_overlap=restored_overlap_full,
        n_overlap_pairs_same=overlap_result.report["n_overlap_pairs_same"],
        n_overlap_pairs_diff=overlap_result.report["n_overlap_pairs_diff"],
        n_removed_overlap=overlap_result.report["n_removed_overlap"],
        n_restored_overlap=overlap_result.report["n_restored_overlap"],
        overlap_pairs_diff_material=overlap_pairs_diff_material,
        one_sided_holes_before=one_sided_holes_before, one_sided_holes_after=one_sided_holes_after,
        backface_px=backface_px,
        feedback_history={"hidden": history_hidden, "slit": history_slit,
                          "fragments": fragment_history, "fragment_rays": ray_history,
                          "overlap": overlap_result.history},
        guard_after_removal=guard_after_removal, guard_merge_attempt=guard_merge_attempt,
        guard_final=guard_final, strict_final=strict_final,
        exposed_final=exposed_final,
        face_region_final=final_face_region,
        solidify_report=solidify_report, reference_mesh=mesh, replaced_input=replaced_input,
        guard_solidify=solidify_report.get("cap_guard") if solidify_report else None,
        merge_report=merge_report, rings=final_rings, invariants=invariants, passed=passed)
