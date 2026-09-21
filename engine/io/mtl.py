from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import numpy as np
from PIL import Image


@dataclass
class MtlMaterial:
    name: str
    lines: list[str] = field(default_factory=list)
    map_kd: str | None = None


def parse_mtl(path: Path) -> dict[str, MtlMaterial]:
    out: dict[str, MtlMaterial] = {}
    cur = None
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("newmtl "):
            cur = MtlMaterial(line[7:].strip())
            out[cur.name] = cur
        elif cur is not None and line and not line.startswith("#"):
            if line.startswith("map_Kd "):
                cur.map_kd = line[7:].strip()
            cur.lines.append(line)
    return out


def write_mtl_subset(materials, used, dst, texture_dir="tex") -> dict[str, str]:
    textures, out = {}, []
    for name in used:
        mat = materials.get(name)
        if mat is None:
            continue
        out.append(f"newmtl {name}")
        for line in mat.lines:
            if line.startswith("map_Kd ") and mat.map_kd:
                textures[name] = mat.map_kd
                line = f"map_Kd {texture_dir}/{PurePosixPath(mat.map_kd.replace(chr(92), '/')).name}"
            out.append(line)
        out.append("")
    Path(dst).write_text("\n".join(out), encoding="utf-8", newline="\n")
    return textures


def texture_flatness(path: Path) -> float:
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=float).reshape(-1, 3)
    return float(rgb.std(axis=0).max())
