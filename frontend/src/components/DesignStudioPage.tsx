import { useEffect, useMemo, useRef, useState } from 'react'
import Plot from 'react-plotly.js'
import * as Plotly from 'plotly.js-dist-min'
import type { DesignStudioOverlayColumn, DesignStudioParetoCandidate, DesignStudioParetoResponse, DesignStudioPrediction, DesignStudioState, ExperimentVisualisationConfig, ProjectSchema } from '../lib/api'
import { exportDesignStudioZip, findDesignStudioPareto, getDesignStudioState, predictDesignStudio, seedDesignStudioBatch } from '../lib/api'
import { lightPlotOnDarkCardLayout, miraiChartColors, plotConfig } from '../lib/plotlyTheme'
import { formatNumber } from '../lib/doeUtils'
import { ModelMap } from './ModelMap'
import { Alert, PanelHeader } from './ui'

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function asPlotData(value: unknown) {
  return value as any
}

function asPlotLayout(value: unknown) {
  return value as any
}

const plotLayoutBase = lightPlotOnDarkCardLayout({
  margin: { l: 60, r: 24, t: 34, b: 56 },
})

type ObjectivePreset = {
  id: string
  label: string
  description: string
  weights: Record<string, number>
}

type DesignWorkflow = 'single_result' | 'plot' | 'optimize' | 'compare' | 'model_map'
type VisualisationType = 'generic' | 'electrochemical' | 'battery_degradation' | 'energy_demand'
type OverlayMode = 'comparable' | 'same_current_conditions' | 'custom' | 'none'
type PlotAnnotationMode = 'none' | 'selected' | 'all'

function numericObjectiveWeights(weights: Record<string, string>) {
  return Object.fromEntries(Object.entries(weights).map(([key, value]) => [key, Number(value) || 0]))
}

export function DesignStudioPage({ schema }: { schema: ProjectSchema }) {
  const [state, setState] = useState<DesignStudioState | null>(null)
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [visualisationFixedInputs, setVisualisationFixedInputs] = useState<Record<string, string>>({})
  const [prediction, setPrediction] = useState<DesignStudioPrediction | null>(null)
  const [savedComparison, setSavedComparison] = useState<DesignStudioPrediction | null>(null)
  const [activeWorkflow, setActiveWorkflow] = useState<DesignWorkflow>('plot')
  const [overlayMode, setOverlayMode] = useState<OverlayMode>('none')
  const [trainingOverlayEnabled, setTrainingOverlayEnabled] = useState(false)
  const [trainingOverlayFilters, setTrainingOverlayFilters] = useState<Record<string, string>>({})
  const [trainingOverlayRanges, setTrainingOverlayRanges] = useState<Record<string, { min?: string, max?: string }>>({})
  const [searchSpaceModes, setSearchSpaceModes] = useState<Record<string, 'free' | 'fixed' | 'range'>>({})
  const [searchSpaceRanges, setSearchSpaceRanges] = useState<Record<string, { min?: string, max?: string }>>({})
  const [selectedExperimentVisualisationConfigId, setSelectedExperimentVisualisationConfigId] = useState('')
  const [plotTitle, setPlotTitle] = useState('Predicted response')
  const [visualisationType, setVisualisationType] = useState<VisualisationType>('generic')
  const [sweepInputName, setSweepInputName] = useState('')
  const [primaryOutputName, setPrimaryOutputName] = useState('')
  const [secondaryOutputName, setSecondaryOutputName] = useState('')
  const [sweepPointCount, setSweepPointCount] = useState('60')
  const [sweepRangeMin, setSweepRangeMin] = useState('')
  const [sweepRangeMax, setSweepRangeMax] = useState('')
  const [responseAxesSwapped, setResponseAxesSwapped] = useState(false)
  const [plotAnnotationMode, setPlotAnnotationMode] = useState<PlotAnnotationMode>('none')
  const [selectedAnnotationInputs, setSelectedAnnotationInputs] = useState<string[]>([])
  const [trainingOverlayGroupBy, setTrainingOverlayGroupBy] = useState('')
  const [objectiveMode, setObjectiveMode] = useState('')
  const [objectiveWeights, setObjectiveWeights] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [predicting, setPredicting] = useState(false)
  const [seeding, setSeeding] = useState(false)
  const [paretoLoading, setParetoLoading] = useState(false)
  const [paretoResults, setParetoResults] = useState<DesignStudioParetoResponse | null>(null)
  const [exporting, setExporting] = useState(false)
  const [exportingCurvePng, setExportingCurvePng] = useState(false)
  const [hasPendingInputChanges, setHasPendingInputChanges] = useState(false)
  const [visualisationStale, setVisualisationStale] = useState(false)
  const responseCurvePlotRef = useRef<unknown>(null)
  const [error, setError] = useState<string | null>(null)

  const currentDesignPoint = inputs
  const numericInputs = useMemo(() => Object.fromEntries(schema.inputs.map((input) => [input.name, Number(currentDesignPoint[input.name])])), [currentDesignPoint, schema.inputs])
  const numericVisualisationFixedInputs = useMemo(() => Object.fromEntries(schema.inputs.map((input) => [input.name, Number(visualisationFixedInputs[input.name] ?? currentDesignPoint[input.name])])), [currentDesignPoint, schema.inputs, visualisationFixedInputs])
  const objectivePresets = useMemo<ObjectivePreset[]>(() => {
    const singleOutputPresets = schema.outputs.map((output) => {
      const weight = output.direction === 'minimize' ? -1 : 1
      return {
        id: `single:${output.name}`,
        label: `${output.direction === 'minimize' ? 'Minimize' : 'Maximize'} ${output.label}`,
        description: `Search for candidates with ${output.direction === 'minimize' ? 'lower' : 'higher'} predicted ${output.label}.`,
        weights: { [output.name]: weight },
      }
    })
    return [...singleOutputPresets, { id: 'custom', label: 'Custom weights', description: 'Choose your own tradeoff across outputs.', weights: {} }]
  }, [schema.outputs])
  const selectedObjectiveWeights = useMemo(() => {
    if (objectiveMode === 'custom') return numericObjectiveWeights(objectiveWeights)
    const preset = objectivePresets.find((item) => item.id === objectiveMode)
    return preset?.weights ?? numericObjectiveWeights(objectiveWeights)
  }, [objectiveMode, objectivePresets, objectiveWeights])
  const selectedObjective = objectivePresets.find((item) => item.id === objectiveMode)
  const defaultInputSourceLabel = state?.default_inputs_source === 'observed_prediction_artifact_median'
    ? 'Initial design point uses observed artifact medians.'
    : 'Initial design point uses schema midpoint fallback.'
  const currentGoalLabel = selectedObjective?.label || 'Selected objective'
  const activeObjectiveCount = Object.values(selectedObjectiveWeights).filter((value) => Math.abs(value) > 1e-12).length
  function visualisationSweepVariable(config?: ExperimentVisualisationConfig) {
    return asString(asRecord(config?.x).variable) || schema.inputs[0]?.name
  }
  function visualisationPrimaryOutput(config?: ExperimentVisualisationConfig) {
    return asString(asRecord(config?.y).variable) || schema.outputs[0]?.name
  }
  function copyCurrentInputsToVisualisation() {
    setVisualisationFixedInputs(currentDesignPoint)
    setVisualisationStale(true)
  }

  function visualisationRangeIssue() {
    if (!sweepMeta) return null
    const min = sweepRangeMin === '' ? sweepMeta.min : Number(sweepRangeMin)
    const max = sweepRangeMax === '' ? sweepMeta.max : Number(sweepRangeMax)
    if (!Number.isFinite(min) || !Number.isFinite(max)) return 'Sweep range must use numeric values.'
    if (min < sweepMeta.min || max > sweepMeta.max) return `${sweepMeta.label} sweep range must stay within the schema bounds ${formatNumber(sweepMeta.min)} to ${formatNumber(sweepMeta.max)}${sweepMeta.unit ? ` ${sweepMeta.unit}` : ''}.`
    return null
  }

  function dynamicExperimentVisualisationConfig(configId = selectedExperimentVisualisationConfigId): ExperimentVisualisationConfig | undefined {
    const config = state?.plot_recipes?.find((item) => item.id === configId)
    const xVariable = sweepInputName || visualisationSweepVariable(config)
    const yVariable = primaryOutputName || visualisationPrimaryOutput(config)
    const secondary = secondaryOutputName && secondaryOutputName !== yVariable ? secondaryOutputName : ''
    if (!xVariable || !yVariable) return undefined
    return {
      id: configId || `dynamic_${xVariable}_${yVariable}`,
      label: plotTitle || `${schema.outputs.find((output) => output.name === yVariable)?.label ?? yVariable} vs ${schema.inputs.find((input) => input.name === xVariable)?.label ?? xVariable}`,
      description: 'Experiment visualisation: sweep one variable, keep fixed inputs constant, and predict selected response(s).',
      kind: 'scatter_response',
      template_id: 'generic_tabular_doe',
      safe: true,
      recommended: true,
      x: { source: 'input', variable: xVariable },
      y: { source: 'prediction', variable: yVariable },
      series: secondary ? [{ variable: secondary }] : [],
      filters: [],
      group_by: null,
      points: Math.max(10, Math.min(200, Number(sweepPointCount) || 60)),
      x_min: sweepRangeMin === '' ? undefined : Number(sweepRangeMin),
      x_max: sweepRangeMax === '' ? undefined : Number(sweepRangeMax),
    } as ExperimentVisualisationConfig & { points: number }
  }

  function experimentVisualisationPayload(configId = selectedExperimentVisualisationConfigId) {
    const config = state?.plot_recipes?.find((item) => item.id === configId)
    const dynamicConfig = dynamicExperimentVisualisationConfig(configId)
    // Compatibility boundary: the backend route still accepts legacy plot_recipe
    // fields, but the Design Studio UI sends an experiment visualisation config.
    return dynamicConfig ? { plot_recipe_id: configId || undefined, experiment_visualisation: dynamicConfig } : { plot_recipe_id: config?.id || configId || undefined }
  }

  function trainingOverlayPayload() {
    const overlayEnabled = trainingOverlayEnabled && overlayMode !== 'none'
    const filters = Object.fromEntries(Object.entries(trainingOverlayFilters).filter(([, value]) => value !== ''))
    const ranges = Object.fromEntries(Object.entries(trainingOverlayRanges).map(([name, range]) => [name, Object.fromEntries(Object.entries(range).filter(([, value]) => value !== undefined && value !== ''))]).filter(([, range]) => Object.keys(range as Record<string, string>).length > 0))
    return {
      training_overlay_enabled: overlayEnabled,
      training_overlay_filters: overlayEnabled && Object.keys(filters).length ? filters : undefined,
      training_overlay_ranges: overlayEnabled && Object.keys(ranges).length ? ranges : undefined,
      training_overlay_group_by: overlayEnabled && trainingOverlayGroupBy ? trainingOverlayGroupBy : undefined,
    }
  }

  function searchSpacePayload() {
    const fixed_inputs: Record<string, number> = {}
    const constraints: Record<string, { min?: number, max?: number }> = {}
    schema.inputs.forEach((input) => {
      const mode = searchSpaceModes[input.name] || 'free'
      if (mode === 'fixed') {
        const value = Number(inputs[input.name])
        if (Number.isFinite(value)) fixed_inputs[input.name] = value
      }
      if (mode === 'range') {
        const range = searchSpaceRanges[input.name] || {}
        const min = range.min === undefined || range.min === '' ? undefined : Number(range.min)
        const max = range.max === undefined || range.max === '' ? undefined : Number(range.max)
        constraints[input.name] = {}
        if (Number.isFinite(min)) constraints[input.name].min = min
        if (Number.isFinite(max)) constraints[input.name].max = max
      }
    })
    return { fixed_inputs, constraints }
  }

  function suggestedOverlayFilters(options: DesignStudioOverlayColumn[] | undefined, defaultInputs: Record<string, string>) {
    const suggestions: Record<string, string> = {}
    ;(options || []).forEach((column) => {
      if (column.filter_kind !== 'exact' || defaultInputs[column.name] === undefined || !Array.isArray(column.values)) return
      const current = Number(defaultInputs[column.name])
      const match = column.values.find((value) => {
        const numericValue = typeof value === 'number' ? value : Number(value)
        return Number.isFinite(current) && Number.isFinite(numericValue) ? Math.abs(current - numericValue) < 1e-9 : String(value) === defaultInputs[column.name]
      })
      if (match !== undefined && match !== null) suggestions[column.name] = String(match)
    })
    return suggestions
  }

  function overlayColumnTier(column: DesignStudioOverlayColumn): 'suggested' | 'other' | 'internal' {
    const name = column.name.toLowerCase()
    const role = (column.role || '').toLowerCase()
    const isInternalName = /(^|_)(row|index|idx|model|source|prediction|residual|error)($|_)/.test(name) || name === 'source'
    if (isInternalName) return 'internal'
    if (column.recommended || role === 'input' || role === 'context' || role === 'group' || role === 'curve_axis') return 'suggested'
    if (role === 'id' || (column.distinct_count ?? 0) > 100) return 'other'
    return 'other'
  }

  function applyOverlayMode(nextMode: OverlayMode) {
    setOverlayMode(nextMode)
    if (nextMode === 'none') {
      setTrainingOverlayEnabled(false)
      return
    }
    setTrainingOverlayEnabled(true)
    if (nextMode === 'comparable' || nextMode === 'same_current_conditions') {
      setTrainingOverlayFilters(suggestedOverlayFilters(state?.training_overlay_options?.columns, inputs))
      setTrainingOverlayRanges({})
    }
  }

  async function loadState() {
    setLoading(true)
    setError(null)
    try {
      const payload = await getDesignStudioState(schema.project_id)
      const defaultInputs = Object.fromEntries(schema.inputs.map((input) => [input.name, String(payload.default_inputs[input.name] ?? (input.min + input.max) / 2)]))
      const numericDefaultInputs = Object.fromEntries(schema.inputs.map((input) => [input.name, Number(defaultInputs[input.name])]))
      const defaultVisualisationConfig = payload.plot_recipes?.find((item) => item.id === payload.selected_plot_recipe_id) || payload.plot_recipes?.find((item) => item.recommended) || payload.plot_recipes?.[0]
      const defaultExperimentVisualisationConfigId = defaultVisualisationConfig?.id || ''
      const defaultSweep = visualisationSweepVariable(defaultVisualisationConfig) || schema.inputs[0]?.name || ''
      const defaultOutput = visualisationPrimaryOutput(defaultVisualisationConfig) || schema.outputs[0]?.name || ''
      const initialOverlayFilters = suggestedOverlayFilters(payload.training_overlay_options?.columns, defaultInputs)
      setState(payload)
      setTrainingOverlayFilters(initialOverlayFilters)
      setInputs(defaultInputs)
      setVisualisationFixedInputs(defaultInputs)
      setSelectedExperimentVisualisationConfigId(defaultExperimentVisualisationConfigId)
      setPlotTitle(defaultVisualisationConfig?.label || 'Predicted response')
      setSweepInputName(defaultSweep)
      setSweepRangeMin('')
      setSweepRangeMax('')
      setPrimaryOutputName(defaultOutput)
      setSecondaryOutputName('')
      setSearchSpaceModes(Object.fromEntries(schema.inputs.map((input) => [input.name, 'free'])))
      setSearchSpaceRanges(Object.fromEntries(schema.inputs.map((input) => [input.name, { min: String(input.min), max: String(input.max) }])))
      setPrediction(await predictDesignStudio(schema.project_id, { inputs: numericDefaultInputs, experiment_visualisation_enabled: false }))
      setHasPendingInputChanges(false)
      setVisualisationStale(false)
      const defaultObjectiveName = Object.keys(payload.default_objective_weights ?? {})[0]
      setObjectiveMode(defaultObjectiveName ? `single:${defaultObjectiveName}` : 'custom')
      setObjectiveWeights(Object.fromEntries(schema.outputs.map((output) => [output.name, String(payload.default_objective_weights[output.name] ?? 0)])))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load Design Studio')
    } finally {
      setLoading(false)
    }
  }

  async function runPrediction(nextInputs = numericInputs) {
    setPredicting(true)
    setError(null)
    try {
      const result = await predictDesignStudio(schema.project_id, { inputs: nextInputs, experiment_visualisation_enabled: false })
      setPrediction((current) => ({ ...result, curve: current?.curve ?? result.curve, training_overlay: current?.training_overlay ?? result.training_overlay }))
      setHasPendingInputChanges(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to predict design')
    } finally {
      setPredicting(false)
    }
  }

  async function runVisualisation(configId = selectedExperimentVisualisationConfigId) {
    const rangeIssue = visualisationRangeIssue()
    if (rangeIssue) {
      setError(rangeIssue)
      return
    }
    setPredicting(true)
    setError(null)
    try {
      setPrediction(await predictDesignStudio(schema.project_id, { inputs: numericVisualisationFixedInputs, experiment_visualisation_enabled: true, ...trainingOverlayPayload(), ...experimentVisualisationPayload(configId) }))
      setHasPendingInputChanges(false)
      setVisualisationStale(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to generate visualisation')
    } finally {
      setPredicting(false)
    }
  }

  function updateInput(name: string, value: string) {
    setInputs((current) => ({ ...current, [name]: value }))
    setHasPendingInputChanges(true)
    setVisualisationStale(true)
  }

  async function seedFromBatch() {
    setSeeding(true)
    setError(null)
    try {
      const seeded = await seedDesignStudioBatch(schema.project_id, {
        objective_weights: selectedObjectiveWeights,
        n_candidates: 3000,
        ...trainingOverlayPayload(),
        ...searchSpacePayload(),
        ...experimentVisualisationPayload(),
      })
      setPrediction(seeded)
      const nextDesignPoint = Object.fromEntries(schema.inputs.map((input) => [input.name, String(seeded.inputs[input.name] ?? currentDesignPoint[input.name] ?? '')]))
      setInputs(nextDesignPoint)
      setVisualisationFixedInputs(nextDesignPoint)
      setHasPendingInputChanges(false)
      setVisualisationStale(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to seed from batch search')
    } finally {
      setSeeding(false)
    }
  }

  async function findParetoTradeoffs() {
    const balancedPreset = objectivePresets.find((preset) => preset.id.startsWith('balanced:'))
    const effectiveWeights = activeObjectiveCount >= 2
      ? selectedObjectiveWeights
      : balancedPreset?.weights
    if (!effectiveWeights || Object.values(effectiveWeights).filter((value) => Math.abs(value) > 1e-12).length < 2) {
      setError('Pareto tradeoffs need at least two active objectives. Choose Custom weights and set two or more non-zero weights.')
      return
    }
    if (activeObjectiveCount < 2 && balancedPreset) {
      setObjectiveMode(balancedPreset.id)
      setObjectiveWeights(Object.fromEntries(schema.outputs.map((output) => [output.name, String(balancedPreset.weights[output.name] ?? 0)])))
    }
    setParetoLoading(true)
    setError(null)
    try {
      setParetoResults(await findDesignStudioPareto(schema.project_id, {
        objective_weights: effectiveWeights,
        n_candidates: 3000,
        max_results: 12,
        ...trainingOverlayPayload(),
        ...searchSpacePayload(),
        ...experimentVisualisationPayload(),
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to find Pareto tradeoffs')
    } finally {
      setParetoLoading(false)
    }
  }

  async function loadParetoCandidate(candidate: DesignStudioParetoCandidate) {
    const nextDesignPoint = Object.fromEntries(schema.inputs.map((input) => [input.name, String(candidate.inputs[input.name] ?? currentDesignPoint[input.name] ?? '')]))
    setInputs(nextDesignPoint)
    setVisualisationFixedInputs(nextDesignPoint)
    setVisualisationStale(false)
    await runPrediction(candidate.inputs)
  }

  async function exportZip() {
    setExporting(true)
    setError(null)
    try {
      const blob = await exportDesignStudioZip(schema.project_id, {
        inputs: numericInputs,
        ...trainingOverlayPayload(),
        ...searchSpacePayload(),
        comparison_candidate: savedComparison?.inputs,
        ...experimentVisualisationPayload(),
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${schema.project_id}_design_studio_export.zip`
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to export design package')
    } finally {
      setExporting(false)
    }
  }

  async function exportResponseCurvePng() {
    if (!responseCurvePlotRef.current || !curveRows.length) return
    setExportingCurvePng(true)
    setError(null)
    try {
      await (Plotly as any).downloadImage(responseCurvePlotRef.current, {
        format: 'png',
        filename: `${schema.project_id}_dynamic_response_curve`,
        width: 1200,
        height: 720,
        scale: 2,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to export experiment visualisation PNG')
    } finally {
      setExportingCurvePng(false)
    }
  }

  useEffect(() => {
    loadState()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema.project_id])

  const visualisationConfigs = state?.plot_recipes ?? []
  const selectedExperimentVisualisationConfig = visualisationConfigs.find((item) => item.id === selectedExperimentVisualisationConfigId) ?? visualisationConfigs.find((item) => item.recommended) ?? visualisationConfigs[0]
  const curveVisualisationConfig = asRecord(prediction?.curve?.recipe) as ExperimentVisualisationConfig | Record<string, unknown>
  const curveRows = asRecord(prediction?.curve).rows as Array<Record<string, unknown>> | undefined ?? []
  const trainingOverlayRows = asRecord(prediction?.training_overlay).rows as Array<Record<string, unknown>> | undefined ?? []
  const trainingOverlay = asRecord(prediction?.training_overlay)
  const overlayColumns = state?.training_overlay_options?.columns ?? []
  const suggestedOverlayColumns = overlayColumns.filter((column) => overlayColumnTier(column) === 'suggested')
  const otherOverlayColumns = overlayColumns.filter((column) => overlayColumnTier(column) === 'other')
  const internalOverlayColumns = overlayColumns.filter((column) => overlayColumnTier(column) === 'internal')
  const visibleOverlayColumns = [...suggestedOverlayColumns, ...otherOverlayColumns, ...internalOverlayColumns]
  const activeOverlayFilterLabels = Object.entries(trainingOverlayFilters)
    .filter(([, value]) => value !== '')
    .map(([name, value]) => `${overlayColumns.find((column) => column.name === name)?.label || name} = ${value}`)
  const activeOverlayRangeLabels = Object.entries(trainingOverlayRanges)
    .map(([name, range]) => {
      const parts = [range.min ? `min ${range.min}` : '', range.max ? `max ${range.max}` : ''].filter(Boolean).join(', ')
      return parts ? `${overlayColumns.find((column) => column.name === name)?.label || name}: ${parts}` : ''
    })
    .filter(Boolean)
  const overlaySummaryLabels = [...activeOverlayFilterLabels, ...activeOverlayRangeLabels]
  const displayedOverlaySummaryLabels = overlaySummaryLabels.slice(0, 4)
  const hiddenOverlaySummaryCount = Math.max(0, overlaySummaryLabels.length - displayedOverlaySummaryLabels.length)
  const overlayVisible = trainingOverlayEnabled && overlayMode !== 'none'
  const metadataVariables = schema.metadata?.all_variables ?? schema.domain_metadata?.all_variables ?? schema.metadata?.variables ?? schema.domain_metadata?.variables ?? []
  const trainingOverlayGroupOptions = overlayColumns.filter((column) => overlayColumnTier(column) !== 'internal').map((column) => column.name)
  const activeModel = asRecord(state?.active_model)
  const aliases = asRecord(activeModel.aliases)
  const champion = asRecord(aliases.champion)
  const traceability = asRecord(activeModel.mlflow_traceability)
  const cacheStatus = asRecord(traceability.cache_status)
  const defaultObjectiveName = Object.keys(state?.default_objective_weights ?? {})[0]
  const emphasizedOutputs = new Set(Object.entries(selectedObjectiveWeights).filter(([, value]) => Math.abs(value) > 1e-12).map(([name]) => name))
  const curveXAxisVariable = asString(asRecord(asRecord(curveVisualisationConfig).x).variable) || asString(asRecord(selectedExperimentVisualisationConfig?.x).variable)
  const curveYAxisVariable = asString(asRecord(asRecord(curveVisualisationConfig).y).variable) || asString(asRecord(selectedExperimentVisualisationConfig?.y).variable)
  const curveXAxisMeta = schema.inputs.find((input) => input.name === curveXAxisVariable) ?? schema.outputs.find((output) => output.name === curveXAxisVariable)
  const curveYAxisMeta = schema.outputs.find((output) => output.name === curveYAxisVariable) ?? schema.inputs.find((input) => input.name === curveYAxisVariable)
  const curveYVariables = (Array.isArray(asRecord(curveVisualisationConfig).y_variables) ? asRecord(curveVisualisationConfig).y_variables as unknown[] : [])
    .map((value) => asString(value))
    .filter(Boolean)
  const fallbackYVariables = [curveYAxisVariable, secondaryOutputName].filter((value, index, values) => value && values.indexOf(value) === index)
  const genericCurveYVariables = curveYVariables.length ? curveYVariables : fallbackYVariables
  const genericOutputMetas = genericCurveYVariables.map((variable) => schema.outputs.find((output) => output.name === variable)).filter(Boolean)
  const genericOutputUnits = Array.from(new Set(genericOutputMetas.map((output) => output?.unit).filter(Boolean)))
  const genericSwappedXAxisTitle = genericCurveYVariables.length === 1
    ? `${genericOutputMetas[0]?.label ?? genericCurveYVariables[0]}${genericOutputMetas[0]?.unit ? ` / ${genericOutputMetas[0].unit}` : ''}`
    : `Selected predicted output${genericOutputUnits.length === 1 ? ` / ${genericOutputUnits[0]}` : ''}`
  const genericSwappedYAxisTitle = `${curveXAxisMeta?.label ?? curveXAxisVariable}${curveXAxisMeta?.unit ? ` / ${curveXAxisMeta.unit}` : ''}`
  const predictedGroupVariable = asString(asRecord(curveVisualisationConfig).group_variable)
  const predictedGroupMeta = schema.inputs.find((input) => input.name === predictedGroupVariable)
  const predictedGroupValues = predictedGroupVariable
    ? Array.from(new Set(curveRows.map((row) => asNumber(row.__group_value)).filter((value): value is number => value !== undefined)))
    : []
  const predictedTraceGroups = predictedGroupValues.length ? predictedGroupValues : [undefined]
  const annotationInputNames = plotAnnotationMode === 'all'
    ? schema.inputs.filter((input) => input.name !== sweepInputName).map((input) => input.name)
    : plotAnnotationMode === 'selected'
      ? selectedAnnotationInputs.filter((name) => name !== sweepInputName)
      : []
  const plotAnnotationLabels = annotationInputNames
    .map((name) => {
      const input = schema.inputs.find((item) => item.name === name)
      if (!input) return ''
      const value = Number(visualisationFixedInputs[input.name] ?? inputs[input.name])
      return `${input.label} = ${Number.isFinite(value) ? formatNumber(value) : '—'}${input.unit ? ` ${input.unit}` : ''}`
    })
    .filter(Boolean)
  const plotAnnotations = plotAnnotationLabels.length
    ? [{
      xref: 'paper' as const,
      yref: 'paper' as const,
      x: 0.02,
      y: 0.98,
      xanchor: 'left' as const,
      yanchor: 'top' as const,
      align: 'left' as const,
      showarrow: false,
      text: `<b>Fixed conditions</b><br>${plotAnnotationLabels.join('<br>')}`,
      bgcolor: 'rgba(255,255,255,0.88)',
      bordercolor: '#cbd5e1',
      borderwidth: 1,
      borderpad: 8,
      font: { size: 12, color: miraiChartColors.axis },
    }]
    : []
  const responseCurveData = asPlotData([
        ...genericCurveYVariables.flatMap((variable, index) => predictedTraceGroups.map((groupValue, groupIndex) => {
          const rows = groupValue === undefined ? curveRows : curveRows.filter((row) => asNumber(row.__group_value) === groupValue)
          return {
          name: groupValue === undefined
            ? `Predicted ${schema.outputs.find((output) => output.name === variable)?.label || variable}`
            : `Predicted ${schema.outputs.find((output) => output.name === variable)?.label || variable} · ${predictedGroupMeta?.label ?? predictedGroupVariable} ${formatNumber(groupValue)}${predictedGroupMeta?.unit ? ` ${predictedGroupMeta.unit}` : ''}`,
          x: rows.map((row) => asNumber(row[responseAxesSwapped ? variable : curveXAxisVariable])),
          y: rows.map((row) => asNumber(row[responseAxesSwapped ? curveXAxisVariable : variable])),
          type: 'scatter',
          mode: 'lines+markers',
          line: { color: ['#2F6BFF', '#2563eb', '#dc2626', '#7c3aed', '#0891b2', '#ea580c'][((index + groupIndex) % 6)], width: 3 },
        }})),
        ...genericCurveYVariables
          .filter((variable) => overlayVisible && trainingOverlayRows.some((row) => asNumber(row[`${variable}_true`]) !== undefined))
          .flatMap((variable, index) => {
            const groupValues = trainingOverlayGroupBy
              ? Array.from(new Set(trainingOverlayRows.map((row) => asString(row[trainingOverlayGroupBy])).filter(Boolean)))
              : ['Training data']
            return groupValues.map((groupValue, groupIndex) => {
              const rows = trainingOverlayGroupBy ? trainingOverlayRows.filter((row) => asString(row[trainingOverlayGroupBy]) === groupValue) : trainingOverlayRows
              return {
                name: `${schema.outputs.find((output) => output.name === variable)?.label || variable} · ${groupValue}`,
                x: rows.map((row) => asNumber(row[responseAxesSwapped ? `${variable}_true` : curveXAxisVariable])),
                y: rows.map((row) => asNumber(row[responseAxesSwapped ? curveXAxisVariable : `${variable}_true`])),
                type: 'scatter',
                mode: 'markers',
                marker: { color: ['#334155', '#92400e', '#0f766e', '#6d28d9', '#be123c'][((index + groupIndex) % 5)], size: 7, opacity: 0.62 },
                visible: trainingOverlayRows.length ? true : 'legendonly',
              }
            })
          }),
      ])
  const responseCurveLayout = asPlotLayout(lightPlotOnDarkCardLayout({
        ...plotLayoutBase,
        paper_bgcolor: '#ffffff',
        plot_bgcolor: '#ffffff',
        height: 470,
        title: { text: plotTitle || selectedExperimentVisualisationConfig?.label || 'Predicted response' },
        xaxis: { title: { text: responseAxesSwapped ? genericSwappedXAxisTitle : `${curveXAxisMeta?.label ?? curveXAxisVariable}${curveXAxisMeta?.unit ? ` / ${curveXAxisMeta.unit}` : ''}` }, zeroline: false },
        yaxis: { title: { text: responseAxesSwapped ? genericSwappedYAxisTitle : `${curveYAxisMeta?.label ?? curveYAxisVariable}${curveYAxisMeta?.unit ? ` / ${curveYAxisMeta.unit}` : ''}` }, zeroline: false },
        annotations: plotAnnotations,
      }))
  const sweepMeta = schema.inputs.find((input) => input.name === sweepInputName)
  const visualisationFixedConditionLabels = schema.inputs
    .filter((input) => input.name !== sweepInputName)
    .map((input) => `${input.label} = ${formatNumber(Number(visualisationFixedInputs[input.name] ?? inputs[input.name]))}${input.unit ? ` ${input.unit}` : ''}`)
  const visualisationGroupLabels: string[] = []
  const sweepRangeIssue = visualisationRangeIssue()
  const sweepRangeLabel = `${sweepMeta?.label ?? sweepInputName}: ${sweepRangeMin || formatNumber(sweepMeta?.min)} to ${sweepRangeMax || formatNumber(sweepMeta?.max)}${sweepMeta?.unit ? ` ${sweepMeta.unit}` : ''}, ${Math.max(10, Math.min(200, Number(sweepPointCount) || 60))} points`

  return (
    <div className="space-y-8">
      <section className="rounded-[2rem] border border-white/70 bg-white/90 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
        <PanelHeader
          eyebrow="Design Studio"
          title="Interactive surrogate-model playground"
          description="Seed a candidate, move schema-driven inputs, watch predictions update, compare against real experiments, and export a design package for lab review."
        />
        <div className="mt-4 flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.14em]">
          <span className="rounded-md border border-[#74C7F5]/40 bg-[#0D1B2D] px-3 py-1 text-[#BDEAFF]">Served-model predictions</span>
          <span className="rounded-md border border-slate-700 bg-[#070C16] px-3 py-1 text-slate-300">Champion: {asString(traceability.model_version) || asString(champion.version) || 'not set'}</span>
          {defaultObjectiveName && <span className="rounded-md border border-[#2F6BFF]/50 bg-[#10203A] px-3 py-1 text-[#BDEAFF]">Default objective: {schema.outputs.find((output) => output.name === defaultObjectiveName)?.label ?? defaultObjectiveName}</span>}
          <span className="rounded-md border border-slate-700 bg-[#070C16] px-3 py-1 text-slate-300">{defaultInputSourceLabel}</span>
          <span className="rounded-md border border-[#74C7F5]/40 bg-[#0D1B2D] px-3 py-1 text-[#BDEAFF]">Schema bounds enforced</span>
          {prediction?.warnings?.length ? <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-800">{prediction.warnings.length} model/support warning{prediction.warnings.length === 1 ? '' : 's'}</span> : null}
        </div>
        <details className="mt-4 rounded-2xl border border-slate-200 bg-[#0B1220] p-4 text-sm text-slate-600">
          <summary className="cursor-pointer select-none font-semibold text-slate-900">MLflow traceability</summary>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {[
              ['Workspace ID', traceability.workspace_id],
              ['Project ID', traceability.project_id || schema.project_id],
              ['Registered model', traceability.registered_model_name || activeModel.registered_model_name],
              ['Alias', traceability.alias],
              ['Model version', traceability.model_version || champion.version],
              ['Run ID', traceability.run_id || champion.run_id],
              ['Model URI/source', traceability.model_uri || traceability.model_source || champion.source],
              ['Tracking URI', traceability.tracking_uri || activeModel.tracking_uri],
              ['Loaded at', traceability.loaded_at],
              ['Loaded by', traceability.loaded_by],
              ['Artifact/cache status', cacheStatus.status],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-2xl bg-white p-3">
                <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">{String(label)}</div>
                <div className="mt-1 break-all font-medium text-slate-800">{asString(value) || '—'}</div>
              </div>
            ))}
          </div>
        </details>
      </section>

      <nav className="rounded-lg border border-slate-700/80 bg-[#0B1220] p-2 shadow-xl shadow-black/20" aria-label="Design Studio workflows">
        <div className="grid gap-2 md:grid-cols-5">
          {[
            ['single_result', 'Single result', 'Edit the current design point and generate KPIs'],
            ['plot', 'Experiment visualisation', 'Sweep one input around fixed conditions from the current design point'],
            ['optimize', 'Optimize', 'Search space, objectives, and candidates'],
            ['compare', 'Compare/export', 'Save baselines and package outputs'],
            ['model_map', 'Model map', 'Schema inputs and predicted responses'],
          ].map(([id, label, description]) => (
            <button
              key={id}
              type="button"
              onClick={() => setActiveWorkflow(id as DesignWorkflow)}
              className={`rounded-md border px-4 py-3 text-left transition ${activeWorkflow === id ? 'border-[#2F6BFF]/70 bg-[#10203A] text-white shadow-sm shadow-black/20' : 'border-slate-700 bg-[#070C16] text-slate-300 hover:border-[#74C7F5]/50 hover:bg-[#0D1524] hover:text-white'}`}
            >
              <div className="font-semibold">{label}</div>
              <div className={`mt-1 text-xs ${activeWorkflow === id ? 'text-white/80' : 'text-slate-500'}`}>{description}</div>
            </button>
          ))}
        </div>
      </nav>

      {activeWorkflow === 'plot' && visualisationConfigs.length > 0 && (
        <section className="rounded-lg border border-slate-700/80 bg-[#0B1220] p-4 shadow-xl shadow-black/20">
          <div className="grid gap-4 lg:grid-cols-[minmax(16rem,0.7fr)_minmax(16rem,0.7fr)_minmax(0,1.1fr)] lg:items-start">
            <label className="min-w-0 text-sm font-semibold text-slate-700">
              Visualisation type
              <select value={visualisationType} onChange={(event) => setVisualisationType(event.target.value as VisualisationType)} className="mt-2 w-full truncate rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                <option value="generic">Generic experiment visualisation</option>
                <option value="electrochemical">Electrochemical device visualisation — feature not available yet</option>
                <option value="battery_degradation">Battery degradation visualisation — feature not available yet</option>
                <option value="energy_demand">Energy demand visualisation — feature not available yet</option>
              </select>
            </label>
            <label className="min-w-0 text-sm font-semibold text-slate-700">
              Starting setup
              <select
                value={selectedExperimentVisualisationConfigId}
                onChange={(event) => {
                  const nextId = event.target.value
                  const next = visualisationConfigs.find((item) => item.id === nextId)
                  setSelectedExperimentVisualisationConfigId(nextId)
                  setSweepInputName(visualisationSweepVariable(next) || sweepInputName)
                  setPrimaryOutputName(visualisationPrimaryOutput(next) || primaryOutputName)
                  setSecondaryOutputName(Array.isArray(next?.series) ? asString(asRecord(next.series[0]).variable) : '')
                  setPlotTitle(next?.label || 'Predicted response')
                }}
                className="mt-2 w-full truncate rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm"
              >
                {visualisationConfigs.filter((item) => item.safe !== false).map((item) => <option key={item.id} value={item.id}>{item.recommended ? 'Recommended · ' : ''}{item.label}</option>)}
              </select>
            </label>
            <div className="min-w-0 rounded-md border border-slate-700/80 bg-[#070C16] px-4 py-3 text-sm leading-6 text-slate-300">
              {visualisationType === 'generic' ? (
                <><strong className="text-slate-900">Current visualisation setup:</strong> {selectedExperimentVisualisationConfig?.description || 'Sweep one variable while holding fixed inputs constant, then plot predicted response points.'}</>
              ) : (
                <><strong className="text-slate-900">Feature not available yet.</strong> This placeholder shows where future field-level visualisation presets can be added without hardcoding domain logic into the generic workflow.</>
              )}
            </div>
          </div>
          <div className="mt-4 rounded-3xl border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="font-semibold text-slate-950">Experiment visualisation</h3>
                  <p className="mt-1 text-sm leading-6 text-slate-600">Choose X, predicted Y, the sweep range, and fixed values for every other input. A 60-point sweep generates exactly 60 model predictions.</p>
                </div>
                <span className="rounded-full bg-[#0B1220] px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">schema-driven</span>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(12rem,1.1fr)_minmax(10rem,1.1fr)_minmax(10rem,1.1fr)_minmax(10rem,1.15fr)_minmax(7rem,0.75fr)_minmax(7rem,0.75fr)_minmax(6rem,0.6fr)_minmax(9rem,0.85fr)]">
                <label className="min-w-0 text-sm font-semibold text-slate-700">
                  Plot title
                  <input value={plotTitle} onChange={(event) => setPlotTitle(event.target.value)} className="mt-2 w-full truncate rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm" />
                </label>
                <label className="min-w-0 text-sm font-semibold text-slate-700">
                  Sweep variable
                  <select value={sweepInputName} onChange={(event) => { setSweepInputName(event.target.value); setVisualisationStale(true) }} className="mt-2 w-full truncate rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                    {schema.inputs.map((input) => <option key={input.name} value={input.name}>{input.label}{input.unit ? ` / ${input.unit}` : ''}</option>)}
                  </select>
                </label>
                <label className="min-w-0 text-sm font-semibold text-slate-700">
                  Predicted response
                  <select value={primaryOutputName} onChange={(event) => { setPrimaryOutputName(event.target.value); setVisualisationStale(true) }} className="mt-2 w-full truncate rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                    {schema.outputs.map((output) => <option key={output.name} value={output.name}>{output.label}{output.unit ? ` / ${output.unit}` : ''}</option>)}
                  </select>
                </label>
                <label className="min-w-0 text-sm font-semibold text-slate-700">
                  Optional second response
                  <select value={secondaryOutputName} onChange={(event) => { setSecondaryOutputName(event.target.value); setVisualisationStale(true) }} className="mt-2 w-full truncate rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                    <option value="">None</option>
                    {schema.outputs.map((output) => <option key={output.name} value={output.name}>{output.label}{output.unit ? ` / ${output.unit}` : ''}</option>)}
                  </select>
                </label>
                <label className="text-sm font-semibold text-slate-700">
                  Sweep min
                  <input type="number" min={sweepMeta?.min} max={sweepMeta?.max} value={sweepRangeMin} onChange={(event) => { setSweepRangeMin(event.target.value); setVisualisationStale(true) }} placeholder={String(sweepMeta?.min ?? '')} className={`mt-2 w-full rounded-2xl border bg-white px-3 py-2 text-sm ${sweepRangeIssue ? 'border-amber-300 ring-1 ring-amber-200' : 'border-slate-200'}`} />
                </label>
                <label className="text-sm font-semibold text-slate-700">
                  Sweep max
                  <input type="number" min={sweepMeta?.min} max={sweepMeta?.max} value={sweepRangeMax} onChange={(event) => { setSweepRangeMax(event.target.value); setVisualisationStale(true) }} placeholder={String(sweepMeta?.max ?? '')} className={`mt-2 w-full rounded-2xl border bg-white px-3 py-2 text-sm ${sweepRangeIssue ? 'border-amber-300 ring-1 ring-amber-200' : 'border-slate-200'}`} />
                </label>
                <label className="text-sm font-semibold text-slate-700">
                  Points
                  <input type="number" min="10" max="200" value={sweepPointCount} onChange={(event) => { setSweepPointCount(event.target.value); setVisualisationStale(true) }} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm" />
                </label>
                <label className="min-w-0 text-sm font-semibold text-slate-700 xl:col-span-2">
                  Plot orientation
                  <select value={responseAxesSwapped ? 'response_x' : 'sweep_x'} onChange={(event) => setResponseAxesSwapped(event.target.value === 'response_x')} className="mt-2 w-full truncate rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                    <option value="sweep_x">X = sweep variable, Y = predicted response</option>
                    <option value="response_x">X = predicted response, Y = sweep variable</option>
                  </select>
                </label>
              </div>
              <div className="mt-3 rounded-2xl border border-[#2F6BFF]/35 bg-[#10203A] px-4 py-3 text-sm leading-6 text-[#BDEAFF]">
                <strong>Sweep range = model input range.</strong> It must stay inside the approved schema bounds{ sweepMeta ? ` for ${sweepMeta.label}: ${formatNumber(sweepMeta.min)} to ${formatNumber(sweepMeta.max)}${sweepMeta.unit ? ` ${sweepMeta.unit}` : ''}` : '' }. Use Plotly zoom/pan on the chart for display-only axis zooming.
              </div>
              {sweepRangeIssue && <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900">
                <span>{sweepRangeIssue}</span>
                {sweepMeta && <button type="button" onClick={() => { setSweepRangeMin(String(sweepMeta.min)); setSweepRangeMax(String(sweepMeta.max)); setVisualisationStale(true) }} className="rounded-full border border-amber-300 bg-white px-3 py-1 text-xs font-semibold text-amber-900">Use schema range</button>}
              </div>}
              <div className="mt-5 rounded-3xl border border-slate-200 bg-[#0B1220] p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h4 className="font-semibold text-slate-950">Fixed conditions for visualisation</h4>
                    <p className="mt-1 text-sm leading-6 text-slate-600">These fixed values define the design point used for the multi-point visualisation. They are initialized from the current design point and stay synchronized when optimizer candidates are loaded.</p>
                  </div>
                  <button type="button" onClick={copyCurrentInputsToVisualisation} className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:border-[#2F6BFF]/40">
                    Use current design point for visualisation
                  </button>
                </div>
                <div className="mt-4 overflow-x-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                      <tr>
                        <th className="px-3 py-2">Input</th>
                        <th className="px-3 py-2">Visualisation value</th>
                        <th className="px-3 py-2">Schema range</th>
                        <th className="px-3 py-2">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {schema.inputs.filter((input) => input.name !== sweepInputName).map((input) => (
                        <tr key={input.name} className="align-middle">
                          <td className="px-3 py-2 font-semibold text-slate-800">{input.label}{input.unit ? <span className="ml-1 text-xs font-medium text-slate-400">/ {input.unit}</span> : null}</td>
                          <td className="px-3 py-2">
                            <input
                              type="number"
                              min={input.min}
                              max={input.max}
                              step={(input.max - input.min) / 200}
                              value={visualisationFixedInputs[input.name] ?? inputs[input.name] ?? ''}
                              onChange={(event) => { setVisualisationFixedInputs((current) => ({ ...current, [input.name]: event.target.value })); setVisualisationStale(true) }}
                              className="w-36 rounded-xl border border-slate-200 bg-white px-2 py-1 text-sm font-semibold text-slate-900"
                            />
                          </td>
                          <td className="px-3 py-2 text-slate-500">{formatNumber(input.min)} to {formatNumber(input.max)}</td>
                          <td className="px-3 py-2">
                            <button type="button" onClick={() => { setVisualisationFixedInputs((current) => ({ ...current, [input.name]: inputs[input.name] ?? '' })); setVisualisationStale(true) }} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-600">
                              Copy single-result value
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="mt-5 rounded-3xl border border-slate-200 bg-white p-4">
                <div className="grid gap-3 lg:grid-cols-[minmax(14rem,0.45fr)_minmax(0,1fr)_auto] lg:items-end">
                  <label className="min-w-0 text-sm font-semibold text-slate-700">
                    Plot label
                    <select value={plotAnnotationMode} onChange={(event) => setPlotAnnotationMode(event.target.value as PlotAnnotationMode)} className="mt-2 w-full truncate rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                      <option value="none">No in-plot fixed-condition label</option>
                      <option value="selected">Show selected fixed parameters</option>
                      <option value="all">Show all fixed parameters</option>
                    </select>
                  </label>
                  <div className="min-w-0 rounded-2xl bg-[#0B1220] px-3 py-2 text-sm text-slate-600 ring-1 ring-slate-200">
                    {plotAnnotationMode === 'none' ? (
                      <span>Plot label hidden by default. Enable it only when exported figures need fixed-condition context.</span>
                    ) : plotAnnotationMode === 'selected' ? (
                      <div className="flex flex-wrap gap-2">
                        {schema.inputs.filter((input) => input.name !== sweepInputName).map((input) => (
                          <label key={input.name} className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
                            <input type="checkbox" checked={selectedAnnotationInputs.includes(input.name)} onChange={(event) => setSelectedAnnotationInputs((current) => event.target.checked ? [...new Set([...current, input.name])] : current.filter((name) => name !== input.name))} className="h-3.5 w-3.5 accent-[#2F6BFF]" />
                            {input.label}
                          </label>
                        ))}
                      </div>
                    ) : (
                      <span>All fixed parameters will be shown in the plot label. The swept variable is excluded.</span>
                    )}
                  </div>
                  <button type="button" onClick={() => runVisualisation()} disabled={predicting || visualisationType !== 'generic' || Boolean(sweepRangeIssue)} className="rounded-full bg-[#2F6BFF] px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-[#2F6BFF]/20 disabled:opacity-50">
                    {predicting ? 'Generating...' : 'Generate visualisation'}
                  </button>
                </div>
              </div>
              <div className="mt-4 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-slate-950">Measured training overlay</h3>
                    <p className="mt-1 max-w-5xl text-sm leading-6 text-slate-600">Optional: compare this visualisation with measured training rows from the loaded champion artifact. Hidden by default so predicted sweep setup stays primary.</p>
                  </div>
                  <div className="flex flex-wrap justify-end gap-2">
                    <span className="w-fit whitespace-nowrap rounded-full bg-slate-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 ring-1 ring-slate-200">
                      {String(trainingOverlay.filtered_row_count ?? trainingOverlayRows.length)} shown / {String(trainingOverlay.source_row_count ?? state?.training_overlay_options?.row_count ?? 0)} rows
                    </span>
                    {trainingOverlayRows.length ? <span className="w-fit whitespace-nowrap rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-amber-800 ring-1 ring-amber-200">Compare predicted line vs measured markers</span> : null}
                  </div>
                </div>
                <div className="mt-4 grid gap-3 xl:grid-cols-[minmax(16rem,0.45fr)_minmax(0,1fr)] xl:items-start">
                  <label className="min-w-0 text-sm font-semibold text-slate-700">
                    Overlay mode
                    <select value={overlayMode} onChange={(event) => applyOverlayMode(event.target.value as OverlayMode)} className="mt-2 w-full truncate rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm">
                      <option value="comparable">Comparable training data</option>
                      <option value="same_current_conditions">Re-suggest matches from current values</option>
                      <option value="custom">Custom matching filters</option>
                      <option value="none">No measured overlay</option>
                    </select>
                  </label>
                  <div className="min-w-0 rounded-2xl bg-[#0B1220] p-3 text-sm text-slate-600 ring-1 ring-slate-200">
                    <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Matching by</div>
                    {overlayMode === 'none' ? (
                      <div className="mt-2 font-medium text-slate-700">Overlay hidden</div>
                    ) : displayedOverlaySummaryLabels.length ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {displayedOverlaySummaryLabels.map((label) => (
                          <span key={label} className="max-w-full rounded-md bg-[#0D1B2D] px-3 py-1 text-xs font-semibold text-[#BDEAFF] ring-1 ring-[#74C7F5]/30">
                            <span className="block max-w-[22rem] truncate">{label}</span>
                          </span>
                        ))}
                        {hiddenOverlaySummaryCount > 0 && <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">+{hiddenOverlaySummaryCount} more</span>}
                      </div>
                    ) : (
                      <div className="mt-2 font-medium text-slate-700">All available measured training rows</div>
                    )}
                  </div>
                </div>
              </div>

              <details className="mt-4 rounded-3xl border border-slate-200 bg-[#0B1220] p-4">
                <summary className="cursor-pointer select-none font-semibold text-slate-950">Refine matching / Advanced filters</summary>
                <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-slate-600">
                  <label className="flex items-center gap-2 font-semibold text-slate-700">
                    <input type="checkbox" checked={trainingOverlayEnabled && overlayMode !== 'none'} onChange={(event) => { setTrainingOverlayEnabled(event.target.checked); if (event.target.checked && overlayMode === 'none') setOverlayMode('custom'); if (!event.target.checked) setOverlayMode('none') }} className="h-4 w-4 accent-[#2F6BFF]" />
                    Show measured training overlay
                  </label>
                  <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                    {String(trainingOverlay.filtered_row_count ?? trainingOverlayRows.length)} shown / {String(trainingOverlay.source_row_count ?? state?.training_overlay_options?.row_count ?? 0)} source rows
                  </span>
                </div>
                {overlayColumns.length === 0 && <p className="mt-3 text-sm text-slate-500">No filterable predictions.csv columns were found for this loaded champion.</p>}
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  {visibleOverlayColumns.map((column) => column.filter_kind === 'range' ? (
                    <div key={column.name} className="rounded-2xl border border-slate-200 bg-white p-3">
                      <div className="text-sm font-semibold text-slate-800">{column.label}{column.unit ? ` / ${column.unit}` : ''}</div>
                      <div className="mt-2 grid grid-cols-2 gap-2">
                        <input type="number" value={trainingOverlayRanges[column.name]?.min ?? ''} onChange={(event) => setTrainingOverlayRanges((current) => ({ ...current, [column.name]: { ...(current[column.name] ?? {}), min: event.target.value } }))} placeholder={column.min !== undefined ? `min ${formatNumber(column.min)}` : 'min'} className="rounded-xl border border-slate-200 px-2 py-1 text-sm" />
                        <input type="number" value={trainingOverlayRanges[column.name]?.max ?? ''} onChange={(event) => setTrainingOverlayRanges((current) => ({ ...current, [column.name]: { ...(current[column.name] ?? {}), max: event.target.value } }))} placeholder={column.max !== undefined ? `max ${formatNumber(column.max)}` : 'max'} className="rounded-xl border border-slate-200 px-2 py-1 text-sm" />
                      </div>
                    </div>
                  ) : (
                    <label key={column.name} className="rounded-2xl border border-slate-200 bg-white p-3 text-sm font-semibold text-slate-700">
                      {column.label}{column.unit ? ` / ${column.unit}` : ''}
                      <input list={`overlay-${column.name}`} value={trainingOverlayFilters[column.name] ?? ''} onChange={(event) => setTrainingOverlayFilters((current) => ({ ...current, [column.name]: event.target.value }))} placeholder="Any" className="mt-2 w-full rounded-xl border border-slate-200 px-2 py-1 font-normal" />
                      <datalist id={`overlay-${column.name}`}>{(column.values ?? []).map((value) => <option key={`${column.name}-${String(value)}`} value={String(value)} />)}</datalist>
                    </label>
                  ))}
                  <label className="rounded-2xl border border-slate-200 bg-white p-3 text-sm font-semibold text-slate-700">
                    Color/group by
                    <select value={trainingOverlayGroupBy} onChange={(event) => setTrainingOverlayGroupBy(event.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-2 py-1 font-normal">
                      <option value="">No grouping</option>
                      {trainingOverlayGroupOptions.map((name) => <option key={name} value={name}>{overlayColumns.find((column) => column.name === name)?.label || metadataVariables.find((variable) => variable.name === name)?.label || name}</option>)}
                    </select>
                  </label>
                </div>
                {overlayVisible && prediction?.training_overlay && trainingOverlayRows.length === 0 && (
                  <p className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">No measured training points match the current overlay filters.</p>
                )}
              </details>
            </div>
        </section>
      )}

      {error && <Alert tone="error" title="Design Studio issue" messages={[error]} />}
      {prediction?.warnings?.length ? <Alert tone="warning" title="Model/support warnings" messages={prediction.warnings} /> : null}
      {loading && <div className="rounded-[2rem] bg-white/80 p-6 text-slate-600">Loading Design Studio...</div>}

      {!loading && state && (
        <>
          <section id="design-workspace" className="scroll-mt-8 space-y-6">
            {activeWorkflow === 'model_map' && <section className="rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
              <PanelHeader eyebrow="Model map" title="From experiment settings to predicted response" description="A schema view of the loaded model inputs and outputs. This is separated from Experiment visualisation so it does not interrupt plot setup." />
              <div className="mt-4">
                <ModelMap
                  inputs={schema.inputs}
                  outputs={schema.outputs}
                  modelName={prediction?.model_version || asString(champion.version) || 'loaded champion'}
                />
              </div>
            </section>}

            {activeWorkflow === 'single_result' && <section id="design-experiment" className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <PanelHeader eyebrow="Current design point" title="Tune one design point" description="Adjust the current composition/test values, then generate one model result. Experiment visualisation can sweep one input around this same design point." />
                <div className="flex flex-col items-start gap-2 sm:items-end">
                  <button type="button" onClick={() => runPrediction()} disabled={predicting} className="rounded-full bg-[#2F6BFF] px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-[#2F6BFF]/20 disabled:opacity-50">
                    {predicting ? 'Generating...' : 'Generate result'}
                  </button>
                  <span className={`rounded-md px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] ${hasPendingInputChanges ? 'bg-amber-50 text-amber-800 ring-1 ring-amber-200' : prediction ? 'bg-[#0D1B2D] text-[#BDEAFF] ring-1 ring-[#74C7F5]/30' : 'bg-[#070C16] text-slate-500 ring-1 ring-slate-700'}`}>
                    {hasPendingInputChanges ? 'Inputs changed' : prediction ? 'Result current' : 'No result yet'}
                  </span>
                </div>
              </div>
              {hasPendingInputChanges && (
                <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
                  Inputs changed — click <strong>Generate result</strong> to update the single-point KPI predictions. Use the copy action in Experiment visualisation when you want these values as sweep fixed conditions.
                </div>
              )}
              <div className="mt-5 grid gap-4 lg:grid-cols-2 2xl:grid-cols-4">
                {schema.inputs.map((input) => (
                  <label key={input.name} className="block rounded-3xl border border-slate-200 bg-[#0B1220] p-4 shadow-sm">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-semibold text-slate-900">{input.label}</span>
                      <span className="rounded-full bg-white px-2 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-slate-400">{input.unit}</span>
                    </div>
                    <input
                      type="range"
                      min={input.min}
                      max={input.max}
                      step={(input.max - input.min) / 200}
                      value={inputs[input.name] ?? input.min}
                      onChange={(event) => updateInput(input.name, event.target.value)}
                      className="mt-4 w-full accent-[#2F6BFF]"
                    />
                    <div className="mt-3 flex items-center justify-between gap-2 text-xs text-slate-500">
                      <span>{formatNumber(input.min)}</span>
                      <input
                        type="number"
                        min={input.min}
                        max={input.max}
                        step={(input.max - input.min) / 200}
                        value={inputs[input.name] ?? ''}
                        onChange={(event) => updateInput(input.name, event.target.value)}
                        className="w-28 rounded-xl border border-slate-200 bg-white px-2 py-1 text-right text-sm font-semibold text-slate-900"
                      />
                      <span>{formatNumber(input.max)}</span>
                    </div>
                  </label>
                ))}
              </div>

              <div className="mt-6 border-t border-slate-200 pt-5">
                <PanelHeader eyebrow="Predicted outputs" title="Model-estimated KPIs" description="These values are the single generated result for the currently shown input settings. Objective weights are not needed for this direct prediction." />
                {predicting && <div className="mt-3 text-sm text-slate-500">Generating result...</div>}
                {prediction?.seed && (
                  <div className="mt-4 rounded-md border border-[#74C7F5]/30 bg-[#0D1B2D] p-4 text-sm leading-6 text-[#BDEAFF]">
                    <strong>Why this candidate?</strong> It had the highest model score among {formatNumber(asNumber(asRecord(prediction.seed).n_candidates))} sampled virtual candidates for the selected goal: {currentGoalLabel}. Score: {formatNumber(asNumber(asRecord(prediction.seed).score))}. Model version: {prediction.model_version || 'unknown'}.
                  </div>
                )}
                <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  {schema.outputs.map((output) => {
                    const value = prediction?.predictions_at_selected_point[output.name]
                    const comparisonValue = savedComparison?.predictions_at_selected_point[output.name]
                    const delta = value !== undefined && comparisonValue !== undefined ? value - comparisonValue : undefined
                    const emphasized = emphasizedOutputs.has(output.name)
                    return (
                      <div key={output.name} className={`rounded-3xl border p-4 ${emphasized ? 'border-[#2F6BFF]/60 bg-[#10203A]' : 'border-slate-700 bg-[#0B1220]'}`}>
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="text-sm font-semibold text-slate-900">{output.label}</div>
                            <div className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">{output.direction === 'minimize' ? 'Lower is better' : 'Higher is better'}</div>
                          </div>
                          <span className="text-xs text-slate-500">{output.unit}</span>
                        </div>
                        <div className="mt-3 text-2xl font-semibold text-slate-950">{value === undefined ? '-' : `${formatNumber(value)} ${output.unit}`}</div>
                        {delta !== undefined && <div className={`mt-2 text-sm font-semibold ${delta >= 0 ? 'text-[#74C7F5]' : 'text-rose-700'}`}>{delta >= 0 ? '+' : ''}{formatNumber(delta)} vs saved comparison</div>}
                      </div>
                    )
                  })}
                </div>
              </div>
            </section>}

            {activeWorkflow === 'optimize' && <section id="design-objective" className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/90 p-6 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <PanelHeader eyebrow="Design objective" title="Search for candidates using objective weights" description="Objective settings affect search actions only. Loading a candidate updates the current design point and the visualisation fixed conditions together." />
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={seedFromBatch} disabled={seeding} className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-slate-950/15 disabled:opacity-50">
                    {seeding ? 'Searching designs...' : 'Find best starting design'}
                  </button>
                  <button type="button" onClick={findParetoTradeoffs} disabled={paretoLoading} className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50">
                    {paretoLoading ? 'Finding candidates...' : 'Find tradeoff candidates'}
                  </button>
                </div>
              </div>

              <div className="mt-5 grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
                <div className="rounded-3xl border border-[#2F6BFF]/35 bg-[#10203A] p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="font-semibold text-blue-950">Optimization goal</h3>
                      <p className="mt-1 text-sm leading-6 text-[#BDEAFF]">
                        Select a preset or build a custom multi-objective score. The search samples virtual designs, predicts each one, and loads a high-scoring candidate as the current design point.
                      </p>
                    </div>
                    <span className="w-fit rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-[#BDEAFF]">Current goal: {currentGoalLabel}</span>
                  </div>
                  <label className="mt-4 block text-sm font-semibold text-blue-950">
                    Objective preset
                    <select
                      value={objectiveMode}
                      onChange={(event) => {
                        const nextMode = event.target.value
                        setObjectiveMode(nextMode)
                        const preset = objectivePresets.find((item) => item.id === nextMode)
                        if (preset && nextMode !== 'custom') {
                          setObjectiveWeights(Object.fromEntries(schema.outputs.map((output) => [output.name, String(preset.weights[output.name] ?? 0)])))
                        }
                      }}
                      className="mt-2 w-full rounded-2xl border border-blue-200 bg-white px-3 py-2 text-sm text-slate-900"
                    >
                      {objectivePresets.map((preset) => <option key={preset.id} value={preset.id}>{preset.label}</option>)}
                    </select>
                  </label>
                  {selectedObjective?.description && <p className="mt-2 text-xs leading-5 text-[#BDEAFF]">{selectedObjective.description}</p>}
                </div>

                <div className="rounded-3xl border border-slate-200 bg-[#0B1220] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="font-semibold text-slate-950">Objective mix</h3>
                    <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">custom tradeoffs</span>
                  </div>
                  <p className="mt-1 text-sm leading-6 text-slate-600">Check outputs you care about. Positive weights reward larger predictions; negative weights reward smaller predictions. Zero ignores that output.</p>
                  <div className="mt-4 grid gap-2 lg:grid-cols-2">
                    {schema.outputs.map((output) => {
                      const checked = Math.abs(Number(objectiveWeights[output.name] ?? '0')) > 1e-12
                      const defaultWeight = output.direction === 'minimize' ? '-1' : '1'
                      return (
                        <div key={output.name} className={`grid gap-2 rounded-2xl border px-3 py-2 text-sm md:grid-cols-[1fr_5.5rem] md:items-center ${checked ? 'border-[#2F6BFF]/60 bg-[#10203A]' : 'border-slate-700 bg-[#070C16]'}`}>
                          <label className="flex items-center gap-3 font-semibold text-slate-800">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(event) => {
                                setObjectiveMode('custom')
                                setObjectiveWeights((current) => ({ ...current, [output.name]: event.target.checked ? (current[output.name] && current[output.name] !== '0' ? current[output.name] : defaultWeight) : '0' }))
                              }}
                              className="h-4 w-4 accent-[#2F6BFF]"
                            />
                            <span>{output.label} <span className="font-normal text-slate-400">({output.unit || output.direction})</span></span>
                          </label>
                          <input
                            type="number"
                            step="0.1"
                            value={objectiveWeights[output.name] ?? '0'}
                            onFocus={() => setObjectiveMode('custom')}
                            onChange={(event) => {
                              setObjectiveMode('custom')
                              setObjectiveWeights((current) => ({ ...current, [output.name]: event.target.value }))
                            }}
                            className="rounded-xl border border-slate-200 px-2 py-1 text-right font-semibold text-slate-900"
                          />
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>

              <div className="mt-5 rounded-3xl border border-slate-200 bg-white p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="font-semibold text-slate-950">Search space / fixed conditions</h3>
                    <p className="mt-1 text-sm leading-6 text-slate-600">Choose which schema inputs the optimizer may vary. Fixed inputs use the current Single result inputs; constrained inputs search only inside the selected range.</p>
                  </div>
                  <span className="rounded-full bg-[#0B1220] px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">generic inputs</span>
                </div>
                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  {schema.inputs.map((input) => {
                    const mode = searchSpaceModes[input.name] || 'free'
                    const range = searchSpaceRanges[input.name] || { min: String(input.min), max: String(input.max) }
                    return (
                      <div key={input.name} className="rounded-2xl border border-slate-200 bg-[#0B1220] p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="font-semibold text-slate-800">{input.label}{input.unit ? ` / ${input.unit}` : ''}</div>
                          <div className="text-xs text-slate-500">Current design point: {formatNumber(Number(currentDesignPoint[input.name]))}</div>
                        </div>
                        <div className="mt-2 grid gap-2 md:grid-cols-[1fr_1fr_1fr] md:items-center">
                          <select value={mode} onChange={(event) => setSearchSpaceModes((current) => ({ ...current, [input.name]: event.target.value as 'free' | 'fixed' | 'range' }))} className="rounded-xl border border-slate-200 bg-white px-2 py-1 text-sm">
                            <option value="free">Free over schema range</option>
                            <option value="fixed">Fixed at current value</option>
                            <option value="range">Constrained range</option>
                          </select>
                          <input type="number" disabled={mode !== 'range'} value={range.min ?? ''} onChange={(event) => setSearchSpaceRanges((current) => ({ ...current, [input.name]: { ...(current[input.name] ?? {}), min: event.target.value } }))} placeholder={String(input.min)} className="rounded-xl border border-slate-200 bg-white px-2 py-1 text-sm disabled:bg-slate-100" />
                          <input type="number" disabled={mode !== 'range'} value={range.max ?? ''} onChange={(event) => setSearchSpaceRanges((current) => ({ ...current, [input.name]: { ...(current[input.name] ?? {}), max: event.target.value } }))} placeholder={String(input.max)} className="rounded-xl border border-slate-200 bg-white px-2 py-1 text-sm disabled:bg-slate-100" />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </section>}

            {activeWorkflow === 'compare' && <section id="design-compare" className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/90 p-6 shadow-sm">
              <PanelHeader eyebrow="Compare and package" title="Prepare this candidate for lab review" description="Save a comparison candidate or export a complete design package. Generic training-data overlays are controlled in the experiment visualisation settings." />
              <div className="mt-5 grid gap-4 lg:grid-cols-2 lg:items-end">
                <button type="button" onClick={() => prediction && setSavedComparison(prediction)} disabled={!prediction} className="rounded-full border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-700 disabled:opacity-50">
                  Save current as comparison
                </button>
                <button type="button" onClick={exportZip} disabled={exporting || !prediction} className="rounded-full bg-[#2F6BFF] px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">
                  {exporting ? 'Exporting...' : 'Export design package'}
                </button>
              </div>
            </section>}
          </section>

          {activeWorkflow === 'plot' && <section id="design-response-curve" className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <PanelHeader eyebrow="Experiment visualisation" title={plotTitle || selectedExperimentVisualisationConfig?.label || 'Predicted response'} description={selectedExperimentVisualisationConfig?.description || 'Sweep one variable, keep fixed inputs constant, and plot predicted response points.'} />
              <button
                type="button"
                onClick={exportResponseCurvePng}
                disabled={!curveRows.length || exportingCurvePng}
                className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-[#74C7F5] hover:bg-[#0D1524] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {exportingCurvePng ? 'Exporting PNG…' : 'Export plot PNG'}
              </button>
            </div>
            {!curveRows.length && (
              <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
                No experiment visualisation is available yet. Click <strong>Generate visualisation</strong> to sweep the selected variable, or <strong>Find best starting design</strong> to let the model choose a candidate.
              </div>
            )}
            {curveRows.length > 0 && visualisationStale && (
              <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
                Fixed values or plot setup changed since this plot was generated. Click <strong>Generate visualisation</strong> to refresh the multi-point plot.
              </div>
            )}
            {curveRows.length > 0 && (
              <div className="mt-4 rounded-2xl border border-slate-200 bg-[#0B1220] p-4 text-sm leading-6 text-slate-600">
                <div><strong className="text-slate-900">Sweep:</strong> {sweepRangeLabel}</div>
                <div><strong className="text-slate-900">Fixed conditions:</strong> {visualisationFixedConditionLabels.length ? visualisationFixedConditionLabels.join(' · ') : 'Only the swept variable is varied.'}</div>
                {visualisationGroupLabels.length > 0 && <div><strong className="text-slate-900">Grouped curves:</strong> {visualisationGroupLabels.join(' · ')}</div>}
              </div>
            )}
            <Plot
              data={responseCurveData}
              layout={responseCurveLayout}
              config={plotConfig}
              onInitialized={(_, graphDiv) => { responseCurvePlotRef.current = graphDiv }}
              onUpdate={(_, graphDiv) => { responseCurvePlotRef.current = graphDiv }}
              useResizeHandler
              style={{ width: '100%', height: '470px' }}
            />
            <p className="mt-3 rounded-2xl bg-[#0B1220] px-4 py-3 text-sm leading-6 text-slate-600">
              Predicted traces come from the loaded champion model. Training overlay markers come from static predictions.csv *_true measured columns and the generic filters above.
            </p>
          </section>}

          {activeWorkflow === 'optimize' && paretoResults && (
            <section id="design-tradeoffs" className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/90 p-6 shadow-sm">
              <PanelHeader
                eyebrow="Find alternatives"
                title="Tradeoff candidates"
                description="Optional starting points. Use one as the current design point to update Single result inputs and visualisation fixed conditions together."
              />
              <div className="mt-4 rounded-2xl border border-[#2F6BFF]/35 bg-[#10203A] p-4 text-sm leading-6 text-[#BDEAFF]">
                These are alternative starting designs from {paretoResults.n_candidates} virtual candidates. Use one as the current design point, then plot a sweep around that point. Lower raw values are better for minimized objectives.
              </div>
              <div className="mt-5 space-y-3">
                {paretoResults.candidates.map((candidate) => (
                  <article key={candidate.rank} className="rounded-2xl border border-slate-200 bg-[#0B1220] p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="font-semibold text-slate-950">{candidate.label}</h3>
                        <p className="mt-1 text-xs text-slate-500">Rank {candidate.rank} · score {formatNumber(candidate.score)}</p>
                      </div>
                      <button type="button" onClick={() => loadParetoCandidate(candidate)} className="rounded-full bg-slate-950 px-3 py-1.5 text-xs font-semibold text-white">
                        Use as current design point
                      </button>
                    </div>
                    <div className="mt-4 grid gap-2 text-sm md:grid-cols-2">
                      {schema.inputs.map((input) => (
                        <div key={`${candidate.rank}-${input.name}`} className="flex justify-between gap-3 rounded-2xl bg-white px-3 py-2">
                          <span className="text-slate-600">{input.label}</span>
                          <strong className="text-slate-950">{formatNumber(candidate.inputs[input.name])} {input.unit}</strong>
                        </div>
                      ))}
                    </div>
                    <div className="mt-3 space-y-2 text-sm">
                      {paretoResults.objectives.map((objective) => {
                        const obj = asRecord(objective)
                        const name = asString(obj.name)
                        return (
                          <div key={`${candidate.rank}-${name}`} className="flex justify-between gap-3 rounded-2xl bg-white px-3 py-2">
                            <span className="text-slate-600">{asString(obj.label) || name}</span>
                            <strong className="text-slate-950">{formatNumber(candidate.predictions[name])} {asString(obj.unit)}</strong>
                          </div>
                        )
                      })}
                    </div>
                    <p className="mt-3 text-xs leading-5 text-slate-500">{candidate.tradeoff_summary}</p>
                  </article>
                ))}
              </div>
              {paretoResults.objectives.length >= 2 && (
                <details className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
                  <summary className="cursor-pointer select-none text-sm font-semibold text-slate-800">Show Pareto scatter plot</summary>
                  <div className="mt-4">
                  <Plot
                    data={asPlotData([
                      {
                        name: 'Pareto candidates',
                        x: paretoResults.candidates.map((candidate) => candidate.predictions[asString(asRecord(paretoResults.objectives[0]).name)]),
                        y: paretoResults.candidates.map((candidate) => candidate.predictions[asString(asRecord(paretoResults.objectives[1]).name)]),
                        text: paretoResults.candidates.map((candidate) => candidate.label),
                        type: 'scatter',
                        mode: 'markers+text',
                        textposition: 'top center',
                        marker: { size: 11, color: '#2F6BFF', opacity: 0.85 },
                      },
                    ])}
                    layout={asPlotLayout(lightPlotOnDarkCardLayout({
                      ...plotLayoutBase,
                      height: 360,
                      xaxis: { title: { text: `${asString(asRecord(paretoResults.objectives[0]).label)} / ${asString(asRecord(paretoResults.objectives[0]).unit)}` }, zeroline: false },
                      yaxis: { title: { text: `${asString(asRecord(paretoResults.objectives[1]).label)} / ${asString(asRecord(paretoResults.objectives[1]).unit)}` }, zeroline: false },
                    }))}
                    config={plotConfig}
                    useResizeHandler
                    style={{ width: '100%', height: '360px' }}
                  />
                  </div>
                </details>
              )}
            </section>
          )}
        </>
      )}
    </div>
  )
}
