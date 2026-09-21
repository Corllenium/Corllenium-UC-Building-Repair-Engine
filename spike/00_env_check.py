"""Gate G1: does embreex work in this venv, and how fast."""
import platform
import sys
import time

import numpy as np

from _common import save

out = {"python": sys.version.split()[0], "numpy": np.__version__, "platform": platform.platform()}
try:
    import shapely
    import trimesh
    import embreex  # noqa: F401
    from trimesh.ray.ray_pyembree import RayMeshIntersector

    out["shapely"] = shapely.__version__
    out["geos"] = ".".join(map(str, shapely.geos_version))
    out["has_constrained_delaunay"] = hasattr(shapely, "constrained_delaunay_triangles")
    out["trimesh"] = trimesh.__version__
    out["embreex"] = getattr(embreex, "__version__", "unknown")

    sphere = trimesh.creation.icosphere(subdivisions=5)
    rmi = RayMeshIntersector(sphere)
    n = 1_000_000
    rng = np.random.default_rng(0)
    d = rng.normal(size=(n, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    o = -3.0 * d
    t0 = time.perf_counter()
    tri = rmi.intersects_first(o, d)
    dt = time.perf_counter() - t0
    out["sphere_tris"] = int(len(sphere.faces))
    out["rays"] = n
    out["rays_per_s"] = round(n / dt)
    out["hit_fraction"] = float((tri >= 0).mean())
    out["gate_G1"] = bool(out["hit_fraction"] > 0.999)
except Exception as exc:  # spike: any failure is the answer
    out["gate_G1"] = False
    out["error"] = repr(exc)

save("env", out)
for k, v in out.items():
    print(f"{k}: {v}")
