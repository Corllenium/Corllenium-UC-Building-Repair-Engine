"""Ruling E3-R8 (job P2-E3, fix round 1): a site whose edits are all `remove` is charged a `deleted` sample only when
that sample lies on a face the site itself removed.

A removal can delete only its own faces' samples, so charging a neighbour for one (because the sample lies within
the neighbour's box grown by the judge's margin) rolled back innocent groups: on the three golden units 63, 19 and
134 E3 sites, every one of whose charges was such a box charge. Other failure kinds (covered, uv, look, ...) keep the
conservative attribution, and so do sites that add, cut or flip.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.fixes.pipeline import FixProfile
from engine.repair.kernel import repair_unit
from engine.repair.types import Edit, RepairContext, UnitState
from engine.site_judge import SiteJudge
from engine.tests.fixtures import build as B
from engine.tests.fixtures.build import _mesh, _quads
from engine.tests.test_validate_checks import _looks, _with_plate

PLATE = (14, 15)        # in `_cube_and_plate`: a plate standing 2 in from the cube, seen from outside
PARTITION = (12, 13)    # the cube's sealed partition, which nothing sees


@dataclass
class _Planned:
    name: str
    edits: list

    def plan(self, unit, ctx):
        return list(self.edits)


def _cube_and_plate():
    """`box_with_partition` (faces 0-13, 10 in cube) and a plate at x = 12 (faces 14-15), 2 in beside it: well within
    the judge's 24 in margin of the partition."""
    P = [[12.0, 0.0, 0.0], [12.0, 10.0, 0.0], [12.0, 10.0, 10.0], [12.0, 0.0, 10.0]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3)])
    return _with_plate(B.box_with_partition(), _mesh("plate", P, uvs, fv, fvt, face_material=fm))


def _remove(faces, site):
    return Edit(engine="E3", kind="remove", faces=tuple(faces), new_faces=None, new_points=None, site=site,
                reason="test", evidence={})


def test_only_the_remove_only_site_that_deleted_a_seen_sample_is_rolled_back():
    mesh = _cube_and_plate()
    judge = SiteJudge(_looks(*mesh.materials))                       # the owner's margin, 24 in
    unit = UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=FixProfile(), decider=None, validator=judge)
    result = repair_unit(unit, ctx, engines=[_Planned("E3", [_remove(PLATE, 0), _remove(PARTITION, 1)])],
                         validate_sites=True)
    (check,) = result.checks
    rolled = {row["site"]: row for row in check["rolled_back"]}
    assert set(rolled) == {0}, "the partition's site lies in the plate's box but deleted nothing"
    assert "deleted" in rolled[0]["reasons"] and rolled[0]["how"]["touched"] > 0
    assert [sorted(e.faces) for e in result.kept] == [list(PARTITION)]
    assert check["final"] == "PASS"


def test_a_failure_of_another_kind_keeps_the_box_charge():
    """A second plate (faces 16-17, material m1) lies exactly on the first: removing the m0 plate leaves another look
    at its samples' depth, a `look` failure (the Validator's `replaced`), not `deleted`. That kind keeps today's
    conservative attribution, so the partition's remove-only site, within the plate's box, is charged too."""
    import dataclasses
    base = _cube_and_plate()
    twin = dataclasses.replace(base, face_v=np.vstack([base.face_v, base.face_v[list(PLATE)]]),
                               face_vt=np.vstack([base.face_vt, base.face_vt[list(PLATE)]]),
                               face_vn=np.vstack([base.face_vn, base.face_vn[list(PLATE)]]),
                               face_material=np.concatenate([base.face_material, [1, 1]]),
                               face_line=np.arange(1, base.n_faces + 3, dtype=np.int64), materials=["m0", "m1"])
    judge = SiteJudge(_looks(*twin.materials))
    unit = UnitState(mesh=twin, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=FixProfile(), decider=None, validator=judge)
    result = repair_unit(unit, ctx, engines=[_Planned("E3", [_remove(PLATE, 0), _remove(PARTITION, 1)])],
                         validate_sites=True)
    rolled = {row["site"]: row for row in result.checks[0]["rolled_back"]}
    assert "deleted" not in rolled[0]["reasons"] and rolled[0]["reasons"], rolled[0]["reasons"]
    assert set(rolled) == {0, 1}, "a look failure still charges the neighbour whose box holds it"
    assert rolled[1]["how"] == {"touched": 0, "box": rolled[1]["charged"], "cover": 0}
