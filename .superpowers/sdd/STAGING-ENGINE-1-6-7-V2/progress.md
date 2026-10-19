# STAGING-ENGINE-1-6-7-V2

- 2026-10-19 21:10: claimed (claude-vertex-opus). Runner tests 26 passed. The input V2 .blend is re-saved by a live
  Blender session, so the run reads `MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.frozen-210156.blend` (sha256 `10ceb8d7…e9d6`,
  checked before and after the copy). Launched 21:08:47, PID 41992, floors 6,7,1 into
  `MAIN-INFRA-ALL-FLOORS-ENGINE-STAGED.blend`, work dir `engine-7floors-v2`. Waiting for 3,000 MB commit headroom
  (1,756 MB free; runs 2-3, 4-5, 6-7 still going). No engine edits, no floor pass claimed.
- 2026-10-19 21:25: commit headroom reached 3,109 MB at 21:24:55; export done from the frozen copy: 1F 16,354 tris
  (15 objects, 10 caps), 6F 30,518 tris (140 objects, 133 caps), 7F 16,680 tris (133 objects, 130 caps). Engine on 1F
  since 21:25 (floors run in sorted order 1, 6, 7).
