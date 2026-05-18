import type { PredictionMap, Recommendation } from '../lib/api'

export const tabs = [
  { id: 'data-intake', label: 'Data Intake' },
  { id: 'preprocessing-review', label: 'Preprocessing Review' },
  { id: 'model-quality', label: 'Model Quality' },
  { id: 'design-studio', label: 'Design Studio' },
  { id: 'batch', label: 'Batch Search' },
  { id: 'optimization', label: 'Explore & Exploit Tests' },
  { id: 'impact', label: 'Business Impact' },
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
