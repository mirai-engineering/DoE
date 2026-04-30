import type { PredictionMap, Recommendation } from '../lib/api'

export const tabs = [
  { id: 'batch', label: 'Batch Explorer' },
  { id: 'recommendations', label: 'Batch Results' },
  { id: 'visualizations', label: 'Batch Visuals' },
  { id: 'optimization', label: 'Optimization Loop' },
] as const

export type ActiveTab = (typeof tabs)[number]['id']

export type FixedInputConfig = Record<string, { enabled: boolean; value: string }>

export type RecommendationRun = {
  projectId: string
  projectDisplayName: string
  nCandidates: number
  tableTopK: number
  visualizationTopK: number
  requestedTopK: number
  objectiveWeights: Record<string, number>
  fixedInputs: Record<string, number>
  recommendations: Recommendation[]
}

export type HeatmapData = {
  xAxis: string
  yAxis: string
  colorMetric: string
  xValues: number[]
  yValues: number[]
  zValues: number[][]
  predictions: PredictionMap[]
}
