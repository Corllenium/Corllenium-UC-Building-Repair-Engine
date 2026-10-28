from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

from engine.campus.source import _texture_rel
from engine.io.mtl import MtlMaterial, parse_mtl


def parse_kd_d(mat: MtlMaterial) -> tuple[tuple[float, float, float], float]:
    """Parse Kd (diffuse colour) and d (dissolve/opacity) from mat.lines.

    If d is absent and Tr is present, use d = 1 - Tr.
    Defaults to (1.0, 1.0, 1.0) and 1.0 if not present or unparseable.
    """
    kd = (1.0, 1.0, 1.0)
    d: float | None = None
    tr: float | None = None
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
        elif tokens[0] == "Tr" and len(tokens) >= 2:
            try:
                tr = float(tokens[1])
            except ValueError:
                pass

    if d is not None:
        final_d = d
    elif tr is not None:
        final_d = 1.0 - tr
    else:
        final_d = 1.0

    return kd, final_d


def look_key(tex_sha256: str | None, kd: Any, d: Any) -> str:
    """Compute 16-character look key: sha256(f"{tex or 'none'}|{kd rounded 4}|{d rounded 4}")[:16]."""
    kd_round = tuple(round(float(c), 4) + 0.0 for c in kd)
    d_round = round(float(d), 4) + 0.0
    tex_part = tex_sha256 if tex_sha256 else "none"
    raw = f"{tex_part}|{kd_round}|{d_round}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _find_texture_file(rel: PurePosixPath, mtl_path: Path, tex_dir: Path) -> Path | None:
    """Find texture file matching rel path.

    Resolves exact MTL-relative path first, then tex_dir relative path.
    """
    # 1. Resolve exact MTL-relative posix path FIRST
    mtl_rel = mtl_path.parent / rel
    if mtl_rel.is_file():
        return mtl_rel

    # 2. Resolve relative to tex_dir
    tex_rel = tex_dir / rel
    if tex_rel.is_file():
        return tex_rel

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
            rel = _texture_rel(mat.map_kd)
            if rel is None:
                # Rejected path (absolute, drive letter, or '..')
                tex_sha = None
                missing = True
                key = look_key(f"missing:{map_kd_norm}", kd_tup, d_val)
            else:
                tex_file = _find_texture_file(rel, mtl_path, tex_dir)
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


# ----------------------------------------------------------------------- flicker by look


def look_of_material(name: str, materials: dict) -> Any:
    """The look key of material `name`: `materials` is `materials.json` (with or without its "materials" key)
    or a plain {name: look}. A material missing from the map (or with no look) is its own look, so it equals no
    other material's look."""
    table = materials.get("materials", materials)
    info = table.get(name)
    look = info.get("look") if isinstance(info, dict) else info
    return look if look else ("material", name)


def material_name(mesh, face: int) -> str:
    """The name of the material of `face`; a face with no entry is material 0, and an index with no name is its number."""
    index = int(mesh.face_material[face]) if face < len(mesh.face_material) else 0
    return mesh.materials[index] if index < len(mesh.materials) else str(index)


def split_flicker_pairs(mesh, pairs, materials: dict) -> tuple[list, list]:
    """The one definition of E4 against E5 (owner decision, decision-sheet answer 3): a flicker pair whose two
    faces have one look (identical texture, colour and opacity, so possibly two material names) is
    same-look (E4); two looks make it different-look (E5). Returns (same_look_pairs, diff_look_pairs), each
    in the order of `pairs`. `find_errors`' own flicker_diff / flicker_same stay split by material index."""
    same, diff = [], []
    for pair in pairs:
        i, j = int(pair[0]), int(pair[1])
        a = look_of_material(material_name(mesh, i), materials)
        b = look_of_material(material_name(mesh, j), materials)
        (same if a == b else diff).append(pair)
    return same, diff


def flicker_faces_by_look(mesh, pairs, materials: dict) -> tuple[set[int], set[int]]:
    """The faces of `split_flicker_pairs` as (same_look_faces, diff_look_faces); a face in pairs of both kinds
    is in the different-look set only, as `find_errors` does for its material-index split."""
    same, diff = split_flicker_pairs(mesh, pairs, materials)
    faces = lambda ps: {int(f) for p in ps for f in (p[0], p[1])}
    diff_faces = faces(diff)
    return faces(same) - diff_faces, diff_faces
