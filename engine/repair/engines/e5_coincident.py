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
exposure is 0 loses to a twin whose front exposure is above 0, whatever the looks; both exposed keep both
(`both_exposed`: a legitimate two-sided zero-thickness slab; `kept_pairs` samples those pairs with both faces'
exposures for the audit). Rule (d), `interior_twins` (coordinator, 2026-10-24, after the first 7F chain run kept 4,476
faces as `no_backface_winner`): a back-to-back pair BOTH of whose fronts are hidden is an interior block-against-block
seam, and BOTH faces are planned for removal as ONE site (the seam's faces are joined into one site even when their
vertices are not welded together); the cover and only-coverage rules do not apply to it -- the site judge decides, and
a seam any sample sees is rolled back as any site is. The census alone is NOT sufficient (7F chain run #2: 3,738 seam
faces planned, the judge saw 18,191 of their samples and rolled most seams back), so before a seam is planned the
Validator's own viewpoint set must see NEITHER face: `seam_view(mesh, faces)` -- by default the site judge's
`lattice_seen` (E3-R7's dense lattice, `DENSE_POINTS_PER_FACE`) plus `probe_seen` (E3-R4's eye-height probes) from
`ctx.validator` -- and a seam with a seen face stays (`kept.seam_seen`, with `points_seen`), its partners with it;
with no view and no judge no seam is planned (`kept.seam_unverified`). `report["interior_filtered"]` counts
`seams`, `seen`, `unverified`, `planned`. The coverage, anchoring and only-coverage rules apply to rule (c)'s
drop as to any other. With
`cull_opposite_backfaces=False` opposite pairs are only counted. Treating an opposite pair as duplicates is otherwise
blocked (AGENTS.md section 4); this rule is the owner's exception and the Validator judges it under its own
allowed-change class `coincident_backface_removed` (`engine.validate.checks.CBR`, opt-in).

THE GUARD'S OWN DIRECTIONS (MAIN-INFRA-E5-GUARDDIR-20261029, after the 4F strict guard failed on 328 px: rule (d)
removed 20 sites whose fronts the 128-direction census called hidden and the seam view did not see, but which the
eight below-oblique guard views hit, 0.65-62 in in front of the next surface; `diagnosis-below-oblique.json`). Every
face of an opposite pair is ALSO tested along the strict guard's 26 view directions, both signs (52), with
`engine.vis.guard_exposure.guard_visibility`: 10 sample points per face (the census's 4 plus near-corner and
edge-mid) cast from the front, plus the guard's own orthographic pixel grid at `profile.guard_size` (and 2x) in
every view, counting the pixels each face owns from its front and from its back. A face the guard sees is never
called hidden: rule (c) drops a twin only when its front is hidden in BOTH tests (and its winner is exposed in
either); rule (d) plans a seam only when neither face is seen by the census, the guard (front OR back: a pixel
whose first hit is the face changes when it goes, whichever side) or the seam view. A face the census called
hidden but the guard sees is kept `guard_seen` (`kept.guard_seen`, with `guard_front` / `guard_back` on its row).
`report["exposure_n_dirs"]` stays the census's 128; `report["exposure_directions_total"]` is 128 + 52;
`report["guard_exposure"]` records `views`, `directions`, `samples_per_face`, `pixel_grid`, `faces_tested`,
`seen_front`, `seen_back_only`, `census_hidden_guard_seen` and `seconds`.

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
from typing import Any, Callable

import numpy as np
import shapely

from engine.fixes.overlap import double_layers
from engine.fixes.pipeline import guard_depth_tol
from engine.guard.views import VIEWS_26
from engine.vis.exposure import compute_side_exposure
from engine.vis.guard_exposure import guard_visibility
from engine.pipeline import analyse_topology, flat_material_indices
from engine.repair.engines.e3_hidden import DENSE_POINTS_PER_FACE, MAX_SITE_FACES, _components, split_group
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
RULES = ("same_look", "priority", "larger_area", "backface_twin", "interior_twins")
KEPT_REASONS = ("uncovered", "no_winner", "both_exposed", "no_backface_winner", "guard_seen", "anchored",
                "only_coverage", "no_overlap", "seam_seen", "seam_unverified", "covers_prior_removal")
#: How many kept opposite pairs `report["kept_pairs"]` lists (all are counted in `kept_pairs_total`).
KEPT_PAIRS_LISTED = 500


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
    #: Rule d's visibility test: `seam_view(mesh, faces)` gives per face how many points the Validator's viewpoints see
    #: (None: the site judge's `lattice_seen` at `DENSE_POINTS_PER_FACE` points plus `probe_seen`, from
    #: `ctx.validator`; with neither, no seam is planned: `seam_unverified`).
    seam_view: Callable[[Any, np.ndarray], Any] | None = None
    #: The triangles (k, 3, 3 corners, engine frame) an EARLIER stage of the chain removed (E3's, read from the
    #: baseline through the E3 candidate's `source-faces.json`): a face is dropped only while every such triangle on
    #: its plane that overlaps its footprint stays covered 98 % by faces kept after the drop (`covers_prior_removal`
    #: otherwise). Real 7F replay round 1: E3-removed faces had stayed covered by a coincident pair, E5 dropped the pair
    #: as an interior seam, and nothing covered them any more.
    prior_removed: Any = None
    #: Site ids (this engine's numbering on this input) NOT to plan: the replay loop's E5 exclusions.
    exclude_sites: set | None = None
    report: dict | None = field(default=None, repr=False)

    def _seam_view(self, ctx: RepairContext):
        if self.seam_view is not None:
            return self.seam_view
        lattice = getattr(ctx.validator, "lattice_seen", None)
        probes = getattr(ctx.validator, "probe_seen", None)
        if lattice is None or probes is None:
            return None

        def view(mesh, faces):
            dense = lattice(mesh, faces, DENSE_POINTS_PER_FACE)
            dense = dense["any"] if isinstance(dense, dict) else dense
            return np.asarray(dense, np.int64) + np.asarray(probes(mesh, faces), np.int64)
        return view

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

        # ---- and along the strict guard's own 26 view directions (both signs) and its own pixel grid: a face the
        # guard can see is never called hidden (4F, 2026-10-29: 20 seams visible only from the below-oblique views)
        t0 = time.perf_counter()
        guard = None
        opposite_faces = np.array(sorted({f for pair in opposite_of for f in pair}), np.int64)
        if len(opposite_faces):
            guard = guard_visibility(pos - centre, faces, ok, opposite_faces, views=VIEWS_26, size=profile.guard_size)
        seconds["guard_exposure"] = time.perf_counter() - t0
        guard_front = {int(f): (int(guard["front"][f]) if guard is not None else 0) for f in opposite_faces.tolist()}
        guard_back = {int(f): (int(guard["back"][f]) if guard is not None else 0) for f in opposite_faces.tolist()}

        def guard_seen(f: int) -> bool:
            return guard_front.get(f, 0) > 0 or guard_back.get(f, 0) > 0

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
        for f in involved:
            guard_front.setdefault(f, 0)
            guard_back.setdefault(f, 0)
        dropped: dict[int, dict] = {}
        kept_rows: list[dict] = []
        kept_counts = {k: 0 for k in KEPT_REASONS}
        anchored: set[int] = set()
        interior: set[int] = set()                            # faces dropped by rule (d): exempt from the cover check
        interior_pairs: list[tuple[int, int]] = []            # the seams, so both faces travel in one site
        kept_pairs: list[dict] = []                           # the audit sample of kept opposite pairs
        kept_pair_keys: set[tuple[int, int]] = set()
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
                if f in dropped:
                    continue                                  # taken as the partner of an interior seam
                others = [g for g in overlaps[f] if g in poly and g not in dropped]
                if not others:
                    kept_counts["no_overlap"] += 1
                    continue
                winners = [g for g in others if self._beats(g, f, area, look_of, prio_of, opposite_of, exposure,
                                                           guard_front)]
                if not winners:
                    opposite_only = all((g, f) in opposite_of for g in others)
                    f_front = exposure[f][0]
                    census_hidden = f_front is not None and f_front <= 0.0
                    if opposite_only and census_hidden and not guard_seen(f) and f not in anchored:
                        # rule (d), interior_twins: a back-to-back pair BOTH of whose fronts are hidden -- from the
                        # census's directions and from the strict guard's own -- is an interior block-against-block
                        # seam; both faces go, as one site, and the judge decides
                        partners = [g for g in others if exposure[g][0] <= 0.0 and not guard_seen(g)
                                    and g not in anchored]
                        if partners:
                            seam = [f] + partners
                            for h in seam:
                                mates = [g for g in seam if g != h]
                                dropped[h] = {"face": int(h), "material": int(material[h]), "look": look_of[h],
                                              "area": round(float(area[h]), 4), "winners": [int(g) for g in mates],
                                              "winner_looks": [look_of[g] for g in mates],
                                              "winner_areas": [round(float(area[g]), 4) for g in mates],
                                              "front": exposure[h][0], "back": exposure[h][1],
                                              "guard_front": guard_front[h], "guard_back": guard_back[h],
                                              "winner_front": [exposure[g][0] for g in mates],
                                              "winner_back": [exposure[g][1] for g in mates],
                                              "overlap_fraction": round(self._coverage(poly[h], [poly[g] for g in mates]), 6),
                                              "rule": "interior_twins"}
                                interior.add(h)
                            for h in seam[1:]:
                                interior_pairs.append((min(f, h), max(f, h)))
                            continue
                    if opposite_only and census_hidden and guard_seen(f):
                        reason = "guard_seen"                 # the census called it hidden; the guard's directions see it
                    elif opposite_only and f_front is not None and (f_front > 0.0 or guard_front[f] > 0) \
                            and all(exposure[g][0] > 0.0 or guard_front[g] > 0 for g in others):
                        reason = "both_exposed"               # a legitimate two-sided zero-thickness slab
                    elif opposite_only:
                        reason = "no_backface_winner"
                    else:
                        reason = "no_winner"
                    kept_counts[reason] += 1
                    kept_rows.append(self._kept_row(f, reason, others,
                                                    self._coverage(poly[f], [poly[g] for g in others]), look_of, area,
                                                    exposure, guard_front, guard_back))
                    if opposite_only:
                        for g in others:
                            key = (min(f, g), max(f, g))
                            if key not in kept_pair_keys:
                                kept_pair_keys.add(key)
                                kept_pairs.append({"faces": [key[0], key[1]], "looks": [look_of[key[0]], look_of[key[1]]],
                                                   "front": [exposure[key[0]][0], exposure[key[1]][0]],
                                                   "back": [exposure[key[0]][1], exposure[key[1]][1]],
                                                   "reason": reason})
                    continue
                cover = self._coverage(poly[f], [poly[g] for g in winners])
                if f in anchored:
                    kept_counts["anchored"] += 1
                    kept_rows.append(self._kept_row(f, "anchored", winners, cover, look_of, area, exposure,
                                                    guard_front, guard_back))
                    continue
                if cover < self.cover_fraction:
                    kept_counts["uncovered"] += 1
                    kept_rows.append(self._kept_row(f, "uncovered", winners, cover, look_of, area, exposure,
                                                    guard_front, guard_back))
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
                              "guard_front": guard_front[f], "guard_back": guard_back[f],
                              "winner_front": [exposure[g][0] for g in winners],
                              "winner_back": [exposure[g][1] for g in winners],
                              "overlap_fraction": round(cover, 6), "rule": rule}
                anchored.update(winners)
                group_dropped.append(f)
            # the final check: every dropped face is still covered 98 % by the faces of its plane that stay
            kept_in_group = [g for g in members if g not in dropped]
            for f in group_dropped:
                if f in interior:
                    continue                                  # an interior seam is removed whole: the judge decides
                cover = self._coverage(poly[f], [poly[g] for g in kept_in_group if g in overlaps[f]])
                if cover < self.cover_fraction:
                    row = dropped.pop(f)
                    kept_counts["only_coverage"] += 1
                    kept_rows.append({**row, "kept": "only_coverage", "kept_overlap_fraction": round(cover, 6)})
        seconds["decide"] = time.perf_counter() - t0

        # ---- sites: edge-connected groups of the dropped faces, a big one split by a spatial grid
        # ---- rule (d)'s visibility test: a seam is planned only when the Validator's own viewpoints see neither face
        # (7F chain run #2: the census called 3,738 seam faces hidden, the judge saw 18,191 of their samples)
        t0 = time.perf_counter()
        interior_filtered = {"seams": len(interior_pairs), "seen": 0, "unverified": 0, "planned": 0}
        if interior_pairs:
            view = self._seam_view(ctx)
            seam_faces = np.array(sorted(interior), np.int64)
            points_seen: dict[int, int | None] = {int(f): None for f in seam_faces.tolist()}
            if view is not None:
                counts = np.asarray(view(mesh, seam_faces), np.int64)
                if counts.shape != seam_faces.shape:
                    raise ValueError(f"E5: seam_view gave {counts.shape} values for {seam_faces.shape} faces")
                points_seen = {int(f): int(c) for f, c in zip(seam_faces.tolist(), counts.tolist())}
            unplanned: dict[int, str] = {}
            kept_pairs_d: list[tuple[int, int]] = []
            for a, b in interior_pairs:
                if view is None:
                    reason = "seam_unverified"
                    interior_filtered["unverified"] += 1
                elif points_seen[a] > 0 or points_seen[b] > 0:
                    reason = "seam_seen"
                    interior_filtered["seen"] += 1
                else:
                    interior_filtered["planned"] += 1
                    kept_pairs_d.append((a, b))
                    continue
                for h in (a, b):
                    unplanned[h] = reason if unplanned.get(h) != "seam_seen" else "seam_seen"
            # a face of a seen or unverified seam stays, and so does every partner of its seams (never one face alone)
            changed = True
            while changed:
                changed = False
                for a, b in interior_pairs:
                    if (a in unplanned) != (b in unplanned):
                        h, other = (b, a) if a in unplanned else (a, b)
                        unplanned[h] = unplanned[other]
                        changed = True
            for h, reason in sorted(unplanned.items()):
                if h in dropped:
                    row = dropped.pop(h)
                    kept_counts[reason] += 1
                    kept_rows.append({**row, "kept": reason, "points_seen": points_seen[h]})
            interior_pairs = [(a, b) for a, b in kept_pairs_d if a not in unplanned and b not in unplanned]
            interior = {f for pair in interior_pairs for f in pair}
        seconds["seam_view"] = time.perf_counter() - t0

        # ---- the only-coverage rule extended to the prior stage's removals: a drop may not uncover a triangle an
        # earlier stage removed on the same plane (its cover was this pair); a refused seam face takes its partners
        t0 = time.perf_counter()
        prior_report = {"triangles": 0, "faces_checked": 0, "faces_refused": 0}
        if self.prior_removed is not None and dropped:
            P = np.asarray(self.prior_removed, float).reshape(-1, 3, 3)
            prior_report["triangles"] = int(len(P))
            checked: set[int] = set()
            if len(P):
                p_lo, p_hi = P.min(axis=1), P.max(axis=1)
                f_lo, f_hi = tri.min(axis=1), tri.max(axis=1)
                while True:
                    refused = None
                    for f in sorted(dropped):
                        checked.add(f)
                        n_f, c = normal[f], tri[f].mean(axis=0)
                        coplanar = np.abs((P - c) @ n_f).max(axis=1) <= depth_tol
                        near_f = (p_hi >= f_lo[f] - depth_tol).all(axis=1) & (p_lo <= f_hi[f] + depth_tol).all(axis=1)
                        idx = np.flatnonzero(coplanar & near_f)
                        if not len(idx):
                            continue
                        e1, e2 = plane_basis(n_f)
                        basis = np.stack([e1, e2], axis=1)
                        poly_f = shapely.Polygon((tri[f] - c) @ basis)
                        on_plane = np.flatnonzero((np.abs((tri - c) @ n_f).max(axis=1) <= depth_tol) & ok)
                        on_plane = [int(g) for g in on_plane.tolist() if int(g) not in dropped]
                        worst = None
                        for k in idx.tolist():
                            poly_p = shapely.Polygon((P[k] - c) @ basis)
                            if poly_p.area <= 0 or shapely.intersection(poly_p, poly_f).area <= 1e-6:
                                continue
                            near = [g for g in on_plane if (f_hi[g] >= p_lo[k] - depth_tol).all()
                                    and (f_lo[g] <= p_hi[k] + depth_tol).all()]
                            cover = self._coverage(poly_p, [shapely.Polygon((tri[g] - c) @ basis) for g in near])
                            if cover < self.cover_fraction:
                                worst = cover if worst is None else min(worst, cover)
                        if worst is not None:
                            refused = (f, worst)
                            break
                    if refused is None:
                        break
                    f, cover = refused
                    group = {f}
                    changed = True
                    while changed:                            # never one face of a seam alone
                        changed = False
                        for a, b in interior_pairs:
                            if (a in group) != (b in group):
                                group |= {a, b}
                                changed = True
                    for h in sorted(group):
                        if h in dropped:
                            row = dropped.pop(h)
                            kept_counts["covers_prior_removal"] += 1
                            prior_report["faces_refused"] += 1
                            kept_rows.append({**row, "kept": "covers_prior_removal", "prior_cover": round(cover, 6)})
                    interior_pairs = [(a, b) for a, b in interior_pairs if a not in group and b not in group]
                    interior = {x for pair in interior_pairs for x in pair}
            prior_report["faces_checked"] = len(checked)
        seconds["prior_removed"] = time.perf_counter() - t0

        candidates = np.array(sorted(dropped), np.int64)
        centroid = tri.mean(axis=1)
        comps = _components(faces, candidates)
        if interior_pairs:
            # both faces of an interior seam travel in one site, whether or not their vertices are welded together
            owner = {int(f): k for k, members in enumerate(comps) for f in members.tolist()}
            merged = _union_find(len(comps), [(owner[a], owner[b]) for a, b in interior_pairs
                                              if a in owner and b in owner and owner[a] != owner[b]])
            comps = [np.sort(np.concatenate([comps[k] for k in group])) for group in merged]
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

        # ---- the replay loop's exclusions: sites NOT to plan (numbering kept, so the ids stay stable between runs)
        excluded_sites = sorted(int(s) for s in (self.exclude_sites or ()))
        excluded_faces: list[int] = []
        if excluded_sites:
            taken = set(excluded_sites)
            excluded_faces = sorted(f for e in edits if e.site in taken for f in e.faces)
            edits = [e for e in edits if e.site not in taken]
        self.report = {
            "pairs": pair_counts, "depth_tol": float(depth_tol), "facing_dot": float(self.facing_dot),
            "prior_removed": prior_report, "excluded_sites": excluded_sites, "excluded_faces": excluded_faces,
            "cover_fraction": float(self.cover_fraction), "cull_opposite_backfaces": bool(self.cull_opposite_backfaces),
            "exposure_n_dirs": int(profile.n_dirs) if front is not None else None,
            "exposure_directions_total": (int(profile.n_dirs) + int(guard["directions"])) if guard is not None else None,
            "guard_exposure": None if guard is None else {
                "views": int(guard["views"]), "directions": int(guard["directions"]),
                "samples_per_face": int(guard["samples_per_face"]), "pixel_grid": guard["pixel_grid"],
                "faces_tested": int(len(opposite_faces)),
                "seen_front": int(sum(1 for f in opposite_faces.tolist() if guard_front[f] > 0)),
                "seen_back_only": int(sum(1 for f in opposite_faces.tolist()
                                          if guard_front[f] == 0 and guard_back[f] > 0)),
                "census_hidden_guard_seen": int(sum(1 for f in opposite_faces.tolist()
                                                    if float(front[f]) <= 0.0 and guard_seen(f))),
                "seconds": round(seconds["guard_exposure"], 2)},
            "flat_materials": sorted(int(m) for m in flat),
            "faces_in_pairs": len(involved), "groups": sum(1 for g in groups if len(g) > 1),
            "dropped": len(dropped),
            "by_rule": {r: sum(1 for row in dropped.values() if row["rule"] == r) for r in RULES},
            "kept": kept_counts, "kept_faces": kept_rows,
            "kept_pairs": kept_pairs[:KEPT_PAIRS_LISTED], "kept_pairs_total": len(kept_pairs),
            "interior_filtered": interior_filtered,
            "planned": [list(e.faces) for e in edits], "sites": len(edits), "connected_groups": len(comps),
            "groups_split": split, "max_site_faces": int(self.max_site_faces),
            "seconds": {**{k: round(v, 2) for k, v in seconds.items()},
                        "total": round(time.perf_counter() - started, 2)},
        }
        return edits

    @staticmethod
    def _beats(g: int, f: int, area, look_of, prio_of, opposite_of, exposure, guard_front=None) -> bool:
        """Does the kept face `g` beat `f`? A back-to-back pair (rule c, `backface_twin`): `g` wins iff `f`'s front
        is hidden from the census's directions AND from the strict guard's own (`guard_front`, front hits per face,
        0 when absent), and `g`'s front is seen by either, whatever the looks. A same-facing pair: the module
        docstring's rules a and b."""
        if (g, f) in opposite_of:
            f_front, g_front = exposure[f][0], exposure[g][0]
            guard_front = guard_front or {}
            return (f_front is not None and g_front is not None and f_front <= 0.0 and guard_front.get(f, 0) == 0
                    and (g_front > 0.0 or guard_front.get(g, 0) > 0))
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
    def _kept_row(f, reason, others, cover, look_of, area, exposure, guard_front=None, guard_back=None) -> dict:
        guard_front, guard_back = guard_front or {}, guard_back or {}
        return {"face": int(f), "look": look_of[f], "area": round(float(area[f]), 4), "kept": reason,
                "winners": [int(g) for g in others], "winner_looks": [look_of[g] for g in others],
                "front": exposure[f][0], "back": exposure[f][1],
                "guard_front": int(guard_front.get(f, 0)), "guard_back": int(guard_back.get(f, 0)),
                "winner_front": [exposure[g][0] for g in others],
                "overlap_fraction": round(float(cover), 6)}
