import { describe, it, expect } from 'vitest'
import {
  filterKinds, filterMistakes, filterChoices, filterFromQuery, openFromQuery, filterToQuery, clampWindow,
  statusLabel, imageUrl, engineStem, verdictOf, validationSummary, validateCatalogue, LAYER_KINDS, catalogueModelId,
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

  it('checks titles, sources, and the ids and numbers the verdict API accepts', () => {
    const bad2: Catalogue = {
      ...cat,
      models: [
        { id: 'bad id', name: 'X', role: 'r', numbers: { triangles: [1, 2, 3] }, source: 's' },
      ],
      kinds: [
        kind({ id: 'Not_OK', title: ' ', sources: [''], models: {} }),
      ],
      engine_mistakes: [
        mistake({ id: 'mistake-1', title: '  ', models: [] }),
      ],
    }
    expect(validateCatalogue(bad2)).toEqual([
      'model bad id: id does not fit the verdict API',
      'model bad id: bad number "triangles"',
      'Not_OK: id does not fit the verdict API',
      'Not_OK: "title" is empty',
      'Not_OK: "sources" is empty',
      'mistake-1: "title" is empty',
    ])
    expect(validateCatalogue(cat)).toEqual([])
  })

  it('the committed errors.json is valid', () => {
    expect(validateCatalogue(content as unknown as Catalogue)).toEqual([])
  })

  it('maps each error layer to its catalogue kind', () => {
    expect(LAYER_KINDS).toEqual({
      grid: 'gridlines',
      tri: 'gridlines',
      hidden: 'hidden-faces',
      xray: 'hidden-faces',
      onesided: 'reversed-faces',
    })
  })

  it('finds the catalogue model with the same name as a workspace model, else null', () => {
    expect(catalogueModelId(content as unknown as Catalogue, 'chtm_5ft_floor')).toBe('CHTM5')
    expect(catalogueModelId(content as unknown as Catalogue, 'no_such_model')).toBeNull()
  })
})
