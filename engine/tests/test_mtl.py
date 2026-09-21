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
