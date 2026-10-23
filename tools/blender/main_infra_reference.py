"""Capture Blender's displayed OBJ tessellation, bound to original polygon/corner records."""
import argparse
from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path
import struct
import sys

import bpy


def f32(value):
    return struct.unpack('f', struct.pack('f', value))[0]


def ring_key(corners, material):
    return material, min(tuple(corners[i:] + corners[:i]) for i in range(len(corners)))


def source_records(path):
    positions, uvs, polygons = [], [], []
    material = ''
    for line_number, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        parts = raw.partition('#')[0].split(maxsplit=1)
        if not parts:
            continue
        head, tail = parts[0], parts[1] if len(parts) > 1 else ''
        if head == 'v':
            positions.append(tuple(map(float, tail.split())))
        elif head == 'vt':
            uvs.append(tuple(map(float, tail.split())))
        elif head == 'usemtl':
            material = tail
        elif head == 'f':
            corners = []
            for token in tail.split():
                refs = token.split('/')
                vertex = int(refs[0])
                vertex = vertex - 1 if vertex > 0 else len(positions) + vertex
                uv = int(refs[1]) if len(refs) > 1 and refs[1] else 0
                uv = uv - 1 if uv > 0 else len(uvs) + uv if uv < 0 else None
                corners.append((tuple(f32(x) for x in positions[vertex]),
                                tuple(f32(x) for x in uvs[uv]) if uv is not None else None))
            polygons.append({'line': line_number, 'corners': corners, 'material': material})
    return positions, polygons


def capture(source, output):
    positions, original = source_records(source)
    awaiting = defaultdict(deque)
    for polygon in original:
        awaiting[ring_key(polygon['corners'], polygon['material'])].append(polygon)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    settings = {'filepath': str(source), 'use_split_objects': False, 'use_split_groups': False, 'validate_meshes': False}
    properties = bpy.ops.wm.obj_import.get_rna_type().properties
    for name, desired in [('forward_axis', 'Y'), ('up_axis', 'Z')]:
        identifiers = {item.identifier for item in properties[name].enum_items}
        if desired not in identifiers:
            raise RuntimeError(f'Unsupported importer coordinate enum: {name}: {identifiers}')
        settings[name] = desired
    bpy.ops.wm.obj_import(**settings)
    result, imported_count = {}, 0
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        mesh = obj.data
        mesh.calc_loop_triangles()
        by_polygon = defaultdict(list)
        for triangle in mesh.loop_triangles:
            by_polygon[triangle.polygon_index].append(tuple(triangle.loops))
        for polygon in mesh.polygons:
            material = mesh.materials[polygon.material_index].name if mesh.materials and mesh.materials[polygon.material_index] else ''
            corners = []
            for loop in polygon.loop_indices:
                point = obj.matrix_world @ mesh.vertices[mesh.loops[loop].vertex_index].co
                uv = tuple(mesh.uv_layers.active.data[loop].uv) if mesh.uv_layers.active else None
                corners.append((tuple(point), uv))
            key = ring_key(corners, material)
            if not awaiting[key]:
                raise RuntimeError(f'Imported polygon has no original corner/UV/material match: {polygon.index}, {material}')
            source_polygon = awaiting[key].popleft()
            source_corners = source_polygon['corners']
            if len(set(source_corners)) != len(source_corners):
                raise RuntimeError('Ambiguous repeated source corner')
            local = {loop: source_corners.index(corner) for loop, corner in zip(polygon.loop_indices, corners)}
            triangles = [[local[loop] for loop in triangle] for triangle in by_polygon[polygon.index]]
            if len(triangles) != len(source_corners) - 2:
                raise RuntimeError('Native tessellation dropped or added polygon coverage')
            result[str(source_polygon['line'])] = triangles
            imported_count += 1
    unmatched = sum(len(queue) for queue in awaiting.values())
    if unmatched or imported_count != len(original):
        raise RuntimeError(f'Unmatched source polygons: {unmatched}')
    doc = {'schema_version': 1, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
           'source_obj': str(source), 'blender_version': bpy.app.version_string,
           'import_settings': settings, 'raw_polygon_count': len(original),
           'imported_polygon_count': imported_count, 'triangle_count': sum(map(len, result.values())),
           'unmatched_polygons': unmatched, 'polygons': result,
           'max_import_float32_quantization_source_units': max(abs(f32(x) - x) for point in positions for x in point)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, indent=2), encoding='utf-8')
    print(f'REFERENCE {source.name}: {imported_count} polygons, {doc["triangle_count"]} triangles, {unmatched} unmatched', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    capture(args.input.resolve(), args.output.resolve())


if __name__ == '__main__':
    main()
