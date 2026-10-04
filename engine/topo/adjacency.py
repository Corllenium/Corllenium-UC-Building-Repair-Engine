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


def find_t_vertices_reference(positions_w: np.ndarray, table: EdgeTable, tol: float,
                              face_w: np.ndarray | None = None, degenerate: np.ndarray | None = None
                              ) -> dict[int, np.ndarray]:
    """Test oracle: the O(E * V) search over every edge and candidate vertex, kept verbatim.
    Do not modify."""
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


def find_t_vertices(positions_w: np.ndarray, table: EdgeTable, tol: float,
                    face_w: np.ndarray | None = None, degenerate: np.ndarray | None = None,
                    stats: dict | None = None,
                    *, chunk_pairs: int = 1_000_000) -> dict[int, np.ndarray]:
    n_edges = len(table.edges)
    if n_edges == 0:
        if stats is not None:
            stats["pairs_tested"] = 0
            stats["pairs_peak"] = 0
        return {}

    cand = np.unique(table.edges)
    if len(cand) == 0:
        if stats is not None:
            stats["pairs_tested"] = 0
            stats["pairs_peak"] = 0
        return {}
    V = len(cand)

    p_a = positions_w[table.edges[:, 0]]
    p_b = positions_w[table.edges[:, 1]]
    lens = np.linalg.norm(p_b - p_a, axis=1)
    pos_lens = lens[lens > 1e-9]
    typ_len = float(np.median(pos_lens)) if len(pos_lens) > 0 else 1.0
    cell_size = max(typ_len, tol, 1e-4)

    cand_pos = positions_w[cand]
    cand_cells = np.floor(cand_pos / cell_size).astype(np.int64)

    order = np.lexsort((cand_cells[:, 2], cand_cells[:, 1], cand_cells[:, 0]))
    sorted_cells = cand_cells[order]
    diff = np.any(sorted_cells[1:] != sorted_cells[:-1], axis=1)
    split_indices = np.flatnonzero(diff) + 1
    starts = np.r_[0, split_indices]
    ends = np.r_[split_indices, V]
    unique_cells = sorted_cells[starts]

    grid: dict[tuple[int, int, int], np.ndarray] = {}
    for cell, s, e in zip(unique_cells.tolist(), starts.tolist(), ends.tolist()):
        grid[(cell[0], cell[1], cell[2])] = order[s:e]

    min_p = np.minimum(p_a, p_b) - tol
    max_p = np.maximum(p_a, p_b) + tol
    c_min = np.floor(min_p / cell_size).astype(np.int64)
    c_max = np.floor(max_p / cell_size).astype(np.int64)
    c_min0, c_min1, c_min2 = c_min[:, 0], c_min[:, 1], c_min[:, 2]
    c_max0, c_max1, c_max2 = c_max[:, 0], c_max[:, 1], c_max[:, 2]

    buf_size = min(chunk_pairs, 65536)
    buf_e = np.empty(buf_size, dtype=np.int64)
    buf_v = np.empty(buf_size, dtype=np.int64)
    buf_pos = 0

    hits: dict[int, set[int]] = {}
    pairs_tested = 0
    pairs_peak = 0

    def eval_chunk(count: int) -> None:
        nonlocal pairs_tested, pairs_peak
        if count == 0:
            return
        pairs_tested += count
        if count > pairs_peak:
            pairs_peak = count

        sub_e = buf_e[:count]
        sub_v = buf_v[:count]

        sub_ea = table.edges[sub_e, 0]
        sub_eb = table.edges[sub_e, 1]
        sub_cv = cand[sub_v]

        cand_mask = (sub_cv != sub_ea) & (sub_cv != sub_eb)
        if not cand_mask.any():
            return

        cand_idx = np.flatnonzero(cand_mask)
        m_e = sub_e[cand_idx]
        m_ea = sub_ea[cand_idx]
        m_eb = sub_eb[cand_idx]
        m_cv = sub_cv[cand_idx]
        m_v = sub_v[cand_idx]

        A = positions_w[m_ea]
        B = positions_w[m_eb]
        ab = B - A
        denom = np.sum(ab * ab, axis=1)
        safe_denom = np.where(denom == 0, 1.0, denom)

        PA = cand_pos[m_v] - A
        t = np.sum(PA * ab, axis=1) / safe_denom
        t_mask = (t > 1e-9) & (t < 1.0 - 1e-9)
        if not t_mask.any():
            return

        t_idx = np.flatnonzero(t_mask)
        t_sel = t[t_idx]
        PA_sel = PA[t_idx]
        ab_sel = ab[t_idx]

        diff = PA_sel - t_sel[:, None] * ab_sel
        d = np.linalg.norm(diff, axis=1)

        d_mask = d <= tol
        if d_mask.any():
            final_idx = t_idx[d_mask]
            hit_e = m_e[final_idx]
            hit_v = m_cv[final_idx]
            for e_val, v_val in zip(hit_e.tolist(), hit_v.tolist()):
                if e_val in hits:
                    hits[e_val].add(v_val)
                else:
                    hits[e_val] = {v_val}

    for e_idx, (x0, y0, z0, x1, y1, z1) in enumerate(zip(c_min0, c_min1, c_min2, c_max0, c_max1, c_max2)):
        x0, y0, z0, x1, y1, z1 = int(x0), int(y0), int(z0), int(x1), int(y1), int(z1)
        if x0 == x1 and y0 == y1 and z0 == z1:
            vs = grid.get((x0, y0, z0))
            if vs is None:
                continue
            e_cands = vs
            k = len(vs)
        else:
            cell_lists = []
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    for z in range(z0, z1 + 1):
                        vs = grid.get((x, y, z))
                        if vs is not None:
                            cell_lists.append(vs)
            if not cell_lists:
                continue
            e_cands = cell_lists[0] if len(cell_lists) == 1 else np.concatenate(cell_lists)
            k = len(e_cands)

        if buf_pos + k > len(buf_e):
            if buf_pos + k <= chunk_pairs:
                new_size = min(chunk_pairs, max(buf_pos + k, len(buf_e) * 2))
                buf_e.resize(new_size, refcheck=False)
                buf_v.resize(new_size, refcheck=False)
            else:
                if buf_pos > 0:
                    eval_chunk(buf_pos)
                    buf_pos = 0

                if k > chunk_pairs:
                    if len(buf_e) < chunk_pairs:
                        buf_e.resize(chunk_pairs, refcheck=False)
                        buf_v.resize(chunk_pairs, refcheck=False)
                    for off in range(0, k, chunk_pairs):
                        chunk_slice = e_cands[off : off + chunk_pairs]
                        sk = len(chunk_slice)
                        buf_e[:sk] = e_idx
                        buf_v[:sk] = chunk_slice
                        eval_chunk(sk)
                    continue

        buf_e[buf_pos : buf_pos + k] = e_idx
        buf_v[buf_pos : buf_pos + k] = e_cands
        buf_pos += k

    if buf_pos > 0:
        eval_chunk(buf_pos)
        buf_pos = 0

    if stats is not None:
        stats["pairs_tested"] = int(pairs_tested)
        stats["pairs_peak"] = int(pairs_peak)

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
