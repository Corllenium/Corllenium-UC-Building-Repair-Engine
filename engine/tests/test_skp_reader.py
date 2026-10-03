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
