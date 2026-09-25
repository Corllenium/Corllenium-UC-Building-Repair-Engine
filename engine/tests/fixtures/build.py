from pathlib import Path

import numpy as np

from engine.io.obj_reader import read_obj
from engine.model import MeshData


def _mesh(name, positions, uvs, face_v, face_vt, materials=("m0",), face_material=None,
          coord_decimals=2, sig_digits=6):
    f = len(face_v)
    return MeshData(
        name=name, positions=np.asarray(positions, float), uvs=np.asarray(uvs, float).reshape(-1, 2),
        normals=np.zeros((0, 3)), face_v=np.asarray(face_v, np.int64), face_vt=np.asarray(face_vt, np.int64),
        face_vn=np.full((f, 3), -1, np.int64),
        face_material=np.zeros(f, np.int64) if face_material is None else np.asarray(face_material, np.int64),
        face_line=np.arange(1, f + 1, dtype=np.int64), materials=list(materials), mtllib=None,
        coord_decimals=coord_decimals, sig_digits=sig_digits)


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


def _grid(nx, ny, cell, uv_per_unit, keep=None, material_of=None):
    """Positions/uvs/faces of a flat z=0 grid. `keep(i, j)` selects which cells exist (all by
    default); `material_of(i, j)` gives each cell's material index (0 by default). The full
    `(nx+1) x (ny+1)` position lattice is always emitted, so removed cells leave their corner
    positions in place, unused."""
    P = [[i * cell, j * cell, 0.0] for j in range(ny + 1) for i in range(nx + 1)]
    uvs, fv, fvt, fm = [], [], [], []
    for j in range(ny):
        for i in range(nx):
            if keep is not None and not keep(i, j):
                continue
            corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            base = len(uvs)
            uvs.extend([[a * cell * uv_per_unit, b * cell * uv_per_unit] for a, b in corners])
            v = [b * (nx + 1) + a for a, b in corners]
            fv += [[v[0], v[1], v[2]], [v[0], v[2], v[3]]]
            fvt += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
            m = 0 if material_of is None else material_of(i, j)
            fm += [m, m]
    return P, uvs, fv, fvt, fm


def l_shaped_slab(nx=10, ny=10, cell=10.0, cut=5, uv_per_unit=0.05):
    """`grid_slab` with the top-right `cut x cut` block of cells removed: an L with 6 corners."""
    P, uvs, fv, fvt, fm = _grid(nx, ny, cell, uv_per_unit, keep=lambda i, j: not (i >= cut and j >= cut))
    return _mesh("l_shaped_slab", P, uvs, fv, fvt, face_material=fm)


def slab_with_hole(nx=10, ny=10, cell=10.0, lo=4, hi=6, uv_per_unit=0.05):
    """`grid_slab` with the `(lo..hi) x (lo..hi)` block of cells removed: a square with one
    square hole, 4 outer corners and 4 hole corners."""
    P, uvs, fv, fvt, fm = _grid(nx, ny, cell, uv_per_unit,
                                keep=lambda i, j: not (lo <= i < hi and lo <= j < hi))
    return _mesh("slab_with_hole", P, uvs, fv, fvt, face_material=fm)


def two_slabs_sharing_border(nx=10, ny=10, cell=10.0, split=5, uv_per_unit=0.05):
    """One coplanar grid cut into two materials at column `split`: two 5x10 slabs sharing a
    border whose `ny - 1` interior vertices are exactly collinear in both slabs' rings."""
    P, uvs, fv, fvt, fm = _grid(nx, ny, cell, uv_per_unit, material_of=lambda i, j: 0 if i < split else 1)
    return _mesh("two_slabs_sharing_border", P, uvs, fv, fvt, materials=("m0", "m1"), face_material=fm)


def slab_with_wall(nx=10, ny=10, cell=10.0, uv_per_unit=0.05, foot_i=3, foot_j=5, height=25.0):
    """`grid_slab` plus one vertical wall triangle standing on the slab: one foot on an interior
    grid vertex `(foot_i, foot_j)`, the other on the border vertex `(0, foot_j)`."""
    P, uvs, fv, fvt, fm = _grid(nx, ny, cell, uv_per_unit)
    border, foot = foot_j * (nx + 1), foot_j * (nx + 1) + foot_i
    apex = len(P)
    P = P + [[foot_i * cell, foot_j * cell, height]]
    base = len(uvs)
    uvs = uvs + [[0.0, 0.0], [foot_i * cell * uv_per_unit, 0.0], [foot_i * cell * uv_per_unit, height * uv_per_unit]]
    fv = fv + [[border, foot, apex]]
    fvt = fvt + [[base, base + 1, base + 2]]
    fm = fm + [0]
    return _mesh("slab_with_wall", P, uvs, fv, fvt, face_material=fm)


def overlapping_pair(nx=10, ny=10, cell=10.0, uv_per_unit=0.05):
    """`grid_slab` plus one extra coplanar triangle over existing grid vertices `(2,2)-(4,2)-(4,3)`,
    overlapping cells (2,2) and (3,2)."""
    P, uvs, fv, fvt, fm = _grid(nx, ny, cell, uv_per_unit)
    corners = [(2, 2), (4, 2), (4, 3)]
    base = len(uvs)
    uvs = uvs + [[a * cell * uv_per_unit, b * cell * uv_per_unit] for a, b in corners]
    fv = fv + [[b * (nx + 1) + a for a, b in corners]]
    fvt = fvt + [[base, base + 1, base + 2]]
    fm = fm + [0]
    return _mesh("overlapping_pair", P, uvs, fv, fvt, face_material=fm)


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


def box_with_partition(size=10.0):
    """`cube()` (12 tris, indices 0-11) plus one inner quad (2 tris, indices 12-13) spanning
    the full interior at z = size/2. The partition is completely sealed inside the cube on both
    sides, so no ray escapes it from either side: EXP_HIDDEN. The 12 outer cube tris see open
    space on their outward side: EXP_OUTSIDE."""
    m = cube(size)
    s = size
    z = s / 2.0
    corners = [[0, 0, z], [s, 0, z], [s, s, z], [0, s, z]]
    pts = np.array(corners, float)
    base = len(m.positions)
    ubase = len(m.uvs)
    P = np.vstack([m.positions, pts])
    uvs = np.vstack([m.uvs, pts[:, :2] * 0.1])
    fv = np.vstack([m.face_v, [[base, base + 1, base + 2], [base, base + 2, base + 3]]])
    fvt = np.vstack([m.face_vt, [[ubase, ubase + 1, ubase + 2], [ubase, ubase + 2, ubase + 3]]])
    return _mesh("box_with_partition", P, uvs, fv, fvt)


def gridded_box(n=4, cell=2.5, uv_per_unit=0.05):
    """A closed cube (side `s = n * cell`) with each of its 6 faces built from an `n x n` grid of
    small coplanar triangles (`2 * n * n` per face, all consistently wound within a face AND
    correctly wound OUTWARD -- `du`/`dv` are chosen per face so `cross(du, dv)` points away from
    the box), the way a SketchUp export cuts a flat panel into gridlines. No face is ever hidden
    (every face's outward hemisphere sees open space -- exposure is double-sided, so an ordinary
    closed box's own faces are never sealed on BOTH sides the way an interior partition is);
    `merge_regions` should collapse each of the 6 planar regions back to its minimal 2 triangles
    (12 total), and `engine.fixes.orient.classify_orientation` should find nothing to flip."""
    s = n * cell
    P, uvs, fv, fvt = [], [], [], []

    def add_face(origin, du, dv):
        origin, du, dv = np.array(origin, float), np.array(du, float), np.array(dv, float)
        base_p = len(P)
        for j in range(n + 1):
            for i in range(n + 1):
                P.append((origin + (i / n) * du + (j / n) * dv).tolist())
        vid = lambda i, j: base_p + j * (n + 1) + i
        for j in range(n):
            for i in range(n):
                corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
                base_uv = len(uvs)
                uvs.extend([[a * cell * uv_per_unit, b * cell * uv_per_unit] for a, b in corners])
                v = [vid(a, b) for a, b in corners]
                fv.append([v[0], v[1], v[2]])
                fv.append([v[0], v[2], v[3]])
                fvt.append([base_uv, base_uv + 1, base_uv + 2])
                fvt.append([base_uv, base_uv + 2, base_uv + 3])

    # du, dv chosen per face so cross(du, dv) points OUTWARD (away from the box).
    add_face((0, 0, 0), (0, s, 0), (s, 0, 0))  # z = 0, outward -z
    add_face((0, 0, s), (s, 0, 0), (0, s, 0))  # z = s, outward +z
    add_face((0, 0, 0), (s, 0, 0), (0, 0, s))  # y = 0, outward -y
    add_face((0, s, 0), (0, 0, s), (s, 0, 0))  # y = s, outward +y
    add_face((0, 0, 0), (0, 0, s), (0, s, 0))  # x = 0, outward -x
    add_face((s, 0, 0), (0, s, 0), (0, 0, s))  # x = s, outward +x

    return _mesh("gridded_box", P, uvs, fv, fvt)


def open_box_with_cells(size=10.0, gap=0.2):
    """A box with the y=0 side missing (the opening); the other 5 sides are solid (10 tris,
    indices 0-9). Two square inner partitions perpendicular to y, centred in the x/z
    cross-section, each leaving a `gap` fraction of the box open all around its edges so rays
    can thread past it: `near` (indices 10-11) sits close to the opening at y = 0.3*size,
    `deep` (indices 12-13) sits close to the solid back wall at y = 0.7*size (the back wall
    itself is at y = size). A ray escaping from `deep` must also thread past `near`'s gap, so
    `deep` is less exposed than `near`, though both see the opening through some directions."""
    s = size
    lo, hi = gap * s, (1 - gap) * s
    P, uvs, fv, fvt = [], [], [], []

    def add_quad(corners):
        pts = np.array(corners, float)
        keep = [a for a in range(3) if np.ptp(pts[:, a]) > 0]
        base = len(P)
        P.extend(corners)
        ub = len(uvs)
        uvs.extend((pts[:, keep] * 0.1).tolist())
        fv.append([base, base + 1, base + 2])
        fv.append([base, base + 2, base + 3])
        fvt.append([ub, ub + 1, ub + 2])
        fvt.append([ub, ub + 2, ub + 3])

    add_quad([[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0]])  # bottom z=0
    add_quad([[0, 0, s], [0, s, s], [s, s, s], [s, 0, s]])  # top z=s
    add_quad([[0, s, 0], [s, s, 0], [s, s, s], [0, s, s]])  # back y=s (solid; y=0 is the opening)
    add_quad([[0, 0, 0], [0, s, 0], [0, s, s], [0, 0, s]])  # side x=0
    add_quad([[s, 0, 0], [s, 0, s], [s, s, s], [s, s, 0]])  # side x=s

    add_quad([[lo, 0.3 * s, lo], [hi, 0.3 * s, lo], [hi, 0.3 * s, hi], [lo, 0.3 * s, hi]])  # near partition
    add_quad([[lo, 0.7 * s, lo], [hi, 0.7 * s, lo], [hi, 0.7 * s, hi], [lo, 0.7 * s, hi]])  # deep partition

    return _mesh("open_box_with_cells", P, uvs, fv, fvt)


def box_with_partition_and_stitch(size=10.0):
    """`box_with_partition()` plus ONE genuinely collinear zero-area triangle: a new midpoint
    vertex at `(size/2, 0, 0)` on the cube's own `(0,0,0)-(size,0,0)` edge, stitched as the
    triangle `(0,0,0)-(size/2,0,0)-(size,0,0)` -- the kind of T-junction stitching a SketchUp
    export leaves behind. Face 14 is that stitch; faces 12-13 are still the sealed partition."""
    m = box_with_partition(size)
    mid_v, mid_uv, n = len(m.positions), len(m.uvs), m.n_faces
    m.positions = np.vstack([m.positions, [[size / 2.0, 0.0, 0.0]]])
    m.uvs = np.vstack([m.uvs, [[size / 2.0 * 0.1, 0.0]]])
    m.face_v = np.vstack([m.face_v, [[0, mid_v, 1]]])
    m.face_vt = np.vstack([m.face_vt, [[0, mid_uv, 1]]])
    m.face_vn = np.vstack([m.face_vn, [[-1, -1, -1]]])
    m.face_material = np.append(m.face_material, 0)
    m.face_line = np.append(m.face_line, n + 1)
    m.name = "box_with_partition_and_stitch"
    return m


def floor_with_sliver(apex_x=0.0, centre_y=0.0, half_width=5e-5, half_len=500.0,
                      half_floor=600.0, height=5.0):
    """A big floor quad (material 0, faces 0-1) at `z = 0`, plus ONE long thin triangle
    (material 1, face 2) floating `height` above it: `2 * half_len` long and `2 * half_width`
    wide, so its area (`half_len * 2 * half_width`) is under `1e-7 * longest_edge**2` and
    `engine.topo.adjacency.degenerate_mask`'s RELATIVE test calls it zero-area -- even though it
    is a real surface with real area that a ray can really hit, on a differently coloured
    background. Its apex is at `x = apex_x` and its centre line runs along `y = centre_y`, so a
    caller can put a chosen pixel ray straight through it. `coord_decimals=6` keeps the width
    from being welded away (at the default 2 it would round to a genuinely collapsed triangle)."""
    P = [[-half_floor, -half_floor, 0.0], [half_floor, -half_floor, 0.0],
         [half_floor, half_floor, 0.0], [-half_floor, half_floor, 0.0],
         [apex_x - half_len, centre_y - half_width, height],
         [apex_x + half_len, centre_y - half_width, height],
         [apex_x, centre_y + half_width, height]]
    uvs = [[p[0] * 0.01, p[1] * 0.01] for p in P]
    fv = [[0, 1, 2], [0, 2, 3], [4, 5, 6]]
    return _mesh("floor_with_sliver", P, uvs, fv, fv, materials=("floor", "sliver"),
                 face_material=[0, 0, 1], coord_decimals=6)


def rounded_long_slab(n_small=28, big=300.0, small=50.0, width=120.0, y=24000.0, step=0.1,
                      uv_per_unit=0.05):
    """A 60-vertex, 58-triangle strip carrying the real export's ROUNDING NOISE.

    It sits near 24,000 in, so `engine.topo.weld.axis_quanta` gives Y a 0.1 in quantum -- one
    printed step -- and the two vertices at `x = 0` are printed exactly one quantum high, the
    noise a 0.1 in print leaves on a nominally flat surface. Every vertex is therefore within one
    quantum of the strip's own best-fit plane: this IS one flat face.

    The LARGEST triangle (the seed `cluster_planes` starts from) is in the wide first cell at that
    end, so the SEED's own plane is tilted by `step / big`; over the strip's full length that tilt
    puts the far end far outside `1.5 * sum(|n_i| * q_i)`. Seeded from one triangle, one SketchUp
    face splits into several regions -- until the plane is refit to what it has collected."""
    xs = [0.0, big] + [big + k * small for k in range(1, n_small + 1)]
    cols = len(xs)
    P = [[x, y + (step if i == 0 else 0.0), j * width] for j in (0, 1) for i, x in enumerate(xs)]
    uvs, fv, fvt = [], [], []
    for i in range(cols - 1):
        corners = [(i, 0), (i + 1, 0), (i + 1, 1), (i, 1)]
        base = len(uvs)
        uvs.extend([[xs[a] * uv_per_unit, b * width * uv_per_unit] for a, b in corners])
        v = [b * cols + a for a, b in corners]
        fv += [[v[0], v[1], v[2]], [v[0], v[2], v[3]]]
        fvt += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
    return _mesh("rounded_long_slab", P, uvs, fv, fvt)


def creased_pair(angle_deg=3.0, length=120.0, width=120.0, y=24000.0, uv_per_unit=0.05):
    """Two same-material quads hinged along `x = 0`, the second tilted by `angle_deg` about that
    hinge: faces 0-1 are the flat one, faces 2-3 the tilted one.

    At 3 degrees the two normals are well inside `facing_dot` (cos 3 deg = 0.9986 > 0.9), so only
    the plane-distance test can tell them apart -- a genuinely different plane that no amount of
    refitting may swallow. It is also above the 1 degree coplanar threshold and at or below the 5
    degree soft ceiling, which makes its shared hinge edge the EDGE_SOFT fixture."""
    a = np.radians(angle_deg)
    tip_x, tip_y = length * np.cos(a), y + length * np.sin(a)
    P = [[-length, y, 0.0], [0.0, y, 0.0], [tip_x, tip_y, 0.0],
         [-length, y, width], [0.0, y, width], [tip_x, tip_y, width]]
    uvs = [[-length * uv_per_unit, 0.0], [0.0, 0.0], [0.0, width * uv_per_unit],
           [-length * uv_per_unit, width * uv_per_unit],
           [0.0, 0.0], [length * uv_per_unit, 0.0], [length * uv_per_unit, width * uv_per_unit],
           [0.0, width * uv_per_unit]]
    fv = [[0, 1, 4], [0, 4, 3], [1, 2, 5], [1, 5, 4]]
    fvt = [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]]
    return _mesh("creased_pair", P, uvs, fv, fvt)


def arc_topped_strip(n=12, half_span=110.0, sag=0.8, top_z=100.0, y=24000.0, uv_per_unit=0.05):
    """A strip of `n - 1` quads whose BOTTOM edge is straight and whose TOP edge is a gentle
    parabolic arc through `n` vertices, at y ≈ 24,000 in so `axis_quanta` gives the ring
    simplification the real file's 0.15 in bound (`1.5 * max(q)`, q_y = 0.1).

    The arc is scaled so that the farthest top vertex is exactly `sag` (0.8 in) from the chord
    between the two END top vertices, while each top vertex is only `sag * (2 / (n - 1))**2`
    (0.027 in) from the chord of its OWN two neighbours. Every vertex therefore passes a
    per-vertex collinearity test at that bound -- drop them one after another and the boundary
    ends up `sag` away from where it started, five times the bound the guard's ring test assumes.
    Keeping the whole polyline inside the bound is what Ramer-Douglas-Peucker is for."""
    xs = np.linspace(-half_span, half_span, n)
    c = sag / (half_span ** 2 - float(xs[np.argmin(np.abs(xs))]) ** 2)
    zs = top_z - c * xs ** 2
    P = [[float(x), y, 0.0] for x in xs] + [[float(x), y, float(z)] for x, z in zip(xs, zs)]
    uvs, fv, fvt = [], [], []
    for k in range(n - 1):
        corners = [k, k + 1, n + k + 1, n + k]
        base = len(uvs)
        uvs.extend([[P[v][0] * uv_per_unit, P[v][2] * uv_per_unit] for v in corners])
        fv += [[corners[0], corners[1], corners[2]], [corners[0], corners[2], corners[3]]]
        fvt += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
    return _mesh("arc_topped_strip", P, uvs, fv, fvt, coord_decimals=4)


def two_slabs_sharing_curved_border(n=12, half_span=110.0, sag=0.8, half_width=120.0,
                                    y=24000.0, uv_per_unit=0.05, outer_sag=0.0):
    """Two coplanar slabs of DIFFERENT materials (so they stay two regions) meeting along a
    gently CURVED border of `n` vertices -- the shared-border counterpart of `arc_topped_strip`.

    The border runs along y and bulges in x by a parabola scaled exactly like `arc_topped_strip`'s
    arc: the farthest border vertex is `sag` (0.8 in) from the chord between the two END border
    vertices, while each one is only `sag * (2 / (n - 1))**2` (0.027 in) from the chord of its own
    two neighbours. At y = 24,000 in `axis_quanta` gives Y a 0.1 in quantum, so the merge's ring
    bound is `1.5 * 0.1 = 0.15` in: every border vertex passes a per-vertex collinearity test and
    the whole polyline does not, which is exactly the case where the two regions must agree on
    WHICH border vertices survive or a T-junction opens between them.

    `outer_sag` (default 0, a straight edge) dips the right slab's OUTER edge inward by that much
    at its middle, on the same parabola: an OPEN border the right slab can only GROW by
    simplifying, with no neighbour on the other side to shrink by the same amount.

    Faces 0..2*(n-1)-1 are the left slab (material 0, x from `-half_width` to the border), the
    rest the right slab (material 1, border to `+half_width`). Both slabs are wound CCW seen from
    +z, so they share the same region normal."""
    u = np.linspace(-half_span, half_span, n)
    u_mid = float(u[np.argmin(np.abs(u))])
    c = sag / (half_span ** 2 - u_mid ** 2)
    xb = -c * u ** 2                       # the border's bulge, -sag at the ends, 0 at the middle
    co = outer_sag / (half_span ** 2 - u_mid ** 2)
    xo = half_width - co * (half_span ** 2 - u ** 2)   # the outer edge: half_width at the ends
    ys = y + u

    P = ([[-half_width, float(t), 0.0] for t in ys]          # 0..n-1   left edge
         + [[float(b), float(t), 0.0] for b, t in zip(xb, ys)]   # n..2n-1  the curved border
         + [[float(o), float(t), 0.0] for o, t in zip(xo, ys)])  # 2n..3n-1 right (outer) edge
    left, mid, right = 0, n, 2 * n

    uvs, fv, fvt, fm = [], [], [], []
    for a, b, material in ((left, mid, 0), (mid, right, 1)):
        for j in range(n - 1):
            corners = [a + j, b + j, b + j + 1, a + j + 1]
            base = len(uvs)
            uvs.extend([[P[v][0] * uv_per_unit, P[v][1] * uv_per_unit] for v in corners])
            fv += [[corners[0], corners[1], corners[2]], [corners[0], corners[2], corners[3]]]
            fvt += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
            fm += [material, material]
    return _mesh("two_slabs_sharing_curved_border", P, uvs, fv, fvt,
                 materials=("m0", "m1"), face_material=fm, coord_decimals=4)


def creased_pair_with_fine_band(angle_deg=3.0, band=12.0, cell=1.2, flat_len=120.0,
                                tilt_len=100.0, width=30.0, y=24000.0, uv_per_unit=0.05):
    """`creased_pair`'s two planes, but with a BAND of small triangles (edge `cell`, under 2 in)
    running along the crease on BOTH sides -- the shape that lets an iterative plane refit walk
    off its own plane.

    Both halves are one material and one UV class, hinged along `x = 0` and spanning `z`. Within
    `band` inches of the hinge the surface is cut into `cell x cell` quads; beyond it each side is
    one long column out to `flat_len` / `tilt_len`, so the LARGEST triangle (the seed
    `cluster_planes` starts from) is in the flat side's outer column.

    Why it is dangerous: at y = 24,000 in the plane tolerance is `1.5 * |n| . q = 0.15` in, while
    a point `d` inches along the TILTED side sits only `d * sin(3 deg) = 0.052 * d` off the FLAT
    plane. Every tilted vertex within 2.9 in of the hinge is therefore inside the flat plane's
    own tolerance AND inside `facing_dot` (cos 3 deg = 0.9986 > 0.9), so the flat region admits
    the first band columns of the wrong side, refits to a plane tilted towards them, admits the
    next columns, and so on -- one SketchUp face per side arriving as one drifting region."""
    a = np.radians(angle_deg)
    zs = [k * cell for k in range(int(round(width / cell)) + 1)]
    alongs = [k * cell for k in range(int(round(band / cell)) + 1)]

    P, uvs, fv, fvt = [], [], [], []

    def add_side(direction, far, sign, reverse):
        """`reverse` flips the corner order so BOTH halves end up wound to the same side. They
        must: `cluster_planes` only ever considers a candidate whose normal is within
        `facing_dot` of the region's, so two halves wound against each other could never drift
        into one another and the fixture would prove nothing."""
        along = alongs + [far]
        base = len(P)
        for z in zs:
            for s in along:
                P.append([float(s * direction[0]), float(y + s * direction[1]), float(z)])
        cols = len(along)
        vid = lambda i, j: base + j * cols + i
        for j in range(len(zs) - 1):
            for i in range(cols - 1):
                corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
                if reverse:
                    corners = corners[::-1]
                ub = len(uvs)
                uvs.extend([[sign * along[p] * uv_per_unit, zs[q] * uv_per_unit]
                            for p, q in corners])
                v = [vid(p, q) for p, q in corners]
                fv.append([v[0], v[1], v[2]])
                fv.append([v[0], v[2], v[3]])
                fvt.append([ub, ub + 1, ub + 2])
                fvt.append([ub, ub + 2, ub + 3])

    add_side((-1.0, 0.0), flat_len, -1.0, True)                          # the flat half, normal -y
    add_side((float(np.cos(a)), float(np.sin(a))), tilt_len, 1.0, False)  # the tilted half
    return _mesh("creased_pair_with_fine_band", P, uvs, fv, fvt, coord_decimals=4)


def stacked_duplicate_slab(nx=6, ny=6, cell=10.0, uv_per_unit=0.05, top_material=0):
    """`grid_slab` carrying a second copy of its OWN surface: every face repeated, over the SAME
    positions, with its own `vt` rows. This is what the real walkway does -- a surface drawn
    twice -- and `weld_exact` folds the two copies onto one set of welded vertices whatever the
    file's own vertex ids were, so at `top_material=0` the duplicate lands in the SAME region as
    the original and every face of it is covered by the union of the others.

    `top_material=1` makes the copies a different material instead: two regions in one plane,
    which is the z-fight this engine reports and never resolves on its own.

    Faces `0 .. 2*nx*ny-1` are the original slab, the rest its copy."""
    P, uvs, fv, fvt, fm = _grid(nx, ny, cell, uv_per_unit)
    n = len(fv)
    base = len(uvs)
    uvs = uvs + list(uvs)
    fv = fv + [list(f) for f in fv]
    fvt = fvt + [[i + base for i in f] for f in fvt]
    fm = fm + [top_material] * n
    materials = ("m0",) if top_material == 0 else ("m0", "m1")
    return _mesh("stacked_duplicate_slab", P, uvs, fv, fvt, materials=materials,
                 face_material=fm)


def partially_overlapping_fins(nx=10, ny=10, cell=15.0, length=50.0, uv_per_unit=0.05):
    """`grid_slab` plus TWO coplanar triangles hinged on the slab's boundary edge from
    `(nx*cell, 0)` to `(nx*cell, cell)` and reaching `length` beyond it, one sloping down to
    `(nx*cell + length, 0)` and one up to `(nx*cell + length, cell)`.

    They overlap each other over a diamond that is exactly HALF of each (measured: 187.5 of
    375 sq in at the defaults) and they overlap no slab face at all, since both lie entirely
    outside `x = nx*cell`. So they are a real same-material overlap pair in which NEITHER face is
    covered -- the case a coverage rule must not touch. Faces `2*nx*ny` and `+1` are the fins."""
    P, uvs, fv, fvt, fm = _grid(nx, ny, cell, uv_per_unit)
    x0, x1 = nx * cell, nx * cell + length
    lo, hi = nx, (nx + 1) + nx          # grid ids of (nx, 0) and (nx, 1)
    tip_lo, tip_hi = len(P), len(P) + 1
    P = P + [[x1, 0.0, 0.0], [x1, cell, 0.0]]
    base = len(uvs)
    uvs = uvs + [[x0 * uv_per_unit, 0.0], [x0 * uv_per_unit, cell * uv_per_unit],
                 [x1 * uv_per_unit, 0.0], [x1 * uv_per_unit, cell * uv_per_unit]]
    # wound CCW seen from +z, like every slab face: `cluster_planes` only considers a candidate
    # whose normal is within `facing_dot` of the region's, so a fin wound the other way would
    # land in its own plane and the fixture would prove nothing.
    fv = fv + [[lo, tip_lo, hi], [lo, tip_hi, hi]]
    fvt = fvt + [[base, base + 2, base + 1], [base, base + 3, base + 1]]
    fm = fm + [0, 0]
    return _mesh("partially_overlapping_fins", P, uvs, fv, fvt, face_material=fm)


def _quads(P, uvs, fv, fvt, fm, quads, material=0, uv_per_unit=0.05):
    """Append each 4-corner loop of `quads` (indices into `P`) as two triangles, with a planar UV
    projection in the quad's own plane. The loop's own order decides the winding."""
    for loop in quads:
        pts = np.asarray([P[i] for i in loop], float)
        keep = [a for a in range(3) if np.ptp(pts[:, a]) > 1e-12][:2]
        base = len(uvs)
        uvs.extend((pts[:, keep] * uv_per_unit).tolist())
        fv += [[loop[0], loop[1], loop[2]], [loop[0], loop[2], loop[3]]]
        fvt += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
        fm += [material, material]


def slab_with_three_skirts(size=40.0, height=8.0, with_bottom=False):
    """The sidewalk's own shape in miniature: a flat top at `z = 0` with vertical skirts on THREE
    sides reaching down to `z = -height`, the fourth (`x = 0`) left open, and no bottom unless
    `with_bottom`.

    Every face is wound OUTWARD. Vertices 0-3 are the top corners and 4-7 the corners at
    `-height`, so a skirt or a bottom that `engine.fixes.solidify` adds lands on vertices that
    already exist and invents none. Faces: 0-1 the top, 2-7 the three skirts, then (optionally)
    8-9 the bottom."""
    s, h = size, height
    P = [[0.0, 0.0, 0.0], [s, 0.0, 0.0], [s, s, 0.0], [0.0, s, 0.0],
         [0.0, 0.0, -h], [s, 0.0, -h], [s, s, -h], [0.0, s, -h]]
    uvs, fv, fvt, fm = [], [], [], []
    loops = [(0, 1, 2, 3),          # top, +z
             (0, 4, 5, 1),          # y = 0 skirt, -y
             (1, 5, 6, 2),          # x = s skirt, +x
             (2, 6, 7, 3)]          # y = s skirt, +y
    if with_bottom:
        loops.append((4, 7, 6, 5))  # bottom, -z
    _quads(P, uvs, fv, fvt, fm, loops)
    return _mesh("slab_with_three_skirts", P, uvs, fv, fvt, face_material=fm)


def two_level_slab(size=40.0, height=8.0, deep=200.0, panel_x=10.0, panel_z=(-120.0, -80.0)):
    """`slab_with_three_skirts(with_bottom=True)` plus two things that make the cap guard earn
    its keep:

    a DEEP FIN hanging from the open edge's corner `(0, 0, 0)` down to `z = -deep` -- a side face
    (`|n_z| = 0`) sharing that corner, so the open edge's measured thickness is `deep` instead of
    `height`. At the default `max_thickness` (50 in since brief 10; 36 before) that is clamped
    away; raise the ceiling and the skirt reaches `z = -deep`.

    a PANEL at `x = panel_x` facing `-x`, spanning `panel_z`, well below the structure and
    exposed on BOTH sides. A skirt that reaches past it covers it from every `-x` view while it
    is still exposed elsewhere -- so the change is not "a face that is now interior", and the cap
    guard has to refuse it."""
    m = slab_with_three_skirts(size, height, with_bottom=True)
    P = m.positions.tolist()
    uvs, fv, fvt = m.uvs.tolist(), m.face_v.tolist(), m.face_vt.tolist()
    fm = m.face_material.tolist()
    lo, hi = panel_z

    base_v = len(P)
    P += [[0.0, 0.0, -deep], [-1.0, 0.0, -deep],                      # the fin's two free corners
          [panel_x, 0.25 * size, hi], [panel_x, 0.75 * size, hi],     # the panel
          [panel_x, 0.75 * size, lo], [panel_x, 0.25 * size, lo]]
    base_uv = len(uvs)
    uvs += [[0.0, 0.0], [0.0, -deep * 0.05], [-1.0 * 0.05, -deep * 0.05]]
    fv.append([0, base_v, base_v + 1])
    fvt.append([base_uv, base_uv + 1, base_uv + 2])
    fm.append(0)
    _quads(P, uvs, fv, fvt, fm, [(base_v + 2, base_v + 3, base_v + 4, base_v + 5)])
    return _mesh("two_level_slab", P, uvs, fv, fvt, face_material=fm)


def slab_with_partial_underside(size=40.0, deep=9.8, shallow=4.0):
    """The reviewer's scenario: a slab whose MEASURED skirt height (9.8 in) is much deeper than
    the real underside it already has (4 in down), and whose underside covers only PART of the
    footprint -- so `_has_bottom`'s 90 % test says "no bottom" and a new one is invented at
    `-deep`, BOXING IN the real underside.

    Faces 0-1 the top (z = 0, wound +z), 2-7 the three skirts down to `-deep` (`x = 0` left
    open), 8-9 the real underside at `-shallow` over the `x >= size/2, y <= size/2` quarter,
    wound DOWN and open on its two free sides, so it is plainly visible from below -- its FRONT
    exposure on this mesh is about half, nowhere near `cover_max_exposure`.

    The top's two triangles have centroids at `(2s/3, s/3)` and `(s/3, 2s/3)`: the underside sits
    under the first and not the second, so exactly 50 % of the region finds something below it."""
    s, d, h = size, deep, shallow
    P = [[0.0, 0.0, 0.0], [s, 0.0, 0.0], [s, s, 0.0], [0.0, s, 0.0],
         [0.0, 0.0, -d], [s, 0.0, -d], [s, s, -d], [0.0, s, -d],
         [s / 2, 0.0, -h], [s, 0.0, -h], [s, s / 2, -h], [s / 2, s / 2, -h]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3),          # top, +z
                                  (0, 4, 5, 1),          # y = 0 skirt, -y
                                  (1, 5, 6, 2),          # x = s skirt, +x
                                  (2, 6, 7, 3),          # y = s skirt, +y
                                  (11, 10, 9, 8)])       # the real underside, -z
    return _mesh("slab_with_partial_underside", P, uvs, fv, fvt, face_material=fm)


def compartment_with_deep_wall(length=60.0, width=10.0, height=10.0, wall_x=45.0, gap=1.0):
    """A long shallow compartment open at `x = 0`, with an interior WALL right at the far end --
    the shape a sidewalk's rib cells really have, and the case the cap guard's third rule exists
    for.

    Faces 0-1 the top (z = 0), 2-3 the bottom (z = -height), 4-9 the three side walls, all wound
    OUTWARD, so every one of them is met on its BACK side from inside. Faces 10-11 are the wall
    at `x = wall_x`, inset by `gap` all round and wound so its normal points at the OPENING
    (-x) -- the one face a ray through the opening meets on its FRONT side. It is `wall_x` in
    from a `width x height` hole, so its front exposure is a fraction of a percent: well under
    `FixProfile.cover_max_exposure`. Closing the opening seals it on both sides."""
    L, W, H, g = length, width, height, gap
    P = [[0.0, 0.0, 0.0], [L, 0.0, 0.0], [L, W, 0.0], [0.0, W, 0.0],
         [0.0, 0.0, -H], [L, 0.0, -H], [L, W, -H], [0.0, W, -H],
         [wall_x, g, -g], [wall_x, W - g, -g], [wall_x, W - g, -H + g], [wall_x, g, -H + g]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3),          # top, +z
                                  (4, 7, 6, 5),          # bottom, -z
                                  (0, 4, 5, 1),          # y = 0 wall, -y
                                  (2, 6, 7, 3),          # y = W wall, +y
                                  (1, 5, 6, 2),          # x = L wall, +x
                                  (8, 9, 10, 11)])       # the deep wall, -x (INWARD)
    return _mesh("compartment_with_deep_wall", P, uvs, fv, fvt, face_material=fm)


def slab_with_two_depths(size=30.0, width=20.0, kink=3.0, deep=9.8, shallow=1.3,
                         with_bottom=False):
    """ONE top region, a flat hexagon at `z = 0`, whose two ends are already skirted to DIFFERENT
    depths: `shallow` at `x = 0` and `deep` at `x = 2 * size`. Its four remaining outline edges
    are open, and each takes its depth from the end it touches -- `shallow`, `deep`, `deep`,
    `shallow`, going round.

    The outline is a hexagon rather than a rectangle for a reason: the two open edges of each
    long side must not share a corner with the deep end, or the deepest side face reaching either
    endpoint wins and both measure `deep`. The kink at `x = size` is a genuine corner, so the
    union cannot simplify it away the way it would a collinear midpoint.

    Every existing side face is an outward-wound skirt of this same slab, so a new skirt covering
    one covers its BACK -- which the cap guard allows under rule 2 -- and the fixture measures
    S-I4 without also testing rule 3.

    `with_bottom` adds a plate at `-(deep + 2)`, DEEPER than the shallowest skirt: the case S-I5's
    extended downward search has to find, so that no second bottom is placed above it.

    Faces: 0-3 the top (quads `(0,1,4,5)` and `(1,2,3,4)`), 4-5 the shallow end skirt, 6-7 the
    deep end skirt, then optionally 8-9 the plate."""
    u, w, k, D, h = size, width, kink, deep, shallow
    P = [[0.0, 0.0, 0.0], [u, -k, 0.0], [2 * u, 0.0, 0.0],
         [2 * u, w, 0.0], [u, w + k, 0.0], [0.0, w, 0.0],
         [0.0, 0.0, -h], [0.0, w, -h],                    # 6, 7: the shallow end
         [2 * u, 0.0, -D], [2 * u, w, -D]]                # 8, 9: the deep end
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 4, 5), (1, 2, 3, 4),   # the top, +z
                                  (0, 5, 7, 6),                 # x = 0 end skirt, -x, shallow
                                  (2, 8, 9, 3)])                # x = 2u end skirt, +x, deep
    if with_bottom:
        base = len(P)
        P += [[0.0, -k, -(D + 2)], [2 * u, -k, -(D + 2)],
              [2 * u, w + k, -(D + 2)], [0.0, w + k, -(D + 2)]]
        _quads(P, uvs, fv, fvt, fm, [(base, base + 3, base + 2, base + 1)])   # the plate, -z
    return _mesh("slab_with_two_depths", P, uvs, fv, fvt, face_material=fm)


def bare_top_quad(size=40.0):
    """A single flat quad at `z = 0` and nothing else: four open outline edges and not one side
    face anywhere in the file, so no edge's height can be measured at all."""
    s = size
    P = [[0.0, 0.0, 0.0], [s, 0.0, 0.0], [s, s, 0.0], [0.0, s, 0.0]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3)])
    return _mesh("bare_top_quad", P, uvs, fv, fvt, face_material=fm)


def slab_with_strays(nx=4, ny=4, cell=10.0, uv_per_unit=0.05, needle_width=0.02,
                     stray=True, needle=True):
    """A 40 x 40 in slab at `z = 0` plus three things a stray-fragment detector has to tell
    apart:

    * a DETACHED 2 in^2 triangle floating at `z = 20` -- one face, well under
      `FixProfile.fragment_max_area`, the thing the detector exists to remove;
    * a DETACHED 5 x 4 in quad at `z = 25`, 20 in^2 in two 10 in^2 triangles. Its longest extent
      (5 in) is UNDER `fragment_max_extent`, so the extent rule alone would take it -- and the
      "never a component holding a face bigger than `fragment_max_area` on its own" rule is what
      saves it. It is there to prove that rule does something;
    * an ATTACHED needle, a `needle_width` deep triangle hanging off the slab's first `y = 0`
      cell edge and SHARING that edge, so it is part of the main component and can only be
      caught as a SLIVER (`4*pi*area/perimeter^2` is about 0.0008, against a 0.02 threshold).

    `stray=False` drops the two detached pieces, `needle=False` the sliver.

    Faces: 0 .. 2*nx*ny-1 the slab, then the needle, then the stray triangle, then the stray
    quad's two -- each only if it is switched on."""
    P, uvs, fv, fvt, fm = _grid(nx, ny, cell, uv_per_unit)
    w = nx * cell
    if needle:
        base = len(P)
        P.append([cell / 2, -needle_width, 0.0])
        ub = len(uvs)
        uvs.extend([[0.0, 0.0], [cell * uv_per_unit, 0.0], [cell / 2 * uv_per_unit, -needle_width]])
        # vertices 0 and 1 are the (0,0) and (1,0) lattice corners, and (0,1) is a real EDGE of
        # the slab's first cell -- sharing it is what puts the needle in the main component,
        # where only the sliver rule can reach it.
        fv.append([0, 1, base])
        fvt.append([ub, ub + 1, ub + 2])
        fm.append(0)
    if stray:
        base = len(P)
        P += [[0.0, 0.0, 20.0], [2.0, 0.0, 20.0], [0.0, 2.0, 20.0]]          # 2 in^2, detached
        ub = len(uvs)
        uvs.extend([[0.0, 0.0], [2.0 * uv_per_unit, 0.0], [0.0, 2.0 * uv_per_unit]])
        fv.append([base, base + 1, base + 2])
        fvt.append([ub, ub + 1, ub + 2])
        fm.append(0)
        base = len(P)
        P += [[10.0, 0.0, 25.0], [15.0, 0.0, 25.0], [15.0, 4.0, 25.0], [10.0, 4.0, 25.0]]
        _quads(P, uvs, fv, fvt, fm, [(base, base + 1, base + 2, base + 3)], uv_per_unit=uv_per_unit)
    return _mesh("slab_with_strays", P, uvs, fv, fvt, face_material=fm)


def union_sliver_region():
    """ONE flat sidewalk region straight out of the real export (`union_sliver_region.obj`: 202 of
    the 203 triangles of region 29 of the CHTM_SIDE_WALK_2nd_floor snapshot `ce26e0392ab0`, as the
    merge receives them after hidden-face removal, flipping and duplicate-layer removal; 136
    welded vertices), read through `read_obj` so the printed precision (2 decimals, 6 significant
    digits, a 0.1 in Y quantum) is inferred exactly as it is for the snapshot.

    Its grid-snapped union (`engine.fixes.merge._union` at `GRID_SIZE`) is one polygon whose
    interior rings are all SLIVERS: each runs along an edge two triangles SHARE, at most a grid
    cell wide, so every one of its coordinates snaps to one of that edge's two end vertices and
    no three existing vertices can bound it. They are the union's, not the surface's: with the
    same triangles their number changes with the order the union combines them (4 in file order,
    4 or 6 over 8 shuffles, shapely 2.1.2 / GEOS 3.13.1), and a full-precision union leaves 10.

    Kept this size on purpose: a greedy search that dropped one triangle at a time could not
    remove any of these 202 without losing the sliver it was following or splitting the region,
    and a fan or a two-ring neighbourhood around a sliver reproduces nothing."""
    return read_obj(Path(__file__).with_name("union_sliver_region.obj"))


def slab_with_lifted_corner(nx=3, nz=2, cell=100.0, y=24000.0, step=0.1, uv_per_unit=0.05):
    """A flat slab in the x-z plane at `y = 24,000` in, `nx x nz` cells of `cell` inches, with
    ONE corner -- `(0, y, 0)`, vertex 0 -- printed one Y quantum (`step`, 0.1 in at this
    magnitude) off the plane: the rounding a 6-significant-digit export leaves on a surface that
    is not axis-aligned in the source model's own coordinates.

    Every vertex is within one quantum of the plane, so `analyse_topology` keeps the slab ONE
    region and `merge_regions` rebuilds it as ONE polygon (measured: a 5-vertex ring, 3
    triangles) -- whose ring is not coplanar: the lifted corner is `step` off the plane of the
    others, 0.042 in off their best fit. SketchUp's own validity check (`SUModelFixErrors`)
    splits a polygon face whose vertices are more than about 1.2e-3 in off its plane, so this
    is the region the SketchUp writer must not ship as one face."""
    cols = nx + 1
    P = [[i * cell, y + (step if (i, k) == (0, 0) else 0.0), k * cell]
         for k in range(nz + 1) for i in range(nx + 1)]
    uvs, fv, fvt = [], [], []
    for k in range(nz):
        for i in range(nx):
            corners = [(i, k), (i + 1, k), (i + 1, k + 1), (i, k + 1)]
            base = len(uvs)
            uvs.extend([[a * cell * uv_per_unit, b * cell * uv_per_unit] for a, b in corners])
            v = [b * cols + a for a, b in corners]
            fv += [[v[0], v[1], v[2]], [v[0], v[2], v[3]]]
            fvt += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
    return _mesh("slab_with_lifted_corner", P, uvs, fv, fvt)


def printed_ramp(nx=4, ny=3, cell=40.0, slope_deg=23.2, x0=2870.0, y0=23700.0, z0=1931.38,
                 uv_per_unit=0.05):
    """A ramp like file B's (`0b290ec0bcb4`, normal `[0.394, 0, 0.919]`): `nx x ny` cells of
    `cell` inches, falling `slope_deg` degrees along +x, printed exactly as that export prints
    (2 decimals, 6 significant digits: 0.01 in on X and Z, 0.1 in on Y near y = 24,000).

    Rounding Z to 0.01 in scatters the vertices about the plane, so the region is NOT flat:
    its vertices spread 0.0046 in along its own normal (measured). An axis-aligned slab printed
    the same way is exactly flat -- every vertex sits on the plane -- which is the difference the
    merge's snap tolerance is read from (`engine.fixes.merge.snap_tolerance`). One region; the
    merge rebuilds it as 2 triangles."""
    rise = float(np.tan(np.radians(slope_deg)))
    cols = nx + 1
    P = [[round(x0 + i * cell, 2), round(y0 + j * cell, 1), round(z0 - rise * i * cell, 2)]
         for j in range(ny + 1) for i in range(nx + 1)]
    uvs, fv, fvt = [], [], []
    for j in range(ny):
        for i in range(nx):
            corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            base = len(uvs)
            uvs.extend([[a * cell * uv_per_unit, b * cell * uv_per_unit] for a, b in corners])
            v = [b * cols + a for a, b in corners]
            fv += [[v[0], v[1], v[2]], [v[0], v[2], v[3]]]
            fvt += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
    return _mesh("printed_ramp", P, uvs, fv, fvt)


def t_junction_lattice_region():
    """ONE sloped underside region straight out of the real export (`t_junction_lattice_region.obj`:
    all 274 triangles of region 70 of the CHTM_SIDE_WALK_2nd_floor snapshot `ce26e0392ab0`, as
    the merge receives them; 218 welded vertices), read through `read_obj` so the printed
    precision (2 decimals, 6 significant digits, a 0.1 in Y quantum) is inferred exactly as it is
    for the snapshot. The big underside sloped 8 degrees at the right-hand end of that model.

    Its triangulation is a lattice with T-JUNCTIONS: vertices lie exactly on the long edges of
    neighbouring triangles (vertex (2594.51, 23141.9, 1766.4) is 0.000000 in off the 236.2 in
    edge it sits on). In exact arithmetic the two sides meet along that line; the grid-snapped
    union (`engine.fixes.merge._union` at `GRID_SIZE`) moves the long edge and the short ones
    independently, so they part by a grid cell and cross again at an angle of about 4e-7 rad.
    The union keeps 12 real openings (0.25 to 1.27 in wide) and 3 SLIVERS 5e-5 to 9e-5 in wide
    along those lines: one collapses to two vertices, one snaps to three distinct collinear
    vertices, and one has a corner 7.87 in from every vertex -- where the two snapped edges
    cross. Four of its triangles overlap each other (rule 3). Reproduces as a standalone mesh:
    one region, the same union."""
    return read_obj(Path(__file__).with_name("t_junction_lattice_region.obj"))


def ramp_fan_region():
    """ONE ramp region straight out of the real export (`ramp_fan_region.obj`: all 49 triangles of
    region 47 of the CHTM_2nd_to_3rd_building_sidewalk_outside snapshot `0b290ec0bcb4`, as the
    merge receives them; 51 welded vertices), read through `read_obj`. Sloped 23 degrees, normal
    `[0.3939, 0, 0.9191]`, 0.0085 in thick along its normal.

    A fan of 125 to 553 in long triangles meets at vertex (2909.47, 24204.9, 1914.51) with its
    edges 0.3 to 4.7 degrees apart. The grid-snapped union leaves a sliver there whose tip lands
    0.0016 in from that vertex -- the corner `new_vertex` used to refuse -- and two slivers one
    grid cell wide along T-junction lines whose corners snap to 3 and 4 distinct collinear
    vertices, which a rebuilt polygon cannot carry as holes. Reproduces as a standalone mesh:
    one region, the same union."""
    return read_obj(Path(__file__).with_name("ramp_fan_region.obj"))


def frame_with_crossed_seam(size=1000.0, band=100.0, gap=6e-4, uv_per_unit=0.05):
    """ONE flat region: a square frame `size` inches across, its band `band` wide, closed at the
    middle of its bottom side by a SEAM whose two edges cross. The bottom band's left half ends
    in edge 8-9 and its right half starts with edge 11-10; each runs across the band from one
    border to the other with its ends `gap` apart the opposite way round, so the two edges cross
    halfway across the band, 50 in from every vertex, at an angle of 3.4e-4 degrees.

    Faces 0 `(0, 8, 9)` and 3 `(10, 5, 11)` carry the two seam edges. They overlap by 0.015 sq in
    near the inner border, under rule 3's `1e-6 * 20,000 sq in`, so the merge keeps both in the
    region's union; near the outer border they leave a notch `gap` wide at its mouth -- six grid
    cells, far wider than a union sliver -- whose tip is the crossing: a union corner no vertex
    explains. The seam ends are printed to 4 decimals (`coord_decimals=4`) so they do not weld.
    Vertex 11 lies on edge 9-4 and vertex 9 on edge 5-11: the only T-junctions, both in the
    input."""
    L, t, h = size, band, gap / 2
    P = [[0, 0, 0], [L, 0, 0], [L, L, 0], [0, L, 0],                     # 0-3 outer corners
         [t, t, 0], [L - t, t, 0], [L - t, L - t, 0], [t, L - t, 0],     # 4-7 inner corners
         [L / 2 - h, 0, 0], [L / 2 + h, t, 0],                           # 8, 9: left seam edge
         [L / 2 + h, 0, 0], [L / 2 - h, t, 0]]                           # 10, 11: right seam edge
    fv = [[0, 8, 9], [0, 9, 4],          # bottom band, left half
          [10, 1, 5], [10, 5, 11],       # bottom band, right half
          [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]
    uvs = [[p[0] * uv_per_unit, p[1] * uv_per_unit] for p in P]
    return _mesh("frame_with_crossed_seam", P, uvs, fv, fv, coord_decimals=4)


def _with_wall(P, uvs, fv, fvt, fm, foot0, foot1, height, uv_per_unit=0.05):
    """Append one vertical wall triangle of material 0 standing on the segment foot0-foot1 of
    the `z = 0` plane (its feet are new vertices, shared with nothing), apex `height` up."""
    base, ub = len(P), len(uvs)
    mid = [(a + b) / 2 for a, b in zip(foot0, foot1)]
    P = P + [list(foot0), list(foot1), [mid[0], mid[1], height]]
    span = float(np.hypot(foot1[0] - foot0[0], foot1[1] - foot0[1]))
    uvs = uvs + [[0.0, 0.0], [span * uv_per_unit, 0.0],
                 [span / 2 * uv_per_unit, height * uv_per_unit]]
    return (P, uvs, fv + [[base, base + 1, base + 2]], fvt + [[ub, ub + 1, ub + 2]],
            list(fm) + [0])


def two_region_quad(size=40.0, seam=0.37, material=0, flip=False, wall=False, uv_per_unit=0.05):
    """`bare_top_quad`'s two triangles, flat at `z = 0`, with the second one's UVs shifted by a
    non-integer `seam` -- a real texture seam -- so `analyse_topology` puts them in TWO regions
    and classes their shared diagonal (0,0,0)-(size,size,0) EDGE_REAL: the topology alone never
    hides it. `material=1` gives the second triangle material `m1`; `flip=True` winds it
    backwards (normal -z), as the export winds some panel triangles against their neighbours;
    `wall=True` stands a vertical triangle on the middle three quarters of the diagonal."""
    s = size
    P = [[0.0, 0.0, 0.0], [s, 0.0, 0.0], [s, s, 0.0], [0.0, s, 0.0]]
    uv = np.asarray(P, float)[:, :2] * uv_per_unit
    uvs = np.vstack([uv, uv + seam]).tolist()
    second = [0, 3, 2] if flip else [0, 2, 3]
    fv = [[0, 1, 2], second]
    fvt = [[0, 1, 2], [4 + v for v in second]]
    fm = [0, material]
    if wall:
        P, uvs, fv, fvt, fm = _with_wall(P, uvs, fv, fvt, fm, (s / 8, s / 8, 0.0),
                                         (7 * s / 8, 7 * s / 8, 0.0), s / 2, uv_per_unit)
    materials = ("m0", "m1") if material else ("m0",)
    return _mesh("two_region_quad", P, uvs, fv, fvt, materials=materials, face_material=fm)


def t_junction_seam_strip(seam=0.37, wall=False, uv_per_unit=0.05):
    """`t_junction_strip` without its zero-area stitch and with the two upper quads' UVs shifted
    by a non-integer `seam`. The big quad's long top edge (0,10)-(20,10) runs along the two upper
    quads' short edges (0,10)-(10,10) and (10,10)-(20,10), which meet at (10,10) in the middle of
    it -- a T-junction no face closes. The seam makes the big quad and the upper quads two
    regions, so `analyse_topology` classes all three EDGE_TJUNCTION, which it never hides.
    `wall=True` stands a vertical triangle on (2,10)-(18,10), across the T-vertex."""
    P = [[0, 0, 0], [20, 0, 0], [20, 10, 0], [0, 10, 0], [10, 10, 0], [0, 20, 0], [10, 20, 0],
         [20, 20, 0]]
    fv = [[0, 1, 2], [0, 2, 3], [3, 4, 6], [3, 6, 5], [4, 2, 7], [4, 7, 6]]
    uv = np.asarray(P, float)[:, :2] * uv_per_unit
    uvs = np.vstack([uv, uv + seam]).tolist()
    fvt = fv[:2] + [[v + len(P) for v in f] for f in fv[2:]]
    fm = [0] * len(fv)
    if wall:
        P, uvs, fv, fvt, fm = _with_wall(P, uvs, fv, fvt, fm, (2.0, 10.0, 0.0), (18.0, 10.0, 0.0),
                                         8.0, uv_per_unit)
    return _mesh("t_junction_seam_strip", P, uvs, fv, fvt, face_material=fm)


def staggered_slabs(uv_per_unit=0.05):
    """Two coplanar 20 x 10 slabs of one material, B shifted half a slab: A = [0,20] x [0,10],
    B = [10,30] x [10,20]. A's top edge (0,10)-(20,10) and B's bottom edge (10,10)-(30,10) lie
    on one line and overlap along x in [10, 20] -- a line inside the surface there -- while each
    is the slabs' real outline over its other half. Neither is split where the other ends."""
    P = [[0, 0, 0], [20, 0, 0], [20, 10, 0], [0, 10, 0], [10, 10, 0], [30, 10, 0], [30, 20, 0],
         [10, 20, 0]]
    fv = [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]]
    uvs = (np.asarray(P, float)[:, :2] * uv_per_unit).tolist()
    return _mesh("staggered_slabs", P, uvs, fv, fv)


def back_to_back_pair(size=40.0, uv_per_unit=0.05):
    """Two DIFFERENT coplanar triangles of one material on the SAME side of the edge
    (0,0,0)-(size,0,0) they share, wound against each other (normals +z and -z): an
    overlapping double layer, as the export has on some walls. The shared edge is where both
    end -- the outline -- although its two faces are coplanar and of one material. Each
    triangle's sloped side runs through the other layer for part of its length."""
    s = size
    P = [[0.0, 0.0, 0.0], [s, 0.0, 0.0], [0.0, s, 0.0], [s, 0.75 * s, 0.0]]
    fv = [[0, 1, 2], [1, 0, 3]]
    uvs = (np.asarray(P, float)[:, :2] * uv_per_unit).tolist()
    return _mesh("back_to_back_pair", P, uvs, fv, fv)


def split_double_layer(uv_per_unit=0.05):
    """A 20 x 8 quad at `z = 0` (normal +z) with a second layer of one material lying on it,
    wound the other way (normal -z) and split in two at x = 10: triangles (0,0)-(10,0)-(5,4)
    and (10,0)-(20,0)-(15,4). The quad's bottom edge (0,0)-(20,0) and the two triangles' bottom
    edges (0,0)-(10,0), (10,0)-(20,0) run along each other with every face ABOVE them: each is
    the outline, although each lies on the others' boundary along its whole length."""
    P = [[0, 0, 0], [20, 0, 0], [20, 8, 0], [0, 8, 0], [10, 0, 0], [5, 4, 0], [15, 4, 0]]
    fv = [[0, 1, 2], [0, 2, 3], [0, 5, 4], [4, 6, 1]]
    uvs = (np.asarray(P, float)[:, :2] * uv_per_unit).tolist()
    return _mesh("split_double_layer", P, uvs, fv, fv)


def slab_beside_gridded_neighbour(seam=0.37, material=0, uv_per_unit=0.05):
    """A 40 x 20 slab of two triangles at `z = 0` -- vertices 0 (0,0), 1 (40,0), 2 (40,20),
    3 (0,20) -- and above it a 40 x 10 neighbour gridded into four 10 x 10 cells, whose bottom
    border vertices 4 (10,20), 5 (20,20) and 6 (30,20) lie EXACTLY on the slab's top edge 3-2:
    three T-junctions no face closes, as the export leaves them along a merged slab. The top row
    is 7 (0,30) .. 11 (40,30).

    The neighbour's UVs are shifted by a non-integer `seam` (a texture seam), so the two are
    separate regions of ONE material -- a line inside a surface wherever the slab's edge is not
    split; `material=1` gives the neighbour material `m1` instead. Both wound to +z."""
    P = [[0, 0, 0], [40, 0, 0], [40, 20, 0], [0, 20, 0], [10, 20, 0], [20, 20, 0], [30, 20, 0],
         [0, 30, 0], [10, 30, 0], [20, 30, 0], [30, 30, 0], [40, 30, 0]]
    bottom, top = [3, 4, 5, 6, 2], [7, 8, 9, 10, 11]
    fv = [[0, 1, 2], [0, 2, 3]]
    for i in range(4):
        v0, v1, v2, v3 = bottom[i], bottom[i + 1], top[i + 1], top[i]
        fv += [[v0, v1, v2], [v0, v2, v3]]
    uv = np.asarray(P, float)[:, :2] * uv_per_unit
    uvs = np.vstack([uv, uv + seam]).tolist()
    fvt = fv[:2] + [[v + len(P) for v in f] for f in fv[2:]]
    fm = [0, 0] + [material] * (len(fv) - 2)
    materials = ("m0", "m1") if material else ("m0",)
    return _mesh("slab_beside_gridded_neighbour", P, uvs, fv, fvt, materials=materials,
                 face_material=fm)


def triangle_under_gridded_slab(uv_per_unit=0.05):
    """A 40 x 20 slab at `z = 0` gridded into 4 x 2 cells of 10 in (material `m0`, vertices
    `j * 5 + i` at `(10 i, 10 j)`, faces 0-15) and below it ONE triangle, face 16,
    0 (0,0) - 15 (20,-20) - 4 (40,0), of material `m1`: a region of one face, which the merge
    copies through unmerged. Its top edge 0-4 runs along the slab's bottom border, whose vertices
    1 (10,0), 2 (20,0) and 3 (30,0) lie exactly on it. Every vertex's UV is its `xy *
    uv_per_unit`; everything is wound to +z."""
    P = [[i * 10.0, j * 10.0, 0.0] for j in range(3) for i in range(5)] + [[20.0, -20.0, 0.0]]
    fv = []
    for j in range(2):
        for i in range(4):
            v = [j * 5 + i, j * 5 + i + 1, (j + 1) * 5 + i + 1, (j + 1) * 5 + i]
            fv += [[v[0], v[1], v[2]], [v[0], v[2], v[3]]]
    fv.append([0, 15, 4])
    uvs = (np.asarray(P, float)[:, :2] * uv_per_unit).tolist()
    return _mesh("triangle_under_gridded_slab", P, uvs, fv, fv, materials=("m0", "m1"),
                 face_material=[0] * 16 + [1])


def slab_with_a_wall_foot_on_its_diagonal(uv_per_unit=0.05):
    """`grid_slab(10, 10)` (100 x 100 in at `z = 0`, material `m0`) with one vertical wall
    triangle standing inside it: feet (50,50,0) -- the slab's centre, which welds to the grid
    vertex there and lies on BOTH diagonals of the square, so on whichever one the merged slab's
    two triangles share -- and (65,45,0), inside a cell and on no diagonal; apex 25 in up over
    their middle. The wall uses the centre, so the merged slab's diagonal runs through a vertex
    the output uses."""
    P, uvs, fv, fvt, fm = _grid(10, 10, 10.0, uv_per_unit)
    P, uvs, fv, fvt, fm = _with_wall(P, uvs, fv, fvt, fm, (50.0, 50.0, 0.0), (65.0, 45.0, 0.0),
                                     25.0, uv_per_unit)
    return _mesh("slab_with_a_wall_foot_on_its_diagonal", P, uvs, fv, fvt, face_material=fm)


def _slab_from_top(name, top, size=40.0, height=8.0, materials=("m0",), top_material=None,
                   uv_per_unit=0.05):
    """A closed `size` x `size` x `height` slab whose TOP, at `z = 0`, is the triangles `top`
    (each a triple of `(x, y)` points, wound here to +z), over four outward sides and a -z
    bottom, each of those two triangles on the square's corners. Faces `0 .. len(top) - 1` are
    `top` in order, then the 10 side and bottom faces; `top_material[i]` is top face `i`'s
    material (0 by default). A top vertex lying on the square's outline meets the side below it
    at a T-junction, never a gap."""
    P, index = [], {}

    def vid(x, y, z):
        key = (round(float(x), 6), round(float(y), 6), round(float(z), 6))
        if key not in index:
            index[key] = len(P)
            P.append([float(x), float(y), float(z)])
        return index[key]

    uvs, fv, fvt, fm = [], [], [], []
    for i, ((ax, ay), (bx, by), (cx, cy)) in enumerate(top):
        a, b, c = vid(ax, ay, 0.0), vid(bx, by, 0.0), vid(cx, cy, 0.0)
        if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) < 0:
            b, c = c, b
        base = len(uvs)
        uvs.extend((np.array([P[a], P[b], P[c]])[:, :2] * uv_per_unit).tolist())
        fv.append([a, b, c])
        fvt.append([base, base + 1, base + 2])
        fm.append(0 if top_material is None else int(top_material[i]))
    s, h = size, height
    k = [vid(0, 0, 0), vid(s, 0, 0), vid(s, s, 0), vid(0, s, 0),
         vid(0, 0, -h), vid(s, 0, -h), vid(s, s, -h), vid(0, s, -h)]
    _quads(P, uvs, fv, fvt, fm, [(k[0], k[4], k[5], k[1]), (k[1], k[5], k[6], k[2]),
                                  (k[2], k[6], k[7], k[3]), (k[3], k[7], k[4], k[0]),
                                  (k[4], k[7], k[6], k[5])], uv_per_unit=uv_per_unit)
    return _mesh(name, P, uvs, fv, fvt, materials=materials, face_material=fm)


def slab_with_infill_patch(size=40.0, height=8.0, patch=(18.5, 21.5, 19.5, 20.5)):
    """Review C2's probe, as a fixture: a closed slab whose top holds a 3 x 1 in INFILL PATCH --
    a real piece of the walking surface, two triangles, 3 sq in -- that meets the surrounding top
    only through T-JUNCTIONS: the surround has a vertex at the middle of each of the patch's four
    sides and the patch has none, so the two share corner vertices but not one welded edge.

    The surround is `shapely.constrained_delaunay_triangles` of the square with the patch as a
    hole (built exactly as `docs/superpowers/records/scripts/review-probes/probe_fragment_patch.py`
    builds it). Faces: the surround, then the patch (`n_faces - 12` and `n_faces - 11`), then the
    four sides and the bottom (`_slab_from_top`)."""
    import shapely

    x0, x1, y0, y1 = patch
    hole = [(x0, y0), ((x0 + x1) / 2, y0), (x1, y0), (x1, (y0 + y1) / 2), (x1, y1),
            ((x0 + x1) / 2, y1), (x0, y1), (x0, (y0 + y1) / 2)]
    surround = shapely.Polygon([(0, 0), (size, 0), (size, size), (0, size)], [hole])
    top = [tuple(tuple(p) for p in np.asarray(t.exterior.coords)[:3, :2])
           for t in shapely.constrained_delaunay_triangles(surround).geoms]
    top += [((x0, y0), (x1, y0), (x1, y1)), ((x0, y0), (x1, y1), (x0, y1))]
    return _slab_from_top("slab_with_infill_patch", top, size, height)


def slab_with_coplanar_patch(size=40.0, height=8.0, patch=(25.0, 26.0, 10.0, 11.0), lift=0.0):
    """A closed slab whose top is two triangles (faces 0 and 1, material `m0`), with a 1 x 1 in
    PATCH of material `m1` (faces 2 and 3) lying IN the top's plane, wholly inside face 0: a
    painted mark. The patch shares no vertex and no edge with anything, and none of its vertices
    lies on another face's edge -- it touches the top only by lying on it. `lift` raises the
    patch that far above the top instead, parallel to it: then it touches nothing at all."""
    s = size
    x0, x1, y0, y1 = patch
    top = [((0, 0), (s, 0), (s, s)), ((0, 0), (s, s), (0, s)),
           ((x0, y0), (x1, y0), (x1, y1)), ((x0, y0), (x1, y1), (x0, y1))]
    m = _slab_from_top("slab_with_coplanar_patch", top, size, height, materials=("m0", "m1"),
                       top_material=[0, 0, 1, 1])
    m.positions[np.unique(m.face_v[[2, 3]]), 2] += lift     # the patch's own four vertices
    return m


def slab_with_interior_strip(width=0.26, length=29.5, size=40.0, height=8.0):
    """A closed slab whose top carries a STRIP of real surface in its middle: face 0, one
    triangle over a `length` in base along `y = size / 2` with its apex `width` in above it, so
    `width` is exactly how far any point of it lies from the base. It shares all three edges with
    the fat triangles around it (faces 1-10, fanned from the square's corner and from the middle
    of its far side), so removing it opens a slit `width` wide through the top.

    At the defaults it is file B's wall strips in miniature (faces 692, 698, 1804 and 2734 of
    `0b290ec0bcb4`'s solidified reference: 29.5 in long, 0.26 in wide, 3.84 sq in): quality
    about 0.014 and area under 4 sq in, so the sliver rule's quality and area tests both name it."""
    s = size
    y = s / 2.0
    xa, xb, xm = (s - length) / 2.0, (s + length) / 2.0, s / 2.0
    a, b, c, t = (xa, y), (xb, y), (xm, y + width), (xm, s)
    top = [(a, b, c),
           ((0, 0), (s, 0), (s, y)), ((0, 0), (s, y), b), ((0, 0), b, a), ((0, 0), a, (0, y)),
           (a, c, t), (c, b, t), ((0, y), a, t), ((0, y), t, (0, s)), (b, (s, y), t),
           ((s, y), (s, s), t)]
    return _slab_from_top("slab_with_interior_strip", top, size, height)


def printed(mesh, step=0.1):
    """`mesh` as the real exports print it: the same geometry, with `sig_digits` set so the
    coarsest axis quantum (`engine.topo.weld.axis_quanta`) is `step` in. Both real files print Y
    to 0.1 in near 24,000 in, and every tolerance the engine derives from the print step -- the
    T-junction search, the merge's `default_collinear_tol`, the guards' `depth_tol` and border
    shift -- is 0.15 in there. At the fixtures' own 6 significant digits a 40 in slab prints to
    1e-4 in and every one of those is 1.5e-4 in, so a test about what those tolerances allow has
    to give its fixture the real files' print step."""
    import math
    from dataclasses import replace

    largest = float(np.abs(np.asarray(mesh.positions, dtype=np.float64)).max())
    sig_digits = math.ceil(math.log10(largest)) - round(math.log10(step))
    return replace(mesh, sig_digits=int(sig_digits))


def slab_with_t_joined_strip(width=0.1, length=29.5, size=40.0, height=8.0, join="vertex"):
    """`slab_with_interior_strip`, except that the surface below the strip meets its BASE (face 0,
    the strip's longest edge) only through a T-JUNCTION, never a shared edge -- the way these
    exports join most things (353 T-vertices on file A, 363 on B, at the merge input):

    * `join="vertex"`: the fat triangle under the base is split at the base's midpoint, so the
      two halves have a vertex INSIDE the strip's base and share no edge with it;
    * `join="edge"`: the whole lower half of the top is two triangles whose top edge runs from
      `(0, size/2)` to `(size, size/2)`, so the strip's base lies INSIDE that longer edge.

    Either way the strip is sandwiched: its other two edges are shared with the fat triangles
    above it, and removing it opens a slit `width` wide through the top. Face 0 is the strip."""
    s = size
    y = s / 2.0
    xa, xb, xm = (s - length) / 2.0, (s + length) / 2.0, s / 2.0
    a, b, c, t, m = (xa, y), (xb, y), (xm, y + width), (xm, s), (xm, y)
    upper = [(a, c, t), (c, b, t), ((0, y), a, t), ((0, y), t, (0, s)), (b, (s, y), t),
             ((s, y), (s, s), t)]
    if join == "vertex":
        lower = [((0, 0), (s, 0), (s, y)), ((0, 0), (s, y), b), ((0, 0), m, a), ((0, 0), b, m),
                 ((0, 0), a, (0, y))]
    elif join == "edge":
        lower = [((0, 0), (s, 0), (s, y)), ((0, 0), (s, y), (0, y))]
    else:
        raise ValueError(f"join must be 'vertex' or 'edge', got {join!r}")
    return _slab_from_top(f"slab_with_t_joined_strip_{join}", [(a, b, c)] + lower + upper, size,
                          height)


def slab_with_stub_on_t_junctions(size=2000.0, height=8.0, foot=2.0, rise=0.6):
    """Review 2a experiment E3b as a fixture: a closed `size` x `size` x `height` slab (top faces 0
    and 1, split along the diagonal from `(0, 0)` to `(size, size)`; sides and bottom 2-11) with
    an UPRIGHT quad standing on it (faces 12 and 13): `2 * foot * sqrt(2)` in long, `rise` in
    high -- 5.7 x 0.6 in, 3.4 sq in at the defaults. Its two foot vertices lie INSIDE the top's
    diagonal edge, so it shares no edge, no vertex and no plane with anything: a T-junction is
    the only thing joining it to the slab, and without that join it is a stray under 4 sq in.

    At 2000 in a guard pixel spans inches, so the per-view fragment cap never trips on a piece
    this small -- at 40 in the cap alone restored it, which hid a missing join."""
    s, h, c = float(size), float(height), float(size) / 2.0
    P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0], [0, 0, -h], [s, 0, -h], [s, s, -h], [0, s, -h],
         [c - foot, c - foot, 0], [c + foot, c + foot, 0], [c + foot, c + foot, rise],
         [c - foot, c - foot, rise]]
    P = [[float(v) for v in p] for p in P]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3),
                                 (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0), (4, 7, 6, 5),
                                 (8, 9, 10, 11)])
    return _mesh("slab_with_stub_on_t_junctions", P, uvs, fv, fvt, face_material=fm)


def plate_with_offset_corner(jitter=0.1, closed=False):
    """Review 2a experiment E4 as a fixture: a flat 40 x 40 in plate at `z = 0`, five triangles
    fanned from its centre, whose east edge has a vertex at `(40 + jitter, 20)` -- the plate's
    UNIQUE max-x vertex, `jitter` in off the straight edge. Printed like the real files (one
    decimal, 3 significant digits: a 0.1 in quantum, so the merge's collinear tolerance is
    0.15 in), so at the default 0.1 in the merge may drop that vertex, and moves the border by
    at most 0.1 in doing it. `closed=True` hangs an 8 in slab under the same outline (sides and
    a bottom), which keeps the vertex: the side below it is not flat with the top."""
    P = [[20, 20, 0], [0, 0, 0], [40, 0, 0], [40 + jitter, 20, 0], [40, 40, 0], [0, 40, 0]]
    fv = [[0, 1, 2], [0, 2, 3], [0, 3, 4], [0, 4, 5], [0, 5, 1]]
    if closed:
        base = len(P)
        P += [[p[0], p[1], -8.0] for p in P[1:]]
        ring = [1, 2, 3, 4, 5]
        for i in range(5):
            a, b = ring[i], ring[(i + 1) % 5]
            fv += [[a, base + a - 1, base + b - 1], [a, base + b - 1, b]]
        fv += [[base + 0, base + 4, base + 3], [base + 0, base + 3, base + 2],
               [base + 0, base + 2, base + 1]]
    P = np.asarray(P, dtype=np.float64)
    uvs = (P[np.asarray(fv).reshape(-1)][:, :2] * 0.05).tolist()
    fvt = np.arange(len(fv) * 3).reshape(-1, 3).tolist()
    return _mesh(f"plate_with_offset_corner_{'closed' if closed else 'open'}", P, uvs, fv, fvt,
                 coord_decimals=1, sig_digits=3)


def slab_with_lip_over_a_slot(size=2000.0, height=8.0, length=16.0, width=0.1, slot=0.05):
    """A rim-lip slot like file A's faces 3540 and 4659 (brief 09), as a fixture: a closed
    `size` x `size` x `height` slab whose top has a needle-shaped SLOT through it into the slab,
    and a LIP over the slot -- face 0, a needle `length` in long and `width` in wide lying in the
    top's own plane.

    With `c = size / 2` and `y1 - y0 = length`, the slot is the triangle A = (c, y0),
    B = (c, y1), D = (c + slot, y1): the top's left half ends along x = c, and its right part
    leaves out exactly that triangle. The lip is A, B, C = (c + width, y1). Its base A-B lies
    inside the left half's edge along x = c (a T-junction partner), the slot's corner D lies inside
    its short edge B-C, and its other long edge A-C is OPEN -- no other face uses it, no vertex
    lies inside it, it lies inside no edge -- so the detector names the lip a sliver: a ragged
    border. Yet it covers the slot, the only opening into the closed slab, so removing it shows
    the inside of the shell -- the back of the bottom, a side nobody could see on the reference --
    through every line that crosses the slot's half of the lip. The lip's right half lies on the
    top's right part (coplanar), so the lines through it meet an outside surface.

    At the defaults the slab is the real files' scale (a guard pixel spans inches), and
    `printed` gives it their tolerances (0.15 in), inside which the lip lies. Faces: 0 the lip,
    1-2 the left half, 3-7 the right part, then the four sides and the bottom
    (`_slab_from_top`)."""
    s, c = float(size), float(size) / 2.0
    y0 = c - length / 2.0
    y1 = y0 + length
    A, B, C, D = (c, y0), (c, y1), (c + width, y1), (c + slot, y1)
    top = [(A, B, C),
           ((0, 0), (c, 0), (c, s)), ((0, 0), (c, s), (0, s)),
           ((c, 0), (s, 0), A), (A, (s, 0), D), (D, (s, 0), (s, s)), (D, (s, s), (c, s)),
           (D, (c, s), B)]
    return _slab_from_top("slab_with_lip_over_a_slot", top, size, height)


def _slab_on_its_diagonal(name, extra_points, extra_faces, size, height, uv_per_unit=0.05):
    """`slab_with_stub_on_t_junctions`' closed slab (top faces 0 and 1 split along the diagonal
    from `(0, 0)` to `(size, size)`, sides and bottom 2-11), plus `extra_faces` (triangles over
    `extra_points`, numbered from 8) appended as faces 12 onwards."""
    s, h = float(size), float(height)
    P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0], [0, 0, -h], [s, 0, -h], [s, s, -h], [0, s, -h]]
    P = [[float(v) for v in p] for p in P] + [[float(v) for v in p] for p in extra_points]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3),
                                 (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0), (4, 7, 6, 5)])
    for face in extra_faces:
        base = len(uvs)
        uvs.extend((np.asarray([P[i] for i in face])[:, :2] * uv_per_unit).tolist())
        fv.append(list(face))
        fvt.append([base, base + 1, base + 2])
        fm.append(0)
    return _mesh(name, P, uvs, fv, fvt, face_material=fm)


def slab_with_standing_needle(size=2000.0, height=8.0, length=16.0, rise=0.05):
    """A free needle pointing into the sky (brief 09): the closed slab of
    `slab_with_stub_on_t_junctions` with face 12 a NEEDLE standing upright on the top's diagonal
    edge -- its two feet `length` in apart lie INSIDE that edge (a T-junction, which joins it to
    the slab and partners its base), its apex `rise` in straight above their midpoint. Its two
    upper edges are open, so the detector names it a sliver. It is debris: every line through
    it, once it is gone, meets the sky or the slab's top -- an outside surface."""
    c = float(size) / 2.0
    a = length / (2.0 * np.sqrt(2.0))
    return _slab_on_its_diagonal("slab_with_standing_needle",
                                 [[c - a, c - a, 0.0], [c + a, c + a, 0.0], [c, c, rise]],
                                 [(8, 9, 10)], size, height)


def slab_with_needle_lying_on_top(size=2000.0, height=8.0, length=16.0, width=0.05, lift=0.0):
    """A double layer lying on a coplanar face, like file A's faces 49 and 174 (brief 09): the
    closed slab of `slab_with_stub_on_t_junctions` with face 12 a NEEDLE lying ON top face 0 at
    `z = lift` -- 0 by default, exactly in its plane -- wound the same way (+z), 100 in from the
    diagonal and far from every edge: no shared edge, no vertex, no T-junction; only COPLANAR
    CONTACT joins it to the slab, and all three of its edges are open, so the detector names it a
    sliver. Every line through it, once it is gone, meets the top it lay on."""
    c = float(size) / 2.0
    x, y = c + 100.0, c - 100.0
    return _slab_on_its_diagonal(
        "slab_with_needle_lying_on_top",
        [[x - length / 2.0, y, lift], [x + length / 2.0, y, lift], [x, y + width, lift]],
        [(8, 9, 10)], size, height)


def slab_with_folded_pair(size=40.0, height=8.0, apex=(0.6, 0.4), flip=False, material=0):
    """A FOLD (brief 09 item 2), in a closed slab's top: faces 0 and 1 split the top along the
    diagonal from `(0, 0)` to `(size, size)`, and face 2 -- the diagonal again, with its apex at
    `apex * size`, on face 0's side of it -- is folded onto face 0: the two share that edge, lie
    in one plane, and both lie on the same side of it, so the area of face 2 is covered twice.
    With the apex inside face 0 (the default), face 2 lies wholly within face 0 and is the fold's
    redundant member. `flip=True` winds face 2 the other way (-z), as a surface folded back on
    itself is (file B's 5750/5751); by default it is wound like face 0 (+z), as file B's region-79
    pair is. `material` is face 2's (material `m1` when 1). Faces 3-12 are the four sides and
    the bottom (`_slab_from_top`)."""
    s = float(size)
    top = [((0, 0), (s, 0), (s, s)), ((0, 0), (s, s), (0, s)),
           ((0, 0), (s, s), (apex[0] * s, apex[1] * s))]
    m = _slab_from_top("slab_with_folded_pair", top, size, height, materials=("m0", "m1"),
                       top_material=[0, 0, material])
    if flip:
        m.face_v[2] = m.face_v[2][::-1]
        m.face_vt[2] = m.face_vt[2][::-1]
    return m


def slab_with_folded_lip_over_a_slot(size=2000.0, height=8.0, length=16.0, width=0.1,
                                     slot=0.05, cover=0.02, beyond=1.0):
    """File B's fold 5750/5751 in miniature (brief 09 item 2): `slab_with_lip_over_a_slot`'s
    top, with one more face -- face 8, the COVER -- folded onto the lip across its long edge A-C:
    the cover is A, C, E with E = (c + `cover`, y1 + `beyond`), in the top's plane and on the lip's
    side of A-C. The cover reaches `beyond` in past the lip, so it does not lie within the lip;
    the lip lies within the cover except for a sliver at most `cover` in wide along its base A-B
    -- inside the merge's own border tolerance (0.15 in, printed), so the lip is the fold's
    redundant member. But that sliver lies over the slot, so removing the lip opens it: the lip
    has to be refused, and the fold left. The lip is no sliver here -- its long edge A-C is shared
    with the cover -- so only the fold names it. Faces: 0 the lip, 1-7 as in
    `slab_with_lip_over_a_slot`, 8 the cover, then the four sides and the bottom."""
    s, c = float(size), float(size) / 2.0
    y0 = c - length / 2.0
    y1 = y0 + length
    A, B, C, D = (c, y0), (c, y1), (c + width, y1), (c + slot, y1)
    E = (c + cover, y1 + beyond)
    top = [(A, B, C),
           ((0, 0), (c, 0), (c, s)), ((0, 0), (c, s), (0, s)),
           ((c, 0), (s, 0), A), (A, (s, 0), D), (D, (s, 0), (s, s)), (D, (s, s), (c, s)),
           (D, (c, s), B),
           (A, C, E)]
    return _slab_from_top("slab_with_folded_lip_over_a_slot", top, size, height)


def plate_with_crossing_fold():
    """File B's merge region 79 in miniature (brief 09 item 2), as a bare plate at `z = 0`: two
    faces on one edge, from (0, 0) to (0, 10), with both apexes on the same side of it -- face 0's
    at (10, 8), face 1's at (10, 2) -- so each reaches far past the other. The area near the edge
    is covered twice and the rest once, by one face or the other, and by nothing else."""
    P = [[0.0, 0.0, 0.0], [0.0, 10.0, 0.0], [10.0, 8.0, 0.0], [10.0, 2.0, 0.0]]
    fv = [[0, 1, 2], [0, 1, 3]]
    uvs = (np.asarray(P)[np.asarray(fv).reshape(-1)][:, :2] * 0.05).tolist()
    return _mesh("plate_with_crossing_fold", P, uvs, fv, np.arange(6).reshape(-1, 3).tolist())


def slab_with_fold_lying_on_top(size=40.0, height=8.0):
    """A fold both of whose members the rest of the model covers (brief 09 item 2): the closed
    slab of `slab_with_stub_on_t_junctions`, and faces 12 and 13 lying in top face 0's plane,
    inside it, sharing the edge (22, 5)-(34, 5) with both apexes on the same side -- face 12's at
    (28, 8), 18 sq in, and face 13's at (30, 14), 54 sq in. Whichever goes, the other and the top
    under both still cover it."""
    return _slab_on_its_diagonal("slab_with_fold_lying_on_top",
                                 [[22.0, 5.0, 0.0], [34.0, 5.0, 0.0], [28.0, 8.0, 0.0],
                                  [30.0, 14.0, 0.0]],
                                 [(8, 9, 10), (8, 9, 11)], size, height)


# ------------------------------------------------------------------------------------------------
# SR2: broken sides. Each of these is a slab whose side exists but is not a clean wall.
# ------------------------------------------------------------------------------------------------


def _slab_rows(size, height, ys):
    """A slab `size` x `size` from `z = -height` to `0`, its top, bottom and `x = size` skirt cut
    into rows at `ys` (the `y` of every row border, 0 and `size` included), and single-quad skirts
    at `y = 0` and `y = size`. Everything is wound OUTWARD. The `x = 0` side is left to the caller.
    Returns `(P, uvs, fv, fvt, fm, top_border)` where `top_border[k]` is the vertex at
    `(0, ys[k], 0)`."""
    s, h = size, height
    P, uvs, fv, fvt, fm = [], [], [], [], []
    left_top = [len(P) + k for k in range(len(ys))]
    P += [[0.0, y, 0.0] for y in ys]
    right_top = [len(P) + k for k in range(len(ys))]
    P += [[s, y, 0.0] for y in ys]
    left_bot = [len(P) + k for k in range(len(ys))]
    P += [[0.0, y, -h] for y in ys]
    right_bot = [len(P) + k for k in range(len(ys))]
    P += [[s, y, -h] for y in ys]
    loops = []
    for k in range(len(ys) - 1):
        loops.append((left_top[k], right_top[k], right_top[k + 1], left_top[k + 1]))   # top, +z
        loops.append((left_bot[k], left_bot[k + 1], right_bot[k + 1], right_bot[k]))   # bottom, -z
        loops.append((right_top[k], right_bot[k], right_bot[k + 1], right_top[k + 1]))  # x = s, +x
    loops.append((left_top[0], left_bot[0], right_bot[0], right_top[0]))                # y = 0, -y
    loops.append((right_top[-1], right_bot[-1], left_bot[-1], left_top[-1]))            # y = s, +y
    _quads(P, uvs, fv, fvt, fm, loops)
    return P, uvs, fv, fvt, fm, left_top


def slab_with_sawtooth_side(size=40.0, height=8.0, teeth=5, offsets=(0.0, 0.6, -0.4, 0.9, 0.0),
                            gap=2, rib_x=4.0):
    """The owner's broken side in miniature (measured on file B: the ramp's side between the
    upper landing and the lower slab is a row of triangular teeth with gaps). A closed slab --
    top at `z = 0`, bottom at `-height`, skirts at `x = size`, `y = 0` and `y = size`, all wound
    outward -- whose `x = 0` side is a JAGGED SAWTOOTH instead of a wall: `teeth` downward
    triangles, base on the top edge and apex at the bottom, each lying `offsets[k]` in off the
    `x = 0` plane (all within 1 in), every other one wound INWARD so a camera outside meets its
    back side, and tooth `gap` missing altogether. Between them are the up-pointing gaps a person
    sees into the slab through.

    Inside, an interior RIB at `x = rib_x` (4 in in, outside a 2.5 in side band) faces the side,
    `y` 4 to `size - 4`, `z` -1 to `-height + 1`: seen through the gaps, and from nowhere else.

    The top's `x = 0` border is cut at every tooth's base, as the export ties a side to its top,
    so a tooth lying IN the plane shares its top edge with the top (edge count 2) and the others
    leave that edge open. Faces: the slab first (`_slab_rows`), then the teeth in `k` order
    (skipping `gap`), then the rib's two triangles (the last two faces)."""
    s, h = size, height
    w = s / teeth
    ys = [k * w for k in range(teeth + 1)]
    P, uvs, fv, fvt, fm, border = _slab_rows(s, h, ys)
    for k in range(teeth):
        if k == gap:
            continue
        d = offsets[k]
        if d == 0.0:
            a, b = border[k], border[k + 1]
        else:
            a, b = len(P), len(P) + 1
            P += [[d, ys[k], 0.0], [d, ys[k + 1], 0.0]]
        apex = len(P)
        P.append([d, (ys[k] + ys[k + 1]) / 2.0, -h])
        # (b, apex, a) has normal -x (outward); every other tooth is reversed
        tri = [b, apex, a] if k % 2 == 0 else [a, apex, b]
        base = len(uvs)
        uvs += [[P[v][1] * 0.05, P[v][2] * 0.05] for v in tri]
        fv.append(tri)
        fvt.append([base, base + 1, base + 2])
        fm.append(0)
    r = len(P)
    P += [[rib_x, 4.0, -1.0], [rib_x, 4.0, -h + 1.0], [rib_x, s - 4.0, -h + 1.0],
          [rib_x, s - 4.0, -1.0]]
    _quads(P, uvs, fv, fvt, fm, [(r, r + 3, r + 2, r + 1)])        # normal -x: faces the side
    return _mesh("slab_with_sawtooth_side", P, uvs, fv, fvt, face_material=fm)


def slab_with_railing_outside(size=40.0, height=8.0, near=2.0, far=6.0, thick=0.4,
                              with_bottom=True):
    """`slab_with_three_skirts` -- its `x = 0` side missing -- with two things standing OUTSIDE
    that edge, neither of which is part of the slab. Each is a thin sheet with BOTH faces, the way
    a railing or a wall is modelled: one face towards the slab, one away from it, `thick` apart.

    a RAILING whose inner face is `near` in outside the edge (both faces inside a 2.5 in side
    band), parallel to the side, from the slab's underside level `-height` up to `+30`, `y` 5 to
    35 -- it stands above the top, so it is not a piece of the side however close it is;
    a WALL `far` in outside (beyond the band), `y` 10 to 30, `z` -20 to +10.

    Faces: the slab (8, or 10 with the bottom), then the railing's inner and outer faces (two
    triangles each), then the wall's (four)."""
    m = slab_with_three_skirts(size, height, with_bottom=with_bottom)
    P = m.positions.tolist()
    uvs, fv, fvt = m.uvs.tolist(), m.face_v.tolist(), m.face_vt.tolist()
    fm = m.face_material.tolist()
    loops = []
    for x, (y0, y1, z0, z1) in ((near, (5.0, 35.0, -height, 30.0)), (far, (10.0, 30.0, -20.0, 10.0))):
        for d, towards_slab in ((-x, True), (-x - thick, False)):
            r = len(P)
            P += [[d, y0, z0], [d, y0, z1], [d, y1, z1], [d, y1, z0]]
            # (r, r+1, r+2, r+3) has normal -x (away from the slab)
            loops.append((r, r + 3, r + 2, r + 1) if towards_slab else (r, r + 1, r + 2, r + 3))
    _quads(P, uvs, fv, fvt, fm, loops)
    return _mesh("slab_with_railing_outside", P, uvs, fv, fvt, face_material=fm)


def slab_with_half_side(size=40.0, height=8.0, post_x=-10.0):
    """A closed slab whose `x = 0` side covers only HALF its edge -- `y` 0 to `size / 2`, wound
    outward -- and is missing over the other half. The top's `x = 0` border is cut at
    `size / 2`, where the half side ends.

    Outside, beyond the missing half, a POST stands at `x = post_x`: `y` 24 to 30, `z` -20 to
    +20, wound facing away from the slab -- something visible outside the slab that closing the
    side must not change. Faces: the slab (`_slab_rows` with rows at 0, size/2, size), the half
    side's two, then the post's two."""
    s, h = size, height
    P, uvs, fv, fvt, fm, border = _slab_rows(s, h, [0.0, s / 2.0, s])
    lo = len(P)
    P += [[0.0, 0.0, -h], [0.0, s / 2.0, -h]]
    _quads(P, uvs, fv, fvt, fm, [(border[0], border[1], lo + 1, lo)])            # x = 0, -x
    p = len(P)
    P += [[post_x, 24.0, -20.0], [post_x, 24.0, 20.0], [post_x, 30.0, 20.0],
          [post_x, 30.0, -20.0]]
    _quads(P, uvs, fv, fvt, fm, [(p, p + 1, p + 2, p + 3)])                       # normal -x
    return _mesh("slab_with_half_side", P, uvs, fv, fvt, face_material=fm)


def slab_with_side_behind_a_t_junction(size=40.0, height=8.0):
    """The case the merge-fix round found on file B (region 38): a slab whose side EXISTS but
    whose top edge is not shared with the top, because the side's own top edge is cut at a
    T-vertex the top does not have. The top edge therefore counts as OPEN (used by one face),
    and the old solidify laid a skirt over the existing side -- a second, coplanar layer.

    `slab_with_three_skirts(with_bottom=True)` plus the `x = 0` side as three triangles tiling
    its rectangle, wound outward, with a T-vertex at `(0, size / 2, 0)` on the top edge. The side
    is whole: nothing is missing and nothing should be added. Faces: the slab's 10, then the
    side's 3."""
    m = slab_with_three_skirts(size, height, with_bottom=True)
    P = m.positions.tolist()
    uvs, fv, fvt = m.uvs.tolist(), m.face_v.tolist(), m.face_vt.tolist()
    fm = m.face_material.tolist()
    t = len(P)
    P.append([0.0, size / 2.0, 0.0])
    a, c, d, e = 0, 3, 7, 4          # (0,0,0), (0,s,0), (0,s,-h), (0,0,-h)
    for tri in ([a, t, e], [t, d, e], [t, c, d]):          # normal -x
        base = len(uvs)
        uvs += [[P[v][1] * 0.05, P[v][2] * 0.05] for v in tri]
        fv.append(tri)
        fvt.append([base, base + 1, base + 2])
        fm.append(0)
    return _mesh("slab_with_side_behind_a_t_junction", P, uvs, fv, fvt, face_material=fm)


def two_slabs_meeting_at_a_t_junction(size=40.0, height=8.0):
    """One closed slab, `2 * size` long, whose top is TWO regions of different materials meeting
    at `x = size` -- and they meet at a T-junction: the left top's border there is one edge, the
    right top's is cut at `y = size / 2`. Neither top shares that border edge with the other, so
    both count it as OPEN; it is not a side of anything, the slab simply continues across it.
    Skirts on every outer edge and a bottom, all wound outward. Faces: the left top's two
    (material 0), the right top's four (material 1), then the skirts and the bottom."""
    s, h = size, height
    P = [[0.0, 0.0, 0.0], [s, 0.0, 0.0], [s, s, 0.0], [0.0, s, 0.0],             # 0-3 left top
         [s, s / 2.0, 0.0], [2 * s, 0.0, 0.0], [2 * s, s / 2.0, 0.0], [2 * s, s, 0.0],  # 4-7
         [0.0, 0.0, -h], [2 * s, 0.0, -h], [2 * s, s, -h], [0.0, s, -h]]          # 8-11 bottom
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3)], material=0)                      # left top, +z
    _quads(P, uvs, fv, fvt, fm, [(1, 5, 6, 4), (4, 6, 7, 2)], material=1)        # right top, +z
    # skirts and bottom, outward; the y = 0 and y = s skirts span both tops
    _quads(P, uvs, fv, fvt, fm, [(0, 8, 9, 5), (5, 9, 10, 7), (7, 10, 11, 3), (3, 11, 8, 0),
                                  (8, 11, 10, 9)], material=0)
    return _mesh("two_slabs_meeting_at_a_t_junction", P, uvs, fv, fvt, materials=("m0", "m1"),
                 face_material=fm)


def slab_continuing_under_a_landing(length=80.0, width=40.0, depth=10.0, landing_z=(10.0, 20.0)):
    """File A's region 11 in miniature: a lower slab whose top CONTINUES under an upper landing.

    The lower slab runs `x` 0..`length`, `y` 0..`width`, top at `z = 0`, sides down to `-depth`
    wound outward, and NO BOTTOM. Its top is two regions: A (`x` 0..length/2, material m0) sees
    sky; B (`x` length/2..length, material m1) lies under a closed upper landing (`z` 10..20,
    wound outward) and sees none, so it is not a top surface by the sky test -- yet it is the
    same slab's top, and what lies under it is inside that slab. A RIB stands under B at
    `x = 3/4 length`, facing -x, `z` -1 to `-depth + 1`: seen from below through the missing
    bottom, and nowhere else.

    Faces, in order: A's top (2), B's top (2), the lower slab's four sides (8), the landing's six
    quads (12), the rib (2, the last two)."""
    L, W, D = length, width, depth
    z0, z1 = landing_z
    h = L / 2.0
    P, uvs, fv, fvt, fm = [], [], [], [], []

    def v(x, y, z):
        P.append([float(x), float(y), float(z)])
        return len(P) - 1

    a = [v(0, 0, 0), v(h, 0, 0), v(h, W, 0), v(0, W, 0)]
    _quads(P, uvs, fv, fvt, fm, [tuple(a)], material=0)                         # A, +z
    b = [a[1], v(L, 0, 0), v(L, W, 0), a[2]]
    _quads(P, uvs, fv, fvt, fm, [tuple(b)], material=1)                         # B, +z
    low = [v(0, 0, -D), v(L, 0, -D), v(L, W, -D), v(0, W, -D)]
    _quads(P, uvs, fv, fvt, fm, [
        (low[3], low[0], a[0], a[3]),                                            # x = 0, -x
        (low[0], low[1], b[1], a[0]),                                            # y = 0, -y
        (low[2], low[3], a[3], b[2]),                                            # y = W, +y
        (low[1], low[2], b[2], b[1])], material=0)                               # x = L, +x
    t = [v(h, 0, z1), v(L, 0, z1), v(L, W, z1), v(h, W, z1)]
    u = [v(h, 0, z0), v(L, 0, z0), v(L, W, z0), v(h, W, z0)]
    _quads(P, uvs, fv, fvt, fm, [
        (t[0], t[1], t[2], t[3]),                                                # top, +z
        (u[0], u[3], u[2], u[1]),                                                # bottom, -z
        (u[0], u[1], t[1], t[0]),                                                # y = 0, -y
        (u[2], u[3], t[3], t[2]),                                                # y = W, +y
        (u[3], u[0], t[0], t[3]),                                                # x = h, -x
        (u[1], u[2], t[2], t[1])], material=0)                                   # x = L, +x
    x = 0.75 * L
    r = [v(x, 5, -1), v(x, W - 5, -1), v(x, W - 5, -D + 1), v(x, 5, -D + 1)]
    _quads(P, uvs, fv, fvt, fm, [tuple(r)], material=0)                         # rib, -x
    return _mesh("slab_continuing_under_a_landing", P, uvs, fv, fvt, materials=("m0", "m1"),
                 face_material=fm)


def slab_with_a_lip(size=40.0, deep=12.0, lip=2.0, lip_length=8.0, with_lip=True, riser=0.0,
                    riser_length=10.0):
    """SR6 item 2: a slab whose own sides are `deep` on three edges, and whose x = 0 edge is open
    except for a `lip` band hanging `lip` in from the top along `0 <= y <= lip_length` -- a trim,
    not the slab's depth (file B's ramp has one 5.62 in deep over 13.1 of its 804 in of own
    sides). With `riser > 0`, a face also stands UP `riser` in from the y = size edge along
    `0 <= x <= riser_length`: the step to the next landing, which is not a side of this slab at
    all (every one of file A's lower landing's shallow "sides" is such a riser). No bottom.

    Faces: 0-1 the top, 2-3 y = 0, 4-5 x = size, 6-7 y = size (all `deep`, outward), then 8-9
    the lip if any, then the riser if any."""
    s, D = size, deep
    P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0],
         [0, 0, -D], [s, 0, -D], [s, s, -D], [0, s, -D]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3),                    # top, +z
                                 (4, 5, 1, 0),                    # y = 0, -y
                                 (5, 6, 2, 1),                    # x = s, +x
                                 (6, 7, 3, 2)])                   # y = s, +y
    if with_lip:
        base = len(P)
        P += [[0, lip_length, 0], [0, lip_length, -lip], [0, 0, -lip]]
        _quads(P, uvs, fv, fvt, fm, [(base + 2, 0, base, base + 1)])       # the lip, -x
    if riser > 0.0:
        base = len(P)
        P += [[riser_length, s, 0], [riser_length, s, riser], [0, s, riser]]
        _quads(P, uvs, fv, fvt, fm, [(3, base, base + 1, base + 2)])       # the riser, -y
    return _mesh("slab_with_a_lip", P, uvs, fv, fvt, face_material=fm)


def sloped_slab(length=80.0, width=40.0, rise=20.0, thickness=12.0, flat_underside=False,
                side="missing", strip=(8.0, 12.0), inner_plate=None):
    """SR6 item 1: file B's ramp in miniature. The top slopes up along x, `z = rise * x / length`
    over `0 <= x <= length, 0 <= y <= width`. The underside is PARALLEL to it, `thickness` below
    (the ramp's is 39.37 in below its top everywhere), or with `flat_underside` a horizontal plate
    at `z = -thickness` -- a wedge on flat ground. The x = 0, x = length and y = width sides are
    complete, from the top down to the underside. The y = 0 side, under the sloped edge, is
    `side`: "missing" (open), or "low" -- only a strip from `strip[0]` to `strip[1]` in below the
    edge over its upper half: pieces that do not reach the top (the ramp's lie 28 to 39.4 in down
    on its 85 in edge).

    `inner_plate=(x0, x1, h)` adds a plate INSIDE the slab, parallel to its underside and `h` in
    above it over `x0 <= x <= x1` -- the kind of block face file B's ramp has inside it, a few
    tenths of an inch to a few inches above its underside, which the rays looking for the lower
    surface meet first.

    Faces: 0-1 the top, 2-3 the underside, 4-5 x = 0, 6-7 x = length, 8-9 y = width (all
    outward), then 10-11 the strip, then the inner plate."""
    L, W, R, T = length, width, rise, thickness
    under_rise = 0.0 if flat_underside else R
    P = [[0, 0, 0], [L, 0, R], [L, W, R], [0, W, 0],                       # 0-3 the top
         [0, 0, -T], [L, 0, under_rise - T], [L, W, under_rise - T], [0, W, -T]]   # 4-7 under
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3),                    # top, +z
                                 (4, 7, 6, 5),                    # underside, -z
                                 (7, 4, 0, 3),                    # x = 0, -x
                                 (5, 6, 2, 1),                    # x = L, +x
                                 (6, 7, 3, 2)])                   # y = W, +y
    if side == "low":
        d0, d1 = strip
        base = len(P)
        P += [[L / 2, 0, R / 2 - d1], [L, 0, R - d1], [L, 0, R - d0], [L / 2, 0, R / 2 - d0]]
        _quads(P, uvs, fv, fvt, fm, [(base, base + 1, base + 2, base + 3)])   # the strip, -y
    if inner_plate is not None:
        x0, x1, h = inner_plate

        def z_under(x):
            return (under_rise * x / L) - T + h

        base = len(P)
        P += [[x0, 0, z_under(x0)], [x1, 0, z_under(x1)], [x1, W, z_under(x1)], [x0, W, z_under(x0)]]
        _quads(P, uvs, fv, fvt, fm, [(base, base + 1, base + 2, base + 3)])   # inner plate
    return _mesh("sloped_slab", P, uvs, fv, fvt, face_material=fm)


def slab_beside_a_lower_top(size=40.0, box_height=10.0, plate_depth=8.0):
    """SR6 item 3: a closed box (top at `z = box_height`, underside at `z = 0` facing down, four
    sides) standing beside a lower top: a plate at `z = 0` over `size <= x <= 2 * size`, facing
    up, skirted `plate_depth` down on its three free edges and with no bottom. The plate's
    `x = size` edge lies in the box's underside plane, so solidify's continuation probe finds the
    underside there -- the way 64 undersides of file A and 5 of file B were taken for tops a top
    continues into, and each got a bottom invented below it.

    Faces: 0-1 the box top, 2-3 its underside, 4-11 its four sides, 12-13 the plate, 14-19 the
    plate's three skirts."""
    s, H, D = size, box_height, plate_depth
    P = [[0, 0, H], [s, 0, H], [s, s, H], [0, s, H],          # 0-3 the box top
         [0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0],          # 4-7 its underside
         [2 * s, 0, 0], [2 * s, s, 0],                        # 8-9 the plate's far corners
         [s, 0, -D], [2 * s, 0, -D], [2 * s, s, -D], [s, s, -D]]   # 10-13 the plate's skirt feet
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3),                    # box top, +z
                                 (4, 7, 6, 5),                    # underside, -z
                                 (4, 5, 1, 0),                    # y = 0, -y
                                 (5, 6, 2, 1),                    # x = s, +x
                                 (6, 7, 3, 2),                    # y = s, +y
                                 (7, 4, 0, 3),                    # x = 0, -x
                                 (5, 8, 9, 6),                    # the plate, +z
                                 (10, 11, 8, 5),                  # plate y = 0, -y
                                 (11, 12, 9, 8),                  # plate x = 2s, +x
                                 (12, 13, 6, 9)])                 # plate y = s, +y
    return _mesh("slab_beside_a_lower_top", P, uvs, fv, fvt, face_material=fm)



def slab_with_a_bottom_strip(length=60.0, width=20.0, depth=8.0, strip=20.0):
    """SR6: a slab `length x width`, its top in three quads (so its outline, and the bottom
    triangulated from it, has corners along its long edges), its four sides `depth` deep, and no
    bottom but a STRIP of it under `0 <= x <= strip`: pieces the new bottom replaces.

    Faces: 0-5 the top, 6-13 the sides, 14-15 the strip."""
    L, W, D = length, width, depth
    third = L / 3.0
    P = [[0, 0, 0], [third, 0, 0], [2 * third, 0, 0], [L, 0, 0],
         [L, W, 0], [2 * third, W, 0], [third, W, 0], [0, W, 0],         # 0-7 the top
         [0, 0, -D], [L, 0, -D], [L, W, -D], [0, W, -D],                 # 8-11 side feet
         [strip, 0, -D], [strip, W, -D]]                                 # 12-13 the strip
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 6, 7), (1, 2, 5, 6), (2, 3, 4, 5),   # top, +z
                                 (8, 9, 3, 0),                           # y = 0, -y
                                 (9, 10, 4, 3),                          # x = L, +x
                                 (10, 11, 7, 4),                         # y = W, +y
                                 (11, 8, 0, 7),                          # x = 0, -x
                                 (8, 11, 13, 12)])                       # the strip, -z
    return _mesh("slab_with_a_bottom_strip", P, uvs, fv, fvt, face_material=fm)


# ------------------------------------------------------------------------------------------------
# Brief 10: side rebuild follow-ups.
# ------------------------------------------------------------------------------------------------


def slab_with_fins_beside_a_post(post_y=30.0, post_x=(35.0, 55.0), post_z=(-9.0, -2.0)):
    """Brief 10 item 1: `slab_with_two_depths` -- whose two open edges touching its deep end get
    walls 9.8 in deep under a bottom solidify puts at 1.3 in, so both hang 8.5 in below the slab as
    FINS facing each other across it -- with a POST beyond the far one: a plate at `y = post_y`,
    facing -y (towards the slab), over `post_x` and `post_z`, below the slab's bottom and above the
    fins' feet. A ray from -y at the post's height enters the near fin from outside, runs UNDER the
    slab's bottom -- outside the slab -- and leaves through the far fin before it reaches the post.

    Faces: `slab_with_two_depths`' 8, then the post's two."""
    m = slab_with_two_depths()
    P = m.positions.tolist()
    uvs, fv, fvt = m.uvs.tolist(), m.face_v.tolist(), m.face_vt.tolist()
    fm = m.face_material.tolist()
    (x0, x1), (z0, z1) = post_x, post_z
    b = len(P)
    P += [[x0, post_y, z0], [x1, post_y, z0], [x1, post_y, z1], [x0, post_y, z1]]
    _quads(P, uvs, fv, fvt, fm, [(b, b + 1, b + 2, b + 3)])            # the post, -y
    return _mesh("slab_with_fins_beside_a_post", P, uvs, fv, fvt, face_material=fm)


def _closed_box(P, uvs, fv, fvt, fm, x0, x1, y0, y1, z0, z1, material=0):
    """Append a closed box wound outward: its bottom (2 faces), top, then the y0, x1, y1 and x0
    sides, in that order."""
    b = len(P)
    P += [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
          [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]
    _quads(P, uvs, fv, fvt, fm, [(b + 0, b + 3, b + 2, b + 1),     # bottom, -z
                                 (b + 4, b + 5, b + 6, b + 7),     # top, +z
                                 (b + 0, b + 1, b + 5, b + 4),     # y0, -y
                                 (b + 1, b + 2, b + 6, b + 5),     # x1, +x
                                 (b + 2, b + 3, b + 7, b + 6),     # y1, +y
                                 (b + 3, b + 0, b + 4, b + 7)],    # x0, -x
           material=material)


def overhang_beside_a_slab():
    """Review part 2, C2 (`probe_underside_with_hanging_neighbour.py`): L, a closed slab (x 0..40,
    y 0..40, z -8..0), and B, a closed block overhanging open air beside it (x 40..80, z 0..20).
    B's underside is flush with L's top, so L's x = 40 edge CONTINUES into it -- and L's own 8 in
    x = 40 side hangs along the underside's x = 40 edge: a neighbour's side, not a body under it.

    Faces: 0-11 L (bottom 0-1, top 2-3, sides), 12-23 B (its underside 12-13, top 14-15, sides)."""
    P, uvs, fv, fvt, fm = [], [], [], [], []
    _closed_box(P, uvs, fv, fvt, fm, 0, 40, 0, 40, -8, 0)
    _closed_box(P, uvs, fv, fvt, fm, 40, 80, 0, 40, 0, 20)
    return _mesh("overhang_beside_a_slab", P, uvs, fv, fvt, face_material=fm)


def real_top_under_a_landing():
    """Review part 2, M2 (`probe_real_top_taken_for_underside.py`): one slab whose top is two
    regions at z = 0 -- L (x 0..40, m0) sees sky, R (x 40..80, m1) lies under an upper landing U
    (a closed box, x 40..80, z 10..20) and sees none. L has 10 in skirts on x = 0, y = 0 and
    y = 40; under R the export left the sides OPEN (y = 0 and y = 40 over x 40..80), there is no
    bottom anywhere, and R's only own side is a RISER at x = 80 standing up to the landing.

    Faces: 0-1 L's top, 2-3 R's top, 4-9 L's skirts, 10-11 the riser, 12-23 the landing."""
    P, uvs, fv, fvt, fm = [], [], [], [], []

    def v(x, y, z):
        P.append([float(x), float(y), float(z)])
        return len(P) - 1

    a = [v(0, 0, 0), v(40, 0, 0), v(40, 40, 0), v(0, 40, 0)]
    _quads(P, uvs, fv, fvt, fm, [tuple(a)], material=0)                       # L's top, +z
    b = [a[1], v(80, 0, 0), v(80, 40, 0), a[2]]
    _quads(P, uvs, fv, fvt, fm, [tuple(b)], material=1)                       # R's top, +z
    lo = [v(0, 0, -10), v(40, 0, -10), v(40, 40, -10), v(0, 40, -10)]
    _quads(P, uvs, fv, fvt, fm, [(lo[3], lo[0], a[0], a[3]),                  # L x = 0, -x
                                 (lo[0], lo[1], a[1], a[0]),                  # L y = 0, -y
                                 (lo[2], lo[3], a[3], a[2])], material=0)     # L y = 40, +y
    r_top = [v(80, 0, 10), v(80, 40, 10)]
    _quads(P, uvs, fv, fvt, fm, [(b[1], b[2], r_top[1], r_top[0])], material=0)   # riser, +x
    t = [v(40, 0, 20), v(80, 0, 20), v(80, 40, 20), v(40, 40, 20)]
    u = [v(40, 0, 10), v(80, 0, 10), v(80, 40, 10), v(40, 40, 10)]
    _quads(P, uvs, fv, fvt, fm, [(t[0], t[1], t[2], t[3]), (u[0], u[3], u[2], u[1]),
                                 (u[0], u[1], t[1], t[0]), (u[2], u[3], t[3], t[2]),
                                 (u[3], u[0], t[0], t[3]), (u[1], u[2], t[2], t[1])],
           material=0)                                                        # the landing U
    return _mesh("real_top_under_a_landing", P, uvs, fv, fvt, materials=("m0", "m1"),
                 face_material=fm)


def slab_with_a_deep_tooth_in_its_side(teeth_material=1):
    """Review part 2, C1 (`probe_restored_piece_double_layer.py`, `..._same_material.py`):
    `slab_with_sawtooth_side` with every tooth IN the side plane (offsets 0) and in material
    `teeth_material` (m1, concrete, under an m0 top; 0 = the top's own), and tooth 0 reaching 3 in
    BELOW the slab (apex at z = -11 against the slab's -8): its tip is not covered by the 8 in wall,
    so its pixels fail, and the cap guard gives it back while keeping the wall face lying on it.

    Faces: `slab_with_sawtooth_side`'s (the slab 0-33, the teeth 34-37, the rib 38-39)."""
    from dataclasses import replace
    m = slab_with_sawtooth_side(offsets=(0.0, 0.0, 0.0, 0.0, 0.0))
    teeth = np.arange(34, m.n_faces - 2)
    P = m.positions.copy()
    apex = int(m.face_v[teeth[0]][1])                   # tooth 0 is (b, apex, a)
    P[apex, 2] = -11.0
    fm = m.face_material.copy()
    fm[teeth] = teeth_material
    return replace(m, name="slab_with_a_deep_tooth_in_its_side", positions=P, face_material=fm,
                   materials=["m0_paving", "m1_concrete"])


def slab_with_one_deep_tooth(size=40.0, height=8.0):
    """Review part 2, C1 at the real files' scale (`probe_piece_below_wall.py`): a closed slab
    `size` x `size` x `height` (bottom and three skirts, outward) whose x = 0 side is missing
    except ONE tooth in the side plane -- base on the top edge over y = size/2 .. size/2 + 8, apex
    11 in down, 3 in below the slab. At 2000 in a guard pixel spans 2 to 3 in.

    Faces: 0-9 the slab, 10 the tooth."""
    s, h = size, height
    P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0], [0, 0, -h], [s, 0, -h], [s, s, -h], [0, s, -h]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3), (4, 7, 6, 5), (4, 5, 1, 0), (5, 6, 2, 1), (6, 7, 3, 2)])
    y0 = s / 2.0
    b = len(P)
    P += [[0, y0, 0], [0, y0 + 8.0, 0], [0, y0 + 4.0, -11.0]]
    fv.append([b + 1, b + 2, b + 0])                    # normal -x, outward
    base = len(uvs)
    uvs += [[P[v][1] * 0.05, P[v][2] * 0.05] for v in (b + 1, b + 2, b + 0)]
    fvt.append([base, base + 1, base + 2])
    fm.append(0)
    return _mesh("slab_with_one_deep_tooth", P, uvs, fv, fvt, face_material=fm)


def slab_with_a_double_layer_top(size=40.0, height=8.0):
    """Review part 2, C1 failure 3 (`probe_double_bottom.py`): a slab `size` x `size`, its four
    sides `height` deep and closed, NO bottom, whose top is two coincident sheets -- one in m0 and
    one in m1, each on its own vertex rows, as a separate export layer would be (the duplicate
    layer the overlap pass leaves because the materials differ).

    Faces: 0-1 the m0 top, 2-3 the m1 top, 4-11 the sides."""
    s, h = size, height
    P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0], [0, 0, -h], [s, 0, -h], [s, s, -h], [0, s, -h],
         [0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0]]
    uvs, fv, fvt, fm = [], [], [], []
    _quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3)], material=0)                   # top, m0
    _quads(P, uvs, fv, fvt, fm, [(8, 9, 10, 11)], material=1)                 # the same top, m1
    _quads(P, uvs, fv, fvt, fm, [(4, 5, 1, 0), (5, 6, 2, 1), (6, 7, 3, 2), (7, 4, 0, 3)],
           material=0)
    return _mesh("slab_with_a_double_layer_top", P, uvs, fv, fvt, materials=("m0", "m1"),
                 face_material=fm)
