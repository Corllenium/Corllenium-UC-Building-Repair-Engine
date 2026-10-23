"""E5, the checked coincident-layer cull (MAIN-INFRA-E4-MERGE-20261023, E5 follow-up).

THE MEASURED PROBLEM (E4 trial on the real 7F E3 candidate, 2026-10-24, 4 h 11 min): 1,243 coplanar regions, 968 of
them rolled back by the site judge, every one with reasons `{"covered": n}`: the merged clean triangle covers samples
that lie on a COINCIDENT TWIN LAYER -- a second face on the same plane (within the depth tolerance), overlapping the
first's footprint -- which the Validator counts as `flicker_same` (same look) or `flicker_diff` (different look). The
fresh Minecraft exports are full of such twins (7F before E3: flicker_diff 4518, flicker_same 7091). Before the merge
can clean a plane, one layer of each twin has to go: that is this engine, run after E3 and before E4.

REMOVE ONLY (the E3 pattern). `E5Coincident.plan` emits `Edit(engine="E5", kind="remove")` edits and nothing else: no
cut, no new point, no new face. (`engine.repair.types` allows E5 a cut with points on the winner's border -- the owner's
exception of 2026-10-03 -- but this engine does not use it: it never clips and never adds geometry.)

THE PAIRS ARE THE VALIDATOR'S. The twin pairs come from `engine.fixes.overlap.double_layers` exactly as `find_errors`
calls it (`double_layers(positions_c, face_w, guard_depth_tol(quanta, profile), VIEWS_26, profile.guard_size,
centre=centre)` over `analyse_topology(mesh, frozenset(), coplanar_angle, soft_angle)`), so E5 targets exactly the
faces the Validator counts as flicker: two faces whose outlines share more than 1 sq in within ONE plane (parallel,
every corner within the depth tolerance of the other's plane). SAME-FACING pairs (`double_layers`' `opposite` flag
false and the face normals' dot above `FACING_DOT`, 0.7) go to rules (a) and (b) below. OPPOSITE pairs (the
back-to-back case) go to rule (c), `backface_twin` (owner decision 2026-10-24, `cull_opposite_backfaces`, on by
default; measured basis: on the real 7F E3 candidate `double_layers` reported 4,783 pairs, ALL opposite, and the
error census counted 5,556 flicker faces of which 4,974 are also `hidden` -- a face whose normal points into solid
lying exactly on its visible twin, which E3 never proposes because its samples see the room through the twin at a
depth tie): with the per-face front exposure measured exactly as `find_errors` measures it
(`engine.vis.exposure.compute_side_exposure(positions_c, faces, ok, n_dirs=profile.n_dirs)`), the face whose FRONT
exposure is 0 loses to a twin whose front exposure is above 0, whatever the looks; both hidden or both exposed keep
both (`no_backface_winner`). The coverage, anchoring and only-coverage rules below apply to it as to any drop. With
`cull_opposite_backfaces=False` opposite pairs are only counted. Treating an opposite pair as duplicates is otherwise
blocked (AGENTS.md section 4); this rule is the owner's exception and the Validator judges it under its own
allowed-change class `coincident_backface_removed` (`engine.validate.checks.CBR`, opt-in).

WHO LOSES. The same-facing pairs join faces into coincident groups (union-find over the pairs). Within a group every
face is considered in ascending (area, -id) order -- the smaller face first, an exact copy by its higher id -- against
the faces of its group that are still kept and overlap it (`O`). The faces of `O` that BEAT it are:
- (a) same look: the ones with the larger area (equal area: the lower id), so the larger face wins and an identical
  copy keeps its first occurrence;
- (b) different look: the ones with the higher PRIORITY (`priority(material name)`: by default `default_priority`,
  2 for a facade / trim / decorative material -- a name containing one of `DEFAULT_WIN_PATTERNS`: UC_PAL_05,
  UC_PAL_12, UC_PAL_00 from the repair skill, and for Minecraft exports quartz_block_top, quartz_block_side,
  iron_block, glass, wool, trim, facade -- 0 for a generic concrete_white / concrete_gray surface, 1 otherwise), else,
  at equal priority, the larger area; at equal priority and equal area nobody wins (`no_winner`: the owner decides).
A face is DROPPED only when the union of the faces that beat it covers at least `COVER_FRACTION` (98 %) of its own
footprint (shapely, in the group's plane); a face covered less is kept (`uncovered`: partial overlap is never clipped).
The winners that cover a dropped face are ANCHORED: they cannot lose later in the same run, so no pair ever loses both
faces (a three-layer stack keeps its two larger layers; a second run takes the middle one). After the greedy pass every
dropped face is checked once more against the FINAL kept faces of its group: one that is no longer covered 98 % by
kept faces of the plane is put back (`only_coverage`), so a drop never opens a hole.

SITES. One `remove` site per edge-connected group of dropped faces (faces sharing an edge of the welded topology,
`e3_hidden._components`), a group over `max_site_faces` split by `e3_hidden.split_group` (E3's cap, 512). The kernel's
site checks (`validate_sites=True`) judge each site with the Validator: deleting an identical coplanar copy (same look,
UV and winding) passes; removing the different-look copy fails check 1 `look` and check 3 `replaced` in the Validator
as it stands (its docstring says so), so such a site is rolled back until the Validator names E5's allowed-change
class. The plan records the rule; the judge keeps the floor.

`evidence` of a site: `group` (its connected group), `cell`, `group_faces`, `faces`, `area`, `pairs` (one row per
dropped face: `face`, `material`, `look`, `area`, `winners`, `winner_looks`, `winner_areas`, `overlap_fraction` -- the
share of the face's footprint under the winners' union -- and `rule`: `same_look`, `priority`, `larger_area`),
`centroid`, `bbox`. `report` (the last run): `pairs` (`double_layers`, `opposite`, `same_facing`, `off_facing`),
`groups`, `dropped`, `by_rule`, `kept` (reason -> count: `uncovered`, `no_winner`, `anchored`, `only_coverage`,
`no_overlap`), `kept_faces` (one row per kept face that had a winner or an overlapper), `planned` (the faces of each
site), `sites`, `seconds`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import shapely

from engine.fixes.overlap import double_layers
from engine.fixes.pipeline import guard_depth_tol
from engine.guard.views import VIEWS_26
from engine.vis.exposure import compute_side_exposure
from engine.pipeline import analyse_topology, flat_material_indices
from engine.repair.engines.e3_hidden import MAX_SITE_FACES, _components, split_group
from engine.repair.types import NO_MATERIAL_LOOK, Edit, RepairContext, UnitState
from engine.topo.planes import plane_basis

#: A dropped face must be covered at least this share of its footprint by the faces that beat it, and by the kept faces.
COVER_FRACTION = 0.98
#: Two faces of a pair must face the same way this closely (dot of unit normals) to be a coincident twin here.
FACING_DOT = 0.7
#: Material-name patterns (case-insensitive substrings) that WIN a different-look pair: the repair skill's facade /
#: trim palette entries, and the Minecraft export's decorative blocks.
DEFAULT_WIN_PATTERNS = ("UC_PAL_05", "UC_PAL_12", "UC_PAL_00", "quartz_block_top", "quartz_block_side", "iron_block",
                        "glass", "wool", "trim", "facade")
#: Material-name patterns that LOSE a different-look pair: the generic concrete surfaces.
DEFAULT_LOSER_PATTERNS = ("concrete_white", "concrete_gray")
RULES = ("same_look", "priority", "larger_area", "backface_twin")
KEPT_REASONS = ("uncovered", "no_winner", "no_backface_winner", "anchored", "only_coverage", "no_overlap")


def default_priority(material: str, *, win=DEFAULT_WIN_PATTERNS, lose=DEFAULT_LOSER_PATTERNS) -> int:
    """2 for a facade / trim / decorative material, 0 for a generic concrete surface, 1 for anything else."""
    name = (material or "").lower()
    if any(p.lower() in name for p in win):
        return 2
    if any(p.lower() in name for p in lose):
        return 0
    return 1


def _look(mesh, looks: dict, material: int) -> str:
    if material < 0:
        return NO_MATERIAL_LOOK
    return looks.get(material) or f"material:{mesh.materials[material]}"


def _union_find(n: int, edges) -> list[list[int]]:
    parent = list(range(n))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in edges:
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(root(i), []).append(i)
    return [sorted(g) for _, g in sorted(groups.items())]


@dataclass
class E5Coincident:
    """The repair engine E5 (see the module docstring). `flatness` is the per-material texture std the legacy profile
    reads its flat materials from (recorded; the looks decide); `looks` overrides `unit.looks` (material index -> look
    key); `priority(material name) -> int` decides a different-look pair (None: `default_priority` over
    `win_patterns` / `lose_patterns`); `report` holds the last run's numbers."""
    flatness: dict = field(default_factory=dict)
    looks: dict | None = None
    priority: Callable[[str], int] | None = None
    max_site_faces: int = MAX_SITE_FACES
    name: str = "E5"
    legacy: bool = False
    win_patterns: tuple = DEFAULT_WIN_PATTERNS
    lose_patterns: tuple = DEFAULT_LOSER_PATTERNS
    cover_fraction: float = COVER_FRACTION
    facing_dot: float = FACING_DOT
    #: Rule c (owner decision 2026-10-24): drop the solid-facing twin of a back-to-back pair, whatever its look.
    cull_opposite_backfaces: bool = True
    report: dict | None = field(default=None, repr=False)

    def _priority(self, mesh, material: int) -> int:
        name = mesh.materials[material] if material >= 0 else ""
        if self.priority is not None:
            return int(self.priority(name))
        return default_priority(name, win=self.win_patterns, lose=self.lose_patterns)

    def plan(self, unit: UnitState, ctx: RepairContext) -> list[Edit]:
        started = time.perf_counter()
        mesh, profile = unit.mesh, ctx.profile
        looks = unit.looks if self.looks is None else self.looks
        seconds: dict[str, float] = {}

        # ---- the Validator's pairs: double_layers exactly as find_errors calls it
        t0 = time.perf_counter()
        flat = flat_material_indices(mesh, self.flatness, profile.flat_texture_std)
        topo = analyse_topology(mesh, frozenset(), coplanar_angle=profile.coplanar_angle, soft_angle=profile.soft_angle)
        pos, faces = topo.positions_w, topo.face_w
        centre = (pos.min(axis=0) + pos.max(axis=0)) / 2.0
        depth_tol = guard_depth_tol(topo.quanta, profile)
        dl = double_layers(pos - centre, faces, depth_tol, VIEWS_26, profile.guard_size, centre=centre)
        seconds["double_layers"] = time.perf_counter() - t0

        tri = pos[faces]
        cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        area = 0.5 * np.linalg.norm(cross, axis=1)
        normal = np.zeros_like(cross)
        ok = area > 0
        normal[ok] = cross[ok] / (2.0 * area[ok, None])
        pair_counts = {"double_layers": len(dl["pair_list"]), "opposite": 0, "same_facing": 0, "off_facing": 0}
        pairs: list[tuple[int, int, float]] = []
        opposite_of: set[tuple[int, int]] = set()
        for i, j, shared, opposite in dl["pair_list"]:
            if opposite:
                pair_counts["opposite"] += 1
                if not self.cull_opposite_backfaces:
                    continue
                opposite_of.add((int(i), int(j)))
                opposite_of.add((int(j), int(i)))
            elif float(normal[i] @ normal[j]) <= self.facing_dot:
                pair_counts["off_facing"] += 1
                continue
            else:
                pair_counts["same_facing"] += 1
            pairs.append((int(i), int(j), float(shared)))

        # ---- the back-to-back rule needs each face's front exposure, measured as the error census measures it
        t0 = time.perf_counter()
        front = back = None
        if opposite_of:
            front, back = compute_side_exposure(pos - centre, faces, ok, n_dirs=profile.n_dirs)
        seconds["exposure"] = time.perf_counter() - t0

        # ---- the coincident groups, and who loses in each
        t0 = time.perf_counter()
        involved = sorted({f for i, j, _s in pairs for f in (i, j)})
        local = {f: k for k, f in enumerate(involved)}
        groups = _union_find(len(involved), [(local[i], local[j]) for i, j, _s in pairs])
        overlaps: dict[int, set[int]] = {f: set() for f in involved}
        for i, j, _s in pairs:
            overlaps[i].add(j)
            overlaps[j].add(i)
        material = np.asarray(mesh.face_material)
        look_of = {f: _look(mesh, looks, int(material[f])) for f in involved}
        prio_of = {f: self._priority(mesh, int(material[f])) for f in involved}
        exposure = {f: (float(front[f]), float(back[f])) if front is not None else (None, None) for f in involved}
        dropped: dict[int, dict] = {}
        kept_rows: list[dict] = []
        kept_counts = {k: 0 for k in KEPT_REASONS}
        anchored: set[int] = set()
        for members in groups:
            members = [involved[k] for k in members]
            if len(members) < 2:
                continue
            # the group plane: every face's normal signed toward the largest face's (a back-to-back pair's normals
            # would cancel otherwise); the footprints are the same whichever side the plane is viewed from
            ref = normal[max(members, key=lambda f: float(area[f]))]
            n = np.sum([cross[f] * (1.0 if float(normal[f] @ ref) >= 0 else -1.0) for f in members], axis=0)
            length = float(np.linalg.norm(n))
            n = n / length if length > 0 else ref
            e1, e2 = plane_basis(n)
            origin = tri[members].reshape(-1, 3).mean(axis=0)
            poly = {f: shapely.Polygon(np.column_stack([(tri[f] - origin) @ e1, (tri[f] - origin) @ e2]))
                    for f in members}
            group_dropped: list[int] = []
            for f in sorted(members, key=lambda f: (float(area[f]), -f)):
                others = [g for g in overlaps[f] if g in poly and g not in dropped]
                if not others:
                    kept_counts["no_overlap"] += 1
                    continue
                winners = [g for g in others if self._beats(g, f, area, look_of, prio_of, opposite_of, exposure)]
                if not winners:
                    reason = ("no_backface_winner" if all((g, f) in opposite_of for g in others) else "no_winner")
                    kept_counts[reason] += 1
                    kept_rows.append(self._kept_row(f, reason, others,
                                                    self._coverage(poly[f], [poly[g] for g in others]), look_of, area,
                                                    exposure))
                    continue
                cover = self._coverage(poly[f], [poly[g] for g in winners])
                if f in anchored:
                    kept_counts["anchored"] += 1
                    kept_rows.append(self._kept_row(f, "anchored", winners, cover, look_of, area, exposure))
                    continue
                if cover < self.cover_fraction:
                    kept_counts["uncovered"] += 1
                    kept_rows.append(self._kept_row(f, "uncovered", winners, cover, look_of, area, exposure))
                    continue
                rule = ("backface_twin" if any((g, f) in opposite_of for g in winners)
                        else "same_look" if all(look_of[g] == look_of[f] for g in winners)
                        else "priority" if any(prio_of[g] != prio_of[f] for g in winners if look_of[g] != look_of[f])
                        else "larger_area")
                dropped[f] = {"face": int(f), "material": int(material[f]), "look": look_of[f],
                              "area": round(float(area[f]), 4), "winners": [int(g) for g in winners],
                              "winner_looks": [look_of[g] for g in winners],
                              "winner_areas": [round(float(area[g]), 4) for g in winners],
                              "front": exposure[f][0], "back": exposure[f][1],
                              "winner_front": [exposure[g][0] for g in winners],
                              "winner_back": [exposure[g][1] for g in winners],
                              "overlap_fraction": round(cover, 6), "rule": rule}
                anchored.update(winners)
                group_dropped.append(f)
            # the final check: every dropped face is still covered 98 % by the faces of its plane that stay
            kept_in_group = [g for g in members if g not in dropped]
            for f in group_dropped:
                cover = self._coverage(poly[f], [poly[g] for g in kept_in_group if g in overlaps[f]])
                if cover < self.cover_fraction:
                    row = dropped.pop(f)
                    kept_counts["only_coverage"] += 1
                    kept_rows.append({**row, "kept": "only_coverage", "kept_overlap_fraction": round(cover, 6)})
        seconds["decide"] = time.perf_counter() - t0

        # ---- sites: edge-connected groups of the dropped faces, a big one split by a spatial grid
        candidates = np.array(sorted(dropped), np.int64)
        centroid = tri.mean(axis=1)
        comps = _components(faces, candidates)
        edits: list[Edit] = []
        split = 0
        for g, members in enumerate(comps):
            pieces = split_group(members, centroid, self.max_site_faces)
            split += int(len(pieces) > 1)
            for c, site_faces in enumerate(pieces):
                corners = mesh.positions[mesh.face_v[site_faces]].reshape(-1, 3)
                rows = [dropped[int(f)] for f in site_faces.tolist()]
                evidence = {"group": g, "cell": c if len(pieces) > 1 else None, "group_faces": int(len(members)),
                            "faces": int(len(site_faces)), "area": round(float(area[site_faces].sum()), 4),
                            "pairs": rows, "rules": [r["rule"] for r in rows],
                            "centroid": [round(float(v), 4) for v in corners.mean(axis=0)],
                            "bbox": [[round(float(v), 4) for v in corners.min(axis=0)],
                                     [round(float(v), 4) for v in corners.max(axis=0)]]}
                by_rule = {r: sum(1 for row in rows if row["rule"] == r) for r in RULES if any(
                    row["rule"] == r for row in rows)}
                edits.append(Edit(
                    engine="E5", kind="remove", faces=tuple(site_faces.tolist()), new_faces=None, new_points=None,
                    site=len(edits),
                    reason=(f"E5 coincident layer: {len(site_faces)} face(s) of connected group {g} lying on the same "
                            f"plane as, facing the same way as, and covered at least {self.cover_fraction:.0%} by "
                            f"larger or higher-priority faces that stay ({by_rule}); the Validator's own double-layer "
                            f"pairs at depth tolerance {depth_tol:.4f} in"),
                    evidence=evidence))

        self.report = {
            "pairs": pair_counts, "depth_tol": float(depth_tol), "facing_dot": float(self.facing_dot),
            "cover_fraction": float(self.cover_fraction), "cull_opposite_backfaces": bool(self.cull_opposite_backfaces),
            "exposure_n_dirs": int(profile.n_dirs) if front is not None else None,
            "flat_materials": sorted(int(m) for m in flat),
            "faces_in_pairs": len(involved), "groups": sum(1 for g in groups if len(g) > 1),
            "dropped": len(dropped),
            "by_rule": {r: sum(1 for row in dropped.values() if row["rule"] == r) for r in RULES},
            "kept": kept_counts, "kept_faces": kept_rows,
            "planned": [list(e.faces) for e in edits], "sites": len(edits), "connected_groups": len(comps),
            "groups_split": split, "max_site_faces": int(self.max_site_faces),
            "seconds": {**{k: round(v, 2) for k, v in seconds.items()},
                        "total": round(time.perf_counter() - started, 2)},
        }
        return edits

    @staticmethod
    def _beats(g: int, f: int, area, look_of, prio_of, opposite_of, exposure) -> bool:
        """Does the kept face `g` beat `f`? A back-to-back pair (rule c, `backface_twin`): `g` wins iff `f`'s front
        exposure is 0 and `g`'s is above 0, whatever the looks. A same-facing pair: the module docstring's rules a
        and b."""
        if (g, f) in opposite_of:
            f_front, g_front = exposure[f][0], exposure[g][0]
            return f_front is not None and g_front is not None and f_front <= 0.0 < g_front
        if look_of[g] == look_of[f]:
            return area[g] > area[f] or (area[g] == area[f] and g < f)
        if prio_of[g] != prio_of[f]:
            return prio_of[g] > prio_of[f]
        return bool(area[g] > area[f])

    @staticmethod
    def _coverage(target, covers) -> float:
        if not covers or target.area <= 0:
            return 0.0
        return float(shapely.intersection(target, shapely.unary_union(covers)).area / target.area)

    @staticmethod
    def _kept_row(f, reason, others, cover, look_of, area, exposure) -> dict:
        return {"face": int(f), "look": look_of[f], "area": round(float(area[f]), 4), "kept": reason,
                "winners": [int(g) for g in others], "winner_looks": [look_of[g] for g in others],
                "front": exposure[f][0], "back": exposure[f][1],
                "winner_front": [exposure[g][0] for g in others],
                "overlap_fraction": round(float(cover), 6)}
