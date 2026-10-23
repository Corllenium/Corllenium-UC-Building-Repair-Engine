"""The Validator's opt-in allowed-change class `coincident_backface_removed` (owner decision 2026-10-24, relayed by the
coordinator): a BEFORE sample that is deleted / replaced / look-changed is reclassified as allowed iff its face is gone
in AFTER, AFTER keeps a coincident OPPOSITE-facing twin that was the exposed surface in BEFORE, and the sample's own
face had front exposure 0 in BEFORE. Default settings keep every caller strict."""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from engine.tests.fixtures.build import cube
from engine.tests.test_validate_checks import NO_ERRORS, _looks
from engine.validate.checks import ALLOWED_CHANGE_CLASSES, CBR, Settings, validate

SIDE = [8, 9]            # the x = s face of `cube()`: quad (1, 2, 6, 5), outward
LOOKS = _looks("m0", "m1")
ALLOW = Settings(allowed_changes={CBR})


def _with_twin(mesh, faces, material, *, flip):
    """`mesh` plus a coincident copy of `faces` (reversed winding with `flip`) in `material`."""
    fv = mesh.face_v[faces][:, ::-1] if flip else mesh.face_v[faces]
    fvt = mesh.face_vt[faces][:, ::-1] if flip else mesh.face_vt[faces]
    n = mesh.n_faces + len(faces)
    return dataclasses.replace(
        mesh, face_v=np.vstack([mesh.face_v, fv]), face_vt=np.vstack([mesh.face_vt, fvt]),
        face_vn=np.vstack([mesh.face_vn, mesh.face_vn[faces]]),
        face_material=np.concatenate([mesh.face_material, [material] * len(faces)]),
        face_line=np.arange(1, n + 1, dtype=np.int64), materials=["m0", "m1"])


def _without(mesh, faces):
    keep = np.ones(mesh.n_faces, bool)
    keep[list(faces)] = False
    return dataclasses.replace(mesh, face_v=mesh.face_v[keep], face_vt=mesh.face_vt[keep], face_vn=mesh.face_vn[keep],
                               face_material=mesh.face_material[keep],
                               face_line=np.arange(1, int(keep.sum()) + 1, dtype=np.int64))


def _run(before, after, settings=Settings()):
    return validate(before, after, LOOKS, errors=(NO_ERRORS, NO_ERRORS), settings=settings)


def backface_pair():
    """A closed 10 in cube whose x = s side carries an inward-facing coincident copy in another look (the Minecraft
    export's back-to-back twin): BEFORE, and AFTER = BEFORE without the inward copy (faces 12, 13)."""
    before = _with_twin(cube(), SIDE, 1, flip=True)
    return before, _without(before, [12, 13])


def test_settings_default_is_empty_and_the_class_name_is_checked():
    assert Settings().allowed_changes == frozenset() and Settings().as_dict()["allowed_changes"] == []
    s = Settings(allowed_changes=[CBR])
    assert s.allowed_changes == frozenset({CBR}) and s.as_dict()["allowed_changes"] == [CBR]
    assert Settings(**s.as_dict()).allowed_changes == frozenset({CBR}), "round-trips through as_dict (the site judge)"
    assert ALLOWED_CHANGE_CLASSES == frozenset({CBR}) and CBR == "coincident_backface_removed"
    with pytest.raises(ValueError, match="allowed"):
        Settings(allowed_changes={"anything_goes"})


def test_strict_default_still_fails_removing_the_inward_twin_of_another_look():
    before, after = backface_pair()
    v = _run(before, after)
    assert not v.passed
    t, g = v.report["checks"]["textures"], v.report["checks"]["nothing_deleted"]
    assert t["reasons"]["look"] + t["reasons"]["deleted"] > 0 or g["replaced"] + g["deleted"] > 0
    assert "allowed_changes" not in v.report and v.report["settings"]["allowed_changes"] == []


def test_with_the_class_the_same_removal_passes_and_is_reported_under_allowed_changes():
    before, after = backface_pair()
    strict = _run(before, after)
    v = _run(before, after, ALLOW)
    assert v.passed, v.report["checks"]
    t, g = v.report["checks"]["textures"], v.report["checks"]["nothing_deleted"]
    assert t["status"] == "PASS" and g["status"] == "PASS" and g["floor"]["status"] == "PASS"
    assert g["deleted"] == 0 and g["replaced"] == 0 and v.report["sites"] == []
    allowed = v.report["allowed_changes"][CBR]
    assert allowed["samples"] > 0 and allowed["faces"] == 2 and allowed["faces_excused_from_floor"] == 2
    assert allowed["deleted"] + allowed["look"] == allowed["samples"]
    # exactly the samples that failed strictly were reclassified, nothing else changed
    strict_g = strict.report["checks"]["nothing_deleted"]
    assert allowed["samples"] == strict_g["deleted"] + strict_g["replaced"]
    assert v.report["settings"]["allowed_changes"] == [CBR]
    assert any("ALLOWED CHANGES" in note and CBR in note for note in v.report["notes"])


def _with_shifted_uv_twin(mesh, faces, shift):
    """`mesh` plus an inward-facing coincident copy of `faces` in the SAME look whose UVs are shifted by `shift`
    (a non-integer: a different texture layout)."""
    twin = _with_twin(mesh, faces, 0, flip=True)
    k = len(faces)
    new_rows = mesh.uvs[mesh.face_vt[faces][:, ::-1]].reshape(-1, 2) + shift
    fvt = twin.face_vt.copy()
    fvt[-k:] = np.arange(len(mesh.uvs), len(mesh.uvs) + 3 * k).reshape(k, 3)
    return dataclasses.replace(twin, uvs=np.vstack([mesh.uvs, new_rows]), face_vt=fvt, materials=["m0", "m1"])


def test_the_class_also_excuses_the_uv_status_of_a_removed_backface_under_the_same_conditions():
    before = _with_shifted_uv_twin(cube(), SIDE, 0.37)
    after = _without(before, [12, 13])
    strict = _run(before, after)
    assert not strict.passed and strict.report["checks"]["textures"]["reasons"]["uv"] > 0
    v = _run(before, after, ALLOW)
    assert v.passed, v.report["checks"]
    allowed = v.report["allowed_changes"][CBR]
    assert allowed["uv"] > 0 and allowed["uv"] == strict.report["checks"]["textures"]["reasons"]["uv"]
    assert allowed["samples"] == allowed["deleted"] + allowed["look"] + allowed["uv"]
    assert v.report["checks"]["textures"]["reasons"]["uv"] == 0
    # the same shifted twin, OUTWARD (both fronts exposed): the uv failure stays
    outward = _with_twin(cube(), SIDE, 0, flip=False)
    k = 2
    fvt = outward.face_vt.copy()
    fvt[-k:] = np.arange(len(cube().uvs), len(cube().uvs) + 6).reshape(k, 3)
    outward = dataclasses.replace(outward, uvs=np.vstack([cube().uvs, cube().uvs[cube().face_vt[SIDE]].reshape(-1, 2) + 0.37]),
                                  face_vt=fvt)
    v2 = _run(outward, _without(outward, [12, 13]), ALLOW)
    assert not v2.passed and v2.report["allowed_changes"][CBR]["uv"] == 0


def test_a_non_coincident_deletion_still_fails_with_the_class_enabled():
    before = cube()
    v = _run(before, _without(before, SIDE), ALLOW)
    assert not v.passed
    assert v.report["allowed_changes"][CBR]["samples"] == 0
    assert v.report["checks"]["nothing_deleted"]["deleted"] > 0


def test_a_same_facing_twin_removal_is_not_covered_by_the_class():
    before = _with_twin(cube(), SIDE, 1, flip=False)       # an outward copy in another look: both fronts exposed
    v = _run(before, _without(before, [12, 13]), ALLOW)
    assert not v.passed
    assert v.report["allowed_changes"][CBR]["samples"] == 0
    g = v.report["checks"]["nothing_deleted"]
    assert g["replaced"] + g["deleted"] > 0


def test_removing_the_exposed_face_and_keeping_the_inward_twin_is_not_allowed():
    before, _ = backface_pair()
    v = _run(before, _without(before, SIDE), ALLOW)        # the visible outward face goes, the hidden copy stays
    assert not v.passed and v.report["allowed_changes"][CBR]["samples"] == 0
