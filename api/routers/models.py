from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from api.db import get_db
from api.models import Model, ModelVersion
from api.schemas import ImportRequest, ModelOut
from api.services.importer import import_model
from api.settings import Settings, get_settings
from engine.io.snapshot import ManifestMismatch, SourceUnstable

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[ModelOut])
def list_models(db: Session = Depends(get_db)):
    stmt = (
        select(Model)
        .options(selectinload(Model.versions).selectinload(ModelVersion.assets))
        .order_by(Model.name)
    )
    return list(db.scalars(stmt))


@router.get("/{id}", response_model=ModelOut)
def get_model(id: int, db: Session = Depends(get_db)):
    stmt = (
        select(Model)
        .where(Model.id == id)
        .options(selectinload(Model.versions).selectinload(ModelVersion.assets))
    )
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
        # Reload with versions and assets
        stmt = (
            select(Model)
            .where(Model.id == model.id)
            .options(selectinload(Model.versions).selectinload(ModelVersion.assets))
        )
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
