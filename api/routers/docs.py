"""Images for the dashboard's Errors & fixes page, served from data/errors_doc/img.

The owner's screenshots stay out of git (spec 2026-09-26-errors-and-fixes-page-design.md), so
the web image cannot hold them; the API, which mounts data/, serves them by plain file name.
"""
import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.settings import Settings, get_settings

router = APIRouter(prefix="/api/docs", tags=["docs"])

IMAGE_NAME = re.compile(r"[A-Za-z0-9_.-]+\.(png|webp|jpg)")
MEDIA_TYPES = {"png": "image/png", "webp": "image/webp", "jpg": "image/jpeg"}

KIND_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
_LOCK = threading.Lock()  # one read-modify-write at a time within this process


class VerdictIn(BaseModel):
    verdict: Literal["error", "ok", "unsure"] | None
    note: str = Field(default="", max_length=2000)


def validation_file(settings: Settings):
    return settings.data_dir / "errors_doc" / "validation.json"


def read_validation(settings: Settings) -> dict:
    path = validation_file(settings)
    if not path.is_file():
        return {"version": 1, "verdicts": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_validation(settings: Settings, data: dict) -> None:
    path = validation_file(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="validation-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, path)


@router.get("/images/{name}")
def get_doc_image(name: str, settings: Settings = Depends(get_settings)):
    match = IMAGE_NAME.fullmatch(name)
    path = settings.data_dir / "errors_doc" / "img" / name
    if match is None or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return FileResponse(path, media_type=MEDIA_TYPES[match.group(1)])


@router.get("/validation")
def get_validation(settings: Settings = Depends(get_settings)):
    return read_validation(settings)


@router.put("/validation/{kind_id}/{model_id}")
def put_verdict(kind_id: str, model_id: str, body: VerdictIn, settings: Settings = Depends(get_settings)):
    """The owner's verdict on one kind of error in one model; a null verdict clears it."""
    if not KIND_ID.fullmatch(kind_id) or not MODEL_ID.fullmatch(model_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown error kind or model")
    with _LOCK:
        data = read_validation(settings)
        per_kind = data["verdicts"].setdefault(kind_id, {})
        entry = None
        if body.verdict is None:
            per_kind.pop(model_id, None)
        else:
            entry = {"verdict": body.verdict, "note": body.note,
                     "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            per_kind[model_id] = entry
        if not per_kind:
            del data["verdicts"][kind_id]
        _write_validation(settings, data)
    return {"kind": kind_id, "model": model_id, "entry": entry}
