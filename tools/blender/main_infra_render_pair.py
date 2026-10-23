"""Render saved OBJ pairs in one recorded frame, double-sided with their texture looks."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector
import numpy as np


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def imported(path, frame):
    existing = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=str(path), forward_axis='Y', up_axis='Z',
                          use_split_objects=False, use_split_groups=False, validate_meshes=False)
    objects = [obj for obj in bpy.data.objects if obj not in existing and obj.type == 'MESH']
    if not objects:
        raise ValueError('No imported mesh')
    for obj in objects:
        for vertex in obj.data.vertices:
            x, y, z = vertex.co
            if frame == 'source':
                vertex.co = (x, -z, y)
            elif frame == 'engine-inches':
                vertex.co *= 0.0254
        obj.data.update()
        for slot in obj.material_slots:
            material = slot.material
            if material is None:
                raise ValueError('Missing imported material')
            material.use_backface_culling = False
            material.use_nodes = True
            nodes, links = material.node_tree.nodes, material.node_tree.links
            surface = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
            output = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL')
            emission = nodes.new('ShaderNodeEmission')
            if surface:
                color = surface.inputs['Base Color']
                emission.inputs['Color'].default_value = color.default_value
                if color.is_linked:
                    links.new(color.links[0].from_socket, emission.inputs['Color'])
            links.new(emission.outputs[0], output.inputs['Surface'])
            for node in nodes:
                if node.type == 'TEX_IMAGE':
                    if node.image is None or not Path(bpy.path.abspath(node.image.filepath)).is_file():
                        raise ValueError('Missing texture on imported material')
                    if not node.image.has_data:
                        node.image.reload()
                    decoded_pixels = len(node.image.pixels)
                    if decoded_pixels <= 0 or min(node.image.size) <= 0:
                        raise ValueError('Imported texture has no decoded pixels')
                    node.interpolation = 'Closest'
    return objects


def save_diff(path, rgba):
    height, width, _ = rgba.shape
    picture = bpy.data.images.new('difference', width=width, height=height, alpha=True)
    picture.pixels.foreach_set(rgba.astype(np.float32).ravel())
    picture.filepath_raw = str(path)
    picture.file_format = 'PNG'
    picture.save()
    bpy.data.images.remove(picture)


def run(args):
    args.before, args.after, args.out = args.before.resolve(), args.after.resolve(), args.out.resolve()
    if args.out.exists():
        raise ValueError('Evidence output exists; refusing overwrite')
    args.out.mkdir(parents=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    before = imported(args.before, args.before_frame)
    after = imported(args.after, args.after_frame)
    coords = np.asarray([tuple(obj.matrix_world @ vertex.co) for obj in before for vertex in obj.data.vertices])
    lower, upper = coords.min(axis=0), coords.max(axis=0)
    center, span = (lower + upper) / 2, max(float(np.linalg.norm(upper - lower)), 0.1)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 1
    scene.render.resolution_x = scene.render.resolution_y = args.size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = True
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.render.dither_intensity = 0
    camera = bpy.data.objects.new('QA camera', bpy.data.cameras.new('QA camera'))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.clip_start, camera.data.clip_end = 0.001, span * 12
    directions = [('top', (0, 0, 1))] if args.views == 'top' else [
        ('view_' + '_'.join(map(str, direction)), direction)
        for direction in itertools.product((-1, 0, 1), repeat=3) if direction != (0, 0, 0)]
    views = []
    for name, direction in directions:
        position = Vector(center) + Vector(direction).normalized() * span * 2
        views.append((name, position, Vector(center), 'ORTHO'))
    if args.views != 'top':
        for idx, (fx, fy, dx, dy) in enumerate([(0.3, 0.3, 1, 0), (0.7, 0.3, -1, 0),
                (0.3, 0.7, 0, -1), (0.7, 0.7, 0, 1)]):
            position = Vector((lower[0] + fx * (upper[0] - lower[0]),
                               lower[1] + fy * (upper[1] - lower[1]), lower[2] + 1.6002))
            views.append((f'eye_{idx}', position, position + Vector((dx, dy, 0)), 'PERSP'))
    rows = []
    for name, position, target, projection in views:
        camera.location = position
        camera.rotation_euler = (target - position).to_track_quat('-Z', 'Y').to_euler()
        camera.data.type = projection
        camera.data.ortho_scale = span * 1.10
        camera.data.lens = 22
        pixels = []
        for label, visible, hidden in [('before', before, after), ('after', after, before)]:
            for obj in visible:
                obj.hide_render = False
            for obj in hidden:
                obj.hide_render = True
            image_path = args.out / f'{name}.{label}.png'
            scene.render.filepath = str(image_path)
            bpy.ops.render.render(write_still=True)
            saved = bpy.data.images.load(str(image_path), check_existing=False)
            pixels.append(np.asarray(saved.pixels[:], dtype=np.float32).reshape(args.size, args.size, 4))
            bpy.data.images.remove(saved)
        delta = np.abs(pixels[0] - pixels[1])
        different = int(np.any(delta > 0, axis=2).sum())
        display_diff = np.minimum(delta * 4, 1)
        display_diff[:, :, 3] = 1
        save_diff(args.out / f'{name}.diff.png', display_diff)
        rows.append({'name': name, 'projection': projection, 'camera_position_metres': list(position),
            'target_metres': list(target), 'different_pixels': different,
            'max_channel_difference': float(delta.max()), 'mean_channel_difference': float(delta.mean()),
            'non_background_pixels': int((pixels[0][:, :, 3] > 0).sum())})
        print(f'PAIR {name}: {different} different pixels', flush=True)
    report = {'before': str(args.before), 'after': str(args.after),
        'before_sha256': digest(args.before), 'after_sha256': digest(args.after),
        'before_frame': args.before_frame, 'after_frame': args.after_frame,
        'size': args.size, 'blender_version': bpy.app.version_string,
        'shader': 'double-sided emission, saved Kd/image look; nearest texture sampling',
        'bounds_metres': [lower.tolist(), upper.tolist()], 'views': rows,
        'all_pixels_identical': all(row['different_pixels'] == 0 for row in rows)}
    (args.out / 'comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--before-frame', choices=['source', 'engine-inches', 'engine-metres'], required=True)
    parser.add_argument('--after-frame', choices=['source', 'engine-inches', 'engine-metres'], required=True)
    parser.add_argument('--views', choices=['top', 'all'], default='all')
    parser.add_argument('--size', type=int, default=512)
    run(parser.parse_args(sys.argv[sys.argv.index('--') + 1:]))
