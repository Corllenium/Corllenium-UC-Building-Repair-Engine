"""Archiving a guard-passed candidate into 04 and 03 copies bytes verbatim, records the measured verdict, refuses failed gates."""
import hashlib
import json
from pathlib import Path

import pytest


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture(tmp_path, *, guard=True, textures='PASS'):
    root = tmp_path / 'run'
    (root / 'independent-validator' / 'import-audit').mkdir(parents=True)
    (root / 'raw-manifest.json').write_text(json.dumps({'source_revision': 'a' * 64, 'files': []}))
    (root / 'independent-validator' / 'import-audit' / 'qualification-7F.json').write_text(json.dumps({'qualified': True, 'source_obj_sha256': 'b' * 64}))
    cand = root / 'candidates' / '7F'
    (cand / 'textures').mkdir(parents=True)
    (cand / 'candidate.source.obj').write_text('mtllib floor.mtl\nv 0 0 0\nv 1 0 0\nv 1 1 0\nf 1 2 3\n')
    (cand / 'candidate.engine.obj').write_text('mtllib floor.mtl\nv 0 0 0\nv 39.37 0 0\nv 39.37 0 39.37\nf 1 2 3\n')
    (cand / 'floor.mtl').write_text('newmtl wall\nmap_Kd textures/wall.png\n')
    (cand / 'textures' / 'wall.png').write_bytes(b'\x89PNG fake')
    (cand / 'edit-log.jsonl').write_text('')
    audit = {'guard': {'passed': guard, 'totals': {'holes': 0}}, 'input_triangles': 4, 'output_triangles': 2,
             'engine_candidate_sha256': sha(cand / 'candidate.engine.obj'), 'source_candidate_sha256': sha(cand / 'candidate.source.obj'),
             'qualification_sha256': 'c' * 64}
    (cand / 'stage-audit.json').write_text(json.dumps(audit))
    val = root / 'independent-validator' / 'physical-precision' / '7F'
    val.mkdir(parents=True)
    (val / 'validation.json').write_text(json.dumps({'verdict': 'FAIL', 'inputs': {'after_sha256': audit['engine_candidate_sha256']},
        'checks': {'textures': {'status': textures}, 'nothing_deleted': {'status': 'PASS'},
                   'problems': {'status': 'FAIL', 'signed': True, 'kinds': {'cracks': {'before': 9, 'after': 5, 'target': 0, 'status': 'FAIL'}}}}}))
    return root, cand, val


def test_archive_writes_04_record_export_and_03_copy_with_verified_hashes(tmp_path):
    from tools.archive_upper_floor import archive_floor
    root, cand, val = fixture(tmp_path)
    repo04, repo03 = tmp_path / '04', tmp_path / '03'
    result = archive_floor(root=root, floor='7F', candidate=cand, validation_dir=val, repo04=repo04, repo03=repo03,
                           job_id='JOB', run_id='run', now='2026-10-23T11:00:00Z')
    export = repo04 / 'Exports/Repaired-Buildings-20261023-fresh/ByBuilding/Main-Infrastructure/Model-Floor_07'
    assert sha(export / 'Main_Infrustructure_7th_floor.fixed.obj') == sha(cand / 'candidate.engine.obj')
    assert sha(export / 'Main_Infrustructure_7th_floor.fixed.source.obj') == sha(cand / 'candidate.source.obj')
    assert (export / 'textures' / 'wall.png').read_bytes() == b'\x89PNG fake' and (export / 'floor.mtl').is_file()
    report = json.loads((export / 'report.json').read_text())
    assert report['status'] == 'candidate_not_accepted' and report['removed_triangles'] == 2 and report['validator']['verdict'] == 'FAIL'
    assert report['validator']['kinds']['cracks']['after'] == 5
    manifest = json.loads((repo04 / 'Exports/Repaired-Buildings-20261023-fresh/MANIFEST.json').read_text())
    assert manifest['floors']['7F']['files']['Main_Infrustructure_7th_floor.fixed.obj'] == sha(cand / 'candidate.engine.obj')
    record = json.loads((repo04 / '03_REPAIR_RECORDS/MAIN_INFRA_MINECRAFT_20261023/upper-floors/7F/SOURCE_REPAIR_RECORD.json').read_text())
    assert record['acceptance'] == 'open' and record['source_revision'] == 'a' * 64 and 'validation.json' in record['evidence']
    game = repo03 / 'Assets/Models/Campus/Repaired/Main-Infrastructure/Floor/Model-Floor_07'
    assert sha(game / 'Main_Infrustructure_7th_floor.fixed.obj') == sha(cand / 'candidate.source.obj')
    assert (game / 'textures' / 'wall.png').is_file() and (game / 'floor.mtl').is_file()
    receipt = json.loads((game / 'RECEIPT.json').read_text())
    assert receipt['status'] == 'candidate_not_accepted' and '/Floor/' in receipt['frame']
    assert result['validator'] == 'FAIL' and result['removed'] == 2


@pytest.mark.parametrize('kind', ['guard', 'textures'])
def test_failed_guard_or_textures_archives_nothing(tmp_path, kind):
    from tools.archive_upper_floor import archive_floor
    root, cand, val = fixture(tmp_path, guard=kind != 'guard', textures='FAIL' if kind == 'textures' else 'PASS')
    with pytest.raises(ValueError):
        archive_floor(root=root, floor='7F', candidate=cand, validation_dir=val, repo04=tmp_path / '04', repo03=tmp_path / '03',
                      job_id='JOB', run_id='run')
    assert not (tmp_path / '04').exists() and not (tmp_path / '03').exists()
