import { useEffect, useState } from 'react'
import type { ActiveTab } from '../types/doe'
import type { ProjectArtifactStatus, ProjectSchema, ProjectSummary, WorkspaceSummary } from '../lib/api'
import { getProjectArtifactStatus } from '../lib/api'
import { Metadata } from './ui'
import { Tabs } from './Tabs'

export function ProjectHeader({
  projects,
  selectedProjectId,
  selectedProject,
  schema,
  workspaces,
  projectsLoading,
  activeTab,
  onProjectChange,
  onTabChange,
}: {
  projects: ProjectSummary[]
  selectedProjectId: string
  selectedProject: ProjectSummary | undefined
  schema: ProjectSchema | null
  workspaces: WorkspaceSummary[]
  projectsLoading: boolean
  activeTab: ActiveTab
  onProjectChange: (projectId: string) => void
  onTabChange: (tab: ActiveTab) => void
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
  const selectedWorkspace = selectedProject ? workspaceFor(selectedProject) : schema?.workspace_name || workspaceOptions[0] || 'Mirai Engineering'
  const visibleProjects = projects.filter((project) => workspaceFor(project) === selectedWorkspace)

  function handleWorkspaceChange(workspaceName: string) {
    const firstProject = projects.find((project) => workspaceFor(project) === workspaceName)
    if (firstProject) onProjectChange(firstProject.id)
  }

  return (
    <section className="relative z-[80] overflow-visible rounded-[2rem] border border-white/70 bg-[#f8f6ef]/95 shadow-2xl shadow-slate-900/10 backdrop-blur">
      <div className="p-5 md:p-6">
        <div className="grid gap-5 lg:grid-cols-[1fr_24rem] lg:items-start">
          <div>
            <div className="flex items-center gap-4">
              <img src="/assets/doe_logo.png" alt="Mirai DoE" className="h-20 w-20 shrink-0 rounded-2xl border border-slate-200 bg-white object-contain shadow-sm" />
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#60745c]">Mirai DoE</p>
                <h1 className="mt-1 text-3xl font-semibold tracking-[-0.055em] text-slate-950 sm:text-4xl">ML-guided experiments</h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Create models, choose better experiments, and review impact.</p>
              </div>
            </div>
            <Tabs activeTab={activeTab} onTabChange={onTabChange} />
          </div>

          <div className="rounded-3xl border border-slate-900/10 bg-white/75 p-4 shadow-inner shadow-white">
            <div className="grid gap-3">
              <label htmlFor="workspace" className="text-xs font-bold uppercase tracking-[0.14em] text-[#526949]">
                Workspace
                <select id="workspace" value={selectedWorkspace} onChange={(event) => handleWorkspaceChange(event.target.value)} disabled={projectsLoading || workspaceOptions.length === 0} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium normal-case tracking-normal text-slate-950 outline-none transition focus:border-[#60745c] focus:ring-4 focus:ring-[#60745c]/20">
                  {workspaceOptions.map((workspace) => <option key={workspace} value={workspace}>{workspace}</option>)}
                </select>
              </label>

              <label htmlFor="project" className="text-xs font-bold uppercase tracking-[0.14em] text-[#526949]">
                Project
                <select id="project" value={selectedProjectId} onChange={(event) => onProjectChange(event.target.value)} disabled={projectsLoading || projects.length === 0} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium normal-case tracking-normal text-slate-950 outline-none transition focus:border-[#60745c] focus:ring-4 focus:ring-[#60745c]/20">
                  {visibleProjects.map((project) => <option key={project.id} value={project.id}>{project.display_name}</option>)}
                </select>
              </label>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <Metadata label="Inputs" value={schema ? String(schema.inputs.length) : '-'} />
              <Metadata label="Outputs" value={schema ? String(schema.outputs.length) : '-'} />
            </div>

            <div className="mt-4 flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-[#f8f6ef] px-4 py-3 text-sm">
              <div>
                <div className="font-semibold text-slate-800">Model quality</div>
                <div className="mt-0.5 text-xs text-slate-500">{artifactStatusError || artifactStatus?.model_quality.message || 'Checking status'}</div>
              </div>
              <span className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${artifactStatus?.model_quality.available ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-800'}`}>{artifactStatus?.model_quality.available ? 'Ready' : 'Pending'}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
