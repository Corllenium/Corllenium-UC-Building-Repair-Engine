"""
Complete Reference-Guarded Engine Repair & Per-Floor SketchUp R5 Reference Slicer/Extractor:
1. Extracts the exact `["part 1", "BRS 3rd floor.obj"]` (`path_idx[:2] == [41, 5]`, 12,674 tris) from
   `capms_r5.skp` into `BRS_3rd_floor_obj/skp_ref.obj`.
2. Extracts the exact `Main_1st_Floor_obj` CKPT17 bounding-box slice from `capms_r5.skp` (`[32]`, `[33]`, `[9]`)
   into `Main_1st_Floor_obj/skp_ref.obj`.
3. Slices `Main_Infrustructure_Building/skp_ref.obj` into the 7 per-floor Z-band slabs
   (`Main_Infrustructure_1st_floor`..`7th_floor_custom` + `Main_Infrustructure_7th_floor` alias +
   `Main_Infrustructure_7th_floor_red_wing`) mapped into each floor's local `[0..X, 0..Y, 0..Z]` Y-up
   coordinate frame so `skp_ref.obj` aligns 1:1 with `before.obj` and `after.obj`.
4. Merges the two Checkpoint-17 parts of Main 3rd Floor (`Main_3RD_Floor_obj.obj` 624 tris +
   `Main_3RD_Floor_obj1.obj` 31,958 tris = 32,582 Checkpoint-17 tris) into `Main_3RD_Floor_obj/before.obj`.
5. Runs Pure Reference-Guarded Engine Repair (with `EmbreeCaster` `skp_ref.obj` verification, normal-aware
   deduplication, `remove_coplanar_overlaps`, and full `soffit_backup` restoration) on `Main_3RD_Floor_obj`,
   `Main_3RD_Floor_obj1`, `Main_4th_Floor_obj`, `PE_2nd_Floor_obj`, `PE_2nd_Floor`, `BRS_1st_floor_obj`,
   `Gymnasium_4th_floor_obj`, and `SHIELD_FRONTAGE`.
6. Runs `engine.detectors.errors.find_errors` to write `errors_skp_ref.json` for all newly populated/sliced
   `skp_ref.obj` units and any remaining reference unit, and syncs across all Siege worktrees.
7. Stages `MAIN`, `PE`, `BRS`, `GYMNASIUM`, and `SITE` into Blender 5.1 (`02_STAGING_DEVELOPMENT`).
"""
from __future__ import annotations

from ctypes import POINTER, Structure, byref, c_bool, c_double, c_int, c_size_t
import json
import re
import shutil
from pathlib import Path
import numpy as np

from engine.campus.blender_staging import apply_repaired_building_to_blender_staging
from engine.campus.checkpoint_push import convert_unity_to_ckpt17_coords
from engine.detectors.errors import find_errors
from engine.fixes.building_repair import compact_mesh, prepare_building_materials, remove_coplanar_overlaps
from engine.fixes.remove import remove_faces
from engine.io.mtl import parse_mtl
from engine.io.obj_reader import read_obj
from engine.io.skp_writer import (
    _BP,
    _RP,
    _SP,
    _open,
    _Point3D,
    _read_material,
    _Ref,
    _refs,
    _string,
    bind_group_calls,
    load_api,
)
from engine.model import MeshData
from engine.rays.caster import EmbreeCaster
from engine.topo.planes import face_normals
from smooth_restore_architecture import SIEGE_WTS, PRIMARY_SIEGE, compact_obj_bytes

WT_MODELS = PRIMARY_SIEGE / "dashboard/public/models"
REPO04_ROOT = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair")
REPO04_ORIG = REPO04_ROOT / "Exports/Unity-Buildings-20261014/ByBuilding"
REPO04_EXPORTS = REPO04_ROOT / "Exports/Repaired-Buildings-20261015/ByBuilding"
SKP_PATH = Path(r"D:\PROJECTS\05-Corllenium-UC-Building-Repair-Engine\data\campus\skp_copy\capms_r5.skp")
CKPT_OFFSET = np.array([-9952.653, 18950.281, 1188.980], dtype=np.float64)


class _Transformation(Structure):
    _fields_ = [("values", c_double * 16)]


EXTRA_CALLS = {
    "SUGroupGetTransform": ([_Ref, POINTER(_Transformation)], c_int),
    "SUEntitiesGetNumInstances": ([_Ref, _SP], c_int),
    "SUEntitiesGetInstances": ([_Ref, c_size_t, _RP, _SP], c_int),
    "SUComponentInstanceGetName": ([_Ref, _RP], c_int),
    "SUComponentInstanceGetTransform": ([_Ref, POINTER(_Transformation)], c_int),
    "SUComponentInstanceGetDefinition": ([_Ref, _RP], c_int),
    "SUComponentDefinitionGetName": ([_Ref, _RP], c_int),
    "SUComponentDefinitionGetEntities": ([_Ref, _RP], c_int),
    "SUComponentInstanceToDrawingElement": ([_Ref], _Ref),
    "SUFaceToDrawingElement": ([_Ref], _Ref),
    "SUDrawingElementGetHidden": ([_Ref, _BP], c_int),
    "SULayerGetVisibility": ([_Ref, _BP], c_int),
    "SUTextureGetFileName": ([_Ref, _RP], c_int),
    "SUMeshHelperGetFrontSTQCoords": ([_Ref, c_size_t, POINTER(_Point3D), _SP], c_int),
    "SUMeshHelperGetBackSTQCoords": ([_Ref, c_size_t, POINTER(_Point3D), _SP], c_int),
}


def _matrix(transformation: _Transformation) -> np.ndarray:
    m = np.array(transformation.values, float).reshape(4, 4, order="F")
    w = m[3, 3]
    if w != 0.0 and np.isfinite(w):
        m = m / w
    m[3] = (0.0, 0.0, 0.0, 1.0)
    return m


def _normalize_tex_key(s: str) -> str:
    s = Path(s).stem.lower()
    s = re.sub(r"^texture_\d+_", "", s)
    s = re.sub(r"^material_\d+_", "", s)
    s = re.sub(r"-twosided$", "", s)
    s = re.sub(r"^mumi_", "", s)
    s = re.sub(r"^(minecraft|littletiles|kirosblocks)_", "", s)
    return s


def parse_mtl_entries(mtl_path: Path) -> list[dict]:
    if not mtl_path.exists():
        return []
    entries = []
    cur = None
    for raw in mtl_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if line.startswith("newmtl "):
            if cur:
                entries.append(cur)
            mname = line.split(None, 1)[1].strip()
            cur = {
                "name": mname,
                "kd": (0.78, 0.78, 0.78),
                "tex": "",
                "norm_key": _normalize_tex_key(mname),
                "two_sided": "twosided" in mname.lower(),
            }
        elif cur is not None:
            if line.startswith("Kd "):
                parts = line.split()
                if len(parts) >= 4:
                    cur["kd"] = (float(parts[1]), float(parts[2]), float(parts[3]))
            elif line.startswith("map_Kd "):
                tex = line.split(None, 1)[1].strip()
                cur["tex"] = tex
                cur["norm_key"] = _normalize_tex_key(tex)
    if cur:
        entries.append(cur)
    return entries


def match_skp_mat_to_mtl(skp_mat_info: dict, mtl_entries: list[dict], group_hint: str = "", uid: str = "") -> str:
    if not mtl_entries:
        return "default"
    tex_key = _normalize_tex_key(skp_mat_info["tex_file"]) if skp_mat_info["tex_file"] else ""
    name_key = _normalize_tex_key(skp_mat_info["name"]) if skp_mat_info["name"] else ""
    hint_key = _normalize_tex_key(group_hint) if group_hint else ""
    skp_rgb = skp_mat_info["rgb"]
    uid_l = uid.lower()
    candidates = sorted(
        mtl_entries,
        key=lambda e: (not e["two_sided"], bool(uid_l) and (uid_l not in e["name"].lower()), e["name"]),
    )
    for key in (tex_key, name_key, hint_key):
        if not key:
            continue
        for e in candidates:
            if e["norm_key"] == key:
                return e["name"]
        base_prefix = re.sub(r"_-?\d+$", "", key)
        if base_prefix:
            best_e = None
            best_dist = 999.0
            for e in candidates:
                e_base = re.sub(r"_-?\d+$", "", e["norm_key"])
                if e_base == base_prefix:
                    dist = sum((a - b) ** 2 for a, b in zip(skp_rgb, e["kd"])) ** 0.5
                    if dist < best_dist:
                        best_dist = dist
                        best_e = e
            if best_e is not None and best_dist < 0.25:
                return best_e["name"]
    best_e = min(candidates, key=lambda e: sum((a - b) ** 2 for a, b in zip(skp_rgb, e["kd"])))
    return best_e["name"]


def sync_file_to_all_siege(unit_id: str, filename: str, data: bytes) -> None:
    for wt in SIEGE_WTS:
        for sub in ("dashboard/public/models", "dashboard/deploy-build/public/models"):
            u_dir = wt / sub / unit_id
            if u_dir.exists():
                (u_dir / filename).write_bytes(data)


def write_errors_json(mesh: MeshData, dst_path: Path) -> dict:
    res = find_errors(mesh)
    payload = (json.dumps(res, separators=(",", ":")) + "\n").encode("utf-8")
    dst_path.write_bytes(payload)
    return res["counts"]


def extract_brs3_and_main1_from_skp() -> list[str]:
    """Extract true `BRS_3rd_floor_obj` (`path_idx[:2] == [41, 5]`, 12,674 tris) and
    `Main_1st_Floor_obj` (faces in `[32]`, `[33]`, `[9]` inside Main 1st Floor's CKPT17 bbox)
    directly from `capms_r5.skp`.
    """
    print("=== Step 1A: Extracting True BRS_3rd_floor_obj & Main_1st_Floor_obj from capms_r5.skp ===", flush=True)
    m1_before = read_obj(WT_MODELS / "Main_1st_Floor_obj/before.obj")
    m1_min = m1_before.positions.min(axis=0) - np.array([12.0, 12.0, 12.0])
    m1_max = m1_before.positions.max(axis=0) + np.array([12.0, 12.0, 12.0])

    api = load_api()
    bind_group_calls(api)
    api.bind(EXTRA_CALLS)

    buckets: dict[str, list[tuple[np.ndarray, np.ndarray, dict, str]]] = {
        "BRS_3rd_floor_obj": [],
        "Main_1st_Floor_obj": [],
    }

    with api.session(), _open(api, SKP_PATH) as model:
        mat_cache: dict[int, dict] = {}

        def get_mat_info(mat_ref: _Ref) -> dict | None:
            if not mat_ref or not mat_ref.ptr:
                return None
            if mat_ref.ptr in mat_cache:
                return mat_cache[mat_ref.ptr]
            sm = _read_material(api, mat_ref)
            tex_file = ""
            if sm.textured:
                tex = _Ref()
                if api.raw("SUMaterialGetTexture", mat_ref, byref(tex)) == 0 and tex.ptr:
                    tex_file = _string(api, "SUTextureGetFileName", tex)
            rgb = (0.78, 0.78, 0.78)
            if sm.color is not None:
                rgb = (sm.color[0] / 255.0, sm.color[1] / 255.0, sm.color[2] / 255.0)
            info = {"name": sm.name, "textured": sm.textured, "tex_file": tex_file, "rgb": rgb}
            mat_cache[mat_ref.ptr] = info
            return info

        vis_layers: dict[int, bool] = {}

        def is_hidden(elem: _Ref) -> bool:
            flag = c_bool()
            api.ok("SUDrawingElementGetHidden", elem, byref(flag))
            if flag.value:
                return True
            lay = _Ref()
            if api.raw("SUDrawingElementGetLayer", elem, byref(lay)) == 0 and lay.ptr:
                if lay.ptr not in vis_layers:
                    api.ok("SULayerGetVisibility", lay, byref(flag))
                    vis_layers[lay.ptr] = bool(flag.value)
                if not vis_layers[lay.ptr]:
                    return True
            return False

        def walk_node(entities: _Ref, world: np.ndarray, path_idx: list[int], group_hint: str) -> None:
            want_brs3 = path_idx[:2] == [41, 5]
            want_m1 = len(path_idx) >= 1 and path_idx[0] in (9, 32, 33)
            if want_brs3 or want_m1:
                faces = _refs(api, "SUEntitiesGetNumFaces", "SUEntitiesGetFaces", entities)
                if faces:
                    linear = world[:3, :3]
                    trans = world[:3, 3] + CKPT_OFFSET
                    flip_winding = np.linalg.det(linear) < 0.0
                    for face in faces:
                        if is_hidden(api.raw("SUFaceToDrawingElement", face)):
                            continue
                        fmat, bmat = _Ref(), _Ref()
                        api.raw("SUFaceGetFrontMaterial", face, byref(fmat))
                        api.raw("SUFaceGetBackMaterial", face, byref(bmat))
                        f_info = get_mat_info(fmat)
                        b_info = get_mat_info(bmat)
                        use_front = True
                        mat_info = f_info
                        if mat_info is None and b_info is not None:
                            mat_info = b_info
                            use_front = False
                        if mat_info is None:
                            mat_info = {"name": "", "textured": False, "tex_file": "", "rgb": (0.78, 0.78, 0.78)}

                        helper = _Ref()
                        api.ok("SUMeshHelperCreate", byref(helper), face)
                        try:
                            nt, nv, got = c_size_t(), c_size_t(), c_size_t()
                            api.ok("SUMeshHelperGetNumTriangles", helper, byref(nt))
                            api.ok("SUMeshHelperGetNumVertices", helper, byref(nv))
                            if nt.value == 0 or nv.value == 0:
                                continue
                            idx = (c_size_t * (3 * nt.value))()
                            api.ok("SUMeshHelperGetVertexIndices", helper, 3 * nt.value, idx, byref(got))
                            pts = (_Point3D * nv.value)()
                            api.ok("SUMeshHelperGetVertices", helper, nv.value, pts, byref(got))
                            stq = (_Point3D * nv.value)()
                            stq_fn = "SUMeshHelperGetFrontSTQCoords" if use_front else "SUMeshHelperGetBackSTQCoords"
                            api.ok(stq_fn, helper, nv.value, stq, byref(got))

                            verts_local = np.frombuffer(pts, dtype=np.float64).reshape(-1, 3)
                            verts_world = verts_local @ linear.T + trans
                            stq_arr = np.frombuffer(stq, dtype=np.float64).reshape(-1, 3)
                            q = np.where(np.abs(stq_arr[:, 2]) > 1e-12, stq_arr[:, 2], 1.0)
                            uv_arr = np.column_stack([stq_arr[:, 0] / q, stq_arr[:, 1] / q])

                            tri_idx = np.frombuffer(idx, dtype=np.uint64).astype(np.int64).reshape(-1, 3)
                            if flip_winding:
                                tri_idx = tri_idx[:, [0, 2, 1]]

                            tris_v = verts_world[tri_idx].copy()
                            tris_uv = uv_arr[tri_idx].copy()
                            if want_brs3:
                                buckets["BRS_3rd_floor_obj"].append((tris_v, tris_uv, mat_info, group_hint))
                            if want_m1:
                                cent = tris_v.mean(axis=1)
                                in_m1 = np.all((cent >= m1_min) & (cent <= m1_max), axis=1)
                                if np.any(in_m1):
                                    buckets["Main_1st_Floor_obj"].append((tris_v[in_m1], tris_uv[in_m1], mat_info, group_hint))
                        finally:
                            api.raw("SUMeshHelperRelease", byref(helper))

            groups = _refs(api, "SUEntitiesGetNumGroups", "SUEntitiesGetGroups", entities)
            instances = _refs(api, "SUEntitiesGetNumInstances", "SUEntitiesGetInstances", entities)
            child_idx = 0
            for g in groups:
                elem = api.raw("SUGroupToDrawingElement", g)
                if not is_hidden(elem):
                    if len(path_idx) > 0 or child_idx in (9, 32, 33, 41):
                        gname = _string(api, "SUGroupGetName", g)
                        local = _Transformation()
                        api.ok("SUGroupGetTransform", g, byref(local))
                        sub = _Ref()
                        api.ok("SUGroupGetEntities", g, byref(sub))
                        new_hint = gname if gname and not gname.startswith("Group") else group_hint
                        walk_node(sub, world @ _matrix(local), path_idx + [child_idx], new_hint)
                child_idx += 1
            for inst in instances:
                elem = api.raw("SUComponentInstanceToDrawingElement", inst)
                if not is_hidden(elem):
                    if len(path_idx) > 0 or child_idx in (9, 32, 33, 41):
                        iname = _string(api, "SUComponentInstanceGetName", inst)
                        defn = _Ref()
                        api.ok("SUComponentInstanceGetDefinition", inst, byref(defn))
                        dname = _string(api, "SUComponentDefinitionGetName", defn)
                        local = _Transformation()
                        api.ok("SUComponentInstanceGetTransform", inst, byref(local))
                        sub = _Ref()
                        api.ok("SUComponentDefinitionGetEntities", defn, byref(sub))
                        cname = iname or dname
                        new_hint = cname if cname and not cname.startswith("Component") else group_hint
                        walk_node(sub, world @ _matrix(local), path_idx + [child_idx], new_hint)
                child_idx += 1

        root = _Ref()
        api.ok("SUModelGetEntities", model, byref(root))
        walk_node(root, np.eye(4), [], "")

    updated_units = []
    for uid, items in buckets.items():
        if not items:
            continue
        unit_dir = WT_MODELS / uid
        mtl_entries = parse_mtl_entries(unit_dir / "materials.mtl")
        by_mtl: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}
        total_tris = 0
        for tris_v, tris_uv, mat_info, ghint in items:
            mname = match_skp_mat_to_mtl(mat_info, mtl_entries, ghint, uid)
            by_mtl.setdefault(mname, []).append((tris_v, tris_uv))
            total_tris += len(tris_v)

        lines = [
            f"# Corllenium SketchUp R5 Reference Model (capms r5.skp) - {uid}",
            "mtllib materials.mtl",
        ]
        v_offset = 1
        vt_offset = 1
        for mname, chunks in by_mtl.items():
            all_v = np.concatenate([c[0] for c in chunks], axis=0).reshape(-1, 3)
            all_uv = np.concatenate([c[1] for c in chunks], axis=0).reshape(-1, 2)
            for vx, vy, vz in all_v:
                lines.append(f"v {vx:.4f} {vy:.4f} {vz:.4f}")
            for u, v in all_uv:
                lines.append(f"vt {u:.5f} {v:.5f}")
            lines.append(f"g {mname}")
            lines.append(f"usemtl {mname}")
            n_tris = len(all_v) // 3
            for t in range(n_tris):
                i0 = v_offset + 3 * t
                t0_uv = vt_offset + 3 * t
                lines.append(f"f {i0}/{t0_uv} {i0+1}/{t0_uv+1} {i0+2}/{t0_uv+2}")
            v_offset += len(all_v)
            vt_offset += len(all_uv)

        out_bytes = ("\n".join(lines) + "\n").encode("utf-8")
        sync_file_to_all_siege(uid, "skp_ref.obj", out_bytes)
        updated_units.append(uid)
        print(f"  [OK] Extracted {uid}/skp_ref.obj -> {total_tris:,} tris ({len(out_bytes):,} bytes)", flush=True)
    return updated_units


def slice_main_infra_skp_refs() -> list[str]:
    """Slice `Main_Infrustructure_Building/skp_ref.obj` (specifically group [38], `X <= -2090`)
    into the 7 distinct floor Z-bands (`Main_Infrustructure_1st_floor`..`7th_floor_custom` +
    `Main_Infrustructure_7th_floor` alias + `Main_Infrustructure_7th_floor_red_wing`) and map each
    slice into its floor's local `[0..X_max, 0..Y_max, 0..Z_max]` Y-up coordinate frame so that
    `skp_ref.obj` aligns 1:1 with `before.obj` and `after.obj`.
    """
    print("=== Step 1B: Slicing Per-Floor Main_Infrustructure skp_ref.obj Files ===", flush=True)
    whole_path = WT_MODELS / "Main_Infrustructure_Building/skp_ref.obj"
    whole_mesh = read_obj(whole_path)
    pts_w = whole_mesh.positions[whole_mesh.face_v]
    cent_w = pts_w.mean(axis=1)

    # Ensure `Main_Infrustructure_7th_floor` alias folder exists and has all base files from `Main_Infrustructure_7th_floor_custom`
    src_7f = WT_MODELS / "Main_Infrustructure_7th_floor_custom"
    for wt in SIEGE_WTS:
        for sub in ("dashboard/public/models", "dashboard/deploy-build/public/models"):
            dst_7f = wt / sub / "Main_Infrustructure_7th_floor"
            if src_7f.exists():
                dst_7f.mkdir(parents=True, exist_ok=True)
                for item in src_7f.iterdir():
                    if item.is_file() and not (dst_7f / item.name).exists():
                        shutil.copy2(item, dst_7f / item.name)

    z0 = 1188.9799
    inch_per_m = 39.37007874
    floor_specs = [
        ("Main_Infrustructure_1st_floor", 0.0, 6.0),
        ("Main_Infrustructure_2nd_floor", 5.0, 12.0),
        ("Main_Infrustructure_3rd_floor", 10.0, 18.0),
        ("Main_Infrustructure_4th_floor", 15.0, 24.0),
        ("Main_Infrustructure_5th_floor", 20.0, 28.0),
        ("Main_Infrustructure_6th_floor", 25.0, 36.0),
        ("Main_Infrustructure_7th_floor_custom", 28.0, 37.0),
        ("Main_Infrustructure_7th_floor", 28.0, 37.0),
        ("Main_Infrustructure_7th_floor_red_wing", 28.0, 37.0),
    ]

    updated_units = []
    for unit_id, b0, b1 in floor_specs:
        u_dir = WT_MODELS / unit_id
        before_path = u_dir / "before.obj"
        if not before_path.exists():
            continue
        b_mesh = read_obj(before_path)
        b_min = b_mesh.positions.min(axis=0)
        b_max = b_mesh.positions.max(axis=0)

        zmin = z0 + b0 * inch_per_m - 2.0
        zmax = z0 + b1 * inch_per_m + 2.0
        # Select faces in this floor's Z-band within group [38] (X <= -2090)
        in_band = (cent_w[:, 2] >= zmin) & (cent_w[:, 2] <= zmax) & (cent_w[:, 0] <= -2090.0)
        if unit_id == "Main_Infrustructure_7th_floor_red_wing":
            in_band &= cent_w[:, 0] <= -2500.0

        drop_mask = ~in_band
        sliced = remove_faces(whole_mesh, drop_mask)[0]
        sliced, _ = compact_mesh(sliced, {})

        # Map CKPT17 Z-up inches (X_ckpt, Y_ckpt, Z_ckpt) into the floor's local Y-up block frame [b_min..b_max]:
        # X_ckpt -> X_mc, Z_ckpt -> Y_mc (up), -Y_ckpt -> Z_mc (right-handed rotation around X by -90 deg: no winding flip!)
        s_min = sliced.positions.min(axis=0)
        s_max = sliced.positions.max(axis=0)
        span_s = np.maximum(s_max - s_min, 1e-6)
        span_b = np.maximum(b_max - b_min, 1e-6)

        pos_new = np.empty_like(sliced.positions)
        pos_new[:, 0] = b_min[0] + (sliced.positions[:, 0] - s_min[0]) / span_s[0] * span_b[0]
        pos_new[:, 1] = b_min[1] + (sliced.positions[:, 2] - s_min[2]) / span_s[2] * span_b[1]
        pos_new[:, 2] = b_min[2] + (s_max[1] - sliced.positions[:, 1]) / span_s[1] * span_b[2]
        sliced.positions = np.round(pos_new, 4)

        out_bytes = compact_obj_bytes(sliced)
        sync_file_to_all_siege(unit_id, "skp_ref.obj", out_bytes)
        updated_units.append(unit_id)
        print(
            f"  [OK] Sliced {unit_id}/skp_ref.obj -> {sliced.n_faces:,} tris | bbox={sliced.positions.min(axis=0).round(1).tolist()}..{sliced.positions.max(axis=0).round(1).tolist()}",
            flush=True,
        )
    return updated_units


def merge_ckpt17_main_3rd_floor_before() -> None:
    """Combine Checkpoint-17 `Main_3RD_Floor_obj.obj` (624 tris) + `Main_3RD_Floor_obj1.obj` (31,958 tris)
    from `04-Corllenium-Building-Model-Repair/Exports/Unity-Buildings-20261014/ByBuilding/Main/Model-Floor_03/`
    into `Main_3RD_Floor_obj/before.obj` (32,582 Checkpoint-17 triangles covering the entire 3rd floor).
    """
    print("=== Step 2A: Merging Checkpoint-17 Main_3RD_Floor_obj (624) + Main_3RD_Floor_obj1 (31,958) ===", flush=True)
    orig_dir = REPO04_ORIG / "Main/Model-Floor_03"
    m0 = read_obj(orig_dir / "Main_3RD_Floor_obj.obj")
    m0.positions = np.round(convert_unity_to_ckpt17_coords(m0.positions), 4)
    mtl0 = parse_mtl(orig_dir / "Main_3RD_Floor_obj.mtl")
    m0 = prepare_building_materials(m0, mtl0)

    m1 = read_obj(orig_dir / "Main_3RD_Floor_obj1.obj")
    m1.positions = np.round(convert_unity_to_ckpt17_coords(m1.positions), 4)
    mtl1 = parse_mtl(orig_dir / "Main_3RD_Floor_obj1.mtl")
    m1 = prepare_building_materials(m1, mtl1)

    # Merge materials and textures into Main_3RD_Floor_obj/materials.mtl
    u_dir0 = WT_MODELS / "Main_3RD_Floor_obj"
    u_dir1 = WT_MODELS / "Main_3RD_Floor_obj1"
    if u_dir1.exists():
        for f_item in u_dir1.iterdir():
            if f_item.suffix.lower() in (".png", ".jpg") and not (u_dir0 / f_item.name).exists():
                for wt in SIEGE_WTS:
                    for sub in ("dashboard/public/models", "dashboard/deploy-build/public/models"):
                        td = wt / sub / "Main_3RD_Floor_obj"
                        if td.exists():
                            shutil.copy2(f_item, td / f_item.name)
        mtl0_txt = (u_dir0 / "materials.mtl").read_text(encoding="utf-8", errors="ignore") if (u_dir0 / "materials.mtl").exists() else ""
        mtl1_txt = (u_dir1 / "materials.mtl").read_text(encoding="utf-8", errors="ignore") if (u_dir1 / "materials.mtl").exists() else ""
        combined_mtl = mtl0_txt.rstrip() + "\n\n" + mtl1_txt.lstrip()
        sync_file_to_all_siege("Main_3RD_Floor_obj", "materials.mtl", combined_mtl.encode("utf-8"))

    # Combine m0 and m1 into a single MeshData
    mat_list = list(m0.materials)
    mat_map1 = np.zeros(len(m1.materials), dtype=np.int64)
    for i, mname in enumerate(m1.materials):
        if mname not in mat_list:
            mat_list.append(mname)
        mat_map1[i] = mat_list.index(mname)

    v_off = len(m0.positions)
    uv0 = m0.uvs if (m0.uvs is not None and len(m0.uvs) > 0) else np.zeros((1, 2), dtype=np.float64)
    uv1 = m1.uvs if (m1.uvs is not None and len(m1.uvs) > 0) else np.zeros((1, 2), dtype=np.float64)
    vt_off = len(uv0)
    fvt0 = m0.face_vt if (m0.face_vt is not None and len(m0.face_vt) == m0.n_faces and (m0.face_vt >= 0).all()) else np.zeros((m0.n_faces, 3), dtype=np.int64)
    fvt1 = (m1.face_vt + vt_off) if (m1.face_vt is not None and len(m1.face_vt) == m1.n_faces and (m1.face_vt >= 0).all()) else np.zeros((m1.n_faces, 3), dtype=np.int64)

    import copy
    combined = copy.copy(m0)
    combined.positions = np.vstack([m0.positions, m1.positions])
    combined.uvs = np.vstack([uv0, uv1])
    combined.normals = np.zeros((0, 3), dtype=np.float64)
    combined.face_v = np.vstack([m0.face_v, m1.face_v + v_off])
    combined.face_vt = np.vstack([fvt0, fvt1])
    combined.face_vn = np.full((m0.n_faces + m1.n_faces, 3), -1, dtype=np.int64)
    combined.face_material = np.concatenate([m0.face_material, mat_map1[m1.face_material]])
    combined.materials = mat_list
    combined.face_line = np.arange(1, m0.n_faces + m1.n_faces + 1, dtype=np.int64)
    comp_before = compact_obj_bytes(combined)
    sync_file_to_all_siege("Main_3RD_Floor_obj", "before.obj", comp_before)
    err_counts = write_errors_json(combined, u_dir0 / "errors_before.json")
    sync_file_to_all_siege("Main_3RD_Floor_obj", "errors_before.json", (u_dir0 / "errors_before.json").read_bytes())
    print(f"  [OK] Merged Main_3RD_Floor_obj/before.obj -> {combined.n_faces:,} Checkpoint-17 tris | errors_before={err_counts}", flush=True)


def repair_flagged_unit(unit_id: str, bldg_folder: str, floor_folder: str, aliases: list[str] | None = None) -> None:
    """Run Pure Reference-Guarded Engine Repair on `before.obj` for `unit_id`, guarded by `skp_ref.obj`:
    1. Loads `skp_ref.obj` and verifies `before.obj` faces via `EmbreeCaster` (`t <= 1.5 in`, `|dot| >= 0.88`).
    2. Deduplicates coincident triangles using `(sorted_vertices, quantized_normal)` so opposite-normal
       faces are never collapsed by vertex rounding.
    3. Runs `remove_coplanar_overlaps(out, overlap_ratio=0.08, drop_only=True)` to remove coplanar wall-crack
       overlaps, then restores any `ref_verified` or ceiling-soffit face (`fn_z < -0.85`) that was uncovered
       by `> 0.8 in`.
    """
    u_dir = WT_MODELS / unit_id
    before_path = u_dir / "before.obj"
    skp_ref_path = u_dir / "skp_ref.obj"
    if not before_path.exists():
        print(f"  [SKIP] {unit_id}: before.obj not found", flush=True)
        return

    b_mesh = read_obj(before_path)
    n_before = b_mesh.n_faces
    pts_b = b_mesh.positions[b_mesh.face_v]
    fn_b = face_normals(b_mesh.positions, b_mesh.face_v, np.ones(b_mesh.n_faces, dtype=bool))
    dbl_area = np.linalg.norm(np.cross(pts_b[:, 1] - pts_b[:, 0], pts_b[:, 2] - pts_b[:, 0]), axis=1)
    ok_b = (~np.isnan(fn_b).any(axis=1)) & (np.linalg.norm(fn_b, axis=1) > 0.5) & (dbl_area > 1e-5)
    cent_b = pts_b.mean(axis=1)

    # 1. Reference Guard via EmbreeCaster on skp_ref.obj
    ref_verified = np.zeros(b_mesh.n_faces, dtype=bool)
    n_skp = 0
    if skp_ref_path.exists():
        skp = read_obj(skp_ref_path)
        n_skp = skp.n_faces
        fn_s = face_normals(skp.positions, skp.face_v, np.ones(skp.n_faces, dtype=bool))
        ok_s = (~np.isnan(fn_s).any(axis=1)) & (np.linalg.norm(fn_s, axis=1) > 0.5)
        s_valid_fids = np.flatnonzero(ok_s)
        if len(s_valid_fids) > 0:
            caster_s = EmbreeCaster(skp.positions, skp.face_v[s_valid_fids])
            hs1, ts1 = caster_s.first_hit(cent_b - 0.35 * fn_b, fn_b)
            hs2, ts2 = caster_s.first_hit(cent_b + 0.35 * fn_b, -fn_b)
            use_s1 = ts1 <= ts2
            t_s = np.where(use_s1, ts1, ts2)
            h_s = np.where(use_s1, hs1, hs2)
            for bf in np.flatnonzero(ok_b & (t_s <= 1.5) & (h_s >= 0)):
                sf = int(s_valid_fids[int(h_s[bf])])
                if abs(float(np.dot(fn_b[bf], fn_s[sf]))) >= 0.88:
                    ref_verified[bf] = True

    # 2. Normal-aware deduplication of exact coincident triangles (preferring ref_verified faces)
    q_pts = np.round(pts_b * 200.0).astype(np.int64)
    s_pts = np.sort(q_pts, axis=1).reshape(b_mesh.n_faces, 9)
    q_fn = np.round(fn_b * 10.0).astype(np.int64)
    flat_keys = np.hstack([s_pts, q_fn])

    # Sort so ref_verified faces come first when deduplicating identical (vertices, normal) keys
    order = np.argsort(~ref_verified, kind="stable")
    _, unique_pos = np.unique(flat_keys[order], axis=0, return_index=True)
    keep = np.zeros(b_mesh.n_faces, dtype=bool)
    keep[order[unique_pos]] = True
    keep &= ok_b

    # Backup all ref_verified and downward-facing ceiling soffit faces before remove_coplanar_overlaps
    prot_fids = np.flatnonzero(keep & (ref_verified | (fn_b[:, 2] < -0.85)))
    prot_backup = None
    if len(prot_fids) > 0:
        pts_prot = b_mesh.positions[b_mesh.face_v[prot_fids]].copy()
        fn_prot = fn_b[prot_fids].copy()
        uv_prot = (
            b_mesh.uvs[b_mesh.face_vt[prot_fids]].copy()
            if (b_mesh.uvs is not None and len(b_mesh.uvs) > 0 and (b_mesh.face_vt >= 0).all())
            else None
        )
        mat_prot = b_mesh.face_material[prot_fids].copy()
        prot_backup = (pts_prot, fn_prot, uv_prot, mat_prot)

    drop_mask = ~keep
    out = remove_faces(b_mesh, drop_mask)[0] if np.any(drop_mask) else b_mesh
    out, _ = compact_mesh(out, {})

    # 3. Run Engine remove_coplanar_overlaps
    try:
        out, ov_dropped = remove_coplanar_overlaps(out, overlap_ratio=0.08, drop_only=True)
    except Exception as e:
        print(f"  [WARN] remove_coplanar_overlaps on {unit_id}: {e}", flush=True)
        ov_dropped = 0

    # 4. Restore any ceiling soffit or reference-verified surface that was left uncovered (> 0.8 in)
    restored_count = 0
    if prot_backup is not None and out.n_faces > 0:
        pts_prot, fn_prot, uv_prot, mat_prot = prot_backup
        fn_cur = face_normals(out.positions, out.face_v, np.ones(out.n_faces, dtype=bool))
        ok_cur = np.flatnonzero((~np.isnan(fn_cur).any(axis=1)) & (np.linalg.norm(fn_cur, axis=1) > 0.5))
        if len(ok_cur) > 0:
            c_cur = EmbreeCaster(out.positions, out.face_v[ok_cur])
            cent_p = pts_prot.mean(axis=1)
            _, t1 = c_cur.first_hit(cent_p - 0.35 * fn_prot, fn_prot)
            _, t2 = c_cur.first_hit(cent_p + 0.35 * fn_prot, -fn_prot)
            miss = np.flatnonzero(np.minimum(t1, t2) > 0.8)
        else:
            miss = np.arange(len(pts_prot))
        if len(miss) > 0:
            restored_count = int(len(miss))
            add_p = pts_prot[miss].reshape(-1, 3)
            v_b = len(out.positions)
            new_fv = np.arange(len(miss) * 3, dtype=np.int64).reshape(-1, 3) + v_b
            out.positions = np.vstack([out.positions, add_p])
            out.face_v = np.vstack([out.face_v, new_fv])
            if uv_prot is not None and out.uvs is not None:
                add_u = uv_prot[miss].reshape(-1, 2)
                vt_b = len(out.uvs)
                new_fvt = np.arange(len(miss) * 3, dtype=np.int64).reshape(-1, 3) + vt_b
                out.uvs = np.vstack([out.uvs, add_u])
                out.face_vt = np.vstack([out.face_vt, new_fvt])
            out.face_vn = np.vstack([out.face_vn, np.full((len(miss), 3), -1, dtype=np.int64)])
            out.face_material = np.concatenate([out.face_material, mat_prot[miss]])
            out.face_line = np.concatenate([out.face_line, np.zeros(len(miss), dtype=np.int64)])

    out, _ = compact_mesh(out, {})
    fn_out = face_normals(out.positions, out.face_v, np.ones(out.n_faces, dtype=bool))
    out.normals = np.round(fn_out, 4)
    out.face_vn = np.repeat(np.arange(out.n_faces, dtype=np.int64)[:, None], 3, axis=1)

    # 5. Guarantee 0.000% R5 coverage loss under 4-point barycentric EmbreeCaster check
    if skp_ref_path.exists() and out.n_faces > 0:
        skp = read_obj(skp_ref_path)
        bary = np.array([[1 / 3, 1 / 3, 1 / 3], [0.6, 0.2, 0.2], [0.2, 0.6, 0.2], [0.2, 0.2, 0.6]])
        rt = skp.positions[skp.face_v]
        cross_r = np.cross(rt[:, 1] - rt[:, 0], rt[:, 2] - rt[:, 0])
        mag_r = np.linalg.norm(cross_r, axis=1)
        valid_r = mag_r > 1e-12
        if valid_r.any():
            rt = rt[valid_r]
            n_r = cross_r[valid_r] / mag_r[valid_r, None]
            center = (skp.positions.min(axis=0) + skp.positions.max(axis=0)) / 2.0
            p_samples = np.einsum("sb,fbk->fsk", bary, rt).reshape(-1, 3) - center
            n_samples = np.repeat(n_r, 4, axis=0)

            def _match_samples(mesh_t: MeshData) -> tuple[np.ndarray, np.ndarray]:
                mt = mesh_t.positions[mesh_t.face_v]
                on = np.cross(mt[:, 1] - mt[:, 0], mt[:, 2] - mt[:, 0])
                om = np.linalg.norm(on, axis=1)
                good = om > 1e-12
                on[good] /= om[good, None]
                ids = np.flatnonzero(good)
                caster = EmbreeCaster(mesh_t.positions - center, mesh_t.face_v[ids])
                ia, ta = caster.first_hit(p_samples + 2.0 * n_samples, -n_samples)
                ib, tb = caster.first_hit(p_samples - 2.0 * n_samples, n_samples)
                res = np.zeros(len(p_samples), dtype=bool)
                hit_f = np.full(len(p_samples), -1, dtype=np.int64)
                for ix, t in ((ia, ta), (ib, tb)):
                    cand = np.flatnonzero((ix >= 0) & (np.abs(t - 2.0) <= 1.5))
                    fids = ids[ix[cand]]
                    dots = np.abs(np.einsum("ij,ij->i", n_samples[cand], on[fids])) >= 0.88
                    good_c = cand[dots]
                    res[good_c] = True
                    hit_f[good_c] = fids[dots]
                return res, hit_f

            pass_b, bf_b = _match_samples(b_mesh)
            pass_a, _ = _match_samples(out)
            restore_fids = np.unique(bf_b[pass_b & (~pass_a)])
            restore_fids = restore_fids[restore_fids >= 0]
            if len(restore_fids) > 0:
                restored_count += int(len(restore_fids))
                mat_list = list(out.materials)
                mapped_mats = np.zeros(len(restore_fids), dtype=np.int64)
                for idx_i, fid in enumerate(restore_fids):
                    b_mid = int(b_mesh.face_material[fid])
                    mname = b_mesh.materials[b_mid] if (0 <= b_mid < len(b_mesh.materials)) else (mat_list[0] if mat_list else "default")
                    if mname not in mat_list:
                        mat_list.append(mname)
                    mapped_mats[idx_i] = mat_list.index(mname)
                out.materials = mat_list
                pts_add = b_mesh.positions[b_mesh.face_v[restore_fids]].reshape(-1, 3)
                v_b = len(out.positions)
                new_fv = np.arange(len(restore_fids) * 3, dtype=np.int64).reshape(-1, 3) + v_b
                out.positions = np.vstack([out.positions, pts_add])
                out.face_v = np.vstack([out.face_v, new_fv])
                if b_mesh.uvs is not None and len(b_mesh.uvs) > 0 and out.uvs is not None and (b_mesh.face_vt[restore_fids] >= 0).all():
                    uv_add = b_mesh.uvs[b_mesh.face_vt[restore_fids]].reshape(-1, 2)
                    vt_b = len(out.uvs)
                    new_fvt = np.arange(len(restore_fids) * 3, dtype=np.int64).reshape(-1, 3) + vt_b
                    out.uvs = np.vstack([out.uvs, uv_add])
                    out.face_vt = np.vstack([out.face_vt, new_fvt])
                out.face_vn = np.vstack([out.face_vn, np.full((len(restore_fids), 3), -1, dtype=np.int64)])
                out.face_material = np.concatenate([out.face_material, mapped_mats])
                out.face_line = np.concatenate([out.face_line, np.zeros(len(restore_fids), dtype=np.int64)])
                out, _ = compact_mesh(out, {})
                fn_out = face_normals(out.positions, out.face_v, np.ones(out.n_faces, dtype=bool))
                out.normals = np.round(fn_out, 4)
                out.face_vn = np.repeat(np.arange(out.n_faces, dtype=np.int64)[:, None], 3, axis=1)

    comp_bytes = compact_obj_bytes(out)
    target_ids = [unit_id] + (aliases or [])
    for tid in target_ids:
        sync_file_to_all_siege(tid, "after.obj", comp_bytes)

    exp_dir = REPO04_EXPORTS / bldg_folder / floor_folder
    if exp_dir.exists():
        (exp_dir / f"{unit_id}.fixed.obj").write_bytes(comp_bytes)
        rep_path = exp_dir / f"{unit_id}.report.json"
        rep_data = {}
        if rep_path.exists():
            try:
                rep_data = json.loads(rep_path.read_text(encoding="utf-8"))
            except Exception:
                rep_data = {}
        rep_data.update({
            "unit": unit_id,
            "building": bldg_folder.upper(),
            "tris_before": int(n_before),
            "tris_after": int(out.n_faces),
            "skp_ref_tris": int(n_skp),
            "ref_verified_faces": int(ref_verified.sum()),
            "restored_protected_faces": int(restored_count),
        })
        rep_path.write_text(json.dumps(rep_data, indent=2) + "\n", encoding="utf-8")

    print(
        f"  [REPAIRED] {unit_id}: before={n_before:,} (skp_ref={n_skp:,}, ref_verified={int(ref_verified.sum()):,}) -> after={out.n_faces:,} tris (ov_dropped={ov_dropped:,}, restored={restored_count:,}, {len(comp_bytes):,} bytes)",
        flush=True,
    )


def generate_missing_and_updated_skp_ref_errors(force_units: list[str]) -> None:
    print("=== Step 3: Generating & Syncing errors_skp_ref.json Across All Reference Units ===", flush=True)
    force_set = set(force_units)
    count_done = 0
    for u_dir in sorted(WT_MODELS.iterdir()):
        if not u_dir.is_dir():
            continue
        skp_p = u_dir / "skp_ref.obj"
        if not skp_p.exists():
            continue
        err_p = u_dir / "errors_skp_ref.json"
        uid = u_dir.name
        if uid in force_set or not err_p.exists():
            mesh = read_obj(skp_p)
            counts = write_errors_json(mesh, err_p)
            print(f"  [ERRORS_SKP_REF] {uid}: {mesh.n_faces:,} tris -> {counts}", flush=True)
        # Always sync errors_skp_ref.json across all Siege worktrees & deploy-build
        if err_p.exists():
            sync_file_to_all_siege(uid, "errors_skp_ref.json", err_p.read_bytes())
            count_done += 1
    print(f"  [OK] Synced errors_skp_ref.json for {count_done} units across all Siege worktrees.", flush=True)


if __name__ == "__main__":
    updated_a = extract_brs3_and_main1_from_skp()
    updated_b = slice_main_infra_skp_refs()
    merge_ckpt17_main_3rd_floor_before()

    print("\n=== Step 2B: Running Pure Reference-Guarded Engine Repair on Flagged Non-Architecture Floors ===", flush=True)
    flagged = [
        ("Main_3RD_Floor_obj", "Main", "Model-Floor_03", []),
        ("Main_3RD_Floor_obj1", "Main", "Model-Floor_03", []),
        ("Main_4th_Floor_obj", "Main", "Model-Floor_04", []),
        ("PE_2nd_Floor_obj", "PE", "Model-Floor_02", ["PE_2nd_Floor"]),
        ("BRS_1st_floor_obj", "BRS", "Model-Floor_01", []),
        ("BRS_3rd_floor_obj", "BRS", "Model-Floor_03", []),
        ("Gymnasium_4th_floor_obj", "Gymnasium", "Model-Floor_04", []),
        ("SHIELD_FRONTAGE", "Site", "Model-Shield_Frontage", []),
    ]
    for uid, b_folder, f_folder, aliases in flagged:
        repair_flagged_unit(uid, b_folder, f_folder, aliases)

    generate_missing_and_updated_skp_ref_errors(updated_a + updated_b)

    print("\n=== Step 4: Staging Updated Buildings into Blender 5.1 (02_STAGING_DEVELOPMENT) ===", flush=True)
    for bldg in ("MAIN", "PE", "BRS", "GYMNASIUM", "SITE"):
        try:
            r = apply_repaired_building_to_blender_staging(repair_repo_root=REPO04_ROOT, building=bldg)
            print(f"  [BLENDER 5.1] Staged {bldg} -> LOD0 = {r.get('lod0_triangles', 0):,} tris", flush=True)
        except Exception as exc:
            print(f"  [WARN] Blender staging {bldg}: {exc}", flush=True)

    from organize_dashboard_seed import main as regen_seed
    regen_seed()
    for wt in SIEGE_WTS[1:]:
        sd_src = PRIMARY_SIEGE / "dashboard/lib/buildings/seedData.ts"
        sd_dst = wt / "dashboard/lib/buildings/seedData.ts"
        if sd_dst.parent.exists():
            shutil.copy2(sd_src, sd_dst)
    print("=== All Steps Complete! ===", flush=True)
