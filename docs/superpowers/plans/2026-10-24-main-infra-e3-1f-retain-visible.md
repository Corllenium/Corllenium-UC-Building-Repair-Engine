# Visible 1F E3 retention implementation plan

> **For agentic workers:** Use superpowers:executing-plans for the root-assigned native implementation. Code/TDD only until independent review and root phase GO.

**Goal:** Keep the274 original faces in E3site5 and check the remaining original proposals afresh.
**Architecture:** Reuse load_replay_plan/run_checked_replay with explicit restore_sites=(5,), qualified physical input loading, source_survivors and save_survivor_pair. Add only an E3-remove checkpoint adapter using the existing typed/array primitives and a narrow evidence-bound prepare/execute caller.
**Tech Stack:** Python3.12/NumPy, existing OBJ engine and default kernel/SiteJudge.
**Spec:** docs/superpowers/records/briefs/MAIN-INFRA-E3-1F-RETAIN-VISIBLE-20261024.md.

## Constraints and review focus

- Original283/280/3 and whole site5/274 remain distinct from proposed279 or actual fresh rollbacks. All283 original K1 records must verify before selecting.
- Preserve original full position/UV/normal tables, source face/material order and explicit survivor IDs; no E7 stage-index reuse.
- Capture actual mesh, typed edits, kept/rolled identity partition, checks and records before risky serialization. Wrong hashes, references, archive entries or input/code drift refuse reuse while diagnostic capture remains.
- Bind actual a84 attribution,7864lostlines,7732provenance and original audit/map/log/source/material/target/assets; old signedPASS never becomes new proof.
- Default FixProfile/SiteJudge/validate_sites=True, guards/targets/serializer unchanged. Explicit failing sightlines travel in the preparation for independent proof.

## Task1: E3-only checked checkpoint

Create tools/main_infra_e3_checkpoint.py and tools/tests/test_main_infra_e3_checkpoint.py. Reuse existing _partition/_digest/typed_edits/MESH_ARRAYS; E3 removes have no new arrays. Test actual default rollback capture, exact restore, full typed fields/metadata, tamper/archive/partition/input-drift refusal, retained capture after later failure. RED→GREEN under250MiB; named commit.

## Task2: Evidence-bound invocation and serialization

Create tools/main_infra_e3_visible_run.py and tools/tests/test_main_infra_e3_visible_run.py. Implement prepare/execute CLI in new run-20261024-1F-retain-visible namespace, pin the original cohort/evidence, explicitly pass(5,) to existing replay APIs, save checkpoint first and verify frozen preparation/components before source serialization. Reuse exact survivor writer/assets copier, bind saved pairs and all274 retained faces, separate pending guard/independent status and actual errors/receipts. Test wrong namespace/policy/pins, preserved cohort and checkpoints-before-serializer even on failure. RED→GREEN tiny batches; actual CLI/component smoke only, no real prepare/run before root GO.

## Task3: Frozen handoff

Commit named files, brief, policy and measured test/resource records. Supply exact CLI/profile/output paths and independent required14 sightlines; root/independent reviewer releases actual phases. No model acceptance or publication claim.
