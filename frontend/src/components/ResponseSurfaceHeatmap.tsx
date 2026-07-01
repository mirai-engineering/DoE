import { FormEvent, useEffect, useState } from 'react'
import type { Data, Layout } from 'plotly.js'
import type { ExperimentInputs, ProjectSchema } from '../lib/api'
import { batchPredictExperiments } from '../lib/api'
import {
  clampInteger,
  defaultHeatmapAxes,
  formatNumber,
  linspace,
  outputLabel,
  scorePredictionRows,
  toNumberMap,
} from '../lib/doeUtils'
import { Plot } from '../lib/plotly'
import { transparentDarkPlotLayout } from '../lib/plotlyTheme'
import type { HeatmapData, RecommendationRun } from '../types/doe'
import { Alert, NumberField, PanelHeader, SelectField } from './ui'

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
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const nextDefaults = defaultHeatmapAxes(schema)
    setXAxis(nextDefaults.xAxis)
    setYAxis(nextDefaults.yAxis)
    setColorMetric('score')
    setHeatmapData(null)
    setError(null)
  }, [schema])

  async function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (xAxis === yAxis) {
      setError('Select different variables for the x and y axes.')
      return
    }

    const xInput = schema.inputs.find((input) => input.name === xAxis)
    const yInput = schema.inputs.find((input) => input.name === yAxis)
    if (!xInput || !yInput) {
      setError('Selected heatmap axes are not available in the project schema.')
      return
    }

    const axisSteps = clampInteger(gridSize, 24, 8, 40)
    const xValues = linspace(xInput.min, xInput.max, axisSteps)
    const yValues = linspace(yInput.min, yInput.max, axisSteps)
    const baseInputs = toNumberMap(inputValues)
    const rows: ExperimentInputs[] = []

    yValues.forEach((yValue) => {
      xValues.forEach((xValue) => {
        rows.push({
          ...baseInputs,
          [xInput.name]: xValue,
          [yInput.name]: yValue,
        })
      })
    })

    setLoading(true)
    setError(null)
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

  return (
    <section className="rounded-[2rem] border border-white/70 bg-white/90 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
      <PanelHeader
        eyebrow="Response surface"
        title="2D heatmap"
        description="Sweep two variables over their schema bounds while every other input stays fixed at the current Home / Console value."
      />

      <form className="mt-6 grid gap-4 lg:grid-cols-[1fr_1fr_1fr_0.7fr_auto]" onSubmit={handleGenerate}>
        <SelectField
          id="heatmap-x"
          label="X variable"
          value={xAxis}
          onChange={setXAxis}
          options={schema.inputs.map((input) => ({ value: input.name, label: input.label }))}
        />
        <SelectField
          id="heatmap-y"
          label="Y variable"
          value={yAxis}
          onChange={setYAxis}
          options={schema.inputs.map((input) => ({ value: input.name, label: input.label }))}
        />
        <SelectField
          id="heatmap-color"
          label="Color target"
          value={colorMetric}
          onChange={setColorMetric}
          options={[
            { value: 'score', label: 'Recommendation score' },
            ...schema.outputs.map((output) => ({
              value: output.name,
              label: `${output.label} (${output.direction})`,
            })),
          ]}
        />
        <NumberField
          id="heatmap-grid"
          label="Grid size"
          unit="per axis"
          min={8}
          max={40}
          value={gridSize}
          onChange={setGridSize}
        />
        <button
          type="submit"
          disabled={loading}
          className="self-end rounded-2xl bg-slate-950 px-5 py-4 text-sm font-semibold uppercase tracking-[0.16em] text-white shadow-lg shadow-slate-950/20 transition hover:-translate-y-0.5 hover:bg-[#263329] disabled:cursor-not-allowed disabled:brightness-75"
        >
          {loading ? 'Generating...' : 'Generate'}
        </button>
      </form>

      <div className="mt-5 grid gap-3 lg:grid-cols-[0.8fr_1.2fr]">
        <div className="rounded-2xl border border-slate-200 bg-[#0B1220] p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            Varied variables
          </p>
          <p className="mt-2 text-sm font-semibold text-slate-800">
            {variedX?.label ?? xAxis} vs {variedY?.label ?? yAxis}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-[#0B1220] p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            Fixed variables
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
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

      {heatmapData ? (
        <HeatmapPlot
          schema={schema}
          heatmapData={heatmapData}
          recommendationRun={recommendationRun}
          currentInputs={toNumberMap(inputValues)}
        />
      ) : (
        <div className="mt-6 rounded-3xl border border-dashed border-slate-300 bg-white/70 p-8 text-center text-sm text-slate-500">
          Generate a response surface to compare local tradeoffs around the current console inputs.
        </div>
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
      ? 'Recommendation score'
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
      name: 'Best recommendation',
      x: [bestCandidate.inputs[heatmapData.xAxis]],
      y: [bestCandidate.inputs[heatmapData.yAxis]],
      marker: {
        symbol: 'star',
        size: 16,
        color: '#F6F4EA',
        line: { color: '#050914', width: 2 },
      },
      hovertemplate: 'Best recommendation<br>%{x:.4g}, %{y:.4g}<extra></extra>',
    })
  }

  traces.push({
    type: 'scatter',
    mode: 'markers',
    name: 'Current input',
    x: [currentInputs[heatmapData.xAxis]],
    y: [currentInputs[heatmapData.yAxis]],
    marker: {
      symbol: 'circle-open',
      size: 14,
      color: '#ffffff',
      line: { color: '#5DA8FF', width: 3 },
    },
    hovertemplate: 'Current console input<br>%{x:.4g}, %{y:.4g}<extra></extra>',
  })

  const layout: Partial<Layout> = transparentDarkPlotLayout({
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
    <div className="mt-6 overflow-hidden rounded-3xl border border-slate-200 bg-[#0B1220] p-3">
      <Plot
        data={traces}
        layout={layout}
        config={{ displayModeBar: false, responsive: true }}
        useResizeHandler
        className="h-[540px] w-full"
      />
    </div>
  )
}
