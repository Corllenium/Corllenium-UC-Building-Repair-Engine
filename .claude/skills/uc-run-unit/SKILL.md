---
name: uc-run-unit
description: Use when running the UC repair engine's command-line tools on real CHECKPOINT-17 data (freeze the source, index groups, material look keys, inventory, SDK check, census, validate a unit) and when deciding where their outputs go.
---

# Running the engine's tools on real data

Rules first: `AGENTS.md` §2 (where things are, and what is read-only) and §3. Every command runs from
a worktree root:

```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m engine.cli <command> … )
```

`data/` is resolved in the worktree. P0's real runs write to the MAIN checkout's `data/` by absolute
path, as each brief says.

| Command | Available after | What it does | Output |
|---|---|---|---|
| `campus-freeze --export <CKPT17> --backup <BACKUP> --out data/campus --snapshots data/snapshots` | P0 task 7 | stable copies and sha256 of every split OBJ, CKPT17-CLEAN, the MTL and textures; hashes the backup | `data/campus/source.json` |
| `campus-index --source data/campus/source.json --out data/campus/group_index.json` | task 8 | face → SketchUp group path | `group_index.json` |
| `campus-materials --source … --out data/campus/materials.json` | task 9 | look key = texture sha256 + Kd + d | `materials.json` |
| `campus-inventory …` | task 10 | level tables, units, duplicates, misnamed and missing levels | `campus_map.draft.json`, `docs/superpowers/records/campus/campus-map-draft.md` |
| `campus-skp-check …` | task 11 | read-only SDK walk of a verified copy of the backup, compared with the export | `skp_check.json` |
| `census --units … --jobs 4` | task 12 | `find_errors` per unit, with stage timings, peak memory and machine load | `census.json`, `docs/superpowers/records/campus/census.md` |
| `validate --before <snapshot> --after <obj> --materials … --out <dir>` | task 15 | the owner's three checks | `validation.json`, `evidence/*.png` |

**Never:**
- write into `MODEL FIXER ENGINE FILES\` or `OBJ FIXED RESULT\` during work (only publishing from
  `.claude/worktrees/verified` does);
- read the export folder except through these commands;
- open the master `.skp`.

Record the machine load with every timing: other sessions on this machine have slowed a run 16×.
