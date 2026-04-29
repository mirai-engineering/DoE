import type { Data, Layout } from 'plotly.js'
import type { ProjectSchema, Recommendation } from '../lib/api'
import { formatNumber, safeRange } from '../lib/doeUtils'
import { Plot } from '../lib/plotly'
import { PanelHeader } from './ui'

type ParallelDimension = {
  label: string
  values: number[]
  range: [number, number]
  tickformat?: string
}

function buildDimensions(
  schema: ProjectSchema,
  recommendations: Recommendation[],
  scores: number[],
  scoreMin: number,
  scoreMax: number,
): ParallelDimension[] {
  const dims: ParallelDimension[] = schema.inputs.map((input) => ({
    label: input.label,
    values: recommendations.map((rec) => rec.inputs[input.name] ?? 0),
    range: [input.min, input.max] as [number, number],
    tickformat: input.unit === '%' ? '.0f' : '.2f',
  }))

  schema.outputs.forEach((output) => {
    const values = recommendations.map((rec) => rec.predictions[output.name] ?? 0)
    dims.push({
      label: `${output.label} ${output.direction === 'maximize' ? '↑' : '↓'}`,
      values,
      range: safeRange(values, [0, 1]) as [number, number],
      tickformat: output.unit === '%' || output.unit === '-' ? '.0f' : '.2f',
    })
  })

  dims.push({
    label: 'Score',
    values: scores,
    range: [scoreMin, scoreMax] as [number, number],
    tickformat: '.2f',
  })

  return dims
}

export function ParallelCoordinatesChart({
  schema,
  recommendations,
  highlightLimit = 5,
}: {
  schema: ProjectSchema
  recommendations: Recommendation[]
  highlightLimit?: number
}) {
  const scores = recommendations.map((c) => c.score)
  const [scoreMin, scoreMax] = safeRange(scores, [0, 1])
  const dimensions = buildDimensions(schema, recommendations, scores, scoreMin, scoreMax)

  const trace: Data = {
    type: 'parcoords',
    line: {
      color: scores,
      cmin: scoreMin,
      cmax: scoreMax,
      colorscale: [
        [0, '#d7ded1'],
        [0.35, '#8b9b72'],
        [0.7, '#d8c49a'],
        [1, '#17211d'],
      ],
      showscale: true,
      colorbar: { title: { text: 'Score' } },
    },
    dimensions,
  }

  const layout: Partial<Layout> = {
    autosize: true,
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    margin: { l: 120, r: 120, t: 40, b: 50 },
    font: { family: 'Aptos, Avenir Next, sans-serif', color: '#0f172a', size: 9 },
  }

  const topCandidates = recommendations.slice(0, highlightLimit)

  return (
    <section className="rounded-[2rem] border border-white/70 bg-white/90 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
      <PanelHeader
        eyebrow="Design space map"
        title="Parallel coordinates"
        description="Each line is a simulated experiment. Higher-score lines represent better tradeoffs under the current objective weights."
      />
      <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-600">
        <span className="rounded-full bg-slate-950 px-3 py-1 font-semibold text-white">
          {recommendations.length} ranked candidates
        </span>
        {topCandidates.map((candidate, index) => (
          <span
            key={`${candidate.score}-${index}`}
            className="rounded-full border border-[#d8c49a]/60 bg-[#fff7df] px-3 py-1 font-semibold text-slate-800"
          >
            Top {index + 1}: {formatNumber(candidate.score)}
          </span>
        ))}
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        Inputs are shown first, predicted outputs second, and score last. Hover over any
        line to see exact values with units.
      </p>
      <div className="mt-6 overflow-hidden rounded-3xl border border-slate-200 bg-[#fbfaf5] p-3">
        <Plot
          data={[trace]}
          layout={layout}
          config={{ displayModeBar: false, responsive: true }}
          useResizeHandler
          className="h-[620px] w-full"
        />
      </div>
    </section>
  )
}