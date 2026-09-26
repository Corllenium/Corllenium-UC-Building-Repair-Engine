## Global Constraints

- **No database change:** no migration, no table, no write to the live database `fixer`.
- **Images:**
  - The owner's screenshots and every render live in the git-ignored `data/errors_doc/img/` and are never committed.
  - `errors.json` names images by plain file name. A name must match `^[A-Za-z0-9_.-]+\.(png|webp|jpg)$`.
- **Read-only sources:**
  - The session log (`C:/Users/Future26/.claude/projects/D--PROJECTS-UC-MODEL-FIXER/5472478e-978d-426b-bab2-e7cf21699a70.jsonl`) is read, never written.
  - Nothing is ever written in `D:\PROJECTS\UC ENVIRONMENT BUILDING\...`.
- **Kinds** (id, label):

  | id | label |
  |---|---|
  | `inside-faces` | Hidden inside faces |
  | `sides-bottoms` | Sides and bottoms |
  | `lines-gridlines` | Lines and gridlines |
  | `back-faces` | Back faces |
  | `layers-flicker` | Double layers and flicker |
  | `fragments` | Fragments and slivers |
  | `engine-bug` | Engine bug |

- **Engine files:**
  - `vis/exposure.py`, `fixes/remove.py`, `fixes/solidify.py`, `fixes/merge.py`, `fixes/orient.py`, `fixes/overlap.py`;
  - `detectors/fragments.py`, `detectors/folds.py`;
  - `guard/compare.py`, `guard/piece_rays.py`;
  - `io/skp_writer.py`, `topo/adjacency.py`, `topo/planes.py`.

  In the URL query an engine file is its stem (`solidify` for `fixes/solidify.py`).
- **Sections:** `fixed` = "Fixed & partly fixed", `open` = "Still open", `engine-bug` = "Engine bugs from reviews", in that order. **Status:** `fixed`, `partly`, `open`.
- **Python:**
  - Use `"D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"` with `PYTHONPATH` set to the worktree root.
  - API tests: `-m pytest api/tests/<file> -q -p no:cacheprovider`. Each run gets its own `fixer_test_<pid>_*` database.
  - Tool tests: `-m pytest tools/tests/<file> -q -p no:cacheprovider`.
- **Web:**
  - `pnpm --dir web install --frozen-lockfile` once per fresh worktree.
  - Tests: `pnpm --dir web exec vitest run <file>`; types: `pnpm --dir web run type-check`; build: `pnpm --dir web run build`.
- **Commits:** stage files by name, never `git add -A`. End every message with a `Co-Authored-By:` line naming the model that wrote the commit.
- **Deploy:** only by HANDOFF.md section 8, from a commit, with the database backed up and the old images tagged first.

