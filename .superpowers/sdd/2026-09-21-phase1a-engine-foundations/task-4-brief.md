### Task 4: MTL + texture flatness

**Files:** Create `engine\io\mtl.py`, `engine\tests\test_mtl.py`

**Interfaces — Produces:** `MtlMaterial(name, lines, map_kd)`, `parse_mtl(path) -> dict[str, MtlMaterial]`,
`write_mtl_subset(materials, used, dst, texture_dir="tex") -> dict[str, str]` (material -> source `map_Kd` relpath),
`texture_flatness(path) -> float` (max per-channel colour std, 0-255 scale).

- [ ] **Step 1: failing test**

```python
import numpy as np
from PIL import Image

from engine.io.mtl import parse_mtl, texture_flatness, write_mtl_subset

MTL = """newmtl stone
Kd 0.87 0.87 0.87
map_Kd SRC-TEX/stone.png

newmtl paint
Kd 1 0 0

newmtl unused
map_Kd SRC-TEX/unused.png
"""


def test_parse_and_subset(tmp_path):
    src = tmp_path / "lib.mtl"
    src.write_text(MTL)
    mats = parse_mtl(src)
    assert list(mats) == ["stone", "paint", "unused"] and mats["stone"].map_kd == "SRC-TEX/stone.png"
    assert mats["paint"].map_kd is None
    dst = tmp_path / "out.mtl"
    assert write_mtl_subset(mats, ["paint", "stone"], dst) == {"stone": "SRC-TEX/stone.png"}
    text = dst.read_text()
    assert "map_Kd tex/stone.png" in text and "unused" not in text and "newmtl paint" in text


def test_texture_flatness(tmp_path):
    rng = np.random.default_rng(0)
    Image.fromarray(rng.integers(217, 228, (16, 16, 3)).astype(np.uint8)).save(tmp_path / "flat.png")
    checker = np.indices((16, 16)).sum(axis=0) % 2 * 255
    Image.fromarray(np.stack([checker] * 3, axis=2).astype(np.uint8)).save(tmp_path / "pattern.png")
    assert texture_flatness(tmp_path / "flat.png") < 5.0
    assert texture_flatness(tmp_path / "pattern.png") > 100.0
```

Run. Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 2: implementation**

```python
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
```

- [ ] **Step 3:** Run tests. Expected: `2 passed`. Real check: sidewalk textures measured 3.04 in the spike.
- [ ] **Step 4:** Commit `feat(engine): MTL subset and texture flatness`.

---

