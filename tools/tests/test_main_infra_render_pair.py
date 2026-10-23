import json
from pathlib import Path
import subprocess


def test_render_pair_reads_saved_textures_and_detects_changed_appearance(tmp_path):
    from PIL import Image
    Image.new('RGB', (2, 2), (220, 30, 40)).save(tmp_path / 'red.png')
    obj = 'mtllib red.mtl\nv 0 0 0\nv 2 0 0\nv 2 2 0\nv 0 2 0\nvt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nusemtl wall\nf 1/1 2/2 3/3 4/4\n'
    (tmp_path / 'raw.obj').write_text(obj)
    (tmp_path / 'tri.obj').write_text(obj.replace('f 1/1 2/2 3/3 4/4', 'f 1/1 2/2 3/3\nf 1/1 3/3 4/4'))
    (tmp_path / 'red.mtl').write_text('newmtl wall\nKd 1 1 1\nmap_Kd red.png\n')
    (tmp_path / 'bad.mtl').write_text('newmtl wall\nKd 0 0 1\n')
    (tmp_path / 'bad.obj').write_text(obj.replace('red.mtl', 'bad.mtl'))
    script = Path(__file__).resolve().parents[2] / 'tools/blender/main_infra_render_pair.py'
    for other, expected in [('tri', True), ('bad', False)]:
        out = tmp_path / other
        result = subprocess.run([r'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe',
            '--background', '--factory-startup', '--python-exit-code', '13', '--python', str(script), '--',
            '--before', 'raw.obj', '--after', f'{other}.obj',
            '--out', other, '--before-frame', 'engine-metres', '--after-frame', 'engine-metres',
            '--views', 'top', '--size', '128'], cwd=tmp_path, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout[-2500:] + result.stderr[-2500:]
        report = json.loads((out / 'comparison.json').read_text())
        assert report['all_pixels_identical'] is expected
        assert (out / 'top.before.png').is_file()
        assert (out / 'top.after.png').is_file()
        assert (out / 'top.diff.png').is_file()
        assert report['views'][0]['non_background_pixels'] > 0
        pixel = Image.open(out / 'top.before.png').convert('RGB').getpixel((64, 64))
        assert pixel[0] > pixel[1] * 3 and pixel[0] > pixel[2] * 3
