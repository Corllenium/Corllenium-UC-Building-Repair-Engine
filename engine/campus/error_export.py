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

from engine.campus.pixfont import GLYPHS, text_width

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
LABEL_MAX = 48
LINE_PITCH = 9              # text lines, in cells
UNIT_CELL_IN, FLAG_CELL_IN, LEGEND_CELL_IN = 12.0, 8.0, 10.0   # pixel-font cell sizes

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


def exact_duplicates(tris: np.ndarray) -> int:
    """Triangles that repeat an earlier one exactly (same three points, any order). SketchUp keeps one face for
    them when they share a group, so the read-back count is lower by this much."""
    tris = np.asarray(tris, float).reshape(-1, 3, 3)
    if not len(tris):
        return 0
    order = np.lexsort((tris[:, :, 2], tris[:, :, 1], tris[:, :, 0]), axis=1)
    canon = np.take_along_axis(tris, order[:, :, None], axis=1).reshape(len(tris), 9)
    return int(len(tris) - len(np.unique(canon, axis=0)))


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
        widest = max([text_width(label, UNIT_CELL_IN)] + [text_width(f["label"], FLAG_CELL_IN) for f in flags])
        x0 += max(width, widest) + GAP_IN
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


# ------------------------------------------------------------------------------------------ the SketchUp file

PROTECTED = ("CHECKPOINT-17-BACKUP", r"PROJECTS\UC\02-SKETCHUP", "UC ENVIRONMENT BUILDING")
TUBE_R_IN = 1.5             # open-edge tube radius
MARKER_R_IN = 3.0           # crack / degenerate-face marker radius
PLATE_Z_IN = -2.0
CHUNK = 20000               # faces per SUGeometryInput

KIND_NAMES = {"base": "NO ERROR", "flicker_diff": "FLICKER DIFFERENT LOOK", "flicker_same": "FLICKER SAME LOOK",
              "reversed": "REVERSED", "loose": "LOOSE BITS", "hidden": "HIDDEN", "open_edges": "OPEN EDGES",
              "cracks": "CRACKS", "excluded": "EXCLUDED COPY", "skp_mismatch": "EXPORT VS BACKUP"}


def tag_of(kind: str) -> str:
    if kind in ("base", "labels"):
        return kind
    if kind in ERROR_KINDS or kind in LINE_KINDS:
        return f"error_{kind}"
    return f"grouping_{kind}"


TAGS = ["base"] + [tag_of(k) for k in ERROR_KINDS + LINE_KINDS] + [tag_of(k) for k in GROUPING_KINDS] + ["labels"]


def _check_out(out) -> None:
    text = str(out).replace("/", "\\").upper()
    for p in PROTECTED:
        if p.upper() in text:
            raise ValueError(f"refusing to write {out}: it lies in a protected folder ({p})")


def _tubes(seg: np.ndarray, r: float = TUBE_R_IN) -> np.ndarray:
    """(s, 2, 3) segments -> (3s, 4, 3) quads of an open triangular tube around each."""
    seg = np.asarray(seg, float).reshape(-1, 2, 3)
    d = seg[:, 1] - seg[:, 0]
    length = np.linalg.norm(d, axis=1)
    keep = length > 0.01
    seg, d = seg[keep], d[keep] / length[keep, None]
    if not len(seg):
        return np.zeros((0, 4, 3))
    helper = np.where(np.abs(d[:, 2:3]) < 0.9, [[0.0, 0.0, 1.0]], [[1.0, 0.0, 0.0]])
    u = np.cross(d, helper)
    u /= np.linalg.norm(u, axis=1)[:, None]
    v = np.cross(d, u)
    ring = [r * (np.cos(a) * u + np.sin(a) * v) for a in (0.0, 2 * np.pi / 3, 4 * np.pi / 3)]
    quads = []
    for i in range(3):
        a, b = ring[i], ring[(i + 1) % 3]
        quads.append(np.stack([seg[:, 0] + a, seg[:, 0] + b, seg[:, 1] + b, seg[:, 1] + a], axis=1))
    return np.concatenate(quads)


_OCTA = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], float)
_OCTA_F = np.array([[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4], [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]])


def _markers(points: np.ndarray, r: float = MARKER_R_IN) -> np.ndarray:
    """(m, 3) points -> (8m, 3, 3) octahedron triangles."""
    points = np.asarray(points, float).reshape(-1, 3)
    if not len(points):
        return np.zeros((0, 3, 3))
    tri = _OCTA[_OCTA_F] * r                                   # (8, 3, 3)
    return (points[:, None, None, :] + tri[None]).reshape(-1, 3, 3)


def _rect(x: float, y: float, w: float, h: float, z: float = 0.0) -> np.ndarray:
    return np.array([[x, y, z], [x + w, y, z], [x + w, y + h, z], [x, y + h, z]], float)


def _ring(x0: float, y0: float, x1: float, y1: float, m0: float, m1: float, z: float) -> np.ndarray:
    """Four quads framing [x0, x1] x [y0, y1] between margins m0 and m1."""
    return np.stack([_rect(x0 - m1, y0 - m1, x1 - x0 + 2 * m1, m1 - m0, z),
                     _rect(x0 - m1, y1 + m0, x1 - x0 + 2 * m1, m1 - m0, z),
                     _rect(x0 - m1, y0 - m0, m1 - m0, y1 - y0 + 2 * m0, z),
                     _rect(x1 + m0, y0 - m0, m1 - m0, y1 - y0 + 2 * m0, z)])


def _text(text: str, x: float, y: float, cell: float, z: float = 0.0) -> np.ndarray:
    from engine.campus.pixfont import text_rects
    rects = [_rect(rx, ry, rw, rh, z) for rx, ry, rw, rh in text_rects(text, x, y, cell)]
    return np.stack(rects) if rects else np.zeros((0, 4, 3))


def _bind(api) -> None:
    from ctypes import c_char_p, c_int, c_size_t
    from engine.io.skp_writer import _RP, _SP, _Ref
    api.bind({
        "SUGroupCreate": ([_RP], c_int), "SUEntitiesAddGroup": ([_Ref, _Ref], c_int),
        "SUGroupSetName": ([_Ref, c_char_p], c_int), "SUGroupGetName": ([_Ref, _RP], c_int),
        "SUGroupGetEntities": ([_Ref, _RP], c_int), "SUGroupToDrawingElement": ([_Ref], _Ref),
        "SULayerCreate": ([_RP], c_int), "SULayerSetName": ([_Ref, c_char_p], c_int),
        "SULayerGetName": ([_Ref, _RP], c_int), "SUModelAddLayers": ([_Ref, c_size_t, _RP], c_int),
        "SUModelGetNumLayers": ([_Ref, _SP], c_int), "SUModelGetLayers": ([_Ref, c_size_t, _RP, _SP], c_int),
        "SUDrawingElementSetLayer": ([_Ref, _Ref], c_int), "SUDrawingElementGetLayer": ([_Ref, _RP], c_int),
        "SUEntitiesGetNumGroups": ([_Ref, _SP], c_int),
        "SUEntitiesGetGroups": ([_Ref, c_size_t, _RP, _SP], c_int),
    })


class _Writer:
    def __init__(self, api, model):
        from ctypes import byref
        from engine.io.skp_writer import _Color, _Ref
        self.api, self.model = api, model
        self.faces_by_tag: dict[str, int] = {}
        self.rejected = 0
        self.groups = 0
        self.materials, self.layers = {}, {}
        mats = []
        for key, rgb in COLOURS.items():
            m = _Ref()
            api.ok("SUMaterialCreate", byref(m))
            api.ok("SUMaterialSetName", m, f"UC_{key}".encode("utf-8"))
            api.ok("SUMaterialSetColor", m, byref(_Color(*rgb, 255)))
            self.materials[key] = m
            mats.append(m)
        api.ok("SUModelAddMaterials", model, len(mats), (_Ref * len(mats))(*mats))
        lays = []
        for name in TAGS:
            lay = _Ref()
            api.ok("SULayerCreate", byref(lay))
            api.ok("SULayerSetName", lay, name.encode("utf-8"))
            self.layers[name] = lay
            lays.append(lay)
        api.ok("SUModelAddLayers", model, len(lays), (_Ref * len(lays))(*lays))
        self.root = _Ref()
        api.ok("SUModelGetEntities", model, byref(self.root))

    def group(self, parent, name: str, tag: str | None = None):
        from ctypes import byref
        from engine.io.skp_writer import _Ref
        g, ents = _Ref(), _Ref()
        self.api.ok("SUGroupCreate", byref(g))
        self.api.ok("SUEntitiesAddGroup", parent, g)
        self.api.ok("SUGroupSetName", g, name.encode("utf-8"))
        if tag is not None:
            self.api.ok("SUDrawingElementSetLayer", self.api.raw("SUGroupToDrawingElement", g), self.layers[tag])
        self.api.ok("SUGroupGetEntities", g, byref(ents))
        self.groups += 1
        return ents

    def fill(self, ents, polys: np.ndarray, colour: str, tag: str) -> None:
        """Add (k, n, 3) polygons, each one face, both sides in `colour`."""
        from ctypes import byref, c_size_t
        from engine.io.skp_writer import _MaterialInput, _Point3D, _Ref
        polys = np.asarray(polys, float)
        if not len(polys):
            return
        api, n = self.api, polys.shape[1]
        mi = _MaterialInput()
        mi.material = self.materials[colour]
        for start in range(0, len(polys), CHUNK):
            part = np.ascontiguousarray(polys[start:start + CHUNK].reshape(-1, 3), dtype=np.float64)
            geom = _Ref()
            api.ok("SUGeometryInputCreate", byref(geom))
            try:
                api.ok("SUGeometryInputSetVertices", geom, len(part),
                       (_Point3D * len(part)).from_buffer_copy(part.tobytes()))
                added = 0
                for f in range(len(part) // n):
                    loop = _Ref()
                    api.ok("SULoopInputCreate", byref(loop))
                    for i in range(n):
                        api.ok("SULoopInputAddVertexIndex", loop, f * n + i)
                    index = c_size_t()
                    if api.raw("SUGeometryInputAddFace", geom, byref(loop), byref(index)) != 0:
                        api.raw("SULoopInputRelease", byref(loop))
                        self.rejected += 1
                        continue
                    api.ok("SUGeometryInputFaceSetFrontMaterial", geom, index.value, byref(mi))
                    api.ok("SUGeometryInputFaceSetBackMaterial", geom, index.value, byref(mi))
                    added += 1
                api.ok("SUEntitiesFill", ents, geom, True)
                self.faces_by_tag[tag] = self.faces_by_tag.get(tag, 0) + added
            finally:
                api.raw("SUGeometryInputRelease", byref(geom))


def _draw_column(w: _Writer, col: ColumnPlan) -> None:
    ents = w.group(w.root, f"UNIT | {col.label}")
    for mp in col.members:
        ments = w.group(ents, f"MEMBER | {mp.group}")
        for kind in ("base",) + ERROR_KINDS + ("excluded",):
            tris = mp.tris.get(kind, np.zeros((0, 3, 3)))
            marks = _markers(mp.markers.get(kind, np.zeros((0, 3))))
            if not len(tris) and not len(marks):
                continue
            kents = w.group(ments, f"{KIND_NAMES.get(kind, kind.upper())} | {len(tris)} faces", tag_of(kind))
            w.fill(kents, tris, kind, tag_of(kind))
            w.fill(kents, marks, kind, tag_of(kind))
        if len(mp.segments):
            w.fill(w.group(ments, f"OPEN EDGES | {len(mp.segments)} edges", tag_of("open_edges")),
                   _tubes(mp.segments), "open_edges", tag_of("open_edges"))
        if len(mp.cracks):
            w.fill(w.group(ments, f"CRACKS | {len(mp.cracks)} cells", tag_of("cracks")),
                   _markers(mp.cracks), "cracks", tag_of("cracks"))
    x0, x1, y1 = col.x0, col.x0 + col.width, col.depth
    y = -120.0 - 7 * UNIT_CELL_IN
    w.fill(w.group(ents, f"LABEL | {col.label}", "labels"), _text(col.label, x0, y, UNIT_CELL_IN), "labels",
           "labels")
    for j, flag in enumerate(col.flags):
        tag = tag_of(flag["kind"])
        gents = w.group(ents, f"GROUPING | {flag['kind']} | {flag.get('text', '')}"[:1000], tag)
        m0 = 40.0 + j * 50.0
        w.fill(gents, _ring(x0, 0.0, x1, y1, m0, m0 + 40.0, PLATE_Z_IN), flag["kind"], tag)
        w.fill(gents, _text(flag["label"], x0, y - (j + 1) * LINE_PITCH * FLAG_CELL_IN, FLAG_CELL_IN),
               flag["kind"], tag)


def _draw_legend(w: _Writer, plan: BuildingPlan) -> None:
    ents = w.group(w.root, f"LEGEND | {plan.building}", "labels")
    x = -GAP_IN - 2400.0
    pitch = LINE_PITCH * LEGEND_CELL_IN
    rows = [(k, plan.counts.get(k)) for k in ("base",) + ERROR_KINDS + LINE_KINDS]
    used = sorted({f["kind"] for c in plan.columns for f in c.flags}, key=GROUPING_KINDS.index)
    rows += [(k, sum(f["kind"] == k for c in plan.columns for f in c.flags)) for k in used]
    top = len(rows) * pitch
    w.fill(ents, _text(f"{plan.building} ERRORS", x, top + pitch, 2 * LEGEND_CELL_IN), "labels", "labels")
    for i, (kind, count) in enumerate(rows):
        yy = top - i * pitch
        w.fill(ents, _rect(x, yy, 7 * LEGEND_CELL_IN, 7 * LEGEND_CELL_IN)[None], kind, "labels")
        name = KIND_NAMES.get(kind, kind.upper())
        text = name if count is None else f"{name} {count}"
        w.fill(ents, _text(text, x + 10 * LEGEND_CELL_IN, yy, LEGEND_CELL_IN), "labels", "labels")


def write_building_skp(plan: BuildingPlan, out, dll_path=None) -> dict:
    """Draw `plan` into a new SketchUp file at `out`. Returns the faces added per tag and the faces SketchUp
    refused."""
    from ctypes import byref
    from pathlib import Path
    from engine.io.skp_writer import _Ref, load_api
    out = Path(out)
    _check_out(out)
    api = load_api(dll_path)
    _bind(api)
    out.parent.mkdir(parents=True, exist_ok=True)
    with api.session():
        model = _Ref()
        api.ok("SUModelCreate", byref(model))
        try:
            w = _Writer(api, model)
            _draw_legend(w, plan)
            for col in plan.columns:
                _draw_column(w, col)
            api.ok("SUModelSaveToFile", model, str(out).encode("utf-8"))
        finally:
            api.raw("SUModelRelease", byref(model))
    return {"out": str(out), "faces_by_tag": dict(sorted(w.faces_by_tag.items())), "rejected_faces": w.rejected,
            "groups": w.groups}


def read_back(path, dll_path=None) -> dict:
    """Tags, faces per tag (a face counts under the nearest tagged group above it) and group names of a file."""
    from ctypes import byref
    from pathlib import Path
    from engine.io.skp_writer import _Ref, _open, _refs, _string, load_api
    api = load_api(dll_path)
    _bind(api)
    faces: dict[str, int] = {}
    names: list[str] = []
    with api.session(), _open(api, Path(path)) as model:
        tags = [_string(api, "SULayerGetName", lay)
                for lay in _refs(api, "SUModelGetNumLayers", "SUModelGetLayers", model)]

        def walk(ents, tag):
            n = len(_refs(api, "SUEntitiesGetNumFaces", "SUEntitiesGetFaces", ents))
            if n:
                faces[tag] = faces.get(tag, 0) + n
            for g in _refs(api, "SUEntitiesGetNumGroups", "SUEntitiesGetGroups", ents):
                names.append(_string(api, "SUGroupGetName", g))
                lay = _Ref()
                api.ok("SUDrawingElementGetLayer", api.raw("SUGroupToDrawingElement", g), byref(lay))
                name = _string(api, "SULayerGetName", lay)
                sub = _Ref()
                api.ok("SUGroupGetEntities", g, byref(sub))
                walk(sub, tag if name in ("Layer0", "Untagged") else name)

        root = _Ref()
        api.ok("SUModelGetEntities", model, byref(root))
        walk(root, "untagged")
    return {"tags": tags, "faces_by_tag": dict(sorted(faces.items())), "group_names": names}


# ------------------------------------------------------------------------------------------ the command

def _sha256(path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _engine_commit() -> str:
    import subprocess
    from pathlib import Path
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent,
                             capture_output=True, text=True, timeout=30)
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True, timeout=30)
        return out.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "") if out.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def cmd_campus_errors_skp(campus_map, source, errors_dir, skp_check, out_dir, buildings=None,
                          dll_path=None) -> list[dict]:
    """Write `<out_dir>/<BUILDING>/<BUILDING>-errors.skp` and `-errors.json` for each building."""
    import json
    from pathlib import Path
    from engine.campus.census import _load_snapshot_mesh
    from engine.campus.inventory import building_of
    out_dir, errors_dir = Path(out_dir), Path(errors_dir)
    _check_out(out_dir)
    cmap = json.loads(Path(campus_map).read_text(encoding="utf-8"))
    snaps = {s["group"]: Path(s["dir"]) for s in json.loads(Path(source).read_text(encoding="utf-8"))["snapshots"]}
    mismatches = {m["file"]: m for m in json.loads(Path(skp_check).read_text(encoding="utf-8"))["mismatches"]}
    names = sorted({u["building"] for u in cmap["units"]} | {building_of(e["group"]) for e in cmap.get("excluded", [])})
    commit = _engine_commit()
    used: dict[str, str] = {}

    def load_member(group: str):
        _, mesh = _load_snapshot_mesh(snaps[group])
        path = errors_dir / f"{group}.json"
        used[group] = _sha256(path)
        return mesh.positions, mesh.face_v, json.loads(path.read_text(encoding="utf-8"))

    reports = []
    for name in buildings or names:
        plan = plan_building(name, cmap, load_member, mismatches=mismatches, building_of=building_of)
        skp = out_dir / name / f"{name}-errors.skp"
        written = write_building_skp(plan, skp, dll_path)
        back = read_back(skp, dll_path)
        dups: dict[str, int] = {}
        for c in plan.columns:
            for m in c.members:
                for kind, tris in m.tris.items():
                    if n := exact_duplicates(tris):
                        dups[tag_of(kind)] = dups.get(tag_of(kind), 0) + n
        tags = set(written["faces_by_tag"]) | set(back["faces_by_tag"])
        unexplained = {t: back["faces_by_tag"].get(t, 0) - (written["faces_by_tag"].get(t, 0) - dups.get(t, 0))
                       for t in sorted(tags)}
        report = {
            "building": name, "skp": str(skp), "skp_sha256": _sha256(skp), "engine_commit": commit,
            "counts": plan.counts,
            "columns": [{"unit": c.unit, "label": c.label, "type": c.type, "counts": c.counts,
                         "flags": [{"kind": f["kind"], "label": f["label"], "text": f.get("text", "")}
                                   for f in c.flags],
                         "skipped_degenerate_base": sum(m.skipped_degenerate_base for m in c.members)}
                        for c in plan.columns],
            "written": written, "read_back": {"faces_by_tag": back["faces_by_tag"], "tags": back["tags"]},
            "duplicates_by_tag": dups,
            "unexplained_by_tag": {t: d for t, d in unexplained.items() if d},
            "inputs": {"campus_map": _sha256(campus_map), "skp_check": _sha256(skp_check),
                       "errors": {g: used[g] for g in sorted(used)}},
            "draw_rule": "each face in the first kind listing it: " + ", ".join(ERROR_KINDS) + "; else base",
        }
        (out_dir / name / f"{name}-errors.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        reports.append(report)
        used.clear()
    return reports
