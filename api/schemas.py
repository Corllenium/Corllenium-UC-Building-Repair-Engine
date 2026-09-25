from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


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
    hidden: bool = False
    archived_at: datetime | None = None
    created_at: datetime
    versions: list[ModelVersionOut] = []


class ImportRequest(BaseModel):
    file: str


class FixProfileConfig(BaseModel):
    n_dirs: int = 128
    slit_threshold: float = 0.05
    accept_slit: bool = False
    flat_texture_std: float = 8.0
    guard_size: tuple[int, int] = (900, 600)
    edge_flicker_cap_final: float = 0.0001


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
    error: str | None = None
    created_at: datetime
