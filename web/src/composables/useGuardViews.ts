import { ref, computed } from 'vue'

export const DEFAULT_GUARD_VIEWS: string[] = ['+x', '-x', '+y', '-y', '+z', '-z']

export function getGuardImageUrl(runId: number, view: string): string {
  return `/api/runs/${runId}/guard/${encodeURIComponent(view)}`
}

export function useGuardViews(views: string[] = DEFAULT_GUARD_VIEWS, initialView?: string) {
  const availableViews = ref<string[]>([...views])
  const currentView = ref<string>(
    initialView && views.includes(initialView) ? initialView : views[0] || ''
  )

  const currentIndex = computed(() => availableViews.value.indexOf(currentView.value))

  function selectView(view: string) {
    if (availableViews.value.includes(view)) {
      currentView.value = view
    }
  }

  function nextView() {
    if (availableViews.value.length === 0) return
    const idx = currentIndex.value
    const nextIdx = (idx + 1) % availableViews.value.length
    currentView.value = availableViews.value[nextIdx]
  }

  function prevView() {
    if (availableViews.value.length === 0) return
    const idx = currentIndex.value
    const prevIdx = (idx - 1 + availableViews.value.length) % availableViews.value.length
    currentView.value = availableViews.value[prevIdx]
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      if (typeof e.preventDefault === 'function') e.preventDefault()
      nextView()
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      if (typeof e.preventDefault === 'function') e.preventDefault()
      prevView()
    }
  }

  return {
    availableViews,
    currentView,
    currentIndex,
    selectView,
    nextView,
    prevView,
    handleKeyDown,
  }
}
