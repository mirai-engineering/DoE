import { FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import type { ProjectSchema } from '../lib/api'
import {
  approveKnowledgeIntakeDraft,
  createKnowledgeIntakeSession,
  downloadKnowledgeIntakePackage,
  exportKnowledgeIntakePackage,
  getKnowledgeIntakeIssues,
  getKnowledgeIntakeSession,
  type KnowledgeIntakeDraft,
  type KnowledgeIntakeFile,
  type KnowledgeIntakeMappingRow,
  type KnowledgeIntakeSession,
  listKnowledgeIntakeSessions,
  matchKnowledgeIntakeMiraiContract,
  rejectKnowledgeIntakeDraft,
  saveKnowledgeIntakeInstruction,
  uploadKnowledgeIntakeFiles,
  uploadKnowledgeIntakeTargetContract,
} from '../lib/api'
import { knowledgeIntakeContractLabel, knowledgeIntakeStatusLabel } from '../lib/knowledgeIntakePresentation'

const defaultInstruction = 'Inspect these sources against the uploaded target Mirai contract, infer a candidate source-to-contract mapping, list missing fields/questions, and run only approved Knowledge Intake transforms that validate as a Mirai package.'

type PendingAction = 'create' | 'upload-contract' | 'upload-sources' | 'mapping' | 'approve' | 'reject' | 'export' | null
type PanelTab = 'sessions' | 'sources'
type Tone = 'neutral' | 'active' | 'success' | 'warning' | 'error'
type PrimaryAction = 'create' | 'show-contract' | 'show-sources' | 'mapping' | 'approve' | 'export'

type MappingStats = {
  totalFields: number
  mappedFields: number
  missingFields: number
  inputTotal: number
  inputMapped: number
  outputTotal: number
  outputMapped: number
}

type IntakeViewModel = {
  status: string
  explanation: string
  tone: Tone
  action: PrimaryAction
  actionLabel: string
  actionEnabled: boolean
  actionHelp?: string
  stages: Array<{ label: string; state: 'complete' | 'current' | 'upcoming' | 'blocked' }>
}

export function KnowledgeIntakePage({ schema, onGoToDataIntake }: { schema: ProjectSchema; onGoToDataIntake: () => void }) {
  const [sessions, setSessions] = useState<KnowledgeIntakeSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState('')
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [selectedTargetFiles, setSelectedTargetFiles] = useState<File[]>([])
  const [instruction, setInstruction] = useState(defaultInstruction)
  const [draft, setDraft] = useState<KnowledgeIntakeDraft | null>(null)
  const [issues, setIssues] = useState('')
  const [pendingAction, setPendingAction] = useState<PendingAction>(null)
  const [loadingLabel, setLoadingLabel] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [panelTab, setPanelTab] = useState<PanelTab>('sessions')
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [selectedFile, setSelectedFile] = useState<KnowledgeIntakeFile | null>(null)
  const [showMapping, setShowMapping] = useState(false)
  const [tableName, setTableName] = useState('experiments.csv')
  const contractInputRef = useRef<HTMLInputElement>(null)
  const sourceInputRef = useRef<HTMLInputElement>(null)
  const loading = pendingAction !== null

  const activeSession = useMemo(() => sessions.find((session) => session.id === activeSessionId) ?? null, [sessions, activeSessionId])

  useEffect(() => {
    void refreshSessions()
    // The project id is the lifecycle boundary; session refresh intentionally resets with it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema.project_id])

  useEffect(() => {
    if (!inspectorOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setInspectorOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [inspectorOpen])

  async function refreshSessions(selectId?: string) {
    setError(null)
    try {
      const next = await listKnowledgeIntakeSessions(schema.project_id)
      const preferred = selectId || activeSessionId || next[0]?.id || ''
      let selected = next.find((session) => session.id === preferred) ?? null
      if (preferred) selected = await getKnowledgeIntakeSession(schema.project_id, preferred)
      setSessions(selected ? next.map((session) => session.id === selected?.id ? { ...session, ...selected } : session) : next)
      setActiveSessionId(selected?.id ?? '')
      setDraft(isUsableDraft(selected?.draft) ? selected?.draft ?? null : null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load sessions')
    }
  }

  async function runAction(action: Exclude<PendingAction, null>, label: string, work: () => Promise<void>) {
    if (loading) return
    setPendingAction(action)
    setLoadingLabel(label)
    setNotice(null)
    setError(null)
    try {
      await work()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The action could not be completed')
    } finally {
      setPendingAction(null)
      setLoadingLabel('')
    }
  }

  async function handleCreateSession() {
    await runAction('create', 'Creating a new session…', async () => {
      const session = await createKnowledgeIntakeSession(schema.project_id, 'Knowledge intake → uploaded Mirai contract', 'generic_tabular_doe')
      setNotice('Session created. Add the target contract and source files to continue.')
      setPanelTab('sources')
      await refreshSessions(session.id)
    })
  }

  async function handleUploadTargetContract(event: FormEvent) {
    event.preventDefault()
    if (!activeSessionId || selectedTargetFiles.length === 0) return
    await runAction('upload-contract', 'Uploading and validating the target contract…', async () => {
      await uploadKnowledgeIntakeTargetContract(schema.project_id, activeSessionId, selectedTargetFiles)
      setSelectedTargetFiles([])
      if (contractInputRef.current) contractInputRef.current.value = ''
      setNotice('Target contract uploaded and parsed.')
      await refreshSessions(activeSessionId)
    })
  }

  async function handleUploadSources(event: FormEvent) {
    event.preventDefault()
    if (!activeSessionId || selectedFiles.length === 0) return
    await runAction('upload-sources', 'Uploading and indexing source files…', async () => {
      await uploadKnowledgeIntakeFiles(schema.project_id, activeSessionId, selectedFiles)
      setSelectedFiles([])
      if (sourceInputRef.current) sourceInputRef.current.value = ''
      setNotice('Source files uploaded and indexed.')
      await refreshSessions(activeSessionId)
    })
  }

  async function handleMatch(nextInstruction?: string) {
    if (!activeSessionId) return
    const message = nextInstruction ?? instruction
    setInstruction(message)
    await runAction('mapping', 'Inspecting sources and updating the mapping…', async () => {
      await saveKnowledgeIntakeInstruction(schema.project_id, activeSessionId, message)
      const result = await matchKnowledgeIntakeMiraiContract(schema.project_id, activeSessionId)
      setDraft(result.draft)
      setIssues(await getKnowledgeIntakeIssues(schema.project_id, activeSessionId))
      setNotice(result.draft.validation_passed ? 'Mapping complete and validation passed.' : 'Mapping updated. Review the remaining requirements.')
      await refreshSessions(activeSessionId)
    })
  }

  async function handleApprove() {
    if (!activeSessionId) return
    await runAction('approve', 'Approving the validated mapping…', async () => {
      const result = await approveKnowledgeIntakeDraft(schema.project_id, activeSessionId)
      setDraft(result.draft)
      setNotice('Mapping approved.')
      await refreshSessions(activeSessionId)
    })
  }

  async function handleReject() {
    if (!activeSessionId || !window.confirm('Reject and delete the current mapping draft? This cannot be undone.')) return
    await runAction('reject', 'Rejecting the current draft…', async () => {
      await rejectKnowledgeIntakeDraft(schema.project_id, activeSessionId)
      setDraft(null)
      setIssues('')
      setInspectorOpen(false)
      setNotice('Mapping draft rejected and deleted.')
      await refreshSessions(activeSessionId)
    })
  }

  async function handleExport() {
    if (!activeSessionId) return
    await runAction('export', 'Preparing the Mirai package…', async () => {
      await exportKnowledgeIntakePackage(schema.project_id, activeSessionId)
      const blob = await downloadKnowledgeIntakePackage(schema.project_id, activeSessionId)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'mirai_package.zip'
      link.click()
      URL.revokeObjectURL(url)
      setNotice('Mirai package downloaded. Continue in Data Intake when you are ready.')
      await refreshSessions(activeSessionId)
    })
  }

  async function handleSelectSession(sessionId: string) {
    setActiveSessionId(sessionId)
    setIssues('')
    setSelectedFile(null)
    try {
      const detail = await getKnowledgeIntakeSession(schema.project_id, sessionId)
      setSessions((previous) => previous.map((session) => session.id === sessionId ? { ...session, ...detail } : session))
      setDraft(isUsableDraft(detail.draft) ? detail.draft ?? null : null)
    } catch {
      const fallbackDraft = sessions.find((session) => session.id === sessionId)?.draft
      setDraft(isUsableDraft(fallbackDraft) ? fallbackDraft ?? null : null)
    }
  }

  const files = activeSession?.files ?? []
  const mappingBoard = draft?.mapping_board ?? []
  const blockers = Array.isArray(draft?.validation_result?.blockers) ? draft.validation_result.blockers as string[] : []
  const stats = getMappingStats(mappingBoard)
  const viewModel = getIntakeViewModel(activeSession, draft, stats, blockers)
  const contractName = activeSession?.target_contract ? knowledgeIntakeContractLabel(activeSession.target_contract.contract_id ?? activeSession.target_contract_id) : 'Contract not selected'
  const tableOptions = Object.keys(draft?.tables ?? {})
  const effectiveTableName = tableOptions.includes(tableName) ? tableName : tableOptions[0] ?? tableName
  const currentTable = draft?.tables?.[effectiveTableName]

  function runPrimaryAction() {
    if (loading || !viewModel.actionEnabled) return
    if (viewModel.action === 'create') void handleCreateSession()
    if (viewModel.action === 'show-contract') {
      setPanelTab('sources')
      window.setTimeout(() => contractInputRef.current?.focus(), 0)
    }
    if (viewModel.action === 'show-sources') {
      setPanelTab('sources')
      window.setTimeout(() => sourceInputRef.current?.focus(), 0)
    }
    if (viewModel.action === 'mapping') void handleMatch()
    if (viewModel.action === 'approve') void handleApprove()
    if (viewModel.action === 'export') void handleExport()
  }

  return (
    <div className="min-w-0 space-y-5">
      <header className="border-b border-white/[0.10] pb-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold tracking-[-0.04em] text-white">Knowledge Intake</h1>
            <p className="mt-2 truncate text-sm text-[#AAB6C8]" title={`${files.length} source files · ${viewModel.status} · ${draft?.validation_passed ? 'Validation passed' : 'Validation pending'}`}>
              {files.length} source {files.length === 1 ? 'file' : 'files'} · {viewModel.status} · {draft?.validation_passed ? 'Validation passed' : 'Validation pending'}
            </p>
          </div>
          <button type="button" onClick={() => void handleCreateSession()} disabled={loading} className="self-start rounded-md border border-white/[0.12] px-4 py-2 text-sm font-semibold text-slate-100 transition hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-50 sm:self-auto">
            {pendingAction === 'create' ? 'Creating…' : 'New session'}
          </button>
        </div>
      </header>

      {(error || notice || loadingLabel) && (
        <div aria-live="polite" className="space-y-2">
          {error && <Message tone="error">{error}</Message>}
          {notice && <Message tone="success">{notice}</Message>}
          {loadingLabel && <Message tone="active"><span className="mr-2 inline-block h-3 w-3 animate-spin rounded-full border-2 border-[#74C7F5]/30 border-t-[#74C7F5]" />{loadingLabel}</Message>}
        </div>
      )}

      <div className="grid min-w-0 gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="min-w-0 border-r-0 border-white/[0.10] lg:border-r lg:pr-5">
          <div className="grid grid-cols-2 rounded-md bg-white/[0.035] p-1" role="tablist" aria-label="Knowledge intake navigation">
            {(['sessions', 'sources'] as PanelTab[]).map((tab) => (
              <button key={tab} type="button" role="tab" aria-selected={panelTab === tab} onClick={() => setPanelTab(tab)} className={`rounded px-3 py-2 text-sm font-semibold transition ${panelTab === tab ? 'bg-[#17335E] text-white' : 'text-[#AAB6C8] hover:text-white'}`}>
                {tab === 'sessions' ? `Sessions (${sessions.length})` : `Sources (${files.length})`}
              </button>
            ))}
          </div>

          {panelTab === 'sessions' ? (
            <div className="mt-4 max-h-[calc(100vh-330px)] min-h-48 space-y-1 overflow-y-auto pr-1">
              {sessions.length === 0 ? <EmptyText>Create a session to begin.</EmptyText> : sessions.map((session, index) => {
                const sessionNumber = sessions.length - index
                const selected = session.id === activeSessionId
                return (
                  <button key={session.id} type="button" onClick={() => void handleSelectSession(session.id)} className={`w-full rounded-md border px-3 py-3 text-left transition ${selected ? 'border-[#5BA8FF]/35 bg-[#17335E]/55' : 'border-transparent hover:bg-white/[0.035]'}`}>
                    <span className="flex items-center justify-between gap-3">
                      <span className="truncate text-sm font-semibold text-white" title={session.title || session.id}>Session {sessionNumber}</span>
                      <span className="shrink-0 text-xs text-[#9FB0C8]">{session.file_count ?? session.files?.length ?? 0} files</span>
                    </span>
                    <span className="mt-1 block truncate text-xs text-[#9FB0C8]">{knowledgeIntakeStatusLabel(session.status)}{(session.updated_at || session.created_at) ? ` · ${formatDate(session.updated_at ?? session.created_at)}` : ''}</span>
                  </button>
                )
              })}
            </div>
          ) : (
            <div className="mt-5 space-y-6">
              <UploadSection title="Target contract" description={activeSession?.target_contract ? contractName : 'Upload a ZIP, manifest, data dictionary, or contract CSV.'}>
                <form onSubmit={handleUploadTargetContract} className="space-y-2">
                  <input ref={contractInputRef} type="file" multiple accept=".zip,.json,.csv" onChange={(event) => setSelectedTargetFiles(Array.from(event.target.files ?? []))} className="block w-full min-w-0 text-xs text-slate-300 file:mr-2 file:rounded file:border-0 file:bg-[#17335E] file:px-3 file:py-2 file:text-xs file:font-semibold file:text-white" />
                  <UploadButton disabled={!activeSessionId || selectedTargetFiles.length === 0 || loading} active={pendingAction === 'upload-contract'}>Upload contract</UploadButton>
                </form>
              </UploadSection>

              <UploadSection title="Source files" description={`${files.length} file${files.length === 1 ? '' : 's'} available to the mapping workflow.`}>
                <form onSubmit={handleUploadSources} className="space-y-2">
                  <input ref={sourceInputRef} type="file" multiple onChange={(event) => setSelectedFiles(Array.from(event.target.files ?? []))} className="block w-full min-w-0 text-xs text-slate-300 file:mr-2 file:rounded file:border-0 file:bg-[#17335E] file:px-3 file:py-2 file:text-xs file:font-semibold file:text-white" />
                  <UploadButton disabled={!activeSessionId || selectedFiles.length === 0 || loading} active={pendingAction === 'upload-sources'}>Upload sources</UploadButton>
                </form>
                <div className="mt-3 max-h-[38vh] divide-y divide-white/[0.08] overflow-y-auto">
                  {files.length === 0 ? <EmptyText>No source files uploaded.</EmptyText> : files.map((file) => (
                    <button key={file.id} type="button" onClick={() => { setSelectedFile(file); setInspectorOpen(true) }} className="block w-full py-2.5 text-left hover:bg-white/[0.025]">
                      <span className="block truncate text-sm font-medium text-slate-100" title={file.filename}>{file.filename}</span>
                      <span className="mt-1 block text-xs text-[#9FB0C8]">{file.file_type?.toUpperCase()} · {knowledgeIntakeStatusLabel(file.parse_status ?? 'uploaded')}</span>
                    </button>
                  ))}
                </div>
              </UploadSection>
            </div>
          )}
        </aside>

        <main className="min-w-0 space-y-6">
          <section className="rounded-lg border border-white/[0.10] bg-[#0B1424]/75 p-5 sm:p-6">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge tone={viewModel.tone}>{viewModel.status}</StatusBadge>
                  {activeSession && <span className="text-xs text-[#9FB0C8]">Selected session</span>}
                </div>
                <h2 className="mt-4 text-xl font-semibold text-white">{activeSession ? contractName : 'Start a knowledge intake session'}</h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-[#B8C2D4]">{viewModel.explanation}</p>
              </div>
              <div className="w-full shrink-0 xl:w-64">
                <button type="button" onClick={runPrimaryAction} disabled={loading || !viewModel.actionEnabled} className="w-full rounded-md bg-[#2F6BFF] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#4C7DFF] disabled:cursor-not-allowed disabled:opacity-50">
                  {isPrimaryPending(viewModel.action, pendingAction) ? 'Working…' : viewModel.actionLabel}
                </button>
                {viewModel.actionHelp && <p className="mt-2 text-xs leading-5 text-[#9FB0C8]">{viewModel.actionHelp}</p>}
              </div>
            </div>

            <ol className="mt-7 grid gap-2 sm:grid-cols-4" aria-label="Knowledge intake progress">
              {viewModel.stages.map((stage, index) => <WorkflowStage key={stage.label} index={index + 1} {...stage} />)}
            </ol>
          </section>

          <section className="grid gap-x-6 gap-y-5 border-y border-white/[0.10] py-5 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryItem label="Contract" value={contractName} title={contractName} />
            <SummaryItem label="Sources" value={`${files.length} file${files.length === 1 ? '' : 's'}`} />
            <SummaryItem label="Mapping" value={mappingLabel(stats, Boolean(draft), Boolean(activeSession?.target_contract))} />
            <SummaryItem label="Validation" value={draft?.validation_passed ? 'Passed' : draft ? knowledgeIntakeStatusLabel(draft.status) : 'Not run'} />
          </section>

          <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(280px,0.55fr)]">
            <div className="min-w-0">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-white">Mapping workspace</h2>
                  <p className="mt-1 text-sm text-[#9FB0C8]">Give the mapping agent context or ask it to update the contract mapping.</p>
                </div>
                <button type="button" onClick={() => { setSelectedFile(null); setInspectorOpen(true) }} disabled={!activeSession} className="self-start text-sm font-semibold text-[#8FCBFF] hover:text-white disabled:cursor-not-allowed disabled:opacity-50">View details</button>
              </div>
              <textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} rows={5} disabled={!activeSession || loading} className="mt-4 w-full rounded-md border border-white/[0.12] bg-[#050914] px-3 py-3 text-sm leading-6 text-white outline-none placeholder:text-[#74839B] disabled:opacity-60" />
              <div className="mt-3 flex flex-wrap gap-3">
                <button type="button" onClick={() => void handleMatch()} disabled={!activeSession || loading} className="rounded-md border border-[#5BA8FF]/35 px-4 py-2 text-sm font-semibold text-[#BDEAFF] hover:bg-[#5BA8FF]/10 disabled:cursor-not-allowed disabled:opacity-50">{pendingAction === 'mapping' ? 'Updating…' : draft ? 'Update mapping' : 'Run mapping'}</button>
                <button type="button" onClick={() => void handleMatch('approve suggested mapping')} disabled={!activeSession || loading || mappingBoard.length === 0} className="rounded-md px-4 py-2 text-sm font-semibold text-slate-200 hover:bg-white/[0.05] disabled:cursor-not-allowed disabled:opacity-50">Approve suggested mapping</button>
              </div>
            </div>

            <div className="border-t border-white/[0.10] pt-5 xl:border-l xl:border-t-0 xl:pl-6 xl:pt-0">
              <h3 className="text-sm font-semibold text-white">What needs attention</h3>
              {blockers.length ? (
                <ul className="mt-3 space-y-2 text-sm leading-6 text-amber-100">{blockers.slice(0, 3).map((blocker) => <li key={blocker}>• {blocker}</li>)}</ul>
              ) : (
                <p className="mt-3 text-sm leading-6 text-[#B8C2D4]">{draft?.validation_passed ? 'All required fields have been validated.' : viewModel.explanation}</p>
              )}
              <p className="mt-4 text-xs leading-5 text-[#9FB0C8]">Required next step: {viewModel.actionLabel}</p>
            </div>
          </section>

          <div className="flex flex-wrap items-center gap-3 border-t border-white/[0.10] pt-5">
            {draft && <button type="button" onClick={() => void handleReject()} disabled={loading} className="rounded-md px-3 py-2 text-sm font-semibold text-red-200 hover:bg-red-500/10 disabled:opacity-50">{pendingAction === 'reject' ? 'Rejecting…' : 'Reject draft'}</button>}
            {activeSession?.latest_export_key && <button type="button" onClick={onGoToDataIntake} className="rounded-md px-3 py-2 text-sm font-semibold text-[#BDEAFF] hover:bg-[#74C7F5]/10">Continue to Data Intake</button>}
          </div>
        </main>
      </div>

      {inspectorOpen && (
        <Inspector
          session={activeSession}
          file={selectedFile}
          draft={draft}
          issues={issues}
          stats={stats}
          mappingBoard={mappingBoard}
          showMapping={showMapping}
          tableName={effectiveTableName}
          tableOptions={tableOptions}
          currentTable={currentTable}
          onToggleMapping={() => setShowMapping((value) => !value)}
          onTableNameChange={setTableName}
          onClose={() => setInspectorOpen(false)}
        />
      )}
    </div>
  )
}

function Inspector({ session, file, draft, issues, stats, mappingBoard, showMapping, tableName, tableOptions, currentTable, onToggleMapping, onTableNameChange, onClose }: {
  session: KnowledgeIntakeSession | null
  file: KnowledgeIntakeFile | null
  draft: KnowledgeIntakeDraft | null
  issues: string
  stats: MappingStats
  mappingBoard: KnowledgeIntakeMappingRow[]
  showMapping: boolean
  tableName: string
  tableOptions: string[]
  currentTable?: { columns: string[]; preview_rows: string[]; total_rows: number }
  onToggleMapping: () => void
  onTableNameChange: (value: string) => void
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-[100] flex justify-end bg-black/45" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <aside role="dialog" aria-modal="true" aria-label="Knowledge intake details" className="h-full w-full max-w-xl overflow-y-auto border-l border-white/[0.12] bg-[#08111F] p-5 shadow-2xl sm:p-6">
        <div className="flex items-start justify-between gap-4 border-b border-white/[0.10] pb-4">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold text-white" title={file?.filename}>{file ? file.filename : 'Session details'}</h2>
            <p className="mt-1 text-xs text-[#9FB0C8]">Press Escape to close</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close details" className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-white/[0.12] text-xl text-slate-200 hover:bg-white/[0.06]">×</button>
        </div>

        {file ? (
          <dl className="mt-6 grid grid-cols-2 gap-5 text-sm">
            <Detail label="Type" value={file.file_type?.toUpperCase() || 'Unknown'} />
            <Detail label="Status" value={knowledgeIntakeStatusLabel(file.parse_status)} />
            <Detail label="Size" value={formatBytes(file.size_bytes)} />
            <Detail label="File ID" value={file.id} />
          </dl>
        ) : (
          <div className="mt-6 space-y-7">
            <dl className="grid grid-cols-2 gap-5 text-sm">
              <Detail label="Session" value={session ? knowledgeIntakeStatusLabel(session.status) : 'Not selected'} />
              <Detail label="Contract" value={session?.target_contract ? knowledgeIntakeContractLabel(session.target_contract.contract_id) : 'Not selected'} />
              <Detail label="Mapped fields" value={stats.totalFields ? `${stats.mappedFields} of ${stats.totalFields}` : draft ? 'No fields available to map' : 'Not run'} />
              <Detail label="Missing fields" value={`${stats.missingFields}`} />
            </dl>

            <section className="border-t border-white/[0.10] pt-5">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-white">Detailed mapping</h3>
                <button type="button" onClick={onToggleMapping} disabled={!draft} className="text-sm font-semibold text-[#8FCBFF] disabled:opacity-50">{showMapping ? 'Hide' : 'Show'}</button>
              </div>
              {showMapping && (
                <div className="mt-3 overflow-x-auto rounded-md border border-white/[0.10]">
                  {mappingBoard.length ? <MappingTable rows={mappingBoard} /> : <EmptyText>No contract fields available to map.</EmptyText>}
                </div>
              )}
            </section>

            {currentTable && (
              <section className="border-t border-white/[0.10] pt-5">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-white">Package preview</h3>
                  <select value={tableName} onChange={(event) => onTableNameChange(event.target.value)} className="max-w-52 truncate rounded-md border border-white/[0.12] bg-[#050914] px-2 py-1 text-xs text-white" title={tableName}>{tableOptions.map((name) => <option key={name}>{name}</option>)}</select>
                </div>
                <div className="mt-3 overflow-x-auto"><PackagePreview tableName={tableName} table={currentTable} /></div>
              </section>
            )}

            <section className="border-t border-white/[0.10] pt-5">
              <h3 className="text-sm font-semibold text-white">Agent notes</h3>
              <pre className="mt-3 whitespace-pre-wrap text-xs leading-5 text-[#B8C2D4]">{issues || draft?.agent_response || 'No agent notes available.'}</pre>
            </section>
          </div>
        )}
      </aside>
    </div>
  )
}

function getIntakeViewModel(session: KnowledgeIntakeSession | null, draft: KnowledgeIntakeDraft | null, stats: MappingStats, blockers: string[]): IntakeViewModel {
  const hasContract = Boolean(session?.target_contract)
  const fileCount = session?.file_count ?? session?.files?.length ?? 0
  const approved = draft?.status === 'approved_persistent'
  const exported = Boolean(session?.latest_export_key || session?.export || session?.status === 'exported')
  let model: Omit<IntakeViewModel, 'stages'>

  if (!session) model = { status: 'No session selected', explanation: 'Create a session to collect source files and map them into a Mirai contract.', tone: 'neutral', action: 'create', actionLabel: 'Create session', actionEnabled: true }
  else if (!hasContract) model = { status: 'Contract needed', explanation: 'Choose the Mirai contract that these source files should populate.', tone: 'warning', action: 'show-contract', actionLabel: 'Add target contract', actionEnabled: true }
  else if (fileCount === 0) model = { status: 'Sources needed', explanation: 'Add source files before the mapping agent can inspect and validate the data.', tone: 'warning', action: 'show-sources', actionLabel: 'Add source files', actionEnabled: true }
  else if (!draft) model = { status: 'Ready to map', explanation: 'The contract and source files are ready for the mapping agent.', tone: 'active', action: 'mapping', actionLabel: 'Run mapping', actionEnabled: true }
  else if (!draft.validation_passed) model = { status: draft.status === 'needs_user_input' ? 'Needs your input' : knowledgeIntakeStatusLabel(draft.status), explanation: blockers[0] ?? `${stats.missingFields} contract field${stats.missingFields === 1 ? '' : 's'} still require attention.`, tone: blockers.length ? 'warning' : 'active', action: 'mapping', actionLabel: 'Update mapping', actionEnabled: true }
  else if (!approved) model = { status: 'Mapping complete', explanation: 'All required fields have been validated. Review and approve the mapping to continue.', tone: 'success', action: 'approve', actionLabel: 'Review & approve mapping', actionEnabled: true }
  else model = { status: exported ? 'Exported' : 'Approved', explanation: exported ? 'The approved Mirai package is ready for the Data Intake workflow.' : 'The validated mapping is approved and ready to export.', tone: 'success', action: 'export', actionLabel: exported ? 'Download package again' : 'Export package', actionEnabled: true }

  return {
    ...model,
    stages: [
      { label: 'Sources', state: !session || fileCount === 0 ? 'current' : 'complete' },
      { label: 'Mapping', state: !session || fileCount === 0 ? 'upcoming' : !draft ? 'current' : draft.validation_passed ? 'complete' : 'blocked' },
      { label: 'Validation', state: !draft ? 'upcoming' : draft.validation_passed ? 'complete' : 'current' },
      { label: 'Approval & export', state: approved && exported ? 'complete' : draft?.validation_passed ? 'current' : 'upcoming' },
    ],
  }
}

function getMappingStats(rows: KnowledgeIntakeMappingRow[]): MappingStats {
  return rows.reduce<MappingStats>((stats, row) => {
    const mapped = !isMissingMapping(row)
    stats.totalFields += 1
    if (mapped) stats.mappedFields += 1
    else stats.missingFields += 1
    if (row.role === 'input') { stats.inputTotal += 1; if (mapped) stats.inputMapped += 1 }
    if (row.role === 'output') { stats.outputTotal += 1; if (mapped) stats.outputMapped += 1 }
    return stats
  }, { totalFields: 0, mappedFields: 0, missingFields: 0, inputTotal: 0, inputMapped: 0, outputTotal: 0, outputMapped: 0 })
}

function isMissingMapping(row: KnowledgeIntakeMappingRow) {
  const source = String(row.source_column ?? '').trim()
  return row.status === 'missing' || !source || source === '—' || source === '-'
}

function mappingLabel(stats: MappingStats, hasDraft: boolean, hasContract: boolean) {
  if (!hasContract) return 'Contract not selected'
  if (!hasDraft) return 'Not run'
  if (stats.totalFields === 0) return 'No contract fields required'
  return `${stats.mappedFields} of ${stats.totalFields} fields`
}

function isPrimaryPending(action: PrimaryAction, pending: PendingAction) {
  return (action === 'create' && pending === 'create') || (action === 'mapping' && pending === 'mapping') || (action === 'approve' && pending === 'approve') || (action === 'export' && pending === 'export')
}

function Message({ tone, children }: { tone: 'error' | 'success' | 'active'; children: ReactNode }) {
  const classes = tone === 'error' ? 'bg-red-500/10 text-red-100' : tone === 'success' ? 'bg-emerald-500/10 text-emerald-100' : 'bg-[#5BA8FF]/10 text-[#D9F3FF]'
  return <div className={`px-3 py-2 text-sm ${classes}`}>{children}</div>
}

function StatusBadge({ tone, children }: { tone: Tone; children: ReactNode }) {
  const classes: Record<Tone, string> = { neutral: 'bg-white/[0.07] text-slate-200', active: 'bg-[#5BA8FF]/12 text-[#D9F3FF]', success: 'bg-emerald-500/10 text-emerald-100', warning: 'bg-amber-500/10 text-amber-100', error: 'bg-red-500/10 text-red-100' }
  return <span className={`rounded-full px-3 py-1 text-xs font-semibold ${classes[tone]}`}>{children}</span>
}

function WorkflowStage({ label, state, index }: { label: string; state: 'complete' | 'current' | 'upcoming' | 'blocked'; index: number }) {
  const classes = state === 'complete' ? 'border-emerald-400/20 bg-emerald-500/[0.07] text-emerald-100' : state === 'current' ? 'border-[#5BA8FF]/35 bg-[#5BA8FF]/10 text-white' : state === 'blocked' ? 'border-amber-400/25 bg-amber-500/[0.07] text-amber-100' : 'border-white/[0.08] text-[#8493AA]'
  return <li className={`flex items-center gap-2 rounded-md border px-3 py-2.5 text-xs font-semibold ${classes}`}><span>{state === 'complete' ? '✓' : index}</span><span>{label}</span></li>
}

function SummaryItem({ label, value, title }: { label: string; value: string; title?: string }) {
  return <div className="min-w-0"><p className="text-xs font-medium text-[#9FB0C8]">{label}</p><p className="mt-1 truncate text-sm font-semibold text-white" title={title ?? value}>{value}</p></div>
}

function UploadSection({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return <section><h3 className="text-sm font-semibold text-white">{title}</h3><p className="mt-1 text-xs leading-5 text-[#9FB0C8]">{description}</p><div className="mt-3">{children}</div></section>
}

function UploadButton({ disabled, active, children }: { disabled: boolean; active: boolean; children: ReactNode }) {
  return <button type="submit" disabled={disabled} className="w-full rounded-md border border-white/[0.12] px-3 py-2 text-sm font-semibold text-slate-100 hover:bg-white/[0.05] disabled:cursor-not-allowed disabled:opacity-50">{active ? 'Uploading…' : children}</button>
}

function EmptyText({ children }: { children: ReactNode }) {
  return <p className="px-2 py-5 text-sm leading-6 text-[#9FB0C8]">{children}</p>
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0"><dt className="text-xs text-[#9FB0C8]">{label}</dt><dd className="mt-1 break-words font-medium text-white" title={value}>{value}</dd></div>
}

function MappingTable({ rows }: { rows: KnowledgeIntakeMappingRow[] }) {
  return (
    <table className="min-w-full divide-y divide-white/[0.08] text-xs">
      <thead className="text-[#BDEAFF]"><tr><th className="px-3 py-2 text-left">Contract field</th><th className="px-3 py-2 text-left">Source</th><th className="px-3 py-2 text-left">Status</th></tr></thead>
      <tbody className="divide-y divide-white/[0.08] text-slate-300">{rows.map((row) => <tr key={row.field}><td className="px-3 py-2 font-medium text-white">{row.ui_label || row.field}</td><td className="max-w-56 truncate px-3 py-2" title={row.source_column ?? undefined}>{row.source_column || '—'}</td><td className={`px-3 py-2 ${isMissingMapping(row) ? 'text-amber-200' : 'text-emerald-200'}`}>{knowledgeIntakeStatusLabel(row.status)}</td></tr>)}</tbody>
    </table>
  )
}

function PackagePreview({ tableName, table }: { tableName: string; table: { columns: string[]; preview_rows: string[]; total_rows: number } }) {
  return (
    <table className="min-w-full divide-y divide-white/[0.08] text-xs">
      <thead><tr>{table.columns.slice(0, 8).map((column) => <th key={`${tableName}-${column}`} className="px-3 py-2 text-left text-[#BDEAFF]">{column}</th>)}</tr></thead>
      <tbody className="divide-y divide-white/[0.08] text-slate-300">{table.preview_rows.slice(0, 8).map((row, index) => <tr key={`${tableName}-${index}`}>{row.split(',').slice(0, 8).map((cell, cellIndex) => <td key={cellIndex} className="max-w-48 truncate px-3 py-2">{cell}</td>)}</tr>)}</tbody>
    </table>
  )
}

function formatDate(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date)
}

function formatBytes(value?: number) {
  if (value === undefined) return 'Unknown'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function isUsableDraft(value?: KnowledgeIntakeDraft | null): value is KnowledgeIntakeDraft {
  return Boolean(value?.id && value.status !== 'deleted')
}
