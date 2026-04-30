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

type AxisKeyEntry = {
  code: string
  name: string
  unit?: string
  direction?: 'maximize' | 'minimize'
  group: 'inputs' | 'outputs' | 'score'
}

const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

function axisCode(index: number) {
  if (index < alphabet.length) return alphabet[index]
  const first = Math.floor(index / alphabet.length) - 1
  const second = index % alphabet.length
  return `${alphabet[first]}${alphabet[second]}`
}

function buildAxisKey(schema: ProjectSchema): AxisKeyEntry[] {
  const entries: AxisKeyEntry[] = []

  schema.inputs.forEach((input) => {
    entries.push({
      code: axisCode(entries.length),
      name: input.label,
      unit: input.unit,
      group: 'inputs',
    })
  })

  schema.outputs.forEach((output) => {
    entries.push({
      code: axisCode(entries.length),
      name: output.label,
      unit: output.unit,
      direction: output.direction,
      group: 'outputs',
    })
  })

  entries.push({
    code: axisCode(entries.length),
    name: 'Recommendation score',
    group: 'score',
  })

  return entries
}

function buildDimensions(
  schema: ProjectSchema,
  recommendations: Recommendation[],
  scores: number[],
  scoreMin: number,
  scoreMax: number,
  axisKey: AxisKeyEntry[],
): ParallelDimension[] {
  const dims: ParallelDimension[] = schema.inputs.map((input, index) => ({
    label: axisKey[index].code,
    values: recommendations.map((rec) => rec.inputs[input.name] ?? 0),
    range: [input.min, input.max] as [number, number],
    tickformat: input.unit === '%' ? '.0f' : '.2f',
  }))

  schema.outputs.forEach((output, outputIndex) => {
    const values = recommendations.map((rec) => rec.predictions[output.name] ?? 0)
    dims.push({
      label: axisKey[schema.inputs.length + outputIndex].code,
      values,
      range: safeRange(values, [0, 1]) as [number, number],
      tickformat: output.unit === '%' || output.unit === '-' ? '.0f' : '.2f',
    })
  })

  dims.push({
    label: axisKey[axisKey.length - 1].code,
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
  const axisKey = buildAxisKey(schema)
  const dimensions = buildDimensions(schema, recommendations, scores, scoreMin, scoreMax, axisKey)

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
    margin: { l: 60, r: 110, t: 36, b: 50 },
    font: { family: 'Aptos, Avenir Next, sans-serif', color: '#0f172a', size: 12 },
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
        Inputs are shown first, predicted outputs second, and score last. Axis codes keep
        the plot readable while the key maps each code to its variable and unit.
      </p>
      <AxisKey entries={axisKey} />
      <div className="mt-6 overflow-hidden rounded-3xl border border-slate-200 bg-[#fbfaf5] p-3">
        <Plot
          data={[trace]}
          layout={layout}
          config={{ displayModeBar: false, responsive: true }}
          useResizeHandler
          className="h-[680px] w-full"
        />
      </div>
    </section>
  )
}

function AxisKey({ entries }: { entries: AxisKeyEntry[] }) {
  const groups: Array<{ id: AxisKeyEntry['group']; label: string }> = [
    { id: 'inputs', label: 'Inputs' },
    { id: 'outputs', label: 'Predicted outputs' },
    { id: 'score', label: 'Score' },
  ]

  return (
    <div className="mt-6 rounded-3xl border border-slate-200 bg-[#fbfaf5] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">
          Axis key
        </h3>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500">
          {entries.length} plotted dimensions
        </span>
      </div>

      <div className="mt-4 grid gap-4">
        {groups.map((group) => {
          const groupEntries = entries.filter((entry) => entry.group === group.id)
          if (groupEntries.length === 0) return null

          return (
            <div key={group.id}>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#60745c]">
                {group.label}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {groupEntries.map((entry) => (
                  <AxisKeyPill key={entry.code} entry={entry} />
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function AxisKeyPill({ entry }: { entry: AxisKeyEntry }) {
  const direction = entry.direction === 'maximize' ? '↑' : entry.direction === 'minimize' ? '↓' : ''

  return (
    <div className="inline-flex max-w-full items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-950 text-xs font-bold text-white">
        {entry.code}
      </span>
      <span className="min-w-0 truncate font-semibold text-slate-800">
        {entry.name}
        {direction && <span className="ml-1 text-[#526949]">{direction}</span>}
      </span>
      {entry.unit && entry.unit !== '-' && (
        <span className="shrink-0 text-xs font-medium text-slate-400">· {entry.unit}</span>
      )}
    </div>
  )
}
