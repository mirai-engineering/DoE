import { FormEvent, type ReactNode, useEffect, useMemo, useState } from 'react'
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

const defaultInstruction = 'Inspect these sources against the uploaded target Mirai contract, infer a candidate source-to-contract mapping, list missing fields/questions, and run only approved Knowledge Intake transforms that validate as a Mirai package.'

type MappingStats = {
  totalFields: number
  mappedFields: number
  missingFields: number
  inputTotal: number
  inputMapped: number
  outputTotal: number
  outputMapped: number
  highConfidence: number
  mediumConfidence: number
  lowConfidence: number
}

type ValidationSummary = {
  label: 'Ready' | 'Blocked' | 'Needs user input' | 'Unknown'
  reason: string
  nextStep: string
}

type SourceSummary = {
  indexedFiles: number
  containers: number
  tabularColumns: number
  csvFiles: number
  xlsxFiles: number
  pdfFiles: number
  docxFiles: number
}

export function KnowledgeIntakePage({ schema, onGoToDataIntake }: { schema: ProjectSchema; onGoToDataIntake: () => void }) {
  const [sessions, setSessions] = useState<KnowledgeIntakeSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState('')
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [selectedTargetFiles, setSelectedTargetFiles] = useState<File[]>([])
  const [instruction, setInstruction] = useState(defaultInstruction)
  const [draft, setDraft] = useState<KnowledgeIntakeDraft | null>(null)
  const [issues, setIssues] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingLabel, setLoadingLabel] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [tableName, setTableName] = useState('experiments.csv')
  const [showFullNotes, setShowFullNotes] = useState(false)
  const [showFullMapping, setShowFullMapping] = useState(false)
  const [sourcesCollapsed, setSourcesCollapsed] = useState(false)
  const [resultsCollapsed, setResultsCollapsed] = useState(false)

  const activeSession = useMemo(() => sessions.find((session) => session.id === activeSessionId) ?? null, [sessions, activeSessionId])

  useEffect(() => {
    void refreshSessions()
  }, [schema.project_id])

  async function refreshSessions(selectId?: string) {
    setError(null)
    try {
      const next = await listKnowledgeIntakeSessions(schema.project_id)
      const preferred = selectId || activeSessionId || next[0]?.id || ''
      let selected = next.find((session) => session.id === preferred) ?? null
      if (preferred) {
        selected = await getKnowledgeIntakeSession(schema.project_id, preferred)
      }
      setSessions(selected ? next.map((session) => session.id === selected?.id ? { ...session, ...selected } : session) : next)
      setActiveSessionId(preferred)
      setDraft(selected?.draft ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load sessions')
    }
  }

  async function handleCreateSession() {
    setLoading(true)
    setLoadingLabel('Creating intake loop session…')
    setNotice(null)
    setError(null)
    try {
      const session = await createKnowledgeIntakeSession(schema.project_id, 'Knowledge intake → uploaded Mirai contract', 'generic_tabular_doe')
      setNotice('Knowledge intake session created. Upload the target Mirai contract package next.')
      await refreshSessions(session.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create session')
    } finally {
      setLoading(false)
      setLoadingLabel('')
    }
  }

  async function handleUploadTargetContract(event: FormEvent) {
    event.preventDefault()
    if (!activeSessionId || selectedTargetFiles.length === 0) return
    setLoading(true)
    setLoadingLabel('Uploading and validating target Mirai contract…')
    setNotice(null)
    setError(null)
    try {
      await uploadKnowledgeIntakeTargetContract(schema.project_id, activeSessionId, selectedTargetFiles)
      setSelectedTargetFiles([])
      setNotice('Target Mirai contract uploaded and parsed. Now upload source files to populate it.')
      await refreshSessions(activeSessionId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Target contract upload failed')
    } finally {
      setLoading(false)
      setLoadingLabel('')
    }
  }

  async function handleUpload(event: FormEvent) {
    event.preventDefault()
    if (!activeSessionId || selectedFiles.length === 0) return
    setLoading(true)
    setLoadingLabel('Uploading and indexing source files…')
    setNotice(null)
    setError(null)
    try {
      await uploadKnowledgeIntakeFiles(schema.project_id, activeSessionId, selectedFiles)
      setSelectedFiles([])
      setNotice('Files uploaded and indexed.')
      await refreshSessions(activeSessionId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setLoading(false)
      setLoadingLabel('')
    }
  }

  async function handleMatch(nextInstruction?: string) {
    if (!activeSessionId) return
    const message = nextInstruction ?? instruction
    setInstruction(message)
    setLoading(true)
    setLoadingLabel('Agent planner is inspecting sources and drafting the contract mapping…')
    setNotice(null)
    setError(null)
    try {
      await saveKnowledgeIntakeInstruction(schema.project_id, activeSessionId, message)
      const result = await matchKnowledgeIntakeMiraiContract(schema.project_id, activeSessionId)
      setDraft(result.draft)
      const text = await getKnowledgeIntakeIssues(schema.project_id, activeSessionId)
      setIssues(text)
      setNotice(result.draft.validation_passed ? 'Validated contract draft is ready for review.' : 'Loop iteration recorded. Review questions/issues before approval/export can continue.')
      await refreshSessions(activeSessionId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to match Mirai contract')
    } finally {
      setLoading(false)
      setLoadingLabel('')
    }
  }

  async function handleApprove() {
    if (!activeSessionId) return
    setLoading(true)
    setLoadingLabel('Persisting approval for the validated draft…')
    setNotice(null)
    setError(null)
    try {
      const result = await approveKnowledgeIntakeDraft(schema.project_id, activeSessionId)
      setDraft(result.draft)
      setNotice('Draft approved for persistent storage.')
      await refreshSessions(activeSessionId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Approval failed')
    } finally {
      setLoading(false)
      setLoadingLabel('')
    }
  }

  async function handleReject() {
    if (!activeSessionId) return
    setLoading(true)
    setLoadingLabel('Rejecting and deleting the current draft…')
    setNotice(null)
    setError(null)
    try {
      await rejectKnowledgeIntakeDraft(schema.project_id, activeSessionId)
      setDraft(null)
      setIssues('')
      setNotice('Draft rejected and deleted for this demo.')
      await refreshSessions(activeSessionId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reject failed')
    } finally {
      setLoading(false)
      setLoadingLabel('')
    }
  }

  async function handleExport() {
    if (!activeSessionId) return
    setLoading(true)
    setLoadingLabel('Exporting the validated Mirai package ZIP…')
    setNotice(null)
    setError(null)
    try {
      await exportKnowledgeIntakePackage(schema.project_id, activeSessionId)
      const blob = await downloadKnowledgeIntakePackage(schema.project_id, activeSessionId)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'mirai_package.zip'
      link.click()
      URL.revokeObjectURL(url)
      setNotice('Mirai package downloaded. Manually upload this ZIP in Data Intake to continue through the existing preprocessing/review flow.')
      await refreshSessions(activeSessionId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setLoading(false)
      setLoadingLabel('')
    }
  }

  async function handleSelectSession(sessionId: string) {
    setActiveSessionId(sessionId)
    setIssues('')
    try {
      const detail = await getKnowledgeIntakeSession(schema.project_id, sessionId)
      setSessions((prev) => prev.map((session) => session.id === sessionId ? { ...session, ...detail } : session))
      setDraft(detail.draft ?? null)
    } catch {
      const selected = sessions.find((session) => session.id === sessionId)
      setDraft(selected?.draft ?? null)
    }
  }

  const tableOptions = Object.keys(draft?.tables ?? {})
  const effectiveTableName = tableOptions.includes(tableName) ? tableName : tableOptions[0] ?? tableName
  const currentTable = draft?.tables?.[effectiveTableName] ?? null
  const availableColumns = draft?.available_columns ?? []
  const mappingBoard = draft?.mapping_board ?? []
  const conversation = draft?.conversation ?? activeSession?.messages ?? []
  const blockers = Array.isArray(draft?.validation_result?.blockers) ? draft?.validation_result?.blockers as string[] : []
  const targetContract = activeSession?.target_contract
  const targetLabel = targetContract ? `${targetContract.contract_id ?? 'generic_tabular_doe'} · ${targetContract.package_style ?? 'uploaded package'}` : 'No target Mirai contract uploaded'
  const mappingStats = getMappingStats(mappingBoard)
  const validationSummary = getValidationSummary(draft, blockers)
  const sourceSummary = getSourceSummary(activeSession?.files ?? [], availableColumns.length)

  return (
    <div className="space-y-4">
      <KnowledgeIntakeHeader
        schema={schema}
        targetLabel={targetLabel}
        fileCount={activeSession?.file_count ?? activeSession?.files?.length ?? 0}
        sessionStatus={activeSession?.status ?? 'No session'}
        validationLabel={validationSummary.label}
        onCreateSession={handleCreateSession}
        loading={loading}
      />

      {(error || notice) && (
        <div className="space-y-2">
          {error && <div className="flex items-start gap-2 bg-red-500/10 px-3 py-2 text-sm text-red-100"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-red-300" />{error}</div>}
          {notice && <div className="flex items-start gap-2 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-300" />{notice}</div>}
        </div>
      )}

      <section className={`grid min-h-[calc(100vh-270px)] gap-5 transition-[grid-template-columns] duration-200 ${sourcesCollapsed && resultsCollapsed ? 'xl:grid-cols-[2.75rem_minmax(620px,1fr)_2.75rem]' : sourcesCollapsed ? 'xl:grid-cols-[2.75rem_minmax(560px,1fr)_minmax(320px,0.82fr)]' : resultsCollapsed ? 'xl:grid-cols-[minmax(250px,0.72fr)_minmax(560px,1fr)_2.75rem]' : 'xl:grid-cols-[minmax(250px,0.78fr)_minmax(420px,1.55fr)_minmax(320px,1.05fr)]'} lg:grid-cols-[minmax(360px,1.15fr)_minmax(330px,0.85fr)]`}>
        
        <SourcesPanel
          sessions={sessions}
          activeSession={activeSession}
          activeSessionId={activeSessionId}
          selectedFiles={selectedFiles}
          selectedTargetFiles={selectedTargetFiles}
          sourceSummary={sourceSummary}
          loading={loading}
          onSelectSession={handleSelectSession}
          onTargetFilesChange={setSelectedTargetFiles}
          onUploadTargetContract={handleUploadTargetContract}
          onFilesChange={setSelectedFiles}
          onUpload={handleUpload}
          collapsed={sourcesCollapsed}
          onCollapsedChange={setSourcesCollapsed}
        />

        <MappingAgentPanel
          activeSessionId={activeSessionId}
          loading={loading}
          loadingLabel={loadingLabel}
          draft={draft}
          conversation={conversation}
          instruction={instruction}
          issues={issues}
          mappingBoardLength={mappingBoard.length}
          onInstructionChange={setInstruction}
          onAskAgent={handleMatch}
          showFullNotes={showFullNotes}
          onToggleNotes={() => setShowFullNotes((value) => !value)}
        />

        <LiveResultsPanel
          draft={draft}
          tableName={effectiveTableName}
          tableOptions={tableOptions}
          currentTable={currentTable}
          mappingBoard={mappingBoard}
          mappingStats={mappingStats}
          blockers={blockers}
          validationSummary={validationSummary}
          loading={loading}
          showFullMapping={showFullMapping}
          onToggleMapping={() => setShowFullMapping((value) => !value)}
          onTableNameChange={setTableName}
          onApprove={handleApprove}
          onReject={handleReject}
          onExport={handleExport}
          onGoToDataIntake={onGoToDataIntake}
          collapsed={resultsCollapsed}
          onCollapsedChange={setResultsCollapsed}
        />
      </section>
    </div>
  )
}

function KnowledgeIntakeHeader({ schema, targetLabel, fileCount, sessionStatus, validationLabel, onCreateSession, loading }: { schema: ProjectSchema; targetLabel: string; fileCount: number; sessionStatus: string; validationLabel: string; onCreateSession: () => void; loading: boolean }) {
  return (
    <section className="border-b border-slate-400/[0.10] pb-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#74C7F5]">{schema.workspace_name ?? schema.workspace_id ?? 'Workspace'} / {schema.display_name}</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">Knowledge Intake</h2>
          <p className="mt-2 text-sm leading-6 text-slate-400">{targetLabel} · {fileCount} source {fileCount === 1 ? 'file' : 'files'} · {formatStatus(sessionStatus)} · Validation {validationLabel.toLowerCase()}</p>
        </div>
        <button type="button" onClick={onCreateSession} disabled={loading} className="rounded-lg bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4C7DFF] disabled:cursor-not-allowed disabled:opacity-60">
          New session
        </button>
      </div>
    </section>
  )
}

function SourcesPanel({ sessions, activeSession, activeSessionId, selectedFiles, selectedTargetFiles, sourceSummary, loading, onSelectSession, onTargetFilesChange, onUploadTargetContract, onFilesChange, onUpload, collapsed, onCollapsedChange }: { sessions: KnowledgeIntakeSession[]; activeSession: KnowledgeIntakeSession | null; activeSessionId: string; selectedFiles: File[]; selectedTargetFiles: File[]; sourceSummary: SourceSummary; loading: boolean; onSelectSession: (sessionId: string) => Promise<void>; onTargetFilesChange: (files: File[]) => void; onUploadTargetContract: (event: FormEvent) => Promise<void>; onFilesChange: (files: File[]) => void; onUpload: (event: FormEvent) => Promise<void>; collapsed: boolean; onCollapsedChange: (collapsed: boolean) => void }) {
  const targetContract = activeSession?.target_contract
  return (
    <aside className={`flex min-h-0 flex-col border-y border-slate-400/[0.10] ${collapsed ? 'items-center py-4' : 'gap-6 py-4'} lg:col-span-1`}>
      <div className={`flex w-full items-center ${collapsed ? 'justify-center' : 'justify-between px-1'}`}>
        {!collapsed && <p className="text-sm font-semibold text-[#F3F7FF]">Sources</p>}
        <button type="button" onClick={() => onCollapsedChange(!collapsed)} className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-400/[0.12] text-sm font-semibold text-[#9FB0C8] transition hover:border-[#5BA8FF]/30 hover:bg-[#5BA8FF]/10 hover:text-[#F3F7FF]" aria-label={collapsed ? 'Show sources panel' : 'Hide sources panel'} title={collapsed ? 'Show sources' : 'Hide sources'}>
          {collapsed ? '›' : '‹'}
        </button>
      </div>
      {collapsed ? <div className="mt-5 text-[0.65rem] font-semibold uppercase tracking-[0.12em] text-[#7E8AA0] [writing-mode:vertical-rl]">Sources</div> : <>
      <WorkspaceCard title="Sessions" aside={`${sessions.length}`}>
        <div className="max-h-56 divide-y divide-white/[0.06] overflow-auto pr-1">
          {sessions.length === 0 ? (
            <p className="py-3 text-sm text-slate-500">Create a session to start uploading source files.</p>
          ) : sessions.map((session) => (
            <button key={session.id} type="button" onClick={() => { void onSelectSession(session.id) }} className={`relative w-full px-3 py-3 text-left transition ${session.id === activeSessionId ? 'rounded-lg bg-[#2F6BFF]/10 text-white before:absolute before:bottom-2 before:left-0 before:top-2 before:w-px before:bg-[#74C7F5]' : 'text-slate-300 hover:bg-white/[0.035]'}`}>
              <span className="block truncate text-sm font-medium">{session.title || session.id}</span>
              <span className="mt-1 block text-xs text-slate-500">{formatStatus(session.status)} · {session.file_count ?? 0} files</span>
              {(session.updated_at || session.created_at) && <span className="mt-1 block text-[11px] text-slate-600">{formatDate(session.updated_at ?? session.created_at)}</span>}
            </button>
          ))}
        </div>
      </WorkspaceCard>

      <WorkspaceCard title="Uploaded sources" aside={`${activeSession?.files?.length ?? 0}`}>
        <form onSubmit={onUpload} className="space-y-2">
          <input type="file" multiple onChange={(event) => onFilesChange(Array.from(event.target.files ?? []))} className="block w-full rounded-lg border border-slate-400/[0.10] bg-[#050B16] px-3 py-2 text-xs text-slate-200 file:mr-3 file:rounded-md file:border-0 file:bg-[#1C2B45] file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-slate-100" />
          <button type="submit" disabled={!activeSessionId || selectedFiles.length === 0 || loading} className="w-full rounded-lg px-3 py-2 text-sm font-semibold text-slate-100 transition hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-50">Upload selected files</button>
        </form>
        <div className="mt-3 max-h-44 divide-y divide-white/[0.06] overflow-auto pr-1">
          {(activeSession?.files ?? []).length === 0 ? (
            <p className="py-3 text-sm text-slate-500">No files uploaded yet.</p>
          ) : activeSession?.files?.map((file) => <SourceFileRow key={file.id} file={file} />)}
        </div>
      </WorkspaceCard>

      <WorkspaceCard title="Target Mirai contract">
        <form onSubmit={onUploadTargetContract} className="space-y-2">
          <input type="file" multiple accept=".zip,.json,.csv" onChange={(event) => onTargetFilesChange(Array.from(event.target.files ?? []))} className="block w-full rounded-lg border border-slate-400/[0.10] bg-[#050B16] px-3 py-2 text-xs text-slate-200 file:mr-3 file:rounded-md file:border-0 file:bg-[#1C2B45] file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-slate-100" />
          <button type="submit" disabled={!activeSessionId || selectedTargetFiles.length === 0 || loading} className="w-full rounded-lg px-3 py-2 text-sm font-semibold text-slate-100 transition hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-50">Upload target contract</button>
        </form>
        <div className="mt-4 border-t border-slate-400/[0.07] pt-3">
          <p className="text-sm font-medium text-white">{targetContract ? `${targetContract.contract_id ?? 'generic_tabular_doe'} · ${targetContract.package_style ?? 'package'}` : 'No target uploaded'}</p>
          <p className="mt-1 text-xs leading-5 text-slate-500">{targetContract ? `Required files: ${(targetContract.required_files ?? []).join(', ')}` : 'Upload a Mirai package ZIP or manifest/data_dictionary/package CSV files. Fraunhofer packages are examples, not product target options.'}</p>
          {targetContract?.fields && <p className="mt-1 text-xs text-slate-600">{targetContract.fields.length} contract columns · {(targetContract.tables ?? []).length} tables</p>}
        </div>
      </WorkspaceCard>

      <WorkspaceCard title="Source indexing">
        <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          <MetricPill label="Indexed" value={`${sourceSummary.indexedFiles} files`} />
          <MetricPill label="Containers" value={`${sourceSummary.containers}`} />
          <MetricPill label="Tabular columns" value={`${sourceSummary.tabularColumns}`} />
          <MetricPill label="CSV/XLSX" value={`${sourceSummary.csvFiles + sourceSummary.xlsxFiles}`} />
        </div>
        <p className="mt-3 border-t border-slate-400/[0.07] pt-3 text-xs leading-5 text-slate-500">Detected: {sourceSummary.csvFiles} CSV · {sourceSummary.xlsxFiles} XLSX · {sourceSummary.pdfFiles} PDF · {sourceSummary.docxFiles} DOCX</p>
      </WorkspaceCard>
      </>}
    </aside>
  )
}

function MappingAgentPanel({ activeSessionId, loading, loadingLabel, draft, conversation, instruction, issues, mappingBoardLength, onInstructionChange, onAskAgent, showFullNotes, onToggleNotes }: { activeSessionId: string; loading: boolean; loadingLabel: string; draft: KnowledgeIntakeDraft | null; conversation: Array<{ role: string; content: string; created_at?: string }>; instruction: string; issues: string; mappingBoardLength: number; onInstructionChange: (value: string) => void; onAskAgent: (instruction?: string) => Promise<void>; showFullNotes: boolean; onToggleNotes: () => void }) {
  const agentStatus = getAgentStatusText(loading, loadingLabel, draft, mappingBoardLength)
  return (
    <main className="flex min-h-0 flex-col lg:col-span-1">
      <div className="flex items-start justify-between gap-4 border-b border-slate-400/[0.12] bg-[linear-gradient(90deg,rgba(139,92,246,0.10),rgba(91,168,255,0.04))] px-3 pb-3 pt-3">
        <div>
          <h3 className="text-sm font-semibold text-[#F3F7FF]">Mapping Agent</h3>
          <p className="mt-1 text-xs text-[#7E8AA0]">Map uploaded sources into the selected Mirai contract.</p>
        </div>
        <div className="flex items-center gap-2 text-xs font-medium text-[#63D69A]">
          {loading && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#5BA8FF]/30 border-t-[#5BA8FF]" />}
          <span>{agentStatus}</span>
        </div>
      </div>

      <div className="mt-4 flex min-h-[300px] flex-1 flex-col overflow-hidden">
        <div className="flex-1 space-y-3 overflow-auto py-2">
          {conversation.length === 0 ? (
            <div className="border-y border-slate-400/[0.12] bg-[#101A2C]/65 py-8 text-center text-sm leading-6 text-[#AAB6C8]">Run the agent to inspect uploaded sources and propose a source-to-contract mapping.</div>
          ) : conversation.slice(-12).map((turn, index) => (
            <div key={`${turn.role}-${index}`} className={turn.role === 'user' ? 'text-right' : 'text-left'}>
              <div className={`inline-block max-w-[88%] rounded-lg border px-3 py-2 text-sm leading-6 ${turn.role === 'user' ? 'border-[#5BA8FF]/32 bg-[#5BA8FF]/[0.11] text-[#F3F7FF]' : 'border-slate-400/[0.14] bg-[#101A2C]/90 text-[#D7DEEA]'}`}>
                <span className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.10em] text-[#7E8AA0]">{turn.role === 'user' ? 'You' : 'Mapping agent'}</span>
                {turn.content}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 border-t border-slate-400/[0.12] bg-[#0B1220] pt-4">
        <textarea value={instruction} onChange={(event) => onInstructionChange(event.target.value)} rows={4} placeholder="Ask the agent, e.g. 'Use voltage and RH as inputs and current density/ECSA as outputs' or 'approve suggested mapping'." className="w-full rounded-lg border border-slate-400/[0.18] bg-[#050914] px-3 py-2 text-sm leading-6 text-[#F3F7FF] outline-none placeholder:text-[#6F7A90] focus:border-[#5BA8FF]/40 focus:ring-0" />
        <div className="mt-3 flex flex-wrap gap-3">
          <button type="button" onClick={() => { void onAskAgent() }} disabled={!activeSessionId || loading} className="rounded-lg bg-[#2563EB] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#3478FF] disabled:cursor-not-allowed disabled:opacity-50">Ask agent / update mapping</button>
          <button type="button" onClick={() => { void onAskAgent('approve suggested mapping') }} disabled={!activeSessionId || loading || mappingBoardLength === 0} className="rounded-lg px-4 py-2 text-sm font-semibold text-[#8FCBFF] hover:bg-[#5BA8FF]/10 disabled:cursor-not-allowed disabled:opacity-50">Approve suggested mapping</button>
        </div>
      </div>

      <div className="mt-5 border-t border-slate-400/[0.12] pt-4">
        <div className="flex items-center justify-between gap-3">
          <h4 className="text-sm font-semibold text-[#F3F7FF]">Agent notes</h4>
          <button type="button" onClick={onToggleNotes} className="text-xs font-semibold text-[#8FCBFF] hover:text-[#F3F7FF]">{showFullNotes ? 'Hide full notes' : 'View full notes'}</button>
        </div>
        <AgentNotesPreview issues={issues} draft={draft} />
        {showFullNotes && <pre className="mt-3 max-h-44 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-400/[0.14] bg-[#050914] p-3 text-xs leading-5 text-[#B8C2D4]">{issues || 'Run the mapping agent to generate notes.'}</pre>}
      </div>
    </main>
  )
}

function LiveResultsPanel({ draft, tableName, tableOptions, currentTable, mappingBoard, mappingStats, blockers, validationSummary, loading, showFullMapping, onToggleMapping, onTableNameChange, onApprove, onReject, onExport, onGoToDataIntake, collapsed, onCollapsedChange }: { draft: KnowledgeIntakeDraft | null; tableName: string; tableOptions: string[]; currentTable: { columns: string[]; preview_rows: string[]; total_rows: number } | null; mappingBoard: KnowledgeIntakeMappingRow[]; mappingStats: MappingStats; blockers: string[]; validationSummary: ValidationSummary; loading: boolean; showFullMapping: boolean; onToggleMapping: () => void; onTableNameChange: (value: string) => void; onApprove: () => Promise<void>; onReject: () => Promise<void>; onExport: () => Promise<void>; onGoToDataIntake: () => void; collapsed: boolean; onCollapsedChange: (collapsed: boolean) => void }) {
  const missingRows = mappingBoard.filter((row) => isMissingMapping(row))
  const transformBlocker = blockers.find((blocker) => blocker.toLowerCase().includes('deterministic transform'))
  return (
    <aside className={`flex min-h-0 flex-col border-y border-slate-400/[0.10] ${collapsed ? 'items-center py-4' : 'gap-6 py-4'} lg:col-span-1`}>
      <div className={`flex w-full items-center ${collapsed ? 'justify-center' : 'justify-between px-1'}`}>
        {!collapsed && <p className="text-sm font-semibold text-[#F3F7FF]">Inspector</p>}
        <button type="button" onClick={() => onCollapsedChange(!collapsed)} className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-400/[0.12] text-sm font-semibold text-[#9FB0C8] transition hover:border-[#5BA8FF]/30 hover:bg-[#5BA8FF]/10 hover:text-[#F3F7FF]" aria-label={collapsed ? 'Show inspector panel' : 'Hide inspector panel'} title={collapsed ? 'Show inspector' : 'Hide inspector'}>
          {collapsed ? '‹' : '›'}
        </button>
      </div>
      {collapsed ? <div className="mt-5 text-[0.65rem] font-semibold uppercase tracking-[0.12em] text-[#7E8AA0] [writing-mode:vertical-rl]">Inspector</div> : <>
      <section className="bg-[#081526]/55 p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-sm font-semibold text-white">Mapping status</h3>
            <p className="mt-1 text-xs text-slate-500">{draft ? formatStatus(draft.status) : 'Not run'}</p>
          </div>
          <StatusChip label={validationSummary.label} tone={validationSummary.label === 'Ready' ? 'green' : validationSummary.label === 'Blocked' ? 'amber' : 'blue'} />
        </div>

        <div className="mt-5 flex items-end justify-between gap-4">
          <div>
            <p className="text-3xl font-semibold text-white">{mappingStats.mappedFields} / {mappingStats.totalFields || 0}</p>
            <p className="mt-1 text-sm text-slate-500">fields mapped</p>
          </div>
        </div>

        <div className="mt-5 space-y-3 border-t border-slate-400/[0.07] pt-4">
          <ProgressLine label="Inputs" value={mappingStats.inputMapped} total={mappingStats.inputTotal} />
          <ProgressLine label="Outputs" value={mappingStats.outputMapped} total={mappingStats.outputTotal} />
          {(mappingStats.highConfidence + mappingStats.mediumConfidence + mappingStats.lowConfidence) > 0 && (
            <p className="text-xs text-slate-500">Confidence: {mappingStats.highConfidence} high · {mappingStats.mediumConfidence} medium · {mappingStats.lowConfidence} low</p>
          )}
        </div>

        <div className="mt-5 border-t border-slate-400/[0.07] pt-4">
          <div className="mb-2 flex items-center justify-between gap-3">
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Missing fields</span>
            <span className="text-xs text-slate-500">{missingRows.length}</span>
          </div>
          {missingRows.length === 0 ? (
            <p className="text-sm text-emerald-200">None</p>
          ) : (
            <div className="flex max-h-32 flex-wrap gap-2 overflow-auto pr-1">
              {missingRows.map((row) => <span key={row.field} className="rounded-full bg-amber-300/10 px-2.5 py-1 text-xs text-amber-100">{row.field}</span>)}
            </div>
          )}
        </div>

        <div className="mt-5 space-y-3 border-t border-slate-400/[0.07] pt-4 text-sm">
          <div>
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Validation</span>
            <p className="mt-1 font-semibold text-white">{validationSummary.label}</p>
          </div>
          <div>
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Reason</span>
            <p className="mt-1 leading-6 text-slate-400">{transformBlocker ?? validationSummary.reason}</p>
          </div>
          <div>
            <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Required next step</span>
            <p className="mt-1 leading-6 text-slate-400">{validationSummary.nextStep}</p>
          </div>
        </div>

        <div className="mt-5 border-t border-slate-400/[0.07] pt-4">
          <p className="text-sm leading-6 text-slate-400">{draft?.validation_passed ? 'Validated package can be approved and exported after manual approval.' : 'Export package blocked until contract validation passes.'}</p>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <button type="button" onClick={() => { void onApprove() }} disabled={loading || !draft || draft.status === 'approved_persistent' || !draft.validation_passed} className="rounded-lg bg-emerald-500/90 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">Approve draft</button>
            <button type="button" onClick={() => { void onReject() }} disabled={loading || !draft} className="rounded-lg px-3 py-2 text-sm font-semibold text-red-100 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50">Reject/delete</button>
            <button type="button" onClick={() => { void onExport() }} disabled={loading || !draft || draft.status !== 'approved_persistent' || !draft.validation_passed} className="rounded-lg px-3 py-2 text-sm font-semibold text-white hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-50">Export ZIP</button>
            <button type="button" onClick={onGoToDataIntake} className="rounded-lg px-3 py-2 text-sm font-semibold text-[#BDEAFF] hover:bg-[#74C7F5]/10">Data Intake</button>
          </div>
        </div>
      </section>

      <WorkspaceCard title="Detailed mapping" aside={mappingBoard.length ? `${mappingBoard.length} rows` : undefined}>
        <button type="button" onClick={onToggleMapping} disabled={!draft} className="w-full rounded-lg px-3 py-2 text-sm font-semibold text-white hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-50">{showFullMapping ? 'Hide full mapping table' : 'View full mapping table'}</button>
        {showFullMapping && draft && (
          <div className="mt-3 max-h-80 overflow-auto rounded-lg bg-[#050B16]">
            {mappingBoard.length > 0 && <MappingTable rows={mappingBoard} />}
            {currentTable && (
              <div className="border-t border-slate-400/[0.07] p-3">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Package preview</span>
                  {tableOptions.length > 0 && <select value={tableName} onChange={(event) => onTableNameChange(event.target.value)} className="rounded-lg border border-slate-400/[0.10] bg-[#050B16] px-2 py-1 text-xs text-slate-100">{tableOptions.map((name) => <option key={name} value={name}>{name}</option>)}</select>}
                </div>
                <PackagePreview tableName={tableName} table={currentTable} />
              </div>
            )}
          </div>
        )}
      </WorkspaceCard>
      </>}
    </aside>
  )
}

function WorkspaceCard({ title, aside, children }: { title: string; aside?: string; children: ReactNode }) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3 border-b border-slate-400/[0.10] pb-2">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        {aside && <span className="text-xs text-slate-500">{aside}</span>}
      </div>
      {children}
    </section>
  )
}

function SourceFileRow({ file }: { file: KnowledgeIntakeFile }) {
  return (
    <div className="px-1 py-2.5">
      <p className="truncate text-sm font-medium text-slate-100" title={file.filename}>{file.filename}</p>
      <p className="mt-1 text-xs text-slate-500">{file.file_type?.toUpperCase()} · {formatStatus(file.parse_status ?? 'uploaded')}</p>
    </div>
  )
}

function MetricPill({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-600">{label}</p>
      <p className="mt-1 text-sm font-semibold text-slate-100">{value}</p>
    </div>
  )
}

function StatusChip({ label, tone }: { label: string; tone: 'green' | 'amber' | 'blue' }) {
  const classes = tone === 'green' ? 'bg-emerald-500/10 text-emerald-100' : tone === 'amber' ? 'bg-amber-500/10 text-amber-100' : 'bg-[#74C7F5]/10 text-[#D9F3FF]'
  return <span className={`rounded-full px-3 py-1 text-xs font-semibold ${classes}`}>{label}</span>
}

function ProgressLine({ label, value, total }: { label: string; value: number; total: number }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-slate-400"><span>{label}</span><span>{value} / {total}</span></div>
      <div className="h-2 overflow-hidden rounded-full bg-white/[0.07]"><div className="h-full rounded-full bg-[#74C7F5]" style={{ width: `${pct}%` }} /></div>
    </div>
  )
}

function AgentNotesPreview({ issues, draft }: { issues: string; draft: KnowledgeIntakeDraft | null }) {
  const lines = issues.split('\n').map((line) => line.trim()).filter(Boolean)
  const plannerLine = lines.find((line) => line.toLowerCase().startsWith('agent planner:'))
  const targetLine = lines.find((line) => line.toLowerCase().startsWith('target contract:'))
  return (
    <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
      <div><dt className="text-slate-600">Target contract</dt><dd className="mt-1 text-slate-300">{targetLine?.replace('Target contract:', '').trim() || String(draft?.schema?.template_id ?? 'Not selected')}</dd></div>
      <div><dt className="text-slate-600">Planner</dt><dd className="mt-1 text-slate-300">{plannerLine?.replace('Agent planner:', '').trim() || 'Not run'}</dd></div>
      <div><dt className="text-slate-600">Mode</dt><dd className="mt-1 text-slate-300">Contract-driven mapping</dd></div>
      <div><dt className="text-slate-600">Transform</dt><dd className="mt-1 text-slate-300">{draft?.validation_passed ? 'Validated package' : 'None executed'}</dd></div>
    </dl>
  )
}

function MappingTable({ rows }: { rows: KnowledgeIntakeMappingRow[] }) {
  return (
    <table className="min-w-full divide-y divide-white/[0.06] text-xs">
      <thead className="bg-white/[0.035] text-slate-300">
        <tr>
          <th className="px-3 py-2 text-left font-semibold">Contract field</th>
          <th className="px-3 py-2 text-left font-semibold">Role</th>
          <th className="px-3 py-2 text-left font-semibold">Suggested source</th>
          <th className="px-3 py-2 text-left font-semibold">Confidence</th>
          <th className="px-3 py-2 text-left font-semibold">Status</th>
          <th className="px-3 py-2 text-left font-semibold">Rationale</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-white/[0.06] text-slate-300">
        {rows.map((row) => (
          <tr key={row.field}>
            <td className="px-3 py-2 font-medium text-slate-100">{row.field}</td>
            <td className="px-3 py-2">{row.role}</td>
            <td className="max-w-[240px] truncate px-3 py-2">{row.source_column ? `${row.source_column}${row.source_table ? ` · ${row.source_table}` : ''}` : '—'}</td>
            <td className="px-3 py-2">{row.confidence ?? 'none'}</td>
            <td className={`px-3 py-2 ${isMissingMapping(row) ? 'text-amber-300' : 'text-emerald-300'}`}>{row.status}</td>
            <td className="max-w-[300px] px-3 py-2 text-slate-400">{row.rationale}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function PackagePreview({ tableName, table }: { tableName: string; table: { columns: string[]; preview_rows: string[]; total_rows: number } }) {
  return (
    <table className="min-w-full divide-y divide-white/[0.06] text-xs">
      <thead className="bg-white/[0.035] text-slate-300">
        <tr>{table.columns.slice(0, 10).map((column) => <th key={`${tableName}-${column}`} className="px-3 py-2 text-left font-semibold">{column}</th>)}</tr>
      </thead>
      <tbody className="divide-y divide-white/[0.06] text-slate-300">
        {table.preview_rows.slice(0, 10).map((row, index) => (
          <tr key={`${tableName}-${index}`}>{row.split(',').slice(0, 10).map((cell, cellIndex) => <td key={cellIndex} className="max-w-[220px] truncate px-3 py-2">{cell}</td>)}</tr>
        ))}
      </tbody>
    </table>
  )
}

function getMappingStats(mappingRows: KnowledgeIntakeMappingRow[]): MappingStats {
  return mappingRows.reduce<MappingStats>((stats, row) => {
    const mapped = !isMissingMapping(row)
    stats.totalFields += 1
    if (mapped) stats.mappedFields += 1
    else stats.missingFields += 1
    if (row.role === 'input') {
      stats.inputTotal += 1
      if (mapped) stats.inputMapped += 1
    }
    if (row.role === 'output') {
      stats.outputTotal += 1
      if (mapped) stats.outputMapped += 1
    }
    if (row.confidence === 'high') stats.highConfidence += 1
    if (row.confidence === 'medium') stats.mediumConfidence += 1
    if (row.confidence === 'low') stats.lowConfidence += 1
    return stats
  }, { totalFields: 0, mappedFields: 0, missingFields: 0, inputTotal: 0, inputMapped: 0, outputTotal: 0, outputMapped: 0, highConfidence: 0, mediumConfidence: 0, lowConfidence: 0 })
}

function getValidationSummary(draft: KnowledgeIntakeDraft | null, blockers: string[]): ValidationSummary {
  if (!draft) {
    return { label: 'Unknown', reason: 'No mapping run has been created yet.', nextStep: 'Create or select a session, upload sources, then ask the mapping agent.' }
  }
  if (draft.validation_passed) {
    return { label: 'Ready', reason: 'Selected contract validation passed.', nextStep: 'Approve the validated draft, then export the package ZIP.' }
  }
  if (draft.status === 'needs_user_input') {
    return { label: 'Needs user input', reason: blockers[0] ?? 'The agent needs missing field mappings or source context.', nextStep: 'Upload CSV/XLSX files, or describe where the contract variables are located.' }
  }
  return { label: 'Blocked', reason: blockers[0] ?? 'Contract validation has not passed.', nextStep: 'Resolve missing mappings and rerun the mapping agent.' }
}

function getSourceSummary(files: KnowledgeIntakeFile[], tabularColumns: number): SourceSummary {
  return files.reduce<SourceSummary>((summary, file) => {
    const type = `${file.file_type || file.filename.split('.').pop() || ''}`.toLowerCase()
    summary.indexedFiles += file.parse_status ? 1 : 0
    if (type.includes('zip')) summary.containers += 1
    if (type.includes('csv')) summary.csvFiles += 1
    if (type.includes('xlsx')) summary.xlsxFiles += 1
    if (type.includes('pdf')) summary.pdfFiles += 1
    if (type.includes('docx')) summary.docxFiles += 1
    summary.tabularColumns = tabularColumns
    return summary
  }, { indexedFiles: 0, containers: 0, tabularColumns, csvFiles: 0, xlsxFiles: 0, pdfFiles: 0, docxFiles: 0 })
}

function isMissingMapping(row: KnowledgeIntakeMappingRow): boolean {
  const source = String(row.source_column ?? '').trim()
  return row.status === 'missing' || !source || source === '—' || source === '-'
}

function getAgentStatusText(loading: boolean, loadingLabel: string, draft: KnowledgeIntakeDraft | null, mappingBoardLength: number): string {
  if (loading) return loadingLabel || 'Agent is working…'
  if (!draft) return 'Agent waiting for sources'
  if (draft.validation_passed) return 'Validation passed'
  if (mappingBoardLength > 0 && draft.status !== 'needs_user_input') return 'Mapping draft ready for review'
  if (draft.status === 'needs_user_input') return 'Agent needs user input'
  return 'Mapping draft available'
}

function formatStatus(value: string): string {
  return value.replace(/_/g, ' ')
}

function formatDate(value?: string): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}
