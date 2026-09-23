import numpy as np

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
