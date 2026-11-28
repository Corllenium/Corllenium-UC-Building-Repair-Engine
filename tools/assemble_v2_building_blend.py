"""Assemble per-floor Real-Model Engine v2 OBJs into an organized multi-floor master `.blend`
with separate floor collections, zero duplicate packed textures, direct 12-node `.glb` export,
and a Design Studio + Map Sync manifest JSON.

Run headless via Blender 5.1:
    blender.exe -b --factory-startup --python tools/assemble_v2_building_blend.py -- --building CHTM
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

DEFAULT_STAGING_ROOT = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair\02_STAGING_DEVELOPMENT\PerFloor-EngineV2")

FLOOR_SPECS_BY_BUILDING: dict[str, list[tuple[str, str, str]]] = {
    "CHTM": [
        ("01_Floor_4B", "Floor_4B", "CHTM_1st_floor_obj"),
        ("02_Floor_3B", "Floor_3B", "Chtm_2nd_floor"),
        ("03_Floor_2B", "Floor_2B", "CHTM_3rd_floor"),
        ("04_Floor_1B", "Floor_1B", "CHTM_4th_floor"),
        ("05_Floor_4F", "Floor_4F", "CHTM_5ft_floor_obj"),
        ("06_Floor_5F", "Floor_5F", "CHTM_6ft_floor_obj"),
        ("07_Floor_6F", "Floor_6F", "CHTM_7th_floor_obj"),
        ("08_Floor_7F", "Floor_7F", "CHTM_8th_floor_obj"),
        ("09_Floor_8F", "Floor_8F", "CHTM_9th_floor_obj"),
        ("10_Floor_9F", "Floor_9F", "CHTM_10th_floor_obj"),
        ("11_Floor_9M", "Floor_9M", "CHTM_11th_floor_obj"),
        ("12_Floor_RF", "Floor_RF", "CHTM_12th_floor_obj"),
    ],
}


def _parse_cli_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    p = argparse.ArgumentParser(description="Assemble organized multi-floor Engine v2 .blend + .glb + manifest")
    p.add_argument("--building", default="CHTM")
    p.add_argument("--staging-root", default=str(DEFAULT_STAGING_ROOT))
    p.add_argument("--out-blend", default=None)
    p.add_argument("--out-glb", default=None)
    p.add_argument("--out-manifest", default=None)
    return p.parse_args(argv)


def _configure_material_and_dedup_images(
    mat: bpy.types.Material,
    img_by_basename: dict[str, bpy.types.Image],
) -> None:
    if not mat.use_nodes or mat.node_tree is None:
        return
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is not None:
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.85
        if "Specular IOR Level" in bsdf.inputs:
            bsdf.inputs["Specular IOR Level"].default_value = 0.2
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = 0.0
    mat.use_backface_culling = False

    is_glass = "glass" in mat.name.lower() or "stained" in mat.name.lower()
    tex_nodes = [n for n in nt.nodes if n.type == "TEX_IMAGE"]
    for tn in tex_nodes:
        img = tn.image
        if img is not None:
            base = Path(bpy.path.abspath(img.filepath)).name if img.filepath else img.name
            existing = img_by_basename.get(base)
            if existing is None:
                img_by_basename[base] = img
            elif existing is not img:
                tn.image = existing
                img = existing
            if "glass" in base.lower() or "stained" in base.lower():
                is_glass = True
        tn.interpolation = "Closest"

    if is_glass and bsdf is not None and "Alpha" in bsdf.inputs:
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.15
        if not bsdf.inputs["Alpha"].is_linked and tex_nodes and tex_nodes[0].image is not None:
            nt.links.new(tex_nodes[0].outputs["Alpha"], bsdf.inputs["Alpha"])
        if not bsdf.inputs["Alpha"].is_linked:
            bsdf.inputs["Alpha"].default_value = 0.45


def _object_world_bbox(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


def _add_studio_world_and_camera(scene: bpy.types.Scene, vmin: Vector, vmax: Vector) -> None:
    world = bpy.data.worlds.new("CHTM_StudioWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (0.045, 0.068, 0.115, 1.0)
        bg.inputs["Strength"].default_value = 0.85

    for idx, (rot_deg, energy) in enumerate([((52, 0, 35), 2.4), ((48, 0, -145), 1.5)]):
        ldata = bpy.data.lights.new(name=f"MasterSun_{idx}", type="SUN")
        ldata.energy = energy
        ldata.angle = math.radians(12.0)
        lobj = bpy.data.objects.new(name=f"MasterSun_{idx}", object_data=ldata)
        lobj.rotation_euler = tuple(math.radians(a) for a in rot_deg)
        scene.collection.objects.link(lobj)

    vcen = 0.5 * (vmin + vmax)
    vext = vmax - vmin
    cam_data = bpy.data.cameras.new("BuildingMasterCam")
    cam_obj = bpy.data.objects.new("BuildingMasterCam", cam_data)
    scene.collection.objects.link(cam_obj)
    cam_pos = vcen + Vector((-max(vext.x, 10.0) * 0.85, max(vext.y, 10.0) * 0.95, max(vext.z, 10.0) * 1.15))
    cam_obj.location = cam_pos
    cam_obj.rotation_euler = (vcen - cam_pos).normalized().to_track_quat("-Z", "Y").to_euler()
    cam_obj.data.lens = 35.0
    cam_obj.data.clip_start = 0.1
    cam_obj.data.clip_end = 5000.0
    scene.camera = cam_obj


def assemble_building_blend(
    building: str,
    *,
    staging_root: Path = DEFAULT_STAGING_ROOT,
    out_blend: Path | None = None,
    out_glb: Path | None = None,
    out_manifest: Path | None = None,
) -> dict[str, Any]:
    specs = FLOOR_SPECS_BY_BUILDING.get(building)
    if not specs:
        raise ValueError(f"Unsupported building for assembly: {building}")

    b_dir = staging_root / building
    blend_path = out_blend or (b_dir / f"{building}_EngineV2_Master.blend")
    glb_path = out_glb or (b_dir / f"{building}_EngineV2_AllFloors.glb")
    manifest_path = out_manifest or (b_dir / f"{building}_EngineV2_Master.manifest.json")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    root_col_name = f"{building}_RealEngineV2"
    root_col = bpy.data.collections.new(root_col_name)
    scene.collection.children.link(root_col)

    img_by_basename: dict[str, bpy.types.Image] = {}
    floor_objs: list[bpy.types.Object] = []
    manifest_floors: list[dict[str, Any]] = []
    overall_min = Vector((1e9, 1e9, 1e9))
    overall_max = Vector((-1e9, -1e9, -1e9))

    for col_name, floor_code, unit_id in specs:
        fl_dir = b_dir / floor_code
        rep_path = fl_dir / "v2_integrity_report.json"
        if not rep_path.is_file():
            raise FileNotFoundError(f"Missing report for {building}/{floor_code}: {rep_path}")
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        in_obj = Path(rep["out_obj_zup_metres"])
        if not in_obj.is_file():
            raise FileNotFoundError(f"Missing OBJ for {building}/{floor_code}: {in_obj}")

        fl_col = bpy.data.collections.new(col_name)
        root_col.children.link(fl_col)

        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.wm.obj_import(filepath=str(in_obj), forward_axis="Y", up_axis="Z")
        imported = [o for o in bpy.context.selected_objects if o.type == "MESH"]
        if not imported:
            raise RuntimeError(f"No mesh imported for {in_obj}")
        bpy.context.view_layer.objects.active = imported[0]
        if len(imported) > 1:
            bpy.ops.object.join()
        obj = bpy.context.active_object

        obj_name = f"{building}_{floor_code}"
        obj.name = obj_name
        obj.data.name = f"{obj_name}_mesh"

        for c in list(obj.users_collection):
            c.objects.unlink(obj)
        fl_col.objects.link(obj)

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        try:
            bpy.ops.object.material_slot_remove_unused()
        except Exception:
            pass

        opaque_mats: list[str] = []
        transparent_mats: list[str] = []
        for mat in obj.data.materials:
            if mat is None:
                continue
            _configure_material_and_dedup_images(mat, img_by_basename)
            if "glass" in mat.name.lower() or "stained" in mat.name.lower():
                transparent_mats.append(mat.name)
            else:
                opaque_mats.append(mat.name)

        invalid = bool(obj.data.validate(verbose=False))
        fmin, fmax = _object_world_bbox(obj)
        overall_min = Vector((min(overall_min.x, fmin.x), min(overall_min.y, fmin.y), min(overall_min.z, fmin.z)))
        overall_max = Vector((max(overall_max.x, fmax.x), max(overall_max.y, fmax.y), max(overall_max.z, fmax.z)))

        v2_audit = rep["audits"]["real_v2"]
        tri_count = sum(1 for p in obj.data.polygons if len(p.vertices) == 3)
        floor_objs.append(obj)
        manifest_floors.append({
            "collection": col_name,
            "objectName": obj_name,
            "floor": floor_code,
            "unitId": unit_id,
            "glbUrl": f"/models/engine-v2/{building}/{floor_code}/{building}_{floor_code}.real_v2.glb",
            "overlayUrl": f"/models/engine-v2/{building}/{floor_code}/{building}_{floor_code}.error_overlay.json",
            "triangles": int(tri_count),
            "vertices": int(len(obj.data.vertices)),
            "meshValidatePassed": not invalid,
            "boundsZupMetres": {
                "min": [round(float(fmin.x), 4), round(float(fmin.y), 4), round(float(fmin.z), 4)],
                "max": [round(float(fmax.x), 4), round(float(fmax.y), 4), round(float(fmax.z), 4)],
            },
            "boundsYupMetres": {
                "min": [round(float(fmin.x), 4), round(float(fmin.z), 4), round(float(-fmax.y), 4)],
                "max": [round(float(fmax.x), 4), round(float(fmax.z), 4), round(float(-fmin.y), 4)],
            },
            "opaqueMaterials": sorted(set(opaque_mats)),
            "transparentMaterials": sorted(set(transparent_mats)),
            "outerFacadePct": float((v2_audit["checks"].get("outer_facade_completeness") or {}).get("numericValue") or 100.0),
            "flicker": [int(v2_audit["errors"]["flicker_diff"]), int(v2_audit["errors"]["flicker_same"])],
            "reversed": int(v2_audit["errors"]["reversed"]),
        })

    # Clean orphaned duplicate images before packing
    for img in list(bpy.data.images):
        if img.users == 0:
            bpy.data.images.remove(img)

    bpy.ops.file.pack_all()
    _add_studio_world_and_camera(scene, overall_min, overall_max)

    blend_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)

    # Export combined multi-node GLB with all 12 separate named floor nodes for Design Studio / Map Sync
    bpy.ops.object.select_all(action="DESELECT")
    for obj in floor_objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = floor_objs[0]
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_materials="EXPORT",
        export_texcoords=True,
        export_normals=True,
    )

    manifest = {
        "building": building,
        "engineMode": "real_model_v2",
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rootCollection": root_col_name,
        "floorCount": len(manifest_floors),
        "allMeshValidatePassed": all(f["meshValidatePassed"] for f in manifest_floors),
        "totalTriangles": sum(f["triangles"] for f in manifest_floors),
        "packedUniqueTextures": int(sum(1 for img in bpy.data.images if img.packed_file is not None)),
        "meshBakerRecipe": "Mesh Baker 3.40.2 (Paid Only): bake Opaque materials per floor or combined with Consider Mesh UVs=ON + Generate Lightmap UVs -> 1 URP Atlas; keep Glass as 1 Transparent material.",
        "files": {
            "masterBlend": str(blend_path),
            "allFloorsGlb": str(glb_path),
        },
        "boundsZupMetres": {
            "min": [round(float(overall_min.x), 4), round(float(overall_min.y), 4), round(float(overall_min.z), 4)],
            "max": [round(float(overall_max.x), 4), round(float(overall_max.y), 4), round(float(overall_max.z), 4)],
        },
        "floors": manifest_floors,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    args = _parse_cli_args()
    manifest = assemble_building_blend(
        args.building,
        staging_root=Path(args.staging_root),
        out_blend=Path(args.out_blend) if args.out_blend else None,
        out_glb=Path(args.out_glb) if args.out_glb else None,
        out_manifest=Path(args.out_manifest) if args.out_manifest else None,
    )
    print(json.dumps({
        "building": manifest["building"],
        "floorCount": manifest["floorCount"],
        "allMeshValidatePassed": manifest["allMeshValidatePassed"],
        "totalTriangles": manifest["totalTriangles"],
        "packedUniqueTextures": manifest["packedUniqueTextures"],
        "masterBlend": manifest["files"]["masterBlend"],
        "allFloorsGlb": manifest["files"]["allFloorsGlb"],
    }, indent=2))
    return 0 if manifest["allMeshValidatePassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
