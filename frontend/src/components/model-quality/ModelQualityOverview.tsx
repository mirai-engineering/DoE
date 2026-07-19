import type { ModelQualitySummary, ProjectSchema } from '../../lib/api'
import { asNumber, asRecord, asString, formatR2, friendlyModelName, friendlyStatus, splitMean, splitRowCount, splitPresentation } from '../../lib/modelQualityPresentation'
import { formatNumber } from '../../lib/doeUtils'
import { PanelHeader, StatusBadge, TechnicalDetails } from '../ui'

function roleLabels(candidate: Record<string, unknown>, champion: Record<string, unknown>, productionModel: Record<string, unknown>, served: boolean): string[] {
  const name = asString(candidate.model_name)
  const roles: string[] = []
  if (name === 'mean_baseline' || asString(candidate.model_type) === 'mean') roles.push('Baseline')
  else roles.push('Candidate')
  if (candidate.selected_challenger === true) roles.push('Challenger')
  if (name && name === asString(champion.name)) roles.push('Champion')
  if (served && name && [asString(productionModel.name), asString(champion.name)].includes(name)) roles.push('Served')
  return roles
}

function TechnicalValue({ label, value }: { label: string; value: unknown }) {
  const text = asString(value) || (typeof value === 'number' ? String(value) : '—')
  return <div className="min-w-0"><dt className="text-xs font-medium text-[#9FB0C8]">{label}</dt><dd className="mt-1 truncate font-mono text-xs text-slate-200" title={text}>{text}</dd></div>
}

export function ModelQualityOverview({ summary, schema }: { summary: ModelQualitySummary; schema: ProjectSchema }) {
  const metrics = asRecord(summary.metrics)
  const models = asRecord(metrics.models)
  const modelEntries = Object.entries(models)
  const bestModelName = asString(metrics.best_model_name)
  const bestModel = asRecord(models[bestModelName])
  const activeModel = asRecord(summary.active_model)
  const productionModel = asRecord(activeModel.production_model)
  const aliases = asRecord(activeModel.aliases)
  const champion = asRecord(aliases.champion)
  const challenger = asRecord(aliases.challenger)
  const traceability = asRecord(activeModel.mlflow_traceability)
  const requiredArtifacts = asRecord(traceability.required_artifacts)
  const cacheStatus = asRecord(traceability.cache_status)
  const served = asString(activeModel.served_source) === 'loaded_champion'
  const championExists = Boolean(asString(champion.version) || asString(champion.run_id))
  const challengerExists = Boolean(asString(challenger.version) || asString(challenger.run_id) || summary.candidate_comparison?.some((candidate) => candidate.selected_challenger))
  const selectionScore = asNumber(metrics.selection_score) ?? asNumber(bestModel.selection_metric)
  const activeName = asString(champion.name) || asString(productionModel.name) || 'No approved champion'
  const bestMatchesChampion = Boolean(bestModelName && asString(champion.name) && bestModelName === asString(champion.name))

  return (
    <div className="space-y-10 py-7">
      <section aria-labelledby="model-decision-title">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-sm font-medium text-[#74C7F5]">Decision summary</p>
            <h2 id="model-decision-title" className="mt-1.5 text-2xl font-semibold tracking-[-0.035em] text-white">Is the model ready to guide experiments?</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#C7D2E4]">Compare the leading training candidate with the manually approved MLflow champion and the model Mirai has actually loaded for serving.</p>
          </div>
          <StatusBadge tone={served ? 'success' : championExists ? 'warning' : 'neutral'}>{served ? 'Champion loaded' : championExists ? 'Approval exists; load required' : 'Approval required'}</StatusBadge>
        </div>

        <div className="mt-6 grid gap-6 border-y border-white/[0.09] py-6 md:grid-cols-2 xl:grid-cols-4">
          <div><p className="text-xs font-medium text-[#9FB0C8]">Best training candidate</p><p className="mt-2 text-2xl font-semibold text-white">{friendlyModelName(bestModelName || 'unavailable')}</p><p className="mt-1 truncate font-mono text-xs text-[#7F8DA8]" title={bestModelName}>{bestModelName || '—'}</p></div>
          <div><p className="text-xs font-medium text-[#9FB0C8]">Selection metric</p><p className="mt-2 text-2xl font-semibold tabular-nums text-[#BDEAFF]">{formatNumber(selectionScore)}</p><p className="mt-1 text-xs text-[#7F8DA8]">Validation weighted normalized RMSE · lower is better</p></div>
          <div><p className="text-xs font-medium text-[#9FB0C8]">Approved champion</p><p className="mt-2 text-2xl font-semibold text-white">{asString(champion.version) ? `Version ${asString(champion.version)}` : 'None'}</p><p className="mt-1 text-xs text-[#7F8DA8]">{championExists ? 'Champion approval managed in MLflow' : 'Manual approval has not been recorded'}</p></div>
          <div><p className="text-xs font-medium text-[#9FB0C8]">Serving status</p><p className="mt-2 text-2xl font-semibold text-white">{friendlyStatus(activeModel.served_source)}</p><p className="mt-1 text-xs text-[#7F8DA8]">{bestMatchesChampion ? 'Best candidate and champion match' : 'Training rank and approval are separate decisions'}</p></div>
        </div>
      </section>

      <section aria-labelledby="model-state-title">
        <PanelHeader eyebrow="Model state" title="Training candidate → approval → serving" description="These stages are related but not interchangeable. A leading candidate is not served until it is promoted and loaded." />
        <ol className="mt-6 grid gap-3 lg:grid-cols-3">
          {[
            { number: '01', title: 'Training candidate', value: bestModelName ? friendlyModelName(bestModelName) : 'Unavailable', detail: bestModelName || 'No candidate metrics', tone: bestModelName ? 'active' as const : 'neutral' as const },
            { number: '02', title: 'MLflow approval', value: championExists ? `Champion version ${asString(champion.version) || 'recorded'}` : 'Approval required', detail: challengerExists ? `Challenger ${asString(challenger.version) || 'selected'}` : 'No challenger', tone: championExists ? 'success' as const : 'warning' as const },
            { number: '03', title: 'Loaded for serving', value: served ? 'Champion loaded' : 'Not loaded', detail: friendlyStatus(activeModel.lifecycle_status), tone: served ? 'success' as const : 'warning' as const },
          ].map((stage) => (
            <li key={stage.number} className="rounded-lg border border-white/[0.09] bg-[#0B1424]/55 p-5">
              <div className="flex items-center justify-between gap-3"><span className="font-mono text-xs text-[#74C7F5]">{stage.number}</span><StatusBadge tone={stage.tone}>{stage.value}</StatusBadge></div>
              <h3 className="mt-4 font-semibold text-white">{stage.title}</h3>
              <p className="mt-2 truncate font-mono text-xs text-[#9FB0C8]" title={stage.detail}>{stage.detail}</p>
            </li>
          ))}
        </ol>
        <div className="mt-5 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
          <div className="min-w-0"><p className="text-xs font-medium text-[#9FB0C8]">Active model identity</p><p className="mt-1 truncate font-mono text-sm text-white" title={activeName}>{activeName}</p></div>
          <StatusBadge tone={served ? 'success' : 'neutral'}>{served ? 'Served' : 'Not served'}</StatusBadge>
        </div>
      </section>

      <section aria-labelledby="candidate-comparison-title">
        <PanelHeader eyebrow="Candidate comparison" title="Models compared in the latest training result" description="Validation metrics support candidate selection; untouched test metrics remain separate. Negative R² values are preserved." />
        {summary.candidate_comparison?.length ? (
          <div className="mt-6 overflow-x-auto rounded-lg border border-white/[0.09]">
            <table className="min-w-[58rem] w-full text-left text-sm">
              <thead className="sticky top-0 bg-[#0B1424] text-xs text-[#9FB0C8]"><tr><th className="px-4 py-3">Model</th><th className="px-4 py-3">Type</th><th className="px-4 py-3 text-right" title="Lower is better">Validation nRMSE ↓</th><th className="px-4 py-3 text-right" title="Lower is better">Test nRMSE ↓</th><th className="px-4 py-3 text-right" title="Higher is better">Validation R² ↑</th><th className="px-4 py-3 text-right" title="Higher is better">Test R² ↑</th><th className="px-4 py-3">Role</th></tr></thead>
              <tbody className="divide-y divide-white/[0.07]">
                {summary.candidate_comparison.map((candidate, index) => {
                  const roles = roleLabels(candidate, champion, productionModel, served)
                  const leading = asString(candidate.model_name) === bestModelName
                  return <tr key={`${asString(candidate.model_name)}-${index}`} className={leading ? 'bg-[#2F6BFF]/[0.07]' : 'hover:bg-white/[0.025]'}><td className="px-4 py-3"><span className="block font-semibold text-white">{friendlyModelName(asString(candidate.model_name))}</span><span className="block max-w-[15rem] truncate font-mono text-[0.68rem] text-[#7F8DA8]" title={asString(candidate.model_name)}>{asString(candidate.model_name)}</span></td><td className="px-4 py-3 text-slate-300">{friendlyModelName(asString(candidate.model_type))}</td><td className="px-4 py-3 text-right tabular-nums text-slate-200">{formatNumber(asNumber(candidate.validation_weighted_normalized_rmse))}</td><td className="px-4 py-3 text-right tabular-nums text-slate-200">{formatNumber(asNumber(candidate.test_weighted_normalized_rmse))}</td><td className="px-4 py-3 text-right tabular-nums text-slate-200">{formatR2(asNumber(candidate.validation_mean_r2))}</td><td className="px-4 py-3 text-right tabular-nums text-slate-200">{formatR2(asNumber(candidate.test_mean_r2))}</td><td className="px-4 py-3"><div className="flex flex-wrap gap-1">{roles.map((role) => <span key={role} className="rounded-full bg-white/[0.06] px-2 py-1 text-[0.68rem] font-semibold text-slate-200">{role}</span>)}</div></td></tr>
                })}
              </tbody>
            </table>
          </div>
        ) : <p className="mt-5 text-sm text-[#9FB0C8]">No candidate comparison artifact is available.</p>}
      </section>

      <section aria-labelledby="partition-summary-title">
        <PanelHeader eyebrow="Data partitions" title="Grouped split semantics" description="Split membership is preserved from training. Counts are shown only when supplied by the metrics artifact." />
        <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {(['train', 'validation', 'test'] as const).map((split) => <div key={split} className="border-t border-white/[0.09] pt-4"><div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: splitPresentation[split].color }} /><h3 className="font-semibold text-white">{splitPresentation[split].label}</h3></div><p className="mt-3 text-2xl font-semibold tabular-nums text-white">{splitRowCount(bestModel, split) ?? '—'} <span className="text-sm font-medium text-[#7F8DA8]">rows</span></p><p className="mt-2 text-xs leading-5 text-[#9FB0C8]">{splitPresentation[split].purpose}</p></div>)}
          <div className="border-t border-purple-300/30 pt-4"><div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-[#A78BFA]" /><h3 className="font-semibold text-white">BO replay</h3></div><p className="mt-3 text-sm font-semibold text-purple-100">Three cells reserved</p><p className="mt-2 text-xs leading-5 text-[#9FB0C8]">Reserved according to the existing all-cells MVP workflow.</p></div>
        </div>
      </section>

      <TechnicalDetails title="Full split metrics and MLflow traceability">
        <div className="overflow-x-auto"><table className="min-w-[44rem] w-full text-left text-xs"><thead className="text-[#9FB0C8]"><tr><th className="px-3 py-2">Model</th><th className="px-3 py-2">Split</th><th className="px-3 py-2 text-right">R²</th><th className="px-3 py-2 text-right">RMSE</th><th className="px-3 py-2 text-right">nRMSE</th><th className="px-3 py-2 text-right">MAE</th></tr></thead><tbody>{modelEntries.flatMap(([name, value]) => (['train', 'validation', 'test'] as const).map((split) => { const model = asRecord(value); return <tr key={`${name}-${split}`} className="border-t border-white/[0.07]"><td className="px-3 py-2 font-mono text-slate-200">{name}</td><td className="px-3 py-2 text-slate-300">{split}</td><td className="px-3 py-2 text-right tabular-nums">{formatNumber(splitMean(model, split, 'r2'))}</td><td className="px-3 py-2 text-right tabular-nums">{formatNumber(splitMean(model, split, 'rmse'))}</td><td className="px-3 py-2 text-right tabular-nums">{formatNumber(splitMean(model, split, 'normalized_rmse'))}</td><td className="px-3 py-2 text-right tabular-nums">{formatNumber(splitMean(model, split, 'mae'))}</td></tr> }))}</tbody></table></div>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[['Workspace ID', traceability.workspace_id], ['Project ID', traceability.project_id || schema.project_id], ['Registered model', traceability.registered_model_name || activeModel.registered_model_name], ['Alias', traceability.alias], ['Model version', traceability.model_version || champion.version], ['Run ID', traceability.run_id || champion.run_id], ['Model URI', traceability.model_uri], ['Tracking URI', traceability.tracking_uri || activeModel.tracking_uri], ['Loaded at', traceability.loaded_at], ['Artifact cache', cacheStatus.status]].map(([label, value]) => <TechnicalValue key={String(label)} label={String(label)} value={value} />)}</dl>
        {!!Object.keys(requiredArtifacts).length && <div className="mt-5 flex flex-wrap gap-2">{Object.entries(requiredArtifacts).map(([name, present]) => <StatusBadge key={name} tone={present ? 'success' : 'error'}>{name}: {present ? 'present' : 'missing'}</StatusBadge>)}</div>}
      </TechnicalDetails>
    </div>
  )
}
