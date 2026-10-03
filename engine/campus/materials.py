from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from engine.io.mtl import MtlMaterial, parse_mtl


def parse_kd_d(mat: MtlMaterial) -> tuple[tuple[float, float, float], float]:
    """Parse Kd (diffuse colour) and d (dissolve/opacity) from mat.lines.

    Defaults to (1.0, 1.0, 1.0) and 1.0 if not present or unparseable.
    """
    kd = (1.0, 1.0, 1.0)
    d = 1.0
    for line in mat.lines:
        tokens = line.strip().split()
        if not tokens:
            continue
        if tokens[0] == "Kd" and len(tokens) >= 4:
            try:
                kd = (float(tokens[1]), float(tokens[2]), float(tokens[3]))
            except ValueError:
                pass
        elif tokens[0] == "d" and len(tokens) >= 2:
            try:
                d = float(tokens[1])
            except ValueError:
                pass
    return kd, d


def look_key(tex_sha256: str | None, kd: Any, d: Any) -> str:
    """Compute 16-character look key: sha256(f"{tex or 'none'}|{kd rounded 4}|{d rounded 4}")[:16]."""
    kd_round = tuple(round(float(c), 4) + 0.0 for c in kd)
    d_round = round(float(d), 4) + 0.0
    tex_part = tex_sha256 if tex_sha256 else "none"
    raw = f"{tex_part}|{kd_round}|{d_round}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _find_texture_file(map_kd: str, mtl_path: Path, tex_dir: Path) -> Path | None:
    norm = map_kd.replace("\\", "/")
    p = Path(norm)
    candidates = [
        tex_dir / p,
        tex_dir / p.name,
        tex_dir.parent / p,
        mtl_path.parent / p,
        mtl_path.parent / p.name,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def build_materials(mtl_path: Path, tex_dir: Path) -> dict:
    """Build material look keys, groupings, and stats from an MTL file and texture directory."""
    mtl_path = Path(mtl_path)
    tex_dir = Path(tex_dir)
    mats = parse_mtl(mtl_path)

    materials: dict[str, dict[str, Any]] = {}
    looks: dict[str, list[str]] = {}

    for name, mat in mats.items():
        kd_tup, d_val = parse_kd_d(mat)
        kd_list = [round(float(c), 4) for c in kd_tup]
        d_val = round(float(d_val), 4)

        if mat.map_kd is None:
            map_kd_norm = None
            tex_sha: str | None = None
            missing = False
            key = look_key(None, kd_tup, d_val)
        else:
            map_kd_norm = mat.map_kd.replace("\\", "/")
            tex_file = _find_texture_file(map_kd_norm, mtl_path, tex_dir)
            if tex_file is not None:
                tex_sha = hashlib.sha256(tex_file.read_bytes()).hexdigest()
                missing = False
                key = look_key(tex_sha, kd_tup, d_val)
            else:
                tex_sha = None
                missing = True
                key = look_key(f"missing:{map_kd_norm}", kd_tup, d_val)

        materials[name] = {
            "map_kd": map_kd_norm,
            "tex_sha256": tex_sha,
            "kd": kd_list,
            "d": d_val,
            "look": key,
            "missing_texture": missing,
        }
        looks.setdefault(key, []).append(name)

    stats = {
        "materials": len(materials),
        "textured": sum(1 for m in materials.values() if m["map_kd"] is not None),
        "images": len({m["tex_sha256"] for m in materials.values() if m["tex_sha256"] is not None}),
        "looks": len(looks),
    }

    return {
        "materials": materials,
        "looks": looks,
        "stats": stats,
    }
