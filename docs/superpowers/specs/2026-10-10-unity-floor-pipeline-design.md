# Unity floor pipeline: engine-fixed floors that stay fixed in Unity (design)

**Status:** owner-approved direction, 2026-10-10. This spec is for the owner's review before any plan or code.
**Scope:** building floors and elements only (the units of `data/campus/campus_map.json`). The environment (terrain,
roads, water, rocks: `Assets/Models/Env/`) stays outside the engine, as the owner already keeps it separate.

## 1. The problem (owner, 2026-10-10)

- The owner sometimes fixes the model with AI inside Unity, and sometimes in Blender. Those fixed versions have no
  "original file" the engine knows about, so a rebuild can undo or duplicate them.
- **The engine's own fixed OBJ breaks when Unity imports it**, on the route "Engine OBJ → Unity". The symptoms:
  - holes or missing faces;
  - spikes or stretched triangles;
  - black, dark or inside-out faces;
  - wrong or missing textures.
- **The owner cannot spot every error by eye in Unity** (flicker, for example). So the pipeline cannot rely on the
  owner finding errors. **The engine must find them itself, in its own build and in what Unity actually shows.**
- The owner wants a record of each floor or building **outside Unity**.

## 2. Measured facts (read-only, 2026-10-10)

- **The Unity project** is `D:/PROJECTS/UC/01-UNITY/UC-Campus`, on Unity 6000.4.7f1 with URP 17.4.0.
  - It holds 693 campus OBJ files under `Assets/Models/Campus/` (CKPT5-CKPT17, CHTM-Fresh) and 74 environment
    files under `Assets/Models/Env/`.
  - Unity reads the OBJ files with its own importer.
- **`Assets/Editor/CampusModelImporter.cs` (an `AssetPostprocessor`)** sets, for every building model under
  `Assets/Models/Campus/`:
  - `weldVertices = true`;
  - `importNormals = Calculate`, with tangents `CalculateMikk`;
  - `generateSecondaryUV`, which unwraps lightmap UVs;
  - `addCollider = true`, `isReadable = true`, compression off;
  - a global scale (inches to metres) unless the path is pre-scaled.

  Each of these changes the geometry or its shading after the engine has written it. They are **suspects, not
  proven causes**; section 4 measures them.
- **Other editor scripts already measure the model:** `CampusAudit.cs`, `CampusDefectAudit.cs` and
  `CampusBuildingFloors.cs`. `CampusDoubleSided.cs` draws both sides (`_Cull = 0`).
- **The engine's error finder** (`engine/detectors/errors.py::find_errors`) knows 7 kinds: flicker (by material and
  by look), reversed, hidden, loose, open edges and cracks. The Validator judges to the owner's floor (AGENTS.md
  §5, "Visible rule, measured").

## 3. The design: five parts, built in this order

### Part 1: the Unity import check (built first; it answers "is the engine's fix still there in Unity?")

**Owner decision 2026-10-10: nothing is installed in the owner's Unity project.** Validation never runs inside
Unity: Unity only hands over the geometry it made, and the engine (Python) runs `find_errors` and the Validator on
it. There are two ways to get that geometry:

1. **A. The mirror Unity project, for every engine build (automatic).**
   - It is a small Unity project kept in this repo at `unity/ImportMirror/`, on the same Unity version (6000.4.7f1,
     installed at `D:\SOFTWARE\UNITY\Unity Hub\Editor\6000.4.7f1`).
   - It holds a read-only copy of the owner's `CampusModelImporter.cs`, refreshed and hashed each run, so it imports
     exactly as the real project does. It also holds its own exporter `UcFloorExport.cs`.
   - The engine runs Unity headless on it (`-batchmode -nographics -quit -executeMethod`): import the engine build,
     then write **exactly what Unity made of it**:
     - vertices, triangles, normals and UVs per submesh;
     - the material and texture per submesh;
     - the importer settings in force.
   - Output is an OBJ+MTL plus a JSON sidecar, in world coordinates, written to a temp folder.
   - The owner's project and open editor are never touched. Import settings can be varied here one at a time
     (section 3, Part 2) without risk.
2. **B. Reads of the owner's live Unity scene, on request, through the Unity MCP already in that project
   (`com.anklebreaker.unity-mcp`).**
   - When the owner asks to check a floor (or all floors), the engine sends a **read-only** command that reads that
     floor's meshes and materials as shown and writes the same OBJ+MTL+JSON to a folder outside the project.
   - Nothing is saved and no file is added to the project.
   - This finds what is wrong with floors already in Unity, including the owner's AI or hand fixes, and errors such
     as flicker that cannot be seen by eye.
   - If the Unity MCP cannot read mesh data, the fallback is an MCP command that runs the same export code in the
     editor without saving it as an asset. It needs the owner's OK for the first run.
2. **The engine's `engine.cli unity-check --build <engine floor OBJ> --unity <exported OBJ>`.** It compares the two
   with the engine's own tools:
   - face, vertex and triangle counts;
   - `find_errors` per kind, on both;
   - the Validator's before/after pictures, with the engine build as BEFORE and Unity's copy as AFTER, so any face
     Unity lost, moved or re-textured fails;
   - a per-cause breakdown: welded vertices, recomputed normals, UVs changed, materials remapped, faces dropped,
     submesh splits.
3. **Pass rule:** a floor is "Unity-safe" only when Unity's copy has the same faces, looks and UVs as the engine
   build, and `find_errors` on Unity's copy is no worse than on the build.

### Part 2: a Unity-safe export, then the per-floor loop

1. Part 1 measures each suspect import setting in section 2, one at a time, on golden floors (CHTM 5th, sidewalks A
   and B). From that, the engine writes the format and settings that pass, for example:
   - explicit per-face normals;
   - no weld;
   - 32-bit index buffers;
   - lightmap UVs written by the engine, or turned off.
   - Any change to `CampusModelImporter.cs` for building floors needs the owner's OK. It is proposed as a diff with
     measurements, never applied silently.
2. **The per-floor loop**, automatic and per unit:
   1. **Scan what Unity has now.** Route B reads the floor as the owner's scene shows it, and the engine runs
      `find_errors` and the Validator. The result is the floor's error map in the dashboard, with pictures; no eyes
      are needed.
   2. **Repair.** `engine.cli repair-unit`, with every engine merged so far.
   3. **Validate** to the owner's floor.
   4. **Import check (Part 1, route A).** The floor goes to Unity only if the mirror project's copy passes.
   5. **Swap.** A Unity editor action replaces only that floor's object. The owner triggers it at first.
3. **Triggers:**
   - the owner selects a floor in Unity and runs "Check & fix this floor";
   - or a batch over all floors, as a queued job (`tools/jobs.py`).

### Part 3: learning from the owner's Unity fixes and marks

- **A Unity mark ("this is wrong here"):**
  - the editor script records the floor, the world position, an optional note and a screenshot as a request;
  - the request becomes a queued job for that unit;
  - it also becomes a test fixture (the existing rule: every spot the owner marks wrong becomes a fixture).
- **A hand fix in Unity (or Blender):**
  - route B reads the fixed floor (a Blender fix is read from its exported file);
  - the engine compares it with its latest build and records the difference as an example, with the Validator's
    verdict;
  - accepted examples become fixtures, then rules;
  - the ML stage (P4) learns from them and never bypasses the rules (AGENTS.md §5, ML).

### Part 4: the floor record outside Unity

- **One folder per unit:** `MODEL FIXER ENGINE FILES\05-FIXING\<BUILDING>\<Lnn>\` (or the element name), holding:
  - `versions/`: v000 = CHECKPOINT-17, then each engine build or imported Unity/Blender fix, each with its OBJ,
    `report.json`, `validation.json`, the Unity check result and pictures;
  - `in_unity.json`: which version is in Unity now, and when it was swapped;
  - `requests/`: the owner's marks and their jobs;
  - `needs_modelling.json`: spots the engine cannot fix.
- **The dashboard** reads the same records. Only results built from committed code are published there
  (AGENTS.md §3).
- **The tracked current version** is per unit. The engine always repairs from the latest accepted version, so an
  accepted Unity or Blender fix is never undone.

### Part 5: the owner's check scene (owner request 2026-10-10)

The check scene is a separate Unity scene in the **mirror project** (`unity/ImportMirror/`). It holds every building
with **each floor or element as its own object, never merged into one building**. It is the owner's check files.

- **Why the mirror project:** it imports with the same rules as the owner's real project (a sha256-checked copy of
  `CampusModelImporter.cs`), so what the owner sees there is what the real project would show. The real project
  stays untouched, so the owner can open, move, hide or break anything in the check scene without risk.
- **Two layouts in one scene, switchable from a menu:**
  1. **Assembled in place.** Buildings stand at their campus positions; each floor is a separate GameObject the owner
     can show or hide.
  2. **Spread out side by side.** Per building, the floors in a row with labels (like the EDS comparison `.skp`):
     column pitch = the widest floor + 8 m, one row per building.
- **Each floor object is built from that floor's record (Part 4)** and labelled `<BUILDING> <Lnn> v<NNN>
  <verdict>` (PASS, FAIL or NEEDS MODELLING).
- **An optional error overlay** colours each floor's engine errors (flicker, holes, reversed, cracks, open edges) in
  the dashboard's colours, toggled per kind. It shows the glitches the owner cannot see by eye.
- **The scene is rebuilt by a headless batch command** whenever a floor gets a new version. The owner only opens it;
  it is never edited by hand. Opening it in the editor is the owner's choice.

## 4. Error handling and proof

- **The exporter's own check.** The mirror project round-trips an untouched engine build first. If Unity's copy
  differs, the report says why, by cause. That is the import diagnosis itself.
- **The mirror is checked against the real importer.** The mirror refuses to run when its copy of
  `CampusModelImporter.cs` does not match the owner's (by sha256); it re-copies first. So a change the owner makes in
  the real project cannot leave the check out of date.
- **No swap without a pass.** A floor whose Unity copy fails the check is never swapped in. The report names the
  cause.
- **Every tool's output is snapshotted with sha256**, as `engine/io/snapshot.py` does today, so a record can never
  point at a file that changed later.

## 5. Testing

- **Engine side (pytest):**
  - `unity-check` on synthetic pairs: an identical pair passes. Each of these must fail with its cause named:
    - a welded pair of coincident vertices;
    - recomputed normals that flip a face;
    - a dropped submesh;
    - a remapped material;
    - a shifted UV.
- **Unity side:**
  - Route A on a tiny known OBJ in the mirror project: under a no-op importer preset the exported OBJ matches the
    input.
  - Under the copied `CampusModelImporter.cs`, each changed setting is reported by cause.
  - Route B on one floor of the owner's open scene, read-only, once the owner allows the first read.
- **Golden floors:** CHTM 5th and sidewalks A and B, with the engine build → Unity → `unity-check` table before and
  after the import-setting changes.

## 6. Out of scope

- The environment models.
- Fixing inside Unity with C# (the engine stays the one repair tool).
- Blender as a repair route. Blender is only a source of owner fixes, imported like a Unity fix.

## 7. Open points for the owner

1. **Settled 2026-10-10:** nothing is installed in your Unity project. Route A (the mirror project, run headless) and
   route B (read-only reads through the Unity MCP) replace it. Your OK is still asked once: before the first route-B
   read of your open scene. Later, before the swap action, because it writes to your project.
2. Any change to `CampusModelImporter.cs` for building floors will be proposed with measurements and needs your OK.
3. Part 2's swap is manual (you press the button) until you say it may run automatically.
