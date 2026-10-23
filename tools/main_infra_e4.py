"""Run only checked E4 (the coplanar merge) and prove the merged candidate against its region map.

The E3 contract (`tools/main_infra_e3.py`) is remove-only: the candidate's faces are a subset of the source's. E4
changes triangulation, so it has its own binding: the candidate is the surviving source faces (in order) followed by
every kept region's new triangles, each region recorded with the source faces it replaces, its new triangles (indices
into the candidate), their corners, and its area before and after. New triangles use EXISTING vertices only (by index),
so the source-frame candidate is written from the same indices; the new UV rows are frame-free and the new normal rows
are rotated back with the frame. `verify_merged_mesh` reads a saved pair back: positions identical, the original UV and
normal rows identical with the appended rows as mapped, kept faces identical, and every new triangle inside its
region's plane and the union of its source faces' footprint.
"""
import json
import re
from dataclasses import replace
from pathlib import Path

import numpy as np
import shapely

from engine.fixes.pipeline import FixProfile
from engine.io.minecraft_floor import FloorInput, SourcePolygon, _number
from engine.io.obj_reader import read_obj
from engine.repair.engines.e4_merge import AREA_REL_TOL, E4Merge
from engine.repair.kernel import repair_unit
from engine.repair.types import RepairContext, UnitState, apply_edits
from engine.site_judge import SiteJudge
from engine.topo.planes import plane_basis
from engine.topo.weld import axis_quanta
from tools.main_infra_e3 import _material_names, _source_digest, verify_survivor_mesh

MODE = 'e4_coplanar_merge'
CLEANUP_MODES = ('e4_merge_only', 'e3_then_e4_merge')
_ARRAYS = ('positions', 'uvs', 'normals', 'face_v', 'face_vt', 'face_vn', 'face_material', 'face_line')
_META = ('materials', 'mtllib', 'units', 'physical_quanta', 'coord_decimals', 'sig_digits')


def run_checked_e4(before, looks, flatness, *, allowed_regions=None):
    """`(outcome, mapping)` of one checked E4 stage over `before` with the Validator as site judge."""
    original = _source_digest(before)
    unit = UnitState(mesh=before, topo=None,
                     looks={i: looks.key_of(name) for i, name in enumerate(before.materials)}, viewpoints=None)
    engine = E4Merge(flatness=flatness, allowed_regions=None if allowed_regions is None else set(allowed_regions))
    context = RepairContext(profile=FixProfile(), decider=None, validator=SiteJudge(looks))
    outcome = repair_unit(unit, context, engines=[engine], validate_sites=True)
    if _source_digest(before) != original:
        raise ValueError('E4 mutated the source input')
    return outcome, merged_mapping(before, outcome, report=engine.report)


def merged_mapping(before, outcome, *, report=None):
    """The region map of a checked E4 outcome, after proving the outcome is exactly `apply_edits(before, kept)` of
    non-legacy E4 cuts over existing vertices, each site wholly kept or rolled back, and the stage confirmed."""
    if outcome.result is not None or outcome.stages or len(outcome.checks) != 1:
        raise ValueError('only one checked non-legacy E4 stage is allowed')
    check = outcome.checks[0]
    if (check.get('stage') != 'E4' or check.get('engine') != 'E4'
            or check.get('legacy') is not False or check.get('rollback') is not True):
        raise ValueError('E4 site checks and rollback are required')
    planned = {id(item) for item in outcome.edits}
    kept = {id(item) for item in outcome.kept}
    rolled = {id(item) for item in outcome.rolled_back}
    if (len(planned) != len(outcome.edits) or kept & rolled or planned != kept | rolled
            or len(kept) != len(outcome.kept) or len(rolled) != len(outcome.rolled_back)):
        raise ValueError('kept and rolled-back edits must partition the actual plan')
    if {item.site for item in outcome.kept} & {item.site for item in outcome.rolled_back}:
        raise ValueError('an E4 site cannot be partly kept')
    if outcome.kept and check.get('final') != 'PASS':
        raise ValueError('unconfirmed E4 merge cannot ship (final verdict is not PASS)')
    all_faces = set()
    for item in outcome.edits:
        if item.engine != 'E4' or item.kind != 'cut' or item.legacy:
            raise ValueError('only non-legacy E4 cut edits are allowed')
        if item.new_points is not None and len(item.new_points):
            raise ValueError('E4 may not add points')
        if item.new_faces is None or not len(item.new_faces) or (item.new_faces < 0).any() \
                or (item.new_faces >= len(before.positions)).any():
            raise ValueError('E4 new triangles must index existing vertices')
        if (len(set(item.faces)) != len(item.faces)
                or any(face < 0 or face >= before.n_faces or face in all_faces for face in item.faces)):
            raise ValueError('E4 source face indices must be valid and disjoint')
        all_faces.update(item.faces)
    expected, new_to_old = apply_edits(before, list(outcome.kept))
    for name in _ARRAYS:
        if not np.array_equal(getattr(expected, name), getattr(outcome.mesh, name)):
            raise ValueError(f'E4 outcome differs from its kept edits applied to the input: {name}')
    for name in _META:
        if getattr(expected, name) != getattr(outcome.mesh, name):
            raise ValueError(f'E4 changed source metadata: {name}')
    kept_faces = new_to_old[new_to_old >= 0]
    names = _material_names(before)
    regions, appended = [], int(len(kept_faces))
    for item in outcome.kept:
        ids = list(range(appended, appended + len(item.new_faces)))
        appended += len(item.new_faces)
        source = sorted(int(f) for f in item.faces)
        ev = item.evidence
        regions.append(dict(
            site=int(item.site), region=int(ev['region']), material=names[source[0]], source_faces=source,
            new_triangles=ids, face_v=expected.face_v[ids].tolist(), face_vt=expected.face_vt[ids].tolist(),
            face_vn=expected.face_vn[ids].tolist(),
            area_before=float(ev.get('area_before', _areas(before)[source].sum())),
            area_after=float(ev.get('area_after', _areas(expected)[ids].sum())),
            ring_vertices=int(ev.get('ring_vertices', len(np.unique(item.new_faces))))))
    mapping = dict(schema_version=1, mode=MODE, input_triangles=int(before.n_faces),
                   output_triangles=int(expected.n_faces), kept_source_faces=kept_faces.tolist(),
                   appended_uvs=expected.uvs[len(before.uvs):].tolist(),
                   appended_normals=expected.normals[len(before.normals):].tolist(), regions=regions)
    if report is not None:
        mapping['engine_report'] = {k: report[k] for k in ('regions', 'changed', 'sites', 'skipped', 'refused',
                                                            'allowed_regions', 'max_site_faces', 'flat_materials')}
    verify_merged_mesh(before, expected, mapping)
    return mapping


# ------------------------------------------------------------------------------------------- the binding

def _areas(mesh):
    tri = mesh.positions[mesh.face_v]
    return 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)


def _quanta(mesh):
    return (np.asarray(mesh.physical_quanta, float) if mesh.physical_quanta is not None
            else np.asarray(axis_quanta(mesh.positions, mesh.sig_digits), float))


def _rotated(rows, rotation):
    rows = np.asarray(rows, float).reshape(-1, 3)
    return rows if rotation is None else rows @ np.asarray(rotation, float)


def merged_mesh(before, mapping, *, rotation=None):
    """The candidate mesh `mapping` describes over `before`: the kept source faces in order, then every region's new
    triangles. `rotation` (3 x 3) turns the mapped (engine-frame) normal rows into this frame."""
    kept = np.asarray(mapping['kept_source_faces'], np.int64)
    uvs = np.vstack([before.uvs.reshape(-1, 2), np.asarray(mapping['appended_uvs'], float).reshape(-1, 2)])
    normals = np.vstack([before.normals.reshape(-1, 3), _rotated(mapping['appended_normals'], rotation)])
    face_v, face_vt, face_vn = [before.face_v[kept]], [before.face_vt[kept]], [before.face_vn[kept]]
    material, line = [before.face_material[kept]], [before.face_line[kept]]
    for region in mapping['regions']:
        source = np.asarray(region['source_faces'], np.int64)
        k = len(region['new_triangles'])
        face_v.append(np.asarray(region['face_v'], np.int64).reshape(k, 3))
        face_vt.append(np.asarray(region['face_vt'], np.int64).reshape(k, 3))
        face_vn.append(np.asarray(region['face_vn'], np.int64).reshape(k, 3))
        material.append(np.full(k, int(before.face_material[source[0]]), np.int64))
        line.append(np.full(k, int(before.face_line[source].min()), np.int64))
    return replace(before, uvs=uvs, normals=normals, face_v=np.vstack(face_v), face_vt=np.vstack(face_vt),
                   face_vn=np.vstack(face_vn), face_material=np.concatenate(material),
                   face_line=np.concatenate(line))


def verify_merged_mesh(before, after, mapping, *, rotation=None):
    """Raise unless `after` is exactly the candidate `mapping` describes over `before` (see the module docstring)."""
    if mapping.get('mode') != MODE or mapping.get('schema_version') != 1:
        raise ValueError('E4 region map contract differs')
    kept = np.asarray(mapping['kept_source_faces'], np.int64)
    if kept.ndim != 1 or (kept.size and ((kept < 0).any() or (kept >= before.n_faces).any()
                                         or (kept[1:] <= kept[:-1]).any())):
        raise ValueError('kept source faces must be valid, sorted and unique')
    if not np.array_equal(before.positions, after.positions):
        raise ValueError('saved positions changed: the merge never moves, adds or drops a vertex')
    n_uv, n_vn = len(before.uvs), len(before.normals)
    appended_uvs = np.asarray(mapping['appended_uvs'], float).reshape(-1, 2)
    appended_vn = _rotated(mapping['appended_normals'], rotation)
    if (len(after.uvs) != n_uv + len(appended_uvs) or not np.array_equal(after.uvs[:n_uv], before.uvs)
            or not np.array_equal(after.uvs[n_uv:], appended_uvs)):
        raise ValueError('saved uv rows differ from the original rows plus the mapped appended rows')
    if (len(after.normals) != n_vn + len(appended_vn) or not np.array_equal(after.normals[:n_vn], before.normals)
            or not np.array_equal(after.normals[n_vn:], appended_vn)):
        raise ValueError('saved normal rows differ from the original rows plus the mapped appended rows')
    regions = mapping['regions']
    n_new = sum(len(r['new_triangles']) for r in regions)
    if after.n_faces != len(kept) + n_new or mapping.get('output_triangles') != after.n_faces \
            or mapping.get('input_triangles') != before.n_faces:
        raise ValueError('saved triangle counts differ from the region map')
    n_kept = len(kept)
    for name in ('face_v', 'face_vt', 'face_vn'):
        if not np.array_equal(getattr(before, name)[kept], getattr(after, name)[:n_kept]):
            raise ValueError(f'saved kept faces changed: {name}')
    names_before, names_after = _material_names(before), _material_names(after)
    if [names_before[i] for i in kept] != names_after[:n_kept] or not set(after.materials).issubset(before.materials):
        raise ValueError('saved kept face material names changed')
    covered = set(kept.tolist())
    quanta = _quanta(before)
    tol = 1.5 * float(quanta.max())
    cursor = n_kept
    for region in regions:
        source = np.asarray(region['source_faces'], np.int64)
        ids = np.asarray(region['new_triangles'], np.int64)
        if (not len(source) or (source < 0).any() or (source >= before.n_faces).any()
                or (np.sort(source) != source).any() or covered.intersection(source.tolist())):
            raise ValueError('region source faces must be valid, sorted, unique and disjoint from the kept faces')
        covered.update(source.tolist())
        if not len(ids) or not np.array_equal(ids, np.arange(cursor, cursor + len(ids))):
            raise ValueError('region new triangles must follow the kept faces in region order')
        cursor += len(ids)
        for name in ('face_v', 'face_vt', 'face_vn'):
            if not np.array_equal(np.asarray(region[name], np.int64).reshape(len(ids), 3), getattr(after, name)[ids]):
                raise ValueError(f'saved region triangles differ from the region map: {name}')
        if (after.face_v[ids] < 0).any() or (after.face_v[ids] >= len(before.positions)).any():
            raise ValueError('a region triangle indexes a vertex the source does not have')
        if len({names_before[i] for i in source.tolist()}) != 1 \
                or {names_after[i] for i in ids.tolist()} != {names_before[int(source[0])]}:
            raise ValueError('a region spans or changes materials')
        # the plane and the footprint of the source faces
        tri_old = before.positions[before.face_v[source]]
        cross = np.cross(tri_old[:, 1] - tri_old[:, 0], tri_old[:, 2] - tri_old[:, 0])
        normal = cross.sum(axis=0)
        length = float(np.linalg.norm(normal))
        if length <= 0:
            raise ValueError('a region has no area')
        normal /= length
        centre = tri_old.reshape(-1, 3).mean(axis=0)
        tri_new = after.positions[after.face_v[ids]]
        offset = float(np.abs((tri_new.reshape(-1, 3) - centre) @ normal).max())
        if offset > tol:
            raise ValueError(f'a region triangle lies {offset:.6g} off its region plane (tolerance {tol:.6g})')
        e1, e2 = plane_basis(normal)
        to_xy = lambda pts: np.column_stack([(pts - centre) @ e1, (pts - centre) @ e2])
        footprint = shapely.unary_union([shapely.Polygon(to_xy(t)) for t in tri_old]).buffer(tol)
        for t in tri_new:
            if not footprint.covers(shapely.Polygon(to_xy(t))):
                raise ValueError('a region triangle lies outside the footprint of its source faces')
        if (np.cross(tri_new[:, 1] - tri_new[:, 0], tri_new[:, 2] - tri_new[:, 0]) @ normal <= 0).any():
            raise ValueError('a region triangle faces the other way than its source faces')
        a_before, a_after = float(_areas(before)[source].sum()), float(_areas(after)[ids].sum())
        m_before, m_after = float(region['area_before']), float(region['area_after'])
        if abs(a_after - a_before) > AREA_REL_TOL * a_before or abs(m_after - m_before) > AREA_REL_TOL * m_before:
            raise ValueError('a region changed its area')
        if rotation is None and (abs(m_before - a_before) > AREA_REL_TOL * a_before
                                 or abs(m_after - a_after) > AREA_REL_TOL * a_before):
            # the mapped areas are engine-frame square inches: only that frame can be held to them exactly
            raise ValueError('the region map areas differ from the saved triangles')
    if covered != set(range(before.n_faces)):
        raise ValueError('kept faces and region source faces must cover every source face once')


# ------------------------------------------------------------------------------------------------ saving

_FACE_LINE = re.compile(r'^(o|g|f|usemtl)\s*(.*)$')


def floor_from_candidate(path):
    """A `FloorInput` (frame None) of a saved triangle candidate: its mesh by `read_obj`, and each face's object and
    group from the file's `o` / `g` lines, so a later save keeps them."""
    path = Path(path)
    mesh = read_obj(path)
    group, obj, groups = '', '', []
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.partition('#')[0].strip()
        m = _FACE_LINE.match(line) if line else None
        if m is None:
            continue
        head, rest = m.group(1), m.group(2).strip()
        if head == 'g':
            group = rest
        elif head == 'o':
            obj = rest
        elif head == 'f':
            if len(rest.split()) != 3:
                raise ValueError('candidate faces must be triangles')
            groups.append((obj, group))
    if len(groups) != mesh.n_faces:
        raise ValueError('candidate face count differs from its f lines')
    polygons = tuple(SourcePolygon(int(mesh.face_line[i]), tuple(zip(mesh.face_v[i].tolist(), mesh.face_vt[i].tolist(),
                                                                       mesh.face_vn[i].tolist())),
                                   int(mesh.face_material[i]), g, o)
                     for i, (o, g) in enumerate(groups))
    n = mesh.n_faces
    return FloorInput(mesh, polygons, np.arange(n, dtype=np.int64), np.tile(np.arange(3, dtype=np.int64), (n, 1)))


def _write_merged(floor, after, mapping, path):
    """`after` (the candidate over `floor.mesh`) in `write_floor`'s format: a kept face under its own polygon's object
    and group, a region's triangles under the object and group of the region's first source face."""
    mesh = floor.mesh
    out = [f'# {after.name}; units={after.units}']
    if after.mtllib:
        out.append(f'mtllib {after.mtllib}')
    for head, values in (('v', after.positions), ('vt', after.uvs), ('vn', after.normals)):
        out.extend(head + ' ' + ' '.join(_number(x) for x in row) for row in values)
    owner = [int(k) for k in mapping['kept_source_faces']]
    for region in mapping['regions']:
        owner.extend([int(region['source_faces'][0])] * len(region['new_triangles']))
    if len(owner) != after.n_faces:
        raise ValueError('region map does not cover the candidate faces')
    previous = None
    for i, src in enumerate(owner):
        poly = floor.polygons[floor.triangle_polygon[src]]
        mat = int(after.face_material[i])
        state = (mat, poly.group, poly.object_name)
        if state != previous:
            out.extend([f'o {poly.object_name}', f'g {poly.group}'])
            if mat >= 0:
                out.append(f'usemtl {after.materials[mat]}')
            elif previous is not None and previous[0] >= 0:
                raise ValueError('cannot reset OBJ material to unnamed')
        previous = state
        tokens = []
        for v, t, n in zip(after.face_v[i], after.face_vt[i], after.face_vn[i]):
            tokens.append(f'{v+1}/{t+1}/{n+1}' if t >= 0 and n >= 0 else
                          f'{v+1}/{t+1}' if t >= 0 else f'{v+1}//{n+1}' if n >= 0 else str(v + 1))
        out.append('f ' + ' '.join(tokens))
    Path(path).write_text('\n'.join(out) + '\n', encoding='utf-8', newline='\n')


def save_merged_pair(engine_floor, source_floor, mapping, out):
    """Write `candidate.engine.obj`, `candidate.source.obj` and `region-map.json` under `out` (which must not exist),
    read both back and verify them against `mapping`; returns the three paths."""
    out = Path(out)
    if out.exists():
        raise ValueError('candidate output exists; refusing overwrite')
    if source_floor.frame is not None or engine_floor.frame is None:
        raise ValueError('qualified original source and explicit engine frame required')
    expected = source_floor.in_frame(engine_floor.frame).mesh
    verify_survivor_mesh(expected, engine_floor.mesh, np.arange(expected.n_faces))
    if expected.physical_quanta != engine_floor.mesh.physical_quanta:
        raise ValueError('engine frame physical precision differs')
    rotation = engine_floor.frame.rotation
    engine_after = merged_mesh(engine_floor.mesh, mapping)
    source_after = merged_mesh(source_floor.mesh, mapping, rotation=rotation)
    verify_merged_mesh(engine_floor.mesh, engine_after, mapping)
    verify_merged_mesh(source_floor.mesh, source_after, mapping, rotation=rotation)
    out.mkdir(parents=True)
    engine_path, source_path = out / 'candidate.engine.obj', out / 'candidate.source.obj'
    _write_merged(engine_floor, engine_after, mapping, engine_path)
    _write_merged(source_floor, source_after, mapping, source_path)
    verify_merged_mesh(engine_floor.mesh, read_obj(engine_path), mapping)
    verify_merged_mesh(source_floor.mesh, read_obj(source_path), mapping, rotation=rotation)
    mapping_path = out / 'region-map.json'
    mapping_path.write_text(json.dumps(mapping, indent=2), encoding='utf-8')
    return engine_path, source_path, mapping_path
