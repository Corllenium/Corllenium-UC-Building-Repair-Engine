"""E3: an upright stub standing on a closed slab's top; its two foot vertices lie on the INSIDE of
the top's diagonal edge (T-junctions), it shares no edge, no vertex and no plane with anything.

Brief 09 item 3: `detect_fragments` requires `max_width` since 536fca7, so the detector is called
the way `fix_object` calls it (`sliver_width_bound`), and the engine's own path is printed whole.
Run from the repo root: `PYTHONPATH=<tree> .venv/Scripts/python.exe <this script>`."""
import numpy as np
import engine
from engine.detectors.fragments import detect_fragments
from engine.fixes.pipeline import FixProfile, fix_object, sliver_width_bound
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import _mesh, _quads

s, h = 2000.0, 8.0
P = [[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0], [0, 0, -h], [s, 0, -h], [s, s, -h], [0, s, -h],
     [998, 998, 0], [1002, 1002, 0], [1002, 1002, 0.6], [998, 998, 0.6]]
P = [[float(c) for c in p] for p in P]
uvs, fv, fvt, fm = [], [], [], []
_quads(P, uvs, fv, fvt, fm, [(0, 1, 2, 3),                       # top (+z), diagonal 0-2 or 1-3
                             (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0), (4, 7, 6, 5),
                             (8, 9, 10, 11)])                    # the stub, upright
m = _mesh("slab_with_stub_on_t_junctions", P, uvs, fv, fvt, face_material=fm)
print("engine:", engine.__file__)
print("top faces:", m.face_v[:2].tolist())
topo = analyse_topology(m)
d = detect_fragments(topo.positions_w, topo.face_w, FixProfile(), contact_tol=1.5 * float(topo.quanta.max()),
                     max_width=sliver_width_bound(topo.quanta, FixProfile()))
print("stub faces 12,13 -> fragment:", d.fragments[12:14].tolist(), " report:",
      {k: d.report[k] for k in ("n_components", "n_components_by_shared_edges", "n_joined_by_tjunction", "n_joined_by_coplanar_contact")})
r = fix_object(m, {}, FixProfile(guard_size=(900, 600), n_dirs=32, solidify=False))
print("fix_object: stub removed:", r.removed_fragments[12:14].tolist(), " passed:", r.passed,
      " guard_final fragment_removed:", r.guard_final.totals["fragment_removed"],
      " holes:", r.guard_final.totals["holes"], " shipped faces:", r.mesh.n_faces)
