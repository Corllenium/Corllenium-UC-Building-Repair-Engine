from pathlib import Path

import numpy as np

from engine.model import MeshData


def _num(x: float, decimals: int) -> str:
    s = f"{x:.{decimals}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def write_obj(mesh: MeshData, path: Path) -> None:
    d = max(mesh.coord_decimals, 1)
    out = [f"# {mesh.name}"]
    if mesh.mtllib:
        out.append(f"mtllib {mesh.mtllib}")
    out.append(f"o {mesh.name}")
    out += ["v " + " ".join(_num(c, d) for c in p) for p in mesh.positions]
    out += ["vt " + " ".join(_num(c, 6) for c in t) for t in mesh.uvs]
    out += ["vn " + " ".join(_num(c, 6) for c in n) for n in mesh.normals]
    current = None
    for f in range(mesh.n_faces):
        mat = int(mesh.face_material[f])
        if mat != current and mat >= 0:
            out.append(f"usemtl {mesh.materials[mat]}")
        current = mat
        toks = []
        for v, t, n in zip(mesh.face_v[f], mesh.face_vt[f], mesh.face_vn[f]):
            if t >= 0 and n >= 0:
                toks.append(f"{v + 1}/{t + 1}/{n + 1}")
            elif t >= 0:
                toks.append(f"{v + 1}/{t + 1}")
            elif n >= 0:
                toks.append(f"{v + 1}//{n + 1}")
            else:
                toks.append(str(v + 1))
        out.append("f " + " ".join(toks))
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")


def write_obj_polygons(mesh: MeshData, rings: dict[int, dict], path: Path) -> None:
    """Write `mesh` as a polygon (ngon) OBJ: a viewer/documentation artifact showing only real
    shape edges, never the file Unity imports (that stays `write_obj`'s triangulated output, and
    `read_obj` refuses this file's n-gon lines on purpose -- OBJ triangles only, by design).

    `rings` is `engine.fixes.merge.MergeResult.rings` (or an equivalent mapping): for every output
    face index whose entry is HOLE-FREE (`inners` empty), ALL rows sharing that entry OBJECT
    (`is`, not just equal content) collapse into ONE `f` line of `outer`'s vertices, in order,
    position-only (no vt/vn -- an arbitrary n-gon has no single triangle's per-corner attribute
    set); the first such row decides where the line lands and which `usemtl` block it falls in.

    A region WITH holes keeps its triangles: an OBJ `f` line is a single loop and cannot carry an
    inner one, so its `inners` are for the SketchUp export, not for this file. Rows absent from
    `rings` (multi-piece regions, faces copied through unmerged) are triangles too, identical to
    `write_obj`."""
    d = max(mesh.coord_decimals, 1)
    out = [f"# {mesh.name} (polygon export: real shape edges only -- not the Unity file)"]
    if mesh.mtllib:
        out.append(f"mtllib {mesh.mtllib}")
    out.append(f"o {mesh.name}")
    out += ["v " + " ".join(_num(c, d) for c in p) for p in mesh.positions]
    out += ["vt " + " ".join(_num(c, 6) for c in t) for t in mesh.uvs]
    out += ["vn " + " ".join(_num(c, 6) for c in n) for n in mesh.normals]
    current = None
    emitted_rings: set[int] = set()
    for f in range(mesh.n_faces):
        loops = rings.get(f)
        if loops is not None and len(loops["inners"]):
            loops = None                      # a hole cannot be written as one `f` line
        if loops is not None and id(loops) in emitted_rings:
            continue
        mat = int(mesh.face_material[f])
        if mat != current and mat >= 0:
            out.append(f"usemtl {mesh.materials[mat]}")
        current = mat
        if loops is not None:
            emitted_rings.add(id(loops))
            out.append("f " + " ".join(str(int(v) + 1) for v in loops["outer"]))
            continue
        toks = []
        for v, t, n in zip(mesh.face_v[f], mesh.face_vt[f], mesh.face_vn[f]):
            if t >= 0 and n >= 0:
                toks.append(f"{v + 1}/{t + 1}/{n + 1}")
            elif t >= 0:
                toks.append(f"{v + 1}/{t + 1}")
            elif n >= 0:
                toks.append(f"{v + 1}//{n + 1}")
            else:
                toks.append(str(v + 1))
        out.append("f " + " ".join(toks))
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
