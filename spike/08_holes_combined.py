"""Are the holes in file A real, or filled by file B? Render A alone vs A+B, double-sided, straight down and oblique.
Also count open boundary loops and how many are planar (candidates for an in-place rebuild patch)."""
from pathlib import Path

import numpy as np
from PIL import Image

from _common import FILES, OUT, SNAP, load_obj, save, tri_geometry, weld

here = Path(__file__).parent
src = (here / "06_render_classes.py").read_text(encoding="utf-8").split("\ndef main(name):")[0]
RND = {"__file__": str(here / "06_render_classes.py")}
exec(compile(src, "06_render_classes.py", "exec"), RND)


def load(name):
    m = load_obj(SNAP / name)
    P, fw = weld(m)
    area, normals, _, deg = tri_geometry(P, fw)
    return P, fw[~deg], normals[~deg]


PA, fA, nA = load(FILES[0])
PB, fB, nB = load(FILES[1])
centre = (PA.min(axis=0) + PA.max(axis=0)) / 2

P = np.vstack([PA, PB]) - centre
f = np.vstack([fA, fB + len(PA)])
n = np.vstack([nA, nB])
col = np.vstack([np.tile([200.0, 200.0, 205.0], (len(fA), 1)), np.tile([90.0, 190.0, 120.0], (len(fB), 1))])

# restrict the camera frame to file A's extent so both images line up
inA = np.zeros(len(P), bool)
inA[: len(PA)] = True
for tag, view in (("down", (0.001, 0.001, -1.0)), ("oblique", (0.45, 0.55, -0.70))):
    up_hint = (0, 1, 0) if tag == "down" else (0, 0, 1)
    RND["camera"].__defaults__ = (up_hint,)
    a_only, _ = RND["render"](P[inA], fA, nA, col[: len(fA)], view, cull=False)
    Image.fromarray(a_only).save(OUT / f"holes__{tag}_A_alone_double_sided.png")
    # same framing: render combined but with vertices of B kept; frame follows all points, so crop by padding A
    both, _ = RND["render"](P, f, n, col, view, cull=False)
    Image.fromarray(both).save(OUT / f"holes__{tag}_A_grey_plus_B_green.png")


def boundary_loops(Pw, fw):
    pairs = np.stack([fw[:, [0, 1]], fw[:, [1, 2]], fw[:, [2, 0]]], axis=1).reshape(-1, 2)
    key = np.sort(pairs, axis=1)
    uniq, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    open_e = uniq[cnt == 1]
    nbr = {}
    for a, b in open_e:
        nbr.setdefault(int(a), []).append(int(b))
        nbr.setdefault(int(b), []).append(int(a))
    simple = {v for v, ns in nbr.items() if len(ns) == 2}
    seen, loops = set(), []
    for start in simple:
        if start in seen:
            continue
        loop, prev, cur = [start], None, start
        ok = True
        while True:
            seen.add(cur)
            nxt = [x for x in nbr[cur] if x != prev]
            if not nxt:
                ok = False
                break
            prev, cur = cur, nxt[0]
            if cur == start:
                break
            if cur not in simple or cur in seen:
                ok = False
                break
            loop.append(cur)
        if ok and len(loop) >= 3:
            loops.append(loop)
    planar = []
    for loop in loops:
        pts = Pw[loop]
        c = pts.mean(axis=0)
        _, s, vt = np.linalg.svd(pts - c)
        off = np.abs((pts - c) @ vt[2]).max()
        if off <= 0.15:
            x, y = (pts - c) @ vt[0], (pts - c) @ vt[1]
            area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
            planar.append((len(loop), round(float(area), 1), np.round(vt[2], 2).tolist()))
    planar.sort(key=lambda r: -r[1])
    return len(open_e), len(loops), planar


res = {}
for name, (Pw, fw) in ((FILES[0], (PA, fA)), (FILES[1], (PB, fB))):
    n_open, n_loops, planar = boundary_loops(Pw, fw)
    res[name] = {"open_edges": n_open, "closed_simple_boundary_loops": n_loops,
                 "planar_loops_within_0.15in": len(planar),
                 "planar_loop_area_total_in2": round(sum(p[1] for p in planar), 1),
                 "largest_planar_loops_verts_area_normal": planar[:8]}
save("holes", res)
for k, v in res.items():
    print("==", k)
    for kk, vv in v.items():
        print("  ", kk, ":", vv)
