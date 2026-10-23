import hashlib
import json

import pytest


def baseline(tmp_path):
    root = tmp_path / 'baseline'
    root.mkdir()
    (root / 'before.source.obj').write_text('mtllib floor.mtl\nv 0 0 0\nv 2 0 0\nv 0 1 3\nusemtl wall\nf 1 2 3\n')
    (root / 'before.engine.obj').write_text('fixture engine input')
    (root / 'floor.mtl').write_text('newmtl wall\nKd 1 1 1\nmap_Kd textures/wall.png\n')
    (root / 'textures').mkdir()
    (root / 'textures/wall.png').write_bytes(b'fixture texture bytes')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assets = [{'path': name, 'sha256': sha(root / name)} for name in ['floor.mtl', 'textures/wall.png']]
    (root / 'geometry-provenance.json').write_text(json.dumps({'assets': assets, 'source_bounds': [[0, 0, 0], [2, 1, 3]]}))
    proof = tmp_path / 'qualification.json'
    proof.write_text(json.dumps({'qualified': True, 'floor_id': '7F', 'source_revision': 'a' * 64, 'source_triangles_sha256': sha(root / 'before.source.obj'),
                                 'engine_obj_sha256': sha(root / 'before.engine.obj')}))
    return root, proof


def test_packages_all_assets_with_explicit_frame_and_immutable_identity(tmp_path):
    from tools.main_infra_preview import package_preview
    root, proof = baseline(tmp_path)
    args = dict(baseline=root, qualification=proof, public=tmp_path / 'public', revision='a' * 64, run_id='run-1', floor='7F')
    result = package_preview(**args)
    manifest = json.loads(result['manifest_path'].read_text())
    assert manifest['kind'] == 'source'
    assert manifest['display_frame'] == {'up_axis': 'Y', 'units': 'metres', 'source_local': True}
    assert manifest['floor_id'] == 'MAIN_INFRA_7F'
    assert len(manifest['assets']) == 3
    assert all(asset['url'].startswith(result['base_url']) for asset in manifest['assets'])
    assert package_preview(**args)['manifest_path'] == result['manifest_path']
    (result['manifest_path'].parent / 'textures/wall.png').write_bytes(b'changed')
    with pytest.raises(ValueError, match='immutable|hash'):
        package_preview(**args)


def test_unaccepted_package_cannot_be_published_as_accepted(tmp_path):
    from tools.main_infra_preview import package_preview
    root, proof = baseline(tmp_path)
    with pytest.raises(ValueError, match='accepted|workflow'):
        package_preview(baseline=root, qualification=proof, public=tmp_path / 'public', revision='a' * 64,
                        run_id='run-1', floor='1F', kind='accepted')
    assert not (tmp_path / 'public').exists()


def test_bad_source_proof_or_traversal_never_creates_preview(tmp_path):
    from tools.main_infra_preview import package_preview
    root, proof = baseline(tmp_path)
    for run in ['../escape', 'run-1']:
        if run == 'run-1':
            (root / 'before.source.obj').write_text('changed source')
        with pytest.raises(ValueError):
            package_preview(baseline=root, qualification=proof, public=tmp_path / 'public', revision='a' * 64,
                            run_id=run, floor='7F')
    assert not (tmp_path / 'public').exists()


def test_preview_cannot_relabel_another_floor_or_revision(tmp_path):
    from tools.main_infra_preview import package_preview
    root, proof = baseline(tmp_path)
    for floor, revision in [('1F', 'a' * 64), ('7F', 'b' * 64)]:
        with pytest.raises(ValueError, match='identity'):
            package_preview(baseline=root, qualification=proof, public=tmp_path / 'public', revision=revision,
                            run_id='run-1', floor=floor)
    assert not (tmp_path / 'public').exists()


def test_candidate_must_bind_the_supplied_qualification(tmp_path):
    from tools.main_infra_preview import package_preview
    from engine.io.snapshot import sha256_file
    root, proof = baseline(tmp_path)
    (root / 'candidate.source.obj').write_bytes((root / 'before.source.obj').read_bytes())
    (root / 'stage-audit.json').write_text(json.dumps({'guard': {'passed': True},
        'source_coverage': {'exact_coverage': True}, 'source_candidate_sha256': sha256_file(root / 'candidate.source.obj'),
        'qualification_sha256': 'b' * 64}))
    with pytest.raises(ValueError, match='qualification'):
        package_preview(baseline=root, qualification=proof, public=tmp_path / 'public', revision='a' * 64,
                        run_id='run-1', floor='7F', kind='candidate', candidate=root)
    assert not (tmp_path / 'public').exists()
