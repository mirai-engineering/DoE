import { FormEvent, useEffect, useMemo, useState } from 'react'
import type { ProjectSchema } from '../lib/api'
import {
  approveKnowledgeIntakeDraft,
  createIngestionSession,
  createKnowledgeIntakeSession,
  downloadKnowledgeIntakePackage,
  exportKnowledgeIntakePackage,
  getKnowledgeIntakeIssues,
  getKnowledgeIntakeSession,
  type KnowledgeIntakeDraft,
  type KnowledgeIntakeSession,
  listKnowledgeIntakeSessions,
  matchKnowledgeIntakeMiraiContract,
  rejectKnowledgeIntakeDraft,
  saveKnowledgeIntakeInstruction,
  uploadKnowledgeIntakeFiles,
} from '../lib/api'

const defaultInstruction = 'Inspect these sources, infer a candidate source-to-contract mapping, list missing fields/questions, and run only approved deterministic backend transforms for the selected target contract.'

const targetContracts = [
  { id: 'generic_tabular_doe', label: 'Generic model_table.csv / tabular DoE loop' },
  { id: 'mirai_fixed_source_tables', label: 'Mirai tabular DoE fixed-source tables' },
  { id: 'process_maintenance_table', label: 'Process-engineering maintenance table' },
  { id: 'fraunhofer2miraicontract-full', label: 'Demo adapter: Fraunhofer cathode catalyst' },
]

export function KnowledgeIntakePage({ schema, onGoToDataIntake }: { schema: ProjectSchema; onGoToDataIntake: () => void }) {
  const [sessions, setSessions] = useState<KnowledgeIntakeSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState('')
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [instruction, setInstruction] = useState(defaultInstruction)
  const [targetContractId, setTargetContractId] = useState('generic_tabular_doe')
  const [draft, setDraft] = useState<KnowledgeIntakeDraft | null>(null)
  const [issues, setIssues] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingLabel, setLoadingLabel] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [tableName, setTableName] = useState('experiments.csv')

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
      const selectedTarget = targetContracts.find((target) => target.id === targetContractId)
      const session = await createKnowledgeIntakeSession(schema.project_id, `Knowledge intake → ${selectedTarget?.label ?? targetContractId}`, targetContractId)
      setNotice('Knowledge intake session created.')
      await refreshSessions(session.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create session')
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

  async function handleMatch() {
    if (!activeSessionId) return
    setLoading(true)
    setLoadingLabel('Agent planner is inspecting sources and drafting the contract mapping…')
    setNotice(null)
    setError(null)
    try {
      await saveKnowledgeIntakeInstruction(schema.project_id, activeSessionId, instruction)
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
    setLoadingLabel('Exporting the validated package and creating a Data Intake session…')
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
      const packageFile = new File([blob], 'mirai_package.zip', { type: 'application/zip' })
      const ingestion = await createIngestionSession(schema.display_name, [packageFile], `Created from Knowledge Intake session ${activeSessionId}.`, { existingProjectId: schema.project_id })
      setNotice(`Mirai package exported and handed off to Data Intake session ${ingestion.ingestion_session_id}. Continue in Data Intake / Preprocessing.`)
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

  const currentTable = draft?.tables?.[tableName] ?? null
  const tableOptions = Object.keys(draft?.tables ?? {})

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-white/[0.08] bg-[#081526]/88 p-6 shadow-[0_22px_70px_rgba(2,8,23,0.24)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#74C7F5]">Knowledge Intake Harness MVP</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white">Contract-driven intake loop</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">
              This additive loop inspects uploaded sources, records a mapping/transform plan, runs only approved deterministic backend transforms, and exports only after the selected contract validates. The Fraunhofer converter is a demo adapter, not the generic product path.
            </p>
          </div>
          <button type="button" onClick={handleCreateSession} disabled={loading} className="rounded-lg bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-950/30 transition hover:bg-[#4C7DFF] disabled:cursor-not-allowed disabled:opacity-60">
            New session
          </button>
        </div>
        {loading && <div className="mt-4 flex items-center gap-3 rounded-lg border border-[#74C7F5]/30 bg-[#74C7F5]/10 p-3 text-sm text-[#D9F3FF]"><span className="h-4 w-4 animate-spin rounded-full border-2 border-[#74C7F5]/30 border-t-[#74C7F5]" />{loadingLabel || 'Working…'}</div>}
        {error && <div className="mt-4 rounded-lg border border-red-300/30 bg-red-500/10 p-3 text-sm text-red-100">{error}</div>}
        {notice && <div className="mt-4 rounded-lg border border-emerald-300/30 bg-emerald-500/10 p-3 text-sm text-emerald-100">{notice}</div>}
      </section>

      <section className="grid gap-5 lg:grid-cols-[320px_1fr]">
        <aside className="rounded-2xl border border-white/[0.08] bg-[#081526]/80 p-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-white">Sessions</h3>
            <span className="text-xs text-slate-400">{sessions.length}</span>
          </div>
          <div className="mt-3 space-y-2">
            {sessions.length === 0 ? (
              <p className="rounded-lg border border-dashed border-white/10 p-3 text-sm text-slate-400">Create a session to start uploading source files.</p>
            ) : sessions.map((session) => (
              <button key={session.id} type="button" onClick={() => { void handleSelectSession(session.id) }} className={`w-full rounded-lg border px-3 py-2 text-left transition ${session.id === activeSessionId ? 'border-[#74C7F5]/50 bg-[#2F6BFF]/10' : 'border-white/[0.07] bg-white/[0.025] hover:bg-white/[0.045]'}`}>
                <span className="block text-sm font-medium text-white">{session.title || session.id}</span>
                <span className="mt-1 block text-xs text-slate-400">{session.status} · {session.file_count ?? 0} files</span>
              </button>
            ))}
          </div>
        </aside>

        <div className="space-y-5">
          <section className="rounded-2xl border border-white/[0.08] bg-[#081526]/80 p-5">
            <h3 className="text-base font-semibold text-white">1. Upload source files</h3>
            <p className="mt-1 text-sm text-slate-400">MVP accepts PDF, DOCX, XLSX, CSV, and ZIP containers. Generic arbitrary-data conversion is plan-first; export requires a validated deterministic transform.</p>
            <form onSubmit={handleUpload} className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
              <input type="file" multiple onChange={(event) => setSelectedFiles(Array.from(event.target.files ?? []))} className="block w-full rounded-lg border border-white/[0.08] bg-[#050B16] px-3 py-2 text-sm text-slate-200 file:mr-3 file:rounded-md file:border-0 file:bg-[#1C2B45] file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-slate-100" />
              <button type="submit" disabled={!activeSessionId || selectedFiles.length === 0 || loading} className="rounded-lg border border-white/[0.12] px-4 py-2 text-sm font-semibold text-white transition hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-50">Upload</button>
            </form>
            {activeSession?.files && activeSession.files.length > 0 && (
              <div className="mt-4 overflow-hidden rounded-lg border border-white/[0.07]">
                <table className="min-w-full divide-y divide-white/[0.06] text-sm">
                  <tbody className="divide-y divide-white/[0.06]">
                    {activeSession.files.slice(0, 8).map((file) => (
                      <tr key={file.id}>
                        <td className="px-3 py-2 text-slate-200">{file.filename}</td>
                        <td className="px-3 py-2 text-slate-400">{file.file_type}</td>
                        <td className="px-3 py-2 text-slate-400">{file.parse_status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="rounded-2xl border border-white/[0.08] bg-[#081526]/80 p-5">
            <h3 className="text-base font-semibold text-white">2. Choose target contract and run the loop</h3>
            <label className="mt-3 block text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Target contract goal</label>
            <select value={targetContractId} onChange={(event) => setTargetContractId(event.target.value)} className="mt-2 w-full rounded-lg border border-white/[0.08] bg-[#050B16] px-3 py-2 text-sm text-slate-100">
              {targetContracts.map((target) => <option key={target.id} value={target.id}>{target.label}</option>)}
            </select>
            <textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} rows={4} className="mt-3 w-full rounded-lg border border-white/[0.08] bg-[#050B16] px-3 py-2 text-sm leading-6 text-slate-100 outline-none ring-[#74C7F5]/30 focus:ring-2" />
            <div className="mt-3 flex flex-wrap gap-3">
              <button type="button" onClick={handleMatch} disabled={!activeSessionId || loading} className="rounded-lg bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#4C7DFF] disabled:cursor-not-allowed disabled:opacity-50">Run intake loop</button>
              <p className="self-center text-xs text-slate-400">Selected target: {activeSession?.target_contract_id ?? targetContractId}. Export requires contract validation.</p>
            </div>
          </section>

          {draft && (
            <section className="rounded-2xl border border-white/[0.08] bg-[#081526]/80 p-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-base font-semibold text-white">3. Review draft table</h3>
                  <p className="mt-1 text-sm text-slate-400">Status: {draft.status} · validation: {draft.validation_passed ? 'passed' : 'blocked'} · {draft.source_reference_mode}</p>
                </div>
                <select value={tableName} onChange={(event) => setTableName(event.target.value)} className="rounded-lg border border-white/[0.08] bg-[#050B16] px-3 py-2 text-sm text-slate-100">
                  {tableOptions.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </div>
              {currentTable && (
                <div className="mt-4 overflow-auto rounded-lg border border-white/[0.07]">
                  <table className="min-w-full divide-y divide-white/[0.06] text-xs">
                    <thead className="bg-white/[0.035] text-slate-300">
                      <tr>{currentTable.columns.slice(0, 10).map((column) => <th key={column} className="px-3 py-2 text-left font-semibold">{column}</th>)}</tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.06] text-slate-300">
                      {currentTable.preview_rows.slice(0, 10).map((row, index) => (
                        <tr key={`${tableName}-${index}`}>{row.split(',').slice(0, 10).map((cell, cellIndex) => <td key={cellIndex} className="max-w-[220px] truncate px-3 py-2">{cell}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                <div className="rounded-lg border border-white/[0.07] bg-[#050B16] p-3">
                  <h4 className="text-sm font-semibold text-white">Issues / notes</h4>
                  <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-xs leading-5 text-slate-300">{issues || 'Run Match Mirai contract to generate notes.'}</pre>
                </div>
                <div className="rounded-lg border border-white/[0.07] bg-[#050B16] p-3">
                  <h4 className="text-sm font-semibold text-white">Manual gates</h4>
                  <p className="mt-2 text-sm leading-6 text-slate-400">Approve only after validation passes. Export is blocked until a selected contract has validated package files. After export, upload the ZIP through Data Intake and continue through the existing approval flow.</p>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <button type="button" onClick={handleApprove} disabled={loading || draft.status === 'approved_persistent' || !draft.validation_passed} className="rounded-lg bg-emerald-500/90 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">Approve validated draft</button>
                    <button type="button" onClick={handleReject} disabled={loading} className="rounded-lg border border-red-300/30 px-4 py-2 text-sm font-semibold text-red-100 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50">Reject/delete draft</button>
                    <button type="button" onClick={handleExport} disabled={loading || draft.status !== 'approved_persistent' || !draft.validation_passed} className="rounded-lg border border-white/[0.12] px-4 py-2 text-sm font-semibold text-white hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-50">Export package ZIP</button>
                    <button type="button" onClick={onGoToDataIntake} className="rounded-lg border border-[#74C7F5]/35 px-4 py-2 text-sm font-semibold text-[#BDEAFF] hover:bg-[#74C7F5]/10">Go to Data Intake</button>
                  </div>
                </div>
              </div>
            </section>
          )}
        </div>
      </section>
    </div>
  )
}
