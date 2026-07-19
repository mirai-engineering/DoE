export type DesignStudioView = 'single_result' | 'plot' | 'optimize' | 'compare' | 'model_map'
export type DesignResultState = 'loading' | 'error' | 'stale' | 'current' | 'empty'

export const DESIGN_STUDIO_TABS: Array<{ id: DesignStudioView; label: string }> = [
  { id: 'single_result', label: 'Single result' },
  { id: 'plot', label: 'Experiment visualization' },
  { id: 'optimize', label: 'Optimize' },
  { id: 'compare', label: 'Compare/export' },
  { id: 'model_map', label: 'Model map' },
]

export const plannedEngineeringChecks = [
  { title: 'Feasibility check', description: 'Screen a candidate against engineering and operating constraints.' },
  { title: 'Applicability check', description: 'Assess whether the point remains inside the model-supported domain.' },
  { title: 'Uncertainty estimate', description: 'Show calibrated confidence around each model estimate.' },
  { title: 'Explain with Mirai', description: 'Summarize the variables most responsible for this prediction.' },
]

export const plannedOptimizationCapabilities = [
  { title: 'Constraint builder', description: 'Express coupled engineering and manufacturability rules.' },
  { title: 'Robust optimization', description: 'Account for input tolerances and operating variation.' },
  { title: 'Optimization history', description: 'Compare saved searches, assumptions, and selected candidates.' },
]

export function designResultState({ loading, error, stale, hasPrediction }: { loading: boolean; error: boolean; stale: boolean; hasPrediction: boolean }): DesignResultState {
  if (loading) return 'loading'
  if (error) return 'error'
  if (stale) return 'stale'
  if (hasPrediction) return 'current'
  return 'empty'
}

export const designResultPresentation: Record<DesignResultState, { label: string; tone: 'neutral' | 'active' | 'success' | 'warning' | 'error' }> = {
  loading: { label: 'Generating estimate', tone: 'active' },
  error: { label: 'Estimate unavailable', tone: 'error' },
  stale: { label: 'Inputs changed', tone: 'warning' },
  current: { label: 'Estimate current', tone: 'success' },
  empty: { label: 'No estimate yet', tone: 'neutral' },
}

export function schemaBoundsSummary(inputCount: number): string {
  return inputCount === 1 ? '1 bounded input' : `${inputCount} bounded inputs`
}

export function isChampionReady(servedSource: unknown): boolean {
  return servedSource === 'loaded_champion'
}

export function nextDesignStudioView(active: DesignStudioView, key: 'ArrowLeft' | 'ArrowRight' | 'Home' | 'End'): DesignStudioView {
  const index = DESIGN_STUDIO_TABS.findIndex((tab) => tab.id === active)
  if (key === 'Home') return DESIGN_STUDIO_TABS[0].id
  if (key === 'End') return DESIGN_STUDIO_TABS[DESIGN_STUDIO_TABS.length - 1].id
  const offset = key === 'ArrowLeft' ? -1 : 1
  return DESIGN_STUDIO_TABS[(index + offset + DESIGN_STUDIO_TABS.length) % DESIGN_STUDIO_TABS.length].id
}
