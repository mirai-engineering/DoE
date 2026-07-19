import { useEffect, useState } from 'react'
import type { ProjectArtifactStatus, ProjectSchema, ProjectSummary, WorkspaceSummary } from '../lib/api'
import { getProjectArtifactStatus } from '../lib/api'

export function ProjectHeader({
  projects,
  selectedProjectId,
  selectedProject,
  schema,
  workspaces,
  projectsLoading,
  onProjectChange,
  compact = false,
}: {
  projects: ProjectSummary[]
  selectedProjectId: string
  selectedProject: ProjectSummary | undefined
  schema: ProjectSchema | null
  workspaces: WorkspaceSummary[]
  projectsLoading: boolean
  onProjectChange: (projectId: string) => void
  compact?: boolean
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
  const modelReady = Boolean(artifactStatus?.model_quality.available)
  const modelMessage = selectedProjectId ? artifactStatusError || artifactStatus?.model_quality.message || 'Checking model status' : 'Create a project to start model training'

  function handleWorkspaceChange(workspaceName: string) {
    const firstProject = projects.find((project) => workspaceFor(project) === workspaceName)
    if (firstProject) onProjectChange(firstProject.id)
  }

  return (
    <header className="relative z-[80] border-b border-white/[0.07] pb-4">
      <div className={`flex flex-col gap-4 ${compact ? 'lg:flex-row lg:items-end lg:justify-between' : 'xl:flex-row xl:items-end xl:justify-between'}`}>
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm text-[#9FB0C8]">
            <span className="truncate text-slate-300" title={selectedWorkspace}>{selectedWorkspace}</span>
            <span className="text-slate-600">/</span>
            <span className="truncate text-slate-100" title={selectedProject?.display_name || schema?.display_name || 'Project'}>{selectedProject?.display_name || schema?.display_name || 'Project'}</span>
          </div>
          {!compact && <h1 className="mt-1 text-2xl font-semibold tracking-[-0.04em] text-slate-50 sm:text-3xl">AI-guided acceleration</h1>}
          {!compact && <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-[#9FB0C8]">
            <span>{schema ? `${schema.inputs.length} inputs` : 'Inputs pending'}</span>
            <span className="text-slate-600">·</span>
            <span>{schema ? `${schema.outputs.length} outputs` : 'Outputs pending'}</span>
            <span className="text-slate-600">·</span>
            <span className={modelReady ? 'text-[#BDEAFF]' : 'text-amber-100'}>{modelReady ? 'Model ready' : 'Model pending'}</span>
            <span className="min-w-0 truncate text-[#7F8DA8]">{modelMessage}</span>
          </div>}
        </div>

        <div className={`grid min-w-0 gap-3 sm:grid-cols-2 ${compact ? 'lg:w-[30rem]' : 'xl:w-[30rem]'}`}>
          <label htmlFor="workspace" className="min-w-0 text-sm font-medium text-slate-300">
            Workspace
            <select id="workspace" value={selectedWorkspace} onChange={(event) => handleWorkspaceChange(event.target.value)} disabled={projectsLoading || workspaceOptions.length === 0} className="mt-1.5 w-full min-w-0 rounded-md border border-white/[0.08] bg-[#050914]/80 px-3 py-2 text-sm font-medium text-slate-100 outline-none transition focus:border-[#74C7F5] focus:ring-2 focus:ring-[#74C7F5]/20">
              {workspaceOptions.length ? workspaceOptions.map((workspace) => <option key={workspace} value={workspace}>{workspace}</option>) : <option value={selectedWorkspace}>{selectedWorkspace}</option>}
            </select>
          </label>

          <label htmlFor="project" className="min-w-0 text-sm font-medium text-slate-300">
            Project
            <select id="project" value={selectedProjectId} onChange={(event) => onProjectChange(event.target.value)} disabled={projectsLoading || projects.length === 0} className="mt-1.5 w-full min-w-0 rounded-md border border-white/[0.08] bg-[#050914]/80 px-3 py-2 text-sm font-medium text-slate-100 outline-none transition focus:border-[#74C7F5] focus:ring-2 focus:ring-[#74C7F5]/20">
              {visibleProjects.length ? visibleProjects.map((project) => <option key={project.id} value={project.id}>{project.display_name}</option>) : <option value="">No projects yet</option>}
            </select>
          </label>
        </div>
      </div>
    </header>
  )
}
