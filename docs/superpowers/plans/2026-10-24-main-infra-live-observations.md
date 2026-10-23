# Live worker observations implementation plan

> Use superpowers:executing-plans for this single bounded task.

**Goal:** Show actual common3F checked E3 phases and independently registered validator CPU/liveness through the existing canonical status fields.

**Architecture:** Extend the existing embedded Python updater and PowerShell observation loop. A common replay registration binds the pinned preparation/run/floor/worker path/components and actual PID/creation. Validator observations update the existing UI fields only when the canonical row is already bound to that exact validator lifetime; verdicts and evidence stay untouched. Reuse the current atomic writer, transport and bounded histories.

**Tech stack:** PowerShell, Python3.12 stdlib, pytest; no network in fixtures.

**Spec:** docs/superpowers/records/briefs/MAIN-INFRA-LIVE-OBSERVATIONS-20261024.md

## Constraints and review focus

- Engine/guard/targets, production source/runtime and active repair worktrees stay untouched.
- Keep E7 and legacy2F/3F behavior; common3F uses the actual new preparation schema.
- Worker phase timestamps can follow process creation; bind creation from the observed process, never worker.started_utc.
- Wrong run/floor/P/path/PID/creation rejects; a stopped process cannot become a preservation pass.
- Validator lifetime mismatch cannot overwrite an active engine; successful observation cannot alter floor state/verdict/evidence.
- Histories keep100 entries, phase changes deduplicate, CPU samples require30seconds, no invented percent/ETA.

## Task1: Existing publisher extension

**Modify:** docs/superpowers/records/scripts/main-infra/live-worker-status-runtime.ps1
**Create tests:** tools/tests/test_live_status_common_observations.py
**Keep unchanged:** existing test_live_status_e3_tracking.py and live_status_publication_retry.ps1

- [x] Write extracted-embedded-Python tests with temporary genuine preparation/worker JSON and fake native process observations for all common phases, exact bindings, dead workers, legacy compatibility and validators.
- [x] Run bounded RED, mainvenv/BLAS1/Dtemp, whole owned tree cap250MiB.
- [x] Implement only the registered common3F and optional validator observation paths, retaining current transport/atomic health replacement.
- [x] Run new and existing publisher tests; run real D-temp first/second atomic health/retry fixture without network.
- [ ] Freeze named code/tests/records/brief/ledger; send runtime SHA, registry examples and actual outputs to root for independent review and installation. Do not deploy.
