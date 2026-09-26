## Global Constraints

- **Read-only:** `find_errors` never changes the mesh. Nothing is ever written in `D:\PROJECTS\UC ENVIRONMENT BUILDING\...`. There is no database migration and no table.
- **Face numbers:** `find_errors` numbers faces exactly as `mesh.face_v` does. `engine/transport/meshbuf.py` writes `tri_face_id = arange(n_faces)`, so these are the viewer's triangle numbers.
- **Coordinates:** the errors file holds world coordinates in inches. The viewer subtracts the meshbuf header's `origin_offset` (`web/src/three/meshbuf.ts::MeshbufHeader.origin_offset`).
- **Kinds, in priority order** (a face in several kinds is drawn in the first):

  | Kind | Label | Colour | Drawn as |
  |---|---|---|---|
  | `flicker_diff` | "Flicker: texture on texture" | `0xd8282f` red | faces |
  | `flicker_same` | "Flicker: same material" | `0xf08c00` orange | faces |
  | `reversed` | "Reversed / back faces" | `0x9650ff` purple | faces |
  | `hidden` | "Hidden inside faces" | `0x1f5bff` blue | faces |
  | `loose` | "Zero-area and stray bits" | `0xe0199b` magenta | faces |
  | `open_edges` | "Open edges" | `0x16a34a` green | lines |
  | `cracks` | "Cracks (T-junction points)" | `0x00b4d8` cyan | points |
  | `facade` (Task 14; a layer, not an error) | "Facade (seen from outside)" | `0x0d9488` teal | faces, lowest priority, off by default |

  The facade is not in the engine's `KINDS` or `counts`; it is `layers.facade` / `layer_counts.facade`.

- **Files:** stored at `settings.data_dir / "errors" / f"version-{id}.json"` (git-ignored `data/`).
- **Python and tests:**
  - Python is `.venv/Scripts/python.exe` from the repo root.
  - Engine tests: `.venv/Scripts/python.exe -m pytest engine/tests -q -p no:cacheprovider`.
  - API tests: `.venv/Scripts/python.exe -m pytest api/tests -q -p no:cacheprovider`. Each session gets its own `fixer_test_<pid>_*` database.
  - Web tests: `pnpm --dir web exec vitest run`.
- **Commits:** stage files by name; never `git add -A`. End every message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Fixtures:** new engine fixtures are appended at the END of `engine/tests/fixtures/build.py`.
- **Deploy:** only by HANDOFF.md section 8, from a commit, with the database backed up and old images tagged first.

