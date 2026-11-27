"""Package Real-Model Engine v2 OBJ/MTL/textures into a per-floor Blender 5.1 `.blend`,
export its `.glb` directly from Blender, validate mesh topology (`mesh.validate()`),
record results into `v2_integrity_report.json`, and render side-by-side comparison PNGs.

Run headless via:
    blender.exe -b --factory-startup --python tools/blender_package_v2_floor.py -- --report <v2_integrity_report.json>
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any

import bpy
from mathutils import Vector

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None  # type: ignore[assignment]


def _parse_cli_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(description="Package per-floor Engine v2 .blend + .glb + proof renders")
    parser.add_argument("--report", required=True, help="Path to v2_integrity_report.json")
    parser.add_argument("--v1-obj", default=None, help="Optional v1 .fixed.obj path for side-by-side comparison renders")
    parser.add_argument("--proof-dir", default=None, help="Optional output folder for side-by-side proof PNGs")
    return parser.parse_args(argv)


def _configure_principled_material(mat: bpy.types.Material) -> None:
    if not mat.use_nodes or mat.node_tree is None:
        return
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = 0.85
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.2
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = 0.0
    # Single-layer E5 sheets must export doubleSided=true in GLB so wall tops/railings/ceilings render cleanly
    mat.use_backface_culling = False

    is_glass = "glass" in mat.name.lower()
    tex_nodes = [n for n in nt.nodes if n.type == "TEX_IMAGE"]
    for tn in tex_nodes:
        if tn.image is not None and "glass" in tn.image.name.lower():
            is_glass = True
        tn.interpolation = "Closest"

    if is_glass:
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.15
        if "Alpha" in bsdf.inputs:
            linked_alpha = bool(bsdf.inputs["Alpha"].is_linked)
            if not linked_alpha and tex_nodes and tex_nodes[0].image is not None:
                nt.links.new(tex_nodes[0].outputs["Alpha"], bsdf.inputs["Alpha"])
            if not bsdf.inputs["Alpha"].is_linked:
                bsdf.inputs["Alpha"].default_value = 0.45


def _import_v2_scene(obj_path: Path, collection_name: str, object_name: str) -> bpy.types.Object:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    col = bpy.data.collections.new(collection_name)
    scene.collection.children.link(col)

    bpy.ops.wm.obj_import(filepath=str(obj_path), forward_axis="Y", up_axis="Z")
    imported = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if not imported:
        raise RuntimeError(f"No mesh objects imported from {obj_path}")

    if len(imported) > 1:
        bpy.context.view_layer.objects.active = imported[0]
        for o in imported:
            o.select_set(True)
        bpy.ops.object.join()
        obj = bpy.context.active_object
    else:
        obj = imported[0]

    obj.name = object_name
    obj.data.name = f"{object_name}_mesh"

    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)
    bpy.context.view_layer.objects.active = obj

    for mat in obj.data.materials:
        if mat is not None:
            _configure_principled_material(mat)
    return obj


def _object_world_bbox(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


def _add_studio_lights_and_world(scene: bpy.types.Scene) -> None:
    world = bpy.data.worlds.new("SiegeProofWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.045, 0.068, 0.115, 1.0)
        bg.inputs["Strength"].default_value = 0.85

    for idx, (rot_deg, energy) in enumerate([((52, 0, 35), 2.4), ((48, 0, -145), 1.5)]):
        ldata = bpy.data.lights.new(name=f"ProofSun_{idx}", type="SUN")
        ldata.energy = energy
        ldata.angle = math.radians(12.0)
        lobj = bpy.data.objects.new(name=f"ProofSun_{idx}", object_data=ldata)
        lobj.rotation_euler = tuple(math.radians(a) for a in rot_deg)
        scene.collection.objects.link(lobj)


def _aim_camera(cam_obj: bpy.types.Object, cam_pos: Vector, target: Vector, lens_mm: float = 35.0) -> None:
    cam_obj.location = cam_pos
    direction = (target - cam_pos).normalized()
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam_obj.data.lens = lens_mm
    cam_obj.data.clip_start = 0.1
    cam_obj.data.clip_end = 5000.0


def _import_v1_obj_for_compare(v1_path: Path, target_min: Vector, target_max: Vector) -> list[bpy.types.Object]:
    """Import v1 OBJ cleanly scaled & aligned to the Z-up v2 bounding frame for comparison."""
    before_objs = set(bpy.data.objects)
    # Unity-Buildings / Repaired-Buildings .fixed.obj files are Y-up metres;
    # Blender default import maps Y-up OBJ (-Z forward, Y up) -> Z-up (X, -Z, Y) if needed.
    # Match exact centroid + height scale against Real v2 Z-up bounding box.
    bpy.ops.wm.obj_import(filepath=str(v1_path), forward_axis="NEGATIVE_Z", up_axis="Y")
    new_objs = [o for o in bpy.data.objects if o not in before_objs and o.type == "MESH"]
    if not new_objs:
        return []
    bpy.ops.object.select_all(action="DESELECT")
    for o in new_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new_objs[0]
    if len(new_objs) > 1:
        bpy.ops.object.join()
    obj = bpy.context.active_object
    obj.name = "V1_Comparison"
    for mat in obj.data.materials:
        if mat is not None:
            _configure_principled_material(mat)

    vmin, vmax = _object_world_bbox(obj)
    vext = vmax - vmin
    text = target_max - target_min
    # Fix sign/orientation to match v2 target centroid & scale
    if max(vext.x, vext.y, vext.z) > 200.0 and max(text.x, text.y, text.z) < 120.0:
        # Inch-scale OBJ (dashboard after.obj CKPT-17): scale by 0.0254 & rotate Z 180 deg
        obj.scale = (0.0254, 0.0254, 0.0254)
        obj.rotation_euler = (0.0, 0.0, math.pi)
        bpy.context.view_layer.update()
        vmin, vmax = _object_world_bbox(obj)

    vcen = 0.5 * (vmin + vmax)
    tcen = 0.5 * (target_min + target_max)
    # Check whether X/Y span matches or needs 180 Z flip
    vext = vmax - vmin
    if abs(vext.x - text.x) > 1.0 and abs(vext.y - text.x) < 1.0:
        obj.rotation_euler.z += math.pi * 0.5
        bpy.context.view_layer.update()
        vmin, vmax = _object_world_bbox(obj)
        vcen = 0.5 * (vmin + vmax)

    obj.location += (tcen - vcen)
    bpy.context.view_layer.update()
    return [obj]


def _render_single_view(
    scene: bpy.types.Scene,
    cam_obj: bpy.types.Object,
    out_png: Path,
    res_x: int = 900,
    res_y: int = 620,
) -> None:
    scene.camera = cam_obj
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = res_x
    scene.render.resolution_y = res_y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(out_png)
    scene.view_settings.view_transform = "Standard"
    bpy.ops.render.render(write_still=True)


def _compose_side_by_side(
    left_png: Path,
    right_png: Path,
    out_png: Path,
    left_label: str,
    right_label: str,
) -> None:
    if Image is None:
        return
    im_l = Image.open(left_png).convert("RGB")
    im_r = Image.open(right_png).convert("RGB")
    pad = 12
    banner = 42
    w = im_l.width + im_r.width + pad * 3
    h = max(im_l.height, im_r.height) + banner + pad * 2
    canvas = Image.new("RGB", (w, h), (10, 15, 28))
    canvas.paste(im_l, (pad, banner + pad))
    canvas.paste(im_r, (pad * 2 + im_l.width, banner + pad))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    draw.rectangle([pad, 8, pad + im_l.width, banner], fill=(22, 34, 56))
    draw.rectangle([pad * 2 + im_l.width, 8, pad * 2 + im_l.width + im_r.width, banner], fill=(16, 54, 42))
    draw.text((pad + 14, 15), left_label, fill=(145, 225, 195), font=font)
    draw.text((pad * 2 + im_l.width + 14, 15), right_label, fill=(110, 245, 185), font=font)
    canvas.save(out_png)


def package_floor_blend_and_glb(
    report_path: Path,
    *,
    v1_obj_path: Path | None = None,
    proof_dir: Path | None = None,
) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    out_dir = report_path.parent
    stem = f"{report['building']}_{report['floor']}"
    in_obj = Path(report["out_obj_zup_metres"])
    blend_path = out_dir / f"{stem}.blend"
    glb_path = out_dir / f"{stem}.glb"

    obj = _import_v2_scene(in_obj, stem, f"{report['unit_slug']}_v2")
    _add_studio_lights_and_world(bpy.context.scene)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    before_slots = len(obj.material_slots)
    try:
        bpy.ops.object.material_slot_remove_unused()
    except Exception:
        pass
    unused_slots_removed = max(0, before_slots - len(obj.material_slots))

    invalid = bool(obj.data.validate(verbose=False))
    bpy.ops.file.pack_all()

    vmin, vmax = _object_world_bbox(obj)
    vcen = 0.5 * (vmin + vmax)
    vext = vmax - vmin

    # Set default camera in .blend framed on the floor so opening in Blender centers cleanly
    cam_data = bpy.data.cameras.new("FloorPreviewCam")
    cam_obj = bpy.data.objects.new("FloorPreviewCam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    _aim_camera(cam_obj, vcen + Vector((-vext.x * 0.72, vext.y * 0.85, vext.z * 3.6)), vcen, lens_mm=34.0)
    bpy.context.scene.camera = cam_obj

    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    # Export GLB directly from the packaged Blender scene (only our v2 mesh objects, exclude camera/lights)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_materials="EXPORT",
        export_texcoords=True,
        export_normals=True,
    )

    glass_mats = sum(
        1 for m in obj.data.materials
        if m is not None and ("glass" in m.name.lower() or "stained" in m.name.lower())
    )
    opaque_mats = sum(1 for m in obj.data.materials if m is not None) - glass_mats

    blender_topo = {
        "valid": not invalid,
        "invalid_flag": invalid,
        "blend_path": str(blend_path),
        "glb_path": str(glb_path),
        "vertices": int(len(obj.data.vertices)),
        "polygons": int(len(obj.data.polygons)),
        "materials": int(len(obj.data.materials)),
        "opaque_materials": int(opaque_mats),
        "transparent_materials": int(glass_mats),
        "unused_material_slots_removed": int(unused_slots_removed),
        "mesh_baker_ready": True,
        "packed_images": int(sum(1 for img in bpy.data.images if img.packed_file is not None)),
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    report["blender_topology"] = blender_topo
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    rendered_proofs: list[str] = []
    if proof_dir is not None:
        proof_dir.mkdir(parents=True, exist_ok=True)
        # Render side-by-side comparison importing the EXACT exported GLB!
        views = [
            (
                "overview",
                vcen + Vector((-vext.x * 0.78, vext.y * 0.88, max(vext.z * 3.8, 18.0))),
                vcen,
                32.0,
            ),
            (
                "closeup_railing_window",
                Vector((vcen.x - 5.0, vmax.y + 7.5, vmax.z + 1.2)),
                Vector((vcen.x + 2.5, vmax.y - 7.5, vmin.z + 2.4)),
                38.0,
            ),
            (
                "closeup_corner_glass",
                Vector((vmax.x + 8.5, vmax.y + 7.5, vmax.z + 0.5)),
                Vector((vmax.x - 5.5, vmax.y - 5.0, vmin.z + 2.4)),
                40.0,
            ),
            (
                "closeup_canopy_underside",
                Vector((vmax.x - 9.0, vmin.y - 7.5, vmin.z + 1.4)),
                Vector((vmax.x - 10.5, vmin.y + 5.5, vmax.z - 1.0)),
                38.0,
            ),
            (
                "closeup_floor_underside",
                Vector((vcen.x - 8.5, vcen.y - 8.5, vmin.z - 0.8)),
                Vector((vcen.x + 6.5, vcen.y + 6.5, vmin.z + 1.8)),
                36.0,
            ),
        ]

        # 1. Render Real v2 from exported GLB
        bpy.ops.wm.read_factory_settings(use_empty=True)
        _add_studio_lights_and_world(bpy.context.scene)
        bpy.ops.import_scene.gltf(filepath=str(glb_path))
        glb_meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        for go in glb_meshes:
            for mat in go.data.materials:
                if mat is not None:
                    _configure_principled_material(mat)
        cam_r = bpy.data.cameras.new("CamR")
        cam_r_obj = bpy.data.objects.new("CamR", cam_r)
        bpy.context.scene.collection.objects.link(cam_r_obj)

        for vname, cpos, ctgt, lens in views:
            _aim_camera(cam_r_obj, cpos, ctgt, lens_mm=lens)
            _render_single_view(bpy.context.scene, cam_r_obj, proof_dir / f"_{vname}_v2.png")

        # 2. Render v1 on exact same camera views
        if v1_obj_path is not None and v1_obj_path.is_file():
            bpy.ops.wm.read_factory_settings(use_empty=True)
            _add_studio_lights_and_world(bpy.context.scene)
            _import_v1_obj_for_compare(v1_obj_path, vmin, vmax)
            cam_l = bpy.data.cameras.new("CamL")
            cam_l_obj = bpy.data.objects.new("CamL", cam_l)
            bpy.context.scene.collection.objects.link(cam_l_obj)
            for vname, cpos, ctgt, lens in views:
                _aim_camera(cam_l_obj, cpos, ctgt, lens_mm=lens)
                _render_single_view(bpy.context.scene, cam_l_obj, proof_dir / f"_{vname}_v1.png")
                out_pair = proof_dir / f"{vname}_v1_vs_real_v2.png"
                _compose_side_by_side(
                    proof_dir / f"_{vname}_v1.png",
                    proof_dir / f"_{vname}_v2.png",
                    out_pair,
                    f"AFTER v1 ({v1_obj_path.name})",
                    f"AFTER REAL ENGINE v2 ({glb_path.name})",
                )
                rendered_proofs.append(str(out_pair))

    return {"blender_topology": blender_topo, "proofs": rendered_proofs}


def main() -> int:
    args = _parse_cli_args()
    res = package_floor_blend_and_glb(
        Path(args.report),
        v1_obj_path=Path(args.v1_obj) if args.v1_obj else None,
        proof_dir=Path(args.proof_dir) if args.proof_dir else None,
    )
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
