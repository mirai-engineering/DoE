import { useEffect, useMemo, useState } from 'react'
import type { ModelQualityPredictionsResponse, ModelQualitySummary, ProjectSchema } from '../lib/api'
import { getModelQualityPredictions, getModelQualitySummary } from '../lib/api'
import { asRecord, asString, friendlyStatus, type ModelQualityView } from '../lib/modelQualityPresentation'
import { ModelQualityArtifacts } from './model-quality/ModelQualityArtifacts'
import { ModelQualityDiagnostics, type DiagnosticsSelection } from './model-quality/ModelQualityDiagnostics'
import { ModelQualityOutputs } from './model-quality/ModelQualityOutputs'
import { ModelQualityOverview } from './model-quality/ModelQualityOverview'
import { ModelQualityPanel, ModelQualityTabs } from './model-quality/ModelQualityTabs'
import { Alert, EmptyState, StatusBadge, TechnicalDetails } from './ui'

export function ModelQualityPage({ schema }: { schema: ProjectSchema }) {
  const modelQualityConfig = asRecord(schema.domain_metadata?.ui_config?.model_quality)
  const defaultOutput = asString(modelQualityConfig.default_output) || schema.outputs[0]?.name || ''
  const defaultGroup = asString(modelQualityConfig.default_group) || 'split'
  const [summary, setSummary] = useState<ModelQualitySummary | null>(null)
  const [predictions, setPredictions] = useState<ModelQualityPredictionsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [predictionLoading, setPredictionLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [predictionError, setPredictionError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<ModelQualityView>('overview')
  const [selectedOutput, setSelectedOutput] = useState(defaultOutput)
  const [diagnostics, setDiagnostics] = useState<DiagnosticsSelection>({ model: '', output: defaultOutput, splits: 'validation,test', group: defaultGroup, cellId: '', rh: '' })

  useEffect(() => {
    let mounted = true
    setLoading(true)
    setError(null)
    setSelectedOutput(defaultOutput)
    setDiagnostics({ model: '', output: defaultOutput, splits: 'validation,test', group: defaultGroup, cellId: '', rh: '' })
    getModelQualitySummary(schema.project_id)
      .then((value) => { if (mounted) setSummary(value) })
      .catch((loadError) => { if (mounted) setError(loadError instanceof Error ? loadError.message : 'Unable to load model quality') })
      .finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [schema.project_id, defaultGroup, defaultOutput])

  useEffect(() => {
    let mounted = true
    setPredictionLoading(true)
    setPredictionError(null)
    getModelQualityPredictions(schema.project_id, { limit: 50000 })
      .then((value) => { if (mounted) setPredictions(value) })
      .catch((loadError) => { if (mounted) setPredictionError(loadError instanceof Error ? loadError.message : 'Unable to load prediction diagnostics') })
      .finally(() => { if (mounted) setPredictionLoading(false) })
    return () => { mounted = false }
  }, [schema.project_id])

  const metrics = asRecord(summary?.metrics)
  const models = asRecord(metrics.models)
  const bestModelName = asString(metrics.best_model_name)
  const bestModel = asRecord(models[bestModelName])
  const targetReference = asRecord(metrics.target_reference)
  const activeModel = asRecord(summary?.active_model)
  const aliases = asRecord(activeModel.aliases)
  const champion = asRecord(aliases.champion)
  const championExists = Boolean(asString(champion.version) || asString(champion.run_id))
  const championLoaded = asString(activeModel.served_source) === 'loaded_champion'
  const diagnosticsAvailable = Boolean(asRecord(summary?.artifact_summary).prediction_diagnostics_available) || Boolean(predictions?.rows.length)
  const warning = asString(activeModel.operator_warning) || asString(summary?.warning)

  const headerStatus = useMemo(() => {
    if (championLoaded) return { tone: 'success' as const, label: 'Champion loaded', detail: 'The approved champion is active for serving.' }
    if (championExists) return { tone: 'warning' as const, label: 'Load required', detail: 'An MLflow champion exists but is not loaded for serving.' }
    if (bestModelName) return { tone: 'warning' as const, label: 'Approval required', detail: 'Training results are available; champion approval remains manual.' }
    return { tone: 'neutral' as const, label: 'No quality result', detail: 'Train the project before evaluating model quality.' }
  }, [bestModelName, championExists, championLoaded])

  function openDiagnostics(output: string) {
    setDiagnostics((current) => ({ ...current, output }))
    setActiveTab('diagnostics')
  }

  return (
    <div className="space-y-6">
      <header className="border-b border-white/[0.10] pb-5">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div><p className="text-sm font-medium text-[#74C7F5]">Model validation</p><h1 className="mt-1 text-3xl font-semibold tracking-[-0.045em] text-white">Model Quality</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-[#B8C2D4]">Evaluate model performance and identify where predictions are reliable enough to guide Design Studio.</p></div>
          <div className="flex flex-wrap items-center gap-2"><StatusBadge tone={headerStatus.tone}>{headerStatus.label}</StatusBadge>{diagnosticsAvailable && <StatusBadge tone="active">Diagnostics available</StatusBadge>}</div>
        </div>
        <div className="mt-5 rounded-lg border border-white/[0.10] bg-[#0B1424]/75 p-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><p className="text-sm font-semibold text-white">{headerStatus.detail}</p><p className="mt-1 text-sm leading-6 text-[#B8C2D4]">Best candidate: <span className="font-mono text-slate-100">{bestModelName || 'unavailable'}</span> · Serving: {friendlyStatus(activeModel.served_source)}</p></div>{warning && <StatusBadge tone="warning">Operator action needed</StatusBadge>}</div>{warning && <p className="mt-3 text-sm leading-6 text-amber-100">{warning}</p>}<TechnicalDetails title="Validation methodology"><p>All-cells MVP workflow. Splits are grouped by <code>cell_id</code>, three cells are reserved exclusively for BO replay, and acceptance thresholds are provisional/report-only.</p>{championExists && !championLoaded && <p>MLflow has a champion alias, but Mirai will not use it until Load champion model is run.</p>}</TechnicalDetails></div>
      </header>

      <ModelQualityTabs activeTab={activeTab} onChange={setActiveTab} />
      {error && <Alert tone="error" title="Model quality unavailable" messages={[error]} />}
      {loading && <div className="border-y border-white/[0.08] py-10 text-sm text-slate-300" role="status">Loading model quality...</div>}
      {!loading && !summary && !error && <EmptyState title="Model quality is not available yet" description="Complete training and load the appropriate result before reviewing model evidence." />}
      {!loading && summary && <>
        <ModelQualityPanel tab="overview" activeTab={activeTab}><ModelQualityOverview summary={summary} schema={schema} /></ModelQualityPanel>
        <ModelQualityPanel tab="outputs" activeTab={activeTab}><ModelQualityOutputs schema={schema} bestModelName={bestModelName} bestModel={bestModel} targetReference={targetReference} selectedOutput={selectedOutput} onSelectOutput={setSelectedOutput} onOpenDiagnostics={openDiagnostics} /></ModelQualityPanel>
        <ModelQualityPanel tab="diagnostics" activeTab={activeTab}><ModelQualityDiagnostics schema={schema} predictions={predictions} loading={predictionLoading} error={predictionError} bestModelName={bestModelName} selection={diagnostics} onChange={(next) => setDiagnostics((current) => ({ ...current, ...next }))} /></ModelQualityPanel>
        <ModelQualityPanel tab="artifacts" activeTab={activeTab}><ModelQualityArtifacts summary={summary} schema={schema} /></ModelQualityPanel>
      </>}
    </div>
  )
}
