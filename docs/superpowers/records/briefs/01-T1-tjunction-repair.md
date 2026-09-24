# Brief 01 — T1: the merge repairs T-junctions at the source

**Status (2026-09-24 18:40):** core item committed as `28d63df` on `feat-dashboard`
(`fix(engine): the merge threads T-junction vertices into the edges they lie on`). Measured by its
own runs at 14:38: file A 902 -> 1,013 triangles, T-vertices 353 -> 0, 86 edges split; file B
555 -> 601, T-vertices 363 -> 0, 40 edges split; both passed. **Open:** in the SketchUp audit, file
B's T-junction LINES fell only 28 -> 24 although no T-vertex is left; find why. Then the finish steps.

Where: main checkout `D:\PROJECTS\UC MODEL FIXER`, branch `feat-dashboard`. Edit only `engine/`.
Do not edit `engine/fixes/solidify.py`, `engine/guard/compare.py`, `engine/fixes/pipeline.py`
(the side-rebuild job owns them) unless strictly needed; append fixtures at the END of
`engine/tests/fixtures/build.py`.

## Background

SketchUp draws a line inside a flat surface where one face's edge runs along a neighbouring face that
has vertices on that edge but does not share it (a T-junction; Unity shows a hairline crack and
sparkle there). The SketchUp writer already hides every line whose whole length lies inside a flat
same-material surface; the rest lie inside a surface over only part of their length, so only
splitting them in the mesh removes them. The export is full of T-junctions (on file A's underside 54
of 218 vertices lie exactly on a neighbour's edge).

## Item T1 (done in 28d63df)

After the merge has decided every output face, every existing vertex the output uses that lies on
the interior of an output edge (tight tolerance justified from the print quanta) is threaded into
that edge: into a merged region's ring (the corner pass keeps it) or by splitting a copied-through
triangle into a fan. No vertex moved or invented; only edges split; iterate to a fixed point,
bounded, deterministic. `merge_report` gains `t_vertices_before`, `t_vertices_after`, `edges_split`.

## Remaining

1. Why B's audit still shows 24 T-junction lines with 0 T-vertices: candidates are the audit's own
   classification (it ignores material for T-junction lines, so material borders can be counted),
   lines that lie on a coplanar face without any vertex there (not a T-junction at all: an edge
   running across a face's interior), the writer's welding, or a tolerance. Use
   `docs/superpowers/records/scripts/skp_edge_audit.py` (it prints the longest lines with
   coordinates) and probe the longest ones. Fix test-first if in scope; otherwise report precisely.
2. Finish: `.venv/Scripts/python.exe -m pytest engine/tests -q -p no:cacheprovider`; both real
   runs (`-m engine.cli fix data/snapshots/<id> --out data/output`; they also write the owner's
   `.skp`); `preview-data` for both; the audit for both `.skp` files; two runs of file A give a
   byte-identical `report.json`; read `data/output/<name>/qa/top.png` for both and describe them.
3. Report `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/tjunction-report.md` (force-add),
   ending with `## Public signatures`; ledger entry; release the claim.
