import type { ProjectSchema, Recommendation } from '../lib/api'
import { formatNumber } from '../lib/doeUtils'
import { PanelHeader } from './ui'

export function RecommendationsTable({
  schema,
  recommendations,
  limit,
}: {
  schema: ProjectSchema
  recommendations: Recommendation[]
  limit: number
}) {
  const visibleRecommendations = recommendations.slice(0, limit)

  return (
    <section className="rounded-[2rem] border border-white/70 bg-white/90 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
      <PanelHeader
        eyebrow="Best rows"
        title={`Top ${visibleRecommendations.length} recommended experiments`}
        description="Table rows stay focused on the strongest candidates; visualizations use the larger returned candidate set."
      />
      <div className="mt-6 overflow-x-auto rounded-3xl border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-950 text-white">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">Rank</th>
              <th className="px-4 py-3 text-left font-semibold">Score</th>
              {schema.inputs.map((input) => (
                <th key={input.name} className="px-4 py-3 text-left font-semibold">
                  {input.label}
                </th>
              ))}
              {schema.outputs.map((output) => (
                <th key={output.name} className="px-4 py-3 text-left font-semibold">
                  {output.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {visibleRecommendations.map((candidate, index) => (
              <tr key={`${candidate.score}-${index}`} className="hover:bg-[#f7f5ed]">
                <td className="px-4 py-3 font-semibold text-slate-950">{index + 1}</td>
                <td className="px-4 py-3 font-semibold text-[#526949]">
                  {formatNumber(candidate.score)}
                </td>
                {schema.inputs.map((input) => (
                  <td key={input.name} className="whitespace-nowrap px-4 py-3 text-slate-700">
                    {formatNumber(candidate.inputs[input.name])}
                    <span className="ml-1 text-slate-400">{input.unit}</span>
                  </td>
                ))}
                {schema.outputs.map((output) => (
                  <td key={output.name} className="whitespace-nowrap px-4 py-3 text-slate-700">
                    {formatNumber(candidate.predictions[output.name])}
                    <span className="ml-1 text-slate-400">{output.unit}</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
