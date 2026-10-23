"""E4, the checked coplanar merge (MAIN-INFRA-E4-MERGE-20261023).

Fresh Minecraft floor exports cut every flat wall, glass panel and floor into coplanar slivers with T-junctions,
which render as diagonal slits (the Validator's `cracks`) and stray internal lines. The owner asked (in chat,
2026-10-23, for the fresh MAIN INFRA floors, as a separate guarded pass after E3) for one clean surface per coplanar
material region with no internal lines, without moving or inventing a vertex and without bridging a real opening.

`E4Merge.plan` analyses the stage input's topology with the legacy profile's flat materials and dihedral angles
(`e4_topology`), runs `engine.fixes.merge.merge_regions` -- the existing kernel that re-triangulates every region of
`topo.face_region` over its EXISTING vertices (constrained Delaunay over the region's union ring, holes kept, one
affine UV map per region) -- and emits ONE site per coplanar region whose triangulation changed: an
`Edit(engine="E4", kind="cut", faces=<the region's input faces>, new_faces=<its new triangles>, new_points=None)`.
A `cut` is the kernel's "replace these faces by those" (`engine.repair.types`): it inherits the region's material and
lowest source line, takes `new_face_uv` / `new_face_normal` for the new corners, and is allowed to any engine; an
"add" is not (only E8 adds), and E4 never needs one. A region whose output is the same triangles, or the same
triangle count over the same vertices (a re-diagonalisation: no sliver, T-junction or internal line removed), is
skipped as `unchanged`, so a second E4 run over a merged floor plans nothing.

EVERY site is checked here BEFORE the judge sees it, and refused (listed in `report["refused"]`, never planned) when:
- `area_changed`: the new triangles' area differs from the input faces' by more than `AREA_REL_TOL` (1e-6, relative);
- `off_plane`: a new corner lies farther than the region tolerance (`1.5 x max(axis quanta)`, the merge's own ring
  bound) from the input faces' area-weighted plane;
- `flipped`: a new triangle faces the other way than the input faces;
- `uv_lost`: the input faces carry UVs and a new triangle does not;
- `uv_seam`: for a textured (non-flat) material, the one affine UV map of the new triangles misses an input corner's UV
  by more than `UV_RESIDUAL_MAX` (1e-3 UV units; the merge re-bases a FLAT material's UVs by whole tiles, which is
  invisible and only recorded);
- `too_large`: the region has more input faces than `max_site_faces` (a region is one site: it cannot be split).
And the whole plan raises when `merge_regions` returns different `positions` (it never does: positions are never moved,
appended to or re-indexed there; the assertion is the contract made visible).

The kernel's site checks (`validate_sites=True`) then judge each site with the Validator (ring cameras, eye-height
probes, outside directions) and roll back a region whose merge deletes or covers a seen sample: that region's slivers
are copied through unchanged. `allowed_regions` (region ids of `e4_topology`'s `face_region`) restricts the plan to
the regions a crack judgement (`tools/main_infra_crack_judge.py`) said to merge.

`evidence` of a site: `region`, `material` (index), `look`, `faces_before`, `faces_after`, `area_before`,
`area_after`, `ring_vertices` (distinct vertices the new triangles use), `plane_offset`, `uv_residual`,
`centroid`, `bbox`. `report` (the last run): `regions`, `changed`, `sites`, `skipped` (reason -> count),
`refused` (one row per refused region, with its reason), `merge_report` (the merge kernel's own counts), `seconds`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from engine.fixes.merge import default_collinear_tol, merge_regions
from engine.pipeline import Topology, analyse_topology_memo, flat_material_indices
from engine.repair.types import NO_MATERIAL_LOOK, Edit, RepairContext, UnitState
from engine.topo.planes import fit_uv, plane_basis

#: The most input faces one E4 region may hold (mirrors E3's cap; a region is one site and is never split).
MAX_SITE_FACES = 512
#: A site's area after equals its area before within this, relative.
AREA_REL_TOL = 1e-6
#: The largest residual (UV units) of the region's one affine UV map against the input corners of a textured material.
UV_RESIDUAL_MAX = 1e-3

SKIP_REASONS = ("unchanged", "not_allowed")
REFUSE_REASONS = ("area_changed", "off_plane", "flipped", "uv_lost", "uv_seam", "too_large", "mixed_material")


def e4_topology(mesh, flatness: dict, profile) -> tuple[frozenset, Topology]:
    """`(flat material indices, topology)` exactly as the legacy pipeline reads them: `flat_material_indices` at the
    profile's `flat_texture_std`, `analyse_topology_memo` at its `coplanar_angle` / `soft_angle`. The crack judge and
    the engine both call this, so their region ids agree."""
    flat = flat_material_indices(mesh, flatness, profile.flat_texture_std)
    topo = analyse_topology_memo(mesh, flat, coplanar_angle=profile.coplanar_angle, soft_angle=profile.soft_angle)
    return flat, topo


def _canonical(tri: np.ndarray) -> set:
    """The triangles as a set of (winding kept, start vertex canonical) tuples."""
    out = set()
    for a, b, c in np.asarray(tri, np.int64).tolist():
        rolls = [(a, b, c), (b, c, a), (c, a, b)]
        out.add(min(rolls))
    return out


def _look(mesh, looks: dict, material: int) -> str:
    if material < 0:
        return NO_MATERIAL_LOOK
    return looks.get(material) or f"material:{mesh.materials[material]}"


@dataclass
class RegionChange:
    """What the merge did to one region of the stage input: its input faces, its output rows and the measurements
    the rules read. `reason` is None for a region that may be planned, a `SKIP_REASONS` entry for one that need not
    be, a `REFUSE_REASONS` entry for one that must not be."""
    region: int
    faces: np.ndarray                 # input face ids, sorted
    rows: np.ndarray                  # output rows of the merge result
    material: int
    area_before: float
    area_after: float
    plane_offset: float
    ring_vertices: int
    uv_residual: float | None
    reason: str | None
    detail: str = ""
    normal: np.ndarray | None = None

    def record(self, mesh, looks: dict) -> dict:
        corners = mesh.positions[mesh.face_v[self.faces]].reshape(-1, 3)
        return {"region": int(self.region), "material": int(self.material), "look": _look(mesh, looks, self.material),
                "faces_before": int(len(self.faces)), "faces_after": int(len(self.rows)),
                "area_before": float(self.area_before), "area_after": float(self.area_after),
                "ring_vertices": int(self.ring_vertices), "plane_offset": float(self.plane_offset),
                "uv_residual": None if self.uv_residual is None else float(self.uv_residual),
                "centroid": [round(float(v), 4) for v in corners.mean(axis=0)],
                "bbox": [[round(float(v), 4) for v in corners.min(axis=0)],
                         [round(float(v), 4) for v in corners.max(axis=0)]]}


def region_changes(mesh, topo: Topology, result, flat: Iterable[int], *, allowed_regions=None,
                   max_site_faces: int = MAX_SITE_FACES) -> list[RegionChange]:
    """One `RegionChange` per region the merge result holds, in ascending region id, each measured against the rules
    of the module docstring. Raises when `result` changed `positions` or a region's rows disagree on their source."""
    if not np.array_equal(result.mesh.positions, mesh.positions):
        raise ValueError("E4: merge_regions changed positions; the merge never moves, adds or re-indexes a vertex")
    flat = set(int(m) for m in flat)
    tol = default_collinear_tol(topo.quanta)
    tri_old = mesh.positions[mesh.face_v]
    cross_old = np.cross(tri_old[:, 1] - tri_old[:, 0], tri_old[:, 2] - tri_old[:, 0])
    area_old = 0.5 * np.linalg.norm(cross_old, axis=1)
    out_v = result.mesh.face_v
    tri_new = result.mesh.positions[out_v]
    cross_new = np.cross(tri_new[:, 1] - tri_new[:, 0], tri_new[:, 2] - tri_new[:, 0])
    area_new = 0.5 * np.linalg.norm(cross_new, axis=1)

    by_region: dict[int, list[int]] = {}
    for row, region in enumerate(np.asarray(result.face_region).tolist()):
        if region >= 0:
            by_region.setdefault(region, []).append(row)
    changes: list[RegionChange] = []
    for region in sorted(by_region):
        rows = np.asarray(by_region[region], np.int64)
        source = np.sort(np.asarray(result.source_faces[rows[0]], np.int64))
        for row in rows[1:].tolist():
            if not np.array_equal(np.sort(np.asarray(result.source_faces[row], np.int64)), source):
                raise ValueError(f"E4: the rows of merged region {region} name different source faces")
        materials = np.unique(mesh.face_material[source])
        material = int(materials[0])
        a_before, a_after = float(area_old[source].sum()), float(area_new[rows].sum())
        normal = cross_old[source].sum(axis=0)
        length = float(np.linalg.norm(normal))
        normal = normal / length if length > 0 else normal
        centre = mesh.positions[mesh.face_v[source]].reshape(-1, 3).mean(axis=0)
        new_corners = tri_new[rows].reshape(-1, 3)
        offset = float(np.abs((new_corners - centre) @ normal).max()) if len(rows) else 0.0
        used = np.unique(out_v[rows])
        change = RegionChange(region=region, faces=source, rows=rows, material=material, area_before=a_before,
                              area_after=a_after, plane_offset=offset, ring_vertices=int(len(used)),
                              uv_residual=None, reason=None, normal=normal)
        changes.append(change)

        if len(rows) == len(source) and (_canonical(out_v[rows]) == _canonical(mesh.face_v[source])
                                         or np.array_equal(used, np.unique(mesh.face_v[source]))):
            # the same triangles, or the same count over the same vertices: a re-diagonalisation removes no sliver,
            # no T-junction and no internal line, so the region is left as it is (and a second E4 run is a no-op)
            change.reason, change.detail = "unchanged", "the merge returned the region's own triangle count and vertices"
            continue
        if allowed_regions is not None and region not in allowed_regions:
            change.reason, change.detail = "not_allowed", "the crack judgement did not say to merge this region"
            continue
        if len(materials) != 1:
            change.reason, change.detail = "mixed_material", f"the region spans materials {materials.tolist()}"
            continue
        if len(source) > max_site_faces:
            change.reason = "too_large"
            change.detail = f"{len(source)} input faces, more than max_site_faces {max_site_faces}"
            continue
        if abs(a_after - a_before) > AREA_REL_TOL * a_before:
            change.reason = "area_changed"
            change.detail = f"area {a_before:.6f} before, {a_after:.6f} after (tolerance {AREA_REL_TOL} relative)"
            continue
        if offset > tol:
            change.reason = "off_plane"
            change.detail = f"a new corner lies {offset:.6f} in off the region plane (tolerance {tol:.6f} in)"
            continue
        if (cross_new[rows] @ normal <= 0).any():
            change.reason, change.detail = "flipped", "a new triangle faces the other way than the input faces"
            continue
        old_vt = mesh.face_vt[source]
        if (old_vt >= 0).all() and len(mesh.uvs):
            new_vt = result.mesh.face_vt[rows]
            if not (new_vt >= 0).all():
                change.reason, change.detail = "uv_lost", "the input faces carry UVs and a new triangle does not"
                continue
            e1, e2 = plane_basis(normal)
            nxy = np.column_stack([(new_corners - centre) @ e1, (new_corners - centre) @ e2])
            nuv = result.mesh.uvs[new_vt].reshape(-1, 2).astype(np.float64)
            coef, off = fit_uv(nxy, nuv)
            fit_residual = float(np.linalg.norm(nxy @ coef.T + off - nuv, axis=1).max())
            old_corners = tri_old[source].reshape(-1, 3)
            oxy = np.column_stack([(old_corners - centre) @ e1, (old_corners - centre) @ e2])
            ouv = mesh.uvs[old_vt].reshape(-1, 2).astype(np.float64)
            residual = float(np.linalg.norm(oxy @ coef.T + off - ouv, axis=1).max())
            change.uv_residual = max(residual, fit_residual)
            if material not in flat and change.uv_residual > UV_RESIDUAL_MAX:
                change.reason = "uv_seam"
                change.detail = (f"the region's one affine UV map misses an input corner by {residual:.4g} UV units "
                                 f"(at most {UV_RESIDUAL_MAX}; new-corner fit residual {fit_residual:.4g})")
                continue
    return changes


@dataclass
class E4Merge:
    """The repair engine E4 (see the module docstring). `flatness` is the per-material texture std the legacy profile
    reads its flat materials from; `allowed_regions` restricts the plan to those region ids (None: every region);
    `report` holds the last run's numbers."""
    flatness: dict = field(default_factory=dict)
    allowed_regions: set | None = None
    max_site_faces: int = MAX_SITE_FACES
    name: str = "E4"
    legacy: bool = False
    report: dict | None = field(default=None, repr=False)

    def plan(self, unit: UnitState, ctx: RepairContext) -> list[Edit]:
        started = time.perf_counter()
        mesh = unit.mesh
        flat, topo = e4_topology(mesh, self.flatness, ctx.profile)
        t0 = time.perf_counter()
        result = merge_regions(mesh, topo, flat)
        merge_seconds = time.perf_counter() - t0
        allowed = None if self.allowed_regions is None else {int(r) for r in self.allowed_regions}
        changes = region_changes(mesh, topo, result, flat, allowed_regions=allowed, max_site_faces=self.max_site_faces)

        edits: list[Edit] = []
        skipped = {k: 0 for k in SKIP_REASONS}
        refused: list[dict] = []
        for change in changes:
            if change.reason in SKIP_REASONS:
                skipped[change.reason] += 1
                continue
            record = change.record(mesh, unit.looks)
            if change.reason is not None:
                refused.append({**record, "reason": change.reason, "detail": change.detail})
                continue
            rows = change.rows
            new_faces = result.mesh.face_v[rows]
            new_uv = None
            if (mesh.face_vt[change.faces] >= 0).all() and len(mesh.uvs):
                new_uv = result.mesh.uvs[result.mesh.face_vt[rows]]
            new_normal = None
            old_vn = mesh.face_vn[change.faces]
            if (old_vn >= 0).all() and len(mesh.normals) and (result.mesh.face_vn[rows] >= 0).all():
                new_normal = result.mesh.normals[result.mesh.face_vn[rows]]
            edits.append(Edit(
                engine="E4", kind="cut", faces=tuple(change.faces.tolist()), new_faces=new_faces, new_points=None,
                site=len(edits),
                reason=(f"E4 coplanar merge: region {change.region} ({record['look']}), {len(change.faces)} coplanar "
                        f"slivers re-triangulated as {len(rows)} triangles over {change.ring_vertices} existing "
                        f"vertices; area {change.area_before:.3f} kept, no vertex moved or invented"),
                evidence=record, new_face_uv=new_uv, new_face_normal=new_normal))
        self.report = {
            "regions": int(len(set(topo.face_region[topo.face_region >= 0].tolist()))),
            "changed": sum(1 for c in changes if c.reason != "unchanged"),
            "sites": len(edits), "skipped": skipped, "refused": refused,
            "allowed_regions": None if allowed is None else sorted(allowed),
            "max_site_faces": int(self.max_site_faces), "flat_materials": sorted(int(m) for m in flat),
            "merge_report": result.report,
            "seconds": {"merge": round(merge_seconds, 2), "total": round(time.perf_counter() - started, 2)},
        }
        return edits
