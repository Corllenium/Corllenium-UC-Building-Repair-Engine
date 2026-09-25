"""Probe (review of brief 10, 01cc420 "a piece belongs to the slab, and a wall keeps its side's look").

`_attached` decides belonging in the SIDE'S OWN 2-D FRAME -- distances between polygons projected
onto the side plane, and to two lines, the top edge and the wall's FOOT -- so it ignores how far in
front of the side a face stands (anything within the 2.5 in band), and the foot is a line of the
PLAN, not of the model. `_wall_look` then takes the wall's material from the pieces found BEFORE
the cap guard, and keeps it when the guard gives those pieces back.

Each scene: a closed slab, `size` square, 8 in deep (bottom and three skirts, wound outward), whose
x = 0 side is missing or broken, at 40 in and at the real files' 2000 in, through solidify with the
default 900 x 600 guard (n_dirs 32, as the brief-10 tests run it).

  A foot    x = 0 side wholly missing; a SIGN (m1, one quad facing -x) 1.2 in in front of it,
            z -10..-2: it reaches 2 in below the slab and touches nothing. Its projection crosses
            the wall's planned foot (z = -8): "attached", 75 % inside the window -- the only
            piece, so the wall takes ITS material.
  A ground  the same sign standing ON a ground plate (a closed box x -40..-0.5, top at z = -8, the
            wall's foot level), z -8..-2: its lower edge lies on the foot line.
  B tooth   x = 0 side missing but for ONE tooth (m0, in the side plane, base 8 in on the top edge,
            apex 6 in down); a SIGN in m0 1.2 in in front of it, z -5..-1, starting 1 in before the
            tooth's right base corner: 1.2 in from the tooth in 3-D, but its projection overlaps the
            tooth's -- "connected", so attached through the tooth.
  C row     x = 0 side broken the other way: only its MIDDLE strip survives (m0, z -6..-2, whole
            length, in the side plane). A real piece of the side, touching neither the top edge nor
            the foot: not attached, not a piece -- and the wall over the side lies ON it.

usage: PYTHONPATH=<tree>;<this folder> python probe_piece_attachment.py
       (<tree> = the dc24e9a worktree, or the 3561127 tree -- the commit before 01cc420)
"""
from common import FixProfile, _mesh, box, np, quad, where
from engine.fixes.solidify import solidify
from engine.pipeline import analyse_topology

where()
PROFILE = FixProfile(guard_size=(900, 600), n_dirs=32)


def scene(kind, size):
    P, uvs, fv, fvt, fm = [], [], [], [], []
    box(P, uvs, fv, fvt, fm, 0, size, 0, size, -8, 0, skip=("x0",))       # faces 0-9
    watch = {}
    y0 = 0.6 * size
    if kind == "A foot":
        watch["sign (m1)"] = quad(P, uvs, fv, fvt, fm, [(-1.2, y0, -10), (-1.2, y0, -2),
                                                         (-1.2, y0 + 8, -2), (-1.2, y0 + 8, -10)],
                                  material=1)
    elif kind == "A ground":
        box(P, uvs, fv, fvt, fm, -40, -0.5, -10, size + 10, -14, -8)
        watch["sign (m1)"] = quad(P, uvs, fv, fvt, fm, [(-1.2, y0, -8), (-1.2, y0, -2),
                                                         (-1.2, y0 + 8, -2), (-1.2, y0 + 8, -8)],
                                  material=1)
    elif kind == "B tooth":
        c = 0.5 * size
        b = len(P)
        P += [[0.0, c - 4, 0.0], [0.0, c + 4, 0.0], [0.0, c, -6.0]]
        first = len(fv)
        fv.append([b + 1, b + 2, b + 0])                          # normal -x, outward
        k = len(uvs)
        uvs += [[P[v][1] * 0.05, P[v][2] * 0.05] for v in (b + 1, b + 2, b + 0)]
        fvt.append([k, k + 1, k + 2])
        fm.append(0)
        watch["tooth (m0)"] = [first]
        ys = c + 3.0
        watch["sign (m0)"] = quad(P, uvs, fv, fvt, fm, [(-1.2, ys, -5), (-1.2, ys, -1),
                                                         (-1.2, ys + 8, -1), (-1.2, ys + 8, -5)])
    elif kind == "C row":
        watch["middle strip (m0)"] = quad(P, uvs, fv, fvt, fm, [(0, 0, -6), (0, 0, -2),
                                                                 (0, size, -2), (0, size, -6)])
    return _mesh(kind, P, uvs, fv, fvt, materials=("m0", "m1"), face_material=fm), watch


for kind in ("A foot", "A ground", "B tooth", "C row"):
    for size in (40.0, 2000.0):
        m, watch = scene(kind, size)
        r = solidify(m, analyse_topology(m), PROFILE)
        s = r.report
        new = np.nonzero(r.new_faces)[0]
        wall = [f for f in new if np.allclose(r.mesh.positions[r.mesh.face_v[f]][:, 0], 0.0)]
        tri = r.mesh.positions[r.mesh.face_v[wall]]
        area = sum(0.5 * np.linalg.norm(np.cross(t[1] - t[0], t[2] - t[0])) for t in tri)
        side = [f for f in range(r.mesh.n_faces)
                if np.allclose(r.mesh.positions[r.mesh.face_v[f]][:, 0], 0.0)]
        tri_s = r.mesh.positions[r.mesh.face_v[side]]
        side_area = sum(0.5 * np.linalg.norm(np.cross(t[1] - t[0], t[2] - t[0])) for t in tri_s)
        print(f"[{kind}] size {size:g}: cap_guard_passed={s['cap_guard_passed']}, walls built "
              f"{s['skirts_added']} kept {s['sides_rebuilt']['edges']}, refused wall faces "
              f"{s['walls_refused']}, pieces replaced {s['side_pieces_replaced']}")
        for name, faces in watch.items():
            print(f"    {name}: replaced {r.replaced[faces].tolist()}")
        print(f"    kept wall faces in x = 0: {len(wall)}, area {area:.2f}, materials "
              f"{sorted({int(r.mesh.face_material[f]) for f in wall})}; the whole x = 0 plane "
              f"covers {side_area:.2f} of {8 * size:g}")
