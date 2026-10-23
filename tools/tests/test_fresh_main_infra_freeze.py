import json
from pathlib import Path

import pytest

from tools.repair_fresh_main_infra import freeze_source


def source_package(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / '1st floor main infra.obj').write_text('mtllib floor.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    (source / 'floor.mtl').write_text('newmtl brick\nmap_Kd textures/brick.png\n')
    (source / 'textures').mkdir()
    (source / 'textures/brick.png').write_bytes(b'original texture bytes')
    return source


def test_freeze_preserves_every_asset_byte_and_source_hierarchy(tmp_path):
    source = source_package(tmp_path)
    run = tmp_path / 'run'
    manifest = freeze_source(source, run, interval_s=0)
    assert len(manifest['files']) == 3
    assert len(manifest['source_revision']) == 64
    for row in manifest['files']:
        assert (run / 'raw' / row['path']).read_bytes() == (source / row['path']).read_bytes()
    assert json.loads((run / 'raw-manifest.json').read_text()) == manifest


def test_source_change_never_overwrites_a_previous_frozen_package(tmp_path):
    source = source_package(tmp_path)
    run = tmp_path / 'run'
    first = freeze_source(source, run, interval_s=0)
    original = (run / 'raw/1st floor main infra.obj').read_bytes()
    (source / '1st floor main infra.obj').write_text('changed source')
    with pytest.raises(ValueError, match='source|frozen|changed'):
        freeze_source(source, run, interval_s=0)
    assert (run / 'raw/1st floor main infra.obj').read_bytes() == original
    assert json.loads((run / 'raw-manifest.json').read_text()) == first


def test_freeze_refuses_destination_inside_the_live_source(tmp_path):
    source = source_package(tmp_path)
    with pytest.raises(ValueError):
        freeze_source(source, source / 'run', interval_s=0)
