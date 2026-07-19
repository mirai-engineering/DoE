import type { ProjectSchema, Recommendation } from '../lib/api'
import { formatNumber } from '../lib/doeUtils'
import { candidateColors } from '../lib/batchSearchPresentation'
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
        title="Ranked virtual candidates"
        description="Candidate settings and model-predicted outcomes under the current objective."
      />
      <div className="mt-5 max-h-[42rem] overflow-auto" tabIndex={0} aria-label="Ranked virtual candidates table">
        <table className="min-w-max text-sm tabular-nums">
          <thead className="sticky top-0 z-20 bg-[#08111F] text-[#9FB0C8]">
            <tr className="border-b border-white/[0.06] text-xs"><th colSpan={2} className="sticky left-0 z-30 bg-[#08111F] px-4 py-2 text-left font-semibold text-[#BDEAFF]">Ranking</th><th colSpan={schema.inputs.length} className="px-4 py-2 text-center font-semibold">Design inputs</th><th colSpan={schema.outputs.length} className="border-l border-white/[0.10] px-4 py-2 text-center font-semibold">Predicted outputs</th></tr>
            <tr>
              <th className="sticky left-0 z-30 bg-[#08111F] py-3 pl-4 pr-4 text-left font-medium">Rank</th>
              <th className="sticky left-[4.5rem] z-30 bg-[#08111F] px-4 py-3 text-right font-medium">Score</th>
              {schema.inputs.map((input) => (
                <th key={input.name} className="px-4 py-3 text-right font-medium">
                  <span className="block max-w-[12rem] whitespace-normal">{input.label}</span><span className="mt-1 block text-[0.65rem] font-normal text-slate-500">{input.unit || '—'}</span>
                </th>
              ))}
              {schema.outputs.map((output) => (
                <th key={output.name} className="border-l border-white/[0.06] px-4 py-3 text-right font-medium">
                  <span className="block max-w-[12rem] whitespace-normal">{output.label}</span><span className="mt-1 block text-[0.65rem] font-normal text-slate-500">{output.unit || '—'}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.06]">
            {visibleRecommendations.map((candidate, index) => (
              <tr key={`${candidate.score}-${index}`} className={index === 0 ? 'bg-[#2F6BFF]/8 text-white' : 'text-slate-300 hover:bg-white/[0.025]'}>
                <td className={`sticky left-0 z-10 whitespace-nowrap py-2.5 pl-4 pr-4 font-semibold ${index === 0 ? 'bg-[#10203A]' : 'bg-[#08111F]'}`}>
                  <span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ backgroundColor: candidateColors[index % candidateColors.length] }} /><span className={index === 0 ? 'text-[#BDEAFF]' : ''}>Rank {index + 1}</span>
                </td>
                <td className={`sticky left-[4.5rem] z-10 whitespace-nowrap px-4 py-2.5 text-right font-semibold text-[#BDEAFF] ${index === 0 ? 'bg-[#10203A]' : 'bg-[#08111F]'}`}>
                  {formatNumber(candidate.score)}
                </td>
                {schema.inputs.map((input) => (
                  <td key={input.name} className="whitespace-nowrap px-4 py-2.5 text-right">
                    {formatNumber(candidate.inputs[input.name])}
                  </td>
                ))}
                {schema.outputs.map((output) => (
                  <td key={output.name} className="whitespace-nowrap border-l border-white/[0.04] px-4 py-2.5 text-right">
                    {formatNumber(candidate.predictions[output.name])}
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
