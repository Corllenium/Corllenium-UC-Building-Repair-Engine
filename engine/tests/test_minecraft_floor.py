from dataclasses import replace

import numpy as np
import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

from engine.io.minecraft_floor import Frame, FloorFormatError, parse_floor, write_floor


QUAD = """mtllib source.mtl
g facade
v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
vt 0.1 0.2
vt 0.9 0.2
vt 0.9 0.8
vt 0.1 0.8
usemtl brick
f 1/1 2/2 3/3 4/4
"""


def test_textured_quad_keeps_corners_winding_material_and_provenance():
    floor = parse_floor(QUAD, name="test")
    mesh = floor.mesh
    assert mesh.n_faces == 2
    assert mesh.materials == ["brick"]
    assert mesh.units == "source_units_unverified"
    np.testing.assert_array_equal(floor.triangle_polygon, [0, 0])
    for face, local in enumerate(floor.triangle_corners):
        for corner, source_corner in enumerate(local):
            v, t, n = floor.polygons[0].corners[source_corner]
            assert (mesh.face_v[face, corner], mesh.face_vt[face, corner], mesh.face_vn[face, corner]) == (v, t, n)
    tri = mesh.positions[mesh.face_v]
    assert (np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])[:, 2] > 0).all()
    assert floor.polygons[0].group == "facade"
    assert floor.polygons[0].line == 12
    assert mesh.face_material.tolist() == [0, 0]


def test_negative_indices_resolve_at_face_record():
    floor = parse_floor(QUAD.replace("f 1/1 2/2 3/3 4/4", "f -4/-4 -3/-3 -2/-2 -1/-1"))
    assert floor.polygons[0].corners == ((0, 0, -1), (1, 1, -1), (2, 2, -1), (3, 3, -1))


@pytest.mark.parametrize("reverse", [False, True])
def test_concave_polygon_covers_exact_source_region(reverse):
    points = [(0, 0), (3, 0), (3, 3), (1.5, 1), (0, 3)]
    indices = list(range(1, 6))[:: -1 if reverse else 1]
    text = "\n".join(f"v {x} {y} 0" for x, y in points) + "\nf " + " ".join(map(str, indices))
    floor = parse_floor(text)
    triangles = [Polygon(floor.mesh.positions[t][:, :2]) for t in floor.mesh.face_v]
    assert len(triangles) == 3
    assert unary_union(triangles).symmetric_difference(Polygon(points)).area == 0
    assert sum(t.area for t in triangles) == Polygon(points).area


@pytest.mark.parametrize("face", ["0/1 2/2 3/3", "1/1 2/2 5/3", "1/0 2/2 3/3", "1/1 2/2 3/5", "1//1 2//1 3//1", "-5/1 2/2 3/3"])
def test_invalid_references_fail(face):
    with pytest.raises(FloorFormatError, match="line"):
        parse_floor(QUAD.rsplit("f ", 1)[0] + "f " + face)


@pytest.mark.parametrize("vertices,face", [
    ([(0, 0, 0), (2, 2, 0), (0, 2, 0), (2, 0, 0)], "1 2 3 4"),
    ([(0, 0, 0), (2, 0, 0), (2, 2, .01), (0, 2, 0)], "1 2 3 4"),
    ([(0, 0, 0), (1, 0, 0), (2, 0, 0)], "1 2 3"),
    ([(0, 0, 0), (2, 0, 0), (2, 2, 0)], "1 2 3 1"),
])
def test_unsupported_polygon_fails_instead_of_dropping(vertices, face):
    text = "\n".join("v " + " ".join(map(str, p)) for p in vertices) + "\nf " + face
    with pytest.raises(FloorFormatError):
        parse_floor(text)


def test_nonfinite_and_nonface_geometry_rejected():
    for text in [QUAD.replace("v 0 0 0", "v nan 0 0"), QUAD + "l 1 2\n"]:
        with pytest.raises(FloorFormatError):
            parse_floor(text)


def test_frame_requires_physical_and_axis_evidence():
    with pytest.raises(ValueError, match="evidence"):
        Frame(inches_per_unit=1, evidence="")
    with pytest.raises(ValueError):
        Frame(inches_per_unit=-1, evidence="fixture")


def test_explicit_y_up_frame_is_invertible_and_keeps_winding():
    floor = parse_floor(QUAD)
    frame = Frame(inches_per_unit=5000 / 127, evidence="synthetic known metre fixture; Y-up")
    normalized = floor.in_frame(frame)
    np.testing.assert_allclose(frame.to_source(normalized.mesh.positions), floor.mesh.positions, rtol=0, atol=1e-15)
    np.testing.assert_array_equal(normalized.mesh.face_v, floor.mesh.face_v)
    np.testing.assert_array_equal(normalized.mesh.uvs, floor.mesh.uvs)
    assert np.linalg.det(frame.matrix[:3, :3]) > 0
    assert normalized.mesh.units == "inches"


def test_readback_preserves_high_precision_uvs_polygons_and_triangles(tmp_path):
    floor = parse_floor(QUAD.replace("0.1", "0.12345678901234566"))
    for polygons in [False, True]:
        path = tmp_path / ("ngon.obj" if polygons else "fixed.obj")
        write_floor(floor, path, polygons=polygons)
        back = parse_floor(path.read_text())
        np.testing.assert_array_equal(back.mesh.positions, floor.mesh.positions)
        np.testing.assert_array_equal(back.mesh.uvs, floor.mesh.uvs)
        np.testing.assert_array_equal(back.mesh.face_v, floor.mesh.face_v)
        np.testing.assert_array_equal(back.mesh.face_vt, floor.mesh.face_vt)
        assert back.mesh.materials == floor.mesh.materials
        if polygons:
            assert back.polygons[0].corners == floor.polygons[0].corners


def test_partial_polygon_export_cannot_restore_removed_triangle(tmp_path):
    floor = parse_floor(QUAD)
    with pytest.raises(ValueError, match="whole polygon"):
        write_floor(floor, tmp_path / "bad.obj", polygons=True, keep_triangles=np.array([True, False]))
