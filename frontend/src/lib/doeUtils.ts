import type { ProjectSchema, ProjectSummary, PredictionMap } from './api'
import type { FixedInputConfig } from '../types/doe'

export const preferredProjectId = ''
export const defaultTableTopK = 5
export const defaultVisualizationTopK = 75
export const maxVisualizationTopK = 100

const demoDefaultFixedInputNames = ['operating_rh', 'operating_voltage']
const demoDefaultHeatmapAxes = ['pt_c_ratio', 'i_c_ratio'] as const

const defaultObjectiveWeights: Record<string, number> = {
  bol_current_density: 0.4,
  eol_current_density: 0.4,
  ecsa_loss: -0.2,
}

export function selectDefaultProject(projects: ProjectSummary[]) {
  return preferredProjectId ? projects.find((project) => project.id === preferredProjectId) ?? projects[0] : projects[0]
}

export function midpoint(minimum: number, maximum: number) {
  return Number(((minimum + maximum) / 2).toPrecision(6))
}

export function formatNumber(value: number | undefined) {
  if (value === undefined || Number.isNaN(value)) return '-'
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: Math.abs(value) >= 100 ? 1 : 4,
  }).format(value)
}

export function initialInputValues(schema: ProjectSchema) {
  return Object.fromEntries(
    schema.inputs.map((input) => [input.name, String(midpoint(input.min, input.max))]),
  )
}

export function initialWeights(schema: ProjectSchema) {
  return Object.fromEntries(
    schema.outputs.map((output) => {
      const fallback = output.direction === 'minimize' ? -0.1 : 0.2
      return [output.name, String(defaultObjectiveWeights[output.name] ?? fallback)]
    }),
  )
}

export function initialFixedInputs(schema: ProjectSchema): FixedInputConfig {
  const fixedInputNames = new Set(
    demoDefaultFixedInputNames.filter((name) => schema.inputs.some((input) => input.name === name)),
  )

  if (fixedInputNames.size === 0) {
    schema.inputs.slice(0, 2).forEach((input) => fixedInputNames.add(input.name))
  }

  return Object.fromEntries(
    schema.inputs.map((input) => [
      input.name,
      { enabled: fixedInputNames.has(input.name), value: String(midpoint(input.min, input.max)) },
    ]),
  )
}

export function toNumberMap(values: Record<string, string>) {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [key, Number(value)]),
  )
}

export function enabledFixedInputValues(fixedInputs: FixedInputConfig) {
  return Object.fromEntries(
    Object.entries(fixedInputs)
      .filter(([, config]) => config.enabled)
      .map(([key, config]) => [key, Number(config.value)]),
  )
}

export function linspace(minimum: number, maximum: number, count: number) {
  if (count <= 1) return [minimum]
  const step = (maximum - minimum) / (count - 1)
  return Array.from({ length: count }, (_, index) => minimum + step * index)
}

export function safeRange(values: number[], fallback: [number, number]) {
  if (values.length === 0) return fallback
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  if (maximum > minimum) return [minimum, maximum] as [number, number]
  const padding = Math.max(Math.abs(minimum) * 0.05, 0.01)
  return [minimum - padding, maximum + padding] as [number, number]
}

export function normalizeForComparison(values: number[], direction: 'maximize' | 'minimize') {
  const [minimum, maximum] = safeRange(values, [0, 1])
  if (maximum <= minimum) return values.map(() => 0.5)

  return values.map((value) => {
    const normalized = (value - minimum) / (maximum - minimum)
    return direction === 'minimize' ? 1 - normalized : normalized
  })
}

export function scorePredictionRows(
  schema: ProjectSchema,
  predictions: PredictionMap[],
  objectiveWeights: Record<string, number>,
) {
  const scores = Array.from({ length: predictions.length }, () => 0)

  schema.outputs.forEach((output) => {
    const weight = objectiveWeights[output.name]
    if (weight === undefined) return

    const values = predictions.map((prediction) => prediction[output.name] ?? 0)
    const [minimum, maximum] = safeRange(values, [0, 1])
    if (maximum <= minimum) return

    values.forEach((value, index) => {
      scores[index] += weight * ((value - minimum) / (maximum - minimum))
    })
  })

  return scores
}

export function outputLabel(schema: ProjectSchema, outputName: string) {
  const output = schema.outputs.find((item) => item.name === outputName)
  if (!output) return outputName
  return `${output.label} (${output.direction})`
}

export function shortLabel(label: string) {
  const replacements: Array<[RegExp, string]> = [
    [/relative humidity/gi, 'RH'],
    [/current density/gi, 'J'],
    [/equivalent weight/gi, 'EW'],
    [/operating/gi, 'Op.'],
    [/durability score/gi, 'Durability'],
    [/cost score/gi, 'Cost'],
  ]
  const compact = replacements.reduce(
    (current, [pattern, replacement]) => current.replace(pattern, replacement),
    label,
  )

  if (compact.length <= 16) return compact
  return compact
    .split(/[\s/_-]+/)
    .filter(Boolean)
    .map((word) => word[0])
    .join('')
    .toUpperCase()
}

export function defaultHeatmapAxes(schema: ProjectSchema) {
  const [preferredX, preferredY] = demoDefaultHeatmapAxes
  const xAxis = schema.inputs.find((input) => input.name === preferredX)?.name ?? schema.inputs[0]?.name ?? ''
  const yAxis =
    schema.inputs.find((input) => input.name === preferredY && input.name !== xAxis)?.name ??
    schema.inputs.find((input) => input.name !== xAxis)?.name ??
    ''

  return { xAxis, yAxis }
}

export function clampInteger(value: string, fallback: number, minimum: number, maximum: number) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return fallback
  return Math.max(minimum, Math.min(maximum, Math.round(parsed)))
}
