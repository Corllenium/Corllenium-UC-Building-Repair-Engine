"""Fail-closed Task 1 runner. Real cleanup stays blocked until lossless ingest is proven.

This entry point currently audits/freeze-checks the approved source and pilots only.
It does not create candidate meshes or claim the unfinished Tasks 1-3 are complete.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path

import numpy as np

from engine.io.minecraft_floor import FloorFormatError, _triangulate, parse_floor
from engine.io.mtl import parse_mtl
from engine.io.snapshot import copy_verified, sha256_file


FILES = {f"{i}F": f"{ordinal} floor main infra.obj" for i, ordinal in
         enumerate(("1st", "2nd", "3rd", "4th", "5th", "6th", "7th"), 1)}
PILOTS = {key: FILES[key] for key in ("1F", "4F")}
MISSING = ["physical_scale_evidence", "raw_vs_normalized_render_comparison",
           "26_view_candidate_guard", "independent_validator", "independent_reviewer", "owner_floor_acceptance"]


def freeze_source(source, root, *, interval_s=1.0, progress=None):
    source, root = Path(source).resolve(), Path(root).resolve()
    if root.is_relative_to(source) or source.is_relative_to(root):
        raise ValueError('Live source and frozen run must be separate')
    paths = sorted(path for path in source.rglob('*') if path.is_file())
    if not paths or any(not path.resolve().is_relative_to(source) for path in paths):
        raise ValueError('Empty source or asset escapes source root')
    rows = [{'path': path.relative_to(source).as_posix(), 'size': path.stat().st_size,
             'sha256': sha256_file(path)} for path in paths]
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    manifest_path = root / 'raw-manifest.json'
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding='utf-8'))
        if existing.get('source_revision') != digest or verify_frozen(root, existing)['status'] != 'verified':
            raise ValueError('Source changed or frozen package differs; create a new run')
        return existing
    raw = root / 'raw'
    if raw.exists():
        raise ValueError('Incomplete frozen package already exists; do not overwrite it')
    raw.mkdir(parents=True)
    for index, (path, row) in enumerate(zip(paths, rows), 1):
        destination = raw / row['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy_verified(path, destination, interval_s=interval_s)
        if sha256_file(destination) != row['sha256']:
            raise ValueError('Source changed while freezing')
        if progress:
            progress(index, len(rows))
    final_paths = sorted(path for path in source.rglob('*') if path.is_file())
    if final_paths != paths or any(sha256_file(path) != row['sha256'] for path, row in zip(paths, rows)):
        raise ValueError('Source package changed while freezing')
    manifest = {'source': str(source), 'source_revision': digest, 'files': rows,
                'recorded_utc': datetime.now(timezone.utc).isoformat()}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def verify_frozen(root: Path, manifest: dict) -> dict:
    raw = (Path(root) / "raw").resolve()
    failures, expected = [], set()
    for row in manifest["files"]:
        path = (raw / row["path"]).resolve()
        if not path.is_relative_to(raw):
            failures.append(f"outside raw: {row['path']}")
            continue
        expected.add(path)
        if not path.is_file() or path.stat().st_size != row["size"] or sha256_file(path) != row["sha256"]:
            failures.append(f"missing or changed bytes: {row['path']}")
    actual = {p.resolve() for p in raw.rglob("*") if p.is_file()}
    failures.extend(f"unmanifested raw file: {p}" for p in sorted(actual - expected))
    return {"status": "blocked" if failures else "verified", "files": len(expected), "failures": failures}


def pilot_gate(raw: Path, *, pilots=None) -> dict:
    result = {"status": "blocked", "candidate_count": 0, "pilots": {}, "missing_gates": list(MISSING)}
    for key, filename in (pilots or PILOTS).items():
        try:
            floor = parse_floor((Path(raw) / filename).read_text(encoding="utf-8"), name=key)
            result["pilots"][key] = {"status": "parsed_native_only", "triangles": floor.mesh.n_faces,
                                      "units": floor.mesh.units}
        except (FloorFormatError, OSError) as exc:
            result["pilots"][key] = {"status": "blocked_ingest", "error": str(exc), "file": filename}
    if any(row["status"] == "blocked_ingest" for row in result["pilots"].values()):
        result["missing_gates"].insert(0, "lossless_polygon_ingest")
    return result


def polygon_census(path: Path) -> tuple[dict, list]:
    """Read-only diagnosis, including unsupported polygons; never a normalized engine mesh."""
    vertices, uvs, failures = [], [], []
    material, group, object_name = "", "", ""
    sizes, top_axis = Counter(), Counter()
    polygons, tri_equivalent = 0, 0
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = raw.split(maxsplit=1)
        if not parts:
            continue
        head, rest = parts[0], parts[1] if len(parts) > 1 else ""
        if head == "v":
            vertices.append(list(map(float, rest.split())))
        elif head == "vt":
            uvs.append(list(map(float, rest.split())))
        elif head == "usemtl":
            material = rest
        elif head == "g":
            group = rest
        elif head == "o":
            object_name = rest
        elif head == "f":
            tokens = [token.split("/") for token in rest.split()]
            refs = [int(token[0]) - 1 if int(token[0]) > 0 else len(vertices) + int(token[0]) for token in tokens]
            points = np.asarray([vertices[v] for v in refs])
            sizes[len(refs)] += 1
            polygons += 1
            tri_equivalent += len(refs) - 2
            local = points - points[0]
            normal = np.cross(local, np.roll(local, -1, axis=0)).sum(axis=0)
            length = np.linalg.norm(normal)
            distances = local @ (normal / length) if length else np.full(len(points), np.nan)
            if "_top_" in material and length:
                axis = int(np.argmax(np.abs(normal)))
                top_axis[("+" if normal[axis] > 0 else "-") + "XYZ"[axis]] += 1
            try:
                _triangulate(points, line_no)
            except FloorFormatError as exc:
                failures.append({"polygon_index": polygons - 1, "line": line_no, "record": raw,
                                 "error": str(exc), "material": material, "group": group,
                                 "object": object_name, "corner_tokens": rest.split(),
                                 "positions": points.tolist(),
                                 "max_planarity_distance_source_units": float(np.abs(distances).max()) if length else None})
    types = Counter(row["error"].partition(": ")[2] for row in failures)
    return {"file": path.name, "source_polygons": polygons, "triangle_equivalent": tri_equivalent,
            "polygon_sizes": dict(sizes), "unsupported_polygons": len(failures), "unsupported_types": dict(types),
            "top_named_material_dominant_normal_axes": dict(top_axis),
            "units": "unverified: no source unit metadata/calibrated owner dimension provided",
            "diagnostic_only": True}, failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--audit-ingest", action="store_true", required=True)
    parser.add_argument("--non-interactive", action="store_true", required=True)
    parser.add_argument('--freeze-source', type=Path)
    parser.add_argument('--progress', type=Path)
    parser.add_argument('--publish-status', type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    allowed = (Path.cwd() / "data" / "main-infra-fresh").resolve()
    if not root.is_relative_to(allowed) or root == allowed:
        parser.error("root must be a run directory under this sandbox's data/main-infra-fresh")
    if args.freeze_source:
        from tools.main_infra_progress import load_progress, update_floor, utc_now, write_progress
        def event(done, total):
            print(f'FREEZE {done}/{total} files verified', flush=True)
            if args.progress:
                update_floor(args.progress, '1F', 'importing', f'Freezing source package: {done}/{total} files verified', published_path=args.publish_status)
        manifest = freeze_source(args.freeze_source, root, progress=event)
        native = pilot_gate(root / 'raw')['pilots']
        (root / 'native-ingest-reproduction.json').write_text(json.dumps(native, indent=2), encoding='utf-8')
        if args.progress:
            doc = load_progress(args.progress)
            doc.update(source_revision=manifest['source_revision'], source_state='frozen',
                       updated_at=utc_now(), last_work_event_at=utc_now(), step='Fresh source frozen; native polygon rejection reproduced; reference tessellation is next')
            write_progress(args.progress, doc, published_path=args.publish_status)
            for key, result in native.items():
                if result['status'] == 'blocked_ingest':
                    update_floor(args.progress, key, 'blocked', 'Native importer reproduction complete', blocker=result['error'], published_path=args.publish_status)
        print(json.dumps({'frozen_files': len(manifest['files']), 'source_revision': manifest['source_revision'], 'native_pilots': native}))
        return 0
    manifest = json.loads((root / "raw-manifest.json").read_text())
    frozen = verify_frozen(root, manifest)
    (root / "freeze-readback.json").write_text(json.dumps(frozen, indent=2))
    if frozen["status"] != "verified":
        print(json.dumps(frozen, indent=2))
        return 2
    dependencies = []
    raw = root / "raw"
    for path in sorted(raw.glob("*.mtl")):
        for name, mat in parse_mtl(path).items():
            texture = (path.parent / mat.map_kd).resolve() if mat.map_kd else None
            if texture is not None and (not texture.is_relative_to(raw.resolve()) or not texture.is_file()):
                dependencies.append(f"missing or escaping texture: {path.name}: {name}: {mat.map_kd}")
    (root / "asset-dependencies.json").write_text(json.dumps({"failures": dependencies, "verified": not dependencies}, indent=2))
    gate = pilot_gate(raw)
    if dependencies:
        gate["missing_gates"].insert(0, "self_contained_material_dependencies")
    (root / "pilot-gate.json").write_text(json.dumps(gate, indent=2))
    census, unsupported = [], {}
    for key, filename in FILES.items():
        summary, failures = polygon_census(raw / filename)
        census.append({"floor": key, **summary})
        unsupported[key] = failures
    (root / "polygon-census.json").write_text(json.dumps(census, indent=2))
    (root / "unsupported-polygons.json").write_text(json.dumps(unsupported, indent=2, allow_nan=False))
    progress = json.loads((root / "progress.json").read_text())
    progress.update(status="blocked", step="stopped at lossless polygon ingest gate", tasks={
        "1": "blocked: source frozen; synthetic adapter tests pass; real pilot ingest failed",
        "2": "synthetic duplicate-only route tested; no real cleanup run",
        "3": "not_run: pilot ingest gate failed"}, missing_gates=gate["missing_gates"], candidate_count=0)
    for key in FILES:
        progress["floors"][key] = {"status": "blocked_ingest" if key in PILOTS else "not_run_pilot_gate_failed",
                                   "accepted": False, "candidate": None, "unsupported_source_polygons": len(unsupported[key])}
    progress["history"].append({"at": datetime.now(timezone.utc).isoformat(),
                                "event": "Immutable raw readback verified. Pilots blocked. Remaining floors inventoried only; no cleanup escalation."})
    (root / "progress.json").write_text(json.dumps(progress, indent=2))
    print(json.dumps({"freeze": frozen, "pilot_gate": gate, "census": census}, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
