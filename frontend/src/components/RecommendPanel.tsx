import type { Dispatch, FormEvent, SetStateAction } from 'react'
import type { ProjectSchema } from '../lib/api'
import { fixedInputSummary, objectiveRows } from '../lib/batchSearchPresentation'
import { defaultVisualizationTopK, formatNumber, maxVisualizationTopK } from '../lib/doeUtils'
import type { FixedInputConfig, RecommendationRun } from '../types/doe'
import { Alert, NumberField, PanelHeader, StatusBadge, TechnicalDetails } from './ui'

export function RecommendPanel({ schema, objectiveWeights, setObjectiveWeights, fixedInputs, setFixedInputs, nCandidates, setNCandidates, tableTopK, setTableTopK, visualizationTopK, setVisualizationTopK, loading, error, warnings, recommendationRun, configurationStale, onSubmit, onViewRecommendations }: {
  schema: ProjectSchema
  objectiveWeights: Record<string, string>
  setObjectiveWeights: Dispatch<SetStateAction<Record<string, string>>>
  fixedInputs: FixedInputConfig
  setFixedInputs: Dispatch<SetStateAction<FixedInputConfig>>
  nCandidates: string
  setNCandidates: (value: string) => void
  tableTopK: string
  setTableTopK: (value: string) => void
  visualizationTopK: string
  setVisualizationTopK: (value: string) => void
  loading: boolean
  error: string | null
  warnings: string[]
  recommendationRun: RecommendationRun | null
  configurationStale: boolean
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onViewRecommendations: () => void
}) {
  const objective = objectiveRows(schema, objectiveWeights)
  const spaceSummary = fixedInputSummary(schema, fixedInputs)

  return (
    <section className="border-y border-white/[0.10] py-6 text-white">
      <PanelHeader eyebrow="Configure" title="Build a virtual screening run" description="Define the ranking objective and search space, choose the screening scale, then generate a model-ranked shortlist." dark />

      <form className="mt-7 space-y-8" onSubmit={onSubmit} aria-busy={loading}>
        <WorkflowStep number="1" title="Define what makes a strong candidate" description="Choose which predicted outcomes matter and how each should influence the ranking.">
          <div className="mt-4 overflow-x-auto" tabIndex={0}>
            <table className="min-w-full text-sm">
              <thead className="border-b border-white/[0.08] text-left text-xs text-[#9FB0C8]"><tr><th className="px-3 py-2 font-medium">Include</th><th className="px-3 py-2 font-medium">Output</th><th className="px-3 py-2 font-medium">Direction</th><th className="px-3 py-2 text-right font-medium">Weight</th><th className="px-3 py-2 font-medium">Unit</th></tr></thead>
              <tbody className="divide-y divide-white/[0.06]">
                {objective.map(({ output, included, influence }) => (
                  <tr key={output.name}>
                    <td className="px-3 py-3"><StatusBadge tone={included ? 'active' : 'neutral'}>{included ? 'Included' : 'Ignored'}</StatusBadge></td>
                    <td className="min-w-[13rem] px-3 py-3"><div className="font-semibold text-slate-100">{output.label}</div><div className="mt-1 text-xs text-slate-500">{influence}</div></td>
                    <td className="px-3 py-3 capitalize text-slate-300">{output.direction}</td>
                    <td className="px-3 py-3 text-right"><label className="sr-only" htmlFor={`weight-${output.name}`}>Weight for {output.label}</label><input id={`weight-${output.name}`} type="number" step="0.01" value={objectiveWeights[output.name] ?? ''} onChange={(event) => setObjectiveWeights((current) => ({ ...current, [output.name]: event.target.value }))} className="w-28 rounded-md border border-white/[0.12] bg-[#050914] px-3 py-2 text-right font-mono text-sm text-white outline-none focus:border-[#74C7F5] focus:ring-2 focus:ring-[#74C7F5]/20" /></td>
                    <td className="px-3 py-3 text-slate-400">{output.unit || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-sm leading-6 text-slate-400">Positive weights reward larger predictions; negative weights reward smaller predictions; zero ignores an output. Ranking scores are relative to this objective mix and are not physical measurements.</p>
        </WorkflowStep>

        <WorkflowStep number="2" title="Choose what may vary" description="Fix known conditions and allow the remaining inputs to vary within their approved schema bounds." aside={spaceSummary.label}>
          <div className="mt-4 overflow-x-auto" tabIndex={0}>
            <table className="min-w-full text-sm">
              <thead className="border-b border-white/[0.08] text-left text-xs text-[#9FB0C8]"><tr><th className="px-3 py-2 font-medium">Variable</th><th className="px-3 py-2 font-medium">Unit</th><th className="px-3 py-2 font-medium">Search mode</th><th className="px-3 py-2 text-right font-medium">Fixed value</th><th className="px-3 py-2 text-right font-medium">Schema range</th></tr></thead>
              <tbody className="divide-y divide-white/[0.06]">
                {schema.inputs.map((input) => {
                  const config = fixedInputs[input.name] ?? { enabled: false, value: '' }
                  return <tr key={input.name}><td className="min-w-[13rem] px-3 py-3 font-semibold text-slate-100">{input.label}</td><td className="px-3 py-3 text-slate-400">{input.unit || '—'}</td><td className="px-3 py-3"><label className="sr-only" htmlFor={`mode-${input.name}`}>Search mode for {input.label}</label><select id={`mode-${input.name}`} value={config.enabled ? 'fixed' : 'vary'} onChange={(event) => setFixedInputs((current) => ({ ...current, [input.name]: { ...config, enabled: event.target.value === 'fixed' } }))} className="min-w-[12rem] rounded-md border border-white/[0.12] bg-[#050914] px-3 py-2 text-sm text-white outline-none focus:border-[#74C7F5] focus:ring-2 focus:ring-[#74C7F5]/20"><option value="vary">Vary within schema bounds</option><option value="fixed">Fixed</option></select></td><td className="px-3 py-3 text-right"><label className="sr-only" htmlFor={`fixed-${input.name}`}>Fixed value for {input.label}</label><input id={`fixed-${input.name}`} type="number" min={input.min} max={input.max} step="any" value={config.value} disabled={!config.enabled} onChange={(event) => setFixedInputs((current) => ({ ...current, [input.name]: { ...config, value: event.target.value } }))} className="w-28 rounded-md border border-white/[0.12] bg-[#050914] px-3 py-2 text-right font-mono text-sm text-white outline-none focus:border-[#74C7F5] focus:ring-2 focus:ring-[#74C7F5]/20 disabled:opacity-35" /></td><td className="whitespace-nowrap px-3 py-3 text-right font-mono text-slate-400">{formatNumber(input.min)}–{formatNumber(input.max)}</td></tr>
                })}
              </tbody>
            </table>
          </div>
        </WorkflowStep>

        <WorkflowStep number="3" title="Choose the screening scale" description="Set how many virtual designs the model evaluates and how much of the ranked set is retained for review.">
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <NumberField id="n-candidates" label="Virtual candidates to score" unit="model estimates" min={1} max={100000} value={nCandidates} onChange={setNCandidates} dark />
            <NumberField id="table-top-k" label="Shortlist size" unit="results rows" min={1} max={25} value={tableTopK} onChange={setTableTopK} dark />
            <NumberField id="visualization-top-k" label="Candidates shown in visuals" unit={`API cap ${maxVisualizationTopK}`} min={5} max={maxVisualizationTopK} value={visualizationTopK || String(defaultVisualizationTopK)} onChange={setVisualizationTopK} dark />
          </div>
          <TechnicalDetails title="Search-size limits"><p>Virtual candidates are clamped from 1 to 100,000, shortlist rows from 1 to 25, and visualization rows to the existing API cap of {maxVisualizationTopK}. A larger sample does not guarantee a global optimum.</p></TechnicalDetails>
        </WorkflowStep>

        <WorkflowStep number="4" title="Run the batch search" description="Score the configured virtual candidate set and rank it using the exact objective above.">
          <div className="mt-4 flex flex-wrap items-center gap-4"><button type="submit" disabled={loading} className="rounded-md bg-[#2F6BFF] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#245CF0] disabled:cursor-not-allowed disabled:opacity-50">{loading ? 'Screening virtual candidates…' : 'Generate ranked shortlist'}</button><p className="max-w-2xl text-sm leading-6 text-amber-100">Results are model-ranked virtual candidates and require engineering review before physical testing.</p></div>
        </WorkflowStep>
      </form>

      {error && <div className="mt-5"><Alert tone="error" title="Batch search failed" messages={[error]} /></div>}
      {warnings.length > 0 && <div className="mt-5"><Alert tone="warning" title="Batch search warnings" messages={warnings} /></div>}
      {configurationStale && <div className="mt-5"><Alert tone="warning" title="Shortlist is out of date" messages={["The objective, search space, or screening scale changed after this shortlist was generated. Run Batch Search again to refresh it."]} /></div>}
      {recommendationRun && <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-l-2 border-[#74C7F5]/70 bg-[#74C7F5]/10 px-4 py-3"><p className="text-sm font-semibold text-[#BDEAFF]">{recommendationRun.recommendations.length} ranked candidates are ready for review.</p><button type="button" onClick={onViewRecommendations} className="rounded-md border border-white/[0.12] px-4 py-2 text-sm font-semibold text-white hover:bg-white/[0.06]">View results</button></div>}
    </section>
  )
}

function WorkflowStep({ number, title, description, aside, children }: { number: string; title: string; description: string; aside?: string; children: React.ReactNode }) {
  return <section className="border-t border-white/[0.09] pt-5"><div className="flex flex-wrap items-start justify-between gap-3"><div className="flex items-start gap-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#5BA8FF]/12 text-xs font-semibold text-[#BDEAFF]">{number}</span><div><h3 className="font-semibold text-slate-100">{title}</h3><p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">{description}</p></div></div>{aside && <StatusBadge tone="neutral">{aside}</StatusBadge>}</div>{children}</section>
}
