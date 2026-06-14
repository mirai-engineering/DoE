import { useState } from 'react'
import type { IngestionSessionResponse, ProjectSchema, ProjectSummary, WorkspaceSummary } from '../lib/api'
import { createIngestionSession } from '../lib/api'

export function DataIntakePage({ schema, projects, workspaces, onReviewPreprocessing, onSessionCreated }: { schema: ProjectSchema; projects: ProjectSummary[]; workspaces: WorkspaceSummary[]; onReviewPreprocessing?: () => void; onSessionCreated?: (session: IngestionSessionResponse) => void | Promise<void> }) {
  const [intakeMode, setIntakeMode] = useState<'new_project' | 'existing_project'>('new_project')
  const [workspaceName, setWorkspaceName] = useState(schema.workspace_name || 'Mirai Engineering')
  const [existingProjectId, setExistingProjectId] = useState(schema.project_id)
  const [projectName, setProjectName] = useState('New Mirai ML Project')
  const [notes, setNotes] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [session, setSession] = useState<IngestionSessionResponse | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleUpload() {
    if (!files.length) {
      setError('Select at least one file before creating an ingestion session.')
      return
    }
    setUploading(true)
    setError(null)
    try {
      const selectedExistingProject = projects.find((project) => project.id === existingProjectId)
      const effectiveProjectName = intakeMode === 'existing_project'
        ? selectedExistingProject?.display_name || schema.display_name
        : projectName
      const effectiveWorkspaceName = intakeMode === 'existing_project'
        ? workspaceFor(selectedExistingProject) || schema.workspace_name || workspaceName
        : workspaceName
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
    return schema.workspace_name || workspaces[0]?.display_name || 'Mirai Engineering'
  }

  const selectedExistingProject = projects.find((project) => project.id === existingProjectId)
  const workspaceOptions = Array.from(new Set([...workspaces.map((workspace) => workspace.display_name), ...projects.map((project) => workspaceFor(project)), workspaceName].filter(Boolean)))

  const packageItems = [
    'Required mirai_manifest.json: project, tables, columns, joins, split hints, and plot hooks',
    'Required data_dictionary.csv: role, dtype, unit, bounds, required flag, and output direction for every column',
    'Preferred new-package source tables: experiments.csv, conditions.csv, and results.csv with deterministic joins into model_table.csv',
    'Transitional model_table.csv packages remain supported when already ML-ready with selected X/Y columns',
  ]

  const roleExamples = [
    ['input', 'x1, x2, x3 for new fixed packages; semantic labels stay in ui_label'],
    ['output', 'y1, y2 for new fixed packages; KPI names stay in ui_label'],
    ['group', 'batch_id, cell_id, campaign_id, station_id'],
    ['metadata', 'operator_id, material_lot, split'],
  ]

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border border-white/70 bg-white/90 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#60745c]">Data Intake</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.055em] text-slate-950">Drop in a Mirai Experiment Package</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              Choose the owning workspace/client, then either create a new project or add a new dataset to an existing project. Mirai requires a manifest JSON plus data dictionary before preprocessing can be approved.
            </p>
          </div>
          <span className="rounded-full border border-[#d8c99b]/70 bg-[#fff8e8] px-3 py-1 text-xs font-bold uppercase tracking-[0.14em] text-[#526949]">Local MVP</span>
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#60745c]">Upload area</p>
          <div className="mt-4 rounded-[1.5rem] border-2 border-dashed border-slate-200 bg-[#fbfaf5] p-6">
            <div className="text-center text-4xl">⇪</div>
            <h2 className="mt-3 text-center text-xl font-semibold tracking-[-0.04em] text-slate-950">Upload package</h2>
            <p className="mx-auto mt-2 max-w-xl text-center text-sm leading-6 text-slate-600">
              Choose <strong>Create new project</strong> when you need a separate project ID. Choose <strong>Add data to existing project</strong> only for repeat data under the same project ID.
            </p>
            <div className="mt-5 space-y-3">
              <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white/80 p-3 text-sm md:grid-cols-2">
                <label className={`rounded-2xl border px-3 py-3 ${intakeMode === 'new_project' ? 'border-[#60745c] bg-[#eef0ea]' : 'border-slate-200 bg-white'}`}>
                  <span className="flex items-center gap-2 font-semibold text-slate-900">
                    <input type="radio" checked={intakeMode === 'new_project'} onChange={() => setIntakeMode('new_project')} className="accent-[#526949]" />
                    Create new project
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-slate-500">Creates a separate project ID; existing projects and sessions are left untouched.</span>
                </label>
                <label className={`rounded-2xl border px-3 py-3 ${intakeMode === 'existing_project' ? 'border-[#60745c] bg-[#eef0ea]' : 'border-slate-200 bg-white'}`}>
                  <span className="flex items-center gap-2 font-semibold text-slate-900">
                    <input type="radio" checked={intakeMode === 'existing_project'} onChange={() => setIntakeMode('existing_project')} className="accent-[#526949]" />
                    Add data to existing project
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-slate-500">Keeps the same project ID and appends a dataset/session for repeat campaigns or retraining.</span>
                </label>
              </div>

              {intakeMode === 'new_project' ? (
                <>
                  <label className="block text-xs font-bold uppercase tracking-[0.14em] text-[#526949]">
                    Workspace / Client
                    <input list="workspace-options" value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm normal-case tracking-normal text-slate-900 outline-none focus:border-[#60745c]" placeholder="Client or workspace name" />
                    <datalist id="workspace-options">
                      {workspaceOptions.map((workspace) => <option key={workspace} value={workspace} />)}
                    </datalist>
                  </label>
                  <input value={projectName} onChange={(event) => setProjectName(event.target.value)} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none focus:border-[#60745c]" placeholder="Project display name" />
                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs leading-5 text-emerald-800">
                    This will create a new project ID from the display name under <strong>{workspaceName || 'the selected workspace'}</strong>. It will not rewrite <strong>{schema.project_id}</strong> or any existing training artifacts.
                  </div>
                </>
              ) : (
                <label className="block text-xs font-bold uppercase tracking-[0.14em] text-[#526949]">
                  Existing project
                  <select value={existingProjectId} onChange={(event) => setExistingProjectId(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm normal-case tracking-normal text-slate-900 outline-none focus:border-[#60745c]">
                    {projects.map((project) => (
                      <option key={project.id} value={project.id}>{workspaceFor(project)} · {project.display_name} · {project.id}</option>
                    ))}
                  </select>
                  <span className="mt-2 block rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs normal-case leading-5 tracking-normal text-amber-800">
                    No files are overwritten, but this is <strong>not</strong> a new project. It appends a new dataset/session under <strong>{selectedExistingProject?.id || existingProjectId}</strong> and future training can update that same project's challenger/session model.
                  </span>
                </label>
              )}
              <textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="min-h-20 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none focus:border-[#60745c]" placeholder="Optional package notes" />
              <div className="rounded-2xl border border-slate-200 bg-white/80 px-4 py-3 text-xs leading-5 text-slate-600">
                Upload one Mirai Experiment Package for every domain. The package must contain <strong>mirai_manifest.json</strong>, <strong>data_dictionary.csv</strong>, and either the fixed source tables <strong>experiments.csv</strong>, <strong>conditions.csv</strong>, and <strong>results.csv</strong> or a transitional <strong>model_table.csv</strong>. ZIP uploads are accepted only as containers for the same package structure.
              </div>
              <input type="file" multiple onChange={(event) => setFiles(Array.from(event.target.files ?? []))} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600" />
              {error && <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
              <button type="button" onClick={handleUpload} disabled={uploading} className="w-full rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-950/20 disabled:opacity-45">
                {uploading ? 'Creating ingestion session...' : intakeMode === 'existing_project' ? 'Create dataset session' : 'Create project + session'}
              </button>
            </div>
          </div>
          {session && (
            <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
              <div className="font-semibold">Session created: {session.ingestion_session_id}</div>
              <div className="mt-1">Workspace: {session.workspace_name || 'Mirai Engineering'}</div>
              <div>Project ID: {session.project_id}</div>
              <div>Status: {session.status}</div>
              <div>Files inventoried: {session.files.length}</div>
              <button type="button" onClick={onReviewPreprocessing} className="mt-3 rounded-full bg-emerald-700 px-4 py-2 text-xs font-bold uppercase tracking-[0.14em] text-white shadow-lg shadow-emerald-900/15">
                Review preprocessing
              </button>
            </div>
          )}
        </div>

        <div className="rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#60745c]">Package contract</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950">Force structure, not one file</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            OEM/testbench exports may use client-native column names, including spaces or units. The Mirai contract maps each source column to an immutable internal variable id for training and a user-facing UI label for review/project screens.
          </p>
          <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-950 p-4 text-sm text-white shadow-lg shadow-slate-950/10">
            <div className="text-xs font-bold uppercase tracking-[0.18em] text-[#d8c99b]">Safest MVP shape</div>
            <pre className="mt-3 whitespace-pre-wrap text-xs leading-5 text-white/80">{`my_project_upload/\n  mirai_manifest.json\n  data_dictionary.csv\n  experiments.csv\n  conditions.csv\n  results.csv\n\n# data_dictionary.csv maps:\n# source_name: \"Pt/C ratio (%)\"\n# variable_id: x1\n# ui_label: \"Pt/C ratio\"`}</pre>
          </div>
          <div className="mt-4 space-y-3">
            {packageItems.map((item) => (
              <div key={item} className="rounded-2xl border border-slate-200 bg-[#fbfaf5] px-4 py-3 text-sm text-slate-700">{item}</div>
            ))}
          </div>
          <div className="mt-4 grid gap-2">
            {roleExamples.map(([role, examples]) => (
              <div key={role} className="grid gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm sm:grid-cols-[7rem_1fr]">
                <span className="font-mono text-xs font-bold uppercase tracking-[0.14em] text-[#526949]">{role}</span>
                <span className="text-slate-600">{examples}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#60745c]">Mirai Experiment Package</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950">Templates for structured uploads</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              The package contract is mandatory. It enforces fixed source tables, identifiers, source-name-to-variable-id mappings, units, roles, dtypes, bounds, directions, split hints, plot hooks, and joins while allowing real OEM/testbench columns to keep client-native wording.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href="/templates/mirai_manifest_multitable_template.json" download className="rounded-full bg-[#526949] px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-[#526949]/20">Multi-table manifest</a>
            <a href="/templates/data_dictionary_template.csv" download className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700">Dictionary CSV</a>
            <a href="/templates/data_dictionary_multitable_example.csv" download className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700">Multi-table CSV</a>
            <a href="/templates/data_dictionary_template.xlsx.placeholder.txt" download className="rounded-full border border-dashed border-slate-300 bg-[#fbfaf5] px-4 py-2 text-sm font-semibold text-slate-500">XLSX placeholder</a>
          </div>
        </div>
        <div className="mt-6 grid gap-4 lg:grid-cols-3">
          <div className="rounded-[1.5rem] border border-slate-200 bg-[#fbfaf5] p-4">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#60745c]">Allowed templates</p>
            <div className="mt-3 space-y-2 text-sm text-slate-700">
              <div><strong>generic_tabular_doe</strong> — the single enforced Mirai lifecycle for fuel cells, batteries, materials, and other engineering tabular DoE uploads.</div>
              <div>Domain examples are represented by variables and metadata inside the same package structure, not by a separate upload mode.</div>
            </div>
          </div>
          <div className="rounded-[1.5rem] border border-slate-200 bg-[#fbfaf5] p-4">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#60745c]">Required output direction</p>
            <div className="mt-3 space-y-2 text-sm text-slate-700">
              <div><strong>maximize</strong>: yield, efficiency, current density.</div>
              <div><strong>minimize</strong>: degradation, loss, cost, defect rate.</div>
              <div><strong>target</strong>: hit a specified property window.</div>
            </div>
          </div>
          <div className="rounded-[1.5rem] border border-slate-200 bg-[#fbfaf5] p-4">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#60745c]">Constrained joins</p>
            <div className="mt-3 text-sm leading-6 text-slate-700">
              Multi-table uploads are allowed only with declared primary keys and one-to-one, one-to-many, or many-to-one joins. Free-form relational schemas are blocked.
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="rounded-[2rem] border border-amber-200 bg-amber-50/80 p-6 shadow-lg shadow-amber-900/5">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-amber-700">Admin workflow state</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950">Contract blocked until approved</h2>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            If a package lacks a complete manifest/data dictionary, preprocessing is blocked. For now, only Mirai admins can complete and approve the Metadata & Plot Setup contract before preprocessing/training begins.
          </p>
          <div className="mt-4 rounded-2xl bg-white/70 p-4 font-mono text-xs leading-5 text-slate-700">
            output column example:<br />
            y1 → role=output, dtype=float, unit=%, direction=maximize, ui_label=Yield
          </div>
        </div>
        <div className="rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#60745c]">Future Pi manifest assistant</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950">Draft manifest from raw files</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Placeholder only: future Pi may inspect uploaded files and propose a manifest draft. In the MVP, suggestions are never authoritative: the forced Mirai contract and Mirai-admin approval are required.
          </p>
          <button type="button" disabled className="mt-4 rounded-full border border-dashed border-slate-300 bg-[#fbfaf5] px-4 py-2 text-sm font-semibold text-slate-400">Assistant not active yet</button>
        </div>
      </section>

      <section className="grid gap-5 md:grid-cols-3">
        {[
          ['1', 'Inventory', 'File type, size, checksum, and manifest/data-dictionary presence.'],
          ['2', 'Contract approval', 'Mirai admins approve template_id, roles, dtypes, units, bounds, output directions, joins, split hints, and plot recipes.'],
          ['3', 'Preprocessing review', 'Mirai builds canonical model_table.csv, rejected rows, schema, preprocessing, split, profile, and validation artifacts before training.'],
        ].map(([step, title, body]) => (
          <div key={title} className="rounded-[1.5rem] border border-slate-200 bg-white/90 p-5 shadow-sm shadow-slate-900/5">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-slate-950 text-sm font-bold text-white">{step}</span>
            <h3 className="mt-4 text-lg font-semibold text-slate-950">{title}</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">{body}</p>
          </div>
        ))}
      </section>

      <section className="rounded-[1.75rem] border border-slate-200 bg-white/85 p-5 text-sm text-slate-600">
        Current context: <span className="font-semibold text-slate-950">{schema.workspace_name || workspaceFor(projects.find((project) => project.id === schema.project_id))}</span> / <span className="font-semibold text-slate-950">{schema.display_name}</span> · <span className="font-mono text-xs text-slate-500">{schema.project_id}</span>. Choose whether the next upload creates a new project or a dataset under an existing project.
      </section>
    </div>
  )
}
