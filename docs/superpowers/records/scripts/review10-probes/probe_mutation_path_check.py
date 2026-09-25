"""Mutation: rule 6 WITHOUT its path check (every sample counted inside). Which tests notice?"""
import inspect, traceback
import numpy as np
from _pytest.monkeypatch import MonkeyPatch
import engine, engine.guard.compare as C
import engine.tests.test_guard as TG, engine.tests.test_solidify as TS
print("engine:", engine.__file__)
src = inspect.getsource(C._through_closed_shell).replace(
    "np.logical_and.at(inside, owner, codes == INTERIOR_INSIDE)", "pass")
assert "pass" in src
ns = dict(vars(C)); exec(src, ns)
saved = C._through_closed_shell
C._through_closed_shell = ns["_through_closed_shell"]
for mod, name in ((TG, "test_a_view_is_through_the_slab_only_between_two_kept_shell_faces_inside_it"),
                  (TS, "test_a_fin_below_the_slab_is_still_refused_face_by_face")):
    try:
        getattr(mod, name)(); print(name, "PASS")
    except AssertionError:
        print(name, "FAIL", traceback.format_exc().strip().splitlines()[-2][:100])
C._through_closed_shell = saved
