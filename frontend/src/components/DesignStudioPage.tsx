import { useEffect, useMemo, useRef, useState } from 'react'
import Plot from 'react-plotly.js'
import * as Plotly from 'plotly.js-dist-min'
import type { DesignStudioParetoCandidate, DesignStudioParetoResponse, DesignStudioPrediction, DesignStudioState, PlotRecipe, ProjectSchema } from '../lib/api'
import { exportDesignStudioZip, findDesignStudioPareto, getDesignStudioState, predictDesignStudio, seedDesignStudioBatch } from '../lib/api'
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

const plotConfig = { responsive: true, displaylogo: false }
const plotLayoutBase = {
  paper_bgcolor: 'rgba(255,255,255,0)',
  plot_bgcolor: '#ffffff',
  margin: { l: 60, r: 24, t: 34, b: 56 },
  font: { family: 'Inter, ui-sans-serif, system-ui', color: '#334155' },
  legend: { orientation: 'h' as const, y: -0.25 },
}

type ObjectivePreset = {
  id: string
  label: string
  description: string
  weights: Record<string, number>
}

function numericObjectiveWeights(weights: Record<string, string>) {
  return Object.fromEntries(Object.entries(weights).map(([key, value]) => [key, Number(value) || 0]))
}

export function DesignStudioPage({ schema }: { schema: ProjectSchema }) {
  const [state, setState] = useState<DesignStudioState | null>(null)
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [prediction, setPrediction] = useState<DesignStudioPrediction | null>(null)
  const [savedComparison, setSavedComparison] = useState<DesignStudioPrediction | null>(null)
  const [selectedRealCell, setSelectedRealCell] = useState('')
  const [selectedPlotRecipeId, setSelectedPlotRecipeId] = useState('')
  const [sweepInputName, setSweepInputName] = useState('')
  const [primaryOutputName, setPrimaryOutputName] = useState('')
  const [secondaryOutputName, setSecondaryOutputName] = useState('')
  const [sweepPointCount, setSweepPointCount] = useState('60')
  const [responseAxesSwapped, setResponseAxesSwapped] = useState(false)
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
  const responseCurvePlotRef = useRef<unknown>(null)
  const [error, setError] = useState<string | null>(null)

  const realCellOptions = state?.real_cell_options ?? []
  const selectedRealCellPayload = useMemo(() => {
    if (!selectedRealCell) return undefined
    const option = realCellOptions[Number(selectedRealCell)]
    if (!option) return undefined
    return {
      cell_id: asString(option.cell_id),
      operating_rh: asNumber(option.operating_rh),
      split: asString(option.split),
    }
  }, [realCellOptions, selectedRealCell])

  const numericInputs = useMemo(() => Object.fromEntries(schema.inputs.map((input) => [input.name, Number(inputs[input.name])])), [inputs, schema.inputs])
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
    const outputNames = new Set(schema.outputs.map((output) => output.name))
    const fuelCellBalanced = ['bol_current_density', 'eol_current_density', 'ecsa_loss'].every((name) => outputNames.has(name))
      ? [{
          id: 'balanced:fuel-cell',
          label: 'Balanced fuel-cell performance',
          description: 'Favor high BoL/EoL current density while penalizing ECSA loss.',
          weights: { bol_current_density: 0.4, eol_current_density: 0.4, ecsa_loss: -0.2 },
        }]
      : []
    return [...singleOutputPresets, ...fuelCellBalanced, { id: 'custom', label: 'Custom weights', description: 'Choose your own tradeoff across outputs.', weights: {} }]
  }, [schema.outputs])
  const selectedObjectiveWeights = useMemo(() => {
    if (objectiveMode === 'custom') return numericObjectiveWeights(objectiveWeights)
    const preset = objectivePresets.find((item) => item.id === objectiveMode)
    return preset?.weights ?? numericObjectiveWeights(objectiveWeights)
  }, [objectiveMode, objectivePresets, objectiveWeights])
  const selectedObjective = objectivePresets.find((item) => item.id === objectiveMode)
  const currentGoalLabel = selectedObjective?.label || 'Selected objective'
  const activeObjectiveCount = Object.values(selectedObjectiveWeights).filter((value) => Math.abs(value) > 1e-12).length
  const isFuelCellResponseRecipe = (recipe?: PlotRecipe) => recipe?.kind === 'fuel_cell_polarization'

  function dynamicPlotRecipe(recipeId = selectedPlotRecipeId): PlotRecipe | undefined {
    const recipe = state?.plot_recipes?.find((item) => item.id === recipeId)
    if (isFuelCellResponseRecipe(recipe)) return undefined
    const xVariable = sweepInputName || asString(asRecord(recipe?.x).variable) || schema.inputs[0]?.name
    const yVariable = primaryOutputName || asString(asRecord(recipe?.y).variable) || schema.outputs[0]?.name
    const secondary = secondaryOutputName && secondaryOutputName !== yVariable ? secondaryOutputName : ''
    if (!xVariable || !yVariable) return undefined
    return {
      id: recipeId || `dynamic_${xVariable}_${yVariable}`,
      label: `${schema.outputs.find((output) => output.name === yVariable)?.label ?? yVariable} vs ${schema.inputs.find((input) => input.name === xVariable)?.label ?? xVariable}`,
      description: 'Scientist-selected response sweep: hold the current design fixed, vary one input, and predict selected output(s).',
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
    } as PlotRecipe & { points: number }
  }

  function requestPlotPayload(recipeId = selectedPlotRecipeId) {
    const recipe = state?.plot_recipes?.find((item) => item.id === recipeId)
    const dynamicRecipe = dynamicPlotRecipe(recipeId)
    return dynamicRecipe ? { plot_recipe_id: recipeId || undefined, plot_recipe: dynamicRecipe } : { plot_recipe_id: recipe?.id || recipeId || undefined }
  }

  function applyRecipeDefaults(recipe?: PlotRecipe) {
    if (!recipe || isFuelCellResponseRecipe(recipe)) return
    setSweepInputName(asString(asRecord(recipe.x).variable) || schema.inputs[0]?.name || '')
    setPrimaryOutputName(asString(asRecord(recipe.y).variable) || schema.outputs[0]?.name || '')
    const firstSeries = Array.isArray(recipe.series) ? asString(asRecord(recipe.series[0]).variable) : ''
    setSecondaryOutputName(firstSeries && firstSeries !== asString(asRecord(recipe.y).variable) ? firstSeries : '')
  }

  async function loadState() {
    setLoading(true)
    setError(null)
    try {
      const payload = await getDesignStudioState(schema.project_id)
      const defaultInputs = Object.fromEntries(schema.inputs.map((input) => [input.name, String(payload.default_inputs[input.name] ?? (input.min + input.max) / 2)]))
      const numericDefaultInputs = Object.fromEntries(schema.inputs.map((input) => [input.name, Number(defaultInputs[input.name])]))
      const defaultRecipe = payload.plot_recipes?.find((recipe) => recipe.id === payload.selected_plot_recipe_id) || payload.plot_recipes?.find((recipe) => recipe.recommended) || payload.plot_recipes?.[0]
      const defaultPlotRecipeId = defaultRecipe?.id || ''
      const defaultSweep = asString(asRecord(defaultRecipe?.x).variable) || schema.inputs[0]?.name || ''
      const defaultOutput = asString(asRecord(defaultRecipe?.y).variable) || schema.outputs[0]?.name || ''
      const defaultDynamicRecipe = defaultRecipe?.kind === 'fuel_cell_polarization' || !defaultSweep || !defaultOutput
        ? undefined
        : {
            id: defaultPlotRecipeId || `dynamic_${defaultSweep}_${defaultOutput}`,
            label: `${schema.outputs.find((output) => output.name === defaultOutput)?.label ?? defaultOutput} vs ${schema.inputs.find((input) => input.name === defaultSweep)?.label ?? defaultSweep}`,
            description: 'Scientist-selected response sweep: hold the current design fixed, vary one input, and predict selected output(s).',
            kind: 'scatter_response',
            template_id: 'generic_tabular_doe',
            safe: true,
            recommended: true,
            x: { source: 'input', variable: defaultSweep },
            y: { source: 'prediction', variable: defaultOutput },
            series: [],
            filters: [],
            group_by: null,
            points: 60,
          }
      setState(payload)
      setInputs(defaultInputs)
      setSelectedPlotRecipeId(defaultPlotRecipeId)
      setSweepInputName(defaultSweep)
      setPrimaryOutputName(defaultOutput)
      setSecondaryOutputName('')
      setPrediction(await predictDesignStudio(schema.project_id, { inputs: numericDefaultInputs, plot_recipe_id: defaultPlotRecipeId || undefined, ...(defaultDynamicRecipe ? { plot_recipe: defaultDynamicRecipe } : {}) }))
      setHasPendingInputChanges(false)
      const defaultObjectiveName = Object.keys(payload.default_objective_weights ?? {})[0]
      setObjectiveMode(defaultObjectiveName ? `single:${defaultObjectiveName}` : 'custom')
      setObjectiveWeights(Object.fromEntries(schema.outputs.map((output) => [output.name, String(payload.default_objective_weights[output.name] ?? 0)])))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load Design Studio')
    } finally {
      setLoading(false)
    }
  }

  async function runPrediction(nextInputs = numericInputs, plotRecipeId = selectedPlotRecipeId) {
    setPredicting(true)
    setError(null)
    try {
      setPrediction(await predictDesignStudio(schema.project_id, { inputs: nextInputs, comparison_real_cell: selectedRealCellPayload, ...requestPlotPayload(plotRecipeId) }))
      setHasPendingInputChanges(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to predict design')
    } finally {
      setPredicting(false)
    }
  }

  async function choosePlotRecipe(plotRecipeId: string) {
    setSelectedPlotRecipeId(plotRecipeId)
    applyRecipeDefaults(state?.plot_recipes?.find((recipe) => recipe.id === plotRecipeId))
    if (state && prediction) await runPrediction(numericInputs, plotRecipeId)
  }

  function updateInput(name: string, value: string) {
    setInputs((current) => ({ ...current, [name]: value }))
    setHasPendingInputChanges(true)
  }

  async function seedFromBatch() {
    setSeeding(true)
    setError(null)
    try {
      const seeded = await seedDesignStudioBatch(schema.project_id, {
        objective_weights: selectedObjectiveWeights,
        n_candidates: 3000,
        comparison_real_cell: selectedRealCellPayload,
        ...requestPlotPayload(),
      })
      setPrediction(seeded)
      setInputs(Object.fromEntries(schema.inputs.map((input) => [input.name, String(seeded.inputs[input.name] ?? inputs[input.name] ?? '')])))
      setHasPendingInputChanges(false)
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
        comparison_real_cell: selectedRealCellPayload,
        ...requestPlotPayload(),
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to find Pareto tradeoffs')
    } finally {
      setParetoLoading(false)
    }
  }

  async function loadParetoCandidate(candidate: DesignStudioParetoCandidate) {
    setInputs(Object.fromEntries(schema.inputs.map((input) => [input.name, String(candidate.inputs[input.name] ?? inputs[input.name] ?? '')])))
    await runPrediction(candidate.inputs)
  }

  async function exportZip() {
    setExporting(true)
    setError(null)
    try {
      const blob = await exportDesignStudioZip(schema.project_id, {
        inputs: numericInputs,
        comparison_real_cell: selectedRealCellPayload,
        comparison_candidate: savedComparison?.inputs,
        ...requestPlotPayload(),
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
      setError(err instanceof Error ? err.message : 'Unable to export response curve PNG')
    } finally {
      setExportingCurvePng(false)
    }
  }

  useEffect(() => {
    loadState()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema.project_id])

  useEffect(() => {
    if (!state || !prediction) return
    runPrediction()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRealCell])

  const plotRecipes = state?.plot_recipes ?? []
  const selectedPlotRecipe = plotRecipes.find((recipe) => recipe.id === selectedPlotRecipeId) ?? plotRecipes.find((recipe) => recipe.recommended) ?? plotRecipes[0]
  const curveRecipe = asRecord(prediction?.curve?.recipe) as PlotRecipe | Record<string, unknown>
  const curveRows = asRecord(prediction?.curve).rows as Array<Record<string, unknown>> | undefined ?? []
  const comparisonCurveRows = asRecord(savedComparison?.curve).rows as Array<Record<string, unknown>> | undefined ?? []
  const realCurveRows = asRecord(prediction?.comparison_real_cell).rows as Array<Record<string, unknown>> | undefined ?? []
  const activeModel = asRecord(state?.active_model)
  const aliases = asRecord(activeModel.aliases)
  const champion = asRecord(aliases.champion)
  const challenger = asRecord(aliases.challenger)
  const defaultObjectiveName = Object.keys(state?.default_objective_weights ?? {})[0]
  const emphasizedOutputs = new Set(Object.entries(selectedObjectiveWeights).filter(([, value]) => Math.abs(value) > 1e-12).map(([name]) => name))
  const curveKind = asString(asRecord(curveRecipe).kind) || selectedPlotRecipe?.kind || ''
  const curveXAxisVariable = asString(asRecord(asRecord(curveRecipe).x).variable) || asString(asRecord(selectedPlotRecipe?.x).variable)
  const curveYAxisVariable = asString(asRecord(asRecord(curveRecipe).y).variable) || asString(asRecord(selectedPlotRecipe?.y).variable)
  const curveXAxisMeta = schema.inputs.find((input) => input.name === curveXAxisVariable) ?? schema.outputs.find((output) => output.name === curveXAxisVariable)
  const curveYAxisMeta = schema.outputs.find((output) => output.name === curveYAxisVariable) ?? schema.inputs.find((input) => input.name === curveYAxisVariable)
  const curveYVariables = (Array.isArray(asRecord(curveRecipe).y_variables) ? asRecord(curveRecipe).y_variables as unknown[] : [])
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
  const responseCurveData = curveKind === 'fuel_cell_polarization'
    ? asPlotData([
        { name: 'Current design BoL', x: curveRows.map((row) => asNumber(row.bol_current_density)), y: curveRows.map((row) => asNumber(row.operating_voltage)), type: 'scatter', mode: 'lines+markers', line: { color: '#2563eb', width: 3, dash: 'dash' } },
        { name: 'Current design EoL', x: curveRows.map((row) => asNumber(row.eol_current_density)), y: curveRows.map((row) => asNumber(row.operating_voltage)), type: 'scatter', mode: 'lines+markers', line: { color: '#dc2626', width: 3, dash: 'dash' } },
        { name: 'Saved comparison BoL', x: comparisonCurveRows.map((row) => asNumber(row.bol_current_density)), y: comparisonCurveRows.map((row) => asNumber(row.operating_voltage)), type: 'scatter', mode: 'lines', line: { color: '#60a5fa', width: 2, dash: 'dot' }, visible: comparisonCurveRows.length ? true : 'legendonly' },
        { name: 'Saved comparison EoL', x: comparisonCurveRows.map((row) => asNumber(row.eol_current_density)), y: comparisonCurveRows.map((row) => asNumber(row.operating_voltage)), type: 'scatter', mode: 'lines', line: { color: '#f87171', width: 2, dash: 'dot' }, visible: comparisonCurveRows.length ? true : 'legendonly' },
        { name: 'Measured real BoL', x: realCurveRows.map((row) => asNumber(row.bol_current_density_true)), y: realCurveRows.map((row) => asNumber(row.operating_voltage)), type: 'scatter', mode: 'lines+markers', line: { color: '#334155', width: 2 }, visible: realCurveRows.length ? true : 'legendonly' },
        { name: 'Measured real EoL', x: realCurveRows.map((row) => asNumber(row.eol_current_density_true)), y: realCurveRows.map((row) => asNumber(row.operating_voltage)), type: 'scatter', mode: 'lines+markers', line: { color: '#92400e', width: 2 }, visible: realCurveRows.length ? true : 'legendonly' },
      ])
    : asPlotData([
        ...genericCurveYVariables.map((variable, index) => ({
          name: `Predicted ${schema.outputs.find((output) => output.name === variable)?.label || variable}`,
          x: curveRows.map((row) => asNumber(row[responseAxesSwapped ? variable : curveXAxisVariable])),
          y: curveRows.map((row) => asNumber(row[responseAxesSwapped ? curveXAxisVariable : variable])),
          type: 'scatter',
          mode: 'lines+markers',
          line: { color: ['#526949', '#2563eb', '#dc2626', '#7c3aed'][index % 4], width: 3 },
        })),
        ...genericCurveYVariables
          .filter((variable) => realCurveRows.some((row) => asNumber(row[`${variable}_true`]) !== undefined))
          .map((variable, index) => ({
            name: `Observed ${schema.outputs.find((output) => output.name === variable)?.label || variable}`,
            x: realCurveRows.map((row) => asNumber(row[responseAxesSwapped ? `${variable}_true` : curveXAxisVariable])),
            y: realCurveRows.map((row) => asNumber(row[responseAxesSwapped ? curveXAxisVariable : `${variable}_true`])),
            type: 'scatter',
            mode: 'lines+markers',
            line: { color: ['#334155', '#92400e', '#0f766e', '#6d28d9'][index % 4], width: 2, dash: 'dot' },
            visible: realCurveRows.length ? true : 'legendonly',
          })),
      ])
  const responseCurveLayout = curveKind === 'fuel_cell_polarization'
    ? asPlotLayout({ ...plotLayoutBase, paper_bgcolor: '#ffffff', plot_bgcolor: '#ffffff', height: 470, xaxis: { title: { text: 'Current density / A cm⁻²' }, zeroline: false }, yaxis: { title: { text: 'Cell voltage / V' }, zeroline: false } })
    : asPlotLayout({
        ...plotLayoutBase,
        paper_bgcolor: '#ffffff',
        plot_bgcolor: '#ffffff',
        height: 470,
        xaxis: { title: { text: responseAxesSwapped ? genericSwappedXAxisTitle : `${curveXAxisMeta?.label ?? curveXAxisVariable}${curveXAxisMeta?.unit ? ` / ${curveXAxisMeta.unit}` : ''}` }, zeroline: false },
        yaxis: { title: { text: responseAxesSwapped ? genericSwappedYAxisTitle : `${curveYAxisMeta?.label ?? curveYAxisVariable}${curveYAxisMeta?.unit ? ` / ${curveYAxisMeta.unit}` : ''}` }, zeroline: false },
      })

  return (
    <div className="space-y-8">
      <section className="rounded-[2rem] border border-white/70 bg-white/90 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
        <PanelHeader
          eyebrow="Design Studio"
          title="Interactive surrogate-model playground"
          description="Seed a candidate, move schema-driven inputs, watch predictions update, compare against real experiments, and export a design package for lab review."
        />
        <div className="mt-4 flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.14em]">
          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-emerald-800">Served-model predictions</span>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-slate-600">Champion: {asString(champion.version) || 'not set'}</span>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-slate-600">Challenger: {asString(challenger.version) || 'not set'}</span>
          {defaultObjectiveName && <span className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-blue-800">Default objective: {schema.outputs.find((output) => output.name === defaultObjectiveName)?.label ?? defaultObjectiveName}</span>}
        </div>
      </section>

      {plotRecipes.length > 0 && (
        <section className="rounded-[1.5rem] border border-[#d8c99b]/50 bg-[#fffdf7] p-4 shadow-sm">
          <div className="grid gap-4 lg:grid-cols-[0.7fr_1.3fr] lg:items-center">
            <label className="text-sm font-semibold text-slate-700">
              Plot Options
              <select value={selectedPlotRecipeId} onChange={(event) => choosePlotRecipe(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                {plotRecipes.filter((recipe) => recipe.safe !== false).map((recipe) => (
                  <option key={recipe.id} value={recipe.id}>{recipe.recommended ? 'Recommended · ' : ''}{recipe.label}</option>
                ))}
              </select>
            </label>
            <div className="rounded-2xl border border-[#d8c99b]/40 bg-white px-4 py-3 text-sm leading-6 text-slate-600">
              <strong className="text-slate-900">Selected downstream view:</strong> {selectedPlotRecipe?.description || 'Mirai inferred this safe plot from approved project metadata.'}
            </div>
          </div>
          {selectedPlotRecipe?.kind !== 'fuel_cell_polarization' && (
            <div className="mt-4 rounded-3xl border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="font-semibold text-slate-950">Scientist response plot</h3>
                  <p className="mt-1 text-sm leading-6 text-slate-600">Choose one input to sweep while the other current design settings stay fixed. Then plot one or two predicted outputs from the selected project&apos;s challenger model.</p>
                </div>
                <span className="rounded-full bg-[#fbfaf5] px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">schema-driven</span>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-5">
                <label className="text-sm font-semibold text-slate-700">
                  Sweep input
                  <select value={sweepInputName} onChange={(event) => setSweepInputName(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                    {schema.inputs.map((input) => <option key={input.name} value={input.name}>{input.label}{input.unit ? ` / ${input.unit}` : ''}</option>)}
                  </select>
                </label>
                <label className="text-sm font-semibold text-slate-700">
                  Y-axis output
                  <select value={primaryOutputName} onChange={(event) => setPrimaryOutputName(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                    {schema.outputs.map((output) => <option key={output.name} value={output.name}>{output.label}{output.unit ? ` / ${output.unit}` : ''}</option>)}
                  </select>
                </label>
                <label className="text-sm font-semibold text-slate-700">
                  Optional second output
                  <select value={secondaryOutputName} onChange={(event) => setSecondaryOutputName(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                    <option value="">None</option>
                    {schema.outputs.map((output) => <option key={output.name} value={output.name}>{output.label}{output.unit ? ` / ${output.unit}` : ''}</option>)}
                  </select>
                </label>
                <label className="text-sm font-semibold text-slate-700">
                  Sweep points
                  <input type="number" min="10" max="200" value={sweepPointCount} onChange={(event) => setSweepPointCount(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm" />
                </label>
                <label className="rounded-2xl border border-slate-200 bg-[#fbfaf5] px-3 py-2 text-sm font-semibold text-slate-700">
                  Axis orientation
                  <span className="mt-2 flex items-center gap-2 text-sm font-medium text-slate-600">
                    <input type="checkbox" checked={responseAxesSwapped} onChange={(event) => setResponseAxesSwapped(event.target.checked)} className="h-4 w-4 accent-[#526949]" />
                    Switch axes
                  </span>
                </label>
              </div>
              <p className="mt-3 text-xs leading-5 text-slate-500">Changing these controls updates the next generated response curve. Use <strong>Switch axes</strong> for visuals such as fuel-cell polarization curves, where current density is conventionally shown on X and voltage on Y even when the model predicts current from voltage.</p>
            </div>
          )}
        </section>
      )}

      <nav className="rounded-[1.5rem] border border-white/70 bg-white/70 p-3 shadow-sm backdrop-blur" aria-label="Design Studio page sections">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="px-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">On this page</span>
          {[
            ['Model flow', '#design-model-flow'],
            ['Experiment inputs', '#design-experiment'],
            ['Design objective', '#design-objective'],
            ['Compare/export', '#design-compare'],
            ['Response curve', '#design-response-curve'],
            ['Tradeoffs', '#design-tradeoffs'],
          ].map(([label, href]) => (
            <a key={href} href={href} className="rounded-full border border-slate-200 bg-white px-3 py-1.5 font-semibold text-slate-600 transition hover:border-[#526949]/40 hover:text-[#526949]">
              {label}
            </a>
          ))}
        </div>
      </nav>

      {error && <Alert tone="error" title="Design Studio issue" messages={[error]} />}
      {loading && <div className="rounded-[2rem] bg-white/80 p-6 text-slate-600">Loading Design Studio...</div>}

      {!loading && state && (
        <>
          <section id="design-workspace" className="scroll-mt-8 space-y-6">
            <ModelMap
              inputs={schema.inputs}
              outputs={schema.outputs}
              modelName={prediction?.model_version || asString(challenger.version) || asString(champion.version) || 'active surrogate model'}
            />

            <section id="design-experiment" className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <PanelHeader eyebrow="Experiment inputs" title="Tune test conditions" description="Adjust the current composition/test values, then generate one model result for the selected design. The KPI cards below belong to this single generated result." />
                <div className="flex flex-col items-start gap-2 sm:items-end">
                  <button type="button" onClick={() => runPrediction()} disabled={predicting} className="rounded-full bg-[#526949] px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-[#526949]/20 disabled:opacity-50">
                    {predicting ? 'Generating...' : 'Generate result'}
                  </button>
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] ${hasPendingInputChanges ? 'bg-amber-50 text-amber-800 ring-1 ring-amber-200' : prediction ? 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200' : 'bg-slate-100 text-slate-500'}`}>
                    {hasPendingInputChanges ? 'Inputs changed' : prediction ? 'Result current' : 'No result yet'}
                  </span>
                </div>
              </div>
              {hasPendingInputChanges && (
                <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
                  Inputs changed — click <strong>Generate result</strong> to update the single-point KPI predictions and the polarization curve below.
                </div>
              )}
              <div className="mt-5 grid gap-4 lg:grid-cols-2 2xl:grid-cols-4">
                {schema.inputs.map((input) => (
                  <label key={input.name} className="block rounded-3xl border border-slate-200 bg-[#fbfaf5] p-4 shadow-sm">
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
                      className="mt-4 w-full accent-[#526949]"
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
                  <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-900">
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
                      <div key={output.name} className={`rounded-3xl border p-4 ${emphasized ? 'border-blue-200 bg-blue-50' : 'border-slate-200 bg-[#fbfaf5]'}`}>
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="text-sm font-semibold text-slate-900">{output.label}</div>
                            <div className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">{output.direction === 'minimize' ? 'Lower is better' : 'Higher is better'}</div>
                          </div>
                          <span className="text-xs text-slate-500">{output.unit}</span>
                        </div>
                        <div className="mt-3 text-2xl font-semibold text-slate-950">{value === undefined ? '-' : `${formatNumber(value)} ${output.unit}`}</div>
                        {delta !== undefined && <div className={`mt-2 text-sm font-semibold ${delta >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>{delta >= 0 ? '+' : ''}{formatNumber(delta)} vs saved comparison</div>}
                      </div>
                    )
                  })}
                </div>
              </div>
            </section>

            <section id="design-objective" className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/90 p-6 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <PanelHeader eyebrow="Design objective" title="Search for candidates using objective weights" description="Objective settings affect search actions only. They do not change the direct single-result prediction above until a searched candidate is loaded." />
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
                <div className="rounded-3xl border border-blue-100 bg-blue-50 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="font-semibold text-blue-950">Optimization goal</h3>
                      <p className="mt-1 text-sm leading-6 text-blue-900">
                        Select a preset or build a custom multi-objective score. The search samples virtual designs, predicts each one, and loads a high-scoring candidate into Experiment inputs.
                      </p>
                    </div>
                    <span className="w-fit rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-blue-800">Current goal: {currentGoalLabel}</span>
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
                  {selectedObjective?.description && <p className="mt-2 text-xs leading-5 text-blue-800">{selectedObjective.description}</p>}
                </div>

                <div className="rounded-3xl border border-slate-200 bg-[#fbfaf5] p-4">
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
                        <div key={output.name} className={`grid gap-2 rounded-2xl border px-3 py-2 text-sm md:grid-cols-[1fr_5.5rem] md:items-center ${checked ? 'border-blue-200 bg-blue-50' : 'border-slate-200 bg-white'}`}>
                          <label className="flex items-center gap-3 font-semibold text-slate-800">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(event) => {
                                setObjectiveMode('custom')
                                setObjectiveWeights((current) => ({ ...current, [output.name]: event.target.checked ? (current[output.name] && current[output.name] !== '0' ? current[output.name] : defaultWeight) : '0' }))
                              }}
                              className="h-4 w-4 accent-[#526949]"
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
            </section>

            <section id="design-compare" className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/90 p-6 shadow-sm">
              <PanelHeader eyebrow="Compare and package" title="Prepare this candidate for lab review" description="Overlay a measured real-cell curve, save a comparison candidate, or export a complete design package." />
              <div className="mt-5 grid gap-4 lg:grid-cols-[1.2fr_0.8fr_0.8fr] lg:items-end">
                <label className="text-sm font-semibold text-slate-700">
                  Measured real-cell overlay
                  <select value={selectedRealCell} onChange={(event) => setSelectedRealCell(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                    <option value="">No real-cell overlay</option>
                    {realCellOptions.map((option, index) => (
                      <option key={`${asString(option.cell_id)}-${asNumber(option.operating_rh)}-${asString(option.split)}-${index}`} value={String(index)}>
                        {asString(option.cell_id)} · RH {asNumber(option.operating_rh)}% · {asString(option.split)} · {asNumber(option.row_count)} rows
                      </option>
                    ))}
                  </select>
                </label>
                <button type="button" onClick={() => prediction && setSavedComparison(prediction)} disabled={!prediction} className="rounded-full border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-700 disabled:opacity-50">
                  Save current as comparison
                </button>
                <button type="button" onClick={exportZip} disabled={exporting || !prediction} className="rounded-full bg-[#526949] px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">
                  {exporting ? 'Exporting...' : 'Export design package'}
                </button>
              </div>
            </section>
          </section>

          <section id="design-response-curve" className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <PanelHeader eyebrow="Predicted behavior" title={selectedPlotRecipe?.label || 'Predicted response plot'} description={selectedPlotRecipe?.description || 'Mirai selected a safe project-specific response plot from approved intake metadata.'} />
              <button
                type="button"
                onClick={exportResponseCurvePng}
                disabled={!curveRows.length || exportingCurvePng}
                className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-[#d8c99b] hover:bg-[#fffdf7] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {exportingCurvePng ? 'Exporting PNG…' : 'Export plot PNG'}
              </button>
            </div>
            {!curveRows.length && (
              <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
                No response curve is available yet. Click <strong>Generate result</strong> to evaluate the current inputs, or <strong>Find best starting design</strong> to let the model choose a candidate.
              </div>
            )}
            {curveRows.length > 0 && hasPendingInputChanges && (
              <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
                Inputs have changed since this plot was generated. Click <strong>Generate result</strong> to refresh the predicted KPIs and selected response plot.
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
            <p className="mt-3 rounded-2xl bg-[#fbfaf5] px-4 py-3 text-sm leading-6 text-slate-600">
              {curveKind === 'fuel_cell_polarization'
                ? 'Dashed curves are served-model predictions for the current design. Dotted curves are a saved candidate comparison. Solid measured curves come from the selected real experiment.'
                : 'Predicted traces come from the served challenger model. Observed traces, when selected, come from training predictions.csv rows for the chosen cell/RH/split and use *_true measured columns.'}
            </p>
          </section>

          {paretoResults && (
            <section id="design-tradeoffs" className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/90 p-6 shadow-sm">
              <PanelHeader
                eyebrow="Find alternatives"
                title="Tradeoff candidates"
                description="Optional starting points. Load one to update the sliders and evaluate it in the dynamic response curve above."
              />
              <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50 p-4 text-sm leading-6 text-blue-900">
                These are alternative starting designs from {paretoResults.n_candidates} virtual candidates. Load one, then judge it primarily in the response curve above. Lower raw values are better for minimized objectives.
              </div>
              <div className="mt-5 space-y-3">
                {paretoResults.candidates.map((candidate) => (
                  <article key={candidate.rank} className="rounded-2xl border border-slate-200 bg-[#fbfaf5] p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="font-semibold text-slate-950">{candidate.label}</h3>
                        <p className="mt-1 text-xs text-slate-500">Rank {candidate.rank} · score {formatNumber(candidate.score)}</p>
                      </div>
                      <button type="button" onClick={() => loadParetoCandidate(candidate)} className="rounded-full bg-slate-950 px-3 py-1.5 text-xs font-semibold text-white">
                        Load
                      </button>
                    </div>
                    <div className="mt-4 space-y-2 text-sm">
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
                        marker: { size: 11, color: '#526949', opacity: 0.85 },
                      },
                    ])}
                    layout={asPlotLayout({
                      ...plotLayoutBase,
                      height: 360,
                      xaxis: { title: { text: `${asString(asRecord(paretoResults.objectives[0]).label)} / ${asString(asRecord(paretoResults.objectives[0]).unit)}` }, zeroline: false },
                      yaxis: { title: { text: `${asString(asRecord(paretoResults.objectives[1]).label)} / ${asString(asRecord(paretoResults.objectives[1]).unit)}` }, zeroline: false },
                    })}
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
