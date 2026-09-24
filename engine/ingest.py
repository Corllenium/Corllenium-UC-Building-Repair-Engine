"""Building-level ingestion: snapshot every mapped object of one building from a split export.

The split export names objects inconsistently (`Chtm_2nd_floor`, `chtm_5ft_floor`,
`CHTM_7th_floor_obj`); the floor map (schema `corllenium.floor_map/1`) says which OBJ stem is
which canonical floor object (the `floors.model_object_name` in Supabase). Every mapped object is
snapshotted with `engine.io.snapshot.snapshot_object`, under `<out_root>/<building>/<canonical>/`,
and the outcome per object is written to `<out_root>/<building>/ingest_manifest.json`.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from engine.io.snapshot import ManifestMismatch, SourceUnstable, read_manifest, snapshot_object

FLOOR_MAP_SCHEMA = "corllenium.floor_map/1"
INGEST_SCHEMA = "corllenium.ingest/1"


@dataclass
class FloorMapEntry:
    building: str
    split_object: str   # OBJ stem in the split folder, e.g. "Chtm_2nd_floor"
    canonical: str      # floors.model_object_name, e.g. "CHTM_2nd_floor_obj"
    level_code: str     # "3B", "4F", "RF"; "" for sidewalks and site pieces
    role: str           # "floor" | "sidewalk" | "site" | "reference"


@dataclass
class IngestRow:
    canonical: str
    split_object: str
    level_code: str
    role: str
    status: str         # "ok" | "unlisted" | "missing" | "manifest_mismatch" | "unstable"
    snapshot_dir: str | None = None
    sha256: str | None = None
    tris: int | None = None
    detail: str = ""


def load_floor_map(path: Path, building: str | None = None) -> list[FloorMapEntry]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != FLOOR_MAP_SCHEMA:
        raise ValueError(f"{path}: expected schema {FLOOR_MAP_SCHEMA!r}, found {data.get('schema')!r}")
    entries = [FloorMapEntry(**e) for e in data["entries"]]
    if building is not None:
        entries = [e for e in entries if e.building == building]
    return entries


def ingest_building(source_dir, manifest_path, building: str, floor_map_path, out_root,
                    interval_s: float = 1.0, sleep=time.sleep) -> list[IngestRow]:
    source_dir, out_root = Path(source_dir), Path(out_root)
    manifest = read_manifest(Path(manifest_path))
    rows: list[IngestRow] = []
    for e in load_floor_map(floor_map_path, building):
        src = source_dir / f"{e.split_object}.obj"
        listed = manifest.get(src.name)
        row = IngestRow(e.canonical, e.split_object, e.level_code, e.role, status="ok")
        if not src.exists():
            row.status, row.detail = "missing", str(src)
            rows.append(row)
            continue
        try:
            res = snapshot_object(src, out_root / building / e.canonical,
                                  expected_tris=listed.tris if listed else None,
                                  interval_s=interval_s, sleep=sleep)
        except ManifestMismatch as exc:
            row.status, row.detail = "manifest_mismatch", str(exc)
            rows.append(row)
            continue
        except SourceUnstable as exc:
            row.status, row.detail = "unstable", str(exc)
            rows.append(row)
            continue
        row.status = "ok" if listed else "unlisted"
        row.snapshot_dir, row.sha256, row.tris = str(res.dir), res.sha256, res.mesh.n_faces
        rows.append(row)

    out_dir = out_root / building
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ingest_manifest.json").write_text(json.dumps({
        "schema": INGEST_SCHEMA, "building": building, "source_dir": str(source_dir),
        "rows": [asdict(r) for r in rows]}, indent=2), encoding="utf-8")
    return rows
