# MAIN-INFRA-E7-ATTEMPT3-20261023

Status: implementation in progress; no real attempt3 kernel, candidate, native or Validator execution. Frozen attempt2 is unchanged.

The new donor-subset wrapper regenerates the original plan and matches every K1 record/input/component hash, then gives only donor-kept Edits to a NEW default real E7 kernel stage. The actual fresh result is authoritative. The narrow checkpoint preserves all eight mesh tables, full Edit fields/arrays, identities, checks and log before downstream serialization.

All273 exact-source preflight accepted273/rejected0 without kernel/candidate, with unchanged source digest and exact all628 K1 matching. Receipt SHA2565ef4f7d5a395f26ba1284819a35223e0c83a45e2a2dd02f0e88637d4c21f9e3b, script3ae97541eee4f5f8a1d0929774d6ad845d4691a1c5d860caa82142de3bdc2b33. The serializer owner preserved these and independent linkage in reviewed94dc8a4. Its code/test named paths are integrated here as2396ecd, with exact reviewed working-file SHA6456ac625441ce9c2649e088247ba73e094995858b074a127d7a54292365a44a.

## Actual bounded test output

All tests use the main venv interpreter, worktree PYTHONPATH and OPENBLAS/OMP/MKL/NUMEXPR thread counts1, D:/TEMP basetemp, no cache provider.

Checkpoint RED:
```
-m pytest tools/tests/test_main_infra_e7_checkpoint.py -q -p no:cacheprovider
13 failed in 3.79s
```
All failed because the new module was absent.

Checkpoint GREEN:
```
13 passed in 3.91s
```

Subset RED:
```
-m pytest tools/tests/test_main_infra_e7_subset.py -q -p no:cacheprovider --tb=short
16 failed in 6.26s
```
All failed because the new subset module was absent.

Subset/checkpoint GREEN:
```
-m pytest tools/tests/test_main_infra_e7_subset.py tools/tests/test_main_infra_e7_checkpoint.py -q -p no:cacheprovider --tb=short
29 passed in 9.85s
```
Real tiny SiteJudge fixtures passed; injected additional failing samples exercised charged rollback and whole-stage unknown refusal. The test window was released after actual process exit.

Runner implementation and tiny order/save/failure tests have completed RED/GREEN; independent implementation review and final focused regression are pending. Independent implementation review and resource GO are required before real execution. Original baseline15856, E3 stage10136; signed target failures remain unresolved/unmeasured after this new work.

Runner TDD and CLI (actual bounded second window):
```
-m pytest tools/tests/test_main_infra_e7_attempt3.py -q -p no:cacheprovider --tb=short
4 errors in 2.28s
4 passed in 3.90s
-m tools.main_infra_e7_attempt3 --help
exit0
```
RED was missing runner module. GREEN saved a real tiny new checked subset with NEW asset bytes and checkpoint-linked cut receipt. Injected downstream serializer failure left the actual checkpoint hash readable, worker failed, no candidate saved. All processes exited; window released. Real preparation/execute remains held for independent implementation review and fresh root resource GO.

Independent review found preparation/component drift during the kernel was not refused. Capture-first correction was approved by the reviewer: actual typed bytes are persisted before postflight, then original expected preparation/input/component hashes gate verified status and serialization. A drift failure keeps an explicitly diagnostic/unverified checkpoint and actual receipt SHA with failed worker/no candidate. Cut bindings never refresh changed preparation/checkpoint/log hashes as new truth.
```
-k drift: 3 failed, 17 deselected in 3.37s
checkpoint + runner: 20 passed in 8.78s
```
The root-approved bounded BLAS1 window was released after actual exit. No real preparation/kernel/candidate or full Validator execution.
