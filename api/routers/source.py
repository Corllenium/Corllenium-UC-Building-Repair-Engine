from fastapi import APIRouter, Depends, HTTPException, status
from api.schemas import SourceFileOut
from api.services.importer import scan_source_directory
from api.settings import Settings, get_settings
from engine.io.snapshot import ManifestMismatch, SourceUnstable

router = APIRouter(prefix="/api/source", tags=["source"])


@router.get("/files", response_model=list[SourceFileOut])
def list_source_files(settings: Settings = Depends(get_settings)):
    try:
        return scan_source_directory(settings.source_dir, settings.stable_interval_s)
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

