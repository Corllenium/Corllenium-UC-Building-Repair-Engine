---
name: uc-validate-floor
description: Use when a UC floor or element has been repaired and must be judged, or when taking a floor from claim to publish - the workflow claim, snapshot, repair, validate, evidence, review, publish, and how to run and read the Validator (engine.cli validate, validation.json, evidence crops).
---

# Validating a floor

The rule is `AGENTS.md` §6: a floor is good only when the Validator, run by an agent that did not build the
fix, shows all three, and then the owner confirms it:

1. **every facade texture is still there** (check 1: each visible sample keeps its surface, its look and its UV);
2. **the problems are solved** (check 2: `find_errors` after the fix meets the targets the owner signed);
3. **nothing visible was deleted or covered** (check 3: from outside and from eye height inside every floor).

A log line or a self-report is not a pass. The pass is `validation.json` together with its evidence images.

## The workflow

| Step | Who | What |
|---|---|---|
| claim | the builder | `tools/jobs.py next`, the worktree, the brief (skill `uc-handoff`) |
| snapshot | the builder | the unit's frozen source under `data/snapshots/<id>` (`campus-freeze`); never the live export folder |
| repair | the builder (`engine-builder`) | the engine's fix, test first (skill `uc-repair-rules`); real runs use `--skp-dir data/skp_scratch` |
| validate | **another agent** (`floor-validator`) | the command below, on the snapshot and the repaired OBJ |
| evidence | the validator | read `validation.json` and open every `evidence/site-NN-*.png`; say what is seen |
| review | the controller (`rules-reviewer`) and the owner | the verdict and the pictures; the owner accepts or rejects the floor |
| publish | the controller | only COMMITTED code's results, from `.claude/worktrees/verified`, to `OBJ FIXED RESULT\` |

The builder never validates their own fix. A FAIL goes back to the builder with the validator's reasons.

## Running it

```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m engine.cli validate \
    --before "<main>/data/snapshots/<id>" --after "<repaired>.fixed.obj" \
    --materials "<main>/data/campus/materials.json" --out "<short output dir>" )
```

- Exit 0 is PASS, exit 2 is FAIL (or a missing or unreadable input, with a message on stderr).
- The output folder holds `validation.json` and `evidence/`, which exists only when something failed.
- Write to a SHORT path (for example under the temp folder): a long path plus a long snapshot name passes
  260 characters on Windows.
- A large floor takes minutes (CHTM 5th floor about 10 minutes): note the machine load with the timing.
- Do not pass `--area-per-sample` or `--min-per-face` for a verdict: the owner's values are the defaults, and any
  other value makes the report say it is a development run and not an owner verdict.

## Reading it

- `verdict` comes from checks 1 and 3. Check 2 only reports until the owner signs the targets
  (`engine/validate/targets.json`); quote its before and after counts anyway.
- `checks.textures.reasons` counts failing samples by the first reason that applies:

  | Reason | Meaning |
  |---|---|
  | `covered` | a face of AFTER lies in front of the sample by more than the depth tolerance |
  | `overlaid` | a new face of another look or UV lies on the sample, or just in front of it |
  | `deleted` | nothing is at the sample's place any more |
  | `look` | something is there, in another look (texture plus colour) |
  | `uv` | the look is right, the UV differs (mod 1, by more than one texel of that texture) |
  | `side` | the surface is right, but the viewer now sees its back (flipped winding) |

- `sites` clusters the failing samples; the worst 20 carry `evidence` crops: BEFORE and AFTER, 256 px, aligned,
  coloured by look, a face seen from behind in purple, drawn from the viewpoint that judged the site (a probe
  at eye height, when only a probe sees it).
- `notes` lists what the Validator could not compare: materials unknown to `materials.json` (compared by name,
  size and colour from the snapshot's own MTL) and looks with no texture size (no UV test). Report each.

## Deciding

1. Open every evidence crop and say what you see. A crop of a failure that looks like a Validator false
   alarm (for example a coplanar copy that Embree sees either of) is reported as such, with the picture.
2. Say PASS only when checks 1 and 3 pass and `notes` hold no unreported gap. Otherwise say FAIL with counts by
   reason, the number of sites and what the crops show.
3. Do not change the Validator to make a floor pass. A rule change needs the owner (`AGENTS.md` §3: guards
   are never loosened by argument).
4. The owner confirms a floor; the validator never does.
