import type { ProjectSchema } from '../lib/api'
import { formatNumber } from '../lib/doeUtils'
import type { RecommendationRun } from '../types/doe'
import { KpiComparisonChart } from './KpiComparisonChart'
import { RecommendationsTable } from './RecommendationsTable'
import { EmptyRecommendationsState, PanelHeader } from './ui'

export function RecommendationsPage({
  schema,
  recommendationRun,
  onGoHome,
}: {
  schema: ProjectSchema
  recommendationRun: RecommendationRun | null
  onGoHome: () => void
}) {
  if (!recommendationRun || recommendationRun.recommendations.length === 0) {
    return <EmptyRecommendationsState onGoHome={onGoHome} />
  }

  const bestScore = recommendationRun.recommendations[0]?.score ?? 0

  return (
    <div className="space-y-8">
      <section className="border-b border-white/[0.07] pb-5">
        <PanelHeader
          eyebrow="Recommended experiments"
          title="Ranked design points"
          description="Latest candidate search with compact evidence for the top design points."
        />

        <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-[#9FB0C8]">
          <span className="text-slate-200">{recommendationRun.projectDisplayName}</span>
          <span className="text-slate-600">·</span>
          <span>{formatNumber(recommendationRun.nCandidates)} sampled</span>
          <span className="text-slate-600">·</span>
          <span>{formatNumber(recommendationRun.requestedTopK)} returned</span>
          <span className="text-slate-600">·</span>
          <span>Top {formatNumber(recommendationRun.tableTopK)} in table</span>
          <span className="text-slate-600">·</span>
          <span className="text-[#BDEAFF]">Best score {formatNumber(bestScore)}</span>
        </div>
      </section>

      <KpiComparisonChart
        schema={schema}
        recommendations={recommendationRun.recommendations}
        limit={recommendationRun.tableTopK}
      />

      <RecommendationsTable
        schema={schema}
        recommendations={recommendationRun.recommendations}
        limit={recommendationRun.tableTopK}
      />
    </div>
  )
}
