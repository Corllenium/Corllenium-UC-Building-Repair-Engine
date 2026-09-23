import numpy as np

from engine.topo.adjacency import EdgeTable, edge_face_lists, t_junction_sub_edges

EDGE_REAL, EDGE_REMOVABLE, EDGE_OPEN, EDGE_NONMANIFOLD, EDGE_TJUNCTION, EDGE_SOFT = 0, 1, 2, 3, 4, 5

#: At or below this dihedral angle (degrees) two faces are flat to within what the export could
#: even print, so a border between two REGIONS there is a defect, not a crease -- counted as
#: `coplanar_region_borders` in `engine.pipeline.topology_stats`.
COPLANAR_ANGLE = 1.0
#: At or below this dihedral angle (degrees, and above `COPLANAR_ANGLE`) a crease between two
#: same-material regions is SOFT: a real fold, but one so shallow the two sides cannot be merged
#: into a single face without MOVING vertices, which this engine never does. 5 degrees is the
#: project's historic limited-dissolve ceiling.
SOFT_ANGLE = 5.0


def dihedral_degrees(n0: np.ndarray, n1: np.ndarray) -> float:
    """Angle between two unit face normals, in degrees. Two faces continuing one flat surface
    give 0; two wound against each other give 180, which is never soft or coplanar."""
    return float(np.degrees(np.arccos(np.clip(float(np.asarray(n0) @ np.asarray(n1)), -1.0, 1.0))))


def region_border_angles(table: EdgeTable, face_region: np.ndarray, normals: np.ndarray
                         ) -> dict[int, float]:
    """`{edge index: dihedral angle in degrees}` for every edge with exactly two faces that sit
    in two DIFFERENT real regions (both `>= 0`). An edge touching a face in no region at all
    (`-1`: copied through, degenerate) is not a border BETWEEN regions and is left out."""
    ef = edge_face_lists(table)
    out: dict[int, float] = {}
    for e in np.nonzero(table.counts == 2)[0]:
        f0, f1 = ef[e]
        r0, r1 = int(face_region[f0]), int(face_region[f1])
        if r0 >= 0 and r1 >= 0 and r0 != r1:
            out[int(e)] = dihedral_degrees(normals[f0], normals[f1])
    return out


def classify_edges(table: EdgeTable, face_region: np.ndarray, t_vertices: dict,
                   normals: np.ndarray | None = None, material: np.ndarray | None = None, *,
                   coplanar_angle: float = COPLANAR_ANGLE,
                   soft_angle: float = SOFT_ANGLE) -> np.ndarray:
    """Per-edge class. `normals` (unit, per face) and `material` are what EDGE_SOFT needs; with
    either missing no edge is ever classed soft and the result is exactly what it always was."""
    cls = np.full(len(table.edges), EDGE_REAL, np.uint8)
    cls[table.counts == 1] = EDGE_OPEN
    cls[table.counts >= 3] = EDGE_NONMANIFOLD
    ef = edge_face_lists(table)
    soft_ready = normals is not None and material is not None
    for e in np.nonzero(table.counts == 2)[0]:
        f0, f1 = ef[e]
        if face_region[f0] >= 0 and face_region[f0] == face_region[f1]:
            cls[e] = EDGE_REMOVABLE
        elif (soft_ready and material[f0] == material[f1]
                and face_region[f0] >= 0 and face_region[f1] >= 0):
            # Two REAL regions, one material: a shallow fold between them is a SOFT crease -- the
            # viewer draws it faintly, the merge cannot dissolve it without moving vertices.
            # At or below `coplanar_angle` it is not a fold at all but a split that should not
            # exist (`region_border_angles` counts those); it stays EDGE_REAL either way.
            #
            # BOTH regions must be `>= 0`, exactly as in `region_border_angles`: a face in no
            # region (-1: copied through, degenerate) is not one side of a border BETWEEN
            # regions, so an edge with such a face on it is never a region crease. Without this
            # the branch also fired for two faces that BOTH sit outside every region, calling a
            # fold that no merge will ever look at a "crease the merge could not dissolve".
            if coplanar_angle < dihedral_degrees(normals[f0], normals[f1]) <= soft_angle:
                cls[e] = EDGE_SOFT
    sub_edges = t_junction_sub_edges(table, t_vertices)
    for e, subs in sub_edges.items():
        faces = list(ef[e]) + [f for s in subs if s is not None for f in ef[s]]
        regions = {int(face_region[f]) for f in faces}
        whole = all(s is not None for s in subs) and len(regions) == 1 and -1 not in regions
        if whole:
            # `whole` needs every face in ONE region, which a soft edge never is, so this cannot
            # overwrite an EDGE_SOFT verdict.
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
