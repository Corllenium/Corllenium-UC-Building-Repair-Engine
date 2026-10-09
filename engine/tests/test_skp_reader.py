"""`engine.io.skp_reader`: a read-only walk of a SketchUp model through SketchUp's own C API.

Every test that needs `SketchUpAPI.dll` takes the `sketchup` fixture, which SKIPS with the reason
when the API cannot be loaded here. The static checks (no save call is bound) need no SketchUp and
run everywhere."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
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


def _with_w(matrix, w):
    """`matrix` with `w` in its last element: how SketchUp stores a uniform scale of `1 / w`."""
    out = np.array(matrix, float)
    out[3, 3] = w
    return out


def test_a_transform_that_keeps_its_scale_in_w_is_applied_as_sketchup_applies_it(tmp_path, sketchup):
    """SketchUp divides the whole map by `w`: a group with `w = 0.5` and a move of 10 is twice as big and
    moved 20, and so is an instance. SketchUp's own bounds are the oracle."""
    path = tmp_path / "w.skp"
    built = build_scene(path, {"definitions": {"Def": {"faces": [square(0, 0, 0, 10)]}}, "groups": [
        {"name": "W", "transform": _with_w(translation(10, 0, 0), 0.5), "faces": [square(0, 0, 0, 10)]}],
        "instances": [{"definition": "Def", "name": "I", "transform": _with_w(np.eye(4), 0.5)}]})
    root = skp_reader.walk_skp(path)["root"]
    group, instance = _child(root, "W"), _child(root, "I")
    np.testing.assert_allclose(built["bounds"]["W"], [[20, 0, 0], [40, 20, 0]], atol=1e-9)    # the oracle
    np.testing.assert_allclose(group["bbox"], built["bounds"]["W"], atol=1e-9)
    assert group["area"] == pytest.approx(built["areas"]["W"]) == pytest.approx(400.0)
    np.testing.assert_allclose(instance["bbox"], built["bounds"]["I"], atol=1e-9)
    np.testing.assert_allclose(instance["bbox"], [[0, 0, 0], [20, 20, 0]], atol=1e-9)
    assert instance["area"] == pytest.approx(400.0)


def test_transforms_with_w_compose_like_the_scales_they_stand_for(tmp_path, sketchup):
    """An outer scale of 2 (`w = 0.5`) around a group moved 5 and scaled 2 (`w = 0.5`): x becomes 4x + 20."""
    path = tmp_path / "nw.skp"
    built = build_scene(path, {"groups": [{"name": "Outer", "transform": _with_w(np.eye(4), 0.5), "groups": [
        {"name": "Inner", "transform": _with_w(translation(5, 0, 0), 0.5), "faces": [square(0, 0, 0, 10)]}]}]})
    inner = _child(_child(skp_reader.walk_skp(path)["root"], "Outer"), "Inner")
    np.testing.assert_allclose(inner["bbox"], [[20, 0, 0], [60, 40, 0]], atol=1e-9)
    np.testing.assert_allclose(inner["bbox"], built["bounds"]["Outer"], atol=1e-9)
    assert inner["area"] == pytest.approx(16 * 100.0)


def _transformation(values):
    t = skp_reader._Transformation()
    t.values[:] = values
    return t


def test_a_matrix_is_divided_by_its_w_and_left_with_a_last_row_of_0_0_0_1():
    m = skp_reader._matrix(_transformation([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 10, 0, 0, 0.5]))
    np.testing.assert_allclose(m, [[2, 0, 0, 20], [0, 2, 0, 0], [0, 0, 2, 0], [0, 0, 0, 1]])
    plain = skp_reader._matrix(_transformation([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 10, 0, 0, 1]))
    np.testing.assert_allclose(plain, [[1, 0, 0, 10], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])


@pytest.mark.parametrize("values, why", [
    ([1, 0, 0, 0.001, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], "a perspective part"),
    ([1, 0, 0, 0, 0, 1, 0, 0.5, 0, 0, 1, 0, 0, 0, 0, 1], "a perspective part"),
    ([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0], "w of zero")])
def test_a_matrix_that_is_not_affine_is_refused_instead_of_misread(values, why):
    with pytest.raises(skp_reader.SketchUpError, match="not an affine transformation"):
        skp_reader._matrix(_transformation(values))


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


# ----------------------------------------------------------------- hidden things are left out


def test_a_hidden_group_is_skipped_and_counted(tmp_path, sketchup):
    path = tmp_path / "h.skp"
    build_scene(path, {"groups": [{"name": "Shown", "faces": [square(0, 0, 0, 10)]},
                                  {"name": "Hidden", "hidden": True,
                                   "faces": [square(0, 0, 0, 10)]}]})
    walk = skp_reader.walk_skp(path)
    root = walk["root"]
    assert [c["name"] for c in root["children"]] == ["Shown"]
    assert root["skipped"] == [{"kind": "group", "name": "Hidden", "definition": None,
                                "reason": "hidden"}]
    assert walk["totals"] == {"groups": 1, "instances": 0, "faces": 1, "tris": 2,
                              "hidden_nodes": 1, "layer_hidden_nodes": 0, "hidden_faces": 0,
                              "layer_hidden_faces": 0}


def test_a_group_on_a_tag_that_is_off_is_skipped_and_counted(tmp_path, sketchup):
    path = tmp_path / "t.skp"
    build_scene(path, {"layers": {"Off": False, "On": True}, "groups": [
        {"name": "A", "layer": "Off", "faces": [square(0, 0, 0, 10)]},
        {"name": "B", "layer": "On", "faces": [square(0, 0, 0, 10)]}]})
    walk = skp_reader.walk_skp(path)
    root = walk["root"]
    assert [c["name"] for c in root["children"]] == ["B"]
    assert root["skipped"] == [{"kind": "group", "name": "A", "definition": None,
                                "reason": "layer"}]
    assert (walk["totals"]["layer_hidden_nodes"], walk["totals"]["hidden_nodes"]) == (1, 0)
    assert walk["layers_bound"] is True


def test_the_contents_of_a_hidden_group_are_not_walked(tmp_path, sketchup):
    path = tmp_path / "hi.skp"
    build_scene(path, {"groups": [{"name": "H", "hidden": True, "groups": [
        {"name": "Inner", "faces": [square(0, 0, 0, 10)]}]}]})
    walk = skp_reader.walk_skp(path)
    assert walk["root"]["children"] == []
    assert (walk["totals"]["groups"], walk["totals"]["faces"], walk["totals"]["hidden_nodes"]) == (
        0, 0, 1)


def test_a_hidden_instance_is_skipped_and_named_with_its_definition(tmp_path, sketchup):
    path = tmp_path / "hinst.skp"
    build_scene(path, {"definitions": {"Def": {"faces": [square(0, 0, 0, 10)]}}, "instances": [
        {"definition": "Def", "name": "I", "hidden": True}]})
    root = skp_reader.walk_skp(path)["root"]
    assert root["children"] == []
    assert root["skipped"] == [{"kind": "instance", "name": "I", "definition": "Def",
                                "reason": "hidden"}]


def test_a_hidden_face_is_left_out_of_every_number(tmp_path, sketchup):
    path = tmp_path / "hf.skp"
    build_scene(path, {"groups": [{"name": "G", "faces": [
        {"points": square(100, 100, 100, 50), "hidden": True}, square(0, 0, 0, 10)]}]})
    g = _child(skp_reader.walk_skp(path)["root"], "G")
    assert (g["faces"], g["hidden_faces"], g["tris"]) == (1, 1, 2)
    assert g["area"] == pytest.approx(100.0)
    np.testing.assert_allclose(g["bbox"], [[0, 0, 0], [10, 10, 0]], atol=1e-9)


def test_a_face_on_a_tag_that_is_off_is_left_out_of_every_number(tmp_path, sketchup):
    path = tmp_path / "tf.skp"
    build_scene(path, {"layers": {"Off": False}, "groups": [{"name": "G", "faces": [
        {"points": square(100, 100, 100, 50), "layer": "Off"}, square(0, 0, 0, 10)]}]})
    walk = skp_reader.walk_skp(path)
    g = _child(walk["root"], "G")
    assert (g["faces"], g["layer_hidden_faces"], g["hidden_faces"]) == (1, 1, 0)
    assert g["area"] == pytest.approx(100.0)
    np.testing.assert_allclose(g["bbox"], [[0, 0, 0], [10, 10, 0]], atol=1e-9)
    assert walk["totals"]["layer_hidden_faces"] == 1


def test_tags_are_not_applied_when_the_dll_lacks_the_calls(tmp_path, sketchup, monkeypatch):
    path = tmp_path / "nl.skp"
    build_scene(path, {"layers": {"Off": False}, "groups": [
        {"name": "A", "layer": "Off", "faces": [square(0, 0, 0, 10)]}]})
    api = skp_reader.load_api()
    for name in ("SUDrawingElementGetLayer", "SULayerGetVisibility"):
        monkeypatch.delitem(api._fn, name)
    walk = skp_reader.walk_skp(path)
    assert walk["layers_bound"] is False
    assert [c["name"] for c in walk["root"]["children"]] == ["A"]      # not skipped, and says so


# ----------------------------------------------------- names, the file, and what is released


def test_names_are_read_as_utf8_text(tmp_path, sketchup):
    path = tmp_path / "u8.skp"
    build_scene(path, {"groups": [{"name": "Étage 2 – plan.obj", "faces": [square(0, 0, 0, 1)]}]})
    assert [c["name"] for c in skp_reader.walk_skp(path)["root"]["children"]] == [
        "Étage 2 – plan.obj"]


def _counted(monkeypatch, api, *names):
    """Wrap the bound calls `names` so each call is counted; returns `{name: calls}`."""
    calls = dict.fromkeys(names, 0)

    def wrap(name, real):
        def counted(*args):
            calls[name] += 1
            return real(*args)
        return counted

    for name in names:
        monkeypatch.setitem(api._fn, name, wrap(name, api._fn[name]))
    return calls


_PAIRS = ("SUStringCreate", "SUStringRelease", "SUModelCreateFromFile", "SUModelRelease")


def test_every_string_and_the_model_are_released(tmp_path, sketchup, monkeypatch):
    path = tmp_path / "rel.skp"
    build_scene(path, {"definitions": {"Def": {"faces": [square(0, 0, 0, 1)]}}, "groups": [
        {"name": "G", "groups": [{"name": "H", "faces": [square(0, 0, 0, 1)]}],
         "instances": [{"definition": "Def", "name": "I"}]}]})
    calls = _counted(monkeypatch, skp_reader.load_api(), *_PAIRS)
    skp_reader.walk_skp(path)
    assert calls["SUModelCreateFromFile"] == calls["SUModelRelease"] == 1
    assert calls["SUStringCreate"] == calls["SUStringRelease"] > 0


def test_a_walk_that_fails_half_way_still_releases_everything(tmp_path, sketchup, monkeypatch):
    path = tmp_path / "boom.skp"
    build_scene(path, {"groups": [{"name": "G", "faces": [square(0, 0, 0, 1)]}]})
    api = skp_reader.load_api()
    calls = _counted(monkeypatch, api, *_PAIRS)

    def boom(*args):
        raise skp_reader.SketchUpError("boom")

    monkeypatch.setitem(api._fn, "SUGroupGetTransform", boom)
    with pytest.raises(skp_reader.SketchUpError, match="boom"):
        skp_reader.walk_skp(path)
    assert calls["SUModelCreateFromFile"] == calls["SUModelRelease"] == 1
    assert calls["SUStringCreate"] == calls["SUStringRelease"]


def test_a_string_that_cannot_be_read_is_still_released(tmp_path, sketchup, monkeypatch):
    path = tmp_path / "str.skp"
    build_scene(path, {"groups": [{"name": "G", "faces": [square(0, 0, 0, 1)]}]})
    api = skp_reader.load_api()
    calls = _counted(monkeypatch, api, *_PAIRS)

    def boom(*args):
        raise skp_reader.SketchUpError("boom")

    monkeypatch.setitem(api._fn, "SUStringGetUTF8Length", boom)
    with pytest.raises(skp_reader.SketchUpError, match="boom"):
        skp_reader.walk_skp(path)
    assert calls["SUStringCreate"] == calls["SUStringRelease"] > 0
    assert calls["SUModelCreateFromFile"] == calls["SUModelRelease"] == 1


def test_the_file_is_only_read(tmp_path, sketchup):
    path = tmp_path / "ro.skp"
    build_scene(path, {"groups": [{"name": "G", "faces": [square(0, 0, 0, 1)]}]})
    before = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    path.chmod(stat.S_IREAD)                    # a read-only file opens, so nothing is written to it
    try:
        skp_reader.walk_skp(path)
    finally:
        path.chmod(stat.S_IREAD | stat.S_IWRITE)
    assert (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) == before


def test_a_missing_file_and_a_file_that_is_not_a_model_are_errors(tmp_path, sketchup):
    with pytest.raises(FileNotFoundError):
        skp_reader.walk_skp(tmp_path / "nope.skp")
    junk = tmp_path / "junk.skp"
    junk.write_bytes(b"this is not a SketchUp model")
    with pytest.raises(skp_reader.SketchUpError, match="SUModelCreateFromFile"):
        skp_reader.walk_skp(junk)


def test_a_missing_dll_is_unavailable_and_says_where(tmp_path):
    missing = tmp_path / "nowhere" / "SketchUpAPI.dll"
    with pytest.raises(SketchUpUnavailable, match=re.escape(str(missing))):
        skp_reader.walk_skp(tmp_path / "x.skp", dll_path=missing)


# --------------------------------------------------------------- how much memory is left to use


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' commit figures")
def test_available_commit_is_the_megabytes_the_machine_can_still_promise():
    free = skp_reader.available_commit_mb()
    assert isinstance(free, float) and 0 < free < 4 * 1024 * 1024        # under 4 TB, more than none


def test_off_windows_there_is_no_commit_figure_and_so_no_guard(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    assert skp_reader.available_commit_mb() is None
    assert skp_reader._peak_memory_mb() == (None, None)


# ---------------------------------------------------------------- the command that walks a file


def test_main_writes_the_walk_as_json(tmp_path, sketchup):
    path, out = tmp_path / "m.skp", tmp_path / "walk.json"
    build_scene(path, {"groups": [{"name": "G", "faces": [square(0, 0, 0, 10)]}]})
    assert skp_reader.main([str(path), "--out", str(out)]) == 0
    walk = json.loads(out.read_text(encoding="utf-8"))
    assert walk["root"]["children"][0]["name"] == "G"
    assert walk["totals"]["faces"] == 1 and walk["layers_bound"] is True
    assert walk["path"] == str(path)
    if sys.platform == "win32":
        assert walk["peak_working_set_mb"] > 1 and walk["peak_commit_mb"] > 1


def test_run_as_a_module_in_a_child_process(tmp_path, sketchup):
    """The way `engine.campus.skp_check` runs it: the SDK in a process that can be killed."""
    path, out = tmp_path / "c.skp", tmp_path / "walk.json"
    build_scene(path, {"groups": [{"name": "G", "faces": [square(0, 0, 0, 10)]}]})
    repo = Path(skp_reader.__file__).resolve().parents[2]
    done = subprocess.run([sys.executable, "-m", "engine.io.skp_reader", str(path), "--out", str(out)],
                          cwd=repo, env={**os.environ, "PYTHONPATH": str(repo)}, capture_output=True,
                          text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["root"]["children"][0]["faces"] == 1


def test_main_reports_a_bad_file_without_a_traceback(tmp_path, sketchup, capsys):
    junk, out = tmp_path / "junk.skp", tmp_path / "walk.json"
    junk.write_bytes(b"this is not a SketchUp model")
    assert skp_reader.main([str(junk), "--out", str(out)]) == 2
    assert "SUModelCreateFromFile" in capsys.readouterr().err
    assert not out.exists()


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


# ------------------------------------------------------------------------------ the master (P1-H1b item 3)


def test_walk_skp_refuses_the_master_itself_before_it_loads_anything(tmp_path, monkeypatch):
    """Defence in depth: the reader refuses the owner's master even when called without skp_check."""
    master = tmp_path / "UC" / "02-SKETCHUP" / "current"
    master.mkdir(parents=True)
    (master / "M - CHECKPOINT-17.skp").write_bytes(b"skp-bytes")
    monkeypatch.setattr(skp_reader, "load_api",
                        lambda *a, **k: pytest.fail("the API was loaded before the master was refused"))
    with pytest.raises(ValueError, match="master"):
        skp_reader.walk_skp(master / "M - CHECKPOINT-17.skp")
