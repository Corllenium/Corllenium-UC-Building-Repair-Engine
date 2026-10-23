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
passed. An initial native eye_0 image differed129711pixels. Correction: independent
float64 rays proved that camera was only0.6002m above its first-hit floor in a
1m-high cavity, not a valid1.6002m walking-eye viewpoint. It was wrong to label
that render a pedestrian facade failure. The original finding is retained.

Sixteen independently qualified walking-eye native pairs are pixel-identical.
The full signed Validator passes textures108392samples/0failed and visible
coverage5720removedfaces/0lost. Overall remains FAIL because flicker_diff1626,
flicker_same1014 and cracks2372 exceed signed targets0. The candidate is available
for inspection, not accepted. Original source unchanged; no restoration replay
was launched. Both owners still require independent valid interior images.

Counterexample image: Codex E3 worktree
`data/main-infra-e3/run-20261023/independent-validator/1F/native-qa/paired-detail.png`.
The candidate remains frozen with the full signed report and qualified camera
evidence. Source hashes and original-source survivor indices are unchanged.
Claude must retain independent interior visual checks on4F–7F using this engine.

## Live dashboard requirement — owner decision, 2026-10-23

The owner requires `https://corllenium.ai.dev-environment.site/pipelines/jev-repair/`,
not a localhost preview. Codex published actual fresh status atomically into both
hosting static roots and verified the public SHA. Fresh1F source/candidate plus
independent evidence are copied to both roots (24files, hashes verified). No
accepted floor was published, no database was changed and no app restarted.
Live page integration is built from the measured livebb71d31 base in the separate
SIEGE-MAIN-INFRA-LIVE-20261023 worktree; never deploy the older preview branch,
which is197commits behind the live base. Only Codex publishes shared live status.
