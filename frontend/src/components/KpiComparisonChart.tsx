import type { Data, Layout } from 'plotly.js'
import type { ProjectSchema, Recommendation } from '../lib/api'
import { formatNumber, normalizeForComparison } from '../lib/doeUtils'
import { Plot } from '../lib/plotly'
import { transparentDarkPlotLayout } from '../lib/plotlyTheme'
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
        color: ['#050914', '#2F6BFF', '#74C7F5', '#BDEAFF', '#5DA8FF'][index % 5],
      },
    }
  })

  const layout: Partial<Layout> = transparentDarkPlotLayout({
    autosize: true,
    barmode: 'group',
    margin: { l: 48, r: 24, t: 24, b: 82 },
    yaxis: { title: { text: 'Normalized KPI value, higher is better' }, range: [0, 1.05] },
    xaxis: { tickfont: { size: 11 } },
    legend: { orientation: 'h', y: 1.15 },
  })

  return (
    <section className="rounded-[2rem] border border-white/70 bg-white/90 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
      <PanelHeader
        eyebrow="KPI tradeoffs"
        title="Top candidate comparison"
        description="Bars are normalized per KPI. For minimize metrics, the normalization is reversed so taller remains better."
      />
      <div className="mt-6 overflow-hidden rounded-3xl border border-slate-200 bg-[#0B1220] p-3">
        <Plot
          data={traces}
          layout={layout}
          config={{ displayModeBar: false, responsive: true }}
          useResizeHandler
          className="h-[420px] w-full"
        />
      </div>
    </section>
  )
}
