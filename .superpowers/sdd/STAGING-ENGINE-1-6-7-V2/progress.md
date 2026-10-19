# STAGING-ENGINE-1-6-7-V2

- 2026-10-19 21:10: claimed (claude-vertex-opus). Runner tests 26 passed. The input V2 .blend is re-saved by a live
  Blender session, so the run reads `MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.frozen-210156.blend` (sha256 `10ceb8d7…e9d6`,
  checked before and after the copy). Launched 21:08:47, PID 41992, floors 6,7,1 into
  `MAIN-INFRA-ALL-FLOORS-ENGINE-STAGED.blend`, work dir `engine-7floors-v2`. Waiting for 3,000 MB commit headroom
  (1,756 MB free; runs 2-3, 4-5, 6-7 still going). No engine edits, no floor pass claimed.
- 2026-10-19 21:25: commit headroom reached 3,109 MB at 21:24:55; export done from the frozen copy: 1F 16,354 tris
  (15 objects, 10 caps), 6F 30,518 tris (140 objects, 133 caps), 7F 16,680 tris (133 objects, 130 caps). Engine on 1F
  since 21:25 (floors run in sorted order 1, 6, 7).
- 2026-10-19 21:33: 1F done, 16,354 -> 7,217 tris. Guard FAILED on 26/26 views (holes 186, material 46,917,
  moved_same_flat 3,116, flicker 149; 50,246 of 3.77 M model px). Checker: one n-gon ERROR (a 0.03 in sliver;
  coverage and winding agree, vector area equal) and 10 mixed-material n-gons (1,475 sq in) at tile edges. Guard images
  read (see report). 6F engine running. Source V2 re-saved at 21:26:50 (sha256 47ca5bcc...); the run stays on the
  21:01:56 copy.
- 2026-10-19 22:23: 6F done, 30,518 -> 15,712 tris (engine 2,429 s, guard 547 s). Guard FAILED on 26/26 views
  (199,839 of 4.91 M px = 4.07 %; peer 6F on the 19:28 V2 had 11.43 %). Checker PASS for both files. Guard images
  read: light triangles fanned over the ceiling plane (fail_5), a long diagonal strip on the right (fail_17).
  7F waiting for commit headroom (2,133 MB free at 22:22:36).
