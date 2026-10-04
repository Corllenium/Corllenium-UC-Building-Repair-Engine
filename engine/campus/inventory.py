"""Campus inventory (spec 2026-10-03, P0 task 10): buildings, a level table per building, floor and element
units, duplicate groups, misnamed and missing levels. Everything is a draft for the owner to confirm; nothing
here writes geometry.
"""
from __future__ import annotations

import collections
import hashlib
import itertools
import re
from dataclasses import asdict, dataclass

import numpy as np

from engine.model import MeshData

# The brief's prefix table, verbatim. A name belongs to the building whose prefix it starts with, followed
# by an underscore or the end of the name; matching ignores case and the longest prefix wins (so
# `Main_Infrustructure_*` is MAIN_INFRA, not MAIN).
PREFIX_TABLE: tuple[tuple[tuple[str, ...], str], ...] = (
    (("CHTM", "Chtm", "chtm"), "CHTM"),
    (("EDS", "Eds"), "EDS"),
    (("BRS",), "BRS"),
    (("Gymnasium",), "GYMNASIUM"),
    (("Main_Infrustructure",), "MAIN_INFRA"),
    (("MAIN", "Main"), "MAIN"),
    (("PE",), "PE"),
    (("Sciene_A",), "SCIENCE_A"),
    (("Architecture", "ARCHITECTURE"), "ARCHITECTURE"),
)
SITE = "SITE"

_PREFIXES = sorted(((p.casefold(), b) for ps, b in PREFIX_TABLE for p in ps), key=lambda pb: -len(pb[0]))


def building_of(name: str) -> str:
    """The building a split name belongs to (SITE when no prefix matches)."""
    low = name.casefold()
    for prefix, building in _PREFIXES:
        if low == prefix or low.startswith(prefix + "_"):
            return building
    return SITE


# `1st`, `2nd`, `3RD`, `4th`, and the owner's `5ft` / `6ft` typos for `5th` / `6th`.
_ORDINAL = re.compile(r"(?<![A-Za-z0-9])(\d{1,2})(?:st|nd|rd|th|ft)(?![A-Za-z])", re.I)
# `Floor 4`, `Floor_4`, `Floor_plan_2`, `plan 2`.
_PLAN = re.compile(r"(?:floor|plan)[ _]*(\d{1,2})(?!\d)", re.I)


def floor_number(name: str) -> int | None:
    """The floor number a group's name claims, or None."""
    m = _ORDINAL.search(name) or _PLAN.search(name)
    return int(m.group(1)) if m else None


# ------------------------------------------------------------------------------------------ constants

@dataclass(frozen=True)
class InventoryParams:
    """Every constant of the inventory. The defaults are the brief's, except where the real CKPT17 data
    showed the brief's value cannot work (each such default says so; the report has the measurements)."""
    # histogram and peaks (the brief)
    bin_in: float = 1.0               # z bins of 1 in
    flat_nz: float = 0.9              # up/down-facing: n_z > 0.9 / n_z < -0.9
    peak_frac: float = 0.15           # a peak is at least 15 % of the largest peak
    merge_in: float = 20.0            # peaks within 20 in merge (the strongest stays)
    # slab pairing
    slab_window_in: float = 48.0      # brief: 24. CKPT17 slabs are 1 block (39.4 in) or half a block thick
    base_pick: str = "lowest"         # brief: "nearest". Stepped slabs have a second underside 30 in up
    min_slab_in: float = 1.0          # a slab is at least one bin thick (same-plane up and down are no slab)
    min_storey_in: float = 100.0      # brief: only the 20 in merge. 1 block terraces and thin layers sit 39 in apart
    # bands and units
    band_slack_in: float = 1.0        # a band starts one bin below its base (the base is a bin's mean z)
    part_coverage: float = 0.80       # the fewest bands holding 80 % of a group's triangles are its parts
    # duplicates
    dup_flag: float = 0.25            # flag a Jaccard similarity of at least 0.25 (the brief)
    match_tol_in: float = 0.5         # brief: the print step. The CKPT17 copies sit 0.03-0.4 in off (identity only)


BRIEF_PARAMS = InventoryParams(slab_window_in=24.0, base_pick="nearest", min_storey_in=20.0, match_tol_in=0.0)


# ------------------------------------------------------------------------------------------ groups

@dataclass
class GroupData:
    """What the inventory keeps of one split OBJ (one SketchUp group family)."""
    name: str
    building: str
    tris: int
    paths: list[int]
    sha256: str
    file: str
    bbox: np.ndarray        # (2, 3) min and max of the vertices
    cz: np.ndarray          # (tris,) face-centre z
    area: np.ndarray        # (tris,)
    nz: np.ndarray          # (tris,) z of the unit normal (0 for a degenerate face)
    pos: np.ndarray         # (verts, 3)
    fv: np.ndarray          # (tris, 3) vertex indices
    look: np.ndarray        # (tris,) look hash (0 = no material)
    decimals: int


def _look_hash(key: str) -> int:
    return int.from_bytes(hashlib.blake2b(key.encode("utf-8"), digest_size=7).digest(), "big") + 1


def load_group(name: str, mesh: MeshData, looks: dict[str, str] | None = None, paths=(), sha256: str = "",
               file: str = "") -> GroupData:
    """Reduce one split mesh to what the inventory needs. `looks` maps a material name to its look key
    (materials.json); an unknown material is its own look."""
    pos = np.asarray(mesh.positions, float).reshape(-1, 3)
    fv = np.asarray(mesh.face_v, np.int64).reshape(-1, 3)
    tri = pos[fv]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(cross, axis=1)
    nz = np.divide(cross[:, 2], length, out=np.zeros_like(length), where=length > 0)
    hashes = np.array([_look_hash((looks or {}).get(m, f"material:{m}")) for m in mesh.materials] + [0], np.int64)
    bbox = np.array([pos.min(axis=0), pos.max(axis=0)]) if len(pos) else np.zeros((2, 3))
    return GroupData(name=name, building=building_of(name), tris=int(len(fv)), paths=[int(p) for p in paths],
                     sha256=sha256, file=file or f"{name}.obj", bbox=bbox, cz=tri[:, :, 2].mean(axis=1),
                     area=length / 2.0, nz=nz, pos=pos, fv=fv.astype(np.int32),
                     look=hashes[np.asarray(mesh.face_material, np.int64)], decimals=int(mesh.coord_decimals))


# ------------------------------------------------------------------------------------------ level table

@dataclass(frozen=True)
class Slab:
    base: float         # the slab bottom: mean z of the down-facing peak
    top: float          # the slab top: mean z of the up-facing peak
    strength: float     # the weaker of the two peaks, as a share of the building's largest peak


def _merge_peaks(peaks: list[tuple[float, float]], radius: float) -> list[tuple[float, float]]:
    """Peaks within `radius` of a stronger one merge into it."""
    keep: list[tuple[float, float]] = []
    for z, a in sorted(peaks, key=lambda t: (-t[1], t[0])):
        if all(abs(z - kz) > radius for kz, _ in keep):
            keep.append((z, a))
    return sorted(keep)


def _histogram_peaks(z: np.ndarray, w: np.ndarray, p: InventoryParams) -> tuple[list[tuple[float, float]], float]:
    """Peaks of the area histogram over z: (mean z of the bin, area of the bin), and the largest bin."""
    if z.size == 0 or float(w.sum()) <= 0:
        return [], 0.0
    idx = np.floor(z / p.bin_in).astype(np.int64)
    lo = int(idx.min())
    n = int(idx.max()) - lo + 1
    h = np.bincount(idx - lo, weights=w, minlength=n)
    zs = np.bincount(idx - lo, weights=w * z, minlength=n)
    top = float(h.max())
    left = np.concatenate(([-1.0], h[:-1]))
    right = np.concatenate((h[1:], [-1.0]))
    cand = np.nonzero((h >= left) & (h > right) & (h >= p.peak_frac * top))[0]
    return _merge_peaks([(float(zs[i] / h[i]), float(h[i])) for i in cand], p.merge_in), top


def slab_table(groups: list[GroupData], p: InventoryParams) -> list[Slab]:
    """The slabs of one building, lowest first: an up-facing peak (the top) with a down-facing peak (the
    bottom) just below it. Slabs closer than `min_storey_in` collapse, the strongest staying."""
    up_z = np.concatenate([g.cz[g.nz > p.flat_nz] for g in groups])
    up_w = np.concatenate([g.area[g.nz > p.flat_nz] for g in groups])
    dn_z = np.concatenate([g.cz[g.nz < -p.flat_nz] for g in groups])
    dn_w = np.concatenate([g.area[g.nz < -p.flat_nz] for g in groups])
    ups, up_top = _histogram_peaks(up_z, up_w, p)
    downs, dn_top = _histogram_peaks(dn_z, dn_w, p)
    by_base: dict[float, Slab] = {}
    for zt, at in ups:
        cands = [(zb, ab) for zb, ab in downs if p.min_slab_in <= zt - zb <= p.slab_window_in]
        if not cands:
            continue
        zb, ab = min(cands) if p.base_pick == "lowest" else max(cands)
        s = Slab(zb, zt, min(at / up_top, ab / dn_top))
        if zb not in by_base or s.strength > by_base[zb].strength:
            by_base[zb] = s
    keep: list[Slab] = []
    for s in sorted(by_base.values(), key=lambda s: (-s.strength, s.base)):
        if all(abs(s.base - k.base) > p.min_storey_in for k in keep):
            keep.append(s)
    return sorted(keep, key=lambda s: s.base)


# ------------------------------------------------------------------------------------------ bands and parts

def band_counts(cz: np.ndarray, bases: list[float], p: InventoryParams) -> np.ndarray:
    """Triangles per band by face-centre z. Band 0 lies below the first base; band j starts `band_slack_in`
    below base j and runs to the next band; the last band is open above."""
    edges = np.asarray(bases, float) - p.band_slack_in
    return np.bincount(np.searchsorted(edges, cz, side="right"), minlength=len(edges) + 1)


def group_parts(counts: np.ndarray, coverage: float) -> list[int]:
    """The fewest bands (by triangle count) that hold `coverage` of the triangles, lowest first. One part
    is a floor group; more are a group that spans floors. The rest are wall caps and edge noise."""
    total = int(counts.sum())
    if total == 0:
        return [0]
    chosen: list[int] = []
    acc = 0
    for j in sorted(range(len(counts)), key=lambda j: (-int(counts[j]), j)):
        chosen.append(j)
        acc += int(counts[j])
        if acc >= coverage * total:
            break
    return sorted(chosen)


def band_owners(nbands: int, parts: list[int]) -> list[int]:
    """For every band, the part that owns its triangles: the nearest part (the lower one on a tie)."""
    return [min(parts, key=lambda c: (abs(j - c), c)) for j in range(nbands)]


# Groups with one of these words that span more than one band are elements (stairs, bridges, roofs, zones,
# shells, ground pieces, pathways, roads), not floors.
ELEMENT_WORDS = re.compile(r"stair|bridge|roof|zone|shell|ground|pathway|road", re.I)


def is_element(name: str, parts: list[int]) -> bool:
    return len(parts) > 1 and bool(ELEMENT_WORDS.search(name))


@dataclass
class BuildingPlan:
    """The level table of one building and how its groups sit in it."""
    name: str
    groups: list[GroupData]
    slabs: list[Slab]                     # the settled table: every band above the first is occupied
    counts: dict[str, np.ndarray]         # group -> triangles per band
    parts: dict[str, list[int]]           # group -> its part bands
    bands: list[int]                      # the bands that are levels, lowest first (band 0 only if occupied)
    elements: set[str]                    # groups that are element units, not floors


def plan_building(name: str, groups: list[GroupData], p: InventoryParams) -> BuildingPlan:
    """Detect the slabs, then drop the slabs whose band no floor group occupies (a band nobody holds is no
    level; it merges into the band below). Elements never make a level."""
    slabs = slab_table(groups, p)
    while True:
        bases = [s.base for s in slabs]
        counts = {g.name: band_counts(g.cz, bases, p) for g in groups}
        parts = {g.name: group_parts(counts[g.name], p.part_coverage) for g in groups}
        elements = {n for n, ps in parts.items() if is_element(n, ps)}
        occupied = {j for n, ps in parts.items() if n not in elements for j in ps}
        empty = [j for j in range(1, len(slabs) + 1) if j not in occupied]
        if not empty:
            break
        del slabs[empty[0] - 1]
    bands = ([0] if 0 in occupied else []) + list(range(1, len(slabs) + 1))
    return BuildingPlan(name, groups, slabs, counts, parts, bands, elements)


def _r(x: float) -> float:
    return round(float(x), 2)


def name_votes(plan: BuildingPlan) -> list[int]:
    """For every floor group that sits in one band and names a floor: the floor it names minus the ordinal
    of its band (counted from the lowest level)."""
    ordinal = {band: i + 1 for i, band in enumerate(plan.bands)}
    votes = []
    for g in plan.groups:
        parts = plan.parts[g.name]
        n = floor_number(g.name)
        if n is not None and len(parts) == 1 and g.name not in plan.elements:
            votes.append(n - ordinal[parts[0]])
    return votes


def anchor_offset(votes: list[int]) -> tuple[int, int]:
    """(offset, groups agreeing). The level numbers start above 1 only when a strict majority of the named
    floor groups agree on the same positive offset (Science A's floors are all named one above their band);
    a tie, a minority or a negative offset leaves the numbering from the lowest band."""
    if not votes:
        return 0, 0
    counts = collections.Counter(votes)
    best, n = max(counts.items(), key=lambda kv: (kv[1], -abs(kv[0])))
    if best > 0 and 2 * n > len(votes):
        return best, n
    return 0, counts.get(0, 0)


def level_records(plan: BuildingPlan, p: InventoryParams, offset: int = 0) -> list[dict]:
    """One record per level, lowest first: its number, base, top, slab and triangles. Level numbers count
    from the lowest band, plus the anchoring `offset` the names agree on."""
    nbands = len(plan.slabs) + 1
    tris = dict.fromkeys(plan.bands, 0)
    lowest = np.inf
    highest = -np.inf
    for g in plan.groups:
        owner = band_owners(nbands, plan.parts[g.name])
        for j, c in enumerate(plan.counts[g.name]):
            if g.name not in plan.elements:
                tris[owner[j]] = tris.get(owner[j], 0) + int(c)
        bases = [s.base for s in plan.slabs]
        idx = np.searchsorted(np.asarray(bases, float) - p.band_slack_in, g.cz, side="right")
        if 0 in plan.bands and (idx == 0).any():
            lowest = min(lowest, float(g.cz[idx == 0].min()))
        if (idx == nbands - 1).any():
            highest = max(highest, float(g.cz[idx == nbands - 1].max()))
    out = []
    for i, j in enumerate(plan.bands):
        slab = plan.slabs[j - 1] if j >= 1 else None
        base = slab.base if slab else lowest
        top = plan.slabs[j].base if j < len(plan.slabs) else highest
        out.append({"level": f"L{i + 1 + offset:02d}", "band": j, "base": _r(base), "top": _r(top),
                    "slab": {"bottom": _r(slab.base), "top": _r(slab.top)} if slab else None,
                    "tris": tris[j]})
    return out


# ------------------------------------------------------------------------------------------ duplicates

def _link_pairs(pts: np.ndarray, eps: float) -> tuple[np.ndarray, np.ndarray]:
    """Index pairs (i < j) of points at most `eps` apart, by a grid hash with cells of `eps`."""
    cell = np.floor(pts / eps).astype(np.int64)
    cell -= cell.min(axis=0)
    dims = cell.max(axis=0) + 3

    def flat(k: np.ndarray) -> np.ndarray:
        return ((k[:, 0] + 1) * dims[1] + (k[:, 1] + 1)) * dims[2] + (k[:, 2] + 1)

    key = flat(cell)
    order = np.argsort(key, kind="stable")
    sorted_key = key[order]
    ii: list[np.ndarray] = [np.zeros(0, np.int64)]
    jj: list[np.ndarray] = [np.zeros(0, np.int64)]
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                tgt = flat(cell + np.array([dx, dy, dz]))
                lo = np.searchsorted(sorted_key, tgt, "left")
                hi = np.searchsorted(sorted_key, tgt, "right")
                for k in range(int((hi - lo).max())):
                    idx = np.nonzero(hi - lo > k)[0]
                    j = order[lo[idx] + k]
                    keep = idx < j
                    idx, j = idx[keep], j[keep]
                    near = ((pts[idx] - pts[j]) ** 2).sum(axis=1) <= eps * eps
                    ii.append(idx[near])
                    jj.append(j[near])
    return np.concatenate(ii), np.concatenate(jj)


def _components(n: int, ii: np.ndarray, jj: np.ndarray) -> np.ndarray:
    """Connected-component label (the smallest member index) of every node."""
    lab = np.arange(n)
    while ii.size:
        m = np.minimum(lab[ii], lab[jj])
        new = lab.copy()
        np.minimum.at(new, ii, m)
        np.minimum.at(new, jj, m)
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    return lab


def _face_sets(groups: list[GroupData], tol_in: float) -> dict[str, np.ndarray]:
    """Per group, the ids of its distinct faces. A face is its three vertices, sorted, plus its winding and
    its look key. A vertex is the position snapped to the print step; with `tol_in` > 0, vertices closer than
    that also count as one (identity only: no geometry is touched)."""
    dec = max(g.decimals for g in groups)
    scale = 10.0 ** dec
    snapped = np.concatenate([np.rint(g.pos * scale) for g in groups]).astype(np.int64)
    uniq, inverse = np.unique(snapped, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    if tol_in > 0:
        label = _components(len(uniq), *_link_pairs(uniq / scale, tol_in))
    else:
        label = np.arange(len(uniq))
    vid = label[inverse]
    keys, start = [], 0
    for g in groups:
        ids = vid[start:start + len(g.pos)][g.fv]
        start += len(g.pos)
        order = np.argsort(ids, axis=1, kind="stable")
        sorted_ids = np.take_along_axis(ids, order, axis=1)
        even = (((order[:, 0] == 0) & (order[:, 1] == 1)) | ((order[:, 0] == 1) & (order[:, 1] == 2))
                | ((order[:, 0] == 2) & (order[:, 1] == 0)))
        keys.append(np.column_stack([sorted_ids, (~even).astype(np.int64), g.look]))
    _, face_id = np.unique(np.concatenate(keys), axis=0, return_inverse=True)
    face_id = face_id.reshape(-1)
    out, start = {}, 0
    for g, k in zip(groups, keys):
        out[g.name] = np.unique(face_id[start:start + len(k)])
        start += len(k)
    return out


def _jaccard(a: np.ndarray, b: np.ndarray) -> tuple[float, int]:
    shared = int(np.intersect1d(a, b, assume_unique=True).size)
    union = a.size + b.size - shared
    return (shared / union if union else 0.0), shared


def duplicate_flags(groups: list[GroupData], p: InventoryParams) -> list[dict]:
    """Pairs of groups of one building whose faces overlap: Jaccard similarity of the face fingerprints,
    flagged from `dup_flag`. `exact_jaccard` is the same at the print step alone: the CKPT17 copies (Science A,
    BRS obj1) sit 0.03-0.4 in off their originals, so they only match with a tolerance."""
    if len(groups) < 2:
        return []
    tolerant = _face_sets(groups, p.match_tol_in)
    exact = tolerant if p.match_tol_in <= 0 else _face_sets(groups, 0.0)
    out = []
    for a, b in itertools.combinations(groups, 2):
        j, shared = _jaccard(tolerant[a.name], tolerant[b.name])
        if j < p.dup_flag:
            continue
        ex_j, _ = _jaccard(exact[a.name], exact[b.name])
        sizes = [int(tolerant[a.name].size), int(tolerant[b.name].size)]
        of_smaller = shared / min(sizes)
        match = "exact" if ex_j >= p.dup_flag else "shifted"
        how = ("coincident at the print step" if match == "exact"
               else f"copies shifted by less than {p.match_tol_in:g} in (exact at the print step: {ex_j * 100:.0f} %)")
        out.append({"kind": "duplicate", "building": a.building, "groups": [a.name, b.name],
                    "jaccard": round(j, 4), "percent": round(j * 100, 1), "exact_jaccard": round(ex_j, 4),
                    "match": match, "shared": shared, "faces": sizes, "of_smaller": round(of_smaller, 4),
                    "tolerance_in": p.match_tol_in, "decision": None,
                    "text": f"{a.name} and {b.name} share {j * 100:.0f} % of their faces (Jaccard {j:.2f}; "
                            f"{shared} of {sizes[0]} and {sizes[1]} faces, {of_smaller * 100:.0f} % of the smaller); {how}"})
    return out


# ------------------------------------------------------------------------------------------ units

def _member(g: GroupData, faces: str, tris: int, z_range=None) -> dict:
    m = {"group": g.name, "paths": list(g.paths), "sha256": g.sha256, "file": g.file, "tris": int(tris),
         "faces": faces}
    if z_range is not None:
        m["z_range"] = [None if z is None else _r(z) for z in z_range]
    return m


def _unit(unit: str, building: str, level, kind: str, members: list[dict], base, top, slab) -> dict:
    return {"unit": unit, "building": building, "level": level, "type": kind, "members": members,
            "tris": sum(m["tris"] for m in members), "base": base, "top": top, "slab": slab,
            "neighbours": {"below": None, "above": None}, "flags": [], "confirmed_by_owner": False}


def _building_units(plan: BuildingPlan, levels: list[dict], p: InventoryParams):
    """The floor and element units of one building, the split proposals and their flags."""
    label = {lv["band"]: lv["level"] for lv in levels}
    lv_of = {lv["level"]: lv for lv in levels}
    nbands = len(plan.slabs) + 1
    floor_members: dict[str, list[dict]] = {lv["level"]: [] for lv in levels}
    elements: list[dict] = []
    proposals: list[dict] = []
    flags: list[dict] = []
    for g in plan.groups:
        parts = plan.parts[g.name]
        counts = plan.counts[g.name]
        owner = band_owners(nbands, parts)
        if len(parts) == 1:
            level = label[parts[0]]
            floor_members[level].append(_member(g, "all", g.tris))
            named = floor_number(g.name)
            if named is not None and named != int(level[1:]):
                lv = lv_of[level]
                flags.append({"kind": "misnamed", "building": plan.name, "group": g.name, "named": named,
                              "assigned": level, "band": [lv["base"], lv["top"]],
                              "text": f"{g.name}: the name says floor {named}, but its faces sit in {level} "
                                      f"(z {lv['base']:g} to {lv['top']:g} in)"})
        elif g.name in plan.elements:
            unit = _unit(f"{plan.name}-E-{g.name}", plan.name, None, "element", [_member(g, "all", g.tris)],
                         _r(g.bbox[0][2]), _r(g.bbox[1][2]), None)
            unit["spans"] = [label[b] for b in parts]
            elements.append(unit)
        else:
            rows = []
            for part in parts:
                owned = [j for j in range(nbands) if owner[j] == part]
                lo = None if owned[0] == 0 else plan.slabs[owned[0] - 1].base - p.band_slack_in
                hi = None if owned[-1] == nbands - 1 else plan.slabs[owned[-1]].base - p.band_slack_in
                tris = sum(int(counts[j]) for j in owned)
                level = label[part]
                floor_members[level].append(_member(g, f"band {int(level[1:])}", tris, (lo, hi)))
                rows.append({"level": level, "band": int(level[1:]), "unit": f"{plan.name}-{level}", "tris": tris,
                             "share": round(tris / g.tris, 4),
                             "z_range": [None if z is None else _r(z) for z in (lo, hi)]})
            proposals.append({"group": g.name, "building": plan.name, "tris": g.tris, "parts": rows})
            flags.append({"kind": "split", "building": plan.name, "group": g.name, "parts": len(rows),
                          "levels": [r["level"] for r in rows], "tris": [r["tris"] for r in rows],
                          "units": [r["unit"] for r in rows],
                          "text": f"{g.name} spans {len(rows)} levels; proposed split by face centre: "
                                  + ", ".join(f"{r['level']} {r['tris']} tris ({r['share'] * 100:.0f} %)"
                                              for r in rows)})
    # a gap in the sequence: a floor number below the highest named one that no group is named for
    named = {n for n in (floor_number(g.name) for g in plan.groups) if n is not None}
    for number in range(1, max(named, default=0) + 1):
        if number in named:
            continue
        level = f"L{number:02d}"
        holders = sorted({m["group"] for m in floor_members.get(level, [])})
        flags.append({"kind": "missing", "building": plan.name, "level": level, "occupied_by": holders,
                      "text": (f"no group in {plan.name} is named floor {number}; {level} holds {', '.join(holders)}"
                               if holders else
                               f"{plan.name} has no {level}: no group is named floor {number} and no band carries it")})
    floors = [_unit(f"{plan.name}-{lv['level']}", plan.name, lv["level"], "floor", floor_members[lv["level"]],
                    lv["base"], lv["top"], lv["slab"]) for lv in levels]
    for i, u in enumerate(floors):
        u["neighbours"] = {"below": floors[i - 1]["unit"] if i else None,
                           "above": floors[i + 1]["unit"] if i + 1 < len(floors) else None}
    return floors + sorted(elements, key=lambda u: u["unit"]), proposals, flags


def _site_unit(g: GroupData) -> dict:
    return _unit(f"{SITE}-{g.name}", SITE, None, "site", [_member(g, "all", g.tris)],
                 _r(g.bbox[0][2]), _r(g.bbox[1][2]), None)


def build_inventory(groups: list[GroupData], params: InventoryParams | None = None) -> dict:
    """The draft campus map from the loaded groups."""
    p = params or InventoryParams()
    by_building: dict[str, list[GroupData]] = {}
    for g in groups:
        by_building.setdefault(g.building, []).append(g)
    buildings: dict[str, dict] = {}
    units: list[dict] = []
    proposals: list[dict] = []
    flags: list[dict] = []
    for name in sorted(by_building):
        if name == SITE:
            continue
        plan = plan_building(name, by_building[name], p)
        votes = name_votes(plan)
        offset, agree = anchor_offset(votes)
        levels = level_records(plan, p, offset)
        b_units, b_props, b_flags = _building_units(plan, levels, p)
        buildings[name] = {"groups": [g.name for g in plan.groups], "levels": levels,
                           "anchor": {"offset": offset, "votes": len(votes), "agree": agree}}
        units += b_units
        proposals += b_props
        flags += b_flags + duplicate_flags(plan.groups, p)
    units += [_site_unit(g) for g in sorted(by_building.get(SITE, []), key=lambda g: g.name)]
    _attach_flags(units, flags)
    return {"params": asdict(p), "buildings": buildings, "units": units, "proposals": proposals, "flags": flags}


def _attach_flags(units: list[dict], flags: list[dict]) -> None:
    """Give every flag the units of its groups, and every unit the flags that name it."""
    units_of: dict[str, list[str]] = {}
    for u in units:
        for m in u["members"]:
            units_of.setdefault(m["group"], []).append(u["unit"])
    by_unit = {u["unit"]: u for u in units}
    for f in flags:
        names = f.get("groups") or ([f["group"]] if "group" in f else f.get("occupied_by", []))
        f["units"] = sorted({uid for n in names for uid in units_of.get(n, [])})
        for uid in f["units"]:
            by_unit[uid]["flags"].append({"kind": f["kind"], "text": f["text"]})
