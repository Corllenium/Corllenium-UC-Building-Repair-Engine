"""Job P0-15: the Validator's three checks (AGENTS.md section 6) -- textures there, problems solved,
nothing visible deleted or covered -- the evidence crops, and the `validate` command.

Each test builds a BEFORE, makes AFTER one defect different from it (or none), and says which check must
notice and why. Job P0-16 proves the whole Validator with mutations on top of these.
"""
import dataclasses
import json
import struct

import numpy as np
import pytest
from PIL import Image

from engine.tests.fixtures.build import closed_room, cube, grid_slab, two_sided_wall
from engine.validate.checks import (Looks, LookTable, depth_tolerance, face_fingerprints, face_look_ids,
                                    load_looks, png_size, print_step)


# ---------------------------------------------------------------------------------------------
# Step 1: what the checks measure with -- print step, tolerance, look keys, texture sizes, fingerprints
# ---------------------------------------------------------------------------------------------

def _png(path, width, height, colour=(200, 30, 30)):
    Image.new("RGB", (width, height), colour).save(path)
    return path


def test_png_size_reads_the_ihdr_header_and_nothing_else(tmp_path):
    path = _png(tmp_path / "t.png", 16, 8)
    assert png_size(path) == (16, 8)
    # only the first 24 bytes matter: a file cut right after IHDR still gives its size
    cut = tmp_path / "cut.png"
    cut.write_bytes(path.read_bytes()[:24])
    assert png_size(cut) == (16, 8)
    assert png_size(_png(tmp_path / "big.png", 1024, 2048)) == (1024, 2048)
    # not a PNG: no size, not a crash
    junk = tmp_path / "junk.png"
    junk.write_bytes(b"not an image at all, but longer than twenty-four bytes")
    assert png_size(junk) is None
    assert png_size(tmp_path / "missing.png") is None


def test_the_print_step_is_the_exports_own_precision_and_the_depth_tolerance_follows_it():
    near = cube(10.0)                                              # coordinates up to 10, 6 significant digits
    assert print_step(near) == pytest.approx(1e-5)
    assert depth_tolerance(print_step(near)) == 0.05, "the floor of the tolerance: 0.05 in"

    # CHTM's floors sit near y = 24,000: 6 significant digits there print to 0.1 in, and 2 steps is 0.2 in
    far = dataclasses.replace(near, positions=near.positions + [0.0, 24000.0, 0.0])
    assert print_step(far) == pytest.approx(0.1)
    assert depth_tolerance(print_step(far)) == pytest.approx(0.2)
    assert depth_tolerance(0.01) == 0.05 and depth_tolerance(0.03) == pytest.approx(0.06)

    # a vertex no face uses does not set the precision
    stray = dataclasses.replace(near, positions=np.vstack([near.positions, [[0.0, 90000.0, 0.0]]]))
    assert print_step(stray) == pytest.approx(1e-5)
    assert print_step(dataclasses.replace(near, face_v=near.face_v[:0])) == 0.0, "no faces: no precision"


def test_looks_map_materials_to_look_keys_and_an_unknown_material_keeps_its_own_name():
    looks = Looks(key={"plaster": "L-plaster", "brick": "L-brick", "tinted": "L-plaster"})
    table = LookTable()
    room = closed_room()                                           # materials: plaster, brick
    ids = face_look_ids(room, looks, table)
    assert ids.shape == (24,) and ids.dtype == np.int64
    assert len(set(ids[:12])) == 1 and len(set(ids[12:])) == 1 and ids[0] != ids[12]

    # the same look under another material name is the same id (the point of look keys)
    renamed = dataclasses.replace(room, materials=["tinted", "brick"])
    assert np.array_equal(face_look_ids(renamed, looks, table), ids)

    # a material materials.json does not know: its own name, flagged, so two such names stay two looks
    odd = dataclasses.replace(room, materials=["mystery", "brick"])
    odd_ids = face_look_ids(odd, looks, table)
    assert odd_ids[0] not in set(ids) and odd_ids[12] == ids[12]
    assert looks.unknown(odd) == ["mystery"] and looks.unknown(room) == []

    # a face with no `usemtl` (material -1) is never the last material by accident
    bare = dataclasses.replace(room, face_material=np.concatenate([[-1], room.face_material[1:]]))
    bare_ids = face_look_ids(bare, looks, table)
    assert bare_ids[0] not in set(ids) and bare_ids[1] == ids[1]


def test_load_looks_reads_look_keys_texture_sizes_and_mean_colours(tmp_path):
    (tmp_path / "tex").mkdir()
    _png(tmp_path / "tex" / "red.png", 16, 16, (200, 30, 30))
    (tmp_path / "materials.mtl").write_text(
        "newmtl red\nKd 0.5 1 1\nmap_Kd tex/red.png\n\nnewmtl flat\nKd 0.2 0.4 0.6\n\n"
        "newmtl ghost\nKd 1 1 1\nmap_Kd tex/not_there.png\n\nnewmtl unlisted\nKd 1 1 1\n", encoding="utf-8")
    materials = tmp_path / "materials.json"
    materials.write_text(json.dumps({"materials": {
        "red": {"map_kd": "SRC-TEX/red.png", "kd": [0.5, 1.0, 1.0], "look": "A1"},
        "flat": {"map_kd": None, "kd": [0.2, 0.4, 0.6], "look": "B2"},
        "ghost": {"map_kd": "SRC-TEX/not_there.png", "kd": [1.0, 1.0, 1.0], "look": "C3", "missing_texture": True},
    }, "looks": {}, "stats": {}}), encoding="utf-8")

    from engine.io.mtl import parse_mtl
    looks = load_looks(materials, [(parse_mtl(tmp_path / "materials.mtl"), tmp_path)])
    assert looks.key == {"red": "A1", "flat": "B2", "ghost": "C3"}
    assert looks.texel == {"A1": (16, 16)}, "only a look with a texture file on disk has a texel size"
    assert looks.colour["A1"] == (100, 30, 30), "the texture's mean colour times Kd: (200, 30, 30) * (0.5, 1, 1)"
    assert looks.colour["B2"] == (51, 102, 153), "no texture: Kd itself"
    assert "C3" in looks.colour, "a missing texture still has the colour of its Kd"

    # an MTL material that materials.json does not list is left out, and is reported when a mesh uses it
    assert "unlisted" not in looks.key
    # the colour of a look nobody gave a colour is still stable and not grey for every look
    assert looks.colour_of("never-seen") == looks.colour_of("never-seen")
    assert looks.colour_of("never-seen") != looks.colour_of("never-seen-either")


def _fingerprints(mesh, step=0.1):
    table = LookTable()
    ids = face_look_ids(mesh, Looks(key={m: m for m in mesh.materials}), table)
    return face_fingerprints(mesh, step, ids)


def test_a_face_fingerprint_is_its_snapped_corners_in_winding_order_plus_its_look():
    m = grid_slab(2, 2, cell=10.0)
    base = _fingerprints(m)
    assert base.shape == (m.n_faces, 10) and base.dtype == np.int64
    assert len({tuple(r) for r in base}) == m.n_faces, "every face of the slab is told apart"

    # the same corners starting at another corner: the same face
    rolled = dataclasses.replace(m, face_v=m.face_v[:, [1, 2, 0]], face_vt=m.face_vt[:, [1, 2, 0]])
    assert np.array_equal(_fingerprints(rolled), base)
    # the opposite winding is another face: a flipped face must be looked at again
    flipped = dataclasses.replace(m, face_v=m.face_v[:, [0, 2, 1]], face_vt=m.face_vt[:, [0, 2, 1]])
    assert not (_fingerprints(flipped) == base).all(axis=1).any()
    # a corner moved by less than half a step is still on the same print grid; by a whole step it is not
    near = m.positions.copy()
    near[0] += [0.04, 0.0, 0.0]
    far = m.positions.copy()
    far[0] += [0.2, 0.0, 0.0]
    same = (_fingerprints(dataclasses.replace(m, positions=near)) == base).all(axis=1)
    moved = (_fingerprints(dataclasses.replace(m, positions=far)) == base).all(axis=1)
    assert same.all() and moved.sum() == m.n_faces - int((m.face_v == 0).any(axis=1).sum())
    # another material: another look, another fingerprint
    other = dataclasses.replace(m, materials=["m0", "m1"],
                                face_material=np.concatenate([[1], np.zeros(m.n_faces - 1, dtype=np.int64)]))
    changed = ~(_fingerprints(other) == base).all(axis=1)
    assert changed.tolist() == [True] + [False] * (m.n_faces - 1)
