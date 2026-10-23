# Independent prompt audit: required engine output

Scope: only AGENTS.md section 9, lines 163-173, committed in
`d07dff4e958b353c90a3b9ce60954904fa3d20c7`. Sections 1-8 are binding context,
outside the proposed-edit scope. No other prompt surface or configuration is audited.

Target: the current Codex GPT-6 auditor; model-independent consistency checks for
the shared Claude and Hermes instructions. No model migration, tool description,
request builder or subagent roster is in scope.

Independent review: this auditor did not author section 9. The controller supplied
the owner's authorization for the mandatory engine-output rule. The prior
self-review was read as context; the committed blobs were measured independently.

Result: no actionable findings. The section states concrete repair deliverables,
keeps execution within authorized scope and per-floor units, and preserves the
existing source, geometry, validation, acceptance and publication constraints.
Its 127 words contain no guard or threshold relaxation. No prompt edit is proposed.

Counts: Group 1 = 0; Group 2 = 0; Groups 3 and 4 = not applicable.
Remove/rewrite/move/replace-with-API-feature/add/flag = 0. Proposed diff: empty.

Procedure: [Anthropic Prompt Audit, Steps 0-6](https://raw.githubusercontent.com/anthropics/skills/main/skills/claude-api/shared/prompt-audit.md),
read 2026-10-23. The scoped inventory, blame, line classification, pattern scans,
report and proposed diff were completed. The rule is an owner delivery requirement,
not a retired-model workaround. No removal or behavioral change is proposed, so no
before/after behavioral probe applies; future compliance is not claimed tested.

Committed-text readback and `git diff --check d07dff4^ d07dff4 -- AGENTS.md` exited 0:

```json
{"previousSections1Through8Unchanged":true,"bindingSections3Through6Unchanged":true,"previousSectionsSha256":"31dad9416e9a4f221ea55456b204b50d968f38c6bd21902a3875fb75ea084dae","bindingSha256":"440b7cba7570c824bd89e18b2949a486cbb270ffcb4a2d1165ea23fe49d52e9a","addedSectionSha256":"8980ac94eb772118731e2950132a3f399b1cce07fb8e46ea426639e0537b91af","addedSectionWords":127,"section9Count":1}
```

Scoped signal counts: pressure = 0; scaffolds = 0; overspecification = 0;
fossils = 0; volatile paths/flags/URLs = 0. Blame assigns every added line to
`d07dff4`. This audit changes neither AGENTS.md nor code. Only this report and its
empty proposed diff are committed, as the controller explicitly requested.
