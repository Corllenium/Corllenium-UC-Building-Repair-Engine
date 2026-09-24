import tempfile
from pathlib import Path
import numpy as np
import engine.cli as cli
from engine.fixes.pipeline import FixProfile, fix_object, flat_material_indices
from engine.pipeline import analyse_topology
from engine.guard.compare import PX_FRAGMENT_REMOVED, PX_HOLE, PX_MATERIAL_CHANGED, PX_MOVED_OTHER, PX_MOVED_SAME_FLAT
from engine.guard.views import VIEWS_26
from engine.tests.fixtures.build import slab_with_strays

m = slab_with_strays()
profile = FixProfile(guard_size=(120, 80), n_dirs=32, solidify=False)
r = fix_object(m, {}, profile)
print("removed fragments:", np.nonzero(r.removed_fragments)[0].tolist(), " passed:", r.passed,
      " guard_final fragment_removed:", r.guard_final.totals["fragment_removed"])
captured = []
cli.save_triptych = lambda path, before, after, codes, **kw: captured.append((path.name, codes.copy()))
ref = r.reference_mesh
fm = flat_material_indices(ref, {}, profile.flat_texture_std)
topo = analyse_topology(ref, fm)
centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
with tempfile.TemporaryDirectory() as d:
    cli._write_guard_images(ref, r, profile, fm, topo, topo.positions_w - centre, Path(d))
damage = (PX_HOLE, PX_MATERIAL_CHANGED, PX_MOVED_OTHER, PX_MOVED_SAME_FLAT)
for name, codes in captured:
    view = tuple(float(x) for x in name.replace('.png', '').split('_')[1:]) if False else None
    print(f"{name}: image fragment-excused px={int((codes == PX_FRAGMENT_REMOVED).sum())}, "
          f"image damage px={int(np.isin(codes, damage).sum())}")
axis = [(i, v) for i, v in enumerate(VIEWS_26) if sum(abs(c) > 0.5 for c in v) == 1]
for i, v in axis:
    vv = r.guard_final.views[i]
    print(f"real guard view {i} {tuple(round(c,2) for c in v)}: fragment_removed={vv.fragment_removed} holes={vv.holes} moved={vv.moved_same_flat + vv.moved_other}")
