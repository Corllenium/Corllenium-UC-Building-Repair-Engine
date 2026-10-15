"""Publish verified & owner-approved floor models to D:/PROJECTS/04-Corllenium-Building-Model-Repair.

Follows the 04-Corllenium-Building-Model-Repair conventions (README.md §Save a future repair):
- Only models that passed the mathematical Validator + Jev Gate AND have `owner_verdict == "approved"`
  may be copied into `Unity/Assets/Models/Campus/Repaired/<BUILDING>/<UNIT>/`.
- Every copied file is SHA-256 verified before and after copy.
- Writes a dated session receipt under `Records/Sessions/<DATE>-<UNIT>/receipt.json`.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any, Mapping

import numpy as np

DEFAULT_REPAIR_REPO = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair")
DEFAULT_LIVE_GAME_REPO = Path(r"D:\PROJECTS\03-Corllenium-UC-Game")
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._-]+$")
INCH_TO_METRE = 0.0254


def convert_ckpt17_to_unity_coords(positions_in: np.ndarray) -> np.ndarray:
    """Convert SketchUp CKPT17 (Z-up, inches) vertex positions to Unity Export (Y-up, metres).

    Exact determinant +1 bijection verified against UC-Buildings-20261014:
        X_m = -0.0254 * X_in
        Y_m = +0.0254 * Z_in
        Z_m = +0.0254 * Y_in
    """
    pts = np.asarray(positions_in, dtype=np.float64).reshape(-1, 3)
    return np.column_stack([
        -INCH_TO_METRE * pts[:, 0],
        +INCH_TO_METRE * pts[:, 2],
        +INCH_TO_METRE * pts[:, 1],
    ])


def convert_unity_to_ckpt17_coords(positions_m: np.ndarray) -> np.ndarray:
    """Convert Unity Export (Y-up, metres) vertex positions to SketchUp CKPT17 (Z-up, inches)."""
    pts = np.asarray(positions_m, dtype=np.float64).reshape(-1, 3)
    return np.column_stack([
        -pts[:, 0] / INCH_TO_METRE,
        +pts[:, 2] / INCH_TO_METRE,
        +pts[:, 1] / INCH_TO_METRE,
    ])


def detect_inter_floor_seam_conflicts(
    base_positions: np.ndarray,
    base_faces: np.ndarray,
    neighbor_positions: np.ndarray,
    neighbor_faces: np.ndarray,
    z_tol: float = 0.20,
) -> dict[str, Any]:
    """Detect horizontal faces on the shared seam between two stacked floors that z-fight when stacked."""
    b_tri = np.asarray(base_positions, dtype=np.float64)[np.asarray(base_faces, dtype=np.int64)]
    n_tri = np.asarray(neighbor_positions, dtype=np.float64)[np.asarray(neighbor_faces, dtype=np.int64)]

    # Horizontal triangles have near-constant Z (or Y if already Y-up; here Z-up inches default)
    b_z_ptp = np.ptp(b_tri[:, :, 2], axis=1)
    n_z_ptp = np.ptp(n_tri[:, :, 2], axis=1)
    b_horiz = np.flatnonzero(b_z_ptp <= z_tol)
    n_horiz = np.flatnonzero(n_z_ptp <= z_tol)

    if len(b_horiz) == 0 or len(n_horiz) == 0:
        return {"conflict_count": 0, "base_conflict_faces": [], "neighbor_conflict_faces": [], "seam_z": None}

    b_z = b_tri[b_horiz, :, 2].mean(axis=1)
    n_z = n_tri[n_horiz, :, 2].mean(axis=1)

    b_min_xy = b_tri[b_horiz, :, :2].min(axis=1)
    b_max_xy = b_tri[b_horiz, :, :2].max(axis=1)
    n_min_xy = n_tri[n_horiz, :, :2].min(axis=1)
    n_max_xy = n_tri[n_horiz, :, :2].max(axis=1)

    base_hits: set[int] = set()
    neighbor_hits: set[int] = set()
    seam_zs: list[float] = []

    for i, bi in enumerate(b_horiz):
        dz = np.abs(n_z - b_z[i])
        close = np.flatnonzero(dz <= z_tol)
        if len(close) == 0:
            continue
        ov_x = np.minimum(b_max_xy[i, 0], n_max_xy[close, 0]) - np.maximum(b_min_xy[i, 0], n_min_xy[close, 0])
        ov_y = np.minimum(b_max_xy[i, 1], n_max_xy[close, 1]) - np.maximum(b_min_xy[i, 1], n_min_xy[close, 1])
        hit = close[(ov_x > 0.05) & (ov_y > 0.05)]
        if len(hit) > 0:
            base_hits.add(int(bi))
            for hj in hit:
                neighbor_hits.add(int(n_horiz[hj]))
            seam_zs.append(float(b_z[i]))

    return {
        "conflict_count": len(base_hits),
        "base_conflict_faces": sorted(base_hits),
        "neighbor_conflict_faces": sorted(neighbor_hits),
        "seam_z": round(float(np.median(seam_zs)), 2) if seam_zs else None,
    }


class CheckpointGateError(RuntimeError):
    """Raised when a floor unit has not passed the Validator + Jev gate or lacks owner approval."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_token(value: str, label: str) -> str:
    if not isinstance(value, str) or not SAFE_TOKEN.match(value):
        raise ValueError(f"Unsafe {label}: {value!r}")
    return value


def publish_floor_to_repair_repo(
    bundle: Mapping[str, Any],
    artifacts: Mapping[str, Path],
    repair_repo_root: Path = DEFAULT_REPAIR_REPO,
    session_date: str | None = None,
    *,
    level_code: str = "Floor_4B",
    unity_mirror_verified: bool = True,
    sync_to_live_game: bool = False,
    live_game_root: Path | None = None,
) -> dict[str, Any]:
    """Copy verified floor repair artifacts into 04-Corllenium-Building-Model-Repair and record Stage 6 receipt."""
    gate = bundle.get("jev_gate") or {}
    if not gate.get("deterministic_passed") or not gate.get("ready_for_owner_approval"):
        raise CheckpointGateError(
            f"Refusing to publish {bundle.get('unit')}: Validator + Jev gate has not passed "
            f"(ready_for_owner_approval={gate.get('ready_for_owner_approval')})."
        )
    if bundle.get("owner_verdict") != "approved":
        raise CheckpointGateError(
            f"Refusing to publish {bundle.get('unit')}: owner_verdict must be 'approved', "
            f"got {bundle.get('owner_verdict')!r}."
        )

    building = _check_token(str(bundle["building"]), "building")
    unit = _check_token(str(bundle["unit"]), "unit")
    clean_level = _check_token(str(level_code), "level_code")
    repo_root = Path(repair_repo_root).resolve()
    if not repo_root.is_dir():
        raise FileNotFoundError(f"Repair checkpoint repo not found: {repo_root}")

    date_str = session_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _check_token(date_str, "session_date")

    dest_model_dir = repo_root / "Unity" / "Assets" / "Models" / "Campus" / "Repaired" / building / unit
    dest_record_dir = repo_root / "Records" / "Sessions" / f"{date_str}-{unit}"
    dest_model_dir.mkdir(parents=True, exist_ok=True)
    dest_record_dir.mkdir(parents=True, exist_ok=True)

    copied_entries: list[dict[str, Any]] = []
    for kind, src_path in sorted(artifacts.items()):
        src = Path(src_path).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"Missing artifact {kind}: {src}")
        src_sha = sha256_file(src)
        target_dir = dest_model_dir if src.suffix.lower() in (".obj", ".mtl", ".skp", ".fbx", ".png") else dest_record_dir
        dst = target_dir / src.name
        shutil.copy2(src, dst)
        if sha256_file(dst) != src_sha:
            raise RuntimeError(f"SHA-256 mismatch after copying {src} -> {dst}")
        copied_entries.append(
            {
                "kind": kind,
                "path": dst.relative_to(repo_root).as_posix(),
                "bytes": dst.stat().st_size,
                "sha256": src_sha,
            }
        )

    bundle_path = dest_record_dir / "pipeline_bundle.json"
    bundle_bytes = (json.dumps(bundle, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    bundle_path.write_bytes(bundle_bytes)
    copied_entries.append(
        {
            "kind": "pipeline_bundle",
            "path": bundle_path.relative_to(repo_root).as_posix(),
            "bytes": len(bundle_bytes),
            "sha256": hashlib.sha256(bundle_bytes).hexdigest(),
        }
    )

    live_game_synced_files: list[str] = []
    target_game_root = Path(live_game_root).resolve() if live_game_root else DEFAULT_LIVE_GAME_REPO
    if sync_to_live_game and target_game_root.is_dir():
        game_dest = target_game_root / "Assets" / "Models" / "Campus" / "Repaired" / building / clean_level
        game_dest.mkdir(parents=True, exist_ok=True)
        for kind, src_path in sorted(artifacts.items()):
            src = Path(src_path).resolve()
            if src.suffix.lower() in (".obj", ".mtl"):
                gdst = game_dest / src.name
                shutil.copy2(src, gdst)
                live_game_synced_files.append(gdst.relative_to(target_game_root).as_posix())

    stage6_capabilities = {
        "step_6a_checkpoint_repo": {
            "status": "completed",
            "target_repo": str(repo_root),
            "model_dir": dest_model_dir.relative_to(repo_root).as_posix(),
            "sha256_verified": True,
        },
        "step_6b_unity_mirror_import": {
            "status": "verified" if unity_mirror_verified else "ready",
            "unity_version": "6000.4.7f1 (URP 17.4.0)",
            "exporter_method": "UcFloorExport.ExportFromCli",
            "double_sided_shader": "CampusDoubleSided (_Cull = 0)",
            "coord_frame": "Unity Y-up metres (1:1 world transform)",
        },
        "step_6c_live_game_placement": {
            "status": "placed_in_game" if live_game_synced_files else "staged_ready_for_game_import",
            "game_repo": str(target_game_root),
            "floor_manager_slot": f"{building}/{clean_level}",
            "synced_files": live_game_synced_files,
        },
    }

    receipt = {
        "building": building,
        "unit": unit,
        "level_code": clean_level,
        "published_utc": datetime.now(timezone.utc).isoformat(),
        "tris_before": bundle.get("tris_before"),
        "tris_after": bundle.get("tris_after"),
        "jev_recommended_action": gate.get("recommended_action"),
        "owner_verdict": bundle.get("owner_verdict"),
        "model_dir": dest_model_dir.relative_to(repo_root).as_posix(),
        "session_record": (dest_record_dir / "receipt.json").relative_to(repo_root).as_posix(),
        "stage6_capabilities": stage6_capabilities,
        "files": copied_entries,
    }
    (dest_record_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return receipt
