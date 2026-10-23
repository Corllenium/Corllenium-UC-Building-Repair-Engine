"""Run only checked E3 and prove the surviving fresh-source triangle indices."""
import hashlib
import json
from pathlib import Path

import numpy as np

from engine.fixes.pipeline import FixProfile
from engine.fixes.remove import remove_faces
from engine.repair.engines.e3_hidden import E3Hidden
from engine.repair.kernel import repair_unit
from engine.repair.types import RepairContext, UnitState
from engine.site_judge import SiteJudge
from engine.io.minecraft_floor import write_floor
from engine.io.obj_reader import read_obj


def load_qualified_floor(*, raw, reference, baseline, qualification):
    from dataclasses import replace
    from engine.io.minecraft_floor import Frame, parse_floor
    from engine.io.mtl import parse_mtl
    from engine.io.snapshot import sha256_file
    from tools.main_infra_physical_validation import _hash, _same_mesh

    raw, reference, baseline, qualification = map(Path, (raw, reference, baseline, qualification))
    proof = json.loads(qualification.read_text(encoding='utf-8'))
    if (proof.get('qualified') is not True or not proof.get('floor_id')
            or not isinstance(proof.get('source_revision'), str) or len(proof['source_revision']) != 64):
        raise ValueError('independent import qualification is required before repair')
    provenance = json.loads((baseline / 'geometry-provenance.json').read_text(encoding='utf-8'))
    hashes = {}
    for key, path in [('source_obj_sha256', raw), ('native_reference_sha256', reference),
                      ('source_triangles_sha256', baseline / 'before.source.obj'),
                      ('engine_obj_sha256', baseline / 'before.engine.obj')]:
        hashes[key] = _hash(path, proof.get(key))
    for key, proof_key in [('source_sha256', 'source_obj_sha256'), ('reference_sha256', 'native_reference_sha256'),
                           ('source_triangles_sha256', 'source_triangles_sha256'), ('engine_obj_sha256', 'engine_obj_sha256')]:
        if provenance.get(key) != hashes[proof_key]:
            raise ValueError('qualified source provenance differs')
    native = json.loads(reference.read_text(encoding='utf-8'))
    if native.get('source_sha256') != hashes['source_obj_sha256'] or native.get('unmatched_polygons') != 0:
        raise ValueError('native reference source/polygon binding differs')
    source = parse_floor(raw.read_text(encoding='utf-8'),
        triangulations={int(line): value for line, value in native['polygons'].items()})
    frame = Frame(1000 / 25.4, provenance.get('frame_evidence', ''))
    if not np.array_equal(np.asarray(provenance.get('source_to_engine')), frame.matrix):
        raise ValueError('frame differs from owner metre/block scale and Y-up rotation')
    engine = source.in_frame(frame)
    _same_mesh(read_obj(baseline / 'before.source.obj'), source.mesh)
    before = read_obj(baseline / 'before.engine.obj')
    _same_mesh(before, engine.mesh)
    assets = provenance.get('assets')
    if not isinstance(assets, list):
        raise ValueError('qualified asset inventory missing')
    inventory = {}
    for row in assets:
        for root in (raw.parent, baseline):
            path = (root / row['path']).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('asset path escapes source package')
            _hash(path, row['sha256'])
        inventory[(raw.parent / row['path']).resolve()] = row['sha256']
    if source.mesh.mtllib:
        mtl_path = (raw.parent / source.mesh.mtllib).resolve()
        if mtl_path not in inventory:
            raise ValueError('source material omitted from asset inventory')
        definitions = parse_mtl(mtl_path)
        for name in source.mesh.materials:
            if name not in definitions:
                raise ValueError('source material definition missing')
            material = definitions[name]
            if material.map_kd and (mtl_path.parent / material.map_kd.replace(chr(92), '/')).resolve() not in inventory:
                raise ValueError('source texture omitted from asset inventory')
    before = replace(before, physical_quanta=engine.mesh.physical_quanta)
    receipt = dict(**hashes, floor_id=proof['floor_id'], source_revision=proof['source_revision'],
        qualification_sha256=sha256_file(qualification), assets=assets,
        physical_axis_quanta_inches=list(engine.mesh.physical_quanta),
        source_to_engine=frame.matrix.tolist(), source_sig_digits=source.mesh.sig_digits)
    return source, engine, before, receipt


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


def _survivor_indices(indices, count):
    values = np.asarray(indices)
    if values.ndim != 1 or (values.size and values.dtype.kind not in 'iu'):
        raise ValueError('source survivor indices must be a one-dimensional integer list')
    if values.size and ((values < 0).any() or (values >= count).any() or (values[1:] <= values[:-1]).any()):
        raise ValueError('source survivor indices must be valid, sorted and unique')
    return values.astype(np.int64)


def _material_names(mesh):
    if ((mesh.face_material < -1) | (mesh.face_material >= len(mesh.materials))).any():
        raise ValueError('invalid survivor material index')
    return [None if index == -1 else mesh.materials[index] for index in mesh.face_material]


def verify_survivor_mesh(before, after, source_faces):
    indices = _survivor_indices(source_faces, before.n_faces)
    if after.n_faces != len(indices):
        raise ValueError('saved survivor count differs')
    for name in ('positions', 'uvs', 'normals'):
        if not np.array_equal(getattr(before, name), getattr(after, name)):
            raise ValueError(f'saved original source values changed: {name}')
    for name in ('face_v', 'face_vt', 'face_vn'):
        if not np.array_equal(getattr(before, name)[indices], getattr(after, name)):
            raise ValueError(f'saved survivor corners or winding changed: {name}')
    expected = _material_names(before)
    if ([expected[index] for index in indices] != _material_names(after)
            or not set(after.materials).issubset(before.materials)):
        raise ValueError('saved survivor material names changed')


def save_survivor_pair(engine_floor, source_floor, source_faces, out):
    out = Path(out)
    if out.exists():
        raise ValueError('candidate output exists; refusing overwrite')
    indices = _survivor_indices(source_faces, source_floor.mesh.n_faces)
    if source_floor.frame is not None or engine_floor.frame is None:
        raise ValueError('qualified original source and explicit engine frame required')
    expected = source_floor.in_frame(engine_floor.frame).mesh
    verify_survivor_mesh(expected, engine_floor.mesh, np.arange(expected.n_faces))
    if expected.physical_quanta != engine_floor.mesh.physical_quanta:
        raise ValueError('engine frame physical precision differs')
    keep = np.zeros(source_floor.mesh.n_faces, bool)
    keep[indices] = True
    out.mkdir(parents=True)
    engine_path, source_path = out / 'candidate.engine.obj', out / 'candidate.source.obj'
    write_floor(engine_floor, engine_path, keep_triangles=keep)
    write_floor(source_floor, source_path, keep_triangles=keep)
    verify_survivor_mesh(expected, read_obj(engine_path), indices)
    verify_survivor_mesh(source_floor.mesh, read_obj(source_path), indices)
    mapping = dict(schema_version=1, mode='original_source_survivors',
                   input_triangles=source_floor.mesh.n_faces, output_triangles=len(indices),
                   source_faces=indices.tolist())
    mapping_path = out / 'source-faces.json'
    mapping_path.write_text(json.dumps(mapping, indent=2), encoding='utf-8')
    return engine_path, source_path, mapping_path
