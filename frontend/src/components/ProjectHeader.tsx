import type { ActiveTab } from '../types/doe'
import type { ProjectSchema, ProjectSummary } from '../lib/api'
import { Metadata } from './ui'
import { Tabs } from './Tabs'

export function ProjectHeader({
  projects,
  selectedProjectId,
  selectedProject,
  schema,
  projectsLoading,
  activeTab,
  onProjectChange,
  onTabChange,
}: {
  projects: ProjectSummary[]
  selectedProjectId: string
  selectedProject: ProjectSummary | undefined
  schema: ProjectSchema | null
  projectsLoading: boolean
  activeTab: ActiveTab
  onProjectChange: (projectId: string) => void
  onTabChange: (tab: ActiveTab) => void
}) {
  return (
    <section className="overflow-hidden rounded-[2rem] border border-white/70 bg-[#f8f6ef]/90 shadow-2xl shadow-slate-900/10 backdrop-blur">
      <div className="grid gap-8 p-6 md:grid-cols-[1.35fr_0.65fr] md:p-8">
        <div>
          <div className="mb-6 inline-flex items-center gap-3 rounded-full border border-slate-900/10 bg-white/70 px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-slate-600">
            Surrogate model console
          </div>
          <h1 className="max-w-3xl text-5xl font-semibold tracking-[-0.06em] text-slate-950 sm:text-6xl">
            Mirai DoE Engine
          </h1>
          <p className="mt-4 max-w-2xl text-lg leading-8 text-slate-600">
            Predict experiment outcomes and recommend the next best candidates.
          </p>

          <Tabs activeTab={activeTab} onTabChange={onTabChange} />
        </div>

        <div className="rounded-3xl border border-slate-900/10 bg-white/75 p-5 shadow-inner shadow-white">
          <label htmlFor="project" className="text-sm font-semibold text-slate-700">
            Project
          </label>
          <select
            id="project"
            value={selectedProjectId}
            onChange={(event) => onProjectChange(event.target.value)}
            disabled={projectsLoading || projects.length === 0}
            className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-950 outline-none transition focus:border-[#60745c] focus:ring-4 focus:ring-[#60745c]/20"
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.display_name}
              </option>
            ))}
          </select>

          <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
            <Metadata label="Project ID" value={selectedProject?.id ?? 'Loading'} />
            <Metadata label="Version" value={schema?.schema_version ?? '-'} />
            <Metadata label="Inputs" value={schema ? String(schema.inputs.length) : '-'} />
            <Metadata label="Outputs" value={schema ? String(schema.outputs.length) : '-'} />
          </div>
          {schema?.description && (
            <p className="mt-4 text-sm leading-6 text-slate-600">{schema.description}</p>
          )}
        </div>
      </div>
    </section>
  )
}
