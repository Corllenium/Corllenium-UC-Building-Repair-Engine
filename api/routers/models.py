from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from api.db import get_db
from api.models import Model
from api.schemas import ImportRequest, ModelOut
from api.services.importer import import_model, scan_source_directory
from api.settings import Settings, get_settings
from engine.io.snapshot import ManifestMismatch, SourceUnstable

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[ModelOut])
def list_models(include_hidden: bool = False, db: Session = Depends(get_db)):
    stmt = select(Model).options(selectinload(Model.versions)).order_by(Model.name)
    if not include_hidden:
        stmt = stmt.where(Model.hidden == False)
    return list(db.scalars(stmt))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def hide_model(id: int, db: Session = Depends(get_db)):
    model = db.scalar(select(Model).where(Model.id == id))
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    model.hidden = True
    model.archived_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/{id}/restore", response_model=ModelOut)
def restore_model(id: int, db: Session = Depends(get_db)):
    model = db.scalar(select(Model).where(Model.id == id).options(selectinload(Model.versions)))
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    model.hidden = False
    model.archived_at = None
    db.commit()
    db.refresh(model)
    return model


@router.post("/rescan", response_model=list[ModelOut])
def rescan_source_endpoint(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        source_files = scan_source_directory(settings.source_dir, settings.stable_interval_s)
    except SourceUnstable as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
            headers={"Retry-After": "5"},
        )
    except ManifestMismatch as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    for sf in source_files:
        try:
            import_model(db, sf.file, settings)
        except Exception:
            pass

    stmt = select(Model).options(selectinload(Model.versions)).order_by(Model.name)
    return list(db.scalars(stmt))


@router.get("/{id}", response_model=ModelOut)
def get_model(id: int, db: Session = Depends(get_db)):
    stmt = select(Model).where(Model.id == id).options(selectinload(Model.versions))
    model = db.scalar(stmt)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return model


@router.post("/import", response_model=ModelOut, status_code=status.HTTP_201_CREATED)
def import_model_endpoint(
    req: ImportRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        model = import_model(db, req.file, settings)
        # Reload with versions
        stmt = select(Model).where(Model.id == model.id).options(selectinload(Model.versions))
        return db.scalar(stmt)
    except SourceUnstable as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
            headers={"Retry-After": "5"},
        )
    except ManifestMismatch as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
