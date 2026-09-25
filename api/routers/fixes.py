from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import FixRun, ModelVersion, VersionAsset
from api.schemas import FixRunOut
from api.settings import Settings, get_settings

router = APIRouter(prefix="/api/runs", tags=["runs"])


VALID_AXIS_VIEWS: tuple[str, ...] = ("+x", "-x", "+y", "-y", "+z", "-z")
VALID_FAIL_VIEWS: tuple[str, ...] = tuple(f"fail_{i}" for i in range(26))
VALID_GUARD_VIEWS: tuple[str, ...] = VALID_AXIS_VIEWS + VALID_FAIL_VIEWS


@router.get("/{id}", response_model=FixRunOut)
def get_fix_run(id: int, db: Session = Depends(get_db)):
    run = db.scalar(select(FixRun).where(FixRun.id == id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fix run not found")
    return run


@router.get("/{id}/guard/{view}")
def get_guard_image(
    id: int,
    view: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if view not in VALID_GUARD_VIEWS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Guard image view '{view}' not found",
        )

    run = db.scalar(select(FixRun).where(FixRun.id == id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fix run not found")

    if run.fixed_version_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No fixed version associated with run")

    # Locate output directory for this run's model
    ver = db.scalar(select(ModelVersion).where(ModelVersion.id == run.fixed_version_id))
    if ver is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixed version not found")

    obj_asset = db.scalar(
        select(VersionAsset).where(VersionAsset.version_id == ver.id, VersionAsset.kind == "obj")
    )
    if obj_asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixed OBJ asset not found")

    out_dir = (settings.data_dir / obj_asset.path).parent
    img_path = out_dir / f"guard_{view}.png"

    if not img_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Guard image for view {view} not found")

    return FileResponse(img_path, media_type="image/png")
