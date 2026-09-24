"""Probe: does a FAILED run (exit 2) still overwrite the owner's .skp copy?
Same forced failure as test_cmd_fix_exits_two_when_a_visible_face_is_wrongly_removed."""
import json
import sys
import tempfile
from pathlib import Path

import engine.cli as cli
import engine.fixes.pipeline as fix_pipeline
from engine.tests.fixtures.build import box_with_partition
from engine.tests.test_cli import _FAST, _write_snapshot


def bad_guard_feedback(candidates, positions_c, faces, face_material, flat_materials,
                       depth_tol, strict, **kw):
    removed = candidates.copy()
    removed[0] = True          # a real, visible outer face, removed on purpose
    return removed, [{"round": 0, "candidates_remaining": int(removed.sum()),
                      "failing_pixels": 0, "restored": 0}]


fix_pipeline.guard_feedback = bad_guard_feedback

with tempfile.TemporaryDirectory(dir=sys.argv[1]) as tmp:
    tmp = Path(tmp)
    m = box_with_partition()
    snap = _write_snapshot(tmp, m)
    skp_dir = tmp / "OBJ FIXED RESULT"
    skp_dir.mkdir()
    owner_copy = skp_dir / f"{m.name}.fixed.skp"
    owner_copy.write_bytes(b"the last PASSING run's file")
    code = cli.cmd_fix(snap, tmp / "out", accept_slit=False, profile=_FAST, skp_dir=skp_dir)
    report = json.loads((tmp / "out" / m.name / "report.json").read_text(encoding="utf-8"))
    print("exit code:", code, " passed:", report["passed"],
          " guard_final holes:", report["guard_final"]["totals"]["holes"])
    print("skp written:", report["skp"]["written"], " copied_to:", report["skp"]["copied_to"])
    print("owner's copy overwritten:", owner_copy.read_bytes() != b"the last PASSING run's file",
          f"({owner_copy.stat().st_size} bytes now)")
