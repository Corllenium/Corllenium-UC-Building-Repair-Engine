"""E8b, the narrow flat fill (job P2-E8b): the owner's one exception to "no hole filling" (AGENTS.md section 4).

A hole whose whole border lies in one plane matching the neighbouring surface may be filled, using existing points
only, and each fill is shown in the floor review. `E8FlatFill.plan` finds the loops of open edges of its stage input
(the same open edges `find_errors` counts: `analyse_topology`'s `EDGE_OPEN`), and plans ONE "add" per loop that meets
every ruling of the brief, each its own site; every other loop is listed in `not_filled` with the rule that refused
it (E8c, the needs-modelling queue, reads that list). Nothing here is checked by argument: the kernel's site checks
(`validate_sites=True`) judge every fill with the Validator's `fill_site` class, and roll back a fill they charge.

THE RULINGS, in the order a loop is tested (the first that fails names the refusal):
- E8b-R1 a candidate is ONE closed loop of open edges: every point on it has exactly two open edges
  (`not_a_simple_loop`); it does not cross itself after projection to its plane (`self_crossing`); its neighbours
  lie on one side of it (`neighbours_on_both_sides`). A loop whose neighbours lie INSIDE it is the outer border of
  a patch, not a hole: it is counted (`report["outer_boundaries"]`) and neither filled nor listed. A hole with
  another open-edge loop inside it (`inner_loop`), or with any face passing through it (`faces_inside`: a post, a
  wall or a patch standing in the hole), goes to E8c.
- E8b-R2 every loop point lies within `plane_tol = 2 x print step` of the loop's least-squares plane
  (`not_planar`); every face that shares a loop edge has its normal within 1 degree of that plane's, up to sign,
  and all its corners within `plane_tol` of the plane (`neighbour_not_coplanar`: a wall meeting a floor at the
  border disqualifies the loop).
- E8b-R3 the hole's largest inscribed circle, measured in the plane, is at most `FILL_MAX_DIAMETER` (39.37 in, one
  Minecraft block) across (`too_wide`). A named constant, not a FixProfile field.
- E8b-R4 the neighbours have one look (`face_keys`' look: `unit.looks`, else `material:<name>`; no material is the
  look `material:<none>`) (`two_looks`); they face one side (`neighbours_face_both_ways`); one affine map from the
  plane's xy to UV fits every neighbour corner with the largest residual at most `UV_RESIDUAL_MAX` (1e-3 UV units)
  (`uv_seam`; also when only some neighbours carry UVs). A look with no material cannot be written as an add
  (`apply_edits` needs a material index): `no_material`.
- E8b-R5 the fill is ear-clipped (`ear_clip`, written here, no dependency, no Steiner point) on the loop's own
  points: `n - 2` triangles of positive area whose areas sum to the polygon's within 1e-6 relative
  (`triangulation_failed` otherwise). The edit: `Edit(engine="E8", kind="add", new_points=None)` with
  `evidence["material"]`, `new_face_uv` (the neighbours' map continued), `new_face_normal` (the plane normal on the
  neighbours' side), wound to face the same side as its neighbours.

THE MARK. Every fill's `evidence` carries `flat_fill: True` and `loop`: the loop's vertex ids of the stage input, in
order. The kernel hands those to the site judge, and the Validator's `fill_site` class (E8b-R6) accepts a covered
sample only when every line of sight that saw it now ends on such a fill, inside that fill's own loop.

The points a fill uses are the stage input's: with `--engines E8` (E8a, then E8b) that is E8a's kept output, so a
point E8a's solidify invented and kept can be a loop point. E8b itself never invents or moves one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.ops import polylabel

from engine.pipeline import analyse_topology_memo
from engine.repair.types import NO_MATERIAL_LOOK, Edit, RepairContext, UnitState, print_step
from engine.topo.edges import EDGE_OPEN
from engine.topo.planes import fit_uv, plane_basis

#: E8b-R3: the widest hole the flat fill takes, as the diameter of its largest inscribed circle (one block, 1 m).
FILL_MAX_DIAMETER = 39.37
#: E8b-R2: the largest angle between a neighbour's normal and the loop's plane normal, up to sign, in degrees.
NORMAL_TOL_DEG = 1.0
#: E8b-R2: `plane_tol` is this many print steps.
PLANE_STEPS = 2.0
#: E8b-R4: the largest residual (UV units) of the one affine UV map fitted to every neighbour corner.
UV_RESIDUAL_MAX = 1e-3
#: E8b-R5: the fill's area equals the polygon's within this, relative.
AREA_REL_TOL = 1e-6
#: How close (in in) `polylabel` gets to the true centre of the largest inscribed circle.
_POLYLABEL_TOL = 0.005

_RULE = {"not_a_simple_loop": "E8b-R1", "self_crossing": "E8b-R1", "neighbours_on_both_sides": "E8b-R1",
         "inner_loop": "E8b-R1", "faces_inside": "E8b-R1", "not_planar": "E8b-R2",
         "neighbour_not_coplanar": "E8b-R2", "too_wide": "E8b-R3", "two_looks": "E8b-R4",
         "neighbours_face_both_ways": "E8b-R4", "uv_seam": "E8b-R4", "no_material": "E8b-R4",
         "triangulation_failed": "E8b-R5"}


# ------------------------------------------------------------------------------------------- ear clipping

def _cross(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Twice the signed area of (a, b, c), broadcast over leading axes: > 0 counter-clockwise."""
    return (b[..., 0] - a[..., 0]) * (c[..., 1] - a[..., 1]) - (b[..., 1] - a[..., 1]) * (c[..., 0] - a[..., 0])


def ear_clip(xy) -> list[tuple[int, int, int]]:
    """Triangulate the simple polygon `xy` (n, 2) on its own points: n - 2 triangles of indices into `xy`, each
    counter-clockwise, none of zero area, no Steiner point. An ear is a STRICTLY convex point whose triangle holds no
    other remaining point, not even on its sides, so a run of collinear points is never clipped into a sliver of no
    area. Raises `ValueError` when no ear is left (a polygon that is not simple, or collinear to the end)."""
    pts = np.asarray(xy, dtype=np.float64)
    n = len(pts)
    if n < 3:
        raise ValueError("a polygon needs 3 points")
    signed = float(_cross(pts[0], pts[np.arange(1, n - 1)], pts[np.arange(2, n)]).sum())
    order = list(range(n)) if signed > 0 else list(range(n))[::-1]
    span = float(np.ptp(pts, axis=0).max()) or 1.0
    eps = 1e-12 * span * span
    prev = {order[k]: order[k - 1] for k in range(n)}
    nxt = {order[k]: order[(k + 1) % n] for k in range(n)}
    alive = set(order)
    tris: list[tuple[int, int, int]] = []
    v, misses = order[0], 0
    while len(alive) > 3:
        a, c = prev[v], nxt[v]
        ear = float(_cross(pts[a], pts[v], pts[c])) > eps
        if ear:
            others = np.fromiter((i for i in alive if i not in (a, v, c)), dtype=np.int64)
            q = pts[others]
            inside = ((_cross(pts[a], pts[v], q) >= -eps) & (_cross(pts[v], pts[c], q) >= -eps)
                      & (_cross(pts[c], pts[a], q) >= -eps))
            ear = not inside.any()
        if ear:
            tris.append((a, v, c))
            alive.discard(v)
            nxt[a], prev[c] = c, a
            v, misses = c, 0
            continue
        v, misses = c, misses + 1
        if misses > len(alive):
            raise ValueError("no ear left: the polygon is not simple, or its remaining points are collinear")
    a = next(iter(alive))
    last = (prev[a], a, nxt[a])
    if float(_cross(*(pts[i] for i in last))) <= eps:
        raise ValueError("the last triangle has no area")
    tris.append(last)
    return tris


# ------------------------------------------------------------------------------------------- the engine

@dataclass
class _Loop:
    id: int
    welded: list                      # welded vertex ids, in loop order (or a component's vertices, unordered)
    closed: bool
    faces: list = field(default_factory=list)      # the neighbour face of each loop edge (edge k: k -> k + 1)


def _components(edges: np.ndarray) -> list[list[int]]:
    """The connected components of the open-edge graph, as lists of edge rows, smallest vertex first."""
    parent: dict[int, int] = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in edges.tolist():
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    groups: dict[int, list[int]] = {}
    for row, (a, _b) in enumerate(edges.tolist()):
        groups.setdefault(find(a), []).append(row)
    return [groups[k] for k in sorted(groups)]


def _walk(edges: np.ndarray, rows: list[int]) -> list[int] | None:
    """The vertices of the component `rows` in cycle order, or None when some vertex has other than two open edges."""
    nbr: dict[int, list[int]] = {}
    for a, b in edges[rows].tolist():
        nbr.setdefault(a, []).append(b)
        nbr.setdefault(b, []).append(a)
    if any(len(v) != 2 for v in nbr.values()):
        return None
    start = min(nbr)
    loop, prev, cur = [start], None, start
    while True:
        a, b = nbr[cur]
        step = a if a != prev else b
        if step == start:
            break
        loop.append(step)
        prev, cur = cur, step
        if len(loop) > len(nbr):
            return None
    return loop if len(loop) == len(nbr) else None


@dataclass
class E8FlatFill:
    """The engine E8b (see the module docstring). After `plan`: `not_filled` (one row per refused hole) and
    `report` (counts, and the inscribed diameter of every hole that got that far, for the histogram)."""
    name: str = "E8b"
    legacy: bool = False
    not_filled: list = field(default_factory=list, repr=False)
    report: dict | None = field(default=None, repr=False)

    def plan(self, unit: UnitState, ctx: RepairContext) -> list[Edit]:
        mesh = unit.mesh
        self.not_filled = []
        topo = analyse_topology_memo(mesh)
        tol = PLANE_STEPS * print_step(mesh)
        open_rows = np.flatnonzero(np.asarray(topo.edge_class) == EDGE_OPEN)
        edges = topo.table.edges[open_rows]
        # the one face of each open edge
        face_of_edge = np.full(len(topo.table.edges), -1, np.int64)
        fe = topo.table.face_edges
        f_ids, k_ids = np.nonzero(fe >= 0)
        is_open = np.zeros(len(topo.table.edges), bool)
        is_open[open_rows] = True
        hit = is_open[fe[f_ids, k_ids]]
        face_of_edge[fe[f_ids, k_ids][hit]] = f_ids[hit]
        edge_row = {(int(a), int(b)): int(r) for r, (a, b) in zip(open_rows, edges.tolist())}

        open_vertices = np.unique(edges.reshape(-1)) if len(edges) else np.zeros(0, np.int64)
        tri_all = mesh.positions[mesh.face_v]
        lo_all, hi_all = tri_all.min(axis=1), tri_all.max(axis=1)
        report = {"open_edges": int(len(edges)), "components": 0, "loops": 0, "outer_boundaries": 0, "holes": 0,
                  "planned": 0, "not_filled_by_reason": {}, "diameters": [], "plane_tol": tol,
                  "max_diameter": FILL_MAX_DIAMETER}
        edits: list[Edit] = []
        comps = _components(edges) if len(edges) else []
        report["components"] = len(comps)
        for loop_id, rows in enumerate(comps):
            welded = _walk(edges, rows)
            if welded is None:
                verts = sorted(set(edges[rows].reshape(-1).tolist()))
                self._refuse(loop_id, "not_a_simple_loop", "some point on it has other than two open edges",
                             topo.positions_w[verts], {})
                continue
            report["loops"] += 1
            outcome = self._judge_loop(loop_id, welded, unit, topo, tol, edge_row, face_of_edge, open_vertices,
                                       lo_all, hi_all, report)
            if isinstance(outcome, Edit):
                edits.append(outcome)
        report["planned"] = len(edits)
        for row in self.not_filled:
            key = row["reason"]
            report["not_filled_by_reason"][key] = report["not_filled_by_reason"].get(key, 0) + 1
        self.report = report
        return edits

    # -- one loop ------------------------------------------------------------------------------------------------
    def _refuse(self, loop_id, reason, detail, points, measured):
        points = np.asarray(points, float).reshape(-1, 3)
        row = {"loop": int(loop_id), "rule": _RULE[reason], "reason": reason, "detail": detail,
               "vertices": int(len(points)), "centroid": [round(float(v), 3) for v in points.mean(axis=0)],
               "points": [[round(float(v), 3) for v in p] for p in points]}
        row.update(measured)
        self.not_filled.append(row)
        return None

    def _judge_loop(self, loop_id, welded, unit, topo, tol, edge_row, face_of_edge, open_vertices, lo_all, hi_all,
                    report):
        mesh = unit.mesh
        n = len(welded)
        faces = []
        for k in range(n):
            a, b = welded[k], welded[(k + 1) % n]
            faces.append(int(face_of_edge[edge_row[(min(a, b), max(a, b))]]))
        # each loop point as an ORIGINAL vertex id of the neighbour face of the edge leaving it
        fw = topo.face_w
        orig = []
        for k in range(n):
            f = faces[k]
            corner = int(np.flatnonzero(fw[f] == welded[k])[0])
            orig.append(int(mesh.face_v[f, corner]))
        pts = mesh.positions[orig].astype(np.float64)
        measured: dict = {}
        refuse = lambda reason, detail: self._refuse(loop_id, reason, detail, pts, measured)

        # E8b-R2: the loop is planar
        centre = pts.mean(axis=0)
        _u, _s, vt = np.linalg.svd(pts - centre, full_matrices=False)
        normal = vt[2] / np.linalg.norm(vt[2])
        planarity = float(np.abs((pts - centre) @ normal).max())
        measured["planarity"] = round(planarity, 5)
        if planarity > tol:
            return refuse("not_planar", f"a loop point lies {planarity:.4f} in off the loop's plane "
                                        f"(plane_tol {tol:.4f} in)")
        # E8b-R1: simple after projection
        e1, e2 = plane_basis(normal)
        xy = np.column_stack([(pts - centre) @ e1, (pts - centre) @ e2])
        ring = shapely.LinearRing(xy)
        if not ring.is_simple:
            return refuse("self_crossing", "the loop crosses or touches itself in its plane")
        # E8b-R2: every neighbour is coplanar
        fv = mesh.face_v[faces]
        tri = mesh.positions[fv]
        fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        fn /= np.linalg.norm(fn, axis=1, keepdims=True)
        dots = fn @ normal
        angle = float(np.degrees(np.arccos(np.clip(np.abs(dots), -1.0, 1.0))).max())
        offset = float(np.abs((tri - centre) @ normal).max())
        measured.update(max_angle=round(angle, 4), max_offset=round(offset, 5))
        if angle > NORMAL_TOL_DEG or offset > tol:
            return refuse("neighbour_not_coplanar", f"a neighbour face is {angle:.3f} deg off the loop's plane and "
                                                    f"{offset:.4f} in out of it (limits {NORMAL_TOL_DEG} deg, "
                                                    f"{tol:.4f} in)")
        # a hole, or the outer border of a patch: where do the neighbours lie?
        area_signed = 0.5 * float(_cross(xy[0], xy[np.arange(1, n - 1)], xy[np.arange(2, n)]).sum())
        side = []
        for k in range(n):
            f, a, b = faces[k], welded[k], welded[(k + 1) % n]
            third = int(np.flatnonzero((fw[f] != a) & (fw[f] != b))[0])
            v = (mesh.positions[mesh.face_v[f, third]] - centre)
            vxy = np.array([v @ e1, v @ e2])
            side.append(float(_cross(xy[k], xy[(k + 1) % n], vxy)) * np.sign(area_signed))
        side = np.asarray(side)
        if (side > 0).all():
            report["outer_boundaries"] += 1
            return None
        if not (side < 0).all():
            return refuse("neighbours_on_both_sides", "some neighbour faces lie inside the loop and some outside")
        report["holes"] += 1
        polygon = shapely.Polygon(xy)
        # E8b-R3 is measured for every hole that got this far (the histogram)
        pole = polylabel(polygon, tolerance=_POLYLABEL_TOL)
        diameter = 2.0 * float(polygon.exterior.distance(pole))
        report["diameters"].append(round(diameter, 3))
        measured["inscribed_diameter"] = round(diameter, 3)
        measured["area"] = round(abs(area_signed), 3)
        # E8b-R1: nothing inside the hole
        interior = polygon.buffer(-tol)
        if not interior.is_empty:
            lo, hi = pts.min(axis=0) - tol, pts.max(axis=0) + tol
            others = np.setdiff1d(open_vertices, np.asarray(welded))
            if len(others):
                q = topo.positions_w[others]
                near = ((q >= lo) & (q <= hi)).all(axis=1)
                q = q[near] - centre
                on_plane = np.abs(q @ normal) <= tol
                if on_plane.any() and shapely.contains_xy(interior, q[on_plane] @ e1, q[on_plane] @ e2).any():
                    return refuse("inner_loop", "another loop of open edges lies inside the hole")
            if _faces_inside(mesh, topo.ok, lo_all, hi_all, lo, hi, centre, normal, e1, e2, tol, interior):
                return refuse("faces_inside", "a face passes through the hole (a post, a wall or a patch in it)")
        if diameter > FILL_MAX_DIAMETER:
            return refuse("too_wide", f"its largest inscribed circle is {diameter:.2f} in across "
                                      f"(at most {FILL_MAX_DIAMETER} in)")
        # E8b-R4: one look, one side, one UV map
        materials = mesh.face_material[faces]
        looks = sorted({_look(mesh, unit.looks, int(m)) for m in materials.tolist()})
        measured["looks"] = looks
        if len(looks) != 1:
            return refuse("two_looks", f"the neighbours have {len(looks)} looks")
        if not ((dots > 0).all() or (dots < 0).all()):
            return refuse("neighbours_face_both_ways", "the neighbour faces do not all face one side")
        if int(materials.min()) < 0:
            return refuse("no_material", "the neighbours have no material; an add needs a material index")
        material = int(materials.min())
        out_normal = normal if dots[0] > 0 else -normal
        e1, e2 = plane_basis(out_normal)          # right-handed with the fill's normal: counter-clockwise faces it
        xy = np.column_stack([(pts - centre) @ e1, (pts - centre) @ e2])
        vt = mesh.face_vt[faces]
        has_uv = (vt >= 0).all(axis=1)
        uv_map, residual = None, None
        if has_uv.any():
            if not has_uv.all():
                return refuse("uv_seam", "some neighbours carry UVs and some do not")
            corners = (mesh.positions[fv].reshape(-1, 3) - centre)
            cxy = np.column_stack([corners @ e1, corners @ e2])
            cuv = mesh.uvs[vt].reshape(-1, 2).astype(np.float64)
            coef, off = fit_uv(cxy, cuv)
            residual = float(np.linalg.norm(cxy @ coef.T + off - cuv, axis=1).max())
            measured["uv_residual"] = round(residual, 6)
            if residual > UV_RESIDUAL_MAX:
                return refuse("uv_seam", f"one affine UV map leaves a residual of {residual:.4g} on the neighbours "
                                         f"(at most {UV_RESIDUAL_MAX})")
            uv_map = (coef, off)
        # E8b-R5: ear-clipped on the loop's own points
        try:
            local = np.asarray(ear_clip(xy), np.int64)
        except ValueError as exc:
            return refuse("triangulation_failed", str(exc))
        tri_xy = xy[local]
        areas = 0.5 * _cross(tri_xy[:, 0], tri_xy[:, 1], tri_xy[:, 2])
        if len(local) != n - 2 or (areas <= 0).any() or abs(areas.sum() - abs(area_signed)) > AREA_REL_TOL * abs(area_signed):
            return refuse("triangulation_failed", f"{len(local)} triangles for {n} points, area "
                                                  f"{areas.sum():.6f} against {abs(area_signed):.6f}")
        new_faces = np.asarray(orig, np.int64)[local]
        new_uv = None
        if uv_map is not None:
            coef, off = uv_map
            new_uv = tri_xy @ coef.T + off
        new_normal = np.broadcast_to(out_normal, (len(local), 3, 3)).copy()
        look = looks[0]
        evidence = {"flat_fill": True, "loop": [int(i) for i in orig], "loop_id": int(loop_id), "material": material,
                    "look": look, "vertices": int(n), "area": round(float(areas.sum()), 4),
                    "inscribed_diameter": round(diameter, 3),
                    "centroid": [round(float(v), 3) for v in centre], "normal": [round(float(v), 6) for v in out_normal],
                    "planarity": round(planarity, 5), "max_angle": round(angle, 4), "max_offset": round(offset, 5),
                    "uv_residual": None if residual is None else round(residual, 6), "neighbours": sorted(set(faces))}
        return Edit(engine="E8", kind="add", faces=(), new_faces=new_faces, new_points=None, site=int(loop_id),
                    reason=(f"E8 narrow flat fill: a {n}-point hole of {areas.sum():.1f} sq in, {diameter:.2f} in "
                            f"across, in {look}"),
                    evidence=evidence, new_face_uv=new_uv, new_face_normal=new_normal)


def _look(mesh, looks: dict, material: int) -> str:
    """`face_keys`' look of a material index: `looks`, else `material:<name>`; no material is its own look."""
    if material < 0:
        return NO_MATERIAL_LOOK
    return looks.get(material) or f"material:{mesh.materials[material]}"


def _faces_inside(mesh, ok, lo_all, hi_all, lo, hi, centre, normal, e1, e2, tol, interior) -> bool:
    """Does any (non-degenerate) face meet the hole's interior (shrunk by `tol`) where it crosses the plane? A face's
    part in the plane is the convex hull of its corners within `tol` of it and of its edges' crossings of it."""
    cand = np.flatnonzero(ok & (lo_all <= hi).all(axis=1) & (hi_all >= lo).all(axis=1))
    if not len(cand):
        return False
    tri = mesh.positions[mesh.face_v[cand]] - centre
    d = tri @ normal
    crosses = ~((d > tol).all(axis=1) | (d < -tol).all(axis=1))
    for t, dist in zip(tri[crosses], d[crosses]):
        pts = [t[i] for i in range(3) if abs(dist[i]) <= tol]
        for i, j in ((0, 1), (1, 2), (2, 0)):
            if (dist[i] < -tol and dist[j] > tol) or (dist[i] > tol and dist[j] < -tol):
                pts.append(t[i] + (dist[i] / (dist[i] - dist[j])) * (t[j] - t[i]))
        if not pts:
            continue
        flat = shapely.MultiPoint([(float(p @ e1), float(p @ e2)) for p in pts]).convex_hull
        if flat.intersects(interior):
            return True
    return False
