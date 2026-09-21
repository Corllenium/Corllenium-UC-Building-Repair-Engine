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


def find_t_vertices(positions_w: np.ndarray, table: EdgeTable, tol: float) -> dict[int, np.ndarray]:
    open_idx = np.nonzero(table.counts == 1)[0]
    if len(open_idx) == 0:
        return {}
    cand = np.unique(table.edges[open_idx])
    P = positions_w[cand]
    out = {}
    for e in open_idx:
        a, b = table.edges[e]
        A, ab = positions_w[a], positions_w[b] - positions_w[a]
        t = ((P - A) @ ab) / (ab @ ab)
        d = np.linalg.norm((P - A) - np.outer(t, ab), axis=1)
        hit = (t > 1e-9) & (t < 1 - 1e-9) & (d <= tol) & (cand != a) & (cand != b)
        if hit.any():
            out[int(e)] = cand[hit][np.argsort(t[hit])]
    return out
