import { useEffect, useMemo, useState } from 'react'
import Plot from 'react-plotly.js'
import type { ModelQualityPredictionsResponse, ModelQualitySummary, ProjectSchema } from '../lib/api'
import { getModelQualityPredictions, getModelQualityPredictionsExportUrl, getModelQualitySummary } from '../lib/api'
import { formatNumber } from '../lib/doeUtils'
import { Alert, PanelHeader } from './ui'

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function formatR2(value: number | undefined) {
  return value === undefined ? '-' : value.toFixed(3)
}

function formatPercent1(value: number | undefined) {
  return value === undefined ? '-' : `${value.toFixed(1)}%`
}

function formatMetric(value: number | undefined, unit = '') {
  if (value === undefined) return '-'
  const formatted = Math.abs(value) >= 100 ? value.toFixed(1) : Number(value.toPrecision(3)).toString()
  return unit ? `${formatted} ${unit}` : formatted
}

type TrustLevel = 'strong' | 'usable' | 'weak' | 'needs_review'

type OutputTrustData = {
  output: ProjectSchema['outputs'][number]
  validation: Record<string, unknown>
  test: Record<string, unknown>
  level: TrustLevel
  label: string
  sortScore: number
  interpretation: string
  objectiveWeightWarning?: string
}

const TRUST_STYLES: Record<TrustLevel, string> = {
  strong: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  usable: 'border-amber-200 bg-amber-50 text-amber-800',
  weak: 'border-rose-200 bg-rose-50 text-rose-800',
  needs_review: 'border-slate-200 bg-slate-100 text-slate-700',
}

function classifyOutputTrust(metrics: Record<string, unknown>) {
  const r2 = asNumber(metrics.r2)
  const maeMean = asNumber(metrics.mae_percent_of_split_mean)
  const improvement = asNumber(metrics.baseline_improvement_mae_percent)
  if (r2 === undefined && maeMean === undefined) {
    return {
      level: 'needs_review' as TrustLevel,
      label: 'Needs review',
      sortScore: -Infinity,
      interpretation: 'Test evidence is incomplete for this output. Review the detailed metrics before using it in optimization.',
    }
  }
  if ((r2 ?? -Infinity) >= 0.75 && (maeMean ?? Infinity) <= 20) {
    return {
      level: 'strong' as TrustLevel,
      label: 'Strong',
      sortScore: (r2 ?? 0) * 100 - (maeMean ?? 0),
      interpretation: 'This output is suitable for optimization-driven ranking, assuming candidates remain within the training data domain.',
    }
  }
  if ((r2 ?? -Infinity) <= 0.05) {
    return {
      level: 'weak' as TrustLevel,
      label: 'Weak',
      sortScore: (r2 ?? -1) * 100 - (maeMean ?? 100),
      interpretation: 'This output performs close to or worse than a simple baseline. Avoid using it as a dominant optimization objective until the model improves.',
    }
  }
  if ((r2 ?? -Infinity) >= 0.5 || (maeMean ?? Infinity) <= 30) {
    return {
      level: 'usable' as TrustLevel,
      label: 'Accurate',
      sortScore: (r2 ?? 0) * 100 - (maeMean ?? 0) + Math.max(0, improvement ?? 0) * 0.1,
      interpretation: 'This output can support recommendations, but it should not dominate the objective without expert review.',
    }
  }
  return {
    level: 'weak' as TrustLevel,
    label: 'Weak',
    sortScore: (r2 ?? -1) * 100 - (maeMean ?? 100),
    interpretation: 'This output is weakly predicted. Recommendations heavily weighted toward this KPI should be treated cautiously.',
  }
}

function splitMean(model: Record<string, unknown>, split: string, metric: string) {
  const splits = asRecord(model.splits)
  const splitData = asRecord(splits[split])
  const explicitMean = asNumber(splitData[`mean_${metric}`])
  if (explicitMean !== undefined) return explicitMean
  const values = Object.values(splitData)
    .map((value) => asNumber(asRecord(value)[metric]))
    .filter((value): value is number => value !== undefined)
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : undefined
}

function uniqueStrings(rows: Array<Record<string, unknown>>, column: string) {
  return [...new Set(rows.map((row) => asString(row[column])).filter(Boolean))].sort()
}

function uniqueNumbers(rows: Array<Record<string, unknown>>, column: string) {
  return [...new Set(rows.map((row) => asNumber(row[column])).filter((value): value is number => value !== undefined))].sort((a, b) => a - b)
}

function uniqueValuesAsStrings(rows: Array<Record<string, unknown>>, column: string) {
  return [...new Set(rows.map((row) => {
    const text = asString(row[column])
    if (text) return text
    const number = asNumber(row[column])
    return number === undefined ? '' : String(number)
  }).filter(Boolean))].sort()
}

const plotLayoutBase = {
  paper_bgcolor: 'rgba(255,255,255,0)',
  plot_bgcolor: '#ffffff',
  margin: { l: 58, r: 24, t: 30, b: 54 },
  font: { family: 'Inter, ui-sans-serif, system-ui', color: '#334155' },
  legend: { orientation: 'h' as const, y: -0.25 },
}

const plotConfig = { responsive: true, displaylogo: false }

function asPlotData(value: unknown) {
  return value as any
}

function asPlotLayout(value: unknown) {
  return value as any
}

export function ModelQualityPage({ schema }: { schema: ProjectSchema }) {
  const [summary, setSummary] = useState<ModelQualitySummary | null>(null)
  const [predictions, setPredictions] = useState<ModelQualityPredictionsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [predictionLoading, setPredictionLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [predictionError, setPredictionError] = useState<string | null>(null)
  const modelQualityConfig = asRecord(schema.domain_metadata?.ui_config?.model_quality)
  const approvedTemplateId = asString(schema.domain_metadata?.template_id)
  const isFuelCellTemplate = approvedTemplateId === 'fuel_cell'
  const defaultDiagnosticOutput = asString(modelQualityConfig.default_output) || schema.outputs[0]?.name || ''
  const defaultDiagnosticGroup = asString(modelQualityConfig.default_group) || 'split'
  const [diagnosticModel, setDiagnosticModel] = useState('')
  const [diagnosticOutput, setDiagnosticOutput] = useState(defaultDiagnosticOutput)
  const [diagnosticSplit, setDiagnosticSplit] = useState('validation,test')
  const [diagnosticGroup, setDiagnosticGroup] = useState(defaultDiagnosticGroup)
  const [selectedCellId, setSelectedCellId] = useState('')
  const [selectedRh, setSelectedRh] = useState('')

  async function loadSummary() {
    setLoading(true)
    setError(null)
    try {
      setSummary(await getModelQualitySummary(schema.project_id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load model quality')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setDiagnosticOutput(defaultDiagnosticOutput)
    setDiagnosticGroup(defaultDiagnosticGroup)
    loadSummary()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema.project_id, defaultDiagnosticOutput, defaultDiagnosticGroup])

  useEffect(() => {
    async function loadPredictions() {
      setPredictionLoading(true)
      setPredictionError(null)
      try {
        const payload = await getModelQualityPredictions(schema.project_id, { limit: 50000 })
        setPredictions(payload)
      } catch (err) {
        setPredictionError(err instanceof Error ? err.message : 'Unable to load prediction diagnostics')
      } finally {
        setPredictionLoading(false)
      }
    }
    loadPredictions()
  }, [schema.project_id])

  const metrics = asRecord(summary?.metrics)
  const models = asRecord(metrics.models)
  const modelEntries = useMemo(() => Object.entries(models), [models])
  const bestModelName = asString(metrics.best_model_name)
  const bestModel = asRecord(models[bestModelName])
  const bestSplits = asRecord(bestModel.splits)
  const targetReference = asRecord(metrics.target_reference)
  const activeModel = asRecord(summary?.active_model)
  const productionModel = asRecord(activeModel.production_model)
  const aliases = asRecord(activeModel.aliases)
  const champion = asRecord(aliases.champion)
  const challenger = asRecord(aliases.challenger)
  const preprocessing = asRecord(summary?.preprocessing_report)
  const assistant = asRecord(summary?.ai_preprocessing_assistant)
  // TODO: Pass active BO/recommendation objective weights here when Model Quality has access to them.
  const objectiveWeights: Record<string, number> | undefined = undefined
  const outputTrustData = useMemo<OutputTrustData[]>(() => {
    const validationSplit = asRecord(bestSplits.validation)
    const testSplit = asRecord(bestSplits.test)
    return schema.outputs.map((output) => {
      const validation = asRecord(validationSplit[output.name])
      const test = asRecord(testSplit[output.name])
      const trust = classifyOutputTrust(test)
      const objectiveWeight = objectiveWeights?.[output.name]
      const objectiveWeightWarning =
        objectiveWeight !== undefined && Math.abs(objectiveWeight) >= 0.25 && ['weak', 'needs_review'].includes(trust.level)
          ? `Warning: ${output.label} has ${trust.label.toLowerCase()} test performance but currently receives a high objective weight. The optimizer may over-rank candidates based on unreliable predictions.`
          : undefined
      return { output, validation, test, ...trust, objectiveWeightWarning }
    })
  }, [bestSplits, objectiveWeights, schema.outputs])
  const predictionRows = predictions?.rows ?? []
  const diagnosticModelOptions = useMemo(() => uniqueStrings(predictionRows, 'model_name'), [predictionRows])
  const selectedDiagnosticModel = diagnosticModel || bestModelName || diagnosticModelOptions[0] || ''
  const predictionColumns = predictions?.columns ?? []
  const predictionOutputOptions = useMemo(
    () => schema.outputs.filter((output) => predictionColumns.includes(`${output.name}_true`) && predictionColumns.includes(`${output.name}_pred`)),
    [predictionColumns, schema.outputs],
  )
  useEffect(() => {
    if (!predictionOutputOptions.length) return
    if (!predictionOutputOptions.some((output) => output.name === diagnosticOutput)) {
      setDiagnosticOutput(predictionOutputOptions[0].name)
    }
  }, [diagnosticOutput, predictionOutputOptions])
  const activeDiagnosticOutput = predictionOutputOptions.some((output) => output.name === diagnosticOutput)
    ? diagnosticOutput
    : predictionOutputOptions[0]?.name || ''
  const diagnosticRows = useMemo(() => {
    const splitSet = new Set(diagnosticSplit.split(',').map((item) => item.trim()).filter(Boolean))
    return predictionRows.filter((row) => {
      const modelMatches = !selectedDiagnosticModel || asString(row.model_name) === selectedDiagnosticModel
      const splitMatches = splitSet.size === 0 || splitSet.has(asString(row.split))
      return modelMatches && splitMatches
    })
  }, [diagnosticSplit, predictionRows, selectedDiagnosticModel])
  const availableCellIds = useMemo(() => uniqueStrings(diagnosticRows, 'cell_id'), [diagnosticRows])
  const availableRhs = useMemo(() => uniqueNumbers(diagnosticRows, 'operating_rh'), [diagnosticRows])
  const selectedPolarizationCell = selectedCellId || availableCellIds[0] || ''
  const selectedPolarizationRh = selectedRh || (availableRhs[0] !== undefined ? String(availableRhs[0]) : '')
  const polarizationRows = useMemo(() => diagnosticRows
    .filter((row) => !selectedPolarizationCell || asString(row.cell_id) === selectedPolarizationCell)
    .filter((row) => !selectedPolarizationRh || asNumber(row.operating_rh) === Number(selectedPolarizationRh))
    .sort((a, b) => (asNumber(a.operating_voltage) ?? 0) - (asNumber(b.operating_voltage) ?? 0)), [diagnosticRows, selectedPolarizationCell, selectedPolarizationRh])
  const outputMeta = schema.outputs.find((output) => output.name === activeDiagnosticOutput) ?? predictionOutputOptions[0] ?? schema.outputs[0]
  const outputLabel = outputMeta?.label || activeDiagnosticOutput
  const outputUnit = outputMeta?.unit || ''
  const diagnosticSplitLabel = diagnosticSplit
    .split(',')
    .map((split) => split.trim().replace('_', ' '))
    .filter(Boolean)
    .join(' + ')
  const polarizationContext = `Cell ${selectedPolarizationCell || '-'}, RH ${selectedPolarizationRh || '-'}% — ${diagnosticSplitLabel || 'selected splits'}`
  const parityRows = diagnosticRows.filter((row) => asNumber(row[`${activeDiagnosticOutput}_true`]) !== undefined && asNumber(row[`${activeDiagnosticOutput}_pred`]) !== undefined)
  const residualXAxisColumn = isFuelCellTemplate && predictions?.columns.includes('operating_voltage') ? 'operating_voltage' : `${activeDiagnosticOutput}_pred`
  const residualXAxisLabel = isFuelCellTemplate ? 'Operating voltage / V' : `Predicted ${outputLabel}${outputUnit ? ` (${outputUnit})` : ''}`
  const groupCandidates = ['split', defaultDiagnosticGroup, 'cell_id', 'operating_rh'].filter((value, index, array) => value && array.indexOf(value) === index && (value === 'split' || predictions?.columns.includes(value)))
  const exportUrl = getModelQualityPredictionsExportUrl(schema.project_id, { model_name: selectedDiagnosticModel || undefined, splits: diagnosticSplit })

  const trustSummary = useMemo(() => {
    const usableCount = outputTrustData.filter((item) => item.level === 'strong' || item.level === 'usable').length
    const weakCount = outputTrustData.filter((item) => item.level === 'weak' || item.level === 'needs_review').length
    const sorted = [...outputTrustData].sort((a, b) => b.sortScore - a.sortScore)
    const best = sorted[0]
    const weakest = sorted[sorted.length - 1]
    const strongCount = outputTrustData.filter((item) => item.level === 'strong').length
    const overall = weakCount === 0 && strongCount >= Math.max(1, outputTrustData.length - 1) ? 'Good' : usableCount >= Math.ceil(outputTrustData.length / 2) ? 'Medium' : weakCount > 0 ? 'Needs review' : 'Weak'
    const currentDensityUsable = outputTrustData.filter((item) => item.output.name.includes('current_density') && (item.level === 'strong' || item.level === 'usable')).length
    const currentDensityCopy = currentDensityUsable >= 2 ? 'Current-density predictions look accurate enough for ranking.' : 'Current-density predictions need caution.'
    return { usableCount, weakCount, best, weakest, overall, currentDensityCopy }
  }, [outputTrustData])

  return (
    <div className="space-y-8">
      <section className="rounded-[2rem] border border-white/70 bg-white/85 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
        <PanelHeader
          eyebrow="Model Quality"
          title="Training credibility and validation diagnostics"
          description="Inspect split metrics, preprocessing artifacts, active champion version, and prediction diagnostics before trusting DoE recommendations."
        />
        <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          All-cells MVP workflow. Splits are grouped by cell_id, three cells are reserved exclusively for BO replay, and acceptance thresholds are provisional/report-only.
        </div>
      </section>

      <nav className="rounded-[1.5rem] border border-white/70 bg-white/70 p-3 shadow-sm backdrop-blur" aria-label="Model Quality page sections">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="px-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">On this page</span>
          {[
            ['Trust summary', '#quality-trust-summary'],
            ['Split evidence', '#quality-splits'],
            ['Error scale', '#quality-error-scale'],
            ['Prediction diagnostics', '#quality-diagnostics'],
          ].map(([label, href]) => (
            <a key={href} href={href} className="rounded-full border border-slate-200 bg-white px-3 py-1.5 font-semibold text-slate-600 transition hover:border-[#526949]/40 hover:text-[#526949]">
              {label}
            </a>
          ))}
        </div>
      </nav>

      {error && <Alert tone="error" title="Model quality unavailable" messages={[error]} />}
      {loading && <div className="rounded-[2rem] bg-white/80 p-6 text-slate-600">Loading model quality...</div>}

      {!loading && summary && (
        <>
          <section id="quality-trust-summary" className="scroll-mt-8 grid gap-4 md:grid-cols-4">
            <div className="rounded-3xl border border-slate-200 bg-white/85 p-5 shadow-sm">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Active model</div>
              <div className="mt-2 text-xl font-semibold text-slate-950">
                {asString(champion.name) || asString(productionModel.name) || 'No champion model'}
              </div>
              <div className="mt-1 text-sm text-slate-500">Champion version {asString(champion.version) || '-'}</div>
              <div className="mt-2 text-sm text-slate-500">Challenger version {asString(challenger.version) || '-'}</div>
              <div className="mt-3 rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-white w-fit">
                served: {asString(activeModel.served_source) || 'artifact'}
              </div>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white/85 p-5 shadow-sm">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Best smoke model</div>
              <div className="mt-2 text-xl font-semibold text-slate-950">{bestModelName || '-'}</div>
              <div className="mt-1 text-sm text-slate-500">Selection: weighted validation normalized RMSE</div>
              <div className="mt-3 text-2xl font-semibold text-[#526949]">
                {formatNumber(asNumber(bestModel.selection_metric))}
              </div>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white/85 p-5 shadow-sm">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">MLflow approval</div>
              <div className="mt-2 text-xl font-semibold text-slate-950">Champion alias is approval</div>
              <p className="mt-1 text-sm leading-6 text-slate-500">Promote a version to <code>champion</code> in MLflow, then use Load champion model in Mirai. Serving uses the loaded ONNX champion only.</p>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white/85 p-5 shadow-sm">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Mirai serving</div>
              <div className="mt-2 text-xl font-semibold text-slate-950">
                {asString(activeModel.served_source) === 'loaded_champion' ? 'Champion loaded' : 'Not active'}
              </div>
              <p className="mt-1 text-sm leading-6 text-slate-500">Design Studio and prediction APIs require an active loaded champion.</p>
            </div>
          </section>

          {!!summary.candidate_comparison?.length && (
            <section className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/85 p-6 shadow-sm">
              <PanelHeader eyebrow="Training candidates" title="Candidate comparison" description="Top models from the latest training request. Challenger is selected by validation weighted normalized RMSE; champion remains manual in MLflow." />
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="text-xs uppercase tracking-[0.14em] text-slate-500"><tr><th className="px-3 py-2">Model</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Val nRMSE</th><th className="px-3 py-2">Test nRMSE</th><th className="px-3 py-2">Val R²</th><th className="px-3 py-2">Test R²</th><th className="px-3 py-2">Role</th></tr></thead>
                  <tbody className="divide-y divide-slate-100">
                    {summary.candidate_comparison.slice(0, 12).map((candidate, index) => (
                      <tr key={`${asString(candidate.model_name)}-${index}`}>
                        <td className="px-3 py-2 font-semibold text-slate-900">{asString(candidate.model_name)}</td>
                        <td className="px-3 py-2 text-slate-600">{asString(candidate.model_type)}</td>
                        <td className="px-3 py-2 text-slate-600">{formatNumber(asNumber(candidate.validation_weighted_normalized_rmse))}</td>
                        <td className="px-3 py-2 text-slate-600">{formatNumber(asNumber(candidate.test_weighted_normalized_rmse))}</td>
                        <td className="px-3 py-2 text-slate-600">{formatR2(asNumber(candidate.validation_mean_r2))}</td>
                        <td className="px-3 py-2 text-slate-600">{formatR2(asNumber(candidate.test_mean_r2))}</td>
                        <td className="px-3 py-2 text-slate-600">{candidate.selected_challenger ? 'challenger' : 'candidate'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section id="quality-splits" className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/85 p-6 shadow-sm">
            <PanelHeader
              eyebrow="Grouped split summary"
              title="Cell-level partitions"
              description="Train and validation rows are available to the BO replay loop; test cells stay untouched for model-quality evaluation."
            />
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              {['train', 'validation', 'test'].map((split) => (
                <div key={split} className="rounded-2xl bg-[#fbfaf5] p-3 text-sm font-semibold text-slate-700">
                  {split.replace('_', ' ')}
                </div>
              ))}
            </div>
            <div className="mt-3 text-sm text-slate-500">Challenger version: {asString(challenger.version) || 'none'}</div>
          </section>

          <section id="quality-error-scale" className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/85 p-6 shadow-sm">
            <PanelHeader
              eyebrow="Scientific reference scale"
              title="How large are the errors relative to the targets?"
              description="Reference values are computed on training cells only. They help interpret whether an error is large in the physical units scientists care about."
            />
            <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {schema.outputs.map((output) => {
                const ref = asRecord(targetReference[output.name])
                return (
                  <div key={output.name} className="rounded-3xl border border-slate-200 bg-[#fbfaf5] p-4">
                    <div className="text-sm font-semibold text-slate-900">{output.label}</div>
                    <div className="mt-3 space-y-1 text-xs text-slate-600">
                      <div>Mean: <strong>{formatNumber(asNumber(ref.train_mean))} {output.unit}</strong></div>
                      <div>Range: {formatNumber(asNumber(ref.train_min))}–{formatNumber(asNumber(ref.train_max))} {output.unit}</div>
                      <div>Std: {formatNumber(asNumber(ref.std))} {output.unit}</div>
                    </div>
                  </div>
                )
              })}
            </div>
          </section>

          <section className="rounded-[2rem] border border-slate-200 bg-white/85 p-6 shadow-sm">
            <PanelHeader
              eyebrow="Model comparison"
              title="Split metrics"
              description="Averaged metrics compare candidate models with the train-mean baseline. nRMSE is scale-aware; negative R² means worse than the split mean."
            />
            <div className="mt-5 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-[0.16em] text-slate-400">
                  <tr>
                    <th className="px-3 py-2">Model</th>
                    <th className="px-3 py-2">Split</th>
                    <th className="px-3 py-2">R²</th>
                    <th className="px-3 py-2">RMSE</th>
                    <th className="px-3 py-2">nRMSE</th>
                    <th className="px-3 py-2">MAE</th>
                  </tr>
                </thead>
                <tbody>
                  {modelEntries.flatMap(([name, value]) =>
                    ['train', 'validation', 'test'].map((split) => {
                      const model = asRecord(value)
                      return (
                        <tr key={`${name}-${split}`} className="border-t border-slate-100">
                          <td className="px-3 py-2 font-semibold text-slate-800">{name}</td>
                          <td className="px-3 py-2 text-slate-600">{split}</td>
                          <td className="px-3 py-2">{formatNumber(splitMean(model, split, 'r2'))}</td>
                          <td className="px-3 py-2">{formatNumber(splitMean(model, split, 'rmse'))}</td>
                          <td className="px-3 py-2">{formatNumber(splitMean(model, split, 'normalized_rmse'))}</td>
                          <td className="px-3 py-2">{formatNumber(splitMean(model, split, 'mae'))}</td>
                        </tr>
                      )
                    }),
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-[2rem] border border-slate-200 bg-white/85 p-6 shadow-sm">
            <PanelHeader
              eyebrow="Per-output accuracy"
              title="Surrogate model accuracy"
              description="Validation and test metrics for each predicted output. Use this page to judge how much to trust optimization recommendations."
            />

            <div className="mt-6 rounded-3xl border border-slate-200 bg-[#fbfaf5] p-5 shadow-sm">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Surrogate trust summary</div>
                  <div className="mt-2 flex flex-wrap items-center gap-3">
                    <span className="text-3xl font-semibold tracking-[-0.04em] text-slate-950">{trustSummary.overall}</span>
                    <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-600">
                      {bestModelName || 'best model'}
                    </span>
                  </div>
                  <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
                    {trustSummary.usableCount} of {outputTrustData.length} outputs show accurate-enough test performance. {trustSummary.currentDensityCopy}{' '}
                    {trustSummary.weakest ? `${trustSummary.weakest.output.label} is the weakest output and should be treated with caution in optimization.` : ''}
                  </p>
                </div>
                <div className="grid min-w-[18rem] grid-cols-2 gap-3 text-sm">
                  <div className="rounded-2xl bg-white p-3">
                    <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Accurate outputs</div>
                    <div className="mt-1 text-2xl font-semibold text-[#526949]">{trustSummary.usableCount}</div>
                  </div>
                  <div className="rounded-2xl bg-white p-3">
                    <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Weak outputs</div>
                    <div className="mt-1 text-2xl font-semibold text-rose-700">{trustSummary.weakCount}</div>
                  </div>
                  <div className="rounded-2xl bg-white p-3">
                    <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Best predicted</div>
                    <div className="mt-1 text-sm font-semibold text-slate-900">{trustSummary.best?.output.label || '-'}</div>
                  </div>
                  <div className="rounded-2xl bg-white p-3">
                    <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Weakest</div>
                    <div className="mt-1 text-sm font-semibold text-slate-900">{trustSummary.weakest?.output.label || '-'}</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-6 grid gap-5 xl:grid-cols-2">
              {outputTrustData.map((item) => {
                const unit = item.output.unit
                const primaryMetrics = [
                  { label: 'Test R²', value: formatR2(asNumber(item.test.r2)) },
                  { label: 'Test MAE', value: formatMetric(asNumber(item.test.mae), unit) },
                  { label: 'Error vs mean', value: formatPercent1(asNumber(item.test.mae_percent_of_split_mean)) },
                  { label: 'MAE vs mean baseline', value: formatPercent1(asNumber(item.test.baseline_improvement_mae_percent)) },
                ]
                const comparisonRows = [
                  { label: 'Validation', metrics: item.validation, emphasize: false },
                  { label: 'Test', metrics: item.test, emphasize: true },
                ]
                return (
                  <article key={item.output.name} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="text-xl font-semibold tracking-[-0.03em] text-slate-950">{item.output.label}</h3>
                        <p className="mt-1 text-xs font-medium uppercase tracking-[0.16em] text-slate-400">{unit}</p>
                      </div>
                      <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${TRUST_STYLES[item.level]}`}>
                        {item.label}
                      </span>
                    </div>

                    <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
                      {primaryMetrics.map((metric) => (
                        <div key={metric.label} className="rounded-2xl bg-[#fbfaf5] p-3">
                          <div className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-slate-400">{metric.label}</div>
                          <div className="mt-1 text-lg font-semibold text-slate-950">{metric.value}</div>
                        </div>
                      ))}
                    </div>

                    <p className="mt-4 rounded-2xl bg-slate-50 p-3 text-sm leading-6 text-slate-600">{item.interpretation}</p>
                    {item.objectiveWeightWarning && (
                      <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{item.objectiveWeightWarning}</div>
                    )}

                    <div className="mt-5 overflow-x-auto">
                      <table className="min-w-full text-left text-xs">
                        <thead className="uppercase tracking-[0.14em] text-slate-400">
                          <tr>
                            <th className="px-3 py-2">Split</th>
                            <th className="px-3 py-2">R²</th>
                            <th className="px-3 py-2">MAE</th>
                            <th className="px-3 py-2">RMSE</th>
                            <th className="px-3 py-2">MAE/mean</th>
                            <th className="px-3 py-2">MAE vs baseline</th>
                          </tr>
                        </thead>
                        <tbody>
                          {comparisonRows.map((row) => (
                            <tr key={row.label} className={row.emphasize ? 'border-t border-slate-100 bg-[#f8f6ef] font-semibold text-slate-900' : 'border-t border-slate-100 text-slate-600'}>
                              <td className="whitespace-nowrap px-3 py-2">{row.label}</td>
                              <td className="whitespace-nowrap px-3 py-2">{formatR2(asNumber(row.metrics.r2))}</td>
                              <td className="whitespace-nowrap px-3 py-2">{formatMetric(asNumber(row.metrics.mae), unit)}</td>
                              <td className="whitespace-nowrap px-3 py-2">{formatMetric(asNumber(row.metrics.rmse), unit)}</td>
                              <td className="whitespace-nowrap px-3 py-2">{formatPercent1(asNumber(row.metrics.mae_percent_of_split_mean))}</td>
                              <td className="whitespace-nowrap px-3 py-2">{formatPercent1(asNumber(row.metrics.baseline_improvement_mae_percent))}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <details className="mt-4 rounded-2xl border border-slate-200 bg-[#fbfaf5] p-3 text-sm text-slate-600">
                      <summary className="cursor-pointer select-none font-semibold text-slate-800">Show detailed metrics</summary>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        {comparisonRows.map((row) => (
                          <div key={`${item.output.name}-${row.label}-details`} className="rounded-2xl bg-white p-3">
                            <div className="font-semibold text-slate-900">{row.label}</div>
                            <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                              <span>nRMSE {formatNumber(asNumber(row.metrics.normalized_rmse))}</span>
                              <span>RMSE/range {formatPercent1(asNumber(row.metrics.rmse_percent_of_train_range))}</span>
                              <span>RMSE/std {formatPercent1(asNumber(row.metrics.rmse_percent_of_train_std))}</span>
                              <span>Baseline MAE {formatMetric(asNumber(row.metrics.baseline_mae), unit)}</span>
                              <span>Baseline RMSE {formatMetric(asNumber(row.metrics.baseline_rmse), unit)}</span>
                              <span>Status {asString(row.metrics.acceptance_status) || '-'}</span>
                            </div>
                            {asString(row.metrics.r2_note) && <div className="mt-2 text-xs text-amber-700">{asString(row.metrics.r2_note)}</div>}
                            {asString(row.metrics.scientist_summary) && (
                              <div className="mt-2 rounded-xl bg-slate-50 p-2 text-xs text-slate-600">{asString(row.metrics.scientist_summary)}</div>
                            )}
                          </div>
                        ))}
                      </div>
                    </details>
                  </article>
                )
              })}
            </div>
          </section>

          <section id="quality-diagnostics" className="scroll-mt-8 rounded-[2rem] border border-slate-200 bg-white/90 p-6 shadow-sm">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <PanelHeader
                eyebrow="Prediction diagnostics"
                title="Measured vs predicted engineering behavior"
                description="Visual checks of whether the surrogate reproduces physical trends. These plots use training-run predictions for train/validation/test/BO-holdout rows."
              />
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-emerald-800">
                  Training-run predictions
                </span>
                <a
                  href={exportUrl}
                  className="rounded-full bg-slate-950 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800"
                >
                  Download diagnostics ZIP
                </a>
              </div>
            </div>

            {predictionLoading && <div className="mt-5 rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">Loading prediction diagnostics...</div>}
            {predictionError && <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">{predictionError}</div>}

            {!predictionLoading && !predictionError && predictions && (
              <>
                <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                  <label className="text-sm font-semibold text-slate-700">
                    Model
                    <select value={selectedDiagnosticModel} onChange={(event) => setDiagnosticModel(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                      {diagnosticModelOptions.map((model) => <option key={model} value={model}>{model}</option>)}
                    </select>
                  </label>
                  <label className="text-sm font-semibold text-slate-700">
                    Splits
                    <select value={diagnosticSplit} onChange={(event) => setDiagnosticSplit(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                      <option value="validation,test">Validation + test</option>
                      <option value="validation">Validation</option>
                      <option value="test">Test</option>
                      <option value="train">Train</option>
                      <option value="train,validation,test">All splits</option>
                    </select>
                  </label>
                  <label className="text-sm font-semibold text-slate-700">
                    Output
                    <select value={activeDiagnosticOutput} onChange={(event) => setDiagnosticOutput(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                      {predictionOutputOptions.map((output) => <option key={output.name} value={output.name}>{output.label}</option>)}
                    </select>
                  </label>
                  {isFuelCellTemplate && (
                    <label className="text-sm font-semibold text-slate-700">
                      Fuel-cell cell
                      <select value={selectedPolarizationCell} onChange={(event) => setSelectedCellId(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                        {availableCellIds.map((cell) => <option key={cell} value={cell}>{cell}</option>)}
                      </select>
                    </label>
                  )}
                  {isFuelCellTemplate && (
                    <label className="text-sm font-semibold text-slate-700">
                      Operating RH
                      <select value={selectedPolarizationRh} onChange={(event) => setSelectedRh(event.target.value)} className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                        {availableRhs.map((rh) => <option key={rh} value={String(rh)}>{rh}%</option>)}
                      </select>
                    </label>
                  )}
                </div>

                {!predictionOutputOptions.length && (
                  <Alert
                    tone="error"
                    title="Prediction outputs missing"
                    messages={[`predictions.csv does not contain *_true and *_pred columns for the approved schema outputs: ${schema.outputs.map((output) => output.label || output.name).join(', ') || 'none'}. Load a champion model with complete predictions.csv artifacts.`]}
                  />
                )}

                {!!predictionOutputOptions.length && <div className="mt-4 flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.14em]">
                  <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-emerald-800">Source: training-run predictions</span>
                  <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-slate-600">Model: {selectedDiagnosticModel || '-'}</span>
                  <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-slate-600">Splits: {diagnosticSplitLabel || '-'}</span>
                  <span className="rounded-full border border-purple-200 bg-purple-50 px-3 py-1 text-purple-800">BO replay: train + validation</span>
                </div>}

                {!!predictionOutputOptions.length && (isFuelCellTemplate ? (
                  <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50 p-4 text-sm leading-6 text-blue-900">
                    <strong>Fuel-cell recipe:</strong> polarization curves are plotted as current density on the x-axis and voltage on the y-axis. BO replay uses train + validation rows; test remains reserved for model-quality metrics.
                  </div>
                ) : (
                  <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50 p-4 text-sm leading-6 text-blue-900">
                    <strong>Generic diagnostics:</strong> default plots use parity, residuals vs predicted value, residuals grouped by approved metadata, and metrics by output/split.
                  </div>
                ))}

                {!!predictionOutputOptions.length && <details className="mt-4 rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
                  <summary className="cursor-pointer select-none font-semibold text-slate-900">How to read these diagnostics</summary>
                  <ul className="mt-3 list-disc space-y-2 pl-5 leading-6">
                    {isFuelCellTemplate && <li><strong>Polarization curve:</strong> checks whether the surrogate reproduces the physical BoL/EoL curve shape at a fixed RH and cell condition.</li>}
                    <li><strong>Parity plot:</strong> compares measured values with predicted values; points near the diagonal are better.</li>
                    <li><strong>Residual plot:</strong> reveals systematic bias; for generic projects the default x-axis is the predicted value.</li>
                  </ul>
                </details>}

                {!!predictionOutputOptions.length && <div className="mt-6 grid gap-6 xl:grid-cols-2">
                  {isFuelCellTemplate && (
                  <div className="rounded-3xl border border-slate-200 bg-[#fbfaf5] p-4">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <div>
                        <h3 className="text-lg font-semibold text-slate-950">Fuel-cell polarization curve</h3>
                        <p className="text-sm text-slate-500">Measured vs predicted BoL/EoL at fixed RH. {polarizationContext}</p>
                      </div>
                      <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-500">{polarizationRows.length} rows</span>
                    </div>
                    <Plot
                      data={asPlotData([
                        {
                          name: 'Measured BoL',
                          x: polarizationRows.map((row) => asNumber(row.bol_current_density_true)),
                          y: polarizationRows.map((row) => asNumber(row.operating_voltage)),
                          customdata: polarizationRows.map((row) => [asString(row.cell_id), asString(row.split), asNumber(row.operating_rh)]),
                          hovertemplate: '<b>Measured BoL</b><br>Cell: %{customdata[0]}<br>Split: %{customdata[1]}<br>RH: %{customdata[2]}%<br>Current density: %{x:.3f} A cm⁻²<br>Voltage: %{y:.3f} V<extra></extra>',
                          type: 'scatter',
                          mode: 'lines+markers',
                          line: { color: '#2563eb', width: 3 },
                        },
                        {
                          name: 'Predicted BoL',
                          x: polarizationRows.map((row) => asNumber(row.bol_current_density_pred)),
                          y: polarizationRows.map((row) => asNumber(row.operating_voltage)),
                          customdata: polarizationRows.map((row) => [asString(row.cell_id), asString(row.split), asNumber(row.operating_rh)]),
                          hovertemplate: '<b>Predicted BoL</b><br>Cell: %{customdata[0]}<br>Split: %{customdata[1]}<br>RH: %{customdata[2]}%<br>Predicted current density: %{x:.3f} A cm⁻²<br>Voltage: %{y:.3f} V<extra></extra>',
                          type: 'scatter',
                          mode: 'lines+markers',
                          line: { color: '#2563eb', width: 3, dash: 'dash' },
                        },
                        {
                          name: 'Measured EoL',
                          x: polarizationRows.map((row) => asNumber(row.eol_current_density_true)),
                          y: polarizationRows.map((row) => asNumber(row.operating_voltage)),
                          customdata: polarizationRows.map((row) => [asString(row.cell_id), asString(row.split), asNumber(row.operating_rh)]),
                          hovertemplate: '<b>Measured EoL</b><br>Cell: %{customdata[0]}<br>Split: %{customdata[1]}<br>RH: %{customdata[2]}%<br>Current density: %{x:.3f} A cm⁻²<br>Voltage: %{y:.3f} V<extra></extra>',
                          type: 'scatter',
                          mode: 'lines+markers',
                          line: { color: '#dc2626', width: 3 },
                        },
                        {
                          name: 'Predicted EoL',
                          x: polarizationRows.map((row) => asNumber(row.eol_current_density_pred)),
                          y: polarizationRows.map((row) => asNumber(row.operating_voltage)),
                          customdata: polarizationRows.map((row) => [asString(row.cell_id), asString(row.split), asNumber(row.operating_rh)]),
                          hovertemplate: '<b>Predicted EoL</b><br>Cell: %{customdata[0]}<br>Split: %{customdata[1]}<br>RH: %{customdata[2]}%<br>Predicted current density: %{x:.3f} A cm⁻²<br>Voltage: %{y:.3f} V<extra></extra>',
                          type: 'scatter',
                          mode: 'lines+markers',
                          line: { color: '#dc2626', width: 3, dash: 'dash' },
                        },
                      ])}
                      layout={asPlotLayout({
                        ...plotLayoutBase,
                        height: 390,
                        title: { text: polarizationContext, font: { size: 13, color: '#64748b' } },
                        xaxis: { title: { text: 'Current density / A cm⁻²' }, zeroline: false },
                        yaxis: { title: { text: 'Cell voltage / V' }, zeroline: false },
                      })}
                      config={plotConfig}
                      useResizeHandler
                      style={{ width: '100%', height: '390px' }}
                    />
                    <p className="mt-3 rounded-2xl bg-white px-4 py-3 text-xs leading-5 text-slate-600">
                      Dashed lines are model predictions; solid lines are measured data. BoL = beginning of life; EoL = end of life.
                    </p>
                  </div>
                  )}

                  <div className="rounded-3xl border border-slate-200 bg-[#fbfaf5] p-4">
                    <div className="mb-2">
                      <h3 className="text-lg font-semibold text-slate-950">Parity plot</h3>
                      <p className="text-sm text-slate-500">Predicted vs measured for {outputLabel}. Points close to the diagonal indicate better predictions.</p>
                    </div>
                    <Plot
                      data={asPlotData([
                        {
                          name: 'Predictions',
                          x: parityRows.map((row) => asNumber(row[`${activeDiagnosticOutput}_true`])),
                          y: parityRows.map((row) => asNumber(row[`${activeDiagnosticOutput}_pred`])),
                          customdata: parityRows.map((row) => [asString(row.cell_id), asString(row.split), asNumber(row.operating_rh), asNumber(row.operating_voltage)]),
                          hovertemplate: `<b>${outputLabel}</b><br>Cell: %{customdata[0]}<br>Split: %{customdata[1]}<br>RH: %{customdata[2]}%<br>Voltage: %{customdata[3]:.3f} V<br>Measured: %{x:.4g} ${outputUnit}<br>Predicted: %{y:.4g} ${outputUnit}<extra></extra>`,
                          type: 'scatter',
                          mode: 'markers',
                          marker: { color: parityRows.map((row) => asString(row.split) === 'test' ? '#dc2626' : asString(row.split) === 'validation' ? '#2563eb' : '#64748b'), size: 8, opacity: 0.78 },
                        },
                        { name: 'Ideal prediction', x: parityRows.map((row) => asNumber(row[`${activeDiagnosticOutput}_true`])), y: parityRows.map((row) => asNumber(row[`${activeDiagnosticOutput}_true`])), type: 'scatter', mode: 'lines', line: { color: '#0f172a', dash: 'dot', width: 2 } },
                      ])}
                      layout={asPlotLayout({ ...plotLayoutBase, height: 390, xaxis: { title: { text: `Measured ${outputLabel}${outputUnit ? ` (${outputUnit})` : ''}` }, zeroline: false }, yaxis: { title: { text: `Predicted ${outputLabel}${outputUnit ? ` (${outputUnit})` : ''}` }, zeroline: false } })}
                      config={plotConfig}
                      useResizeHandler
                      style={{ width: '100%', height: '390px' }}
                    />
                    <p className="mt-3 rounded-2xl bg-white px-4 py-3 text-xs leading-5 text-slate-600">
                      The dotted diagonal is the ideal prediction line. Points above it are overpredicted; points below it are underpredicted.
                    </p>
                  </div>

                  <div className="rounded-3xl border border-slate-200 bg-[#fbfaf5] p-4 xl:col-span-2">
                    <div className="mb-2 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-slate-950">Residual diagnostic</h3>
                        <p className="text-sm text-slate-500">Residual = measured − predicted. Generic projects default to predicted value on the x-axis.</p>
                      </div>
                      <label className="text-sm font-semibold text-slate-700">
                        Group by
                        <select value={diagnosticGroup} onChange={(event) => setDiagnosticGroup(event.target.value)} className="ml-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm">
                          {groupCandidates.map((candidate) => <option key={candidate} value={candidate}>{candidate.replace(/_/g, ' ')}</option>)}
                        </select>
                      </label>
                    </div>
                    <Plot
                      data={asPlotData([
                        ...uniqueValuesAsStrings(parityRows, diagnosticGroup).map((groupValue) => {
                          const rows = parityRows.filter((row) => asString(row[diagnosticGroup]) === groupValue || String(asNumber(row[diagnosticGroup])) === groupValue)
                          return {
                            name: groupValue,
                            x: rows.map((row) => asNumber(row[residualXAxisColumn])),
                            y: rows.map((row) => asNumber(row[`${activeDiagnosticOutput}_residual`])),
                            customdata: rows.map((row) => [asString(row.cell_id), asString(row.split), asNumber(row.operating_rh), asNumber(row[`${activeDiagnosticOutput}_true`]), asNumber(row[`${activeDiagnosticOutput}_pred`])]),
                            hovertemplate: `<b>${outputLabel} residual</b><br>Cell: %{customdata[0]}<br>Split: %{customdata[1]}<br>RH: %{customdata[2]}%<br>Voltage: %{x:.3f} V<br>Measured: %{customdata[3]:.4g} ${outputUnit}<br>Predicted: %{customdata[4]:.4g} ${outputUnit}<br>Residual: %{y:.4g} ${outputUnit}<extra></extra>`,
                            type: 'scatter' as const,
                            mode: 'markers' as const,
                            marker: { size: 8, opacity: 0.78 },
                          }
                        }),
                        { name: 'No error', x: parityRows.map((row) => asNumber(row[residualXAxisColumn])), y: parityRows.map(() => 0), type: 'scatter' as const, mode: 'lines' as const, line: { color: '#0f172a', dash: 'dot', width: 2 } },
                      ])}
                      layout={asPlotLayout({ ...plotLayoutBase, height: 360, xaxis: { title: { text: residualXAxisLabel }, zeroline: false }, yaxis: { title: { text: `Residual: measured − predicted${outputUnit ? ` (${outputUnit})` : ''}` }, zeroline: false } })}
                      config={plotConfig}
                      useResizeHandler
                      style={{ width: '100%', height: '360px' }}
                    />
                    <p className="mt-3 rounded-2xl bg-white px-4 py-3 text-xs leading-5 text-slate-600">
                      Positive residuals mean the model underpredicted the measured value. Negative residuals mean the model overpredicted it. The dotted line marks no error.
                    </p>
                  </div>
                </div>}

                <p className="mt-4 text-xs leading-5 text-slate-500">
                  DoE live predictions are intentionally not mixed into these validation plots yet. Generated Design Studio predictions should be labeled as served-model predictions and compared separately from training-run diagnostics.
                </p>
              </>
            )}
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-[2rem] border border-slate-200 bg-white/85 p-6 shadow-sm">
              <PanelHeader
                eyebrow="Preprocessing"
                title="Preprocessing aftermath"
                description="Fit-on-train imputation and scaling artifacts available for model-quality inspection."
              />
              <dl className="mt-5 space-y-3 text-sm">
                <div>
                  <dt className="font-semibold text-slate-700">Input imputation</dt>
                  <dd className="text-slate-600">{asString(asRecord(preprocessing.input_imputation).method) || 'median'}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-slate-700">Input scaling</dt>
                  <dd className="text-slate-600">{asString(asRecord(preprocessing.input_scaling).method) || 'minmax'}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-slate-700">Review status</dt>
                  <dd className="text-slate-600">{asString(preprocessing.review_status) || 'pending_preprocessing_approval'}</dd>
                </div>
              </dl>
            </div>

            <div className="rounded-[2rem] border border-dashed border-slate-300 bg-slate-950 p-6 text-white shadow-sm">
              <PanelHeader
                eyebrow="AI preprocessing assistant"
                title="Placeholder only"
                description="Future AI agent will propose transformations with rationale for app-dev approval. Not active yet."
                dark
              />
              <div className="mt-5 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-white/75">
                Status: {asString(assistant.status) || 'placeholder_not_active'}
              </div>
              <div className="mt-4 flex gap-2">
                <button disabled className="rounded-full bg-white/10 px-4 py-2 text-sm font-semibold text-white/40">
                  Accept proposal
                </button>
                <button disabled className="rounded-full bg-white/10 px-4 py-2 text-sm font-semibold text-white/40">
                  Reject proposal
                </button>
              </div>
              <p className="mt-3 text-xs text-white/50">No autonomous preprocessing is active in this build.</p>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
