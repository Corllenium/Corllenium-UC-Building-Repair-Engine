import json
import logging
import os
from pathlib import Path
import shutil
import struct
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import FixRun, ModelVersion, VersionAsset
from api.schemas import FaceOut, FixRequest, FixRunOut, ModelVersionOut
from api.settings import Settings, get_settings
from api.routers.errors import write_errors
from engine.cli import _build_report, _write_guard_images, _write_skp, copy_skp_to_owner
from engine.detectors.errors import find_errors
from engine.fixes.pipeline import FixProfile, fix_object
from engine.io.mtl import parse_mtl, texture_flatness
from engine.io.obj_reader import read_obj
from engine.io.obj_writer import write_obj, write_obj_polygons
from engine.io.snapshot import sha256_file
from engine.pipeline import analyse_topology, flat_material_indices
from engine.transport.meshbuf import pack_meshbuf, MAGIC, VERSION
import numpy as np
import re
import threading

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/versions", tags=["versions"])

_active_model_fixes: set[int] = set()
_fixes_lock = threading.Lock()
_skp_lock = threading.Lock()


def meshbuf_cache_file(settings: Settings, version_id: int) -> Path:
    return settings.data_dir / "meshbuf" / f"version-{version_id}.bin"


def _is_valid_meshbuf_format(buf: bytes) -> bool:
    """Check if buffer is a valid meshbuf format (MAGIC and current VERSION)."""
    if len(buf) < 8:
        return False
    if buf[:4] != MAGIC:
        return False
    try:
        version = struct.unpack("<I", buf[4:8])[0]
        return version == VERSION
    except struct.error:
        return False


def _meshbuf_response(buf: bytes) -> Response:
    hlen = struct.unpack("<I", buf[8:12])[0]
    faces = json.loads(buf[12:12 + hlen].decode("utf-8").strip())["counts"]["faces"]
    return Response(content=buf, media_type="application/octet-stream",
                    headers={"X-Tris-Count": str(faces), "X-Face-Count": str(faces),
                             "Cache-Control": "public, max-age=3600"})


def _sanitize_filename(name: str | None, fallback: str) -> str:
    if not name:
        return fallback
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", name).strip("_")
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned:
        return fallback
    return cleaned


@router.get("/{id}", response_model=ModelVersionOut)
def get_version(id: int, db: Session = Depends(get_db)):
    version = db.scalar(select(ModelVersion).where(ModelVersion.id == id))
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return version


@router.get("/{id}/meshbuf")
def get_meshbuf(
    id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    version = db.scalar(select(ModelVersion).where(ModelVersion.id == id))
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    # Versions are immutable: once a version is created, its OBJ and MTL never change.
    # The importer's legacy flat_materials backfill (api/services/importer.py) may set that field
    # on an existing version; it converges to the same value this route would compute from the same
    # MTL bytes, so the cache stays valid. If that backfill ever changes, delete data/meshbuf/.
    cached = meshbuf_cache_file(settings, id)
    if cached.exists():
        buf = cached.read_bytes()
        if _is_valid_meshbuf_format(buf):
            return _meshbuf_response(buf)
        # Cache is stale (wrong format); will rebuild below and overwrite

    obj_asset = db.scalar(
        select(VersionAsset).where(VersionAsset.version_id == id, VersionAsset.kind == "obj")
    )
    if obj_asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OBJ asset not found")

    obj_path = settings.data_dir / obj_asset.path
    if not obj_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OBJ file missing on disk")

    mesh = read_obj(obj_path)

    # Resolve textures and flatness from mtl
    textures: dict[str, str] = {}
    flatness: dict[str, float] = {}

    mtl_asset = db.scalar(
        select(VersionAsset).where(VersionAsset.version_id == id, VersionAsset.kind == "mtl")
    )
    if mtl_asset:
        mtl_path = settings.data_dir / mtl_asset.path
        if mtl_path.exists():
            for name, mat in parse_mtl(mtl_path).items():
                if mat.map_kd:
                    tex_file = mtl_path.parent / mat.map_kd
                    if tex_file.exists():
                        textures[name] = mat.map_kd
                        flatness[name] = texture_flatness(tex_file)

    if version.flat_materials is not None:
        flat_names = set(version.flat_materials)
        flat_mats = frozenset(i for i, name in enumerate(mesh.materials) if name in flat_names)
    else:
        flat_mats = flat_material_indices(mesh, flatness, 8.0)
    topo = analyse_topology(mesh, flat_mats)
    buf = pack_meshbuf(mesh, topo, textures)

    cached.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=cached.parent, prefix=f"version-{id}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(buf)
        os.replace(tmp_path, cached)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return _meshbuf_response(buf)


@router.get("/{id}/textures/{name}")
def get_texture(
    id: int,
    name: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    asset = db.scalar(
        select(VersionAsset).where(
            VersionAsset.version_id == id,
            VersionAsset.kind == "texture",
            VersionAsset.name == name,
        )
    )
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Texture not found")

    tex_path = settings.data_dir / asset.path
    if not tex_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Texture file missing")

    return FileResponse(tex_path)


@router.get("/{id}/assets/{name}")
def get_version_asset(
    id: int,
    name: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    asset = db.scalar(
        select(VersionAsset).where(
            VersionAsset.version_id == id,
            VersionAsset.name == name,
        )
    )
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    path = settings.data_dir / asset.path
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset file missing")

    return FileResponse(path)


@router.get("/{id}/faces/{face_id}", response_model=FaceOut, response_model_exclude_none=True)
def get_version_face(
    id: int,
    face_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    version = db.scalar(select(ModelVersion).where(ModelVersion.id == id))
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    obj_asset = db.scalar(
        select(VersionAsset).where(VersionAsset.version_id == id, VersionAsset.kind == "obj")
    )
    if obj_asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OBJ asset not found")

    obj_path = settings.data_dir / obj_asset.path
    if not obj_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OBJ file missing on disk")

    mesh = read_obj(obj_path)
    if face_id < 0 or face_id >= mesh.n_faces:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Face {face_id} not found")

    line = int(mesh.face_line[face_id])
    mat_idx = int(mesh.face_material[face_id])
    mat_name = mesh.materials[mat_idx] if (0 <= mat_idx < len(mesh.materials)) else None
    vertices = mesh.positions[mesh.face_v[face_id]].tolist()

    if version.kind == "fixed":
        source_faces = []
        sf_asset = db.scalar(
            select(VersionAsset).where(VersionAsset.version_id == id, VersionAsset.kind == "source_faces")
        )
        sf_list = None
        if sf_asset:
            sf_path = settings.data_dir / sf_asset.path
            if sf_path.exists():
                try:
                    sf_list = json.loads(sf_path.read_text(encoding="utf-8"))
                except Exception:
                    sf_list = None

        orig_face_ids = []
        if sf_list is not None and 0 <= face_id < len(sf_list):
            orig_face_ids = sf_list[face_id]

        fix_run = db.scalar(select(FixRun).where(FixRun.fixed_version_id == id))
        snap_version = None
        if fix_run:
            snap_version = db.scalar(select(ModelVersion).where(ModelVersion.id == fix_run.version_id))
        if snap_version is None:
            snap_version = db.scalar(
                select(ModelVersion)
                .where(ModelVersion.model_id == version.model_id, ModelVersion.kind == "snapshot")
                .order_by(ModelVersion.id.desc())
            )

        snap_mesh = None
        if snap_version:
            snap_obj_asset = db.scalar(
                select(VersionAsset).where(VersionAsset.version_id == snap_version.id, VersionAsset.kind == "obj")
            )
            if snap_obj_asset:
                p = settings.data_dir / snap_obj_asset.path
                if p.exists():
                    snap_mesh = read_obj(p)

        for orig_id in orig_face_ids:
            orig_line = -1
            if snap_mesh is not None and 0 <= orig_id < snap_mesh.n_faces:
                orig_line = int(snap_mesh.face_line[orig_id])
            source_faces.append({"face_id": orig_id, "line": orig_line})

        return FaceOut(
            face_id=face_id,
            line=line,
            material=mat_name,
            vertices=vertices,
            source_faces=source_faces,
        )

    return FaceOut(
        face_id=face_id,
        line=line,
        material=mat_name,
        vertices=vertices,
        source_faces=None,
    )


@router.get("/{id}/run", response_model=FixRunOut)
def get_version_run(id: int, db: Session = Depends(get_db)):
    version = db.scalar(select(ModelVersion).where(ModelVersion.id == id))
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    fix_run = None
    if version.kind == "fixed":
        fix_run = db.scalar(
            select(FixRun)
            .where(FixRun.fixed_version_id == id)
            .order_by(FixRun.id.desc())
        )
    if fix_run is None:
        fix_run = db.scalar(
            select(FixRun)
            .where(FixRun.version_id == id)
            .order_by(FixRun.id.desc())
        )

    if fix_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No fix run found for version")

    return fix_run


@router.post("/{id}/fix", response_model=FixRunOut, status_code=status.HTTP_201_CREATED)
def run_fix_pipeline(
    id: int,
    req: FixRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    version = db.scalar(select(ModelVersion).where(ModelVersion.id == id))
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    model_id = version.model_id
    with _fixes_lock:
        if model_id in _active_model_fixes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="fix already running",
            )
        _active_model_fixes.add(model_id)

    out_dir: Path | None = None
    committed: bool = False
    fix_run: FixRun | None = None
    try:
        # 1. Allocate fix_run in the session and flush to get run_id
        fix_run = FixRun(
            version_id=version.id,
            status="running",
            config=req.profile.model_dump(),
        )
        db.add(fix_run)
        db.flush()
        run_id = fix_run.id

        # 2. Output directory under data/fixed/<run_id>/
        out_dir = settings.data_dir / "fixed" / str(run_id)
        out_dir.mkdir(parents=True, exist_ok=True)

        obj_asset = db.scalar(
            select(VersionAsset).where(VersionAsset.version_id == id, VersionAsset.kind == "obj")
        )
        if obj_asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OBJ asset not found")

        obj_path = settings.data_dir / obj_asset.path
        mesh = read_obj(obj_path)

        # Load flatness
        flatness: dict[str, float] = {}
        mtl_asset = db.scalar(
            select(VersionAsset).where(VersionAsset.version_id == id, VersionAsset.kind == "mtl")
        )
        mtl_path = None
        if mtl_asset:
            mtl_path = settings.data_dir / mtl_asset.path
            if mtl_path.exists():
                for name, mat in parse_mtl(mtl_path).items():
                    if mat.map_kd:
                        tex_file = mtl_path.parent / mat.map_kd
                        if tex_file.exists():
                            flatness[name] = texture_flatness(tex_file)

        p = req.profile
        profile = FixProfile(
            n_dirs=p.n_dirs,
            slit_threshold=p.slit_threshold,
            accept_slit=p.accept_slit,
            flat_texture_std=p.flat_texture_std,
            guard_size=p.guard_size,
            edge_flicker_cap_final=p.edge_flicker_cap_final,
        )

        # Enforce stored flat_materials from the snapshot import (m4)
        if version.flat_materials is not None:
            stored_flat = set(version.flat_materials)
            for mat_name in mesh.materials:
                if mat_name in stored_flat:
                    flatness[mat_name] = 0.0
                else:
                    flatness[mat_name] = max(flatness.get(mat_name, 0.0), profile.flat_texture_std + 10.0)

        result = fix_object(mesh, flatness, profile)

        fallback = f"model_{version.model_id}"
        name = _sanitize_filename(mesh.name, fallback)
        fixed_obj_path = out_dir / f"{name}.fixed.obj"
        write_obj(result.mesh, fixed_obj_path)
        write_obj_polygons(result.mesh, result.rings, out_dir / f"{name}.fixed.ngon.obj")

        fixed_sha256 = sha256_file(fixed_obj_path)

        # Analyze topology of fixed mesh
        if version.flat_materials is not None:
            stored_flat = set(version.flat_materials)
            flat_mats = frozenset(i for i, mat_name in enumerate(result.mesh.materials) if mat_name in stored_flat)
        else:
            flat_mats = flat_material_indices(result.mesh, flatness, profile.flat_texture_std)
        topo = analyse_topology(result.mesh, flat_mats)
        centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
        quanta = [float(q) for q in topo.quanta]
        offset = [float(c) for c in centre]

        fixed_version = ModelVersion(
            model_id=version.model_id,
            kind="fixed",
            sha256=fixed_sha256,
            tri_count=result.mesh.n_faces,
            coord_quantum=quanta,
            origin_offset=offset,
            flat_materials=version.flat_materials,
        )
        db.add(fixed_version)
        db.flush()

        # Copy mtl & textures and record as assets on fixed version
        if mtl_path and mtl_path.exists():
            dest_mtl = out_dir / "materials.mtl"
            dest_mtl.write_bytes(mtl_path.read_bytes())
            db.add(
                VersionAsset(
                    version_id=fixed_version.id,
                    kind="mtl",
                    name="materials.mtl",
                    path=dest_mtl.relative_to(settings.data_dir).as_posix(),
                    sha256=sha256_file(dest_mtl),
                )
            )
            tex_dir = out_dir / "tex"
            tex_dir.mkdir(exist_ok=True)
            src_tex = mtl_path.parent / "tex"
            if src_tex.exists():
                for f in src_tex.glob("*"):
                    if f.is_file():
                        dest_tex = tex_dir / f.name
                        dest_tex.write_bytes(f.read_bytes())
                        db.add(
                            VersionAsset(
                                version_id=fixed_version.id,
                                kind="texture",
                                name=f.name,
                                path=dest_tex.relative_to(settings.data_dir).as_posix(),
                                sha256=sha256_file(dest_tex),
                            )
                        )

        # Add fixed OBJ asset
        db.add(
            VersionAsset(
                version_id=fixed_version.id,
                kind="obj",
                name=fixed_obj_path.name,
                path=fixed_obj_path.relative_to(settings.data_dir).as_posix(),
                sha256=fixed_sha256,
            )
        )

        # Save source_faces asset: map reference mesh IDs to original input face IDs
        orig_indices = np.flatnonzero(~result.replaced_input)
        n_orig = len(orig_indices)

        source_faces_list = []
        for s in result.source_faces:
            row = []
            for r in (s.tolist() if hasattr(s, "tolist") else list(s)):
                r_int = int(r)
                if 0 <= r_int < n_orig:
                    row.append(int(orig_indices[r_int]))
                else:
                    row.append(-1)
            source_faces_list.append(row)
        sf_path = out_dir / "source_faces.json"
        sf_path.write_text(json.dumps(source_faces_list), encoding="utf-8")
        db.add(
            VersionAsset(
                version_id=fixed_version.id,
                kind="source_faces",
                name="source_faces.json",
                path=sf_path.relative_to(settings.data_dir).as_posix(),
                sha256=sha256_file(sf_path),
            )
        )

        # Write guard images under out_dir
        reference = result.reference_mesh
        if version.flat_materials is not None:
            stored_flat = set(version.flat_materials)
            ref_flat_mats = frozenset(i for i, mat_name in enumerate(reference.materials) if mat_name in stored_flat)
        else:
            ref_flat_mats = flat_material_indices(reference, flatness, profile.flat_texture_std)
        ref_topo = analyse_topology(reference, ref_flat_mats)
        ref_centre = (ref_topo.positions_w.min(axis=0) + ref_topo.positions_w.max(axis=0)) / 2.0
        ref_positions_c = ref_topo.positions_w - ref_centre
        _write_guard_images(reference, result, profile, ref_flat_mats, ref_topo, ref_positions_c, out_dir)

        guard_views = [
            v for v in ("+x", "-x", "+y", "-y", "+z", "-z")
            if (out_dir / f"guard_{v}.png").exists()
        ]
        for i in range(26):
            if (out_dir / f"guard_fail_{i}.png").exists():
                guard_views.append(f"fail_{i}")

        with _skp_lock:
            skp_report = _write_skp(
                result,
                name,
                out_dir,
                ref_flat_mats,
                profile,
                enabled=True,
                copy_dir=None,
            )
        if skp_report.get("written"):
            skp_report["path"] = str(out_dir / f"{name}.fixed.skp")
        else:
            skp_report.pop("path", None)

        report_data = _build_report(name, obj_path, mesh, result, profile)
        report_data["guard_views"] = guard_views
        report_data["skp"] = skp_report
        report_data["skp_path"] = skp_report.get("path") if skp_report.get("written") else None
        report_data["skp_summary"] = (
            f"SketchUp file: {report_data['skp_path']}"
            if skp_report.get("written")
            else f"SketchUp skipped: {skp_report.get('reason') or skp_report.get('error') or 'unknown'}"
        )
        mr = report_data.setdefault("merge_report", {})
        mr.setdefault("rolled_back", False)
        mr.setdefault("rolled_back_reason", None)
        mr.setdefault("skipped_by_reason", mr.get("regions_skipped", {}))

        (out_dir / "report.json").write_text(json.dumps(report_data, indent=2), encoding="utf-8")

        fix_run.fixed_version_id = fixed_version.id
        fix_run.status = "completed" if result.passed else "failed"
        fix_run.report_json = report_data

        # Commit everything atomically in ONE transaction at the end
        db.commit()
        db.refresh(fix_run)
        committed = True

        # After successful database commit, copy into the owner's folder (OBJ FIXED RESULT)
        if skp_report.get("written") and settings.skp_dir is not None:
            try:
                copy_skp_to_owner(
                    out_dir / f"{name}.fixed.skp",
                    settings.skp_dir,
                    name,
                    result.passed,
                    out=skp_report,
                )
                if skp_report.get("copied_to"):
                    report_data["skp_path"] = skp_report["copied_to"]
                    report_data["skp_summary"] = f"SketchUp file: {skp_report['copied_to']}"
                elif skp_report.get("copy_error"):
                    report_data["skp_summary"] = (
                        f"SketchUp file copy failed: {skp_report['copy_error']} "
                        f"(owner folder unchanged; previous file may still be open)"
                    )
            except Exception as exc:
                logger.exception("Owner copy failed for version %s: %s", id, exc)
                skp_report["copy_error"] = str(exc)
                report_data["skp_summary"] = (
                    f"SketchUp file copy failed: {exc} "
                    f"(owner folder unchanged; previous file may still be open)"
                )
            finally:
                report_data["skp"] = skp_report
                if skp_report.get("copy_error"):
                    report_data["copy_error"] = skp_report["copy_error"]
                try:
                    (out_dir / "report.json").write_text(json.dumps(report_data, indent=2), encoding="utf-8")
                except Exception as exc:
                    logger.warning("Failed to write report.json with copy results: %s", exc)
                try:
                    fix_run.report_json = report_data
                    db.commit()
                    db.refresh(fix_run)
                except Exception as exc:
                    logger.exception("Failed to commit copy results to database: %s", exc)
                    db.rollback()

        # the 3D error filter's AFTER file; never allowed to change the run's own outcome
        try:
            write_errors(settings, fix_run.fixed_version_id, find_errors(result.mesh, profile))
        except Exception:
            logger.exception("errors file for fixed version %s", fix_run.fixed_version_id)

        return fix_run

    except HTTPException:
        db.rollback()
        if not committed and out_dir is not None and out_dir.exists():
            shutil.rmtree(out_dir, ignore_errors=True)
        raise
    except Exception as exc:
        logger.exception("Fix pipeline failed for version %s", id)
        db.rollback()
        if not committed and out_dir is not None and out_dir.exists():
            shutil.rmtree(out_dir, ignore_errors=True)
        if committed:
            return fix_run
        err_msg = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        failed_run = FixRun(
            version_id=version.id,
            status="failed",
            error=err_msg,
            config=req.profile.model_dump(),
        )
        db.add(failed_run)
        db.commit()
        db.refresh(failed_run)
        return failed_run
    finally:
        with _fixes_lock:
            _active_model_fixes.discard(model_id)
