"""E8, strict solidify (job P2-E8a): `engine.fixes.solidify.solidify` as a repair engine, ONE SITE PER PIECE.

`E8Solidify.plan` runs `solidify` UNCHANGED, on the topology the pipeline gives it (`start_fix`), and hands back
what it built as `Edit`s. A PIECE is one closing group of solidify's: the wall under one outline edge, or one
region's bottom (`SolidifyResult.face_group` / `replaced_group` / `pieces`, a read-only record of what was built).
Each piece is its own site, so the kernel's site checks (`repair_unit(..., validate_sites=True)`) judge every piece
on its own and roll back a piece that broke anything -- above all, one that COVERS a sample some viewpoint sees.

THE STRICT RULE (AGENTS.md section 5: a rebuilt side may cover only faces that are 0 % visible; ruling E8-R1). It is
enforced by the Validator's site checks, which look from every outside direction, the ring of cameras and the
eye-height probes inside the floor; NOT by the cap guard's `cover_max_exposure` (0.10, a threshold that stays: with
0 the skirt closing `open_box_with_cells` is refused, and ray sampling never measures exactly 0 through a small
opening). The guard is a cheap pre-filter; a piece it lets through that covers anything any viewpoint sees is
rolled back by the check. A rolled-back piece leaves its hole open, for E8b (narrow flat fill) or E8c (the
needs-modelling queue).

The edits of a piece (site = its group id), against the stage input (`Edit` conventions, K1/K1b):
- an "add" of its faces, carrying the points solidify invented that they use (`new_points`, numbered from the
  input's point count), the UV at each corner (`new_face_uv`) and the normal at each corner (`new_face_normal`:
  solidify writes none, so every face is the all-NaN "no normal" placeholder and gets `face_vn = -1`, as solidify's
  own output has), and its material in `evidence["material"]`;
- or, for a piece that REPLACED broken pieces of a side or bottom (`SolidifyResult.replaced`) all in its own
  material, ONE "cut" of those faces into its faces; when the replaced faces are in another material (a cut
  inherits its input faces' material, `apply_edits`), an "add" plus a "remove" of the replaced faces, same site.

`apply_edits(input, edits)` then gives solidify's output: the same faces (K1 keys) with the same UVs and materials,
as a multiset (ruling (b)): the input's surviving faces come in the same order and the new ones piece by piece, but
the vertex numbering differs, because every edit counts its own points from the input's count and a point two
pieces share (a corner of two walls) is written once per piece.

`evidence` of the add or cut: `piece` ("wall" | "bottom"), `group`, `region`, `material`, `length` and, for a wall,
`edge` (its top edge's end points); `thickness` (a wall's depth below each end, a bottom's depth), `measured` (a
wall edge's measured height), `replaced` (the input faces it replaced), `faces`, and `solidify`: the region's rows of
the solidify report (thickness, bottom depth, representative side depth).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from engine.fixes.pipeline import start_fix
from engine.fixes.solidify import solidify
from engine.repair.types import Edit, RepairContext, UnitState


def _corner_values(index: np.ndarray, table: np.ndarray, width: int) -> np.ndarray:
    """(k, 3, width) values at each corner of the faces whose `face_vt` / `face_vn` rows are `index`: the table's
    rows, and the all-NaN placeholder for a face without all three (written back as -1 by `apply_edits`)."""
    out = np.full((len(index), 3, width), np.nan)
    has = (index >= 0).all(axis=1)
    if has.any():
        out[has] = np.asarray(table, np.float64).reshape(-1, width)[index[has]]
    return out


def _region_rows(report: dict, region: int) -> dict:
    key = str(region)
    return {"thickness": report.get("thickness_per_region", {}).get(key),
            "bottom_depth": report.get("bottom_depth_per_region", {}).get(key),
            "representative_side": report.get("representative_side_per_region", {}).get(key)}


@dataclass
class E8Solidify:
    """The repair engine E8 (see the module docstring). `flatness` is the per-material texture std the pipeline
    reads its flat materials from (`fix_object`'s `flatness`); `report` holds the last run's solidify report."""
    flatness: dict = field(default_factory=dict)
    name: str = "E8"
    legacy: bool = False
    report: dict | None = field(default=None, repr=False)
    #: P2-E3, read only: `(the stage input, SolidifyResult.seen_through_shell)` of the last run (None: not measured):
    #: the input faces the cap guard let a new face cover only because they are seen through a closed slab. The
    #: legacy hidden stage never deletes one, and neither does E3 run after this engine.
    seen_through: tuple | None = field(default=None, repr=False)

    def plan(self, unit: UnitState, ctx: RepairContext) -> list[Edit]:
        mesh, profile = unit.mesh, ctx.profile
        result = solidify(mesh, start_fix(mesh, self.flatness, profile).topo_input, profile)
        self.report = result.report
        self.seen_through = (None if result.seen_through_shell is None
                             else (mesh, np.asarray(result.seen_through_shell, bool).copy()))
        out, n = result.mesh, len(mesh.positions)
        if len(out.positions) < n or not np.array_equal(out.positions[:n], mesh.positions):
            raise ValueError("E8: solidify moved or dropped an input vertex; its pieces cannot be written as edits")
        group = result.face_group
        pieces = result.pieces or []
        # a replaced face is named by the edits of the piece that replaced it; a piece that shipped no face makes no
        # edit, so its replaced faces would silently stay in the mesh: refuse that instead
        shipped = set(group[group >= 0].tolist())
        orphans = sorted(set(result.replaced_group[result.replaced_group >= 0].tolist()) - shipped)
        if orphans:
            raise ValueError(f"E8: solidify says piece(s) {orphans} replaced input faces, but those pieces shipped no "
                             f"face; their replaced faces would be kept without any edit naming them")
        edits: list[Edit] = []
        for g in sorted(set(group[group >= 0].tolist())):
            info = pieces[g]
            ids = np.flatnonzero(group == g)
            rows = out.face_v[ids].astype(np.int64)
            local = np.unique(rows[rows >= n])
            new_faces = np.where(rows >= n, n + np.searchsorted(local, rows), rows)
            new_points = out.positions[local] if len(local) else None
            material = int(out.face_material[ids[0]])
            if not (out.face_material[ids] == material).all():
                raise ValueError(f"E8: piece {g} has faces of more than one material")
            replaced = np.flatnonzero(result.replaced_group == g)
            evidence = {"piece": info["kind"], "group": int(g), "region": int(info["region"]),
                        "material": material, "length": round(float(info["length"]), 4),
                        "thickness": (info["heights"] if info["kind"] == "wall" else info["depth"]),
                        "replaced": replaced.tolist(), "faces": int(len(ids)),
                        "solidify": _region_rows(result.report, int(info["region"]))}
            if info["kind"] == "wall":
                evidence["edge"] = info["edge"]
                evidence["measured"] = info["measured"]
            what = (f"a wall under an outline edge of top region {info['region']} "
                    f"({info['length']:.2f} in long, {max(info['heights']):.2f} in deep)"
                    if info["kind"] == "wall" else
                    f"the bottom of top region {info['region']}, {info['depth']:.2f} in down")
            uv = _corner_values(out.face_vt[ids], out.uvs, 2)
            normal = _corner_values(out.face_vn[ids], out.normals, 3)
            one_look = len(replaced) and (mesh.face_material[replaced] == material).all()
            if one_look:
                edits.append(Edit(engine="E8", kind="cut", faces=tuple(replaced.tolist()), new_faces=new_faces,
                                  new_points=new_points, site=int(g),
                                  reason=f"E8 solidify: {what}, replacing {len(replaced)} broken piece(s)",
                                  evidence=evidence, new_face_uv=uv, new_face_normal=normal))
                continue
            edits.append(Edit(engine="E8", kind="add", faces=(), new_faces=new_faces, new_points=new_points,
                              site=int(g), reason=f"E8 solidify: {what}", evidence=evidence,
                              new_face_uv=uv, new_face_normal=normal))
            if len(replaced):
                edits.append(Edit(engine="E8", kind="remove", faces=tuple(replaced.tolist()), new_faces=None,
                                  new_points=None, site=int(g),
                                  reason=f"E8 solidify: broken pieces in another material, replaced by {what}",
                                  evidence={"piece": info["kind"], "group": int(g), "region": int(info["region"]),
                                            "replaced_by": "the add of this site"}))
        return edits
