# Stray fragments — brief (task F: loose slivers and disconnected bits)

Repo `D:\PROJECTS\UC MODEL FIXER`, branch `feat-dashboard`. Bash, POSIX syntax, repo path
`/d/PROJECTS/UC MODEL FIXER`. Python ALWAYS `.venv/Scripts/python.exe`. Do not touch the running servers.
Leave untracked files alone. Edit only files under `engine/` (plus `preview/index.html` for the stats line).

## Why (visual pass 2026-09-23)
Close-up renders of the fixed 2nd-floor file show small loose triangles and thin lines sitting on or near flat
walls, and a few small disconnected blocks (visual QA sheet `data/visual_qa/A_ngon/`, Gemini triage: "floating
fragments", "disconnected rectangular block on the far right", "disconnected line fragments"). They are visible
from outside, so the hidden-face rule keeps them; the user wants them gone. The project's defect list calls
these stray floating fragments and sliver fans.

## F1 `feat(engine): stray fragment detector and reviewed removal`
New `engine/detectors/fragments.py` (create the package) run in `fix_object` after solidify and hidden removal,
before flipping and the merge:
- Connected components by shared welded edge over the current mesh. A component is a FRAGMENT candidate when
  (a) its total area is below `profile.fragment_max_area` (default 4 in²), or (b) it is a single face, or
  (c) its longest dimension is below `profile.fragment_max_extent` (default 6 in). Never a component that
  contains a face whose area exceeds `fragment_max_area` on its own.
- Sliver faces attached to the main body (thin needles: `4*pi*area / perimeter² < profile.sliver_q` = 0.02,
  the project's sliver quotient) are candidates too, reported separately as `slivers`.
- Removal under a FRAGMENT-mode guard: allowed changed pixels are exactly those whose BEFORE first hit is a
  candidate face; any other change restores the candidate (same feedback loop as hidden removal). Runs only
  when `profile.accept_fragments` is True (default True; CLI `--keep-fragments`; the dashboard exposes it).
- `FixResult` gains `removed_fragments` (bool over original faces), `n_fragment_components`, `n_removed_fragments`,
  `n_removed_slivers`, `n_restored_fragments`; `report.json`, preview stats and the preview page show them.
Tests, written first: a slab with one detached 2 in² triangle -> removed; a detached 20 in² quad -> kept and
reported as a component above threshold; a needle sliver attached to the slab -> removed; `--keep-fragments`
removes nothing; determinism; the final guard against the reference tolerates exactly the fragment pixels.

## F2 `feat(engine): visual QA sheet written by every run`
Port `spike/17_visual_qa.py` into `engine/guard/qa_render.py` (`write_qa_sheet(mesh_tri, polygon_edges, out_dir)`):
12 views + 9 close-ups, shaded, polygon edges from the merge rings (hidden lines removed). `python -m engine.cli
fix` writes them into `<run dir>/qa/`. Test: the files exist for a fixture run.

## Finish
Engine suite (real count); rerun both real files; report fragment numbers, guard totals, passed; read three QA
images with the Read tool and describe them in one sentence each. Write `fragments-report.md` next to this
brief ending with `## Public signatures`. Commit messages as given, trailer
`Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
