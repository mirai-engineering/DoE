import type { ReactNode } from 'react'
import type { BusinessImpactSummary } from '../../lib/api'
import {
  BUSINESS_IMPACT_SECTIONS,
  asImpactNumber,
  asImpactString,
  hoursLabel,
  moneyCompact,
  orderExperimentJourney,
  type BusinessImpactScenarioField,
  type BusinessImpactScenarioInputs,
} from '../../lib/businessImpactPresentation'
import { formatNumber } from '../../lib/doeUtils'
import { PanelHeader } from '../ui'

type Range = { low: number; high: number }

function ArrowIcon({ className = '' }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M5 12h13m-5-5 5 5-5 5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function DocumentIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className="h-4 w-4">
      <path d="M7 3.75h7l3 3v13.5H7V3.75Z" stroke="currentColor" strokeWidth="1.5" />
      <path d="M14 3.75v3h3M9.5 11h5M9.5 14.5h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

export function HeadlineMetric({ label, value, subtext, qualifier }: { label: string; value: string; subtext: string; qualifier?: string }) {
  return (
    <div className="border-t border-white/10 py-5 first:border-t-0 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-semibold text-[#BDEAFF]">{label}</p>
        {qualifier && <span className="rounded-full border border-white/10 px-2.5 py-1 text-[0.68rem] font-semibold text-[#9FB0C8]">{qualifier}</span>}
      </div>
      <p className="mt-2 whitespace-nowrap font-semibold tabular-nums tracking-[-0.065em] text-white text-[clamp(2.15rem,9vw,4.7rem)] leading-none">{value}</p>
      <p className="mt-3 max-w-xl text-sm leading-6 text-[#9FB0C8]">{subtext}</p>
    </div>
  )
}

export function ImpactHero({
  projectName,
  caseStudyTitle,
  heroStatement,
  savedBenchHours,
  savedBenchDays,
  capacityRange,
}: {
  projectName: string
  caseStudyTitle: string
  heroStatement: string
  savedBenchHours: number
  savedBenchDays: number
  capacityRange: Range
}) {
  return (
    <section id="impact-story" className="relative scroll-mt-24 overflow-hidden border-b border-white/[0.08] pb-10 pt-2 text-white sm:pb-12">
      <div aria-hidden="true" className="pointer-events-none absolute -right-40 -top-52 h-[34rem] w-[34rem] rounded-full bg-[#2F6BFF]/[0.09] blur-3xl" />
      <div className="relative grid gap-10 xl:grid-cols-[minmax(0,1.08fr)_minmax(25rem,0.92fr)] xl:items-center xl:gap-16">
        <div className="min-w-0 py-2 xl:py-8">
          <div className="flex min-w-0 items-center gap-3 text-xs font-semibold text-[#74C7F5]">
            <span className="h-px w-8 shrink-0 bg-[#74C7F5]/70" />
            <span className="uppercase tracking-[0.18em]">Decision impact</span>
          </div>
          <h1 className="mt-5 max-w-[15ch] text-[clamp(2.65rem,5.5vw,5.4rem)] font-semibold leading-[0.95] tracking-[-0.075em] text-[#F8FAFC]">
            Software-guided shortlist for physical experiments.
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-7 text-[#C7D2E4] sm:text-lg sm:leading-8">{heroStatement}</p>
          <div className="mt-7 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 text-xs text-[#7F8DA8]">
            <span className="max-w-full truncate font-semibold text-slate-300" title={projectName}>{projectName}</span>
            <span aria-hidden="true">·</span>
            <span className="max-w-full truncate" title={caseStudyTitle}>{caseStudyTitle}</span>
          </div>
        </div>

        <div className="relative rounded-[1.65rem] border border-white/[0.09] bg-[linear-gradient(145deg,#0D1B2D_0%,#081526_62%,#07111F_100%)] p-6 shadow-[0_28px_80px_rgba(0,0,0,0.28)] sm:p-8">
          <div className="mb-6 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-[#7F8DA8]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#74C7F5]" />
            Operational consequence
          </div>
          <HeadlineMetric
            label="Bench time saved"
            value={`~${formatNumber(savedBenchHours)} h`}
            subtext={`${formatNumber(savedBenchDays)} calendar days of specialized test-station capacity.`}
          />
          <HeadlineMetric
            label="Capacity protected"
            value={`${moneyCompact(capacityRange.low)}–${moneyCompact(capacityRange.high)}`}
            qualifier="Planning proxy"
            subtext="External testbed capacity proxy for avoided long-running characterization work. This is a scenario estimate, not realized customer savings."
          />
        </div>
      </div>
    </section>
  )
}

export function ImpactNarrative({ headline }: { headline: Record<string, string> }) {
  const stages = [
    { number: '01', title: 'Bottleneck', body: headline.problem },
    { number: '02', title: "Mirai's intervention", body: headline.method },
    { number: '03', title: 'Operational result', body: headline.measured_by },
  ]
  return (
    <section aria-labelledby="impact-narrative-title" className="border-b border-white/[0.07] py-7">
      <h2 id="impact-narrative-title" className="sr-only">How Mirai creates operational impact</h2>
      <ol className="grid gap-6 md:grid-cols-3 md:gap-0">
        {stages.map((stage, index) => (
          <li key={stage.number} className={`relative min-w-0 ${index > 0 ? 'md:border-l md:border-white/[0.08] md:pl-7 lg:pl-9' : ''} ${index < stages.length - 1 ? 'md:pr-7 lg:pr-9' : ''}`}>
            <div className="flex items-center gap-3">
              <span className="font-mono text-[0.7rem] font-semibold text-[#74C7F5]">{stage.number}</span>
              <h3 className="text-sm font-semibold text-white">{stage.title}</h3>
            </div>
            <p className="mt-3 text-sm leading-6 text-[#9FB0C8]">{stage.body}</p>
            {index < stages.length - 1 && <ArrowIcon className="absolute -right-3 top-1 hidden h-6 w-6 rounded-full bg-[#050914] p-1 text-[#52647D] md:block" />}
          </li>
        ))}
      </ol>
    </section>
  )
}

export function ImpactSectionNav({ activeSection, onNavigate }: { activeSection: string; onNavigate: (sectionId: string) => void }) {
  return (
    <nav className="sticky top-0 z-40 -mx-4 border-b border-white/[0.08] bg-[#050914] px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8" aria-label="Business Impact page sections">
      <div className="flex items-center gap-1 overflow-x-auto py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <span className="mr-2 hidden shrink-0 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#60708A] sm:inline">Explore impact</span>
        {BUSINESS_IMPACT_SECTIONS.map((section) => {
          const active = activeSection === section.id
          return (
            <a
              key={section.id}
              href={`#${section.id}`}
              aria-current={active ? 'location' : undefined}
              onClick={() => onNavigate(section.id)}
              className={`mirai-focus-ring relative shrink-0 rounded px-3 py-2 text-sm font-semibold transition ${active ? 'text-white after:absolute after:inset-x-3 after:-bottom-2 after:h-0.5 after:bg-[#74C7F5]' : 'text-[#8FA0B9] hover:bg-white/[0.035] hover:text-white'}`}
            >
              <span className="flex items-center gap-2">
                {active && <span className="h-1.5 w-1.5 rounded-full bg-[#74C7F5]" />}
                {section.label}
              </span>
            </a>
          )
        })}
      </div>
    </nav>
  )
}

export function ExperimentFunnel({ rows }: { rows: Array<Record<string, unknown>> }) {
  const stages = orderExperimentJourney(rows)
  return (
    <section aria-labelledby="experiment-journey-title" className="min-w-0">
      <PanelHeader
        eyebrow="Experiment journey"
        title="From physical evidence to a focused lab shortlist"
        description="The business value is not replacing scientists. It is helping them decide which expensive physical experiments deserve the bench."
      />
      <ol aria-label="Experiment selection stages" className="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {stages.map((row, index) => {
          const finalStage = asImpactString(row.tone) === 'saved'
          return (
            <li key={`${asImpactString(row.label)}-${index}`} className={`relative min-w-0 border-t px-1 pt-5 ${finalStage ? 'border-[#74C7F5] bg-gradient-to-b from-[#74C7F5]/[0.08] to-transparent sm:px-4' : 'border-white/10'}`}>
              <div className="flex items-start justify-between gap-3">
                <span className={`text-[0.65rem] font-semibold uppercase tracking-[0.16em] ${finalStage ? 'text-[#74C7F5]' : 'text-[#60708A]'}`}>Stage {index + 1}</span>
                {index < stages.length - 1 && <ArrowIcon className="h-5 w-5 shrink-0 text-[#52647D]" />}
              </div>
              <p className="mt-5 text-4xl font-semibold tabular-nums tracking-[-0.055em] text-white">{formatNumber(asImpactNumber(row.value))}</p>
              <p className={`mt-2 max-w-[15rem] text-sm font-semibold leading-5 ${finalStage ? 'text-[#BDEAFF]' : 'text-slate-200'}`}>{asImpactString(row.label)}</p>
            </li>
          )
        })}
      </ol>
      <p className="mt-5 text-xs leading-5 text-[#7F8DA8]">Stage widths are intentionally equal: historical cells, virtual recipes, prioritized recipes, and avoided recipes are different populations and are not shown as a proportional funnel.</p>
    </section>
  )
}

export function ScheduleComparison({ rows }: { rows: Array<Record<string, unknown>> }) {
  const maxHours = Math.max(...rows.map((row) => asImpactNumber(row.hours)), 1)
  return (
    <section aria-labelledby="schedule-comparison-title" className="min-w-0">
      <PanelHeader
        eyebrow="Time saved"
        title="Campaign schedule impact"
        description="Reference case: each full sample characterization can be expensive and slow. Scenario: reduce physical experiments after virtual screening."
      />
      <div className="mt-7 space-y-5" role="img" aria-label={rows.map((row) => `${asImpactString(row.label)}: ${hoursLabel(asImpactNumber(row.hours))}`).join('. ')}>
        {rows.map((row) => {
          const reclaimed = asImpactString(row.label).includes('Reclaimed')
          const width = Math.max(8, (asImpactNumber(row.hours) / maxHours) * 100)
          return (
            <div key={asImpactString(row.label)}>
              <div className="mb-2.5 flex items-end justify-between gap-4">
                <span className={`text-sm font-semibold ${reclaimed ? 'text-[#BDEAFF]' : 'text-slate-200'}`}>{asImpactString(row.label)}</span>
                <span className="whitespace-nowrap text-sm font-semibold tabular-nums text-white">{hoursLabel(asImpactNumber(row.hours))}</span>
              </div>
              <div className="h-7 overflow-hidden rounded-md bg-white/[0.055] ring-1 ring-inset ring-white/[0.04]">
                <div
                  className={`h-full rounded-md ${reclaimed ? 'bg-[linear-gradient(90deg,#2F6BFF,#74C7F5)] shadow-[0_0_28px_rgba(116,199,245,0.16)]' : 'bg-[#40516A]'}`}
                  style={{ width: `${width}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
      <p className="mt-5 text-xs leading-5 text-[#7F8DA8]">All schedule bars use the same time scale. Exact durations remain visible independently of bar length.</p>
    </section>
  )
}

export function OperationalImpactRow({ scenario, internalRange }: { scenario: Record<string, unknown>; internalRange: Range }) {
  const metrics = [
    {
      label: 'Physical recipes avoided',
      value: formatNumber(asImpactNumber(scenario.avoided_physical_recipes)),
      body: `Fewer physical samples consumed in a campaign of ${formatNumber(asImpactNumber(scenario.baseline_physical_recipes))} candidate designs.`,
    },
    {
      label: 'Hands-on work avoided',
      value: `~${formatNumber(asImpactNumber(scenario.saved_hands_on_hours))} h`,
      body: 'Setup, inspection, assembly, transfer, monitoring, and review time that scientists can redirect to better hypotheses.',
    },
    {
      label: 'Internal direct savings',
      value: `${moneyCompact(internalRange.low)}–${moneyCompact(internalRange.high)}`,
      body: 'Conservative planning proxy for avoided materials, consumables, gases, and test setup overhead.',
    },
  ]
  return (
    <section aria-labelledby="operational-impact-title" className="border-y border-white/[0.08] py-7 sm:py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-[#74C7F5]">Operational consequence</p>
          <h2 id="operational-impact-title" className="mt-1.5 text-2xl font-semibold tracking-[-0.04em] text-white">What the shortlist changes</h2>
        </div>
        <span className="rounded-full border border-white/10 px-3 py-1.5 text-xs font-semibold text-[#9FB0C8]">Campaign planning scenario</span>
      </div>
      <div className="grid gap-6 md:grid-cols-3 md:gap-0">
        {metrics.map((metric, index) => (
          <div key={metric.label} className={`${index > 0 ? 'md:border-l md:border-white/[0.09] md:pl-7 lg:pl-9' : ''} ${index < metrics.length - 1 ? 'md:pr-7 lg:pr-9' : ''}`}>
            <p className="text-sm font-semibold text-[#9FB0C8]">{metric.label}</p>
            <p className={`mt-2 whitespace-nowrap text-4xl font-semibold tabular-nums tracking-[-0.055em] ${index === 0 ? 'text-[#BDEAFF]' : 'text-white'}`}>{metric.value}</p>
            <p className="mt-3 text-sm leading-6 text-[#7F8DA8]">{metric.body}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

const inputDefinitions: Array<{ field: BusinessImpactScenarioField; label: string; unit: string; max?: number }> = [
  { field: 'hoursPerCampaign', label: 'Hours per DoE campaign', unit: 'hours' },
  { field: 'hourlyCost', label: 'Fully loaded hourly cost', unit: 'USD / hour' },
  { field: 'campaignsPerYear', label: 'Campaigns per year', unit: 'campaigns' },
  { field: 'reductionPercent', label: 'Expected reduction (%)', unit: 'percent', max: 100 },
]

export function ScenarioAssumptions({
  inputs,
  errors,
  onChange,
}: {
  inputs: BusinessImpactScenarioInputs
  errors: Record<BusinessImpactScenarioField, string | null>
  onChange: (field: BusinessImpactScenarioField, value: string) => void
}) {
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold tracking-[-0.025em] text-white">Scenario assumptions</h3>
        <span className="text-xs font-semibold text-[#7F8DA8]">Editable</span>
      </div>
      <div className="mt-6 grid gap-x-5 gap-y-4 sm:grid-cols-2">
        {inputDefinitions.map(({ field, label, unit, max }) => {
          const error = errors[field]
          const errorId = `${field}-error`
          return (
            <label key={field} htmlFor={field} className="block min-w-0 text-sm font-semibold text-slate-200">
              <span className="flex items-end justify-between gap-3">
                <span>{label}</span>
                <span className="shrink-0 text-[0.68rem] font-medium text-[#60708A]">{unit}</span>
              </span>
              <input
                id={field}
                value={inputs[field]}
                onChange={(event) => onChange(field, event.target.value)}
                type="number"
                min="0"
                max={max}
                step="any"
                aria-invalid={Boolean(error)}
                aria-describedby={error ? errorId : undefined}
                className={`mt-2.5 w-full rounded-md border bg-[#050914] px-3.5 py-3 font-medium tabular-nums text-white outline-none transition focus:ring-2 ${error ? 'border-amber-400/70 focus:border-amber-300 focus:ring-amber-300/15' : 'border-white/[0.10] focus:border-[#74C7F5] focus:ring-[#74C7F5]/20'}`}
              />
              <span id={errorId} className={`mt-1.5 block min-h-4 text-xs ${error ? 'text-amber-200' : 'text-transparent'}`} aria-live="polite" aria-hidden={!error}>{error ?? '\u00a0'}</span>
            </label>
          )
        })}
      </div>
    </div>
  )
}

export function ScenarioResults({ savedHoursPerCampaign, savedCostPerCampaign, annualizedSavings }: { savedHoursPerCampaign: number; savedCostPerCampaign: number; annualizedSavings: number }) {
  const results = [
    { label: 'Hours saved per campaign', value: `~${formatNumber(savedHoursPerCampaign)} h` },
    { label: 'Cost saved per campaign', value: moneyCompact(savedCostPerCampaign) },
    { label: 'Annualized savings', value: moneyCompact(annualizedSavings) },
  ]
  return (
    <div className="rounded-2xl border border-[#74C7F5]/15 bg-[#071629] p-6 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h3 className="text-lg font-semibold tracking-[-0.025em] text-white">Estimated annual impact</h3>
        <span className="rounded-full border border-[#74C7F5]/20 bg-[#74C7F5]/[0.06] px-3 py-1 text-[0.68rem] font-semibold text-[#BDEAFF]">Customer-configurable planning scenario</span>
      </div>
      <dl className="mt-7 space-y-5">
        {results.map((result, index) => (
          <div key={result.label} className={`flex flex-col gap-2 border-t border-white/[0.08] pt-5 sm:flex-row sm:items-end sm:justify-between ${index === 0 ? 'border-t-0 pt-0' : ''}`}>
            <dt className="text-sm font-semibold text-[#9FB0C8]">{result.label}</dt>
            <dd className={`whitespace-nowrap font-semibold tabular-nums tracking-[-0.05em] text-white ${index === results.length - 1 ? 'text-4xl text-[#BDEAFF]' : 'text-3xl'}`}>{result.value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-7 border-t border-white/[0.08] pt-5 text-xs leading-5 text-[#7F8DA8]">Pitch placeholder — not yet connected to saved experiment runs. Later, these fields can use actual campaign history from ML-Guided Design workflows.</p>
    </div>
  )
}

function EvidenceRow({ type, children }: { type: string; children: ReactNode }) {
  return (
    <li className="grid gap-2 border-t border-white/[0.08] py-4 first:border-t-0 first:pt-0 sm:grid-cols-[8.5rem_1fr]">
      <span className="text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-[#74C7F5]">{type}</span>
      <span className="text-sm leading-6 text-[#C7D2E4]">{children}</span>
    </li>
  )
}

export function EvidenceBase({ caseStudy, caveats }: { caseStudy: Record<string, number | string>; caveats: string[] }) {
  return (
    <section id="impact-evidence" className="scroll-mt-24 border-t border-white/[0.08] pt-8 sm:pt-10">
      <PanelHeader
        eyebrow="Evidence behind the impact"
        title="Proof and limitations, side by side"
        description="The impact story stays inspectable by separating published facts, repository evidence, planning capacity, and model limitations."
      />
      <div className="mt-7 grid gap-8 lg:grid-cols-2 lg:gap-12">
        <div>
          <div className="mb-5 flex items-center gap-2 text-white">
            <DocumentIcon />
            <h3 className="text-lg font-semibold">Evidence base</h3>
          </div>
          <ul>
            <EvidenceRow type="Published reference">{formatNumber(asImpactNumber(caseStudy.physical_cells_in_paper))} physical test articles in the reference dataset and {formatNumber(asImpactNumber(caseStudy.paper_polarization_curves))} measured response curves.</EvidenceRow>
            <EvidenceRow type="Published reference">~{formatNumber(asImpactNumber(caseStudy.paper_data_points))} reference data points and ~{formatNumber(asImpactNumber(caseStudy.paper_hours_per_sample))} hours per full sample characterization.</EvidenceRow>
            <EvidenceRow type="Repository audit">{formatNumber(asImpactNumber(caseStudy.physical_cells_in_repo))} extracted cells and {formatNumber(asImpactNumber(caseStudy.model_rows_in_repo))} model rows in the current local artifact.</EvidenceRow>
            <EvidenceRow type="Repository audit">Raw AST traces account for ~{formatNumber(asImpactNumber(caseStudy.raw_ast_trace_hours_in_repo))} hours of recorded bench time.</EvidenceRow>
            <EvidenceRow type="Planning capacity">~{formatNumber(asImpactNumber(caseStudy.virtual_candidates_per_screen))} virtual candidates can be screened before committing lab work.</EvidenceRow>
          </ul>
        </div>
        <div>
          <div className="mb-5 flex items-center justify-between gap-3">
            <h3 className="text-lg font-semibold text-white">Assumptions and limitations</h3>
            <span className="rounded-full border border-amber-200/15 px-2.5 py-1 text-[0.68rem] font-semibold text-amber-100/80">Read with the scenario</span>
          </div>
          <ul className="space-y-0">
            {caveats.map((caveat, index) => (
              <li key={caveat} className="grid grid-cols-[1.75rem_1fr] gap-3 border-t border-white/[0.08] py-4 first:border-t-0 first:pt-0">
                <span className="font-mono text-xs font-semibold text-amber-100/65">0{index + 1}</span>
                <span className="text-sm leading-6 text-[#C7D2E4]">{caveat}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

function sourceType(label: string): string {
  if (label.includes('Repo-audited')) return 'Dataset evidence'
  if (label.includes('day-rate')) return 'External proxy'
  return 'External reference'
}

export function ImpactReferences({ sources }: { sources: BusinessImpactSummary['sources'] }) {
  return (
    <section id="impact-references" className="scroll-mt-24 border-t border-white/[0.08] pb-6 pt-8 sm:pt-10">
      <PanelHeader
        eyebrow="References"
        title="Sources supporting the impact model"
        description="Direct paper facts remain separate from planning assumptions so customer costs can replace public proxies when available."
      />
      <div className="mt-7 divide-y divide-white/[0.08] border-y border-white/[0.08]">
        {sources.map((source) => {
          const externalUrl = /^https?:\/\//.test(source.url)
          return (
            <article key={source.label} className="grid gap-3 py-5 lg:grid-cols-[10rem_minmax(12rem,0.7fr)_minmax(0,1.3fr)] lg:gap-7">
              <div><span className="rounded-full border border-white/10 px-2.5 py-1 text-[0.68rem] font-semibold text-[#9FB0C8]">{sourceType(source.label)}</span></div>
              <h3 className="text-sm font-semibold leading-6 text-white">{source.label}</h3>
              <div className="min-w-0">
                <p className="text-sm leading-6 text-[#9FB0C8]">{source.claim}</p>
                {externalUrl ? (
                  <a href={source.url} target="_blank" rel="noreferrer" className="mirai-focus-ring mt-2 inline-flex max-w-full items-center gap-2 text-xs font-semibold text-[#74C7F5] hover:text-[#BDEAFF]">
                    Inspect source <ArrowIcon className="h-4 w-4" />
                  </a>
                ) : (
                  <span className="mt-2 block break-all font-mono text-[0.68rem] leading-5 text-[#74C7F5]">{source.url}</span>
                )}
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
