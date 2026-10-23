"""Independent import qualification derived only from saved artifacts: hashes, render-pair pixels, look keys."""
import hashlib
import json
from pathlib import Path

import pytest

from engine.io.minecraft_floor import Frame
from tools.repair_fresh_main_infra import normalize_reference

CLEAN_RUN = Path(__file__).resolve().parents[3] / 'MAIN-INFRA-CLEAN-20261023/data/main-infra-fresh/run-20261023'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def render_dir(root, name, *, rgb_changes=0, alpha_changes=0, size=8):
    """A fake main_infra_render_pair output: comparison.json plus before/after PNG pairs."""
    from PIL import Image
    out = root / name
    out.mkdir(parents=True)
    views = []
    for view in ('top', 'eye_0'):
        before = Image.new('RGBA', (size, size), (200, 100, 50, 255))
        after = before.copy()
        changed = 0
        if view == 'top':
            for i in range(rgb_changes):
                after.putpixel((i, 0), (10, 100, 50, 255)); changed += 1
            for i in range(alpha_changes):
                after.putpixel((i, 1), (200, 100, 50, 0)); changed += 1
        before.save(out / f'{view}.before.png'); after.save(out / f'{view}.after.png')
        views.append({'name': view, 'different_pixels': changed, 'non_background_pixels': size * size})
    (out / 'comparison.json').write_text(json.dumps({'size': size, 'views': views,
        'all_pixels_identical': all(v['different_pixels'] == 0 for v in views)}))
    return out


def baseline_fixture(tmp_path):
    from tools.tests.test_main_infra_normalize_reference import reference_fixture
    from PIL import Image
    raw, reference = reference_fixture(tmp_path)
    Image.new('RGB', (2, 2), (220, 30, 40)).save(tmp_path / 'red.png')
    text = 'mtllib raw.mtl\n' + raw.read_text() .replace('f 1 2 3 4', 'usemtl wall\nf 1 2 3 4')
    raw.write_text(text)
    (tmp_path / 'raw.mtl').write_text('newmtl wall\nKd 1 1 1\nd 1\nmap_Kd red.png\n')
    doc = json.loads(reference.read_text())
    doc.update(source_sha256=sha(raw), polygons={'7': [[0, 1, 2], [0, 2, 3]]})
    reference.write_text(json.dumps(doc))
    normalize_reference(raw, reference, tmp_path / 'normalized', Frame(1000 / 25.4, 'fixture'))
    return raw, reference, tmp_path / 'normalized'


def test_qualification_binds_saved_hashes_and_counts_rgb_and_alpha_pixels_separately(tmp_path):
    from tools.main_infra_qualify import build_qualification
    raw, reference, baseline = baseline_fixture(tmp_path)
    source_qa = render_dir(tmp_path, 'import-qa')
    frame_qa = render_dir(tmp_path, 'frame-qa', rgb_changes=3)
    doc = build_qualification(floor='7F', source_revision='a' * 64, raw=raw, reference=reference, baseline=baseline,
                              source_qa=source_qa, frame_qa=frame_qa, reviewer='test-reviewer', now='2026-10-23T10:00:00Z')
    assert list(doc) == ['schema_version', 'qualified', 'floor_id', 'source_revision', 'source_obj_sha256', 'engine_obj_sha256',
                         'source_triangles_sha256', 'native_reference_sha256', 'reviewer', 'reviewed_utc', 'audit_ref', 'scope',
                         'frame_rgb_different_pixels', 'frame_alpha_different_pixels', 'guards_or_targets_modified']
    assert doc['qualified'] is True and doc['floor_id'] == '7F' and doc['reviewed_utc'] == '2026-10-23T10:00:00Z'
    assert doc['source_obj_sha256'] == sha(raw) and doc['native_reference_sha256'] == sha(reference)
    assert doc['engine_obj_sha256'] == sha(baseline / 'before.engine.obj')
    assert doc['source_triangles_sha256'] == sha(baseline / 'before.source.obj')
    assert doc['frame_rgb_different_pixels'] == 3 and doc['frame_alpha_different_pixels'] == 0
    assert doc['guards_or_targets_modified'] is False


@pytest.mark.parametrize('kind', ['source_rgb', 'frame_alpha', 'reference_unmatched', 'raw_changed'])
def test_any_source_change_alpha_change_or_unmatched_polygon_refuses_qualification(tmp_path, kind):
    from tools.main_infra_qualify import build_qualification
    raw, reference, baseline = baseline_fixture(tmp_path)
    source_qa = render_dir(tmp_path, 'import-qa', rgb_changes=1 if kind == 'source_rgb' else 0)
    frame_qa = render_dir(tmp_path, 'frame-qa', alpha_changes=1 if kind == 'frame_alpha' else 0)
    if kind == 'reference_unmatched':
        doc = json.loads(reference.read_text()); doc['unmatched_polygons'] = 1; reference.write_text(json.dumps(doc))
    if kind == 'raw_changed':
        raw.write_text(raw.read_text() + '# edited after normalization\n')
    doc = build_qualification(floor='7F', source_revision='a' * 64, raw=raw, reference=reference, baseline=baseline,
                              source_qa=source_qa, frame_qa=frame_qa, reviewer='test-reviewer')
    assert doc['qualified'] is False
    assert doc['refusals'], doc


def test_materials_file_uses_engine_look_keys(tmp_path):
    from tools.main_infra_qualify import write_materials
    raw, reference, baseline = baseline_fixture(tmp_path)
    out = tmp_path / 'materials-7F.json'
    doc = write_materials(baseline, out)
    saved = json.loads(out.read_text())
    assert saved == doc and list(saved) == ['materials', 'looks', 'stats']
    wall = saved['materials']['wall']
    assert wall['map_kd'] == 'red.png' and wall['tex_sha256'] == sha(baseline / 'red.png') and wall['missing_texture'] is False
    assert saved['stats'] == {'materials': 1, 'textured': 1, 'images': 1, 'looks': 1}


@pytest.mark.skipif(not (CLEAN_RUN / 'frame-qa-v2/4F/comparison.json').is_file(), reason="Codex 4F pilot artifacts absent")
def test_reproduces_codex_4f_qualification_and_materials_from_saved_artifacts():
    from tools.main_infra_qualify import build_qualification, write_materials
    expected = json.loads((CLEAN_RUN / 'independent-validator/import-audit/qualification-4F.json').read_text())
    manifest = json.loads((CLEAN_RUN / 'raw-manifest.json').read_text())
    doc = build_qualification(floor='4F', source_revision=manifest['source_revision'],
                              raw=CLEAN_RUN / 'raw/4th floor main infra.obj', reference=CLEAN_RUN / 'reference/4F.json',
                              baseline=CLEAN_RUN / 'normalized/4F', source_qa=CLEAN_RUN / 'import-qa-v2/4F',
                              frame_qa=CLEAN_RUN / 'frame-qa-v2/4F', reviewer=expected['reviewer'], now=expected['reviewed_utc'])
    assert doc == expected
    materials = write_materials(CLEAN_RUN / 'normalized/4F', None)
    assert materials == json.loads((CLEAN_RUN / 'independent-validator/preflight-20261023/materials-4F.json').read_text())
