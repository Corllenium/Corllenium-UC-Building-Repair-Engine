# engine/tests/test_e1_loose.py
import pytest
import numpy as np

from engine.tests.fixtures.build import slab_with_debris, printed
from engine.repair.engines.e1_loose import E1Loose
from engine.repair.types import UnitState, RepairContext, apply_edits, face_keys
from engine.fixes.pipeline import FixProfile


def test_e1_engine_shape():
    m = printed(slab_with_debris())
    engine = E1Loose(viewpoints=[])
    unit = UnitState(mesh=m, topo=None, looks={}, viewpoints=None)
    ctx = RepairContext(profile=FixProfile(accept_fragments=True), decider=None, validator=None)

    edits = engine.plan(unit, ctx)
    assert len(edits) > 0
    assert all(e.engine == "E1" and e.kind == "remove" for e in edits)

    # each site has its own edit
    sites = [e.site for e in edits]
    assert len(sites) == len(set(sites))

    # removed faces include the 4 debris faces: 32, 33, 34, 35
    removed_faces = set(f for e in edits for f in e.faces)
    assert {32, 33, 34, 35}.issubset(removed_faces)

    # apply_edits removes all 4 debris faces, keeping exactly the 32 slab faces
    after_mesh, _ = apply_edits(m, edits)
    assert after_mesh.n_faces == 32

    # verify removed face keys match exactly the 4 debris faces
    all_keys = face_keys(m, {})
    debris_keys = sorted(all_keys[f] for f in (32, 33, 34, 35))
    edits_keys = sorted(all_keys[f] for e in edits for f in e.faces)
    assert debris_keys == edits_keys
