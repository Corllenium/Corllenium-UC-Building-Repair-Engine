"""F2: the visual QA sheet -- 12 views and 9 close-ups of the fixed mesh, shaded, with the edges
SketchUp will draw and hidden lines removed."""
import numpy as np
from PIL import Image

from engine.guard.qa_render import polygon_edges, qa_file_names, write_qa_sheet
from engine.tests.fixtures.build import _mesh, box_with_partition

_EDGE = (40, 40, 46)


def _edge_pixels(path) -> int:
    img = np.asarray(Image.open(path).convert("RGB"))
    return int((img == np.array(_EDGE, np.uint8)).all(axis=2).sum())


def _quad_and_triangle():
    """A quad (faces 0-1, sharing the diagonal 0-2) and a separate triangle (face 2)."""
    P = [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0], [20, 0, 0], [30, 0, 0], [20, 10, 0]]
    fv = [[0, 1, 2], [0, 2, 3], [4, 5, 6]]
    return _mesh("quad_and_triangle", P, [[0, 0]] * 7, fv, fv)


# --------------------------------------------------------------------------- which edges


def test_a_merged_region_draws_its_loop_and_not_its_triangulation_diagonal():
    m = _quad_and_triangle()
    ring = {"outer": np.array([0, 1, 2, 3]), "inners": []}
    edges = polygon_edges(m, {0: ring, 1: ring})          # the SAME dict, as merge emits it

    got = {tuple(e) for e in edges.tolist()}
    assert got == {(0, 1), (1, 2), (2, 3), (0, 3),           # the quad's outline
                   (4, 5), (5, 6), (4, 6)}                   # the copied-through triangle
    assert (0, 2) not in got                                 # never the diagonal


def test_a_region_with_a_hole_draws_its_inner_loop_too():
    """The SketchUp export carries holes even though the ngon OBJ cannot, so the sheet draws
    them: that is the edge a person will see."""
    m = _quad_and_triangle()
    ring = {"outer": np.array([0, 1, 2, 3]), "inners": [np.array([4, 6, 5])]}
    got = {tuple(e) for e in polygon_edges(m, {0: ring, 1: ring}).tolist()}
    assert {(4, 6), (5, 6), (4, 5)} <= got


def test_a_rolled_back_merge_draws_every_triangle_edge():
    got = {tuple(e) for e in polygon_edges(_quad_and_triangle(), {}).tolist()}
    assert (0, 2) in got and len(got) == 8


# ------------------------------------------------------------------- hidden lines removed


def test_an_edge_behind_a_surface_is_not_drawn():
    """A 100 in plate at z = 10 over a 20 in quad at z = 0, drawing only the small quad's four
    edges. From above the plate hides them completely; from below nothing does."""
    P = [[0, 0, 10], [100, 0, 10], [100, 100, 10], [0, 100, 10],
         [40, 40, 0], [60, 40, 0], [60, 60, 0], [40, 60, 0]]
    fv = [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]]
    m = _mesh("plate_over_quad", P, [[0, 0]] * 8, fv, fv)
    small = np.array([[4, 5], [5, 6], [6, 7], [4, 7]])

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        paths = {p.stem: p for p in write_qa_sheet(m, small, tmp, size=(200, 120))}
        assert _edge_pixels(paths["top"]) == 0
        # the quad's 80 in perimeter at 100 * 1.06 / 120 = 0.88 in per pixel: about 90 pixels
        assert 80 <= _edge_pixels(paths["bottom"]) <= 100


# ------------------------------------------------------------------------- the files


def test_the_sheet_is_21_files_even_when_a_close_up_slice_is_empty(tmp_path):
    """`box_with_partition`'s vertices sit at x = 0, 5 and 10, so a thirds slice can hold fewer
    than 3 of them; that slice falls back to the whole-model frame rather than being skipped."""
    written = write_qa_sheet(box_with_partition(), None, tmp_path, size=(160, 100))
    assert [p.name for p in written] == qa_file_names()
    assert len(written) == 21
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(qa_file_names())


def test_the_sheet_is_deterministic(tmp_path):
    a = write_qa_sheet(box_with_partition(), None, tmp_path / "a", size=(160, 100))
    b = write_qa_sheet(box_with_partition(), None, tmp_path / "b", size=(160, 100))
    for pa, pb in zip(a, b):
        assert pa.read_bytes() == pb.read_bytes(), pa.name


def test_an_edge_just_under_a_flat_surface_is_not_drawn():
    """The same scene with the small quad only 2 in under the plate. A flat depth tolerance of
    three pixels (2.65 in at this size) let it bleed through the plate as if it were drawn ON
    it -- measured on file A's top view, about 6,000 edge samples 0.5 to 3.3 in behind the
    surface they were drawn over. The tolerance is now the depth change the HIT surface's own
    slope makes across a pixel, which for a plate facing the camera is almost nothing."""
    P = [[0, 0, 2], [100, 0, 2], [100, 100, 2], [0, 100, 2],
         [40, 40, 0], [60, 40, 0], [60, 60, 0], [40, 60, 0]]
    fv = [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]]
    m = _mesh("plate_just_over_quad", P, [[0, 0]] * 8, fv, fv)
    small = np.array([[4, 5], [5, 6], [6, 7], [4, 7]])

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        paths = {p.stem: p for p in write_qa_sheet(m, small, tmp, size=(200, 120))}
        assert _edge_pixels(paths["top"]) == 0
        assert 80 <= _edge_pixels(paths["bottom"]) <= 100


def test_an_edge_on_a_steep_visible_surface_is_still_drawn():
    """The other side of the same rule: an edge lying ON a surface seen at a steep angle must
    survive, although its pixel's ray meets that surface up to half a pixel away and so, on a
    steep surface, at a noticeably different depth. A 60 degree roof's ridge-to-eave edges from
    straight above: every one of them is in view."""
    P = [[0, 0, 0], [100, 0, 0], [100, 50, 86.6], [0, 50, 86.6],
         [0, 100, 0], [100, 100, 0]]
    fv = [[0, 1, 2], [0, 2, 3], [3, 2, 5], [3, 5, 4]]
    m = _mesh("steep_roof", P, [[0, 0]] * 6, fv, fv)
    ridge_and_eaves = np.array([[0, 1], [3, 2], [4, 5], [0, 3], [1, 2], [3, 4], [2, 5]])

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        paths = {p.stem: p for p in write_qa_sheet(m, ridge_and_eaves, tmp, size=(200, 120))}
        # 3 edges of 100 in across and 4 of 50 in in plan, at ~0.88 in per pixel: ~565 px
        assert _edge_pixels(paths["top"]) > 450
