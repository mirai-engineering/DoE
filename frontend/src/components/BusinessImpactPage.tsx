import { useEffect, useMemo, useState } from 'react'
import type { BusinessImpactSummary, ProjectSchema } from '../lib/api'
import { getBusinessImpactSummary } from '../lib/api'
import { formatNumber } from '../lib/doeUtils'
import { Alert, PanelHeader } from './ui'

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function asRange(value: unknown): { low: number; high: number } {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return { low: 0, high: 0 }
  const record = value as Record<string, unknown>
  return { low: asNumber(record.low), high: asNumber(record.high) }
}

function moneyCompact(value: number) {
  if (value >= 1000000) return `$${formatNumber(value / 1000000)}M`
  if (value >= 1000) return `$${Math.round(value / 1000)}k`
  return `$${formatNumber(value)}`
}

function hoursLabel(hours: number) {
  if (hours >= 24) return `${formatNumber(hours / 24)} days`
  return `${formatNumber(hours)} h`
}

function ImpactMetric({ label, value, subtext }: { label: string; value: string; subtext: string }) {
  return (
    <div className="rounded-[1.8rem] border border-white/10 bg-white/10 p-5 text-white shadow-sm shadow-slate-950/20">
      <div className="text-sm font-medium text-[#74C7F5]">{label}</div>
      <div className="mt-3 text-4xl font-semibold tracking-[-0.06em]">{value}</div>
      <div className="mt-2 text-sm leading-6 text-white/65">{subtext}</div>
    </div>
  )
}

function HorizontalBar({ label, value, max, tone }: { label: string; value: number; max: number; tone: string }) {
  const width = max > 0 ? Math.max(6, Math.min(100, (value / max) * 100)) : 0
  const color = tone === 'saved' ? 'bg-[#74C7F5]' : tone === 'software' ? 'bg-[#74C7F5]' : 'bg-slate-900'
  return (
    <div>
      <div className="mb-2 flex items-end justify-between gap-4">
        <span className="text-sm font-semibold text-slate-700">{label}</span>
        <span className="text-sm font-bold text-slate-950">{formatNumber(value)}</span>
      </div>
      <div className="h-4 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  )
}

function SimpleFunnel({ rows }: { rows: Array<Record<string, unknown>> }) {
  const max = Math.max(...rows.map((row) => asNumber(row.value)), 1)
  return (
    <div className="space-y-4">
      {rows.map((row) => (
        <HorizontalBar
          key={asString(row.label)}
          label={asString(row.label)}
          value={asNumber(row.value)}
          max={max}
          tone={asString(row.tone)}
        />
      ))}
    </div>
  )
}

function TimeCapacityChart({ rows }: { rows: Array<Record<string, unknown>> }) {
  const max = Math.max(...rows.map((row) => asNumber(row.hours)), 1)
  return (
    <div className="space-y-5">
      {rows.map((row) => (
        <div key={asString(row.label)} className="border-y border-slate-400/[0.10] py-4">
          <div className="flex items-center justify-between gap-4">
            <div className="text-sm font-semibold text-slate-800">{asString(row.label)}</div>
            <div className="text-sm font-bold text-slate-950">{hoursLabel(asNumber(row.hours))}</div>
          </div>
          <div className="mt-3 h-5 overflow-hidden rounded-full bg-slate-100">
            <div
              className={`h-full rounded-full ${asString(row.label).includes('Reclaimed') ? 'bg-[#74C7F5]' : 'bg-[#74C7F5]'}`}
              style={{ width: `${Math.max(8, (asNumber(row.hours) / max) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

export function BusinessImpactPage({ schema }: { schema: ProjectSchema }) {
  const templateId = schema.domain_metadata?.template_id
  const isFraunhoferFuelCellDemo = schema.project_id === 'fuel_cell_demo_65248559'
  const businessImpactUnavailable = Boolean(templateId && templateId !== 'fuel_cell' && !isFraunhoferFuelCellDemo)
  const [summary, setSummary] = useState<BusinessImpactSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hoursPerCampaign, setHoursPerCampaign] = useState('520')
  const [hourlyCost, setHourlyCost] = useState('150')
  const [campaignsPerYear, setCampaignsPerYear] = useState('4')
  const [reductionPercent, setReductionPercent] = useState('35')

  useEffect(() => {
    let mounted = true
    async function loadImpact() {
      if (businessImpactUnavailable) {
        setLoading(false)
        setSummary(null)
        return
      }
      setLoading(true)
      setError(null)
      try {
        const data = await getBusinessImpactSummary(schema.project_id)
        if (mounted) setSummary(data)
      } catch (nextError) {
        if (mounted) setError(nextError instanceof Error ? nextError.message : 'Unable to load impact summary')
      } finally {
        if (mounted) setLoading(false)
      }
    }
    loadImpact()
    return () => {
      mounted = false
    }
  }, [schema.project_id, businessImpactUnavailable])

  const scenario = useMemo(() => summary?.scenario ?? {}, [summary?.scenario])
  const caseStudy = summary?.case_study ?? {}
  const capacityRange = asRange(scenario.external_capacity_value_saved_usd)
  const internalRange = asRange(scenario.internal_direct_cost_saved_usd)

  const savingsPreview = useMemo(() => {
    const hours = Math.max(0, Number(hoursPerCampaign) || 0)
    const cost = Math.max(0, Number(hourlyCost) || 0)
    const campaigns = Math.max(0, Number(campaignsPerYear) || 0)
    const reduction = Math.max(0, Math.min(100, Number(reductionPercent) || 0)) / 100
    const savedHoursPerCampaign = hours * reduction
    const savedCostPerCampaign = savedHoursPerCampaign * cost
    const annualizedSavings = savedCostPerCampaign * campaigns
    return { savedHoursPerCampaign, savedCostPerCampaign, annualizedSavings }
  }, [hoursPerCampaign, hourlyCost, campaignsPerYear, reductionPercent])

  const heroStatement = useMemo(() => {
    const avoided = asNumber(scenario.avoided_physical_recipes)
    const savedHours = asNumber(scenario.saved_bench_hours)
    const low = capacityRange.low
    const high = capacityRange.high
    if (!summary) return ''
    return `Avoid ${avoided} physical experiment builds, reclaim ~${formatNumber(savedHours)} bench-hours, and protect ${moneyCompact(low)}–${moneyCompact(high)} of scarce test capacity.`
  }, [summary, scenario, capacityRange.low, capacityRange.high])

  if (businessImpactUnavailable) {
    return (
      <div className="space-y-6">
        <section className="border-y border-slate-400/[0.10] py-6">
          <p className="text-xs font-bold tracking-normal text-[#74C7F5]">Business Impact</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.055em] text-slate-950">Business-impact metadata not configured</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
            This project uses the approved schema-driven workflow, but no Mirai-approved business-impact assumptions are attached yet. Add template-specific cost, capacity, and experimental-throughput metadata before showing ROI claims.
          </p>
        </section>
      </div>
    )
  }

  if (loading) {
    return <div className="border-y border-slate-400/[0.10] py-8 text-slate-300">Loading impact case study...</div>
  }

  if (error || !summary) {
    return <Alert tone="error" title="Impact case study unavailable" messages={[error ?? 'No impact data returned']} />
  }

  return (
    <div className="space-y-8">
      <section id="impact-story" className="scroll-mt-8 border-b border-slate-400/[0.07] pb-6 text-white">
        <div className="grid gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-end">
          <div>
            <p className="text-sm font-medium text-[#74C7F5]">
              Decision summary
            </p>
            <h2 className="mt-4 max-w-4xl text-4xl font-semibold tracking-[-0.07em] sm:text-5xl">
              Software-guided shortlist for physical experiments.
            </h2>
            <p className="mt-5 max-w-3xl text-lg leading-8 text-white/70">{heroStatement}</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
            <ImpactMetric
              label="Bench time saved"
              value={`~${formatNumber(asNumber(scenario.saved_bench_hours))} h`}
              subtext={`${formatNumber(asNumber(scenario.saved_bench_days))} calendar days of specialized test-station capacity.`}
            />
            <ImpactMetric
              label="Capacity protected"
              value={`${moneyCompact(capacityRange.low)}–${moneyCompact(capacityRange.high)}`}
              subtext="External testbed capacity proxy for avoided long-running characterization work."
            />
          </div>
        </div>

        <div className="mt-8 grid gap-4 text-sm text-white/70 md:grid-cols-3">
          <div className="border-t border-slate-400/[0.10] pt-5">
            <div className="mb-3 inline-flex rounded-full bg-white/10 px-3 py-1 text-xs font-semibold tracking-normal text-[#74C7F5]">
              X — Bottleneck
            </div>
            <p className="leading-6">{summary.headline.problem}</p>
          </div>
          <div className="border-t border-slate-400/[0.10] pt-5">
            <div className="mb-3 inline-flex rounded-full bg-white/10 px-3 py-1 text-xs font-semibold tracking-normal text-[#74C7F5]">
              Y — Method
            </div>
            <p className="leading-6">{summary.headline.method}</p>
          </div>
          <div className="border-t border-slate-400/[0.10] pt-5">
            <div className="mb-3 inline-flex rounded-full bg-white/10 px-3 py-1 text-xs font-semibold tracking-normal text-[#74C7F5]">
              Z — Proof
            </div>
            <p className="leading-6">{summary.headline.measured_by}</p>
          </div>
        </div>
      </section>

      <nav className="border-b border-slate-400/[0.07] pb-3" aria-label="Business Impact page sections">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="px-2 text-xs font-semibold tracking-normal text-slate-400">On this page</span>
          {[
            ['Impact story', '#impact-story'],
            ['ROI assumptions', '#impact-roi-assumptions'],
            ['Evidence', '#impact-evidence'],
            ['References', '#impact-references'],
          ].map(([label, href]) => (
            <a key={href} href={href} className="rounded-md px-3 py-1.5 font-medium text-slate-300 transition hover:bg-white/[0.035] hover:text-white">
              {label}
            </a>
          ))}
        </div>
      </nav>

      <section className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="border-t border-slate-400/[0.07] pt-6">
          <PanelHeader
            eyebrow="Experiment funnel"
            title="From thousands of ideas to fewer physical experiments"
            description="The business value is not replacing scientists. It is helping them decide which expensive physical experiments deserve the bench."
          />
          <div className="mt-6">
            <SimpleFunnel rows={summary.visuals.funnel} />
          </div>
        </div>

        <div className="border-t border-slate-400/[0.07] pt-6">
          <PanelHeader
            eyebrow="Time saved"
            title="Campaign schedule impact"
            description="Reference case: each full sample characterization can be expensive and slow. Scenario: reduce physical experiments after virtual screening."
          />
          <div className="mt-6">
            <TimeCapacityChart rows={summary.visuals.time_comparison} />
          </div>
        </div>
      </section>

      <section id="impact-roi-assumptions" className="scroll-mt-8 border-t border-slate-400/[0.07] pt-6">
        <PanelHeader
          eyebrow="ROI assumptions"
          title="Customer-specific savings preview"
          description="Pitch placeholder — not yet connected to saved experiment runs. Later, these fields can use actual campaign history from ML-Guided Design workflows."
        />
        <div className="mt-6 grid gap-4 md:grid-cols-4">
          <label className="text-sm font-semibold text-slate-700">
            Hours per DoE campaign
            <input value={hoursPerCampaign} onChange={(event) => setHoursPerCampaign(event.target.value)} type="number" min="0" className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-slate-950" />
          </label>
          <label className="text-sm font-semibold text-slate-700">
            Fully loaded hourly cost
            <input value={hourlyCost} onChange={(event) => setHourlyCost(event.target.value)} type="number" min="0" className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-slate-950" />
          </label>
          <label className="text-sm font-semibold text-slate-700">
            Campaigns per year
            <input value={campaignsPerYear} onChange={(event) => setCampaignsPerYear(event.target.value)} type="number" min="0" className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-slate-950" />
          </label>
          <label className="text-sm font-semibold text-slate-700">
            Expected reduction (%)
            <input value={reductionPercent} onChange={(event) => setReductionPercent(event.target.value)} type="number" min="0" max="100" className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-slate-950" />
          </label>
        </div>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          <div className="border-l border-slate-400/[0.10] pl-4">
            <div className="text-xs font-semibold tracking-normal text-slate-500">Hours saved / campaign</div>
            <div className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-white">~{formatNumber(savingsPreview.savedHoursPerCampaign)} h</div>
          </div>
          <div className="border-l border-slate-400/[0.10] pl-4">
            <div className="text-xs font-semibold tracking-normal text-slate-500">Cost saved / campaign</div>
            <div className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-white">{moneyCompact(savingsPreview.savedCostPerCampaign)}</div>
          </div>
          <div className="border-l border-slate-400/[0.10] pl-4">
            <div className="text-xs font-semibold tracking-normal text-slate-500">Annualized savings</div>
            <div className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-white">{moneyCompact(savingsPreview.annualizedSavings)}</div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 md:grid-cols-3">
        <div className="border-t border-slate-400/[0.07] pt-6">
          <div className="text-sm font-semibold text-slate-500">Physical recipes avoided</div>
          <div className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-white">
            {formatNumber(asNumber(scenario.avoided_physical_recipes))}
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-600">Fewer physical samples consumed in a campaign of {formatNumber(asNumber(scenario.baseline_physical_recipes))} candidate designs.</p>
        </div>
        <div className="border-t border-slate-400/[0.07] pt-6">
          <div className="text-sm font-semibold text-slate-500">Hands-on work avoided</div>
          <div className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-white">
            ~{formatNumber(asNumber(scenario.saved_hands_on_hours))} h
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-600">Setup, inspection, assembly, transfer, monitoring, and review time that scientists can redirect to better hypotheses.</p>
        </div>
        <div className="border-t border-slate-400/[0.07] pt-6">
          <div className="text-sm font-semibold text-slate-500">Internal direct savings</div>
          <div className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-white">
            {moneyCompact(internalRange.low)}–{moneyCompact(internalRange.high)}
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-600">Conservative planning proxy for avoided materials, consumables, gases, and test setup overhead.</p>
        </div>
      </section>

      <section id="impact-evidence" className="scroll-mt-8 border-t border-slate-400/[0.07] pt-6">
        <PanelHeader
          eyebrow="Evidence package"
          title="What this is based on"
          description="Investor-friendly numbers should be simple, but the assumptions must remain inspectable. These are the references and caveats behind the pitch view."
        />
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <div className="border-y border-slate-400/[0.10] py-5">
            <h3 className="text-base font-semibold text-slate-950">Reference case</h3>
            <ul className="mt-4 space-y-2 text-sm leading-6 text-slate-600">
              <li>{formatNumber(asNumber(caseStudy.physical_cells_in_paper))} physical test articles in the reference dataset; {formatNumber(asNumber(caseStudy.physical_cells_in_repo))} extracted in this repo.</li>
              <li>{formatNumber(asNumber(caseStudy.paper_polarization_curves))} measured response curves and ~{formatNumber(asNumber(caseStudy.paper_data_points))} reference data points.</li>
              <li>~{formatNumber(asNumber(caseStudy.paper_hours_per_sample))} hours per full sample characterization.</li>
              <li>~{formatNumber(asNumber(caseStudy.virtual_candidates_per_screen))} virtual candidates can be screened before committing lab work.</li>
            </ul>
          </div>
          <div className="border-y border-slate-400/[0.10] py-5">
            <h3 className="text-base font-semibold text-slate-950">Caveats for a credible pitch</h3>
            <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-600">
              {summary.caveats.map((caveat) => (
                <li key={caveat}>{caveat}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section id="impact-references" className="scroll-mt-8 border-t border-slate-400/[0.07] pt-6">
        <PanelHeader
          eyebrow="References"
          title="Meaningful sources used for the impact model"
          description="The dashboard separates direct paper facts from planning assumptions, so the ROI story can be replaced with customer-specific costs later."
        />
        <div className="mt-5 space-y-3">
          {summary.sources.map((source) => (
            <div key={source.label} className="border-t border-slate-400/[0.07] pt-4">
              <div className="text-sm font-semibold text-slate-950">{source.label}</div>
              <div className="mt-1 text-sm leading-6 text-slate-600">{source.claim}</div>
              <div className="mt-1 break-all text-xs text-[#74C7F5]">{source.url}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
