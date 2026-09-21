from pathlib import Path

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
