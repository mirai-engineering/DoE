import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react'
import { SignInButton, SignUpButton } from '@clerk/clerk-react'
import batteriesImage from '../../assets/batteries.png'
import coverageMapImage from '../../assets/coverage-map.png'
import electrolyzersImage from '../../assets/electrolyzers.png'
import manufacturingImage from '../../assets/manufacturing.png'
import materialsImage from '../../assets/materials.png'
import processImage from '../../assets/process.png'
import residualPlotImage from '../../assets/residual-plot.png'

const CONTACT_EMAIL = 'contact@mirai-engineeirng.com'

const NAV_ITEMS = [
  { label: 'Workflow', href: '#workflow' },
  { label: 'Data Scientist', href: '#data-scientist' },
  { label: 'Proof', href: '#proof' },
  { label: 'Test Plans', href: '#test-plans' },
  { label: 'Industries', href: '#industries' },
]

const PAIN_POINTS = [
  { icon: '⌁', symptom: 'Fragmented sources', impact: "CSV dumps, lab notebooks, LIMS exports, sensor logs, and analysis scripts that don't agree.", detail: 'Engineers spend review cycles reconciling identifiers instead of learning from experiments already paid for.', signal: 'Traceability gap' },
  { icon: '◇', symptom: 'Untraceable preprocessing', impact: 'Critical transforms live in personal code and ad-hoc spreadsheets.', detail: 'Hard to reproduce, impossible to audit, and every downstream model inherits hidden assumptions.', signal: 'Audit risk' },
  { icon: '◎', symptom: 'Hidden model risk', impact: 'Surrogates without diagnostics create overconfidence and hidden extrapolation.', detail: 'Teams need residuals, coverage, and validation context before acting on predictions.', signal: 'Trust bottleneck' },
  { icon: '△', symptom: 'Implicit trade-offs', impact: 'Performance, durability, and cost choices happen in meetings, not quantified frontiers.', detail: 'The best next test should arrive with explicit evidence, constraints, and alternatives.', signal: 'Decision drag' },
]

const STAGES = [
  { number: '1', title: 'Data Package', desc: 'Upload multi-file test-bench exports. Mirai detects schemas, units, protocols, and provenance automatically.', meta: 'v4 / 12 sources / 3 protocols' },
  { number: '2', title: 'Structured Dataset', desc: 'Unified experiment table with validated schema, unit consistency, and missingness profile.', meta: '47 vars / 320 rows / validated' },
  { number: '3', title: 'Prepare & Validate', desc: 'Outlier detection, transform logging, leakage checks, and ML-readiness scoring.', meta: '4 transforms / 2 flags resolved' },
  { number: '4', title: 'Surrogate Model', desc: 'Train, tune, and validate surrogates with cross-validation, calibration, and uncertainty estimation.', meta: 'MLP / R² 0.85 / 5-fold CV' },
  { number: '5', title: 'Virtual Test Space', desc: 'Explore thousands of feasible candidates, weigh objectives, and inspect trade-offs on response surfaces.', meta: '320 candidates / 3 objectives' },
  { number: '6', title: 'Ranked Run Plan', desc: 'Export a ranked next-experiment plan with objective deltas, uncertainty, and constraint status.', meta: '5 candidates / 2 constraints' },
]

const STORY_STAGES = [
  {
    num: '01', label: 'Tabular Experiment Data',
    headline: 'Product and process R&D already produces the data Mirai needs: rows of experiments, columns of settings, and measured outcomes.',
    body: 'Recipes, operating conditions, material choices, batch records, and test results are brought together into a clean tabular view engineers can trust.',
    metrics: ['Inputs mapped', 'Outcomes linked', 'Context preserved'],
    bg: '/assets/lab-scene.png',
  },
  {
    num: '02', label: 'Validated Surrogate Model',
    headline: 'Mirai learns the relationship between controllable variables and product or process performance.',
    body: 'The platform trains validated surrogate models on your table, checks data quality, and shows where predictions are reliable versus uncertain.',
    metrics: ['Design space learned', 'Diagnostics included', 'Uncertainty visible'],
    bg: '/assets/batteries-all.png',
  },
  {
    num: '03', label: 'Virtual What-Ifs',
    headline: 'Teams can compare thousands of possible settings before spending budget on the next physical run.',
    body: 'Mirai ranks candidates across competing objectives like yield, cost, durability, quality, and performance — using the same tabular contract across domains.',
    metrics: ['Many candidates', 'Trade-offs ranked', 'Risk flagged'],
    bg: '/assets/perfect-battery.png',
  },
  {
    num: '04', label: 'Decision-Ready Plan',
    headline: 'The result is not a dashboard. It is a ranked next-experiment plan with evidence and trade-offs attached.',
    body: 'Engineers inspect the recommendation, understand why it is suggested, and take a defensible run plan back to the lab or production floor.',
    metrics: ['Next run selected', 'Objectives balanced', 'Exportable plan'],
    bg: '/assets/optimization-dash.png',
  },
]

const PROMPTS = [
  'What preprocessing was applied to this dataset?',
  'Can I trust the ECSA-loss prediction?',
  'Which variables have the biggest quality concerns?',
  'Why is candidate C-017 ranked first?',
  'What trade-off is driving this recommendation?',
]

const ACTIVITY_LOG = [
  { action: 'Reviewed table profile', meta: '47 vars, 3 protocols' },
  { action: 'Checked preprocessing report', meta: '4 transforms applied' },
  { action: 'Read validation metrics', meta: '5-fold CV, R² 0.85' },
  { action: 'Compared candidate objectives', meta: '5 candidates, 3 objectives' },
  { action: 'Generated recommendation rationale', meta: 'C-017 selected' },
]

const PILLARS = [
  { mark: 'I', label: 'Ingest & Structure', desc: 'Auto-detect schema, units, protocols, and provenance from multi-file bench exports.' },
  { mark: 'V', label: 'Validate & Diagnose', desc: 'Cross-validation, residual analysis, calibration, and coverage maps are first-class outputs.' },
  { mark: 'R', label: 'Recommend with Trust', desc: 'Predictions include confidence intervals and extrapolation risk flags on the design space.' },
]

const CANDIDATES = [
  { id: 'C-017', perf: '+12.6%', dur: '+8.7%', cost: '-4.1%', best: true },
  { id: 'C-023', perf: '+5.4%', dur: '+12.2%', cost: '+2.3%', best: false },
  { id: 'C-008', perf: '+9.5%', dur: '-6.0%', cost: '+12.0%', best: false },
  { id: 'C-031', perf: '+2.3%', dur: '+14.0%', cost: '-3.0%', best: false },
  { id: 'C-042', perf: '+6.7%', dur: '-2.0%', cost: '+0.8%', best: false },
]

const INDUSTRIES = [
  { title: 'Processes', objectives: 'Yield, throughput, recipe settings, energy use', detail: 'Learn from tabulated process data to recommend operating windows, recipes, and robust parameter settings.', image: processImage },
  { title: 'Batteries', objectives: 'Capacity retention, fast-charge, safety margins, cost', detail: 'Balance formation protocols, material recipes, and cycle-life targets under sparse experimental budgets.', image: batteriesImage },
  { title: 'Materials', objectives: 'Strength, fatigue, corrosion, manufacturability', detail: 'Connect composition and processing variables to measured properties with traceable surrogate models.', image: materialsImage },
  { title: 'Electrolyzers', objectives: 'Efficiency, lifetime, operating window, stack cost', detail: 'Optimize operating conditions while keeping durability and degradation risks visible.', image: electrolyzersImage },
  { title: 'Advanced manufacturing', objectives: 'Yield, cycle time, defects, energy use', detail: 'Rank parameter sets for production experiments where downtime and scrap are expensive.', image: manufacturingImage },
]

const scatterPoints = Array.from({ length: 40 }, (_, i) => ({
  x: 5 + (i / 39) * 110,
  y: 95 - (i / 39) * 90 + (((i * 17) % 9) - 4) * 1.6,
}))
function scrollToHash(hash: string) {
  document.querySelector(hash)?.scrollIntoView({ behavior: 'smooth' })
}

function showDemoContactMessage(event: MouseEvent<HTMLElement>) {
  event.preventDefault()
  window.alert(`To request a demo, please write us at ${CONTACT_EMAIL}.`)
}

function Eyebrow({ children }: { children: string }) {
  return <p className="mb-4 font-mono text-[0.75rem] uppercase tracking-[0.15em] text-[#7C5CFF]">{children}</p>
}

function Meta({ children, className = '' }: { children: string; className?: string }) {
  return <p className={`font-mono text-[10px] uppercase tracking-[0.08em] text-[#8899BB] ${className}`}>{children}</p>
}

function MiraiLogo({ className = '' }: { className?: string }) {
  return <img src="/assets/mirai-mark.png" alt="Mirai" className={`h-7 w-7 rounded-md border border-slate-600 bg-[#050914] object-cover ${className}`} />
}

function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const handleNav = useCallback((event: MouseEvent<HTMLAnchorElement>) => {
    const href = event.currentTarget.getAttribute('href')
    if (!href?.startsWith('#')) return
    event.preventDefault()
    scrollToHash(href)
    setMobileOpen(false)
  }, [])

  return (
    <header className={`fixed left-0 right-0 top-0 z-50 transition-all duration-300 ${scrolled ? 'border-b border-violet-300/15 bg-[#030716]/85 backdrop-blur-lg' : 'bg-transparent'}`}>
      <nav className="mx-auto flex h-16 max-w-[1400px] items-center justify-between px-6">
        <a href="#" onClick={handleNav} className="flex items-center gap-2.5" aria-label="Mirai home">
          <MiraiLogo />
          <span className="text-sm font-medium tracking-tight text-[#F6F4EA]">Mirai</span>
        </a>

        <div className="hidden items-center gap-8 md:flex">
          {NAV_ITEMS.map((item) => (
            <a key={item.href} href={item.href} onClick={handleNav} className="text-sm text-[#C5D0E6] transition-colors duration-200 hover:text-[#F6F4EA]">{item.label}</a>
          ))}
          <a href={`mailto:${CONTACT_EMAIL}?subject=Mirai%20%E2%80%94%20Demo%20Request`} onClick={showDemoContactMessage} className="inline-flex h-9 items-center rounded-full bg-[#6D5DFB]/90 px-5 text-xs font-medium tracking-wide text-white transition-all duration-200 hover:bg-[#6D5DFB]">Request a demo</a>
        </div>

        <button onClick={() => setMobileOpen((open) => !open)} className="flex flex-col gap-1.5 p-2 md:hidden" aria-label="Toggle menu" aria-expanded={mobileOpen}>
          <span className={`block h-px w-5 bg-[#F6F4EA] transition-all ${mobileOpen ? 'translate-y-[3px] rotate-45' : ''}`} />
          <span className={`block h-px w-5 bg-[#F6F4EA] transition-all ${mobileOpen ? 'opacity-0' : ''}`} />
          <span className={`block h-px w-5 bg-[#F6F4EA] transition-all ${mobileOpen ? '-translate-y-[3px] -rotate-45' : ''}`} />
        </button>
      </nav>

      {mobileOpen && (
        <div className="border-t border-violet-300/15 bg-[#030716]/95 px-6 py-6 backdrop-blur-lg md:hidden">
          <div className="flex flex-col gap-3">
            {NAV_ITEMS.map((item) => (
              <a key={item.href} href={item.href} onClick={handleNav} className="text-sm text-[#C5D0E6] transition-colors hover:text-[#F6F4EA]">{item.label}</a>
            ))}
            <a href={`mailto:${CONTACT_EMAIL}?subject=Mirai%20%E2%80%94%20Demo%20Request`} onClick={showDemoContactMessage} className="mt-2 inline-flex h-9 items-center justify-center rounded-full bg-[#6D5DFB]/90 px-5 text-xs font-medium tracking-wide text-white">Request a demo</a>
          </div>
        </div>
      )}
    </header>
  )
}

function Hero() {
  return (
    <section className="relative min-h-[100dvh] overflow-hidden bg-[#030716]">
      <div className="absolute inset-0 lg:left-[32%]">
        <img src="/assets/hero.png" alt="" className="h-full w-full object-cover object-[82%_center] opacity-90 lg:opacity-100" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#030716] via-[#030716]/68 to-transparent lg:via-[#030716]/28" />
        <div className="absolute inset-0 bg-gradient-to-t from-[#030716]/35 via-transparent to-[#030716]/10" />
      </div>
      <div className="pointer-events-none absolute -right-1/4 top-1/3 h-1/2 w-1/2 rounded-full bg-[#6D5DFB]/10 blur-[120px]" />
      <div className="pointer-events-none absolute -bottom-1/4 left-0 h-1/2 w-1/2 rounded-full bg-[#3B82F6]/10 blur-[100px]" />

      <div className="relative mx-auto flex min-h-[100dvh] max-w-[1400px] flex-col items-start justify-center px-6 pb-20 pt-24 lg:flex-row lg:items-center lg:gap-12">
        <div className="relative z-10 w-full max-w-[540px] shrink-0 animate-fade-in-up">
          <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.18em] text-[#7C5CFF]">ML-guided product and process design</p>
          <h1 className="text-4xl font-semibold leading-[1.06] tracking-tight sm:text-5xl lg:text-[3.25rem]">
            <span className="text-[#F6F4EA]">Model better products and processes</span><br />
            <span className="text-[#7C5CFF]">before you run them.</span>
          </h1>
          <p className="mt-5 max-w-[500px] text-base leading-relaxed text-[#C5D0E6]">Mirai turns tabular experiment data — inputs, settings, recipes, and measured outcomes — into validated surrogate models and ranked next-test plans.</p>

          <div className="mt-8 flex flex-wrap gap-3">
            <a href="#cta" onClick={(event) => { event.preventDefault(); scrollToHash('#cta') }} className="inline-flex h-11 items-center rounded-full bg-[#6D5DFB]/90 px-7 text-sm font-medium tracking-wide text-white transition-all duration-200 hover:bg-[#6D5DFB]">Explore the platform</a>
            <SignInButton mode="modal">
              <button className="inline-flex h-11 items-center rounded-full border border-violet-300/30 px-7 text-sm font-medium tracking-wide text-[#C5D0E6] transition-all duration-200 hover:border-[#6D5DFB]/50 hover:text-[#F6F4EA]">Sign in</button>
            </SignInButton>
          </div>

          <div className="mt-12 grid gap-5 sm:grid-cols-3">
            {[
              { icon: '01', label: 'Any Table', desc: 'Products, processes, recipes, and outcomes' },
              { icon: '02', label: 'Validated Models', desc: 'Surrogates with diagnostics and uncertainty' },
              { icon: '03', label: 'Fewer Tests', desc: 'Virtual candidates before lab budget' },
            ].map((feature) => (
              <div key={feature.label} className="rounded-2xl border border-violet-300/15 bg-[#071126]/70 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] backdrop-blur-sm">
                <span className="font-mono text-xs tracking-[0.18em] text-[#63D7FF]">{feature.icon}</span>
                <p className="mt-2 text-sm font-semibold text-[#F6F4EA]">{feature.label}</p>
                <p className="mt-1 text-xs leading-relaxed text-[#AEBBDD]">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="hidden lg:block lg:flex-1" />
      </div>
    </section>
  )
}

function Problem() {
  return (
    <section className="relative border-t border-violet-300/15 bg-[#010412] py-16">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="grid items-start gap-12 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <Eyebrow>The problem</Eyebrow>
            <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">Physical experiments are too valuable for trial-and-error.</h2>
            <p className="mt-4 text-[15px] leading-relaxed text-[#D6DEF0]">In industrial R&amp;D, the hardest part isn't running tests — it's turning fragmented results into consistent, reusable evidence for the next decision.</p>
            <p className="mt-3 text-sm leading-relaxed text-[#AEBBDD]">Mirai keeps raw files, preprocessing decisions, model versions, and recommendations connected so teams can audit how each conclusion was produced.</p>
            <div className="mt-8 overflow-hidden rounded-2xl border border-violet-300/20 bg-[#071126] p-4 shadow-[0_0_32px_rgba(109,93,251,0.08)]">
              <div className="aspect-[1929/1440] overflow-hidden rounded-xl border border-blue-300/10 bg-[#020817]">
                <img src="/assets/problem-diagram.png" alt="Fragmented experimental sources unified into a traceable dataset" className="h-full w-full object-cover object-center opacity-95" />
              </div>
            </div>
          </div>
          <div className="grid self-start gap-4 sm:grid-cols-2 lg:col-span-3">
            {PAIN_POINTS.map((point, index) => (
              <div key={point.symptom} className="rounded-2xl border border-violet-300/20 bg-[#0A1630] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] animate-fade-in-up" style={{ animationDelay: `${index * 80}ms` }}>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-violet-300/25 bg-[#6D5DFB]/12 text-lg text-[#8E7CFF]">{point.icon}</span>
                    <Meta className="text-[#AEBBDD]">Symptom</Meta>
                  </div>
                  <span className="rounded-full border border-blue-300/15 bg-[#3B82F6]/10 px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.08em] text-[#63D7FF]">{point.signal}</span>
                </div>
                <h3 className="text-lg font-semibold text-[#F6F4EA]">{point.symptom}</h3>
                <div className="my-4 h-px bg-gradient-to-r from-[#7C5CFF]/45 via-[#3B82F6]/30 to-transparent" />
                <p className="text-sm leading-relaxed text-[#D6DEF0]">{point.impact}</p>
                <p className="mt-3 text-xs leading-relaxed text-[#AEBBDD]">{point.detail}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function Workflow() {
  return (
    <section id="workflow" className="relative border-t border-violet-300/15 bg-[#030716] py-16">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="mx-auto max-w-2xl text-center">
          <Eyebrow>The Mirai workflow</Eyebrow>
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">From fragmented data to ranked test plans.</h2>
          <p className="mt-4 text-sm leading-relaxed text-[#C5D0E6]">Each stage produces traceable artifacts that can be reviewed, reused, and improved.</p>
        </div>
        <div className="mt-12 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {STAGES.map((stage, index) => (
            <div key={stage.number} className="relative animate-fade-in-up" style={{ animationDelay: `${index * 60}ms` }}>
              {index < STAGES.length - 1 && <div className="absolute left-full top-1/2 hidden h-px w-3 -translate-y-1/2 bg-gradient-to-r from-violet-400/25 to-blue-400/5 xl:block" />}
              <div className="relative z-10 flex h-full min-h-[285px] flex-col rounded-xl border border-violet-300/15 bg-[#0A1630] p-4">
                <div className="mb-4 flex min-h-[32px] items-center gap-2">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#6D5DFB]/15 text-[11px] font-semibold text-[#7C5CFF]">{stage.number}</span>
                  <p className="text-base font-semibold leading-tight text-[#F6F4EA]">{stage.title}</p>
                </div>
                <p className="min-h-[112px] text-sm leading-relaxed text-[#D6DEF0]">{stage.desc}</p>
                <div className="mt-auto rounded-lg border border-violet-300/15 bg-[#0D1D3D]/70 px-3 py-3">
                  <div className="flex min-h-[30px] items-center justify-between gap-3">
                    <span className="font-mono text-[10px] uppercase leading-relaxed tracking-[0.08em] text-[#AEBBDD]">{stage.meta}</span>
                    <div className="h-2 w-2 shrink-0 rounded-full bg-[#7C5CFF]/60" />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function ExperimentNavigator() {
  const sectionRef = useRef<HTMLDivElement>(null)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const el = sectionRef.current
    if (!el) return
    const onScroll = () => {
      const rect = el.getBoundingClientRect()
      const total = el.offsetHeight - window.innerHeight
      setProgress(total <= 0 ? 0.5 : Math.max(0, Math.min(1, -rect.top / total)))
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const stageIdx = Math.min(STORY_STAGES.length - 1, Math.floor(progress * STORY_STAGES.length))
  const stage = STORY_STAGES[stageIdx]

  return (
    <section id="experiment-navigator" ref={sectionRef} className="relative border-t border-violet-300/15" style={{ height: '400vh' }}>
      <div className="sticky top-0 h-[100dvh] w-full overflow-hidden bg-[#010412]">
        {STORY_STAGES.map((story, index) => (
          <div key={story.num} className={`absolute inset-0 transition-opacity duration-700 ${stageIdx === index ? 'opacity-100' : 'pointer-events-none opacity-0'}`}>
            <img src={story.bg} alt="" className="h-full w-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-r from-[#030716]/90 via-[#030716]/60 to-[#030716]/40" />
            <div className="absolute inset-0 bg-gradient-to-t from-[#030716]/40 to-transparent" />
          </div>
        ))}
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-violet-400/30 to-transparent" />

        <div className="absolute bottom-8 left-6 right-6 z-20 lg:bottom-0 lg:left-0 lg:top-0 lg:flex lg:w-[440px] lg:max-w-[40vw] lg:flex-col lg:justify-center lg:px-14">
          <div className="rounded-2xl border border-white/10 bg-[#030716]/80 p-6 shadow-2xl backdrop-blur-xl lg:p-8">
            <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.22em] text-[#7C5CFF]/80">The Experiment Navigator</p>
            <div className="mb-5 flex items-center gap-2">
              {STORY_STAGES.map((item, index) => (
                <div key={item.num} className={`h-[3px] flex-1 rounded-full transition-all duration-500 ${index === stageIdx ? 'bg-[#6D5DFB] shadow-[0_0_8px_rgba(109,93,251,0.5)]' : index < stageIdx ? 'bg-[#63D7FF]/50' : 'bg-white/10'}`} />
              ))}
              <span className="ml-1 min-w-[24px] text-right font-mono text-[10px] text-white/30">{stageIdx + 1}/{STORY_STAGES.length}</span>
            </div>
            <p className="mb-2 font-mono text-[12px] uppercase tracking-[0.16em] text-[#7C5CFF]">{stage.num} / {stage.label}</p>
            <h3 className="text-[22px] font-semibold leading-snug tracking-tight text-white">{stage.headline}</h3>
            <p className="mt-3 text-[14px] leading-relaxed text-[#C5D0E6]">{stage.body}</p>
            <div className="mt-5 flex flex-wrap gap-3 border-t border-white/10 pt-4">
              {stage.metrics.map((metric) => (
                <div key={metric} className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#6D5DFB]" />
                  <span className="font-mono text-[11px] tracking-wide text-[#C5D0E6]">{metric}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {progress < 0.03 && (
          <div className="pointer-events-none absolute bottom-8 left-1/2 z-30 flex -translate-x-1/2 flex-col items-center gap-2">
            <svg width="12" height="20" viewBox="0 0 12 20" className="text-white/30"><rect x="1" y="1" width="10" height="18" rx="5" stroke="currentColor" strokeWidth="1.5" fill="none" /><circle cx="6" cy="7" r="2" fill="currentColor" className="animate-pulse-soft" /></svg>
            <span className="font-mono text-[8px] tracking-[0.2em] text-white/20">SCROLL</span>
          </div>
        )}
      </div>
    </section>
  )
}

function DataScientist() {
  return (
    <section id="data-scientist" className="relative border-t border-violet-300/15 bg-[#010412] py-20">
      <div className="pointer-events-none absolute left-1/4 right-1/4 top-0 h-px bg-gradient-to-r from-transparent via-violet-400/20 to-transparent" />
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="mb-14 text-center">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-violet-300/20 bg-[#6D5DFB]/5 px-4 py-1.5"><span className="font-mono text-[10px] tracking-wider text-[#7C5CFF]/80">AI AGENT</span></div>
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">The Mirai <span className="text-[#7C5CFF]">Data Scientist</span></h2>
          <p className="mx-auto mt-3 max-w-2xl text-base leading-relaxed text-[#C5D0E6]">A project-scoped AI agent that answers with references to your uploaded test-bench data, preprocessing choices, validation diagnostics, and optimization trade-offs.</p>
        </div>

        <div className="grid gap-5 lg:grid-cols-[280px_1fr_280px]">
          <div className="space-y-4">
            <div className="rounded-xl border border-violet-300/15 bg-[#0A1630] p-4">
              <p className="mb-3 font-mono text-[11px] uppercase tracking-wider text-[#C5D0E6]">Suggested investigations</p>
              <div className="space-y-2">
                {PROMPTS.map((prompt, index) => (
                  <div key={prompt} className={`rounded-lg border px-3 py-2.5 text-left text-xs leading-snug transition-all duration-200 ${index === 3 ? 'border-violet-400/30 bg-[#6D5DFB]/10 text-[#F6F4EA]' : 'border-violet-300/10 bg-[#0D1D3D]/50 text-[#C5D0E6]'}`}>{prompt}</div>
                ))}
              </div>
            </div>
            {[
              ['Project-scoped', 'bg-[#6D5DFB]', 'text-[#7C5CFF]'],
              ['Read-only analysis', 'bg-[#3B82F6]', 'text-[#3B82F6]'],
              ['Grounded in project artifacts', 'bg-[#D8C99B]/60', 'text-[#D8C99B]/80'],
            ].map(([label, dot, text]) => (
              <div key={label} className="flex items-center gap-2 rounded-lg border border-violet-300/15 bg-[#0A1630] px-3 py-2"><div className={`h-2 w-2 rounded-full ${dot}`} /><span className={`font-mono text-[10px] tracking-wider ${text}`}>{label}</span></div>
            ))}
          </div>

          <div className="overflow-hidden rounded-xl border border-violet-300/15 bg-[#0A1630] shadow-[0_0_30px_rgba(109,93,251,0.04)]">
            <div className="flex items-center gap-3 border-b border-violet-300/15 bg-[#0D1D3D]/60 px-5 py-3">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#6D5DFB]/15"><span className="h-2 w-2 rounded-full bg-[#7C5CFF]" /></div>
              <div className="flex-1"><p className="text-sm font-medium text-[#F6F4EA]">Mirai Data Scientist</p><p className="font-mono text-[10px] tracking-wider text-[#63D7FF]">Active · Project-scoped</p></div>
              <span className="rounded-full border border-violet-300/15 px-2.5 py-0.5 font-mono text-[8px] tracking-wider text-[#8899BB]">C-017</span>
            </div>
            <div className="space-y-5 p-5">
              <div className="flex justify-end"><div className="max-w-[75%] rounded-2xl rounded-br-sm border border-violet-300/25 bg-[#6D5DFB]/20 px-4 py-3"><p className="text-sm text-white">Why is candidate C-017 ranked first?</p></div></div>
              <div className="max-w-[88%] rounded-2xl rounded-tl-sm border border-[#111B3A] bg-[#0D1D3D] px-4 py-3.5 shadow-lg">
                <div className="mb-3 flex flex-wrap gap-1.5"><span className="rounded-full border border-cyan-300/20 bg-[#63D7FF]/10 px-2 py-0.5 font-mono text-[8px] tracking-wider text-[#63D7FF]">CITED FROM Dataset v3</span><span className="rounded-full border border-violet-300/20 bg-[#6D5DFB]/10 px-2 py-0.5 font-mono text-[8px] tracking-wider text-[#7C5CFF]">CITED FROM Transform chain</span></div>
                <p className="mb-4 text-sm leading-relaxed text-[#C5D0E6]">Candidate C-017 ranks first because it improves predicted BoL current density while keeping ECSA loss within the validated training domain.</p>
                <div className="mb-3 rounded-lg border border-violet-300/15 bg-[#6D5DFB]/10 p-3">
                  <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-[#7C5CFF]/80">Key drivers</p>
                  {[
                    ['Current Density', '+12.6%', 'text-[#63D7FF]'], ['ECSA-Loss Improvement', '-5.9%', 'text-[#7C5CFF]'], ['Estimated Cost Impact', '-4.1%', 'text-[#3B82F6]'],
                  ].map(([label, value, color]) => <div key={label} className="flex items-center justify-between"><span className="text-xs text-[#8899BB]">{label}</span><span className={`text-xs font-medium ${color}`}>{value}</span></div>)}
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    ['Acceptable', 'Surrogate Validation', 'text-[#63D7FF]'], ['96%', 'Training-Domain Coverage', 'text-[#7C5CFF]'], ['Moderate', 'Prediction Uncertainty', 'text-[#3B82F6]'],
                  ].map(([value, label, color]) => <div key={label} className="rounded-lg border border-blue-300/10 bg-[#3B82F6]/5 p-2 text-center"><p className={`text-sm font-medium ${color}`}>{value}</p><p className="mt-0.5 text-[9px] text-[#8899BB]">{label}</p></div>)}
                </div>
              </div>
            </div>
            <div className="border-t border-violet-300/15 px-4 py-3"><div className="flex items-center gap-2 rounded-lg border border-violet-300/15 bg-[#0D1D3D] px-3 py-2.5"><span className="flex-1 text-xs text-[#8899BB]">Ask about data, preprocessing, or model quality...</span><span className="font-mono text-[9px] tracking-wider text-[#7C5CFF]/60">AGENT READY</span></div></div>
            <div className="border-t border-violet-300/15 bg-[#0D1D3D]/30 px-5 py-3"><p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-[#8899BB]">Tool activity</p>{ACTIVITY_LOG.map((item, index) => <div key={item.action} className="flex items-center gap-2 text-[10px]"><div className={`h-1 w-1 rounded-full ${index < ACTIVITY_LOG.length - 1 ? 'bg-[#7C5CFF]/30' : 'bg-[#63D7FF]'}`} /><span className="text-[#C5D0E6]">{item.action}</span><span className="ml-auto text-[#8899BB]/60">{item.meta}</span></div>)}</div>
          </div>

          <div className="space-y-4">
            <img src="/assets/agent-panel.png" alt="Mirai Data Scientist project evidence panel" className="hidden rounded-xl border border-violet-300/15 object-cover opacity-90 lg:block" />
            <div className="rounded-xl border border-violet-300/15 bg-[#0A1630] p-4">
              <p className="mb-3 font-mono text-[11px] uppercase tracking-wider text-[#C5D0E6]">Surrogate model accuracy</p>
              {[
                ['BoL Current Density', '0.850', '0.318', 'Accurate'], ['EoL Current Density', '0.756', '0.278', 'Accurate'], ['BoL ECSA', '0.312', '9.80', 'Caution'], ['ECSA Loss', '0.891', '0.069', 'Strong'],
              ].map(([name, r2, mae, status]) => <div key={name} className="mb-3 flex items-center justify-between last:mb-0"><div><p className="text-xs text-[#C5D0E6]">{name}</p><p className="font-mono text-[10px] text-[#8899BB]">R² {r2} · MAE {mae}</p></div><span className="rounded border border-violet-300/15 px-2 py-0.5 font-mono text-[10px] tracking-wider text-[#63D7FF]">{status}</span></div>)}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function Proof() {
  return (
    <section id="proof" className="relative border-t border-violet-300/15 bg-[#030716] py-16">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="mx-auto max-w-2xl text-center"><Eyebrow>Product proof</Eyebrow><h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">Recommendations are only as good as the model behind them.</h2><p className="mt-4 text-sm leading-relaxed text-[#C5D0E6]">Mirai prioritizes model quality, traceability, and uncertainty — so decisions are auditable and repeatable.</p></div>
        <div className="mt-12 grid gap-4 sm:grid-cols-3">{PILLARS.map((pillar) => <div key={pillar.mark} className="rounded-xl border border-violet-300/20 bg-[#0A1630] p-6"><div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-violet-300/35 bg-[#6D5DFB]/15"><span className="text-sm font-semibold text-[#8E7CFF]">{pillar.mark}</span></div><h3 className="text-base font-semibold text-[#F6F4EA]">{pillar.label}</h3><p className="mt-2 text-sm leading-relaxed text-[#D6DEF0]">{pillar.desc}</p></div>)}</div>
        <div className="mt-8 overflow-hidden rounded-xl border border-violet-300/20 bg-[#0A1630]"><div className="border-b border-violet-300/20 px-5 py-3"><Meta className="text-[#AEBBDD]">Model trust & diagnostics</Meta></div><div className="grid gap-4 p-5 sm:grid-cols-3">
          <div className="group overflow-hidden rounded-xl border border-violet-300/15 bg-[#0D1D3D] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
            <div className="relative aspect-[16/9] overflow-hidden bg-[#020817]"><img src="/assets/generated/battery-parity-diagnostics.png" alt="Battery testing parity diagnostics" className="h-full w-full object-cover opacity-90 transition duration-500 group-hover:scale-[1.03]" /><div className="absolute inset-0 bg-gradient-to-t from-[#071126] via-[#071126]/10 to-transparent" /><svg viewBox="0 0 120 100" className="absolute inset-x-6 bottom-5 h-24 opacity-90"><line x1="12" y1="88" x2="108" y2="12" stroke="rgba(124,92,255,0.9)" strokeWidth="1.2" strokeDasharray="4,4" />{scatterPoints.slice(0, 28).map((pt, i) => <circle key={i} cx={pt.x} cy={pt.y} r="2.2" fill="rgba(99,215,255,0.78)" />)}</svg></div>
            <div className="p-4"><Meta className="mb-2 text-[#63D7FF]">Parity plot</Meta><p className="text-sm leading-relaxed text-[#D6DEF0]">Predicted vs. observed battery-test outcomes stay close to the validation diagonal before recommendations are trusted.</p></div>
          </div>
          <div className="group overflow-hidden rounded-xl border border-violet-300/15 bg-[#0D1D3D] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
            <div className="relative aspect-[16/9] overflow-hidden bg-[#071126]"><img src={residualPlotImage} alt="Battery residual plot diagnostics" className="h-full w-full object-contain object-center opacity-95 transition duration-500 group-hover:scale-[1.02]" /></div>
            <div className="p-4"><Meta className="mb-2 text-[#63D7FF]">Residual plot</Meta><p className="text-sm leading-relaxed text-[#D6DEF0]">Residual bands expose systematic drift in charge-cycle measurements before model error turns into wasted lab time.</p></div>
          </div>
          <div className="group overflow-hidden rounded-xl border border-violet-300/15 bg-[#0D1D3D] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
            <div className="relative aspect-[16/9] overflow-hidden bg-[#071126]"><img src={coverageMapImage} alt="Battery design-space coverage map" className="h-full w-full object-contain object-center opacity-95 transition duration-500 group-hover:scale-[1.02]" /></div>
            <div className="p-4"><Meta className="mb-2 text-[#63D7FF]">Coverage map</Meta><p className="text-sm leading-relaxed text-[#D6DEF0]">Coverage maps show where battery recipes are interpolation-safe and where a candidate is extrapolating beyond evidence.</p></div>
          </div>
        </div></div>
        <div className="mx-auto mt-10 max-w-2xl text-center"><div className="const-divider mb-6" /><p className="text-sm italic leading-relaxed text-[#C5D0E6]">“Mirai gave us a single source of truth from bench logs to surrogate diagnostics — so our experiment discussions became quantitative instead of anecdotal.”</p><p className="mt-3 text-xs text-[#8899BB]">R&amp;D Modeling Lead, Energy Storage (pilot)</p></div>
      </div>
    </section>
  )
}

function TestPlans() {
  return (
    <section id="test-plans" className="relative border-t border-violet-300/15 bg-[#010412] py-16">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="grid items-start gap-10 lg:grid-cols-[0.9fr_1.35fr]">
          <div>
            <Eyebrow>Decision-ready test plans</Eyebrow>
            <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">Turn validated models into ranked test plans.</h2>
            <p className="mt-4 text-[15px] leading-relaxed text-[#D6DEF0]">Mirai turns multi-objective trade-offs into clear next steps — what to run, why it matters, and what you will learn.</p>
            <ul className="mt-6 space-y-3">
              {['Evaluate thousands of feasible virtual candidates before committing lab budget.', 'Make trade-offs explicit across performance, durability, degradation, and cost.', 'Keep validation and uncertainty visible in the decision workflow.', 'Every plan links back to the dataset version, transforms, model version, and validation report used.'].map((item) => <li key={item} className="flex items-start gap-2 text-sm leading-relaxed text-[#D6DEF0]"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#7C5CFF]" />{item}</li>)}
            </ul>
          </div>
          <div>
            <div className="mb-5 overflow-hidden rounded-2xl border border-violet-300/20 bg-[#071126] p-3 shadow-[0_0_32px_rgba(109,93,251,0.08)]">
              <div className="h-[300px] overflow-hidden rounded-xl border border-blue-300/10 bg-[#020817]">
                <img src="/assets/run-plan.png" alt="Ranked Mirai run plan" className="h-full w-full object-cover object-[70%_13%] opacity-100" />
              </div>
            </div>
            <div className="overflow-hidden rounded-xl border border-violet-300/20 bg-[#0A1630]">
              <div className="flex items-center justify-between border-b border-violet-300/20 px-5 py-3">
                <div className="flex items-center gap-2"><Meta className="text-[#AEBBDD]">Recommended runs</Meta><span className="rounded-full border border-violet-300/35 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.08em] text-[#8E7CFF]">5 candidates</span></div>
                <Meta className="hidden text-[#AEBBDD] sm:block">Objectives: Performance, Durability, Cost</Meta>
              </div>
              <div className="grid grid-cols-[1fr_1fr_1fr_1fr_48px] gap-3 border-b border-violet-300/15 bg-[#0D1D3D]/65 px-5 py-2 font-mono text-[10px] uppercase tracking-[0.08em] text-[#AEBBDD]"><span>Candidate</span><span>Performance</span><span>Durability</span><span>Cost</span><span /></div>
              {CANDIDATES.map((candidate) => <div key={candidate.id} className={`grid grid-cols-[1fr_1fr_1fr_1fr_48px] gap-3 px-5 py-2.5 text-sm ${candidate.best ? 'bg-[#6D5DFB]/8' : ''}`}><span className={`font-mono text-[0.75rem] uppercase tracking-[0.08em] ${candidate.best ? 'text-[#63D7FF]' : 'text-[#F6F4EA]'}`}>{candidate.id}{candidate.best && <span className="ml-1.5 text-[9px] text-[#63D7FF]">BEST</span>}</span><span className="text-[#63D7FF]">{candidate.perf}</span><span className={candidate.dur.startsWith('-') ? 'text-[#FF8B72]' : 'text-[#D6DEF0]'}>{candidate.dur}</span><span className="text-[#D6DEF0]">{candidate.cost}</span><span className="font-mono text-[10px] uppercase tracking-[0.08em] text-[#AEBBDD]">Info</span></div>)}
              <div className="flex flex-col gap-3 border-t border-violet-300/15 px-5 py-3 sm:flex-row sm:items-center sm:justify-between"><Meta className="text-[#AEBBDD]">Model: MLP v2.4 · R²: 0.85 / 0.76 / 0.31 / 0.89</Meta><div className="flex items-center gap-2"><span className="rounded bg-[#0D1D3D] px-2 py-1 font-mono text-[9px] uppercase tracking-[0.08em] text-[#63D7FF]">Export CSV</span><span className="rounded bg-[#6D5DFB]/10 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.08em] text-[#8E7CFF]">View details</span></div></div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function Industries() {
  return (
    <section id="industries" className="relative border-t border-violet-300/15 bg-[#030716] py-16">
      <div className="mx-auto max-w-[1400px] px-6">
        <div className="mx-auto max-w-2xl text-center">
          <Eyebrow>Industries</Eyebrow>
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-4xl">Built for tabular product and process experiments where trade-offs are real.</h2>
          <p className="mt-4 text-sm leading-relaxed text-[#D6DEF0]">Start with one table of experiments. Expand across teams, projects, and sites.</p>
        </div>
        <div className="mt-12 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {INDUSTRIES.map((industry) => <div key={industry.title} className="group overflow-hidden rounded-2xl border border-violet-300/20 bg-[#071126] p-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] transition-all duration-300 hover:border-violet-300/35"><div className="aspect-[3/2] overflow-hidden rounded-xl bg-[#030716]"><img src={industry.image} alt={`${industry.title} tabular experiment optimization`} className="h-full w-full object-contain object-center opacity-95 transition duration-500 group-hover:scale-[1.01]" /></div></div>)}
        </div>
      </div>
    </section>
  )
}

function Cta() {
  return (
    <section id="cta" className="relative overflow-hidden border-t border-violet-300/15 bg-[#010412]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_20%,rgba(109,93,251,0.14),transparent_32%),radial-gradient(circle_at_82%_78%,rgba(59,130,246,0.12),transparent_34%)]" />
      <div className="relative mx-auto max-w-[1400px] px-6 py-20">
        <div className="grid items-center gap-10 lg:grid-cols-[0.95fr_1.05fr]">
          <div>
            <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.18em] text-[#7C5CFF]">Mirai</p>
            <h2 className="text-3xl font-semibold leading-tight tracking-tight text-[#F6F4EA] sm:text-[2.5rem]">Make every physical test count.</h2>
            <p className="mt-4 max-w-md text-base leading-relaxed text-[#D6DEF0]">Walk through ingestion, traceability, surrogate diagnostics, and next-experiment recommendations for a representative slice of your bench data.</p>
            <p className="mt-3 max-w-md text-sm leading-relaxed text-[#AEBBDD]">Use Mirai to turn historical experiments and process tables into a defensible ranked plan before the next expensive lab or production run.</p>
            <div className="mt-8 flex flex-wrap gap-3"><a href={`mailto:${CONTACT_EMAIL}?subject=Mirai%20%E2%80%94%20Demo%20Request`} onClick={showDemoContactMessage} className="inline-flex h-11 items-center rounded-full bg-[#6D5DFB]/90 px-8 text-sm font-medium tracking-wide text-white transition-all duration-200 hover:bg-[#6D5DFB]">Request a demo</a><SignInButton mode="modal"><button className="inline-flex h-11 items-center rounded-full border border-violet-300/30 px-7 text-sm font-medium tracking-wide text-[#D6DEF0] transition-all duration-200 hover:border-[#6D5DFB]/50 hover:text-[#F6F4EA]">Sign in to Mirai</button></SignInButton><SignUpButton mode="modal"><button className="inline-flex h-11 items-center rounded-full border border-blue-300/20 px-7 text-sm font-medium tracking-wide text-[#D6DEF0] transition-all duration-200 hover:border-[#3B82F6]/50 hover:text-[#F6F4EA]">Create account</button></SignUpButton></div>
          </div>
          <div className="overflow-hidden rounded-2xl border border-violet-300/20 bg-[#071126] p-3 shadow-[0_0_36px_rgba(109,93,251,0.12)]">
            <div className="aspect-[2560/1429] overflow-hidden rounded-xl border border-blue-300/10 bg-[#020817]">
              <img src="/assets/cta-bg.png" alt="Decision-ready Mirai run plan export" className="h-full w-full object-cover object-center opacity-100" />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  const linkGroups = [
    { title: 'Product', color: 'text-[#3B82F6]', links: [{ label: 'How it works', href: '#workflow' }, { label: 'Mirai Data Scientist', href: '#data-scientist' }, { label: 'Validation & uncertainty', href: '#proof' }, { label: 'Test plans', href: '#test-plans' }] },
    { title: 'Industries', color: 'text-[#7C5CFF]', links: INDUSTRIES.map((industry) => ({ label: industry.title, href: '#industries' })) },
    { title: 'Company', color: 'text-[#3B82F6]', links: [{ label: 'Security & governance', href: '#cta' }, { label: 'Contact', href: `mailto:${CONTACT_EMAIL}` }] },
  ]
  return (
    <footer className="border-t border-violet-300/15 bg-[#030716] py-16"><div className="mx-auto max-w-[1400px] px-6"><div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">{linkGroups.map((group) => <div key={group.title}><Meta className={`mb-3 ${group.color}`}>{group.title}</Meta><div className="flex flex-col gap-2">{group.links.map((link) => <a key={link.label} href={link.href} onClick={link.href.startsWith('#') ? (event) => { event.preventDefault(); scrollToHash(link.href) } : undefined} className="text-xs text-[#8899BB] transition-colors hover:text-[#C5D0E6]">{link.label}</a>)}</div></div>)}<div><Meta className="mb-3 text-[#7C5CFF]">Get in touch</Meta><div className="flex flex-col gap-2"><a href={`mailto:${CONTACT_EMAIL}?subject=Mirai%20%E2%80%94%20Demo%20Request`} onClick={showDemoContactMessage} className="text-xs text-[#8899BB] transition-colors hover:text-[#C5D0E6]">Request a demo</a><a href={`mailto:${CONTACT_EMAIL}`} className="text-xs text-[#8899BB] transition-colors hover:text-[#C5D0E6]">{CONTACT_EMAIL}</a></div><div className="mt-6 flex items-center gap-2"><MiraiLogo className="opacity-60" /><span className="text-[10px] text-[#8899BB]">Mirai</span></div></div></div><div className="const-divider mb-4 mt-12" /><div className="flex flex-col gap-2 text-[10px] text-[#8899BB] sm:flex-row sm:items-center sm:justify-between"><span>&copy; 2026 Mirai. All rights reserved.</span><span className="font-mono uppercase tracking-[0.08em]">Data-to-Decision for industrial R&amp;D</span></div></div></footer>
  )
}

export function LandingPage() {
  return (
    <main className="min-h-[100dvh] bg-[#030716] text-[#F6F4EA]">
      <Navbar />
      <Hero />
      <Problem />
      <Workflow />
      <ExperimentNavigator />
      <DataScientist />
      <Proof />
      <TestPlans />
      <Industries />
      <Cta />
      <Footer />
    </main>
  )
}
