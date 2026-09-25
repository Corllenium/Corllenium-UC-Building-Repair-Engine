"""Check of 170141f's exactness claim ("a crack 0.16 in wide along x at slope 0.4 is 0.149 in
across and passes; 0.20 in (0.186 across) fails"), with the suite's own crack scene and harness:
the crack's width along x is swept, the lower surface exposed, border tolerance 0.15 in."""
import engine.tests.test_guard as tg
print("engine:", tg.__file__)
for gap in (0.02, 0.14, 0.155, 0.16, 0.161, 0.162, 0.165, 0.17, 0.2, 0.29):
    tg._CRACK_GAP = gap
    P, cracked, closed, _ = tg._crack_scene()
    before, after, rep = tg._opened_crack_report(closed, cracked, 4, border_shift_tol=tg._BORDER_TOL,
                                                 exposed_after=tg._lower_exposed(True))
    opened = int(((before.tri >= 0) & (before.tri < 2) & (after.tri >= 2)).sum())
    across = gap / (1 + tg._CRACK_SLOPE ** 2) ** 0.5
    print(f"gap along x {gap:.3f} (across {across:.4f}): opened px {opened}, border_shift "
          f"{rep.totals['border_shift']}, moved_other {rep.totals['moved_other']}, passed {rep.passed}")
