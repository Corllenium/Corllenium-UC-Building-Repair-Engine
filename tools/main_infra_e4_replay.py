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
    tri_before = before.positions[before.face_v]
    e5 = _e5_chain(candidate, before.n_faces)
    reasons: dict[int, list] = {}
    e5_reasons: dict[int, list] = {}
    unexplained = []
    for entry in failing:
        f, kind = int(entry['face']), entry.get('kind')
        row = {'face': f, 'kind': kind, 'pixels': entry.get('pixels'), 'viewpoint': entry.get('viewpoint'),
               'reasons': entry.get('reasons')}
        t = tri_before[f]
        n = np.cross(t[1] - t[0], t[2] - t[0])
        length = float(np.linalg.norm(n))
        n = n / length if length > 0 else None
        basis = centre = poly_f = None
        if n is not None:
            e1, e2 = plane_basis(n)
            basis = np.stack([e1, e2], axis=1)
            centre = t.mean(axis=0)
            poly_f = shapely.Polygon((t - centre) @ basis)
        # E5 first: a face E5 removed names its site; a face E3 removed names the E5 site(s) whose removed faces lay
        # on it (they were its cover)
        e5_hits: dict[int, str] = {}
        if e5 is not None:
            if f in e5['site_of']:
                e5_hits[e5['site_of'][f]] = 'e5_removed'
            elif f in e5['removed_by_e3'] and n is not None:
                for site, faces in e5['faces_of'].items():
                    tris = tri_before[np.asarray(faces, np.int64)]
                    coplanar = np.abs((tris - centre) @ n).max(axis=1) <= tol
                    if not coplanar.any():
                        continue
                    union = shapely.unary_union([shapely.Polygon((tr - centre) @ basis) for tr in tris[coplanar]])
                    if shapely.intersection(poly_f, union).area > MIN_OVERLAP:
                        e5_hits[site] = 'e5_removed_its_cover'
        hits: dict[int, str] = {}
        for c in entry.get('covering_faces') or []:
            if int(c) in by_new_face:
                hits.setdefault(by_new_face[int(c)], 'covering_face')
        if kind == 'removed' and f in by_source:
            hits.setdefault(by_source[f], 'source_face')
        if n is not None and not e5_hits:
            for k, r in enumerate(regions):
                if k in hits:
                    continue
                new = tri_after[np.asarray(r['new_triangles'], np.int64)]
                if not (np.abs((new.reshape(-1, 3) - centre) @ n) <= tol).all():
                    continue
                union = shapely.unary_union([shapely.Polygon((tr - centre) @ basis) for tr in new])
                if shapely.intersection(poly_f, union).area > MIN_OVERLAP:
                    hits[k] = 'coplanar_overlap'
        if not hits and not e5_hits:
            unexplained.append(row)
            continue
        for k, how in hits.items():
            reasons.setdefault(int(regions[k]['region']), []).append({**row, 'how': how, 'site': int(regions[k]['site'])})
        for site, how in e5_hits.items():
            e5_reasons.setdefault(int(site), []).append({**row, 'how': how, 'e5_faces': e5['faces_of'][site]})
    return dict(schema_version=2, candidate=str(candidate), validation=str(validation),
                validation_sha256=sha256_file(validation), region_map_sha256=sha256_file(candidate / 'region-map.json'),
                depth_tolerance_in=tol, failing=len(failing),
                e4_regions=sorted(reasons), regions=sorted(reasons), e5_sites=sorted(e5_reasons),
                reasons={'e4_regions': {str(r): rows for r, rows in sorted(reasons.items())},
                         'e5_sites': {str(s): rows for s, rows in sorted(e5_reasons.items())}},
                unexplained=unexplained,
                e5_candidate=None if e5 is None else e5['e5_candidate'],
                e3_candidate=None if e5 is None else e5['e3_candidate'],
                interior=_interior(interior))


def _e5_chain(candidate: Path, n_baseline: int):
    """The E5 stage the E4 audit chains through, in BASELINE face ids: `site_of` (baseline face -> the kept E5 site that
    removed it), `faces_of` (site -> its removed baseline faces), `removed_by_e3`, the two candidate dirs. None when
    the audit names no E5 candidate."""
    audit = json.loads((candidate / 'stage-audit.json').read_text(encoding='utf-8'))
    binding = audit.get('e5_candidate')
    if not isinstance(binding, dict) or not binding.get('candidate'):
        return None
    e5_dir = Path(binding['candidate'])
    e5_audit = json.loads((e5_dir / 'stage-audit.json').read_text(encoding='utf-8'))
    e3_binding = e5_audit.get('e3_candidate') or audit.get('e3_candidate')
    if isinstance(e3_binding, dict) and e3_binding.get('candidate'):
        e3_dir = Path(e3_binding['candidate'])
        e3_faces = [int(f) for f in json.loads((e3_dir / 'source-faces.json').read_text(encoding='utf-8'))['source_faces']]
    else:
        e3_dir, e3_faces = None, list(range(n_baseline))
    site_of: dict[int, int] = {}
    faces_of: dict[int, list] = {}
    for line in (e5_dir / 'edit-log.jsonl').read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if 'check' in row or row.get('rolled_back', False) or row.get('engine') != 'E5':
            continue
        site = int(row['site'])
        for local in row['faces']:
            base = int(e3_faces[int(local)])
            site_of[base] = site
            faces_of.setdefault(site, []).append(base)
    return dict(site_of=site_of, faces_of=faces_of, removed_by_e3=set(range(n_baseline)) - set(e3_faces),
                e5_candidate=str(e5_dir), e3_candidate=None if e3_dir is None else str(e3_dir))


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
