import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import FixRun, ModelVersion, VersionAsset
from api.schemas import FixRequest, FixRunOut, ModelVersionOut
from api.settings import Settings, get_settings
from engine.cli import _build_report
from engine.fixes.pipeline import FixProfile, fix_object
from engine.io.mtl import parse_mtl, texture_flatness
from engine.io.obj_reader import read_obj
from engine.io.obj_writer import write_obj, write_obj_polygons
from engine.io.snapshot import sha256_file
from engine.pipeline import analyse_topology, flat_material_indices
from engine.transport.meshbuf import pack_meshbuf
import threading

router = APIRouter(prefix="/api/versions", tags=["versions"])

_active_model_fixes: set[int] = set()
_fixes_lock = threading.Lock()


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

    return Response(
        content=buf,
        media_type="application/octet-stream",
        headers={
            "X-Tris-Count": str(mesh.n_faces),
            "X-Face-Count": str(mesh.n_faces),
            "Cache-Control": "public, max-age=3600",
        },
    )


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

        # Enforce stored flat_materials from the snapshot import
        if version.flat_materials is not None:
            stored_flat = set(version.flat_materials)
            for mat_name in mesh.materials:
                if mat_name not in stored_flat:
                    flatness[mat_name] = max(flatness.get(mat_name, 0.0), profile.flat_texture_std + 10.0)
                elif mat_name not in flatness:
                    flatness[mat_name] = 0.0

        result = fix_object(mesh, flatness, profile)

        name = mesh.name
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
                    path=str(dest_mtl.relative_to(settings.data_dir)),
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
                                path=str(dest_tex.relative_to(settings.data_dir)),
                                sha256=sha256_file(dest_tex),
                            )
                        )

        # Add fixed OBJ asset
        db.add(
            VersionAsset(
                version_id=fixed_version.id,
                kind="obj",
                name=fixed_obj_path.name,
                path=str(fixed_obj_path.relative_to(settings.data_dir)),
                sha256=fixed_sha256,
            )
        )

        # Save source_faces asset
        source_faces_list = [
            [int(x) for x in (s.tolist() if hasattr(s, "tolist") else list(s))]
            for s in result.source_faces
        ]
        sf_path = out_dir / "source_faces.json"
        sf_path.write_text(json.dumps(source_faces_list), encoding="utf-8")
        db.add(
            VersionAsset(
                version_id=fixed_version.id,
                kind="source_faces",
                name="source_faces.json",
                path=str(sf_path.relative_to(settings.data_dir)),
                sha256=sha256_file(sf_path),
            )
        )

        report_data = _build_report(name, obj_path, mesh, result, profile)
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
        return fix_run

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        failed_run = FixRun(
            version_id=version.id,
            status="failed",
            error=str(exc),
            config=req.profile.model_dump(),
        )
        db.add(failed_run)
        db.commit()
        db.refresh(failed_run)
        return failed_run
    finally:
        with _fixes_lock:
            _active_model_fixes.discard(model_id)
