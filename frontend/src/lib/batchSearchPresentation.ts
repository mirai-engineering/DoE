import type { ProjectSchema } from './api.ts'
import { clampInteger, defaultTableTopK, defaultVisualizationTopK, enabledFixedInputValues, linspace, maxVisualizationTopK, toNumberMap } from './doeUtils.ts'
import type { FixedInputConfig, RecommendationRun } from '../types/doe.ts'

export type BatchSearchView = 'configure' | 'results' | 'visuals'

export const BATCH_SEARCH_TABS: Array<{ id: BatchSearchView; label: string }> = [
  { id: 'configure', label: 'Configure' },
  { id: 'results', label: 'Results' },
  { id: 'visuals', label: 'Visuals' },
]

export function buildBatchSearchRequest({ objectiveWeights, fixedInputs, nCandidates, tableTopK, visualizationTopK }: {
  objectiveWeights: Record<string, string>
  fixedInputs: FixedInputConfig
  nCandidates: string
  tableTopK: string
  visualizationTopK: string
}) {
  const requestedCandidates = clampInteger(nCandidates, 2000, 1, 100000)
  const requestedTableTopK = clampInteger(tableTopK, defaultTableTopK, 1, 25)
  const requestedVisualizationTopK = clampInteger(visualizationTopK, defaultVisualizationTopK, requestedTableTopK, maxVisualizationTopK)
  const requestedTopK = Math.min(Math.max(requestedTableTopK, requestedVisualizationTopK), requestedCandidates, maxVisualizationTopK)
  const weights = toNumberMap(objectiveWeights)
  const fixedInputValues = enabledFixedInputValues(fixedInputs)
  return {
    request: { objective_weights: weights, fixed_inputs: fixedInputValues, n_candidates: requestedCandidates, top_k: requestedTopK },
    run: { nCandidates: requestedCandidates, tableTopK: requestedTableTopK, visualizationTopK: requestedVisualizationTopK, requestedTopK, objectiveWeights: weights, fixedInputs: fixedInputValues },
  }
}

export function fixedInputSummary(schema: ProjectSchema, fixedInputs: FixedInputConfig) {
  const fixed = schema.inputs.filter((input) => fixedInputs[input.name]?.enabled).length
  return { fixed, sampled: Math.max(0, schema.inputs.length - fixed), label: `${fixed} fixed condition${fixed === 1 ? '' : 's'} · ${Math.max(0, schema.inputs.length - fixed)} variable${schema.inputs.length - fixed === 1 ? '' : 's'} sampled` }
}

export function objectiveRows(schema: ProjectSchema, weights: Record<string, string> | Record<string, number>) {
  return schema.outputs.map((output) => {
    const value = Number(weights[output.name] ?? 0)
    return { output, value, included: Math.abs(value) > 1e-12, influence: value > 0 ? 'Reward larger predictions' : value < 0 ? 'Reward smaller predictions' : 'Ignored' }
  })
}

export function recommendationRunSummary(run: RecommendationRun) {
  return {
    sampled: run.nCandidates,
    returned: run.recommendations.length,
    shortlist: Math.min(run.tableTopK, run.recommendations.length),
    visualized: Math.min(run.visualizationTopK, run.recommendations.length),
    bestScore: run.recommendations[0]?.score,
  }
}

export function isRecommendationRunStale(run: RecommendationRun | null, current: ReturnType<typeof buildBatchSearchRequest>['run']): boolean {
  if (!run) return false
  const stableEntries = (values: Record<string, number>) => Object.entries(values).sort(([a], [b]) => a.localeCompare(b))
  return run.nCandidates !== current.nCandidates || run.tableTopK !== current.tableTopK || run.visualizationTopK !== current.visualizationTopK || run.requestedTopK !== current.requestedTopK || JSON.stringify(stableEntries(run.objectiveWeights)) !== JSON.stringify(stableEntries(current.objectiveWeights)) || JSON.stringify(stableEntries(run.fixedInputs)) !== JSON.stringify(stableEntries(current.fixedInputs))
}

export function buildHeatmapRequestRows(schema: ProjectSchema, xAxis: string, yAxis: string, gridSize: string, inputValues: Record<string, string>) {
  const xInput = schema.inputs.find((input) => input.name === xAxis)
  const yInput = schema.inputs.find((input) => input.name === yAxis)
  if (!xInput || !yInput || xInput.name === yInput.name) return null
  const axisSteps = clampInteger(gridSize, 24, 8, 40)
  const xValues = linspace(xInput.min, xInput.max, axisSteps)
  const yValues = linspace(yInput.min, yInput.max, axisSteps)
  const baseInputs = toNumberMap(inputValues)
  const rows = yValues.flatMap((yValue) => xValues.map((xValue) => ({ ...baseInputs, [xInput.name]: xValue, [yInput.name]: yValue })))
  return { xInput, yInput, xValues, yValues, rows }
}

export function heatmapRequestFingerprint({ xAxis, yAxis, colorMetric, gridSize, inputValues, objectiveWeights }: { xAxis: string; yAxis: string; colorMetric: string; gridSize: string; inputValues: Record<string, string>; objectiveWeights: Record<string, number> }) {
  const sorted = (values: Record<string, string | number>) => Object.entries(values).sort(([a], [b]) => a.localeCompare(b))
  return JSON.stringify([xAxis, yAxis, colorMetric, gridSize, sorted(inputValues), sorted(objectiveWeights)])
}

export const candidateColors = ['#5BA8FF', '#F5B942', '#34D399', '#A78BFA', '#F472B6', '#22D3EE', '#FB923C']

export function nextBatchSearchView(active: BatchSearchView, key: 'ArrowLeft' | 'ArrowRight' | 'Home' | 'End'): BatchSearchView {
  const index = BATCH_SEARCH_TABS.findIndex((tab) => tab.id === active)
  if (key === 'Home') return BATCH_SEARCH_TABS[0].id
  if (key === 'End') return BATCH_SEARCH_TABS[BATCH_SEARCH_TABS.length - 1].id
  const offset = key === 'ArrowLeft' ? -1 : 1
  return BATCH_SEARCH_TABS[(index + offset + BATCH_SEARCH_TABS.length) % BATCH_SEARCH_TABS.length].id
}
