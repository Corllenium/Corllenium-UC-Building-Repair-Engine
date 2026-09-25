import os
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import Model, ModelVersion, VersionAsset
from api.schemas import SourceFileOut
from api.settings import Settings
from engine.io.mtl import texture_flatness
from engine.io.snapshot import (
    ManifestMismatch,
    SnapshotResult,
    SourceUnstable,
    read_manifest_stable,
    sha256_file,
    snapshot_object,
)
from engine.pipeline import analyse_topology, flat_material_indices


def find_source_file(source_dir: Path, file_name: str, stable_interval_s: float = 1.0) -> tuple[Path, int | None]:
    """Finds an OBJ file under source_dir or source_dir/split and reads its manifest expected_tris if available."""
    candidates = [
        source_dir / file_name,
        source_dir / "split" / file_name,
    ]
    target: Path | None = None
    for cand in candidates:
        if cand.is_file():
            target = cand
            break

    if target is None:
        raise FileNotFoundError(f"Source file {file_name!r} not found in {source_dir} or {source_dir / 'split'}")

    manifest_path = target.parent / "_MANIFEST.txt"
    if not manifest_path.exists():
        manifest_path = source_dir / "_MANIFEST.txt"

    expected_tris = None
    if manifest_path.exists():
        m = read_manifest_stable(manifest_path, interval_s=stable_interval_s)
        if file_name in m:
            expected_tris = m[file_name].tris

    return target, expected_tris


def scan_source_directory(source_dir: Path, stable_interval_s: float = 1.0) -> list[SourceFileOut]:
    """Scans for available OBJ files in the source directory and split/ subfolder."""
    if not source_dir.exists():
        return []

    manifest_map: dict[str, int] = {}
    for manifest_cand in [source_dir / "_MANIFEST.txt", source_dir / "split" / "_MANIFEST.txt"]:
        if manifest_cand.exists():
            for name, row in read_manifest_stable(manifest_cand, interval_s=stable_interval_s).items():
                manifest_map[name] = row.tris

    found: dict[str, SourceFileOut] = {}

    def scan_folder(folder: Path):
        for p in folder.glob("*.obj"):
            if p.is_file() and not p.name.startswith("."):
                name = p.name
                if name not in found:
                    found[name] = SourceFileOut(
                        file=name,
                        tri_count=manifest_map.get(name),
                        size_bytes=p.stat().st_size,
                    )

    scan_folder(source_dir)
    if (source_dir / "split").is_dir():
        scan_folder(source_dir / "split")

    return sorted(found.values(), key=lambda s: s.file)


def import_model(db: Session, file_name: str, settings: Settings) -> Model:
    """Imports an OBJ export into an immutable snapshot and records it in PostgreSQL."""
    src_file, expected_tris = find_source_file(settings.source_dir, file_name, stable_interval_s=settings.stable_interval_s)

    snapshots_dir = settings.data_dir / "snapshots"
    snap: SnapshotResult = snapshot_object(
        src_file,
        snapshots_dir,
        expected_tris=expected_tris,
        interval_s=settings.stable_interval_s,
    )

    # Check if model already exists
    stem = Path(file_name).stem
    stmt = select(Model).where(Model.source_file == file_name)
    model = db.scalar(stmt)
    if model is None:
        model = Model(name=stem, source_file=file_name)
        db.add(model)
        db.commit()
        db.refresh(model)

    # Check if a version with this OBJ and these assets already exists. A texture-only or MTL-only
    # re-export keeps the OBJ sha256 but lands in a new snapshot directory, so it needs its own
    # version: the old one's assets still point at the old textures.
    ver_stmt = select(ModelVersion).where(
        ModelVersion.model_id == model.id,
        ModelVersion.sha256 == snap.sha256,
        ModelVersion.asset_sha256 == snap.asset_sha256,
        ModelVersion.kind == "snapshot",
    )
    existing_ver = db.scalar(ver_stmt)
    if existing_ver is not None:
        return model

    # Analyze topology to compute quantum and bounding center offset
    flat_materials = flat_material_indices(snap.mesh, snap.flatness, 8.0)
    topo = analyse_topology(snap.mesh, flat_materials)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
    quanta = [float(q) for q in topo.quanta]
    offset = [float(c) for c in centre]

    version = ModelVersion(
        model_id=model.id,
        kind="snapshot",
        sha256=snap.sha256,
        asset_sha256=snap.asset_sha256,
        tri_count=snap.mesh.n_faces,
        coord_quantum=quanta,
        origin_offset=offset,
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    # Add assets: obj
    db.add(
        VersionAsset(
            version_id=version.id,
            kind="obj",
            name=snap.obj_path.name,
            path=str(snap.obj_path.relative_to(settings.data_dir)),
            sha256=snap.sha256,
        )
    )

    # Add assets: mtl
    if snap.mtl_path and snap.mtl_path.exists():
        db.add(
            VersionAsset(
                version_id=version.id,
                kind="mtl",
                name=snap.mtl_path.name,
                path=str(snap.mtl_path.relative_to(settings.data_dir)),
                sha256=sha256_file(snap.mtl_path),
            )
        )

    # Add assets: textures
    for tex_name, tex_path in snap.textures.items():
        if tex_path.exists():
            db.add(
                VersionAsset(
                    version_id=version.id,
                    kind="texture",
                    name=tex_path.name,
                    path=str(tex_path.relative_to(settings.data_dir)),
                    sha256=sha256_file(tex_path),
                )
            )

    db.commit()
    db.refresh(model)
    return model
