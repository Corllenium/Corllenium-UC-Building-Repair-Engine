# Task K1 brief (extracted verbatim from docs/superpowers/plans/2026-10-03-repair-engine-p1-p2.md, lines 91-126)

### Task K1: repair types (claude)

**Files:** Create `engine/repair/__init__.py`, `engine/repair/types.py`, `engine/tests/test_repair_types.py`.

**Interfaces (produced, consumed by every engine and the kernel):**
```python
FaceKey = str     # sha256 of the 3 vertices snapped to the print step (sorted per face, winding kept) + look key

@dataclass(frozen=True)
class Edit:
    engine: str                    # "E1" .. "E8"
    kind: str                      # "remove" | "flip" | "add" | "cut"
    faces: tuple[int, ...]         # input face ids it removes, flips or replaces
    new_faces: np.ndarray | None   # (k, 3) vertex ids for "add" / "cut"
    new_points: np.ndarray | None  # (m, 3) new positions: only E8 solidify and the E5 cut
    site: int
    reason: str
    evidence: dict                 # the numbers behind it: exposure, coverage, areas, look keys
    decision: dict | None = None   # {"question", "provider", "answer", "confidence"} when the Decider was asked

@dataclass
class UnitState:  mesh: MeshData; topo; looks: dict[int, str]; viewpoints; neighbours: list[MeshData]
@dataclass
class RepairContext: profile: FixProfile; decider; validator; log: list
class RepairEngine(Protocol):
    name: str
    def plan(self, unit: UnitState, ctx: RepairContext) -> list[Edit]: ...
def face_keys(mesh: MeshData, looks: dict[int, str]) -> list[FaceKey]
def apply_edits(mesh: MeshData, edits: list[Edit]) -> tuple[MeshData, np.ndarray]   # new mesh + new→old face map
```

**Exit:**
- `face_keys` is stable under face and vertex reordering (property test);
- `apply_edits` with no edits returns an identical mesh;
- remove, flip, add and cut round-trip on fixtures;
- an `Edit` with `new_points` from any engine other than E5 or E8 raises.

## Controller rulings (pre-flight, binding for this task)
- K1-R1: `Edit` is `@dataclass(frozen=True, eq=False)` (ndarray fields; equality is never used).
- K1-R2: `engine/repair` computes its own print step from the OBJ's printed precision, `MeshData.coord_decimals` (step = 10 ** -coord_decimals); it does NOT import `engine/validate`, and the validator never imports `engine/repair`.
