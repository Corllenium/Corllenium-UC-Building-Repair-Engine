"""Audit of the edges SketchUp would draw: every edge of the polygon OBJ (.fixed.ngon.obj), classed by
how many polygons share it and the angle between them. An edge between two COPLANAR polygons of the
SAME material is a line inside a slab (what the owner does not want); coplanar + different material
is a material border; > 5 degrees is a real shape edge; one polygon only is an open border."""
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

path = Path(sys.argv[1])
V, faces, mats = [], [], []
cur = None
for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
    if line.startswith("v "):
        V.append([float(t) for t in line.split()[1:4]])
    elif line.startswith("usemtl"):
        cur = line.split(maxsplit=1)[1].strip()
    elif line.startswith("f "):
        faces.append([int(t.split("/")[0]) - 1 for t in line.split()[1:]])
        mats.append(cur)
V = np.array(V)
# weld by exact position so edges shared through duplicated vertices are found
_, wid = np.unique(V, axis=0, return_inverse=True)
wid = wid.ravel()


def newell(poly):
    p = V[poly]
    q = np.roll(p, -1, axis=0)
    n = np.array([np.sum((p[:, 1] - q[:, 1]) * (p[:, 2] + q[:, 2])),
                  np.sum((p[:, 2] - q[:, 2]) * (p[:, 0] + q[:, 0])),
                  np.sum((p[:, 0] - q[:, 0]) * (p[:, 1] + q[:, 1]))])
    ln = np.linalg.norm(n)
    return n / ln if ln > 0 else n


normals = [newell(f) for f in faces]
edges = defaultdict(list)
for fi, f in enumerate(faces):
    for a, b in zip(f, f[1:] + f[:1]):
        key = tuple(sorted((int(wid[a]), int(wid[b]))))
        edges[key].append(fi)

rep = {w: i for i, w in enumerate(wid)}  # any vertex per welded id
cls = defaultdict(lambda: [0, 0.0])
examples = defaultdict(list)
for (a, b), fs in edges.items():
    length = float(np.linalg.norm(V[rep[a]] - V[rep[b]]))
    if len(fs) == 1:
        k = "open (1 polygon)"
    elif len(fs) > 2:
        k = "non-manifold (3+ polygons)"
    else:
        f0, f1 = fs
        ang = np.degrees(np.arccos(np.clip(abs(normals[f0] @ normals[f1]), -1, 1)))
        same = mats[f0] == mats[f1]
        if ang < 1.0:
            k = "coplanar SAME material (line inside a slab)" if same else "coplanar, material border"
        elif ang <= 5.0:
            k = "soft crease 1-5 deg"
        else:
            k = "shape edge > 5 deg"
        if ang < 1.0 and same:
            examples[k].append((length, V[rep[a]].round(1).tolist(), V[rep[b]].round(1).tolist(), f0, f1))
    cls[k][0] += 1
    cls[k][1] += length

print(f"{path.name}: {len(faces)} polygons, {len(edges)} edges")
for k, (n, L) in sorted(cls.items()):
    print(f"  {k:48s} {n:6d} edges  {L / 12:9.1f} ft")
ex = sorted(examples["coplanar SAME material (line inside a slab)"], reverse=True)[:8]
if ex:
    print("  longest lines inside a slab:")
    for L, pa, pb, f0, f1 in ex:
        print(f"    {L:7.1f} in  {pa} -> {pb}  polygons {f0} ({len(faces[f0])} v) / {f1} ({len(faces[f1])} v)")
