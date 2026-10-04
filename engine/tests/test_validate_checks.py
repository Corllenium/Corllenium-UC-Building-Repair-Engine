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
from engine.validate.checks import (Looks, LookTable, Settings, check_problems, default_targets_path,
                                    depth_tolerance, face_fingerprints, face_look_ids, load_looks, load_targets,
                                    png_size, print_step, validate)
from engine.validate.evidence import BACK_TINT, BACKGROUND, _basis, render_crop, write_evidence
from engine.validate.sampling import face_normals, face_samples
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
        "covered": 0, "deleted": 4, "look": 0, "uv": 0, "side": 0}
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
    assert v.report["materials"] == {"unknown_before": ["m0"], "unknown_after": ["m0"]}
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
