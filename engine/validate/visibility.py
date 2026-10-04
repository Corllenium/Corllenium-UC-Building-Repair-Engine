"""What each viewpoint sees of the samples.

Written for the Validator and independent of the code it judges (see `engine.validate`): rays go
through `engine.rays.caster.EmbreeCaster` and nothing else of the engine.
"""
from __future__ import annotations

from engine.model import MeshData
from engine.rays.caster import EmbreeCaster
from engine.validate.sampling import check_frame


def build_caster(mesh: MeshData) -> EmbreeCaster:
    """The ray caster for `mesh`, which must already be in the Validator's frame
    (`sampling.recentred`): Embree stores float32, so a mesh sitting near 24,000 in is refused
    with a `ValueError` instead of being silently rounded. `first_hit`'s `tri` indexes
    `mesh.face_v`, degenerate faces included (they are never hit)."""
    check_frame(mesh.positions, "mesh positions")
    return EmbreeCaster(mesh.positions, mesh.face_v)
