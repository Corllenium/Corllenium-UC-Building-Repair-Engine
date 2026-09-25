"""Probe: how wide a crack the merge OPENS does SR6's opened-crack rule (compare.py:640-669)
excuse as a border shift at the merge's 0.15 in tolerance? The test pins 0.02 in; this reuses its
own scene (`engine.tests.test_guard._crack_scene`, a slab 10 in above a lower surface) with wider
cracks. What AFTER's centre ray meets through the crack is never asked (the lower surface here).

usage: PYTHONPATH=<tree at e27eb79> .venv/Scripts/python.exe probe_opened_crack_width.py
"""
import numpy as np
import engine.tests.test_guard as tg

for gap in (0.02, 0.10, 0.20, 0.26, 0.29, 0.31, 0.40):
    tg._CRACK_GAP = gap
    P, faces_cracked, faces_closed, _ = tg._crack_scene()
    before, after, rep = tg._opened_crack_report(faces_closed, faces_cracked, 4,
                                                 border_shift_tol=tg._BORDER_TOL)
    opened = (before.tri >= 0) & (before.tri < 2) & (after.tri >= 2)
    t = rep.totals
    print(f"crack {gap:.2f} in: {int(opened.sum())} px fall through; border_shift {t['border_shift']}, "
          f"moved_other {t['moved_other']}, holes {t['holes']}, passed {rep.passed}")
