import numpy as np

from engine.topo.adjacency import edge_face_lists, t_junction_sub_edges


def face_normals(positions_w, face_w, ok):
    """Unit normal per face, all-zero where `ok` is False (a zero-area face has no normal)."""
    tri = positions_w[face_w]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(cross, axis=1)
    out = np.zeros_like(cross)
    out[ok] = cross[ok] / length[ok, None]
    return out


def plane_basis(n):
    a = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(n, a)
    e1 /= np.linalg.norm(e1)
    return e1, np.cross(n, e1)


def fit_plane(points, orient_like):
    """Total-least-squares plane through `points` (`(..., 3)`, flattened): `(normal, centroid)`.

    The normal is the right singular vector of the CENTRED points with the smallest singular
    value -- the direction of least spread, i.e. the plane's own normal. SVD fixes that vector
    only up to sign, so it is flipped to agree with `orient_like` (the seed triangle's normal),
    which makes the result independent of LAPACK's sign convention."""
    p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    centroid = p.mean(axis=0)
    _u, _s, vt = np.linalg.svd(p - centroid, full_matrices=False)
    n = vt[2]
    return (-n if float(n @ orient_like) < 0.0 else n), centroid


def cluster_planes(tri, normals, area, material, ok, quanta, facing_dot=0.9, tol_quanta=1.5,
                   max_refit=8):
    """Label every face with the planar region it belongs to, growing each region from its
    largest unassigned triangle by ITERATIVE REFIT.

    Each round accepts every still-unassigned candidate of the same material whose normal is
    within `facing_dot` of the region normal and whose three vertices all lie within `tol` of the
    region's CURRENT plane, then refits that plane by least squares (`fit_plane`) over the
    accepted vertices and tests ALL unassigned candidates again -- so a face rejected by an
    earlier, worse plane can still join, and one accepted by it can still leave. The member set
    only stops changing when the plane agrees with what it has collected; `max_refit` is a
    backstop, not the mechanism.

    This exists because a seed triangle's own plane carries the export's rounding noise. On the
    real file, Y is printed to 0.1 in; over a 40 m slab the tilt that one print step puts on a
    seed normal exceeds `tol` at the far end, so one flat SketchUp face arrived as several
    regions and the viewer drew their borders as lines inside the slab.

    `tol = tol_quanta * sum(|n_i| * q_i)` is evaluated with the CURRENT normal, so it tracks the
    plane as it turns. The returned `planes[i]` is `(n, p0, tol)` of the FINAL fit -- the plane
    everything downstream (`plane_basis`, the UV projection, `merge_regions`) then works in.

    Deterministic: seeds are taken by descending area with a STABLE sort, so equal areas are
    seeded in ascending face id, and every test is a whole-array comparison."""
    label = np.full(len(tri), -1)
    planes = []
    for s in np.argsort(-area, kind="stable"):
        if not ok[s] or label[s] != -1:
            continue
        seed_n = normals[s]
        n, p0 = seed_n, tri[s, 0]
        free = ok & (label == -1) & (material == material[s])
        member = np.zeros(len(tri), bool)
        member[s] = True
        tol = tol_quanta * float(np.abs(n) @ quanta)
        for _ in range(max_refit):
            tol = tol_quanta * float(np.abs(n) @ quanta)
            cand = free & (normals @ n > facing_dot)
            cand &= np.abs((tri - p0) @ n).max(axis=1) <= tol
            cand[s] = True          # the seed defines the region; it can never reject itself
            if np.array_equal(cand, member):
                break
            member = cand
            n, p0 = fit_plane(tri[member], seed_n)
        label[member] = len(planes)
        planes.append((n, p0, tol))
    return label, planes


def fit_uv(xy, uv):
    A = np.column_stack([xy, np.ones(len(xy))])
    coef, *_ = np.linalg.lstsq(A, uv, rcond=None)
    return coef[:2].T, coef[2]


def cluster_uv(xy, uv, area, uv_tol=0.02, max_refit=6):
    """xy, uv: (k,3,2). Greedy seeds by area, iterative least-squares refit."""
    k = len(xy)
    label = np.full(k, -1)
    fits = []
    for s in np.argsort(-area):
        if label[s] != -1:
            continue
        J, o = fit_uv(xy[s], uv[s])
        member = np.zeros(k, bool)
        member[s] = True
        kk = np.zeros_like(uv)
        for _ in range(max_refit):
            r = uv - (xy @ J.T + o)
            kk = np.round(r)
            same_k = (kk == kk[:, :1, :]).all(axis=(1, 2))
            close = (np.abs(r - kk) <= uv_tol).all(axis=(1, 2))
            new = (label == -1) & same_k & close
            new[s] = True
            if (new == member).all():
                break
            member = new
            J, o = fit_uv(xy[member].reshape(-1, 2), (uv[member] - kk[member]).reshape(-1, 2))
        label[member] = len(fits)
        fits.append((J, o))
    return label, fits


def build_regions(mesh, positions_w, face_w, ok, table, t_vertices, quanta, flat_materials, uv_tol=0.02):
    tri = positions_w[face_w]
    cr = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = 0.5 * np.linalg.norm(cr, axis=1)
    normals = face_normals(positions_w, face_w, ok)
    uv_all = np.zeros((mesh.n_faces, 3, 2))
    has_uv = (mesh.face_vt >= 0).all(axis=1)
    if len(mesh.uvs):
        uv_all[has_uv] = mesh.uvs[mesh.face_vt[has_uv]]

    plabel, planes = cluster_planes(tri, normals, area, mesh.face_material, ok, quanta)
    group = np.full(mesh.n_faces, -1, np.int64)
    next_group = 0
    for pi, (n, p0, _tol) in enumerate(planes):
        members = np.nonzero(plabel == pi)[0]
        if int(mesh.face_material[members[0]]) in flat_materials:
            group[members] = next_group
            next_group += 1
            continue
        e1, e2 = plane_basis(n)
        xy = np.stack([(tri[members] - p0) @ e1, (tri[members] - p0) @ e2], axis=2)
        ulabel, fits = cluster_uv(xy, uv_all[members], area[members], uv_tol)
        group[members] = next_group + ulabel
        next_group += len(fits)

    # connected components inside a group: faces sharing an edge, or meeting across a T-junction chain
    parent = np.arange(mesh.n_faces)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    ef = edge_face_lists(table)
    sub_edges = t_junction_sub_edges(table, t_vertices)

    def join(faces):
        faces = [f for f in faces if group[f] >= 0]
        for f in faces[1:]:
            if group[f] == group[faces[0]]:
                parent[find(f)] = find(faces[0])

    for faces in ef:
        join(list(faces))
    for e, subs in sub_edges.items():
        faces = list(ef[e])
        for s in subs:
            if s is not None:
                faces += list(ef[s])
        join(faces)

    face_region = np.full(mesh.n_faces, -1, np.int64)
    roots = {}
    for f in np.nonzero(group >= 0)[0]:
        face_region[f] = roots.setdefault(find(f), len(roots))
    return face_region
