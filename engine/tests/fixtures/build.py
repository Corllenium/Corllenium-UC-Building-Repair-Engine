import numpy as np

from engine.model import MeshData


def _mesh(name, positions, uvs, face_v, face_vt, materials=("m0",), face_material=None):
    f = len(face_v)
    return MeshData(
        name=name, positions=np.asarray(positions, float), uvs=np.asarray(uvs, float).reshape(-1, 2),
        normals=np.zeros((0, 3)), face_v=np.asarray(face_v, np.int64), face_vt=np.asarray(face_vt, np.int64),
        face_vn=np.full((f, 3), -1, np.int64),
        face_material=np.zeros(f, np.int64) if face_material is None else np.asarray(face_material, np.int64),
        face_line=np.arange(1, f + 1, dtype=np.int64), materials=list(materials), mtllib=None,
        coord_decimals=2, sig_digits=6)


def cube(size=10.0):
    s = size
    P = np.array([[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0], [0, 0, s], [s, 0, s], [s, s, s], [0, s, s]], float)
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (3, 0, 4, 7)]
    uvs, fv, fvt = [], [], []
    for q in quads:
        pts = P[list(q)]
        keep = [a for a in range(3) if np.ptp(pts[:, a]) > 0]
        base = len(uvs)
        uvs.extend((pts[:, keep] * 0.1).tolist())
        fv += [[q[0], q[1], q[2]], [q[0], q[2], q[3]]]
        fvt += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
    return _mesh("cube", P, uvs, fv, fvt)


def grid_slab(nx=10, ny=10, cell=10.0, uv_per_unit=0.05, shift_cols=(), break_col=None):
    """Flat z=0 slab, shared positions, 4 private UVs per cell.
    shift_cols: columns whose UVs are shifted by a whole number of tiles (invisible seam).
    break_col:  columns >= break_col get a +0.37 non-integer UV offset (real seam)."""
    P = [[i * cell, j * cell, 0.0] for j in range(ny + 1) for i in range(nx + 1)]
    vid = lambda i, j: j * (nx + 1) + i
    uvs, fv, fvt = [], [], []
    for j in range(ny):
        for i in range(nx):
            shift = np.array([3.0, -2.0]) if i in shift_cols else np.zeros(2)
            if break_col is not None and i >= break_col:
                shift = shift + 0.37
            corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            base = len(uvs)
            uvs.extend([(np.array([a * cell, b * cell]) * uv_per_unit + shift).tolist() for a, b in corners])
            v = [vid(a, b) for a, b in corners]
            fv += [[v[0], v[1], v[2]], [v[0], v[2], v[3]]]
            fvt += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
    return _mesh("grid_slab", P, uvs, fv, fvt)


def t_junction_strip():
    """Big quad 20x10 below, two 10x10 quads above. Vertex (10,10) sits mid-edge of the big quad's top edge.
    One zero-area stitching triangle (0,10)-(10,10)-(20,10), as SketchUp exports them."""
    P = [[0, 0, 0], [20, 0, 0], [20, 10, 0], [0, 10, 0], [10, 10, 0], [0, 20, 0], [10, 20, 0], [20, 20, 0]]
    fv = [[0, 1, 2], [0, 2, 3], [3, 4, 6], [3, 6, 5], [4, 2, 7], [4, 7, 6], [3, 4, 2]]
    uvs = (np.asarray(P, float)[:, :2] * 0.05).tolist()
    return _mesh("t_strip", P, uvs, fv, fv)


def t_junction_shared_strip(drop_zero_area=False):
    """t_junction_strip() plus one vertical wall triangle (0,10,0)-(20,10,0)-(10,10,-10) that also
    uses the big quad's long top edge, so that edge's count becomes 2 (shared) instead of 1 (open).
    drop_zero_area removes the (3,4,2) stitching triangle, to prove the T-vertex at (10,10,0) is
    still found by the widened geometric search alone, without the hint."""
    P = [[0, 0, 0], [20, 0, 0], [20, 10, 0], [0, 10, 0], [10, 10, 0], [0, 20, 0], [10, 20, 0], [20, 20, 0],
         [10, 10, -10]]
    fv = [[0, 1, 2], [0, 2, 3], [3, 4, 6], [3, 6, 5], [4, 2, 7], [4, 7, 6], [3, 4, 2], [3, 2, 8]]
    if drop_zero_area:
        fv = [f for f in fv if f != [3, 4, 2]]
    uvs = (np.asarray(P, float)[:, :2] * 0.05).tolist()
    return _mesh("t_shared_strip", P, uvs, fv, fv)
