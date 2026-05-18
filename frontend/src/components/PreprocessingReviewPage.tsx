import { useEffect, useMemo, useState } from 'react'
import type { DomainMetadataStatus, FuelCellPackageValidation, IngestionSessionResponse, PreprocessingEdaSummary, PreprocessingStatus, ProjectDomainMetadata, ProjectSchema, TrainingConfiguration, TrainingRequestResponse, VariableMetadata } from '../lib/api'
import {
  appendIngestionFiles,
  approveDomainMetadata,
  approvePreprocessing,
  createTrainingRequest,
  getDomainMetadata,
  getPreprocessingEdaSummary,
  getPreprocessingReport,
  getPreprocessingStatus,
  getTrainingStatus,
  listIngestionSessions,
  listTrainingRequests,
  preprocessingYdataReportUrl,
  startFuelCellPreprocessing,
  startTrainingRequest,
  updateDomainMetadata,
  validateFuelCellPackage,
} from '../lib/api'

function StatusPill({ children, tone = 'slate' }: { children: string; tone?: 'slate' | 'amber' | 'green' | 'rose' }) {
  const classes = tone === 'green'
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : tone === 'amber'
      ? 'border-amber-200 bg-amber-50 text-amber-700'
      : tone === 'rose'
        ? 'border-rose-200 bg-rose-50 text-rose-700'
        : 'border-slate-200 bg-slate-50 text-slate-600'
  return <span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-[0.14em] ${classes}`}>{children}</span>
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
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <h3 className="font-semibold text-slate-950">{title}</h3>
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="text-slate-500"><tr><th className="py-2 pr-4">Variable</th><th className="py-2 pr-4">Min</th><th className="py-2 pr-4">Mean</th><th className="py-2 pr-4">Max</th><th className="py-2 pr-4">Missing</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {entries.map(([name, stats]) => <tr key={name}><td className="py-2 pr-4 font-medium text-slate-800">{name}</td><td className="py-2 pr-4 text-slate-600">{formatNumber(stats.min)}</td><td className="py-2 pr-4 text-slate-600">{formatNumber(stats.mean)}</td><td className="py-2 pr-4 text-slate-600">{formatNumber(stats.max)}</td><td className="py-2 pr-4 text-slate-600">{formatNumber(stats.missing, 0)}</td></tr>)}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function PreprocessingReviewPage({ schema, onOpenModelQuality }: { schema: ProjectSchema; onOpenModelQuality?: () => void }) {
  const [sessions, setSessions] = useState<IngestionSessionResponse[]>([])
  const [selectedSessionId, setSelectedSessionId] = useState('')
  const [validation, setValidation] = useState<FuelCellPackageValidation | null>(null)
  const [preprocessingStatus, setPreprocessingStatus] = useState<PreprocessingStatus>({ status: 'not_started' })
  const [report, setReport] = useState<Record<string, unknown> | null>(null)
  const [edaSummary, setEdaSummary] = useState<PreprocessingEdaSummary | null>(null)
  const [trainingRequest, setTrainingRequest] = useState<TrainingRequestResponse | null>(null)
  const [trainingStatus, setTrainingStatus] = useState<Record<string, unknown> | null>(null)
  const [trainingConfig, setTrainingConfig] = useState<TrainingConfiguration>(() => defaultTrainingConfiguration(schema))
  const [metadataStatus, setMetadataStatus] = useState<DomainMetadataStatus | null>(null)
  const [metadataDraft, setMetadataDraft] = useState<ProjectDomainMetadata | null>(null)
  const [appendFiles, setAppendFiles] = useState<File[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const selectedSession = useMemo(
    () => sessions.find((session) => session.ingestion_session_id === selectedSessionId) ?? null,
    [sessions, selectedSessionId],
  )

  async function loadSessions() {
    setError(null)
    const next = await listIngestionSessions()
    setSessions(next)
    const latestRaw = window.localStorage.getItem('mirai.latestIngestionSession')
    const latest = latestRaw ? JSON.parse(latestRaw) as IngestionSessionResponse : null
    const preferred = latest && next.some((session) => session.ingestion_session_id === latest.ingestion_session_id)
      ? latest.ingestion_session_id
      : next[0]?.ingestion_session_id ?? ''
    setSelectedSessionId((current) => current || preferred)
  }

  async function refreshSessionState(session = selectedSession) {
    if (!session) return
    setError(null)
    try {
      const [nextValidation, nextStatus, nextMetadata] = await Promise.all([
        validateFuelCellPackage(session),
        getPreprocessingStatus(session),
        getDomainMetadata(session),
      ])
      setValidation(nextValidation)
      setPreprocessingStatus(nextStatus)
      setMetadataStatus(nextMetadata)
      setMetadataDraft(cloneMetadata(nextMetadata.domain_metadata))
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
  }

  useEffect(() => {
    setTrainingConfig(defaultTrainingConfiguration(schema))
  }, [schema.project_id])

  useEffect(() => {
    loadSessions().catch((loadError) => setError(loadError instanceof Error ? loadError.message : 'Unable to load sessions'))
  }, [])

  useEffect(() => {
    if (selectedSession) refreshSessionState(selectedSession)
  }, [selectedSessionId])

  useEffect(() => {
    if (!selectedSession || !['queued', 'running'].includes(preprocessingStatus.status)) return undefined
    const timer = window.setInterval(() => {
      refreshSessionState(selectedSession)
    }, 2500)
    return () => window.clearInterval(timer)
  }, [selectedSessionId, selectedSession, preprocessingStatus.status])

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
  const metadataApproved = metadataStatus?.approval_status === 'approved'
  const metadataVariables = metadataDraft?.variables ?? []
  const inputOrSweepVariables = metadataVariables.filter((variable) => ['input', 'sweep'].includes(variable.role))
  const outputVariables = metadataVariables.filter((variable) => variable.role === 'output')
  const selectedRecipe = metadataDraft?.ui_config?.plot_recipes?.find((recipe) => recipe.id === metadataDraft.ui_config?.selected_plot_recipe_id) ?? metadataDraft?.ui_config?.plot_recipes?.[0]
  const selectedX = selectedRecipe?.x?.variable || inputOrSweepVariables[0]?.name || metadataVariables[0]?.name || ''
  const selectedY = selectedRecipe?.y?.variable || outputVariables[0]?.name || metadataVariables.find((variable) => variable.role === 'output')?.name || ''
  const trainingCompleted = trainingStatus?.['status'] === 'completed'

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

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border border-white/70 bg-white/90 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#60745c]">Preprocessing Review</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.055em] text-slate-950">Approve fuel-cell preprocessing before training</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              Select the uploaded fuel-cell package, unpack Cell archives, generate canonical model tables, approve preprocessing, then start synchronous training.
            </p>
          </div>
          <StatusPill tone={actionTone(preprocessingStatus.status)}>{preprocessingStatus.status || 'not_started'}</StatusPill>
        </div>
      </section>

      <section className="rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-[18rem] flex-1">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#60745c]">Uploaded session</p>
            <select value={selectedSessionId} onChange={(event) => setSelectedSessionId(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none focus:border-[#60745c]">
              <option value="">No ingestion sessions found</option>
              {sessions.map((session) => (
                <option key={session.ingestion_session_id} value={session.ingestion_session_id}>{session.project_name} · {session.ingestion_session_id}</option>
              ))}
            </select>
          </div>
          <button type="button" onClick={() => refreshSessionState()} disabled={!selectedSession || Boolean(busy)} className="rounded-full border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 disabled:opacity-45">Refresh</button>
        </div>
        {selectedSession && (
          <>
          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <div className="rounded-2xl border border-slate-200 bg-[#fbfaf5] p-4 text-sm"><div className="font-semibold text-slate-950">Project</div><div className="mt-1 break-all text-slate-600">{selectedSession.project_id}</div></div>
            <div className="rounded-2xl border border-slate-200 bg-[#fbfaf5] p-4 text-sm"><div className="font-semibold text-slate-950">Dataset</div><div className="mt-1 break-all text-slate-600">{selectedSession.dataset_id}</div></div>
            <div className="rounded-2xl border border-slate-200 bg-[#fbfaf5] p-4 text-sm"><div className="font-semibold text-slate-950">Files</div><div className="mt-1 text-slate-600">{selectedSession.files.length} uploaded</div></div>
            <div className="rounded-2xl border border-slate-200 bg-[#fbfaf5] p-4 text-sm"><div className="font-semibold text-slate-950">Cell zips</div><div className="mt-1 text-slate-600">{validation?.cell_archive_count ?? 0}</div></div>
          </div>
          <div className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-[#fbfaf5] p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="font-semibold text-slate-950">Forgot a file?</h3>
                <p className="mt-1 text-sm text-slate-600">Append missing `Cell_NN.zip`, manifest, dictionary, or workbook files to this same ingestion session before rerunning preprocessing.</p>
              </div>
              <StatusPill tone="amber">Invalidates preprocessing</StatusPill>
            </div>
            <div className="mt-3 flex flex-wrap gap-3">
              <input type="file" multiple onChange={(event) => setAppendFiles(Array.from(event.target.files ?? []))} className="min-w-[18rem] flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600" />
              <button type="button" onClick={handleAppendFiles} disabled={!appendFiles.length || Boolean(busy)} className="rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-950/20 disabled:opacity-45">
                {busy === 'append-files' ? 'Appending...' : 'Append files'}
              </button>
            </div>
          </div>
          </>
        )}
      </section>

      {error && <section className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</section>}

      {preprocessingComplete && (
        <section className="rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#60745c]">EDA before approval</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950">Preprocessing evidence</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">Review row counts, rejected rows, missingness, split strategy, and variable ranges before approving training. This evidence is generated from the canonical model table.</p>
            </div>
            <StatusPill tone={edaSummary ? 'green' : 'amber'}>{edaSummary ? 'Generated' : 'Refresh evidence'}</StatusPill>
          </div>

          {!edaSummary && (
            <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
              Preprocessing completed, but the EDA summary is not loaded in this browser state yet. Click <strong>Refresh</strong>; approval should be based on this evidence, not just the readiness checklist.
            </div>
          )}

          <div className="mt-5 grid gap-3 md:grid-cols-5">
            {[
              ['Cells succeeded', edaSummary?.summary.cells_succeeded ?? rowCounts.cells_succeeded],
              ['Cells failed', edaSummary?.summary.cells_failed ?? rowCounts.cells_failed],
              ['Extracted files', edaSummary?.summary.extracted_file_count],
              ['Model rows', edaSummary?.summary.model_rows ?? modelRows],
              ['Rejected rows', edaSummary?.summary.rejected_rows?.count ?? rowCounts['rejected_rows.csv']],
            ].map(([label, value]) => (
              <div key={label as string} className="rounded-2xl border border-slate-200 bg-[#fbfaf5] p-4">
                <div className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">{label}</div>
                <div className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950">{formatNumber(value, 0)}</div>
              </div>
            ))}
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <h3 className="font-semibold text-slate-950">Split plan</h3>
              <p className="mt-1 text-sm text-slate-600">{edaSummary?.summary.split_strategy ?? 'See split artifact after refresh'} · BO holdout cells: {formatNumber(edaSummary?.summary.bo_holdout_cell_count, 0)}</p>
              <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                {Object.entries(edaSummary?.summary.split_counts ?? {}).map(([split, count]) => <div key={split} className="rounded-xl bg-[#fbfaf5] px-3 py-2"><span className="font-semibold text-slate-950">{split}</span><span className="float-right text-slate-600">{formatNumber(count, 0)}</span></div>)}
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <h3 className="font-semibold text-slate-950">Rejected-row reasons</h3>
              <div className="mt-3 space-y-2 text-sm">
                {Object.entries(edaSummary?.summary.rejected_rows?.reasons ?? {}).map(([reason, count]) => <div key={reason} className="rounded-xl bg-[#fbfaf5] px-3 py-2"><span className="font-semibold text-slate-950">{reason}</span><span className="float-right text-slate-600">{formatNumber(count, 0)}</span></div>)}
              </div>
            </div>
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <DistributionTable title="Input ranges" rows={edaSummary?.summary.input_distributions} />
            <DistributionTable title="Output ranges" rows={edaSummary?.summary.output_distributions} />
          </div>

          {!!edaSummary?.summary.leakage_warnings?.length && (
            <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4">
              <h3 className="font-semibold text-amber-900">Review warnings</h3>
              <ul className="mt-2 list-disc pl-5 text-sm leading-6 text-amber-800">
                {edaSummary.summary.leakage_warnings.map((warning) => <li key={warning}>{warning}</li>)}
              </ul>
            </div>
          )}

          <div className="mt-5 rounded-2xl border border-slate-200 bg-[#fbfaf5] p-4 text-xs text-slate-600">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="font-semibold text-slate-950">Artifacts</div>
              {selectedSession && (
                <a
                  href={preprocessingYdataReportUrl(selectedSession)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-full bg-slate-950 px-4 py-2 text-xs font-bold uppercase tracking-[0.14em] text-white shadow-lg shadow-slate-950/20"
                >
                  Open ydata HTML EDA ↗
                </a>
              )}
            </div>
            <div className="mt-2 text-slate-500">The HTML report is generated from the canonical model table on first click using ydata-profiling, then cached in the session EDA folder.</div>
            <div className="mt-1 break-all">ydata HTML: {edaSummary?.artifacts.ydata_html_endpoint ?? 'available after refresh'}</div>
            <div className="mt-1 break-all">EDA JSON: {edaSummary?.artifacts.eda_report_json ?? 'available after refresh'}</div>
            <div className="break-all">Split JSON: {edaSummary?.artifacts.split_report_json ?? 'available after refresh'}</div>
            <div className="break-all">Preprocessing report: {edaSummary?.artifacts.preprocessing_report_json ?? preprocessingStatus.report_path ?? 'available after refresh'}</div>
          </div>
        </section>
      )}

      {metadataDraft && (
        <section className="rounded-[2rem] border border-[#d8c99b]/50 bg-[#fffdf7] p-6 shadow-lg shadow-slate-900/5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#60745c]">Metadata & Plot Setup</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950">Approve what this project means</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                Mirai inferred variable roles, labels, units, and safe plot options. Review or edit these before they drive Design Studio, Model Quality, and OEM-facing plots.
              </p>
            </div>
            <StatusPill tone={metadataApproved ? 'green' : metadataStatus?.approval_status === 'draft' ? 'amber' : 'slate'}>{metadataStatus?.approval_status || 'needs review'}</StatusPill>
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-[0.35fr_0.65fr]">
            <label className="text-sm font-semibold text-slate-700">
              Template
              <select
                value={metadataDraft.template_id}
                onChange={(event) => updateMetadataDraft((draft) => { draft.template_id = event.target.value; draft.label = event.target.value === 'fuel_cell' ? 'Fuel cell' : 'Generic tabular DoE' })}
                className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm"
              >
                <option value="fuel_cell">Fuel cell</option>
                <option value="generic_tabular_doe">Generic tabular DoE</option>
              </select>
            </label>
            <div className="rounded-2xl border border-[#d8c99b]/40 bg-white px-4 py-3 text-sm leading-6 text-slate-600">
              <strong className="text-slate-900">Current primary plot:</strong> {selectedRecipe?.label || 'No plot recipe selected'}
              <div className="text-slate-500">{selectedRecipe?.description || 'Choose X and Y variables below to create a safe recommended plot.'}</div>
            </div>
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <label className="text-sm font-semibold text-slate-700">
              X variable
              <select value={selectedX} onChange={(event) => updatePrimaryRecipe(event.target.value, selectedY)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                {metadataVariables.map((variable) => <option key={variable.name} value={variable.name}>{variableLabel(variable)} · {variable.role}</option>)}
              </select>
            </label>
            <label className="text-sm font-semibold text-slate-700">
              Y variable
              <select value={selectedY} onChange={(event) => updatePrimaryRecipe(selectedX, event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                {metadataVariables.map((variable) => <option key={variable.name} value={variable.name}>{variableLabel(variable)} · {variable.role}</option>)}
              </select>
            </label>
          </div>

          <div className="mt-5 overflow-x-auto rounded-2xl border border-slate-200 bg-white">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-[#fbfaf5] text-xs uppercase tracking-[0.14em] text-slate-500">
                <tr><th className="px-3 py-3">Variable</th><th className="px-3 py-3">Label</th><th className="px-3 py-3">Unit</th><th className="px-3 py-3">Role</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {metadataVariables.map((variable, index) => (
                  <tr key={`${variable.name}-${index}`}>
                    <td className="px-3 py-3 font-mono text-xs text-slate-600">{variable.name}</td>
                    <td className="px-3 py-3"><input value={variable.label || ''} onChange={(event) => updateVariable(index, { label: event.target.value })} className="w-full rounded-xl border border-slate-200 px-3 py-2" /></td>
                    <td className="px-3 py-3"><input value={variable.unit || ''} onChange={(event) => updateVariable(index, { unit: event.target.value })} className="w-full rounded-xl border border-slate-200 px-3 py-2" /></td>
                    <td className="px-3 py-3">
                      <select value={variable.role} onChange={(event) => updateVariable(index, { role: event.target.value as VariableMetadata['role'] })} className="w-full rounded-xl border border-slate-200 px-3 py-2">
                        <option value="input">input</option>
                        <option value="output">output</option>
                        <option value="group">group</option>
                        <option value="sweep">sweep</option>
                        <option value="time">time</option>
                        <option value="metadata">metadata</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-5 flex flex-wrap justify-end gap-3">
            <button type="button" disabled={!selectedSession || Boolean(busy)} onClick={saveMetadataDraft} className="rounded-full border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-700 disabled:opacity-45">
              {busy === 'metadata-save' ? 'Saving...' : 'Save metadata draft'}
            </button>
            <button type="button" disabled={!selectedSession || Boolean(busy)} onClick={approveMetadataDraft} className="rounded-full bg-[#526949] px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-[#526949]/20 disabled:opacity-45">
              {busy === 'metadata-approval' ? 'Approving...' : 'Approve metadata & plot setup'}
            </button>
          </div>
        </section>
      )}

      <section className="grid gap-5 lg:grid-cols-[0.95fr_1.05fr]">
        <div className="rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#60745c]">Readiness checklist</p>
          <div className="mt-4 space-y-3">
            <div className="rounded-2xl border border-slate-200 bg-[#fbfaf5] p-4">
              <div className="flex items-center justify-between gap-3"><h3 className="font-semibold text-slate-950">Fuel-cell package</h3><StatusPill tone={validation?.valid ? 'green' : 'amber'}>{validation?.valid ? 'Valid' : 'Needs attention'}</StatusPill></div>
              <p className="mt-2 text-sm leading-6 text-slate-600">Requires `data_overview.xlsx` plus individual `Cell_NN.zip` files. {validation?.message}</p>
              {!!validation?.errors.length && <ul className="mt-2 list-disc pl-5 text-sm text-amber-700">{validation.errors.map((item) => <li key={item}>{item}</li>)}</ul>}
            </div>
            <div className="rounded-2xl border border-slate-200 bg-[#fbfaf5] p-4">
              <div className="flex items-center justify-between gap-3"><h3 className="font-semibold text-slate-950">Preprocessing artifacts</h3><StatusPill tone={actionTone(preprocessingStatus.status)}>{preprocessingStatus.stage ?? preprocessingStatus.status}</StatusPill></div>
              <p className="mt-2 text-sm leading-6 text-slate-600">Canonical rows: {modelRows ?? 'pending'}. Cell IDs: {preprocessingStatus.cell_ids?.length ?? validation?.cell_ids.length ?? 0}.</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-[#fbfaf5] p-4">
              <div className="flex items-center justify-between gap-3"><h3 className="font-semibold text-slate-950">Admin approval</h3><StatusPill tone={preprocessingApproved ? 'green' : 'slate'}>{preprocessingApproved ? 'Approved' : 'Locked'}</StatusPill></div>
              <p className="mt-2 text-sm leading-6 text-slate-600">Approval unlocks training. Training remains disabled until preprocessing is complete and explicitly approved.</p>
            </div>
          </div>
        </div>

        <div className="space-y-5">
          <div className="rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#60745c]">Training Configuration</p>
            <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-2xl font-semibold tracking-[-0.05em] text-slate-950">Advanced model sweep</h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Edit MVLR/Ridge/MLP hyperparameters before creating the training request. MLflow will register the best validation candidate as challenger; champion remains manual.</p>
              </div>
              <StatusPill tone="amber">{trainingConfig.search.mode}</StatusPill>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <label className="text-sm font-semibold text-slate-700">Search mode<select value={trainingConfig.search.mode} onChange={(event) => setTrainingConfig((current) => ({ ...current, search: { ...current.search, mode: event.target.value } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2"><option value="single_config">single_config</option><option value="small_sweep_1h">small_sweep_1h</option><option value="balanced_sweep_2h">balanced_sweep_2h</option></select></label>
              <label className="text-sm font-semibold text-slate-700">Budget minutes<input type="number" value={trainingConfig.search.wall_clock_budget_minutes} onChange={(event) => setTrainingConfig((current) => ({ ...current, search: { ...current.search, wall_clock_budget_minutes: Number(event.target.value) || 60 } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2" /></label>
              <label className="text-sm font-semibold text-slate-700">Seeds<input value={trainingConfig.mlp.seeds.join(',')} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, seeds: parseNumberList(event.target.value).map((value) => Math.round(value)) } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2" /></label>
            </div>
            <div className="mt-4 rounded-2xl border border-slate-200 bg-[#fbfaf5] p-4">
              <h3 className="font-semibold text-slate-950">Linear baselines</h3>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <label className="flex items-center gap-2 text-sm font-semibold text-slate-700"><input type="checkbox" checked={trainingConfig.linear.include_mvlr} onChange={(event) => setTrainingConfig((current) => ({ ...current, linear: { ...current.linear, include_mvlr: event.target.checked } }))} /> Include MVLR</label>
                <label className="flex items-center gap-2 text-sm font-semibold text-slate-700"><input type="checkbox" checked={trainingConfig.linear.include_ridge} onChange={(event) => setTrainingConfig((current) => ({ ...current, linear: { ...current.linear, include_ridge: event.target.checked } }))} /> Include Ridge</label>
                <label className="text-sm font-semibold text-slate-700 md:col-span-2">Ridge alphas<input value={trainingConfig.linear.ridge_alphas.join(',')} onChange={(event) => setTrainingConfig((current) => ({ ...current, linear: { ...current.linear, ridge_alphas: parseNumberList(event.target.value) } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2" /></label>
              </div>
            </div>
            <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
              <h3 className="font-semibold text-slate-950">MLP hyperparameters</h3>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <label className="text-sm font-semibold text-slate-700">Architecture<select value={trainingConfig.mlp.architecture_family} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, architecture_family: event.target.value } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2"><option value="plain_mlp">plain_mlp</option><option value="shared_trunk_multi_head">shared_trunk_multi_head</option></select></label>
                <label className="text-sm font-semibold text-slate-700">Hidden layers<input value={trainingConfig.mlp.hidden_layers.join(',')} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, hidden_layers: parseNumberList(event.target.value).map((value) => Math.round(value)) } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2" /></label>
                <label className="text-sm font-semibold text-slate-700">Trunk layers<input value={trainingConfig.mlp.trunk_layers.join(',')} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, trunk_layers: parseNumberList(event.target.value).map((value) => Math.round(value)) } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2" /></label>
                <label className="text-sm font-semibold text-slate-700">Head layers<input value={trainingConfig.mlp.head_layers.join(',')} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, head_layers: parseNumberList(event.target.value).map((value) => Math.round(value)) } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2" /></label>
                <label className="text-sm font-semibold text-slate-700">Activation<select value={trainingConfig.mlp.activation} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, activation: event.target.value } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2"><option>SiLU</option><option>GELU</option><option>ReLU</option><option>Tanh</option></select></label>
                <label className="text-sm font-semibold text-slate-700">Normalization<select value={trainingConfig.mlp.normalization} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, normalization: event.target.value } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2"><option value="layer_norm">layer_norm</option><option value="batch_norm">batch_norm</option><option value="none">none</option></select></label>
                <label className="text-sm font-semibold text-slate-700">Dropout<input type="number" step="0.01" value={trainingConfig.mlp.dropout} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, dropout: Number(event.target.value) || 0 } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2" /></label>
                <label className="text-sm font-semibold text-slate-700">Learning rate<input type="number" step="0.0001" value={trainingConfig.mlp.learning_rate} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, learning_rate: Number(event.target.value) || 0.003 } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2" /></label>
                <label className="text-sm font-semibold text-slate-700">Weight decay<input type="number" step="0.00001" value={trainingConfig.mlp.weight_decay} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, weight_decay: Number(event.target.value) || 0 } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2" /></label>
                <label className="text-sm font-semibold text-slate-700">Loss<select value={trainingConfig.mlp.loss} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, loss: event.target.value } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2"><option value="mse">mse</option><option value="smooth_l1">smooth_l1</option><option value="weighted_mse">weighted_mse</option><option value="weighted_smooth_l1">weighted_smooth_l1</option></select></label>
                <label className="text-sm font-semibold text-slate-700">Batch size<input value={String(trainingConfig.mlp.batch_size)} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, batch_size: event.target.value === 'full_batch' ? 'full_batch' : Number(event.target.value) || 'full_batch' } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2" /></label>
                <label className="text-sm font-semibold text-slate-700">Max epochs<input type="number" value={trainingConfig.mlp.max_epochs} onChange={(event) => setTrainingConfig((current) => ({ ...current, mlp: { ...current.mlp, max_epochs: Number(event.target.value) || 500 } }))} className="mt-2 w-full rounded-2xl border border-slate-200 px-3 py-2" /></label>
              </div>
            </div>
          </div>

          <div className="rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#60745c]">Actions</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <button type="button" disabled={!selectedSession || Boolean(busy) || ['queued', 'running'].includes(preprocessingStatus.status)} onClick={() => selectedSession && runAction('preprocessing', async () => { setPreprocessingStatus(await startFuelCellPreprocessing(selectedSession)) })} className="rounded-full bg-slate-950 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-950/20 disabled:opacity-45">{['queued', 'running'].includes(preprocessingStatus.status) ? 'Preprocessing...' : 'Start preprocessing'}</button>
              <button type="button" disabled={!selectedSession || !preprocessingComplete || preprocessingApproved || Boolean(busy)} onClick={() => selectedSession && runAction('approval', async () => { setReport(await approvePreprocessing(selectedSession, 'Approved from Preprocessing Review UI.')); await refreshSessionState(selectedSession) })} className="rounded-full bg-[#526949] px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-[#526949]/20 disabled:opacity-45">Approve preprocessing</button>
              <button type="button" disabled={!selectedSession || !preprocessingApproved || Boolean(busy)} onClick={() => selectedSession && runAction('training-request', async () => { const request = await createTrainingRequest(selectedSession, trainingConfig); setTrainingRequest(request); setTrainingStatus(await getTrainingStatus(selectedSession, request.training_request_id)) })} className="rounded-full border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 disabled:opacity-45">Create training request</button>
              <button type="button" disabled={!selectedSession || !trainingRequest || Boolean(busy)} onClick={() => selectedSession && trainingRequest && runAction('training', async () => { setTrainingStatus(await startTrainingRequest(selectedSession, trainingRequest.training_request_id)) })} className="rounded-full bg-slate-950 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-950/20 disabled:opacity-45">{busy === 'training' ? 'Training...' : 'Start training'}</button>
            </div>
          </div>

          <div className="rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#60745c]">Training request</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950">{trainingRequest ? trainingRequest.training_request_id : 'Locked until approved'}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">Mean baseline, MVLR, and MLP are staged after approval using the default plan above. Training is synchronous for this MVP and activates the latest artifacts for Model Quality.</p>
            {trainingRequest && (
              <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
                <div className="font-semibold">Request staged</div>
                <div className="mt-1">Preset: {trainingRequest.preset}</div>
                <div className="mt-1">Models: {trainingRequest.model_families.join(', ')}</div>
                <div className="mt-1 break-all">Dataset: {trainingRequest.dataset_id}</div>
                <div className="mt-1 break-all">Session: {trainingRequest.ingestion_session_id}</div>
                <div className="mt-1 break-all">MLflow experiment/model: {trainingRequest.project_id}</div>
              </div>
            )}
            {trainingCompleted && (
              <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
                <div className="font-semibold">Training completed</div>
                <div className="mt-1">Best model: {String((trainingStatus?.result as Record<string, unknown> | undefined)?.best_model_name ?? '—')}</div>
                <div className="mt-1 break-all">MLflow experiment/model: {String((trainingStatus?.result as Record<string, unknown> | undefined)?.mlflow_registered_model_name ?? trainingRequest?.project_id ?? '—')}</div>
                <div className="mt-1 break-all">Challenger alias: {String(((trainingStatus?.result as Record<string, unknown> | undefined)?.alias_model as Record<string, unknown> | undefined)?.version ?? '—')}</div>
              </div>
            )}
            {trainingCompleted && <button type="button" onClick={onOpenModelQuality} className="mt-4 inline-flex rounded-full bg-emerald-700 px-4 py-2 text-sm font-semibold text-white">Open Model Quality</button>}
          </div>
        </div>
      </section>

      <section className="rounded-[1.75rem] border border-slate-200 bg-white/85 p-5 text-sm text-slate-600">
        Active context: <span className="font-semibold text-slate-950">{schema.project_id}</span>{selectedSession && selectedSession.project_id !== schema.project_id ? <> · selected session project: <span className="font-semibold text-slate-950">{selectedSession.project_id}</span></> : null}. Uploaded projects keep their own raw, canonical, training, MLflow experiment, and registered-model identity.
      </section>
    </div>
  )
}
