### Task 17: Jev decision helper — pilot (claude; owner OK 2026-10-03)

**Why.** The owner wants TypeSafe's Jev for fast decisions. Jev takes text plus typed questions:
- `Noul` (true or false);
- `Choice` (one of the given criteria, with probabilities);
- `Score` (an ordinal criterion).

Each answer comes with a confidence. Many questions go in one call (`TypeSafeClient().system_one(state=…, questions=…)`, package `typesafe-sdk`, key `TYPESAFE_API_KEY`, model `jev-latest`).

**Where it may be used:** soft, typed questions only, gated by confidence. A confident answer pre-fills; an uncertain one goes to the owner or the deterministic path.
- **Never** for deleting or keeping geometry, guard tolerances, or a Validator verdict (`AGENTS.md` §3, §6).
- Only text leaves the machine: group names, material names, report text. Never geometry.

**Files:**
- Create: `engine/decide/__init__.py`, `engine/decide/jev.py`, `engine/tests/test_decide_jev.py`.
- Modify: `pyproject.toml`, adding the optional group `decide = ["typesafe-sdk"]`.
- Add the CLI `decide-pilot`.

**Interface:**
```python
@dataclass
class Decision:
    answer: str | float | bool | None
    confidence: float
    probabilities: dict
    source: str            # "jev" | "none" (no key / no SDK) | "error"
    accepted: bool         # confidence >= the decider's min_confidence

class JevDecider:
    def __init__(self, client=None, min_confidence: float = 0.8, batch: int = 20): ...
    available: bool        # SDK importable and TYPESAFE_API_KEY set (or a client injected)
    def ask(self, state: str, questions: dict) -> dict[str, Decision]: ...

def classify_group_names(rows: list[dict], decider) -> list[dict]
#   rows: {"name", "tris", "z_min", "z_max", "footprint_building"}
#   asks: building (Choice over the AGENTS.md list + SITE), unit type (Choice: floor, stair, roof, shell,
#   road, landscape, bridge, other), floor number (Score 0-15), duplicate copy (Noul)
def classify_materials(names: list[str], decider) -> list[dict]
#   asks: category (Choice: glass, concrete, metal, wood, stone, plant, fabric, paint, other),
#   trim or patch material (Noul)
```

- [ ] **Step 1: Write the failing tests** (with a fake client: no network, no key):
  - `ask` maps a canned `system_one` response into `Decision`s;
  - `accepted` follows `min_confidence`;
  - 45 questions with `batch = 20` make 3 calls;
  - without a key or the SDK, `available` is False and every function returns `source = "none"`, `accepted = False`, with no network;
  - an SDK exception becomes `source = "error"` for that batch only;
  - the key never appears in any `repr`, log or exception text (assert on the captured output).
- [ ] **Steps 2-4:**
  - see the tests fail;
  - implement;
  - install `typesafe-sdk` into the project venv (`"$PY" -m pip install typesafe-sdk`; the owner approved it);
  - see the tests pass.
- [ ] **Step 5: Pilot measurement** (needs the owner's key in the environment of the process that runs it). `decide-pilot --source data/campus/source.json --materials data/campus/materials.json --out data/campus/jev_pilot.json` reports:
  - on the 85 group names, against the inventory's deterministic answers (Task 10; until then, the name-table truth) for building, type and floor:
    - the accuracy;
    - the coverage at confidence ≥ 0.8;
    - the accuracy within that coverage;
  - on the 391 materials: the category histogram and a 30-material spot check read by Claude;
  - the latency per call and the token usage.
- [ ] **Step 6:** report and commit `feat(decide): a confidence-gated Jev helper for soft typed decisions, piloted on group names and materials`.

**Done when** the pilot numbers are in the ledger and the owner decides where Jev stays: the inventory pre-fill, the material categories for E5, the tie-break suggestions in the floor review, or the review triage.

---

## Controller additions (2026-10-08) — these override the task text above where they differ

Worktree: `D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/P0-17`, branch `claude/P0-17`, base `83b89a8` (feat/repair-p0, green: 1273 passed).

### Facts from the live TypeSafe docs (read 2026-10-08; docs.typesafe.ai/sdk/python.md, /api.md, /primitives/*.md)
- `from typesafe_sdk import TypeSafeClient, Choice, Noul, Score, TypeSafeError, TypeSafeAPIError`.
- `TypeSafeClient(model="jev-latest")` reads `TYPESAFE_API_KEY` from the environment. An invalid key raises
  `TypeSafeError` at client creation. `TypeSafeAPIError` has `.status` and `.request_id`. HTTP 429 = rate limit.
- `client.system_one(state=<dict>, questions={id: Noul(instructions=...) | Choice(instructions=..., criteria={opt: None|description}) | Score(instructions=..., criteria=[level0, level1, ...])})`.
  `state` is a dict (named JSON fields); question ids are not sent to the model, so the instructions must be self-contained.
- Response: `response.answers[id]`, also typed `response.nouls[id].noul`, `response.choices[id]` (`.choice`, `.probabilities`, `.confidence`),
  `response.scores[id]` (`.score` float, `.probabilities` keyed by int level, `.confidence`). `response.model` (e.g. `jev-1.13.0`),
  `response.usage.input_tokens / output_tokens`.
- **A Noul has no `confidence`**: `.noul` is P(yes) in [0, 1].
- A Choice accepts up to 255 options. Questions in one call run in parallel.
- After installing the SDK, confirm these names against the installed package (`help(...)`/type hints) before relying on them; if any differs, follow the installed SDK and say so in the report.

### Rulings (controller)
1. **Noul mapping:** `answer = noul >= 0.5` (bool), `probabilities = {"yes": p, "no": 1 - p}`, `confidence = max(p, 1 - p)`.
2. **`state`:** `JevDecider.ask(state, questions)` accepts a `str` or a `dict`; a `str` is sent as `{"text": state}`.
3. **Key source (owner decision 2026-10-08):** use `TYPESAFE_API_KEY` from the process environment first. If it is not set, read the
   git-ignored repo-root `.env` and take ONLY the `TYPESAFE_API_KEY=` line (ignore every other line; strip quotes and whitespace),
   and pass it to the client explicitly; never put it into `os.environ`. The `.env` path is resolved from the repo root (the
   directory containing `pyproject.toml` of the running engine), and is a constructor parameter so tests use a tmp file.
   Never print, log, `repr`, or put the key in an exception message. Tests: env wins over `.env`; `.env` with other lines yields
   only the key; no env and no `.env` → `available is False`; the key string appears in no `repr`, captured log or exception text.
   **You (the implementer) never open the real `.env` file.** Tests use only `tmp_path` files with a fake key.
4. **Ground truth for the pilot:** `data/campus/campus_map.json` (owner-confirmed via P0-13), not the Task 10 inventory text.
   Its `buildings.<NAME>.groups` lists 78 of the 85 groups in `data/campus/source.json` (`manifest[].group`); groups in none of
   them are SITE. Building keys use underscores (`MAIN_INFRA`, `SCIENCE_A`); map them to the Choice options explicitly.
   Unit type and floor truth come from `units[]` (`unit`, `building`, `level`, `type`, `members`); if a group has no single
   unit, mark that field's truth as unknown and exclude it from accuracy (report the count).
5. **Materials:** `data/campus/materials.json` → `materials` (391 names; each has `map_kd`, `kd`, `look`). Send the name plus
   the texture file name (basename of `map_kd`) and `kd` as state text; never pixels.
6. **Pilot run:** the CLI must run end-to-end without a key and write `jev_pilot.json` with `source: "none"` counts. Do NOT run the
   real pilot with the key — the controller runs it. Do NOT write into `data/campus/` in tests; use `tmp_path`.
7. **SDK install:** the owner approved `"D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pip install typesafe-sdk`
   (2026-10-03, reconfirmed 2026-10-08). If the install is blocked by permissions, stop and report BLOCKED with the exact message;
   the wrapper must still work (and its tests pass) without the SDK, via the injected fake client.
8. Every Decision log line (if you add logging) records question id, source, confidence, latency, tokens — never the key, never state text longer than 200 chars.
