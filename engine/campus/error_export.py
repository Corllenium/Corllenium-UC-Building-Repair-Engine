"""Per-building colour-coded error export (P0-18): the census error maps drawn into one SketchUp file per building.

Read-only: nothing here changes the model. The plan (this module's first half) needs no SketchUp; the writer
(`write_building_skp`) draws a plan through the SketchUp C API.

Layout: one column per unit (floors in level order, then elements and site pieces, then the owner's excluded
duplicates), 315 in apart, each moved so its bbox min x/y sits at the column origin and its base at z = 0. Each face is
drawn once, in the first error kind that lists it (ERROR_KINDS order), else in light grey (`base`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from engine.campus.pixfont import GLYPHS

#: face kinds, in drawing priority: a face listed under several kinds is drawn in the first
ERROR_KINDS = ("flicker_diff", "flicker_same", "reversed", "loose", "hidden")
LINE_KINDS = ("open_edges", "cracks")
GROUPING_KINDS = ("split", "misnamed", "missing", "duplicate", "shared", "footprint", "skp_mismatch",
                  "excluded", "owner", "pending")

BASE_RGB = (205, 205, 205)
COLOURS = {
    "base": BASE_RGB,
    "flicker_diff": (230, 25, 25),
    "flicker_same": (255, 140, 0),
    "reversed": (30, 90, 255),
    "loose": (0, 200, 220),
    "hidden": (240, 215, 0),
    "open_edges": (0, 190, 60),
    "cracks": (150, 40, 220),
    "split": (140, 85, 30),
    "misnamed": (0, 128, 128),
    "missing": (60, 60, 60),
    "duplicate": (255, 0, 200),
    "excluded": (255, 0, 200),
    "shared": (110, 60, 200),
    "footprint": (200, 120, 160),
    "skp_mismatch": (180, 0, 60),
    "owner": (0, 110, 40),
    "pending": (255, 90, 0),
    "labels": (30, 30, 30),
}

GAP_IN = 315.0              # 8 m between columns
CELL_IN = 6.0               # one crack / degenerate marker per 6 in cell
DEGENERATE_AREA = 1e-4      # sq in: below this a triangle is drawn as a marker (or skipped in base)
LABEL_MAX = 40

#: the drawing order of columns by unit type
_TYPE_ORDER = {"floor": 0, "element": 1, "site": 2}
_GROUP_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+")


def face_kinds(n_faces: int, faces_by_kind: dict) -> np.ndarray:
    """(n_faces,) int8: the index in ERROR_KINDS of the first kind listing each face, -1 for none."""
    out = np.full(n_faces, -1, np.int8)
    for k in range(len(ERROR_KINDS) - 1, -1, -1):          # last kind first, so the first kind wins
        idx = np.asarray(faces_by_kind.get(ERROR_KINDS[k], ()), np.int64)
        if idx.size and (idx.min() < 0 or idx.max() >= n_faces):
            raise ValueError(f"{ERROR_KINDS[k]}: face index out of range 0..{n_faces - 1}")
        out[idx] = k
    return out


def member_mask(member: dict, cz: np.ndarray) -> np.ndarray:
    """The faces of a campus-map member: all of them, or its band by face-centre z (lo <= z < hi, as the inventory
    splits them)."""
    cz = np.asarray(cz, float)
    if member.get("faces", "all") == "all":
        return np.ones(len(cz), bool)
    lo, hi = member["z_range"]
    keep = np.ones(len(cz), bool)
    if lo is not None:
        keep &= cz >= lo
    if hi is not None:
        keep &= cz < hi
    return keep


def grid_dedup(points: np.ndarray, cell: float) -> np.ndarray:
    """The first point of each `cell`-sized grid cell, in input order."""
    points = np.asarray(points, float).reshape(-1, 3)
    if not len(points):
        return points
    keys = np.floor(points / cell).astype(np.int64)
    _, first = np.unique(keys, axis=0, return_index=True)
    return points[np.sort(first)]


def _drawable(text: str) -> str:
    text = " ".join(text.upper().split())
    return "".join(ch if ch in GLYPHS else " " for ch in text)[:LABEL_MAX].rstrip()


def flag_label(flag: dict) -> str:
    """A short label line for a grouping flag, in characters the pixel font can draw."""
    kind, text = flag["kind"], flag.get("text", "")
    head = text.split(":")[0].strip()
    label = None
    if kind == "split":
        label = f"SPLIT: {text.split()[0]}"
    elif kind == "misnamed":
        label = f"MISNAMED: {head}"
    elif kind == "missing" and (m := re.search(r"named floor (\d+)", text)):
        label = f"MISSING: NO GROUP NAMED FLOOR {m.group(1)}"
    elif kind == "duplicate" and (m := re.match(r"(\S+) and (\S+) share (\d+) %", text)):
        label = f"DUPLICATE: {m.group(2)} {m.group(3)}%"
    elif kind == "shared" and (m := re.search(r"named for floors ([\d, ]+)", text)):
        label = "SHARED: FLOORS " + " ".join(re.findall(r"\d+", m.group(1)))
    elif kind == "footprint" and (m := re.search(r"(\d+) % of its footprint lies in ([A-Za-z0-9_]+)", text)):
        label = f"FOOTPRINT: {m.group(1)}% IN {m.group(2)}"
    elif kind == "owner":
        label = head
    elif kind in ("skp_mismatch", "pending", "excluded"):
        label = flag["label"] if "label" in flag else text
    if label is None:
        label = f"{kind}: {text}"
    return _drawable(label)


# ------------------------------------------------------------------------------------------ the plan

@dataclass
class MemberPlan:
    group: str
    tris: dict[str, np.ndarray] = field(default_factory=dict)       # kind -> (k, 3, 3), moved
    markers: dict[str, np.ndarray] = field(default_factory=dict)    # kind -> (m, 3) degenerate-face markers
    segments: np.ndarray = field(default_factory=lambda: np.zeros((0, 2, 3)))
    cracks: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    skipped_degenerate_base: int = 0


@dataclass
class ColumnPlan:
    unit: str
    label: str
    type: str
    x0: float
    width: float
    depth: float
    members: list[MemberPlan]
    flags: list[dict]
    counts: dict[str, int]


@dataclass
class BuildingPlan:
    building: str
    columns: list[ColumnPlan]
    counts: dict[str, int]


def _level_key(unit: dict):
    lv = unit.get("level")
    num = int(lv[1:]) if lv and lv[1:].isdigit() else 10 ** 6
    return (_TYPE_ORDER.get(unit.get("type"), 9), num, unit["unit"])


def _stale(flag: dict, members: set[str], known: set[str]) -> bool:
    """A misnamed / shared / missing flag that names a known group which is no longer a member of the unit
    (the owner moved it, as CHTM_12th to CHTM-L12)."""
    if flag["kind"] not in ("misnamed", "shared", "missing"):
        return False
    named = {t for t in _GROUP_TOKEN.findall(flag.get("text", "")) if t in known}
    return bool(named - members)


@dataclass
class _Loaded:
    pos: np.ndarray
    fv: np.ndarray
    errors: dict
    tri: np.ndarray
    cz: np.ndarray
    degenerate: np.ndarray
    kinds: np.ndarray


def _load(group: str, load_member, cache: dict) -> _Loaded:
    if group not in cache:
        pos, fv, errors = load_member(group)
        pos = np.asarray(pos, float).reshape(-1, 3)
        fv = np.asarray(fv, np.int64).reshape(-1, 3)
        if int(errors.get("n_faces", len(fv))) != len(fv):
            raise ValueError(f"{group}: errors file lists {errors.get('n_faces')} faces, mesh has {len(fv)}")
        tri = pos[fv]
        area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) / 2.0
        cache[group] = _Loaded(pos, fv, errors, tri, tri[:, :, 2].mean(axis=1), area < DEGENERATE_AREA,
                               face_kinds(len(fv), errors.get("faces", {})))
    return cache[group]


def _in_range(z: np.ndarray, member: dict) -> np.ndarray:
    return member_mask(member, z)


def _member_plan(group: str, member: dict, data: _Loaded, offset: np.ndarray, excluded: bool,
                 counts: dict[str, int]) -> MemberPlan:
    keep = member_mask(member, data.cz)
    mp = MemberPlan(group=group)
    good = keep & ~data.degenerate
    if excluded:
        mp.tris["excluded"] = data.tri[good] + offset
        mp.skipped_degenerate_base = int((keep & data.degenerate).sum())
        return mp
    mp.tris["base"] = data.tri[good & (data.kinds < 0)] + offset
    mp.skipped_degenerate_base = int((keep & data.degenerate & (data.kinds < 0)).sum())
    centres = data.tri.mean(axis=1)
    for k, kind in enumerate(ERROR_KINDS):
        sel = data.kinds == k
        mp.tris[kind] = data.tri[good & sel] + offset
        mp.markers[kind] = grid_dedup(centres[keep & data.degenerate & sel], CELL_IN) + offset
        listed = np.asarray(data.errors.get("faces", {}).get(kind, ()), np.int64)
        counts[kind] += int(keep[listed].sum()) if listed.size else 0
    seg = np.asarray(data.errors.get("open_edges", ()), float).reshape(-1, 2, 3)
    if len(seg):
        seg = seg[_in_range(seg[:, :, 2].mean(axis=1), member)]
    mp.segments = seg + offset
    counts["open_edges"] += len(seg)
    cracks = np.asarray(data.errors.get("cracks", ()), float).reshape(-1, 3)
    if len(cracks):
        cracks = cracks[_in_range(cracks[:, 2], member)]
    counts["cracks"] += len(cracks)
    mp.cracks = grid_dedup(cracks, CELL_IN) + offset
    return mp


def _bbox(members: list[tuple[dict, _Loaded]]) -> tuple[np.ndarray, np.ndarray]:
    pts = [d.tri[member_mask(m, d.cz)].reshape(-1, 3) for m, d in members]
    pts = np.vstack(pts) if pts else np.zeros((0, 3))
    if not len(pts):
        return np.zeros(3), np.zeros(3)
    return pts.min(axis=0), pts.max(axis=0)


def plan_building(building: str, campus_map: dict, load_member: Callable[[str], tuple],
                  mismatches: dict | None = None, building_of: Callable[[str], str] | None = None) -> BuildingPlan:
    """Lay out one building's units (plus the owner's excluded duplicates that belong to it).

    `load_member(group)` returns `(positions, face_v, errors)` for one split group, `errors` as the census writes
    `data/campus/errors/<group>.json`. `mismatches` maps an OBJ file name to its skp_check mismatch record."""
    if building_of is None:
        from engine.campus.inventory import building_of
    mismatches = mismatches or {}
    units = sorted((u for u in campus_map["units"] if u["building"] == building), key=_level_key)
    excluded = [e for e in campus_map.get("excluded", []) if building_of(e["group"]) == building]
    if not units and not excluded:
        raise ValueError(f"no units for building {building!r}")
    known = {m["group"] for u in campus_map["units"] for m in u["members"]} | \
            {e["group"] for e in campus_map.get("excluded", [])}
    cache: dict[str, _Loaded] = {}
    columns: list[ColumnPlan] = []
    totals = {k: 0 for k in ERROR_KINDS + LINE_KINDS}
    x0 = 0.0
    specs = [(u, False) for u in units] + \
            [({"unit": f"EXCLUDED-{e['group']}", "level": None, "type": "excluded", "base": None,
               "members": [{"group": e["group"], "faces": "all"}], "flags": [], "confirmed_by_owner": True,
               "reason": e.get("reason", "")}, True) for e in excluded]
    for unit, is_excluded in specs:
        loaded = [(m, _load(m["group"], load_member, cache)) for m in unit["members"]]
        lo, hi = _bbox(loaded)
        base = unit.get("base")
        base = float(lo[2]) if base is None else float(base)
        offset = np.array([x0 - lo[0], -lo[1], -base])
        counts = {k: 0 for k in ERROR_KINDS + LINE_KINDS}
        members = [_member_plan(m["group"], m, d, offset, is_excluded, counts) for m, d in loaded]
        flags = _column_flags(unit, is_excluded, known, mismatches)
        label = f"{unit['level']} {unit['unit']}" if unit.get("level") else unit["unit"]
        width, depth = float(hi[0] - lo[0]), float(hi[1] - lo[1])
        columns.append(ColumnPlan(unit["unit"], label, unit.get("type", "floor"), x0, width, depth, members,
                                  flags, counts))
        if not is_excluded:
            for k in totals:
                totals[k] += counts[k]
        x0 += width + GAP_IN
    return BuildingPlan(building, columns, totals)


def _column_flags(unit: dict, is_excluded: bool, known: set[str], mismatches: dict) -> list[dict]:
    if is_excluded:
        flags = [{"kind": "excluded", "text": unit.get("reason", ""),
                  "label": "EXCLUDED: DUPLICATE COPY (OWNER)"}]
    else:
        names = {m["group"] for m in unit["members"]}
        flags = [dict(f) for f in unit.get("flags", []) if not _stale(f, names, known)]
        for m in unit["members"]:
            mm = mismatches.get(m.get("file", f"{m['group']}.obj"))
            if mm is not None:
                rel = float(mm["area_rel"])
                flags.append({"kind": "skp_mismatch",
                              "text": f"{m['group']}: the CHECKPOINT-17 backup has {rel * 100:+.2f} % more area "
                                      f"than the export",
                              "label": f"BACKUP {rel * 100:+.2f}% AREA: {m['group']}"})
        if not unit.get("confirmed_by_owner", True):
            flags.append({"kind": "pending", "text": "not yet confirmed by the owner",
                          "label": "PENDING: NOT CONFIRMED BY OWNER"})
    for f in flags:
        f["label"] = flag_label(f)
    return flags
