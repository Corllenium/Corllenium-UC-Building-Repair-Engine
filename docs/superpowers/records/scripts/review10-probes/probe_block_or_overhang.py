"""Item 6 (f7e27d1): `slab_with_a_block_standing_on_it(at_edge=True)` read the other way. Its
geometry -- a U-shaped top at z 0 round a notch at the slab's y = 0 edge, no side hanging from the
notch's edges, a closed block over the notch whose underside lies in the top's plane -- is ALSO
an overhang over a notch whose sides the export lost (a cantilevered block, open air under it).
The rule's three tests (the top's measured depth, no own side along the shared edges, 99 % inside
the top's convex hull) read nothing that differs between the two. What ships for the block's
underside (faces 12, 13 of the block: its bottom is the first two of its 12)?"""
from common import SMALL, area_at, fate, fix_object, shapely, solidify_summary, where
from engine.tests.fixtures.build import slab_with_a_block_standing_on_it
where()
m = slab_with_a_block_standing_on_it(at_edge=True)
first = m.n_faces - 12
r = fix_object(m, {}, SMALL)
print("passed", r.passed)
print("   ", solidify_summary(r))
print("    the block's underside", [first, first + 1], fate(r, [first, first + 1]))
notch = shapely.box(20.0, 0.0, 40.0, 20.0)
print("    SHIPPED over the notch: z = 0", area_at(r.mesh, notch, 0.0), "| z = -8", area_at(r.mesh, notch, -8.0))
