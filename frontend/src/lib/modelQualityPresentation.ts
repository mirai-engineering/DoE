import type { ProjectSchema } from './api.ts'

export type ModelQualityView = 'overview' | 'outputs' | 'diagnostics' | 'artifacts'
export type TrustLevel = 'strong' | 'usable' | 'weak' | 'needs_review'

export type OutputTrustData = {
  output: ProjectSchema['outputs'][number]
  validation: Record<string, unknown>
  test: Record<string, unknown>
  level: TrustLevel
  label: string
  sortScore: number
  interpretation: string
}

export const MODEL_QUALITY_TABS: Array<{ id: ModelQualityView; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'outputs', label: 'Outputs' },
  { id: 'diagnostics', label: 'Diagnostics' },
  { id: 'artifacts', label: 'Artifacts' },
]

export const splitPresentation = {
  train: { label: 'Train', color: '#94A3B8', purpose: 'Fits model parameters.' },
  validation: { label: 'Validation', color: '#F5B942', purpose: 'Selects and compares candidates.' },
  test: { label: 'Test', color: '#5BA8FF', purpose: 'Untouched final quality evaluation.' },
  bo_holdout: { label: 'BO replay', color: '#A78BFA', purpose: 'Reserved for optimization replay.' },
} as const

export function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

export function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

export function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function formatR2(value: number | undefined): string {
  return value === undefined ? '—' : value.toFixed(3)
}

export function formatPercent1(value: number | undefined): string {
  return value === undefined ? '—' : `${value.toFixed(1)}%`
}

export function formatMetric(value: number | undefined, unit = ''): string {
  if (value === undefined) return '—'
  const formatted = Math.abs(value) >= 100 ? value.toFixed(1) : Number(value.toPrecision(3)).toString()
  return unit ? `${formatted} ${unit}` : formatted
}

export function friendlyModelName(value: string): string {
  const labels: Record<string, string> = {
    mean_baseline: 'Mean baseline',
    mlp: 'MLP',
    mvlr: 'Multivariate linear regression',
    mean: 'Mean baseline',
    ridge: 'Ridge regression',
  }
  return labels[value] ?? value.replace(/_/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase())
}

export function friendlyStatus(value: unknown): string {
  const raw = asString(value)
  const labels: Record<string, string> = {
    loaded_champion: 'Champion loaded',
    champion_not_loaded: 'Champion not loaded',
    candidate_review: 'Candidate awaiting review',
    candidate_ready_for_review: 'Candidate ready for review',
    approved_champion_active: 'Approved champion active',
    awaiting_local_run_import: 'Awaiting training run',
    placeholder_not_active: 'Not active',
    pending_preprocessing_approval: 'Pending preprocessing approval',
    available: 'Available',
    unavailable: 'Unavailable',
  }
  return labels[raw] ?? (raw ? raw.replace(/_/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase()) : 'Unavailable')
}

export function artifactDisplayName(value: string): string {
  const filename = value.split('/').pop() ?? value
  const labels: Record<string, string> = {
    'metrics_summary.json': 'Model metrics summary',
    'candidate_comparison.csv': 'Candidate comparison',
    'predictions.csv': 'Diagnostic predictions',
    'training_manifest.json': 'Training manifest',
    'preprocessing.json': 'Fitted preprocessing parameters',
    'preprocessing_report.json': 'Preprocessing report',
    'schema.json': 'Training schema',
    'model.onnx': 'Served ONNX model',
  }
  return labels[filename] ?? filename.replace(/[_-]/g, ' ').replace(/\.[^.]+$/, '').replace(/\b\w/g, (character) => character.toUpperCase())
}

export function classifyOutputTrust(metrics: Record<string, unknown>) {
  const r2 = asNumber(metrics.r2)
  const maeMean = asNumber(metrics.mae_percent_of_split_mean)
  const improvement = asNumber(metrics.baseline_improvement_mae_percent)
  if (r2 === undefined && maeMean === undefined) return { level: 'needs_review' as TrustLevel, label: 'Needs review', sortScore: -Infinity, interpretation: 'Test evidence is incomplete for this output. Review the detailed metrics before using it in optimization.' }
  if ((r2 ?? -Infinity) >= 0.75 && (maeMean ?? Infinity) <= 20) return { level: 'strong' as TrustLevel, label: 'Strong', sortScore: (r2 ?? 0) * 100 - (maeMean ?? 0), interpretation: 'This output is suitable for optimization-driven ranking, assuming candidates remain within the training data domain.' }
  if ((r2 ?? -Infinity) <= 0.05) return { level: 'weak' as TrustLevel, label: 'Weak', sortScore: (r2 ?? -1) * 100 - (maeMean ?? 100), interpretation: 'This output performs close to or worse than a simple baseline. Avoid using it as a dominant optimization objective until the model improves.' }
  if ((r2 ?? -Infinity) >= 0.5 || (maeMean ?? Infinity) <= 30) return { level: 'usable' as TrustLevel, label: 'Usable with review', sortScore: (r2 ?? 0) * 100 - (maeMean ?? 0) + Math.max(0, improvement ?? 0) * 0.1, interpretation: 'This output can support recommendations, but it should not dominate the objective without expert review.' }
  return { level: 'weak' as TrustLevel, label: 'Weak', sortScore: (r2 ?? -1) * 100 - (maeMean ?? 100), interpretation: 'This output is weakly predicted. Recommendations heavily weighted toward this KPI should be treated cautiously.' }
}

export function buildOutputTrustData(schema: ProjectSchema, bestModel: Record<string, unknown>): OutputTrustData[] {
  const splits = asRecord(bestModel.splits)
  const validation = asRecord(splits.validation)
  const test = asRecord(splits.test)
  return schema.outputs.map((output) => ({ output, validation: asRecord(validation[output.name]), test: asRecord(test[output.name]), ...classifyOutputTrust(asRecord(test[output.name])) }))
}

export function splitMean(model: Record<string, unknown>, split: string, metric: string): number | undefined {
  const splitData = asRecord(asRecord(model.splits)[split])
  const explicitMean = asNumber(splitData[`mean_${metric}`])
  if (explicitMean !== undefined) return explicitMean
  const values = Object.values(splitData).map((value) => asNumber(asRecord(value)[metric])).filter((value): value is number => value !== undefined)
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : undefined
}

export function splitRowCount(model: Record<string, unknown>, split: string): number | undefined {
  const splitData = asRecord(asRecord(model.splits)[split])
  return Object.values(splitData).map((value) => asNumber(asRecord(value).n)).find((value) => value !== undefined)
}

export function filterDiagnosticRows(rows: Array<Record<string, unknown>>, model: string, splits: string): Array<Record<string, unknown>> {
  const splitSet = new Set(splits.split(',').map((value) => value.trim()).filter(Boolean))
  return rows.filter((row) => (!model || asString(row.model_name) === model) && (!splitSet.size || splitSet.has(asString(row.split))))
}

export function diagnosticPoints(rows: Array<Record<string, unknown>>, output: string) {
  return rows
    .filter((row) => asNumber(row[`${output}_true`]) !== undefined && asNumber(row[`${output}_pred`]) !== undefined)
    .map((row) => ({ row, measured: asNumber(row[`${output}_true`])!, predicted: asNumber(row[`${output}_pred`])!, residual: asNumber(row[`${output}_residual`]) }))
}

export function nextModelQualityView(active: ModelQualityView, key: 'ArrowLeft' | 'ArrowRight' | 'Home' | 'End'): ModelQualityView {
  const index = MODEL_QUALITY_TABS.findIndex((tab) => tab.id === active)
  if (key === 'Home') return MODEL_QUALITY_TABS[0].id
  if (key === 'End') return MODEL_QUALITY_TABS[MODEL_QUALITY_TABS.length - 1].id
  const offset = key === 'ArrowLeft' ? -1 : 1
  return MODEL_QUALITY_TABS[(index + offset + MODEL_QUALITY_TABS.length) % MODEL_QUALITY_TABS.length].id
}
