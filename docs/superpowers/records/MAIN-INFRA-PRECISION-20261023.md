# Fresh MAIN INFRA physical precision validation integration

Base: signed Validator 33606ce94b7d08a09f72539a486aa5a3e293230b.
Integrated from reviewed ce73489: explicit physical axis quanta, topology cache
identity, native source/frame helpers and the hash-bound pilot wrapper/tests.
No engine/validate, guard, signed-target or FixProfile file differs from base.

Actual focused command: main Python -B -m pytest
engine/tests/test_physical_precision.py engine/tests/test_minecraft_floor.py
tools/tests/test_main_infra_physical_validation.py -q -p no:cacheprovider.
Output: 36 passed in 1.97s. The real textured fixture executes the signed
Validator with default settings and signed targets, writes/readbacks its report,
and checks overwrite refusal. Broader suite and real pilot reruns remain pending.

Independent feature review of ce73489: no remaining actionable findings;
70 tests passed in 5.39s. No floor pass or owner acceptance is implied.
