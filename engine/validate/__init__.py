"""The Validator: judges a repaired floor by the owner's rule (AGENTS.md section 6).

Every facade texture still there, the problems solved, nothing visible deleted or covered -- from
outside, and from eye height inside every floor.

Independence. The Validator judges the repair engine, so it is written from scratch and is NOT
built on the code it judges: no `engine.guard` (not `compare_views`, not `render`, not
`piece_rays`), no `engine.fixes`, no `engine.vis`. The only engine modules it may use are
`engine.model` (the mesh), `engine.rays.caster` (the ray caster) and its own siblings.

The modules:

* `sampling`: where to look and what texture is there (`face_samples`, `uv_at`), face normals
  and areas, and the frame (`recentred`, `check_frame`);
* `viewpoints`: where to look from (`outside_directions`, `pedestrian_ring`, `interior_probes`);
* `visibility`: what each viewpoint sees, and which side of the face (`visible_samples`,
  `VisibleSet`, `build_caster`).

Conventions, shared by every module here:

* Units are inches, Z is up.
* The Validator works in a RECENTRED frame (`sampling.recentred`): positions shifted by the
  bounding-box centre, because Embree stores float32. BEFORE and AFTER of one floor are shifted
  by the SAME centre, so they share one frame. Depth and UV comparisons are float64.
* A face's normal comes from its winding, `cross(b - a, c - a)`: counter-clockwise from the
  front. A face with no area has no normal and is never visible.
* Unity draws both sides of every face (`_Cull = 0`), so a face is seen from either side; what
  differs is whether the viewer sees its FRONT or its BACK.
* Everything is deterministic: the same input gives the same samples, viewpoints and
  visibility, every run.
"""
