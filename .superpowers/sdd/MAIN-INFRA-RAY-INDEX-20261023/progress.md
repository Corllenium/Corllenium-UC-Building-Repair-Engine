# Ray-index integration ledger

- Scope: reuse ce4e325 on b603d39; fail closed on nonfinite constructor input; no real-data run.
- Baseline: 15 caster tests passed in 1.25s.
- RED: 6 expected DID NOT RAISE failures in 1.24s for NaN/+Inf/-Inf referenced/unused vertices.
- GREEN: exact reviewed index reuse plus constructor finite refusal; focused 23 passed in 2.17s.
- Criterion methods and reused tree/search bodies match their original committed source.
- Broader isolated engine/tools suite active; no actual floor/API/DB run.
