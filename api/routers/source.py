from fastapi import APIRouter, Depends
from api.schemas import SourceFileOut
from api.services.importer import scan_source_directory
from api.settings import Settings, get_settings

router = APIRouter(prefix="/api/source", tags=["source"])


@router.get("/files", response_model=list[SourceFileOut])
def list_source_files(settings: Settings = Depends(get_settings)):
    return scan_source_directory(settings.source_dir)
