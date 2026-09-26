"""Where does double_layers spend its time on a real building? Profile one slice of CHTM 5th floor."""
import cProfile
import pstats
import sys
import time
from pathlib import Path

import numpy as np

from engine.fixes import overlap
from engine.fixes.pipeline import FixProfile, guard_depth_tol
from engine.guard.views import VIEWS_26
from engine.io.obj_reader import read_obj
from engine.pipeline import analyse_topology

mesh = read_obj(next(Path(sys.argv[1]).glob("*.obj")))
topo = analyse_topology(mesh, frozenset())
pos, faces = topo.positions_w, topo.face_w
centre = (pos.min(axis=0) + pos.max(axis=0)) / 2
# a slice: the faces whose centroid lies in the western third of the building
c = pos[faces].mean(axis=1)
x0 = pos[:, 0].min()
sel = np.nonzero(c[:, 0] < x0 + (pos[:, 0].max() - x0) / 3)[0]
print(f"slice: {len(sel)} of {len(faces)} faces")
depth_tol = guard_depth_tol(topo.quanta, FixProfile())

t0 = time.perf_counter()
prof = cProfile.Profile()
prof.enable()
d = overlap.double_layers(pos - centre, faces[sel], depth_tol, VIEWS_26, FixProfile().guard_size, centre=centre)
prof.disable()
print(f"double_layers on the slice: {time.perf_counter() - t0:.1f} s, {d['count']} pairs, {d['px']} px")
st = pstats.Stats(prof)
st.sort_stats("cumulative").print_stats(18)
