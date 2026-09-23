from dataclasses import dataclass

import numpy as np

from engine.model import MeshData
from engine.topo.adjacency import EdgeTable, build_edge_table, degenerate_mask, find_t_vertices
from engine.topo.edges import (COPLANAR_ANGLE, EDGE_NONMANIFOLD, EDGE_OPEN, EDGE_REAL, EDGE_REMOVABLE,
                               EDGE_SOFT, EDGE_TJUNCTION, SOFT_ANGLE, classify_edges,
                               region_border_angles)
from engine.topo.planes import build_regions, face_normals
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
    #: The two dihedral thresholds `edge_class` was decided with, in degrees, kept so that
    #: `topology_stats` reports `coplanar_region_borders` against the SAME threshold the classes
    #: were built with rather than against the module default.
    coplanar_angle: float = COPLANAR_ANGLE
    soft_angle: float = SOFT_ANGLE


def analyse_topology(mesh: MeshData, flat_materials=frozenset(), *,
                     coplanar_angle: float = COPLANAR_ANGLE,
                     soft_angle: float = SOFT_ANGLE) -> Topology:
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
    normals = face_normals(positions_w, face_w, ok)
    edge_class = classify_edges(table, face_region, t_vertices, normals, mesh.face_material,
                                coplanar_angle=coplanar_angle, soft_angle=soft_angle)
    return Topology(positions_w, face_w, ok, quanta, table, t_vertices, face_region, edge_class,
                    coplanar_angle=coplanar_angle, soft_angle=soft_angle)


def coplanar_region_borders(t: Topology) -> int:
    """How many edges sit between two DIFFERENT real regions while being flat to within
    `t.coplanar_angle` -- a line drawn through what is geometrically one surface.

    A pure diagnostic (no edge class depends on it): before the iterative plane refit this
    counted the seed-plane splits that made the viewer draw borders inside a flat slab, and it
    is meant to read about 0 now. Material is deliberately NOT part of the test: a coplanar
    border between two MATERIALS is a real edge that must stay, and it is counted here too, so
    a non-zero reading is a prompt to look, not proof of a defect."""
    angles = region_border_angles(t.table, t.face_region, face_normals(t.positions_w, t.face_w, t.ok))
    return int(sum(1 for a in angles.values() if a <= t.coplanar_angle))


def topology_stats(t: Topology) -> dict:
    c = t.edge_class
    return {
        "faces": int(len(t.face_w)), "zero_area_faces": int((~t.ok).sum()),
        "welded_vertices": int(len(t.positions_w)), "axis_quanta": t.quanta.tolist(),
        "regions": int(len(set(t.face_region[t.face_region >= 0].tolist()))),
        "edges": int(len(c)), "real_edges": int((c == EDGE_REAL).sum()),
        "removable_edges": int((c == EDGE_REMOVABLE).sum()), "open_edges": int((c == EDGE_OPEN).sum()),
        "nonmanifold_edges": int((c == EDGE_NONMANIFOLD).sum()), "t_junction_edges": int((c == EDGE_TJUNCTION).sum()),
        "soft_edges": int((c == EDGE_SOFT).sum()),
        "coplanar_region_borders": coplanar_region_borders(t),
        "edges_with_t_vertices": int(len(t.t_vertices)),
    }
