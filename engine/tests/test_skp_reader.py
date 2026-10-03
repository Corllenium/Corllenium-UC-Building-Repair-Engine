"""`engine.io.skp_reader`: a read-only walk of a SketchUp model through SketchUp's own C API.

Every test that needs `SketchUpAPI.dll` takes the `sketchup` fixture, which SKIPS with the reason
when the API cannot be loaded here. The static checks (no save call is bound) need no SketchUp and
run everywhere."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from engine.fixes.merge import merge_regions
from engine.io import skp_reader
from engine.io.skp_writer import SketchUpUnavailable, write_skp
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import bare_top_quad, slab_with_hole
from engine.tests.skp_scene import build_scene, rotation_z, scaling, square, translation


@pytest.fixture
def sketchup():
    """Skip, saying why, when this machine has no usable SketchUp C API."""
    try:
        skp_reader.load_api()
    except SketchUpUnavailable as exc:
        pytest.skip(f"SketchUp C API unavailable: {exc}")


def _write_triangles(tmp_path, mesh, name="model"):
    """`mesh` written by the project's own writer with every triangle as its own face."""
    path = tmp_path / f"{name}.skp"
    rings, region = {}, np.full(mesh.n_faces, -1, np.int64)
    write_skp(mesh, rings, region, analyse_topology(mesh), {}, path)
    return path


# ------------------------------------------------------------------------------ no save call


def test_the_reader_binds_no_save_call():
    bound = {*skp_reader._REQUIRED, *skp_reader._OPTIONAL}
    assert bound, "the binding tables are empty"
    assert [n for n in bound if "save" in n.lower()] == []
    assert [n for n in dir(skp_reader) if "save" in n.lower()] == []
    assert "SaveToFile" not in Path(skp_reader.__file__).read_text(encoding="utf-8")


def test_the_loaded_api_has_no_save_call_bound(sketchup):
    api = skp_reader.load_api()
    assert api._fn, "nothing was bound"
    assert [n for n in api._fn if "save" in n.lower()] == []


# ------------------------------------------------------------------------ the writer's models


def test_two_triangles_read_back_with_the_right_face_count_and_area(tmp_path, sketchup):
    path = _write_triangles(tmp_path, bare_top_quad(size=40.0))      # a 40 x 40 quad, 2 triangles
    walk = skp_reader.walk_skp(path)
    root = walk["root"]
    assert (root["faces"], root["tris"]) == (2, 2)
    assert root["area"] == pytest.approx(1600.0, abs=1e-6)
    assert root["bbox"] == [[0.0, 0.0, 0.0], [40.0, 40.0, 0.0]]
    assert root["children"] == []


def test_a_face_with_a_hole_counts_the_triangles_a_triangulation_needs(tmp_path, sketchup):
    mesh = slab_with_hole()                              # 100 x 100 with a 20 x 20 hole
    merged = merge_regions(mesh, analyse_topology(mesh))
    path = tmp_path / "holed.skp"
    write_skp(merged.mesh, merged.rings, merged.face_region, analyse_topology(merged.mesh), {}, path)
    root = skp_reader.walk_skp(path)["root"]
    assert (root["faces"], root["tris"]) == (1, 8)
    assert root["area"] == pytest.approx(100.0 * 100.0 - 20.0 * 20.0, abs=1e-6)


# ------------------------------------------------------------------- groups and their transforms


def _child(node, name):
    [child] = [c for c in node["children"] if c["name"] == name]
    return child


def _world(matrix, points):
    """`points` moved by the 4 x 4 `matrix`, worked out here and not by the reader."""
    pts = np.asarray(points, float)
    return pts @ matrix[:3, :3].T + matrix[:3, 3]


def test_a_group_is_a_child_node_with_its_own_faces_in_world_coordinates(tmp_path, sketchup):
    path = tmp_path / "g.skp"
    build_scene(path, {"groups": [{"name": "G", "transform": translation(10, 20, 30),
                                   "faces": [square(0, 0, 0, 10)]}]})
    root = skp_reader.walk_skp(path)["root"]
    assert (root["faces"], root["bbox"], root["area"]) == (0, None, 0.0)
    g = _child(root, "G")
    assert (g["kind"], g["definition"], g["faces"], g["tris"]) == ("group", None, 1, 2)
    assert g["area"] == pytest.approx(100.0)
    np.testing.assert_allclose(g["bbox"], [[10, 20, 30], [20, 30, 30]], atol=1e-9)


def test_the_world_box_and_area_agree_with_sketchups_own_answers(tmp_path, sketchup):
    """A group turned a quarter about z and moved: the box stays exact, so SketchUp's own bounds
    and `SUFaceGetAreaWithTransform` are the oracle for the reader's convention."""
    path = tmp_path / "r.skp"
    built = build_scene(path, {"groups": [{
        "name": "R", "transform": translation(100, 0, 5) @ rotation_z(90),
        "faces": [square(1, 2, 0, 10), square(-5, 0, 3, 4, "xz")]}]})
    g = _child(skp_reader.walk_skp(path)["root"], "R")
    np.testing.assert_allclose(g["bbox"], built["bounds"]["R"], atol=1e-9)
    np.testing.assert_allclose(g["bbox"], [[88, -5, 5], [100, 11, 12]], atol=1e-9)
    assert g["area"] == pytest.approx(built["areas"]["R"]) == pytest.approx(116.0)
    assert g["faces"] == 2


def test_nested_groups_compose_their_transforms(tmp_path, sketchup):
    outer_t, inner_t = translation(100, 0, 0), translation(0, 5, 0) @ rotation_z(90)
    face = square(1, 2, 0, 10)
    path = tmp_path / "n.skp"
    built = build_scene(path, {"groups": [{"name": "Outer", "transform": outer_t, "groups": [
        {"name": "Inner", "transform": inner_t, "faces": [face]}]}]})
    outer = _child(skp_reader.walk_skp(path)["root"], "Outer")
    inner = _child(outer, "Inner")
    moved = _world(outer_t @ inner_t, face)
    np.testing.assert_allclose(inner["bbox"], [moved.min(axis=0), moved.max(axis=0)], atol=1e-9)
    # the outer group holds nothing but the inner one: SketchUp's bounds for it are the inner box
    np.testing.assert_allclose(inner["bbox"], built["bounds"]["Outer"], atol=1e-9)
    assert (outer["faces"], outer["bbox"], outer["area"]) == (0, None, 0.0)


def test_a_uniform_scale_multiplies_area_by_its_square(tmp_path, sketchup):
    path = tmp_path / "s.skp"
    built = build_scene(path, {"groups": [{"name": "S", "transform": scaling(3),
                                           "faces": [square(0, 0, 0, 10)]}]})
    g = _child(skp_reader.walk_skp(path)["root"], "S")
    assert g["area"] == pytest.approx(900.0) == pytest.approx(built["areas"]["S"])
    np.testing.assert_allclose(g["bbox"], [[0, 0, 0], [30, 30, 0]], atol=1e-9)


def test_a_non_uniform_scale_scales_each_face_by_its_own_plane(tmp_path, sketchup):
    """Doubling x doubles a face in the xy or xz plane and leaves one in the yz plane alone."""
    path = tmp_path / "u.skp"
    built = build_scene(path, {"groups": [{"name": "N", "transform": scaling(2, 1, 1), "faces": [
        square(0, 0, 0, 10, "xy"), square(0, 0, 0, 10, "xz"), square(0, 0, 0, 10, "yz")]}]})
    g = _child(skp_reader.walk_skp(path)["root"], "N")
    assert g["area"] == pytest.approx(200.0 + 200.0 + 100.0)
    assert g["area"] == pytest.approx(built["areas"]["N"])


def test_a_mirrored_group_keeps_its_area_and_its_box_is_mirrored(tmp_path, sketchup):
    path = tmp_path / "m.skp"
    built = build_scene(path, {"groups": [{"name": "M", "transform": scaling(-1, 1, 1),
                                           "faces": [square(1, 0, 0, 10)]}]})
    g = _child(skp_reader.walk_skp(path)["root"], "M")
    assert g["area"] == pytest.approx(100.0)
    np.testing.assert_allclose(g["bbox"], [[-11, 0, 0], [-1, 10, 0]], atol=1e-9)
    np.testing.assert_allclose(g["bbox"], built["bounds"]["M"], atol=1e-9)


# ------------------------------------------------------------------------ component instances


def test_a_component_instance_is_a_node_that_names_its_definition(tmp_path, sketchup):
    path = tmp_path / "i.skp"
    build_scene(path, {"definitions": {"Def": {"faces": [square(0, 0, 0, 10)]}},
                       "instances": [{"definition": "Def", "name": "I1",
                                      "transform": translation(10, 0, 0)},
                                     {"definition": "Def", "transform": translation(0, 10, 0)}]})
    root = skp_reader.walk_skp(path)["root"]
    assert len(root["children"]) == 2
    named, unnamed = _child(root, "I1"), _child(root, "")
    assert (named["kind"], named["definition"], named["faces"]) == ("instance", "Def", 1)
    assert (unnamed["kind"], unnamed["definition"], unnamed["faces"]) == ("instance", "Def", 1)
    np.testing.assert_allclose(named["bbox"], [[10, 0, 0], [20, 10, 0]], atol=1e-9)
    np.testing.assert_allclose(unnamed["bbox"], [[0, 10, 0], [10, 20, 0]], atol=1e-9)
    assert named["area"] == pytest.approx(100.0)


def test_an_instance_inside_a_group_composes_both_transforms(tmp_path, sketchup):
    path = tmp_path / "ig.skp"
    build_scene(path, {"definitions": {"Def": {"faces": [square(0, 0, 0, 10)]}}, "groups": [
        {"name": "G", "transform": translation(0, 0, 50) @ scaling(2), "instances": [
            {"definition": "Def", "name": "I", "transform": translation(10, 0, 0)}]}]})
    inst = _child(_child(skp_reader.walk_skp(path)["root"], "G"), "I")
    np.testing.assert_allclose(inst["bbox"], [[20, 0, 50], [40, 20, 50]], atol=1e-9)
    assert inst["area"] == pytest.approx(400.0)


def test_one_definition_walked_twice_gives_each_instance_its_own_numbers(tmp_path, sketchup):
    path = tmp_path / "twice.skp"
    build_scene(path, {"definitions": {"Def": {"faces": [square(0, 0, 0, 10)]}}, "instances": [
        {"definition": "Def", "name": "A", "transform": scaling(1)},
        {"definition": "Def", "name": "B", "transform": scaling(2)}]})
    root = skp_reader.walk_skp(path)["root"]
    assert _child(root, "A")["area"] == pytest.approx(100.0)
    assert _child(root, "B")["area"] == pytest.approx(400.0)


# ------------------------------------------------------------- the transform maths, no SketchUp


def _faces(normals, areas, points):
    faces = object.__new__(skp_reader._Faces)
    faces.count, faces.areas = len(areas), np.array(areas, float)
    faces.normals, faces.points = np.array(normals, float), np.array(points, float)
    return faces


def test_area_scale_is_det_times_the_length_of_the_transformed_normal():
    faces = _faces([[0, 0, 1], [0, 1, 0], [1, 0, 0]], [10.0, 10.0, 10.0], [[0, 0, 0], [1, 2, 3]])
    area, bbox = faces.in_world(np.diag([2.0, 3.0, 5.0, 1.0]))
    assert area == pytest.approx(10 * 6 + 10 * 10 + 10 * 15)       # xy: 2*3, xz: 2*5, yz: 3*5
    assert bbox == [[0.0, 0.0, 0.0], [2.0, 6.0, 15.0]]


def test_a_flattened_transform_has_no_area_instead_of_failing():
    faces = _faces([[0, 0, 1]], [10.0], [[0, 0, 0], [1, 1, 0]])
    area, bbox = faces.in_world(np.diag([1.0, 1.0, 0.0, 1.0]))
    assert area == 0.0 and bbox == [[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]]
