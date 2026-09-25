"""Does `test_a_sign_standing_in_front_of_a_missing_side_is_never_a_piece(size)` (01cc420) fail
BEFORE its fix? Its fixture, `slab_with_half_side_and_a_sign`, is taken verbatim from dc24e9a's
build.py and run through the engine on PYTHONPATH (3561127, the commit before 01cc420, or dc24e9a),
exactly as the test runs it.

usage: PYTHONPATH=<tree> python probe_sign_test_before_fix.py <path to dc24e9a build.py>
"""
import ast
import sys

import numpy as np

import engine
import engine.tests.fixtures.build as B
from engine.fixes.pipeline import FixProfile
from engine.fixes.solidify import solidify
from engine.pipeline import analyse_topology

print("engine:", engine.__file__)
src = open(sys.argv[1], encoding="utf-8").read()
tree = ast.parse(src)
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
          and n.name == "slab_with_half_side_and_a_sign")
ns = dict(vars(B))
exec(compile(ast.Module(body=[fn], type_ignores=[]), sys.argv[1], "exec"), ns)
for size in (40.0, 2000.0):
    m, sign = ns["slab_with_half_side_and_a_sign"](size)
    r = solidify(m, analyse_topology(m), FixProfile(guard_size=(900, 600), n_dirs=32))
    print(f"size {size:g}: cap_guard_passed={r.report['cap_guard_passed']}, sign replaced "
          f"{r.replaced[sign].tolist()} -> the test {'PASSES' if not r.replaced[sign].any() else 'FAILS'}")
