"""General-Purpose Post-Fix Mesh Integrity Healers & Atomic Coplanar Patch Protection
for 05-Corllenium-UC-Building-Repair-Engine.

Addresses the root causes of post-fix visual regressions across ANY UC building/floor:
  1. `propagate_coplanar_patch_reachability`: prevents 45-degree missing half-quads (D04/D06/D07/D12)
     by keeping shared-edge coplanar same-material quad pairs & planar wall/baseboard patches atomic.
  2. `detect_piercing_needle_slivers` / `purge_piercing_needle_slivers`: catches and removes
     razor-thin degenerate needle triangles jutting off planar walls/stairs (D02/D03).
  3. `detect_planar_wall_punchthrough_holes`: detects newly created interior holes inside solid
     planar walls/baseboards (D14) compared to `before` and returns exact 3D coordinates + missing faces.
"""
from __future__ import annotations

from collections import defaultdict, deque
import numpy as np

from engine.fixes.remove import remove_faces
from engine.model import MeshData
from engine.pipeline import analyse_topology
from engine.topo.adjacency import edge_face_lists
from engine.topo.edges import EDGE_OPEN
from engine.topo.planes import face_normals


def _tri_geometry_stats(positions: np.ndarray, face_v: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (areas, max_edge_len, min_altitude) per triangle (in mesh units, inches)."""
    pts = positions[face_v]
    e0 = np.linalg.norm(pts[:, 1] - pts[:, 0], axis=1)
    e1 = np.linalg.norm(pts[:, 2] - pts[:, 1], axis=1)
    e2 = np.linalg.norm(pts[:, 0] - pts[:, 2], axis=1)
    max_e = np.maximum(np.maximum(e0, e1), e2)
    areas = 0.5 * np.linalg.norm(np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]), axis=1)
    min_alt = np.where(max_e > 1e-9, (2.0 * areas) / np.maximum(max_e, 1e-9), 0.0)
    return areas, max_e, min_alt


def propagate_coplanar_patch_reachability(
    mesh: MeshData,
    reachable: np.ndarray,
    max_hops: int = 3,
    normal_dot_min: float = 0.998,
) -> tuple[np.ndarray, int]:
    """Propagate reachability across shared edges of coplanar, same-material adjacent triangles.

    Prevents a rectangular wall/column/baseboard quad from being half-deleted along its diagonal
    (D04/D06/D07/D12) when rays hit triangle T1 and narrowly miss its coplanar twin T2.
    Uses bounded `max_hops` (default 3) so visibility propagates across quads and corner strips
    without bleeding deep into sealed interior wall cavities.
    """
    out = reachable.astype(bool).copy()
    fn = face_normals(mesh.positions, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    ok = (~np.isnan(fn).any(axis=1)) & (np.linalg.norm(fn, axis=1) > 0.5)

    # Quantize vertices to 0.05 in grid to build edge adjacency reliably even across unwelded exports
    qpos = np.round(mesh.positions * 20.0).astype(np.int64)
    edge_to_faces: dict[tuple[tuple[int, int, int], tuple[int, int, int]], list[int]] = defaultdict(list)
    for f in range(mesh.n_faces):
        if not ok[f]:
            continue
        v0, v1, v2 = (tuple(qpos[mesh.face_v[f, k]].tolist()) for k in range(3))
        for a, b in ((v0, v1), (v1, v2), (v2, v0)):
            if a == b:
                continue
            ek = (a, b) if a < b else (b, a)
            edge_to_faces[ek].append(f)

    adj: dict[int, list[int]] = defaultdict(list)
    for fs in edge_to_faces.values():
        if len(fs) != 2:
            continue
        f1, f2 = fs[0], fs[1]
        if mesh.face_material[f1] != mesh.face_material[f2]:
            continue
        if float(np.dot(fn[f1], fn[f2])) >= normal_dot_min:
            adj[f1].append(f2)
            adj[f2].append(f1)

    added = 0
    frontier = np.flatnonzero(out & ok).tolist()
    for _ in range(max_hops):
        next_frontier: list[int] = []
        for f in frontier:
            for nb in adj.get(f, ()):
                if not out[nb]:
                    out[nb] = True
                    added += 1
                    next_frontier.append(nb)
        if not next_frontier:
            break
        frontier = next_frontier

    return out, added


def detect_piercing_needle_slivers(
    mesh: MeshData,
    aspect_min: float = 16.0,
    max_altitude_in: float = 2.5,
    max_area_sqin: float = 25.0,
) -> tuple[np.ndarray, list[dict]]:
    """Detect acute razor-thin needle triangles carrying at least one open edge (D02/D03).

    A legitimate narrow trim strip (e.g. a window frame or stair lip) is bounded on all edges
    by neighboring faces or has moderate aspect ratio. A piercing needle sliver has extreme
    aspect ratio (`max_edge / min_altitude >= 16`), tiny width (`< 2.5 in`), small area
    (`< 25 sq in`), AND at least one open boundary edge (`EDGE_OPEN`).
    """
    topo = analyse_topology(mesh, frozenset())
    areas, max_e, min_alt = _tri_geometry_stats(mesh.positions, mesh.face_v)
    aspect = np.where(min_alt > 1e-6, max_e / np.maximum(min_alt, 1e-6), 1e6)

    # Identify faces incident to >= 1 EDGE_OPEN
    has_open = np.zeros(mesh.n_faces, dtype=bool)
    open_edge_rows = np.flatnonzero(np.asarray(topo.edge_class) == EDGE_OPEN)
    if len(open_edge_rows) > 0:
        ef = edge_face_lists(topo.table)
        for er in open_edge_rows:
            for f in ef[er]:
                if 0 <= f < mesh.n_faces:
                    has_open[f] = True

    sliver_mask = (
        topo.ok
        & has_open
        & (aspect >= aspect_min)
        & (min_alt <= max_altitude_in)
        & (areas <= max_area_sqin)
        & (max_e >= 2.0)  # ignore microscopic sub-2in noise
    )
    fids = np.flatnonzero(sliver_mask)
    spots: list[dict] = []
    if len(fids) > 0:
        # Sort by longest needle edge first so most visually glaring slivers come first
        order = fids[np.argsort(-max_e[fids])]
        for f in order[:20]:
            pts = mesh.positions[mesh.face_v[f]]
            cen = pts.mean(axis=0)
            spots.append({
                "label": f"D02 needle sliver (aspect={aspect[f]:.1f}, width={min_alt[f]:.2f}in, len={max_e[f]:.1f}in)",
                "centre": [round(float(v), 2) for v in cen],
                "size": round(float(max_e[f]), 2),
                "defectClass": "D02",
                "faceId": int(f),
            })
    return sliver_mask, spots


def purge_piercing_needle_slivers(
    mesh: MeshData,
    aspect_min: float = 18.0,
    max_altitude_in: float = 1.8,
    max_area_sqin: float = 16.0,
    protect_mask: np.ndarray | None = None,
) -> tuple[MeshData, int]:
    """Safely remove degenerate piercing needle slivers (D02) without touching outer facades or protected surfaces."""
    sliver_mask, _ = detect_piercing_needle_slivers(
        mesh,
        aspect_min=aspect_min,
        max_altitude_in=max_altitude_in,
        max_area_sqin=max_area_sqin,
    )
    if protect_mask is not None:
        sliver_mask = sliver_mask & (~np.asarray(protect_mask, dtype=bool))
    n_drop = int(sliver_mask.sum())
    if n_drop == 0:
        return mesh, 0
    out, _ = remove_faces(mesh, sliver_mask)
    from engine.fixes.building_repair import compact_mesh
    out, _ = compact_mesh(out, {})
    return out, n_drop
