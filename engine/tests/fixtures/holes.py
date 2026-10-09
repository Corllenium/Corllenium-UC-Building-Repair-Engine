"""Slabs with holes, for the narrow flat fill (job P2-E8b): `holed_slab` and the scenes the tests use.

A slab is a z = `z` plate on a rectilinear lattice `xs` x `ys` (cell (i, j) spans xs[i]..xs[i+1], ys[j]..ys[j+1]),
two triangles per cell wound counter-clockwise from above (normal +z), every cell sharing the lattice's points, so a
missing cell leaves a hole whose border is a loop of open edges through lattice points. The top's UV is one affine
map, `(x, y) * uv_per_unit`, unless a cell's `uv_shift` says otherwise. `closed=True` adds the bottom (every cell,
normal -z) and the outer sides (one quad per outer lattice segment, normal outward), so the only open edges are the
holes' borders. `below` adds a plate under the whole slab (a room's floor seen through the holes).
"""
from __future__ import annotations

import numpy as np

from engine.tests.fixtures.build import _mesh


def holed_slab(name="holed_slab", xs=None, ys=None, *, nx=10, ny=10, cell=10.0, holes=(), z=0.0, thickness=8.0,
               closed=True, materials=("m0",), material_of=None, uv_shift=None, lift=None, uv_per_unit=0.05,
               below=None, coord_decimals=2):
    """See the module docstring. `holes`: the cells removed from the top. `material_of(i, j)`: a top cell's material
    index (0 by default). `uv_shift(i, j)`: a (du, dv) added to a top cell's UVs. `lift`: {(i, j): dz} raises top
    lattice point (i, j). `below`: `(depth, material)`, a plate at `z - depth` under the whole lattice."""
    xs = np.arange(nx + 1) * cell if xs is None else np.asarray(xs, float)
    ys = np.arange(ny + 1) * cell if ys is None else np.asarray(ys, float)
    nx, ny = len(xs) - 1, len(ys) - 1
    holes = set(holes)
    lift = lift or {}
    P, uvs, fv, fvt, fm = [], [], [], [], []

    def lattice(height, lifted=None):
        base = len(P)
        for j in range(ny + 1):
            for i in range(nx + 1):
                P.append([xs[i], ys[j], height + (lifted or {}).get((i, j), 0.0)])
        return lambda i, j: base + j * (nx + 1) + i

    def quad(v, uv, material, flip=False):
        base = len(uvs)
        uvs.extend(uv)
        tris = [[0, 1, 2], [0, 2, 3]]
        if flip:
            tris = [[0, 2, 1], [0, 3, 2]]
        for t in tris:
            fv.append([v[k] for k in t])
            fvt.append([base + k for k in t])
            fm.append(material)

    top = lattice(z, lift)
    for j in range(ny):
        for i in range(nx):
            if (i, j) in holes:
                continue
            corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            shift = np.zeros(2) if uv_shift is None else np.asarray(uv_shift(i, j), float)
            uv = [(np.array([xs[a], ys[b]]) * uv_per_unit + shift).tolist() for a, b in corners]
            quad([top(a, b) for a, b in corners], uv, 0 if material_of is None else material_of(i, j))
    if closed:
        bottom = lattice(z - thickness)
        for j in range(ny):
            for i in range(nx):
                corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
                uv = [[xs[a] * uv_per_unit, ys[b] * uv_per_unit] for a, b in corners]
                quad([bottom(a, b) for a, b in corners], uv, 0, flip=True)
        centre = np.array([(xs[0] + xs[-1]) / 2.0, (ys[0] + ys[-1]) / 2.0, z - thickness / 2.0])
        segments = ([((i, 0), (i + 1, 0)) for i in range(nx)] + [((i, ny), (i + 1, ny)) for i in range(nx)]
                    + [((0, j), (0, j + 1)) for j in range(ny)] + [((nx, j), (nx, j + 1)) for j in range(ny)])
        for a, b in segments:
            v = [top(*a), top(*b), bottom(*b), bottom(*a)]
            pts = np.array([P[k] for k in v])
            along = np.linalg.norm(pts[:, :2] - pts[0, :2], axis=1)
            uv = [[s * uv_per_unit, p[2] * uv_per_unit] for s, p in zip(along, pts)]
            normal = np.cross(pts[1] - pts[0], pts[2] - pts[0])
            outward = float(normal @ (pts.mean(axis=0) - centre)) > 0.0
            quad(v, uv, 0, flip=not outward)
    if below is not None:
        depth, material = below
        floor = lattice(z - depth)
        for j in range(ny):
            for i in range(nx):
                corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
                uv = [[xs[a] * uv_per_unit, ys[b] * uv_per_unit] for a, b in corners]
                quad([floor(a, b) for a, b in corners], uv, material)
    return _mesh(name, P, uvs, fv, fvt, materials=materials, face_material=fm, coord_decimals=coord_decimals)


def square_hole_slab(**kw):
    """A closed 100 x 100 x 8 in slab whose top has one 20 in square hole (cells (4..5, 4..5), 10 in cells): an
    8-point loop (4 corners and 4 midpoints), every neighbour one look and one UV map."""
    return holed_slab("square_hole_slab", holes={(i, j) for i in (4, 5) for j in (4, 5)}, **kw)


def floor_over_room(holes=None, nx=12, ny=12):
    """An open floor (m0, one sheet) 120 x 120 in over a room floor (m1) 100 in below. By default two holes: a 20 in
    square (cells (1..2, 1..2)), which the narrow flat fill takes, and a 60 in square (cells (5..10, 4..9)), refused
    as too wide (R3). E8a (solidify) builds nothing on it; both outer borders are patch borders."""
    if holes is None:
        holes = {(i, j) for i in (1, 2) for j in (1, 2)} | {(i, j) for i in range(5, 11) for j in range(4, 10)}
    return holed_slab("floor_over_room", nx=nx, ny=ny, holes=holes, closed=False, materials=("m0", "m1"),
                      below=(100.0, 1))


def fillable_and_wide_holes():
    """A closed 120 x 120 x 8 in slab with two holes in its top: a 20 in square (cells (1..2, 1..2)), which the
    narrow flat fill takes, and a 60 in (1.52 m) square (cells (5..10, 4..9)), wider than one block: refused (R3)."""
    holes = {(i, j) for i in (1, 2) for j in (1, 2)} | {(i, j) for i in range(5, 11) for j in range(4, 10)}
    return holed_slab("fillable_and_wide_holes", nx=12, ny=12, holes=holes)
