"""Brief 09 item 2: FOLDS -- two faces sharing an edge, folded onto the same side of it in one
plane, so the same area is covered twice (file B's faces 5750/5751, which close the top of a ramp's
side wall and show as two lines inside a surface in the `.skp`; file B's merge region 79, 47.7 sq
in covered twice). Each is detected; a member is removed only when the rays through it
(`engine.guard.piece_rays`) show that the rest of the model still covers it exactly -- every line
along which it was seen still meets a face level with it, so nothing reaches the inside, or
anything else; and every fold left is reported, with the reason.
"""
import numpy as np
import pytest

from engine.detectors.folds import detect_folds
from engine.fixes.pipeline import FixProfile, fix_object
from engine.pipeline import analyse_topology
from engine.rays.caster import EmbreeCaster
from engine.tests.fixtures.build import (plate_with_crossing_fold, printed,
                                         slab_with_folded_lip_over_a_slot, slab_with_folded_pair,
                                         stacked_duplicate_slab)

_FAST = FixProfile(guard_size=(120, 80), n_dirs=32, solidify=False)


def _folds(mesh, protected=None):
    """The detector exactly as `fix_object` calls it: one plane within the T-junction tolerance."""
    topo = analyse_topology(mesh)
    return detect_folds(topo.positions_w, topo.face_w, mesh.face_material,
                        contact_tol=1.5 * float(topo.quanta.max()), protected=protected)


def _fold(result, faces):
    found = [f for f in result.fold_report["folds"] if f["faces"] == list(faces)]
    assert len(found) == 1, result.fold_report
    return found[0]


def _z_down(mesh, xy, top=50.0):
    xy = np.asarray(xy, dtype=np.float64)
    tri, t = EmbreeCaster(mesh.positions, mesh.face_v).first_hit(
        np.column_stack([xy, np.full(len(xy), top)]), np.tile([0.0, 0.0, -1.0], (len(xy), 1)))
    return np.where(tri >= 0, top - t, np.nan)


# ----------------------------------------------------------------------------- the detector


@pytest.mark.parametrize("flip", [False, True])
def test_a_folded_pair_is_one_fold(flip):
    d = _folds(slab_with_folded_pair(flip=flip))
    assert d.report["n_folds"] == 1
    [fold] = d.folds
    assert fold["faces"] == [0, 2] and fold["reason"] is None
    # face 2 lies wholly within face 0: the area covered twice is all of face 2 (0.1 of 40 x 40)
    assert fold["overlap_area"] == pytest.approx(160.0)


def test_a_crossing_pair_is_a_fold_too():
    [fold] = _folds(plate_with_crossing_fold()).folds
    assert fold["faces"] == [0, 1] and fold["reason"] is None
    assert 0.0 < fold["overlap_area"] < 40.0


def test_a_fold_between_two_materials_is_never_proposed():
    """Which of two colours a person wants is not a question geometry can answer -- the same rule
    the duplicate-layer removal keeps."""
    [fold] = _folds(slab_with_folded_pair(material=1)).folds
    assert fold["reason"] == "different materials"


@pytest.mark.parametrize("invented", [0, 2])
def test_a_fold_with_a_face_solidify_invented_is_never_proposed(invented):
    """Solidify's faces close a shell; whether one of them should lie over an original face is
    the cap guard's question, not this one's."""
    m = slab_with_folded_pair()
    protected = np.zeros(m.n_faces, dtype=bool)
    protected[invented] = True
    [fold] = _folds(m, protected).folds
    assert fold["reason"] == "protected"


def test_exact_duplicates_are_not_folds():
    """Two copies of one triangle share all three edges: a duplicate layer, which
    `engine.fixes.overlap` removes when the rest of its region covers it. Counted, never a fold."""
    d = _folds(stacked_duplicate_slab(nx=3, ny=3))
    assert d.folds == [] and d.report["n_duplicate_pairs"] > 0


# ------------------------------------------------------------------- through `fix_object`


@pytest.mark.parametrize("flip", [False, True])
def test_fix_object_resolves_a_fold_by_removing_the_member_the_rest_still_covers(flip):
    r = fix_object(slab_with_folded_pair(flip=flip), {}, _FAST)
    assert r.removed_fragments[2] and not r.removed_fragments[0]
    assert r.n_removed_folds == 1
    fold = _fold(r, [0, 2])
    assert fold["verdict"] == "resolved" and fold["redundant"] == 2
    # each member judged alone: face 2 covered along every line, face 0 not (its part beyond
    # face 2 opens onto the inside of the slab)
    alone = {m["face"]: m for m in fold["members"]}
    assert alone[2]["lines"] > 0 and alone[2]["lines_level"] == alone[2]["lines"]
    assert alone[0]["lines_level"] < alone[0]["lines"] and alone[0]["lines_inside"] > 0
    assert fold["lines"] > 0 and fold["lines_level"] == fold["lines"]
    [ray] = [v for v in r.fragment_ray_check if v["faces"] == [2]]
    assert ray["kind"] == "fold" and ray["refused"] is False and ray["removed"] is True
    [removal] = [e for e in r.fragment_removals if e["faces"] == [2]]
    assert removal["kind"] == "fold" and removal["covered_by"] == 0
    # the top is still whole where the fold was
    g = np.linspace(1.0, 39.0, 20)
    xy = np.array([(x, y) for x in g for y in g])
    assert np.isclose(_z_down(r.mesh, xy), 0.0, atol=1e-6).all()
    assert r.passed is True


def test_fix_object_keeps_the_member_over_a_slot_and_removes_the_one_the_rest_covers():
    """File B's 5750/5751 in miniature. The lip lies within its fold partner (the cover) all but a
    sliver over the slot -- so it is NOT the one to go: removed, it opens the slot. The cover is
    what the rest of the model covers exactly, the lip over the top's surface and the top beside
    it, so the fold is resolved by removing the cover, and the slot stays shut."""
    m = printed(slab_with_folded_lip_over_a_slot())
    r = fix_object(m, {}, FixProfile(guard_size=(240, 160), n_dirs=32, solidify=False))
    assert r.fragment_report["n_sliver_faces"] == 0          # the premise: only the fold names it
    fold = _fold(r, [0, 8])
    alone = {m["face"]: m for m in fold["members"]}
    assert alone[0]["lines_inside"] > 0                        # the lip alone opens the slot
    assert alone[8]["lines"] > 0 and alone[8]["lines_level"] == alone[8]["lines"]
    assert fold["redundant"] == 8 and fold["verdict"] == "resolved"
    assert r.removed_fragments[8] and not r.removed_fragments[0]
    c = 1000.0
    ys = np.linspace(c - 6.0, c + 7.5, 28)
    xs = c + 0.1 * 0.05 * (ys - (c - 8.0)) / 16.0              # inside the lip's own sliver
    assert np.isclose(_z_down(r.mesh, np.column_stack([xs, ys])), 0.0, atol=1e-6).all()
    assert r.passed is True


def test_fix_object_leaves_a_fold_where_each_member_covers_what_nothing_else_does():
    """File B's region 79 in miniature. Removing either member would only show the sky here --
    which the rays would let DEBRIS uncover -- but a fold's member is no debris: it goes only
    where the rest of the model still covers it, and here nothing does. Resolving it would need a
    vertex where the two edges cross, which nothing here may invent."""
    r = fix_object(plate_with_crossing_fold(), {}, _FAST)
    assert not r.removed_fragments.any() and r.n_removed_folds == 0
    fold = _fold(r, [0, 1])
    assert fold["verdict"] == "left" and fold["reason"] == "neither is covered by the rest"
    assert fold["redundant"] is None
    assert all(0 < m["lines_level"] < m["lines"] and m["lines_inside"] == 0
               for m in fold["members"])
    assert r.fold_report["n_left"] == 1 and r.fold_report["n_resolved"] == 0
    assert r.passed is True


def test_fix_object_reports_a_fold_it_never_proposed():
    r = fix_object(slab_with_folded_pair(material=1), {}, _FAST)
    assert not r.removed_fragments[2] and r.n_removed_folds == 0
    fold = _fold(r, [0, 2])
    assert fold["verdict"] == "left" and fold["reason"] == "different materials"
    assert fold["members"] == [] and fold["lines"] is None
    assert r.passed is True


def test_when_the_rest_covers_both_members_the_smaller_goes():
    from engine.tests.fixtures.build import slab_with_fold_lying_on_top
    r = fix_object(slab_with_fold_lying_on_top(), {}, _FAST)
    fold = _fold(r, [12, 13])
    assert all(m["lines"] > 0 and m["lines_level"] == m["lines"] for m in fold["members"])
    assert fold["redundant"] == 12 and fold["verdict"] == "resolved"
    assert r.removed_fragments[12] and not r.removed_fragments[13]
    assert r.passed is True


def test_a_fold_member_is_judged_as_a_piece_that_must_stay_covered(monkeypatch):
    """Proposed, a fold's member is judged with every other removal done as a piece that must
    STAY COVERED (`piece_ray_check(covered=...)`), not as debris, which may uncover the sky."""
    import engine.fixes.pipeline as fix_pipeline
    seen = []
    real = fix_pipeline.piece_ray_check

    def spy(units, *args, covered=None, **kwargs):
        seen.append([([int(f) for f in u], bool(c)) for u, c in zip(units, covered)])
        return real(units, *args, covered=covered, **kwargs)

    monkeypatch.setattr(fix_pipeline, "piece_ray_check", spy)
    fix_object(slab_with_folded_pair(), {}, _FAST)
    assert seen and seen[0] == [([2], True)]


def test_fold_resolution_is_deterministic():
    a, b = (fix_object(slab_with_folded_pair(flip=True), {}, _FAST) for _ in range(2))
    assert a.fold_report == b.fold_report
    assert a.removed_fragments.tolist() == b.removed_fragments.tolist()
    assert np.array_equal(a.mesh.face_v, b.mesh.face_v)
