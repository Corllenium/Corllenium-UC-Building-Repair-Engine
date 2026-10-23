import hashlib
import json

import numpy as np
import pytest

from engine.io.minecraft_floor import Frame, parse_floor
from tools.repair_fresh_main_infra import normalize_reference


def reference_fixture(tmp_path, *, missing_material=False):
    source = tmp_path / 'raw.obj'
    text = 'v 0 0 0\nv 1 0 0\nv 1 1 0.000001\nv 0 1 0\nf 1 2 3 4\n'
    if missing_material:
        text = 'mtllib missing.mtl\n' + text
    source.write_text(text)
    line = 6 if missing_material else 5
    reference = tmp_path / 'reference.json'
    reference.write_text(json.dumps({'schema_version': 1,
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'blender_version': '5.1.2', 'raw_polygon_count': 1, 'imported_polygon_count': 1,
        'triangle_count': 2, 'unmatched_polygons': 0,
        'polygons': {str(line): [[0, 1, 2], [0, 2, 3]]}}))
    return source, reference


def test_normalization_preserves_display_corners_and_explicit_engine_frame(tmp_path):
    source, reference = reference_fixture(tmp_path)
    result = normalize_reference(source, reference, tmp_path / 'normalized', Frame(1000 / 25.4, 'owner metre/block; Y-up fixture'))
    display = parse_floor(result['source_triangles'].read_text())
    engine = parse_floor(result['engine_obj'].read_text())
    np.testing.assert_array_equal(display.mesh.positions, [[0, 0, 0], [1, 0, 0], [1, 1, .000001], [0, 1, 0]])
    assert engine.mesh.positions[1, 0] == pytest.approx(39.37007874015748)
    assert engine.mesh.positions[2, 2] == pytest.approx(39.37007874015748)
    assert len(display.mesh.positions) == 4
    assert display.mesh.n_faces == engine.mesh.n_faces == 2
    saved = json.loads(result['provenance'].read_text())
    assert saved['source_polygon_count'] == 1
    assert saved['source_corner_positions_changed'] == 0
    assert saved['units'] == 'inches'


def test_reference_from_different_source_cannot_normalize_a_floor(tmp_path):
    source, reference = reference_fixture(tmp_path)
    doc = json.loads(reference.read_text())
    doc['source_sha256'] = '0' * 64
    reference.write_text(json.dumps(doc))
    output = tmp_path / 'normalized'
    with pytest.raises(ValueError, match='source|hash'):
        normalize_reference(source, reference, output, Frame(1, 'fixture'))
    assert not output.exists()


def test_missing_material_dependency_blocks_normalization(tmp_path):
    source, reference = reference_fixture(tmp_path, missing_material=True)
    output = tmp_path / 'normalized'
    with pytest.raises((ValueError, FileNotFoundError)):
        normalize_reference(source, reference, output, Frame(1, 'fixture'))
    assert not output.exists()
