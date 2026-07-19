import type { Data, Layout } from 'plotly.js'
import type { ProjectSchema, Recommendation } from '../lib/api'
import { formatNumber, normalizeForComparison } from '../lib/doeUtils'
import { candidateColors } from '../lib/batchSearchPresentation'
import { Plot } from '../lib/plotly'
import { createMiraiPlotlyTheme, plotConfig } from '../lib/plotlyTheme'
import { PanelHeader } from './ui'

export function KpiComparisonChart({
  schema,
  recommendations,
  limit = 5,
}: {
  schema: ProjectSchema
  recommendations: Recommendation[]
  limit?: number
}) {
  const topRecommendations = recommendations.slice(0, limit)
  const labels = schema.outputs.map((output) => `${output.label}<br>${output.direction}`)
  const traces: Data[] = topRecommendations.map((candidate, index) => {
    const rawValues = schema.outputs.map((output) => candidate.predictions[output.name] ?? 0)
    const normalizedByOutput = schema.outputs.map((output) => {
      const values = topRecommendations.map((item) => item.predictions[output.name] ?? 0)
      return normalizeForComparison(values, output.direction)[index]
    })

    return {
      type: 'bar',
      name: `Rank ${index + 1}`,
      x: labels,
      y: normalizedByOutput,
      customdata: rawValues.map((value, outputIndex) => {
        const output = schema.outputs[outputIndex]
        return `${formatNumber(value)} ${output.unit}`
      }),
      hovertemplate:
        '<b>%{x}</b><br>Optimization-normalized value: %{y:.3f}<br>Raw: %{customdata}<extra>%{fullData.name}</extra>',
      marker: {
        color: candidateColors[index % candidateColors.length],
        line: index === 0 ? { color: '#E8EEF8', width: 1.5 } : undefined,
      },
    }
  })

  const layout: Partial<Layout> = createMiraiPlotlyTheme({
    autosize: true,
    barmode: 'group',
    margin: { l: 48, r: 24, t: 24, b: 82 },
    yaxis: { title: { text: 'Normalized KPI value, higher is better' }, range: [0, 1.05] },
    xaxis: { tickfont: { size: 11 } },
    legend: { orientation: 'h', y: 1.15 },
  })

  return (
    <section className="border-t border-white/[0.07] pt-6">
      <PanelHeader
        eyebrow="Candidate comparison"
        title="Compare the leading candidates"
        description="Normalized KPI values show the tradeoffs behind the current ranking. For minimized outputs, the display direction is reversed so higher remains better."
      />
      <div className="mt-5 overflow-hidden border-y border-white/[0.07] py-2">
        <Plot
          data={traces}
          layout={layout}
          config={{ ...plotConfig, displayModeBar: false }}
          useResizeHandler
          className="h-[420px] w-full"
        />
      </div>
    </section>
  )
}
