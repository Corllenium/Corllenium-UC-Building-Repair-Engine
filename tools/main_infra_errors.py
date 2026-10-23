"""Per-face error sets for a fresh MAIN INFRA preview package, in the dashboard's errors_before.json shape.

Runs the unchanged detector census (`engine.detectors.errors.find_errors`) on the engine-frame mesh and writes
``errors.json`` beside the published ``preview.json``:  {"faces": {kind: [triangle ids]}, "counts": {...},
"n_faces": N, "source_sha256": ...}.  Triangle ids follow the OBJ face order, which the preview model shares.
Kinds: flicker_diff, flicker_same, reversed, hidden, loose, open_edges, cracks (ERROR_KIND_META in the dashboard).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from engine.detectors.errors import find_errors
from engine.io.obj_reader import read_obj

KINDS = ('flicker_diff', 'flicker_same', 'reversed', 'hidden', 'loose', 'open_edges', 'cracks')


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def error_sets(engine_obj):
    mesh = read_obj(Path(engine_obj))
    timings = {}
    report = find_errors(mesh, timings=timings)
    faces = {k: sorted(int(f) for f in report['faces'].get(k, [])) for k in KINDS}
    return {'schema_version': 1, 'n_faces': int(mesh.n_faces), 'engine_obj_sha256': sha256_file(engine_obj),
            'counts': {k: len(v) for k, v in faces.items()}, 'faces': faces,
            'timings_s': {k: round(v, 2) for k, v in timings.items()}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-obj', type=Path, required=True, help='before.engine.obj or candidate.engine.obj')
    parser.add_argument('--out', type=Path, action='append', required=True, help='errors.json destination (repeatable)')
    args = parser.parse_args(argv)
    started = time.perf_counter()
    doc = error_sets(args.engine_obj)
    doc['wall_s'] = round(time.perf_counter() - started, 1)
    text = json.dumps(doc, separators=(',', ':'))
    for out in args.out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding='utf-8')
    print(json.dumps({'engine_obj': str(args.engine_obj), 'n_faces': doc['n_faces'], 'counts': doc['counts'], 'wall_s': doc['wall_s']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
