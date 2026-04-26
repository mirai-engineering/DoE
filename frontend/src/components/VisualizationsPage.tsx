import type { ProjectSchema } from '../lib/api'
import type { RecommendationRun } from '../types/doe'
import { EmptyRecommendationsState } from './ui'
import { ParallelCoordinatesChart } from './ParallelCoordinatesChart'
import { ResponseSurfaceHeatmap } from './ResponseSurfaceHeatmap'

export function VisualizationsPage({
  schema,
  recommendationRun,
  inputValues,
  onGoHome,
}: {
  schema: ProjectSchema
  recommendationRun: RecommendationRun | null
  inputValues: Record<string, string>
  onGoHome: () => void
}) {
  if (!recommendationRun || recommendationRun.recommendations.length === 0) {
    return <EmptyRecommendationsState onGoHome={onGoHome} />
  }

  return (
    <div className="space-y-8">
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
