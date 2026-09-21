import numpy as np

from engine.topo.adjacency import EdgeTable, edge_face_lists

EDGE_REAL, EDGE_REMOVABLE, EDGE_OPEN, EDGE_NONMANIFOLD, EDGE_TJUNCTION = 0, 1, 2, 3, 4


def classify_edges(table: EdgeTable, face_region: np.ndarray, t_vertices: dict) -> np.ndarray:
    cls = np.full(len(table.edges), EDGE_REAL, np.uint8)
    cls[table.counts == 1] = EDGE_OPEN
    cls[table.counts >= 3] = EDGE_NONMANIFOLD
    ef = edge_face_lists(table)
    for e in np.nonzero(table.counts == 2)[0]:
        f0, f1 = ef[e]
        if face_region[f0] >= 0 and face_region[f0] == face_region[f1]:
            cls[e] = EDGE_REMOVABLE
    lookup = {(int(a), int(b)): i for i, (a, b) in enumerate(table.edges)}
    for e, verts in t_vertices.items():
        a, b = table.edges[e]
        chain = [int(a), *[int(v) for v in verts], int(b)]
        subs = [lookup.get((min(p, q), max(p, q))) for p, q in zip(chain, chain[1:])]
        faces = list(ef[e]) + [f for s in subs if s is not None for f in ef[s]]
        regions = {int(face_region[f]) for f in faces}
        whole = all(s is not None for s in subs) and len(regions) == 1 and -1 not in regions
        kind = EDGE_REMOVABLE if whole else EDGE_TJUNCTION
        cls[e] = kind
        for s in subs:
            if s is not None and table.counts[s] == 1:
                cls[s] = kind
    return cls
