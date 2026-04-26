import type { ProjectSchema } from '../lib/api'
import { formatNumber } from '../lib/doeUtils'
import type { RecommendationRun } from '../types/doe'
import { KpiComparisonChart } from './KpiComparisonChart'
import { RecommendationsTable } from './RecommendationsTable'
import { EmptyRecommendationsState, Metadata, PanelHeader } from './ui'

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
      <section className="rounded-[2rem] border border-white/70 bg-white/90 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
        <PanelHeader
          eyebrow="Ranked design points"
          title="Recommended experiments"
          description="Summary of the latest candidate search. The table is intentionally limited while charts use the larger returned candidate set."
        />

        <div className="mt-6 grid gap-3 md:grid-cols-5">
          <Metadata label="Project" value={recommendationRun.projectDisplayName} />
          <Metadata label="Sampled" value={formatNumber(recommendationRun.nCandidates)} />
          <Metadata label="Returned" value={formatNumber(recommendationRun.requestedTopK)} />
          <Metadata label="Table top k" value={formatNumber(recommendationRun.tableTopK)} />
          <Metadata label="Best score" value={formatNumber(bestScore)} />
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
