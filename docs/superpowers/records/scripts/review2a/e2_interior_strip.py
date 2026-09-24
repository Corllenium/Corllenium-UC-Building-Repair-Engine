"""E2: a strip of real surface sandwiched inside a closed slab's top (all three edges shared with
fat neighbours), narrower than sliver_max_width. Is it removed, and does a slit ship?"""
import numpy as np
from engine.fixes.pipeline import FixProfile, fix_object
from engine.rays.caster import EmbreeCaster
from engine.tests.fixtures.build import slab_with_interior_strip

for width, size in ((0.10, (240, 160)), (0.10, (900, 600)), (0.14, (900, 600)), (0.26, (900, 600))):
    m = slab_with_interior_strip(width=width)
    r = fix_object(m, {}, FixProfile(guard_size=size, n_dirs=32))
    g = r.guard_final.totals
    hist = r.guard_history["fragments"] if hasattr(r, "guard_history") and r.guard_history else None
    # rays straight down through the strip where it is widest (x = 20), at 40 % of its width,
    # and along its length where it is still wider than 0.01 in
    xs = np.linspace(8.0, 32.0, 97)
    frac = 1.0 - np.abs(xs - 20.0) / 14.75
    ys = 20.0 + 0.4 * width * frac
    o = np.stack([xs, ys, np.full_like(xs, 50.0)], axis=1)
    caster = EmbreeCaster(r.mesh.positions, r.mesh.face_v)
    tri, t = caster.first_hit(o, np.tile([0.0, 0.0, -1.0], (len(o), 1)))
    z = np.where(tri >= 0, 50.0 - t, np.nan)
    through = int(np.sum(~np.isclose(z, 0.0, atol=1e-6)))
    print(f"width {width} guard {size}: strip removed={bool(r.removed_fragments[0])} "
          f"n_slivers={r.n_removed_slivers} passed={r.passed} "
          f"final holes={g['holes']} moved={g['moved_same_flat']+g['moved_other']} "
          f"fragment_removed={g['fragment_removed']} border_shift={g['border_shift']} "
          f"| rays through the top along the strip: {through}/{len(o)} "
          f"(z hit: {sorted(set(np.round(z[~np.isclose(z, 0.0, atol=1e-6)], 3).tolist()))[:4]})")
    fh = getattr(r, "guard_history", None)
