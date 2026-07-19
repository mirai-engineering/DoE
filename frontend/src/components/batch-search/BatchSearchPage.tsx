import { useEffect, useState, type Dispatch, type FormEvent, type SetStateAction } from 'react'
import type { DesignStudioState, PredictionMap, ProjectSchema } from '../../lib/api'
import { getDesignStudioState } from '../../lib/api'
import { buildBatchSearchRequest, isRecommendationRunStale, type BatchSearchView } from '../../lib/batchSearchPresentation'
import type { FixedInputConfig, RecommendationRun } from '../../types/doe'
import { PredictPanel } from '../PredictPanel'
import { RecommendPanel } from '../RecommendPanel'
import { RecommendationsPage } from '../RecommendationsPage'
import { VisualizationsPage } from '../VisualizationsPage'
import { Alert, DisclosurePanel, PanelHeader, StatusBadge, TechnicalDetails } from '../ui'
import { BatchSearchPanel, BatchSearchTabs } from './BatchSearchTabs'

export function BatchSearchPage({ schema, activeView, onViewChange, inputValues, setInputValues, prediction, predictWarnings, predictLoading, predictError, onPredict, objectiveWeights, setObjectiveWeights, fixedInputs, setFixedInputs, nCandidates, setNCandidates, tableTopK, setTableTopK, visualizationTopK, setVisualizationTopK, recommendLoading, recommendError, recommendWarnings, recommendationRun, onRecommend }: {
  schema: ProjectSchema
  activeView: BatchSearchView
  onViewChange: (view: BatchSearchView) => void
  inputValues: Record<string, string>
  setInputValues: Dispatch<SetStateAction<Record<string, string>>>
  prediction: PredictionMap | null
  predictWarnings: string[]
  predictLoading: boolean
  predictError: string | null
  onPredict: (event: FormEvent<HTMLFormElement>) => void
  objectiveWeights: Record<string, string>
  setObjectiveWeights: Dispatch<SetStateAction<Record<string, string>>>
  fixedInputs: FixedInputConfig
  setFixedInputs: Dispatch<SetStateAction<FixedInputConfig>>
  nCandidates: string
  setNCandidates: (value: string) => void
  tableTopK: string
  setTableTopK: (value: string) => void
  visualizationTopK: string
  setVisualizationTopK: (value: string) => void
  recommendLoading: boolean
  recommendError: string | null
  recommendWarnings: string[]
  recommendationRun: RecommendationRun | null
  onRecommend: (event: FormEvent<HTMLFormElement>) => void
}) {
  const [modelState, setModelState] = useState<DesignStudioState | null>(null)
  const [modelContextLoading, setModelContextLoading] = useState(true)
  const [modelContextError, setModelContextError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setModelContextLoading(true)
    setModelState(null)
    setModelContextError(null)
    getDesignStudioState(schema.project_id).then((state) => { if (active) setModelState(state) }).catch((error) => { if (active) setModelContextError(error instanceof Error ? error.message : 'Model context unavailable') }).finally(() => { if (active) setModelContextLoading(false) })
    return () => { active = false }
  }, [schema.project_id])

  const activeModel = asRecord(modelState?.active_model)
  const traceability = asRecord(activeModel.mlflow_traceability)
  const servedSource = typeof activeModel.served_source === 'string' ? activeModel.served_source : ''
  const championReady = servedSource === 'loaded_champion'
  const modelVersion = recommendationRun?.modelVersion || stringValue(traceability.model_version)
  const configurationStale = isRecommendationRunStale(recommendationRun, buildBatchSearchRequest({ objectiveWeights, fixedInputs, nCandidates, tableTopK, visualizationTopK }).run)

  return (
    <div className="space-y-7">
      <section className="border-b border-white/[0.10] pb-5">
        <PanelHeader eyebrow="Batch Search" title="Screen the design space" description="Score virtual candidates with the approved model, rank them against your engineering objectives, and review the most promising designs before physical testing." />
        <div className="mt-4 flex flex-wrap gap-2">
          <StatusBadge tone="neutral">{schema.inputs.length} schema-bound inputs</StatusBadge>
          <StatusBadge tone={modelContextLoading ? 'active' : championReady ? 'success' : 'warning'}>{modelContextLoading ? 'Checking champion status' : championReady ? 'Champion loaded' : 'Champion not loaded'}</StatusBadge>
          <StatusBadge tone={recommendationRun ? 'success' : 'active'}>{recommendationRun ? `${recommendationRun.recommendations.length} candidates ready` : 'Ready to configure'}</StatusBadge>
          {modelVersion && <StatusBadge tone="neutral">Served model {modelVersion}</StatusBadge>}
        </div>
        <p className="mt-4 max-w-4xl text-sm leading-6 text-[#B8C2D4]">Instead of physically testing every possible combination, Mirai uses the approved surrogate model to evaluate many virtual candidates and focus engineering attention on a shortlist.</p>
        <TechnicalDetails title="Model and lineage details">
          <div className="grid gap-3 sm:grid-cols-2"><div><span className="text-slate-500">Project</span><div className="font-mono text-slate-200">{schema.project_id}</div></div><div><span className="text-slate-500">Serving source</span><div className="font-mono text-slate-200">{servedSource || 'Unavailable'}</div></div><div><span className="text-slate-500">Served model version</span><div className="font-mono text-slate-200">{modelVersion || 'Resolved when the search runs'}</div></div><div><span className="text-slate-500">Run ID</span><div className="break-all font-mono text-slate-200">{stringValue(traceability.run_id) || '—'}</div></div></div>
        </TechnicalDetails>
      </section>

      {modelContextError && <Alert tone="warning" title="Model context unavailable" messages={[modelContextError]} />}
      {!modelContextLoading && !modelContextError && !championReady && <Alert tone="warning" title="Approved champion not loaded" messages={["Batch Search will preserve the existing serving behavior, but a loaded champion is required for the intended governed workflow."]} />}

      <BatchSearchTabs activeTab={activeView} onChange={onViewChange} />

      <BatchSearchPanel tab="configure" activeTab={activeView}>
        <div className="space-y-7">
          <RecommendPanel schema={schema} objectiveWeights={objectiveWeights} setObjectiveWeights={setObjectiveWeights} fixedInputs={fixedInputs} setFixedInputs={setFixedInputs} nCandidates={nCandidates} setNCandidates={setNCandidates} tableTopK={tableTopK} setTableTopK={setTableTopK} visualizationTopK={visualizationTopK} setVisualizationTopK={setVisualizationTopK} loading={recommendLoading} error={recommendError} warnings={recommendWarnings} recommendationRun={recommendationRun} configurationStale={configurationStale} onSubmit={onRecommend} onViewRecommendations={() => onViewChange('results')} />
          <DisclosurePanel title="Evaluate one reference design">
            <p className="mb-5 max-w-3xl text-sm leading-6 text-slate-400">Predict one known or proposed point for context. These values are independent from Batch Search fixed conditions; they remain the fixed reference conditions used by the response-surface visualization.</p>
            <PredictPanel schema={schema} inputValues={inputValues} setInputValues={setInputValues} prediction={prediction} warnings={predictWarnings} loading={predictLoading} error={predictError} onSubmit={onPredict} embedded />
          </DisclosurePanel>
        </div>
      </BatchSearchPanel>

      <BatchSearchPanel tab="results" activeTab={activeView}><RecommendationsPage schema={schema} recommendationRun={recommendationRun} warnings={recommendWarnings} configurationStale={configurationStale} onGoHome={() => onViewChange('configure')} /></BatchSearchPanel>
      <BatchSearchPanel tab="visuals" activeTab={activeView}><VisualizationsPage schema={schema} recommendationRun={recommendationRun} warnings={recommendWarnings} configurationStale={configurationStale} inputValues={inputValues} onGoHome={() => onViewChange('configure')} /></BatchSearchPanel>
    </div>
  )
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}
