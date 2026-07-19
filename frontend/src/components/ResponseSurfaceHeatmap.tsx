import { FormEvent, useEffect, useState } from 'react'
import type { Data, Layout } from 'plotly.js'
import type { ExperimentInputs, ProjectSchema } from '../lib/api'
import { batchPredictExperiments } from '../lib/api'
import {
  defaultHeatmapAxes,
  formatNumber,
  outputLabel,
  scorePredictionRows,
  toNumberMap,
} from '../lib/doeUtils'
import { buildHeatmapRequestRows, heatmapRequestFingerprint } from '../lib/batchSearchPresentation'
import { Plot } from '../lib/plotly'
import { createMiraiPlotlyTheme, plotConfig } from '../lib/plotlyTheme'
import type { HeatmapData, RecommendationRun } from '../types/doe'
import { Alert, EmptyState, NumberField, PanelHeader, SelectField, StatusBadge } from './ui'

export function ResponseSurfaceHeatmap({
  schema,
  recommendationRun,
  inputValues,
}: {
  schema: ProjectSchema
  recommendationRun: RecommendationRun
  inputValues: Record<string, string>
}) {
  const defaults = defaultHeatmapAxes(schema)
  const [xAxis, setXAxis] = useState(defaults.xAxis)
  const [yAxis, setYAxis] = useState(defaults.yAxis)
  const [colorMetric, setColorMetric] = useState('score')
  const [gridSize, setGridSize] = useState('24')
  const [heatmapData, setHeatmapData] = useState<HeatmapData | null>(null)
  const [generatedRequestKey, setGeneratedRequestKey] = useState('')
  const [heatmapWarnings, setHeatmapWarnings] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const nextDefaults = defaultHeatmapAxes(schema)
    setXAxis(nextDefaults.xAxis)
    setYAxis(nextDefaults.yAxis)
    setColorMetric('score')
    setHeatmapData(null)
    setGeneratedRequestKey('')
    setHeatmapWarnings([])
    setError(null)
  }, [schema])

  async function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (xAxis === yAxis) {
      setError('Select different variables for the x and y axes.')
      return
    }

    const requestGrid = buildHeatmapRequestRows(schema, xAxis, yAxis, gridSize, inputValues)
    if (!requestGrid) {
      setError('Selected heatmap axes are not available in the project schema.')
      return
    }
    const { xInput, yInput, xValues, yValues, rows } = requestGrid

    setLoading(true)
    setError(null)
    setHeatmapWarnings([])
    try {
      const response = await batchPredictExperiments(schema.project_id, rows)
      const values =
        colorMetric === 'score'
          ? scorePredictionRows(schema, response.predictions, recommendationRun.objectiveWeights)
          : response.predictions.map((prediction) => prediction[colorMetric] ?? 0)

      const zValues = yValues.map((_, rowIndex) =>
        xValues.map((_, columnIndex) => values[rowIndex * xValues.length + columnIndex]),
      )

      setHeatmapData({
        xAxis: xInput.name,
        yAxis: yInput.name,
        colorMetric,
        xValues,
        yValues,
        zValues,
        predictions: response.predictions,
      })
      setGeneratedRequestKey(heatmapRequestFingerprint({ xAxis, yAxis, colorMetric, gridSize, inputValues, objectiveWeights: recommendationRun.objectiveWeights }))
      setHeatmapWarnings(response.warnings)
    } catch (heatmapError) {
      setHeatmapData(null)
      setError(heatmapError instanceof Error ? heatmapError.message : 'Unable to generate heatmap')
    } finally {
      setLoading(false)
    }
  }

  const fixedInputs = schema.inputs.filter((input) => input.name !== xAxis && input.name !== yAxis)
  const variedX = schema.inputs.find((input) => input.name === xAxis)
  const variedY = schema.inputs.find((input) => input.name === yAxis)
  const currentRequestKey = heatmapRequestFingerprint({ xAxis, yAxis, colorMetric, gridSize, inputValues, objectiveWeights: recommendationRun.objectiveWeights })
  const heatmapStale = Boolean(heatmapData && generatedRequestKey !== currentRequestKey)

  return (
    <section className="border-t border-white/[0.07] pt-6">
      <PanelHeader
        eyebrow="Response surface"
        title="Explore a two-variable response surface"
        description="Vary two inputs across their schema bounds while keeping all other conditions fixed at the current reference-design values."
      />

      <form className="mt-6 grid gap-4 lg:grid-cols-[1fr_1fr_1fr_0.7fr_auto]" onSubmit={handleGenerate}>
        <SelectField
          id="heatmap-x"
          label="X variable"
          value={xAxis}
          onChange={setXAxis}
          options={schema.inputs.map((input) => ({ value: input.name, label: input.label }))}
          dark
        />
        <SelectField
          id="heatmap-y"
          label="Y variable"
          value={yAxis}
          onChange={setYAxis}
          options={schema.inputs.map((input) => ({ value: input.name, label: input.label }))}
          dark
        />
        <SelectField
          id="heatmap-color"
          label="Color target"
          value={colorMetric}
          onChange={setColorMetric}
          options={[
            { value: 'score', label: 'Ranking score' },
            ...schema.outputs.map((output) => ({
              value: output.name,
              label: `${output.label} (${output.direction})`,
            })),
          ]}
          dark
        />
        <NumberField
          id="heatmap-grid"
          label="Grid size"
          unit="per axis"
          min={8}
          max={40}
          value={gridSize}
          onChange={setGridSize}
          dark
        />
        <button
          type="submit"
          disabled={loading}
          className="self-end rounded-md bg-[#2F6BFF] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#245CF0] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Generating surface…' : 'Generate heatmap'}
        </button>
      </form>

      <div className="mt-5 grid gap-3 lg:grid-cols-[0.8fr_1.2fr]">
        <div className="border-t border-white/[0.07] pt-4">
          <p className="text-xs font-semibold tracking-normal text-slate-400">
            Varied variables
          </p>
          <p className="mt-2 text-sm font-semibold text-slate-200">
            {variedX?.label ?? xAxis}{variedX?.unit ? ` (${variedX.unit})` : ''} vs {variedY?.label ?? yAxis}{variedY?.unit ? ` (${variedY.unit})` : ''}
          </p>
        </div>
        <div className="border-t border-white/[0.07] pt-4">
          <p className="text-xs font-semibold tracking-normal text-slate-400">
            Fixed variables
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-300">
            {fixedInputs
              .map((input) => `${input.label}: ${formatNumber(Number(inputValues[input.name]))} ${input.unit}`)
              .join(' | ')}
          </p>
        </div>
      </div>

      {error && (
        <div className="mt-5">
          <Alert tone="error" title="Heatmap failed" messages={[error]} />
        </div>
      )}
      {heatmapWarnings.length > 0 && <div className="mt-5"><Alert tone="warning" title="Response-surface warnings" messages={heatmapWarnings} /></div>}
      {heatmapStale && <div className="mt-5"><StatusBadge tone="warning">Setup changed · regenerate the heatmap</StatusBadge></div>}

      {heatmapData ? (
        <HeatmapPlot
          schema={schema}
          heatmapData={heatmapData}
          recommendationRun={recommendationRun}
          currentInputs={toNumberMap(inputValues)}
        />
      ) : (
        <div className="mt-6 border-y border-white/[0.08]"><EmptyState title="Generate a response surface" description="Choose two inputs and a predicted target to inspect the model response." /></div>
      )}
    </section>
  )
}

function HeatmapPlot({
  schema,
  heatmapData,
  recommendationRun,
  currentInputs,
}: {
  schema: ProjectSchema
  heatmapData: HeatmapData
  recommendationRun: RecommendationRun
  currentInputs: ExperimentInputs
}) {
  const xInput = schema.inputs.find((input) => input.name === heatmapData.xAxis)
  const yInput = schema.inputs.find((input) => input.name === heatmapData.yAxis)
  const metricLabel =
    heatmapData.colorMetric === 'score'
      ? 'Ranking score'
      : outputLabel(schema, heatmapData.colorMetric)
  const bestCandidate = recommendationRun.recommendations[0]

  const traces: Data[] = [
    {
      type: 'heatmap',
      x: heatmapData.xValues,
      y: heatmapData.yValues,
      z: heatmapData.zValues,
      colorscale: [
        [0, '#050914'],
        [0.45, '#2F6BFF'],
        [0.75, '#BDEAFF'],
        [1, '#F6F4EA'],
      ],
      colorbar: { title: { text: metricLabel } },
      hovertemplate: `${xInput?.label ?? 'X'}: %{x:.4g}<br>${yInput?.label ?? 'Y'}: %{y:.4g}<br>${metricLabel}: %{z:.4g}<extra></extra>`,
    },
  ]

  if (bestCandidate) {
    traces.push({
      type: 'scatter',
      mode: 'markers',
      name: 'Rank 1 virtual candidate',
      x: [bestCandidate.inputs[heatmapData.xAxis]],
      y: [bestCandidate.inputs[heatmapData.yAxis]],
      marker: {
        symbol: 'star',
        size: 16,
        color: '#F6F4EA',
        line: { color: '#050914', width: 2 },
      },
      hovertemplate: 'Rank 1 virtual candidate<br>%{x:.4g}, %{y:.4g}<extra></extra>',
    })
  }

  traces.push({
    type: 'scatter',
    mode: 'markers',
    name: 'Reference design',
    x: [currentInputs[heatmapData.xAxis]],
    y: [currentInputs[heatmapData.yAxis]],
    marker: {
      symbol: 'circle-open',
      size: 14,
      color: '#ffffff',
      line: { color: '#5DA8FF', width: 3 },
    },
    hovertemplate: 'Reference design<br>%{x:.4g}, %{y:.4g}<extra></extra>',
  })

  const layout: Partial<Layout> = createMiraiPlotlyTheme({
    autosize: true,
    margin: { l: 72, r: 72, t: 24, b: 64 },
    xaxis: {
      title: { text: `${xInput?.label ?? heatmapData.xAxis} ${xInput?.unit ? `(${xInput.unit})` : ''}` },
    },
    yaxis: {
      title: { text: `${yInput?.label ?? heatmapData.yAxis} ${yInput?.unit ? `(${yInput.unit})` : ''}` },
    },
    legend: { orientation: 'h', y: 1.12 },
  })

  return (
    <div className="mt-6 overflow-hidden border-y border-white/[0.08] py-3">
      <Plot
        data={traces}
        layout={layout}
        config={{ ...plotConfig, displayModeBar: false }}
        useResizeHandler
        className="h-[540px] w-full"
      />
    </div>
  )
}
