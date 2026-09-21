import numpy as np

from engine.topo.adjacency import EdgeTable, edge_face_lists, t_junction_sub_edges

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
    sub_edges = t_junction_sub_edges(table, t_vertices)
    for e, subs in sub_edges.items():
        faces = list(ef[e]) + [f for s in subs if s is not None for f in ef[s]]
        regions = {int(face_region[f]) for f in faces}
        whole = all(s is not None for s in subs) and len(regions) == 1 and -1 not in regions
        if whole:
            cls[e] = EDGE_REMOVABLE
            for s in subs:
                if s is not None and table.counts[s] == 1:
                    cls[s] = EDGE_REMOVABLE
        elif table.counts[e] == 1:
            # Only a genuinely open edge becomes a T-junction marker. An edge with counts >= 2
            # already has a real connection (or was promoted to removable above); a T-vertex
            # incidentally lying on it must not downgrade/override that count-based class.
            cls[e] = EDGE_TJUNCTION
            for s in subs:
                if s is not None and table.counts[s] == 1:
                    cls[s] = EDGE_TJUNCTION
    return cls
