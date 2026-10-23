# Fresh MAIN INFRA floor ownership — owner decision, 2026-10-23

| Owner | Exclusive repair floors | Engine | Output ownership |
|---|---|---|---|
| Codex | 1F, 2F, 3F | UC MODEL FIXER engine | Codex worktrees and per-floor scratch outputs |
| Claude Code | 4F, 5F, 6F, 7F | The same UC MODEL FIXER engine | Claude's own branch/worktree and per-floor outputs |

Source: the owner's fresh Minecraft export at
`Z:/PC-4-STORAGE/UC MODELS/UPDATED MINECRAFT MODEL/MAIN INFRUSTRUCTURE`.
Frozen source revision: `7b2f7451b5723f724a1e074fdedc07dbcf7291d330ae550066f4926886136511`.
Scale: 1 block = 1 metre. Source files are read-only for both workers.

Codex's actual 1F E3 run is in `.claude/worktrees/MAIN-INFRA-E3-20261023`,
output `data/main-infra-e3/run-20261023/1F/`. Codex's 2F/3F input preparation
uses that worktree's `data/main-infra-fresh/import-2f-3f-20261023/`.
Claude must use a different owned worktree and output root for 4F–7F, for example
`data/main-infra-claude-4f-7f/`. Never overwrite another worker's models,
stage audits, mappings, renders or validation reports. Prior 4F diagnostics
remain historical evidence; Codex will launch no further 4F–7F jobs.

Both workers must claim their own queue job and run the relevant engine;
setup or an unchanged candidate does not count as repaired (AGENTS section 9).
Preserve the owner's cuts, facades, textures, UVs and all visible geometry.
Independent validation and owner acceptance remain required by AGENTS sections 3–6.

Dashboard coordination: Codex is the sole writer of the shared canonical
`data/main-infra-fresh/current.json` and local preview status while its publisher
is active. Claude writes floor-specific status/evidence for 4F–7F in its own
output root, then supplies those paths for publication. Claude must not run a
second publisher against the shared status, overwrite Codex's 1F–3F cards,
rebuild shared services or modify the live database. This avoids lost updates
from competing read/modify/write operations. It does not restrict Claude's
independent floor repair runs in its own output directories.

Recorded/checked here: floor sets are disjoint and together cover all seven
floors; queue ownership and output roots are separate. Claude's actual process,
claimed branch and future output artifacts are not yet confirmed by Codex.

## Measured engine finding — 1F, 2026-10-23

Actual checked E3 produced15856→10136triangles,5720removed,280kept sites and3
rolled-back sites. Its final site check and independent strict26 exterior guard
passed. However native Blender eye_0 showed129711changedpixels, including gaps
in a green band and changed ceiling appearance. This candidate is REJECTED for
delivery; it was removed from current candidate selection and never accepted.
The original source is unchanged. Exterior guard/site PASS alone is insufficient.
Both owners must inspect independent interior images before accepting a floor.

Counterexample image: Codex E3 worktree
`data/main-infra-e3/run-20261023/independent-validator/1F/native-qa/paired-detail.png`.
The original failed candidate remains frozen for diagnosis and full signed
validation. Codex is identifying visible removed faces and restoring whole
affected sites in a separate candidate. Claude must retain its independent
interior visual checks on4F–7F when using this same engine.
