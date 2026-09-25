from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class Model(Base):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    versions: Mapped[list["ModelVersion"]] = relationship(
        "ModelVersion", back_populates="model", cascade="all, delete-orphan", order_by="ModelVersion.id"
    )


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(Integer, ForeignKey("models.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # 'snapshot', 'preview', 'fixed'
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    asset_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tri_count: Mapped[int] = mapped_column(Integer, nullable=False)
    coord_quantum: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    origin_offset: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    flat_materials: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    model: Mapped["Model"] = relationship("Model", back_populates="versions")
    assets: Mapped[list["VersionAsset"]] = relationship(
        "VersionAsset", back_populates="version", cascade="all, delete-orphan"
    )
    fix_runs: Mapped[list["FixRun"]] = relationship(
        "FixRun", back_populates="version", foreign_keys="[FixRun.version_id]", cascade="all, delete-orphan"
    )


class VersionAsset(Base):
    __tablename__ = "version_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # 'obj', 'mtl', 'texture', 'report'
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    version: Mapped["ModelVersion"] = relationship("ModelVersion", back_populates="assets")


class IssueType(Base):
    __tablename__ = "issue_types"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    default_action: Mapped[str] = mapped_column(String(32), default="auto_fix", nullable=False)


class FixRun(Base):
    __tablename__ = "fix_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fixed_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # 'pending', 'running', 'completed', 'failed'
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    version: Mapped["ModelVersion"] = relationship("ModelVersion", foreign_keys=[version_id], back_populates="fix_runs")
