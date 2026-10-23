"""The crack judgement before E4: cracks grouped by coplanar region, one Choice question per region to the Decider,
rules first (deterministic, provider 'rules'), Jev only as a recorded suggestion, the owner otherwise."""
import dataclasses
import json

import numpy as np
import pytest

from engine.decide.decider import Decider, RuleProvider
from engine.decide.jev import Decision
from engine.decide.providers import AskProvider
from engine.fixes.pipeline import FixProfile
from engine.io.minecraft_floor import parse_floor
from engine.repair.engines import e4_merge
from engine.repair.engines.e4_merge import E4Merge
from engine.repair.types import RepairContext, UnitState
from tools.tests.test_main_infra_e4 import FLATNESS, FLOOR, FRAME


def _mesh(text=FLOOR):
    return parse_floor(text, name='fixture').in_frame(FRAME).mesh


ERRORS = {'faces': {'cracks': [1, 2]}}


def _decider(tmp_path, providers=()):
    from tools.main_infra_crack_judge import CRACK_REGION, QTYPE, crack_rule
    return Decider([CRACK_REGION], [RuleProvider({QTYPE: crack_rule}), *providers],
                   log_path=tmp_path / 'log.jsonl', cache_path=tmp_path / 'cache.jsonl')


def test_rules_say_merge_for_a_flat_panel_whose_area_the_merge_keeps(tmp_path):
    from tools.main_infra_crack_judge import judge_cracks
    mesh = _mesh()
    judgement = judge_cracks(mesh, ERRORS['faces']['cracks'], flatness=FLATNESS, decider=_decider(tmp_path))
    assert judgement['merge'] == [0] and judgement['keep'] == [] and judgement['unsure'] == []
    (row,) = judgement['regions']
    assert row['decision'] == 'merge' and row['provider'] == 'rules' and row['confidence'] == 1.0
    assert row['material'] == 'glass' and row['crack_faces'] == [1, 2] and row['region_faces'] == 4
    assert row['state']['area_preserved'] is True and row['state']['stair_open_edges'] == 0
    assert row['state']['spot']['faces'] == [0, 1, 2, 3] and row['state']['spot']['size'] > 0
    assert judgement['unassigned_faces'] == []
    # E4 restricted to the judgement plans exactly that region
    engine = E4Merge(flatness=FLATNESS, allowed_regions=set(judgement['merge']))
    edits = engine.plan(UnitState(mesh=mesh, topo=None, looks={}, viewpoints=None),
                        RepairContext(profile=FixProfile(), decider=None, validator=None))
    assert [e.evidence['region'] for e in edits] == [0]


def test_rules_say_keep_for_a_region_whose_open_edges_lie_on_a_stair_material(tmp_path):
    from tools.main_infra_crack_judge import judge_cracks
    mesh = _mesh(FLOOR.replace('usemtl glass', 'usemtl stair_tread_glass'))
    judgement = judge_cracks(mesh, [1, 2], flatness={'stair_tread_glass': 50.0}, decider=_decider(tmp_path))
    assert judgement['keep'] == [0] and judgement['merge'] == []
    (row,) = judgement['regions']
    assert row['decision'] == 'keep' and row['provider'] == 'rules'
    assert row['state']['stair_material'] is True and row['state']['stair_open_edges'] == 4


def test_a_region_the_rules_cannot_settle_goes_to_the_owner_with_jevs_answer_as_a_suggestion_only(tmp_path, monkeypatch):
    from tools.main_infra_crack_judge import judge_cracks
    real = e4_merge.merge_regions

    def drop_one(mesh, topo, flat, **kw):
        result = real(mesh, topo, flat, **kw)
        keep = np.arange(result.mesh.n_faces) != 0
        out = dataclasses.replace(result.mesh, face_v=result.mesh.face_v[keep], face_vt=result.mesh.face_vt[keep],
                                  face_vn=result.mesh.face_vn[keep], face_material=result.mesh.face_material[keep],
                                  face_line=result.mesh.face_line[keep])
        return dataclasses.replace(result, mesh=out, source_faces=[s for s, k in zip(result.source_faces, keep) if k],
                                   face_region=result.face_region[keep])

    monkeypatch.setattr(e4_merge, 'merge_regions', drop_one)
    mesh = _mesh()
    # no Jev: the question is queued for the owner
    judgement = judge_cracks(mesh, [1, 2], flatness=FLATNESS, decider=_decider(tmp_path / 'a'))
    (row,) = judgement['regions']
    assert judgement['unsure'] == [0] and row['decision'] == 'unsure' and row['provider'] == 'queue'
    assert row['state']['area_preserved'] is False and row['state']['merge_reason'] == 'area_changed'

    class FakeJev:
        calls = []

        def ask(self, state, questions):
            return {qid: Decision('keep', 0.9, {'keep': 0.9, 'merge': 0.1}, 'jev', True) for qid in questions}

    judgement = judge_cracks(mesh, [1, 2], flatness=FLATNESS,
                             decider=_decider(tmp_path / 'b', [AskProvider('jev', FakeJev())]))
    (row,) = judgement['regions']
    assert row['decision'] == 'unsure' and row['provider'] == 'queue', 'suggest mode: Jev never decides alone'
    assert row['suggestion'] == {'provider': 'jev', 'answer': 'keep', 'confidence': 0.9,
                                 'probabilities': {'keep': 0.9, 'merge': 0.1}}


def test_crack_faces_outside_any_region_are_listed_not_judged(tmp_path):
    from tools.main_infra_crack_judge import judge_cracks
    mesh = _mesh()
    judgement = judge_cracks(mesh, [4, 99], flatness=FLATNESS, decider=_decider(tmp_path))
    assert judgement['regions'] == [] or all(r['crack_faces'] != [99] for r in judgement['regions'])
    assert 99 in judgement['unassigned_faces']


def test_the_cli_writes_the_judgement_from_an_errors_json(tmp_path):
    from engine.io.obj_writer import write_obj
    from tools.main_infra_crack_judge import main
    mesh = _mesh()
    before = tmp_path / 'before.obj'
    write_obj(mesh, before)
    (tmp_path / 'errors.json').write_text(json.dumps(ERRORS))
    (tmp_path / 'flatness.json').write_text(json.dumps(FLATNESS))
    out = tmp_path / 'crack-judgement.json'
    main(['--before', str(before), '--errors', str(tmp_path / 'errors.json'), '--flatness', str(tmp_path / 'flatness.json'),
          '--decide-dir', str(tmp_path / 'decide'), '--out', str(out)])
    judgement = json.loads(out.read_text())
    assert judgement['merge'] == [0] and judgement['regions'][0]['provider'] == 'rules'
    assert judgement['decider'] == {'providers': ['rules'], 'jev': 'off'}
    with pytest.raises(ValueError, match='exists'):
        main(['--before', str(before), '--errors', str(tmp_path / 'errors.json'), '--out', str(out)])
