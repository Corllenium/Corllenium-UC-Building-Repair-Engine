# Brief 05 — dashboard fix wave (D1-D12)

The full brief is `.superpowers/sdd/2026-09-22-dashboard-and-engine-continuation/fix-wave-1-brief.md`
(items D0-D12, from the review that judged the dashboard "Not ready"). Its ledger is
`.superpowers/sdd/2026-09-22-dashboard-and-engine-continuation/progress.md`.

Changes since that brief was written:
- **D0 is superseded** by the F5 merge (`e57462d`, asset-aware snapshot identity); only verify that
  `api/tests/test_versions.py` and `api/tests/test_importer.py` pass in any order.
- **D12 (a `.skp` per API run)**: the engine now has `engine/io/skp_writer.py::write_skp` and
  `engine/cli.py` already writes `<run dir>/<name>.fixed.skp` and copies it to `OBJ FIXED RESULT/`;
  the API run should call the same code path, not a copy of it.
- The AFTER panel (D3) must show what now ships: the merged, solidified, side-rebuilt result, the
  rollback state, `backface_px`, `border_shift`, and the `.skp` summary.

Rules specific to this wave: `api/`, `web/` and `api/tests` only; API tests drop the shared test
database, so never run them while another process does; verify on a spare port (127.0.0.1:8191)
before touching the live servers, and ask the owner before restarting the live API (8190) or web
(5190).
