import { useState } from 'react'
import type { IngestionSessionResponse, ProjectSchema } from '../lib/api'
import { createIngestionSession } from '../lib/api'

export function DataIntakePage({ schema, onReviewPreprocessing, onSessionCreated }: { schema: ProjectSchema; onReviewPreprocessing?: () => void; onSessionCreated?: (session: IngestionSessionResponse) => void }) {
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
      const result = await createIngestionSession(projectName, files, notes)
      setSession(result)
      window.localStorage.setItem('mirai.latestIngestionSession', JSON.stringify(result))
      window.localStorage.setItem('mirai.activeProjectId', result.project_id)
      onSessionCreated?.(result)
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const packageItems = [
    'Raw CSV/XLSX files or a zipped testbench export',
    'Manifest JSON for backend validation',
    'CSV/XLSX data dictionary for scientists',
    'Project, sample, campaign, or test identifiers for joins and leakage-safe splits',
  ]

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border border-white/70 bg-white/90 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#60745c]">Data Intake</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.055em] text-slate-950">Drop in a Mirai Experiment Package</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              Start a new tailored ML project from raw lab/testbench data. The MVP accepts local raw-data uploads, inventories every file, and prepares a Mirai-admin mapping review before preprocessing.
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
              Create a new project, store raw files locally, calculate checksums, and generate a file inventory.
            </p>
            <div className="mt-5 space-y-3">
              <input value={projectName} onChange={(event) => setProjectName(event.target.value)} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none focus:border-[#60745c]" placeholder="Project name" />
              <textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="min-h-20 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none focus:border-[#60745c]" placeholder="Optional package notes" />
              <input type="file" multiple onChange={(event) => setFiles(Array.from(event.target.files ?? []))} className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600" />
              {error && <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
              <button type="button" onClick={handleUpload} disabled={uploading} className="w-full rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-950/20 disabled:opacity-45">
                {uploading ? 'Creating ingestion session...' : 'Create ingestion session'}
              </button>
            </div>
          </div>
          {session && (
            <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
              <div className="font-semibold">Session created: {session.ingestion_session_id}</div>
              <div className="mt-1">Project ID: {session.project_id}</div>
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
            OEM/testbench exports can stay scattered, but every package needs identifiers, column roles, units, and join relationships.
          </p>
          <div className="mt-4 space-y-3">
            {packageItems.map((item) => (
              <div key={item} className="rounded-2xl border border-slate-200 bg-[#fbfaf5] px-4 py-3 text-sm text-slate-700">{item}</div>
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
              The package contract enforces semantic structure — identifiers, units, roles, and joins — while allowing real OEM/testbench exports to remain split across files and worksheets.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href="/templates/mirai_manifest_template.json" download className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-slate-950/20">One-table manifest</a>
            <a href="/templates/mirai_manifest_multitable_template.json" download className="rounded-full bg-[#526949] px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-[#526949]/20">Multi-table manifest</a>
            <a href="/templates/data_dictionary_template.csv" download className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700">Dictionary CSV</a>
            <a href="/templates/data_dictionary_multitable_example.csv" download className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700">Multi-table CSV</a>
            <a href="/templates/data_dictionary_template.xlsx.placeholder.txt" download className="rounded-full border border-dashed border-slate-300 bg-[#fbfaf5] px-4 py-2 text-sm font-semibold text-slate-500">XLSX placeholder</a>
          </div>
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="rounded-[2rem] border border-amber-200 bg-amber-50/80 p-6 shadow-lg shadow-amber-900/5">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-amber-700">Admin workflow state</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950">Needs mapping</h2>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            If a package lacks a complete manifest/data dictionary, Mirai admins map files and columns to inputs, outputs, context fields, units, join keys, and split groups before preprocessing begins.
          </p>
        </div>
        <div className="rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-lg shadow-slate-900/5">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#60745c]">Future Pi manifest assistant</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950">Draft manifest from raw files</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Placeholder only: future Pi will inspect uploaded files and propose a manifest draft. In the MVP, no automated mapping is applied without Mirai-admin approval.
          </p>
          <button type="button" disabled className="mt-4 rounded-full border border-dashed border-slate-300 bg-[#fbfaf5] px-4 py-2 text-sm font-semibold text-slate-400">Assistant not active yet</button>
        </div>
      </section>

      <section className="grid gap-5 md:grid-cols-3">
        {[
          ['1', 'Inventory', 'File type, size, checksum, and sheet/column detection.'],
          ['2', 'Needs mapping', 'Mirai admins map customer columns to inputs, outputs, context, units, and keys.'],
          ['3', 'Preprocessing review', 'EDA and preprocessing artifacts become available for approval before training.'],
        ].map(([step, title, body]) => (
          <div key={title} className="rounded-[1.5rem] border border-slate-200 bg-white/90 p-5 shadow-sm shadow-slate-900/5">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-slate-950 text-sm font-bold text-white">{step}</span>
            <h3 className="mt-4 text-lg font-semibold text-slate-950">{title}</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">{body}</p>
          </div>
        ))}
      </section>

      <section className="rounded-[1.75rem] border border-slate-200 bg-white/85 p-5 text-sm text-slate-600">
        Current context project: <span className="font-semibold text-slate-950">{schema.display_name}</span>. New uploads will create a separate project ID.
      </section>
    </div>
  )
}
