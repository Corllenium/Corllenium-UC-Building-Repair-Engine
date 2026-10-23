import hashlib
import json
from pathlib import Path
import subprocess


def test_blender_reference_matches_every_original_polygon_and_look(tmp_path):
    source = tmp_path / 'raw.obj'
    source.write_text('''mtllib source.mtl
v 5.0 4.0 1.8043478
v 4.0 4.0 1.7173913
v 4.0 3.0 1.7173913
v 5.0 3.0 1.8043479
vt 0 0
vt 1 0
vt 1 1
vt 0 1
usemtl facade
f 1/1 2/2 3/3 4/4
usemtl other
f 1/1 2/2 3/3 4/4
''')
    (tmp_path / 'source.mtl').write_text('newmtl facade\nKd 1 0 0\nnewmtl other\nKd 0 0 1\n')
    output = tmp_path / 'reference.json'
    script = Path(__file__).resolve().parents[2] / 'tools/blender/main_infra_reference.py'
    result = subprocess.run([
        r'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe',
        '--background', '--factory-startup', '--python-exit-code', '13', '--python', str(script),
        '--', '--input', str(source), '--output', str(output),
    ], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.is_file(), 'Blender reference was not produced'
    reference = json.loads(output.read_text())
    assert reference['source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert reference['raw_polygon_count'] == reference['imported_polygon_count'] == 2
    assert reference['triangle_count'] == 4
    assert set(reference['polygons']) == {'11', '13'}
    assert {corner for triangle in reference['polygons']['11'] for corner in triangle} == {0, 1, 2, 3}
    assert reference['unmatched_polygons'] == 0
