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

from engine.io.atomic import atomic_write_text
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
    status: str         # "ok" | "unlisted" | "missing" | "manifest_mismatch" | "unstable" | "error"
    snapshot_dir: str | None = None
    sha256: str | None = None
    tris: int | None = None
    detail: str = ""


def load_floor_map(path: Path, building: str | None = None) -> list[FloorMapEntry]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != FLOOR_MAP_SCHEMA:
        raise ValueError(f"{path}: expected schema {FLOOR_MAP_SCHEMA!r}, found {data.get('schema')!r}")
    entries = [FloorMapEntry(**e) for e in data["entries"]]

    # C2: two rows mapping the same (building, canonical) or (building, split_object) is a floor
    # map bug -- the second row would silently overwrite (or race) the first's snapshot, or two
    # canonicals would fight over which split OBJ is "theirs". Checked over ALL entries, not just
    # a `building`-filtered subset, so the map's own integrity does not depend on which building a
    # caller happens to be asking for right now.
    seen_canonical: dict[tuple[str, str], FloorMapEntry] = {}
    seen_split: dict[tuple[str, str], FloorMapEntry] = {}
    for e in entries:
        ckey = (e.building, e.canonical)
        if ckey in seen_canonical:
            raise ValueError(f"{path}: duplicate canonical {e.canonical!r} for building {e.building!r}")
        seen_canonical[ckey] = e
        skey = (e.building, e.split_object)
        if skey in seen_split:
            raise ValueError(f"{path}: duplicate split_object {e.split_object!r} for building {e.building!r}")
        seen_split[skey] = e

    if building is not None:
        entries = [e for e in entries if e.building == building]
    return entries


def ingest_building(source_dir, manifest_path, building: str, floor_map_path, out_root,
                    interval_s: float = 1.0, sleep=time.sleep) -> list[IngestRow]:
    source_dir, out_root = Path(source_dir), Path(out_root)

    # C1: an unmapped/typo'd building must fail loudly here, before any snapshotting or manifest
    # write -- not silently produce a "0/0 snapshotted" manifest that looks like a clean, empty
    # success. `all_entries` (unfiltered) is what names the buildings that DO exist.
    all_entries = load_floor_map(floor_map_path)
    entries = [e for e in all_entries if e.building == building]
    if not entries:
        raise ValueError(f"{floor_map_path}: no entries for building {building!r}; "
                         f"known: {sorted(set(e.building for e in all_entries))}")

    manifest = read_manifest(Path(manifest_path))
    rows: list[IngestRow] = []
    for e in entries:
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
        except ValueError as exc:
            row.status, row.detail = "error", str(exc)
            rows.append(row)
            continue
        row.status = "ok" if listed else "unlisted"
        row.snapshot_dir, row.sha256, row.tris = str(res.dir.resolve()), res.sha256, res.mesh.n_faces
        rows.append(row)

    out_dir = out_root / building
    out_dir.mkdir(parents=True, exist_ok=True)
    # C3: absolute paths -- a manifest read back by `engine.batch.discover_items` from a
    # different cwd (or a `batch` run days later) must not depend on where `ingest` happened to
    # be run from.
    atomic_write_text(out_dir / "ingest_manifest.json", json.dumps({
        "schema": INGEST_SCHEMA, "building": building, "source_dir": str(source_dir.resolve()),
        "rows": [asdict(r) for r in rows]}, indent=2))
    return rows
