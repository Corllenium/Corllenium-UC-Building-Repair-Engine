# Exact E7 cut serialization handoff

Job MAIN-INFRA-E7-SERIALIZE-20261023, branch `codex/main-infra-e7-serialize-20261023`, base b603d39. Worktree `D:/LLM_BACKUP/Codex session/main-infra-e7-serialize-20261023/05-Corllenium-UC-Building-Repair-Engine`.

## API and proof

`tools/main_infra_e7_serialization.py` exports:

- `prepare_cut_pair(source_floor, engine_floor, before, input_lineage, outcome, looks, *, binding) -> CutPair`
- `save_cut_pair(pair, out) -> receipt` (returned dict includes `receipt_sha256`)
- `bind_saved_cut_pair(source_floor, engine_floor, before, input_lineage, looks, candidate, *, binding, expected_receipt_sha256) -> (source_after, engine_after, receipt)`

The first two FloorInputs contain original full source tables and their qualified forward-frame counterpart. `before` is the exact E3 survivor stage input handed to checked E7, including its qualified physical metadata. `input_lineage` maps those stage faces to original source triangle IDs. The source position table is never obtained by inverse transformation. Original UV/normal tables remain exact prefixes; only actual kept cut-corner rows are appended in existing apply_edits order. Constant source normals are copied; varying normals are refused by the b603d39 planner.

`binding` has `paths` and matching trusted `sha256` maps, plus `before_digest` from existing `_source_digest(before).hex()`. Required path keys are `raw`, `reference`, `qualification`, `provenance`, `baseline_source`, `baseline_engine`, `source_input`, `engine_input`, `lineage`, `edit_log`; extra frozen assets can be added to both maps and are hashed too. Paths refer to frozen owned inputs, never the live export. Hash values must come from the independently qualified input chain, not a newly accepted changed input. The independently qualified caller remains responsible for a complete asset inventory; this module writes no assets and changes no material library references.

The qualification contract follows the actual existing 1F file: qualified, nonempty floor_id/source_revision and source/native/baseline source/baseline engine SHA values. Frame evidence comes from hash-bound geometry-provenance.json, whose source/reference/baseline hashes and source_to_engine matrix are checked against source.in_frame(Frame(1000/25.4)). No source_to_engine field is invented in qualification.json. The controller supplied and rehashed the real 1F qualifier path before this contract was finalized; no real floor geometry was processed here.

The serializer verifies the actual plan/kept/rolled identity partition, sole nonlegacy rollback-enabled E7 check and last confirmed PASS for anything kept. K1 keys and actual log records are recomputed, but UV/normal protection does not rely on K1. Reapplying kept edits must exactly reproduce the actual outcome. Kept cuts must also match a fresh deterministic E7 planner result with its original-triangle/overlap/constant-normal admission proofs. A fake PASS with K1-equivalent altered UV/normal values is refused. Rolled-back cuts produce no children.

Each output face records its stage input face, original source triangle, original raw polygon line/group/object/material, edit/site/child and source/engine corner indices in cut-lineage.json. Generated OBJ face line numbers are separate. The receipt distinguishes `original_source_triangles`, `stage_input_triangles` and `output_triangles`. For real 1F cumulative comparison the original baseline is 15,856, not the E7 stage input 10,136. Both serialized frames retain all original position rows even where E3 removed faces.

write_floor's existing Decimal(repr(float)) formatter writes both frames. Every saved float64 table is reread and compared by dtype, shape and bytes (including signed zero), as are vertex/UV/normal indices and per-face material names. Object/group state is checked with parse_floor. Material reader IDs may differ by encounter; material names are the identity. A trusted expected receipt hash binds models, full checked edit payload, lineage, actual log, all input hashes and table digests. Saving stages a fresh .incomplete directory and finalizes only after readback; existing output directories are refused. Failed owned staging remains diagnostic and is not published.

## Measured tests

Initial RED: 25 failures in 4.64s; 24 were missing-module failures and one exposed a mixed-site fixture attribution-margin mistake. Moving the two fixture seams 100 inches apart produced the intended actual default SiteJudge outcome of one kept and one rolled-back cut; its remaining RED was the missing serializer. Initial GREEN: 25 passed in 5.40s.

The actual qualification schema was then pinned before correction: its RED failed the old guessed frame field. Expanded GREEN: 33 passed in 8.34s. The original/stage count distinction was separately pinned RED (missing original_source_triangles), then final focused GREEN: `33 passed in 7.77s`, exit 0.

Related command (before the count-only receipt addition):

```powershell
$env:PYTHONPATH=(Get-Location).Path
& 'D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' -m pytest tools/tests/test_main_infra_e7_serialization.py engine/tests/test_e7_thread.py tools/tests/test_main_infra_e3_serialization.py tools/tests/test_main_infra_e3_binding.py tools/tests/test_main_infra_physical_validation.py engine/tests/test_repair_uv.py -q -p no:cacheprovider --basetemp=data/test-tmp/e7-serialize-related/run --tb=short
```

Actual output: `132 passed in 19.82s`, exit 0. The final focused run covers all serializer tests and the added count fields. This is not a claim that the whole repository suite was run.

## Retained small artifact

`data/main-infra-e7-serialization/fixture-20261023/summary.json` and its candidate package were written and read back in this turn. Original source 3 triangles -> E3 stage input 2 -> E7 output 3; one kept cut; 5 position rows in each frame; original ancestors [2,1,1]. Original source positions and signed-zero normal prefix are bit-identical. All saved tables passed exact binding.

- Receipt SHA c8c6ff38058e822c94fa2db25fd96d1cf1053c5cab9b03b9ab502e218d5c4ada
- Source OBJ SHA 25abe914a6c1df5911c737cb7f21888dbca38b4c01f3b22a6835c0791bf6f250
- Engine OBJ SHA 6ccaaf6ce2198401e7f549ce13d6f551107bc03f53d00db19f673bf29c3de057

Only fixture artifacts were produced. No real-floor engine run, native render, full signed Validator pass, facade acceptance, dashboard publication or production change is claimed. Independent code review is the next gate; the controller owns actual input loading, real candidate generation, cumulative native/full validation and shared HANDOFF/session records.

## Real 1F caller example and mandatory asset gate

The geometry serializer FILES set covers models, lineage, checked payload and edit log only. Before any native check, full Validator run or publication, the caller must copy the original MTL/PNGs with existing copy_verified and verify every NEW candidate asset's SHA against the qualified asset inventory. Hashing original assets in binding does not prove that new copies were preserved. This remains an explicit caller gate; no asset framework or publisher is added here.

Concrete 1F path mapping (edit_log is the proposed new owned E7 run path; create it from the actual fresh checked outcome, never use the old E3 log):

```python
from pathlib import Path
clean = Path('D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/MAIN-INFRA-CLEAN-20261023/data/main-infra-fresh/run-20261023')
e3 = Path('D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/MAIN-INFRA-E3-20261023/data/main-infra-e3/run-20261023/1F')
paths = {
    'raw': clean / 'raw/1st floor main infra.obj',
    'reference': clean / 'reference/1F.json',
    'qualification': clean / 'independent-validator/import-audit/qualification-1F.json',
    'provenance': clean / 'normalized/1F/geometry-provenance.json',
    'baseline_source': clean / 'normalized/1F/before.source.obj',
    'baseline_engine': clean / 'normalized/1F/before.engine.obj',
    'source_input': e3 / 'candidate.source.obj',
    'engine_input': e3 / 'candidate.engine.obj',
    'lineage': e3 / 'source-faces.json',
    'edit_log': Path('D:/PROJECTS/UC MODEL FIXER/data/main-infra-e7/run-20261023/1F/edit-log.jsonl'),
}
binding = {
    'paths': {key: str(path) for key, path in paths.items()},
    'sha256': trusted_hashes,
    'before_digest': _source_digest(qualified_e3_before).hex(),
}
```

trusted_hashes must contain exactly the same keys (plus any extra explicitly bound original assets). Anchor raw/native/baselines/qualification/E3 pair/map to the existing qualified import and E3 receipts; record the provenance hash only after rechecking its existing frame derivation. Anchor the new edit-log hash to the actual fresh checked E7 outcome and freeze that run receipt. Do not fill a changed input's expected hash merely to make the binder accept it. The already bound E3 survivor count is the E7 stage input; the full original source remains the cumulative baseline.
