"""Run only checked E3 and prove the surviving fresh-source triangle indices."""
import hashlib

import numpy as np

from engine.fixes.pipeline import FixProfile
from engine.fixes.remove import remove_faces
from engine.repair.engines.e3_hidden import E3Hidden
from engine.repair.kernel import repair_unit
from engine.repair.types import RepairContext, UnitState
from engine.site_judge import SiteJudge


def _source_digest(mesh):
    digest = hashlib.sha256()
    for name in ('positions', 'uvs', 'normals', 'face_v', 'face_vt', 'face_vn', 'face_material', 'face_line'):
        values = np.ascontiguousarray(getattr(mesh, name))
        digest.update(f'{name}:{values.dtype.str}:{values.shape};'.encode())
        digest.update(values.tobytes())
    digest.update(repr((mesh.materials, mesh.mtllib, mesh.units, mesh.physical_quanta,
                        mesh.coord_decimals, mesh.sig_digits)).encode())
    return digest.digest()


def source_survivors(before, outcome):
    if outcome.result is not None or outcome.stages or len(outcome.checks) != 1:
        raise ValueError('only one checked non-legacy E3 stage is allowed')
    check = outcome.checks[0]
    if (check.get('stage') != 'E3' or check.get('engine') != 'E3'
            or check.get('legacy') is not False or check.get('rollback') is not True):
        raise ValueError('E3 site checks and rollback are required')
    planned = {id(item) for item in outcome.edits}
    kept = {id(item) for item in outcome.kept}
    rolled = {id(item) for item in outcome.rolled_back}
    if (len(planned) != len(outcome.edits) or kept & rolled or planned != kept | rolled
            or len(kept) != len(outcome.kept) or len(rolled) != len(outcome.rolled_back)):
        raise ValueError('kept and rolled-back edits must partition the actual plan')
    if {item.site for item in outcome.kept} & {item.site for item in outcome.rolled_back}:
        raise ValueError('an E3 site cannot be partly kept')
    if outcome.kept and check.get('final') != 'PASS':
        raise ValueError('unconfirmed E3 removal cannot ship')
    all_faces = set()
    for item in outcome.edits:
        if item.engine != 'E3' or item.kind != 'remove' or item.legacy:
            raise ValueError('only non-legacy E3 remove edits are allowed')
        if any(value is not None and len(value) for value in (item.new_points, item.new_faces,
                                                             item.new_face_uv, item.new_face_normal)):
            raise ValueError('E3 may not add or replace geometry or corner attributes')
        if (len(set(item.faces)) != len(item.faces)
                or any(face < 0 or face >= before.n_faces or face in all_faces for face in item.faces)):
            raise ValueError('E3 source face indices must be valid and disjoint')
        all_faces.update(item.faces)
    drop = np.zeros(before.n_faces, bool)
    for item in outcome.kept:
        drop[list(item.faces)] = True
    expected, indices = remove_faces(before, drop)
    for name in ('positions', 'uvs', 'normals', 'face_v', 'face_vt', 'face_vn', 'face_material', 'face_line'):
        if not np.array_equal(getattr(expected, name), getattr(outcome.mesh, name)):
            raise ValueError(f'E3 changed original survivor data: {name}')
    for name in ('materials', 'mtllib', 'units', 'physical_quanta', 'coord_decimals', 'sig_digits'):
        if getattr(expected, name) != getattr(outcome.mesh, name):
            raise ValueError(f'E3 changed source metadata: {name}')
    return indices


def run_checked_e3(before, looks, flatness):
    original = _source_digest(before)
    unit = UnitState(mesh=before, topo=None,
                     looks={i: looks.key_of(name) for i, name in enumerate(before.materials)}, viewpoints=None)
    context = RepairContext(profile=FixProfile(), decider=None, validator=SiteJudge(looks))
    outcome = repair_unit(unit, context, engines=[E3Hidden(flatness=flatness)], validate_sites=True)
    if _source_digest(before) != original:
        raise ValueError('E3 mutated the source input')
    return outcome, source_survivors(before, outcome)
