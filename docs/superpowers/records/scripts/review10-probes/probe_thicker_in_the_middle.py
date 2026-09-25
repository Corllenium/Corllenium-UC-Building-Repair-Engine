"""`_underside`'s docstring (solidify.py:1437-1441 at dc24e9a): "THE SEARCH REACHES PAST h
DELIBERATELY ... an underside deeper than that is still this slab's underside -- it is what a slab
that is thicker in the middle than at its rim looks like. Stopping at h + tol declares such a region
bottomless and invents a second bottom ABOVE the real one". Since 9f64ae9 / 444d0ef the underside
must lie where the slab's SIDES end (`_ends_here`, within side_band).

Scene: a CLOSED slab, top 40 x 40 at z = 0, rim skirts 8 in deep, a rim bottom (a ring, z = -8,
5 in wide), and a thicker middle: inner walls from -8 to -12 round x, y 5..35, inner bottom at -12."""
from common import SMALL, _mesh, fix_object, np, quad, solidify_summary, where
from engine.fixes.solidify import solidify
from engine.pipeline import analyse_topology
where()
P, uvs, fv, fvt, fm = [], [], [], [], []
q = lambda c: quad(P, uvs, fv, fvt, fm, c)
q([(0, 0, 0), (40, 0, 0), (40, 40, 0), (0, 40, 0)])                       # top, +z
q([(0, 0, -8), (40, 0, -8), (40, 0, 0), (0, 0, 0)])                       # y = 0, -y
q([(40, 0, -8), (40, 40, -8), (40, 40, 0), (40, 0, 0)])                   # x = 40, +x
q([(40, 40, -8), (0, 40, -8), (0, 40, 0), (40, 40, 0)])                   # y = 40, +y
q([(0, 40, -8), (0, 0, -8), (0, 0, 0), (0, 40, 0)])                       # x = 0, -x
for a, b, c, d in [((0, 0), (0, 40), (5, 35), (5, 5)), ((0, 40), (40, 40), (35, 35), (5, 35)),
                   ((40, 40), (40, 0), (35, 5), (35, 35)), ((40, 0), (0, 0), (5, 5), (35, 5))]:
    q([(*a, -8), (*b, -8), (*c, -8), (*d, -8)])                           # the ring, -z
q([(5, 5, -12), (5, 5, -8), (35, 5, -8), (35, 5, -12)])                   # inner walls, outward
q([(35, 5, -12), (35, 5, -8), (35, 35, -8), (35, 35, -12)])
q([(35, 35, -12), (35, 35, -8), (5, 35, -8), (5, 35, -12)])
q([(5, 35, -12), (5, 35, -8), (5, 5, -8), (5, 5, -12)])
q([(5, 5, -12), (5, 35, -12), (35, 35, -12), (35, 5, -12)])               # inner bottom, -z
m = _mesh("thicker_in_the_middle", P, uvs, fv, fvt, face_material=fm)
r = solidify(m, analyse_topology(m), SMALL)
s = r.report
print(f"bottom_exists {s['bottom_exists']}, bottoms_added {s['bottoms_added']}, bottom depth "
      f"{s['bottom_depth_per_region']}, new faces kept {int(r.new_faces.sum())}, refused "
      f"{s['bottom_faces_refused']}")
new = r.mesh.positions[r.mesh.face_v[r.new_faces]]
print("kept invented faces (z):", sorted({round(float(z), 3) for z in new[:, :, 2].ravel()}))
