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
                                    y=24000.0, uv_per_unit=0.05):
    """Two coplanar slabs of DIFFERENT materials (so they stay two regions) meeting along a
    gently CURVED border of `n` vertices -- the shared-border counterpart of `arc_topped_strip`.

    The border runs along y and bulges in x by a parabola scaled exactly like `arc_topped_strip`'s
    arc: the farthest border vertex is `sag` (0.8 in) from the chord between the two END border
    vertices, while each one is only `sag * (2 / (n - 1))**2` (0.027 in) from the chord of its own
    two neighbours. At y = 24,000 in `axis_quanta` gives Y a 0.1 in quantum, so the merge's ring
    bound is `1.5 * 0.1 = 0.15` in: every border vertex passes a per-vertex collinearity test and
    the whole polyline does not, which is exactly the case where the two regions must agree on
    WHICH border vertices survive or a T-junction opens between them.

    Faces 0..2*(n-1)-1 are the left slab (material 0, x from `-half_width` to the border), the
    rest the right slab (material 1, border to `+half_width`). Both slabs are wound CCW seen from
    +z, so they share the same region normal."""
    u = np.linspace(-half_span, half_span, n)
    c = sag / (half_span ** 2 - float(u[np.argmin(np.abs(u))]) ** 2)
    xb = -c * u ** 2                       # the border's bulge, 0 at the ends, -sag at the middle
    ys = y + u

    P = ([[-half_width, float(t), 0.0] for t in ys]          # 0..n-1   left edge
         + [[float(b), float(t), 0.0] for b, t in zip(xb, ys)]   # n..2n-1  the curved border
         + [[half_width, float(t), 0.0] for t in ys])        # 2n..3n-1 right edge
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
    `height`. At the default `max_thickness` (36 in) that is clamped away; raise the ceiling and
    the skirt reaches `z = -deep`.

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
