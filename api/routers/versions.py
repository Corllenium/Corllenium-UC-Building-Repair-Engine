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

router = APIRouter(prefix="/api/versions", tags=["versions"])


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


@router.post("/{id}/fix", response_model=FixRunOut)
def run_fix_pipeline(
    id: int,
    req: FixRequest,
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

    result = fix_object(mesh, flatness, profile)

    # Save output to data/output/<name>/
    name = mesh.name
    out_dir = settings.data_dir / "output" / name
    out_dir.mkdir(parents=True, exist_ok=True)

    fixed_obj_path = out_dir / f"{name}.fixed.obj"
    write_obj(result.mesh, fixed_obj_path)
    write_obj_polygons(result.mesh, result.rings, out_dir / f"{name}.fixed.ngon.obj")

    # Copy mtl & textures if available
    if mtl_path and mtl_path.exists():
        (out_dir / "materials.mtl").write_bytes(mtl_path.read_bytes())
        tex_dir = out_dir / "tex"
        tex_dir.mkdir(exist_ok=True)
        src_tex = mtl_path.parent / "tex"
        if src_tex.exists():
            for f in src_tex.glob("*"):
                if f.is_file():
                    (tex_dir / f.name).write_bytes(f.read_bytes())

    fixed_sha256 = sha256_file(fixed_obj_path)

    # Analyze topology of fixed mesh
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
    )
    db.add(fixed_version)
    db.commit()
    db.refresh(fixed_version)

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

    fix_run = FixRun(
        version_id=version.id,
        fixed_version_id=fixed_version.id,
        status="completed" if result.passed else "failed",
        config=req.profile.model_dump(),
        report_json=report_data,
    )
    db.add(fix_run)
    db.commit()
    db.refresh(fix_run)

    return fix_run
