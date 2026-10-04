"""Campus inventory (spec 2026-10-03, P0 task 10): buildings, a level table per building, floor and element
units, duplicate groups, misnamed and missing levels. Everything is a draft for the owner to confirm; nothing
here writes geometry, and no mesh is changed or welded (the duplicate check's vertex identity is a comparison
key only).

Per building (the campus is never processed as one mesh):
- `slab_table`: area histograms of up- and down-facing triangles -> slabs (a top peak with the bottom peak
  under it); the bases are the level table.
- `plan_building`: bands between the bases; a group's *parts* are the fewest bands holding 80 % of its
  triangles; a band no floor group occupies is dropped.
- `name_votes` / `anchor_offset`: the floor numbers in the names; when a strict majority sit one above their
  band (Science A) the level numbers start there.
- `duplicate_flags`, `footprint_flags`, and the misnamed / missing / shared / split flags of `_building_units`.

The defaults of `InventoryParams` are the brief's, except where CHECKPOINT-17 showed the brief's value cannot
work (24 in slab window, nearest base, 20 in level spacing, print-step duplicates): each says so, and
`BRIEF_PARAMS` (CLI `--literal`) reproduces the brief as written for comparison. The real-run measurements
behind the changes are in the P0-10 report and in `docs/superpowers/records/campus/campus-map-draft.md`.
"""
from __future__ import annotations

import collections
import hashlib
import itertools
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file
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
    slab_window_in: float = 60.0      # brief: 24. CKPT17 slabs are 20, 39 or (Science A plan_4) 54 in thick
    base_pick: str = "lowest"         # brief: "nearest". Stepped slabs have a second underside 30 in up
    min_slab_in: float = 1.0          # a slab is at least one bin thick (same-plane up and down are no slab)
    min_storey_in: float = 100.0      # brief: only the 20 in merge. 1 block terraces and thin layers sit 39 in apart
    # bands and units
    band_slack_in: float = 1.0        # a band starts one bin below its base (the base is a bin's mean z)
    part_coverage: float = 0.80       # the fewest bands holding 80 % of a group's triangles are its parts
    # duplicates
    dup_flag: float = 0.25            # flag a Jaccard similarity of at least 0.25 (the brief)
    match_tol_in: float = 0.5         # brief: the print step. CKPT17 copies sit 0.03-0.4 in off; vertices within this
    #                                   count as one identity (identity only, and it chains: see `_face_sets`)
    # footprints
    footprint_frac: float = 0.5       # "mostly" in another building: more than half the group's box (the brief)


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
        vz = g.pos[g.fv][:, :, 2]            # the open ends of the table are vertex heights, not face centres
        if 0 in plan.bands and (idx == 0).any():
            lowest = min(lowest, float(vz[idx == 0].min()))
        if (idx == nbands - 1).any():
            highest = max(highest, float(vz[idx == nbands - 1].max()))
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


def _identity_extent(points: np.ndarray, label: np.ndarray) -> float:
    """The largest bounding-box diagonal of the points that share a label: no two vertices of one identity are
    further apart than this."""
    if len(points) == 0:
        return 0.0
    order = np.argsort(label, kind="stable")
    sorted_label, pts = label[order], points[order]
    starts = np.flatnonzero(np.concatenate(([True], sorted_label[1:] != sorted_label[:-1])))
    spread = np.maximum.reduceat(pts, starts, axis=0) - np.minimum.reduceat(pts, starts, axis=0)
    return float(np.sqrt((spread ** 2).sum(axis=1)).max())


def _face_sets(groups: list[GroupData], tol_in: float) -> tuple[dict[str, np.ndarray], float]:
    """Per group, the ids of its distinct faces, and the largest extent of a vertex identity. A face is its
    three vertices, sorted, plus its winding and its look key. A vertex is the position snapped to the print
    step; with `tol_in` > 0, vertices within `tol_in` of each other also count as one, and that identity
    chains (A near B and B near C make A, B and C one), so an identity can reach further than `tol_in`: the
    returned extent says how far. Identity only: no geometry is touched."""
    dec = max(g.decimals for g in groups)
    scale = 10.0 ** dec
    snapped = np.concatenate([np.rint(g.pos * scale) for g in groups]).astype(np.int64)
    uniq, inverse = np.unique(snapped, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    if tol_in > 0:
        label = _components(len(uniq), *_link_pairs(uniq / scale, tol_in))
        extent = _identity_extent(uniq / scale, label)
    else:
        label = np.arange(len(uniq))
        extent = 0.0
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
    return out, extent


def _jaccard(a: np.ndarray, b: np.ndarray) -> tuple[float, int]:
    shared = int(np.intersect1d(a, b, assume_unique=True).size)
    union = a.size + b.size - shared
    return (shared / union if union else 0.0), shared


def duplicate_flags(groups: list[GroupData], p: InventoryParams) -> tuple[list[dict], float]:
    """Pairs of groups of one building whose faces overlap: Jaccard similarity of the face fingerprints,
    flagged from `dup_flag`; and the largest extent of a vertex identity among these groups. `exact_jaccard` is
    the same at the print step alone: the CKPT17 copies (Science A, BRS obj1) sit 0.03-0.4 in off their
    originals, so they only match with a tolerance, and the tolerance chains (see `_face_sets`)."""
    if len(groups) < 2:
        return [], 0.0
    tolerant, extent = _face_sets(groups, p.match_tol_in)
    exact = tolerant if p.match_tol_in <= 0 else _face_sets(groups, 0.0)[0]
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
               else f"vertices within {p.match_tol_in:g} in of each other count as one, and that chains (the "
                    f"largest chain in {a.building} spans {extent:.2f} in); exact at the print step: {ex_j * 100:.0f} %")
        out.append({"kind": "duplicate", "building": a.building, "groups": [a.name, b.name],
                    "jaccard": round(j, 4), "percent": round(j * 100, 1), "exact_jaccard": round(ex_j, 4),
                    "match": match, "shared": shared, "faces": sizes, "of_smaller": round(of_smaller, 4),
                    "tolerance_in": p.match_tol_in, "identity_extent_in": round(extent, 2), "decision": None,
                    "text": f"{a.name} and {b.name} share {j * 100:.0f} % of their faces (Jaccard {j:.2f}; "
                            f"{shared} of {sizes[0]} and {sizes[1]} faces, {of_smaller * 100:.0f} % of the smaller); {how}"})
    return out, extent


# ------------------------------------------------------------------------------------------ footprints

def _union_overlap(rect: tuple[float, float, float, float], others: list[tuple[float, float, float, float]]) -> float:
    """Area of `rect` that lies inside the union of the rectangles `others` (coordinate compression)."""
    x0, y0, x1, y1 = rect
    clipped = [(max(x0, a), max(y0, b), min(x1, c), min(y1, d)) for a, b, c, d in others]
    clipped = [r for r in clipped if r[0] < r[2] and r[1] < r[3]]
    if not clipped:
        return 0.0
    xs = sorted({r[0] for r in clipped} | {r[2] for r in clipped})
    area = 0.0
    for xa, xb in zip(xs, xs[1:]):
        length, reach = 0.0, None
        for ya, yb in sorted((r[1], r[3]) for r in clipped if r[0] <= xa and r[2] >= xb):
            if reach is None or ya > reach:
                length += yb - ya
                reach = yb
            elif yb > reach:
                length += yb - reach
                reach = yb
        area += length * (xb - xa)
    return area


def footprint_flags(by_building: dict[str, list[GroupData]], p: InventoryParams) -> list[dict]:
    """Groups whose footprint (XY bounding box) lies mostly in another building's footprint (the union of
    that building's group boxes), and more in it than in the rest of their own building."""
    rect = {g.name: (float(g.bbox[0][0]), float(g.bbox[0][1]), float(g.bbox[1][0]), float(g.bbox[1][1]))
            for gs in by_building.values() for g in gs}
    out = []
    for name, groups in by_building.items():
        if name == SITE:
            continue
        for g in groups:
            r = rect[g.name]
            area = (r[2] - r[0]) * (r[3] - r[1])
            if area <= 0:
                continue
            own = _union_overlap(r, [rect[o.name] for o in groups if o is not g]) / area
            best, other = max(((_union_overlap(r, [rect[o.name] for o in gs]) / area, b)
                               for b, gs in by_building.items() if b not in (name, SITE)), default=(0.0, None))
            if other is None or best < p.footprint_frac or best <= own:
                continue
            out.append({"kind": "footprint", "building": name, "group": g.name, "other": other,
                        "fraction_other": round(best, 4), "fraction_own": round(own, 4),
                        "text": f"{g.name} ({name}): {best * 100:.0f} % of its footprint lies in {other}, "
                                f"{own * 100:.0f} % in the rest of {name}"})
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
    # band 0 is a level only when a floor group sits in it; an element can still reach into it
    below = f"below {levels[0]['level']}" if levels else "below L01"
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
            unit["spans"] = [label.get(b, below) for b in parts]
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
    # two floor groups named for different floors in one level: the table may be missing a level there
    for lv in levels:
        members = floor_members[lv["level"]]
        numbers = sorted({n for n in (floor_number(m["group"]) for m in members) if n is not None})
        if len(numbers) > 1:
            names = sorted({m["group"] for m in members if floor_number(m["group"]) is not None})
            flags.append({"kind": "shared", "building": plan.name, "level": lv["level"], "numbers": numbers,
                          "groups": names,
                          "text": f"{lv['level']} of {plan.name} holds groups named for floors "
                                  f"{', '.join(map(str, numbers))} ({', '.join(names)}): a level may be missing here"})
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
    identity = {"tolerance_in": p.match_tol_in, "largest_extent_in": 0.0, "building": None}
    widest = 0.0

    def duplicates_of(building: str, gs: list[GroupData]) -> list[dict]:
        nonlocal widest
        found, extent = duplicate_flags(gs, p)
        if extent > widest:
            widest = extent
            identity.update(largest_extent_in=round(extent, 2), building=building)
        return found

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
        flags += b_flags + duplicates_of(name, plan.groups)
    units += [_site_unit(g) for g in sorted(by_building.get(SITE, []), key=lambda g: g.name)]
    flags += duplicates_of(SITE, by_building.get(SITE, []))     # SITE has no level table, but copies still matter
    flags += footprint_flags(by_building, p)
    _attach_flags(units, flags)
    return {"params": asdict(p), "buildings": buildings, "units": units, "proposals": proposals, "flags": flags,
            "identity": identity, "coverage": _coverage(groups, units, proposals)}


def _coverage(groups: list[GroupData], units: list[dict], proposals: list[dict]) -> dict:
    """The proof that every group is in exactly one unit, or in exactly one proposal whose parts hold all its
    triangles."""
    seen: dict[str, list[tuple[str, int]]] = {}
    for u in units:
        for m in u["members"]:
            seen.setdefault(m["group"], []).append((m["faces"], m["tris"]))
    proposed = {pr["group"] for pr in proposals}
    whole = split = 0
    ok = True
    for g in groups:
        rows = seen.get(g.name, [])
        if g.name in proposed:
            split += 1
            ok &= len(rows) >= 2 and all(f.startswith("band ") for f, _ in rows) and sum(t for _, t in rows) == g.tris
        else:
            whole += 1
            ok &= rows == [("all", g.tris)]
    total = sum(g.tris for g in groups)
    unit_tris = sum(u["tris"] for u in units)
    return {"groups": len(groups), "whole": whole, "split": split, "tris": total, "unit_tris": unit_tris,
            "ok": bool(ok and unit_tris == total)}


def _attach_flags(units: list[dict], flags: list[dict]) -> None:
    """Give every flag its units, and every unit the flags that name it. A flag about a level (missing, shared)
    belongs to that level's unit alone, whichever groups hold its faces; the others belong to the units of
    their groups."""
    units_of: dict[str, list[str]] = {}
    for u in units:
        for m in u["members"]:
            units_of.setdefault(m["group"], []).append(u["unit"])
    by_unit = {u["unit"]: u for u in units}
    for f in flags:
        if "level" in f:
            unit = f"{f['building']}-{f['level']}"
            f["units"] = [unit] if unit in by_unit else []
        else:
            names = f.get("groups") or [f["group"]]
            f["units"] = sorted({uid for n in names for uid in units_of.get(n, [])})
        for uid in f["units"]:
            by_unit[uid]["flags"].append({"kind": f["kind"], "text": f["text"]})


# ------------------------------------------------------------------------------------------ the owner's table

def _fmt(x, digits: int = 1) -> str:
    return "" if x is None else f"{x:,.{digits}f}"


def _table(header: list[str], rows: list[list]) -> list[str]:
    return (["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
            + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows])


def _members_text(unit: dict) -> str:
    return ", ".join(f"{m['group']} ({m['tris']:,}" + ("" if m["faces"] == "all" else f", {m['faces']}") + ")"
                     for m in unit["members"])


def _identity_cells(params: dict, identity: dict) -> list[str]:
    """The 'used' and 'measured reason' cells of the vertex identity row."""
    tol = params["match_tol_in"]
    if tol <= 0:
        return ["the print step only", "the brief's rule as written: nothing is matched across a shift"]
    reach = identity.get("largest_extent_in") or 0.0
    where = f" ({identity['building']})" if identity.get("building") else ""
    return [f"print step and {tol:g} in, chained",
            "the obj1 copies sit 0.03 in (Science A) to 0.4 in (BRS 4th, 5th) off their originals, so nothing "
            f"coincides at the print step. Vertices within {tol:g} in of each other form one identity and "
            f"identities chain, so one can reach further than {tol:g} in: the largest spans {reach:.2f} in{where}, "
            "measured as the bounding-box diagonal of its vertices"]


def render_markdown(inv: dict) -> str:
    """The owner-readable draft: summary, level tables, units, splits, flags, and how it was made."""
    src, cov, params = inv.get("source", {}), inv["coverage"], inv["params"]
    units, flags = inv["units"], inv["flags"]
    by_kind = {k: [f for f in flags if f["kind"] == k]
               for k in ("duplicate", "misnamed", "missing", "shared", "footprint", "split")}
    out = ["# Campus map draft (P0-10): buildings, levels and units for the owner to confirm", "",
           f"Built by `python -m engine.cli campus-inventory` from the frozen CHECKPOINT-17 split snapshots "
           f"({cov['groups']} files, {cov['tris']:,} triangles; clean OBJ sha256 "
           f"`{str(src.get('clean_obj_sha256'))[:16]}`"
           + ("; each snapshot file was re-hashed and matches the sha256 in source.json" if src.get("snapshots_verified")
              else "") +
           "). **Nothing here is confirmed:** every unit has "
           "`confirmed_by_owner: false`. The machine-readable twin is `data/campus/campus_map.draft.json` "
           "(git-ignored; the command regenerates it). Heights are inches, Z up.", "",
           "## What you confirm", "",
           "1. Each building's **level table** (base, top, slab) in the tables below.",
           "2. Each **flag**: which group of a duplicate pair stays, whether a misnamed group is renamed or its "
           "level is accepted, whether a missing level is real, which building a group of another footprint "
           "belongs to, and each proposed split.", "",
           f"Coverage: every one of the {cov['groups']} splits is in exactly one unit ({cov['whole']}) or exactly "
           f"one split proposal ({cov['split']}); the units hold {cov['unit_tris']:,} of {cov['tris']:,} triangles "
           f"({'ok' if cov['ok'] else 'NOT ok'}).", "", "## Summary", ""]
    rows = []
    for name, b in inv["buildings"].items():
        bu = [u for u in units if u["building"] == name]
        nflags = sum(1 for f in flags if f.get("building") == name)
        rows.append([name, len(b["groups"]), f"{sum(u['tris'] for u in bu):,}", len(b["levels"]),
                     sum(1 for u in bu if u["type"] == "floor"), sum(1 for u in bu if u["type"] == "element"),
                     nflags])
    site = [u for u in units if u["type"] == "site"]
    rows.append([SITE, len(site), f"{sum(u['tris'] for u in site):,}", "", "", "", ""])
    out += _table(["Building", "Groups", "Triangles", "Levels", "Floor units", "Element units", "Flags"], rows)
    out += ["", "Flags in total: " + ", ".join(f"{k} {len(v)}" for k, v in by_kind.items()) + ".", "",
            "## Levels and floor units", ""]
    for name, b in inv["buildings"].items():
        a = b["anchor"]
        if a["offset"]:
            note = (f"Level numbers start at L{1 + a['offset']:02d}: {a['agree']} of {a['votes']} named floor "
                    f"groups agree on an offset of +{a['offset']}.")
        else:
            note = (f"Level numbers count from the lowest band ({a['agree']} of {a['votes']} named floor groups "
                    "agree).")
        out += [f"### {name}", "", f"{len(b['groups'])} groups. {note}", ""]
        floors = {u["level"]: u for u in units if u["building"] == name and u["type"] == "floor"}
        out += _table(["Level", "Unit", "Base", "Top", "Slab bottom - top", "Triangles", "Groups (triangles)"],
                      [[lv["level"], floors[lv["level"]]["unit"], _fmt(lv["base"]), _fmt(lv["top"]),
                        f"{_fmt(lv['slab']['bottom'])} - {_fmt(lv['slab']['top'])}" if lv["slab"] else "no slab found",
                        f"{lv['tris']:,}", _members_text(floors[lv["level"]])] for lv in b["levels"]])
        out.append("")
    out += ["## Element and site units", ""]
    out += _table(["Unit", "Type", "Triangles", "Lowest z", "Highest z", "Spans", "Group"],
                  [[u["unit"], u["type"], f"{u['tris']:,}", _fmt(u["base"]), _fmt(u["top"]),
                    ", ".join(u.get("spans", [])), u["members"][0]["group"]]
                   for u in units if u["type"] in ("element", "site")])
    out += ["", "## Proposed splits (by face centre; no triangle is cut)", ""]
    out += _table(["Group", "Level", "Triangles", "Share", "Faces with z from", "to (exclusive)"],
                  [[pr["group"] if i == 0 else "", row["level"], f"{row['tris']:,}", f"{row['share'] * 100:.0f} %",
                    _fmt(row["z_range"][0]) or "-inf", _fmt(row["z_range"][1]) or "+inf"]
                   for pr in inv["proposals"] for i, row in enumerate(pr["parts"])])
    out += ["", "## Flags", "",
            f"### Duplicates (Jaccard similarity of the face fingerprints, flagged from {params['dup_flag']:g})", ""]
    out += _table(["Building", "Group A", "Group B", "Similarity", "Exact at print step", "Faces A / B", "Shared",
                   "Of the smaller", "Kind"],
                  [[f["building"], f["groups"][0], f["groups"][1], f"{f['percent']:.1f} %",
                    f"{f['exact_jaccard'] * 100:.1f} %", f"{f['faces'][0]:,} / {f['faces'][1]:,}", f"{f['shared']:,}",
                    f"{f['of_smaller'] * 100:.1f} %", f["match"]] for f in by_kind["duplicate"]])
    out += ["", "### Misnamed (the floor number in the name against the level its faces sit in)", ""]
    out += _table(["Group", "Name says", "Sits in", "Level z (base - top)", "Building"],
                  [[f["group"], f["named"], f["assigned"], f"{_fmt(f['band'][0])} - {_fmt(f['band'][1])}",
                    f["building"]] for f in by_kind["misnamed"]])
    out += ["", "### Missing levels (a floor number below the highest named one that no group is named for)", ""]
    out += _table(["Building", "Level", "Held by"],
                  [[f["building"], f["level"], ", ".join(f["occupied_by"]) or "nothing: no group, no band"]
                   for f in by_kind["missing"]])
    out += ["", "### Levels shared by groups named for different floors (a level may be missing there)", ""]
    out += _table(["Building", "Level", "Floors named", "Groups"],
                  [[f["building"], f["level"], ", ".join(map(str, f["numbers"])), ", ".join(f["groups"])]
                   for f in by_kind["shared"]])
    out += ["", "### Footprints (a group whose box lies mostly in another building)", "",
            "Listed when more than half of the group's XY box lies in another building's footprint (the union of "
            "that building's group boxes) and more of its box lies there than in the rest of its own building. The "
            "second condition is an addition to the brief's rule: without it, a group that sits inside its own "
            "building and merely overlaps a neighbouring building's box is listed too.", ""]
    out += _table(["Group", "Named for", "In its own building", "In", "That building's footprint"],
                  [[f["group"], f["building"], f"{f['fraction_own'] * 100:.0f} %", f["other"],
                    f"{f['fraction_other'] * 100:.0f} %"] for f in by_kind["footprint"]])
    out += ["", "## How the draft was made", "",
            "1. **Level table**, per building: area histograms of up-facing (`n_z > 0.9`) and down-facing "
            f"(`n_z < -0.9`) triangles over z in {params['bin_in']:g} in bins. A peak is a local maximum of at "
            f"least {params['peak_frac'] * 100:g} % of the largest; peaks within {params['merge_in']:g} in merge, "
            "the strongest staying. A slab is an up-facing peak (its top) with a down-facing peak (its bottom, "
            "the level's `base`) below it.",
            f"2. **Bands and units**: a band runs from one base to the next; a face is in a band by its centre z. "
            f"A group's *parts* are the fewest bands holding {params['part_coverage'] * 100:g} % of its "
            "triangles. One part is a floor unit; several parts make an element unit when the name holds stair, "
            "bridge, roof, zone, shell, ground, pathway or road, and a split proposal otherwise. A band no floor "
            "group occupies is dropped. Groups without a building prefix are site units.",
            "3. **Numbering**: from the lowest band (L01), unless a strict majority of the named floor groups "
            "agree on a positive offset (Science A: floors 2 to 6), which then starts the numbers and leaves the "
            "lower levels missing.",
            "4. **Flags**: duplicates by fingerprint, compared within each building and among the SITE groups (a "
            "face is its three vertices sorted, its winding and its look key, so a back-to-back pair never "
            "matches); misnamed by the number in the name against the "
            "level; missing by the floor numbers the names skip; footprints by the XY boxes: a group is flagged when "
            "more than half of its box lies in another building's footprint and more of its box lies there than in "
            "the rest of its own building (the second condition is an addition to the brief's rule).", "",
            "Constants where CHECKPOINT-17 showed the brief's value cannot work (measured on the frozen data):", ""]
    out += _table(["Constant", "Brief", "Used", "Measured reason"], [
        ["slab bottom window", f"{BRIEF_PARAMS.slab_window_in:g} in", f"{params['slab_window_in']:g} in",
         "slabs are 19.7 in (half a block), 39.4 in (a block) or, for Science A plan_4, 54 in thick"],
        ["slab bottom pick", "nearest down peak", f"{params['base_pick']} down peak in the window",
         "stepped slabs have a second underside about 30 in above the real bottom (BRS 5th, EDS 3rd)"],
        ["levels closer than", f"{BRIEF_PARAMS.min_storey_in:g} in (peak merge only)", f"{params['min_storey_in']:g} in",
         "terraces and thin layers repeat every 39 in; the shortest storey measured is 157 in"],
        ["duplicate vertex identity", "the print step", *_identity_cells(params, inv.get("identity") or {})],
    ])
    brief = inv.get("brief_levels", {})
    if brief:
        out += ["", "Levels per building with the brief's constants (what the draft would otherwise have): "
                + ", ".join(f"{b} {n}" for b, n in brief.items()) + "."]
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------ the command

def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(f"{type(o).__name__} is not JSON serialisable")


def _write_atomic(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".inventory-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_groups(source: dict, index: dict, materials: dict) -> list[GroupData]:
    """Read every split snapshot and check it against source.json and the group index."""
    split = index["split"]
    names = [s["group"] for s in source["snapshots"]]
    if set(names) != set(split):
        raise ValueError("source.json and group_index.json disagree on the splits: "
                         f"{sorted(set(names) ^ set(split))[:5]}")
    looks = {name: m["look"] for name, m in materials["materials"].items()}
    groups = []
    for s in source["snapshots"]:
        path = Path(s["dir"]) / s["file"]
        actual = sha256_file(path)
        if actual != s["sha256"]:
            raise ValueError(f"{s['group']}: sha256 of {path} is {actual[:16]}..., source.json says "
                             f"{s['sha256'][:16]}...: the snapshot is not the frozen file, refusing to inventory it")
        mesh = read_obj(path)
        want = split[s["group"]]["tris"]
        if not (mesh.n_faces == s["tris"] == want):
            raise ValueError(f"{s['group']}: the snapshot has {mesh.n_faces} triangles, source.json says "
                             f"{s['tris']}, group_index.json says {want}")
        groups.append(load_group(s["group"], mesh, looks, split[s["group"]]["paths"], s["sha256"], s["file"]))
    return groups


def levels_with(groups: list[GroupData], params: InventoryParams) -> dict[str, int]:
    """How many levels each building gets with `params` (shows what the brief's constants would give)."""
    by_building: dict[str, list[GroupData]] = {}
    for g in groups:
        by_building.setdefault(g.building, []).append(g)
    return {b: len(plan_building(b, gs, params).bands) for b, gs in sorted(by_building.items()) if b != SITE}


def cmd_campus_inventory(source_json, index_json, materials_json, out_json, out_md,
                         params: InventoryParams | None = None) -> dict:
    """Build the draft campus map from the frozen snapshots and write the JSON and the owner's table."""
    source = json.loads(Path(source_json).read_text(encoding="utf-8"))
    index = json.loads(Path(index_json).read_text(encoding="utf-8"))
    materials = json.loads(Path(materials_json).read_text(encoding="utf-8"))
    groups = load_groups(source, index, materials)
    result = build_inventory(groups, params)
    result["source"] = {"source_json": str(source_json), "frozen": source.get("created"),
                        "clean_obj_sha256": (source.get("clean_obj") or {}).get("sha256"),
                        "splits": len(groups), "tris": sum(g.tris for g in groups),
                        "snapshots_verified": True}      # load_groups re-hashed every file and would have refused
    result["brief_levels"] = levels_with(groups, BRIEF_PARAMS)
    if not result["coverage"]["ok"]:
        raise RuntimeError(f"coverage check failed: {result['coverage']}")
    _write_atomic(Path(out_json), json.dumps(result, indent=1, default=_json_default) + "\n")
    _write_atomic(Path(out_md), render_markdown(result))
    return result
