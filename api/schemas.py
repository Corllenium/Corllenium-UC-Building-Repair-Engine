from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceFileOut(BaseModel):
    file: str
    tri_count: int | None = None
    size_bytes: int | None = None


class VersionAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_id: int
    kind: str
    name: str
    path: str
    sha256: str


class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_id: int
    kind: str
    sha256: str
    asset_sha256: str | None = None
    tri_count: int
    flat_materials: list[str] | None = None
    created_at: datetime
    assets: list[VersionAssetOut] = []



class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_file: str
    created_at: datetime
    versions: list[ModelVersionOut] = []


class ImportRequest(BaseModel):
    file: str


class FixProfileConfig(BaseModel):
    n_dirs: int = Field(default=128, ge=8, le=512)
    slit_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    accept_slit: bool = False
    flat_texture_std: float = Field(default=8.0, ge=0.0, le=255.0)
    guard_size: tuple[int, int] = (900, 600)
    edge_flicker_cap_final: float = Field(default=0.0001, ge=0.0, le=1.0)

    @field_validator("guard_size")
    @classmethod
    def validate_guard_size(cls, v: tuple[int, int]) -> tuple[int, int]:
        if len(v) != 2:
            raise ValueError("guard_size must be a tuple of (width, height)")
        w, h = v
        if not (64 <= w <= 4096 and 64 <= h <= 4096):
            raise ValueError("guard_size dimensions must each be between 64 and 4096")
        return v


class FixRequest(BaseModel):
    profile: FixProfileConfig = FixProfileConfig()


class FixRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_id: int
    fixed_version_id: int | None = None
    status: str
    config: dict[str, Any] | None = None
    report_json: dict[str, Any] | None = None
    guard_views: list[str] = []
    skp: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime


class SourceFaceOut(BaseModel):
    face_id: int
    line: int


class FaceOut(BaseModel):
    face_id: int
    line: int
    material: str | None = None
    vertices: list[list[float]]
    source_faces: list[SourceFaceOut] | None = None

