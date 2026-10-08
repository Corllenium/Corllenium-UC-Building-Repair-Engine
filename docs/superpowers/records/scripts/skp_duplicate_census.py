"""One-off probe for job P0-11 (2026-10-03): how much of the CHECKPOINT-17 backup's face area is exact
duplicate faces, and does taking them out reconcile the backup with the export?

WHY. `campus-skp-check` finds 18 of 85 export files whose face area is 0.5-2.1 % smaller than what the
backup holds for them (their boxes agree to 0.05 in). This script tests one explanation: the backup
stacks faces exactly on top of each other (same corners to 0.1 in, same facing) and the export lacks
many of the copies. For every split file it adds up the area of the backup's faces, then the area of
those faces that repeat an earlier face of the same file, and compares both with the export.

HOW. Read only, through `engine.io.skp_reader` (it cannot save): it opens the verified copy of the
backup that `campus-skp-check` made, groups the faces by the same split rule `engine.campus.skp_check`
uses, and prints a table. It uses the reader's PRIVATE helpers (`_Walker`, `_Visibility`, `_refs`, `_open`),
so it is a probe, not an engine module. It needs about 2.7 GB of commit memory. It opens nothing else:
`--skp` must be a file in a `data/campus/skp_copy/` folder whose sha256 is the one `--source` froze
(`skp_check.require_verified_copy`, AGENTS.md section 2), or it prints an error and exits with 2.

    PYTHONPATH="<repo root>" .venv/Scripts/python.exe docs/superpowers/records/scripts/skp_duplicate_census.py \
        --source data/campus/source.json --skp "data/campus/skp_copy/<backup>.skp" [--out census.json]

RESULT, 2026-10-03, source.json of 19:12:52, 70 files that have exactly one group in the backup: 56 are
within 0.5 % of the export's area as they stand and 64 once the duplicates are taken out (CHTM 3rd floor
+1.86 % becomes +0.39 %, Architecture dep 7th floor +1.05 % becomes 0.00 %). It does not explain all of it:
`unnamed` stays at +2.09 % and EDS 1st floor at +0.71 %. And the export itself still holds 5,456 exact
duplicate triangles, so it is not a complete de-duplication.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from collections import defaultdict
from ctypes import byref, c_double, c_size_t
from pathlib import Path

import numpy as np

from engine.campus import skp_check
from engine.io import skp_reader as R

#: Corners are compared to this many decimals (inches) and facings to two.
CORNER_DECIMALS = 1


class FaceData:
    """The faces a viewer sees in one entities collection: area, normal and the vertex indices of each,
    plus the distinct vertex positions (in the collection's own coordinates)."""

    def __init__(self, api, entities, visibility):
        self.faces: list[tuple[float, tuple, list[int]]] = []
        positions: dict[int, int] = {}
        order: list[tuple] = []
        area, normal, point = c_double(), R._Point3D(), R._Point3D()
        count, got = c_size_t(), c_size_t()
        for face in R._refs(api, "SUEntitiesGetNumFaces", "SUEntitiesGetFaces", entities):
            if visibility.reason(api.raw("SUFaceToDrawingElement", face)) is not None:
                continue
            api.ok("SUFaceGetArea", face, byref(area))
            api.ok("SUFaceGetNormal", face, byref(normal))
            api.ok("SUFaceGetNumVertices", face, byref(count))
            vertices = (R._Ref * count.value)()
            api.ok("SUFaceGetVertices", face, count.value, vertices, byref(got))
            indices = []
            for v in vertices[:got.value]:
                if v.ptr not in positions:
                    api.ok("SUVertexGetPosition", v, byref(point))
                    positions[v.ptr] = len(order)
                    order.append((point.x, point.y, point.z))
                indices.append(positions[v.ptr])
            self.faces.append((area.value, (normal.x, normal.y, normal.z), indices))
        self.points = np.array(order, float).reshape(-1, 3)


def census(skp: Path) -> dict[str, list[dict]]:
    """`{file key: [one entry per group that gives it: faces, area, duplicate faces, duplicate area]}`."""
    units: dict[tuple, dict] = defaultdict(lambda: {"area": 0.0, "dup_area": 0.0, "faces": 0, "dups": 0,
                                                    "seen": set()})
    cache: dict[int, FaceData] = {}
    uids = itertools.count(1)              # a group's identity (id() is reused once a node is gone)
    api = R.load_api()
    with api.session(), R._open(api, skp) as model:
        root = R._Ref()
        api.ok("SUModelGetEntities", model, byref(root))
        visibility = R._Visibility(api)
        walker = R._Walker(api)

        def visit(entities, chain, world):
            if entities.ptr not in cache:
                cache[entities.ptr] = FaceData(api, entities, visibility)
            data = cache[entities.ptr]
            if data.faces:
                key, selected = skp_check.split_key(chain) if chain else (skp_check.UNNAMED, None)
                unit = units[(key, selected["uid"] if selected is not None else 0)]
                unit["key"] = key
                linear = world[:3, :3]
                det = abs(np.linalg.det(linear))
                inverse = np.linalg.inv(linear) if det > 0 else None
                moved = data.points @ linear.T + world[:3, 3]
                for area, normal, indices in data.faces:
                    n = np.array(normal) @ inverse if inverse is not None else np.array(normal)
                    scaled = area * det * np.linalg.norm(n) if inverse is not None else 0.0
                    facing = np.round(n / (np.linalg.norm(n) or 1.0), 2) + 0.0
                    corners = np.round(moved[indices], CORNER_DECIMALS) + 0.0
                    signature = hash((tuple(sorted(map(tuple, corners.tolist()))), tuple(facing.tolist())))
                    unit["faces"] += 1
                    unit["area"] += scaled
                    if signature in unit["seen"]:
                        unit["dup_area"] += scaled
                        unit["dups"] += 1
                    else:
                        unit["seen"].add(signature)
            for kind, name, definition, reason, local, inner in walker.children(entities):
                if reason is None:
                    visit(inner, chain + [{"kind": kind, "name": name, "definition": definition,
                                           "uid": next(uids)}], world @ local)

        visit(root, [], np.eye(4))
    out: dict[str, list[dict]] = {}
    for unit in units.values():
        out.setdefault(unit["key"], []).append({k: unit[k] for k in ("faces", "area", "dups", "dup_area")})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--skp", type=Path, required=True, help="the verified copy of the backup")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    source = json.loads(args.source.read_text(encoding="utf-8"))
    try:                                  # before the SDK is touched: only the verified copy is opened
        skp = skp_check.require_verified_copy(source, args.skp)
    except (skp_check.BackupMismatch, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    snapshots = {s["file"]: s["dir"] for s in source["snapshots"]}
    started = time.time()
    result = census(skp)
    print(f"walked in {time.time() - started:.1f} s; {sum(len(v) for v in result.values())} groups give a file")
    rows = []
    for m in source["manifest"]:
        groups = result.get(m["group"])
        if not groups or len(groups) != 1:
            continue                                  # two groups of one name cannot be told apart here
        export = skp_check.export_stats(snapshots[m["file"]])["area"]
        g = groups[0]
        before = (g["area"] - export) / export * 100
        after = (g["area"] - g["dup_area"] - export) / export * 100
        rows.append((abs(before), m["group"], g, export, before, after))
    rows.sort(key=lambda r: -r[0])
    print("file | backup area | duplicate area (faces / all faces) | export area | before | after removing them")
    for _, name, g, export, before, after in rows[:30]:
        print(f"{name[:32]:32} {g['area']:14,.0f} {g['dup_area']:10,.0f} ({g['dups']:4d}/{g['faces']:5d}) "
              f"{export:14,.0f} {before:+7.3f}% {after:+7.3f}%")
    print(f"files with one group: {len(rows)}; within 0.5 % as they stand: "
          f"{sum(1 for r in rows if abs(r[4]) <= 0.5)}; after removing the duplicates: "
          f"{sum(1 for r in rows if abs(r[5]) <= 0.5)}")
    if args.out:
        args.out.write_text(json.dumps(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
