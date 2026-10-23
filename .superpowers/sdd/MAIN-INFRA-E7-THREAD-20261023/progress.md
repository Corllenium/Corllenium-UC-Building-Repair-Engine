# MAIN INFRA E7 threading ledger

- Job created and claimed via main `tools/jobs.py`; native isolated worktree created from 1302797, branch `codex/main-infra-e7-thread-20261023`.
- Baseline: `pytest engine/tests/test_merge.py -k 'thread or print_step_off' -q -p no:cacheprovider --basetemp=data/test-tmp/e7-baseline/run --tb=short`: 7 passed, 56 deselected in 1.49s.
- Plan and brief written before production code. No real-floor run authorized in this job.
- Controller reviewed/approved plan and brief after RED; prompt scope audit found no binding conflict.
- Ruling: combine planner and checked wrapper into one reviewable implementation commit, because the small visible and failure fixtures prove the safe entry together. No real-floor operation is part of the item.
- RED 13 then 17 expected missing-module failures; focused GREEN 17 passed in 1.13s.
- Related geometry/attribute/kernel verification: 191 passed in 67.52s, exit 0.
- Small fixture readback and actual engine QA image inspected. 2 -> 3 triangles, one kept site, same material names/geometry; UV roundtrip max 2.22e-16, normal error 0. Generic six-decimal UV/vn writer is not claimed adequate for arbitrary fresh cuts.
- API and required future input/serialization/native/full-validation proof recorded in MAIN-INFRA-E7-THREAD-20261023.md. No real floor run or candidate output.
