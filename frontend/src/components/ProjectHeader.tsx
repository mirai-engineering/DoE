import { useEffect, useState } from 'react'
import type { ProjectArtifactStatus, ProjectSchema, ProjectSummary, WorkspaceSummary } from '../lib/api'
import { getProjectArtifactStatus } from '../lib/api'
import { Metadata } from './ui'

export function ProjectHeader({
  projects,
  selectedProjectId,
  selectedProject,
  schema,
  workspaces,
  projectsLoading,
  onProjectChange,
}: {
  projects: ProjectSummary[]
  selectedProjectId: string
  selectedProject: ProjectSummary | undefined
  schema: ProjectSchema | null
  workspaces: WorkspaceSummary[]
  projectsLoading: boolean
  onProjectChange: (projectId: string) => void
}) {
  const [artifactStatus, setArtifactStatus] = useState<ProjectArtifactStatus | null>(null)
  const [artifactStatusError, setArtifactStatusError] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedProjectId) return
    let isMounted = true
    setArtifactStatus(null)
    setArtifactStatusError(null)
    getProjectArtifactStatus(selectedProjectId)
      .then((status) => {
        if (isMounted) setArtifactStatus(status)
      })
      .catch((error) => {
        if (isMounted) setArtifactStatusError(error instanceof Error ? error.message : 'Status unavailable')
      })
    return () => {
      isMounted = false
    }
  }, [selectedProjectId])

  function workspaceFor(project?: ProjectSummary) {
    const explicit = project?.workspace_name
    if (explicit) return explicit
    return schema?.workspace_name || workspaces[0]?.display_name || 'Mirai Engineering'
  }

  const workspaceOptions = Array.from(new Set([...workspaces.map((workspace) => workspace.display_name), ...projects.map((project) => workspaceFor(project))]))
  const selectedWorkspace = selectedProject ? workspaceFor(selectedProject) : schema?.workspace_name || workspaceOptions[0] || 'Your workspace'
  const visibleProjects = projects.filter((project) => workspaceFor(project) === selectedWorkspace)

  function handleWorkspaceChange(workspaceName: string) {
    const firstProject = projects.find((project) => workspaceFor(project) === workspaceName)
    if (firstProject) onProjectChange(firstProject.id)
  }

  return (
    <section className="relative z-[80] overflow-hidden rounded-lg border border-slate-700/80 bg-[#0B1220] shadow-xl shadow-black/25">
      <div className="border-b border-slate-700/70 px-5 py-5 md:px-6">
        <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(32rem,0.95fr)] xl:items-end">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#74C7F5]">Mirai</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-slate-50 sm:text-4xl">AI-guided process and product acceleration</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">Design better experiments before you run them with a controlled scientific workflow.</p>
          </div>

          <div className="grid min-w-0 gap-3 md:grid-cols-2">
            <label htmlFor="workspace" className="min-w-0 text-xs font-bold uppercase tracking-[0.14em] text-slate-400">
              Workspace
              <select id="workspace" value={selectedWorkspace} onChange={(event) => handleWorkspaceChange(event.target.value)} disabled={projectsLoading || workspaceOptions.length === 0} className="mt-2 w-full min-w-0 rounded-md border border-slate-700 bg-[#050914] px-3 py-2.5 text-sm font-medium normal-case tracking-normal text-slate-100 outline-none transition focus:border-[#2F6BFF] focus:ring-2 focus:ring-[#2F6BFF]/25">
                {workspaceOptions.length ? workspaceOptions.map((workspace) => <option key={workspace} value={workspace}>{workspace}</option>) : <option value={selectedWorkspace}>{selectedWorkspace}</option>}
              </select>
            </label>

            <label htmlFor="project" className="min-w-0 text-xs font-bold uppercase tracking-[0.14em] text-slate-400">
              Project
              <select id="project" value={selectedProjectId} onChange={(event) => onProjectChange(event.target.value)} disabled={projectsLoading || projects.length === 0} className="mt-2 w-full min-w-0 rounded-md border border-slate-700 bg-[#050914] px-3 py-2.5 text-sm font-medium normal-case tracking-normal text-slate-100 outline-none transition focus:border-[#2F6BFF] focus:ring-2 focus:ring-[#2F6BFF]/25">
                {visibleProjects.length ? visibleProjects.map((project) => <option key={project.id} value={project.id}>{project.display_name}</option>) : <option value="">No projects yet</option>}
              </select>
            </label>
          </div>
        </div>
      </div>

      <div className="grid gap-3 px-5 py-4 md:grid-cols-[8rem_8rem_minmax(0,1fr)] md:px-6">
        <Metadata label="Inputs" value={schema ? String(schema.inputs.length) : '-'} />
        <Metadata label="Outputs" value={schema ? String(schema.outputs.length) : '-'} />
        <div className="flex min-w-0 items-center justify-between gap-4 rounded-md border border-slate-700 bg-[#070C16] px-3 py-2.5 text-sm">
          <div className="min-w-0">
            <div className="font-semibold text-slate-100">Model quality</div>
            <div className="mt-0.5 truncate text-xs text-slate-400">{selectedProjectId ? artifactStatusError || artifactStatus?.model_quality.message || 'Checking status' : 'Create a project to start model training'}</div>
          </div>
          <span className={`shrink-0 rounded px-2.5 py-1 text-xs font-semibold ${artifactStatus?.model_quality.available ? 'border border-emerald-400/30 bg-emerald-950/40 text-emerald-200' : 'border border-amber-300/30 bg-amber-950/40 text-amber-100'}`}>{artifactStatus?.model_quality.available ? 'Ready' : 'Pending'}</span>
        </div>
      </div>
    </section>
  )
}
