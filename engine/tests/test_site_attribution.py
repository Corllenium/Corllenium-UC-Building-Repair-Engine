"""Job P1-K3b item 1: a focus run's failing samples, each charged to the sites that could have caused it.

`SiteJudge.check` names every failing sample with its BEFORE face, its point and the viewpoint that judged it;
`SiteJudge.attribute` charges a sample to a site when its face is one the site touched, or lies within the site's
grown box, or is one of the site's cover candidates AND one of the site's new faces lies between the sample and
that viewpoint. A sample charged to no site is unknown: it is kept, never dropped.
"""
import dataclasses

import numpy as np

from engine.site_judge import SiteJudge
from engine.tests.fixtures.build import grid_slab
from engine.tests.test_validate_checks import _looks, _moved, _two_looks, _with_material, _with_plate, _without_faces
from engine.tests.test_validate_mutations import LOOKS, SIZE, two_look_cube


def _judge(before, looks, **kw):
    judge = SiteJudge(looks, **kw)
    judge.begin(before)
    return judge


def test_the_verdict_names_each_failing_samples_face_point_and_judging_viewpoint():
    m = two_look_cube()
    judge = _judge(m, LOOKS)
    after = _without_faces(m, [8])
    verdict = judge.check(after, judge.focus(after, [8], []))
    s = verdict.samples
    # job P2-V2: 4 failing samples, and the floor's row for face 8 (index -1 - its viewpoint)
    assert len(s.face) == len(verdict.failing) == 5 and (s.index >= 0).sum() == 4 and set(s.face[s.index < 0]) == {8}
    assert {(int(f), int(i)) for f, i in zip(s.face, s.index)} == set(verdict.failing)
    assert np.allclose(s.point[:, 0], SIZE), "the samples lie on the x = 10 side, in the model's coordinates"
    # the judging viewpoint: a far-off direction (a unit vector toward the viewer) or a camera / probe position,
    # and either way on the side the face looks at (+x)
    toward = np.where(s.is_dir[:, None], s.witness, s.witness - s.point)
    assert (toward[:, 0] > 0).all()
    assert np.allclose(np.linalg.norm(s.witness[s.is_dir], axis=1), 1.0)
    assert [c["deleted"] for c in s.clusters] == [4, 1] and (s.cluster[s.index >= 0] == 0).all()


def test_a_failure_on_a_face_a_site_touched_is_charged_to_that_site_only():
    m = two_look_cube()
    judge = _judge(m, LOOKS, margin=1.0)
    after = _without_faces(m, [8])
    bad = judge.site_focus(after, [8], [])
    calm = judge.site_focus(after, [], [])                  # a site that changed nothing here
    verdict = judge.check(after, judge.union([bad, calm]))
    got = judge.attribute(verdict, {1: bad, 2: calm})
    assert sorted(got.charged) == [1] and len(got.charged[1]) == 5          # 4 samples and the floor's row (P2-V2)
    assert got.how[1] == {"touched": 5, "box": 0, "cover": 0}
    assert len(got.unknown) == 0


def _two_plates():
    """A visible 2 in face at (30, 30, 0) in look m0; site 1 lays a 60 in plate 40 in above it (x 0..60: it covers
    the face from straight above), site 2 a 60 in plate 45 in up at x 62..122, off to the side: a viewer up and to
    the right at 45 degrees would see the face through it, but the face's judging viewpoint is the one straight
    above. Both plates are in look m1. AFTER is BEFORE with site 1's two faces, then site 2's, appended. (Job P2-V2: every line of
    sight is asked now, so site 2's plate covers the face too, from that 45 degree viewer.)"""
    face = _two_looks(_moved(grid_slab(1, 1, cell=2.0), [30.0, 30.0, 0.0]))
    plate = _with_material(_two_looks(grid_slab(1, 1, cell=60.0)), [0, 1], 1)
    after = _with_plate(_with_plate(face, _moved(plate, [0.0, 0.0, 40.0])), _moved(plate, [62.0, 0.0, 45.0]))
    return face, after, _looks("m0", "m1")


def test_two_sites_add_plates_and_only_the_one_whose_plate_is_between_the_sample_and_its_viewer_is_charged():
    """K3 review finding 6: the cover candidates count covers from other sites' faces. A site's shadow set is
    deliberately large, so the covered face is a candidate of BOTH sites; attribution charges only the site whose
    new face lies on the line from the sample to the viewpoint that judged it."""
    before, after, looks = _two_plates()
    judge = _judge(before, looks, margin=2.0)
    covering = judge.site_focus(after, [], [2, 3])
    harmless = judge.site_focus(after, [], [4, 5])
    assert {0, 1} <= set(covering.cover.tolist()) and {0, 1} <= set(harmless.cover.tolist()), \
        "the covered face is a cover candidate of both sites (the shadows over-approximate)"
    verdict = judge.check(after, judge.union([covering, harmless]))
    assert verdict.failed and verdict.summary["nothing_deleted"]["covered"] > 0
    got = judge.attribute(verdict, {7: covering, 9: harmless})
    # job P2-V2: covered is asked on every line of sight, and the second plate stands on the line to a viewer up and
    # to the right of the face: it covers the face too, and each site is charged only by its own plate's lines
    assert sorted(got.charged) == [7, 9], got.how
    assert got.how[7]["cover"] == len(got.charged[7]) and got.how[9]["cover"] == len(got.charged[9])
    assert len(got.charged[7]) > len(got.charged[9]) > 0 and len(got.unknown) == 0


def test_a_failure_no_given_site_could_have_caused_is_unknown_and_kept():
    before, after, looks = _two_plates()
    judge = _judge(before, looks, margin=2.0)
    covering = judge.site_focus(after, [], [2, 3])
    harmless = judge.site_focus(after, [], [4, 5])
    calm = judge.site_focus(after, [], [])                  # job P2-V2: both plates cover now; ask of a site that
    verdict = judge.check(after, judge.union([covering, harmless]))     # changed nothing
    got = judge.attribute(verdict, {9: calm})                # neither covering site is among those asked about
    assert got.charged == {} and len(got.unknown) == len(verdict.failing) > 0


def test_a_new_face_lying_on_the_sample_is_between_it_and_its_viewer():
    """An overlay: a new layer ON the face (within the depth tolerance), in another look."""
    slab = _two_looks(grid_slab(2, 2, cell=10.0))
    layer = _with_material(_two_looks(grid_slab(2, 2, cell=10.0)), np.arange(8), 1)
    after = _with_plate(slab, layer)
    judge = _judge(slab, _looks("m0", "m1"), margin=0.0)
    site = judge.site_focus(after, [], np.arange(8, 16))
    verdict = judge.check(after, site.focus())
    assert verdict.failed and verdict.summary["nothing_deleted"]["overlaid"] > 0
    # margin 0 still holds the slab in the site's box (the layer lies on it); shrink the box test away by asking
    # about the cover rule alone: the slab's faces are cover candidates and the layer is between
    got = judge.attribute(verdict, {1: dataclasses.replace(site, near=np.zeros(0, dtype=np.int64))})
    assert sorted(got.charged) == [1] and got.how[1]["cover"] == len(verdict.failing)
