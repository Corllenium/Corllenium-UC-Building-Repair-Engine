"""Probe (review of brief 10, 3561127 "one bottom per footprint"): `_coincident_new_faces` now also
refuses a new face lying ON a new face another group built before it -- walls included, opposite
windings included (`_Planes.lying_on` compares |cos|). Where two slabs meet at a STEP and both lost
the side between them, the upper slab's wall and the lower slab's wall overlap only in part.

Scene: A, a slab x 0..40, top z = 0, bottom -8; B, beside it, x 40..80, top z = -4, bottom -12
(a step down of 4 in). Both closed (bottoms, outer sides) except the side each has at x = 40,
which the export lost. The picture needs A's riser (x = 40, z -4..0) and B's side below A
(x = 40, z -12..-8); the band z -8..-4 between them is the two slabs' interface.

Prints, per commit on PYTHONPATH: the walls built at x = 40 and kept, and what covers the plane
x = 40 in the shipped mesh by height band.
"""
from common import SMALL, _mesh, box, fix_object, np, solidify_summary, where

where()


def scene():
    P, uvs, fv, fvt, fm = [], [], [], [], []
    box(P, uvs, fv, fvt, fm, 0, 40, 0, 40, -8, 0, skip=("x1",))       # A, no x = 40 side
    box(P, uvs, fv, fvt, fm, 40, 80, 0, 40, -12, -4, skip=("x0",))    # B, no x = 40 side
    return _mesh("step_between_two_slabs", P, uvs, fv, fvt, face_material=fm)


m = scene()
r = fix_object(m, {}, SMALL)
print(f"passed={r.passed}")
print("   ", solidify_summary(r))
tri = r.mesh.positions[r.mesh.face_v]
on = np.nonzero(np.isclose(tri[:, :, 0], 40.0).all(axis=1))[0]
for lo, hi in ((-4.0, 0.0), (-8.0, -4.0), (-12.0, -8.0)):
    area = 0.0
    for f in on:
        t = tri[f]
        import shapely
        area += shapely.Polygon(t[:, 1:]).intersection(shapely.box(0.0, lo, 40.0, hi)).area
    print(f"    shipped x = 40 plane, z {lo:g}..{hi:g}: {area:.1f} of 160 sq in")
