from dataclasses import dataclass

import numpy as np


@dataclass
class EdgeTable:
    edges: np.ndarray
    counts: np.ndarray
    face_edges: np.ndarray


def degenerate_mask(positions_w: np.ndarray, face_w: np.ndarray) -> np.ndarray:
    p = positions_w[face_w]
    area = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    longest = np.linalg.norm(p - np.roll(p, -1, axis=1), axis=2).max(axis=1)
    return area <= 1e-7 * np.maximum(longest, 1e-300) ** 2


def build_edge_table(face_w: np.ndarray, include: np.ndarray) -> EdgeTable:
    pairs = np.sort(np.stack([face_w[:, [0, 1]], face_w[:, [1, 2]], face_w[:, [2, 0]]], axis=1), axis=2)
    edges, inverse, counts = np.unique(pairs[include].reshape(-1, 2), axis=0, return_inverse=True, return_counts=True)
    face_edges = np.full((face_w.shape[0], 3), -1, np.int64)
    face_edges[include] = inverse.reshape(-1, 3)
    return EdgeTable(edges.astype(np.int64), counts.astype(np.int64), face_edges)


def edge_face_lists(table: EdgeTable) -> list[np.ndarray]:
    fe = table.face_edges.reshape(-1)
    faces = np.repeat(np.arange(table.face_edges.shape[0]), 3)
    keep = fe >= 0
    fe, faces = fe[keep], faces[keep]
    order = np.argsort(fe, kind="stable")
    splits = np.cumsum(np.bincount(fe, minlength=len(table.edges)))[:-1]
    return np.split(faces[order], splits)


def _t_vertex_hints(positions_w: np.ndarray, table: EdgeTable, face_w: np.ndarray,
                    degenerate: np.ndarray, tol: float) -> dict[int, set[int]]:
    """Zero-area faces are the stitching an exporter (e.g. SketchUp) leaves across a
    T-junction: for each one with three DISTINCT vertex ids, the vertex whose parameter lies
    strictly between the other two on their common line is a T-vertex hint for the edge those
    other two form, if that edge exists in `table`. A face with a repeated vertex id (fully
    collapsed, not a genuine collinear stitch) yields no hint."""
    lookup = {(int(a), int(b)): i for i, (a, b) in enumerate(table.edges)}
    hints: dict[int, set[int]] = {}
    for face in face_w[degenerate]:
        ids = [int(v) for v in face]
        if len(set(ids)) != 3:
            continue
        pos = positions_w[ids]
        for mid in range(3):
            o1, o2 = (mid + 1) % 3, (mid + 2) % 3
            ab = pos[o2] - pos[o1]
            denom = float(ab @ ab)
            if denom == 0.0:
                continue
            t = float((pos[mid] - pos[o1]) @ ab) / denom
            if not (1e-9 < t < 1 - 1e-9):
                continue
            d = float(np.linalg.norm((pos[mid] - pos[o1]) - t * ab))
            if d > tol:
                continue
            p, q = ids[o1], ids[o2]
            e = lookup.get((min(p, q), max(p, q)))
            if e is not None:
                hints.setdefault(e, set()).add(ids[mid])
            break
    return hints


def find_t_vertices(positions_w: np.ndarray, table: EdgeTable, tol: float,
                    face_w: np.ndarray | None = None, degenerate: np.ndarray | None = None
                    ) -> dict[int, np.ndarray]:
    """Geometric search runs on every edge in the table (count >= 1); candidates are all welded
    vertices referenced by faces included in the table. When `face_w`/`degenerate` are given,
    zero-area faces contribute additional hints (see `_t_vertex_hints`), merged and de-duplicated
    with the geometric hits, ordered from `edges[e][0]` to `edges[e][1]`."""
    n_edges = len(table.edges)
    if n_edges == 0:
        return {}
    cand = np.unique(table.edges)
    P = positions_w[cand]
    hits: dict[int, set[int]] = {}
    for e in range(n_edges):
        a, b = table.edges[e]
        A, ab = positions_w[a], positions_w[b] - positions_w[a]
        t = ((P - A) @ ab) / (ab @ ab)
        d = np.linalg.norm((P - A) - np.outer(t, ab), axis=1)
        hit = (t > 1e-9) & (t < 1 - 1e-9) & (d <= tol) & (cand != a) & (cand != b)
        if hit.any():
            hits[e] = {int(v) for v in cand[hit]}

    if face_w is not None and degenerate is not None and degenerate.any():
        for e, verts in _t_vertex_hints(positions_w, table, face_w, degenerate, tol).items():
            hits.setdefault(e, set()).update(verts)

    out = {}
    for e, verts in hits.items():
        a, b = table.edges[e]
        remaining = verts - {int(a), int(b)}
        if not remaining:
            continue
        ids = np.array(sorted(remaining), dtype=np.int64)
        A, ab = positions_w[a], positions_w[b] - positions_w[a]
        t = ((positions_w[ids] - A) @ ab) / (ab @ ab)
        out[e] = ids[np.argsort(t)]
    return out


def t_junction_sub_edges(table: EdgeTable, t_vertices: dict[int, np.ndarray]) -> dict[int, list[int | None]]:
    """For each open edge `e` in `t_vertices`, resolve the chain
    `edges[e][0] -> t-vertices in order -> edges[e][1]` to the edge-table indices of its
    consecutive sub-edges, with None where a vertex pair along the chain is not an edge
    in `table`."""
    lookup = {(int(a), int(b)): i for i, (a, b) in enumerate(table.edges)}
    out: dict[int, list[int | None]] = {}
    for e, verts in t_vertices.items():
        a, b = table.edges[e]
        chain = [int(a), *[int(v) for v in verts], int(b)]
        out[e] = [lookup.get((min(p, q), max(p, q))) for p, q in zip(chain, chain[1:])]
    return out
