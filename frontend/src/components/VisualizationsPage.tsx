import type { ProjectSchema } from '../lib/api'
import type { RecommendationRun } from '../types/doe'
import { ParallelCoordinatesChart } from './ParallelCoordinatesChart'
import { ResponseSurfaceHeatmap } from './ResponseSurfaceHeatmap'
import { Alert, EmptyState } from './ui'

export function VisualizationsPage({
  schema,
  recommendationRun,
  warnings,
  configurationStale,
  inputValues,
  onGoHome,
}: {
  schema: ProjectSchema
  recommendationRun: RecommendationRun | null
  warnings: string[]
  configurationStale: boolean
  inputValues: Record<string, string>
  onGoHome: () => void
}) {
  if (!recommendationRun || recommendationRun.recommendations.length === 0) {
    return <section className="border-y border-white/[0.08]"><EmptyState title="No ranked candidates yet" description="Configure the objective and search space, then generate a shortlist before opening tradeoff visuals." /><div className="pb-8 text-center"><button type="button" onClick={onGoHome} className="rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white">Configure Batch Search</button></div></section>
  }

  return (
    <div className="space-y-8">
      {warnings.length > 0 && <Alert tone="warning" title="Batch search warnings" messages={warnings} />}
      {configurationStale && <Alert tone="warning" title="Visuals use an earlier configuration" messages={["Generate a new shortlist to apply the latest Batch Search settings."]} />}
      <ParallelCoordinatesChart
        schema={schema}
        recommendations={recommendationRun.recommendations}
        highlightLimit={recommendationRun.tableTopK}
      />

      <ResponseSurfaceHeatmap
        schema={schema}
        recommendationRun={recommendationRun}
        inputValues={inputValues}
      />
    </div>
  )
}
