"""E4 `allow_growth` (MAIN-INFRA-E4-MERGE-20261023, E5 follow-up): a region whose new triangle count exceeds its input
face count is refused `grew` unless the engine was told to allow growth. Measured motive: on the 7F E4 trial 123 of
275 kept regions grew (2 input faces -> 8-14 triangles) because `keep_all` rings carry many vertices."""
from __future__ import annotations

import dataclasses

import numpy as np

from engine.repair.engines import e4_merge
from engine.repair.engines.e4_merge import E4Merge
from engine.tests.test_e4_merge import TEXTURED, _plan, t_quad


def _patch(monkeypatch):
    """`merge_regions` replaced: the merge of `t_quad` comes back as a 6-triangle fan over the SAME six vertices with
    the input's own UV rows -- the area is kept (800), the UV map is the one affine map, nothing moved; only the count
    grew from 4 to 6."""
    real = e4_merge.merge_regions

    def fan_of_six(mesh, topo, flat, **kw):
        result = real(mesh, topo, flat, **kw)
        fv = np.array([[0, 1, 4], [4, 1, 5], [5, 1, 2], [0, 4, 3], [4, 5, 3], [5, 2, 3]], np.int64)
        fvt = np.array([[0, 1, 4], [4, 1, 7], [7, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11]], np.int64)
        out = dataclasses.replace(result.mesh, uvs=mesh.uvs, face_v=fv, face_vt=fvt,
                                  face_vn=np.full((6, 3), -1, np.int64), face_material=np.zeros(6, np.int64),
                                  face_line=np.ones(6, np.int64))
        return dataclasses.replace(result, mesh=out, source_faces=[[0, 1, 2, 3]] * 6, face_region=np.zeros(6, np.int64))

    monkeypatch.setattr(e4_merge, "merge_regions", fan_of_six)


def test_a_region_that_grows_is_refused_grew_by_default(monkeypatch):
    _patch(monkeypatch)
    edits, engine = _plan(t_quad())
    assert edits == []
    (refused,) = engine.report["refused"]
    assert refused["reason"] == "grew" and refused["faces_before"] == 4 and refused["faces_after"] == 6
    assert "6" in refused["detail"] and "4" in refused["detail"]
    assert engine.report["allow_growth"] is False


def test_allow_growth_lets_an_area_keeping_grown_region_through(monkeypatch):
    _patch(monkeypatch)
    edits, engine = _plan(t_quad(), E4Merge(flatness=TEXTURED, allow_growth=True))
    assert len(edits) == 1 and len(edits[0].new_faces) == 6 and edits[0].faces == (0, 1, 2, 3)
    assert edits[0].evidence["area_after"] == edits[0].evidence["area_before"] and engine.report["refused"] == []
    assert engine.report["allow_growth"] is True


def test_the_real_merge_of_the_fixtures_never_grows():
    edits, engine = _plan(t_quad())
    assert len(edits) == 1 and len(edits[0].new_faces) == 2 and engine.report["refused"] == []
