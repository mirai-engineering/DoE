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
    <section className="border-t border-white/[0.07] pt-6">
      <PanelHeader
        eyebrow="Candidate table"
        title={`Top ${visibleRecommendations.length} recommended experiments`}
        description="Ranked candidate settings and predicted outputs."
      />
      <div className="mt-5 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="border-b border-white/[0.08] text-[#9FB0C8]">
            <tr>
              <th className="py-3 pr-4 text-left font-medium">Rank</th>
              <th className="px-4 py-3 text-right font-medium">Score</th>
              {schema.inputs.map((input) => (
                <th key={input.name} className="px-4 py-3 text-right font-medium">
                  {input.label}
                </th>
              ))}
              {schema.outputs.map((output) => (
                <th key={output.name} className="px-4 py-3 text-right font-medium">
                  {output.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.06]">
            {visibleRecommendations.map((candidate, index) => (
              <tr key={`${candidate.score}-${index}`} className={index === 0 ? 'bg-[#2F6BFF]/8 text-white' : 'text-slate-300 hover:bg-white/[0.025]'}>
                <td className="whitespace-nowrap py-3 pr-4 font-semibold">
                  <span className={index === 0 ? 'border-l-2 border-[#74C7F5] pl-3 text-[#BDEAFF]' : 'pl-3'}>{index + 1}</span>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right font-semibold text-[#74C7F5]">
                  {formatNumber(candidate.score)}
                </td>
                {schema.inputs.map((input) => (
                  <td key={input.name} className="whitespace-nowrap px-4 py-3 text-right">
                    {formatNumber(candidate.inputs[input.name])}
                    <span className="ml-1 text-slate-500">{input.unit}</span>
                  </td>
                ))}
                {schema.outputs.map((output) => (
                  <td key={output.name} className="whitespace-nowrap px-4 py-3 text-right">
                    {formatNumber(candidate.predictions[output.name])}
                    <span className="ml-1 text-slate-500">{output.unit}</span>
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
