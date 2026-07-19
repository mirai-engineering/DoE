import type { ProjectSchema } from '../lib/api'
import { objectiveRows, recommendationRunSummary } from '../lib/batchSearchPresentation'
import { formatNumber } from '../lib/doeUtils'
import type { RecommendationRun } from '../types/doe'
import { KpiComparisonChart } from './KpiComparisonChart'
import { RecommendationsTable } from './RecommendationsTable'
import { Alert, EmptyState, PanelHeader, TechnicalDetails } from './ui'

export function RecommendationsPage({ schema, recommendationRun, warnings, configurationStale, onGoHome }: { schema: ProjectSchema; recommendationRun: RecommendationRun | null; warnings: string[]; configurationStale: boolean; onGoHome: () => void }) {
  if (!recommendationRun || recommendationRun.recommendations.length === 0) {
    return <section className="border-y border-white/[0.08]"><EmptyState title="No ranked candidates yet" description="Configure the objective and search space, then generate a shortlist." /><div className="pb-8 text-center"><button type="button" onClick={onGoHome} className="rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white">Configure Batch Search</button></div></section>
  }

  const summary = recommendationRunSummary(recommendationRun)
  const activeObjectives = objectiveRows(schema, recommendationRun.objectiveWeights).filter((row) => row.included)
  const fixedNames = schema.inputs.filter((input) => recommendationRun.fixedInputs[input.name] !== undefined).map((input) => input.label)

  return (
    <div className="space-y-8">
      <section className="border-b border-white/[0.08] pb-6">
        <PanelHeader eyebrow="Model-ranked candidates" title="Review the ranked shortlist" description="Compare the strongest virtual candidates under the selected objective before deciding which designs deserve engineering review." />
        <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <SummaryMetric label="Virtual candidates scored" value={formatNumber(summary.sampled)} />
          <SummaryMetric label="Ranked candidates returned" value={formatNumber(summary.returned)} />
          <SummaryMetric label="Shortlist shown" value={formatNumber(summary.shortlist)} />
          <SummaryMetric label="Best recommendation score" value={formatNumber(summary.bestScore)} accent />
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-3"><SummaryLine label="Project" value={recommendationRun.projectDisplayName} /><SummaryLine label="Ranking objective" value={activeObjectives.length ? activeObjectives.map((row) => `${row.output.label} ${row.value > 0 ? '+' : ''}${row.value}`).join(' · ') : 'All output weights are zero'} /><SummaryLine label="Fixed conditions" value={fixedNames.length ? fixedNames.join(' · ') : 'None'} /></div>
        <p className="mt-5 text-sm leading-6 text-amber-100">Scores rank model predictions under the current objective; they are not measured performance.</p>
        {warnings.length > 0 && <div className="mt-4"><Alert tone="warning" title="Batch search warnings" messages={warnings} /></div>}
        {configurationStale && <div className="mt-4"><Alert tone="warning" title="Results use an earlier configuration" messages={["Return to Configure and generate a new shortlist to apply the latest objective, fixed conditions, or search-size settings."]} /></div>}
      </section>

      <KpiComparisonChart schema={schema} recommendations={recommendationRun.recommendations} limit={recommendationRun.tableTopK} />
      <RecommendationsTable schema={schema} recommendations={recommendationRun.recommendations} limit={recommendationRun.tableTopK} />

      <TechnicalDetails title="How ranking works">
        <p>Mirai samples {formatNumber(recommendationRun.nCandidates)} virtual candidates within the schema bounds, holds the selected fixed inputs constant, predicts every output with served model {recommendationRun.modelVersion ?? '—'}, normalizes outputs within this search, applies the signed objective weights, and sorts the resulting relative scores from highest to lowest.</p>
        <p>For comparison charts, minimized outputs are visually reversed so higher normalized values remain better. Raw predictions and recommendation scores are unchanged.</p>
        <p>Requested API retention: {formatNumber(recommendationRun.requestedTopK)} candidates · visualization setting: {formatNumber(recommendationRun.visualizationTopK)}.</p>
      </TechnicalDetails>
    </div>
  )
}

function SummaryMetric({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return <div className="border-l border-white/[0.10] pl-3"><div className="text-xs text-[#9FB0C8]">{label}</div><div className={`mt-1 text-xl font-semibold tabular-nums ${accent ? 'text-[#BDEAFF]' : 'text-white'}`}>{value}</div></div>
}

function SummaryLine({ label, value }: { label: string; value: string }) {
  return <div className="border-t border-white/[0.07] pt-3"><div className="text-xs text-slate-500">{label}</div><div className="mt-1 text-sm font-medium text-slate-200">{value}</div></div>
}
