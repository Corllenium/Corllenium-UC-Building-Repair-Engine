import json
from pathlib import Path

import pytest

from engine.io.minecraft_floor import Frame
from tools.repair_fresh_main_infra import normalize_reference


def fixture(tmp_path):
    from tools.tests.test_main_infra_normalize_reference import reference_fixture
    raw, ref = reference_fixture(tmp_path)
    doc = json.loads(ref.read_text())
    raw.write_text(raw.read_text() + 'f 1 2 3 4\n')
    import hashlib
    doc.update(source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(), raw_polygon_count=2,
               imported_polygon_count=2, triangle_count=4)
    doc['polygons']['6'] = doc['polygons']['5']
    ref.write_text(json.dumps(doc))
    baseline = normalize_reference(raw, ref, tmp_path / 'normalized', Frame(1000 / 25.4, 'fixture'))
    qa = tmp_path / 'qualification.json'
    qa.write_text(json.dumps({'qualified': True, 'engine_obj_sha256': hashlib.sha256(baseline['engine_obj'].read_bytes()).hexdigest(),
                            'source_triangles_sha256': hashlib.sha256(baseline['source_triangles'].read_bytes()).hexdigest()}))
    return baseline['engine_obj'].parent, qa


def test_saved_candidate_preserves_coverage_and_uses_existing_strict_26_view_guard(tmp_path):
    from tools.main_infra_candidate import build_candidate
    baseline, qa = fixture(tmp_path)
    report = build_candidate(baseline, qa, tmp_path / 'candidate')
    assert report['input_triangles'] == 4 and report['output_triangles'] == 2
    assert report['source_coverage']['missing'] == report['source_coverage']['added'] == 0
    assert report['guard']['passed'] and len(report['guard']['views']) == 26
    assert report['accepted'] is False and report['independent_validation'] == 'pending'
    assert len(list(Path(report['before_snapshot']).glob('*.obj'))) == 1
    assert Path(report['engine_candidate']).is_file()
    assert (tmp_path / 'candidate/edit-log.jsonl').is_file()


def test_unqualified_or_mismatched_baseline_cannot_start_cleanup(tmp_path):
    from tools.main_infra_candidate import build_candidate
    baseline, qa = fixture(tmp_path)
    doc = json.loads(qa.read_text())
    doc['engine_obj_sha256'] = '0' * 64
    qa.write_text(json.dumps(doc))
    out = tmp_path / 'candidate'
    with pytest.raises(ValueError, match='qualification|hash'):
        build_candidate(baseline, qa, out)
    assert not out.exists()


def test_failed_coverage_leaves_baseline_and_no_candidate(tmp_path, monkeypatch):
    import tools.main_infra_candidate as candidate
    baseline, qa = fixture(tmp_path)
    old = (baseline / 'before.engine.obj').read_bytes()
    def reject(*args):
        raise ValueError('coverage rejection')
    monkeypatch.setattr(candidate, 'verify_exact_coverage', reject)
    with pytest.raises(ValueError, match='coverage rejection'):
        candidate.build_candidate(baseline, qa, tmp_path / 'candidate')
    assert (baseline / 'before.engine.obj').read_bytes() == old
    assert not (tmp_path / 'candidate').exists()


def test_original_oracle_factory_runs_the_same_strict_guard_and_saves_its_identity(tmp_path):
    from engine.rays.bounded_brute import BoundedBruteCaster
    from tools.main_infra_candidate import build_candidate
    baseline, qa = fixture(tmp_path)
    report = build_candidate(baseline, qa, tmp_path / 'candidate', caster_factory=BoundedBruteCaster)
    assert report['ray_caster'] == 'BoundedBruteCaster'
    assert report['guard']['passed'] and len(report['guard']['views']) == 26
    assert report['accepted'] is False and report['output_triangles'] == 2
