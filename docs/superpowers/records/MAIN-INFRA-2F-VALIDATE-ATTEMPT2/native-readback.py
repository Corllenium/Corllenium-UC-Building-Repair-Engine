"""Read saved QA PNG pairs back and summarize them for human inspection."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def summarize(root):
    rows = []
    for path in sorted(root.glob('*.before.png')):
        name = path.name.removesuffix('.before.png')
        before = np.asarray(Image.open(path).convert('RGBA'))
        after = np.asarray(Image.open(root / f'{name}.after.png').convert('RGBA'))
        rows.append({'name': name, 'different_pixels': int(np.any(before != after, axis=2).sum()),
                     'max_byte_delta': int(np.abs(before.astype(int) - after.astype(int)).max())})
    if not rows:
        raise ValueError('No QA pairs')
    sheet = Image.new('RGB', (6 * 200, ((len(rows) + 5) // 6) * 224), '#252b33')
    draw = ImageDraw.Draw(sheet)
    for i, row in enumerate(rows):
        photo = Image.open(root / f'{row["name"]}.before.png').convert('RGBA')
        photo.thumbnail((200, 200))
        x, y = (i % 6) * 200, (i // 6) * 224
        sheet.paste(photo, (x, y + 24), photo)
        draw.text((x + 3, y + 3), row['name'], fill='white')
    sheet.save(root / 'all-views.png')
    selected = [r for r in rows if r['name'] in ['view_1_1_1', 'view_0_0_1', 'view_1_0_0', 'eye_0']]
    detail = Image.new('RGB', (3 * 384, len(selected) * 408), '#252b33')
    draw = ImageDraw.Draw(detail)
    for i, row in enumerate(selected):
        for j, label in enumerate(['before', 'after', 'diff']):
            photo = Image.open(root / f'{row["name"]}.{label}.png').convert('RGBA')
            photo.thumbnail((384, 384))
            detail.paste(photo, (j * 384, i * 408 + 24), photo)
            draw.text((j * 384 + 3, i * 408 + 3), f'{row["name"]}: {label}', fill='white')
    if selected:
        detail.save(root / 'paired-detail.png')
    report = {'png_pairs_readback': len(rows), 'all_bytes_identical': all(r['different_pixels'] == 0 for r in rows), 'views': rows}
    (root / 'png-readback.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'root': str(root), 'png_pairs': len(rows), 'identical': report['all_bytes_identical'],
                      'different_pixels': sum(r['different_pixels'] for r in rows)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roots', nargs='+', type=Path)
    for root in parser.parse_args().roots:
        summarize(root)
