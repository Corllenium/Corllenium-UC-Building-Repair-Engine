import json
from pathlib import Path
from shutil import copyfile

import numpy as np
import pytest

from engine.io.minecraft_floor import Frame
from engine.io.snapshot import sha256_file, snapshot_object
from engine.pipeline import analyse_topology
from tools.repair_fresh_main_infra import normalize_reference


def fixture(tmp_path):
    raw = tmp_path / 'source.obj'
    raw.write_text('mtllib source.mtl\nusemtl wall\nv 0 0 10\nv 1 0 10\nv 0 1 10\nv 1 1 10.0000001\nf 1 2 3\nf 2 4 3\n')
    (tmp_path / 'source.mtl').write_text('newmtl wall\nKd 1 1 1\nmap_Kd wall.png\n')
    from PIL import Image
    Image.new('RGB', (2, 2), (20, 80, 30)).save(tmp_path / 'wall.png')
    reference = tmp_path / 'reference.json'
    reference.write_text(json.dumps(dict(schema_version=1, source_sha256=sha256_file(raw),
        unmatched_polygons=0, blender_version='fixture', raw_polygon_count=2,
        imported_polygon_count=2, triangle_count=2, polygons={'7': [[0, 1, 2]], '8': [[0, 1, 2]]})))
    base = tmp_path / 'baseline'
    normalize_reference(raw, reference, base, Frame(1000 / 25.4, 'owner: 1 block = 1 metre; Y-up'))
    qualification = tmp_path / 'qualification.json'
    qualification.write_text(json.dumps(dict(qualified=True, floor_id='4F', source_revision='a' * 64,
        source_obj_sha256=sha256_file(raw), native_reference_sha256=sha256_file(reference),
        engine_obj_sha256=sha256_file(base / 'before.engine.obj'),
        source_triangles_sha256=sha256_file(base / 'before.source.obj'))))
    candidate = tmp_path / 'candidate'
    candidate.mkdir()
    snapshot = snapshot_object(base / 'before.engine.obj', candidate / 'snapshots', interval_s=0).dir
    copyfile(base / 'before.engine.obj', candidate / 'candidate.engine.obj')
    copyfile(base / 'before.source.obj', candidate / 'candidate.source.obj')
    assets = json.loads((base / 'geometry-provenance.json').read_text())['assets']
    for row in assets:
        copyfile(base / row['path'], candidate / row['path'])
    (candidate / 'stage-audit.json').write_text(json.dumps(dict(before_snapshot=str(snapshot),
        qualification_sha256=sha256_file(qualification), guard={'passed': True},
        engine_candidate_sha256=sha256_file(candidate / 'candidate.engine.obj'),
        source_candidate_sha256=sha256_file(candidate / 'candidate.source.obj'), assets=assets)))
    return dict(raw=raw, reference=reference, baseline=base, qualification=qualification, candidate=candidate)


def test_bound_saved_obj_uses_original_precision_for_both_topologies(tmp_path):
    from tools import main_infra_physical_validation as module
    inputs = fixture(tmp_path)
    before, after, receipt = module.load_physical_pair(**inputs)
    for mesh in (before, after):
        topo = analyse_topology(mesh)
        assert topo.face_region[0] == topo.face_region[1]
        np.testing.assert_allclose(topo.quanta, [3.937007874015748e-8, 3.937007874015748e-6,
                                               3.937007874015748e-8], rtol=1e-14)
    assert receipt['source_sig_digits'] == 9
    assert receipt['source_obj_sha256'] == sha256_file(inputs['raw'])
    assert receipt['before_sha256'] == sha256_file(Path(receipt['before']))


@pytest.mark.parametrize('changed', ['raw', 'reference', 'qualification', 'before', 'after', 'source_candidate'])
def test_precision_binding_refuses_changed_evidence_or_mesh(tmp_path, changed):
    from tools import main_infra_physical_validation as module
    inputs = fixture(tmp_path)
    audit = json.loads((inputs['candidate'] / 'stage-audit.json').read_text())
    paths = {**inputs, 'before': next(Path(audit['before_snapshot']).glob('*.obj')),
             'after': inputs['candidate'] / 'candidate.engine.obj',
             'source_candidate': inputs['candidate'] / 'candidate.source.obj'}
    path = paths[changed]
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='hash|qualification|Reference'):
        module.load_physical_pair(**inputs)


@pytest.mark.parametrize('changed', ['raw_mtl', 'raw_png', 'baseline_png', 'candidate_mtl',
                                    'candidate_png', 'snapshot_mtl', 'snapshot_png'])
def test_physical_binding_refuses_changed_material_or_texture(tmp_path, changed):
    from tools import main_infra_physical_validation as module
    inputs = fixture(tmp_path)
    audit = json.loads((inputs['candidate'] / 'stage-audit.json').read_text())
    snapshot = Path(audit['before_snapshot'])
    path = {'raw_mtl': tmp_path / 'source.mtl', 'raw_png': tmp_path / 'wall.png',
            'baseline_png': inputs['baseline'] / 'wall.png',
            'candidate_mtl': inputs['candidate'] / 'source.mtl',
            'candidate_png': inputs['candidate'] / 'wall.png',
            'snapshot_mtl': snapshot / 'materials.mtl', 'snapshot_png': snapshot / 'tex/wall.png'}[changed]
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='hash|material|asset'):
        module.load_physical_pair(**inputs)


def test_real_validation_writes_bound_report_and_preserves_default_density(tmp_path):
    from tools.main_infra_physical_validation import main
    inputs = fixture(tmp_path)
    materials = tmp_path / 'looks.json'
    materials.write_text(json.dumps({'materials': {'wall': {'look': 'wall', 'kd': [1, 1, 1],
                                                           'map_kd': 'wall.png'}}}))
    out = tmp_path / 'validation'
    argv = [part for key, value in {**inputs, 'materials': materials, 'out': out}.items()
            for part in ('--' + key, str(value))]
    code = main(argv)
    report = json.loads((out / 'validation.json').read_text())
    assert report['checks']['textures']['status'] == 'PASS'
    assert report['checks']['nothing_deleted']['status'] == 'PASS'
    assert report['checks']['problems']['signed'] is True
    assert report['settings']['min_per_face'] == 4
    assert report['settings']['area_per_sample'] == 36
    assert report['settings']['eye'] == 63
    assert report['physical_precision']['source_sig_digits'] == 9
    assert report['inputs']['materials_sha256'] == sha256_file(materials)
    assert code in (0, 2)
    assert (code == 0) == (report['verdict'] == 'PASS')
    with pytest.raises(ValueError, match='already exists'):
        main(argv)
