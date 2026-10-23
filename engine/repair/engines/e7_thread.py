"""Strict E7 cuts: split original triangles at existing exact-edge vertices only."""
from collections import Counter
from dataclasses import dataclass, field
import math
from types import SimpleNamespace

import numpy as np
import shapely

from engine.fixes.merge import _barycentric, _thread_output, thread_tolerance
from engine.fixes.overlap import _polygons, plane_groups
from engine.repair.types import Edit
from engine.topo.adjacency import degenerate_mask
from engine.topo.planes import plane_basis
from engine.topo.weld import axis_quanta


def _overlapping_faces(topo):
    blocked = set()
    for faces, normal, origin in plane_groups(topo, 1.5 * float(topo.quanta.max())):
        basis = np.stack(plane_basis(normal), axis=1)
        polys, _areas = _polygons(topo.positions_w, topo.face_w, faces, origin, basis)
        left, right = shapely.STRtree(polys).query(polys, predicate='intersects')
        upper = left < right
        left, right = left[upper], right[upper]
        shared = shapely.area(shapely.intersection(polys[left], polys[right])) > 0
        blocked.update(int(face) for face in faces[left[shared]])
        blocked.update(int(face) for face in faces[right[shared]])
    return blocked


def _source_weights(mesh, source, faces):
    faces = np.asarray(faces, dtype=np.int64)
    if (faces.ndim != 2 or faces.shape[1] != 3 or len(faces) < 2
            or (faces < 0).any() or (faces >= len(mesh.positions)).any()):
        raise ValueError('invalid existing vertex indices')
    original = mesh.face_v[source]
    corners = mesh.positions[original]
    points = mesh.positions[faces]
    normal = np.cross(corners[1] - corners[0], corners[2] - corners[0])
    children = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
    if not (children @ normal > 0).all():
        raise ValueError('winding')
    weights = np.array([np.eye(3)[np.flatnonzero(original == vertex)[0]] if vertex in original
                        else _barycentric(mesh.positions[vertex], corners)
                        for vertex in faces.reshape(-1)]).reshape(-1, 3, 3)
    local = points - corners[0]
    reconstructed = weights @ (corners - corners[0])
    roundoff = 32 * np.finfo(float).eps * max(1.0, float(np.abs(local).max()))
    if not np.isfinite(weights).all() or np.abs(local - reconstructed).max() > roundoff:
        raise ValueError('off source plane')
    area_before = float(np.linalg.norm(normal) / 2)
    area_after = float(np.linalg.norm(children, axis=1).sum() / 2)
    if not math.isclose(area_before, area_after, rel_tol=32 * np.finfo(float).eps, abs_tol=0):
        raise ValueError('area')
    # This union is a proof on one source triangle; no union coordinates become output geometry.
    polygons = shapely.polygons(weights[:, :, 1:])
    original_polygon = shapely.Polygon([[0, 0], [1, 0], [0, 1]])
    if not shapely.equals(shapely.union_all(polygons), original_polygon):
        raise ValueError('source boundary')
    return faces, weights, area_before, area_after


def _attributes(mesh, source, weights, index_name, table_name):
    indices = getattr(mesh, index_name)[source]
    if (indices < 0).all():
        return None
    if (indices < 0).any():
        raise ValueError('partial corner attributes')
    values = getattr(mesh, table_name)[indices]
    if not np.isfinite(values).all():
        raise ValueError('nonfinite corner attributes')
    return weights @ values


@dataclass
class E7Thread:
    name = 'E7'
    report: dict = field(default_factory=dict, init=False)

    def plan(self, unit, ctx):
        mesh = unit.mesh
        quanta = (axis_quanta(mesh.positions, mesh.sig_digits) if mesh.physical_quanta is None
                  else np.asarray(mesh.physical_quanta))
        ok = ~degenerate_mask(mesh.positions, mesh.face_v)
        topo = SimpleNamespace(positions_w=mesh.positions, face_w=mesh.face_v, quanta=quanta,
                               face_region=np.where(ok, np.arange(mesh.n_faces), -1))
        tolerance = thread_tolerance(quanta)
        _builds, pieces, edges = _thread_output(topo, [], list(range(mesh.n_faces)), {}, tolerance)
        overlaps = _overlapping_faces(topo) if pieces else set()
        refused, edits = Counter(), []
        for source, children in sorted(pieces.items()):
            if source in overlaps:
                refused['overlap'] += 1
                continue
            try:
                faces, weights, area_before, area_after = _source_weights(mesh, source, children)
                uv = _attributes(mesh, source, weights, 'face_vt', 'uvs')
                normal = _attributes(mesh, source, weights, 'face_vn', 'normals')
            except ValueError as error:
                refused[str(error)] += 1
                continue
            edits.append(Edit(self.name, 'cut', (source,), faces, None, source,
                'existing exact-edge T-junction threading',
                dict(source_face=source, source_line=int(mesh.face_line[source]),
                     material=int(mesh.face_material[source]), area_before=area_before,
                     area_after=area_after, thread_tolerance=tolerance),
                new_face_uv=uv, new_face_normal=normal))
        self.report = dict(candidates=len(pieces), proposed=len(edits), refused=dict(refused),
                           edges_considered=len(edges), thread_tolerance=tolerance)
        return edits
