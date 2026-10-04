"""Campus inventory (spec 2026-10-03, P0 task 10): buildings, a level table per building, floor and element
units, duplicate groups, misnamed and missing levels. Everything is a draft for the owner to confirm; nothing
here writes geometry.
"""
from __future__ import annotations

import hashlib
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


BRIEF_PARAMS = InventoryParams(slab_window_in=24.0, base_pick="nearest", min_storey_in=20.0)


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


@dataclass
class BuildingPlan:
    """The level table of one building and how its groups sit in it."""
    name: str
    groups: list[GroupData]
    slabs: list[Slab]                     # the settled table: every band above the first is occupied
    counts: dict[str, np.ndarray]         # group -> triangles per band
    parts: dict[str, list[int]]           # group -> its part bands
    bands: list[int]                      # the bands that are levels, lowest first (band 0 only if occupied)


def plan_building(name: str, groups: list[GroupData], p: InventoryParams) -> BuildingPlan:
    """Detect the slabs, then drop the slabs whose band no group occupies (a band nobody holds is no level;
    it merges into the band below)."""
    slabs = slab_table(groups, p)
    while True:
        bases = [s.base for s in slabs]
        counts = {g.name: band_counts(g.cz, bases, p) for g in groups}
        parts = {g.name: group_parts(counts[g.name], p.part_coverage) for g in groups}
        occupied = {j for ps in parts.values() for j in ps}
        empty = [j for j in range(1, len(slabs) + 1) if j not in occupied]
        if not empty:
            break
        del slabs[empty[0] - 1]
    bands = ([0] if 0 in occupied else []) + list(range(1, len(slabs) + 1))
    return BuildingPlan(name, groups, slabs, counts, parts, bands)


def _r(x: float) -> float:
    return round(float(x), 2)


def level_records(plan: BuildingPlan, p: InventoryParams) -> list[dict]:
    """One record per level, lowest first: its number, base, top, slab and triangles."""
    nbands = len(plan.slabs) + 1
    tris = dict.fromkeys(plan.bands, 0)
    lowest = np.inf
    highest = -np.inf
    for g in plan.groups:
        owner = band_owners(nbands, plan.parts[g.name])
        for j, c in enumerate(plan.counts[g.name]):
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
        out.append({"level": f"L{i + 1:02d}", "band": j, "base": _r(base), "top": _r(top),
                    "slab": {"bottom": _r(slab.base), "top": _r(slab.top)} if slab else None,
                    "tris": tris[j]})
    return out


def build_inventory(groups: list[GroupData], params: InventoryParams | None = None) -> dict:
    """The draft campus map from the loaded groups."""
    p = params or InventoryParams()
    by_building: dict[str, list[GroupData]] = {}
    for g in groups:
        by_building.setdefault(g.building, []).append(g)
    buildings = {}
    for name in sorted(by_building):
        if name == SITE:
            continue
        plan = plan_building(name, by_building[name], p)
        buildings[name] = {"groups": [g.name for g in plan.groups], "levels": level_records(plan, p)}
    return {"params": asdict(p), "buildings": buildings}
