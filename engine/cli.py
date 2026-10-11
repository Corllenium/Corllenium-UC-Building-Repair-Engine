"""Command-line entry point for the automatic fix pipeline.

`python -m engine.cli fix <snapshot_dir> [--accept-slit] [--out data/output]`
    Runs `engine.fixes.pipeline.fix_object` on the snapshot and writes, under `<out>/<name>/`:
    `<name>.fixed.obj` (triangles -- the file for Unity), `<name>.fixed.ngon.obj` (polygons, a
    viewer/documentation artifact), a copy of `materials.mtl` and `tex/`, `report.json` (every
    number in `FixResult`, both guard reports per view, the profile, the input sha256), and
    `guard_<view>.png` before/after/difference triptychs for 6 axis views, and the 21-image
    visual QA sheet under `qa/` (`engine.guard.qa_render`; a failure to draw it is recorded in
    report.json's `qa` and does not fail the run). Exit code 0 when `passed`, 2 otherwise.

    It also writes `<name>.fixed.skp` (`engine.io.skp_writer`, through SketchUp's own C API) and
    copies it into `<repo root>/OBJ FIXED RESULT/`, the folder the owner opens in SketchUp after
    every run: a PASSING run's copy replaces `<name>.fixed.skp` there, a failed run's goes to
    `<name>.fixed.FAILED.skp` and leaves the owner's file as it was (see `_write_skp`); `--skp-dir`
    names another folder, `--no-skp` skips it. Without SketchUp the run still succeeds and
    report.json's `skp` says why no file was written.

    `--kernel` runs the same fix through the observe-only repair kernel
    (`engine.repair.kernel.repair_unit`): the same files, byte for byte, plus `edit_log.jsonl` next to
    report.json -- one line per edit each stage was observed to make.

    `--kernel --validate-sites [--materials data/campus/materials.json]` also checks every stage with
    the Validator's focus mode (`engine.site_judge.SiteJudge`, the owner's settings; job P1-K3b): one
    focus run per stage, each failing sample charged to the stage's sites. The legacy stages are one
    site each and are NOT rolled back (ruling K3-R2), so the files are the `--kernel` run's, and
    `edit_log.jsonl` gains one `{"check": {...}}` line per stage: its verdict, the failing counts by
    reason and the run times. It prints each stage's verdict and the total time.

`python -m engine.cli preview-data <snapshot_dir> --out preview/data`
    Writes the JSON `preview/index.html` reads (see `spike/12_export_preview.py` for the shape
    this mirrors), with AFTER built from the REAL fixed mesh and the REAL guard numbers, and
    `stats` extended with the new counts (flipped, thin_sheets, one_sided_holes_before/after,
    outline_edges_after, unavoidable_diagonals_after, guard_passed).

`python -m engine.cli validate --before <snapshot_dir> --after <obj> --materials <materials.json> --out <dir>`
    Judges a repaired floor by the owner's rule (AGENTS.md section 6, `engine.validate`): are the facade
    textures still there, are the problems solved, was nothing visible deleted or covered. Writes
    `<dir>/validation.json` (`{"checks": {"textures", "problems", "nothing_deleted"}, "verdict": "PASS" or
    "FAIL", "sites": [...]}` and everything the run was made from) and `<dir>/evidence/*.png`, two
    256 px crops (BEFORE, AFTER) of each of the 20 worst failing sites. Exit code 0 on PASS, 2 on FAIL
    or when an input is missing. Nothing is changed or fixed; the inputs are only read.

`python -m engine.cli campus-unit-before --unit <UNIT> --out <dir>`
    Writes a campus unit's BEFORE as a snapshot-shaped folder (`<UNIT>.obj`, `materials.mtl`) from its members'
    frozen snapshots, banded members cut by face-centre z, so `validate --before <dir>` takes a whole unit.
    Exit 0 when each member's face count is the campus map's, 1 when one differs, 2 on a refused input.

`python -m engine.cli repair-unit (--unit <UNIT> | --snapshot <dir>) --engines E8 --out <dir>`
    Repairs one unit with the P2 engines (E8: E8a, strict solidify, then E8b, the narrow flat fill; `E8a` or `E8b`
    runs one of them): builds its BEFORE as `campus-unit-before`
    does (into `<dir>/before/`), runs the repair kernel with the site judge on (`validate_sites=True`), so each
    piece of work is its own site and one that breaks anything visible -- a rebuilt side covering anything any
    viewpoint sees, eye-height probes included -- is rolled back. Writes `<unit>.fixed.obj`, `edit_log.jsonl` and
    `report.json` (pieces built, kept and rolled back by reason; the Validator's covered count after rollback;
    times; for E8b `fills`, each kept fill with its BEFORE | AFTER crop in `fills/`, `not_filled`, every hole refused
    with its rule, and `fill_stats`; `needs_modelling`, the summary of `needs_modelling.json`). Also writes
    `needs_modelling.json` (schema version 1: every refused hole and every slab side or bottom the site check rolled back,
    per floor, for a person to model in SketchUp, each with a stable id, a suggested camera view and a BEFORE crop in
    `needs_modelling/`; see `engine.campus.needs_modelling`). A refused run (exit 1) removes the outputs an earlier run left in
    `--out`. No `.skp`. Exit 0 when the E8 stage passed, 1 when the unit's BEFORE differs from the campus map
    (nothing repaired), 2 on a refused input, 3 when the stage was rolled back whole or ended FAIL (every file is
    still written, and the mesh shipped is the BEFORE).
    `--engines` takes a comma list run IN ORDER (job P2-E3), e.g. `--engines E8a,E3`: E3 removes hidden faces,
    interior-aware (`engine.repair.engines.e3_hidden`), one site per connected group, each judged like the rest;
    report.json then also carries `e3` (candidates, groups, sites kept and rolled back by reason, faces removed, the
    Validator's deleted count after rollback, disagreements). `E8` keeps meaning E8a then E8b. Unknown names exit 2.

A snapshot directory is the layout `engine.io.snapshot.snapshot_object` produces: one `<name>.obj`,
`materials.mtl`, and a `tex/` folder of the textures it references.

`engine/` imports nothing from `api`, `spike`, fastapi, sqlalchemy; `trimesh`/`embreex` stay
confined to `engine/rays/` -- this module never imports them directly, only through
`engine.rays.caster.ReusableCaster`/`EmbreeCaster`.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import shutil
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from engine.fixes.pipeline import FixProfile, FixResult, fix_object, guard_depth_tol
from engine.guard.compare import (PX_FRAGMENT_REMOVED, GuardReport, ViewVerdict, classify_pixels,
                                  face_planes)
from engine.guard.qa_render import polygon_edges, qa_file_names, write_qa_sheet
from engine.guard.render import save_triptych
from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.io.mtl import MtlMaterial, parse_mtl, texture_flatness
from engine.io.obj_reader import read_obj
from engine.io.obj_writer import write_obj, write_obj_polygons
from engine.io.protected import refuse_protected
from engine.io.skp_writer import SketchUpError, check_skp_validity, write_skp
from engine.io.snapshot import sha256_file
from engine.model import MeshData
from engine.pipeline import (Topology, analyse_topology, analyse_topology_memo,
                             coplanar_region_borders, flat_material_indices)  # noqa: F401 -- analyse_topology stays importable from here
from engine.rays.caster import ReusableCaster
from engine.topo.adjacency import build_edge_table, edge_face_lists
from engine.topo.edges import EDGE_SOFT
from engine.topo.weld import weld_exact


def _repo_root() -> Path:
    """The directory that holds this engine's pyproject.toml (the repo or worktree root)."""
    here = Path(__file__).resolve()
    return next((p for p in here.parents if (p / "pyproject.toml").is_file()), here.parents[1])


#: decide-pull writes only inside this folder (tests point it at a tmp folder).
DATA_DIR: Path = _repo_root() / "data"

#: The 6 axis-aligned views (of the 26 the guard itself uses) reported as before/after/diff PNGs.
_AXIS_VIEWS = [v for v in VIEWS_26 if sum(1 for c in (round(x) for x in v) if c != 0) == 1]


def _axis_name(view) -> str:
    base = [round(c) for c in view]
    i = next(i for i, c in enumerate(base) if c != 0)
    return f"{'+' if base[i] > 0 else '-'}{'xyz'[i]}"


def _face_normals(positions: np.ndarray, faces: np.ndarray) -> np.ndarray:
    tri = positions[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(n, axis=1)
    out = np.zeros_like(n)
    safe = length > 0.0
    out[safe] = n[safe] / length[safe, None]
    return out


# --------------------------------------------------------------------------------- snapshot load


def _load_snapshot(snapshot_dir: Path) -> tuple[Path, MeshData, dict[str, float], dict[str, MtlMaterial]]:
    """`(obj_path, mesh, flatness, mtl_materials)`. `flatness` is per-material texture std, from
    `engine.io.mtl.parse_mtl` + `texture_flatness`, exactly like `engine.io.snapshot` computes it
    -- but re-derived from the snapshot's own `materials.mtl`/`tex/` rather than requiring a
    `SnapshotResult`, so this works on any directory laid out like one."""
    snapshot_dir = Path(snapshot_dir)
    obj_paths = sorted(snapshot_dir.glob("*.obj"))
    if len(obj_paths) != 1:
        raise ValueError(f"{snapshot_dir}: expected exactly one .obj file, found {len(obj_paths)}")
    obj_path = obj_paths[0]
    mesh = read_obj(obj_path)

    mtl_materials: dict[str, MtlMaterial] = {}
    flatness: dict[str, float] = {}
    mtl_path = snapshot_dir / "materials.mtl"
    if mtl_path.exists():
        mtl_materials = parse_mtl(mtl_path)
        for name, mat in mtl_materials.items():
            if mat.map_kd:
                tex_path = snapshot_dir / mat.map_kd
                if tex_path.exists():
                    flatness[name] = texture_flatness(tex_path)
    return obj_path, mesh, flatness, mtl_materials


def _copy_assets(snapshot_dir: Path, out_dir: Path) -> None:
    mtl_src = snapshot_dir / "materials.mtl"
    if mtl_src.exists():
        shutil.copyfile(mtl_src, out_dir / "materials.mtl")
    tex_src = snapshot_dir / "tex"
    if tex_src.is_dir():
        tex_dst = out_dir / "tex"
        if tex_dst.exists():
            shutil.rmtree(tex_dst)
        shutil.copytree(tex_src, tex_dst)


# --------------------------------------------------------------------------------------- report


def _view_verdict_dict(v: ViewVerdict) -> dict:
    return {"view": list(v.view), "model_px": v.model_px, "holes": v.holes,
            "moved_same_flat": v.moved_same_flat, "moved_other": v.moved_other,
            "material_changed": v.material_changed, "zfight_tie": v.zfight_tie,
            "crack_closed": v.crack_closed, "edge_flicker": v.edge_flicker,
            "fragment_removed": v.fragment_removed,
            "edge_flicker_hole": v.edge_flicker_hole, "edge_flicker_moved": v.edge_flicker_moved,
            "edge_flicker_material": v.edge_flicker_material,
            "edge_flicker_grown": v.edge_flicker_grown, "border_shift": v.border_shift,
            "grown": v.grown, "grown_base": v.grown_base,
            "border_shift_grown": v.border_shift_grown,
            "crack_closed_grown": v.crack_closed_grown, "zfight_tie_grown": v.zfight_tie_grown}


def _guard_report_dict(g: GuardReport) -> dict:
    return {"passed": g.passed, "totals": g.totals, "views": [_view_verdict_dict(v) for v in g.views]}


def _profile_dict(p: FixProfile) -> dict:
    return {"n_dirs": p.n_dirs, "slit_threshold": p.slit_threshold, "accept_slit": p.accept_slit,
            "flat_texture_std": p.flat_texture_std, "guard_size": list(p.guard_size),
            "coplanar_angle": p.coplanar_angle, "soft_angle": p.soft_angle,
            "edge_flicker_cap_final": p.edge_flicker_cap_final,
            "depth_tol_max": p.depth_tol_max, "crack_closed_cap": p.crack_closed_cap,
            "solidify": p.solidify, "top_min_nz": p.top_min_nz,
            "top_sky_fraction": p.top_sky_fraction,
            "skirt_search_radius": p.skirt_search_radius,
            "min_thickness": p.min_thickness, "max_thickness": p.max_thickness,
            "bottom_exists_fraction": p.bottom_exists_fraction,
            "bottom_search_extra": p.bottom_search_extra,
            "cover_max_exposure": p.cover_max_exposure,
            "side_band": p.side_band,
            "cap_guard_max_rounds": p.cap_guard_max_rounds,
            "accept_fragments": p.accept_fragments,
            "fragment_max_area": p.fragment_max_area,
            "fragment_max_extent": p.fragment_max_extent, "sliver_q": p.sliver_q,
            "fragment_removed_cap": p.fragment_removed_cap,
            "qa_size": list(p.qa_size)}


def _build_report(name: str, obj_path: Path, mesh: MeshData, result: FixResult,
                   profile: FixProfile) -> dict:
    """Every number in `FixResult`, both guard reports (per view), the profile, and the input
    file's sha256 -- so report.json fully explains what a run did without re-running it."""
    return {
        "name": name,
        "input_sha256": sha256_file(obj_path),
        "profile": _profile_dict(profile),
        "tris_before": mesh.n_faces,
        # the reference every guard in this run compared against -- the solidified mesh, which
        # is bigger than the input by exactly what `solidify_report` describes
        "tris_reference": result.reference_mesh.n_faces,
        "tris_after": result.mesh.n_faces,
        # every key EXCEPT `runtime_s`: report.json has to be byte-identical between two
        # runs of the same input, and a wall-clock number never is. The CLI prints it.
        "solidify_report": {k: v for k, v in result.solidify_report.items()
                            if k != "runtime_s"},
        "guard_solidify": result.guard_solidify,
        "materials_before": len(mesh.materials),
        "materials_after": len(result.mesh.materials),
        "n_hidden_candidates": result.n_hidden_candidates,
        "n_restored_by_guard": result.n_restored_by_guard,
        "n_removed_hidden": result.n_removed_hidden,
        "n_removed_slit": result.n_removed_slit,
        "n_zero_area_dropped": result.n_zero_area_dropped,
        "n_degenerate_restored": result.n_degenerate_restored,
        "n_flipped": int(result.flipped.sum()),
        "n_thin_sheets": int(result.thin_sheets.sum()),
        # brief 11 item 1: thin faces wound like the connected near-coplanar sheet they belong to
        # (also in `n_flipped`), and the rule's own measurement -- see
        # `engine.fixes.orient.orient_sheets`
        "n_sheet_flipped": int(result.sheet_flipped.sum()),
        "sheet_orientation": result.sheet_report,
        "n_fragment_components": result.n_fragment_components,
        "n_removed_fragments": result.n_removed_fragments,
        "n_removed_slivers": result.n_removed_slivers,
        "n_restored_fragments": result.n_restored_fragments,
        "n_refused_by_rays": result.n_refused_by_rays,
        "n_removed_folds": result.n_removed_folds,
        # every fold (two faces folded onto the same side of their shared edge, the area covered
        # twice), resolved or left, and why. See `engine.detectors.folds`.
        "fold_report": result.fold_report,
        # component counts and the smallest components the size rules did NOT catch -- the
        # evidence for where the thresholds sit against this model. See `engine.detectors`.
        "fragment_report": result.fragment_report,
        "fragment_removals": result.fragment_removals,
        # every candidate's verdict from the rays through it, removed or not: the lines along
        # which it was seen, and how many of them then met a side never exposed. See
        # `engine.guard.piece_rays`.
        "fragment_ray_check": result.fragment_ray_check,
        "n_overlap_pairs_same": result.n_overlap_pairs_same,
        "n_overlap_pairs_diff": result.n_overlap_pairs_diff,
        "n_removed_overlap": result.n_removed_overlap,
        "n_restored_overlap": result.n_restored_overlap,
        # never removed here, only reported: which of two materials a person wants is not a
        # question geometry can answer. Face ids are ORIGINAL ones.
        "overlap_pairs_diff_material": result.overlap_pairs_diff_material,
        "one_sided_holes_before": result.one_sided_holes_before,
        "one_sided_holes_after": result.one_sided_holes_after,
        # SketchUp's blue-purple, in pixels over the 26 guard views: faces seen from their BACK
        # side, for the input, the solidified reference and the final mesh, per view and total
        "backface_px": result.backface_px,
        # brief 15 item 1: what can still flicker in Unity -- pairs of shipped faces drawn twice in
        # one plane, their shared area, their pixels over the 26 views, and a per-plane list. Not
        # the pair list itself (review M5): it would put every remaining pair in every run's
        # report.json and fix_runs.report_json; the 3D error filter's file carries it.
        "double_layers": (None if result.double_layers is None else
                          {k: v for k, v in result.double_layers.items() if k != "pair_list"}),
        "feedback_history": result.feedback_history,
        "guard_after_removal": _guard_report_dict(result.guard_after_removal),
        # the MERGED mesh's guard, kept even when the merge was rolled back and something else
        # shipped -- `null` only when the merge never converged. See `FixResult`.
        "guard_merge_attempt": (None if result.guard_merge_attempt is None
                                 else _guard_report_dict(result.guard_merge_attempt)),
        "guard_final": _guard_report_dict(result.guard_final),
        # which of those counts are failures depends on this: `moved_same_flat` is tolerated by
        # construction when a colour-tolerant slit removal actually removed something.
        "strict_final": result.strict_final,
        "merge_report": dict(result.merge_report),
        "invariants": result.invariants,
        "passed": result.passed,
    }


# --------------------------------------------------------------------------------- guard images


def _failing_view_indices(result: FixResult, profile: FixProfile) -> list[int]:
    """Indices into `VIEWS_26` of every view that ANY of the run's three guards -- the merge
    attempt, the post-removal guard, the final one -- counted a REAL failure in.

    "Real failure" is exactly `engine.guard.compare.compare_views`' own per-view arithmetic, at
    the same strictness (`result.strict_final`) and the same cap that guard ran under: `holes`,
    `material_changed`, `moved_other` and `grown` (surface where BEFORE saw the sky) always;
    `moved_same_flat` only when the run is strict; `edge_flicker` only when it exceeds that
    view's `edge_flicker_cap * model_px`. The removal guard always runs at cap 0.0, where a
    single flicker pixel is a failure; the merge attempt and the final guard run at
    `profile.edge_flicker_cap_final`. `grown` was missing here (review 2a), so a view that failed
    on growth alone had no picture.

    Listing a view on `moved_same_flat` or `edge_flicker` ALONE, as this used to, meant a
    non-strict (`--accept-slit`) run wrote 13-18 triptychs of pixels the guard itself had already
    tolerated, burying the ones worth looking at. `zfight_tie` and `crack_closed` are never
    failures under any setting and were never listed.

    The guards report their views in `VIEWS_26` order, which is the order `_render` built them in."""
    bad: set[int] = set()
    final_cap = profile.edge_flicker_cap_final
    for guard, cap in ((result.guard_merge_attempt, final_cap),
                       (result.guard_after_removal, 0.0),
                       (result.guard_final, final_cap)):
        if guard is None:
            continue
        for index, v in enumerate(guard.views):
            failures = v.holes + v.material_changed + v.moved_other + v.grown
            if result.strict_final:
                failures += v.moved_same_flat
            if v.edge_flicker > cap * v.model_px:
                failures += v.edge_flicker
            if failures:
                bad.add(index)
    return sorted(bad)


def _write_guard_images(mesh: MeshData, result: FixResult, profile: FixProfile,
                        flat_materials: frozenset, topo: Topology, positions_c: np.ndarray,
                        out_dir: Path) -> None:
    """One `guard_<view>.png` triptych per axis view, plus one `guard_fail_<index>.png` for every
    view any guard counted a REAL failure in (`_failing_view_indices`, which applies the run's own
    strictness and each guard's own flicker cap) -- the six axis views are rarely the ones that
    catch a defect, and a failing oblique view had no picture at all before. An axis view that
    also fails gets both names.

    Each triptych is BEFORE (original mesh, shaded), AFTER (final shipped mesh, shaded), DIFF
    (failures red, grown surface blue, tolerated moves amber). A diagnostic image, not the
    authoritative numbers -- it classifies each pixel on its own, with no ring, tie or crack
    re-check (see `engine.guard.compare.classify_pixels`), so a handful of borderline boundary
    pixels the real `guard_final` tolerated still show red here; report.json's own numbers are
    always the real guard reports, not re-derived from these images.

    The pixels of faces the fragment pass removed ARE judged here the way the final guard judges
    them: excused only where the shipped mesh shows the sky or a side the reference already
    showed (`result.exposed_final`), and in a view with more of them than
    `profile.fragment_removed_cap` allows, not excused at all. Drawn without `exposed_after`,
    where only the sky excuses one, the images painted as damage pixels the real guard excused
    (review 2a, experiment E-img: 6 in `guard_-z.png` of a passing run).

    AFTER is always the mesh that SHIPPED. A view listed because `guard_merge_attempt` failed
    therefore shows the rolled-back result, not the discarded merge candidate -- it says which
    view to look at, and report.json's `guard_merge_attempt` says what that view counted."""
    _, remap = weld_exact(mesh.positions, mesh.coord_decimals)
    face_w_before = topo.face_w
    ids_before = np.arange(len(face_w_before), dtype=np.int64)
    normals_before = _face_normals(positions_c, face_w_before)

    face_w_after = remap[result.mesh.face_v]
    ids_after = np.arange(len(face_w_after), dtype=np.int64)
    normals_after = _face_normals(positions_c, face_w_after)

    planes_before = face_planes(positions_c, face_w_before)
    planes_after = face_planes(positions_c, face_w_after)
    depth_tol = guard_depth_tol(topo.quanta, profile)   # the SAME tolerance the guards used

    caster_before = ReusableCaster()
    caster_after = ReusableCaster()

    def write(view, path: Path) -> None:
        before = ortho_first_hit(positions_c, face_w_before, ids_before, view, positions_c,
                                 profile.guard_size, caster_before)
        after = ortho_first_hit(positions_c, face_w_after, ids_after, view, positions_c,
                                profile.guard_size, caster_after)
        # `removed_before` / `exposed_after`: the pixels the fragment pass removed ON PURPOSE are
        # excused here exactly as the real guard excuses them -- or every stray it deleted would
        # paint red -- and, like there, only where AFTER shows what was already outside.
        def classify(removed):
            return classify_pixels(
                before.depth, before.tri, after.depth, after.tri, mesh.face_material,
                result.mesh.face_material, flat_materials, depth_tol, origins=before.origins,
                direction=before.direction, plane_before=planes_before, plane_after=planes_after,
                removed_before=removed, exposed_after=result.exposed_final)

        codes = classify(result.removed_fragments)
        # ...and over the per-view cap they are judged as what they are, as `compare_views`
        # does. Without `removed_before` nothing is stamped and, with no ring or tie here,
        # nothing promoted, so this IS the class each of those pixels would have had.
        excused = int((codes == PX_FRAGMENT_REMOVED).sum())
        if excused and excused > profile.fragment_removed_cap * int((before.tri >= 0).sum()):
            codes = classify(None)
        save_triptych(path, before, after, codes, normals_before=normals_before,
                     normals_after=normals_after)

    for view in _AXIS_VIEWS:
        write(view, out_dir / f"guard_{_axis_name(view)}.png")
    for index in _failing_view_indices(result, profile):
        write(VIEWS_26[index], out_dir / f"guard_fail_{index}.png")


# -------------------------------------------------------------------------------- SketchUp file


def default_skp_dir() -> Path:
    """`<repo root>/OBJ FIXED RESULT`: the folder the owner opens the latest `.skp` from. The
    repo root is the directory holding the `engine` package this module was imported from."""
    return Path(__file__).resolve().parents[1] / "OBJ FIXED RESULT"


def copy_skp_to_owner(path: Path, copy_dir: Path, name: str, passed: bool, out: dict | None = None) -> dict:
    """Copy the fixed SKP to the owner's directory according to the engine's rules:
    - If passed: copy to <copy_dir>/<name>.fixed.skp, and unlink any stale <name>.fixed.FAILED.skp
    - If failed: copy to <copy_dir>/<name>.fixed.FAILED.skp, leaving any existing <name>.fixed.skp
    Records copied_to, previous_kept, copy_error, removed_stale_failed_copy, and stale_failed_copy_error in out."""
    if out is None:
        out = {}
    owner_copy = copy_dir / f"{name}.fixed.skp"
    failed_copy = copy_dir / f"{name}.fixed.FAILED.skp"
    dest_path = owner_copy if passed else failed_copy
    if not passed:
        out["previous_kept"] = str(owner_copy) if owner_copy.exists() else None
    try:
        copy_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest_path)
        out["copied_to"] = str(dest_path)
    except OSError as exc:       # e.g. the owner still has the previous file open
        out["copy_error"] = str(exc)
    # a passing copy supersedes any FAILED one an earlier run left beside it
    if passed and out.get("copied_to") and failed_copy.exists():
        try:
            failed_copy.unlink()
            out["removed_stale_failed_copy"] = str(failed_copy)
        except OSError as exc:
            out["stale_failed_copy_error"] = str(exc)
    return out


def _write_skp(result: FixResult, name: str, out_dir: Path, flat_materials: frozenset,
               profile: FixProfile, enabled: bool, copy_dir: Path | None) -> dict:
    """Write `<out_dir>/<name>.fixed.skp` from the SHIPPED mesh and copy it into `copy_dir`
    (created if needed), returning report.json's `skp` block: `engine.io.skp_writer.write_skp`'s
    own report plus `written`, `copied_to` and `sketchup_check_changed` (whether SketchUp's own
    validity fix would change the file; False is the expected answer). A missing SketchUp, any
    SketchUp API failure, or any other exception (a ctypes access violation surfaces as
    `OSError`) does not fail the run: the block says `written: false` and why -- with the
    exception's type as `error` when it is not a `SketchUpError` -- and no stale `.skp` is left
    in the run dir.

    WHICH COPY. Only a PASSING run's copy replaces `<copy_dir>/<name>.fixed.skp`, the file the
    owner opens, and it also deletes a `<name>.fixed.FAILED.skp` an earlier failed run left
    beside it (`removed_stale_failed_copy`). A FAILED run is copied to
    `<name>.fixed.FAILED.skp` instead and leaves the owner's file as it was: `previous_kept`
    names that file, or is `None` when there was none to keep."""
    if not enabled:
        return {"written": False, "reason": "disabled by --no-skp"}
    path = out_dir / f"{name}.fixed.skp"
    mtl_path = out_dir / "materials.mtl"
    # the hidden edges are decided on the shipped mesh's own topology, with the run's thresholds
    topo = analyse_topology_memo(result.mesh, flat_materials, coplanar_angle=profile.coplanar_angle,
                                 soft_angle=profile.soft_angle)
    try:
        written = write_skp(result.mesh, result.rings, result.face_region_final, topo,
                            parse_mtl(mtl_path) if mtl_path.exists() else {}, path,
                            tex_dir=out_dir / "tex")
        check = check_skp_validity(path)
    except SketchUpError as exc:
        path.unlink(missing_ok=True)
        return {"written": False, "reason": str(exc)}
    except Exception as exc:     # e.g. a ctypes access violation, which surfaces as OSError
        path.unlink(missing_ok=True)
        return {"written": False, "error": type(exc).__name__, "reason": str(exc)}
    out = {"written": True, **written, "sketchup_check_changed": check["changed"],
           "copied_to": None}
    if copy_dir is not None:
        copy_skp_to_owner(path, copy_dir, name, result.passed, out)
    return out


# --------------------------------------------------------------------------------- fix command


def _print_checks(name: str, checks: list[dict], seconds: float) -> None:
    """One line per checked stage: its verdict, the failing samples by reason, what was rolled back."""
    for c in checks:
        if "skipped" in c:
            print(f"{name}: check {c['stage']}: skipped ({c['skipped']})")
            continue
        runs = c["runs"]
        first = runs[0] if runs else None
        reasons = {} if first is None else {k: v for k, v in {**first["textures"], **first["nothing_deleted"]}.items() if v}
        took = sum(r["seconds"] + r["focus_seconds"] + r["cover_seconds"] for r in runs)
        print(f"{name}: check {c['stage']} ({c['engine']}, {c['edits']} edits, {c['sites']} sites): "
              f"{c['first']} -> {c['final']}; failing {0 if first is None else first['failing']} {reasons}; "
              f"unknown {c['unknown']['samples']}; rolled back {[r['site'] for r in c['rolled_back']]}; "
              f"{len(runs)} run(s), {took:.1f} s")
    print(f"{name}: site checks done in {seconds:.1f} s (the whole kernel run)")


def cmd_fix(snapshot_dir: Path, out_root: Path, accept_slit: bool,
            profile: FixProfile | None = None, solidify: bool = True,
            fragments: bool = True, skp: bool = True, skp_dir: Path | None = None,
            kernel: bool = False, validate_sites: bool = False, materials: Path | None = None) -> int:
    """`skp_dir` receives a copy of the `.skp`; `None` (the default here) copies it nowhere --
    `main` passes `default_skp_dir()` unless `--skp-dir` names another folder. `kernel` runs the
    fix through `engine.repair.kernel.repair_unit` and also writes `edit_log.jsonl`;
    `validate_sites` (with `kernel`) checks each stage with the Validator's looks from `materials`
    (materials.json) and the snapshot's own MTL, and logs the checks in `edit_log.jsonl`."""
    obj_path, mesh, flatness, mtl_materials = _load_snapshot(snapshot_dir)
    if validate_sites and not kernel:
        raise ValueError("validate_sites needs kernel")
    if profile is None:
        profile = FixProfile(accept_slit=accept_slit, solidify=solidify,
                             accept_fragments=fragments)
    else:
        profile = replace(profile, accept_slit=accept_slit, solidify=solidify,
                          accept_fragments=fragments)

    kernel_result = None
    if kernel:
        from engine.repair.kernel import repair_unit, write_records
        from engine.repair.types import RepairContext, UnitState
        judge = None
        if validate_sites:
            from engine.site_judge import SiteJudge
            from engine.validate.checks import load_looks
            judge = SiteJudge(load_looks(Path(materials or "data/campus/materials.json"),
                                         [(mtl_materials, Path(snapshot_dir))]))
        started = time.perf_counter()
        kernel_result = repair_unit(UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None),
                                    RepairContext(profile=profile, decider=None, validator=judge),
                                    flatness=flatness, obj_path=obj_path,
                                    validate_sites=validate_sites)
        result = kernel_result.result
        if validate_sites:
            _print_checks(mesh.name, kernel_result.checks, time.perf_counter() - started)
    else:
        result = fix_object(mesh, flatness, profile)

    name = mesh.name
    out_dir = Path(out_root) / name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").unlink(missing_ok=True)
    if kernel_result is not None:
        write_records(out_dir / "edit_log.jsonl", kernel_result.records)

    write_obj(result.mesh, out_dir / f"{name}.fixed.obj")
    write_obj_polygons(result.mesh, result.rings, out_dir / f"{name}.fixed.ngon.obj")
    _copy_assets(snapshot_dir, out_dir)

    # The triptychs show the run's own BEFORE, which is the reference the guards compared
    # against: the solidified mesh when `profile.solidify` is on, the input otherwise.
    flat_materials = flat_material_indices(mesh, flatness, profile.flat_texture_std)
    reference = result.reference_mesh
    topo = analyse_topology_memo(reference, flat_materials)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
    positions_c = topo.positions_w - centre
    _write_guard_images(reference, result, profile, flat_materials, topo, positions_c, out_dir)

    # The picture a person checks before trusting the run: the SHIPPED mesh, with the outline of
    # every polygon the export writes (the merge's rings, or every triangle edge when the merge
    # was rolled back and there are none), hidden lines removed. More than SketchUp will draw:
    # the writer also hides gridlines, coplanar same-material edges and T-junction lines, which
    # this sheet still draws. See `engine.guard.qa_render`. Like the `.skp` below it is an
    # optional export: a failure is recorded in report.json (`qa`) and does not decide `passed`,
    # and the previous run's pictures are deleted first, so none of them is left looking current.
    qa_dir = out_dir / "qa"
    for stale in qa_file_names():
        (qa_dir / stale).unlink(missing_ok=True)
    try:
        qa = write_qa_sheet(result.mesh, polygon_edges(result.mesh, result.rings), qa_dir,
                            size=profile.qa_size)
        qa_report = {"written": True, "images": len(qa)}
    except Exception as exc:
        qa_report = {"written": False, "error": type(exc).__name__, "reason": str(exc),
                     "images": sum((qa_dir / name).exists() for name in qa_file_names())}

    skp_report = _write_skp(result, name, out_dir, flat_materials, profile, skp, skp_dir)

    report = (_build_report(name, obj_path, mesh, result, profile) if kernel_result is None
              else kernel_result.report)
    report["qa"] = qa_report
    report["skp"] = skp_report
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    if result.solidify_report:
        sr = result.solidify_report
        print(f"{name}: solidify {sr['skirts_added']} skirts / {sr['bottoms_added']} bottoms, "
              f"{sr['invented_vertices']} vertices invented, "
              f"{sr['cap_guard_removed']} faces refused by the cap guard, "
              f"{sr['faces_newly_hidden']} faces newly hidden, {sr['runtime_s']}s")
        print(f"  sides rebuilt: {sr['sides_rebuilt']['edges']} edges "
              f"({sr['sides_rebuilt']['length']} in), "
              f"{sr['side_pieces_replaced']} side pieces replaced, "
              f"{sr['interior_faces_covered']} interior faces covered, "
              f"{sr['walls_refused']['faces']} wall faces refused {sr['walls_refused']['reasons']}")
        # review of brief 10, M6 and I1: the readings a person should be able to check -- a block
        # standing on a slab reads exactly like an overhang over a notch whose sides were lost
        rule6 = sr.get("rule6_volumes", {})
        seen = sr.get("seen_through_shell", {})
        print(f"  tops read as undersides: {sr.get('undersides_not_tops', 0)}, blocks standing "
              f"on slabs: {sr.get('blocks_standing_on_slabs', 0)}, walls relooked: "
              f"{sr.get('walls_relooked', 0)}; rule 6 sees through "
              f"{len(rule6.get('confirmed', []))} confirmed volumes (not: "
              f"{ {k: len(v) for k, v in rule6.get('not_confirmed', {}).items()} }), "
              f"{seen.get('faces', 0)} faces seen only through a shell "
              f"({seen.get('kept_from_hidden_pass', 0)} kept from the hidden pass)")
    print(f"{name}: {mesh.n_faces} -> {result.mesh.n_faces} tris, passed={result.passed}, "
          f"border_shift={result.guard_final.totals['border_shift']}")
    back = result.backface_px
    print(f"  backface_px final={back['final']['total']} (input={back['input']['total']}, "
          f"reference={back['reference']['total']}) -- pixels showing a face's back side")
    double = result.double_layers or {"count": 0, "area": 0.0, "px": 0, "planes": []}
    print(f"  double layers: {double['count']} pairs, {double['area']} sq in, {double['px']} px "
          f"over the 26 views, in {len(double['planes'])} planes -- what can still flicker")
    sheet = result.sheet_report
    print(f"  sheets: {sheet['sheets_made_consistent']} made consistent "
          f"({sheet['faces_flipped']} thin faces re-wound), {sheet['sheets_refused']} refused, "
          f"{sheet['faces_lying_on_another']} faces lying on another left as they are; "
          f"back_px {sheet['back_px']['before']} -> {sheet['back_px']['after']} before the merge")
    if qa_report["written"]:
        print(f"  wrote {out_dir} (and {qa_report['images']} QA images under qa/)")
    else:
        print(f"  wrote {out_dir}; QA sheet NOT written: {qa_report['error']}: "
              f"{qa_report['reason']}")
    if skp_report["written"]:
        hidden = sum(skp_report[k] for k in ("soft_edges", "gridline_edges_softened",
                                             "coplanar_edges_softened", "tjunction_lines_softened"))
        # a failed run's copy is the FAILED one, and the owner's file is still the previous
        # run's: say so on the line the owner reads, not only in report.json
        kept = ""
        if "previous_kept" in skp_report:
            kept = (f"; the run FAILED, so {skp_report['previous_kept']} was kept"
                    if skp_report["previous_kept"] else
                    f"; the run FAILED, and there is no previous {name}.fixed.skp")
        print(f"  wrote {skp_report['path']}: {skp_report['faces']} faces, {hidden} edges hidden, "
              f"{skp_report['visible_lines_inside_surfaces']} lines left inside surfaces, "
              f"copied to {skp_report['copied_to'] or skp_report.get('copy_error', 'nowhere')}"
              f"{kept}")
    else:
        print(f"  no .skp written: {skp_report['reason']}")
    return 0 if result.passed else 2


# --------------------------------------------------------------------------- preview-data command


def _round_flat(a, nd=3) -> list:
    return np.round(np.asarray(a, dtype=float).reshape(-1), nd).tolist()


def _before_edges(topo: Topology, positions_c: np.ndarray, removed: np.ndarray):
    """`(grid, tri_before, outline_before)` segment lists for the ORIGINAL mesh's visible (ok,
    surviving) faces: `grid` is a boundary between a REMOVED (hidden/slit) face and two coplanar
    surviving faces of the same plane region; `tri_before` a boundary between two coplanar
    surviving faces neither of which is removed (an ordinary gridline, nothing hidden behind it);
    `outline_before` everything else (a real shape edge, or the model's own silhouette)."""
    ok = topo.ok
    ok_ids = np.nonzero(ok)[0]
    groups = edge_face_lists(topo.table)
    plabel = topo.face_region

    grid, tri_before, outline_before = [], [], []
    for edge, faces in zip(topo.table.edges, groups):
        visible = [int(f) for f in faces if not removed[f]]
        if not visible:
            continue
        seg = [positions_c[int(edge[0])].tolist(), positions_c[int(edge[1])].tolist()]
        labels = {int(plabel[f]) for f in visible}
        if len(visible) >= 2 and len(labels) == 1 and labels != {-1}:
            (grid if any(removed[f] for f in faces) else tri_before).append(seg)
        else:
            outline_before.append(seg)
    return grid, tri_before, outline_before


def _after_edges(result: FixResult, positions_o: np.ndarray):
    """`(outline_after, tri_after)` segment lists for the FIXED mesh: an edge shared by exactly
    two triangles of the SAME merged region (`face_region_final[a] == face_region_final[b] >= 0`)
    is an UNAVOIDABLE DIAGONAL -- it exists only because OBJ needs triangles, not because it is a
    real shape edge; everything else (a mesh boundary, a border between two different regions, or
    a border with a copied-through face) is a real OUTLINE edge.

    This used to test `source_faces[a] is source_faces[b]`, the array identity
    `engine.fixes.merge` sets up for every triangle of one region. `fix_object` rebuilds
    `source_faces` with `.astype`, which copies, so that identity never survived into a
    `FixResult` and `tri_after` was ALWAYS empty: every diagonal was drawn as a real edge.
    A region id is data, not an object address, so it survives being rebuilt."""
    n = result.mesh.n_faces
    table = build_edge_table(result.mesh.face_v, np.ones(n, dtype=bool))
    groups = edge_face_lists(table)
    region = result.face_region_final

    outline, diagonal = [], []
    for edge, faces in zip(table.edges, groups):
        seg = [positions_o[int(edge[0])].tolist(), positions_o[int(edge[1])].tolist()]
        same_region = (len(faces) == 2 and region[int(faces[0])] >= 0
                       and region[int(faces[0])] == region[int(faces[1])])
        (diagonal if same_region else outline).append(seg)
    return outline, diagonal


def _soft_edges(topo: Topology, positions_c: np.ndarray):
    """Every EDGE_SOFT edge of `topo` as a segment: a same-material crease between two regions
    too shallow to be a real shape edge and too steep to merge without moving a vertex. The
    preview draws these in their own colour so a person can see what the merge left behind and
    why -- see `engine.topo.edges.classify_edges`."""
    return [[positions_c[int(a)].tolist(), positions_c[int(b)].tolist()]
            for (a, b), cls in zip(topo.table.edges, topo.edge_class) if cls == EDGE_SOFT]


def _material_colors(snapshot_dir: Path, materials: list[str], mtl_materials: dict[str, MtlMaterial]) -> list[dict]:
    out = []
    for name in materials:
        rgb = [0.8, 0.8, 0.8]
        mat = mtl_materials.get(name)
        if mat is not None and mat.map_kd:
            tex_path = snapshot_dir / mat.map_kd
            if tex_path.exists():
                mean = np.asarray(Image.open(tex_path).convert("RGB"), dtype=float).reshape(-1, 3).mean(axis=0)
                rgb = [round(float(c) / 255.0, 4) for c in mean]
        out.append({"name": name, "color": rgb})
    return out


def cmd_preview_data(snapshot_dir: Path, out_dir: Path, profile: FixProfile | None = None,
                     solidify: bool = True) -> int:
    obj_path, mesh, flatness, mtl_materials = _load_snapshot(snapshot_dir)
    profile = replace(profile or FixProfile(), solidify=solidify)
    result = fix_object(mesh, flatness, profile)

    # BEFORE IS THE ORIGINAL EXPORT, which is what a pane labelled "as exported" has to show.
    # It was switched to the run's REFERENCE mesh when solidify landed -- defensible, since every
    # per-face array in `FixResult` is indexed against that mesh -- but it put skirts and bottoms
    # the export never had into the "before" picture, which is the one thing that pane is for.
    # What solidify added is written separately, as `reference`, and the page draws it as added.
    #
    # The reference's first rows are the input's faces MINUS the side pieces solidify replaced
    # (SR2), in their original order, and every invented face follows. So the BEFORE pane is
    # drawn from the INPUT mesh itself, and each input face finds its reference row through the
    # replaced mask; a replaced piece counts as removed. Both meshes are framed on the SAME
    # centre so the two panes stay registered.
    input_mesh, mesh = mesh, result.reference_mesh
    flat_materials = flat_material_indices(mesh, flatness, profile.flat_texture_std)
    topo = analyse_topology_memo(mesh, flat_materials)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
    positions_c_w = topo.positions_w - centre       # welded frame (topo.face_w indexes it)
    positions_c_o = mesh.positions - centre          # original frame: AFTER (result.mesh.face_v indexes it)
    topo_input = analyse_topology_memo(input_mesh, flat_materials)

    replaced = np.asarray(result.replaced_input, dtype=bool)
    n_kept = int((~replaced).sum())                  # reference rows below this are input faces
    reference_row = np.where(replaced, -1, np.cumsum(~replaced) - 1)
    removed = result.removed_hidden | result.removed_slit
    removed_input = replaced | np.where(reference_row >= 0,
                                        removed[np.maximum(reference_row, 0)], False)
    ok_ids = np.nonzero(topo.ok)[0]
    before_ids = np.nonzero(topo_input.ok)[0]        # the export's own faces, and only those
    before_tri = topo_input.positions_w[topo_input.face_w[before_ids]] - centre
    before_mat = input_mesh.face_material[before_ids]
    before_hidden = removed_input[before_ids].astype(int)

    added_ids = ok_ids[ok_ids >= n_kept]             # everything solidify invented and kept
    added_tri = positions_c_w[topo.face_w[added_ids]]
    added_mat = mesh.face_material[added_ids]

    after_tri = positions_c_o[result.mesh.face_v]
    after_mat = result.mesh.face_material

    # ...and the BEFORE pane's edges come from the INPUT mesh's own topology, or an outline edge
    # of a skirt the export never had would float there with no surface under it. Welded ids
    # differ between the two topologies, but `_before_edges` emits COORDINATES, and both are
    # recentred on the same `centre`, so the segments land in the same frame as everything else.
    grid, tri_before, outline_before = _before_edges(
        topo_input, topo_input.positions_w - centre, removed_input)
    outline_after, tri_after = _after_edges(result, positions_c_o)

    # The SHIPPED mesh's own topology: `result.mesh.positions` IS `mesh.positions` (nothing in
    # the pipeline ever touches it), so it welds to the same frame `positions_c_w` is in.
    topo_after = analyse_topology_memo(result.mesh, flat_materials,
                                       coplanar_angle=profile.coplanar_angle,
                                       soft_angle=profile.soft_angle)
    soft_after = _soft_edges(topo_after, positions_c_w)

    guard_final = result.guard_final.totals
    # `edge_flicker` is NOT damage: it is the class `compare_views` promotes a pixel INTO when
    # the two pictures differ only by a boundary that moved less than the tolerance, and the
    # final guard tolerates it up to `edge_flicker_cap_final`. Adding it to a number the page
    # then labelled "damaged px" made the page report the opposite of what the guard decided.
    # `grown` IS damage -- surface where the original showed sky fails like a hole -- and left
    # out, a run failing on growth alone read "FAILED, 0 damaged px" (review 2a).
    guard_damaged_px = (guard_final["holes"] + guard_final["material_changed"]
                        + guard_final["moved_other"] + guard_final["moved_same_flat"]
                        + guard_final["grown"])
    guard_flicker_px = guard_final["edge_flicker"]

    data = {
        "name": mesh.name,
        "stats": {
            # the REFERENCE mesh's count -- the export plus whatever solidify added and the cap
            # guard kept. `tris_input` is the BEFORE pane's own count.
            "tris_total": int(mesh.n_faces),
            "tris_input": int(input_mesh.n_faces),
            "tris_added_by_solidify": int(len(added_ids)),
            "skirts_added": int(result.solidify_report.get("skirts_added", 0)),
            "bottoms_added": int(result.solidify_report.get("bottoms_added", 0)),
            "invented_vertices": int(result.solidify_report.get("invented_vertices", 0)),
            "faces_newly_hidden": int(result.solidify_report.get("faces_newly_hidden", 0)),
            # SR2: pieces of broken sides solidify replaced with a wall or a bottom -- drawn in
            # the BEFORE pane as removed, since the export had them and the result does not
            "side_pieces_replaced": int(replaced.sum()),
            "zero_area": int(result.n_zero_area_dropped),
            "before_tris": int(topo.ok.sum()),
            "hidden": int(removed.sum()),
            # ...and the part of it the BEFORE pane can show: faces of the EXPORT only. `hidden`
            # also counts faces solidify invented and the hidden pass then removed again (96 on
            # file A), which the original-export pane never draws.
            "hidden_in_export": int(before_hidden.sum()),
            "after_hidden_removed": int(topo.ok.sum() - removed.sum()),
            "after_merged": int(result.mesh.n_faces),
            "regions": int(result.merge_report.get("regions_merged", 0)),
            "guard_views": len(VIEWS_26),
            "guard_model_px": int(guard_final["model_px"]),
            "guard_damaged_px": int(guard_damaged_px),
            "guard_flicker_px": int(guard_flicker_px),
            "guard_border_shift_px": int(guard_final["border_shift"]),
            # the page names its own thresholds from these rather than hard-coding "1-5 deg"
            "coplanar_angle": float(profile.coplanar_angle),
            "soft_angle": float(profile.soft_angle),
            "guard_tol_in": guard_depth_tol(topo.quanta, profile),
            "gridline_edges": len(grid),
            "flipped": int(result.flipped.sum()),
            "thin_sheets": int(result.thin_sheets.sum()),
            "n_fragment_components": int(result.n_fragment_components),
            "n_removed_fragments": int(result.n_removed_fragments),
            "n_removed_slivers": int(result.n_removed_slivers),
            "n_restored_fragments": int(result.n_restored_fragments),
            "n_refused_by_rays": int(result.n_refused_by_rays),
            "n_removed_folds": int(result.n_removed_folds),
            "n_overlap_pairs_same": int(result.n_overlap_pairs_same),
            "n_overlap_pairs_diff": int(result.n_overlap_pairs_diff),
            "n_removed_overlap": int(result.n_removed_overlap),
            "n_restored_overlap": int(result.n_restored_overlap),
            "one_sided_holes_before": result.one_sided_holes_before,
            "one_sided_holes_after": result.one_sided_holes_after,
            "outline_edges_after": len(outline_after),
            "unavoidable_diagonals_after": len(tri_after),
            "soft_edges": len(soft_after),
            "coplanar_region_borders": coplanar_region_borders(topo_after),
            "guard_passed": bool(result.guard_final.passed),
            # the CAP GUARD's own verdict, re-verified against the mesh solidify handed back.
            # It is an invariant of the run (see `engine.fixes.pipeline`), so the pane that shows
            # what solidify added has to say whether that step was accepted.
            "cap_guard_passed": bool(result.invariants.get("cap_guard_passed", True)),
            # Never failures under any setting, and the page says so: a tie is an overlap that
            # was already in the export, a closed crack is an improvement. See `classify_pixels`.
            "zfight_tie": int(guard_final["zfight_tie"]),
            "crack_closed": int(guard_final["crack_closed"]),
            # pixels the fragment pass was authorised to change, excused by name. Never damage.
            "fragment_removed_px": int(guard_final["fragment_removed"]),
            # True when the merged mesh failed its guard (or never converged) and the shipped
            # mesh is the removal-only fallback -- without which "N flat regions" would be read
            # as a description of what was delivered when it is not.
            "merge_rolled_back": bool(result.merge_report.get("rolled_back", False)),
        },
        "materials": _material_colors(snapshot_dir, mesh.materials, mtl_materials),
        # the export exactly as it arrived
        "before": {"pos": _round_flat(before_tri), "mat": before_mat.tolist(),
                   "hidden": before_hidden.tolist()},
        # ...and, separately, only what `solidify` added to it and the cap guard kept, so the
        # page can draw it in its own colour and call it what it is. Empty under --no-solidify.
        "reference": {"pos": _round_flat(added_tri), "mat": added_mat.tolist()},
        "after": {"pos": _round_flat(after_tri), "mat": after_mat.tolist()},
        "edges": {"grid": _round_flat(grid), "tri_before": _round_flat(tri_before),
                  "outline_before": _round_flat(outline_before), "outline_after": _round_flat(outline_after),
                  "tri_after": _round_flat(tri_after), "soft_after": _round_flat(soft_after)},
    }

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{mesh.name}.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    index_path = out_dir / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    index = [e for e in index if e.get("name") != mesh.name]
    index.append({"file": f"{mesh.name}.json", "name": mesh.name})
    index_path.write_text(json.dumps(index), encoding="utf-8")

    print(f"{mesh.name}: wrote {out_dir / (mesh.name + '.json')}")
    for k, v in data["stats"].items():
        print(f"  {k}: {v}")
    return 0


def cmd_errors(snapshot_dir: Path, out_file: Path, profile: FixProfile | None = None) -> dict:
    """What is wrong with the snapshot's model, face by face (the 3D error filter's file);
    the model is not changed."""
    from engine.detectors.errors import find_errors
    _obj_path, mesh, _flatness, _mtl = _load_snapshot(Path(snapshot_dir))
    result = find_errors(mesh, profile or FixProfile())
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(result), encoding="utf-8")
    print(f"{mesh.name}: " + ", ".join(f"{k} {v}" for k, v in result["counts"].items()))
    return result


# -------------------------------------------------------------------------------------- validate


def fills_from_edit_log(path: Path, after, before_faces: int | None = None) -> list:
    """The kept flat fills of an `edit_log.jsonl` as the Validator's `FillSite`s (ruling P2-E8b-R11): every line
    marked `flat_fill`, not rolled back, with its `after_faces` and `loop_points`. Each fill's faces must exist in
    `after` and have every corner on one of the loop's points (within 1e-3 in, the OBJ's printing); otherwise the log
    does not describe this AFTER and a `ValueError` says so.

    `before_faces` (the BEFORE's face count; P2-E8c item 4c): a fill's faces are NEW faces. The AFTER lists the BEFORE's
    surviving faces first and the added ones after them, so a face id below the survivors' count names an existing
    BEFORE face and the log is refused. The survivors are `before_faces` less the faces the log's kept cuts and
    removes took away (a kept E8a cut makes the first new id lower than the BEFORE's count). Without it the check is
    not made."""
    from engine.validate.checks import FillSite

    if not path.is_file():
        raise FileNotFoundError(f"--edit-log {path} is not a file")
    fills = []
    lines = [json.loads(text) for text in path.read_text(encoding="utf-8").splitlines()]
    first_new = None
    if before_faces is not None:
        took = sum(len(line.get("faces") or []) for line in lines
                   if "check" not in line and not line.get("rolled_back") and line.get("kind") in ("cut", "remove"))
        first_new = int(before_faces) - took
    for number, line in enumerate(lines, start=1):
        if "check" in line or not line.get("flat_fill") or line.get("rolled_back"):
            continue
        faces, loop = line.get("after_faces"), line.get("loop_points")
        if not faces or not loop:
            raise ValueError(f"edit log {path} line {number}: a kept flat fill without after_faces and loop_points")
        faces = np.asarray(faces, np.int64)
        loop = np.asarray(loop, np.float64).reshape(-1, 3)
        if faces.min() < 0 or faces.max() >= after.n_faces:
            raise ValueError(f"edit log {path} line {number}: fill faces {faces.tolist()} are not faces of the AFTER "
                             f"({after.n_faces} faces)")
        if first_new is not None and faces.min() < first_new:
            raise ValueError(f"edit log {path} line {number}: fill face {int(faces.min())} names an existing BEFORE face "
                             f"(a new face's id is at least {first_new}: the BEFORE's {before_faces} faces less the "
                             f"{int(before_faces) - first_new} a kept cut took away)")
        corners = after.positions[after.face_v[faces]].reshape(-1, 3)
        off = np.linalg.norm(corners[:, None, :] - loop[None, :, :], axis=2).min(axis=1)
        if (off > 1e-3).any():
            raise ValueError(f"edit log {path} line {number}: the AFTER's faces {faces.tolist()} are not the fill "
                             f"(a corner lies {off.max():.4f} in off its loop's points)")
        fills.append(FillSite(faces=faces, loop=loop))
    return fills


def cmd_validate(before_dir: Path, after_path: Path, materials: Path, out_dir: Path,
                 targets: Path | None = None, settings=None, edit_log: Path | None = None) -> int:
    """Judge `after_path` (an OBJ) against the snapshot `before_dir` by the owner's three checks and write
    `<out_dir>/validation.json` and `<out_dir>/evidence/*.png`. Returns 0 on PASS, 2 on FAIL or on an
    input that is missing or unreadable (a message on stderr, and no verdict written).

    `edit_log` (ruling P2-E8b-R11): the `edit_log.jsonl` of the repair that made `after_path`. Its kept flat fills
    (`fills_from_edit_log`) go to the Validator's `fill_site` class, so a shipped fill is judged as a fill. A
    log whose fill faces are not, in AFTER, faces on the fill's own loop is refused (exit 2)."""
    # The process counters (peak memory) come from winprobe: only the SketchUp binding modules and winprobe may
    # import ctypes (test_skp_writer.test_ctypes_is_imported_only_by_the_sketchup_binding_modules).
    from engine.campus.winprobe import peak_memory_mb
    from engine.validate.checks import Settings, default_targets_path, load_looks, load_targets, validate
    from engine.validate.evidence import write_evidence

    started = time.perf_counter()
    settings = settings or Settings()
    before_dir, after_path, materials, out_dir = Path(before_dir), Path(after_path), Path(materials), Path(out_dir)
    try:
        refuse_protected(out_dir)
        if not after_path.is_file():
            raise FileNotFoundError(f"--after {after_path} is not a file")
        if not materials.is_file():
            raise FileNotFoundError(f"--materials {materials} is not a file")
        before_obj, before, _flatness, before_mtl = _load_snapshot(before_dir)
        after = read_obj(after_path)
        sources = [(before_mtl, before_dir)]
        after_mtl = after_path.parent / after.mtllib if after.mtllib else None
        if after_mtl is not None and after_mtl.is_file():
            sources.append((parse_mtl(after_mtl), after_path.parent))
        looks = load_looks(materials, sources)
        signed = load_targets(targets)
        fills = None if edit_log is None else fills_from_edit_log(Path(edit_log), after, before.n_faces)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    shown = {"tenth": -1}

    def progress(done: int, total: int) -> None:
        tenth = int(10 * done / max(total, 1))
        if tenth != shown["tenth"]:
            shown["tenth"] = tenth
            print(f"  {done}/{total} samples cast", file=sys.stderr, flush=True)

    try:
        result = validate(before, after, looks, targets=signed, settings=settings, progress=progress, fills=fills)
    except ValueError as exc:                              # e.g. a mesh too far from the origin to cast rays at
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    write_evidence(result, out_dir)
    report = result.report
    peak, commit = peak_memory_mb()
    targets_used = Path(targets) if targets is not None else default_targets_path()     # what load_targets read
    report["inputs"] = {"before": str(before_obj), "after": str(after_path), "materials": str(materials),
                        "targets": str(targets_used) if targets_used.is_file() else None,
                        "before_sha256": sha256_file(before_obj), "after_sha256": sha256_file(after_path)}
    if edit_log is not None:
        report["inputs"]["edit_log"] = str(edit_log)
    report["peak_working_set_mb"], report["peak_commit_mb"] = peak, commit
    report["wall_s"] = round(time.perf_counter() - started, 2)
    (out_dir / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    checks = report["checks"]
    t, p, g = checks["textures"], checks["problems"], checks["nothing_deleted"]
    print(f"validate {before.name}: verdict {report['verdict']}")
    print(f"  textures        {t['status']:<11} {t['samples']} samples seen in BEFORE, {t['samples_failed']} failed {t['reasons']}")
    print(f"  problems        {p['status']:<11} " + ("targets signed" if p["signed"] else "targets unsigned: counts only")
          + "; before -> after: " + ", ".join(f"{k} {v['before']}->{v['after']}" for k, v in p["kinds"].items()))
    print(f"  nothing_deleted {g['status']:<11} {g['deleted']} deleted, {g['replaced']} replaced, {g['covered']} covered, "
          f"{g['overlaid']} overlaid "
          f"({g['samples_extra']} samples only the {report['viewpoints']['extra_directions']} extra directions saw)")
    floor = g.get("floor")
    if floor is not None:
        worst = floor["measured"][0] if floor["measured"] else None
        print(f"  floor           {floor['status']:<11} {floor['faces_failed']} of {floor['faces_measured']} measured faces "
              f"show more than {floor['floor_px']} px at {floor['in_per_px']} in/px (lattice {floor['lattice']['points']} "
              f"points on {floor['lattice']['faces']} faces)"
              + (f"; worst face {worst['face']} ({worst['kind']}) {'>=' if worst['at_least'] else ''}{worst['pixels']} px "
                 f"from {worst['viewpoint']['kind']} {worst['viewpoint']['index']}" if worst else ""))
    print(f"  {report['sites_total']} sites, {sum(1 for s in report['sites'] if s['evidence'])} with evidence crops; "
          f"wrote {out_dir / 'validation.json'}")
    for note in report["notes"]:
        print(f"  note: {note}")
    print(f"  time {report['wall_s']} s, peak working set {peak} MB, peak commit {commit} MB")
    return 0 if result.passed else 2


# ------------------------------------------------------------------------------------ repair-unit command

#: The repair engines `repair-unit` takes (P2): E8, which is E8a (strict solidify) then E8b (the narrow flat fill,
#: ruling E8b-R7), either one alone, and E3 (hidden faces, interior-aware; job P2-E3).
REPAIR_ENGINES = ("E8", "E8a", "E8b", "E3", "E1")
#: The kernel stages each engine name runs. They run in the order the names are given (ruling E3-R6: `E8a,E3`),
#: each stage once, at its first place; `E8` is E8a then E8b.
REPAIR_STAGES = {"E8": ("E8a", "E8b"), "E8a": ("E8a",), "E8b": ("E8b",), "E3": ("E3",), "E1": ("E1",)}
#: `repair-unit`'s exit code when an engine stage was rolled back whole or ended FAIL (its outputs are still written).
REPAIR_STAGE_FAILED = 3
#: `repair-unit`'s exit codes, as its help gives them.
REPAIR_EXIT_CODES = ("exit 0: every E8 stage passed (its last check PASS, or every piece rolled back on its own charge), "
                     "and so did every E3 stage; "
                     "1: the unit's BEFORE differs from the campus map, nothing repaired; "
                     "2: a refused input (unknown engine, protected folder, missing file); "
                     "3: the stage was rolled back whole or ended FAIL - every file is still written and the "
                     "mesh shipped is the BEFORE, the safe one")


def repair_stages(engines) -> list[str]:
    """The kernel stages `repair-unit` runs for the engine names `engines` (words, each possibly a comma list such as
    `E8a,E3`), in the order given, each stage once at its first place (`E8` is E8a then E8b; ruling E3-R6).
    ValueError for an unknown name, or for none."""
    names = [n.strip() for e in engines for n in str(e).split(",") if n.strip()]
    unknown = [n for n in names if n not in REPAIR_ENGINES]
    if unknown or not names:
        raise ValueError(f"repair-unit runs only {REPAIR_ENGINES}; not {unknown or 'no engine'}")
    return list(dict.fromkeys(s for n in names for s in REPAIR_STAGES[n]))


#: The folders of crops `repair-unit` writes in `--out`.
_STALE_DIRS = ("fills", "needs_modelling", "visible_debris")


def _remove_stale_outputs(out_dir: Path, name: str | None, *, everything: bool = False) -> None:
    """Remove what an earlier `repair-unit` left in `out_dir`, so it cannot be mistaken for this run's. Always the
    needs-modelling file and its crops (this run rewrites them); with `everything` (the run stops at exit 1, before
    it writes anything) also `report.json`, `edit_log.jsonl`, `<name>.fixed.obj` and the `fills/` crops. In the crop
    folders only the `*.png` files go, and the folder only when it is then empty. Files this tool never writes stay."""
    out_dir = Path(out_dir)
    names = ["needs_modelling.json"] + (["report.json", "edit_log.jsonl", f"{name}.fixed.obj"] if everything else [])
    for file in names:
        (out_dir / file).unlink(missing_ok=True)
    for folder in (_STALE_DIRS if everything else ("needs_modelling",)):
        # only this tool's own crops (*.png); the folder goes only when that leaves it empty
        for crop in (out_dir / folder).glob("*.png"):
            crop.unlink(missing_ok=True)
        try:
            (out_dir / folder).rmdir()
        except OSError:
            pass                      # not there, or it holds something that is not ours


def _after_rollback(check: dict) -> dict:
    """What the stage's LAST check says of the mesh it ships. When it kept sites, the last run judged exactly those
    (the kernel rolls back the rest, and a stage whose last run is not PASS is rolled back whole); when it kept
    none, the stage ships its input, which covers nothing by construction."""
    runs = check.get("runs") or []
    kept_any = check.get("sites", 0) > len(check.get("rolled_back", []))
    if not runs or not kept_any:
        return {"verdict": check.get("final", "PASS"), "covered": 0, "textures_covered": 0, "deleted": 0, "failing": 0,
                "judged_by": "nothing kept: the stage ships its input"}
    last = runs[-1]
    return {"verdict": check["final"], "covered": int(last["nothing_deleted"]["covered"]),
            "textures_covered": int(last["textures"].get("covered", 0)),
            "deleted": int(last["nothing_deleted"]["deleted"]), "failing": int(last["failing"]),
            "judged_by": f"the {last['kind']} run on the {last['sites']} kept site(s)"}


def _e3_report(engine, edits: list, result, check: dict | None) -> dict:
    """report.json's `e3` (job P2-E3): the engine's own numbers (`E3Hidden.report`: legacy candidates, what each rule
    took out, candidates, groups, sites, probes, disagreements), then `sites` (planned, kept, rolled back, by the
    Validator's reason; a site counts once under each reason its charged samples had), `faces_removed` (by the kept
    sites), `deleted_after_rollback` (the Validator's deleted count in the stage's last check, on the kept sites:
    must be 0), `after_rollback`, and `site_rows`, one per site (its group, faces, area, rules, centroid, box, kept,
    reasons, samples charged)."""
    kept = {id(e) for e in result.kept}
    rolled = {row["site"]: row for row in (check or {}).get("rolled_back", [])}
    rows, by_reason, samples_by_reason = [], collections.Counter(), collections.Counter()
    for e in edits:
        ev, row = e.evidence, rolled.get(e.site)
        reasons = {} if row is None else dict(row["reasons"])
        if row is not None and row.get("stage_rolled_back"):
            reasons = {"stage_rolled_back": 0}
        if row is not None:
            by_reason.update(reasons.keys())
            samples_by_reason.update(reasons)
        rows.append({"site": int(e.site), "group": ev.get("group"), "cell": ev.get("cell"), "faces": len(e.faces),
                     "group_faces": ev.get("group_faces"), "area": ev.get("area"),
                     "rules": dict(collections.Counter(ev.get("rules", []))), "centroid": ev.get("centroid"),
                     "bbox": ev.get("bbox"), "kept": id(e) in kept, "reasons": reasons,
                     "charged": 0 if row is None else int(row["charged"])})
    after = _after_rollback(check) if check is not None else None
    return {**(engine.report or {}),
            "sites": {"planned": len(rows), "kept": sum(r["kept"] for r in rows),
                      "rolled_back": sum(not r["kept"] for r in rows),
                      "rolled_back_by_reason": dict(sorted(by_reason.items())),
                      "rolled_back_samples_by_reason": {k: int(v) for k, v in sorted(samples_by_reason.items()) if v}},
            "faces_removed": int(sum(r["faces"] for r in rows if r["kept"])),
            "deleted_after_rollback": 0 if after is None else int(after["deleted"]),
            "after_rollback": after,
            "site_rows": rows}


def _e1_report(engine, edits: list, result, check: dict | None) -> dict:
    """report.json's `e1` (job P2-E1): engine's numbers (candidates by kind, visible_debris), sites (planned, kept,
    rolled_back), kept count, rolled_back list with reasons."""
    kept = {id(e) for e in result.kept}
    rolled = {row["site"]: row for row in (check or {}).get("rolled_back", [])}
    rows, by_reason = [], collections.Counter()
    for e in edits:
        ev, row = e.evidence, rolled.get(e.site)
        reasons = {} if row is None else dict(row["reasons"])
        if row is not None and row.get("stage_rolled_back"):
            reasons = {"stage_rolled_back": 0}
        if row is not None:
            by_reason.update(reasons.keys())
        rows.append({"site": int(e.site), "faces": len(e.faces), "rule": ev.get("rule"),
                     "area": ev.get("area"), "centroid": ev.get("centroid"),
                     "bbox": ev.get("bbox"), "kept": id(e) in kept, "reasons": reasons,
                     "charged": 0 if row is None else int(row["charged"])})
    after = _after_rollback(check) if check is not None else None
    rep = engine.report or {}
    kept_count = sum(r["kept"] for r in rows)
    rolled_count = sum(not r["kept"] for r in rows)
    return {
        "candidates": rep.get("candidates", {}),
        "sites": {"planned": len(rows), "kept": kept_count, "rolled_back": rolled_count,
                  "rolled_back_by_reason": dict(sorted(by_reason.items()))},
        "kept": kept_count,
        "rolled_back": [row for row in rolled.values()],
        "visible_debris": rep.get("visible_debris", []),
        "visible_debris_count": rep.get("visible_debris_count", 0),
        "after_rollback": after,
        "site_rows": rows,
    }


def _repair_report(result, check_by_stage: dict, before=None) -> tuple[list[dict], dict]:
    """`(pieces, sites)` of report.json: one row per site E8 planned, and the counts kept and rolled back, by
    reason (a site counts once under each reason the Validator gave for the samples charged to it). With `before`
    (the stage's input), a piece that was NOT kept also carries the outline of the faces it would have built
    (`border`, `border_ordered`, `border_rings`, `area_in2`, `normal`: `needs_modelling.piece_border`), which is
    where the unit still needs modelling (job P2-E8c)."""
    rolled = {}
    for check in check_by_stage.values():
        for row in check.get("rolled_back", []):
            rolled[row["site"]] = row
    kept_sites = {e.site for e in result.kept}
    pieces, by_reason, samples_by_reason = [], collections.Counter(), collections.Counter()
    for site in dict.fromkeys(e.site for e in result.edits):
        mine = [e for e in result.edits if e.site == site]
        build = next((e for e in mine if e.kind in ("add", "cut")), mine[0])
        ev = build.evidence
        row = rolled.get(site)
        reasons = {} if row is None else dict(row["reasons"])
        if row is not None and row.get("stage_rolled_back"):
            reasons = {"stage_rolled_back": 0}
        pieces.append({"site": int(site), "piece": ev.get("piece"), "region": ev.get("region"),
                       "kinds": [e.kind for e in mine], "faces": int(sum(len(e.new_faces) for e in mine
                                                                         if e.new_faces is not None)),
                       "new_points": int(sum(0 if e.new_points is None else len(e.new_points) for e in mine)),
                       "replaced": int(sum(len(e.faces) for e in mine)), "length": ev.get("length"),
                       "thickness": ev.get("thickness"), "kept": site in kept_sites, "reasons": reasons,
                       "charged": 0 if row is None else int(row["charged"]), "reason": build.reason})
        if before is not None and site not in kept_sites and build.new_faces is not None:
            from engine.campus.needs_modelling import piece_border
            extra = build.new_points if build.new_points is not None else np.zeros((0, 3))
            pieces[-1].update(piece_border(np.vstack([before.positions, extra]), build.new_faces))
        if row is not None:
            by_reason.update(reasons.keys())
            samples_by_reason.update(reasons)
    sites = {"built": len(pieces), "kept": sum(p["kept"] for p in pieces),
             "rolled_back": sum(not p["kept"] for p in pieces),
             "rolled_back_by_reason": dict(sorted(by_reason.items())),
             "rolled_back_samples_by_reason": {k: int(v) for k, v in sorted(samples_by_reason.items()) if v},
             "by_piece": {kind: {"built": sum(p["piece"] == kind for p in pieces),
                                 "kept": sum(p["piece"] == kind and p["kept"] for p in pieces)}
                          for kind in ("wall", "bottom")}}
    return pieces, sites


def cmd_repair_unit(out_dir: Path, *, unit: str | None = None, snapshot: Path | None = None,
                    engines=REPAIR_ENGINES, campus_map: Path = Path("data/campus/campus_map.json"),
                    source: Path = Path("data/campus/source.json"),
                    materials: Path = Path("data/campus/materials.json"),
                    profile: FixProfile | None = None) -> int:
    """Repair one floor or element unit with the P2 engines, each piece of work checked by the Validator.

    The BEFORE is the campus unit `unit`, built as `campus-unit-before` builds it (into `<out_dir>/before/`), or the
    snapshot folder `snapshot`. The repair kernel runs `engines` (E8a, E8b, E3, in the order given) with the site
    judge on (`validate_sites=True`, the owner's settings; looks from `materials` and the BEFORE's MTL): a site that broke
    anything visible is rolled back. Writes `<out_dir>/<name>.fixed.obj` (with `materials.mtl` next to it),
    `edit_log.jsonl` and `report.json`: the pieces built, kept and rolled back (by the Validator's reason), the
    stage checks, the Validator's covered count after rollback, and the times. Writes no `.skp`.
    Returns 0 when the E8 stage passed (its last check PASS, or NOTHING KEPT: every piece rolled back on its own
    charge); 3 (`REPAIR_STAGE_FAILED`) when the stage was rolled back whole or ended FAIL -- every file is still
    written, and the mesh shipped is the safe one (the stage's input); 1 when the unit's BEFORE differs from the
    campus map (nothing repaired). Raises ValueError for an unknown engine, a unit or snapshot missing (or both
    given), a protected `out_dir`, or a snapshot in a protected folder (`main` turns those into exit 2)."""
    from engine.campus.unit_before import build_unit_before
    from engine.repair.engines.e1_loose import E1Loose
    from engine.repair.engines.e3_hidden import E3Hidden
    from engine.repair.engines.e8_fill import E8FlatFill
    from engine.repair.engines.e8_solidify import E8Solidify
    from engine.repair.kernel import repair_unit
    from engine.repair.types import RepairContext, UnitState
    from engine.site_judge import SiteJudge
    from engine.validate.checks import load_looks

    engines = list(engines)
    stages = repair_stages(engines)          # ValueError for an unknown name (exit 2), in the order given
    if (unit is None) == (snapshot is None):
        raise ValueError("give exactly one of a unit and a snapshot")
    out_dir = Path(out_dir)
    refuse_protected(out_dir)
    if snapshot is not None:
        # the live export folder (and the backup and the master) are read only through engine/io/snapshot.py's
        # stable copies (AGENTS.md section 3): a snapshot folder in one of them is refused before anything is read
        try:
            refuse_protected(snapshot)
        except ValueError as exc:
            raise ValueError(f"refusing to read {snapshot}: it lies in a protected folder, which is read only "
                             f"through engine/io/snapshot.py (its frozen copies under data/snapshots) ({exc})") from exc
    started = time.perf_counter()
    before_report = None
    if unit is not None:
        cmap = json.loads(Path(campus_map).read_text(encoding="utf-8"))
        src = json.loads(Path(source).read_text(encoding="utf-8"))
        before_dir = out_dir / "before"
        before_report = build_unit_before(cmap, src, unit, before_dir)
        if not before_report["matches_campus_map"]:
            # as campus-unit-before: a BEFORE that is not the campus map's unit is not repaired
            parts = ", ".join(f"{m['group']} [{m['band']}] {m['faces']} (map {m['expected']})"
                              for m in before_report["members"])
            _remove_stale_outputs(out_dir, unit, everything=True)
            print(f"error: {unit}: the BEFORE built from the snapshots DIFFERS from the campus map's tris ({parts}); "
                  f"nothing repaired -> {before_report['obj']}", file=sys.stderr)
            return 1
    else:
        before_dir = Path(snapshot)
    obj_path, mesh, flatness, mtl_materials = _load_snapshot(before_dir)
    profile = profile or FixProfile()
    judge = SiteJudge(load_looks(Path(materials), [(mtl_materials, before_dir)]))
    solid = E8Solidify(flatness=flatness) if "E8a" in stages else None
    fill = E8FlatFill() if "E8b" in stages else None
    hidden = E3Hidden(flatness=flatness, solidify=solid) if "E3" in stages else None
    loose = E1Loose(flatness=flatness, solidify=solid, out_dir=out_dir) if "E1" in stages else None
    kernel_engines = [{"E8a": solid, "E8b": fill, "E3": hidden, "E1": loose}[s] for s in stages]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").unlink(missing_ok=True)
    _remove_stale_outputs(out_dir, None)
    built = time.perf_counter()
    result = repair_unit(UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None),
                         RepairContext(profile=profile, decider=None, validator=judge),
                         engines=kernel_engines, validate_sites=True, edit_log=out_dir / "edit_log.jsonl")
    repaired = time.perf_counter()

    name = mesh.name
    fixed = out_dir / f"{name}.fixed.obj"
    write_obj(result.mesh, fixed)
    if before_dir != out_dir:
        if snapshot is not None:
            _copy_assets(before_dir, out_dir)
        elif (before_dir / "materials.mtl").is_file():
            shutil.copyfile(before_dir / "materials.mtl", out_dir / "materials.mtl")

    checks = {c["stage"]: c for c in result.checks}
    by_stage = _edits_by_stage(result)
    solid_stage = None if solid is None else solid.name
    pieces, sites = _repair_report(_StageView(result, by_stage.get(solid_stage, [])),
                                   {k: c for k, c in checks.items() if k == solid_stage}, before=mesh)
    after = [dict(_after_rollback(c), stage=stage) for stage, c in checks.items()]
    sr = (solid.report if solid is not None else None) or {}
    fills, not_filled, fill_stats = [], [], None
    if fill is not None:
        fills, not_filled, fill_stats = _fill_report(fill, by_stage.get(fill.name, []), result, checks.get(fill.name),
                                                     mesh, judge.looks, out_dir)
    e3 = None
    if hidden is not None:
        e3 = _e3_report(hidden, by_stage.get(hidden.name, []), result, checks.get(hidden.name))
    e1 = None
    if loose is not None:
        e1 = _e1_report(loose, by_stage.get(loose.name, []), result, checks.get(loose.name))
    report = {
        "unit": unit, "snapshot": None if snapshot is None else str(snapshot), "engines": engines,
        "stages_run": stages,
        "before": {"obj": str(obj_path), "sha256": sha256_file(obj_path), "faces": int(mesh.n_faces),
                   "unit_before": before_report},
        "after": {"obj": str(fixed), "sha256": sha256_file(fixed), "faces": int(result.mesh.n_faces)},
        "profile": _profile_dict(profile),
        "sites": sites,
        "pieces": pieces,
        "covered_after_rollback": int(sum(a["covered"] for a in after)),
        "after_rollback": after,
        "stages": [{k: c.get(k) for k in ("stage", "engine", "sites", "edits", "first", "final", "rounds",
                                           "rounds_exhausted", "stage_rolled_back", "unknown", "runs", "rolled_back")}
                   for c in result.checks],
        "solidify": {k: sr.get(k) for k in ("skirts_added", "bottoms_added", "sides_rebuilt", "side_pieces_replaced",
                                            "invented_vertices", "cap_guard_removed", "cap_guard_passed",
                                            "walls_refused", "bottom_faces_refused", "runtime_s")},
        "fills": fills,
        "not_filled": not_filled,
        "fill_stats": fill_stats,
        **({"e3": e3} if e3 is not None else {}),
        **({"e1": e1} if e1 is not None else {}),
        "seconds": {"before": round(built - started, 2), "kernel": round(repaired - built, 2),
                    "total": round(time.perf_counter() - started, 2)},
        "exit_code": _repair_exit_code(result.checks),
    }
    queued = time.perf_counter()
    needs = _needs_modelling(report, result.records, mesh, judge.looks, out_dir)
    report["needs_modelling"] = {"file": "needs_modelling.json", "entries": needs["counts"]["entries"],
                                 "by_kind": needs["counts"]["by_kind"], "by_reason": needs["counts"]["by_reason"]}
    report["seconds"]["needs_modelling"] = round(time.perf_counter() - queued, 2)
    report["seconds"]["total"] = round(time.perf_counter() - started, 2)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    _print_checks(name, result.checks, repaired - built)
    s = sites
    if solid is not None:
        print(f"{name}: E8 built {s['built']} pieces ({s['by_piece']['wall']['built']} walls, "
              f"{s['by_piece']['bottom']['built']} bottoms); kept {s['kept']}, rolled back {s['rolled_back']} "
              f"{s['rolled_back_by_reason']}")
    if fill_stats is not None:
        f = fill_stats
        print(f"{name}: E8b found {f['loops']} closed loops ({f['outer_boundaries']} patch outer borders, {f['holes']} "
              f"holes) among {f['components']} pieces of open edges; filled {f['kept']}, rolled back "
              f"{f['rolled_back']}; not filled {f['not_filled_by_reason']}")
    if e3 is not None:
        s3 = e3["sites"]
        print(f"{name}: E3 legacy candidates {e3['legacy_candidates']} {e3['by_rule']}, left out {e3['excluded']}; "
              f"{e3['candidates']} candidate faces in {e3['groups']} groups ({e3['groups_split']} split) -> "
              f"{s3['planned']} sites; kept {s3['kept']}, rolled back {s3['rolled_back']} "
              f"{s3['rolled_back_by_reason']}; removed {e3['faces_removed']} faces; deleted after rollback "
              f"{e3['deleted_after_rollback']}; disagreements {e3['disagreements']['faces']}")
    if e1 is not None:
        s1 = e1["sites"]
        print(f"{name}: E1 candidates {e1['candidates']}; sites: planned {s1['planned']}, kept {s1['kept']}, "
              f"rolled back {s1['rolled_back']}; visible debris: {len(e1['visible_debris'])}")
    print(f"{name}: needs modelling: {needs['counts']['entries']} spots {needs['counts']['by_kind']} "
          f"{needs['counts']['by_reason']} ({needs['counts']['outer_boundaries']} patch outer borders only counted); "
          f"{report['seconds']['needs_modelling']} s")
    print(f"{name}: covered after rollback {report['covered_after_rollback']}; "
          f"{mesh.n_faces} -> {result.mesh.n_faces} faces; {report['seconds']['total']} s; wrote {out_dir}")
    if report["exit_code"] == REPAIR_STAGE_FAILED:
        print(f"{name}: an engine stage was rolled back whole or did not end PASS: the BEFORE ships for it "
              f"(exit {REPAIR_STAGE_FAILED})", file=sys.stderr)
    return report["exit_code"]


def _needs_modelling(report: dict, records: list, before, looks, out_dir: Path) -> dict:
    """Write `<out_dir>/needs_modelling.json` (job P2-E8c) and a BEFORE crop per entry under
    `<out_dir>/needs_modelling/<id>.png` (`engine.fill_review.SpotCropper`, from the entry's `suggested_view`), and
    return the document. `report` is the run's report.json dict, `records` the lines of its edit log."""
    from engine.campus.needs_modelling import build_needs_modelling, validate_document
    from engine.fill_review import SpotCropper

    doc = build_needs_modelling(report, records, before)
    if doc["entries"]:
        cropper = SpotCropper(before, looks)
        for entry in doc["entries"]:
            entry["crop"] = f"needs_modelling/{entry['id']}.png"
            cropper.write(entry["border"], entry["ordered"], entry["suggested_view"], Path(out_dir) / entry["crop"])
    validate_document(doc)
    (Path(out_dir) / "needs_modelling.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc


def fill_diameter_bins() -> tuple:
    """The inscribed-diameter histogram's bin edges in report.json's `fill_stats` (inches): one edge is E8b's own cap,
    `engine.repair.engines.e8_fill.FILL_MAX_DIAMETER` (ruling E8b-R3), read when called."""
    from engine.repair.engines import e8_fill
    return (0.0, 5.0, 10.0, 20.0, float(e8_fill.FILL_MAX_DIAMETER), 80.0, 160.0)


def _fill_report(engine, edits: list, result, check: dict | None, before, looks, out_dir: Path):
    """`(fills, not_filled, fill_stats)` of report.json (ruling E8b-R8). `fills`: one row per kept fill, with its
    BEFORE | AFTER crop (`fills/fill-<site>.png`, `engine.fill_review`). `not_filled`: every hole E8b refused (its
    rule and reason), then every fill the site check rolled back (rule E8b-R7, reason `charged` with the Validator's
    reasons as `detail`, or `stage_rolled_back`). `fill_stats`: E8b's counts, patch outer borders included (counted,
    never listed), kept and rolled back, refusals by reason and the inscribed-diameter histogram of every hole."""
    from engine.fill_review import write_fill_crop

    after = result.mesh
    kept = {id(e) for e in result.kept}
    rolled = {row["site"]: row for row in (check or {}).get("rolled_back", [])}
    fills, not_filled = [], [dict(row) for row in engine.not_filled]
    rnd = lambda v: [round(float(x), 3) for x in v]
    for e in edits:
        ev = e.evidence
        loop = after.positions[np.asarray(ev["loop"], np.int64)]
        if id(e) in kept:
            crop = f"fills/fill-{e.site:04d}.png"
            write_fill_crop(before, after, loop, ev["normal"], looks, Path(out_dir) / crop)
            fills.append({"site": int(e.site), "loop": ev["loop_id"], "vertices": ev["vertices"], "area": ev["area"],
                          "inscribed_diameter": ev["inscribed_diameter"], "look": ev["look"],
                          "centroid": ev["centroid"], "normal": ev["normal"], "crop": crop})
            continue
        row = rolled.get(e.site, {})
        whole = bool(row.get("stage_rolled_back"))
        not_filled.append({"loop": ev["loop_id"], "site": int(e.site), "rule": "E8b-R7",
                           "reason": "stage_rolled_back" if whole else "charged",
                           "detail": {} if whole else dict(row.get("reasons", {})), "vertices": ev["vertices"],
                           "centroid": ev["centroid"], "points": [rnd(p) for p in loop],
                           "inscribed_diameter": ev["inscribed_diameter"], "area": ev["area"]})
    report = engine.report or {}
    diameters = np.asarray(report.get("diameters", []), dtype=np.float64)
    edges = sorted(fill_diameter_bins()) + [np.inf]
    counts = np.histogram(diameters, bins=edges)[0].tolist() if len(diameters) else [0] * (len(edges) - 1)
    labels = [f"{a:g}-{b:g}" if np.isfinite(b) else f">{a:g}" for a, b in zip(edges[:-1], edges[1:])]
    stats = {k: report.get(k) for k in ("open_edges", "components", "loops", "outer_boundaries", "holes", "planned",
                                        "plane_tol", "max_diameter")}
    stats.update(kept=len(fills), rolled_back=len(edits) - len(fills),
                 not_filled_by_reason=dict(sorted(collections.Counter(r["reason"] for r in not_filled).items())),
                 diameter_histogram={"bins_in": labels, "counts": counts})
    return fills, not_filled, stats


class _StageView:
    """The part of a kernel result one stage made: its `edits` and the `kept` among them."""

    def __init__(self, result, edits: list):
        ids = {id(e) for e in edits}
        self.edits = list(edits)
        self.kept = [e for e in result.kept if id(e) in ids]


def _edits_by_stage(result) -> dict:
    """`{stage: [its edits]}`: the edit lines of `result.records` run in the order of `result.edits`."""
    lines = [r for r in result.records if "check" not in r]
    out: dict = {}
    for edit, line in zip(result.edits, lines):
        out.setdefault(line["stage"], []).append(edit)
    return out


def _repair_exit_code(checks: list[dict]) -> int:
    """0 when every stage passed: its last check PASS, or NOTHING KEPT (each piece rolled back on its own charge,
    the stage's input ships); `REPAIR_STAGE_FAILED` (3) when a stage was rolled back whole or ended any other way."""
    for check in checks:
        if check.get("stage_rolled_back") or check.get("final") not in ("PASS", "NOTHING KEPT"):
            return REPAIR_STAGE_FAILED
    return 0


# ------------------------------------------------------------------------------------------ main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m engine.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    fix_p = sub.add_parser("fix", help="fix one snapshot, writing the fixed OBJs, report and guard images")
    fix_p.add_argument("snapshot_dir")
    fix_p.add_argument("--accept-slit", action="store_true")
    fix_p.add_argument("--no-solidify", dest="solidify", action="store_false",
                       help="do not close slabs with skirts and bottoms before fixing")
    fix_p.add_argument("--keep-fragments", dest="fragments", action="store_false",
                       help="do not remove stray fragments, attached slivers or the redundant "
                            "member of a fold")
    fix_p.add_argument("--out", default="data/output")
    fix_p.add_argument("--no-skp", dest="skp", action="store_false",
                       help="do not write the SketchUp file")
    fix_p.add_argument("--skp-dir", default=None,
                       help="folder that receives a copy of the latest .skp "
                            "(default: <repo root>/OBJ FIXED RESULT)")
    fix_p.add_argument("--kernel", action="store_true",
                       help="run through the observe-only repair kernel; the same files, plus "
                            "edit_log.jsonl next to report.json")
    fix_p.add_argument("--validate-sites", dest="validate_sites", action="store_true",
                       help="with --kernel: check every stage with the Validator's focus mode and log "
                            "the checks in edit_log.jsonl (legacy stages are not rolled back)")
    fix_p.add_argument("--materials", type=Path, default=Path("data/campus/materials.json"),
                       help="materials.json for --validate-sites")

    preview_p = sub.add_parser("preview-data", help="write the JSON preview/index.html reads")
    preview_p.add_argument("snapshot_dir")
    preview_p.add_argument("--no-solidify", dest="solidify", action="store_false",
                           help="do not close slabs with skirts and bottoms before fixing")
    preview_p.add_argument("--out", default="preview/data")

    errors_p = sub.add_parser("errors", help="find what is wrong with each face, without fixing it")
    errors_p.add_argument("snapshot", type=Path)
    errors_p.add_argument("--out", type=Path, required=True)

    freeze_p = sub.add_parser("campus-freeze",
                              help="freeze the CHECKPOINT-17 export (stable copies + sha256) and hash the backup")
    freeze_p.add_argument("--export", type=Path, required=True, help="the CKPT17 export folder (read only)")
    freeze_p.add_argument("--backup", type=Path, required=True, help="the CHECKPOINT-17 backup folder (hashed only)")
    freeze_p.add_argument("--out", type=Path, default=Path("data/campus"))
    freeze_p.add_argument("--snapshots", type=Path, default=Path("data/snapshots"))

    index_p = sub.add_parser("campus-index",
                             help="index every face of CKPT17-CLEAN.obj by its SketchUp group path")
    index_p.add_argument("--source", type=Path, default=Path("data/campus/source.json"),
                         help="the source.json file from campus-freeze")
    index_p.add_argument("--out", type=Path, default=Path("data/campus/group_index.json"),
                         help="output group_index.json")

    mat_p = sub.add_parser("campus-materials",
                           help="build material look keys for texture and color comparison")
    mat_p.add_argument("--source", type=Path, default=Path("data/campus/source.json"),
                       help="the campus source.json path")
    mat_p.add_argument("--out", type=Path, default=Path("data/campus/materials.json"),
                       help="destination path for materials.json")
    mat_p.add_argument("--mtl", type=Path, default=None,
                       help="optional explicit path to MTL file (overrides source.json)")
    mat_p.add_argument("--tex-dir", type=Path, default=None,
                       help="optional explicit path to texture directory")

    skp_check_p = sub.add_parser(
        "campus-skp-check",
        help="check the frozen export against the CHECKPOINT-17 backup through the SketchUp SDK "
             "(read only: the SDK opens a sha256-verified copy of the backup and cannot save)")
    skp_check_p.add_argument("--source", type=Path, default=Path("data/campus/source.json"),
                             help="the freeze (campus-freeze) whose files are checked")
    skp_check_p.add_argument("--backup", type=Path, required=True,
                             help="the CHECKPOINT-17 backup folder (read only)")
    skp_check_p.add_argument("--out", type=Path, default=Path("data/campus"),
                             help="receives skp_copy/, skp_walk.json and skp_check.json")
    skp_check_p.add_argument("--summary", type=Path, default=None,
                             help="also write a short markdown summary here")
    skp_check_p.add_argument("--name", default=None,
                             help="the backup .skp, when source.json lists more than one")
    skp_check_p.add_argument("--timeout-min", type=float, default=None,
                             help="minutes the SketchUp walk may take before it is killed (default 30)")
    skp_check_p.add_argument("--min-free-commit-mb", type=float, default=None,
                             help="MB of commit memory that must be free to start the walk "
                                  "(default 3500; the walk peaks at about 2.5 GB)")
    skp_check_p.add_argument("--dll", type=Path, default=None, help="SketchUpAPI.dll, if not the default")

    validate_p = sub.add_parser(
        "validate",
        help="judge a repaired floor by the owner's rule: textures there, problems solved, nothing visible "
             "deleted or covered")
    validate_p.add_argument("--before", type=Path, required=True,
                            help="BEFORE: a snapshot directory (one .obj, materials.mtl, tex/)")
    validate_p.add_argument("--after", type=Path, required=True, help="AFTER: an OBJ file")
    validate_p.add_argument("--materials", type=Path, default=Path("data/campus/materials.json"),
                            help="the campus look keys (default data/campus/materials.json)")
    validate_p.add_argument("--out", type=Path, required=True,
                            help="receives validation.json and evidence/*.png")
    validate_p.add_argument("--targets", type=Path, default=None,
                            help="the owner's signed targets (default engine/validate/targets.json when it exists; "
                                 "without it check 2 only reports)")
    validate_p.add_argument("--area-per-sample", type=float, default=36.0,
                            help="one sample per this many sq in of face (owner's value 36). Any other value is a "
                                 "development run and the report says it is not an owner verdict")
    validate_p.add_argument("--edit-log", type=Path, default=None,
                            help="the edit_log.jsonl of the repair that made --after: its kept flat fills are judged "
                                 "by the Validator's fill_site class (ruling P2-E8b-R11)")
    validate_p.add_argument("--min-per-face", type=int, default=4,
                            help="at least this many samples on every face (owner's value 4; see --area-per-sample)")

    before_p = sub.add_parser(
        "campus-unit-before",
        help="write a campus unit's BEFORE (its members' frozen snapshots, bands cut by face-centre z) as a "
             "folder that `validate --before` takes")
    before_p.add_argument("--unit", required=True, help="the unit's name in the campus map, e.g. CHTM-L05")
    before_p.add_argument("--map", type=Path, default=Path("data/campus/campus_map.json"),
                          help="the owner-confirmed campus map")
    before_p.add_argument("--source", type=Path, default=Path("data/campus/source.json"),
                          help="the source.json file from campus-freeze (snapshot folders)")
    before_p.add_argument("--out", type=Path, required=True,
                          help="receives <unit>.obj and materials.mtl (a short temp folder)")
    before_p.add_argument("--copy-textures", action="store_true",
                          help="copy the textures to <out>/tex (default: the MTL points at the snapshots')")

    repair_p = sub.add_parser(
        "repair-unit",
        help="repair one floor or element unit with the P2 engines (E8, E3), every piece checked by the "
             "Validator and rolled back if it breaks anything visible",
        description="Repair one floor or element unit with the P2 engines (E8, E3); every piece is checked by "
                    "the Validator and rolled back if it breaks anything visible. " + REPAIR_EXIT_CODES + ".")
    where = repair_p.add_mutually_exclusive_group(required=True)
    where.add_argument("--unit", default=None, help="the unit's name in the campus map, e.g. CHTM-L05")
    where.add_argument("--snapshot", type=Path, default=None,
                       help="a snapshot folder (one .obj, materials.mtl, tex/) as the BEFORE, instead of a unit")
    repair_p.add_argument("--engines", nargs="+", required=True,
                          help=f"the engines to run, in this order, as a comma list (e.g. E8a,E3): "
                               f"{', '.join(REPAIR_ENGINES)} (E8 = E8a, strict solidify, then E8b, the narrow flat "
                               f"fill; E3 = hidden faces, interior-aware); an unknown name exits 2")
    repair_p.add_argument("--out", type=Path, required=True,
                          help="receives before/, <unit>.fixed.obj, edit_log.jsonl and report.json (a short temp folder)")
    repair_p.add_argument("--map", type=Path, default=Path("data/campus/campus_map.json"),
                          help="the owner-confirmed campus map")
    repair_p.add_argument("--source", type=Path, default=Path("data/campus/source.json"),
                          help="the source.json file from campus-freeze (snapshot folders)")
    repair_p.add_argument("--materials", type=Path, default=Path("data/campus/materials.json"),
                          help="the campus look keys the Validator judges by")

    census_p = sub.add_parser("census", help="run find_errors census over units with timings, peak memory and fix plan")
    census_p.add_argument("units", nargs="*", default=None, help="snapshot directories (default: all snapshots in source.json)")
    census_p.add_argument("--out", type=Path, default=Path("data/campus/census.json"), help="output census JSON path")
    census_p.add_argument("--errors-dir", type=Path, default=None, help="output directory for per-unit error JSONs")
    census_p.add_argument("--md", type=Path, default=None, help="output path for markdown census table")
    census_p.add_argument("--jobs", type=int, default=4, help="number of parallel worker processes")
    census_p.add_argument("--timeout", type=float, default=1800.0, help="timeout per unit in seconds")
    census_p.add_argument("--materials", type=Path, default=Path("data/campus/materials.json"), help="path to materials.json")

    inv_p = sub.add_parser("campus-inventory",
                           help="buildings, level tables, floor/element units, duplicates, misnamed and missing "
                                "levels: the draft campus map for the owner to confirm")
    inv_p.add_argument("--source", type=Path, default=Path("data/campus/source.json"),
                       help="the source.json file from campus-freeze")
    inv_p.add_argument("--index", type=Path, default=Path("data/campus/group_index.json"),
                       help="the group_index.json file from campus-index")
    inv_p.add_argument("--materials", type=Path, default=Path("data/campus/materials.json"),
                       help="the materials.json file from campus-materials")
    inv_p.add_argument("--out", type=Path, default=Path("data/campus/campus_map.draft.json"),
                       help="the draft campus map (JSON)")
    inv_p.add_argument("--md", type=Path, default=Path("data/campus/campus_map.draft.md"),
                       help="the owner-readable table (under data/ by default; copying it into "
                            "docs/superpowers/records/campus/ is a deliberate step)")
    inv_p.add_argument("--literal", action="store_true",
                       help="use the brief's constants as written (24 in slab window, nearest base, 20 in merge, "
                            "print-step duplicates) instead of the measured ones")

    col_p = sub.add_parser("campus-errors-skp",
                           help="one colour-coded SketchUp file per building: every error kind and grouping "
                                "problem on its own tag (read-only export)")
    col_p.add_argument("--map", type=Path, default=Path("data/campus/campus_map.json"),
                       help="the owner-confirmed campus map")
    col_p.add_argument("--source", type=Path, default=Path("data/campus/source.json"),
                       help="the source.json file from campus-freeze (snapshot folders)")
    col_p.add_argument("--errors", type=Path, default=Path("data/campus/errors"),
                       help="the census error maps, one <group>.json per split")
    col_p.add_argument("--skp-check", type=Path, default=Path("data/campus/skp_check.json"),
                       help="the export-vs-backup check (mismatches become grouping flags)")
    col_p.add_argument("--out", type=Path, default=Path("data/coloring_scratch"),
                       help="writes <out>/<BUILDING>/<BUILDING>-errors.skp and .json")
    col_p.add_argument("--materials", type=Path, default=Path("data/campus/materials.json"),
                       help="the materials.json file from campus-materials (flicker is split by look)")
    col_p.add_argument("--buildings", nargs="*", default=None, help="only these buildings (default: all)")
    col_p.add_argument("--dll", default=None, help="SketchUpAPI.dll (default: $FIXER_SKETCHUP_DLL or SketchUp 2026)")

    pilot_p = sub.add_parser("decide-pilot",
                             help="measure TypeSafe's Jev on the 85 group names and 391 materials (suggest-only; "
                                  "needs TYPESAFE_API_KEY, runs without a key and reports source none)")
    pilot_p.add_argument("--source", type=Path, default=Path("data/campus/source.json"))
    pilot_p.add_argument("--materials", type=Path, default=Path("data/campus/materials.json"))
    pilot_p.add_argument("--map", type=Path, default=Path("data/campus/campus_map.json"),
                         help="the owner-confirmed campus map: the ground truth")
    pilot_p.add_argument("--out", type=Path, default=Path("data/campus/jev_pilot.json"))
    pilot_p.add_argument("--env-file", type=Path, default=None,
                         help="read TYPESAFE_API_KEY from this file when the environment has none "
                              "(default: the repo-root .env; only that one line is read)")
    pilot_p.add_argument("--min-confidence", type=float, default=0.8)
    pilot_p.add_argument("--batch", type=int, default=20, help="questions per Jev call")

    pull_p = sub.add_parser("decide-pull",
                            help="fetch the owner-confirmed answers of one question type from the VPS decide "
                                 "service and write <out>/<type>.json as {subject: answer} (needs "
                                 "UC_DECIDE_PASSWORD)")
    pull_p.add_argument("--url", default=None,
                        help="the service base URL, e.g. https://host (https unless localhost); "
                             "default: the environment variable UC_DECIDE_URL")
    pull_p.add_argument("--type", required=True, dest="qtype", help="the question type, e.g. mat.category")
    pull_p.add_argument("--out", type=Path, default=None,
                        help="a folder inside <repo>/data (default: <repo>/data/decide/confirmed)")
    pull_p.add_argument("--env-file", type=Path, default=None,
                        help="read UC_DECIDE_PASSWORD from this file when the environment has none "
                             "(default: the repo-root .env; only that one line is read)")

    imp_p = sub.add_parser("decide-import-pilot",
                           help="load the paid Jev pilot answers (jev_pilot.json) into the VPS decide service as "
                                "pending suggestions, with the exact questions the classifiers ask (needs "
                                "UC_DECIDE_PASSWORD; --dry-run sends nothing)")
    imp_p.add_argument("--url", default=None,
                       help="the service base URL, e.g. https://host (https unless localhost); "
                            "default: the environment variable UC_DECIDE_URL")
    imp_p.add_argument("--source", type=Path, default=Path("data/campus/source.json"))
    imp_p.add_argument("--materials", type=Path, default=Path("data/campus/materials.json"))
    imp_p.add_argument("--pilot", type=Path, default=Path("data/campus/jev_pilot.json"))
    imp_p.add_argument("--env-file", type=Path, default=None,
                       help="read UC_DECIDE_PASSWORD from this file when the environment has none "
                            "(default: the repo-root .env; only that one line is read)")
    imp_p.add_argument("--dry-run", action="store_true", help="print the counts and send nothing")

    return parser


#: Where each writing command puts its files (argparse names); the commands that write nothing are not here.
#: campus-errors-skp checks its own output (error_export raises, as its tests expect).
_OUTPUT_ARGS = {"fix": ("out", "skp_dir"), "preview-data": ("out",), "errors": ("out",),
                "campus-skp-check": ("out", "summary"), "validate": ("out",),
                "census": ("out", "md", "errors_dir"), "campus-freeze": ("out", "snapshots"),
                "campus-index": ("out",), "campus-materials": ("out",), "campus-inventory": ("out", "md"),
                "decide-pilot": ("out",), "campus-unit-before": ("out",), "repair-unit": ("out",)}


def _refuse_protected_outputs(args) -> str | None:
    """The refusal text when a writing command's output lies in a protected folder, else None; checked before
    the command does anything."""
    try:
        for name in _OUTPUT_ARGS.get(args.command, ()):
            if getattr(args, name, None) is not None:
                refuse_protected(getattr(args, name))
    except ValueError as exc:
        return str(exc)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    refusal = _refuse_protected_outputs(args)
    if refusal is not None:
        print(f"error: {refusal}", file=sys.stderr)
        return 2
    if args.command == "fix":
        if args.validate_sites and not args.kernel:
            parser.error("--validate-sites needs --kernel")
        return cmd_fix(Path(args.snapshot_dir), Path(args.out), args.accept_slit,
                       solidify=args.solidify, fragments=args.fragments, skp=args.skp,
                       skp_dir=Path(args.skp_dir) if args.skp_dir else default_skp_dir(),
                       kernel=args.kernel, validate_sites=args.validate_sites,
                       materials=args.materials)
    if args.command == "preview-data":
        return cmd_preview_data(Path(args.snapshot_dir), Path(args.out),
                                solidify=args.solidify)
    elif args.command == "errors":
        cmd_errors(args.snapshot, args.out)
        return 0
    elif args.command == "validate":
        from engine.validate.checks import Settings
        return cmd_validate(args.before, args.after, args.materials, args.out, targets=args.targets,
                            settings=Settings(area_per_sample=args.area_per_sample, min_per_face=args.min_per_face),
                            edit_log=args.edit_log)
    elif args.command == "campus-freeze":
        from engine.campus.source import freeze_source
        res = freeze_source(args.export, args.backup, args.out, args.snapshots)
        totals = json.loads(res.json_path.read_text(encoding="utf-8"))["totals"]
        print(f"froze {totals['files']} files, {totals['tris']} triangles -> {res.json_path}")
        return 0
    elif args.command == "campus-index":
        from engine.campus.groups import cmd_campus_index
        res = cmd_campus_index(args.source, args.out)
        print(f"indexed {len(res['paths'])} paths, {len(res['faces'])} runs, {len(res['split'])} splits -> {args.out}")
        return 0
    elif args.command == "campus-materials":
        from engine.campus.materials import build_materials
        if args.mtl:
            mtl_path = Path(args.mtl)
            tex_dir = Path(args.tex_dir) if args.tex_dir else mtl_path.parent
        else:
            source_path = Path(args.source)
            source_data = json.loads(source_path.read_text(encoding="utf-8"))
            mtl_path = Path(source_data["clean_mtl"]["path"])
            if args.tex_dir:
                tex_dir = Path(args.tex_dir)
            elif (mtl_path.parent / "SRC-TEX").is_dir():
                tex_dir = mtl_path.parent / "SRC-TEX"
            else:
                tex_dir = mtl_path.parent

        out_path = Path(args.out)

        res = build_materials(mtl_path, tex_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(res, indent=2), encoding="utf-8")
        stats = res["stats"]
        print(f"materials: {stats['materials']}, textured: {stats['textured']}, images: {stats['images']}, looks: {stats['looks']}")
        print(f"looks ({len(res['looks'])}):")
        sorted_looks = sorted(res["looks"].items(), key=lambda kv: len(kv[1]), reverse=True)
        for key, mats in sorted_looks[:10]:
            print(f"  {key} ({len(mats)} materials): {mats}")
        print(f"wrote materials to {out_path}")
        return 0
    elif args.command == "campus-unit-before":
        from engine.campus.unit_before import build_unit_before
        try:
            cmap = json.loads(Path(args.map).read_text(encoding="utf-8"))
            source = json.loads(Path(args.source).read_text(encoding="utf-8"))
            report = build_unit_before(cmap, source, args.unit, args.out, copy_textures=args.copy_textures)
        except (ValueError, OSError, KeyError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        parts = ", ".join(f"{m['group']} [{m['band']}] {m['faces']}" for m in report["members"])
        print(f"{report['unit']}: {report['faces']} faces from {len(report['members'])} members ({parts}); "
              + ("equals the campus map's tris" if report["matches_campus_map"]
                 else "DIFFERS from the campus map's tris") + f" -> {report['obj']}")
        return 0 if report["matches_campus_map"] else 1
    elif args.command == "repair-unit":
        try:
            return cmd_repair_unit(args.out, unit=args.unit, snapshot=args.snapshot, engines=args.engines,
                                   campus_map=args.map, source=args.source, materials=args.materials)
        except (ValueError, OSError, KeyError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    elif args.command == "campus-skp-check":
        from engine.campus import skp_check
        from engine.io.snapshot import SourceUnstable
        extra = {}
        if args.timeout_min is not None:
            extra["timeout_s"] = args.timeout_min * 60.0
        if args.min_free_commit_mb is not None:
            extra["min_free_commit_mb"] = args.min_free_commit_mb
        try:
            report = skp_check.check_source(args.source, args.backup, args.out, summary=args.summary,
                                            name=args.name, dll_path=args.dll, **extra)
        except (skp_check.BackupMismatch, skp_check.WalkFailed, SourceUnstable, ValueError,
                FileNotFoundError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        c = report["counts"]
        print(f"checked {c['files']} files against {report['source']['backup']}: {c['matches']} match, "
              f"{c['mismatches']} mismatch, {c['ambiguous_files']} ambiguous, {c['misses']} miss "
              f"-> {args.out / 'skp_check.json'}")
        return 0
    elif args.command == "census":
        from engine.campus.census import census
        units = [Path(u) for u in args.units] if args.units else None
        res = census(units=units, out_json=args.out, jobs=args.jobs, timeout_s=args.timeout,
                     errors_dir=args.errors_dir, out_md=args.md, materials_path=args.materials)
        totals = res["totals"]
        wall_sec = totals.get("wall_seconds", totals["seconds"])
        print(f"census completed: {totals['units']} units ({totals['ok']} ok, {totals['timeout']} timeout, {totals['error']} error), "
              f"{totals['triangles']:,} triangles in {wall_sec:.2f} s wall ({totals['seconds']:.2f} s unit sum) -> {args.out}")
        if totals.get("error", 0) > 0:
            return 1
        return 0
    elif args.command == "campus-inventory":
        from engine.campus.inventory import BRIEF_PARAMS, cmd_campus_inventory
        res = cmd_campus_inventory(args.source, args.index, args.materials, args.out, args.md,
                                   BRIEF_PARAMS if args.literal else None)
        by_type = collections.Counter(u["type"] for u in res["units"])
        by_kind = collections.Counter(f["kind"] for f in res["flags"])
        cov = res["coverage"]
        print(f"campus inventory: {cov['groups']} splits, {cov['tris']:,} triangles -> {len(res['units'])} units "
              f"(floor {by_type['floor']}, element {by_type['element']}, site {by_type['site']}), "
              f"{len(res['proposals'])} split proposals")
        for name, b in res["buildings"].items():
            a = b["anchor"]
            print(f"  {name}: {len(b['groups'])} groups, {len(b['levels'])} levels"
                  + (f", numbered from L{1 + a['offset']:02d}" if a["offset"] else ""))
        print("  flags: " + ", ".join(f"{k} {by_kind[k]}"
                                      for k in ("duplicate", "misnamed", "missing", "shared", "footprint", "split")))
        print(f"  coverage: {cov['whole']} whole + {cov['split']} split = {cov['whole'] + cov['split']} of {cov['groups']} "
              f"splits, {cov['unit_tris']:,} of {cov['tris']:,} triangles in units ({'ok' if cov['ok'] else 'NOT ok'})")
        print(f"wrote {args.out} and {args.md}")
        return 0
    elif args.command == "campus-errors-skp":
        from engine.campus.error_export import cmd_campus_errors_skp
        for r in cmd_campus_errors_skp(args.map, args.source, args.errors, args.skp_check, args.out,
                                       args.buildings, args.dll, args.materials):
            back = r["read_back"]["faces_by_tag"]
            dups, odd = sum(r["duplicates_by_tag"].values()), r["unexplained_by_tag"]
            same = "as written" if not odd else f"UNEXPLAINED {odd}"
            print(f"{r['building']}: {len(r['columns'])} columns, {sum(back.values()):,} faces read back "
                  f"({same}; {dups:,} exact duplicate triangles kept once), "
                  f"{r['written']['rejected_faces']} refused -> {r['skp']}")
        return 0
    elif args.command == "decide-pilot":
        from engine.decide.jev import JevDecider
        from engine.decide.pilot import run_pilot
        decider = JevDecider(min_confidence=args.min_confidence, batch=args.batch, env_file=args.env_file)
        if not decider.available:
            print("Jev is not available (no TYPESAFE_API_KEY or no typesafe-sdk): every answer is source none, "
                  "nothing is sent")
        rep = run_pilot(args.source, args.materials, args.map, args.out, decider)
        g, m, c = rep["groups"], rep["materials"], rep["calls"]
        print(f"group names: {g['n']}, sources {g['sources']}")

        def fmt(v):
            return "n/a" if v is None else f"{v:.3f}"
        for k in ("building", "type", "type_strict", "floor"):
            s = g[k]
            print(f"  {k}: accuracy {fmt(s['accuracy'])}, coverage {fmt(s['coverage'])} at confidence >= "
                  f"{rep['min_confidence']}, accuracy within coverage {fmt(s['accuracy_within_coverage'])} "
                  f"({s['n_truth']} with truth, {s['unknown_truth']} unknown)")
        print(f"materials: {m['n']}, sources {m['sources']}, categories {m['histogram']}")
        print(f"calls: {c['n']} ({c['failed']} failed), tokens in/out {c['input_tokens']}/{c['output_tokens']}")
        print(f"wrote {args.out}")
        return 0
    elif args.command == "decide-pull":
        from engine.decide.remote import pull_confirmed
        url = args.url or os.environ.get("UC_DECIDE_URL")
        if not url:
            print("error: no service URL: pass --url or set UC_DECIDE_URL", file=sys.stderr)
            return 2
        out = DATA_DIR / "decide" / "confirmed" if args.out is None else Path(args.out)
        if not out.resolve().is_relative_to(DATA_DIR.resolve()):
            print(f"error: --out must be inside {DATA_DIR} (decide-pull writes to data/ only), got {out}",
                  file=sys.stderr)
            return 2
        try:
            path = pull_confirmed(url, args.qtype, out, env_file=args.env_file)
        except (ValueError, RuntimeError) as exc:      # their texts carry no secret
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"wrote {len(json.loads(path.read_text(encoding='utf-8')))} confirmed answers -> {path}")
        return 0
    elif args.command == "decide-import-pilot":
        from engine.decide import pilot_import
        read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
        try:
            items, unreproducible = pilot_import.build_import_report(read(args.source), read(args.materials),
                                                                     read(args.pilot))
        except (OSError, ValueError, KeyError) as exc:
            print(f"error: could not build the pilot questions: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        n = pilot_import.counts(items, unreproducible)
        print(f"groups: {n['groups']} items from {n['group_rows']} groups, materials: {n['materials']} items from "
              f"{n['material_names']} spot-check materials, unreproducible: {n['unreproducible']}")
        if unreproducible:
            print(f"skipped, not reproducible from today's snapshots: {', '.join(unreproducible)}")
        if args.dry_run:
            print("dry run: nothing sent")
            return 0
        url = args.url or os.environ.get("UC_DECIDE_URL")
        if not url:
            print("error: no service URL: pass --url or set UC_DECIDE_URL", file=sys.stderr)
            return 2
        try:
            total = pilot_import.import_items(items, url, env_file=args.env_file)
        except (ValueError, RuntimeError) as exc:      # their texts carry no secret
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"imported: added {total['added']}, skipped {total['skipped']}, invalid {total['invalid']}, "
              f"unreproducible {n['unreproducible']}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
