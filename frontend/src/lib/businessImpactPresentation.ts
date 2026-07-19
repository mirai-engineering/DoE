import { formatNumber } from './doeUtils.ts'

export const BUSINESS_IMPACT_SCENARIO_DEFAULTS = {
  hoursPerCampaign: '520',
  hourlyCost: '150',
  campaignsPerYear: '4',
  reductionPercent: '35',
} as const

export type BusinessImpactScenarioInputs = {
  hoursPerCampaign: string
  hourlyCost: string
  campaignsPerYear: string
  reductionPercent: string
}

export type BusinessImpactScenarioField = keyof BusinessImpactScenarioInputs

export const BUSINESS_IMPACT_SECTIONS = [
  { id: 'impact-story', label: 'Impact story' },
  { id: 'impact-roi-assumptions', label: 'ROI assumptions' },
  { id: 'impact-evidence', label: 'Evidence' },
  { id: 'impact-references', label: 'References' },
] as const

export function asImpactNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

export function asImpactString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

export function asImpactRange(value: unknown): { low: number; high: number } {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return { low: 0, high: 0 }
  const record = value as Record<string, unknown>
  return { low: asImpactNumber(record.low), high: asImpactNumber(record.high) }
}

export function moneyCompact(value: number): string {
  if (value >= 1000000) return `$${formatNumber(value / 1000000)}M`
  if (value >= 1000) return `$${Math.round(value / 1000)}k`
  return `$${formatNumber(value)}`
}

export function hoursLabel(hours: number): string {
  if (hours >= 24) return `${formatNumber(hours / 24)} days`
  return `${formatNumber(hours)} h`
}

export function calculateBusinessImpactSavings(inputs: BusinessImpactScenarioInputs) {
  const hours = Math.max(0, Number(inputs.hoursPerCampaign) || 0)
  const cost = Math.max(0, Number(inputs.hourlyCost) || 0)
  const campaigns = Math.max(0, Number(inputs.campaignsPerYear) || 0)
  const reduction = Math.max(0, Math.min(100, Number(inputs.reductionPercent) || 0)) / 100
  const savedHoursPerCampaign = hours * reduction
  const savedCostPerCampaign = savedHoursPerCampaign * cost
  const annualizedSavings = savedCostPerCampaign * campaigns
  return { savedHoursPerCampaign, savedCostPerCampaign, annualizedSavings }
}

export function businessImpactInputError(field: BusinessImpactScenarioField, value: string): string | null {
  if (value.trim() === '' || !Number.isFinite(Number(value))) return 'Enter a numeric value.'
  if (Number(value) < 0) return 'Value must be zero or greater.'
  if (field === 'reductionPercent' && Number(value) > 100) return 'Reduction must be between 0 and 100%.'
  return null
}

export function orderExperimentJourney(rows: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  const stageOrder: Record<string, number> = { learned: 0, software: 1, run: 2, saved: 3 }
  return [...rows].sort((left, right) => {
    const leftOrder = stageOrder[asImpactString(left.tone)] ?? Number.MAX_SAFE_INTEGER
    const rightOrder = stageOrder[asImpactString(right.tone)] ?? Number.MAX_SAFE_INTEGER
    return leftOrder - rightOrder
  })
}
