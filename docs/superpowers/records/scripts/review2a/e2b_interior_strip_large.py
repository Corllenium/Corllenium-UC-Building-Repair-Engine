"""E2b: the same sandwiched strip, in a slab the size of the real files (pixel ~2 in at 900 x 600)."""
import numpy as np
from engine.fixes.pipeline import FixProfile, fix_object
from engine.rays.caster import EmbreeCaster
from engine.tests.fixtures.build import slab_with_interior_strip

S = 2000.0
for width in (0.05, 0.10, 0.14):
    m = slab_with_interior_strip(width=width, length=29.5, size=S, height=8.0)
    r = fix_object(m, {}, FixProfile(guard_size=(900, 600), n_dirs=32))
    g = r.guard_final.totals
    xs = np.linspace(S / 2 - 12.0, S / 2 + 12.0, 97)
    frac = 1.0 - np.abs(xs - S / 2) / 14.75
    ys = S / 2 + 0.4 * width * frac
    o = np.stack([xs, ys, np.full_like(xs, 50.0)], axis=1)
    caster = EmbreeCaster(r.mesh.positions, r.mesh.face_v)
    tri, t = caster.first_hit(o, np.tile([0.0, 0.0, -1.0], (len(o), 1)))
    z = np.where(tri >= 0, 50.0 - t, np.nan)
    bad = ~np.isclose(z, 0.0, atol=1e-6)
    print(f"slab {S:.0f} in, strip 29.5 x {width} in: detector sliver={bool(r.fragment_report.get('n_sliver_faces'))} "
          f"removed={bool(r.removed_fragments[0])} restored={r.n_restored_fragments} passed={r.passed} "
          f"invariants={all(r.invariants.values())} final holes={g['holes']} moved={g['moved_same_flat']+g['moved_other']} "
          f"frag_px={g['fragment_removed']} merge_rolled_back={r.merge_report.get('rolled_back', False)} "
          f"| down-rays through the top along the strip: {int(bad.sum())}/{len(o)} z={sorted(set(np.round(z[bad], 2).tolist()))}")
