"""Build (or update) the Blender staging library for the fresh MAIN INFRA floor candidates (repo 04).

Mirrors `bpy_unity_sync_library.py`: OBJ import with forward Z / up Y (Minecraft Y-up to Blender Z-up), packed
textures, a receipt with vertex/index/uv signatures. One collection per floor, each at its own source origin
(the owner's floor placement is not known, so nothing is stacked or guessed). The master staging .blend files
are not touched; link this library from them when the owner decides.

  blender --background --factory-startup --python-exit-code 13 --python tools/blender/main_infra_fresh_library.py --
      --export <04>/Exports/Repaired-Buildings-20261023-fresh --output <04>/02_STAGING_DEVELOPMENT/BUILDINGS_AND_ENVIRONMENT/libraries/INFRA-FRESH-20261023.blend
      [--floors 7F,6F]
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy
import numpy as np

ORDINAL = {'1F': '1st', '2F': '2nd', '3F': '3rd', '4F': '4th', '5F': '5th', '6F': '6th', '7F': '7th'}


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signature(mesh):
    v = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get('co', v)
    idx = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get('vertices', idx)
    out = {'vertices': hashlib.sha256(v.tobytes()).hexdigest(), 'indices': hashlib.sha256(idx.tobytes()).hexdigest(),
           'vertex_count': len(mesh.vertices), 'triangle_count': len(mesh.loop_triangles)}
    if mesh.uv_layers.active:
        uv = np.empty(len(mesh.loops) * 2, dtype=np.float32)
        mesh.uv_layers.active.data.foreach_get('uv', uv)
        out['uvs'] = hashlib.sha256(uv.tobytes()).hexdigest()
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--floors', default='7F,6F,5F,4F')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    manifest = json.loads((args.export / 'MANIFEST.json').read_text(encoding='utf-8'))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    root_coll = bpy.data.collections.new('BLD_INFRA_FRESH')
    scene.collection.children.link(root_coll)
    receipt = []
    for floor in [f.strip() for f in args.floors.split(',') if f.strip()]:
        entry = manifest['floors'].get(floor)
        if not entry:
            print('SKIP', floor, 'not in export manifest', flush=True)
            continue
        stem = f'Main_Infrustructure_{ORDINAL[floor]}_floor'
        obj_path = args.export / entry['path'] / f'{stem}.fixed.source.obj'
        if sha256_file(obj_path) != entry['files'][f'{stem}.fixed.source.obj']:
            raise ValueError(f'{obj_path} differs from the 04 manifest hash')
        before = set(bpy.data.objects)
        bpy.ops.wm.obj_import(filepath=str(obj_path), forward_axis='Z', up_axis='Y', use_split_objects=False,
                              use_split_groups=False, validate_meshes=False)
        imported = [ob for ob in bpy.data.objects if ob not in before]
        if len(imported) != 1:
            raise ValueError(f'{floor}: expected one object, imported {len(imported)}')
        ob = imported[0]
        ob.name = ob.data.name = f'FRESH_{stem}'
        coll = bpy.data.collections.new(f'BLD_INFRA_FRESH_{floor}')
        root_coll.children.link(coll)
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        coll.objects.link(ob)
        ob.data.calc_loop_triangles()
        report = json.loads((args.export / entry['path'] / 'report.json').read_text(encoding='utf-8'))
        receipt.append({'floor': floor, 'object': ob.name, 'collection': coll.name, 'obj': str(obj_path.relative_to(args.export)),
                        'objSha256': entry['files'][f'{stem}.fixed.source.obj'], 'cleanup_mode': report['cleanup_mode'],
                        'status': report['status'], 'input_triangles': report['input_triangles'],
                        'output_triangles': report['output_triangles'], 'validator': report['validator'],
                        'signature': signature(ob.data), 'materials': [m.name for m in ob.data.materials if m],
                        'bounds_metres': [list(map(float, np.min([v.co for v in ob.data.vertices], axis=0))),
                                          list(map(float, np.max([v.co for v in ob.data.vertices], axis=0)))]})
        print('IMPORTED', floor, ob.name, len(ob.data.vertices), len(ob.data.loop_triangles), flush=True)
    bpy.ops.file.pack_all()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output), compress=True)
    record = {'bucket': 'INFRA_FRESH', 'source': str(args.export), 'source_revision': '7b2f7451b5723f724a1e074fdedc07dbcf7291d330ae550066f4926886136511',
              'frame': 'OBJ Y-up metres imported with forward Z / up Y; each floor at its own source origin; no stacking applied',
              'components': receipt, 'images_packed': len([i for i in bpy.data.images if i.packed_file]),
              'blender_version': bpy.app.version_string, 'status': 'candidates_not_accepted',
              'updated_utc': datetime.now(timezone.utc).isoformat(), 'blendSha256': sha256_file(args.output)}
    args.output.with_suffix('.receipt.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'floors': [r['floor'] for r in receipt], 'images_packed': record['images_packed']}), flush=True)


if __name__ == '__main__':
    main()
