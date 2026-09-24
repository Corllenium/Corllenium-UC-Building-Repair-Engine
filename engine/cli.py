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
    copies it -- the LATEST, overwriting the previous one -- into `<repo root>/OBJ FIXED RESULT/`,
    the folder the owner opens in SketchUp after every run; `--skp-dir` names another folder,
    `--no-skp` skips it. Without SketchUp the run still succeeds and report.json's `skp` says why
    no file was written.

`python -m engine.cli preview-data <snapshot_dir> --out preview/data`
    Writes the JSON `preview/index.html` reads (see `spike/12_export_preview.py` for the shape
    this mirrors), with AFTER built from the REAL fixed mesh and the REAL guard numbers, and
    `stats` extended with the new counts (flipped, thin_sheets, one_sided_holes_before/after,
    outline_edges_after, unavoidable_diagonals_after, guard_passed).

A snapshot directory is the layout `engine.io.snapshot.snapshot_object` produces: one `<name>.obj`,
`materials.mtl`, and a `tex/` folder of the textures it references.

`engine/` imports nothing from `api`, `spike`, fastapi, sqlalchemy; `trimesh`/`embreex` stay
confined to `engine/rays/` -- this module never imports them directly, only through
`engine.rays.caster.ReusableCaster`/`EmbreeCaster`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
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
from engine.io.skp_writer import SketchUpError, check_skp_validity, write_skp
from engine.io.snapshot import sha256_file
from engine.model import MeshData
from engine.pipeline import (Topology, analyse_topology, coplanar_region_borders,
                             flat_material_indices)
from engine.rays.caster import ReusableCaster
from engine.topo.adjacency import build_edge_table, edge_face_lists
from engine.topo.edges import EDGE_SOFT
from engine.topo.weld import weld_exact

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
        "n_fragment_components": result.n_fragment_components,
        "n_removed_fragments": result.n_removed_fragments,
        "n_removed_slivers": result.n_removed_slivers,
        "n_restored_fragments": result.n_restored_fragments,
        # component counts and the smallest components the size rules did NOT catch -- the
        # evidence for where the thresholds sit against this model. See `engine.detectors`.
        "fragment_report": result.fragment_report,
        "fragment_removals": result.fragment_removals,
        "n_overlap_pairs_same": result.n_overlap_pairs_same,
        "n_overlap_pairs_diff": result.n_overlap_pairs_diff,
        "n_removed_overlap": result.n_removed_overlap,
        "n_restored_overlap": result.n_restored_overlap,
        # never removed here, only reported: which of two materials a person wants is not a
        # question geometry can answer. Face ids are ORIGINAL ones.
        "overlap_pairs_diff_material": result.overlap_pairs_diff_material,
        "one_sided_holes_before": result.one_sided_holes_before,
        "one_sided_holes_after": result.one_sided_holes_after,
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
    topo = analyse_topology(result.mesh, flat_materials, coplanar_angle=profile.coplanar_angle,
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
        owner_copy = copy_dir / f"{name}.fixed.skp"
        failed_copy = copy_dir / f"{name}.fixed.FAILED.skp"
        dest_path = owner_copy if result.passed else failed_copy
        if not result.passed:
            out["previous_kept"] = str(owner_copy) if owner_copy.exists() else None
        try:
            copy_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest_path)
            out["copied_to"] = str(dest_path)
        except OSError as exc:       # e.g. the owner still has the previous file open
            out["copy_error"] = str(exc)
        # a passing copy supersedes any FAILED one an earlier run left beside it
        if result.passed and out["copied_to"] and failed_copy.exists():
            try:
                failed_copy.unlink()
                out["removed_stale_failed_copy"] = str(failed_copy)
            except OSError as exc:
                out["stale_failed_copy_error"] = str(exc)
    return out


# --------------------------------------------------------------------------------- fix command


def cmd_fix(snapshot_dir: Path, out_root: Path, accept_slit: bool,
            profile: FixProfile | None = None, solidify: bool = True,
            fragments: bool = True, skp: bool = True, skp_dir: Path | None = None) -> int:
    """`skp_dir` receives a copy of the `.skp`; `None` (the default here) copies it nowhere --
    `main` passes `default_skp_dir()` unless `--skp-dir` names another folder."""
    obj_path, mesh, flatness, _mtl_materials = _load_snapshot(snapshot_dir)
    if profile is None:
        profile = FixProfile(accept_slit=accept_slit, solidify=solidify,
                             accept_fragments=fragments)
    else:
        profile = replace(profile, accept_slit=accept_slit, solidify=solidify,
                          accept_fragments=fragments)

    result = fix_object(mesh, flatness, profile)

    name = mesh.name
    out_dir = Path(out_root) / name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").unlink(missing_ok=True)

    write_obj(result.mesh, out_dir / f"{name}.fixed.obj")
    write_obj_polygons(result.mesh, result.rings, out_dir / f"{name}.fixed.ngon.obj")
    _copy_assets(snapshot_dir, out_dir)

    # The triptychs show the run's own BEFORE, which is the reference the guards compared
    # against: the solidified mesh when `profile.solidify` is on, the input otherwise.
    flat_materials = flat_material_indices(mesh, flatness, profile.flat_texture_std)
    reference = result.reference_mesh
    topo = analyse_topology(reference, flat_materials)
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

    report = _build_report(name, obj_path, mesh, result, profile)
    report["qa"] = qa_report
    report["skp"] = skp_report
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    if result.solidify_report:
        sr = result.solidify_report
        print(f"{name}: solidify {sr['skirts_added']} skirts / {sr['bottoms_added']} bottoms, "
              f"{sr['invented_vertices']} vertices invented, "
              f"{sr['cap_guard_removed']} faces refused by the cap guard, "
              f"{sr['faces_newly_hidden']} faces newly hidden, {sr['runtime_s']}s")
    print(f"{name}: {mesh.n_faces} -> {result.mesh.n_faces} tris, passed={result.passed}, "
          f"border_shift={result.guard_final.totals['border_shift']}")
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
    # The reference's first `input_mesh.n_faces` rows ARE the input's faces (solidify only
    # appends), so `removed[:n]`, `topo.ok[:n]` and the rest line up without any remapping, and
    # both meshes are framed on the SAME centre so the two panes stay registered.
    input_mesh, mesh = mesh, result.reference_mesh
    flat_materials = flat_material_indices(mesh, flatness, profile.flat_texture_std)
    topo = analyse_topology(mesh, flat_materials)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
    positions_c_w = topo.positions_w - centre       # welded frame (topo.face_w indexes it)
    positions_c_o = mesh.positions - centre          # original frame: AFTER (result.mesh.face_v indexes it)

    n_input = input_mesh.n_faces
    ok_ids = np.nonzero(topo.ok)[0]
    removed = result.removed_hidden | result.removed_slit
    before_ids = ok_ids[ok_ids < n_input]            # the export's own faces, and only those
    before_tri = positions_c_w[topo.face_w[before_ids]]
    before_mat = mesh.face_material[before_ids]
    before_hidden = removed[before_ids].astype(int)

    added_ids = ok_ids[ok_ids >= n_input]            # everything solidify invented and kept
    added_tri = positions_c_w[topo.face_w[added_ids]]
    added_mat = mesh.face_material[added_ids]

    after_tri = positions_c_o[result.mesh.face_v]
    after_mat = result.mesh.face_material

    # ...and the BEFORE pane's edges come from the INPUT mesh's own topology, or an outline edge
    # of a skirt the export never had would float there with no surface under it. Welded ids
    # differ between the two topologies, but `_before_edges` emits COORDINATES, and both are
    # recentred on the same `centre`, so the segments land in the same frame as everything else.
    topo_input = analyse_topology(input_mesh, flat_materials)
    grid, tri_before, outline_before = _before_edges(
        topo_input, topo_input.positions_w - centre, removed[:n_input])
    outline_after, tri_after = _after_edges(result, positions_c_o)

    # The SHIPPED mesh's own topology: `result.mesh.positions` IS `mesh.positions` (nothing in
    # the pipeline ever touches it), so it welds to the same frame `positions_c_w` is in.
    topo_after = analyse_topology(result.mesh, flat_materials,
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
                       help="do not remove stray fragments and attached slivers")
    fix_p.add_argument("--out", default="data/output")
    fix_p.add_argument("--no-skp", dest="skp", action="store_false",
                       help="do not write the SketchUp file")
    fix_p.add_argument("--skp-dir", default=None,
                       help="folder that receives a copy of the latest .skp "
                            "(default: <repo root>/OBJ FIXED RESULT)")

    preview_p = sub.add_parser("preview-data", help="write the JSON preview/index.html reads")
    preview_p.add_argument("snapshot_dir")
    preview_p.add_argument("--no-solidify", dest="solidify", action="store_false",
                           help="do not close slabs with skirts and bottoms before fixing")
    preview_p.add_argument("--out", default="preview/data")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "fix":
        return cmd_fix(Path(args.snapshot_dir), Path(args.out), args.accept_slit,
                       solidify=args.solidify, fragments=args.fragments, skp=args.skp,
                       skp_dir=Path(args.skp_dir) if args.skp_dir else default_skp_dir())
    if args.command == "preview-data":
        return cmd_preview_data(Path(args.snapshot_dir), Path(args.out),
                                solidify=args.solidify)
    return 1


if __name__ == "__main__":
    sys.exit(main())
