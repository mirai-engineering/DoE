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
        if (isMounted) setArtifactStatusError(error instanceof Error ? error.message : 'Artifact status unavailable')
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
  const artifactPointers = artifactStatus?.artifact_pointers ?? {}
  const durableBuckets = Array.from(new Set(Object.values(artifactPointers).map((pointer) => pointer.bucket).filter(Boolean)))
  const availablePointerCount = Object.values(artifactPointers).filter((pointer) => pointer.object_key).length

  function handleWorkspaceChange(workspaceName: string) {
    const firstProject = projects.find((project) => workspaceFor(project) === workspaceName)
    if (firstProject) onProjectChange(firstProject.id)
  }

  return (
    <section className="relative z-[80] overflow-visible rounded-[2rem] border border-white/70 bg-[#f8f6ef]/95 shadow-2xl shadow-slate-900/10 backdrop-blur">
      <div className="grid gap-8 p-6 md:grid-cols-[1.35fr_0.65fr] md:p-8">
        <div>
          <div className="mb-6 inline-flex items-center gap-3 rounded-full border border-slate-900/10 bg-white/70 px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-slate-600">
            ML-guided DoE platform
          </div>
          <div className="flex items-center gap-5">
            <img
              src="/assets/doe_logo.png"
              alt="Mirai DoE"
              className="h-48 w-48 shrink-0 rounded-2xl border border-slate-200 object-contain shadow-sm"
            />
            <h1 className="max-w-3xl text-5xl font-semibold tracking-[-0.06em] text-slate-950 sm:text-6xl">
              Mirai DoE Engine
            </h1>
          </div>
          <p className="mt-4 max-w-3xl text-lg leading-8 text-slate-600">
            Abstract ML engineering for test teams: trust tailored models, design better experiments, and quantify saved test effort.
          </p>

          <Tabs activeTab={activeTab} onTabChange={onTabChange} />
        </div>

        <div className="rounded-3xl border border-slate-900/10 bg-white/75 p-5 shadow-inner shadow-white">
          <div className="grid gap-4">
            <label htmlFor="workspace" className="text-sm font-semibold text-slate-700">
              Workspace / Client
              <select
                id="workspace"
                value={selectedWorkspace}
                onChange={(event) => handleWorkspaceChange(event.target.value)}
                disabled={projectsLoading || workspaceOptions.length === 0}
                className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-950 outline-none transition focus:border-[#60745c] focus:ring-4 focus:ring-[#60745c]/20"
              >
                {workspaceOptions.map((workspace) => (
                  <option key={workspace} value={workspace}>{workspace}</option>
                ))}
              </select>
            </label>

            <label htmlFor="project" className="text-sm font-semibold text-slate-700">
              Project
              <select
                id="project"
                value={selectedProjectId}
                onChange={(event) => onProjectChange(event.target.value)}
                disabled={projectsLoading || projects.length === 0}
                className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-950 outline-none transition focus:border-[#60745c] focus:ring-4 focus:ring-[#60745c]/20"
              >
                {visibleProjects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.display_name} · {project.id}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
            <Metadata label="Workspace" value={selectedWorkspace} />
            <Metadata label="Display name" value={schema?.display_name ?? selectedProject?.display_name ?? 'Loading'} />
            <Metadata label="Project ID" value={selectedProject?.id ?? 'Loading'} />
            <Metadata label="Schema version" value={schema?.schema_version ?? '-'} />
            <Metadata label="Inputs" value={schema ? String(schema.inputs.length) : '-'} />
            <Metadata label="Outputs" value={schema ? String(schema.outputs.length) : '-'} />
          </div>
          {schema?.description && (
            <p className="mt-4 text-sm leading-6 text-slate-600">{schema.description}</p>
          )}

          <div className="mt-5 rounded-3xl border border-slate-200 bg-[#f8f6ef] p-4 text-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Durable state
                </div>
                <div className="mt-1 font-semibold text-slate-800">
                  {artifactStatus ? `${availablePointerCount} scoped pointers` : artifactStatusError ? 'Status unavailable' : 'Checking pointers...'}
                </div>
              </div>
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${artifactStatus?.model_quality.available ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-800'}`}>
                {artifactStatus?.model_quality.available ? 'quality ready' : 'quality pending'}
              </span>
            </div>
            <p className="mt-3 line-clamp-3 text-xs leading-5 text-slate-500">
              {artifactStatusError || artifactStatus?.model_quality.message || 'Loading workspace/project artifact pointers.'}
            </p>
            {durableBuckets.length > 0 && (
              <p className="mt-2 truncate text-xs font-medium text-slate-600">
                Bucket: {durableBuckets.join(', ')}
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
