"""Strict polygon ingest. Source coordinates stay unscaled until evidence supplies a frame."""
from __future__ import annotations

from dataclasses import dataclass, replace
from collections import Counter
from decimal import Decimal
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon

from engine.model import MeshData


class FloorFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Frame:
    inches_per_unit: float
    evidence: str

    def __post_init__(self):
        if not self.evidence.strip():
            raise ValueError("physical scale and Y-up evidence required")
        if not np.isfinite(self.inches_per_unit) or self.inches_per_unit <= 0:
            raise ValueError("scale must be finite and positive")

    @property
    def matrix(self):
        matrix = np.eye(4)
        matrix[:3, :3] = self.rotation * self.inches_per_unit
        return matrix

    @property
    def rotation(self):
        # Proper rotation: source +Y becomes engine +Z; determinant stays positive.
        return np.array([[1., 0., 0.], [0., 0., -1.], [0., 1., 0.]])

    def to_source(self, positions):
        return (np.asarray(positions) / self.inches_per_unit) @ self.rotation


@dataclass(frozen=True)
class SourcePolygon:
    line: int
    corners: tuple[tuple[int, int, int], ...]
    material: int
    group: str
    object_name: str


@dataclass
class FloorInput:
    mesh: MeshData
    polygons: tuple[SourcePolygon, ...]
    triangle_polygon: np.ndarray
    triangle_corners: np.ndarray
    frame: Frame | None = None

    def in_frame(self, frame: Frame):
        if self.frame is not None:
            raise ValueError("input already normalized")
        mesh = replace(self.mesh,
                       positions=self.mesh.positions @ frame.rotation.T * frame.inches_per_unit,
                       normals=self.mesh.normals @ frame.rotation.T,
                       units="inches", coord_decimals=15, sig_digits=17)
        return replace(self, mesh=mesh, frame=frame)


def _index(token: str, count: int, line: int) -> int:
    try:
        value = int(token)
    except ValueError as exc:
        raise FloorFormatError(f"line {line}: invalid index {token!r}") from exc
    index = value - 1 if value > 0 else count + value
    if value == 0 or not 0 <= index < count:
        raise FloorFormatError(f"line {line}: index {value} outside available {count} records")
    return index


def _cross(a, b, c):
    ab, ac = b - a, c - a
    return ab[0] * ac[1] - ab[1] * ac[0]


def _triangulate(points: np.ndarray, line: int) -> list[tuple[int, int, int]]:
    n = len(points)
    if n < 3 or len(np.unique(points, axis=0)) != n:
        raise FloorFormatError(f"line {line}: polygon has too few or repeated corners")
    local = points - points[0]
    normal = np.cross(local, np.roll(local, -1, axis=0)).sum(axis=0)
    length = np.linalg.norm(normal)
    scale = max(float(np.ptp(points, axis=0).max()), 1e-300)
    if length == 0:
        raise FloorFormatError(f"line {line}: degenerate or self-intersecting polygon")
    normal /= length
    # Numerical arithmetic allowance, independent of physical repair tolerances.
    if np.max(np.abs(local @ normal)) > 64 * np.finfo(float).eps * scale:
        raise FloorFormatError(f"line {line}: nonplanar polygon")
    xy = np.delete(local, int(np.argmax(np.abs(normal))), axis=1)
    polygon = Polygon(xy)
    if not polygon.is_valid or polygon.area == 0:
        raise FloorFormatError(f"line {line}: invalid/self-intersecting polygon")
    area2 = sum(_cross(np.zeros(2), xy[i], xy[(i + 1) % n]) for i in range(n))
    sign = 1 if area2 > 0 else -1
    remaining = list(range(n))
    triangles = []
    while len(remaining) > 3:
        for offset in range(len(remaining)):
            i = (offset + 1) % len(remaining)
            a, b, c = remaining[i - 1], remaining[i], remaining[(i + 1) % len(remaining)]
            if sign * _cross(xy[a], xy[b], xy[c]) <= 0:
                continue
            others = [j for j in remaining if j not in (a, b, c)]
            if any(all(sign * _cross(xy[u], xy[v], xy[j]) >= 0
                       for u, v in ((a, b), (b, c), (c, a))) for j in others):
                continue
            triangles.append((a, b, c))
            del remaining[i]
            break
        else:
            raise FloorFormatError(f"line {line}: cannot triangulate without losing a corner")
    triangles.append(tuple(remaining))
    areas = [sign * _cross(xy[a], xy[b], xy[c]) for a, b, c in triangles]
    if min(areas) <= 0 or not np.isclose(sum(areas), abs(area2), rtol=64 * np.finfo(float).eps, atol=0):
        raise FloorFormatError(f"line {line}: triangulation coverage failed")
    return triangles


def _reference_triangles(points, line, triangles):
    n = len(points)
    if len(triangles) != n - 2 or n < 3 or len(np.unique(points, axis=0)) != n:
        raise FloorFormatError(f'line {line}: reference triangle/corner count differs')
    result, edges = [], Counter()
    for triangle in triangles:
        if len(triangle) != 3 or any(type(i) is not int or not 0 <= i < n for i in triangle) or len(set(triangle)) != 3:
            raise FloorFormatError(f'line {line}: invalid reference corner')
        a, b, c = triangle
        result.append((a, b, c))
        for u, v in ((a, b), (b, c), (c, a)):
            edges[u, v] += 1
            edges[v, u] -= 1
    boundary = Counter()
    for u in range(n):
        v = (u + 1) % n
        boundary[u, v] += 1
        boundary[v, u] -= 1
    if edges != boundary:
        raise FloorFormatError(f'line {line}: reference changes polygon boundary or winding')
    local = points - points[0]
    normal = np.cross(local, np.roll(local, -1, axis=0)).sum(axis=0)
    if not np.linalg.norm(normal):
        raise FloorFormatError(f'line {line}: degenerate reference polygon')
    xy = np.delete(local, int(np.argmax(np.abs(normal))), axis=1)
    polygon = Polygon(xy)
    if not polygon.is_valid or polygon.area == 0:
        raise FloorFormatError(f'line {line}: invalid reference polygon')
    area2 = sum(_cross(np.zeros(2), xy[i], xy[(i + 1) % n]) for i in range(n))
    sign = 1 if area2 > 0 else -1
    areas = [sign * _cross(xy[a], xy[b], xy[c]) for a, b, c in result]
    if min(areas) <= 0 or not np.isclose(sum(areas), abs(area2), rtol=64 * np.finfo(float).eps, atol=0):
        raise FloorFormatError(f'line {line}: reference coverage differs')
    return result


def parse_floor(text: str, name="floor", *, triangulations=None) -> FloorInput:
    positions, uvs, normals, materials, polygons = [], [], [], [], []
    triangle_polygon, triangle_corners, corners, fmat, flines = [], [], [], [], []
    current, mtllib, group, object_name = -1, None, "", ""
    decimals, sig = 0, 0
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.partition("#")[0].strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        head, rest = parts[0], parts[1] if len(parts) > 1 else ""
        if head in ("v", "vt", "vn"):
            size = 2 if head == "vt" else 3
            tokens = rest.split()
            try:
                values = [float(t) for t in tokens]
            except ValueError as exc:
                raise FloorFormatError(f"line {line_no}: invalid {head}") from exc
            if len(values) != size or not np.isfinite(values).all():
                raise FloorFormatError(f"line {line_no}: unsupported {head} coordinates")
            {"v": positions, "vt": uvs, "vn": normals}[head].append(values)
            if head == "v":
                for t in tokens:
                    dec = Decimal(t)
                    decimals = max(decimals, max(0, -dec.as_tuple().exponent))
                    sig = max(sig, len(dec.as_tuple().digits))
        elif head == "mtllib":
            if mtllib is not None and mtllib != rest:
                raise FloorFormatError(f"line {line_no}: multiple material libraries unsupported")
            mtllib = rest
        elif head == "usemtl":
            if not rest:
                raise FloorFormatError(f"line {line_no}: empty material")
            if rest not in materials:
                materials.append(rest)
            current = materials.index(rest)
        elif head == "g":
            group = rest
        elif head == "o":
            object_name = rest
        elif head == "s":
            if rest not in ("off", "0"):
                raise FloorFormatError(f"line {line_no}: smoothing groups unsupported")
        elif head == "f":
            poly_corners = []
            for token in rest.split():
                ref = token.split("/")
                if len(ref) > 3:
                    raise FloorFormatError(f"line {line_no}: invalid corner")
                poly_corners.append(tuple(_index(ref[k], count, line_no) if k < len(ref) and ref[k] else -1
                                          for k, count in enumerate((len(positions), len(uvs), len(normals)))))
                if poly_corners[-1][0] < 0:
                    raise FloorFormatError(f"line {line_no}: missing position")
            points = np.asarray([positions[c[0]] for c in poly_corners])
            if triangulations is not None:
                if line_no not in triangulations:
                    raise FloorFormatError(f'line {line_no}: reference is incomplete')
                local_tris = _reference_triangles(points, line_no, triangulations[line_no])
            else:
                local_tris = _triangulate(points, line_no)
            for tri in local_tris:
                triangle_polygon.append(len(polygons))
                triangle_corners.append(tri)
                corners.append([poly_corners[j] for j in tri])
                fmat.append(current)
                flines.append(line_no)
            polygons.append(SourcePolygon(line_no, tuple(poly_corners), current, group, object_name))
        else:
            raise FloorFormatError(f"line {line_no}: unsupported OBJ record {head!r}")
    if not polygons:
        raise FloorFormatError("no polygons")
    if triangulations is not None and set(triangulations) != {poly.line for poly in polygons}:
        raise FloorFormatError('reference names a non-polygon record')
    refs = np.asarray(corners, dtype=np.int64)
    mesh = MeshData(name, np.asarray(positions, float).reshape(-1, 3),
                    np.asarray(uvs, float).reshape(-1, 2), np.asarray(normals, float).reshape(-1, 3),
                    refs[:, :, 0], refs[:, :, 1], refs[:, :, 2], np.asarray(fmat, np.int64),
                    np.asarray(flines, np.int64), materials, mtllib, decimals, sig,
                    units="source_units_unverified")
    return FloorInput(mesh, tuple(polygons), np.asarray(triangle_polygon, np.int64),
                      np.asarray(triangle_corners, np.int64))


def _number(value):
    return format(Decimal(repr(float(value))), "f")


def write_floor(floor: FloorInput, path: Path, *, polygons=False, keep_triangles=None):
    mesh = floor.mesh
    keep = np.ones(mesh.n_faces, bool) if keep_triangles is None else np.asarray(keep_triangles, bool)
    if keep.shape != (mesh.n_faces,):
        raise ValueError("keep_triangles shape differs")
    out = [f"# {mesh.name}; units={mesh.units}"]
    if mesh.mtllib:
        out.append(f"mtllib {mesh.mtllib}")
    for head, values in (("v", mesh.positions), ("vt", mesh.uvs), ("vn", mesh.normals)):
        out.extend(head + " " + " ".join(_number(x) for x in row) for row in values)
    if polygons:
        records = []
        for i, poly in enumerate(floor.polygons):
            subset = keep[floor.triangle_polygon == i]
            if subset.any() and not subset.all():
                raise ValueError("polygon export requires whole polygon retention/removal")
            if subset.all():
                records.append((poly.corners, poly.material, poly.group, poly.object_name))
    else:
        records = [(list(zip(mesh.face_v[i], mesh.face_vt[i], mesh.face_vn[i])), int(mesh.face_material[i]),
                    floor.polygons[floor.triangle_polygon[i]].group,
                    floor.polygons[floor.triangle_polygon[i]].object_name) for i in np.flatnonzero(keep)]
    previous = None
    for refs, mat, group, obj in records:
        state = (mat, group, obj)
        if state != previous:
            out.extend([f"o {obj}", f"g {group}"])
            if mat >= 0:
                out.append(f"usemtl {mesh.materials[mat]}")
            elif previous is not None and previous[0] >= 0:
                raise ValueError("cannot reset OBJ material to unnamed")
        previous = state
        tokens = []
        for v, t, n in refs:
            tokens.append(f"{v+1}/{t+1}/{n+1}" if t >= 0 and n >= 0 else
                          f"{v+1}/{t+1}" if t >= 0 else f"{v+1}//{n+1}" if n >= 0 else str(v+1))
        out.append("f " + " ".join(tokens))
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
