import { useEffect, useMemo, useState } from 'react'
import type { BusinessImpactSummary, ProjectSchema } from '../lib/api'
import { getBusinessImpactSummary } from '../lib/api'
import {
  BUSINESS_IMPACT_SCENARIO_DEFAULTS,
  BUSINESS_IMPACT_SECTIONS,
  asImpactNumber,
  asImpactRange,
  businessImpactInputError,
  calculateBusinessImpactSavings,
  moneyCompact,
  type BusinessImpactScenarioField,
  type BusinessImpactScenarioInputs,
} from '../lib/businessImpactPresentation'
import { formatNumber } from '../lib/doeUtils'
import {
  EvidenceBase,
  ExperimentFunnel,
  ImpactHero,
  ImpactNarrative,
  ImpactReferences,
  ImpactSectionNav,
  OperationalImpactRow,
  ScenarioAssumptions,
  ScenarioResults,
  ScheduleComparison,
} from './impact/BusinessImpactSections'
import { Alert, PanelHeader } from './ui'

export function BusinessImpactPage({ schema }: { schema: ProjectSchema }) {
  const templateId = schema.domain_metadata?.template_id
  const isFraunhoferFuelCellDemo = schema.project_id === 'fuel_cell_demo_65248559'
  const businessImpactUnavailable = Boolean(templateId && templateId !== 'fuel_cell' && !isFraunhoferFuelCellDemo)
  const [summary, setSummary] = useState<BusinessImpactSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeSection, setActiveSection] = useState<string>(BUSINESS_IMPACT_SECTIONS[0].id)
  const [scenarioInputs, setScenarioInputs] = useState<BusinessImpactScenarioInputs>(() => ({ ...BUSINESS_IMPACT_SCENARIO_DEFAULTS }))

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

  useEffect(() => {
    if (!summary || typeof IntersectionObserver === 'undefined') return
    const sections = BUSINESS_IMPACT_SECTIONS
      .map((section) => document.getElementById(section.id))
      .filter((section): section is HTMLElement => Boolean(section))
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0]
        if (visible) setActiveSection(visible.target.id as (typeof BUSINESS_IMPACT_SECTIONS)[number]['id'])
      },
      { rootMargin: '-18% 0px -62% 0px', threshold: [0.01, 0.2, 0.5] },
    )
    sections.forEach((section) => observer.observe(section))
    return () => observer.disconnect()
  }, [summary])

  const scenario = useMemo(() => summary?.scenario ?? {}, [summary?.scenario])
  const caseStudy = summary?.case_study ?? {}
  const capacityRange = asImpactRange(scenario.external_capacity_value_saved_usd)
  const internalRange = asImpactRange(scenario.internal_direct_cost_saved_usd)
  const savingsPreview = useMemo(() => calculateBusinessImpactSavings(scenarioInputs), [scenarioInputs])
  const inputErrors = useMemo(
    () => Object.fromEntries(
      (Object.keys(scenarioInputs) as BusinessImpactScenarioField[]).map((field) => [field, businessImpactInputError(field, scenarioInputs[field])]),
    ) as Record<BusinessImpactScenarioField, string | null>,
    [scenarioInputs],
  )

  const heroStatement = useMemo(() => {
    const avoided = asImpactNumber(scenario.avoided_physical_recipes)
    const savedHours = asImpactNumber(scenario.saved_bench_hours)
    if (!summary) return ''
    return `Avoid ${avoided} physical experiment builds, reclaim ~${formatNumber(savedHours)} bench-hours, and protect ${moneyCompact(capacityRange.low)}–${moneyCompact(capacityRange.high)} of scarce test capacity.`
  }, [summary, scenario, capacityRange.low, capacityRange.high])

  function updateScenarioInput(field: BusinessImpactScenarioField, value: string) {
    setScenarioInputs((current) => ({ ...current, [field]: value }))
  }

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
    return (
      <div className="border-y border-white/[0.08] py-10" role="status">
        <div className="h-2 w-36 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full w-1/2 rounded-full bg-[#74C7F5]/70 motion-safe:animate-pulse" /></div>
        <p className="mt-4 text-sm text-slate-300">Loading impact case study...</p>
      </div>
    )
  }

  if (error || !summary) {
    return <Alert tone="error" title="Impact case study unavailable" messages={[error ?? 'No impact data returned']} />
  }

  return (
    <div className="space-y-0">
      <ImpactHero
        projectName={schema.display_name}
        caseStudyTitle={summary.title}
        heroStatement={heroStatement}
        savedBenchHours={asImpactNumber(scenario.saved_bench_hours)}
        savedBenchDays={asImpactNumber(scenario.saved_bench_days)}
        capacityRange={capacityRange}
      />

      <ImpactNarrative headline={summary.headline} />

      <ImpactSectionNav activeSection={activeSection} onNavigate={setActiveSection} />

      <section className="grid gap-10 border-b border-white/[0.08] py-9 lg:grid-cols-2 lg:gap-12 lg:py-12">
        <ExperimentFunnel rows={summary.visuals.funnel} />
        <ScheduleComparison rows={summary.visuals.time_comparison} />
      </section>

      <OperationalImpactRow scenario={scenario} internalRange={internalRange} />

      <section id="impact-roi-assumptions" className="scroll-mt-24 border-b border-white/[0.08] py-9 sm:py-12">
        <PanelHeader
          eyebrow="ROI assumptions"
          title="A transparent customer-specific savings preview"
          description="Edit the planning inputs to inspect the economic scenario. These estimates remain visibly separate from dataset evidence and realized customer outcomes."
        />
        <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,0.95fr)_minmax(24rem,1.05fr)] lg:gap-12">
          <ScenarioAssumptions inputs={scenarioInputs} errors={inputErrors} onChange={updateScenarioInput} />
          <ScenarioResults {...savingsPreview} />
        </div>
      </section>

      <EvidenceBase caseStudy={caseStudy} caveats={summary.caveats} />
      <ImpactReferences sources={summary.sources} />
    </div>
  )
}
