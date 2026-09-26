"""The 3D error filter's files: one per version, `data/errors/version-<id>.json`."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import ModelVersion, VersionAsset
from api.settings import Settings, get_settings
from engine.detectors.errors import find_errors
from engine.fixes.pipeline import FixProfile
from engine.io.obj_reader import read_obj

router = APIRouter(prefix="/api/versions", tags=["errors"])


def errors_file(settings: Settings, version_id: int) -> Path:
    return settings.data_dir / "errors" / f"version-{version_id}.json"


def write_errors(settings: Settings, version_id: int, result: dict) -> None:
    path = errors_file(settings, version_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result), encoding="utf-8")
    tmp.replace(path)


@router.post("/{id}/errors")
def compute_errors(id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    version = db.scalar(select(ModelVersion).where(ModelVersion.id == id))
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    obj_asset = db.scalar(select(VersionAsset).where(VersionAsset.version_id == id, VersionAsset.kind == "obj"))
    if obj_asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OBJ asset not found")
    obj_path = settings.data_dir / obj_asset.path
    if not obj_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OBJ file missing on disk")
    result = find_errors(read_obj(obj_path), FixProfile())
    write_errors(settings, id, result)
    return JSONResponse(result)


@router.get("/{id}/errors")
def get_errors(id: int, settings: Settings = Depends(get_settings)):
    path = errors_file(settings, id)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not computed yet")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))
