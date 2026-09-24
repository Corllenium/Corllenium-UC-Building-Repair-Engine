"""`engine.io.skp_writer`: the fixed mesh written as a SketchUp model through SketchUp's own C API,
and read back through the same API.

Every test that needs `SketchUpAPI.dll` takes the `sketchup` fixture, which SKIPS with the reason
when the API cannot be loaded here. The error paths for a missing or wrong DLL need no SketchUp
and run everywhere."""
from __future__ import annotations

import os
import re
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from engine.fixes.merge import merge_regions
from engine.io import skp_writer
from engine.io.mtl import MtlMaterial
from engine.io.skp_writer import (SketchUpUnavailable, check_skp_validity, read_skp,
                                  read_skp_summary, write_skp)
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import (back_to_back_pair, bare_top_quad, creased_pair, cube,
                                         grid_slab, slab_with_hole, slab_with_lifted_corner,
                                         slab_with_wall, split_double_layer, staggered_slabs,
                                         t_junction_seam_strip, t_junction_strip,
                                         two_region_quad, two_slabs_sharing_border)
from engine.topo.edges import EDGE_OPEN, EDGE_REAL, EDGE_TJUNCTION


@pytest.fixture
def sketchup():
    """Skip, saying why, when this machine has no usable SketchUp C API."""
    try:
        skp_writer.load_api()
    except SketchUpUnavailable as exc:
        pytest.skip(f"SketchUp C API unavailable: {exc}")


def _merged(mesh):
    r = merge_regions(mesh, analyse_topology(mesh))
    return r.mesh, r.rings, r.face_region


def _copied_through(mesh):
    """Every face copied through unmerged: what `fix_object` ships when the merge is rolled back."""
    return mesh, {}, np.full(mesh.n_faces, -1, np.int64)


def _write(tmp_path, mesh, rings, face_region, name="model", mtl=None, tex_dir=None, **kw):
    path = tmp_path / f"{name}.skp"
    report = write_skp(mesh, rings, face_region, analyse_topology(mesh), mtl or {}, path,
                       tex_dir=tex_dir, **kw)
    return path, report


def _texture(tmp_path, name="stone.png"):
    """A small non-uniform PNG in `<tmp>/tex/`, the layout a run directory has."""
    tex = tmp_path / "tex"
    tex.mkdir(exist_ok=True)
    img = np.zeros((16, 32, 3), np.uint8)
    img[..., 0] = (np.arange(32) * 8)[None, :]
    img[..., 1] = (np.arange(16) * 16)[:, None]
    Image.fromarray(img).save(tex / name)
    return tex


_STONE = {"m0": MtlMaterial("m0", ["Kd 0.5 0.5 0.5", "map_Kd tex/stone.png"], map_kd="tex/stone.png")}


def _mesh_uv_at(mesh) -> dict[tuple, np.ndarray]:
    """`{position: uv}` taken from the mesh's own triangle corners."""
    out: dict[tuple, np.ndarray] = {}
    for f in range(mesh.n_faces):
        for v, t in zip(mesh.face_v[f], mesh.face_vt[f]):
            out.setdefault(tuple(mesh.positions[v].tolist()), mesh.uvs[t])
    return out


# --------------------------------------------------------------------------- the DLL itself


def test_missing_dll_raises_sketchup_unavailable_naming_the_path(tmp_path):
    mesh, rings, region = _copied_through(bare_top_quad())
    missing = tmp_path / "nowhere" / "SketchUpAPI.dll"
    with pytest.raises(SketchUpUnavailable, match=re.escape(str(missing))):
        write_skp(mesh, rings, region, analyse_topology(mesh), {}, tmp_path / "x.skp",
                  dll_path=missing)
    assert not (tmp_path / "x.skp").exists()


def test_dll_path_comes_from_the_environment_when_not_given(tmp_path, monkeypatch):
    missing = tmp_path / "env" / "SketchUpAPI.dll"
    monkeypatch.setenv("FIXER_SKETCHUP_DLL", str(missing))
    assert skp_writer.resolve_dll_path() == missing
    with pytest.raises(SketchUpUnavailable, match=re.escape(str(missing))):
        skp_writer.load_api()


def test_dll_path_defaults_to_sketchup_2026(monkeypatch):
    monkeypatch.delenv("FIXER_SKETCHUP_DLL", raising=False)
    assert skp_writer.resolve_dll_path() == Path(
        r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUpAPI.dll")


@pytest.mark.skipif(sys.platform != "win32", reason="needs a Windows system DLL to load")
def test_a_dll_without_the_sketchup_symbols_is_unavailable_and_says_which():
    kernel32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "kernel32.dll"
    if not kernel32.exists():
        pytest.skip(f"{kernel32} not present")
    with pytest.raises(SketchUpUnavailable, match="SUInitialize"):
        skp_writer.load_api(kernel32)


def test_ctypes_is_imported_only_by_the_skp_writer():
    engine_root = Path(skp_writer.__file__).resolve().parents[1]
    users = sorted(p.relative_to(engine_root).as_posix() for p in engine_root.rglob("*.py")
                   if re.search(r"^\s*(import ctypes|from ctypes)", p.read_text(encoding="utf-8"),
                                re.M))
    assert users == ["io/skp_writer.py"]


# --------------------------------------------------------------------------------- faces


def test_merged_grid_slab_is_one_face_with_four_hard_edges(tmp_path, sketchup):
    mesh, rings, region = _merged(grid_slab())
    path, report = _write(tmp_path, mesh, rings, region)
    s = read_skp_summary(path)
    assert (s["faces"], s["edges"], s["soft_edges"], s["loops_with_inners"]) == (1, 4, 0, 0)
    assert (report["faces"], report["polygon_faces"], report["faces_missing"]) == (1, 1, 0)


def test_slab_with_hole_is_one_face_whose_hole_is_an_inner_loop(tmp_path, sketchup):
    mesh, rings, region = _merged(slab_with_hole())
    path, report = _write(tmp_path, mesh, rings, region)
    s = read_skp_summary(path)
    assert (s["faces"], s["loops_with_inners"], s["edges"], s["soft_edges"]) == (1, 1, 8, 0)
    assert report["fallback_regions"] == [] and report["inner_loops"] == 1
    [face] = read_skp(path).faces
    [hole] = face.inners
    assert sorted(map(tuple, hole[:, :2].tolist())) == [(40.0, 40.0), (40.0, 60.0),
                                                        (60.0, 40.0), (60.0, 60.0)]


def test_holed_region_is_written_as_its_triangles_when_the_dll_has_no_inner_loops(
        tmp_path, sketchup, monkeypatch):
    real_load = skp_writer.load_api

    def without_inner_loops(dll_path=None):
        api = real_load(dll_path)
        monkeypatch.setattr(api, "has_inner_loops", False)
        return api

    monkeypatch.setattr(skp_writer, "load_api", without_inner_loops)
    mesh, rings, region = _merged(slab_with_hole())
    path, report = _write(tmp_path, mesh, rings, region)
    assert report["fallback_regions"] == [{"region": 0, "reason": "no_inner_loop_api"}]
    s = read_skp_summary(path)
    assert (s["faces"], s["loops_with_inners"]) == (8, 0)
    # the 8 outline edges stay hard, the 8 triangulation diagonals are hidden
    assert (s["edges"], s["soft_edges"], report["gridline_edges_softened"]) == (16, 8, 8)


def test_merged_cube_is_six_faces_and_twelve_edges(tmp_path, sketchup):
    mesh, rings, region = _merged(cube())
    path, _ = _write(tmp_path, mesh, rings, region)
    s = read_skp_summary(path)
    assert (s["faces"], s["edges"], s["soft_edges"]) == (6, 12, 0)


def test_zero_area_face_is_skipped_not_written(tmp_path, sketchup):
    mesh, rings, region = _copied_through(t_junction_strip())   # face 6 is a zero-area stitch
    path, report = _write(tmp_path, mesh, rings, region)
    assert report["degenerate_faces_skipped"] == 1
    s = read_skp_summary(path)
    assert (s["faces"], s["edges_without_face"]) == (6, 0)


def test_writing_over_an_existing_file_replaces_it(tmp_path, sketchup):
    path, _ = _write(tmp_path, *_merged(cube()))
    path, _ = _write(tmp_path, *_merged(grid_slab()))
    assert read_skp_summary(path)["faces"] == 1


# --------------------------------------------------------------------------- hidden edges


def test_three_degree_crease_is_two_faces_sharing_one_soft_edge(tmp_path, sketchup):
    mesh, rings, region = _merged(creased_pair(angle_deg=3.0))
    path, report = _write(tmp_path, mesh, rings, region)
    s = read_skp_summary(path)
    assert (s["faces"], s["edges"], s["soft_edges"], s["smooth_edges"]) == (2, 7, 1, 1)
    assert (report["soft_edges"], report["gridline_edges_softened"],
            report["unmatched_edges"]) == (1, 0, 0)
    [hinge] = [e for e in read_skp(path).edges if e.soft]
    assert sorted([hinge.start.tolist(), hinge.end.tolist()]) == [[0.0, 24000.0, 0.0],
                                                                 [0.0, 24000.0, 120.0]]


def test_coplanar_copied_through_triangles_share_a_soft_edge(tmp_path, sketchup):
    mesh, rings, region = _copied_through(bare_top_quad())
    path, report = _write(tmp_path, mesh, rings, region)
    s = read_skp_summary(path)
    assert (s["faces"], s["edges"], s["soft_edges"], s["smooth_edges"]) == (2, 5, 1, 1)
    assert (report["gridline_edges_softened"], report["soft_edges"],
            report["unmatched_edges"]) == (1, 0, 0)


# ---------------------------------------------------------------------------- orientation


def test_face_wound_against_its_triangles_is_reversed_and_keeps_its_texture(tmp_path, sketchup):
    mesh, rings, region = _merged(grid_slab())
    backwards = {"outer": rings[0]["outer"][::-1].copy(), "inners": []}
    rings = {f: backwards for f in rings}        # one shared object per region, as the merge does
    path, report = _write(tmp_path, mesh, rings, region, mtl=_STONE, tex_dir=_texture(tmp_path))
    assert report["reversed_faces"] == 1
    [face] = read_skp(path).faces
    assert np.allclose(face.normal, [0.0, 0.0, 1.0])     # the triangles' side, not the loop's
    expected = _mesh_uv_at(mesh)
    for p, front, back in zip(face.outer, face.front_uv, face.back_uv):
        assert np.allclose(front, expected[tuple(p.tolist())], atol=1e-9)
        assert np.allclose(back, expected[tuple(p.tolist())], atol=1e-9)


def test_region_off_its_plane_is_written_as_triangles(tmp_path, sketchup):
    mesh, rings, region = _merged(slab_with_lifted_corner())
    path, report = _write(tmp_path, mesh, rings, region)
    [entry] = report["fallback_regions"]
    assert (entry["region"], entry["reason"]) == (0, "nonplanar") and entry["deviation"] > 1e-3
    s = read_skp_summary(path)
    assert (s["faces"], s["edges"], s["soft_edges"]) == (3, 7, 2)
    assert check_skp_validity(path)["changed"] is False


def test_polygon_sketchups_own_save_splits_is_rebuilt_as_soft_edged_triangles(tmp_path,
                                                                              sketchup):
    """Why the planarity fallback exists. With the pre-check switched off the region goes in as
    ONE face, and `SUModelSaveToFile` itself splits it into triangles joined by HARD edges --
    visible lines. The writer sees that after the save and rebuilds the region as its own
    triangles, whose diagonals it can hide."""
    mesh, rings, region = _merged(slab_with_lifted_corner())
    path, report = _write(tmp_path, mesh, rings, region, plane_tol=np.inf)
    assert report["fallback_regions"] == [{"region": 0, "reason": "split_by_sketchup"}]
    s = read_skp_summary(path)
    assert (s["faces"], s["edges"], s["soft_edges"]) == (3, 7, 2)
    assert (report["faces"], report["edges"]) == (s["faces"], s["edges"])


def test_clean_merged_model_gives_sketchups_own_check_nothing_to_fix(tmp_path, sketchup):
    path, _ = _write(tmp_path, *_merged(slab_with_hole()))
    assert check_skp_validity(path)["changed"] is False


# ------------------------------------------------------------------------------ materials


def test_one_sketchup_material_per_obj_material_with_its_kd_colour_on_both_sides(tmp_path,
                                                                                 sketchup):
    mesh, rings, region = _merged(two_slabs_sharing_border())
    mtl = {"m0": MtlMaterial("m0", ["Kd 0.2 0.4 0.6"]), "m1": MtlMaterial("m1", ["Kd 1 0 0"])}
    path, report = _write(tmp_path, mesh, rings, region, mtl=mtl)
    assert read_skp_summary(path)["materials"] == len(mesh.materials) == 2
    model = read_skp(path)
    colours = {m.name: (m.textured, tuple(m.color[:3])) for m in model.materials}
    assert colours == {"m0": (False, (51, 102, 153)), "m1": (False, (255, 0, 0))}
    assert sorted((f.front_material, f.back_material) for f in model.faces) == [("m0", "m0"),
                                                                               ("m1", "m1")]
    assert report["material_path"] == "geometry_input"


def test_textured_material_is_positioned_with_the_mesh_uvs_on_both_sides(tmp_path, sketchup):
    mesh, rings, region = _merged(grid_slab())
    path, report = _write(tmp_path, mesh, rings, region, mtl=_STONE, tex_dir=_texture(tmp_path))
    assert report["materials"] == [{"name": "m0", "texture": "stone.png", "color": None}]
    model = read_skp(path)
    assert model.materials[0].textured
    expected = _mesh_uv_at(mesh)
    [face] = model.faces
    for p, front, back in zip(face.outer, face.front_uv, face.back_uv):
        assert np.allclose(front, expected[tuple(p.tolist())], atol=1e-9)
        assert np.allclose(back, expected[tuple(p.tolist())], atol=1e-9)


def test_texture_missing_from_the_run_directory_falls_back_to_the_kd_colour(tmp_path, sketchup):
    mesh, rings, region = _merged(grid_slab())
    path, report = _write(tmp_path, mesh, rings, region, mtl=_STONE, tex_dir=tmp_path / "tex")
    assert report["materials"] == [{"name": "m0", "texture": None, "color": [128, 128, 128]}]
    assert not read_skp(path).materials[0].textured


def test_region_whose_uvs_are_not_one_affine_map_is_reported(tmp_path, sketchup):
    mesh, rings, region = _merged(grid_slab())
    _, report = _write(tmp_path, mesh, rings, region, name="clean")
    assert report["uv_residual_regions"] == []
    bent = replace(mesh, uvs=mesh.uvs.copy())
    bent.uvs[mesh.face_vt[0, 0]] += [0.05, 0.0]      # one corner off the region's affine map
    _, report = _write(tmp_path, bent, rings, region, name="bent")
    [entry] = report["uv_residual_regions"]
    assert entry["region"] == 0 and entry["residual"] > 1e-3


# ------------------------------------------------------------------------ units, determinism


def test_bbox_is_the_mesh_bbox_in_world_inches(tmp_path, sketchup):
    mesh, rings, region = _merged(creased_pair())          # sits at y = 24,000 in
    path, _ = _write(tmp_path, mesh, rings, region)
    lo, hi = mesh.bbox()
    assert read_skp_summary(path)["bbox"] == [lo.tolist(), hi.tolist()]


def test_writing_twice_gives_the_same_model(tmp_path, sketchup):
    mesh, rings, region = _merged(slab_with_hole())
    a, report_a = _write(tmp_path, mesh, rings, region, name="a")
    b, report_b = _write(tmp_path, mesh, rings, region, name="b")
    assert read_skp_summary(a) == read_skp_summary(b)
    report_a.pop("path"), report_b.pop("path")
    assert report_a == report_b


# ------------------------------------------------------------------ lines inside flat surfaces
# Decided on SketchUp's OWN model after the fill, whatever the topology called the edge.


_VISIBLE_CLASSES = ("visible_border_edges", "visible_angled_edges", "visible_shape_edges",
                    "visible_material_borders", "visible_nonmanifold_edges",
                    "visible_lines_inside_surfaces")


def _edge(model, p, q):
    """The one edge of a read-back model between points `p` and `q`, either way round."""
    p, q = np.asarray(p, float), np.asarray(q, float)
    [edge] = [e for e in model.edges if (np.allclose(e.start, p) and np.allclose(e.end, q))
              or (np.allclose(e.start, q) and np.allclose(e.end, p))]
    return edge


def _visible(model):
    return sorted(sorted([e.start.tolist(), e.end.tolist()]) for e in model.edges if not e.soft)


def test_coplanar_triangles_of_two_regions_share_a_soft_edge(tmp_path, sketchup):
    mesh, rings, region = _copied_through(two_region_quad())
    # the topology keeps the diagonal: it borders two regions (a texture seam), so it is not 1
    assert sorted(analyse_topology(mesh).edge_class.tolist()) == [EDGE_REAL] + [EDGE_OPEN] * 4
    path, report = _write(tmp_path, mesh, rings, region)
    diagonal = _edge(read_skp(path), (0, 0, 0), (40, 40, 0))
    assert diagonal.faces == 2 and diagonal.soft and diagonal.smooth
    assert (report["coplanar_edges_softened"], report["gridline_edges_softened"],
            report["soft_only_edges"]) == (1, 0, 0)
    assert (report["visible_border_edges"], report["visible_lines_inside_surfaces"]) == (4, 0)


def test_coplanar_pair_wound_against_each_other_is_soft_but_not_smooth(tmp_path, sketchup):
    """Smoothing averages the two faces' normals across the edge, and opposite normals average
    to nothing: a flat pair wound against each other is hidden with `soft` alone."""
    mesh, rings, region = _copied_through(two_region_quad(flip=True))
    path, report = _write(tmp_path, mesh, rings, region)
    model = read_skp(path)
    assert float(model.faces[0].normal @ model.faces[1].normal) == pytest.approx(-1.0)
    diagonal = _edge(model, (0, 0, 0), (40, 40, 0))
    assert diagonal.soft and not diagonal.smooth
    assert (report["coplanar_edges_softened"], report["soft_only_edges"]) == (1, 1)


def test_coplanar_triangles_of_two_materials_keep_the_line_between_them(tmp_path, sketchup):
    mesh, rings, region = _copied_through(two_region_quad(material=1))
    path, report = _write(tmp_path, mesh, rings, region)
    assert not _edge(read_skp(path), (0, 0, 0), (40, 40, 0)).soft
    assert report["coplanar_edges_softened"] == 0
    assert (report["visible_material_borders"], report["visible_border_edges"]) == (1, 4)


def test_t_junction_lines_inside_a_strip_are_soft_and_its_outline_is_not(tmp_path, sketchup):
    mesh, rings, region = _copied_through(t_junction_seam_strip())
    topo = analyse_topology(mesh)
    along = [e for e, (a, b) in enumerate(topo.table.edges)
             if topo.positions_w[a][1] == topo.positions_w[b][1] == 10.0]
    assert sorted(topo.edge_class[along].tolist()) == [EDGE_TJUNCTION] * 3   # never hidden by it
    path, report = _write(tmp_path, mesh, rings, region)
    model = read_skp(path)
    for p, q in [((0, 10, 0), (20, 10, 0)), ((0, 10, 0), (10, 10, 0)), ((10, 10, 0), (20, 10, 0))]:
        line = _edge(model, p, q)
        assert line.faces == 1 and line.soft and line.smooth
    outline = [((0, 0, 0), (20, 0, 0)), ((20, 0, 0), (20, 10, 0)), ((20, 10, 0), (20, 20, 0)),
               ((20, 20, 0), (10, 20, 0)), ((10, 20, 0), (0, 20, 0)), ((0, 20, 0), (0, 10, 0)),
               ((0, 10, 0), (0, 0, 0))]
    assert _visible(model) == sorted(sorted([[float(c) for c in p], [float(c) for c in q]])
                                     for p, q in outline)
    assert report["tjunction_lines_softened"] == 3
    assert (report["visible_border_edges"], report["visible_lines_inside_surfaces"]) == (7, 0)


def test_line_where_a_wall_stands_on_a_slab_stays_visible(tmp_path, sketchup):
    mesh, rings, region = _merged(slab_with_wall())
    path, report = _write(tmp_path, mesh, rings, region)
    foot = _edge(read_skp(path), (0, 50, 0), (30, 50, 0))
    assert foot.faces == 1 and not foot.soft
    assert (report["coplanar_edges_softened"], report["tjunction_lines_softened"]) == (0, 0)
    assert report["visible_angled_edges"] == 1


def test_coplanar_line_a_wall_stands_on_stays_visible(tmp_path, sketchup):
    """An edge on an angled face is where that face meets the surface: never hidden, even when
    it also lies inside a flat surface of one material."""
    mesh, rings, region = _copied_through(two_region_quad(wall=True))
    path, report = _write(tmp_path, mesh, rings, region)
    diagonal = _edge(read_skp(path), (0, 0, 0), (40, 40, 0))
    assert diagonal.faces == 2 and not diagonal.soft
    assert report["coplanar_edges_softened"] == 0 and report["visible_angled_edges"] == 2


def test_t_junction_lines_a_wall_stands_on_stay_visible(tmp_path, sketchup):
    mesh, rings, region = _copied_through(t_junction_seam_strip(wall=True))
    path, report = _write(tmp_path, mesh, rings, region)
    model = read_skp(path)
    for p, q in [((0, 10, 0), (20, 10, 0)), ((0, 10, 0), (10, 10, 0)), ((10, 10, 0), (20, 10, 0))]:
        assert not _edge(model, p, q).soft
    assert report["tjunction_lines_softened"] == 0 and report["visible_angled_edges"] == 4


def test_real_outline_of_a_slab_of_copied_through_triangles_stays_visible(tmp_path, sketchup):
    mesh, rings, region = _copied_through(grid_slab(nx=4, ny=4))
    path, report = _write(tmp_path, mesh, rings, region)
    s = read_skp_summary(path)
    assert (s["edges"] - s["soft_edges"], report["visible_border_edges"]) == (16, 16)
    assert report["tjunction_lines_softened"] == 0


def test_outline_that_only_partly_runs_along_a_neighbour_stays_visible(tmp_path, sketchup):
    """A's top edge and B's bottom edge each lie inside the surface over half their length and
    are the real outline over the other half. Hiding them would hide that outline, so both stay
    and are reported as lines inside surfaces: only splitting them in the mesh removes them."""
    mesh, rings, region = _copied_through(staggered_slabs())
    path, report = _write(tmp_path, mesh, rings, region)
    model = read_skp(path)
    assert not _edge(model, (0, 10, 0), (20, 10, 0)).soft
    assert not _edge(model, (10, 10, 0), (30, 10, 0)).soft
    assert len(_visible(model)) == 8 and report["tjunction_lines_softened"] == 0
    assert (report["visible_lines_inside_surfaces"], report["visible_border_edges"]) == (2, 6)


def test_edge_two_back_to_back_faces_both_end_on_stays_visible(tmp_path, sketchup):
    mesh, rings, region = _copied_through(back_to_back_pair())
    path, report = _write(tmp_path, mesh, rings, region)
    shared = _edge(read_skp(path), (0, 0, 0), (40, 0, 0))
    assert shared.faces == 2 and not shared.soft
    assert report["coplanar_edges_softened"] == 0
    # the shared edge and the two vertical sides are outline; each triangle's sloped side runs
    # through the other layer for part of its length, and is outline for the rest
    assert (report["visible_border_edges"], report["visible_lines_inside_surfaces"]) == (3, 2)


def test_outline_of_a_split_double_layer_stays_visible(tmp_path, sketchup):
    """Each bottom edge lies on the other layer's boundary along its whole length, but every
    face is on the same side of it: nothing lies beyond, so it is the outline. The upper
    triangles' sloped sides run across the quad, which lies on both sides of them: hidden."""
    mesh, rings, region = _copied_through(split_double_layer())
    path, report = _write(tmp_path, mesh, rings, region)
    model = read_skp(path)
    for p, q in [((0, 0, 0), (20, 0, 0)), ((0, 0, 0), (10, 0, 0)), ((10, 0, 0), (20, 0, 0))]:
        assert not _edge(model, p, q).soft
    for p, q in [((0, 0, 0), (5, 4, 0)), ((5, 4, 0), (10, 0, 0)), ((10, 0, 0), (15, 4, 0)),
                 ((15, 4, 0), (20, 0, 0))]:
        assert _edge(model, p, q).soft
    assert (report["tjunction_lines_softened"], report["visible_border_edges"]) == (4, 6)


@pytest.mark.parametrize("build, merged", [
    (cube, True), (grid_slab, False), (slab_with_hole, True), (two_slabs_sharing_border, True),
    (slab_with_wall, True), (staggered_slabs, False), (t_junction_seam_strip, False),
    (two_region_quad, False), (back_to_back_pair, False), (split_double_layer, False)])
def test_every_visible_edge_is_in_exactly_one_class(tmp_path, sketchup, build, merged):
    mesh = build()
    path, report = _write(tmp_path, *(_merged(mesh) if merged else _copied_through(mesh)))
    s = read_skp_summary(path)
    assert report["edges"] == s["edges"]
    assert sum(report[k] for k in _VISIBLE_CLASSES) == (
        s["edges"] - s["soft_edges"] - s["edges_without_face"])
