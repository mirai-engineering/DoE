import type { ModelQualitySummary, ProjectSchema } from '../../lib/api'
import { artifactDisplayName, asRecord, asString, friendlyStatus } from '../../lib/modelQualityPresentation'
import { PanelHeader, StatusBadge, TechnicalDetails } from '../ui'

function stringList(value: unknown): string[] { return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [] }

export function ModelQualityArtifacts({ summary, schema }: { summary: ModelQualitySummary; schema: ProjectSchema }) {
  const artifacts = asRecord(summary.artifact_summary)
  const activeModel = asRecord(summary.active_model)
  const traceability = asRecord(activeModel.mlflow_traceability)
  const required = asRecord(traceability.required_artifacts)
  const cache = asRecord(traceability.cache_status)
  const preprocessing = asRecord(summary.preprocessing_report)
  const files = stringList(artifacts.files)
  const predictionsPath = asString(artifacts.predictions_artifact)
  const availableFiles = predictionsPath && !files.includes(predictionsPath) ? [...files, predictionsPath] : files
  const latestRun = summary.latest_runs[0] ?? {}
  const assistant = asRecord(summary.ai_preprocessing_assistant)

  return (
    <div className="space-y-10 py-7">
      <section><PanelHeader eyebrow="Model lineage" title="Evidence supporting this model result" description="Training, MLflow, preprocessing, diagnostics, and serving state remain linked through their exact identifiers." /><div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">{[
        ['Training run', asString(latestRun.run_name) || asString(latestRun.run_id) || 'Unavailable', Boolean(asString(latestRun.run_id))],
        ['MLflow champion', asString(traceability.model_version) ? `Version ${asString(traceability.model_version)}` : 'No version recorded', Boolean(asString(traceability.model_version))],
        ['Diagnostics', artifacts.prediction_diagnostics_available ? 'Available' : 'Unavailable', Boolean(artifacts.prediction_diagnostics_available)],
        ['Serving state', friendlyStatus(activeModel.served_source), asString(activeModel.served_source) === 'loaded_champion'],
      ].map(([label, value, available]) => <div key={String(label)} className="rounded-lg border border-white/[0.09] bg-[#0B1424]/55 p-5"><div className="flex items-center justify-between gap-3"><p className="text-xs font-medium text-[#9FB0C8]">{String(label)}</p><StatusBadge tone={available ? 'success' : 'neutral'}>{available ? 'Available' : 'Not available'}</StatusBadge></div><p className="mt-3 truncate font-semibold text-white" title={String(value)}>{String(value)}</p></div>)}</div></section>

      <section className="grid gap-8 lg:grid-cols-2">
        <div><PanelHeader eyebrow="Validation artifacts" title="Metrics and diagnostic evidence" description="Only files reported by the artifact summary or loaded MLflow package are shown." /><div className="mt-5 divide-y divide-white/[0.08] border-y border-white/[0.08]">{availableFiles.length ? availableFiles.map((file) => <div key={file} className="py-4"><p className="text-sm font-semibold text-white">{artifactDisplayName(file)}</p><p className="mt-1 truncate font-mono text-xs text-[#7F8DA8]" title={file}>{file}</p></div>) : <p className="py-5 text-sm text-[#9FB0C8]">No file inventory is available in the current artifact summary.</p>}</div></div>
        <div><PanelHeader eyebrow="Preprocessing provenance" title="Fit-on-train preparation state" description="The model result retains the preprocessing methods and approval state supplied by the existing report." /><dl className="mt-5 divide-y divide-white/[0.08] border-y border-white/[0.08]">{[
          ['Input imputation', asString(asRecord(preprocessing.input_imputation).method) || 'median'],
          ['Input scaling', asString(asRecord(preprocessing.input_scaling).method) || 'minmax'],
          ['Review status', friendlyStatus(preprocessing.review_status)],
          ['Project', schema.display_name],
        ].map(([label, value]) => <div key={label} className="flex items-start justify-between gap-5 py-4"><dt className="text-sm text-[#9FB0C8]">{label}</dt><dd className="max-w-[65%] break-words text-right text-sm font-semibold text-white">{value}</dd></div>)}</dl></div>
      </section>

      <section><PanelHeader eyebrow="Serving evidence" title="MLflow and loaded-model state" description="Approval metadata and runtime loading remain distinct and inspectable." /><div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[
        ['Registered model', traceability.registered_model_name || activeModel.registered_model_name], ['Alias', traceability.alias], ['Model version', traceability.model_version], ['Run ID', traceability.run_id], ['Model URI', traceability.model_uri], ['Tracking URI', traceability.tracking_uri || activeModel.tracking_uri], ['Loaded at', traceability.loaded_at], ['Loaded by', traceability.loaded_by], ['Artifact cache', asString(cache.status) || 'unavailable'],
      ].map(([label, value]) => { const text = asString(value) || (typeof value === 'number' ? String(value) : '—'); return <div key={String(label)} className="min-w-0 border-t border-white/[0.09] pt-4"><p className="text-xs text-[#9FB0C8]">{String(label)}</p><p className="mt-1 truncate font-mono text-xs text-slate-200" title={text}>{text}</p></div> })}</div>{!!Object.keys(required).length && <div className="mt-6 flex flex-wrap gap-2">{Object.entries(required).map(([name, present]) => <StatusBadge key={name} tone={present ? 'success' : 'error'}>{artifactDisplayName(name)}: {present ? 'present' : 'missing'}</StatusBadge>)}</div>}</section>

      <TechnicalDetails><p>Training and validation artifacts are read from the current training result or loaded MLflow run. No artifact is generated by this page.</p><p>Preprocessing assistant: {friendlyStatus(assistant.status)}. {asString(assistant.message) || 'No autonomous preprocessing is active.'}</p><p className="break-all font-mono text-xs">Project ID: {schema.project_id}</p><p className="break-all font-mono text-xs">Run ID: {asString(traceability.run_id) || '—'}</p></TechnicalDetails>
    </div>
  )
}
