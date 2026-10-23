from dataclasses import replace

import numpy as np
import pytest

from engine.fixes import pipeline
from engine.fixes.precut_cleanup import CoverageError, cleanup, verify_exact_coverage
from engine.io.minecraft_floor import parse_floor


TRI = """v 0 0 0
v 2 0 0
v 0 2 0
vt 0 0
vt 1 0
vt 0 1
usemtl stone
f 1/1 2/2 3/3
"""


def test_forbidden_pipeline_operations_are_never_called(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden pipeline call")
    for name in ["fix_object", "start_fix", "stage_solidify", "stage_hidden", "stage_slit",
                 "stage_fragments", "stage_orientation", "stage_overlap", "stage_merge", "finish_fix"]:
        monkeypatch.setattr(pipeline, name, forbidden)
    result = cleanup(parse_floor(TRI).mesh)
    assert result.mesh.n_faces == 1
    assert result.disabled == ("solidify", "holes", "material_preparation", "recolor", "fragments",
                               "slits", "normal_unification", "partial_overlap", "hidden", "merge")


def test_noop_is_exact_including_all_corner_attributes():
    mesh = parse_floor(TRI).mesh
    result = cleanup(mesh, stages=())
    for name in ["positions", "uvs", "normals", "face_v", "face_vt", "face_vn", "face_material", "face_line"]:
        np.testing.assert_array_equal(getattr(result.mesh, name), getattr(mesh, name))
    assert not result.removed_to_survivor


def test_unknown_and_unsafe_requests_rejected_before_any_stage():
    mesh = parse_floor(TRI).mesh
    for stages in [("unknown",), ("exact_duplicates", "solidify"), ("hidden",), ("merge",)]:
        with pytest.raises(ValueError, match="stage"):
            cleanup(mesh, stages=stages)


def test_exact_duplicate_removal_uses_values_and_cyclic_winding():
    text = TRI + "v 0 0 0\nv 2 0 0\nv 0 2 0\nvt 0 0\nvt 1 0\nvt 0 1\nf 5/5 6/6 4/4\n"
    mesh = parse_floor(text).mesh
    result = cleanup(mesh)
    assert result.mesh.n_faces == 1
    assert result.removed_to_survivor == {1: 0}
    assert verify_exact_coverage(mesh, result.mesh)["exact_coverage"]


@pytest.mark.parametrize("suffix", [
    "f 3/3 2/2 1/1\n",  # opposite winding
    "usemtl glass\nf 1/1 2/2 3/3\n",  # different appearance
    "f 1/2 2/3 3/1\n",  # different UV
    "v 1 0 0\nf 1/1 4/2 3/3\n",  # partial overlap
])
def test_ambiguous_sheets_and_partial_overlaps_are_retained(suffix):
    mesh = parse_floor(TRI + suffix).mesh
    assert cleanup(mesh).mesh.n_faces == 2


@pytest.mark.parametrize("role", ["facade", "covered_floor", "stair_riser", "narrow_trim"])
def test_protected_surface_removal_fails_regardless_of_role(role):
    mesh = parse_floor(TRI, name=role).mesh
    empty = replace(mesh, face_v=mesh.face_v[:0], face_vt=mesh.face_vt[:0], face_vn=mesh.face_vn[:0],
                    face_material=mesh.face_material[:0], face_line=mesh.face_line[:0])
    with pytest.raises(CoverageError, match="missing"):
        verify_exact_coverage(mesh, empty)


@pytest.mark.parametrize("kind", ["uv", "material", "normal", "coordinate", "opening_fill"])
def test_damage_is_rejected(kind):
    before = parse_floor(TRI).mesh
    if kind == "uv":
        after = replace(before, uvs=before.uvs + .01)
    elif kind == "material":
        after = replace(before, materials=["different"])
    elif kind == "normal":
        after = replace(before, face_v=before.face_v[:, ::-1], face_vt=before.face_vt[:, ::-1])
    elif kind == "coordinate":
        after = replace(before, positions=before.positions + .001)
    else:
        after = parse_floor(TRI + "v 2 2 0\nf 2/2 4/1 3/3\n").mesh
    with pytest.raises(CoverageError):
        verify_exact_coverage(before, after)


def test_nonfinite_corner_cannot_be_accepted_as_duplicate():
    before = parse_floor(TRI).mesh
    with pytest.raises(CoverageError):
        cleanup(replace(before, uvs=np.full_like(before.uvs, np.nan)))
