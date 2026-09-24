"""Probe: a real piece of a slab's visible top -- a 3 x 1 in infill patch -- whose edges meet the
surrounding top only through T-junctions (the surround has a vertex at the middle of each of the
patch's sides; the patch has none). Components are taken over SHARED WELDED EDGES, so the patch is
its own 2-face, 3 sq in component. Is it removed as a 'fragment', and does every guard pass?"""
import numpy as np
import shapely

from engine.fixes.pipeline import FixProfile, fix_object
from engine.rays.caster import EmbreeCaster
from engine.tests.fixtures.build import _mesh, _quads

S, H = 40.0, 8.0
x0, x1, y0, y1 = 18.5, 21.5, 19.5, 20.5          # the 3 x 1 in patch
hole = [(x0, y0), ((x0 + x1) / 2, y0), (x1, y0), (x1, (y0 + y1) / 2), (x1, y1),
        ((x0 + x1) / 2, y1), (x0, y1), (x0, (y0 + y1) / 2)]      # midpoints on the surround only
top = shapely.Polygon([(0, 0), (S, 0), (S, S), (0, S)], [hole])

P, index = [], {}


def vid(x, y, z):
    key = (round(x, 6), round(y, 6), round(z, 6))
    if key not in index:
        index[key] = len(P)
        P.append([x, y, z])
    return index[key]


uvs, fv, fvt, fm = [], [], [], []


def tri(a, b, c):
    pts = np.array([P[a], P[b], P[c]])
    n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
    if n[2] < 0:
        b, c = c, b
    base = len(uvs)
    uvs.extend((np.array([P[a], P[b], P[c]])[:, :2] * 0.05).tolist())
    fv.append([a, b, c]); fvt.append([base, base + 1, base + 2]); fm.append(0)


for part in shapely.constrained_delaunay_triangles(top).geoms:      # the surround, +z
    (ax, ay), (bx, by), (cx, cy) = np.asarray(part.exterior.coords)[:3]
    tri(vid(ax, ay, 0), vid(bx, by, 0), vid(cx, cy, 0))
n_surround = len(fv)
c = [vid(x0, y0, 0), vid(x1, y0, 0), vid(x1, y1, 0), vid(x0, y1, 0)]
tri(c[0], c[1], c[2]); tri(c[0], c[2], c[3])                    # the patch, +z, corner to corner
patch = [n_surround, n_surround + 1]
corners = [vid(0, 0, 0), vid(S, 0, 0), vid(S, S, 0), vid(0, S, 0),
           vid(0, 0, -H), vid(S, 0, -H), vid(S, S, -H), vid(0, S, -H)]
_quads(P, uvs, fv, fvt, fm, [(corners[0], corners[4], corners[5], corners[1]),   # sides, outward
                             (corners[1], corners[5], corners[6], corners[2]),
                             (corners[2], corners[6], corners[7], corners[3]),
                             (corners[3], corners[7], corners[4], corners[0]),
                             (corners[4], corners[7], corners[6], corners[5])])  # bottom, -z
mesh = _mesh("slab_with_infill_patch", P, uvs, fv, fvt, face_material=fm)

res = fix_object(mesh, {}, FixProfile(guard_size=(240, 160), n_dirs=32))
g = res.guard_final.totals
print("patch faces removed as fragments:", [bool(res.removed_fragments[f]) for f in patch])
print("fragment report:", {k: res.fragment_report[k] for k in
                           ("n_components", "n_candidate_components", "n_fragment_faces")})
print("passed:", res.passed, " invariants:", res.invariants)
print("guard_final: holes", g["holes"], "moved", g["moved_same_flat"] + g["moved_other"],
      "material", g["material_changed"], "flicker", g["edge_flicker"],
      "fragment_removed px", g["fragment_removed"])
caster = EmbreeCaster(res.mesh.positions, res.mesh.face_v)
tri_hit, t = caster.first_hit(np.array([[20.0, 20.0, 50.0]]), np.array([[0.0, 0.0, -1.0]]))
print("ray straight down through the patch centre, shipped mesh: hits z =",
      None if tri_hit[0] < 0 else round(50.0 - float(t[0]), 3), "(the top is at z = 0)")
