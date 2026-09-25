import { describe, it, expect } from 'vitest'
import { useGuardViews, getGuardImageUrl, DEFAULT_GUARD_VIEWS } from './useGuardViews'

describe('useGuardViews', () => {
  const views = ['+x', '-x', '+y', '-y', '+z', '-z']

  it('initializes with default views and first view selected', () => {
    const { currentView, availableViews } = useGuardViews(views)
    expect(availableViews.value).toEqual(views)
    expect(currentView.value).toBe('+x')
  })

  it('respects custom initial view', () => {
    const { currentView } = useGuardViews(views, '+z')
    expect(currentView.value).toBe('+z')
  })

  it('steps forward and backward with wrap around', () => {
    const { currentView, nextView, prevView } = useGuardViews(views, '+x')
    expect(currentView.value).toBe('+x')

    nextView()
    expect(currentView.value).toBe('-x')

    prevView()
    expect(currentView.value).toBe('+x')

    prevView() // wrap around to end
    expect(currentView.value).toBe('-z')

    nextView() // wrap around to start
    expect(currentView.value).toBe('+x')
  })

  it('handles keyboard navigation (ArrowRight / ArrowLeft / ArrowUp / ArrowDown)', () => {
    const { currentView, handleKeyDown } = useGuardViews(views, '+x')

    handleKeyDown({ key: 'ArrowRight' } as KeyboardEvent)
    expect(currentView.value).toBe('-x')

    handleKeyDown({ key: 'ArrowDown' } as KeyboardEvent)
    expect(currentView.value).toBe('+y')

    handleKeyDown({ key: 'ArrowLeft' } as KeyboardEvent)
    expect(currentView.value).toBe('-x')

    handleKeyDown({ key: 'ArrowUp' } as KeyboardEvent)
    expect(currentView.value).toBe('+x')
  })

  it('selects view directly', () => {
    const { currentView, selectView } = useGuardViews(views)
    selectView('+y')
    expect(currentView.value).toBe('+y')
  })

  it('generates correct guard image URL', () => {
    expect(getGuardImageUrl(42, '+x')).toBe('/api/runs/42/guard/%2Bx')
    expect(getGuardImageUrl(42, '-z')).toBe('/api/runs/42/guard/-z')
  })
})
