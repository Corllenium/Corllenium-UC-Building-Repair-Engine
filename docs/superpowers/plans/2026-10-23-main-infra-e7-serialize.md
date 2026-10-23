# Exact E7 Cut Serialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Save and independently bind exact source/engine pairs from actual checked existing-vertex E7 cuts.

**Architecture:** Reconstruct qualified stage inputs from original tables and E3 ancestry, verify actual kept kernel edits, then construct source-domain counterparts without inverse positions. Reuse precise write_floor, record per-face lineage and read every saved table back exactly before finalizing a fresh package.

**Tech Stack:** Python 3.12, NumPy, existing Minecraft FloorInput writer, repair kernel and SHA helpers.

**Spec:** docs/superpowers/briefs/MAIN-INFRA-E7-SERIALIZE-20261023.md and the approved cut-serialization proposal.

## Global Constraints

- No guards, thresholds, FixProfile, Validator, E3 core or existing tests changed.
- Original position tables and vertex IDs only; no inverse position reconstruction.
- Exact prefixes and checked cut-corner attributes, explicit E3 ancestry, frozen input hashes.
- No real-floor execution or publication.

## Review Focus

- Nonbinary attributes must survive saved readback exactly, beyond six decimals.
- E3 ancestry cannot silently become generated OBJ line numbering.
- Rolled-back cuts contribute no children and a fake PASS cannot ship them.
- Swapped UV/normal corners and changed materials cannot hide behind K1 keys.
- Readback failure and existing output directories must fail closed.

### Task 1: Checked pure pair and saved binding

**Files:** Create tools/main_infra_e7_serialization.py and tools/tests/test_main_infra_e7_serialization.py; record results in this job's ledger/report.

**Interfaces:** prepare_cut_pair(source_floor, engine_floor, before, input_lineage, outcome, looks, *, binding) -> CutPair; save_cut_pair(pair, out) -> receipt; bind_saved_cut_pair(source_floor, engine_floor, before, input_lineage, looks, candidate, *, binding, expected_receipt_sha256) -> (source_after, engine_after, receipt).

- [x] Write literal source-frame seam fixtures, actual checked E7 outcomes, trusted frozen input hashes and E3 source ancestry; run missing-module RED.
- [x] Implement pure input/outcome proof, exact source counterpart and deterministic output lineage using existing helpers.
- [x] Add precise save/readback and trusted receipt binding; use staged new output directories only.
- [x] Exercise nonbinary UV values, frame rotation, original table prefixes, kept/rolled children, log/hash/attribute tampering, wrong lineage, no overwrite and failed readback.
- [x] Run focused tests plus relevant E7/binding/serialization regressions; record actual results and commit only named files.
