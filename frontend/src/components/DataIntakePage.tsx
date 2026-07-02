import { useState } from 'react'
import type { AccountStatus, IngestionSessionResponse, ProjectSchema, ProjectSummary, WorkspaceSummary } from '../lib/api'
import { createIngestionSession } from '../lib/api'
import { DisclosurePanel, LifecycleStepper } from './ui'

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
  const selectedFileLabel = files.length ? `${files.length} file${files.length === 1 ? '' : 's'} selected` : 'No file selected'

  return (
    <div className="space-y-8">
      <section className="space-y-5">
        <div>
          <p className="text-sm font-medium text-[#74C7F5]">Data Intake</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.055em] text-white">Create a project from data</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[#9BA8C0]">
            Upload a Mirai package, validate its structure, and continue to metadata review.
          </p>
        </div>

        <LifecycleStepper steps={[
          { id: 'upload', label: 'Create project', status: session ? 'done' : 'current' },
          { id: 'metadata', label: 'Review metadata', status: session ? 'current' : 'locked' },
          { id: 'preprocess', label: 'Preprocess', status: 'locked' },
          { id: 'train', label: 'Train', status: 'locked' },
          { id: 'quality', label: 'Quality', status: 'locked' },
        ]} />
      </section>

      {(account && account.status !== 'active_single_workspace') && (
        <div className="border-l-2 border-amber-400/70 bg-amber-400/[0.08] px-4 py-3 text-sm text-amber-100">
          <div className="font-semibold text-white">Workspace setup required</div>
          <div className="mt-1 text-amber-100/80">{account.message || 'Your account is active, but no client workspace has been assigned yet.'}</div>
        </div>
      )}

      {projects.length === 0 && (!account || account.status === 'active_single_workspace') && (
        <div className="border-l-2 border-[#74C7F5]/70 bg-[#74C7F5]/[0.07] px-4 py-3 text-sm text-[#BDEAFF]">
          <div className="font-semibold text-white">First project</div>
          <div className="mt-1 text-[#BDEAFF]/80">Name your workspace and first project, then upload a Mirai package.</div>
        </div>
      )}

      <section className="grid gap-8 border-t border-white/[0.07] pt-8 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <div className="rounded-xl border border-white/10 bg-[#0B1220]/82 p-5 shadow-[0_14px_36px_rgba(2,6,23,0.16)] sm:p-6">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-xl font-semibold tracking-[-0.035em] text-white">Upload package</h2>
              <p className="mt-1 text-sm text-[#9BA8C0]">ZIP package or the required files selected together.</p>
            </div>
            <span className="text-sm font-medium text-[#74C7F5]">{selectedFileLabel}</span>
          </div>

          <div className="mt-5 inline-flex rounded-md bg-[#050914] p-1 ring-1 ring-white/10">
            <button
              type="button"
              onClick={() => setIntakeMode('new_project')}
              className={`rounded px-3 py-1.5 text-sm font-medium transition ${intakeMode === 'new_project' ? 'bg-[#2F6BFF] text-white' : 'text-[#9FB0C8] hover:text-white'}`}
            >
              New project
            </button>
            <button
              type="button"
              disabled={projects.length === 0}
              onClick={() => setIntakeMode('existing_project')}
              className={`rounded px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-45 ${intakeMode === 'existing_project' ? 'bg-[#2F6BFF] text-white' : 'text-[#9FB0C8] hover:text-white'}`}
            >
              Existing project
            </button>
          </div>

          <div className="mt-5 space-y-4">
            {intakeMode === 'new_project' ? (
              <div className="grid gap-4 md:grid-cols-2">
                <label className="block text-sm font-medium text-slate-200">
                  Workspace
                  <input list="workspace-options" value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} className="mt-2 w-full rounded-md border border-slate-700 bg-[#050914] px-3 py-2.5 text-sm text-white outline-none transition focus:border-[#74C7F5]" placeholder="Client or workspace" />
                  <datalist id="workspace-options">
                    {workspaceOptions.map((workspace) => <option key={workspace} value={workspace} />)}
                  </datalist>
                </label>
                <label className="block text-sm font-medium text-slate-200">
                  Project name
                  <input value={projectName} onChange={(event) => setProjectName(event.target.value)} className="mt-2 w-full rounded-md border border-slate-700 bg-[#050914] px-3 py-2.5 text-sm text-white outline-none transition focus:border-[#74C7F5]" placeholder="Project name" />
                </label>
              </div>
            ) : (
              <label className="block text-sm font-medium text-slate-200">
                Project
                <select value={existingProjectId} onChange={(event) => setExistingProjectId(event.target.value)} className="mt-2 w-full rounded-md border border-slate-700 bg-[#050914] px-3 py-2.5 text-sm text-white outline-none transition focus:border-[#74C7F5]">
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>{workspaceFor(project)} · {project.display_name}</option>
                  ))}
                </select>
                <span className="mt-2 block text-xs font-normal text-[#9BA8C0]">Adds a dataset to {selectedExistingProject?.display_name || 'the selected project'}.</span>
              </label>
            )}

            <label className="block text-sm font-medium text-slate-200">
              Notes
              <textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="mt-2 min-h-20 w-full rounded-md border border-slate-700 bg-[#050914] px-3 py-2.5 text-sm text-white outline-none transition focus:border-[#74C7F5]" placeholder="Optional context for the data review" />
            </label>

            <label className="block text-sm font-medium text-slate-200">
              Package files
              <input type="file" multiple onChange={(event) => setFiles(Array.from(event.target.files ?? []))} className="mt-2 w-full rounded-md border border-dashed border-slate-700 bg-[#050914] px-3 py-3 text-sm text-[#9BA8C0] outline-none transition file:mr-4 file:rounded file:border-0 file:bg-[#2F6BFF] file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-white hover:border-slate-500" />
            </label>

            {storageBlocked && (
              <div className="border-l-2 border-amber-400/70 bg-amber-400/[0.08] px-4 py-3 text-sm text-amber-100">
                <div className="font-semibold text-white">Storage setup required</div>
                <div className="mt-1 text-amber-100/80">{account?.message || 'Your private project bucket has not been assigned yet. Request setup from a Mirai admin before uploading client data.'}</div>
              </div>
            )}
            {error && <div className="border-l-2 border-rose-400/80 bg-rose-500/[0.08] px-4 py-3 text-sm text-rose-100">{error}</div>}

            <button type="button" onClick={handleUpload} disabled={uploading || storageBlocked} className="w-full rounded-md bg-[#2F6BFF] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#245CF0] disabled:cursor-not-allowed disabled:opacity-45 sm:w-auto">
              {uploading ? 'Creating…' : intakeMode === 'existing_project' ? 'Create dataset session' : 'Create project'}
            </button>
          </div>
        </div>

        <aside className="space-y-6 lg:border-l lg:border-white/[0.07] lg:pl-6">
          <div>
            <h2 className="text-base font-semibold text-white">Package requirements</h2>
            <p className="mt-2 text-sm leading-6 text-[#9BA8C0]">Upload one ZIP, or select these files together.</p>
            <ul className="mt-4 space-y-2 text-sm text-slate-200">
              {['mirai_manifest.json', 'data_dictionary.csv', 'experiments.csv', 'conditions.csv', 'results.csv'].map((file) => (
                <li key={file} className="flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#74C7F5]" />
                  <span>{file}</span>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-sm leading-6 text-[#9BA8C0]">Client-native column names are okay. The manifest maps them to stable Mirai variables.</p>
          </div>

          <DisclosurePanel title="Download templates">
            <div className="flex flex-wrap gap-2">
              <a href="/templates/mirai_manifest_multitable_template.json" download className="rounded-md bg-[#2F6BFF] px-3 py-2 text-sm font-semibold text-white">Manifest</a>
              <a href="/templates/data_dictionary_template.csv" download className="rounded-md border border-white/10 px-3 py-2 text-sm font-semibold text-slate-200 hover:bg-white/[0.04]">Dictionary</a>
              <a href="/templates/data_dictionary_multitable_example.csv" download className="rounded-md border border-white/10 px-3 py-2 text-sm font-semibold text-slate-200 hover:bg-white/[0.04]">Example CSV</a>
            </div>
          </DisclosurePanel>

          {session && (
            <div className="border-l-2 border-[#74C7F5]/80 bg-[#74C7F5]/[0.07] px-4 py-3 text-sm text-[#BDEAFF]">
              <div className="font-semibold text-white">Project created</div>
              <div className="mt-1">{session.project_name}</div>
              <div className="mt-1 text-xs text-[#74C7F5]">{session.files.length} file{session.files.length === 1 ? '' : 's'} uploaded</div>
              <button type="button" onClick={onReviewPreprocessing} className="mt-3 rounded-md bg-[#2F6BFF] px-3 py-2 text-sm font-semibold text-white">
                Review metadata
              </button>
            </div>
          )}
        </aside>
      </section>
    </div>
  )
}
