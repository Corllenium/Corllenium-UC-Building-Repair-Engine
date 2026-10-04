"""Job P0-15: the Validator's three checks (AGENTS.md section 6) -- textures there, problems solved,
nothing visible deleted or covered -- the evidence crops, and the `validate` command.

Each test builds a BEFORE, makes AFTER one defect different from it (or none), and says which check must
notice and why. Job P0-16 proves the whole Validator with mutations on top of these.
"""
import dataclasses
import json
import os

import numpy as np
import pytest
from PIL import Image

import engine.cli as cli
from engine.io.obj_writer import write_obj
from engine.io.snapshot import sha256_file
from engine.tests.fixtures.build import closed_room, cube, grid_slab, two_sided_wall
from engine.validate.checks import (Looks, LookTable, Settings, _barycentric, check_problems, default_targets_path,
                                    depth_tolerance, face_fingerprints, face_look_ids, load_looks, load_targets,
                                    png_size, print_step, validate)
from engine.validate.evidence import BACK_TINT, BACKGROUND, _basis, render_crop, write_evidence
from engine.validate.sampling import face_normals, face_samples
from engine.validate.viewpoints import outside_directions
from engine.validate.visibility import build_caster


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


def test_a_face_fingerprint_is_its_snapped_corners_in_winding_order_plus_its_look_and_uvs():
    m = grid_slab(2, 2, cell=10.0)
    base = _fingerprints(m)
    assert base.shape == (m.n_faces, 16) and base.dtype == np.int64
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
    # the UVs count, mod 1: moved by whole tiles it is the same face, by 0.37 of a tile it is not
    assert np.array_equal(_fingerprints(grid_slab(2, 2, cell=10.0, shift_cols=(0, 1))), base)
    assert not (_fingerprints(grid_slab(2, 2, cell=10.0, break_col=0)) == base).all(axis=1).any()
    # a face with no UVs has its own mark, the same in both meshes that have none
    bare = dataclasses.replace(m, face_vt=np.where(np.arange(m.n_faces)[:, None] == 0, -1, m.face_vt))
    assert (_fingerprints(bare) == base).all(axis=1).tolist() == [False] + [True] * (m.n_faces - 1)
    assert np.array_equal(_fingerprints(bare), _fingerprints(bare))


# ---------------------------------------------------------------------------------------------
# Step 2: checks 1 and 3 -- identity passes, and each way AFTER can go wrong is named
# ---------------------------------------------------------------------------------------------

KINDS = ("flicker_diff", "flicker_same", "reversed", "hidden", "loose", "open_edges", "cracks")
NO_ERRORS = {"counts": dict.fromkeys(KINDS, 0), "spots": {k: [] for k in KINDS}}


def _looks(*names, texel=(16, 16)):
    """Every material is its own look and every look has a 16 x 16 texture (1 texel = 0.0625 of the UV unit)."""
    return Looks(key={n: f"look-{n}" for n in names}, texel={f"look-{n}": texel for n in names})


def _check(before, after, looks, **kw):
    """`validate` with check 2 given nothing to find, so these tests are about checks 1 and 3."""
    return validate(before, after, looks, errors=(NO_ERRORS, NO_ERRORS), **kw)


def _checks(v):
    c = v.report["checks"]
    return c["textures"], c["nothing_deleted"]


def _without_faces(mesh, drop):
    keep = np.ones(mesh.n_faces, dtype=bool)
    keep[list(drop)] = False
    return dataclasses.replace(
        mesh, face_v=mesh.face_v[keep], face_vt=mesh.face_vt[keep], face_vn=mesh.face_vn[keep],
        face_material=mesh.face_material[keep], face_line=np.arange(1, int(keep.sum()) + 1, dtype=np.int64))


def _with_flipped(mesh, faces):
    fv, fvt = mesh.face_v.copy(), mesh.face_vt.copy()
    fv[faces] = fv[faces][:, [0, 2, 1]]
    fvt[faces] = fvt[faces][:, [0, 2, 1]]
    return dataclasses.replace(mesh, face_v=fv, face_vt=fvt)


def _with_plate(mesh, plate):
    """`mesh` with the faces of `plate` added (its vertices and UVs after the mesh's own)."""
    n_v, n_t, n_f = len(mesh.positions), len(mesh.uvs), mesh.n_faces
    return dataclasses.replace(
        mesh, positions=np.vstack([mesh.positions, plate.positions]), uvs=np.vstack([mesh.uvs, plate.uvs]),
        face_v=np.vstack([mesh.face_v, plate.face_v + n_v]), face_vt=np.vstack([mesh.face_vt, plate.face_vt + n_t]),
        face_vn=np.vstack([mesh.face_vn, plate.face_vn]),
        face_material=np.concatenate([mesh.face_material, plate.face_material]),
        face_line=np.arange(1, n_f + plate.n_faces + 1, dtype=np.int64))


def _moved(mesh, delta):
    return dataclasses.replace(mesh, positions=mesh.positions + np.asarray(delta, dtype=np.float64))


def _two_looks(mesh):
    """`mesh` with a second material "m1" (a different look) that no face uses yet."""
    return dataclasses.replace(mesh, materials=["m0", "m1"])


def _with_material(mesh, faces, material):
    fm = mesh.face_material.copy()
    fm[faces] = material
    return dataclasses.replace(mesh, face_material=fm)


def _with_shifted_uv(mesh, face, shift):
    """Face `face` gets its own copies of its three UVs, moved by `shift` in both U and V."""
    base = len(mesh.uvs)
    uvs = np.vstack([mesh.uvs, mesh.uvs[mesh.face_vt[face]] + shift])
    fvt = mesh.face_vt.copy()
    fvt[face] = [base, base + 1, base + 2]
    return dataclasses.replace(mesh, uvs=uvs, face_vt=fvt)


def test_identity_passes_every_check_on_a_cube():
    m = cube(10.0)
    v = _check(m, m, _looks("m0"))
    textures, gone = _checks(v)
    assert (textures["status"], gone["status"]) == ("PASS", "PASS")
    assert v.report["checks"]["problems"]["status"] == "REPORT_ONLY"
    assert v.report["verdict"] == "PASS" and v.passed
    assert textures["samples"] == 48 and textures["faces"] == 12, "4 samples on each of 12 faces, all seen from outside"
    assert textures["samples_failed"] == 0 and gone["samples"] == 48 and gone["deleted"] == gone["covered"] == 0
    assert v.report["sites"] == []


def test_identity_passes_every_check_on_a_two_sided_wall():
    m = two_sided_wall()                    # two layers in ONE place, in two looks: whichever Embree returns first
    v = _check(m, m, _looks("concrete", "prismarine"))
    textures, gone = _checks(v)
    assert (textures["status"], gone["status"], v.report["verdict"]) == ("PASS", "PASS", "PASS")
    assert textures["faces"] == 4 and textures["samples"] == len(face_samples(m)) == 100
    assert textures["samples_failed"] == 0 and gone["deleted"] == 0 and gone["replaced"] == 0


def test_identity_passes_every_check_in_a_closed_room_whose_walls_only_the_probes_see():
    m = closed_room()
    v = _check(m, m, _looks("plaster", "brick"))
    textures, gone = _checks(v)
    assert (textures["status"], gone["status"], v.report["verdict"]) == ("PASS", "PASS", "PASS")
    assert textures["faces"] == 24, "the inner skin from the probes, the outer skin from outside: every face"
    assert v.report["viewpoints"] == {"directions": 128, "cameras": 24, "probes": 40, "extra_directions": 1024}
    assert textures["samples_failed"] == 0 and gone["deleted"] == 0 and gone["covered"] == 0


def test_identity_holds_when_the_model_sits_far_from_the_origin():
    near = closed_room()
    far = _moved(near, [24000.0, 24000.0, 0.0])
    v = _check(far, far, _looks("plaster", "brick"))
    assert v.report["verdict"] == "PASS"
    assert np.allclose(v.report["frame"]["centre"], [24100.0, 24080.0, 60.0])
    assert v.report["print_step_in"] == pytest.approx(0.1) and v.report["depth_tolerance_in"] == pytest.approx(0.2)


def test_the_report_is_the_same_whatever_the_chunk_size():
    m = closed_room()
    a = _check(m, m, _looks("plaster", "brick"))
    b = _check(m, m, _looks("plaster", "brick"), settings=Settings(chunk=7))
    assert b.report["settings"]["chunk"] == 7
    drop = lambda r: {k: v for k, v in r.items() if k not in ("timings_s", "settings")}
    assert drop(a.report) == drop(b.report)


def test_a_deleted_visible_face_is_deleted_for_check_1_and_check_3_and_has_a_site():
    m = cube(10.0)
    v = _check(m, _without_faces(m, [8]), _looks("m0"))           # one triangle of the x = 10 side
    textures, gone = _checks(v)
    assert (textures["status"], gone["status"], v.report["verdict"]) == ("FAIL", "FAIL", "FAIL")
    assert textures["samples_failed"] == 4 and textures["reasons"] == {
        "covered": 0, "overlaid": 0, "deleted": 4, "look": 0, "uv": 0, "side": 0}
    assert gone["deleted"] == 4 and gone["replaced"] == 0 and gone["covered"] == 0
    assert gone["faces_unmet"] == 1, "face 8 was visible and none of its samples is met any more"
    (site,) = v.report["sites"]
    assert site["faces"] == [8] and site["samples"] == 4
    assert site["checks"] == ["textures", "nothing_deleted"] and site["reasons"]["deleted"] == 4
    assert 0.0 < site["centre"][1] < 10.0 and site["centre"][0] == pytest.approx(10.0, abs=0.01), "on the x = 10 face"


def test_a_visible_face_in_another_look_is_replaced_for_check_3_and_a_look_failure_for_check_1():
    m = _two_looks(cube(10.0))
    v = _check(m, _with_material(m, [3], 1), _looks("m0", "m1"))   # the top, second triangle
    textures, gone = _checks(v)
    assert textures["status"] == "FAIL" and textures["reasons"]["look"] == 4 and textures["samples_failed"] == 4
    assert gone["status"] == "FAIL" and gone["replaced"] == 4 and gone["deleted"] == 0
    assert gone["faces_unmet"] == 1


def test_a_look_under_another_material_name_is_the_same_look():
    m = _two_looks(cube(10.0))
    tinted = Looks(key={"m0": "L", "m1": "L"}, texel={"L": (16, 16)})    # two names, one look: a tint group
    v = _check(m, _with_material(m, [3], 1), tinted)
    assert v.report["verdict"] == "PASS" and _checks(v)[0]["samples_failed"] == 0


def test_a_material_unknown_to_materials_json_is_listed_and_still_compares_by_its_name():
    m = cube(10.0)
    v = _check(m, m, Looks(key={}))
    assert v.report["verdict"] == "PASS"
    assert v.report["materials"]["unknown_before"] == ["m0"] and v.report["materials"]["unknown_after"] == ["m0"]
    other = _check(m, dataclasses.replace(m, materials=["m9"]), Looks(key={}))
    assert other.report["verdict"] == "FAIL" and _checks(other)[0]["reasons"]["look"] == 48


def test_uvs_shifted_by_half_fail_check_1_and_only_check_1():
    m = cube(10.0)
    v = _check(m, _with_shifted_uv(m, 2, 0.5), _looks("m0"))
    textures, gone = _checks(v)
    assert textures["status"] == "FAIL" and textures["reasons"]["uv"] == 4 and textures["samples_failed"] == 4
    assert gone["status"] == "PASS", "the surface and its look are still there at the same depth"
    assert v.report["sites"][0]["checks"] == ["textures"]


def test_uvs_may_move_by_a_whole_tile_and_by_less_than_a_texel_but_not_by_two():
    m = cube(10.0)                                                  # a 16 x 16 texture: one texel is 0.0625
    for shift, expected in ((1.0, "PASS"), (-2.0, "PASS"), (0.03, "PASS"), (0.0625, "PASS"), (0.1, "FAIL")):
        v = _check(m, _with_shifted_uv(m, 2, shift), _looks("m0"))
        assert v.report["checks"]["textures"]["status"] == expected, shift
    wide = _looks("m0", texel=(1024, 1024))                         # on a 1024 px texture 0.03 is 30 texels
    assert _check(m, _with_shifted_uv(m, 2, 0.03), wide).report["checks"]["textures"]["status"] == "FAIL"


def test_no_texture_no_uv_test():
    m = cube(10.0)
    flat = Looks(key={"m0": "flat"})                                 # no texel size: no texture shows the UV
    v = _check(m, _with_shifted_uv(m, 2, 0.5), flat)
    assert v.report["verdict"] == "PASS"


def test_a_face_without_uvs_in_both_is_fine_and_in_one_is_not():
    m = cube(10.0)
    bare = dataclasses.replace(m, face_vt=np.where(np.arange(12)[:, None] == 2, -1, m.face_vt))
    assert _check(bare, bare, _looks("m0")).report["verdict"] == "PASS"
    assert _check(m, bare, _looks("m0")).report["checks"]["textures"]["reasons"]["uv"] == 4


def test_a_flipped_visible_face_is_seen_from_behind_and_fails_check_1_only():
    m = cube(10.0)
    v = _check(m, _with_flipped(m, [2]), _looks("m0"))
    textures, gone = _checks(v)
    assert textures["status"] == "FAIL" and textures["reasons"]["side"] == 4 and textures["samples_failed"] == 4
    assert gone["status"] == "PASS"


def test_a_face_one_inch_in_front_of_a_visible_face_covers_it():
    m = cube(10.0)
    plate = _moved(grid_slab(1, 1, cell=10.0), [0.0, 0.0, 11.0])      # 1 in over the top, same material
    v = _check(m, _with_plate(m, plate), _looks("m0"))
    textures, gone = _checks(v)
    assert gone["status"] == "FAIL" and gone["covered"] == 8 and gone["deleted"] == 0, "the top's 2 faces x 4 samples"
    assert gone["faces_covered"] == 2
    assert textures["status"] == "FAIL" and textures["reasons"]["covered"] == 8
    assert v.report["sites"][0]["faces"] == [2, 3] and v.report["sites"][0]["reasons"]["covered"] == 8


def test_layers_within_the_tolerance_are_the_same_depth_and_layers_beyond_it_are_not():
    slab = grid_slab(4, 4, cell=10.0)                                 # 40 x 40 in at z = 0, faces +z
    looks = _looks("m0")
    assert depth_tolerance(print_step(slab)) == 0.05
    for dz, expected in ((0.015, "PASS"), (0.04, "PASS"), (-0.04, "PASS"), (0.06, "FAIL"), (-0.06, "FAIL"),
                         (0.2, "FAIL"), (-0.2, "FAIL")):
        moved = _check(slab, _moved(slab, [0.0, 0.0, dz]), looks)
        assert moved.report["verdict"] == expected, f"the surface moved by {dz}"
    # an EXTRA layer above the surface: 0.015 and 0.04 in up are z-fight layers, 0.06 and more cover it
    above = lambda dz: _with_plate(slab, _moved(grid_slab(4, 4, cell=10.0), [0.0, 0.0, dz]))
    for dz in (0.015, 0.04):
        assert _check(slab, above(dz), looks).report["verdict"] == "PASS", dz
    for dz in (0.06, 0.1, 0.3):
        assert _check(slab, above(dz), looks).report["checks"]["nothing_deleted"]["covered"] > 0, dz


def test_a_deleted_wall_that_only_a_probe_inside_the_room_sees_fails_check_3():
    m = closed_room()
    v = _check(m, _without_faces(m, [4, 5]), _looks("plaster", "brick"))     # the wall y = 0, facing into the room
    textures, gone = _checks(v)
    assert gone["status"] == "FAIL" and gone["faces_unmet"] == 2 and gone["deleted"] > 0
    assert set(v.report["sites"][0]["faces"]) <= {4, 5}
    assert all(set(s["faces"]) <= {4, 5} for s in v.report["sites"]), "nothing else of the room changed"
    # the probes are the BEFORE's: with the wall gone, the probes of the lattice are still the same 40
    assert v.report["viewpoints"]["probes"] == 40


def test_an_after_with_no_faces_has_deleted_everything_without_crashing():
    m = cube(10.0)
    v = _check(m, _without_faces(m, range(12)), _looks("m0"))
    textures, gone = _checks(v)
    assert v.report["verdict"] == "FAIL" and gone["deleted"] == 48 and gone["faces_unmet"] == 12
    assert textures["reasons"]["deleted"] == 48


def test_a_before_with_no_faces_has_nothing_to_judge():
    m = cube(10.0)
    v = _check(_without_faces(m, range(12)), m, _looks("m0"))
    assert v.report["verdict"] == "PASS" and _checks(v)[0]["samples"] == 0


def test_faces_whose_fingerprint_is_absent_get_the_extra_directions_and_only_those_faces():
    m = cube(10.0)
    sides = np.array([[1.0, 0, 0], [-1.0, 0, 0], [0, 1.0, 0], [0, -1.0, 0]])      # the standard set sees no top
    everywhere = np.vstack([sides, [[0, 0, 1.0], [0, 0, -1.0]]])
    none = np.zeros((0, 3))
    kw = dict(dirs=sides, cams=none, probes=none, extra_dirs=everywhere)

    same = _check(m, m, _looks("m0"), **kw)
    textures, gone = _checks(same)
    assert same.report["verdict"] == "PASS" and textures["samples"] == 32, "the 8 side faces; top and bottom unseen"
    assert gone["suspect_faces"] == 0 and gone["samples_extra"] == 0, "nothing changed: no extra directions at all"

    top_gone = _check(m, _without_faces(m, [2, 3]), _looks("m0"), **kw)           # the top, seen only from above
    textures, gone = _checks(top_gone)
    assert textures["status"] == "PASS" and textures["samples"] == 32, "check 1 never saw the top"
    assert gone["status"] == "FAIL" and gone["suspect_faces"] == 2 and gone["samples_extra"] == 8
    assert gone["deleted"] == 8 and gone["faces_unmet"] == 2
    assert top_gone.report["sites"][0]["checks"] == ["nothing_deleted"]

    top_changed = _check(_two_looks(m), _with_material(_two_looks(m), [2, 3], 1), _looks("m0", "m1"), **kw)
    textures, gone = _checks(top_changed)
    assert textures["status"] == "PASS" and gone["status"] == "FAIL" and gone["replaced"] == 8, "its look is gone"


# ---------------------------------------------------------------------------------------------
# Step 3: check 2, problems solved -- find_errors before and after, against the targets the owner signs
# ---------------------------------------------------------------------------------------------

def _errors(counts=None, spots=None):
    """What `engine.detectors.errors.find_errors` returns, as far as check 2 reads it."""
    return {"counts": {**dict.fromkeys(KINDS, 0), **(counts or {})}, "spots": {**{k: [] for k in KINDS}, **(spots or {})}}


def _spot(x):
    return {"label": f"spot {x}", "centre": [float(x), 0.0, 5.0], "size": 2.0, "value": 3.0, "faces": [x, x + 1]}


SIGNED = {"signed": True, "kinds": {"flicker_diff": 0, "flicker_same": 0, "reversed": 0, "hidden": 0, "loose": 0,
                                    "open_edges": None, "cracks": 0}}


def test_until_the_owner_signs_every_kind_is_unsigned_and_check_2_only_reports():
    before = _errors({"flicker_diff": 12, "hidden": 40})
    after = _errors({"flicker_diff": 3, "hidden": 40}, spots={"flicker_diff": [_spot(1), _spot(2), _spot(3)]})
    for targets in (None, {"signed": False, "kinds": SIGNED["kinds"]}, {}):
        result = check_problems(before, after, targets)
        assert result["status"] == "REPORT_ONLY"
        assert list(result["kinds"]) == list(KINDS), "all seven kinds, in the engine's order"
        assert result["kinds"]["flicker_diff"] == {
            "before": 12, "after": 3, "target": "unsigned", "status": "REPORT_ONLY",
            "residual": [_spot(1), _spot(2), _spot(3)]}, "the counts and where the residue is"
        assert result["kinds"]["hidden"]["before"] == result["kinds"]["hidden"]["after"] == 40
        assert all(k["target"] == "unsigned" and k["status"] == "REPORT_ONLY" for k in result["kinds"].values())


def test_signed_targets_pass_or_fail_each_kind_and_the_check_with_them():
    before = _errors({"flicker_diff": 12, "hidden": 40, "open_edges": 90})
    solved = _errors({"open_edges": 31})                              # open edges are only listed, and all else is 0
    result = check_problems(before, solved, SIGNED)
    assert result["status"] == "PASS"
    assert result["kinds"]["flicker_diff"]["target"] == 0 and result["kinds"]["flicker_diff"]["status"] == "PASS"
    assert result["kinds"]["open_edges"]["target"] == "listed" and result["kinds"]["open_edges"]["status"] == "REPORT_ONLY"

    left = _errors({"flicker_diff": 3, "cracks": 1}, spots={"flicker_diff": [_spot(1)], "cracks": [_spot(9)]})
    result = check_problems(before, left, SIGNED)
    assert result["status"] == "FAIL"
    assert result["kinds"]["flicker_diff"]["status"] == "FAIL" and result["kinds"]["cracks"]["status"] == "FAIL"
    assert result["kinds"]["flicker_diff"]["residual"] == [_spot(1)], "every residual is listed with its location"
    assert result["kinds"]["hidden"]["status"] == "PASS" and result["kinds"]["reversed"]["status"] == "PASS"

    roomy = {"signed": True, "kinds": {**SIGNED["kinds"], "hidden": {"max": 5, "note": "protected faces"}}}
    assert check_problems(before, _errors({"hidden": 5}), roomy)["kinds"]["hidden"]["status"] == "PASS"
    assert check_problems(before, _errors({"hidden": 6}), roomy)["kinds"]["hidden"]["status"] == "FAIL"


def test_signed_with_no_number_for_any_kind_is_still_only_a_report():
    nobody = {"signed": True, "kinds": {k: None for k in KINDS}}
    result = check_problems(_errors({"hidden": 4}), _errors({"hidden": 4}), nobody)
    assert result["status"] == "REPORT_ONLY" and all(k["target"] == "listed" for k in result["kinds"].values())


def test_the_targets_file_is_read_from_json_and_a_missing_one_means_unsigned(tmp_path):
    assert load_targets(tmp_path / "targets.json") is None
    path = tmp_path / "targets.json"
    path.write_text(json.dumps(SIGNED), encoding="utf-8")
    assert load_targets(path) == SIGNED
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="targets"):
        load_targets(path)
    assert default_targets_path().name == "targets.json" and default_targets_path().parent.name == "validate"


def test_check_2_is_in_the_report_and_a_signed_failure_fails_the_verdict():
    m = cube(10.0)
    ok = validate(m, m, _looks("m0"), errors=(_errors({"hidden": 2}), _errors()), targets=SIGNED)
    assert ok.report["checks"]["problems"]["status"] == "PASS" and ok.report["verdict"] == "PASS"
    bad = validate(m, m, _looks("m0"), errors=(_errors({"hidden": 2}), _errors({"hidden": 1})), targets=SIGNED)
    problems = bad.report["checks"]["problems"]
    assert problems["status"] == "FAIL" and problems["kinds"]["hidden"] == {
        "before": 2, "after": 1, "target": 0, "status": "FAIL", "residual": []}
    assert bad.report["verdict"] == "FAIL", "checks 1 and 3 pass; the signed target for check 2 does not"
    assert bad.report["checks"]["textures"]["status"] == "PASS"
    unsigned = validate(m, m, _looks("m0"), errors=(_errors({"hidden": 2}), _errors({"hidden": 1})))
    assert unsigned.report["verdict"] == "PASS" and unsigned.report["checks"]["problems"]["status"] == "REPORT_ONLY"


def test_without_errors_given_validate_runs_find_errors_on_both_meshes():
    m = cube(10.0)
    v = validate(m, m, _looks("m0"))                       # errors=None: the real detectors, imported lazily
    problems = v.report["checks"]["problems"]
    assert problems["status"] == "REPORT_ONLY" and list(problems["kinds"]) == list(KINDS)
    assert all(k["before"] == k["after"] == 0 for k in problems["kinds"].values()), "a clean cube has nothing wrong"
    room = closed_room()
    v = validate(room, _without_faces(room, [4, 5]), _looks("plaster", "brick"))
    assert v.report["checks"]["problems"]["kinds"]["hidden"]["before"] == 12, "find_errors really ran on the room"


def test_loading_the_validator_does_not_load_the_code_it_judges():
    """`find_errors` imports engine.fixes, engine.guard and engine.vis, so check 2 imports it lazily: the
    checks, the evidence and the rest of the Validator can be loaded without any of them."""
    import subprocess
    import sys
    code = ("import sys, engine.validate.checks, engine.validate.evidence\n"
            "bad = sorted(m for m in sys.modules if m.split('.')[:2] in (['engine', 'guard'], ['engine', 'fixes'], "
            "['engine', 'vis'], ['engine', 'detectors']))\n"
            "print('LOADED', bad)\n")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert done.stdout.strip() == "LOADED []", done.stdout


# ---------------------------------------------------------------------------------------------
# Step 4: the evidence -- two 256 px orthographic crops, BEFORE and AFTER, for each of the 20 worst sites
# ---------------------------------------------------------------------------------------------

RED, BLUE = (200, 40, 40), (40, 60, 210)


def _coloured(**colours):
    """Looks for materials named like the keywords, each with its mean texture colour."""
    return Looks(key={n: f"look-{n}" for n in colours}, texel={f"look-{n}": (16, 16) for n in colours},
                 colour={f"look-{n}": c for n, c in colours.items()})


def _crops(tmp_path, site):
    return (np.asarray(Image.open(tmp_path / site["evidence"]["before"]).convert("RGB")),
            np.asarray(Image.open(tmp_path / site["evidence"]["after"]).convert("RGB")))


def test_a_failing_site_gets_two_aligned_256_px_crops_coloured_by_look(tmp_path):
    m = _with_material(_two_looks(cube(10.0)), [2, 3], 1)             # the top is in look m1, blue; the rest red
    looks = _coloured(m0=RED, m1=BLUE)
    v = _check(m, _without_faces(m, [2, 3]), looks)                    # AFTER has lost the top
    entries = write_evidence(v, tmp_path)

    (site,) = v.report["sites"]
    assert site["evidence"] == {"before": "evidence/site-01-before.png", "after": "evidence/site-01-after.png"}
    assert entries == [site["evidence"]]
    assert sorted(p.name for p in (tmp_path / "evidence").iterdir()) == ["site-01-after.png", "site-01-before.png"]
    before, after = _crops(tmp_path, site)
    assert before.shape == after.shape == (256, 256, 3)

    # BEFORE: looking down at the top, which is look m1 (blue) in the middle of the crop
    assert before[128, 128, 2] > before[128, 128, 0] + 100, f"blue at the centre, got {before[128, 128]}"
    assert np.abs(before[128, 128].astype(int) - np.array(BLUE)).max() < 20, "the look's colour, lightly shaded"
    # AFTER: through the hole, the inside of the bottom (look m0, red) seen from behind: another colour
    assert after[128, 128, 0] > after[128, 128, 2], f"not blue any more, got {after[128, 128]}"
    assert np.abs(after[128, 128].astype(int) - before[128, 128].astype(int)).max() > 60
    # the same camera: what did not change is the same pixels, and what did is not all of them
    same = (before == after).all(axis=2).mean()
    assert 0.5 < same < 1.0, f"{same:.2f} of the pixels agree"
    assert tuple(before[0, 128]) == tuple(after[0, 128]) == (255, 220, 0), "a tick marks the site at the top edge"
    assert tuple(before[128, 0]) == (255, 220, 0), "and at the left edge"


def test_a_site_only_a_probe_sees_is_drawn_from_where_the_probe_stood(tmp_path):
    room = closed_room()
    looks = _coloured(plaster=(230, 225, 200), brick=(150, 60, 40))
    v = _check(room, _without_faces(room, [4, 5]), looks)             # the wall y = 0 of the room, gone
    write_evidence(v, tmp_path)
    before, after = _crops(tmp_path, v.report["sites"][0])
    assert before[128, 128, 1] > 150 and before[128, 128, 0] > 150, f"plaster, got {before[128, 128]}"
    assert after[128, 128, 1] < 110, f"through the gap, the brick skin seen from behind: {after[128, 128]}"


def test_only_the_20_worst_sites_get_crops_and_the_worst_come_first(tmp_path):
    slab = grid_slab(20, 20, cell=10.0)                               # 200 x 200 in, faces +z, 800 triangles
    cells = [(i, j) for j in (1, 4, 7, 10, 13, 16, 19) for i in (1, 4, 7, 10, 13, 16, 19)]    # 49, 30 in apart
    lost = [2 * (j * 20 + i) for i, j in cells]
    lost += [2 * (19 * 20 + 19) + 1]                                   # the other triangle of the last cell: twice the area
    v = _check(slab, _without_faces(slab, lost), _looks("m0"))
    sites = v.report["sites"]
    assert v.report["sites_total"] == 49 and len(sites) == 49
    entries = write_evidence(v, tmp_path)
    assert len(entries) == 20 and sum(s["evidence"] is not None for s in sites) == 20
    assert [s["id"] for s in sites if s["evidence"] is not None] == list(range(1, 21)), "the 20 worst"
    assert len(list((tmp_path / "evidence").glob("*.png"))) == 40
    areas = [s["area_in2"] for s in sites]
    assert areas == sorted(areas, reverse=True), "worst (most area lost) first"


def test_one_defect_is_one_site_and_two_far_apart_are_two():
    slab = grid_slab(10, 10, cell=10.0)                               # 100 x 100 in
    # three triangles side by side near one corner, one triangle at the far corner
    lost = [0, 1, 2, 2 * (9 * 10 + 9)]
    v = _check(slab, _without_faces(slab, lost), _looks("m0"))
    first, second = v.report["sites"]
    assert v.report["sites_total"] == 2
    assert first["faces"] == [0, 1, 2] and second["faces"] == [2 * (9 * 10 + 9)]
    assert first["area_in2"] > second["area_in2"]
    assert first["centre"][0] < 30.0 and second["centre"][0] > 70.0
    assert Settings().cluster_cell == 6.0, "the brief's 6 in grid"


def test_a_floor_with_no_failure_has_no_evidence(tmp_path):
    m = cube(10.0)
    v = _check(m, m, _looks("m0"))
    assert write_evidence(v, tmp_path) == []
    assert not (tmp_path / "evidence").exists()


def test_a_wall_lost_whole_is_one_site_though_its_samples_are_further_apart_than_the_grid():
    room = closed_room()
    # the wall y = 0 is 200 x 120 in; its lattice has 19 samples along the long side: 10.5 in apart, more
    # than one 6 in cell, so cells that merely touch would cut the wall into strips
    v = _check(room, _without_faces(room, [4, 5]), _looks("plaster", "brick"))
    assert v.report["sites_total"] == 1
    (site,) = v.report["sites"]
    assert site["faces"] == [4, 5] and site["samples"] == 722 and site["size"] > 200.0


def test_a_face_seen_from_behind_is_drawn_half_and_half_with_purple(tmp_path):
    m = _with_material(_two_looks(cube(10.0)), [2, 3], 1)
    v = _check(m, _with_flipped(m, [2, 3]), _coloured(m0=RED, m1=BLUE))        # the top, now wound away from the viewer
    write_evidence(v, tmp_path)
    before, after = _crops(tmp_path, v.report["sites"][0])
    mixed = 0.5 * before[128, 128].astype(float) + 0.5 * np.array(BACK_TINT)
    assert np.abs(after[128, 128] - mixed).max() <= 1.0, f"{after[128, 128]} is not {mixed}"
    assert np.abs(before[128, 128].astype(int) - np.array(BLUE)).max() < 20


def test_the_after_crop_is_coloured_by_the_looks_of_the_after(tmp_path):
    m = _with_material(_two_looks(cube(10.0)), [2, 3], 1)                       # the top is blue
    v = _check(m, _with_material(m, [2, 3], 0), _coloured(m0=RED, m1=BLUE))     # AFTER has it red
    write_evidence(v, tmp_path)
    before, after = _crops(tmp_path, v.report["sites"][0])
    assert np.abs(before[128, 128].astype(int) - np.array(BLUE)).max() < 20
    assert np.abs(after[128, 128].astype(int) - np.array(RED)).max() < 20, f"red at the centre, got {after[128, 128]}"


def test_render_crop_shades_by_how_squarely_a_face_is_seen_and_leaves_misses_pale():
    slab = grid_slab(2, 2, cell=10.0)                                   # 20 x 20 in at z = 0, faces +z
    caster, normals = build_caster(slab), face_normals(slab)
    colours = np.tile([200.0, 100.0, 50.0], (slab.n_faces, 1))
    centre = np.array([10.0, 10.0, 0.0])

    def crop(u, window=10.0):
        u = np.asarray(u, dtype=float) / np.linalg.norm(u)
        right, up = _basis(u)
        assert abs(right @ u) < 1e-12 and abs(up @ u) < 1e-12 and abs(right @ up) < 1e-12 and np.allclose(np.cross(right, up), -u)
        return render_crop(caster, normals, colours, centre - u * 50.0, u, right, up, window, px=64)

    assert tuple(crop([0.0, 0.0, -1.0])[32, 32]) == (200, 100, 50), "head on: the look's own colour"
    sixty = np.radians(60.0)
    tilted = crop([np.sin(sixty), 0.0, -np.cos(sixty)])[32, 32]
    assert np.abs(tilted - np.array([200, 100, 50]) * (0.55 + 0.45 * 0.5)).max() <= 1, "|cos| 0.5: shade 0.775"
    wide = crop([0.0, 0.0, -1.0], window=100.0)
    assert tuple(wide[2, 2]) == BACKGROUND and tuple(wide[61, 61]) == BACKGROUND, "the window is wider than the slab"
    assert tuple(wide[32, 32]) == (200, 100, 50)


# ---------------------------------------------------------------------------------------------
# Step 5: the `validate` command
# ---------------------------------------------------------------------------------------------

def _snapshot(tmp_path, mesh, name):
    """A directory laid out like `engine.io.snapshot` makes one: `<mesh name>.obj`, `materials.mtl` and a
    16 x 16 PNG in `tex/` for each material. Returns the directory."""
    d = tmp_path / name
    (d / "tex").mkdir(parents=True)
    write_obj(dataclasses.replace(mesh, mtllib="materials.mtl"), d / f"{mesh.name}.obj")
    lines = []
    for i, material in enumerate(mesh.materials):
        _png(d / "tex" / f"{material}.png", 16, 16, (200 - 90 * i, 40 + 70 * i, 40))
        lines += [f"newmtl {material}", "Kd 1 1 1", f"map_Kd tex/{material}.png", ""]
    (d / "materials.mtl").write_text("\n".join(lines), encoding="utf-8")
    return d


def _materials_json(tmp_path, names):
    path = tmp_path / "materials.json"
    path.write_text(json.dumps({"materials": {n: {"map_kd": f"SRC-TEX/{n}.png", "kd": [1.0, 1.0, 1.0],
                                                  "look": f"look-{n}"} for n in names},
                                "looks": {}, "stats": {}}), encoding="utf-8")
    return path


def _validate_args(before, after, materials, out, *more):
    return ["validate", "--before", str(before), "--after", str(after), "--materials", str(materials),
            "--out", str(out), *more]


def test_validate_writes_validation_json_and_evidence_and_exits_2_on_a_failure(tmp_path):
    m = _with_material(_two_looks(cube(10.0)), [2, 3], 1)
    before = _snapshot(tmp_path, m, "before")
    after = _snapshot(tmp_path, _without_faces(m, [2, 3]), "after")
    out = tmp_path / "out"
    code = cli.main(_validate_args(before, after / "cube.obj", _materials_json(tmp_path, ["m0", "m1"]), out))
    assert code == 2

    data = json.loads((out / "validation.json").read_text(encoding="utf-8"))
    assert data["verdict"] == "FAIL" and set(data["checks"]) == {"textures", "problems", "nothing_deleted"}
    assert data["checks"]["textures"]["status"] == "FAIL" and data["checks"]["nothing_deleted"]["status"] == "FAIL"
    assert data["checks"]["problems"]["status"] == "REPORT_ONLY", "no signed targets: check 2 only reports"
    assert set(data["checks"]["problems"]["kinds"]) == set(KINDS)
    (site,) = data["sites"]
    assert site["faces"] == [2, 3] and site["checks"] == ["textures", "nothing_deleted"]
    for name in site["evidence"].values():
        assert Image.open(out / name).size == (256, 256)
    # what the run was made from and what it cost
    assert data["inputs"]["before_sha256"] == sha256_file(before / "cube.obj")
    assert data["inputs"]["after_sha256"] == sha256_file(after / "cube.obj")
    assert data["inputs"]["materials"] == str(tmp_path / "materials.json")
    assert data["viewpoints"]["directions"] == 128 and data["timings_s"]["total"] > 0
    if os.name == "nt":
        assert data["peak_working_set_mb"] > 10.0
    assert data["materials"] == {"unknown_before": [], "unknown_after": [], "no_texel": []}


def test_validate_exits_0_on_a_pass_and_writes_no_evidence(tmp_path, capsys):
    m = _with_material(_two_looks(cube(10.0)), [2, 3], 1)
    before = _snapshot(tmp_path, m, "before")
    out = tmp_path / "out"
    code = cli.main(_validate_args(before, before / "cube.obj", _materials_json(tmp_path, ["m0", "m1"]), out))
    assert code == 0
    data = json.loads((out / "validation.json").read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS" and data["sites"] == [] and not (out / "evidence").exists()
    said = capsys.readouterr().out
    assert "PASS" in said and "textures" in said and "nothing_deleted" in said and "REPORT_ONLY" in said


def test_validate_reads_the_signed_targets_and_a_missed_one_fails_the_run(tmp_path):
    room = closed_room()                                   # find_errors marks its 12 inner faces "hidden"
    before = _snapshot(tmp_path, room, "before")
    out = tmp_path / "out"
    targets = tmp_path / "targets.json"
    targets.write_text(json.dumps({"signed": True, "kinds": {"hidden": 0}}), encoding="utf-8")
    code = cli.main(_validate_args(before, before / "closed_room.obj", _materials_json(tmp_path, ["plaster", "brick"]),
                                   out, "--targets", str(targets)))
    data = json.loads((out / "validation.json").read_text(encoding="utf-8"))
    assert data["checks"]["textures"]["status"] == data["checks"]["nothing_deleted"]["status"] == "PASS"
    assert data["checks"]["problems"]["status"] == "FAIL" and data["checks"]["problems"]["kinds"]["hidden"] == {
        "before": 12, "after": 12, "target": 0, "status": "FAIL", "residual": data["checks"]["problems"]["kinds"][
            "hidden"]["residual"]}
    assert data["checks"]["problems"]["kinds"]["hidden"]["residual"], "the places that still have it"
    assert data["verdict"] == "FAIL" and code == 2 and data["inputs"]["targets"] == str(targets)


def test_validate_says_when_it_was_run_at_a_lower_density_than_the_owners(tmp_path):
    m = cube(10.0)
    before = _snapshot(tmp_path, m, "before")
    out = tmp_path / "out"
    code = cli.main(_validate_args(before, before / "cube.obj", _materials_json(tmp_path, ["m0"]), out,
                                   "--area-per-sample", "100", "--min-per-face", "2"))
    data = json.loads((out / "validation.json").read_text(encoding="utf-8"))
    assert code == 0 and data["settings"]["area_per_sample"] == 100.0 and data["settings"]["min_per_face"] == 2
    assert any("NOT AN OWNER VERDICT" in note for note in data["notes"])
    default = tmp_path / "default"
    cli.main(_validate_args(before, before / "cube.obj", _materials_json(tmp_path, ["m0"]), default))
    assert json.loads((default / "validation.json").read_text(encoding="utf-8"))["notes"] == []


def test_validate_refuses_missing_inputs_with_a_message_and_exit_2(tmp_path, capsys):
    m = cube(10.0)
    before = _snapshot(tmp_path, m, "before")
    mats = _materials_json(tmp_path, ["m0"])
    assert cli.main(_validate_args(before, tmp_path / "nope.obj", mats, tmp_path / "o1")) == 2
    assert "nope.obj" in capsys.readouterr().err
    assert cli.main(_validate_args(before, before / "cube.obj", tmp_path / "nope.json", tmp_path / "o2")) == 2
    assert "nope.json" in capsys.readouterr().err
    assert cli.main(_validate_args(tmp_path / "nowhere", before / "cube.obj", mats, tmp_path / "o3")) == 2
    assert "nowhere" in capsys.readouterr().err
    assert not (tmp_path / "o1" / "validation.json").exists(), "no verdict is written for a run that did not happen"


def test_validate_parser_defaults_are_the_owners():
    args = cli.build_parser().parse_args(["validate", "--before", "b", "--after", "a.obj", "--out", "o"])
    assert args.command == "validate" and str(args.materials).replace("\\", "/") == "data/campus/materials.json"
    assert args.area_per_sample == 36.0 and args.min_per_face == 4 and args.targets is None


# ---------------------------------------------------------------------------------------------
# What v0 does NOT allow: no allowed-change classes yet (the E4 and E5 engines will name theirs)
# ---------------------------------------------------------------------------------------------

def test_v0_has_no_allowed_change_classes_so_removing_a_copy_of_a_back_to_back_pair_fails():
    wall = two_sided_wall()        # faces 0-1 face -y (concrete), faces 2-3 face +y (prismarine): one place, 2 layers
    # a pair in two looks (flicker): take away the second layer and its look is gone from that place
    v = _check(wall, _without_faces(wall, [2, 3]), _looks("concrete", "prismarine"))
    textures, gone = _checks(v)
    assert textures["status"] == "FAIL" and textures["reasons"]["look"] == 50
    assert gone["status"] == "FAIL" and gone["replaced"] == 50 and gone["faces_unmet"] == 2, "expected until E5 exists"

    # a pair in ONE look (what E4 will remove): the look survives on the other layer, but the viewer who saw the
    # removed layer's FRONT now sees the other one's back
    same = Looks(key={"concrete": "L", "prismarine": "L"}, texel={"L": (16, 16)})
    v = _check(wall, _without_faces(wall, [2, 3]), same)
    textures, gone = _checks(v)
    assert textures["status"] == "FAIL" and textures["reasons"]["side"] == 50, "expected until E4 exists"
    assert gone["status"] == "PASS", "nothing is deleted or covered: the surface and its look are still there"


# ---------------------------------------------------------------------------------------------
# Found by an identity sweep over the real snapshots: a sliver 1,190 in long and 0.0008 in wide
# ---------------------------------------------------------------------------------------------

#: Face 4847 of PE_1st_Floor, moved onto z = 0: 1,190 x 0.0008 in (area 0.5 sq in), its three UVs on one line
#: (a 30 UV unit span along it), so 1 texel of a 256 px texture is 0.15 in of position along the face.
SLIVER = np.array([[-40.47, -414.0, 0.0], [1089.37, -37.4, 0.0], [1014.37, -62.4, 0.0]])
SLIVER_UV = np.array([[-275.485, -1.995], [-245.296, -1.995], [-247.3, -1.995]])


def _sliver_mesh():
    return dataclasses.replace(cube(), positions=SLIVER, uvs=SLIVER_UV, face_v=np.array([[0, 1, 2]], dtype=np.int64),
                               face_vt=np.array([[0, 1, 2]], dtype=np.int64), face_vn=np.full((1, 3), -1, dtype=np.int64),
                               face_material=np.zeros(1, dtype=np.int64), face_line=np.ones(1, dtype=np.int64),
                               materials=["m0"], name="sliver")


def test_barycentric_weights_on_a_thousand_to_one_sliver_are_exact():
    face = np.array([[0, 1, 2]])
    for w in ([1 / 6, 2 / 3, 1 / 6], [2 / 3, 1 / 6, 1 / 6], [1 / 6, 1 / 6, 2 / 3], [0.5, 0.25, 0.25]):
        q = (np.array(w) @ SLIVER)[None]
        assert np.abs(_barycentric(SLIVER, face, q)[0] - w).max() < 1e-9, w
    # a point INSIDE has three positive weights; a point just BESIDE the long edge A-B, away from C, has a negative
    # weight for C: by a hundredth of the sliver's width that is -0.01, not off by 1e-4 of its length
    inside = (np.array([0.5, 0.25, 0.25]) @ SLIVER)[None]
    assert _barycentric(SLIVER, face, inside)[0].min() > 0.2
    along = SLIVER[1] - SLIVER[0]
    side = np.array([-along[1], along[0], 0.0]) / np.linalg.norm(along)
    if side @ (SLIVER[2] - SLIVER[0]) > 0.0:
        side = -side                                              # pointing away from C
    width = 1.0 / np.linalg.norm(along)                           # C's distance from A-B: 2 x area / |A-B|
    on_edge = (0.5 * SLIVER[0] + 0.5 * SLIVER[1])[None]
    for fraction in (0.01, 0.6):
        beside = on_edge + side * fraction * width
        weights = _barycentric(SLIVER, face, beside)[0]
        assert weights[2] == pytest.approx(-fraction, abs=1e-6) and weights.sum() == pytest.approx(1.0), fraction
        assert weights.min() < 0.0, "outside the sliver"


def test_identity_holds_on_a_sliver_whose_uvs_run_30_units_along_its_length():
    m = _sliver_mesh()
    look = np.array([[-0.19301817, 0.09523481, 0.9765625]])             # the look direction that failed in the sweep
    v = _check(m, m, _looks("m0", texel=(256, 256)), dirs=look / np.linalg.norm(look), cams=np.zeros((0, 3)),
               probes=np.zeros((0, 3)))
    textures = v.report["checks"]["textures"]
    assert textures["samples"] == 4 and textures["samples_failed"] == 0, textures["reasons"]
    assert v.report["verdict"] == "PASS"


# ---------------------------------------------------------------------------------------------
# Fix round 1, CRITICAL: a NEW face in a look the place did not have, lying ON a visible face or IN FRONT of it
# within the depth tolerance, hides its texture (or z-fights with it). It used to pass checks 1 and 3.
# ---------------------------------------------------------------------------------------------

def _plated(dz, look=1, y=0.0, plate=None, n=4):
    """`(before, after)`: an n x n slab of 10 in cells at z = 0 facing +z in look m0, and the same slab with a
    second layer `dz` above it, all of it, in `look` (0 is m0, 1 is m1). `y` moves both along y."""
    slab = _two_looks(_moved(grid_slab(n, n, cell=10.0), [0.0, y, 0.0]))
    layer = _moved(grid_slab(n, n, cell=10.0) if plate is None else plate, [0.0, y, dz])
    layer = _with_material(_two_looks(layer), np.arange(layer.n_faces), look)
    return slab, _with_plate(slab, layer)


def _other_diagonal(mesh):
    """`mesh`, a grid of quads each cut into the triangles 2k and 2k+1, with every quad cut along its OTHER
    diagonal: the same surface, the same UVs, every face a new one."""
    fv, fvt = mesh.face_v.copy(), mesh.face_vt.copy()
    for a in (fv, fvt):
        first, second = a[0::2].copy(), a[1::2].copy()
        a[0::2] = np.stack([first[:, 0], first[:, 1], second[:, 2]], axis=1)
        a[1::2] = np.stack([first[:, 1], first[:, 2], second[:, 2]], axis=1)
    return dataclasses.replace(mesh, face_v=fv, face_vt=fvt)


@pytest.mark.parametrize("dz", [0.0, 0.01, 0.03, 0.045])
def test_a_new_face_in_another_look_on_or_just_over_a_visible_face_fails_checks_1_and_3(dz):
    before, after = _plated(dz)
    v = _check(before, after, _looks("m0", "m1"))
    textures, gone = _checks(v)
    assert v.report["verdict"] == "FAIL"
    assert textures["status"] == "FAIL" and textures["reasons"]["overlaid"] == 128 == textures["samples_failed"], dz
    assert gone["status"] == "FAIL" and gone["overlaid"] == 128 and gone["covered"] == 0 and gone["deleted"] == 0
    assert v.report["after"]["new_faces"] == 32, "the 32 faces of the layer"
    (site,) = v.report["sites"]
    assert site["reasons"] == {"overlaid": 128} and site["checks"] == ["textures", "nothing_deleted"]


def test_a_new_face_over_a_visible_face_at_the_chtm_tolerance_and_beyond_it():
    before, after = _plated(0.19, y=24000.0)                       # print step 0.1 in: the tolerance is 0.2 in
    v = _check(before, after, _looks("m0", "m1"))
    assert v.report["depth_tolerance_in"] == pytest.approx(0.2)
    gone = _checks(v)[1]
    # the depth tolerance is measured along the line of sight, so from the oblique line to a far probe 0.19 in of
    # height is more than 0.2 in along it: those few samples are `covered`, the rest `overlaid`; all fail
    assert v.report["verdict"] == "FAIL" and gone["overlaid"] + gone["covered"] == 128 and gone["overlaid"] >= 100
    before, after = _plated(0.3, y=24000.0)                        # further in front than that it COVERS
    textures, gone = _checks(_check(before, after, _looks("m0", "m1")))
    assert gone["covered"] == 128 and gone["overlaid"] == 0 and textures["reasons"]["covered"] == 128


def test_a_layer_a_hair_behind_a_visible_face_z_fights_and_one_further_behind_is_hidden():
    looks = _looks("m0", "m1")
    assert _check(*_plated(-0.01), looks).report["verdict"] == "FAIL", "within the 0.02 in that two layers z-fight"
    assert _check(*_plated(-0.03), looks).report["verdict"] == "PASS", "behind the slab and hidden by it"


def test_a_layer_on_only_part_of_a_visible_face_fails_only_the_samples_under_it():
    slab = _two_looks(grid_slab(4, 4, cell=10.0))
    half = _with_material(_two_looks(grid_slab(2, 4, cell=10.0)), np.arange(16), 1)     # x 0..20 of 0..40
    v = _check(slab, _with_plate(slab, half), _looks("m0", "m1"))
    assert _checks(v)[1]["overlaid"] == 64 and _checks(v)[0]["samples_failed"] == 64


def test_adding_or_deleting_an_identical_coplanar_copy_is_not_a_change():
    slab = _two_looks(grid_slab(4, 4, cell=10.0))
    twice = _with_plate(slab, slab)                       # the same faces again: one place, two layers, one look
    looks = _looks("m0", "m1")
    assert _check(twice, slab, looks).report["verdict"] == "PASS", "the top copy deleted: allowed"
    added = _check(slab, twice, looks)
    assert added.report["verdict"] == "PASS" and added.report["after"]["new_faces"] == 0, "an identical copy is no new face"


def test_a_new_layer_in_the_same_look_but_another_uv_fails_and_a_whole_tile_shift_does_not():
    slab = _two_looks(grid_slab(4, 4, cell=10.0))
    looks = _looks("m0", "m1")
    other_uv = _two_looks(grid_slab(4, 4, cell=10.0, break_col=0))                     # +0.37 in U and V everywhere
    v = _check(slab, _with_plate(slab, other_uv), looks)
    assert v.report["verdict"] == "FAIL" and _checks(v)[1]["overlaid"] == 128
    whole_tiles = _two_looks(grid_slab(4, 4, cell=10.0, shift_cols=range(4)))          # +3 and -2 whole tiles
    assert _check(slab, _with_plate(slab, whole_tiles), looks).report["verdict"] == "PASS"


def test_re_cutting_a_surface_into_new_faces_of_the_same_look_and_uv_is_not_overlaid():
    slab = _two_looks(grid_slab(6, 6, cell=10.0))
    v = _check(slab, _other_diagonal(slab), _looks("m0", "m1"))
    assert v.report["verdict"] == "PASS", v.report["checks"]
    assert v.report["after"]["new_faces"] == 72 and _checks(v)[0]["samples_failed"] == 0 and _checks(v)[0]["samples"] > 0


def test_a_new_face_in_a_look_that_BEFOREs_own_window_already_had_is_not_foreign():
    slab = _two_looks(grid_slab(4, 4, cell=10.0))
    plate = _with_material(_two_looks(grid_slab(4, 4, cell=10.0)), np.arange(32), 1)
    before = _with_plate(slab, plate)                     # a flicker pair: one place, the slab in m0 and a plate in m1
    after = _with_plate(slab, _other_diagonal(plate))     # the plate re-cut: new faces, in look m1
    v = _check(before, after, _looks("m0", "m1"))
    assert v.report["verdict"] == "PASS", v.report["checks"]
    assert v.report["after"]["new_faces"] == 32 and _checks(v)[0]["samples"] == 256


def test_a_replaced_face_is_its_own_failure_and_not_an_overlay_on_top_of_it():
    m = _two_looks(cube(10.0))
    textures, gone = _checks(_check(m, _with_material(m, [3], 1), _looks("m0", "m1")))
    assert textures["reasons"]["look"] == 4 and textures["reasons"]["overlaid"] == 0
    assert gone["replaced"] == 4 and gone["overlaid"] == 0
    textures, gone = _checks(_check(cube(10.0), _with_shifted_uv(cube(10.0), 2, 0.5), _looks("m0")))
    assert textures["reasons"]["uv"] == 4 and textures["reasons"]["overlaid"] == 0 and gone["status"] == "PASS"


def test_the_face_grid_offers_every_face_that_passes_within_reach_of_a_point_exactly_once():
    from engine.validate.checks import _FaceGrid
    rng = np.random.default_rng(7)
    n = 300
    corners = rng.uniform(0.0, 100.0, (n, 1, 3)) + rng.uniform(-15.0, 15.0, (n, 3, 3))
    huge = np.array([[[0.0, 0.0, 50.0], [500.0, 0.0, 50.0], [0.0, 500.0, 50.0]],        # too wide for the grid's cap:
                     [[-300.0, 20.0, -300.0], [300.0, 20.0, -300.0], [0.0, 20.0, 400.0]]])   # kept apart and offered to all
    tri = np.concatenate([corners, huge])
    positions = tri.reshape(-1, 3)
    face_v = np.arange(len(positions)).reshape(-1, 3)
    reach = 0.2
    grid = _FaceGrid(positions, face_v, np.arange(len(face_v)), reach)
    points = rng.uniform(-20.0, 120.0, (400, 3))
    rows, faces = grid.lookup(points)
    offered = set(zip(rows.tolist(), faces.tolist()))
    assert len(offered) == len(rows), "no pair is offered twice"
    lo, hi = tri.min(axis=1) - reach, tri.max(axis=1) + reach
    near = ((points[:, None, :] >= lo[None]) & (points[:, None, :] <= hi[None])).all(axis=2)
    wanted = set(zip(*[a.tolist() for a in np.nonzero(near)]))
    assert wanted and wanted <= offered, "every face whose box, grown by the reach, holds the point is offered"
    assert len(offered) < len(points) * len(face_v) / 4, "and the grid really narrows it down"
    assert len(_FaceGrid(positions, face_v, np.zeros(0, dtype=np.int64), reach).lookup(points)[0]) == 0


# ---------------------------------------------------------------------------------------------
# Fix round 1, IMPORTANT: a material materials.json does not know used to get no texel size, so its UV was
# silently never compared (sidewalk A's only material is such a one)
# ---------------------------------------------------------------------------------------------

def _unknown_material_snapshot(tmp_path, with_texture=True):
    """A snapshot folder whose MTL has three materials materials.json does not list: one with a 32 x 16 texture, one flat,
    and one whose texture file is not there; and a materials.json that lists a single other material."""
    from engine.io.mtl import parse_mtl
    snap = tmp_path / "snap"
    (snap / "tex").mkdir(parents=True)
    if with_texture:
        _png(snap / "tex" / "walk.png", 32, 16, (100, 150, 200))
    (snap / "materials.mtl").write_text(
        "newmtl Sidewalk_x\nKd 0.5 1 1\nmap_Kd tex/walk.png\n\nnewmtl Plain_y\nKd 0.2 0.4 0.6\n\n"
        "newmtl Ghost_z\nKd 1 1 1\nmap_Kd tex/not_there.png\n", encoding="utf-8")
    materials = _materials_json(tmp_path, ["known"])
    return parse_mtl(snap / "materials.mtl"), snap, materials


def test_a_material_materials_json_does_not_know_gets_its_texture_size_and_colour_from_the_snapshot(tmp_path):
    mtl, snap, materials = _unknown_material_snapshot(tmp_path)
    looks = load_looks(materials, [(mtl, snap)])
    assert looks.key == {"known": "look-known"}, "materials.json's own entries, and only those"
    assert looks.key_of("Sidewalk_x") == "unknown:Sidewalk_x"
    assert looks.texel == {"unknown:Sidewalk_x": (32, 16)}, "read from the snapshot's own PNG header"
    assert looks.colour["unknown:Sidewalk_x"] == (50, 150, 200), "the texture's mean (100, 150, 200) times Kd (0.5, 1, 1)"
    assert looks.colour["unknown:Plain_y"] == (51, 102, 153), "flat: its Kd"
    assert "unknown:Plain_y" in looks.flat and "unknown:Ghost_z" not in looks.flat, "a texture that is missing is not flat"


def test_the_uv_of_a_material_unknown_to_materials_json_is_compared(tmp_path):
    mtl, snap, materials = _unknown_material_snapshot(tmp_path)
    looks = load_looks(materials, [(mtl, snap)])
    m = dataclasses.replace(cube(10.0), materials=["Sidewalk_x"])
    assert _check(m, m, looks).report["verdict"] == "PASS"
    v = _check(m, _with_shifted_uv(m, 2, 0.5), looks)
    textures = v.report["checks"]["textures"]
    assert textures["status"] == "FAIL" and textures["reasons"]["uv"] == 4, "it used to PASS: no texel size, no UV test"
    assert v.report["materials"]["no_texel"] == [], "nothing is left unchecked"
    assert any("not in materials.json" in note and "Sidewalk_x" in note for note in v.report["notes"]), v.report["notes"]


def test_a_look_with_no_texture_size_is_listed_in_the_notes_and_never_skipped_silently():
    m = _with_material(_two_looks(cube(10.0)), [2, 3], 1)            # the top is m1, the rest m0
    looks = Looks(key={"m0": "A", "m1": "B"}, flat=frozenset({"B"}))   # no texel size for either; B is flat by design
    v = _check(m, _with_shifted_uv(m, 2, 0.5), looks)
    assert v.report["verdict"] == "PASS", "with no texture to show it, a UV shift cannot be seen: it is not a failure"
    listed = {e["look"]: e for e in v.report["materials"]["no_texel"]}
    assert listed == {"A": {"look": "A", "materials": ["m0"], "flat": False},
                      "B": {"look": "B", "materials": ["m1"], "flat": True}}
    notes = " | ".join(v.report["notes"])
    assert "UV NOT COMPARED" in notes and "A (m0)" in notes, "the one whose texture size is simply unknown"
    assert "flat" in notes and "B (m1)" in notes, "and the flat one, listed too"


def test_validate_command_compares_the_uv_of_a_material_missing_from_materials_json_and_says_so(tmp_path):
    m = cube(10.0)                                                    # its material m0 is NOT in the materials.json below
    before = _snapshot(tmp_path, m, "before")
    after = _snapshot(tmp_path, _with_shifted_uv(m, 2, 0.5), "after")
    out = tmp_path / "out"
    code = cli.main(_validate_args(before, after / "cube.obj", _materials_json(tmp_path, ["some_other_material"]), out))
    data = json.loads((out / "validation.json").read_text(encoding="utf-8"))
    assert code == 2 and data["checks"]["textures"]["reasons"]["uv"] == 4, "it used to exit 0"
    assert data["materials"]["unknown_before"] == ["m0"] and data["materials"]["no_texel"] == []
    assert any("not in materials.json" in note for note in data["notes"])
    # and when nothing is wrong with the UV the same material passes, with the same note
    same = tmp_path / "same"
    assert cli.main(_validate_args(before, before / "cube.obj", tmp_path / "materials.json", same)) == 0
    assert any("not in materials.json" in note for note in json.loads((same / "validation.json").read_text(
        encoding="utf-8"))["notes"])


# ---------------------------------------------------------------------------------------------
# Fix round 1, IMPORTANT: the cover test was replayed from the best viewpoint only. A cover that only an
# eye-height probe sees was missed whenever an outside direction won (AGENTS.md section 5: eye height)
# ---------------------------------------------------------------------------------------------

def _vertical_panel(x, y0, y1, z0, z1):
    """A rectangle in the plane x = `x` (two triangles), one material, no UVs."""
    corners = np.array([[x, y0, z0], [x, y1, z0], [x, y1, z1], [x, y0, z1]], dtype=float)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return dataclasses.replace(
        cube(), positions=corners, uvs=np.zeros((1, 2)), face_v=faces, face_vt=np.zeros((2, 3), dtype=np.int64),
        face_vn=np.full((2, 3), -1, dtype=np.int64), face_material=np.zeros(2, dtype=np.int64),
        face_line=np.arange(1, 3, dtype=np.int64), materials=["m0"], name="panel")


def test_a_cover_only_an_eye_height_probe_sees_is_found_and_the_crop_is_drawn_from_the_probe(tmp_path):
    floor = grid_slab(10, 10, cell=10.0)                               # 100 x 100 in at z = 0 facing +z: 800 samples
    after = _with_plate(floor, _vertical_panel(30.0, 0.0, 40.0, 10.0, 60.0))
    probe = np.array([[20.0, 20.0, 63.0]])                             # the only probe, 63 in above (20, 20)
    none = np.zeros((0, 3))
    sky = np.array([[0.0, 0.0, -1.0]])                                 # one look direction: straight down, square to the floor

    # from outside nothing is wrong: straight down on the floor the panel (a sheet at x = 30) covers nothing
    assert _check(floor, after, _looks("m0"), dirs=sky, cams=none, probes=none).report["verdict"] == "PASS"

    v = _check(floor, after, _looks("m0"), dirs=sky, cams=none, probes=probe)
    textures, gone = _checks(v)
    assert v.report["verdict"] == "FAIL" and gone["status"] == "FAIL" and textures["status"] == "FAIL"
    # exactly the samples whose line to the probe crosses the panel, worked out here from scratch
    s = face_samples(floor)
    o = s.points + [0.0, 0.0, 0.02]                                    # BEFORE's ray starts 0.02 in above the face
    lam = (30.0 - o[:, 0]) / (probe[0, 0] - o[:, 0])                   # where along the segment it meets x = 30
    y, z = o[:, 1] + lam * (probe[0, 1] - o[:, 1]), o[:, 2] + lam * (probe[0, 2] - o[:, 2])
    hidden = (o[:, 0] > 30.0) & (lam > 0.0) & (lam < 1.0) & (y >= 0.0) & (y <= 40.0) & (z >= 10.0) & (z <= 60.0)
    assert 0 < hidden.sum() < len(s)
    assert gone["covered"] == int(hidden.sum()) and textures["reasons"]["covered"] == int(hidden.sum())
    # the crop of that site is drawn from the probe that saw the cover (column 1: after the one direction)
    assert set(v.wit_col[np.concatenate(v.members)].tolist()) == {1}
    write_evidence(v, tmp_path)
    before, after_img = _crops(tmp_path, v.report["sites"][0])
    assert (before != after_img).any(), "the panel shows in AFTER, in front of the floor"


def test_the_cover_is_replayed_from_the_probe_only_where_it_is_not_already_the_best_viewpoint(monkeypatch):
    from engine.validate import checks
    calls = []
    original = checks._Judge.covered
    monkeypatch.setattr(checks._Judge, "covered", lambda self, p, w: (calls.append(len(p)), original(self, p, w))[1])
    none, sky = np.zeros((0, 3)), outside_directions(128)

    tile = grid_slab(1, 1, cell=10.0)                      # 8 samples, the probe right over the middle: the best of all
    _check(tile, tile, _looks("m0"), dirs=sky, cams=none, probes=np.array([[5.0, 5.0, 63.0]]))
    assert sum(calls) == 8, "one replay each: the probe is the witness already"

    calls.clear()
    floor = grid_slab(10, 10, cell=10.0)                   # most samples have a direction straight above as the best
    _check(floor, floor, _looks("m0"), dirs=sky, cams=none, probes=np.array([[20.0, 20.0, 63.0]]))
    assert 800 < sum(calls) <= 1600, "at most twice the casts"
    calls.clear()
    _check(floor, floor, _looks("m0"), dirs=sky, cams=none, probes=none)
    assert sum(calls) == 800, "no probe, no second replay"


def test_given_cameras_and_probes_are_positions_in_the_models_own_coordinates():
    """Meshes come in the model's coordinates and are shifted into the Validator's frame inside `validate`; the cameras
    and probes a caller hands it are positions too, in the SAME coordinates (directions need no frame)."""
    none = np.zeros((0, 3))
    sky = np.array([[0.0, 0.0, -1.0]])
    near = grid_slab(10, 10, cell=10.0)
    far = _moved(near, [24000.0, 24000.0, 0.0])
    panel = _vertical_panel(30.0, 0.0, 40.0, 10.0, 60.0)
    counts = []
    for shift in ([0.0, 0.0, 0.0], [24000.0, 24000.0, 0.0]):
        before = _moved(near, shift)
        after = _with_plate(before, _moved(panel, shift))
        v = _check(before, after, _looks("m0"), dirs=sky, cams=none, probes=np.array([[20.0, 20.0, 63.0]]) + shift)
        counts.append(v.report["checks"]["nothing_deleted"]["covered"])
    assert counts[0] == counts[1] > 0, counts


# ---------------------------------------------------------------------------------------------
# Fix round 1, minor 7: `inputs.targets` named the file only when --targets was given
# ---------------------------------------------------------------------------------------------

def test_validate_records_the_default_targets_file_it_used_when_none_is_given(tmp_path, monkeypatch):
    import engine.validate.checks as checks
    default = tmp_path / "default_targets.json"
    default.write_text(json.dumps({"signed": True, "kinds": {"hidden": 0}}), encoding="utf-8")
    monkeypatch.setattr(checks, "default_targets_path", lambda: default)
    room = closed_room()                                           # find_errors marks its 12 inner faces "hidden"
    before = _snapshot(tmp_path, room, "before")
    out = tmp_path / "out"
    code = cli.main(_validate_args(before, before / "closed_room.obj",
                                   _materials_json(tmp_path, ["plaster", "brick"]), out))      # no --targets
    data = json.loads((out / "validation.json").read_text(encoding="utf-8"))
    assert data["inputs"]["targets"] == str(default), "the file that was really used"
    assert data["checks"]["problems"]["signed"] is True and data["checks"]["problems"]["status"] == "FAIL"
    assert code == 2

    monkeypatch.setattr(checks, "default_targets_path", lambda: tmp_path / "there_is_no_such_file.json")
    cli.main(_validate_args(before, before / "closed_room.obj", tmp_path / "materials.json", tmp_path / "out2"))
    none = json.loads((tmp_path / "out2" / "validation.json").read_text(encoding="utf-8"))
    assert none["inputs"]["targets"] is None and none["checks"]["problems"]["signed"] is False


# ---------------------------------------------------------------------------------------------
# Fix round 1, minor 8: the process peak-memory probe (working set and commit) lives in winprobe
# ---------------------------------------------------------------------------------------------

def test_winprobe_gives_the_peak_working_set_and_the_peak_commit_and_the_reader_uses_it(monkeypatch):
    from engine.campus import winprobe
    from engine.io import skp_reader
    if os.name == "nt":
        working_set, commit = winprobe.peak_memory_mb()
        assert isinstance(working_set, float) and isinstance(commit, float) and working_set > 10.0 and commit > 10.0
        assert abs(winprobe.get_process_peak_memory_mb() - working_set) < 50.0, "the older census probe is the first of them"
        reader = skp_reader._peak_memory_mb()
        assert abs(reader[0] - working_set) < 50.0 and abs(reader[1] - commit) < 50.0, "the SketchUp reader asks winprobe"
    monkeypatch.setattr(os, "name", "posix")
    assert winprobe.peak_memory_mb() == (None, None)
    assert winprobe.get_process_peak_memory_mb() == 0.0 and skp_reader._peak_memory_mb() == (None, None)
