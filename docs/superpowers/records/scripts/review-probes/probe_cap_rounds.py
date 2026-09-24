"""Probe: S-I2's premise. With cap_guard_max_rounds=1 on slab_with_partial_underside, is the loop
cut off AFTER a round that removed faces (the path whose verification S-I2 added), or does it
'converge and prove nothing' as the report says?"""
from engine.fixes.pipeline import FixProfile
from engine.fixes.solidify import solidify
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import slab_with_partial_underside

for rounds in (0, 1, 8):
    m = slab_with_partial_underside()
    r = solidify(m, analyse_topology(m), FixProfile(guard_size=(120, 80), n_dirs=32,
                                                    cap_guard_max_rounds=rounds))
    print(f"max_rounds={rounds}: history={r.report['cap_guard']}  "
          f"cap_guard_passed={r.report['cap_guard_passed']}")
