"""Scratch: render a written .skp WITHOUT the SketchUp GUI. The faces come back through the C API
(`engine.io.skp_writer.read_skp`: SketchUp's own triangulation of every face, holes included) and
the drawn edges are exactly the ones SketchUp shows -- every edge that is neither soft nor smooth
-- through the existing `engine.guard.qa_render` renderer. Usage: render_skp.py <file.skp> <out dir>"""
import sys
from pathlib import Path

import numpy as np

from engine.guard.qa_render import write_qa_sheet
from engine.io.skp_writer import read_skp
from engine.model import MeshData


def main(skp: str, out_dir: str) -> None:
    model = read_skp(skp, uvs=False, triangles=True)
    tris = np.concatenate([f.triangles for f in model.faces if len(f.triangles)])
    visible = [(e.start, e.end) for e in model.edges if not (e.soft or e.smooth)]
    pts = np.concatenate([tris.reshape(-1, 3), np.array(visible).reshape(-1, 3)])
    uniq, inverse = np.unique(pts, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    n_tri = len(tris) * 3
    face_v = inverse[:n_tri].reshape(-1, 3)
    edges = inverse[n_tri:].reshape(-1, 2)
    f = len(face_v)
    mesh = MeshData(name=Path(skp).stem, positions=uniq, uvs=np.zeros((0, 2)),
                    normals=np.zeros((0, 3)), face_v=face_v, face_vt=np.full((f, 3), -1),
                    face_vn=np.full((f, 3), -1), face_material=np.zeros(f, np.int64),
                    face_line=np.arange(1, f + 1), materials=["m"], mtllib=None,
                    coord_decimals=6, sig_digits=9)
    written = write_qa_sheet(mesh, edges, Path(out_dir), size=(1600, 1000))
    print(f"{skp}: {len(model.faces)} faces -> {len(tris)} SketchUp triangles, "
          f"{len(visible)} visible edges of {len(model.edges)}; wrote {len(written)} images to {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
