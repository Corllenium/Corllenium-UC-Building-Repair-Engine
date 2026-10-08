"""P1-K2: the observe-only repair kernel.

Item 1 -- `fix_object` is a loop over its seven stages, a pure refactor: running the stages by hand
gives the very same `FixResult` (compared through the report.json bytes `engine.cli` writes and the
shipped mesh's arrays).
"""
from __future__ import annotations

import json

import numpy as np
import pytest

import engine.fixes.pipeline as fix_pipeline
from engine.fixes.pipeline import FixProfile, fix_object
from engine.tests.fixtures.build import (bare_top_quad, box_with_partition, gridded_box, printed,
                                         slab_with_strays, stacked_duplicate_slab)

_FAST = FixProfile(guard_size=(120, 80), n_dirs=32)
#: the fragment tests' loosened cap (engine/tests/test_fragments.py): the fixture views are tiny
_STRAYS = FixProfile(guard_size=(120, 80), n_dirs=32, solidify=False, fragment_removed_cap=5e-3)


def _reversed_gridded_box():
    m = gridded_box(4, 2.5)
    m.face_v[10] = m.face_v[10][::-1]
    return m


#: (name, mesh builder, profile): between them every stage changes something
FIXTURES = [
    ("box_with_partition", box_with_partition, _FAST),          # hidden faces, merge
    ("reversed_gridded_box", _reversed_gridded_box, _FAST),      # a flip, merge
    ("stacked_duplicate_slab", lambda: stacked_duplicate_slab(nx=3, ny=3), _FAST),  # overlap
    ("slab_with_strays", lambda: printed(slab_with_strays()), _STRAYS),  # fragments, slivers
    ("bare_top_quad", bare_top_quad, _FAST),                    # solidify adds skirts and a bottom
]


def _report_bytes(tmp_path, mesh, result, profile) -> bytes:
    from engine import cli
    obj = tmp_path / "input.obj"
    obj.write_bytes(b"same input for both")
    return json.dumps(cli._build_report(mesh.name, obj, mesh, result, profile), indent=2).encode()


def _same_mesh_arrays(a, b):
    for field in ("positions", "uvs", "normals", "face_v", "face_vt", "face_vn", "face_material",
                  "face_line"):
        assert np.array_equal(getattr(a, field), getattr(b, field)), field
    assert a.materials == b.materials


# ----------------------------------------------------------------------- item 1: the stages


def test_fix_object_is_the_seven_stages_in_order():
    assert [name for name, _ in fix_pipeline.FIX_STAGES] == [
        "solidify", "hidden", "slit", "fragments", "orientation", "overlap", "merge"]


@pytest.mark.parametrize("name, build, profile", FIXTURES, ids=[f[0] for f in FIXTURES])
def test_running_the_stages_by_hand_gives_fix_objects_result(tmp_path, name, build, profile):
    mesh = build()
    expected = fix_object(mesh, {}, profile)

    state = fix_pipeline.start_fix(mesh, {}, profile)
    for _, stage in fix_pipeline.FIX_STAGES:
        state = stage(state)
    by_hand = fix_pipeline.finish_fix(state)

    assert _report_bytes(tmp_path, mesh, by_hand, profile) == _report_bytes(tmp_path, mesh, expected, profile)
    _same_mesh_arrays(by_hand.mesh, expected.mesh)
    _same_mesh_arrays(by_hand.reference_mesh, expected.reference_mesh)
    assert [s.tolist() for s in by_hand.source_faces] == [s.tolist() for s in expected.source_faces]
