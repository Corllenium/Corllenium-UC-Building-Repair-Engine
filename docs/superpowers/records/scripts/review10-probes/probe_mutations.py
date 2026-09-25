"""Mutation checks of brief-10 tests at dc24e9a: which tests FAIL when the mechanism they are named
for is switched off. A test that still passes does not pin that mechanism.

  M-a  `_refuse_together` a no-op (returns 0, refuses nothing).
  M-b  rule 6 off (`_through_closed_shell` allows nothing).
"""
import traceback

from _pytest.monkeypatch import MonkeyPatch

import engine
import engine.guard.compare as C
import engine.tests.test_guard as TG
import engine.tests.test_solidify as TS

print("engine:", engine.__file__)

TESTS = [
    ("test_solidify", "test_a_shell_is_refused_together_when_one_of_its_faces_fails", True),
    ("test_guard", "test_a_face_held_up_by_a_refused_face_is_refused_with_it_unless_another_holds_it",
     False),
    ("test_solidify", "test_a_top_edge_that_ran_into_an_underside_only_is_a_side", False),
    ("test_solidify", "test_a_railing_seen_through_an_open_slab_is_hidden_only_through_the_closed_slab",
     False),
]


def run(module, name, needs_mp):
    mod = TS if module == "test_solidify" else TG
    fn = getattr(mod, name)
    mp = MonkeyPatch()
    try:
        fn(mp) if needs_mp else fn()
        return "PASS"
    except AssertionError:
        return "FAIL (" + traceback.format_exc().strip().splitlines()[-1][:90] + ")"
    finally:
        mp.undo()


def never_through(start, direction, gap, entry, planes_after, shell_caster, shell_ids, interior):
    import numpy as np
    return np.zeros(len(start), bool), np.full(len(start), -1, np.int64)


for label, attr, repl in (("as committed", None, None),
                          ("M-a _refuse_together no-op", "_refuse_together", lambda *a, **k: 0),
                          ("M-b rule 6 off", "_through_closed_shell", never_through)):
    saved = getattr(C, attr) if attr else None
    if attr:
        setattr(C, attr, repl)
    try:
        for module, name, needs_mp in TESTS:
            print(f"[{label}] {name}: {run(module, name, needs_mp)}")
    finally:
        if attr:
            setattr(C, attr, saved)
