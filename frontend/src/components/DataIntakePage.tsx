import { useState } from 'react'
import type { AccountStatus, IngestionSessionResponse, ProjectSchema, ProjectSummary, WorkspaceSummary } from '../lib/api'
import { createIngestionSession } from '../lib/api'
import { DisclosurePanel, LifecycleStepper, SectionCard } from './ui'

export function DataIntakePage({ schema, projects, workspaces, account, onReviewPreprocessing, onSessionCreated }: { schema: ProjectSchema | null; projects: ProjectSummary[]; workspaces: WorkspaceSummary[]; account?: AccountStatus | null; onReviewPreprocessing?: () => void; onSessionCreated?: (session: IngestionSessionResponse) => void | Promise<void> }) {
  const [intakeMode, setIntakeMode] = useState<'new_project' | 'existing_project'>('new_project')
  const [workspaceName, setWorkspaceName] = useState(schema?.workspace_name || workspaces[0]?.display_name || '')
  const [existingProjectId, setExistingProjectId] = useState(schema?.project_id || projects[0]?.id || '')
  const [projectName, setProjectName] = useState('New Mirai ML Project')
  const [notes, setNotes] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [session, setSession] = useState<IngestionSessionResponse | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleUpload() {
    if (storageBlocked) {
      setError(account?.message || 'Workspace setup is required before uploading data.')
      return
    }
    if (intakeMode === 'existing_project' && !existingProjectId) {
      setError('Select an existing project or create a new one.')
      return
    }
    if (!files.length) {
      setError('Select a Mirai package to continue.')
      return
    }
    setUploading(true)
    setError(null)
    try {
      const selectedExistingProject = projects.find((project) => project.id === existingProjectId)
      const effectiveProjectName = intakeMode === 'existing_project'
        ? selectedExistingProject?.display_name || schema?.display_name || 'Selected project'
        : projectName
      const effectiveWorkspaceName = intakeMode === 'existing_project'
        ? workspaceFor(selectedExistingProject) || schema?.workspace_name || workspaceName
        : workspaceName || currentWorkspace?.display_name || 'Your workspace'
      const result = await createIngestionSession(effectiveProjectName, files, notes, {
        workspaceName: effectiveWorkspaceName,
        existingProjectId: intakeMode === 'existing_project' ? existingProjectId : undefined,
      })
      setSession(result)
      window.localStorage.setItem('mirai.latestIngestionSession', JSON.stringify(result))
      window.localStorage.setItem('mirai.activeProjectId', result.project_id)
      await onSessionCreated?.(result)
      onReviewPreprocessing?.()
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  function workspaceFor(project?: ProjectSummary) {
    const explicit = project?.workspace_name
    if (explicit) return explicit
    return schema?.workspace_name || workspaces[0]?.display_name || workspaceName || 'Your workspace'
  }

  const selectedExistingProject = projects.find((project) => project.id === existingProjectId)
  const currentWorkspace = workspaces.find((workspace) => workspace.display_name === workspaceName) || workspaces[0]
  const capabilitiesBlocked = account ? !account.can_upload || account.status !== 'active_single_workspace' : false
  const storageBlocked = capabilitiesBlocked || (projects.length === 0 && currentWorkspace?.storage_provisioned === false)
  const workspaceOptions = Array.from(new Set([...workspaces.map((workspace) => workspace.display_name), ...projects.map((project) => workspaceFor(project)), workspaceName].filter(Boolean)))

  return (
    <div className="space-y-6">
      <LifecycleStepper steps={[
        { id: 'upload', label: 'Create project', status: session ? 'done' : 'current' },
        { id: 'metadata', label: 'Review metadata', status: session ? 'current' : 'locked' },
        { id: 'preprocess', label: 'Preprocess', status: 'locked' },
        { id: 'train', label: 'Train', status: 'locked' },
        { id: 'quality', label: 'Quality', status: 'locked' },
      ]} />

      <SectionCard>
        <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#74C7F5]">Data Intake</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.055em] text-white">Create a project from data</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">Upload a Mirai package. We’ll validate it, prepare metadata review, and move you to preprocessing. Storage stays scoped to your signed-in workspace.</p>
            {account && account.status !== 'active_single_workspace' ? (
              <div className="mt-5 rounded-md border border-[#74C7F5]/30 bg-[#0D1B2D] px-4 py-3 text-sm text-slate-300">
                <div className="font-semibold text-white">Workspace setup required</div>
                <div className="mt-1">{account.message || 'Your account is active, but no client workspace has been assigned yet.'}</div>
              </div>
            ) : projects.length === 0 && (
              <div className="mt-5 rounded-md border border-[#74C7F5]/30 bg-[#0D1B2D] px-4 py-3 text-sm text-slate-300">
                <div className="font-semibold text-white">Create your first workspace/project</div>
                <div className="mt-1">Name your client workspace and first project, then upload a Mirai package. Your login remains the security boundary; the workspace name is a display label.</div>
              </div>
            )}

            <div className="mt-6 rounded-lg border-2 border-dashed border-slate-200 bg-[#0B1220] p-6">
              <div className="text-center text-4xl">⇪</div>
              <h2 className="mt-3 text-center text-xl font-semibold tracking-[-0.04em] text-white">Upload package</h2>
              <p className="mt-2 text-center text-sm text-slate-500">ZIP or package files</p>

              <div className="mt-5 grid gap-3 rounded-md border border-slate-200 bg-white/80 p-3 text-sm md:grid-cols-2">
                <label className={`rounded-md border px-3 py-3 ${intakeMode === 'new_project' ? 'border-[#2F6BFF]/70 bg-[#10203A]' : 'border-slate-700 bg-[#070C16]'}`}>
                  <span className="flex items-center gap-2 font-semibold text-white">
                    <input type="radio" checked={intakeMode === 'new_project'} onChange={() => setIntakeMode('new_project')} className="accent-[#74C7F5]" />
                    New project
                  </span>
                </label>
                <label className={`rounded-md border px-3 py-3 ${projects.length === 0 ? 'cursor-not-allowed border-slate-700 bg-[#070C16] opacity-60' : intakeMode === 'existing_project' ? 'border-[#2F6BFF]/70 bg-[#10203A]' : 'border-slate-700 bg-[#070C16]'}`}>
                  <span className="flex items-center gap-2 font-semibold text-white">
                    <input type="radio" checked={intakeMode === 'existing_project'} disabled={projects.length === 0} onChange={() => setIntakeMode('existing_project')} className="accent-[#74C7F5]" />
                    Existing project
                  </span>
                </label>
              </div>

              <div className="mt-4 space-y-3">
                {intakeMode === 'new_project' ? (
                  <>
                    <label className="block text-xs font-bold uppercase tracking-[0.14em] text-[#74C7F5]">
                      Workspace
                      <input list="workspace-options" value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} className="mt-2 w-full rounded-md border border-slate-200 bg-white px-4 py-3 text-sm normal-case tracking-normal text-slate-900 outline-none focus:border-[#74C7F5]" placeholder="Client or workspace" />
                      <datalist id="workspace-options">
                        {workspaceOptions.map((workspace) => <option key={workspace} value={workspace} />)}
                      </datalist>
                    </label>
                    <input value={projectName} onChange={(event) => setProjectName(event.target.value)} className="w-full rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none focus:border-[#74C7F5]" placeholder="Project name" />
                  </>
                ) : (
                  <label className="block text-xs font-bold uppercase tracking-[0.14em] text-[#74C7F5]">
                    Project
                    <select value={existingProjectId} onChange={(event) => setExistingProjectId(event.target.value)} className="mt-2 w-full rounded-md border border-slate-200 bg-white px-4 py-3 text-sm normal-case tracking-normal text-slate-900 outline-none focus:border-[#74C7F5]">
                      {projects.map((project) => (
                        <option key={project.id} value={project.id}>{workspaceFor(project)} · {project.display_name}</option>
                      ))}
                    </select>
                    <span className="mt-2 block text-xs normal-case tracking-normal text-slate-500">Adds a dataset to {selectedExistingProject?.display_name || 'the selected project'}.</span>
                  </label>
                )}
                <textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="min-h-16 w-full rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none focus:border-[#74C7F5]" placeholder="Notes (optional)" />
                <input type="file" multiple onChange={(event) => setFiles(Array.from(event.target.files ?? []))} className="w-full rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-300" />
                {storageBlocked && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                    <div className="font-semibold">Storage setup required</div>
                    <div className="mt-1">{account?.message || 'Your private project bucket has not been assigned yet. Request setup from a Mirai admin before uploading client data.'}</div>
                  </div>
                )}
                {error && <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
                <button type="button" onClick={handleUpload} disabled={uploading || storageBlocked} className="w-full rounded-md bg-slate-950 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-950/20 disabled:opacity-45">
                  {uploading ? 'Creating...' : intakeMode === 'existing_project' ? 'Create dataset session' : 'Create project'}
                </button>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-lg border border-slate-200 bg-[#0B1220] p-5">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#74C7F5]">Package requirements</p>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-white">Expected package files</h2>
              <p className="mt-3 text-sm text-slate-300">Upload one ZIP, or select these five files together:</p>
              <ul className="mt-4 space-y-2 text-sm text-slate-200">
                <li>• mirai_manifest.json</li>
                <li>• data_dictionary.csv</li>
                <li>• experiments.csv</li>
                <li>• conditions.csv</li>
                <li>• results.csv</li>
              </ul>
              <p className="mt-4 text-sm leading-6 text-slate-400">Column names can be client-native. The contract maps them to stable internal variables.</p>
            </div>

            <DisclosurePanel title="Download templates">
              <div className="flex flex-wrap gap-2">
                <a href="/templates/mirai_manifest_multitable_template.json" download className="rounded-md bg-[#2F6BFF] px-4 py-2 text-sm font-semibold text-white">Manifest</a>
                <a href="/templates/data_dictionary_template.csv" download className="rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700">Dictionary</a>
                <a href="/templates/data_dictionary_multitable_example.csv" download className="rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700">Example CSV</a>
              </div>
            </DisclosurePanel>

            {session && (
              <div className="rounded-md border border-[#74C7F5]/30 bg-[#0D1B2D] p-4 text-sm text-[#BDEAFF]">
                <div className="font-semibold">Project created</div>
                <div className="mt-1">{session.project_name}</div>
                <div className="mt-1 text-xs text-[#74C7F5]">{session.files.length} file{session.files.length === 1 ? '' : 's'} uploaded</div>
                <button type="button" onClick={onReviewPreprocessing} className="mt-3 rounded-md bg-[#2F6BFF] px-4 py-2 text-xs font-bold uppercase tracking-[0.14em] text-white shadow-lg shadow-[#2F6BFF]/20">
                  Review metadata
                </button>
              </div>
            )}
          </div>
        </div>
      </SectionCard>
    </div>
  )
}
