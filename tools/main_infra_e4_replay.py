"""Map the Validator's failing floor faces to the E4 regions responsible, for the owner's flag -> site -> replay loop.

Usage:
  python tools/main_infra_e4_replay.py --candidate <e4 dir> --validation <validation.json> [--interior <renders dir>] --out <json>

For each failing floor face of check 3 (`checks.nothing_deleted.floor.failing`, kinds `covered` and `removed`; the face
ids are the BASELINE's, the Validator's BEFORE) the regions responsible are:
- the region whose NEW triangles include a `covering_faces` entry (AFTER face ids; `how: covering_face`);
- for `removed`, the region whose source faces (mapped to baseline ids by the binding: the receipt's
  `e4_region_source_faces`, carried in `validation.json` as `physical_precision`) contain the face (`how: source_face`);
- every region whose NEW triangles lie within the depth tolerance of the failing face's plane and whose footprint
  overlaps the failing face in that plane (shapely; `how: coplanar_overlap`).
The baseline snapshot (`physical_precision.before`) gives the failing faces' geometry; the chain never moves a vertex,
so its positions must equal the candidate's. Output: `{regions: [ids], reasons: {region: [{face, kind, pixels,
viewpoint, how, site}]}, unexplained: [...]}` -- `regions` are `e4_topology` region ids, what `run_checked_e4_floor.py
--exclude-regions` takes. A failure no region explains is listed under `unexplained` and the command returns 2: the loop
must stop there, it has nothing to exclude for it.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import shapely

from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file
from engine.topo.planes import plane_basis

#: Footprint overlap (sq in, in the failing face's plane) below which a coplanar region does not count.
MIN_OVERLAP = 1e-6


def _interior(interior):
    if interior is None:
        return None
    interior = Path(interior)
    comparison = interior / 'comparison.json'
    if not comparison.exists():
        return {'renders': str(interior), 'comparison': None}
    return {'renders': str(interior), 'comparison': json.loads(comparison.read_text(encoding='utf-8'))}


def explain_failures(*, candidate, validation, interior=None) -> dict:
    candidate, validation = Path(candidate), Path(validation)
    report = json.loads(validation.read_text(encoding='utf-8'))
    mapping = json.loads((candidate / 'region-map.json').read_text(encoding='utf-8'))
    after = read_obj(candidate / 'candidate.engine.obj')
    receipt = report.get('physical_precision') or {}
    before_path = receipt.get('before')
    if not before_path:
        raise ValueError('validation.json carries no physical_precision.before: the baseline snapshot is needed')
    before = read_obj(Path(before_path))
    if not np.array_equal(before.positions, after.positions):
        raise ValueError('candidate positions differ from the baseline snapshot: the chain never moves a vertex')
    region_sources = receipt.get('e4_region_source_faces')
    regions = mapping['regions']
    if not isinstance(region_sources, list) or len(region_sources) != len(regions):
        raise ValueError("the receipt's e4_region_source_faces do not match the region map")
    tol = report.get('depth_tolerance_in')
    if tol is None:
        tol = report['checks']['nothing_deleted'].get('depth_tolerance_in')
    tol = float(tol)
    failing = report['checks']['nothing_deleted'].get('floor', {}).get('failing', [])

    by_new_face = {int(t): k for k, r in enumerate(regions) for t in r['new_triangles']}
    by_source = {int(f): k for k, faces in enumerate(region_sources) for f in faces}
    tri_after = after.positions[after.face_v]
    reasons: dict[int, list] = {}
    unexplained = []
    for entry in failing:
        f, kind = int(entry['face']), entry.get('kind')
        row = {'face': f, 'kind': kind, 'pixels': entry.get('pixels'), 'viewpoint': entry.get('viewpoint'),
               'reasons': entry.get('reasons')}
        hits: dict[int, str] = {}
        for c in entry.get('covering_faces') or []:
            if int(c) in by_new_face:
                hits.setdefault(by_new_face[int(c)], 'covering_face')
        if kind == 'removed' and f in by_source:
            hits.setdefault(by_source[f], 'source_face')
        t = before.positions[before.face_v[f]]
        n = np.cross(t[1] - t[0], t[2] - t[0])
        length = float(np.linalg.norm(n))
        if length > 0:
            n = n / length
            e1, e2 = plane_basis(n)
            basis = np.stack([e1, e2], axis=1)
            centre = t.mean(axis=0)
            poly_f = shapely.Polygon((t - centre) @ basis)
            for k, r in enumerate(regions):
                if k in hits:
                    continue
                new = tri_after[np.asarray(r['new_triangles'], np.int64)]
                if not (np.abs((new.reshape(-1, 3) - centre) @ n) <= tol).all():
                    continue
                union = shapely.unary_union([shapely.Polygon((tr - centre) @ basis) for tr in new])
                if shapely.intersection(poly_f, union).area > MIN_OVERLAP:
                    hits[k] = 'coplanar_overlap'
        if not hits:
            unexplained.append(row)
            continue
        for k, how in hits.items():
            reasons.setdefault(int(regions[k]['region']), []).append({**row, 'how': how, 'site': int(regions[k]['site'])})
    return dict(schema_version=1, candidate=str(candidate), validation=str(validation),
                validation_sha256=sha256_file(validation), region_map_sha256=sha256_file(candidate / 'region-map.json'),
                depth_tolerance_in=tol, failing=len(failing), regions=sorted(reasons),
                reasons={str(r): rows for r, rows in sorted(reasons.items())}, unexplained=unexplained,
                interior=_interior(interior))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--validation', type=Path, required=True)
    parser.add_argument('--interior', type=Path, default=None)
    parser.add_argument('--out', type=Path, required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    got = explain_failures(candidate=args.candidate, validation=args.validation, interior=args.interior)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(got, indent=2), encoding='utf-8')
    print(json.dumps(dict(regions=got['regions'], failing=got['failing'], unexplained=len(got['unexplained']),
                          out=str(args.out))), flush=True)
    return 0 if not got['unexplained'] else 2


if __name__ == '__main__':
    sys.exit(main())
