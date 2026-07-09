import { useCallback, useEffect, useMemo, useState } from 'react'
import type { DomainMetadataStatus, MiraiContractValidation, IngestionSessionResponse, MLPreprocessingReport, MLPreprocessingStatus, PreprocessingEdaSummary, PreprocessingStatus, ProjectDomainMetadata, ProjectSchema, TrainingConfiguration, TrainingRequestResponse, VariableMetadata } from '../lib/api'
import {
  appendIngestionFiles,
  approveDomainMetadata,
  approvePreprocessing,
  approveMLPreprocessing,
  askDataScientist,
  createTrainingRequest,
  executeMLPreprocessing,
  exportApprovedTrainingPackage,
  getDomainMetadata,
  getMLPreprocessedTableBlob,
  getMLPreprocessingHumanReportBlob,
  getMLPreprocessingReport,
  getMLPreprocessingStatus,
  getPreprocessingEdaSummary,
  loadChampionModel,
  getPreprocessingReport,
  getPreprocessingStatus,
  getPreprocessingYdataReportBlob,
  getTrainingStatus,
  listIngestionSessions,
  listTrainingRequests,
  startMiraiPreprocessing,
  startMLPreprocessing,
  startTrainingRequest,
  updateDomainMetadata,
  validateMiraiContract,
} from '../lib/api'
import { DisclosurePanel, LifecycleStepper, SectionCard } from './ui'

function StatusPill({ children, tone = 'slate' }: { children: string; tone?: 'slate' | 'amber' | 'green' | 'rose' }) {
  const classes = tone === 'green'
    ? 'border-[#74C7F5]/30 bg-[#0D1B2D] text-[#BDEAFF]'
    : tone === 'amber'
      ? 'border-amber-200 bg-amber-50 text-amber-700'
      : tone === 'rose'
        ? 'border-rose-200 bg-rose-50 text-rose-700'
        : 'border-slate-200 bg-[#0D1B2D] text-slate-300'
  return <span className={`rounded-full border px-3 py-1 text-xs font-bold tracking-normal ${classes}`}>{children}</span>
}

function actionTone(status?: string): 'slate' | 'amber' | 'green' | 'rose' {
  if (!status || status === 'not_started') return 'slate'
  if (status.includes('failed')) return 'rose'
  if (status.includes('approved') || status.includes('complete') || status === 'completed') return 'green'
  return 'amber'
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function formatNumber(value: unknown, digits = 3): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: digits }) : '—'
}

function cloneMetadata(metadata: ProjectDomainMetadata): ProjectDomainMetadata {
  return JSON.parse(JSON.stringify(metadata)) as ProjectDomainMetadata
}

function variableLabel(variable?: VariableMetadata) {
  return variable ? `${variable.label || variable.name}${variable.unit ? ` / ${variable.unit}` : ''}` : 'Select variable'
}

const EDITABLE_METADATA_ROLES = new Set<VariableMetadata['role']>(['input', 'output', 'group', 'sweep', 'time', 'cycle', 'sequence', 'curve_axis'])
const INTERNAL_NAME_PATTERNS = [
  /(^|_)(id|uuid|hash)$/i,
  /(^|_)(experiment|condition|result|row|source|file|path|provenance)(_id|_index|_name|_path|_hash)?$/i,
  /^(experiment_id|condition_id|result_id|row_index|source_file|source_path|split)$/i,
]

function isInternalVariable(variable: VariableMetadata) {
  if (['id', 'metadata', 'context', 'ignore'].includes(variable.role)) return true
  const names = [variable.name, variable.source_name, variable.variable_id, variable.semantic_type].filter(Boolean) as string[]
  return names.some((name) => INTERNAL_NAME_PATTERNS.some((pattern) => pattern.test(name)))
}

function isEditableModelVariable(variable: VariableMetadata) {
  return EDITABLE_METADATA_ROLES.has(variable.role) && !isInternalVariable(variable)
}

function buildPrimaryRecipe(metadata: ProjectDomainMetadata, xVariable: string, yVariable: string) {
  const variables = metadata.variables ?? []
  const x = variables.find((variable) => variable.name === xVariable)
  const y = variables.find((variable) => variable.name === yVariable)
  const kind = metadata.template_id === 'fuel_cell' ? 'fuel_cell_polarization' : 'scatter_response'
  return {
    id: metadata.template_id === 'fuel_cell' ? 'fuel_cell_polarization_curve' : `response_${xVariable}_${yVariable}`,
    label: metadata.template_id === 'fuel_cell' ? 'Dynamic response curve' : `${y?.label || yVariable} vs ${x?.label || xVariable}`,
    description: metadata.template_id === 'fuel_cell'
      ? 'Uses the observed voltage grid and predicts BoL/EoL current density at each voltage.'
      : `Safe response plot using ${variableLabel(x)} on the x-axis and ${variableLabel(y)} on the y-axis.`,
    kind,
    template_id: metadata.template_id,
    safe: true,
    recommended: true,
    x: { source: x?.role === 'output' ? 'prediction' : 'input', variable: xVariable, label: x?.label || xVariable, unit: x?.unit || '' },
    y: { source: y?.role === 'input' ? 'input' : 'prediction', variable: yVariable, label: y?.label || yVariable, unit: y?.unit || '' },
    series: [],
    group_by: variables.find((variable) => variable.role === 'group')?.name ?? null,
    filters: variables.filter((variable) => ['group', 'metadata'].includes(variable.role)).map((variable) => variable.name),
  }
}

function defaultTrainingConfiguration(schema: ProjectSchema): TrainingConfiguration {
  const equalWeight = schema.outputs.length ? 1 / schema.outputs.length : 1
  return {
    linear: { include_mvlr: true, fit_intercept: true, include_ridge: true, ridge_alphas: [0.01, 0.1, 1, 10] },
    mlp: {
      include: true,
      architecture_family: 'plain_mlp',
      hidden_layers: [128, 64, 32],
      trunk_layers: [128, 128],
      head_layers: [64],
      secondary_head_layers: [32],
      activation: 'SiLU',
      normalization: 'layer_norm',
      dropout: 0.05,
      optimizer: 'AdamW',
      learning_rate: 0.003,
      weight_decay: 0.0001,
      batch_size: 'full_batch',
      max_epochs: 500,
      early_stopping_patience: 100,
      loss: 'smooth_l1',
      output_weights: Object.fromEntries(schema.outputs.map((output) => [output.name, equalWeight])),
      seeds: [7],
    },
    search: { mode: 'single_config', wall_clock_budget_minutes: 60, rerun_top_k: 0 },
    selection_metric: 'validation_weighted_normalized_rmse',
  }
}

function parseNumberList(value: string): number[] {
  return value.split(',').map((item) => Number(item.trim())).filter((value) => Number.isFinite(value))
}


function DistributionTable({ title, rows }: { title: string; rows?: Record<string, Record<string, number>> }) {
  const entries = Object.entries(rows ?? {})
  if (!entries.length) return null
  return (
    <div className="border-t border-slate-400/[0.07] pt-4">
      <h3 className="font-semibold text-white">{title}</h3>
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="text-slate-500"><tr><th className="py-2 pr-4">Variable</th><th className="py-2 pr-4">Min</th><th className="py-2 pr-4">Mean</th><th className="py-2 pr-4">Max</th><th className="py-2 pr-4">Missing</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {entries.map(([name, stats]) => <tr key={name}><td className="py-2 pr-4 font-medium text-slate-100">{name}</td><td className="py-2 pr-4 text-slate-300">{formatNumber(stats.min)}</td><td className="py-2 pr-4 text-slate-300">{formatNumber(stats.mean)}</td><td className="py-2 pr-4 text-slate-300">{formatNumber(stats.max)}</td><td className="py-2 pr-4 text-slate-300">{formatNumber(stats.missing, 0)}</td></tr>)}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function PreprocessingReviewPage({ schema, onOpenModelQuality }: { schema: ProjectSchema | null; onOpenModelQuality?: () => void }) {
  const [sessions, setSessions] = useState<IngestionSessionResponse[]>([])
  const [selectedSessionId, setSelectedSessionId] = useState('')
  const [validation, setValidation] = useState<MiraiContractValidation | null>(null)
  const [preprocessingStatus, setPreprocessingStatus] = useState<PreprocessingStatus>({ status: 'not_started' })
  const [report, setReport] = useState<Record<string, unknown> | null>(null)
  const [edaSummary, setEdaSummary] = useState<PreprocessingEdaSummary | null>(null)
  const [mlPreprocessingStatus, setMLPreprocessingStatus] = useState<MLPreprocessingStatus>({ status: 'not_started' })
  const [mlPreprocessingReport, setMLPreprocessingReport] = useState<MLPreprocessingReport | null>(null)
  const [mlPreprocessingLog, setMLPreprocessingLog] = useState<string[]>([])
  const [mlPreprocessingQuestion, setMLPreprocessingQuestion] = useState('')
  const [mlPreprocessingChat, setMLPreprocessingChat] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([])
  const [trainingRequest, setTrainingRequest] = useState<TrainingRequestResponse | null>(null)
  const [trainingStatus, setTrainingStatus] = useState<Record<string, unknown> | null>(null)
  const [exportMessage, setExportMessage] = useState<string | null>(null)
  const [mlflowImport, setMlflowImport] = useState({ runId: '', registeredModelName: '', modelVersion: '', alias: 'challenger' })
  const [importMessage, setImportMessage] = useState<string | null>(null)
  const [trainingConfig, setTrainingConfig] = useState<TrainingConfiguration>(() => defaultTrainingConfiguration(schema ?? { project_id: '', display_name: '', inputs: [], outputs: [] }))
  const [metadataStatus, setMetadataStatus] = useState<DomainMetadataStatus | null>(null)
  const [metadataDraft, setMetadataDraft] = useState<ProjectDomainMetadata | null>(null)
  const [appendFiles, setAppendFiles] = useState<File[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [mlAgentScopeCollapsed, setMLAgentScopeCollapsed] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const selectedSession = useMemo(
    () => sessions.find((session) => session.ingestion_session_id === selectedSessionId) ?? null,
    [sessions, selectedSessionId],
  )

  const loadSessions = useCallback(async () => {
    setError(null)
    const next = await listIngestionSessions(schema?.project_id)
    setSessions(next)
    const latestRaw = window.localStorage.getItem('mirai.latestIngestionSession')
    const latest = latestRaw ? JSON.parse(latestRaw) as IngestionSessionResponse : null
    const preferred = latest && next.some((session) => session.ingestion_session_id === latest.ingestion_session_id)
      ? latest.ingestion_session_id
      : next[0]?.ingestion_session_id ?? ''
    setSelectedSessionId((current) => next.some((session) => session.ingestion_session_id === current) ? current : preferred)
  }, [schema?.project_id])

  const refreshSessionState = useCallback(async (session?: IngestionSessionResponse | null) => {
    if (!session) return
    setError(null)
    try {
      const [nextValidation, nextStatus, nextMetadata, nextMLStatus] = await Promise.all([
        validateMiraiContract(session),
        getPreprocessingStatus(session),
        getDomainMetadata(session),
        getMLPreprocessingStatus(session).catch(() => ({ status: 'not_started' } as MLPreprocessingStatus)),
      ])
      setValidation(nextValidation)
      setPreprocessingStatus(nextStatus)
      setMetadataStatus(nextMetadata)
      setMetadataDraft(cloneMetadata(nextMetadata.domain_metadata))
      setMLPreprocessingStatus(nextMLStatus)
      if (nextMLStatus.status && nextMLStatus.status !== 'not_started') {
        setMLPreprocessingReport(await getMLPreprocessingReport(session).catch(() => null))
      } else {
        setMLPreprocessingReport(null)
      }
      if (['preprocessing_complete_needs_approval', 'approved_for_training'].includes(nextStatus.status)) {
        try {
          const [nextReport, nextEda, requests] = await Promise.all([
            getPreprocessingReport(session),
            getPreprocessingEdaSummary(session),
            listTrainingRequests(session),
          ])
          setReport(nextReport)
          setEdaSummary(nextEda)
          const latestRequest = [...requests].sort((a, b) => String(b.requested_at ?? '').localeCompare(String(a.requested_at ?? '')))[0] ?? null
          setTrainingRequest(latestRequest)
          if (latestRequest) {
            setTrainingStatus(await getTrainingStatus(session, latestRequest.training_request_id))
          } else {
            setTrainingStatus(null)
          }
        } catch {
          setReport(null)
          setEdaSummary(null)
        }
      } else {
        setReport(null)
        setEdaSummary(null)
        setTrainingRequest(null)
        setTrainingStatus(null)
      }
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'Unable to refresh preprocessing state')
    }
  }, [])

  useEffect(() => {
    if (schema) setTrainingConfig(defaultTrainingConfiguration(schema))
  }, [schema])

  useEffect(() => {
    loadSessions().catch((loadError) => setError(loadError instanceof Error ? loadError.message : 'Unable to load sessions'))
  }, [loadSessions])

  useEffect(() => {
    if (selectedSession) refreshSessionState(selectedSession)
  }, [refreshSessionState, selectedSession, selectedSessionId])

  useEffect(() => {
    if (!selectedSession || !['queued', 'running'].includes(preprocessingStatus.status)) return undefined
    const timer = window.setInterval(() => {
      refreshSessionState(selectedSession)
    }, 2500)
    return () => window.clearInterval(timer)
  }, [refreshSessionState, selectedSessionId, selectedSession, preprocessingStatus.status])

  async function runAction(label: string, action: () => Promise<void>) {
    setBusy(label)
    setError(null)
    try {
      await action()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : `${label} failed`)
    } finally {
      setBusy(null)
    }
  }

  const rowCounts = preprocessingStatus.row_counts ?? {}
  const modelRows = numberValue(rowCounts.model_table) ?? numberValue(rowCounts['model_table.csv'])
  const preprocessingApproved = preprocessingStatus.status === 'approved_for_training' || report?.['status'] === 'approved_for_training'
  const preprocessingComplete = preprocessingStatus.status === 'preprocessing_complete_needs_approval' || preprocessingApproved
  const metadataApproved = metadataStatus?.approval_status === 'approved' || preprocessingComplete
  const metadataVariables = metadataDraft?.variables ?? []
  const editableVariableEntries = metadataVariables.map((variable, index) => ({ variable, index })).filter(({ variable }) => isEditableModelVariable(variable))
  const provenanceVariableEntries = metadataVariables.map((variable, index) => ({ variable, index })).filter(({ variable }) => !isEditableModelVariable(variable))
  const editableVariables = editableVariableEntries.map(({ variable }) => variable)
  const inputOrSweepVariables = editableVariables.filter((variable) => ['input', 'sweep'].includes(variable.role))
  const outputVariables = editableVariables.filter((variable) => variable.role === 'output')
  const selectedRecipe = metadataDraft?.ui_config?.plot_recipes?.find((recipe) => recipe.id === metadataDraft.ui_config?.selected_plot_recipe_id) ?? metadataDraft?.ui_config?.plot_recipes?.[0]
  const selectedX = (selectedRecipe?.x?.variable && inputOrSweepVariables.some((variable) => variable.name === selectedRecipe.x?.variable) ? selectedRecipe.x.variable : undefined) || inputOrSweepVariables[0]?.name || ''
  const selectedY = (selectedRecipe?.y?.variable && outputVariables.some((variable) => variable.name === selectedRecipe.y?.variable) ? selectedRecipe.y.variable : undefined) || outputVariables[0]?.name || ''
  const lifecycleStatus = String(trainingStatus?.['status'] ?? trainingRequest?.status ?? '')
  const candidateReady = lifecycleStatus === 'candidate_ready_for_review'
  const championActive = lifecycleStatus === 'approved_champion_active'
  const trainingCompleted = lifecycleStatus === 'completed' || candidateReady || championActive
  const mlPreprocessingReady = mlPreprocessingStatus.status === 'ml_preprocessing_ready_for_training'
  const mlPreprocessingNeedsApproval = mlPreprocessingStatus.status === 'preprocessing_plan_needs_approval'
  const mlPreprocessingStarted = mlPreprocessingStatus.status && mlPreprocessingStatus.status !== 'not_started'

  function updateMetadataDraft(updater: (draft: ProjectDomainMetadata) => void) {
    setMetadataDraft((current) => {
      if (!current) return current
      const next = cloneMetadata(current)
      updater(next)
      return next
    })
  }

  function updateVariable(index: number, patch: Partial<VariableMetadata>) {
    updateMetadataDraft((draft) => {
      const variables = [...(draft.variables ?? [])]
      variables[index] = { ...variables[index], ...patch }
      draft.variables = variables
    })
  }

  function updatePrimaryRecipe(xVariable: string, yVariable: string) {
    updateMetadataDraft((draft) => {
      const recipe = buildPrimaryRecipe(draft, xVariable, yVariable)
      draft.ui_config = {
        ...(draft.ui_config ?? {}),
        selected_plot_recipe_id: recipe.id,
        plot_recipes: [recipe],
        design_studio: { ...(draft.ui_config?.design_studio ?? {}), primary_plot_recipe_id: recipe.id },
      }
    })
  }

  async function saveMetadataDraft() {
    if (!selectedSession || !metadataDraft) return
    await runAction('metadata-save', async () => {
      const status = await updateDomainMetadata(selectedSession, metadataDraft, 'Saved from Metadata & Plot Setup UI.')
      setMetadataStatus(status)
      setMetadataDraft(cloneMetadata(status.domain_metadata))
    })
  }

  async function approveMetadataDraft() {
    if (!selectedSession || !metadataDraft) return
    await runAction('metadata-approval', async () => {
      await updateDomainMetadata(selectedSession, metadataDraft, 'Approved draft staged from Metadata & Plot Setup UI.')
      const status = await approveDomainMetadata(selectedSession, 'Approved metadata and plot setup from Preprocessing Review UI.')
      setMetadataStatus(status)
      setMetadataDraft(cloneMetadata(status.domain_metadata))
    })
  }

  async function handleAppendFiles() {
    if (!selectedSession || !appendFiles.length) return
    await runAction('append-files', async () => {
      const updated = await appendIngestionFiles(selectedSession, appendFiles)
      window.localStorage.setItem('mirai.latestIngestionSession', JSON.stringify(updated))
      setSessions((current) => current.map((session) => session.ingestion_session_id === updated.ingestion_session_id ? updated : session))
      setAppendFiles([])
      setReport(null)
      setEdaSummary(null)
      setTrainingRequest(null)
      setTrainingStatus(null)
      await refreshSessionState(updated)
    })
  }

  const lifecycleSteps = [
    { id: 'upload', label: 'Create project', status: 'done' as const },
    { id: 'metadata', label: 'Review metadata', status: metadataApproved ? 'done' as const : 'current' as const },
    { id: 'preprocess', label: 'Preprocess', status: preprocessingComplete ? 'done' as const : metadataApproved ? 'current' as const : 'locked' as const },
    { id: 'ml-preprocess', label: 'ML preprocessing', status: mlPreprocessingReady ? 'done' as const : preprocessingApproved ? 'current' as const : 'locked' as const },
    { id: 'train', label: 'Train', status: trainingCompleted ? 'done' as const : mlPreprocessingReady ? 'current' as const : 'locked' as const },
    { id: 'quality', label: 'Quality', status: trainingCompleted ? 'current' as const : 'locked' as const },
  ]

  const metadataSummary = [
    ['Inputs', inputOrSweepVariables.length],
    ['Outputs', outputVariables.length],
    ['Other/provenance', provenanceVariableEntries.length],
  ]

  const canUseProjectChampionLoader = Boolean(schema?.project_id && !championActive && (mlPreprocessingReady || preprocessingApproved || trainingRequest || trainingCompleted || !selectedSession))
  const projectOnlyChampionControls = Boolean(schema?.project_id && !selectedSession)
  const canRunPreprocessing = selectedSession && metadataApproved && !['queued', 'running'].includes(preprocessingStatus.status)
  const recommendedTrainingReady = selectedSession && preprocessingApproved && mlPreprocessingReady && !trainingRequest
  const canExportApprovedPackage = Boolean(selectedSession && preprocessingApproved && trainingRequest)
  const expectedMlflowExperiment = schema?.project_id || selectedSession?.project_id || '<project_id>'
  const expectedRegisteredModel = expectedMlflowExperiment && expectedMlflowExperiment !== '<project_id>' ? `doe_surrogate_${expectedMlflowExperiment}` : 'doe_surrogate_<project_id>'

  async function handleExportApprovedPackage() {
    if (!selectedSession || !trainingRequest) return
    await runAction('export-package', async () => {
      await exportApprovedTrainingPackage(selectedSession, trainingRequest.training_request_id)
      setExportMessage('Approved training package export started. Check your downloads folder.')
    })
  }

  async function handleOpenYdataReport() {
    if (!selectedSession) return
    const popup = window.open('', '_blank')
    if (popup) popup.opener = null
    await runAction('open-ydata-report', async () => {
      try {
        const { blob } = await getPreprocessingYdataReportBlob(selectedSession)
        const url = window.URL.createObjectURL(new Blob([blob], { type: 'text/html' }))
        if (popup) {
          popup.location.href = url
          window.setTimeout(() => window.URL.revokeObjectURL(url), 60_000)
        } else {
          const link = document.createElement('a')
          link.href = url
          link.target = '_blank'
          link.rel = 'noopener noreferrer'
          document.body.appendChild(link)
          link.click()
          link.remove()
          window.setTimeout(() => window.URL.revokeObjectURL(url), 60_000)
        }
      } catch (reportError) {
        popup?.close()
        throw reportError
      }
    })
  }

  async function draftMLPreprocessingPlan() {
    if (!selectedSession) return
    await runAction('ml-preprocessing-draft', async () => {
      const log = ['Loading bounded EDA/profile evidence…', 'Loading ML preprocessing skill and policy…']
      setMLPreprocessingLog(log)
      const drafted = await startMLPreprocessing(selectedSession)
      setMLPreprocessingStatus(drafted)
      const nextReport = await getMLPreprocessingReport(selectedSession)
      setMLPreprocessingReport(nextReport)
      setMLPreprocessingLog([...log, 'Drafted deterministic tool plan and passed validation gates.', 'Paused before applying. Ask the ML preprocessing agent, then approve/apply when ready.'])
    })
  }

  async function applyMLPreprocessingPlan() {
    if (!selectedSession) return
    await runAction('ml-preprocessing-apply', async () => {
      setMLPreprocessingLog((current) => [...current, 'Approving plan. Running train-only fit and transform-only validation/test application…'])
      const approved = await approveMLPreprocessing(selectedSession, 'Approved deterministic ML preprocessing plan from Preprocessing Review UI.')
      setMLPreprocessingStatus(approved)
      const executed = await executeMLPreprocessing(selectedSession)
      setMLPreprocessingStatus(executed)
      const nextReport = await getMLPreprocessingReport(selectedSession)
      setMLPreprocessingReport(nextReport)
      setMLPreprocessingLog((current) => [...current, 'ml_preprocessing_ready_for_training', 'Preprocessing ready — this is what we did.'])
    })
  }

  function downloadBlob(blob: Blob, filename: string) {
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  }

  async function handleDownloadPreprocessedTable() {
    if (!selectedSession) return
    await runAction('download-ml-preprocessed-table', async () => {
      const { blob, filename } = await getMLPreprocessedTableBlob(selectedSession)
      downloadBlob(blob, filename)
    })
  }

  async function handleDownloadMLPreprocessingReport() {
    if (!selectedSession) return
    await runAction('download-ml-preprocessing-report', async () => {
      const { blob, filename } = await getMLPreprocessingHumanReportBlob(selectedSession)
      downloadBlob(blob, filename)
    })
  }

  async function askMLPreprocessingAgent(question?: string) {
    if (!selectedSession || !schema?.project_id) return
    const prompt = (question ?? mlPreprocessingQuestion).trim()
    if (!prompt) return
    const next = [...mlPreprocessingChat, { role: 'user' as const, content: prompt }]
    setMLPreprocessingChat(next)
    setMLPreprocessingQuestion('')
    await runAction('ml-preprocessing-chat', async () => {
      const response = await askDataScientist(
        schema.project_id,
        `For the selected ML preprocessing session ${selectedSession.ingestion_session_id}, answer this question using ml_preprocessing_summary and other scoped read-only tools as needed: ${prompt}`,
        next.slice(-8),
      )
      setMLPreprocessingChat([...next, { role: 'assistant', content: response.answer }])
    })
  }

  async function handleLoadChampionModel() {
    if (!schema?.project_id) return
    await runAction('load-champion-model', async () => {
      const status = await loadChampionModel(schema.project_id, {
        mlflow_run_id: mlflowImport.runId.trim() || undefined,
        registered_model_name: mlflowImport.registeredModelName.trim() || undefined,
        model_version: mlflowImport.modelVersion.trim() || undefined,
        notes: 'Loaded from Preprocessing Review UI after MLflow champion approval.',
      })
      setTrainingStatus(status)
      setTrainingRequest((current) => current ? { ...current, status: 'approved_champion_active' } : current)
      setImportMessage('Champion model loaded. Model Quality and Design Studio now use the served champion.')
    })
  }

  const nextAction = (() => {
    if (!selectedSession) {
      if (schema?.project_id) return { label: busy === 'load-champion-model' ? 'Loading...' : championActive ? 'Reload champion model' : 'Load champion model', disabled: Boolean(busy), run: handleLoadChampionModel }
      return { label: 'Select a session', disabled: true, run: undefined as (() => void) | undefined }
    }
    if (!metadataApproved) return { label: busy === 'metadata-approval' ? 'Approving...' : 'Approve metadata', disabled: !metadataDraft || Boolean(busy), run: approveMetadataDraft }
    if (!preprocessingComplete) return { label: busy === 'preprocessing' ? 'Preprocessing...' : 'Run preprocessing', disabled: !canRunPreprocessing || Boolean(busy), run: () => runAction('preprocessing', async () => { setPreprocessingStatus(await startMiraiPreprocessing(selectedSession)) }) }
    if (!preprocessingApproved) return { label: busy === 'approval' ? 'Approving...' : 'Approve preprocessing', disabled: Boolean(busy), run: () => runAction('approval', async () => { setReport(await approvePreprocessing(selectedSession, 'Approved from Preprocessing Review UI.')); await refreshSessionState(selectedSession) }) }
    if (!mlPreprocessingStarted) return { label: busy === 'ml-preprocessing-draft' ? 'Drafting...' : 'Draft ML preprocessing plan', disabled: Boolean(busy), run: draftMLPreprocessingPlan }
    if (!mlPreprocessingReady) return { label: busy === 'ml-preprocessing-apply' ? 'Applying...' : 'Apply ML preprocessing', disabled: Boolean(busy), run: applyMLPreprocessingPlan }
    if (!trainingRequest) return { label: busy === 'training-request' ? 'Creating...' : 'Create training request', disabled: !recommendedTrainingReady || Boolean(busy), run: () => runAction('training-request', async () => { const request = await createTrainingRequest(selectedSession, trainingConfig); setTrainingRequest(request); setTrainingStatus(await getTrainingStatus(selectedSession, request.training_request_id)) }) }
    if (!trainingCompleted) return { label: busy === 'training' ? 'Training...' : 'Start recommended training', disabled: Boolean(busy), run: () => runAction('training', async () => { setTrainingStatus(await startTrainingRequest(selectedSession, trainingRequest.training_request_id)) }) }
    if (candidateReady || trainingCompleted) return { label: busy === 'load-champion-model' ? 'Loading...' : 'Load champion model', disabled: Boolean(busy), run: handleLoadChampionModel }
    return { label: 'Open model quality', disabled: false, run: onOpenModelQuality }
  })()

  return (
    <div className="space-y-6">
      <LifecycleStepper steps={lifecycleSteps} />

      <SectionCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-[#74C7F5]">Lifecycle</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.055em] text-white">Prepare this project for training</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">Confirm the metadata, run preprocessing, then start the recommended training path.</p>
          </div>
          <StatusPill tone={championActive ? 'green' : trainingCompleted ? 'amber' : actionTone(preprocessingStatus.status)}>{championActive ? 'champion loaded' : trainingCompleted ? 'ready to load champion' : preprocessingStatus.status || 'not started'}</StatusPill>
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
          <label className="text-sm font-semibold text-slate-300">
            Session
            <select value={selectedSessionId} onChange={(event) => setSelectedSessionId(event.target.value)} className="mt-2 w-full border-y border-slate-400/[0.10] px-4 py-3 text-sm text-white outline-none focus:border-[#74C7F5]">
              <option value="">No sessions found</option>
              {sessions.map((session) => (
                <option key={session.ingestion_session_id} value={session.ingestion_session_id}>{session.project_name} · {session.ingestion_session_id}</option>
              ))}
            </select>
          </label>
          <button type="button" onClick={() => refreshSessionState()} disabled={!selectedSession || Boolean(busy)} className="rounded-full border border-slate-200 bg-[#0B1220] px-4 py-3 text-sm font-semibold text-slate-300 disabled:opacity-45">Refresh</button>
        </div>

        {selectedSession && (
          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <div className="border-t border-slate-400/[0.07] pt-4 text-sm"><div className="text-xs font-bold tracking-normal text-slate-400">Project</div><div className="mt-1 truncate font-semibold text-white">{selectedSession.project_name}</div></div>
            <div className="border-t border-slate-400/[0.07] pt-4 text-sm"><div className="text-xs font-bold tracking-normal text-slate-400">Files</div><div className="mt-1 font-semibold text-white">{selectedSession.files.length}</div></div>
            <div className="border-t border-slate-400/[0.07] pt-4 text-sm"><div className="text-xs font-bold tracking-normal text-slate-400">Columns</div><div className="mt-1 font-semibold text-white">{validation?.column_count ?? '—'}</div></div>
            <div className="border-t border-slate-400/[0.07] pt-4 text-sm"><div className="text-xs font-bold tracking-normal text-slate-400">Rows</div><div className="mt-1 font-semibold text-white">{modelRows ?? 'Pending'}</div></div>
          </div>
        )}

        {projectOnlyChampionControls && (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            <div className="font-semibold text-amber-900">No intake session is available in this deployment.</div>
            <p className="mt-1 leading-6">The original preprocessing session is app-local runtime state, but this project can still use MLflow champion artifacts. Promote the intended version to <code>champion</code>, then load or reload the champion model here.</p>
          </div>
        )}
      </SectionCard>

      {error && <section className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</section>}

      <SectionCard>
        <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
          <div>
            <p className="text-xs font-bold tracking-normal text-[#74C7F5]">Next step</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-white">{nextAction.label}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              {projectOnlyChampionControls
                ? 'No intake session is available here, so use the project-level MLflow champion loader to refresh serving state.'
                : championActive
                  ? 'Approved champion is active for serving, Model Quality, and Design Studio.'
                  : candidateReady
                    ? 'Training artifacts are ready. Promote the intended version to champion in MLflow, then load the champion model here.'
                    : trainingCompleted
                      ? 'Training artifacts are ready for review.'
                  : !metadataApproved
                    ? 'Review the variable summary, then approve metadata.'
                    : !preprocessingComplete
                      ? 'Generate the canonical model table and evidence.'
                        : !preprocessingApproved
                          ? 'Review evidence, then approve training readiness.'
                          : !trainingRequest
                            ? 'Use the recommended training configuration.'
                            : 'Run the approved training request or import a completed local MLflow run.'}
            </p>
          </div>
          <button type="button" disabled={nextAction.disabled} onClick={nextAction.run} className="h-fit rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white shadow-sm shadow-slate-950/20 disabled:opacity-45">
            {nextAction.label}
          </button>
        </div>
      </SectionCard>

      {metadataDraft && (
        <SectionCard className="bg-[#0B1220] border-[#74C7F5]/50">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-bold tracking-normal text-[#74C7F5]">Metadata</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-white">Variable summary</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">Confirm labels and roles before preprocessing. Internal IDs stay fixed for training.</p>
            </div>
            <StatusPill tone={metadataApproved ? 'green' : metadataStatus?.approval_status === 'draft' ? 'amber' : 'slate'}>{metadataStatus?.approval_status || 'needs review'}</StatusPill>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-3">
            {metadataSummary.map(([label, value]) => (
              <div key={label as string} className="border-t border-slate-400/[0.07] pt-4">
                <div className="text-xs font-bold tracking-normal text-slate-400">{label}</div>
                <div className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-white">{value}</div>
              </div>
            ))}
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <div className="border-t border-slate-400/[0.07] pt-4">
              <div className="font-semibold text-white">Inputs</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {inputOrSweepVariables.slice(0, 8).map((variable) => <span key={variable.name} className="rounded-full bg-[#10203A] px-3 py-1 text-xs font-semibold text-slate-300">{variable.label || variable.name}</span>)}
              </div>
            </div>
            <div className="border-t border-slate-400/[0.07] pt-4">
              <div className="font-semibold text-white">Outputs</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {outputVariables.slice(0, 8).map((variable) => <span key={variable.name} className="rounded-md border border-slate-700 bg-[#0D1B2D] px-3 py-1 text-xs font-semibold text-slate-200">{variable.label || variable.name}</span>)}
              </div>
            </div>
          </div>

          <div className="mt-5 space-y-3">
            <DisclosurePanel title="Edit labels/details">
              <div className="grid gap-4 md:grid-cols-2">
                <label className="text-sm font-semibold text-slate-300">
                  X variable
                  <select value={selectedX} onChange={(event) => updatePrimaryRecipe(event.target.value, selectedY)} disabled={!inputOrSweepVariables.length || !selectedY} className="mt-2 w-full border-y border-slate-400/[0.10] px-3 py-2 text-sm disabled:opacity-50">
                    {inputOrSweepVariables.map((variable) => <option key={variable.name} value={variable.name}>{variableLabel(variable)} · {variable.role}</option>)}
                  </select>
                </label>
                <label className="text-sm font-semibold text-slate-300">
                  Y variable
                  <select value={selectedY} onChange={(event) => updatePrimaryRecipe(selectedX, event.target.value)} disabled={!outputVariables.length || !selectedX} className="mt-2 w-full border-y border-slate-400/[0.10] px-3 py-2 text-sm disabled:opacity-50">
                    {outputVariables.map((variable) => <option key={variable.name} value={variable.name}>{variableLabel(variable)} · {variable.role}</option>)}
                  </select>
                </label>
              </div>
              <div className="mt-4 overflow-x-auto border-y border-slate-400/[0.10]">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-[#0B1220] text-xs tracking-normal text-slate-500">
                    <tr><th className="px-3 py-3">ID</th><th className="px-3 py-3">Source</th><th className="px-3 py-3">Label</th><th className="px-3 py-3">Unit</th><th className="px-3 py-3">Role</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {editableVariableEntries.map(({ variable, index }) => (
                      <tr key={`${variable.name}-${index}`}>
                        <td className="px-3 py-3 font-mono text-xs text-slate-300">{variable.variable_id || variable.name}</td>
                        <td className="px-3 py-3 text-xs text-slate-300"><div className="font-medium text-slate-100">{variable.source_name || variable.name}</div></td>
                        <td className="px-3 py-3"><input value={variable.label || ''} onChange={(event) => updateVariable(index, { label: event.target.value, ui_label: event.target.value })} className="w-full rounded-xl border border-slate-200 px-3 py-2" /></td>
                        <td className="px-3 py-3"><input value={variable.unit || ''} onChange={(event) => updateVariable(index, { unit: event.target.value })} className="w-full rounded-xl border border-slate-200 px-3 py-2" /></td>
                        <td className="px-3 py-3">
                          <select value={variable.role} onChange={(event) => updateVariable(index, { role: event.target.value as VariableMetadata['role'] })} className="w-full rounded-xl border border-slate-200 px-3 py-2">
                            <option value="input">input</option><option value="output">output</option><option value="group">group</option><option value="sweep">sweep</option><option value="time">time</option><option value="cycle">cycle</option><option value="sequence">sequence</option><option value="curve_axis">curve_axis</option>
                          </select>
                        </td>
                      </tr>
                    ))}
                    {!editableVariableEntries.length && <tr><td colSpan={5} className="px-3 py-6 text-sm text-slate-500">No editable modeling variables were detected.</td></tr>}
                  </tbody>
                </table>
              </div>
              {!!provenanceVariableEntries.length && (
                <DisclosurePanel title={`Internal/provenance fields (${provenanceVariableEntries.length})`} defaultOpen={false}>
                  <p className="text-sm leading-6 text-slate-300">These IDs, joins, split columns, and source metadata are kept read-only so they cannot accidentally become training inputs.</p>
                  <div className="mt-3 max-h-80 overflow-auto border-y border-slate-400/[0.10]">
                    <table className="min-w-full text-left text-xs">
                      <thead className="bg-[#0D1B2D] tracking-normal text-slate-500">
                        <tr><th className="px-3 py-3">ID</th><th className="px-3 py-3">Source</th><th className="px-3 py-3">Label</th><th className="px-3 py-3">Role</th></tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {provenanceVariableEntries.map(({ variable, index }) => (
                          <tr key={`${variable.name}-${index}`}>
                            <td className="px-3 py-3 font-mono text-slate-300">{variable.variable_id || variable.name}</td>
                            <td className="px-3 py-3 text-slate-300">{variable.source_name || variable.name}</td>
                            <td className="px-3 py-3 text-slate-300">{variable.label || '—'}</td>
                            <td className="px-3 py-3 text-slate-500">{variable.role}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </DisclosurePanel>
              )}
              <div className="mt-4 flex flex-wrap justify-end gap-3">
                <button type="button" disabled={!selectedSession || Boolean(busy)} onClick={saveMetadataDraft} className="rounded-full border border-slate-300 bg-[#0B1220] px-5 py-3 text-sm font-semibold text-slate-300 disabled:opacity-45">{busy === 'metadata-save' ? 'Saving...' : 'Save draft'}</button>
                <button type="button" disabled={!selectedSession || Boolean(busy)} onClick={approveMetadataDraft} className="rounded-full bg-[#2F6BFF] px-5 py-3 text-sm font-semibold text-white shadow-sm shadow-[#2F6BFF]/20 disabled:opacity-45">{busy === 'metadata-approval' ? 'Approving...' : 'Approve metadata'}</button>
              </div>
            </DisclosurePanel>
          </div>
        </SectionCard>
      )}

      {preprocessingComplete && (
        <SectionCard>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-bold tracking-normal text-[#74C7F5]">Evidence</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-white">Preprocessing results</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">Canonical data is ready for review.</p>
            </div>
            <StatusPill tone={edaSummary ? 'green' : 'amber'}>{edaSummary ? 'ready' : 'loading'}</StatusPill>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-4">
            {[
              ['Model rows', edaSummary?.summary.model_rows ?? modelRows],
              ['Rejected rows', edaSummary?.summary.rejected_rows?.count ?? rowCounts['rejected_rows.csv']],
              ['Inputs', validation?.input_count],
              ['Outputs', validation?.output_count],
            ].map(([label, value]) => (
              <div key={label as string} className="border-t border-slate-400/[0.07] pt-4">
                <div className="text-xs font-bold tracking-normal text-slate-400">{label}</div>
                <div className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-white">{formatNumber(value, 0)}</div>
              </div>
            ))}
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <DistributionTable title="Input ranges" rows={edaSummary?.summary.input_distributions} />
            <DistributionTable title="Output ranges" rows={edaSummary?.summary.output_distributions} />
          </div>

          {!!edaSummary?.summary.leakage_warnings?.length && (
            <div className="mt-5 rounded-lg border border-amber-200 bg-amber-50 p-4">
              <h3 className="font-semibold text-amber-900">Review warnings</h3>
              <ul className="mt-2 list-disc pl-5 text-sm leading-6 text-amber-800">
                {edaSummary.summary.leakage_warnings.map((warning) => <li key={warning}>{warning}</li>)}
              </ul>
            </div>
          )}

          <div className="mt-5 space-y-3">
            <DisclosurePanel title="Diagnostics and artifact links">
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="border-t border-slate-400/[0.07] pt-4">
                  <h3 className="font-semibold text-white">Split plan</h3>
                  <p className="mt-1 text-sm text-slate-300">{edaSummary?.summary.split_strategy ?? 'See split artifact after refresh'} · BO policy: {edaSummary?.summary.bo_policy ?? 'train + validation; test untouched'}</p>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                    {Object.entries(edaSummary?.summary.split_counts ?? {}).map(([split, count]) => <div key={split} className="border-l border-slate-400/[0.10] px-3 py-2"><span className="font-semibold text-white">{split}</span><span className="float-right text-slate-300">{formatNumber(count, 0)}</span></div>)}
                  </div>
                </div>
                <div className="border-t border-slate-400/[0.07] pt-4">
                  <h3 className="font-semibold text-white">Rejected-row reasons</h3>
                  <div className="mt-3 space-y-2 text-sm">
                    {Object.entries(edaSummary?.summary.rejected_rows?.reasons ?? {}).map(([reason, count]) => <div key={reason} className="border-l border-slate-400/[0.10] px-3 py-2"><span className="font-semibold text-white">{reason}</span><span className="float-right text-slate-300">{formatNumber(count, 0)}</span></div>)}
                  </div>
                </div>
              </div>
              <div className="mt-4 border-t border-slate-400/[0.07] pt-4 text-xs text-slate-300">
                {selectedSession && <button type="button" onClick={handleOpenYdataReport} disabled={busy === 'open-ydata-report'} className="rounded-full bg-slate-950 px-4 py-2 text-xs font-bold tracking-normal text-white shadow-sm shadow-slate-950/20 disabled:opacity-50">{busy === 'open-ydata-report' ? 'Opening HTML EDA…' : 'Open HTML EDA ↗'}</button>}
                <div className="mt-3 break-all">EDA JSON: {edaSummary?.artifacts.eda_report_json ?? 'available after refresh'}</div>
                <div className="break-all">Split JSON: {edaSummary?.artifacts.split_report_json ?? 'available after refresh'}</div>
                <div className="break-all">Preprocessing report: {edaSummary?.artifacts.preprocessing_report_json ?? preprocessingStatus.report_path ?? 'available after refresh'}</div>
              </div>
            </DisclosurePanel>
          </div>
        </SectionCard>
      )}

      {preprocessingApproved && (
        <SectionCard>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-bold tracking-normal text-[#74C7F5]">ML preprocessing</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-white">Training-ready model table</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">Start the deterministic ML preprocessing lifecycle. Mirai uses EDA evidence to draft a typed tool plan, fits tool parameters on train rows only, and writes the actual model_table_preprocessed.csv used for training.</p>
            </div>
            <StatusPill tone={mlPreprocessingReady ? 'green' : mlPreprocessingStarted ? 'amber' : 'slate'}>{mlPreprocessingReady ? 'ready' : mlPreprocessingStarted ? 'in review' : 'not started'}</StatusPill>
          </div>
          <div className="mt-5 border-t border-slate-400/[0.07] pt-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="max-w-2xl text-sm leading-6 text-slate-300">
                <div className="font-semibold text-white">{mlPreprocessingReady ? 'Preprocessing ready — this is what we did' : mlPreprocessingStarted ? 'Review ML preprocessing plan before applying' : 'Draft ML preprocessing plan'}</div>
                <p className="mt-1">{mlPreprocessingReport?.summary ?? mlPreprocessingStatus.summary ?? 'Canonical data remains untouched; training will use the approved ML preprocessing version.'}</p>
              </div>
              <div className="flex flex-wrap gap-3">
                {!mlPreprocessingStarted && <button type="button" onClick={draftMLPreprocessingPlan} disabled={!selectedSession || Boolean(busy)} className="rounded-full bg-slate-950 px-5 py-3 text-xs font-bold tracking-normal text-white shadow-sm shadow-slate-950/20 disabled:opacity-45">{busy === 'ml-preprocessing-draft' ? 'Drafting…' : 'Draft plan'}</button>}
                {mlPreprocessingStarted && !mlPreprocessingReady && <button type="button" onClick={applyMLPreprocessingPlan} disabled={!selectedSession || Boolean(busy)} className="rounded-full bg-slate-950 px-5 py-3 text-xs font-bold tracking-normal text-white shadow-sm shadow-slate-950/20 disabled:opacity-45">{busy === 'ml-preprocessing-apply' ? 'Applying…' : 'Approve & apply'}</button>}
                {mlPreprocessingStarted && <button type="button" onClick={handleDownloadMLPreprocessingReport} disabled={Boolean(busy)} className="rounded-full border border-slate-300 bg-[#0B1220] px-5 py-3 text-xs font-bold tracking-normal text-slate-300 disabled:opacity-45">Human report</button>}
                {mlPreprocessingReady && <button type="button" onClick={handleDownloadPreprocessedTable} disabled={Boolean(busy)} className="rounded-full border border-slate-300 bg-[#0B1220] px-5 py-3 text-xs font-bold tracking-normal text-slate-300 disabled:opacity-45">Download CSV for inspection</button>}
              </div>
            </div>
            {(mlPreprocessingLog.length > 0 || mlPreprocessingNeedsApproval || mlPreprocessingReady) && (
              <div className="mt-4 rounded-lg border border-slate-200 bg-[#0f172a] p-4 font-mono text-xs leading-6 text-slate-100">
                {(mlPreprocessingLog.length ? mlPreprocessingLog : [String(mlPreprocessingStatus.status)]).map((line, index) => <div key={`${line}-${index}`}>› {line}</div>)}
              </div>
            )}
            {!!mlPreprocessingReport?.export_files?.length && (
              <div className="mt-4 space-y-2 text-xs text-slate-300">
                <p className="font-semibold text-slate-300">Standalone artifacts are for review. Local training requires the approved training package in the Training section.</p>
                <div className="flex flex-wrap gap-2">
                  {mlPreprocessingReport.export_files.map((name) => <span key={name} className="rounded-full bg-[#0B1220] px-3 py-1 font-semibold">{name}</span>)}
                </div>
              </div>
            )}
            <div className="mt-5 overflow-hidden border-y border-slate-400/[0.12]">
              <div className="border-b border-slate-400/[0.08] bg-[linear-gradient(90deg,rgba(139,92,246,0.10),rgba(91,168,255,0.045))] px-5 py-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#8B5CF6]/20 text-[#A78BFA]">
                      <span className="h-2.5 w-2.5 rounded-full bg-[#A78BFA]" />
                    </div>
                    <div>
                      <p className="font-mono text-xs font-bold tracking-normal text-[#A78BFA]">ML preprocessing agent</p>
                      <h3 className="mt-1 text-lg font-semibold tracking-[-0.03em] text-[#F3F7FF]">Ask about preprocessing choices</h3>
                      <p className="mt-1 max-w-3xl text-sm leading-6 text-[#B8C2D4]">Discuss the draft or completed preprocessing before/after applying it. The agent reads scoped ML preprocessing artifacts, not cross-workspace files or raw storage paths.</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => void askMLPreprocessingAgent('Explain what happened during ML preprocessing and list the exported files.')} disabled={!selectedSession || Boolean(busy)} className="rounded-lg border border-slate-400/[0.10] bg-[#101A2C]/60 px-3 py-2 text-xs font-semibold text-[#D7DEEA] transition hover:border-[#5BA8FF]/30 hover:bg-[#121F35]/90 hover:text-[#F3F7FF] disabled:opacity-45">What happened?</button>
                    <button type="button" onClick={() => void askMLPreprocessingAgent('x7 looks binary. Why was it not one-hot encoded? Should we change that before training?')} disabled={!selectedSession || Boolean(busy)} className="rounded-lg border border-[#5BA8FF]/35 bg-[#5BA8FF]/[0.11] px-3 py-2 text-xs font-semibold text-[#F3F7FF] transition hover:border-[#5BA8FF]/45 disabled:opacity-45">Ask about x7</button>
                  </div>
                </div>
              </div>

              <div className={`grid gap-0 transition-[grid-template-columns] duration-200 ${mlAgentScopeCollapsed ? 'lg:grid-cols-[minmax(0,1fr)_2.75rem]' : 'lg:grid-cols-[minmax(0,1fr)_16rem]'}`}>
                <div className="flex min-h-[20rem] flex-col">
                  <div className="max-h-80 flex-1 space-y-4 overflow-y-auto px-5 py-5">
                    {mlPreprocessingChat.length === 0 ? (
                      <div className="border-y border-slate-400/[0.12] bg-[#101A2C]/65 py-6 text-center">
                        <p className="text-sm font-semibold text-[#F3F7FF]">Ask before approving/running, or after completion to explain the report.</p>
                        <p className="mt-2 text-xs leading-5 text-[#AAB6C8]">Answers remain project-scoped and grounded in preprocessing artifacts.</p>
                      </div>
                    ) : mlPreprocessingChat.map((message, index) => (
                      <div key={`${message.role}-${index}`} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[85%] rounded-xl px-4 py-3 text-sm leading-6 ${message.role === 'user' ? 'border border-[#5BA8FF]/32 bg-[#5BA8FF]/[0.11] text-[#F3F7FF]' : 'border border-slate-400/[0.14] bg-[#101A2C]/90 text-[#D7DEEA]'}`}>
                          {message.role === 'assistant' && <div className="mb-2 inline-flex rounded-full border border-[#D9C27E]/20 bg-[#D9C27E]/10 px-3 py-1 font-mono text-[0.65rem] font-bold tracking-normal text-[#D8C98F]">Cited from preprocessing</div>}
                          <p className="whitespace-pre-wrap">{message.content}</p>
                        </div>
                      </div>
                    ))}
                    {busy === 'ml-preprocessing-chat' && <div className="border-l border-slate-400/[0.10] pl-4 text-sm text-slate-300">Checking scoped ML preprocessing artifacts…</div>}
                  </div>

                  <form onSubmit={(event) => { event.preventDefault(); void askMLPreprocessingAgent() }} className="border-t border-slate-400/[0.12] bg-[#0B1220] p-4">
                    <div className="flex flex-col gap-3 rounded-lg border border-slate-400/[0.16] bg-[#0B1220] p-3 sm:flex-row sm:items-center">
                      <input value={mlPreprocessingQuestion} onChange={(event) => setMLPreprocessingQuestion(event.target.value)} maxLength={1200} placeholder="Ask about tool choices, one-hot encoding, leakage, or exports…" className="min-h-11 flex-1 rounded-md border border-slate-400/[0.18] bg-[#050914] px-3 text-sm text-[#F3F7FF] outline-none placeholder:text-[#6F7A90] focus:border-[#5BA8FF]/40 focus:ring-0" />
                      <span className="hidden text-xs font-semibold tracking-normal text-[#63D69A] sm:inline"><span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-[#63D69A]" />Ready</span>
                      <button type="submit" disabled={!selectedSession || Boolean(busy) || !mlPreprocessingQuestion.trim()} className="rounded-md bg-[#2563EB] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#3478FF] disabled:opacity-45">Ask</button>
                    </div>
                  </form>
                </div>

                <aside className={`border-t border-slate-400/[0.07] bg-[#0B1220] ${mlAgentScopeCollapsed ? 'flex items-center justify-center p-3' : 'p-5'} lg:border-l-0 lg:border-t-0`}>
                  {mlAgentScopeCollapsed ? (
                    <button type="button" onClick={() => setMLAgentScopeCollapsed(false)} className="inline-flex h-full min-h-40 flex-col items-center justify-center gap-3 rounded-md text-[#9FB0C8] transition hover:bg-[#5BA8FF]/10 hover:text-[#F3F7FF]" aria-label="Show agent scope" title="Show agent scope">
                      <span className="text-sm font-semibold">‹</span>
                      <span className="text-[0.65rem] font-semibold uppercase tracking-[0.12em] [writing-mode:vertical-rl]">Scope</span>
                    </button>
                  ) : (
                    <>
                      <div className="flex items-center justify-between gap-3">
                        <p className="font-mono text-xs font-bold tracking-normal text-[#7E8AA0]">Agent scope</p>
                        <button type="button" onClick={() => setMLAgentScopeCollapsed(true)} className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-400/[0.12] text-sm font-semibold text-[#9FB0C8] transition hover:border-[#5BA8FF]/30 hover:bg-[#5BA8FF]/10 hover:text-[#F3F7FF]" aria-label="Hide agent scope" title="Hide scope">›</button>
                      </div>
                      <div className="mt-4 space-y-3">
                        <div className="rounded-lg border border-[#8B5CF6]/20 bg-[#8B5CF6]/[0.11] px-3 py-3 text-xs font-medium text-[#B89CFF]"><span className="mr-2 inline-block h-2 w-2 rounded-full bg-[#8B5CF6]/70" />Project-scoped</div>
                        <div className="rounded-lg border border-[#5BA8FF]/20 bg-[#5BA8FF]/10 px-3 py-3 text-xs font-medium text-[#8FCBFF]"><span className="mr-2 inline-block h-2 w-2 rounded-full bg-[#5BA8FF]/75" />Read-only tools</div>
                        <div className="rounded-lg border border-[#D9C27E]/20 bg-[#D9C27E]/10 px-3 py-3 text-xs font-medium text-[#D8C98F]"><span className="mr-2 inline-block h-2 w-2 rounded-full bg-[#D9C27E]/75" />No raw paths</div>
                      </div>
                    </>
                  )}
                </aside>
              </div>
            </div>
          </div>
        </SectionCard>
      )}

      <SectionCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-bold tracking-normal text-[#74C7F5]">Training</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-white">Recommended training</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">Use the default Mirai training path unless this project needs a custom sweep.</p>
          </div>
          <StatusPill tone={championActive ? 'green' : trainingRequest ? 'amber' : preprocessingApproved ? 'slate' : 'slate'}>{championActive ? 'champion loaded' : trainingCompleted ? 'ready to load champion' : trainingRequest ? 'request ready' : 'not started'}</StatusPill>
        </div>

        <div className="mt-5 grid gap-4 xl:grid-cols-2">
          <div className="border-t border-slate-400/[0.07] pt-4 text-sm text-slate-300">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-2xl">
                <div className="flex flex-wrap items-center gap-2"><span className="font-semibold text-white">1. Create training request</span><StatusPill tone={trainingRequest ? 'green' : mlPreprocessingReady ? 'amber' : 'slate'}>{trainingRequest ? 'ready' : mlPreprocessingReady ? 'available' : 'waiting'}</StatusPill></div>
                <p className="mt-1 leading-6">Locks the approved preprocessing state to a versioned training request. This is required before downloading the full local-training package.</p>
                {trainingRequest && <p className="mt-2 text-[#BDEAFF]">Request: <span className="font-mono">{trainingRequest.training_request_id}</span> · {trainingRequest.model_families.join(', ')}</p>}
                {!mlPreprocessingReady && <p className="mt-2 text-slate-500">Complete ML preprocessing first so training uses <code>model_table_preprocessed.csv</code>.</p>}
              </div>
              <button type="button" onClick={() => selectedSession && runAction('training-request', async () => { const request = await createTrainingRequest(selectedSession, trainingConfig); setTrainingRequest(request); setTrainingStatus(await getTrainingStatus(selectedSession, request.training_request_id)) })} disabled={!recommendedTrainingReady || Boolean(busy)} className="rounded-full bg-slate-950 px-5 py-3 text-xs font-bold tracking-normal text-white shadow-sm shadow-slate-950/20 disabled:opacity-45">
                {busy === 'training-request' ? 'Creating...' : trainingRequest ? 'Request created' : 'Create request'}
              </button>
            </div>
          </div>

          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-2xl">
                <div className="flex flex-wrap items-center gap-2"><span className="font-semibold">2. Download approved training package</span><StatusPill tone={canExportApprovedPackage ? 'green' : 'slate'}>{canExportApprovedPackage ? 'ready' : 'locked'}</StatusPill></div>
                <p className="mt-1 leading-6">Use this package for local or on-premise training while logging remotely. It includes <code>training_manifest.json</code>, schema, ML preprocessing artifacts, and the actual <code>model_table_preprocessed.csv</code>.</p>
                <p className="mt-2 font-semibold leading-6">Do not train from the standalone CSV alone. The manifest prevents logging into the wrong MLflow experiment.</p>
                {exportMessage && <p className="mt-2 text-[#BDEAFF]">{exportMessage}</p>}
              </div>
              <button type="button" onClick={handleExportApprovedPackage} disabled={!canExportApprovedPackage || Boolean(busy)} className="rounded-full bg-slate-950 px-5 py-3 text-xs font-bold tracking-normal text-white shadow-sm shadow-slate-950/20 disabled:opacity-45">
                {busy === 'export-package' ? 'Exporting...' : 'Download package'}
              </button>
            </div>
          </div>

          <div className="border-t border-slate-400/[0.07] pt-4 text-sm text-slate-300">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-2xl">
                <div className="flex flex-wrap items-center gap-2"><span className="font-semibold text-white">3. Optional in-app training</span><StatusPill tone={trainingCompleted ? 'green' : trainingRequest ? 'amber' : 'slate'}>{trainingCompleted ? 'done' : trainingRequest ? 'available' : 'waiting'}</StatusPill></div>
                <p className="mt-1 leading-6">Run Mirai’s managed training path from the approved request. For local remote-MLflow training, download the package instead and run the local command.</p>
              </div>
              <button type="button" onClick={() => selectedSession && trainingRequest && runAction('training', async () => { setTrainingStatus(await startTrainingRequest(selectedSession, trainingRequest.training_request_id)) })} disabled={!trainingRequest || trainingCompleted || Boolean(busy)} className="rounded-full border border-slate-950 bg-[#0B1220] px-5 py-3 text-xs font-bold tracking-normal text-white disabled:opacity-45">
                {busy === 'training' ? 'Training...' : trainingCompleted ? 'Training complete' : 'Start in-app training'}
              </button>
            </div>
          </div>

          <div className="border-t border-slate-400/[0.07] pt-4 text-sm text-slate-300">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-2xl">
                <div className="flex flex-wrap items-center gap-2"><span className="font-semibold text-white">4. Load promoted MLflow champion</span><StatusPill tone={championActive ? 'green' : canUseProjectChampionLoader ? 'amber' : 'slate'}>{championActive ? 'active' : canUseProjectChampionLoader ? 'available' : 'waiting'}</StatusPill></div>
                <p className="mt-1 leading-6">Expected MLflow experiment: <code>{expectedMlflowExperiment}</code>. Registered model: <code>{expectedRegisteredModel}</code>. Promote the approved version to <code>champion</code>, then load it here.</p>
              </div>
            </div>
          </div>
        </div>

        {canUseProjectChampionLoader && (
          <div className="mt-4 border-t border-slate-400/[0.07] pt-4 text-sm text-slate-300">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-2xl">
                <div className="flex flex-wrap items-center gap-2"><span className="font-semibold text-white">Load champion model</span><span className="rounded-full bg-amber-100 px-2 py-1 text-[10px] font-bold tracking-normal text-amber-800">App dev step</span></div>
                <p className="mt-1 leading-6">After local or on-prem training, promote the approved MLflow model version to <code>champion</code>, then load it here. Mirai verifies identity, required artifacts, ONNX serving, and activates the champion in one step. This project-level loader is available even when the current browser session does not have a Mirai training request cached.</p>
                <p className="mt-1 text-xs font-semibold tracking-normal text-slate-500">Optional fields must match the current MLflow champion for this project.</p>
                {importMessage && <p className="mt-2 text-[#74C7F5]">{importMessage}</p>}
              </div>
              <div className="grid w-full gap-3 lg:w-[30rem]">
                <input value={mlflowImport.runId} onChange={(event) => setMlflowImport((current) => ({ ...current, runId: event.target.value }))} placeholder="Champion MLflow run ID optional" className="rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-[#74C7F5]" />
                <div className="grid gap-3 md:grid-cols-2">
                  <input value={mlflowImport.modelVersion} onChange={(event) => setMlflowImport((current) => ({ ...current, modelVersion: event.target.value }))} placeholder="Champion version optional" className="rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-[#74C7F5]" />
                  <input value={mlflowImport.registeredModelName} onChange={(event) => setMlflowImport((current) => ({ ...current, registeredModelName: event.target.value }))} placeholder="Model name optional" className="rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-[#74C7F5]" />
                </div>
                <button type="button" onClick={handleLoadChampionModel} disabled={Boolean(busy)} className="rounded-full border border-slate-950 bg-[#0B1220] px-5 py-3 text-xs font-bold tracking-normal text-white disabled:opacity-45">
                  {busy === 'load-champion-model' ? 'Loading...' : 'Load champion model'}
                </button>
              </div>
            </div>
          </div>
        )}
        {championActive && (
          <div className="mt-4 rounded-lg border border-[#74C7F5]/30 bg-[#0D1B2D] p-4 text-sm text-[#BDEAFF]">
            <div className="font-semibold">Approved champion active</div>
            <div className="mt-1">Champion model: {String((trainingStatus?.mlflow as Record<string, unknown> | undefined)?.model_name ?? '—')}</div>
          </div>
        )}
        {trainingCompleted && !candidateReady && !championActive && (
          <div className="mt-4 rounded-lg border border-[#74C7F5]/30 bg-[#0D1B2D] p-4 text-sm text-[#BDEAFF]">
            <div className="font-semibold">Training completed</div>
            <div className="mt-1">Best model: {String((trainingStatus?.result as Record<string, unknown> | undefined)?.best_model_name ?? (trainingStatus?.mlflow as Record<string, unknown> | undefined)?.model_name ?? '—')}</div>
          </div>
        )}

        <div className="mt-5">
          <DisclosurePanel title="Advanced settings">
            <div className="grid gap-3 md:grid-cols-3">
              <label className="text-sm font-semibold text-slate-300">Search mode<select value={trainingConfig.search.mode} onChange={(event) => setTrainingConfig((current) => ({ ...current, search: { ...current.search, mode: event.target.value } }))} className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2"><option value="single_config">single_config</option><option value="small_sweep_1h">small_sweep_1h</option><option value="balanced_sweep_2h">balanced_sweep_2h</option></select></label>
              <label className="text-sm font-semibold text-slate-300">Budget minutes<input type="number" value={trainingConfig.search.wall_clock_budget_minutes} onChange={(event) => setTrainingConfig((current) => ({ ...current, search: { ...current.search, wall_clock_budget_minutes: Number(event.target.value) || 60 } }))} className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2" /></label>
              <label className="text-sm font-semibold text-slate-300">Seeds<input value={trainingConfig.mlp.seeds.join(',')} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, seeds: parseNumberList(event.target.value).map((value) => Math.round(value)) } }))} className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2" /></label>
            </div>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <div className="border-t border-slate-400/[0.07] pt-4">
                <h3 className="font-semibold text-white">Linear baselines</h3>
                <div className="mt-3 grid gap-3">
                  <label className="flex items-center gap-2 text-sm font-semibold text-slate-300"><input type="checkbox" checked={trainingConfig.linear.include_mvlr} onChange={(event) => setTrainingConfig((current) => ({ ...current, linear: { ...current.linear, include_mvlr: event.target.checked } }))} /> Include MVLR</label>
                  <label className="flex items-center gap-2 text-sm font-semibold text-slate-300"><input type="checkbox" checked={trainingConfig.linear.include_ridge} onChange={(event) => setTrainingConfig((current) => ({ ...current, linear: { ...current.linear, include_ridge: event.target.checked } }))} /> Include Ridge</label>
                  <label className="text-sm font-semibold text-slate-300">Ridge alphas<input value={trainingConfig.linear.ridge_alphas.join(',')} onChange={(event) => setTrainingConfig((current) => ({ ...current, linear: { ...current.linear, ridge_alphas: parseNumberList(event.target.value) } }))} className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2" /></label>
                </div>
              </div>
              <div className="border-t border-slate-400/[0.07] pt-4">
                <h3 className="font-semibold text-white">MLP</h3>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <label className="text-sm font-semibold text-slate-300">Architecture<select value={trainingConfig.mlp.architecture_family} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, architecture_family: event.target.value } }))} className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2"><option value="plain_mlp">plain_mlp</option><option value="shared_trunk_multi_head">shared_trunk_multi_head</option></select></label>
                  <label className="text-sm font-semibold text-slate-300">Hidden layers<input value={trainingConfig.mlp.hidden_layers.join(',')} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, hidden_layers: parseNumberList(event.target.value).map((value) => Math.round(value)) } }))} className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2" /></label>
                  <label className="text-sm font-semibold text-slate-300">Learning rate<input type="number" step="0.0001" value={trainingConfig.mlp.learning_rate} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, learning_rate: Number(event.target.value) || 0.003 } }))} className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2" /></label>
                  <label className="text-sm font-semibold text-slate-300">Max epochs<input type="number" value={trainingConfig.mlp.max_epochs} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, max_epochs: Number(event.target.value) || 500 } }))} className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2" /></label>
                </div>
              </div>
            </div>
          </DisclosurePanel>
        </div>
      </SectionCard>

      <div className="space-y-3">
        <DisclosurePanel title="Session tools">
          {selectedSession ? (
            <div>
              <div className="grid gap-3 md:grid-cols-3">
                <div className="border-t border-slate-400/[0.07] pt-4 text-sm"><div className="font-semibold text-white">Project ID</div><div className="mt-1 break-all text-slate-300">{selectedSession.project_id}</div></div>
                <div className="border-t border-slate-400/[0.07] pt-4 text-sm"><div className="font-semibold text-white">Dataset</div><div className="mt-1 break-all text-slate-300">{selectedSession.dataset_id}</div></div>
                <div className="border-t border-slate-400/[0.07] pt-4 text-sm"><div className="font-semibold text-white">Session</div><div className="mt-1 break-all text-slate-300">{selectedSession.ingestion_session_id}</div></div>
              </div>
              <div className="mt-4 flex flex-wrap gap-3">
                <input type="file" multiple onChange={(event) => setAppendFiles(Array.from(event.target.files ?? []))} className="min-w-[18rem] flex-1 border-y border-slate-400/[0.10] px-4 py-3 text-sm text-slate-300" />
                <button type="button" onClick={handleAppendFiles} disabled={!appendFiles.length || Boolean(busy)} className="rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white shadow-sm shadow-slate-950/20 disabled:opacity-45">{busy === 'append-files' ? 'Appending...' : 'Append files'}</button>
              </div>
            </div>
          ) : <div className="text-sm text-slate-500">Select a session first.</div>}
        </DisclosurePanel>
      </div>
    </div>
  )
}
