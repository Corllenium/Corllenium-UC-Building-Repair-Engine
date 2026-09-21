from dataclasses import dataclass

import numpy as np

from engine.model import MeshData
from engine.topo.adjacency import EdgeTable, build_edge_table, degenerate_mask, find_t_vertices
from engine.topo.edges import (EDGE_NONMANIFOLD, EDGE_OPEN, EDGE_REAL, EDGE_REMOVABLE, EDGE_TJUNCTION,
                               classify_edges)
from engine.topo.planes import build_regions
from engine.topo.weld import axis_quanta, weld_exact

FLAT_TEXTURE_STD = 8.0


def flat_material_indices(mesh: MeshData, flatness: dict[str, float],
                          threshold: float = FLAT_TEXTURE_STD) -> frozenset[int]:
    """Indices into mesh.materials whose texture flatness is below threshold. A material
    absent from `flatness` (no texture, plain colour) counts as flat regardless of threshold."""
    out = []
    for i, name in enumerate(mesh.materials):
        std = flatness.get(name)
        if std is None or std < threshold:
            out.append(i)
    return frozenset(out)


@dataclass
class Topology:
    positions_w: np.ndarray
    face_w: np.ndarray
    ok: np.ndarray
    quanta: np.ndarray
    table: EdgeTable
    t_vertices: dict
    face_region: np.ndarray
    edge_class: np.ndarray


def analyse_topology(mesh: MeshData, flat_materials=frozenset()) -> Topology:
    for m in flat_materials:
        if not isinstance(m, (int, np.integer)) or isinstance(m, bool):
            raise TypeError(
                f"flat_materials must contain int indices into mesh.materials, got {m!r} "
                f"({type(m).__name__}); use flat_material_indices() to convert names first")
    positions_w, remap = weld_exact(mesh.positions, mesh.coord_decimals)
    face_w = remap[mesh.face_v]
    ok = ~degenerate_mask(positions_w, face_w)
    quanta = axis_quanta(positions_w, mesh.sig_digits)
    table = build_edge_table(face_w, ok)
    t_vertices = find_t_vertices(positions_w, table, tol=1.5 * float(quanta.max()), face_w=face_w, degenerate=~ok)
    face_region = build_regions(mesh, positions_w, face_w, ok, table, t_vertices, quanta, set(flat_materials))
    return Topology(positions_w, face_w, ok, quanta, table, t_vertices, face_region,
                    classify_edges(table, face_region, t_vertices))


def topology_stats(t: Topology) -> dict:
    c = t.edge_class
    return {
        "faces": int(len(t.face_w)), "zero_area_faces": int((~t.ok).sum()),
        "welded_vertices": int(len(t.positions_w)), "axis_quanta": t.quanta.tolist(),
        "regions": int(len(set(t.face_region[t.face_region >= 0].tolist()))),
        "edges": int(len(c)), "real_edges": int((c == EDGE_REAL).sum()),
        "removable_edges": int((c == EDGE_REMOVABLE).sum()), "open_edges": int((c == EDGE_OPEN).sum()),
        "nonmanifold_edges": int((c == EDGE_NONMANIFOLD).sum()), "t_junction_edges": int((c == EDGE_TJUNCTION).sum()),
        "edges_with_t_vertices": int(len(t.t_vertices)),
    }
