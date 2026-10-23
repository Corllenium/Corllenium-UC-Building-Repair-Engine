# Prompt audit: required engine output

Scope: the new AGENTS.md section 9, lines 163-173, at commit d07dff4 in the owned MAIN-INFRA-E3-20261023 worktree. Sections 3-6 were read as binding context and are outside the proposed-edit scope. CLAUDE.md and HERMES.md both direct their readers to AGENTS.md.

Target: the current Codex GPT-6 auditor, with model-independent checks for the shared Claude and Hermes instructions. No model migration, API configuration or tool-description changes are in scope.

Review mode: controller-authorized self-review. All four agent slots were occupied, so the required independent prompt-auditor subagent was not run. The controller can commission that independent pass when a slot is available.

Procedure: [Anthropic Prompt Audit, Steps 0-6](https://raw.githubusercontent.com/anthropics/skills/main/skills/claude-api/shared/prompt-audit.md), fetched 2026-10-23. Inventory and git blame identify d07dff4 as the owner-requested outcome rule. Its execution, deliverable and preservation clauses are project requirements, not model-era workarounds.

Result: no actionable finding in the added section. The rule requires engine execution and measurable candidate delivery while retaining the authorized scope, binding preservation rules, validation, acceptance and publication gates. The proposed audit diff is empty; no additional prompt edits are proposed.

Ledger: Group 1 = 0; Group 2 = 0; Groups 3 and 4 = not applicable. Remove/rewrite/move/add/flag = 0. Applied: the owner's requested section 9 in d07dff4; no audit hunks applied. Independent prompt-auditor review remains outstanding because of the recorded concurrency limit.

Verification: `git diff --check HEAD^ HEAD -- AGENTS.md` exited 0. A readback of d07dff4 and its parent produced:

```json
{"previousSections1Through8Unchanged":true,"bindingSections3Through6Unchanged":true,"bindingSha256":"440b7cba7570c824bd89e18b2949a486cbb270ffcb4a2d1165ea23fe49d52e9a","newSectionNumber9":1,"proposedAuditDiffBytes":0}
```
