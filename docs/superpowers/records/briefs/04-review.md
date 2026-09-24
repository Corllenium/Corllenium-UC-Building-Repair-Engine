# Brief 04 — independent review of everything since b2134e9

**Split (2026-09-24 19:10):** part 1 now, on `feat-dashboard` at `ce48932` (everything except the side
rebuild, which is still being built on `feat/side-rebuild`); part 2 reviews the side rebuild after
brief 03 merges it. Part 1 writes `review-since-b2134e9.md`, part 2 `review-side-rebuild.md`.
Part 2 ALSO reviews the review fixes that Hermes finished and merged while Claude was at its limit
(a1e0349, 63eabfc, 0b4b8e9, ba61235, f285ef3, merge 19f97cc): nobody has reviewed them yet.

Read-only. Review the committed state (`git show`, `git diff b2134e9..<head>`), never the working
tree (others may have work in progress there). Prior review style: findings grouped Critical /
Important / Minor, each with `file:line`, the failure scenario (concrete input -> wrong output), and
the fix; verify each finding against the code before reporting it.

Scope (all on `feat-dashboard` after brief 03): the solidify fixes (a528705..9c52695), fragments and
the QA sheet (5169e68..c0bbc98), the peer merges (d505241 area rule, dee358d union slivers, F5
snapshot identity), the border-shift guard (022a67b), the SketchUp export (e97443e, d24da30) and its
softening (bcccca2), the merge new-vertex fix (d6ef1a9, b3b9ad3), the T-junction threading (28d63df
and follow-ups), and the side rebuild (feat/side-rebuild).

Questions that matter most:
- Does any guard tolerate a change it does not measure? (border shift, fragment excuse by name,
  cap-guard allowed changes of the side rebuild, crack/flicker caps, z-fight ties). Can real visible
  damage pass?
- Does anything but solidify invent or move a vertex? Does the T-junction threading keep the surface
  identical (area, bbox) and deterministic?
- Does the side rebuild ever remove or cover something outside the slab volume, or a top face?
- The SketchUp writer: inner loops, soft/smooth decisions, materials on both sides, the planar
  tolerance fallback to soft triangles, the read-back used by tests. Can a real outline edge be
  hidden?
- Tests that reach their paths artificially (S-I3 patches shapely, S-I2 uses 0 rounds) or were
  written after the code (F1 regression, F2 renderer): are they still meaningful?
- Docstrings that state measurements: do they match the code and the numbers in the reports?

Write `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/review-since-b2134e9.md` (force-add), then a
ledger entry and a ruling per finding (fix now / defer with reason). Fixes go into a new numbered
brief.
