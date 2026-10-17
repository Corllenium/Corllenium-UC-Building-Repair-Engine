# Blender staging Tasks 1-3 verification ledger

Job: STAGING-T123-V1. Spec: owner's 2026-10-17 request and `docs/superpowers/records/briefs/STAGING-T123-V1.md`. Checkouts explicitly named by owner: main and `.hermes/worktrees/siege-jev-gate`.

- [x] Compared the five named files. Three implementation files were already identical; copied the two missing main tests from the worktree, then measured identical SHA-256s for all five. No foreign source edits.
- [x] Ran the five requested pytest modules with the specified interpreter and explicit per-checkout PYTHONPATH. Main: 81 passed in 2.58s, exit 0. Worktree: 81 passed in 2.58s, exit 0. Short D: basetemps avoid a measured 271-character Windows CopyFile2 path failure from the initial long scratch location. No code changes were needed.
- [x] Compiled/imported both runners safely from both working directories. Both import siege-jev-gate's engine by explicit source configuration. Remaining runner --stages parsing/forwarding passes. Third/fourth runner does not parse CLI arguments; normal --help was deliberately not invoked because it would execute floor work.
- [x] Separate read-only Blender 5.1.2 inspection: receipt and all 12 floor signatures/OBJ material slot names match across library/buildings/current environment collection. Combined current CHTM LOD0 44,669 vertices/99,310 triangles. Buildings self-contained; restored ceiling present, local/nonhidden, 188 vertices/171 triangles. Receipt/.blend hashes, sizes and mtimes unchanged; exit 0, all_checks_passed=true, failed_checks=[]. No visual owner/Validator pass claimed.
- [x] Prepared a review-only third/fourth runner patch, with five mocked checks (original: three expected failures; candidate: all five pass) and clean patch applicability. Original remains unchanged. Explicit owner exception requested because AGENTS.md section 3 protects pre-existing untracked files.
- [ ] Apply runner patch only if owner grants that exception, then rerun actual runner CLI checks. Verification result currently carries this one acceptance gap.

Actual commands/output, hashes, limitations, and local evidence paths: `docs/superpowers/records/STAGING-T123-V1-report.md`. HANDOFF section 2 and session history updated. Queue status will reflect hand-in for review, not a claim that the missing runner CLI is implemented.
