# MAIN INFRA reset: current status, October 23, 2026

**Current state: awaiting owner review of the replacement plan.** No fresh floor
is repaired, independently validated, accepted or published by this reset.

Current design: [Design](../specs/2026-10-23-main-infra-fresh-cleanup-design.md).
Current implementation plan: [Plan](../plans/2026-10-23-main-infra-fresh-cleanup.md).
Job: `MAIN-INFRA-RESET-20261023`; branch `codex/main-infra-reset-20261023`.

## Source and owner's decisions

`Z:\PC-4-STORAGE\UC MODELS\UPDATED MINECRAFT MODEL\MAIN INFRUSTRUCTURE`
is the owner's designated fresh source. Inventory: 7 OBJ, 7 MTL, 22 PNG, 36 files.
Keep the owner's floor cuts and facade look/UVs/visible coverage. The owner confirmed
1 Minecraft block = 1 metre and authorized deletion of both old plans/jobs and
failed generated outputs. No other building's source/reference changed.

## Retired this turn

- Removed five superseded MAIN INFRA queue entries; their full original records are
  in `main-infra-reset-20261023/retired-jobs.json`.
- Deleted six generated OBJ variants with explicit failed visual-guard reports:
  V2 1F, V2 6F, and earlier 6F, each triangle and n-gon variant.
- Deleted four obsolete plan/brief files: the former Hermes fresh-export plan,
  the two V2 run briefs, and the old October 19 staging PLAN.md.
- Every exact path, byte count, SHA-256 and failed-report reference is in
  `main-infra-reset-20261023/deletion-receipt.json`. All ten files were read back
  absent and all five old entries were read back absent. No recursive deletion.
- Matching repair processes at deletion: zero. Source/raw snapshots, prior sandbox
  code/tests/evidence and diagnostic reports were excluded. Other old outputs with
  passed=true were not represented as failed or removed by this inventory.

## Floor status

| Floor | Actual state | Next gate |
|---|---|---|
| 1F | Queued; no fresh candidate | Reproduce and qualify polygon ingest, then pilot cleanup |
| 2F | Queued; no fresh candidate | Both 1F and 4F pilots pass |
| 3F | Queued; no fresh candidate | Both 1F and 4F pilots pass |
| 4F | Queued; no fresh candidate | Reproduce and qualify polygon ingest, then independent pilot |
| 5F | Queued; no fresh candidate | Both 1F and 4F pilots pass |
| 6F | Queued; no fresh candidate | Both 1F and 4F pilots pass |
| 7F | Queued; no fresh candidate | Both 1F and 4F pilots pass; ordinary fresh 7F, no custom swap |

Previous ingest blockers: 1F raw line 10224, 4F raw line 36210, nonplanar quads.
Physical block scale is now owner-confirmed; exporter mapping/up-axis and lossless
tessellation still need technical proof. A source change creates a new revision.

## Dashboard findings and plan review

The correct target is the existing Corllenium planning dashboard in repository 02,
not the Vue/FastAPI fixer UI. Its stale all-78-complete status cannot describe this
source. Its simulated engine action creates metrics/validation; its approve/push
action uses hardcoded commit `4c91e8b`. The replacement plan explicitly prevents
those actions from manufacturing fresh MAIN INFRA results or acceptance.

A separate builder-check agent reviewed design/plan. Its two material findings
were addressed: progress wiring now precedes import qualification, and fresh
MAIN INFRA cannot use the simulated validation/approval handlers. No product
code or dashboard deployment occurred in this turn.

Execution order: reset -> actual status wiring -> lossless import -> 1F/4F pilots
-> remaining floors sequentially -> accepted artifact/display adoption. Raw preview
stays labelled uncleaned; failed candidates stay outside accepted references.

## Actual verification

From the isolated worktree, with PYTHONPATH set to it:

```text
D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe -B -m pytest tools/tests/test_jobs.py -q -p no:cacheprovider --basetemp data/tmp/main-infra-reset-check
.........                                                                [100%]
9 passed in 1.22s
```

Deletion command readback:

```text
READBACK: 6 failed OBJ variants and 4 obsolete plan/brief files absent; 5 obsolete queue entries absent; 0 matching repair processes.
```

The canonical initial progress JSON is `data/main-infra-fresh/current.json` in the
main checkout. It records planning state and is **not yet connected to the dashboard**.
No geometry/appearance success is claimed; no SKP was produced.
