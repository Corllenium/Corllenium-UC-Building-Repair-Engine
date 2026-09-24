"""Read-only audit of a written .skp: which edges does SketchUp DRAW (not soft), and why.

A visible edge between two coplanar faces of the same material is a line inside a slab -- the
thing the owner does not want. Coplanar + different material is a material border (real).
Angle > 5 degrees is a shape edge (real). One face only is an open border; 3+ is non-manifold."""
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from engine.io.skp_writer import read_skp

path = Path(sys.argv[1])
model = read_skp(path, uvs=False, triangles=False)


def key(p, q):
    a = tuple(np.round(p, 4))
    b = tuple(np.round(q, 4))
    return (a, b) if a <= b else (b, a)


edge_faces = defaultdict(list)
for fi, f in enumerate(model.faces):
    for loop in [f.outer, *f.inners]:
        for i in range(len(loop)):
            edge_faces[key(loop[i], loop[(i + 1) % len(loop)])].append(fi)

cls = defaultdict(lambda: [0, 0.0])
worst = []
unmatched = 0
for e in model.edges:
    L = float(np.linalg.norm(e.end - e.start))
    if e.soft:
        cls["hidden (soft)"][0] += 1
        cls["hidden (soft)"][1] += L
        continue
    fs = edge_faces.get(key(e.start, e.end), [])
    if not fs:
        unmatched += 1
        k = "visible, no face found (unmatched)"
    elif len(fs) == 1:
        k = "visible, open border (1 face)"
    elif len(fs) > 2:
        k = "visible, non-manifold (3+ faces)"
    else:
        f0, f1 = (model.faces[i] for i in fs)
        ang = np.degrees(np.arccos(np.clip(abs(float(f0.normal @ f1.normal)), 0.0, 1.0)))
        m0 = f0.front_material
        m1 = f1.front_material
        if ang < 1.0 and m0 == m1:
            k = "VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)"
            worst.append((L, np.round(e.start, 1).tolist(), np.round(e.end, 1).tolist()))
        elif ang < 1.0:
            k = "visible, material border (coplanar)"
        elif ang <= 5.0:
            k = "visible, crease 1-5 deg"
        else:
            k = "visible, shape edge > 5 deg"
    cls[k][0] += 1
    cls[k][1] += L

print(f"{path.name}: {len(model.faces)} faces, {len(model.edges)} edges")
for k, (n, L) in sorted(cls.items()):
    print(f"  {k:62s} {n:5d}  {L / 12:8.1f} ft")
for L, a, b in sorted(worst, reverse=True)[:6]:
    print(f"    line inside a surface: {L:7.1f} in  {a} -> {b}")


# ---- refine visible OPEN edges: does the edge lie on another face (a T-junction line)? ----
def plane(f):
    n = f.normal / np.linalg.norm(f.normal)
    return n, float(n @ f.outer[0])


def basis(n):
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(n, a); u /= np.linalg.norm(u)
    return u, np.cross(n, u)


def inside(pt2, poly2, tol):
    # point in polygon (even-odd) OR within tol of its boundary
    x, y = pt2
    c = False
    n = len(poly2)
    for i in range(n):
        (x1, y1), (x2, y2) = poly2[i], poly2[(i + 1) % n]
        d = np.array([x2 - x1, y2 - y1]); L2 = d @ d
        t = 0.0 if L2 == 0 else np.clip(((x - x1) * d[0] + (y - y1) * d[1]) / L2, 0, 1)
        if np.hypot(x - (x1 + t * d[0]), y - (y1 + t * d[1])) <= tol:
            return True
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


planes = [plane(f) for f in model.faces]
bases = [basis(p[0]) for p in planes]
sub = defaultdict(lambda: [0, 0.0])
tj = []
for e in model.edges:
    if e.soft:
        continue
    fs = edge_faces.get(key(e.start, e.end), [])
    if len(fs) != 1:
        continue
    own = fs[0]
    L = float(np.linalg.norm(e.end - e.start))
    mid = 0.5 * (e.start + e.end)
    hit = None
    for gi, g in enumerate(model.faces):
        if gi == own:
            continue
        n, d = planes[gi]
        if abs(n @ e.start - d) > 0.02 or abs(n @ e.end - d) > 0.02:
            continue
        u, v = bases[gi]
        p2 = np.array([mid @ u, mid @ v])
        if inside(p2, [(q @ u, q @ v) for q in g.outer], 0.02) and not any(
                inside(p2, [(q @ u, q @ v) for q in inner], -1.0) for inner in g.inners):
            coplanar = abs(float(planes[own][0] @ n)) > np.cos(np.radians(1.0))
            hit = "coplanar" if coplanar else "angled"
            break
    k = {None: "open edge = real border of the model",
         "coplanar": "open edge lying ON a coplanar face (T-junction line inside a surface)",
         "angled": "open edge lying on an angled face (face meets a surface it does not split)"}[hit]
    sub[k][0] += 1
    sub[k][1] += L
    if hit == "coplanar":
        tj.append((L, np.round(e.start, 1).tolist(), np.round(e.end, 1).tolist()))
print("  visible open edges split:")
for k, (n, L) in sorted(sub.items()):
    print(f"    {k:72s} {n:5d}  {L / 12:8.1f} ft")
for L, a, b in sorted(tj, reverse=True)[:5]:
    print(f"      T-junction line: {L:7.1f} in  {a} -> {b}")
