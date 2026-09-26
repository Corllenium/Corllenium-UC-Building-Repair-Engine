### Task 8: the catalogue's logic, and the content test

**Files:**
- Create: `web/src/utils/errorsDoc.ts`, `web/src/utils/errorsDoc.test.ts`, `web/public/docs/errors.json` (seed)

**Interfaces:**
- Produces (exported from `web/src/utils/errorsDoc.ts`):

```ts
export type Status = 'fixed' | 'partly' | 'open' | 'planned'
export type Verdict = 'error' | 'ok' | 'unsure'
export interface Example { image?: string; date?: string; words?: string; caption?: string; model?: string }
export interface Kind {
  id: string; title: string; summary: string; color: string            // color: '#rrggbb'
  models: Record<string, { status: Status; count: string }>             // keyed by model id
  what: string; find: string[]; why: string; why_note?: string
  unity: string[]; solution: string[]; never?: string[]; done: string[]; remain: string
  engine_files: string[]; examples: Example[]; sources: string[]
}
export interface EngineMistake {
  id: string; title: string; what_happened: string; how_caught: string; fix: string
  models: string[]; engine_files: string[]; commits?: string[]; examples: Example[]
}
export interface ModelCard { id: string; name: string; role: string; skp?: string; numbers: Record<string, number | number[]>; source: string }
export interface Catalogue {
  built_from: { commit: string; date: string }
  origin: string[]                       // intro paragraphs
  models: ModelCard[]; kinds: Kind[]; engine_mistakes: EngineMistake[]; other_screenshots: Example[]
}
export interface DocFilter { model: string | null; engine: string | null }
export interface VerdictEntry { verdict: Verdict; note: string; at: string }
export interface Validation { version: 1; verdicts: Record<string, Record<string, VerdictEntry>> }   // kind id -> model id -> entry

export const ENGINE_FILES: string[]      // the 13 files of the Global Constraints, in that order
export const STATUS_LABEL: Record<Status, string>   // Fixed / Partly fixed / Open / Planned, not fixed yet
export const VERDICTS: { id: Verdict; label: string }[]   // error 'Error, must fix'; ok 'OK for this model'; unsure 'Not sure'
export const IMAGE_NAME: RegExp          // /^[A-Za-z0-9_.-]+\.(png|webp|jpg)$/
export const WINDOW_HEADER = 48          // px of the floating window's title bar that must stay on screen
export function engineStem(file: string): string
export function statusLabel(s: Status): string
export function imageUrl(name: string): string      // '/api/docs/images/' + encodeURIComponent(name)
export function filterKinds(kinds: Kind[], f: DocFilter): Kind[]          // model: kind.models has the key; engine: in engine_files
export function filterMistakes(ms: EngineMistake[], f: DocFilter): EngineMistake[]   // model: in m.models; engine: in engine_files
export function filterChoices(cat: Catalogue): { models: { id: string; label: string }[]; engineFiles: string[] }
export function filterFromQuery(q: Record<string, unknown>, cat: Catalogue): DocFilter
export function openFromQuery(q: Record<string, unknown>, cat: Catalogue): string | null   // a kind or mistake id, else null
export function filterToQuery(f: DocFilter, open: string | null): Record<string, string>   // model, engine (stem), open
export function clampWindow(x: number, y: number, w: number, vw: number, vh: number): { x: number; y: number }
export function verdictOf(v: Validation | null, kindId: string, modelId: string): VerdictEntry | null
export function validationSummary(cat: Catalogue, v: Validation | null): { pairs: number; validated: number; error: number; ok: number; unsure: number }
export function validateCatalogue(cat: Catalogue): string[]
```

- [ ] **Step 1: Write the failing tests** (`web/src/utils/errorsDoc.test.ts`)

```ts
import { describe, it, expect } from 'vitest'
import {
  filterKinds, filterMistakes, filterChoices, filterFromQuery, openFromQuery, filterToQuery, clampWindow,
  statusLabel, imageUrl, engineStem, verdictOf, validationSummary, validateCatalogue,
  type Catalogue, type Kind, type EngineMistake, type Validation,
} from './errorsDoc'
import content from '../../public/docs/errors.json'

function kind(over: Partial<Kind>): Kind {
  return {
    id: 'k', title: 'T', summary: 'S', color: '#1f5bff', models: { A: { status: 'fixed', count: '1' } },
    what: 'W', find: ['F'], why: 'Y', unity: ['U'], solution: ['S1'], done: ['D'], remain: 'R',
    engine_files: ['vis/exposure.py'], examples: [], sources: ['report.json'], ...over,
  }
}

function mistake(over: Partial<EngineMistake>): EngineMistake {
  return {
    id: 'm', title: 'M', what_happened: 'H', how_caught: 'C', fix: 'F', models: ['A'],
    engine_files: ['guard/compare.py'], examples: [], ...over,
  }
}

const cat: Catalogue = {
  built_from: { commit: 'abc1234', date: '2026-09-26 12:00' },
  origin: ['Minecraft, Little Tiles, SketchUp, OBJ.'],
  models: [
    { id: 'CHTM5', name: 'chtm_5ft_floor', role: 'example, not fixed', numbers: {}, source: 's' },
    { id: 'A', name: 'CHTM_SIDE_WALK_2nd_floor', role: 'fixed file', numbers: {}, source: 's' },
    { id: 'B', name: 'CHTM_2nd_to_3rd_building_sidewalk_outside', role: 'fixed file', numbers: {}, source: 's' },
  ],
  kinds: [
    kind({ id: 'hidden-faces', engine_files: ['vis/exposure.py', 'fixes/remove.py'], models: {
      CHTM5: { status: 'planned', count: '12,870' }, A: { status: 'fixed', count: '2,065' }, B: { status: 'fixed', count: '2,771' } } }),
    kind({ id: 'gridlines', models: { A: { status: 'fixed', count: 'x' } }, engine_files: ['fixes/merge.py', 'topo/planes.py'] }),
    kind({ id: 'sawtooth', models: { B: { status: 'partly', count: 'y' } }, engine_files: ['fixes/solidify.py'] }),
  ],
  engine_mistakes: [
    mistake({ id: 'guard-blind', models: ['B'], engine_files: ['guard/compare.py'] }),
    mistake({ id: 'underside-top', models: ['A'], engine_files: ['fixes/solidify.py'] }),
  ],
  other_screenshots: [],
}

describe('errorsDoc', () => {
  it('filters kinds by the model they occur in and by engine file, combined', () => {
    const none = { model: null, engine: null }
    expect(filterKinds(cat.kinds, none).map(k => k.id)).toEqual(['hidden-faces', 'gridlines', 'sawtooth'])
    expect(filterKinds(cat.kinds, { ...none, model: 'CHTM5' }).map(k => k.id)).toEqual(['hidden-faces'])
    expect(filterKinds(cat.kinds, { ...none, model: 'A' }).map(k => k.id)).toEqual(['hidden-faces', 'gridlines'])
    expect(filterKinds(cat.kinds, { ...none, engine: 'fixes/solidify.py' }).map(k => k.id)).toEqual(['sawtooth'])
    expect(filterKinds(cat.kinds, { model: 'A', engine: 'fixes/solidify.py' })).toEqual([])
  })

  it('filters engine mistakes the same way', () => {
    expect(filterMistakes(cat.engine_mistakes, { model: 'A', engine: null }).map(m => m.id)).toEqual(['underside-top'])
    expect(filterMistakes(cat.engine_mistakes, { model: null, engine: 'guard/compare.py' }).map(m => m.id)).toEqual(['guard-blind'])
  })

  it('offers the models, and only the engine files something uses, in the fixed order', () => {
    const c = filterChoices(cat)
    expect(c.models).toEqual([
      { id: 'CHTM5', label: 'CHTM5 · chtm_5ft_floor' },
      { id: 'A', label: 'A · CHTM_SIDE_WALK_2nd_floor' },
      { id: 'B', label: 'B · CHTM_2nd_to_3rd_building_sidewalk_outside' },
    ])
    expect(c.engineFiles).toEqual(['vis/exposure.py', 'fixes/remove.py', 'fixes/solidify.py', 'fixes/merge.py',
      'guard/compare.py', 'topo/planes.py'])
  })

  it('reads the filter and the open window from the URL, ignoring unknown values', () => {
    expect(filterFromQuery({ model: 'B', engine: 'solidify' }, cat)).toEqual({ model: 'B', engine: 'fixes/solidify.py' })
    expect(filterFromQuery({ model: 'Z', engine: 'nope' }, cat)).toEqual({ model: null, engine: null })
    expect(filterFromQuery({ model: ['A', 'B'] }, cat).model).toBe('A')
    expect(openFromQuery({ open: 'gridlines' }, cat)).toBe('gridlines')
    expect(openFromQuery({ open: 'guard-blind' }, cat)).toBe('guard-blind')
    expect(openFromQuery({ open: 'nothing' }, cat)).toBeNull()
  })

  it('writes the filter and the open window back as a short query', () => {
    expect(filterToQuery({ model: 'A', engine: 'fixes/solidify.py' }, 'hidden-faces'))
      .toEqual({ model: 'A', engine: 'solidify', open: 'hidden-faces' })
    expect(filterToQuery({ model: null, engine: null }, null)).toEqual({})
    expect(engineStem('guard/piece_rays.py')).toBe('piece_rays')
  })

  it('keeps a dragged window s title bar on screen', () => {
    expect(clampWindow(100, 50, 560, 1600, 900)).toEqual({ x: 100, y: 50 })
    expect(clampWindow(-40, -10, 560, 1600, 900)).toEqual({ x: 0, y: 0 })
    expect(clampWindow(1500, 880, 560, 1600, 900)).toEqual({ x: 1040, y: 852 })
    expect(clampWindow(50, 50, 900, 700, 500)).toEqual({ x: 0, y: 50 })
  })

  it('labels statuses in plain words and builds image URLs through the API', () => {
    expect(statusLabel('planned')).toBe('Planned, not fixed yet')
    expect(statusLabel('partly')).toBe('Partly fixed')
    expect(imageUrl('you-0921-0346-1.png')).toBe('/api/docs/images/you-0921-0346-1.png')
  })

  it('reads the owner s verdicts and counts the validated kind-and-model pairs', () => {
    const v: Validation = { version: 1, verdicts: {
      'hidden-faces': { CHTM5: { verdict: 'error', note: '', at: 't' }, A: { verdict: 'ok', note: 'fine here', at: 't' } },
      gridlines: { B: { verdict: 'error', note: '', at: 't' } },     // B is not one of gridlines' models: not counted
      unknown: { A: { verdict: 'unsure', note: '', at: 't' } },
    } }
    expect(validationSummary(cat, v)).toEqual({ pairs: 5, validated: 2, error: 1, ok: 1, unsure: 0 })
    expect(validationSummary(cat, null)).toEqual({ pairs: 5, validated: 0, error: 0, ok: 0, unsure: 0 })
    expect(verdictOf(v, 'hidden-faces', 'A')?.note).toBe('fine here')
    expect(verdictOf(v, 'hidden-faces', 'B')).toBeNull()
    expect(verdictOf(null, 'hidden-faces', 'A')).toBeNull()
  })

  it('names every problem in a bad catalogue, in a fixed order', () => {
    const bad: Catalogue = {
      ...cat,
      kinds: [
        kind({ id: 'a', what: ' ', color: 'blue', models: { Z: { status: 'fixed', count: '1' } },
               engine_files: ['fixes/nope.py'], examples: [{ image: '../x.png' }] }),
        kind({ id: 'a', solution: [], models: { A: { status: 'maybe' as never, count: '1' } } }),
      ],
      engine_mistakes: [mistake({ id: 'm', fix: '', models: ['Q'] })],
    }
    expect(validateCatalogue(bad)).toEqual([
      'a: "what" is empty',
      'a: bad colour "blue"',
      'a: unknown model "Z"',
      'a: unknown engine file "fixes/nope.py"',
      'a: bad image name "../x.png"',
      'a: duplicate id',
      'a: "solution" has no steps',
      'a: unknown status "maybe"',
      'm: "fix" is empty',
      'm: unknown model "Q"',
    ])
    expect(validateCatalogue(cat)).toEqual([])
  })

  it('the committed errors.json is valid', () => {
    expect(validateCatalogue(content as unknown as Catalogue)).toEqual([])
  })
})
```

- [ ] **Step 2: Run and see them fail**

Run: `pnpm --dir web exec vitest run src/utils/errorsDoc.test.ts`
Expected: FAIL. `./errorsDoc` and `../../public/docs/errors.json` do not resolve.

- [ ] **Step 3: Implement** `web/src/utils/errorsDoc.ts` to the interface above. These rules are exact:
  - `ENGINE_FILES`, in this order: `vis/exposure.py`, `fixes/remove.py`, `fixes/solidify.py`, `fixes/merge.py`, `fixes/orient.py`, `fixes/overlap.py`, `detectors/fragments.py`, `detectors/folds.py`, `guard/compare.py`, `guard/piece_rays.py`, `io/skp_writer.py`, `topo/adjacency.py`, `topo/planes.py`.
  - `filterChoices`:
    - `models` are all of `cat.models` in order, labelled `` `${id} · ${name}` ``;
    - `engineFiles` are the `ENGINE_FILES` that any kind or engine mistake names, kept in `ENGINE_FILES` order.
  - `filterFromQuery`:
    - takes the first element of an array value;
    - `model` must be a model id and `engine` must be the stem of one of `filterChoices(cat).engineFiles`, which returns the full path;
    - anything else becomes `null`.
  - `openFromQuery` returns `q.open` when it equals a kind id or an engine-mistake id; otherwise `null`.
  - `filterToQuery` includes only the keys that are set, with `engine` as its stem.
  - `clampWindow`: `x = min(max(x, 0), max(0, vw - w))` and `y = min(max(y, 0), max(0, vh - WINDOW_HEADER))`.
  - `validationSummary`:
    - `pairs` counts every `(kind, model id)` in `kind.models`;
    - `validated`, `error`, `ok` and `unsure` count only those pairs that have a verdict;
    - verdicts for other ids are ignored.
  - `validateCatalogue`: one shared set of ids across kinds and engine mistakes.
    - **For each kind**, in array order, check in this order:
      1. duplicate id → `id: duplicate id`;
      2. each of `summary`, `what`, `why`, `remain` that is empty after trim → `id: "<field>" is empty`;
      3. each of `find`, `unity`, `solution`, `done` that has no non-empty item → `id: "<field>" has no steps`;
      4. `color` not matching `/^#[0-9a-fA-F]{6}$/` → `id: bad colour "<color>"`;
      5. for each `models` key in order: not a model id → `id: unknown model "<key>"`, then a status not in `STATUS_LABEL` → `id: unknown status "<status>"`;
      6. each engine file not in `ENGINE_FILES` → `id: unknown engine file "<file>"`;
      7. each example image not matching `IMAGE_NAME` → `id: bad image name "<name>"`.
    - **For each engine mistake**, check in this order:
      1. duplicate id;
      2. each of `what_happened`, `how_caught`, `fix` that is empty → `id: "<field>" is empty`;
      3. each model not a model id → `id: unknown model "<m>"`;
      4. engine files;
      5. example images.
    - **Last**, check each `other_screenshots` image, as `other_screenshots: bad image name "<name>"`.

  Then create the seed `web/public/docs/errors.json`. It must validate. Its content is the owner-approved "Hidden inside faces" kind (12:05), with the "How we find it" part the owner asked for at 12:15:

```json
{
  "built_from": { "commit": "ab22ff3", "date": "2026-09-25 23:53" },
  "origin": [
    "These models were built in Minecraft with the Little Tiles mod, exported, brought into SketchUp, and exported again as one OBJ per SketchUp group. Every step keeps all the geometry the step before made, so the OBJ carries what Little Tiles builds with: many small closed boxes on the block grid.",
    "This page lays out every kind of error found so far: what it is, how it is found, why the model has it, how much of each model it is, why it is unwanted in Unity, the solution, what was done, and why some can remain. It is a plan: nothing in any model is changed by it. Give your verdict per model in each error's window."
  ],
  "models": [
    { "id": "CHTM5", "name": "chtm_5ft_floor", "role": "Example building, not fixed: errors measured only", "numbers": { "triangles": 20599 },
      "source": "snapshot c0c877002500 (dashboard model 2, version 6)" },
    { "id": "A", "name": "CHTM_SIDE_WALK_2nd_floor", "role": "Sidewalk, fixed by the engine",
      "skp": "D:/PROJECTS/UC MODEL FIXER/OBJ FIXED RESULT/CHTM_SIDE_WALK_2nd_floor.fixed.skp",
      "numbers": { "triangles": [4692, 881], "back_faces_px": [569108, 18348] },
      "source": "data/output_verified/CHTM_SIDE_WALK_2nd_floor/report.json at ab22ff3" },
    { "id": "B", "name": "CHTM_2nd_to_3rd_building_sidewalk_outside", "role": "Sidewalk, fixed by the engine",
      "skp": "D:/PROJECTS/UC MODEL FIXER/OBJ FIXED RESULT/CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp",
      "numbers": { "triangles": [7227, 513], "back_faces_px": [464939, 2869] },
      "source": "data/output_verified/CHTM_2nd_to_3rd_building_sidewalk_outside/report.json at ab22ff3" }
  ],
  "kinds": [
    {
      "id": "hidden-faces",
      "title": "Hidden inside faces",
      "summary": "Faces inside the solid parts of the model that no camera outside can ever see.",
      "color": "#1f5bff",
      "models": {
        "CHTM5": { "status": "planned", "count": "12,870 of 20,599 triangles (62 %)" },
        "A": { "status": "fixed", "count": "2,108 of 4,692 triangles; 2,065 removed, 43 kept by the guard" },
        "B": { "status": "fixed", "count": "2,787 of 7,227 triangles; 2,771 removed, 16 kept by the guard" }
      },
      "what": "Faces inside the solid parts of the model: between two slabs, inside a wall, under a floor. They are real triangles in the OBJ, but no camera standing anywhere outside can ever see them.",
      "find": [
        "Take 4 points on each face: its centre, and three points near its corners (0.6 / 0.2 / 0.2 of the way to each corner).",
        "From every point, cast 128 rays spread evenly over all directions, on both sides of the face. The rays hit every other face of the object from either side, the way Unity and SketchUp draw them.",
        "A ray escapes when it leaves the object without hitting a face. A face is hidden when none of its rays escapes.",
        "When some rays escape but fewer than 5 % (the slit threshold, 0.05), the face is seen only through a thin gap: a 'slit' face. It is kept unless 'Accept slit faces' is on.",
        "The test sees this object alone. A face hidden only by a neighbouring building still counts as visible, because Unity may stream that neighbour out.",
        "Zero-area triangles are left out: they are their own kind of error."
      ],
      "why": "Little Tiles builds everything from small boxes (tiles) on Minecraft's block grid. Each tile is exported as a closed box with all six sides, including the sides pressed against a neighbouring tile, so a wall built from 16 small tiles carries every wall between every pair of tiles. SketchUp keeps every face it imports, and the OBJ export per group keeps them again. That is also why they come in pairs: two touching tiles give two faces on one plane, facing opposite ways. CHTM 5th floor has 13,947 such pairs.",
      "why_note": "Our reading of the measurements; we have not seen the exporter's code.",
      "unity": [
        "Unity still sends every one of those triangles to the GPU: 62 % of CHTM 5th floor is never seen.",
        "They take lightmap space and collider cost for nothing.",
        "Where a hidden face lies exactly on an outer surface, Unity cannot decide which one is in front, so it flickers.",
        "In X-ray and in SketchUp they fill the slabs with lines (the 09-21 screenshots)."
      ],
      "solution": [
        "Find them with the ray test above, never by guessing.",
        "Remove only those faces, never the sides of a slab or wall (owner's rule: only the inside).",
        "Guard every removal: render the object from 26 directions with and without the removed faces; if even one pixel of the outside changes, that face is put back.",
        "Check what is left in the dashboard: X-ray, and the blue 'Hidden inside faces' filter of the 3D viewer."
      ],
      "never": [
        "Blender's 'select interior faces' and delete: it deleted 88 % of this model once.",
        "Welding vertices farther apart than 0.1 mm.",
        "'Make Manifold' or 'Fill Holes': both closed real openings in this model before."
      ],
      "done": [
        "Sidewalk A: 2,065 removed, 43 put back by the guard.",
        "Sidewalk B: 2,771 removed, 16 put back by the guard.",
        "Both files pass every check.",
        "CHTM 5th floor: not touched. Planning only."
      ],
      "remain": "Faces seen through a real small gap are kept on purpose, so no hole opens. Faces the guard put back stay: removing them changed the picture, so they were visible after all.",
      "engine_files": ["vis/exposure.py", "fixes/remove.py", "guard/compare.py"],
      "examples": [],
      "sources": [
        "CHTM 5th floor: engine.cli errors on snapshot c0c877002500, 2026-09-26 (hidden 12,870)",
        "A and B: report.json at ab22ff3 (n_hidden_candidates, n_removed_hidden, n_restored_by_guard)",
        "Method: engine/vis/exposure.py (4 sample points, 128 directions, slit threshold 0.05); guard: engine/guard/compare.py (26 views)"
      ]
    }
  ],
  "engine_mistakes": [],
  "other_screenshots": []
}
```

- [ ] **Step 4: Run and see them pass**, then the type check

Run: `pnpm --dir web exec vitest run src/utils/errorsDoc.test.ts`, then `pnpm --dir web run type-check`.
Expected: 10 tests pass, and the type check exits 0. If `vue-tsc` rejects the JSON import, add `"resolveJsonModule": true` to `compilerOptions` in the tsconfig that includes `src` (check `web/tsconfig.app.json` or `web/tsconfig.json`), and list that file in the commit.

- [ ] **Step 5: Commit**

```bash
git add web/src/utils/errorsDoc.ts web/src/utils/errorsDoc.test.ts web/public/docs/errors.json
git commit -m "feat(web): the error catalogue's model, filters, verdict counts and content test" -m "The Errors page lays out every kind of error for the owner to validate before any fix phase; validateCatalogue enforces the spec's rules on the committed errors.json, which starts with the owner-approved 'Hidden inside faces' kind." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

