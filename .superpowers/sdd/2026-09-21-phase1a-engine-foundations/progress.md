# SDD ledger — plan: docs/superpowers/plans/2026-09-21-phase1a-engine-foundations.md
Spec: docs/superpowers/specs/2026-09-21-uc-model-fixer-design.md (read). Branch: phase1a-engine. Merge base: see `git merge-base main HEAD`.

Ruling: feature branch in the main working tree instead of a git worktree — .venv and data/ (snapshots, spike results) are git-ignored and exist only here, a worktree would have neither — costs: no isolation from the running preview server, which only reads preview/.

## Pre-flight scan
| Pair / task | Produces vs consumes | Finding |
|---|---|---|
| T1 -> T2 | MeshData incl. coord_decimals, sig_digits / reader fills all 14 fields | agree |
| T1 -> T3 | fixtures cube(), MeshData.materials mutable list / writer test mutates materials + face_material | agree |
| T2,T4 -> T5 | read_obj, parse_mtl, write_mtl_subset -> dict[material, relpath], texture_flatness / snapshot uses wanted.values() and flatness per material | agree |
| T6 -> T7 | build_edge_table(face_w, include), find_t_vertices(positions_w, table, tol) -> dict[edge, ids ordered from edges[e][0]], edge_face_lists / planes + edges walk chain a..b in that order | agree |
| T7 -> T8 | Topology.positions_w, .table.edges, .edge_class, .face_region / meshbuf blocks | agree |
| spike/_region.py -> T7 | cluster_uv returns (J,o,resid), constants module-level / plan says return (J,o), constants become kwargs | agree, change is stated in T7 |
| T1 self | t_junction_strip 7 faces, 1 zero-area; test asserts area == 0 exactly (integer collinear points) | agree |
| T2 self | face_line [13,15,16] counted against OBJ literal; sig_digits 6 from "22669.4" | agree |
| T3 self | _num strips trailing zeros, "-0" -> "0"; round trip exact for integer cube | agree |
| T4 self | subset returns only textured used materials; constant image std 0.0 | agree |
| T5 self | tmp renamed to final, finally-rmtree is then a no-op; second call reuses final | agree |
| T6 self | cube 18 edges all count 2; slab 320 edges, 40 open; strip: 1 T-vertex on edge x in {0,20} | agree |
| T7 self | cube 6 regions/6 removable/12 real; slab 280 removable/40 open; strip 7 removable (3 diagonals + quad-quad + long + 2 sub) | agree (count corrected to 7 before commit b884dc8) |
| T8 self | counts faces 12 edges 18, offsets % 4 == 0, origin [5,5,5] | agree |
| Global | 27 tests = 3+3+2+2+5+5+6+1 | agree |
| Rubric | T7 mandates verbatim port of spike functions = duplicated logic block | Ruling: allowed — spike/ is throwaway and never imported by engine/, spec says validated algorithms are re-implemented in engine — costs: two copies until spike/ is deleted |

## Execution
Task 1: complete (commits caef965..aaa9021, review clean; trailer confirmed by controller; controller re-ran pytest: 3 passed)
Ruling: batch Tasks 2+3+4 into one implementer dispatch and one review, then 5+6, then 7+8 — every task carries complete code in the plan (transcription + test), each task still gets its own commit, and one review seat costs ~120k tokens — costs if wrong: a defect in an early task of a batch is found one review later than it would have been.
Task 2: complete (commits aaa9021..ed1f712, review clean)
Task 3: complete (commits ed1f712..65db33f, review clean)
Task 4: complete (commits 65db33f..f34af60, review clean). Controller checks: 10 passed; read_obj on real snapshot CHTM_SIDE_WALK_2nd_floor = 4692 faces, 1607 v, 2771 vt, 666 vn, sig 6, first f line 5050 (matches grep) -> resolves reviewer's "fully triangulated" cannot-verify.
Task 2: minor (deferred): obj_reader line.partition(" ") would not tokenize a tab-separated keyword line
Task 2-4: minor (deferred): implementer report line counts inaccurate (report only, no code impact)
Task 6: complete (commits 666ded9..b30c6b9, review: spec ok, approved alone). Controller: 20 passed; trailers confirmed on 666ded9 and b30c6b9; fixtures were reviewed in Task 1.
Task 6: minor (deferred): find_t_vertices is O(open_edges x candidates); fine at ~600 open edges, revisit for building-sized meshes
Task 5: review = Changes required. Finding (Important, plan-mandated): snapshot.py parses the LIVE .mtl via parse_mtl(mtl_src) and copies live textures without verify; read_manifest reads the live manifest with no stability check. Breaches Global Constraint "only snapshot.py reads the source, only via stability check + copy + sha256".
Ruling: finding stands, plan reference code was wrong against its own constraint and the spec ("jobs never read the live folder") — fix: one _copy_verified helper (wait_stable -> copy -> key unchanged) for OBJ, MTL and every texture; MTL parsed from the copy, copy kept as source.mtl; add read_manifest_stable (single read of bytes between two key checks, parse those bytes) — costs if wrong: ~1 s extra per asset on import, nothing structural.
Task 5: real-data check by implementer: sha256 ce26e0392ab0... (identical to spike's independent hash), 4692 faces, flatness 3.0439, missing [].
Task 5: fix round 1/5 (1 addressed, 0 open — live-source reads now only through _copy_verified / read_manifest_stable; commits b30c6b9..7d73e84). Controller: 26 passed; real-data re-check sha ce26e039..., 4692 faces, flatness 3.0439, missing [], source.mtl present.
Task 5: complete (commits f34af60..7d73e84, review clean after 1 fix round)
Task 5: minor (deferred): tex_src.exists() probes the live path outside _copy_verified (existence only, no content read)
Note: suite total is now 27 + 6 = 33 expected at end of plan (6 tests added by Task 5 fix).
Task 7+8: review = Approved with 1 Important (plan-mandated): T-junction chain -> sub-edge resolution duplicated in engine/topo/planes.py (build_regions) and engine/topo/edges.py (classify_edges).
Ruling: finding stands, fix it — extract one helper into engine/topo/adjacency.py used by both; the two copies encode the same ordering contract (chain runs edges[e][0] -> edges[e][1]) and drifting apart would silently mis-class gridlines — costs if wrong: one small refactor round.
Task 7: minor (folded into the same fix): function-local import of edge_face_lists in planes.py
Task 8: minor (deferred): test_meshbuf only covers a clean cube. Controller ran pack/unpack on the real file instead (see below).
Task 7: fix round 1/5 (2 addressed, 0 open — chain logic now only in adjacency.t_junction_sub_edges; commits 2c5c105..0dc2d1f). Regression: real-model sha256(face_region+edge_class) identical before/after (427dfacc...), bincount [1097, 2524, 326, 1738, 316]. Controller: 35 passed.
Task 7: complete (commits a021cd3..0dc2d1f, review clean after 1 fix round). Real data: topology_stats faces 4692, zero_area 217, welded 1589, quanta [0.01,0.1,0.01], regions 986, removable 2524, nonmanifold 1738, 0.27 s.
Task 8: complete (commits 70887ce..2c5c105, review clean). Controller real-data check: meshbuf 648,404 bytes in 0.25 s, all normals unit and finite, tri_face_id == arange, 217 faces region -1.
Task 7: minor (deferred): t_junction_sub_edges lookup dict rebuilt by each of its two callers

## Final whole-branch review (opus): Ready with fixes. 0 Critical, 8 Important, 6 Minor.
F1 meshbuf header: Path values not JSON serializable -> IN fix wave.
F2 flat_materials takes indices, snapshot flatness keyed by name, no threshold constant in engine -> IN fix wave.
F3 zero-area faces dropped before adjacency; spec says use them as T-junction hints. F4 T-vertices only searched on open edges.
Ruling: F3+F4 IN fix wave — spec is binding ("use them as hints, drop them after adjacency") and my plan narrowed it; wrong gridline classes are the exact failure this engine exists to prevent — costs if wrong: class counts on the real model shift, so the wave must report before/after counts.
F5 snapshot dir keyed on OBJ sha only, texture-only re-export reuses stale textures.
Ruling: F5 PARKED to Phase 1B — version identity is the OBJ sha per spec and version_assets there records per-asset hashes, so the importer can detect drift; changing the dir key now breaks the brief's dir.name == sha[:12] contract — costs if wrong: stale flatness after a texture-only re-export until 1B lands.
F6 .incoming tmp dir is per-OBJ not per-call (concurrent jobs collide) -> IN fix wave.
F7a permanently missing .mtl raises SourceUnstable, caller could retry forever.
Ruling: F7a PARKED — during a rebuild the whole split folder vanished and came back (observed), so "missing" is genuinely ambiguous inside the engine; bounded retries are the Phase 1B importer's job — costs if wrong: an importer without a retry cap spins.
F7b Windows file lock surfaces as raw PermissionError -> IN fix wave (OSError during verified copy -> SourceUnstable).
F8 textures flattened to basename, same-basename collision overwrites silently.
Ruling: F8 guard only, IN fix wave — this export keeps every texture in one SRC-TEX dir so a collision cannot occur today; raise instead of overwriting — costs if wrong: a future multi-dir export fails loudly instead of importing.
Minor exponent-form coordinate token breaks decimals/sig detection -> IN fix wave (raise ObjFormatError). Other new minors: can wait.
T8 deferred minor (meshbuf cube-only test) -> reviewer says fix before merge -> IN fix wave.
Final fix wave: 1 dispatch, 8 commits 0dc2d1f..1dcd360 (F1,F2,F3+F4,F6,F7b,F8,M1,T8). Controller: 53 passed; imports clean; real model: flat_material_indices -> {0}, names rejected with TypeError, meshbuf packs with Path textures; topology regions 986->888, open 326->250, t_junction 316->389, edges_with_t_vertices 164->406, 0.41 s.
Final scoped re-review (sonnet): all 9 findings ADDRESSED, no new Critical/Important.
Final: minor (deferred): classify_edges "whole chain" branch can now reach counts>=3 edges and mark them REMOVABLE when all faces share one region; nonmanifold count unchanged 1738 on real data.
Ruling: no merge into main by the controller — a merge is a side effect the user decides; Phase 2E continues on a branch stacked on phase1a-engine and the merge choice is presented at the end — costs if wrong: one extra branch to merge later.
PHASE 1A COMPLETE. Parked for Phase 1B: F5 (snapshot dir keyed on OBJ sha only) -> now Task 1 of the 1B plan; F7a (retry cap belongs to importer) -> 1B global constraint "API never loops on SourceUnstable".
