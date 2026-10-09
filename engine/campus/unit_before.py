"""A campus unit's BEFORE for the Validator (P1-H1 item 9).

The Validator takes one snapshot folder (`validate --before <dir>`: one .obj, `materials.mtl`, textures), but a
campus unit (data/campus/campus_map.json) is made of several members, and a member is a whole frozen group
("faces": "all") or one band of a group split between floors ("band N" with `z_range`; a face belongs to the band
by its centre z, lo <= z < hi, as `error_export.member_mask` and the inventory split them).

`build_unit_before` reads each member's frozen snapshot (data/campus/source.json names the folders; the OBJ's
sha256 must be the frozen one), keeps the member's faces, and writes `<out>/<unit>.obj` and `<out>/materials.mtl`:
a folder `validate --before` takes as it is. Nothing is repaired or changed: the faces, their vertices, UVs,
normals and materials are the snapshots' own. Textures are referenced where they lie (absolute `map_Kd`), and
copied to `<out>/tex/` only when `copy_textures` is set. Two members that give one material name two different
definitions are refused: the merged MTL could not keep both.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import numpy as np

from engine.campus.error_export import member_mask
from engine.io.mtl import parse_mtl
from engine.io.obj_reader import read_obj
from engine.io.obj_writer import write_obj
from engine.io.protected import refuse_protected
from engine.io.snapshot import sha256_file
from engine.model import MeshData


def _band_name(member: dict) -> str:
    return "all" if member.get("faces", "all") == "all" else str(member["faces"])


def _snapshot_of(source: dict, group: str) -> dict:
    for row in source["snapshots"]:
        if row["group"] == group:
            return row
    raise ValueError(f"{group}: no frozen snapshot in source.json")


def _compact(positions, uvs, normals, face_v, face_vt, face_vn):
    """The kept faces with only the vertices, UVs and normals they use, indices remapped (-1 stays -1)."""
    def pick(table, index):
        used = np.unique(index[index >= 0])
        remap = np.full(len(table) + 1, -1, np.int64)
        remap[used] = np.arange(len(used))
        return table[used], np.where(index >= 0, remap[np.where(index >= 0, index, len(table))], -1)
    positions, face_v = pick(positions, face_v)
    uvs, face_vt = pick(uvs, face_vt)
    normals, face_vn = pick(normals, face_vn)
    return positions, uvs, normals, face_v, face_vt, face_vn


def build_unit_before(campus_map: dict, source: dict, unit: str, out_dir, *, copy_textures: bool = False) -> dict:
    """Write unit `unit`'s BEFORE folder (see the module docstring) and return a report:
    {"unit", "obj", "mtl", "obj_sha256", "faces", "members": [{"group", "band", "faces", "expected", ...}],
    "matches_campus_map", "textures": "referenced" | "copied", "missing_textures"}.
    Raises ValueError for an unknown unit, a protected `out_dir`, a snapshot whose OBJ is not the frozen one, or a
    material name defined two ways. `matches_campus_map` is False when a member's kept face count differs from the
    `tris` the campus map gives it (reported, not hidden: the BEFORE is still what the snapshots hold)."""
    out_dir = Path(out_dir)
    refuse_protected(out_dir)
    rows = [u for u in campus_map["units"] if u["unit"] == unit]
    if not rows:
        raise ValueError(f"no unit {unit!r} in the campus map")
    members = rows[0]["members"]

    parts = []                                    # (mesh, kept mask, snapshot folder)
    report_members = []
    for member in members:
        snap = _snapshot_of(source, member["group"])
        folder = Path(snap["dir"])
        obj = folder / snap["file"]
        frozen = snap.get("sha256")
        if member.get("sha256") and frozen and member["sha256"] != frozen:
            raise ValueError(f"{member['group']}: sha256 differs between campus_map.json and source.json")
        actual = sha256_file(obj)
        if frozen and actual != frozen:
            raise ValueError(f"{obj}: sha256 {actual[:12]} is not the frozen {frozen[:12]}")
        mesh = read_obj(obj)
        cz = mesh.positions[mesh.face_v][:, :, 2].mean(axis=1)
        keep = member_mask(member, cz)
        parts.append((mesh, keep, folder))
        report_members.append({"group": member["group"], "band": _band_name(member), "faces": int(keep.sum()),
                               "expected": member.get("tris"), "snapshot": str(folder), "sha256": actual})

    # the faces, side by side, in member order
    materials: list[str] = []
    positions, uvs, normals, f_v, f_vt, f_vn, f_mat = [], [], [], [], [], [], []
    voff = toff = noff = 0
    mtl_of: dict[str, tuple[list[str], Path, str | None]] = {}     # name -> (lines, folder, map_Kd)
    texture_sha: dict[Path, str] = {}

    def texture_id(path: Path) -> str | None:
        if not path.is_file():
            return None
        if path not in texture_sha:
            texture_sha[path] = sha256_file(path)
        return texture_sha[path]

    for mesh, keep, folder in parts:
        pos, uv, nrm, fv, fvt, fvn = _compact(mesh.positions, mesh.uvs, mesh.normals, mesh.face_v[keep],
                                              mesh.face_vt[keep], mesh.face_vn[keep])
        mtl = parse_mtl(folder / "materials.mtl") if (folder / "materials.mtl").is_file() else {}
        local = np.full(len(mesh.materials) + 1, -1, np.int64)
        for k in sorted({int(m) for m in mesh.face_material[keep] if m >= 0}):
            name = mesh.materials[k]
            if name in mtl:
                entry = mtl[name]
                here = (entry.lines, folder, entry.map_kd)
                if name in mtl_of:
                    lines, other, tex = mtl_of[name]
                    same_tex = (tex is None and entry.map_kd is None) or (
                        tex is not None and entry.map_kd is not None
                        and texture_id(other / tex.replace("\\", "/")) == texture_id(folder / entry.map_kd.replace("\\", "/")))
                    if lines != entry.lines or not same_tex:
                        raise ValueError(f"material {name!r} is defined two ways by the unit's members "
                                         f"({other} and {folder}): the merged MTL could not keep both")
                else:
                    mtl_of[name] = here
            if name not in materials:
                materials.append(name)
            local[k] = materials.index(name)
        fm = mesh.face_material[keep]
        f_mat.append(np.where(fm >= 0, local[np.where(fm >= 0, fm, len(mesh.materials))], -1))
        positions.append(pos)
        uvs.append(uv)
        normals.append(nrm)
        f_v.append(fv + voff)
        f_vt.append(np.where(fvt >= 0, fvt + toff, -1))
        f_vn.append(np.where(fvn >= 0, fvn + noff, -1))
        voff, toff, noff = voff + len(pos), toff + len(uv), noff + len(nrm)

    def cat(arrays, shape):
        arrays = [a for a in arrays if len(a)]
        return np.concatenate(arrays) if arrays else np.zeros(shape)
    n_faces = sum(len(a) for a in f_v)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", unit)
    merged = MeshData(
        name=safe, positions=cat(positions, (0, 3)), uvs=cat(uvs, (0, 2)), normals=cat(normals, (0, 3)),
        face_v=cat(f_v, (0, 3)).astype(np.int64), face_vt=cat(f_vt, (0, 3)).astype(np.int64),
        face_vn=cat(f_vn, (0, 3)).astype(np.int64), face_material=cat(f_mat, (0,)).astype(np.int64),
        face_line=np.zeros(n_faces, np.int64), materials=materials, mtllib="materials.mtl",
        coord_decimals=max(m.coord_decimals for m, _k, _f in parts),
        sig_digits=max(m.sig_digits for m, _k, _f in parts))

    out_dir.mkdir(parents=True, exist_ok=True)
    obj_path, mtl_path = out_dir / f"{safe}.obj", out_dir / "materials.mtl"
    write_obj(merged, obj_path)
    text, missing, copied = [], 0, {}
    for name in materials:
        if name not in mtl_of:
            continue
        lines, folder, map_kd = mtl_of[name]
        text.append(f"newmtl {name}")
        for line in lines:
            if map_kd is not None and line.startswith("map_Kd "):
                src = folder / map_kd.replace("\\", "/")
                missing += 0 if src.is_file() else 1
                if copy_textures:
                    dest = out_dir / "tex" / src.name
                    if src.is_file():
                        if dest.exists() and sha256_file(dest) != sha256_file(src):
                            raise ValueError(f"two different textures are both called {src.name}")
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        if not dest.exists():
                            shutil.copyfile(src, dest)
                    line = f"map_Kd tex/{src.name}"
                else:
                    line = f"map_Kd {src.resolve().as_posix()}"
            text.append(line)
        text.append("")
    mtl_path.write_text("\n".join(text), encoding="utf-8", newline="\n")

    matches = all(m["expected"] is None or m["expected"] == m["faces"] for m in report_members)
    return {"unit": unit, "obj": str(obj_path), "mtl": str(mtl_path), "obj_sha256": sha256_file(obj_path),
            "faces": int(merged.n_faces), "members": report_members, "matches_campus_map": bool(matches),
            "expected_faces": rows[0].get("tris"), "textures": "copied" if copy_textures else "referenced",
            "missing_textures": missing}
