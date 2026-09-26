"""Images for the dashboard's Errors & fixes page, served from data/errors_doc/img.

The owner's screenshots stay out of git (spec 2026-09-26-errors-and-fixes-page-design.md), so
the web image cannot hold them; the API, which mounts data/, serves them by plain file name.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from api.settings import Settings, get_settings

router = APIRouter(prefix="/api/docs", tags=["docs"])

IMAGE_NAME = re.compile(r"[A-Za-z0-9_.-]+\.(png|webp|jpg)")
MEDIA_TYPES = {"png": "image/png", "webp": "image/webp", "jpg": "image/jpeg"}


@router.get("/images/{name}")
def get_doc_image(name: str, settings: Settings = Depends(get_settings)):
    match = IMAGE_NAME.fullmatch(name)
    path = settings.data_dir / "errors_doc" / "img" / name
    if match is None or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return FileResponse(path, media_type=MEDIA_TYPES[match.group(1)])
