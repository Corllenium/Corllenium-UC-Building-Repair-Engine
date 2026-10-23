"""Qualify interior render poses for a fresh floor: real walking-height Validator probes near each fixed eye camera.

Parametrized version of the 1F reviewer script Codex used on 2026-10-23
(`.../MAIN-INFRA-E3-20261023/.../preflight/iv_e3_camera_qualification.py`). The fixed `eye_N` cameras of
main_infra_render_pair.py sit 1.6 m above the bounding-box floor, which inside a stacked floor model can be
inside a cavity; a changed pixel there says nothing about what a student sees. This selects, for each fixed
eye, the 4 nearest actual `interior_probes()` of the Validator, certifies each against the original float64
triangles (eye exactly 63 in above a floor face, more than 83 in headroom) and writes the poses for the
`--poses` render. Run with PYTHONPATH = the E3 worktree (engine.validate.viewpoints/sampling live there).
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import trimesh
from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file
from engine.rays.caster import BruteCaster
from engine.validate.sampling import recentred, face_normals
from engine.validate.viewpoints import interior_probes, HEADROOM_START


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True, help='engine-frame BEFORE obj (the qualified baseline snapshot)')
    parser.add_argument('--native-qa', type=Path, required=True, help='render-pair output dir with the fixed eye cameras')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--floor', required=True)
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--per-eye', type=int, default=4)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    path = args.before.resolve()
    mesh = read_obj(path)
    b, centre = recentred(mesh)
    probes = interior_probes(b)
    world_probes = (probes + centre) * .0254
    caster = BruteCaster(b.positions, b.face_v)
    face_normals(b)
    qa = json.loads((args.native_qa / 'comparison.json').read_text())
    orig = [row for row in qa['views'] if row['name'].startswith('eye_')]
    points = np.array([row['camera_position_metres'] for row in orig]) / .0254 - centre
    fac, t = caster.first_hit(points, np.tile([0., 0., -1.], (len(points), 1)))
    feet = points.copy()
    feet[:, 2] -= t
    upf, upt = caster.first_hit(feet + [0, 0, HEADROOM_START], np.tile([0., 0., 1.], (len(points), 1)))
    nearest, distance, nearface = trimesh.proximity.closest_point_naive(trimesh.Trimesh(b.positions, b.face_v, process=False), points)
    rows, selected = [], []
    for i, row in enumerate(orig):
        dist = np.linalg.norm(world_probes - np.asarray(row['camera_position_metres']), axis=1)
        ids = np.argsort(dist, kind='stable')[:args.per_eye]
        rows.append(dict(name=row['name'], camera_common_metres=row['camera_position_metres'], downward_first_source_face=int(fac[i]),
                         floor_height_metres=float((feet[i, 2] + centre[2]) * .0254), eye_height_above_floor_metres=float(t[i] * .0254),
                         required_eye_height_metres=63 * .0254, headroom_upward_source_face=int(upf[i]),
                         clearance_from_floor_metres=None if np.isinf(upt[i]) else float((upt[i] + HEADROOM_START) * .0254),
                         unchanged_probe_headroom_required_metres=83 * .0254, nearest_surface_distance_metres=float(distance[i] * .0254),
                         nearest_surface_source_face=int(nearface[i]), nearest_engine_probe_ids=ids.tolist(),
                         nearest_engine_probe_distances_metres=dist[ids].tolist()))
        direction = np.asarray(row['target_metres']) - np.asarray(row['camera_position_metres'])
        direction /= np.linalg.norm(direction)
        for rank, pid in enumerate(ids):
            selected.append(dict(name=f"{row['name']}_qualified_{rank}_probe_{int(pid)}", probe_id=int(pid),
                                 position_metres=world_probes[pid].tolist(), target_metres=(world_probes[pid] + direction).tolist(),
                                 projection='PERSP'))
    selpoints = np.array([row['position_metres'] for row in selected]) / .0254 - centre
    sf, st = caster.first_hit(selpoints, np.tile([0., 0., -1.], (len(selpoints), 1)))
    sfeet = selpoints.copy()
    sfeet[:, 2] -= st
    suf, sut = caster.first_hit(sfeet + [0, 0, HEADROOM_START], np.tile([0., 0., 1.], (len(selpoints), 1)))
    for i, row in enumerate(selected):
        assert sf[i] >= 0 and abs(st[i] - 63) < 1e-7 and sut[i] > 83, f"probe {row['name']} is not a certified walking pose"
        row.update(floor_source_face=int(sf[i]), floor_height_metres=float((sfeet[i, 2] + centre[2]) * .0254),
                   eye_height_above_floor_metres=float(st[i] * .0254),
                   clearance_from_floor_metres=None if np.isinf(sut[i]) else float((sut[i] + HEADROOM_START) * .0254), headroom_clear=True)
    report = dict(job_id=args.job_id, floor_id=args.floor, reviewer=args.reviewer, recorded_utc=datetime.now(timezone.utc).isoformat(),
                  before_sha256=sha256_file(path),
                  method='Original float64 BruteCaster first-floor/downward and upward-clearance casts; actual unchanged interior_probes() generation; selected probes independently checked against original triangles',
                  native_fixed_cameras=rows, actual_engine_probes=len(probes), actual_probe_positions_common_metres=world_probes.tolist(),
                  qualified_render_poses=selected,
                  scope='Camera qualification only; no model/guard/targets/settings changes. Fixed native camera differences remain recorded; walkable-viewpoint interpretation is separate.')
    (out / 'camera-qualification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (out / 'qualified-native-poses.json').write_text(json.dumps(dict(poses=selected), indent=2), encoding='utf-8')
    print(json.dumps(dict(native_fixed_cameras=[dict(name=r['name'], eye_height_above_floor_metres=r['eye_height_above_floor_metres'],
                                                      clearance_from_floor_metres=r['clearance_from_floor_metres']) for r in rows],
                          actual_engine_probes=len(probes), qualified_render_poses=len(selected),
                          camera_qualification_sha256=sha256_file(out / 'camera-qualification.json'))))


if __name__ == '__main__':
    main()
