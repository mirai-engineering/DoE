import { type Dispatch, type ReactNode, type SetStateAction, useCallback, useEffect, useMemo, useState } from 'react'
import type {
  DomainMetadataStatus,
  IngestionSessionResponse,
  MLPreprocessingReport,
  MLPreprocessingStatus,
  MiraiContractValidation,
  PreprocessingEdaSummary,
  PreprocessingStatus,
  ProjectDomainMetadata,
  ProjectSchema,
  TrainingConfiguration,
  TrainingRequestResponse,
  VariableMetadata,
} from '../lib/api'
import {
  appendIngestionFiles,
  approveDomainMetadata,
  approveMLPreprocessing,
  approvePreprocessing,
  createTrainingRequest,
  executeMLPreprocessing,
  exportApprovedTrainingPackage,
  getDomainMetadata,
  getMLPreprocessedTableBlob,
  getMLPreprocessingHumanReportBlob,
  getMLPreprocessingReport,
  getMLPreprocessingStatus,
  getPreprocessingEdaSummary,
  getPreprocessingReport,
  getPreprocessingStatus,
  getPreprocessingYdataReportBlob,
  getTrainingStatus,
  listIngestionSessions,
  listTrainingRequests,
  loadChampionModel,
  startMLPreprocessing,
  startMiraiPreprocessing,
  startTrainingRequest,
  updateDomainMetadata,
  validateMiraiContract,
} from '../lib/api'
import {
  artifactDisplayName,
  derivePreparationViewModel,
  preparationStatusLabel,
  preparationStatusTone,
  type PreparationFacts,
  type PreparationTab,
} from '../lib/preparationPresentation'
import { AskMiraiWorkspace } from './preparation/AskMiraiWorkspace'
import { PreparationTabs } from './preparation/PreparationTabs'
import { DisclosurePanel, EmptyState, StatusBadge, TechnicalDetails } from './ui'

const EDITABLE_METADATA_ROLES = new Set<VariableMetadata['role']>(['input', 'output', 'group', 'sweep', 'time', 'cycle', 'sequence', 'curve_axis'])
const INTERNAL_NAME_PATTERNS = [
  /(^|_)(id|uuid|hash)$/i,
  /(^|_)(experiment|condition|result|row|source|file|path|provenance)(_id|_index|_name|_path|_hash)?$/i,
  /^(experiment_id|condition_id|result_id|row_index|source_file|source_path|split)$/i,
]

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function formatNumber(value: unknown, digits = 0): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: digits }) : '—'
}

function cloneMetadata(metadata: ProjectDomainMetadata): ProjectDomainMetadata {
  return JSON.parse(JSON.stringify(metadata)) as ProjectDomainMetadata
}

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
    description: `Safe response plot using ${x?.label || xVariable} on the x-axis and ${y?.label || yVariable} on the y-axis.`,
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
  return value.split(',').map((item) => Number(item.trim())).filter((item) => Number.isFinite(item))
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
  const [trainingRequest, setTrainingRequest] = useState<TrainingRequestResponse | null>(null)
  const [trainingStatus, setTrainingStatus] = useState<Record<string, unknown> | null>(null)
  const [exportMessage, setExportMessage] = useState<string | null>(null)
  const [importMessage, setImportMessage] = useState<string | null>(null)
  const [mlflowImport, setMlflowImport] = useState({ runId: '', registeredModelName: '', modelVersion: '' })
  const [trainingConfig, setTrainingConfig] = useState<TrainingConfiguration>(() => defaultTrainingConfiguration(schema ?? { project_id: '', display_name: '', inputs: [], outputs: [] }))
  const [metadataStatus, setMetadataStatus] = useState<DomainMetadataStatus | null>(null)
  const [metadataDraft, setMetadataDraft] = useState<ProjectDomainMetadata | null>(null)
  const [appendFiles, setAppendFiles] = useState<File[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<PreparationTab>('overview')
  const [contextualPrompt, setContextualPrompt] = useState('')

  const selectedSession = useMemo(() => sessions.find((session) => session.ingestion_session_id === selectedSessionId) ?? null, [sessions, selectedSessionId])

  const loadSessions = useCallback(async () => {
    setError(null)
    const next = await listIngestionSessions(schema?.project_id)
    setSessions(next)
    const latestRaw = window.localStorage.getItem('mirai.latestIngestionSession')
    const latest = latestRaw ? JSON.parse(latestRaw) as IngestionSessionResponse : null
    const preferred = latest && next.some((session) => session.ingestion_session_id === latest.ingestion_session_id) ? latest.ingestion_session_id : next[0]?.ingestion_session_id ?? ''
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
      setMLPreprocessingReport(nextMLStatus.status !== 'not_started' ? await getMLPreprocessingReport(session).catch(() => null) : null)
      if (['preprocessing_complete_needs_approval', 'approved_for_training'].includes(nextStatus.status)) {
        const [nextReport, nextEda, requests] = await Promise.all([
          getPreprocessingReport(session),
          getPreprocessingEdaSummary(session),
          listTrainingRequests(session),
        ])
        setReport(nextReport)
        setEdaSummary(nextEda)
        const latestRequest = [...requests].sort((a, b) => String(b.requested_at ?? '').localeCompare(String(a.requested_at ?? '')))[0] ?? null
        setTrainingRequest(latestRequest)
        setTrainingStatus(latestRequest ? await getTrainingStatus(session, latestRequest.training_request_id) : null)
      } else {
        setReport(null)
        setEdaSummary(null)
        setTrainingRequest(null)
        setTrainingStatus(null)
      }
    } catch (refreshError) {
      setReport(null)
      setEdaSummary(null)
      setTrainingRequest(null)
      setTrainingStatus(null)
      setError(refreshError instanceof Error ? refreshError.message : 'Unable to refresh preparation state')
    }
  }, [])

  useEffect(() => { if (schema) setTrainingConfig(defaultTrainingConfiguration(schema)) }, [schema])
  useEffect(() => { loadSessions().catch((loadError) => setError(loadError instanceof Error ? loadError.message : 'Unable to load sessions')) }, [loadSessions])
  useEffect(() => { if (selectedSession) void refreshSessionState(selectedSession) }, [refreshSessionState, selectedSession])
  useEffect(() => {
    if (!selectedSession || !['queued', 'running'].includes(preprocessingStatus.status)) return undefined
    const timer = window.setInterval(() => void refreshSessionState(selectedSession), 2500)
    return () => window.clearInterval(timer)
  }, [refreshSessionState, selectedSession, preprocessingStatus.status])

  async function runAction(label: string, action: () => Promise<void>) {
    if (busy) return
    setBusy(label)
    setError(null)
    try { await action() }
    catch (actionError) { setError(actionError instanceof Error ? actionError.message : `${label} failed`) }
    finally { setBusy(null) }
  }

  const rowCounts = preprocessingStatus.row_counts ?? {}
  const modelRows = numberValue(edaSummary?.summary.model_rows) ?? numberValue(rowCounts.model_table) ?? numberValue(rowCounts['model_table.csv'])
  const rejectedRows = numberValue(edaSummary?.summary.rejected_rows?.count) ?? numberValue(rowCounts['rejected_rows.csv'])
  const preprocessingApproved = preprocessingStatus.status === 'approved_for_training' || report?.status === 'approved_for_training'
  const preprocessingComplete = preprocessingStatus.status === 'preprocessing_complete_needs_approval' || preprocessingApproved
  const metadataApproved = metadataStatus?.approval_status === 'approved' || preprocessingComplete
  const metadataVariables = metadataDraft?.variables ?? []
  const editableVariableEntries = metadataVariables.map((variable, index) => ({ variable, index })).filter(({ variable }) => isEditableModelVariable(variable))
  const provenanceVariableEntries = metadataVariables.map((variable, index) => ({ variable, index })).filter(({ variable }) => !isEditableModelVariable(variable))
  const inputVariables = editableVariableEntries.filter(({ variable }) => ['input', 'sweep'].includes(variable.role))
  const outputVariables = editableVariableEntries.filter(({ variable }) => variable.role === 'output')
  const selectedRecipe = metadataDraft?.ui_config?.plot_recipes?.find((recipe) => recipe.id === metadataDraft.ui_config?.selected_plot_recipe_id) ?? metadataDraft?.ui_config?.plot_recipes?.[0]
  const selectedX = (selectedRecipe?.x?.variable && inputVariables.some(({ variable }) => variable.name === selectedRecipe.x?.variable) ? selectedRecipe.x.variable : undefined) || inputVariables[0]?.variable.name || ''
  const selectedY = (selectedRecipe?.y?.variable && outputVariables.some(({ variable }) => variable.name === selectedRecipe.y?.variable) ? selectedRecipe.y.variable : undefined) || outputVariables[0]?.variable.name || ''
  const lifecycleStatus = String(trainingStatus?.status ?? trainingRequest?.status ?? '')
  const candidateReady = lifecycleStatus === 'candidate_ready_for_review'
  const championActive = lifecycleStatus === 'approved_champion_active'
  const trainingCompleted = lifecycleStatus === 'completed' || candidateReady || championActive
  const mlPreprocessingReady = mlPreprocessingStatus.status === 'ml_preprocessing_ready_for_training'
  const mlPreprocessingStarted = Boolean(mlPreprocessingStatus.status && mlPreprocessingStatus.status !== 'not_started')
  const canRunPreprocessing = Boolean(selectedSession && metadataApproved && !['queued', 'running'].includes(preprocessingStatus.status))
  const recommendedTrainingReady = Boolean(selectedSession && preprocessingApproved && mlPreprocessingReady && !trainingRequest)
  const canExportApprovedPackage = Boolean(selectedSession && preprocessingApproved && trainingRequest)
  const canUseProjectChampionLoader = Boolean(schema?.project_id && !championActive && (mlPreprocessingReady || preprocessingApproved || trainingRequest || trainingCompleted || !selectedSession))
  const expectedMlflowExperiment = schema?.project_id || selectedSession?.project_id || '<project_id>'
  const expectedRegisteredModel = expectedMlflowExperiment !== '<project_id>' ? `doe_surrogate_${expectedMlflowExperiment}` : 'doe_surrogate_<project_id>'
  const facts: PreparationFacts = {
    hasSchema: Boolean(schema),
    hasSession: Boolean(selectedSession),
    metadataApproved,
    preprocessingStatus: preprocessingStatus.status,
    preprocessingComplete,
    preprocessingApproved,
    mlPreprocessingStatus: mlPreprocessingStatus.status,
    mlPreprocessingStarted,
    mlPreprocessingReady,
    hasTrainingRequest: Boolean(trainingRequest),
    trainingStatus: lifecycleStatus,
    trainingCompleted,
    candidateReady,
    championActive,
  }
  const viewModel = derivePreparationViewModel(facts)
  const inputCount = validation?.input_count ?? inputVariables.length
  const outputCount = validation?.output_count ?? outputVariables.length
  const artifacts = Array.from(new Set([...(edaSummary?.artifacts.canonical_files ?? []), ...(mlPreprocessingReport?.export_files ?? [])]))

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
      draft.ui_config = { ...(draft.ui_config ?? {}), selected_plot_recipe_id: recipe.id, plot_recipes: [recipe], design_studio: { ...(draft.ui_config?.design_studio ?? {}), primary_plot_recipe_id: recipe.id } }
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
      await refreshSessionState(updated)
    })
  }

  async function runCanonicalPreprocessing() {
    if (!selectedSession) return
    await runAction('preprocessing', async () => setPreprocessingStatus(await startMiraiPreprocessing(selectedSession)))
  }

  async function approveCanonicalPreprocessing() {
    if (!selectedSession) return
    await runAction('approval', async () => {
      setReport(await approvePreprocessing(selectedSession, 'Approved from Preprocessing Review UI.'))
      await refreshSessionState(selectedSession)
    })
  }

  async function draftMLPreprocessingPlan() {
    if (!selectedSession) return
    await runAction('ml-preprocessing-draft', async () => {
      setMLPreprocessingLog(['Loading bounded dataset evidence…', 'Drafting reproducible preprocessing recommendations…'])
      const drafted = await startMLPreprocessing(selectedSession)
      setMLPreprocessingStatus(drafted)
      setMLPreprocessingReport(await getMLPreprocessingReport(selectedSession))
      setMLPreprocessingLog((current) => [...current, 'Plan drafted and validation gates checked.', 'Waiting for review before applying.'])
    })
  }

  async function applyMLPreprocessingPlan() {
    if (!selectedSession) return
    await runAction('ml-preprocessing-apply', async () => {
      setMLPreprocessingLog((current) => [...current, 'Approving plan and fitting parameters on training rows only…'])
      setMLPreprocessingStatus(await approveMLPreprocessing(selectedSession, 'Approved deterministic ML preprocessing plan from Preprocessing Review UI.'))
      setMLPreprocessingStatus(await executeMLPreprocessing(selectedSession))
      setMLPreprocessingReport(await getMLPreprocessingReport(selectedSession))
      setMLPreprocessingLog((current) => [...current, 'Training-ready dataset created.'])
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

  async function handleOpenYdataReport() {
    if (!selectedSession) return
    const popup = window.open('', '_blank')
    if (popup) popup.opener = null
    await runAction('open-ydata-report', async () => {
      try {
        const { blob } = await getPreprocessingYdataReportBlob(selectedSession)
        const url = window.URL.createObjectURL(new Blob([blob], { type: 'text/html' }))
        if (popup) popup.location.href = url
        else window.open(url, '_blank', 'noopener,noreferrer')
        window.setTimeout(() => window.URL.revokeObjectURL(url), 60_000)
      } catch (reportError) { popup?.close(); throw reportError }
    })
  }

  async function handleDownloadPreprocessedTable() {
    if (!selectedSession) return
    await runAction('download-ml-preprocessed-table', async () => { const file = await getMLPreprocessedTableBlob(selectedSession); downloadBlob(file.blob, file.filename) })
  }

  async function handleDownloadMLPreprocessingReport() {
    if (!selectedSession) return
    await runAction('download-ml-preprocessing-report', async () => { const file = await getMLPreprocessingHumanReportBlob(selectedSession); downloadBlob(file.blob, file.filename) })
  }

  async function createVersionedTrainingRequest() {
    if (!selectedSession) return
    await runAction('training-request', async () => {
      const request = await createTrainingRequest(selectedSession, trainingConfig)
      setTrainingRequest(request)
      setTrainingStatus(await getTrainingStatus(selectedSession, request.training_request_id))
    })
  }

  async function startManagedTraining() {
    if (!selectedSession || !trainingRequest) return
    await runAction('training', async () => setTrainingStatus(await startTrainingRequest(selectedSession, trainingRequest.training_request_id)))
  }

  async function handleExportApprovedPackage() {
    if (!selectedSession || !trainingRequest) return
    await runAction('export-package', async () => {
      await exportApprovedTrainingPackage(selectedSession, trainingRequest.training_request_id)
      setExportMessage('Approved training package downloaded.')
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

  function openAskMirai(prompt: string) {
    setContextualPrompt(prompt)
    setActiveTab('ask-mirai')
  }

  function handlePrimaryAction() {
    setActiveTab(viewModel.action.destination)
    if (!viewModel.action.enabled || busy) return
    if (viewModel.action.kind === 'run_preprocessing' && !preprocessingStatus.status.includes('failed') && !['queued', 'running'].includes(preprocessingStatus.status)) void runCanonicalPreprocessing()
    if (viewModel.action.kind === 'draft_ml_plan') void draftMLPreprocessingPlan()
    if (viewModel.action.kind === 'create_training_request') void createVersionedTrainingRequest()
    if (viewModel.action.kind === 'load_champion') void handleLoadChampionModel()
    if (viewModel.action.kind === 'open_model_quality') onOpenModelQuality?.()
  }

  return (
    <div className="min-w-0 space-y-5">
      <PreparationHeader
        sessions={sessions}
        selectedSessionId={selectedSessionId}
        onSessionChange={setSelectedSessionId}
        onRefresh={() => void refreshSessionState(selectedSession)}
        busy={Boolean(busy)}
        modelRows={modelRows}
        rejectedRows={rejectedRows}
        inputCount={inputCount}
        outputCount={outputCount}
        viewModel={viewModel}
        onPrimaryAction={handlePrimaryAction}
      />

      {error && <div role="alert" className="bg-red-500/10 px-3 py-2 text-sm text-red-100">{error}</div>}
      <PreparationTabs activeTab={activeTab} onChange={setActiveTab} />

      <TabPanel tab="overview" activeTab={activeTab}>
        <OverviewTab
          session={selectedSession}
          facts={facts}
          modelRows={modelRows}
          rejectedRows={rejectedRows}
          inputCount={inputCount}
          outputCount={outputCount}
          validation={validation}
          artifacts={artifacts}
          viewModel={viewModel}
          onPrimaryAction={handlePrimaryAction}
          onNavigate={setActiveTab}
          appendFiles={appendFiles}
          onAppendFilesChange={setAppendFiles}
          onAppendFiles={handleAppendFiles}
          busy={busy}
        />
      </TabPanel>

      <TabPanel tab="variables" activeTab={activeTab}>
        <VariablesTab
          metadataStatus={metadataStatus}
          metadataApproved={metadataApproved}
          editableVariables={editableVariableEntries}
          provenanceVariables={provenanceVariableEntries}
          inputVariables={inputVariables}
          outputVariables={outputVariables}
          selectedX={selectedX}
          selectedY={selectedY}
          onUpdateVariable={updateVariable}
          onUpdateRecipe={updatePrimaryRecipe}
          onSave={() => void saveMetadataDraft()}
          onApprove={() => void approveMetadataDraft()}
          onAsk={openAskMirai}
          disabled={!selectedSession || Boolean(busy)}
          busy={busy}
        />
      </TabPanel>

      <TabPanel tab="preprocessing" activeTab={activeTab}>
        <PreprocessingTab
          selectedSession={selectedSession}
          validation={validation}
          preprocessingStatus={preprocessingStatus}
          preprocessingComplete={preprocessingComplete}
          preprocessingApproved={preprocessingApproved}
          canRunPreprocessing={canRunPreprocessing}
          modelRows={modelRows}
          rejectedRows={rejectedRows}
          edaSummary={edaSummary}
          mlStatus={mlPreprocessingStatus}
          mlReport={mlPreprocessingReport}
          mlStarted={mlPreprocessingStarted}
          mlReady={mlPreprocessingReady}
          mlLog={mlPreprocessingLog}
          busy={busy}
          onRunCanonical={() => void runCanonicalPreprocessing()}
          onApproveCanonical={() => void approveCanonicalPreprocessing()}
          onOpenEda={() => void handleOpenYdataReport()}
          onDraftPlan={() => void draftMLPreprocessingPlan()}
          onApplyPlan={() => void applyMLPreprocessingPlan()}
          onDownloadReport={() => void handleDownloadMLPreprocessingReport()}
          onDownloadTable={() => void handleDownloadPreprocessedTable()}
          onAsk={openAskMirai}
        />
      </TabPanel>

      <TabPanel tab="training" activeTab={activeTab}>
        <TrainingTab
          selectedSession={selectedSession}
          trainingRequest={trainingRequest}
          trainingStatus={trainingStatus}
          trainingConfig={trainingConfig}
          setTrainingConfig={setTrainingConfig}
          recommendedTrainingReady={recommendedTrainingReady}
          canExportPackage={canExportApprovedPackage}
          trainingCompleted={trainingCompleted}
          championActive={championActive}
          canLoadChampion={canUseProjectChampionLoader}
          busy={busy}
          exportMessage={exportMessage}
          importMessage={importMessage}
          mlflowImport={mlflowImport}
          setMlflowImport={setMlflowImport}
          expectedMlflowExperiment={expectedMlflowExperiment}
          expectedRegisteredModel={expectedRegisteredModel}
          onCreateRequest={() => void createVersionedTrainingRequest()}
          onExportPackage={() => void handleExportApprovedPackage()}
          onStartTraining={() => void startManagedTraining()}
          onLoadChampion={() => void handleLoadChampionModel()}
          onOpenModelQuality={onOpenModelQuality}
          onAsk={openAskMirai}
        />
      </TabPanel>

      <TabPanel tab="ask-mirai" activeTab={activeTab}>
        {schema ? <AskMiraiWorkspace projectId={schema.project_id} projectName={schema.display_name} session={selectedSession} facts={facts} usableRows={modelRows} inputCount={inputCount} outputCount={outputCount} artifacts={artifacts} variableLabels={editableVariableEntries.map(({ variable }) => variable.label || variable.name)} contextualPrompt={contextualPrompt} onNavigate={setActiveTab} /> : <EmptyState title="Project context unavailable" description="Select a project before asking Mirai about preparation evidence." />}
      </TabPanel>
    </div>
  )
}

function PreparationHeader({ sessions, selectedSessionId, onSessionChange, onRefresh, busy, modelRows, rejectedRows, inputCount, outputCount, viewModel, onPrimaryAction }: {
  sessions: IngestionSessionResponse[]
  selectedSessionId: string
  onSessionChange: (value: string) => void
  onRefresh: () => void
  busy: boolean
  modelRows: number | null
  rejectedRows: number | null
  inputCount: number
  outputCount: number
  viewModel: ReturnType<typeof derivePreparationViewModel>
  onPrimaryAction: () => void
}) {
  return (
    <header className="border-b border-white/[0.10] pb-5">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div className="min-w-0">
          <h1 className="text-3xl font-semibold tracking-[-0.045em] text-white">Prepare for training</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-[#B8C2D4]">Review the dataset, approve preprocessing decisions, and create a reproducible training package.</p>
          <p className="mt-3 flex flex-wrap gap-x-2 gap-y-1 text-sm text-[#9FB0C8]">
            <span>{modelRows === null ? 'Usable rows pending' : `${modelRows.toLocaleString()} usable rows`}</span><span>·</span>
            <span>{inputCount} inputs</span><span>·</span><span>{outputCount} outputs</span><span>·</span>
            <span>{rejectedRows === null ? 'Rejected rows pending' : rejectedRows === 0 ? 'No rejected rows' : `${rejectedRows.toLocaleString()} rejected rows`}</span>
          </p>
        </div>
        <div className="grid w-full gap-3 sm:grid-cols-[minmax(0,1fr)_auto] xl:w-[34rem]">
          <label className="min-w-0 text-xs font-medium text-[#9FB0C8]">Dataset session
            <select value={selectedSessionId} onChange={(event) => onSessionChange(event.target.value)} className="mt-1.5 w-full min-w-0 truncate rounded-md border border-white/[0.10] bg-[#050914] px-3 py-2 text-sm text-white">
              <option value="">No sessions found</option>
              {sessions.map((session) => <option key={session.ingestion_session_id} value={session.ingestion_session_id}>{session.project_name} · {session.dataset_id}</option>)}
            </select>
          </label>
          <button type="button" onClick={onRefresh} disabled={!selectedSessionId || busy} className="self-end rounded-md border border-white/[0.12] px-3 py-2 text-sm font-semibold text-slate-200 hover:bg-white/[0.05] disabled:opacity-45">Refresh</button>
        </div>
      </div>
      <div className="mt-5 flex flex-col gap-4 rounded-lg border border-white/[0.10] bg-[#0B1424]/75 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0"><div className="flex items-center gap-2"><StatusBadge tone={viewModel.tone}>{viewModel.displayStatus}</StatusBadge></div><p className="mt-2 text-sm leading-6 text-[#B8C2D4]">{viewModel.explanation}</p></div>
        <button type="button" onClick={onPrimaryAction} disabled={!viewModel.action.enabled || busy} className="shrink-0 rounded-md bg-[#2F6BFF] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#4C7DFF] disabled:cursor-not-allowed disabled:opacity-45">{viewModel.action.label}</button>
      </div>
    </header>
  )
}

function TabPanel({ tab, activeTab, children }: { tab: PreparationTab; activeTab: PreparationTab; children: ReactNode }) {
  return <section id={`preparation-panel-${tab}`} role="tabpanel" aria-labelledby={`preparation-tab-${tab}`} hidden={activeTab !== tab} tabIndex={0}>{children}</section>
}

function OverviewTab({ session, facts, modelRows, rejectedRows, inputCount, outputCount, validation, artifacts, viewModel, onPrimaryAction, onNavigate, appendFiles, onAppendFilesChange, onAppendFiles, busy }: {
  session: IngestionSessionResponse | null
  facts: PreparationFacts
  modelRows: number | null
  rejectedRows: number | null
  inputCount: number
  outputCount: number
  validation: MiraiContractValidation | null
  artifacts: string[]
  viewModel: ReturnType<typeof derivePreparationViewModel>
  onPrimaryAction: () => void
  onNavigate: (tab: PreparationTab) => void
  appendFiles: File[]
  onAppendFilesChange: (files: File[]) => void
  onAppendFiles: () => Promise<void>
  busy: string | null
}) {
  const steps = [
    { label: 'Variables reviewed', done: facts.metadataApproved },
    { label: 'Dataset validated', done: facts.preprocessingApproved },
    { label: 'Training-ready dataset', done: facts.mlPreprocessingReady },
    { label: 'Training request', done: facts.hasTrainingRequest },
    { label: 'Champion active', done: facts.championActive },
  ]
  return (
    <div className="space-y-7 py-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <section>
          <h2 className="text-xl font-semibold text-white">Project readiness</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#B8C2D4]">Mirai turns validated engineering data into a reproducible, approved training asset. Each stage stays reviewable before training begins.</p>
          <ol className="mt-6 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">{steps.map((step, index) => <li key={step.label} className={`rounded-md border px-3 py-3 text-xs font-semibold ${step.done ? 'border-emerald-400/20 bg-emerald-500/[0.07] text-emerald-100' : index === steps.findIndex((item) => !item.done) ? 'border-[#5BA8FF]/35 bg-[#5BA8FF]/10 text-white' : 'border-white/[0.08] text-[#8493AA]'}`}>{step.done ? '✓ ' : `${index + 1}. `}{step.label}</li>)}</ol>
        </section>
        <aside className="border-t border-white/[0.10] pt-5 xl:border-l xl:border-t-0 xl:pl-6 xl:pt-0">
          <p className="text-xs font-medium text-[#9FB0C8]">Recommended next step</p>
          <p className="mt-2 text-lg font-semibold text-white">{viewModel.action.label}</p>
          <p className="mt-2 text-sm leading-6 text-[#B8C2D4]">{viewModel.blocker ?? 'No blocking issue is currently reported.'}</p>
          <button type="button" onClick={onPrimaryAction} disabled={!viewModel.action.enabled || Boolean(busy)} className="mt-4 rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{viewModel.action.label}</button>
        </aside>
      </div>

      <section className="grid gap-x-6 gap-y-5 border-y border-white/[0.10] py-5 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Usable rows" value={modelRows === null ? 'Pending' : modelRows.toLocaleString()} />
        <Metric label="Rejected rows" value={rejectedRows === null ? 'Pending' : rejectedRows.toLocaleString()} />
        <Metric label="Inputs" value={String(inputCount)} />
        <Metric label="Outputs" value={String(outputCount)} />
        <Metric label="Contract" value={validation?.valid ? 'Valid' : validation ? 'Needs attention' : 'Pending'} />
      </section>

      <div className="grid gap-7 lg:grid-cols-2">
        <section>
          <div className="flex items-center justify-between gap-3"><h2 className="text-lg font-semibold text-white">Preparation record</h2><button type="button" onClick={() => onNavigate('preprocessing')} className="text-sm font-semibold text-[#8FCBFF]">View preprocessing</button></div>
          <dl className="mt-4 divide-y divide-white/[0.08] text-sm"><SummaryRow label="Dataset session" value={session?.dataset_id ?? 'Not selected'} /><SummaryRow label="Variable metadata" value={facts.metadataApproved ? 'Approved' : 'Needs review'} /><SummaryRow label="Validated dataset" value={preparationStatusLabel(facts.preprocessingStatus)} /><SummaryRow label="Training-ready dataset" value={preparationStatusLabel(facts.mlPreprocessingStatus)} /><SummaryRow label="Training" value={preparationStatusLabel(facts.trainingStatus)} /></dl>
        </section>
        <section>
          <h2 className="text-lg font-semibold text-white">Available artifacts</h2>
          {artifacts.length ? <ul className="mt-4 divide-y divide-white/[0.08] text-sm text-[#B8C2D4]">{artifacts.slice(0, 6).map((artifact) => <li key={artifact} className="py-2.5"><span className="font-medium text-white">{artifactDisplayName(artifact)}</span><span className="mt-0.5 block truncate text-xs text-[#8493AA]" title={artifact}>{artifact}</span></li>)}</ul> : <p className="mt-4 text-sm text-[#9FB0C8]">Artifacts will appear after dataset preparation begins.</p>}
        </section>
      </div>

      <DisclosurePanel title="Session tools">
        {session ? <div><div className="grid gap-3 sm:grid-cols-3"><TechnicalValue label="Project ID" value={session.project_id} /><TechnicalValue label="Dataset ID" value={session.dataset_id} /><TechnicalValue label="Session ID" value={session.ingestion_session_id} /></div><div className="mt-4 flex flex-col gap-3 sm:flex-row"><input type="file" multiple onChange={(event) => onAppendFilesChange(Array.from(event.target.files ?? []))} className="min-w-0 flex-1 rounded-md border border-white/[0.10] px-3 py-2 text-sm" /><button type="button" onClick={() => void onAppendFiles()} disabled={!appendFiles.length || Boolean(busy)} className="rounded-md border border-white/[0.12] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'append-files' ? 'Appending…' : 'Append files'}</button></div></div> : <p>Select a session first.</p>}
      </DisclosurePanel>
    </div>
  )
}

function VariablesTab({ metadataStatus, metadataApproved, editableVariables, provenanceVariables, inputVariables, outputVariables, selectedX, selectedY, onUpdateVariable, onUpdateRecipe, onSave, onApprove, onAsk, disabled, busy }: {
  metadataStatus: DomainMetadataStatus | null
  metadataApproved: boolean
  editableVariables: Array<{ variable: VariableMetadata; index: number }>
  provenanceVariables: Array<{ variable: VariableMetadata; index: number }>
  inputVariables: Array<{ variable: VariableMetadata; index: number }>
  outputVariables: Array<{ variable: VariableMetadata; index: number }>
  selectedX: string
  selectedY: string
  onUpdateVariable: (index: number, patch: Partial<VariableMetadata>) => void
  onUpdateRecipe: (x: string, y: string) => void
  onSave: () => void
  onApprove: () => void
  onAsk: (prompt: string) => void
  disabled: boolean
  busy: string | null
}) {
  return (
    <div className="space-y-6 py-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><h2 className="text-xl font-semibold text-white">Variables</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-[#B8C2D4]">Review variable roles, labels, and units before preprocessing. Internal identifiers remain stable throughout training.</p></div><StatusBadge tone={metadataApproved ? 'success' : 'warning'}>{metadataApproved ? 'Approved' : preparationStatusLabel(metadataStatus?.approval_status)}</StatusBadge></div>
      <div className="grid gap-4 sm:grid-cols-3"><Metric label="Model inputs" value={String(inputVariables.length)} /><Metric label="Model outputs" value={String(outputVariables.length)} /><Metric label="Context/provenance" value={String(provenanceVariables.length)} /></div>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm font-medium text-slate-200">Primary x-axis<select value={selectedX} onChange={(event) => onUpdateRecipe(event.target.value, selectedY)} disabled={!inputVariables.length || !selectedY} className="mt-2 w-full rounded-md border border-white/[0.10] bg-[#050914] px-3 py-2"><option value="">Select input</option>{inputVariables.map(({ variable }) => <option key={variable.name} value={variable.name}>{variable.label || variable.name}</option>)}</select></label>
        <label className="text-sm font-medium text-slate-200">Primary y-axis<select value={selectedY} onChange={(event) => onUpdateRecipe(selectedX, event.target.value)} disabled={!outputVariables.length || !selectedX} className="mt-2 w-full rounded-md border border-white/[0.10] bg-[#050914] px-3 py-2"><option value="">Select output</option>{outputVariables.map(({ variable }) => <option key={variable.name} value={variable.name}>{variable.label || variable.name}</option>)}</select></label>
      </div>
      <div className="overflow-x-auto rounded-md border border-white/[0.10]">
        <table className="min-w-[760px] w-full text-left text-sm"><thead className="bg-white/[0.035] text-xs text-[#9FB0C8]"><tr><th className="px-3 py-3">Variable</th><th className="px-3 py-3">Display label</th><th className="px-3 py-3">Unit</th><th className="px-3 py-3">Role</th><th className="px-3 py-3">Context</th></tr></thead><tbody className="divide-y divide-white/[0.08]">{editableVariables.map(({ variable, index }) => <tr key={`${variable.name}-${index}`}><td className="px-3 py-3"><span className="block font-medium text-white">{variable.label || variable.name}</span><span className="mt-1 block font-mono text-xs text-[#8493AA]">{variable.source_name || variable.name}</span></td><td className="px-3 py-3"><input value={variable.label || ''} onChange={(event) => onUpdateVariable(index, { label: event.target.value, ui_label: event.target.value })} className="w-full rounded-md border border-white/[0.10] px-3 py-2" /></td><td className="px-3 py-3"><input value={variable.unit || ''} onChange={(event) => onUpdateVariable(index, { unit: event.target.value })} className="w-28 rounded-md border border-white/[0.10] px-3 py-2" /></td><td className="px-3 py-3"><select value={variable.role} onChange={(event) => onUpdateVariable(index, { role: event.target.value as VariableMetadata['role'] })} className="rounded-md border border-white/[0.10] px-3 py-2"><RoleOptions /></select></td><td className="px-3 py-3"><button type="button" onClick={() => onAsk(`Explain the role and preprocessing considerations for ${variable.label || variable.name}.`)} className="text-xs font-semibold text-[#8FCBFF]">Ask Mirai</button></td></tr>)}{!editableVariables.length && <tr><td colSpan={5} className="px-3 py-8 text-center text-[#9FB0C8]">No editable modeling variables were detected.</td></tr>}</tbody></table>
      </div>
      {!!provenanceVariables.length && <DisclosurePanel title={`Context and provenance fields (${provenanceVariables.length})`}><p className="mb-3 leading-6">These read-only IDs, joins, split columns, and source fields are excluded from editable model inputs.</p><div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead className="text-[#9FB0C8]"><tr><th className="py-2 pr-4">Field</th><th className="py-2 pr-4">Source</th><th className="py-2 pr-4">Role</th></tr></thead><tbody className="divide-y divide-white/[0.08]">{provenanceVariables.map(({ variable }) => <tr key={variable.name}><td className="py-2 pr-4 font-medium text-white">{variable.label || variable.name}</td><td className="py-2 pr-4">{variable.source_name || variable.name}</td><td className="py-2 pr-4">{preparationStatusLabel(variable.role)}</td></tr>)}</tbody></table></div></DisclosurePanel>}
      <div className="flex flex-wrap justify-end gap-3 border-t border-white/[0.10] pt-5"><button type="button" onClick={onSave} disabled={disabled} className="rounded-md border border-white/[0.12] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'metadata-save' ? 'Saving…' : 'Save draft'}</button><button type="button" onClick={onApprove} disabled={disabled} className="rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'metadata-approval' ? 'Approving…' : 'Approve variables'}</button></div>
    </div>
  )
}

function PreprocessingTab({ selectedSession, validation, preprocessingStatus, preprocessingComplete, preprocessingApproved, canRunPreprocessing, modelRows, rejectedRows, edaSummary, mlStatus, mlReport, mlStarted, mlReady, mlLog, busy, onRunCanonical, onApproveCanonical, onOpenEda, onDraftPlan, onApplyPlan, onDownloadReport, onDownloadTable, onAsk }: {
  selectedSession: IngestionSessionResponse | null
  validation: MiraiContractValidation | null
  preprocessingStatus: PreprocessingStatus
  preprocessingComplete: boolean
  preprocessingApproved: boolean
  canRunPreprocessing: boolean
  modelRows: number | null
  rejectedRows: number | null
  edaSummary: PreprocessingEdaSummary | null
  mlStatus: MLPreprocessingStatus
  mlReport: MLPreprocessingReport | null
  mlStarted: boolean
  mlReady: boolean
  mlLog: string[]
  busy: string | null
  onRunCanonical: () => void
  onApproveCanonical: () => void
  onOpenEda: () => void
  onDraftPlan: () => void
  onApplyPlan: () => void
  onDownloadReport: () => void
  onDownloadTable: () => void
  onAsk: (prompt: string) => void
}) {
  const warnings = [...(edaSummary?.summary.leakage_warnings ?? []), ...(mlReport?.warnings ?? []), ...(mlReport?.risks ?? [])]
  const missingEntries = Object.entries(edaSummary?.summary.missingness ?? {}).filter(([, count]) => count > 0)
  return (
    <div className="space-y-8 py-6">
      <div><h2 className="text-xl font-semibold text-white">Preprocessing</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-[#B8C2D4]">Mirai uses the dataset analysis to recommend reproducible preprocessing steps, with parameters fitted on training rows only.</p></div>

      <PreparationStage number={1} title="Validate and prepare the engineering dataset" status={preprocessingStatus.status} current={!preprocessingApproved}>
        <p className="text-sm leading-6 text-[#B8C2D4]">Creates the canonical validated dataset, rejected-row record, split evidence, and analysis artifacts.</p>
        {!preprocessingComplete && <div className="mt-4"><button type="button" onClick={onRunCanonical} disabled={!canRunPreprocessing || Boolean(busy)} className="rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'preprocessing' ? 'Preparing…' : ['queued', 'running'].includes(preprocessingStatus.status) ? 'Preparation in progress' : 'Run preprocessing'}</button>{validation?.errors?.length ? <ul className="mt-3 text-sm text-red-100">{validation.errors.map((item) => <li key={item}>{item}</li>)}</ul> : null}</div>}
        {preprocessingComplete && <div className="mt-5 space-y-5"><div className="grid gap-4 sm:grid-cols-4"><Metric label="Usable rows" value={formatNumber(modelRows)} /><Metric label="Rejected rows" value={formatNumber(rejectedRows)} /><Metric label="Inputs" value={formatNumber(validation?.input_count)} /><Metric label="Outputs" value={formatNumber(validation?.output_count)} /></div><div className="grid gap-3 lg:grid-cols-2">{rejectedRows !== null && <DecisionStory finding={rejectedRows === 0 ? 'No rows were rejected.' : `${rejectedRows.toLocaleString()} rows were rejected.`} recommendation={rejectedRows === 0 ? 'Proceed with the validated row set.' : 'Review rejection reasons before approval.'} effect="Approval confirms which rows are eligible for downstream preparation." safeguard={edaSummary?.summary.split_strategy ? `Split strategy: ${edaSummary.summary.split_strategy}` : 'Split evidence is available in technical details.'} />}{missingEntries.length > 0 && <DecisionStory finding={`${missingEntries.length} variables contain missing values.`} recommendation="Review the model-preparation plan for the proposed handling." effect="Only approved, reproducible handling is applied to the training-ready dataset." safeguard="Fitted preprocessing parameters use training rows only." />}</div>{warnings.length > 0 && <div className="bg-amber-500/10 px-3 py-3 text-sm text-amber-100"><p className="font-semibold">Items requiring attention</p><ul className="mt-2 list-disc space-y-1 pl-5">{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}<div className="flex flex-wrap gap-3">{!preprocessingApproved && <button type="button" onClick={onApproveCanonical} disabled={Boolean(busy)} className="rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'approval' ? 'Approving…' : 'Approve validated dataset'}</button>}<button type="button" onClick={onOpenEda} disabled={!selectedSession || Boolean(busy)} className="rounded-md border border-white/[0.12] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'open-ydata-report' ? 'Opening…' : 'Open analysis report'}</button><button type="button" onClick={() => onAsk(rejectedRows ? 'Why were rows rejected, and what evidence supports those decisions?' : 'Summarize the dataset analysis and leakage safeguards.')} className="rounded-md px-4 py-2 text-sm font-semibold text-[#8FCBFF]">Ask Mirai</button></div><TechnicalDetails><TechnicalGrid eda={edaSummary} status={preprocessingStatus} /></TechnicalDetails></div>}
      </PreparationStage>

      <PreparationStage number={2} title="Create the training-ready dataset" status={mlStatus.status} current={preprocessingApproved && !mlReady} locked={!preprocessingApproved}>
        {!preprocessingApproved ? <p className="text-sm text-[#9FB0C8]">Approve the validated dataset before drafting model-preparation recommendations.</p> : <><p className="text-sm leading-6 text-[#B8C2D4]">{mlReport?.summary ?? mlStatus.summary ?? 'Draft a reproducible preprocessing plan from the approved dataset evidence.'}</p><div className="mt-4 flex flex-wrap gap-3">{!mlStarted && <button type="button" onClick={onDraftPlan} disabled={Boolean(busy)} className="rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'ml-preprocessing-draft' ? 'Drafting…' : 'Draft preprocessing plan'}</button>}{mlStarted && !mlReady && <button type="button" onClick={onApplyPlan} disabled={Boolean(busy)} className="rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'ml-preprocessing-apply' ? 'Applying…' : 'Approve & apply plan'}</button>}{mlStarted && <button type="button" onClick={onDownloadReport} disabled={Boolean(busy)} className="rounded-md border border-white/[0.12] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'download-ml-preprocessed-report' ? 'Downloading…' : 'Download plan report'}</button>}{mlReady && <button type="button" onClick={onDownloadTable} disabled={Boolean(busy)} className="rounded-md border border-white/[0.12] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'download-ml-preprocessed-table' ? 'Downloading…' : 'Download training-ready dataset'}</button>}<button type="button" onClick={() => onAsk(mlReady ? 'Compare the validated and training-ready datasets.' : 'Explain the proposed preprocessing plan and its leakage safeguards.')} className="rounded-md px-4 py-2 text-sm font-semibold text-[#8FCBFF]">Ask Mirai</button></div>{mlStarted && <div className="mt-5 grid gap-3 lg:grid-cols-2"><DecisionStory finding={mlReport?.summary ?? preparationStatusLabel(mlStatus.status)} recommendation={mlReady ? 'Use the approved training-ready dataset for versioned training.' : 'Review and approve the deterministic plan.'} effect={mlReady ? 'The training asset is reproducible from its approved plan and fitted parameters.' : 'Applying the plan creates the dataset used by training.'} safeguard="Parameters are fitted on training rows, then applied without refitting to validation and test rows." approval={preparationStatusLabel(mlStatus.status)} /></div>}{mlLog.length > 0 && <TechnicalDetails><ul className="space-y-1 font-mono text-xs">{mlLog.map((line, index) => <li key={`${line}-${index}`}>› {line}</li>)}</ul>{mlReport?.export_files?.length ? <div className="mt-4"><p className="font-semibold text-white">Generated artifacts</p><ul className="mt-2 space-y-1">{mlReport.export_files.map((file) => <li key={file}>{artifactDisplayName(file)} <span className="text-[#8493AA]">({file})</span></li>)}</ul></div> : null}</TechnicalDetails>}</>}
      </PreparationStage>
    </div>
  )
}

function TrainingTab({ selectedSession, trainingRequest, trainingStatus, trainingConfig, setTrainingConfig, recommendedTrainingReady, canExportPackage, trainingCompleted, championActive, canLoadChampion, busy, exportMessage, importMessage, mlflowImport, setMlflowImport, expectedMlflowExperiment, expectedRegisteredModel, onCreateRequest, onExportPackage, onStartTraining, onLoadChampion, onOpenModelQuality, onAsk }: {
  selectedSession: IngestionSessionResponse | null
  trainingRequest: TrainingRequestResponse | null
  trainingStatus: Record<string, unknown> | null
  trainingConfig: TrainingConfiguration
  setTrainingConfig: Dispatch<SetStateAction<TrainingConfiguration>>
  recommendedTrainingReady: boolean
  canExportPackage: boolean
  trainingCompleted: boolean
  championActive: boolean
  canLoadChampion: boolean
  busy: string | null
  exportMessage: string | null
  importMessage: string | null
  mlflowImport: { runId: string; registeredModelName: string; modelVersion: string }
  setMlflowImport: Dispatch<SetStateAction<{ runId: string; registeredModelName: string; modelVersion: string }>>
  expectedMlflowExperiment: string
  expectedRegisteredModel: string
  onCreateRequest: () => void
  onExportPackage: () => void
  onStartTraining: () => void
  onLoadChampion: () => void
  onOpenModelQuality?: () => void
  onAsk: (prompt: string) => void
}) {
  const trainingState = String(trainingStatus?.status ?? trainingRequest?.status ?? 'not_started')
  return (
    <div className="space-y-7 py-6">
      <div><h2 className="text-xl font-semibold text-white">Training</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-[#B8C2D4]">Create a versioned request, choose managed or local/on-premises execution, then activate the model promoted in MLflow.</p></div>
      <div className="space-y-0 border-l border-white/[0.12] pl-5 sm:pl-7">
        <TrainingStage number={1} title="Create a versioned training request" status={trainingRequest ? 'completed' : recommendedTrainingReady ? 'available' : 'waiting'} current={!trainingRequest}>
          <p>Locks the approved dataset, preprocessing plan, and training configuration into one reproducible request.</p>{trainingRequest && <p className="mt-2 text-xs text-[#9FB0C8]">Request <span className="font-mono text-slate-200">{trainingRequest.training_request_id}</span> · {trainingRequest.model_families.join(', ')}</p>}<button type="button" onClick={onCreateRequest} disabled={!recommendedTrainingReady || Boolean(busy)} className="mt-4 rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'training-request' ? 'Creating…' : trainingRequest ? 'Request created' : 'Create training request'}</button>
        </TrainingStage>
        <TrainingStage number={2} title="Choose a training path" status={trainingCompleted ? 'completed' : trainingRequest ? trainingState : 'locked'} current={Boolean(trainingRequest && !trainingCompleted)}>
          <div className="grid gap-4 lg:grid-cols-2"><div className="rounded-md border border-white/[0.10] p-4"><h4 className="font-semibold text-white">Mirai-managed training</h4><p className="mt-2 text-sm leading-6 text-[#B8C2D4]">Run the approved request within Mirai using the selected deterministic configuration.</p><button type="button" onClick={onStartTraining} disabled={!trainingRequest || trainingCompleted || Boolean(busy)} className="mt-4 rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'training' ? 'Training…' : trainingCompleted ? 'Training complete' : 'Start managed training'}</button></div><div className="rounded-md border border-white/[0.10] p-4"><h4 className="font-semibold text-white">Local or on-premises</h4><p className="mt-2 text-sm leading-6 text-[#B8C2D4]">Download the same approved package when data or compute must remain in your controlled environment.</p><button type="button" onClick={onExportPackage} disabled={!canExportPackage || Boolean(busy)} className="mt-4 rounded-md border border-white/[0.12] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'export-package' ? 'Downloading…' : 'Download training package'}</button>{exportMessage && <p className="mt-2 text-xs text-emerald-100">{exportMessage}</p>}</div></div><button type="button" onClick={() => onAsk('Explain the managed and local/on-premises training paths for this project.')} className="mt-3 text-sm font-semibold text-[#8FCBFF]">Ask Mirai about training paths</button>
        </TrainingStage>
        <TrainingStage number={3} title="Load the promoted champion" status={championActive ? 'completed' : canLoadChampion ? 'available' : 'locked'} current={canLoadChampion && !championActive}>
          <p>After review and promotion in MLflow, Mirai verifies the champion artifacts and activates the model for serving.</p>{canLoadChampion && <div className="mt-4 grid gap-3 lg:grid-cols-3"><input value={mlflowImport.runId} onChange={(event) => setMlflowImport((current) => ({ ...current, runId: event.target.value }))} placeholder="Champion run ID (optional)" className="rounded-md border border-white/[0.10] px-3 py-2" /><input value={mlflowImport.modelVersion} onChange={(event) => setMlflowImport((current) => ({ ...current, modelVersion: event.target.value }))} placeholder="Version (optional)" className="rounded-md border border-white/[0.10] px-3 py-2" /><input value={mlflowImport.registeredModelName} onChange={(event) => setMlflowImport((current) => ({ ...current, registeredModelName: event.target.value }))} placeholder="Model name (optional)" className="rounded-md border border-white/[0.10] px-3 py-2" /></div>}<div className="mt-4 flex flex-wrap gap-3">{canLoadChampion && <button type="button" onClick={onLoadChampion} disabled={Boolean(busy)} className="rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white disabled:opacity-45">{busy === 'load-champion-model' ? 'Loading…' : 'Load champion model'}</button>}{championActive && onOpenModelQuality && <button type="button" onClick={onOpenModelQuality} className="rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white">Open model quality</button>}</div>{importMessage && <p className="mt-3 text-sm text-emerald-100">{importMessage}</p>}<TechnicalDetails><p>Expected MLflow experiment: <code>{expectedMlflowExperiment}</code></p><p>Registered model: <code>{expectedRegisteredModel}</code></p><p>Current status: <code>{trainingState}</code></p></TechnicalDetails>
        </TrainingStage>
      </div>
      <DisclosurePanel title="Advanced training settings"><AdvancedTrainingSettings config={trainingConfig} setConfig={setTrainingConfig} /></DisclosurePanel>
      {!selectedSession && <p className="text-sm text-amber-100">No local preparation session is available. The project-level champion loader remains available when a champion has already been promoted.</p>}
    </div>
  )
}

function AdvancedTrainingSettings({ config, setConfig }: { config: TrainingConfiguration; setConfig: Dispatch<SetStateAction<TrainingConfiguration>> }) {
  return <div className="grid gap-5"><div className="grid gap-3 md:grid-cols-3"><label>Search mode<select value={config.search.mode} onChange={(event) => setConfig((current) => ({ ...current, search: { ...current.search, mode: event.target.value } }))} className="mt-2 w-full rounded-md border border-white/[0.10] px-3 py-2"><option value="single_config">Single configuration</option><option value="small_sweep_1h">Small one-hour sweep</option><option value="balanced_sweep_2h">Balanced two-hour sweep</option></select></label><label>Budget minutes<input type="number" value={config.search.wall_clock_budget_minutes} onChange={(event) => setConfig((current) => ({ ...current, search: { ...current.search, wall_clock_budget_minutes: Number(event.target.value) || 60 } }))} className="mt-2 w-full rounded-md border border-white/[0.10] px-3 py-2" /></label><label>Seeds<input value={config.mlp.seeds.join(',')} onChange={(event) => setConfig((current) => ({ ...current, mlp: { ...current.mlp, seeds: parseNumberList(event.target.value).map(Math.round) } }))} className="mt-2 w-full rounded-md border border-white/[0.10] px-3 py-2" /></label></div><div className="grid gap-4 border-t border-white/[0.10] pt-4 md:grid-cols-2"><div className="space-y-3"><p className="font-semibold text-white">Linear baselines</p><label className="flex items-center gap-2"><input type="checkbox" checked={config.linear.include_mvlr} onChange={(event) => setConfig((current) => ({ ...current, linear: { ...current.linear, include_mvlr: event.target.checked } }))} /> Include multivariate linear regression</label><label className="flex items-center gap-2"><input type="checkbox" checked={config.linear.include_ridge} onChange={(event) => setConfig((current) => ({ ...current, linear: { ...current.linear, include_ridge: event.target.checked } }))} /> Include ridge regression</label><label className="block">Ridge alphas<input value={config.linear.ridge_alphas.join(',')} onChange={(event) => setConfig((current) => ({ ...current, linear: { ...current.linear, ridge_alphas: parseNumberList(event.target.value) } }))} className="mt-2 w-full rounded-md border border-white/[0.10] px-3 py-2" /></label></div><div className="grid gap-3 sm:grid-cols-2"><p className="font-semibold text-white sm:col-span-2">Neural network</p><label>Architecture<select value={config.mlp.architecture_family} onChange={(event) => setConfig((current) => ({ ...current, mlp: { ...current.mlp, architecture_family: event.target.value } }))} className="mt-2 w-full rounded-md border border-white/[0.10] px-3 py-2"><option value="plain_mlp">Plain MLP</option><option value="shared_trunk_multi_head">Shared trunk, multiple heads</option></select></label><label>Hidden layers<input value={config.mlp.hidden_layers.join(',')} onChange={(event) => setConfig((current) => ({ ...current, mlp: { ...current.mlp, hidden_layers: parseNumberList(event.target.value).map(Math.round) } }))} className="mt-2 w-full rounded-md border border-white/[0.10] px-3 py-2" /></label><label>Learning rate<input type="number" step="0.0001" value={config.mlp.learning_rate} onChange={(event) => setConfig((current) => ({ ...current, mlp: { ...current.mlp, learning_rate: Number(event.target.value) || 0.003 } }))} className="mt-2 w-full rounded-md border border-white/[0.10] px-3 py-2" /></label><label>Maximum epochs<input type="number" value={config.mlp.max_epochs} onChange={(event) => setConfig((current) => ({ ...current, mlp: { ...current.mlp, max_epochs: Number(event.target.value) || 500 } }))} className="mt-2 w-full rounded-md border border-white/[0.10] px-3 py-2" /></label></div></div></div>
}

function PreparationStage({ number, title, status, current, locked = false, children }: { number: number; title: string; status: string; current: boolean; locked?: boolean; children: ReactNode }) {
  return <section className={`rounded-lg border p-5 sm:p-6 ${current ? 'border-[#5BA8FF]/30 bg-[#0B1424]/70' : 'border-white/[0.09]'} ${locked ? 'opacity-65' : ''}`}><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-lg font-semibold text-white"><span className="mr-2 text-[#74C7F5]">{number}.</span>{title}</h3><StatusBadge tone={locked ? 'neutral' : preparationStatusTone(status)}>{locked ? 'Locked' : preparationStatusLabel(status)}</StatusBadge></div><div className="mt-4">{children}</div></section>
}

function TrainingStage({ number, title, status, current, children }: { number: number; title: string; status: string; current: boolean; children: ReactNode }) {
  return <section className={`relative pb-8 pl-2 last:pb-0 ${current ? '' : 'opacity-80'}`}><span className={`absolute -left-[2.1rem] top-0 grid h-7 w-7 place-items-center rounded-full text-xs font-semibold ring-1 ${status === 'completed' ? 'bg-emerald-500/15 text-emerald-100 ring-emerald-400/25' : current ? 'bg-[#2F6BFF] text-white ring-[#74C7F5]/40' : 'bg-[#0B1220] text-[#8493AA] ring-white/15'}`}>{status === 'completed' ? '✓' : number}</span><div className={`rounded-lg p-5 ${current ? 'bg-[#0B1424]/75 ring-1 ring-[#5BA8FF]/25' : ''}`}><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-lg font-semibold text-white">{title}</h3><StatusBadge tone={preparationStatusTone(status)}>{preparationStatusLabel(status)}</StatusBadge></div><div className="mt-3 text-sm leading-6 text-[#B8C2D4]">{children}</div></div></section>
}

function DecisionStory({ finding, recommendation, effect, safeguard, approval }: { finding: string; recommendation: string; effect: string; safeguard: string; approval?: string }) {
  return <article className="rounded-md border border-white/[0.10] p-4"><dl className="space-y-3 text-sm"><DecisionLine label="Finding" value={finding} /><DecisionLine label="Recommendation" value={recommendation} /><DecisionLine label="Expected effect" value={effect} /><DecisionLine label="Leakage safeguard" value={safeguard} />{approval && <DecisionLine label="Approval" value={approval} />}</dl></article>
}

function DecisionLine({ label, value }: { label: string; value: string }) { return <div><dt className="text-xs font-medium text-[#9FB0C8]">{label}</dt><dd className="mt-1 leading-6 text-slate-100">{value}</dd></div> }
function Metric({ label, value }: { label: string; value: string }) { return <div className="min-w-0"><p className="text-xs font-medium text-[#9FB0C8]">{label}</p><p className="mt-1 truncate text-xl font-semibold text-white" title={value}>{value}</p></div> }
function SummaryRow({ label, value }: { label: string; value: string }) { return <div className="flex items-center justify-between gap-4 py-3"><dt className="text-[#9FB0C8]">{label}</dt><dd className="text-right font-medium text-white">{value}</dd></div> }
function TechnicalValue({ label, value }: { label: string; value: string }) { return <div><p className="text-xs text-[#9FB0C8]">{label}</p><p className="mt-1 break-all font-mono text-xs text-slate-200">{value}</p></div> }
function RoleOptions() { return <><option value="input">Model input</option><option value="output">Model output</option><option value="group">Group</option><option value="sweep">Sweep variable</option><option value="time">Time</option><option value="cycle">Cycle</option><option value="sequence">Sequence</option><option value="curve_axis">Curve axis</option></> }
function TechnicalGrid({ eda, status }: { eda: PreprocessingEdaSummary | null; status: PreprocessingStatus }) { return <div className="grid gap-4 sm:grid-cols-2"><TechnicalValue label="Split strategy" value={eda?.summary.split_strategy ?? 'Pending'} /><TechnicalValue label="BO policy" value={eda?.summary.bo_policy ?? 'Pending'} /><TechnicalValue label="EDA artifact" value={eda?.artifacts.eda_report_json ?? 'Pending'} /><TechnicalValue label="Preprocessing report" value={eda?.artifacts.preprocessing_report_json ?? status.report_path ?? 'Pending'} /></div> }
